"""Persistent state: accounts (salted scrypt password hashes, ratings, rank tiers), login
sessions ("remember me" tokens, stored hashed), recovery codes (stored hashed) and match
history. SQLite from the standard library; one connection used from the event loop thread.

Older databases are upgraded in place (missing columns and tables are added)."""
import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import sqlite3
import time

from .. import rating as glicko
from ..proto import name_skeleton
from ..ranks import RankState

log = logging.getLogger("t5lobby.store")


def _is_read(sql):
    head = sql.lstrip()[:7].upper()
    return head.startswith("SELECT") or head.startswith("PRAGMA") or head.startswith("WITH")

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    pw TEXT NOT NULL,
    created REAL NOT NULL,
    last_seen REAL,
    rating REAL NOT NULL, rd REAL NOT NULL, vol REAL NOT NULL,
    last_ranked REAL,
    games INTEGER NOT NULL DEFAULT 0, wins INTEGER NOT NULL DEFAULT 0,
    losses INTEGER NOT NULL DEFAULT 0, draws INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS matches (
    id TEXT PRIMARY KEY,
    created REAL NOT NULL, ended REAL,
    ranked INTEGER NOT NULL,
    p1_name TEXT, p2_name TEXT, p1_account INTEGER, p2_account INTEGER,
    build TEXT, path TEXT, rtt_ms REAL, delay INTEGER,
    status TEXT NOT NULL, winner INTEGER, score TEXT, reports TEXT, rating TEXT
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    account_id INTEGER NOT NULL,
    created REAL NOT NULL,
    last_used REAL NOT NULL,
    expires REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS recovery (
    account_id INTEGER NOT NULL,
    code_hash TEXT NOT NULL,
    created REAL NOT NULL,
    used REAL
);
CREATE TABLE IF NOT EXISTS ip_bans (
    net TEXT PRIMARY KEY,          -- an address or a CIDR network
    until REAL NOT NULL,           -- unix time
    reason TEXT,
    created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS blocks (
    account_id INTEGER NOT NULL,       -- who blocked
    blocked_id INTEGER NOT NULL,       -- the blocked account (guests cannot be blocked for good: see lobby.py)
    blocked_name TEXT NOT NULL,
    created REAL NOT NULL,
    PRIMARY KEY (account_id, blocked_id)
);
CREATE TABLE IF NOT EXISTS notices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created REAL NOT NULL,
    expires REAL NOT NULL,             -- unix time; the notice ends then
    text TEXT NOT NULL,
    cleared REAL                       -- set by `admin notice --clear`
);
CREATE TABLE IF NOT EXISTS sets (
    id TEXT PRIMARY KEY,               -- a ranked set (docs/RANKED.md "Ranked sets"): first to wins_needed games
    created REAL NOT NULL, ended REAL,
    ranked INTEGER NOT NULL,
    p1_name TEXT, p2_name TEXT, p1_account INTEGER, p2_account INTEGER,     -- P1 / P2 of every game of the set
    wins_needed INTEGER NOT NULL,
    status TEXT NOT NULL,              -- playing | confirmed | forfeit | void
    winner INTEGER,                    -- 0 = P1, 1 = P2, NULL = no winner
    score TEXT,                        -- JSON [games won by P1, by P2]
    games TEXT,                        -- JSON [{match, number, status, winner, score, reason}] in order (replays too)
    rating TEXT,                       -- JSON [P1 change, P2 change]: the one rating update of the set
    reason TEXT, blame INTEGER
);
CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY,              -- e.g. "drain": the admin tool asked for a quiet restart
    value TEXT,
    updated REAL
);
CREATE INDEX IF NOT EXISTS sessions_account ON sessions (account_id);
CREATE INDEX IF NOT EXISTS recovery_account ON recovery (account_id);
"""

# Columns added after the first release of the schema: (table, column, declaration).
RANKED_COLUMNS = [
    ("accounts", "ranked_games", "INTEGER NOT NULL DEFAULT 0"),
    ("accounts", "tier", "INTEGER NOT NULL DEFAULT 0"),
    ("accounts", "tier_since", "INTEGER NOT NULL DEFAULT 0"),
    ("accounts", "tier_peak", "INTEGER NOT NULL DEFAULT 0"),
    ("accounts", "tier_floor", "INTEGER NOT NULL DEFAULT 0"),
    ("accounts", "pw_changed", "REAL"),
    ("matches", "origin", "TEXT"),
    ("matches", "started", "REAL"),
    ("matches", "duration", "REAL"),
    ("matches", "p1_char", "TEXT"),
    ("matches", "p2_char", "TEXT"),
    ("matches", "stage", "TEXT"),
    ("matches", "reason", "TEXT"),
    ("matches", "blame", "INTEGER"),
    ("matches", "lag", "TEXT"),            # the post-game lag check (JSON): ping, expected and observed frames
    ("matches", "set_id", "TEXT"),         # a game of a ranked set (sets.id): rated with the set, not on its own
    ("matches", "set_game", "INTEGER"),    # its number in the set (1, 2, 3; a replay keeps the number)
]
# Moderation (the admin tool, docs/HOSTING.md): account bans. Address bans live in ip_bans.
MODERATION_COLUMNS = [
    ("accounts", "banned_until", "REAL"),          # unix time; PERMANENT = for ever; NULL = not banned
    ("accounts", "ban_reason", "TEXT"),
]
# What a name looks like (proto.name_skeleton): a new name may not look like an existing account's.
NAME_COLUMNS = [
    ("accounts", "name_skel", "TEXT"),
]
RANKED_INDEXES = """
CREATE INDEX IF NOT EXISTS matches_p1 ON matches (p1_account, ended);
CREATE INDEX IF NOT EXISTS matches_p2 ON matches (p2_account, ended);
CREATE INDEX IF NOT EXISTS matches_created ON matches (created);
CREATE INDEX IF NOT EXISTS sets_p1 ON sets (p1_account, ended);
CREATE INDEX IF NOT EXISTS sets_p2 ON sets (p2_account, ended);
"""
PERMANENT = 32503680000.0     # 3000-01-01: "banned for ever"

SESSION_DAYS = 30.0
RECOVERY_CODES = 8
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"     # no 0/O, 1/I/L: read off a screen, typed back


def hash_password(password, n=1 << 14, r=8, p=1):
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, maxmem=256 << 20, dklen=32)
    b64 = lambda b: base64.b64encode(b).decode("ascii")  # noqa: E731
    return f"scrypt${n}${r}${p}${b64(salt)}${b64(dk)}"


def check_password(password, stored):
    try:
        algo, n, r, p, salt, dk = stored.split("$")
        if algo != "scrypt":
            return False
        want = base64.b64decode(dk)
        got = hashlib.scrypt(password.encode("utf-8"), salt=base64.b64decode(salt), n=int(n), r=int(r),
                             p=int(p), maxmem=256 << 20, dklen=len(want))
        return hmac.compare_digest(got, want)
    except (ValueError, TypeError):
        return False


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_code(code):
    """'abcd-efgh-jkmn' / 'ABCD EFGH JKMN' -> 'ABCDEFGHJKMN'."""
    return "".join(ch for ch in str(code).upper() if ch.isalnum())


def new_recovery_code():
    raw = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(12))      # ~59 bits
    return f"{raw[:4]}-{raw[4:8]}-{raw[8:]}"


def _private(path):
    """Password hashes live in the database: no access for other users of the machine (POSIX). The systemd
    unit's UMask=0077 does this for a service install; "Host for friends" on Linux/macOS, Docker and a hand
    start inherit the user's umask (often 022: everybody may read). SQLite gives the -wal/-shm files the
    database's mode. The group keeps what it had (an admin group setup)."""
    if path == ":memory:" or str(path).startswith("file:") or os.name == "nt":
        return
    for p in (path, path + "-wal", path + "-shm"):
        try:
            st = os.stat(p)
            if st.st_mode & 0o007:
                os.chmod(p, st.st_mode & 0o770)
        except OSError:
            pass


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL" if path != ":memory:" else "PRAGMA journal_mode=MEMORY")
        self.db.execute("PRAGMA busy_timeout=5000")    # the admin tool may hold the write lock briefly
        self.db.execute("PRAGMA synchronous=FULL")     # a committed result survives a power cut, not only a crash
        self.db.executescript(SCHEMA)
        _private(path)
        self._add_columns()
        self.db.executescript(RANKED_INDEXES)
        self._backfill_skeletons()
        self._schedule = None
        self.commit_errors = 0
        self.writes = 0

    def _add_columns(self):
        for table, col, decl in RANKED_COLUMNS + MODERATION_COLUMNS + NAME_COLUMNS:
            have = {r["name"] for r in self.db.execute(f"PRAGMA table_info({table})")}
            if col not in have:
                self.db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
        self.db.execute("CREATE INDEX IF NOT EXISTS accounts_skel ON accounts (name_skel)")

    def _backfill_skeletons(self):
        rows = self.db.execute("SELECT id, name FROM accounts WHERE name_skel IS NULL").fetchall()
        if rows:
            self.db.execute("BEGIN")
            self.db.executemany("UPDATE accounts SET name_skel = ? WHERE id = ?",
                                [(name_skeleton(r["name"]), r["id"]) for r in rows])
            self.db.execute("COMMIT")

    # ----------------------------------------------------------------- writes and transactions
    # Alone (admin tool, tests) every statement commits by itself. The server calls defer_commits():
    # then everything one event-loop callback writes is one transaction, committed right after that
    # callback (loop.call_soon) -- before the messages it queued reach any socket. A crash loses at
    # most that callback's writes and never applies half of them: a ranked result updates both
    # accounts and the match row together, or not at all (before, a crash between the statements left
    # one player's rating changed and the match "playing" for ever).
    def defer_commits(self, schedule):
        self._schedule = schedule

    def _x(self, sql, args=()):
        if not _is_read(sql):
            self.writes += 1                  # (anything cached from the database is stale now)
            if self._schedule is not None and not self.db.in_transaction:
                self.db.execute("BEGIN IMMEDIATE")
                self._schedule(self.flush)
        return self.db.execute(sql, args)

    def _xmany(self, sql, rows):
        self.writes += 1
        if self._schedule is not None and not self.db.in_transaction:
            self.db.execute("BEGIN IMMEDIATE")
            self._schedule(self.flush)
        return self.db.executemany(sql, rows)

    def flush(self):
        """Commit what the server wrote since the last commit (also called before a backup and at stop)."""
        if not self.db.in_transaction:
            return
        try:
            self.db.execute("COMMIT")
        except sqlite3.Error as e:
            self.commit_errors += 1
            log.error("database commit failed, the last changes are lost: %s", e)
            try:
                self.db.execute("ROLLBACK")
            except sqlite3.Error:
                pass

    def close(self):
        self.flush()
        self.db.close()

    # ----------------------------------------------------------------- after a crash or restart
    def void_interrupted(self, now=None):
        """Matches the database still shows as running: the server stopped (crash, restart, update)
        while they were played, and nobody can report them now. Void them: no rating change, no
        blame. -> how many."""
        now = now or time.time()
        n = self._x("UPDATE matches SET status = 'void', reason = 'server_restart', ended = ?, "
                    "duration = CASE WHEN started IS NOT NULL THEN ROUND(? - started, 1) END "
                    "WHERE status = 'playing'", (now, now)).rowcount
        self.flush()
        return n

    # ----------------------------------------------------------------- flags (admin tool -> server)
    def get_flag(self, key):
        r = self._x("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
        return r[0] if r else None

    def set_flag(self, key, value):
        if value is None:
            self._x("DELETE FROM kv WHERE key = ?", (key,))
        else:
            self._x("INSERT OR REPLACE INTO kv (key, value, updated) VALUES (?, ?, ?)", (key, str(value), time.time()))

    # ----------------------------------------------------------------- accounts
    def account(self, name):
        return self._x("SELECT * FROM accounts WHERE name = ?", (name,)).fetchone()

    def account_by_id(self, aid):
        return self._x("SELECT * FROM accounts WHERE id = ?", (aid,)).fetchone()

    def create_account(self, name, pw_hash):
        """-> row, or None when the name exists (any case)."""
        try:
            self._x(
                "INSERT INTO accounts (name, pw, created, rating, rd, vol, name_skel) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (name, pw_hash, time.time(), glicko.DEFAULT_R, glicko.DEFAULT_RD, glicko.DEFAULT_VOL,
                 name_skeleton(name)))
        except sqlite3.IntegrityError:
            return None
        return self.account(name)

    def similar_account(self, name):
        """The name of another account that looks like `name` (same proto.name_skeleton), or None."""
        r = self._x("SELECT name FROM accounts WHERE name_skel = ? AND name != ? LIMIT 1",
                    (name_skeleton(name), name)).fetchone()
        return r[0] if r else None

    def touch(self, aid):
        self._x("UPDATE accounts SET last_seen = ? WHERE id = ?", (time.time(), aid))

    def set_password(self, aid, pw_hash):
        self._x("UPDATE accounts SET pw = ?, pw_changed = ? WHERE id = ?", (pw_hash, time.time(), aid))

    def rating(self, aid):
        """Current Rating with inactivity RD growth applied."""
        row = self.account_by_id(aid)
        rt = glicko.Rating(row["rating"], row["rd"], row["vol"])
        if row["last_ranked"]:
            rt = glicko.inflate(rt, (time.time() - row["last_ranked"]) / 86400.0)
        return rt

    def rank_state(self, aid):
        row = self.account_by_id(aid)
        return RankState(row["tier"], row["ranked_games"], row["tier_since"], row["tier_peak"], row["tier_floor"])

    def set_rating(self, aid, rt, outcome, rank=None):
        col = {"win": "wins", "loss": "losses", "draw": "draws"}[outcome]
        self._x(
            f"UPDATE accounts SET rating = ?, rd = ?, vol = ?, last_ranked = ?, games = games + 1, "
            f"ranked_games = ranked_games + 1, {col} = {col} + 1 WHERE id = ?",
            (rt.r, rt.rd, rt.vol, time.time(), aid))
        if rank is not None:
            self._x("UPDATE accounts SET tier = ?, tier_since = ?, tier_peak = ?, tier_floor = ? WHERE id = ?",
                            (rank.tier, rank.since_change, rank.peak, rank.floor, aid))

    def add_unranked_game(self, aid, outcome):
        col = {"win": "wins", "loss": "losses", "draw": "draws"}[outcome]
        self._x(f"UPDATE accounts SET games = games + 1, {col} = {col} + 1 WHERE id = ?", (aid,))

    def leaderboard(self, limit=20, offset=0):
        rows = [dict(r) for r in self._x(
            "SELECT id, name, rating, rd, games, ranked_games, wins, losses, draws, tier, tier_peak FROM accounts "
            "WHERE ranked_games > 0 ORDER BY rating - 2 * rd DESC, rating DESC LIMIT ? OFFSET ?", (limit, offset))]
        for i, r in enumerate(rows):
            r["place"] = offset + i + 1
            r["main"] = self.main_char(r.pop("id"))
        return rows

    # ----------------------------------------------------------------- sessions ("remember me")
    def create_session(self, aid, days=SESSION_DAYS):
        """New login token for `aid`; only its hash is stored. -> the token (hex)."""
        token = secrets.token_hex(32)
        now = time.time()
        self._x("INSERT INTO sessions (token_hash, account_id, created, last_used, expires) "
                        "VALUES (?, ?, ?, ?, ?)", (_sha(token), aid, now, now, now + days * 86400.0))
        return token

    def session_account(self, token, days=SESSION_DAYS):
        """Account row for a valid token (sliding expiry), else None."""
        if not isinstance(token, str) or len(token) != 64:
            return None
        h = _sha(token)
        row = self._x("SELECT * FROM sessions WHERE token_hash = ?", (h,)).fetchone()
        now = time.time()
        if row is None:
            return None
        if row["expires"] < now:
            self._x("DELETE FROM sessions WHERE token_hash = ?", (h,))
            return None
        self._x("UPDATE sessions SET last_used = ?, expires = ? WHERE token_hash = ?",
                        (now, now + days * 86400.0, h))
        return self.account_by_id(row["account_id"])

    def revoke_session(self, token):
        if isinstance(token, str):
            self._x("DELETE FROM sessions WHERE token_hash = ?", (_sha(token),))

    def revoke_sessions(self, aid, keep=None):
        """Log out every remembered login of `aid` (except the token `keep`)."""
        if keep:
            self._x("DELETE FROM sessions WHERE account_id = ? AND token_hash != ?", (aid, _sha(keep)))
        else:
            self._x("DELETE FROM sessions WHERE account_id = ?", (aid,))

    def session_count(self, aid):
        return self._x("SELECT COUNT(*) FROM sessions WHERE account_id = ?", (aid,)).fetchone()[0]

    def prune_sessions(self):
        self._x("DELETE FROM sessions WHERE expires < ?", (time.time(),))

    # ----------------------------------------------------------------- recovery codes
    def issue_recovery_codes(self, aid, n=RECOVERY_CODES):
        """A fresh set of one-time codes (the old set stops working). -> the codes, shown once."""
        codes = [new_recovery_code() for _ in range(n)]
        now = time.time()
        self._x("DELETE FROM recovery WHERE account_id = ?", (aid,))
        self._xmany("INSERT INTO recovery (account_id, code_hash, created) VALUES (?, ?, ?)",
                            [(aid, _sha(normalize_code(c)), now) for c in codes])
        return codes

    def use_recovery_code(self, aid, code):
        """Consume one code of `aid`. -> True when it was valid and unused."""
        h = _sha(normalize_code(code))
        cur = self._x("UPDATE recovery SET used = ? WHERE account_id = ? AND code_hash = ? AND used IS NULL",
                              (time.time(), aid, h))
        return cur.rowcount == 1

    def recovery_left(self, aid):
        return self._x("SELECT COUNT(*) FROM recovery WHERE account_id = ? AND used IS NULL",
                               (aid,)).fetchone()[0]

    # ----------------------------------------------------------------- matches
    def save_match(self, m):
        self._x(
            "INSERT OR REPLACE INTO matches (id, created, ended, ranked, p1_name, p2_name, p1_account, "
            "p2_account, build, path, rtt_ms, delay, status, winner, score, reports, rating, origin, started, "
            "duration, p1_char, p2_char, stage, reason, blame, set_id, set_game) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (m["id"], m["created"], m.get("ended"), int(m["ranked"]), m["p1_name"], m["p2_name"],
             m.get("p1_account"), m.get("p2_account"), m.get("build"), m.get("path"), m.get("rtt_ms"),
             m.get("delay"), m["status"], m.get("winner"), json.dumps(m.get("score")),
             json.dumps(m.get("reports")), json.dumps(m.get("rating")), m.get("origin"), m.get("started"),
             m.get("duration"), m.get("p1_char"), m.get("p2_char"), m.get("stage"), m.get("reason"),
             m.get("blame"), m.get("set_id"), m.get("set_game")))

    def match_row(self, mid):
        r = self._x("SELECT * FROM matches WHERE id = ?", (mid,)).fetchone()
        return dict(r) if r else None

    def history(self, aid, limit=20, offset=0):
        """Finished matches of an account, newest first, from that player's side:
        {match, time, ranked, status, opponent, you_char, opp_char, stage, result: win|loss|draw|-,
         score [you, opp], delta, reason}. A game of a ranked set also has
         set {id, game, status, result: win|loss|-, score [you, opp], delta}: the set's outcome; the
         rating change of the set shows as `delta` on its deciding game only."""
        out = []
        for r in self._x(
                "SELECT m.*, s.status AS s_status, s.winner AS s_winner, s.score AS s_score, s.rating AS s_rating, "
                "s.games AS s_games FROM matches m LEFT JOIN sets s ON s.id = m.set_id "
                "WHERE (m.p1_account = ? OR m.p2_account = ?) AND m.status != 'playing' "
                "ORDER BY COALESCE(m.ended, m.created) DESC LIMIT ? OFFSET ?", (aid, aid, limit, offset)):
            r = dict(r)
            side = 0 if r["p1_account"] == aid else 1
            score = json.loads(r["score"]) if r["score"] else None
            rating = json.loads(r["rating"]) if r["rating"] else None
            counted = r["status"] in COUNTED
            if not counted:
                res = "-"
            elif r["winner"] is None:
                res = "draw"
            else:
                res = "win" if r["winner"] == side else "loss"
            out.append({
                "match": r["id"], "time": r["ended"] or r["created"], "ranked": bool(r["ranked"]),
                "status": r["status"], "reason": r["reason"],
                "opponent": r["p2_name"] if side == 0 else r["p1_name"],
                "you_char": r["p1_char"] if side == 0 else r["p2_char"],
                "opp_char": r["p2_char"] if side == 0 else r["p1_char"],
                "stage": r["stage"], "result": res,
                "score": (score if side == 0 else score[::-1]) if score else None,
                "delta": rating[side]["delta"] if rating else None,
                "path": r["path"], "rtt_ms": r["rtt_ms"], "delay": r["delay"]})
            if r.get("set_id"):
                view = _set_view(r["set_id"], r["set_game"], r["s_status"], r["s_winner"], r["s_score"],
                                 r["s_rating"], side)
                out[-1]["set"] = view
                games = json.loads(r["s_games"]) if r.get("s_games") else []
                if view["delta"] is not None and games and games[-1].get("match") == r["id"]:
                    out[-1]["delta"] = view["delta"]       # the deciding game carries the set's rating change
        return out

    # ----------------------------------------------------------------- ranked sets
    def save_set(self, s):
        self._x(
            "INSERT OR REPLACE INTO sets (id, created, ended, ranked, p1_name, p2_name, p1_account, p2_account, "
            "wins_needed, status, winner, score, games, rating, reason, blame) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (s["id"], s["created"], s.get("ended"), int(s["ranked"]), s["p1_name"], s["p2_name"], s.get("p1_account"),
             s.get("p2_account"), s["wins_needed"], s["status"], s.get("winner"), json.dumps(s.get("score")),
             json.dumps(s.get("games") or []), json.dumps(s.get("rating")), s.get("reason"), s.get("blame")))

    def set_row(self, sid):
        r = self._x("SELECT * FROM sets WHERE id = ?", (sid,)).fetchone()
        if r is None:
            return None
        d = dict(r)
        for k in ("score", "games", "rating"):
            d[k] = json.loads(d[k]) if d[k] else None
        return d

    def set_history(self, aid, limit=10, offset=0):
        """Finished ranked sets of an account, newest first, from that player's side: {id, time, status,
        reason, opponent, result: win|loss|-, score [you, opp], delta, games [{match, number, status, reason,
        result, score [you, opp], you_char, opp_char, stage}]}."""
        out = []
        for r in self._x(
                "SELECT * FROM sets WHERE (p1_account = ? OR p2_account = ?) AND status != 'playing' "
                "ORDER BY COALESCE(ended, created) DESC LIMIT ? OFFSET ?", (aid, aid, limit, offset)):
            r = dict(r)
            side = 0 if r["p1_account"] == aid else 1
            d = _set_view(r["id"], None, r["status"], r["winner"], r["score"], r["rating"], side)
            d.pop("game")
            games = []
            for g in json.loads(r["games"]) if r["games"] else []:
                row = self._x("SELECT p1_char, p2_char, stage FROM matches WHERE id = ?",
                                      (g.get("match"),)).fetchone()
                sc = g.get("score")
                games.append({"match": g.get("match"), "number": g.get("number"), "status": g.get("status"),
                              "reason": g.get("reason"),
                              "result": "-" if g.get("winner") is None else ("win" if g["winner"] == side else "loss"),
                              "score": (sc if side == 0 else sc[::-1]) if sc else None,
                              "you_char": row[0 if side == 0 else 1] if row else None,
                              "opp_char": row[1 if side == 0 else 0] if row else None,
                              "stage": row[2] if row else None})
            d.update({"time": r["ended"] or r["created"], "reason": r["reason"],
                      "opponent": r["p2_name"] if side == 0 else r["p1_name"], "games": games})
            out.append(d)
        return out

    def void_open_sets(self, reason="server_restart", now=None):
        """Sets still 'playing' in the database belong to a server that stopped: a running set lives in the
        server's memory only. Each becomes void -- no rating changes during a set, so there is nothing to
        undo -- and so does any game of it still 'playing'. -> how many sets."""
        now = now or time.time()
        ids = [r[0] for r in self._x("SELECT id FROM sets WHERE status = 'playing'")]
        for sid in ids:
            self._x("UPDATE sets SET status = 'void', reason = ?, ended = ? WHERE id = ?", (reason, now, sid))
            self._x("UPDATE matches SET status = 'void', reason = ?, ended = ? WHERE set_id = ? AND "
                            "status = 'playing'", (reason, now, sid))
        return len(ids)

    def char_usage(self, aid, limit=5):
        """[{char, games, wins}] over counted matches, most played first."""
        rows = self._x(
            "SELECT ch, COUNT(*) AS games, SUM(won) AS wins FROM ("
            "  SELECT p1_char AS ch, CASE WHEN winner = 0 THEN 1 ELSE 0 END AS won FROM matches "
            "   WHERE p1_account = ? AND p1_char IS NOT NULL AND status IN ('confirmed','onesided','forfeit','resolved')"
            "  UNION ALL "
            "  SELECT p2_char AS ch, CASE WHEN winner = 1 THEN 1 ELSE 0 END AS won FROM matches "
            "   WHERE p2_account = ? AND p2_char IS NOT NULL AND status IN ('confirmed','onesided','forfeit','resolved')"
            ") GROUP BY ch ORDER BY games DESC, wins DESC LIMIT ?", (aid, aid, limit))
        return [{"char": r["ch"], "games": r["games"], "wins": r["wins"] or 0} for r in rows]

    def main_char(self, aid):
        u = self.char_usage(aid, 1)
        return u[0]["char"] if u else None

    def strikes(self, aid, since):
        """Matches since `since` that ended without a result because of this account
        (crash, quit before the minimum length, no report)."""
        return self._x(
            "SELECT COUNT(*) FROM matches WHERE ended >= ? AND status = 'void' AND "
            "((p1_account = ? AND blame = 0) OR (p2_account = ? AND blame = 1))", (since, aid, aid)).fetchone()[0]

    def disputes(self, aid, since):
        return self._x(
            "SELECT COUNT(*) FROM matches WHERE ended >= ? AND status = 'disputed' AND (p1_account = ? OR p2_account = ?)",
            (since, aid, aid)).fetchone()[0]

    def pair_ranked(self, a, b, since):
        """Rated results between accounts a and b since `since` (anti win-trading cap): ranked sets that
        counted, plus ranked games rated on their own (the games of a set are not counted one by one)."""
        games = self._x(
            "SELECT COUNT(*) FROM matches WHERE ranked = 1 AND ended >= ? AND set_id IS NULL AND status IN "
            "('confirmed','onesided','forfeit','resolved') AND "
            "((p1_account = ? AND p2_account = ?) OR (p1_account = ? AND p2_account = ?))",
            (since, a, b, b, a)).fetchone()[0]
        sets = self._x(
            "SELECT COUNT(*) FROM sets WHERE ranked = 1 AND ended >= ? AND status IN ('confirmed','forfeit') AND "
            "((p1_account = ? AND p2_account = ?) OR (p1_account = ? AND p2_account = ?))",
            (since, a, b, b, a)).fetchone()[0]
        return games + sets

    def place(self, aid):
        """Leaderboard place of an account (1 = top), None when it has no ranked match."""
        row = self.account_by_id(aid)
        if row is None or not row["ranked_games"]:
            return None
        key = row["rating"] - 2 * row["rd"]
        return 1 + self._x("SELECT COUNT(*) FROM accounts WHERE ranked_games > 0 AND rating - 2 * rd > ?",
                                   (key,)).fetchone()[0]

    # ----------------------------------------------------------------- moderation (admin tool + server)
    @staticmethod
    def ban_state(row, now=None):
        """(until, reason) when the account row is banned now, else None."""
        until = row["banned_until"] if "banned_until" in row.keys() else None
        if until and until > (now or time.time()):
            return until, row["ban_reason"] or ""
        return None

    def ban_account(self, name, until, reason=""):
        return self._x("UPDATE accounts SET banned_until = ?, ban_reason = ? WHERE name = ?",
                               (until, reason, name)).rowcount > 0

    def unban_account(self, name):
        return self._x("UPDATE accounts SET banned_until = NULL, ban_reason = NULL WHERE name = ?",
                               (name,)).rowcount > 0

    def banned_account_ids(self, now=None):
        return {r[0] for r in self._x("SELECT id FROM accounts WHERE banned_until > ?",
                                               (now or time.time(),))}

    def ban_ip(self, net, until, reason=""):
        self._x("INSERT OR REPLACE INTO ip_bans (net, until, reason, created) VALUES (?, ?, ?, ?)",
                        (net, until, reason, time.time()))

    def unban_ip(self, net):
        return self._x("DELETE FROM ip_bans WHERE net = ?", (net,)).rowcount > 0

    def ip_bans(self, now=None):
        return [dict(r) for r in self._x("SELECT * FROM ip_bans WHERE until > ? ORDER BY created",
                                                  (now or time.time(),))]

    def reset_rating(self, name):
        """Back to 1500 / RD 350 and unranked (placement again); the win/loss record stays."""
        return self._x(
            "UPDATE accounts SET rating = ?, rd = ?, vol = ?, last_ranked = NULL, ranked_games = 0, tier = 0, "
            "tier_since = 0, tier_peak = 0, tier_floor = 0 WHERE name = ?",
            (glicko.DEFAULT_R, glicko.DEFAULT_RD, glicko.DEFAULT_VOL, name)).rowcount > 0

    def delete_account(self, name):
        row = self.account(name)
        if row is None:
            return False
        self._x("DELETE FROM accounts WHERE id = ?", (row["id"],))
        self._drop_orphans()
        return True

    def _drop_orphans(self):
        """Remembered logins, recovery codes and blocks of accounts that no longer exist."""
        for table in ("sessions", "recovery"):
            self._x(f"DELETE FROM {table} WHERE account_id NOT IN (SELECT id FROM accounts)")
        self._x("DELETE FROM blocks WHERE account_id NOT IN (SELECT id FROM accounts) "
                        "OR blocked_id NOT IN (SELECT id FROM accounts)")

    def list_accounts(self, pattern=None, limit=50, banned_only=False):
        sql, args = "SELECT * FROM accounts WHERE 1 = 1", []
        if pattern:
            esc = pattern.replace("!", "!!").replace("%", "!%").replace("_", "!_")
            sql += " AND name LIKE ? ESCAPE '!'"
            args.append(f"%{esc}%")
        if banned_only:
            sql += " AND banned_until > ?"
            args.append(time.time())
        sql += " ORDER BY COALESCE(last_seen, created) DESC LIMIT ?"
        args.append(limit)
        return [dict(r) for r in self._x(sql, args)]

    def recent_matches(self, limit=20, name=None):
        sql, args = "SELECT * FROM matches", []
        if name:
            sql += " WHERE p1_name = ? COLLATE NOCASE OR p2_name = ? COLLATE NOCASE"
            args += [name, name]
        sql += " ORDER BY created DESC LIMIT ?"
        args.append(limit)
        return [dict(r) for r in self._x(sql, args)]

    def purge_guest_matches(self, older_than_days):
        """Match records in which no account took part (guests only), older than the given age."""
        cut = time.time() - older_than_days * 86400.0
        return self._x("DELETE FROM matches WHERE p1_account IS NULL AND p2_account IS NULL "
                               "AND created < ?", (cut,)).rowcount

    def purge_inactive_accounts(self, days, include_played=False):
        """Accounts not seen for `days` (by default only those that never finished a game)."""
        cut = time.time() - days * 86400.0
        sql = "DELETE FROM accounts WHERE COALESCE(last_seen, created) < ? AND (banned_until IS NULL OR banned_until < ?)"
        if not include_played:
            sql += " AND games = 0"
        n = self._x(sql, (cut, time.time())).rowcount
        self._drop_orphans()
        return n

    # ----------------------------------------------------------------- blocked players (per account)
    def add_block(self, aid, target_id, name):
        """-> True when the block is new."""
        cur = self._x("INSERT OR IGNORE INTO blocks (account_id, blocked_id, blocked_name, created) "
                              "VALUES (?, ?, ?, ?)", (aid, target_id, name, time.time()))
        return cur.rowcount == 1

    def remove_block(self, aid, target_id):
        return self._x("DELETE FROM blocks WHERE account_id = ? AND blocked_id = ?",
                               (aid, target_id)).rowcount > 0

    def blocks_of(self, aid):
        return [dict(r) for r in self._x(
            "SELECT blocked_id, blocked_name, created FROM blocks WHERE account_id = ? ORDER BY created", (aid,))]

    # ----------------------------------------------------------------- server notices (admin tool -> server)
    def add_notice(self, text, expires, now=None):
        cur = self._x("INSERT INTO notices (created, expires, text) VALUES (?, ?, ?)",
                              (now or time.time(), expires, text))
        return cur.lastrowid

    def clear_notices(self, now=None):
        """End every notice that is still showing. -> how many."""
        now = now or time.time()
        return self._x("UPDATE notices SET cleared = ? WHERE cleared IS NULL AND expires > ?",
                               (now, now)).rowcount

    def active_notices(self, now=None):
        return [dict(r) for r in self._x(
            "SELECT id, created, expires, text FROM notices WHERE cleared IS NULL AND expires > ? ORDER BY id",
            (now or time.time(),))]

    def recent_notices(self, limit=10):
        return [dict(r) for r in self._x("SELECT * FROM notices ORDER BY id DESC LIMIT ?", (limit,))]

    def set_match_lag(self, mid, data):
        self._x("UPDATE matches SET lag = ? WHERE id = ?", (json.dumps(data), mid))

    def stats(self, now=None):
        """Numbers for the status page: accounts and the last 24 hours of matches."""
        now = now or time.time()
        day = now - 86400.0
        one = lambda sql, *a: self._x(sql, a).fetchone()[0]   # noqa: E731
        by_status = {r[0]: r[1] for r in self._x(
            "SELECT status, COUNT(*) FROM matches WHERE created >= ? GROUP BY status", (day,))}
        by_path = {r[0] or "none": r[1] for r in self._x(
            "SELECT path, COUNT(*) FROM matches WHERE created >= ? GROUP BY path", (day,))}
        return {
            "accounts": one("SELECT COUNT(*) FROM accounts"),
            "accounts_seen_24h": one("SELECT COUNT(*) FROM accounts WHERE last_seen >= ?", day),
            "accounts_seen_7d": one("SELECT COUNT(*) FROM accounts WHERE last_seen >= ?", now - 7 * 86400.0),
            "accounts_banned": one("SELECT COUNT(*) FROM accounts WHERE banned_until > ?", now),
            "ip_bans": one("SELECT COUNT(*) FROM ip_bans WHERE until > ?", now),
            "matches_24h": sum(by_status.values()),
            "matches_24h_by_status": by_status,
            "matches_24h_by_path": by_path,
            "matches_total": one("SELECT COUNT(*) FROM matches"),
        }


# Statuses whose result counts (record, rating when ranked).
COUNTED = ("confirmed", "onesided", "forfeit", "resolved")
# ... and those of a ranked set (decided by its games, or by a player leaving it).
SET_COUNTED = ("confirmed", "forfeit")


def _set_view(sid, game, status, winner, score, rating, side):
    """A ranked set from one player's side (history rows)."""
    score = json.loads(score) if isinstance(score, str) else score
    rating = json.loads(rating) if isinstance(rating, str) else rating
    counted = status in SET_COUNTED and winner is not None
    return {"id": sid, "game": game, "status": status,
            "result": ("win" if winner == side else "loss") if counted else "-",
            "score": (score if side == 0 else score[::-1]) if score else None,
            "delta": rating[side]["delta"] if rating else None}
