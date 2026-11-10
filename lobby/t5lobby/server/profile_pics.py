"""Profile pictures (docs/ONLINE.md "Profile picture"): a picture of an account's customized fighter, shown on its
profile card to the players in the lobby.

    pic_put  {fighter, costume, size, sha256}  -> pic_go {id, chunk}
    pic_part {id, off, data}                   (base64, in order; the last part completes it)
                                               -> pic_ok {fighter, costume, sha, size}
    pic_get  {name, fighter, costume}          -> pic {name, fighter, costume, sha, size, data}
    pic_del  {fighter?, costume?}              -> pic_gone {n}

Rules:
- Accounts only, one picture per fighter and costume (1-3), at most T5L_PIC_MAX per account (the oldest goes for a
  new one), each at most T5L_PIC_MAX_KB. The upload is checked and written anew by picfmt.clean: what is stored is
  the server's own file of the pixels and nothing else (no text, no time, no profile; a file that is anything but
  the strict format is refused whole). The server cannot tell what the pixels show: `t5lobby-admin pics` lists and
  removes them, T5L_PROFILE_PICS=0 switches the feature off.
- A picture goes only to a logged-in lobby connection that announced the cap (`pic_get`, rate limited like a
  profile): never to the status port, never to a connection that has not logged in, not to a player the owner
  blocked. The profile lists what there is (`pics`: fighter, costume, sha, size) only for clients with the cap.
- Uploads are rate limited per account (T5L_PIC_UPLOADS_HOUR) and bounded in memory (one at a time per connection,
  T5L_PIC_CONCURRENT checks at once); the whole store is bounded (T5L_PIC_TOTAL_MB: no new pictures beyond it).
- The pictures live in a database file of their own next to the lobby's (T5L_PIC_DB; they can be made again by the
  launchers, so the lobby's backups leave them out). An account that is removed -- by itself ("Remove my data"),
  by the admin tool or as inactive -- loses its pictures: at once on this server, and by the hourly sweep for
  accounts another process removed. Account ids are never given again.
- An older launcher announces no cap: it gets no `pics` field and never asks. An older server has no feature
  "profile_pics": the launcher takes and sends nothing.
"""
import asyncio
import base64
import binascii
import hashlib
import logging
import re
import secrets
import sqlite3
import time

from .. import picfmt, proto
from ..proto import LobbyError
from .ratelimit import KeyedBuckets

log = logging.getLogger("t5lobby")

FEATURE = "profile_pics"
CAP = FEATURE
CHUNK = 4096                      # bytes per pic_part (base64 ~5.5 KB: under the 8 KB line limit)
UPLOAD_SECONDS = 60.0             # an upload not finished after this is dropped
COSTUMES = (1, 2, 3)
SWEEP_SECONDS = 3600.0

E_PICS_OFF = "pics_off"           # this server keeps no profile pictures
E_PIC_BAD = "pic_bad"             # not a picture of the expected format, or the bytes do not match
E_PIC_SIZE = "pic_size"           # too big / empty
E_PIC_FULL = "pic_full"           # the server's picture store is full

SCHEMA = """
CREATE TABLE IF NOT EXISTS pics (
    account_id INTEGER NOT NULL,
    fighter TEXT NOT NULL,
    costume INTEGER NOT NULL,
    sha TEXT NOT NULL,
    size INTEGER NOT NULL,
    updated REAL NOT NULL,
    png BLOB NOT NULL,
    PRIMARY KEY (account_id, fighter, costume)
);
"""


def pic_db_path(pic_db, db):
    """Where the pictures are kept: T5L_PIC_DB, else "<lobby database>-pics" (in memory with an in-memory lobby)."""
    if pic_db:
        return pic_db
    if db == ":memory:" or str(db).startswith("file:"):
        return ":memory:"
    return db + "-pics"


class PicStore:
    """The pictures' own small database (the event loop's thread and the admin tool use it)."""

    def __init__(self, path):
        self.path = path
        self.db = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL" if path != ":memory:" else "PRAGMA journal_mode=MEMORY")
        self.db.execute("PRAGMA busy_timeout=5000")
        self.db.execute("PRAGMA synchronous=NORMAL")   # (the launchers can make every picture again)
        self.db.executescript(SCHEMA)

    def close(self):
        self.db.close()

    def put(self, aid, fighter, costume, png, keep):
        """Store (replace) one picture; beyond `keep` pictures the account's oldest go. -> sha."""
        sha = hashlib.sha256(png).hexdigest()
        self.db.execute("INSERT OR REPLACE INTO pics (account_id, fighter, costume, sha, size, updated, png) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)", (aid, fighter, costume, sha, len(png), time.time(), png))
        self.db.execute("DELETE FROM pics WHERE account_id = ? AND rowid NOT IN "
                        "(SELECT rowid FROM pics WHERE account_id = ? ORDER BY updated DESC, rowid DESC LIMIT ?)",
                        (aid, aid, max(1, keep)))
        return sha

    def list(self, aid):
        return [{"fighter": r[0], "costume": r[1], "sha": r[2], "size": r[3], "at": r[4]} for r in self.db.execute(
            "SELECT fighter, costume, sha, size, updated FROM pics WHERE account_id = ? ORDER BY updated DESC", (aid,))]

    def get(self, aid, fighter, costume):
        r = self.db.execute("SELECT sha, png FROM pics WHERE account_id = ? AND fighter = ? AND costume = ?",
                            (aid, fighter, costume)).fetchone()
        return (r[0], bytes(r[1])) if r else None

    def delete(self, aid, fighter=None, costume=None):
        sql, args = "DELETE FROM pics WHERE account_id = ?", [aid]
        if fighter is not None:
            sql += " AND fighter = ?"
            args.append(fighter)
        if costume is not None:
            sql += " AND costume = ?"
            args.append(costume)
        return self.db.execute(sql, args).rowcount

    def total(self):
        """(pictures, bytes) in the store."""
        r = self.db.execute("SELECT COUNT(*), COALESCE(SUM(size), 0) FROM pics").fetchone()
        return r[0], r[1]

    def accounts(self):
        return [r[0] for r in self.db.execute("SELECT DISTINCT account_id FROM pics")]

    def sweep(self, exists):
        """Remove the pictures of accounts that are gone (`exists(account id)` -> bool). -> pictures removed."""
        n = 0
        for aid in self.accounts():
            if not exists(aid):
                n += self.delete(aid)
        return n


class ProfilePicsMixin:
    """LobbyServer's profile picture handlers. Needs self.cfg (profile_pics, pic_*), self.store, self.table."""

    def _pics_init(self):
        cfg = self.cfg
        self._pics = None
        if cfg.profile_pics:
            path = pic_db_path(cfg.pic_db, cfg.db)
            try:
                self._pics = PicStore(path)
            except (sqlite3.Error, OSError) as e:
                log.warning("profile pictures off: %s is not usable (%s)", path, e)
        per_hour = max(1, cfg.pic_uploads_hour)
        self._pic_rate = KeyedBuckets(rate=per_hour / 3600.0, burst=per_hour)
        self._pic_sem = asyncio.Semaphore(max(1, cfg.pic_concurrent))
        self._pic_swept = 0.0

    def pics_on(self):
        return getattr(self, "_pics", None) is not None

    def pics_welcome(self, conn):
        if not self.pics_on() or CAP not in conn.caps:
            return {}
        return {"profile_pics": {"max_bytes": self._pic_max_bytes(), "max": max(1, self.cfg.pic_max),
                                 "w": picfmt.MAX_W, "h": picfmt.MAX_H, "chunk": CHUNK}}

    def _pic_max_bytes(self):
        return max(1024, min(picfmt.MAX_BYTES, self.cfg.pic_max_kb * 1000))

    def _pic_key(self, msg):
        """(fighter, costume) of a request, checked."""
        fighter, costume = msg.get("fighter"), msg.get("costume")
        if not isinstance(fighter, str) or not re.fullmatch(r"[a-z0-9_]{1,24}", fighter) \
                or fighter == "random" or not self.table.valid_fighter(fighter):
            raise LobbyError(proto.E_BAD_REQUEST, "fighter: a fighter's key")
        if type(costume) is not int or costume not in COSTUMES:
            raise LobbyError(proto.E_BAD_REQUEST, "costume: 1, 2 or 3")
        return fighter, costume

    def _pics_need(self, conn):
        if not self.pics_on() or CAP not in conn.caps:
            raise LobbyError(E_PICS_OFF, "this server keeps no profile pictures")

    def _profile_pics(self, aid):
        """The `pics` field of a profile: what there is, newest first (never the pictures themselves)."""
        if not self.pics_on():
            return []
        return [{"fighter": r["fighter"], "costume": r["costume"], "sha": r["sha"], "size": r["size"]}
                for r in self._pics.list(aid)]

    def pics_forget(self, aid):
        """The account is gone: its pictures go with it."""
        if self.pics_on() and aid is not None:
            return self._pics.delete(aid)
        return 0

    def _pics_tick(self):
        """Housekeeping: uploads that stalled; hourly, the pictures of accounts another process removed."""
        if not self.pics_on():
            return
        now = time.monotonic()
        for c in self.conns:
            up = getattr(c, "pic_up", None)
            if up is not None and now - up["t"] > UPLOAD_SECONDS:
                c.pic_up = None
        if now - self._pic_swept >= SWEEP_SECONDS:
            self._pic_swept = now
            self._pic_rate.prune()
            n = self._pics.sweep(lambda aid: self.store.account_by_id(aid) is not None)
            if n:
                log.info("profile pictures: %d picture(s) of removed accounts deleted", n)

    async def h_pic_put(self, conn, msg):
        self._pics_need(conn)
        p = conn.player
        if p.account_id is None:
            raise LobbyError(proto.E_NOT_ALLOWED, "profile pictures are kept for accounts only")
        fighter, costume = self._pic_key(msg)
        size, digest = msg.get("size"), msg.get("sha256")
        if type(size) is not int or not 64 <= size <= self._pic_max_bytes():
            raise LobbyError(E_PIC_SIZE, f"a profile picture is at most {self._pic_max_bytes() // 1000} KB",
                             max_bytes=self._pic_max_bytes())
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise LobbyError(proto.E_BAD_REQUEST, "sha256: 64 lowercase hex digits")
        have = {(r["fighter"], r["costume"]): r["sha"] for r in self._pics.list(p.account_id)}
        if have.get((fighter, costume)) == digest:
            return {"t": "pic_ok", "fighter": fighter, "costume": costume, "sha": digest, "size": size, "same": True}
        if (fighter, costume) not in have and self._pics.total()[1] + size > self.cfg.pic_total_mb * 1_000_000:
            self._count("pics_refused")
            raise LobbyError(E_PIC_FULL, "the server keeps no more profile pictures right now")
        key = f"a:{p.account_id}"
        if not self._pic_rate.take(key):
            self._count("pics_refused")
            raise LobbyError(proto.E_RATE, "enough new profile pictures for now; later again",
                             retry=int(self._pic_rate.wait(key)) + 1)
        conn.pic_up = {"id": secrets.token_hex(8), "fighter": fighter, "costume": costume, "size": size,
                       "sha256": digest, "buf": bytearray(), "t": time.monotonic(), "aid": p.account_id}
        return {"t": "pic_go", "id": conn.pic_up["id"], "chunk": CHUNK}

    async def h_pic_part(self, conn, msg):
        self._pics_need(conn)
        up = getattr(conn, "pic_up", None)
        p = conn.player
        if up is None or msg.get("id") != up["id"] or p.account_id != up["aid"]:
            raise LobbyError(proto.E_STATE, "pic_put first")
        if time.monotonic() - up["t"] > UPLOAD_SECONDS:
            conn.pic_up = None
            raise LobbyError(proto.E_STATE, "the upload took too long; start again")
        data = msg.get("data")
        try:
            if not isinstance(data, str) or len(data) > CHUNK * 2:
                raise ValueError
            part = base64.b64decode(data, validate=True)
        except (ValueError, binascii.Error):
            conn.pic_up = None
            raise LobbyError(proto.E_BAD_REQUEST, "data: base64") from None
        buf = up["buf"]
        if msg.get("off") != len(buf) or not part or len(part) > CHUNK or len(buf) + len(part) > up["size"]:
            conn.pic_up = None
            raise LobbyError(proto.E_BAD_REQUEST, "parts in order, the announced size in all")
        buf += part
        if len(buf) < up["size"]:
            return None
        conn.pic_up = None
        raw = bytes(buf)
        if hashlib.sha256(raw).hexdigest() != up["sha256"]:
            raise LobbyError(E_PIC_BAD, "the picture arrived damaged; try again")
        try:
            async with self._pic_sem:
                png = await asyncio.to_thread(picfmt.clean, raw, self._pic_max_bytes())
        except picfmt.PicError as e:
            self._count("pics_refused")
            log.info("profile picture of %s refused: %s", p.name, e)
            raise LobbyError(E_PIC_BAD, "this is not a profile picture of the expected format") from None
        if conn.closed or conn.player is not p or p.account_id != up["aid"] \
                or self.store.account_by_id(up["aid"]) is None:
            return None                                # (gone while the picture was checked)
        sha = self._pics.put(up["aid"], up["fighter"], up["costume"], png, max(1, self.cfg.pic_max))
        self._count("pics_stored")
        log.info("profile picture: %s %s costume %d, %d bytes", p.name, up["fighter"], up["costume"], len(png))
        return {"t": "pic_ok", "fighter": up["fighter"], "costume": up["costume"], "sha": sha, "size": len(png)}

    async def h_pic_get(self, conn, msg):
        self._pics_need(conn)
        me = conn.player
        name = str(msg.get("name") or me.name)
        fighter, costume = self._pic_key(msg)
        row = self.store.account(name) if proto.valid_name(name) else None
        got = self._pics.get(row["id"], fighter, costume) if row is not None else None
        if got is not None and me.account_id != row["id"] and self._pic_hidden_from(row["id"], me):
            got = None
        if got is None:
            raise LobbyError(proto.E_NOT_FOUND, "no such picture")
        sha, png = got
        return {"t": "pic", "name": row["name"], "fighter": fighter, "costume": costume, "sha": sha,
                "size": len(png), "data": base64.b64encode(png).decode("ascii")}

    def _pic_hidden_from(self, owner_id, me):
        """The owner blocked this player: no picture for them."""
        try:
            if me.account_id is not None and self.store.is_blocked_by(owner_id, me.account_id):
                return True
            owner = self.by_account.get(owner_id)
            return owner is not None and self._is_blocked(owner, me)
        except Exception:      # noqa: BLE001 -- a block lookup must never show a picture by failing
            return True

    async def h_pic_del(self, conn, msg):
        self._pics_need(conn)
        p = conn.player
        if p.account_id is None:
            raise LobbyError(proto.E_NOT_ALLOWED, "profile pictures are kept for accounts only")
        if msg.get("fighter") is None and msg.get("costume") is None:
            n = self._pics.delete(p.account_id)
        elif msg.get("costume") is None:
            fighter, _ = self._pic_key(dict(msg, costume=1))
            n = self._pics.delete(p.account_id, fighter)
        else:
            n = self._pics.delete(p.account_id, *self._pic_key(msg))
        return {"t": "pic_gone", "n": n}
