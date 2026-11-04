"""Problem reports the launcher sends to the developer (docs/HOSTING.md "Problem reports").

The launcher makes the same scrubbed zip as "Save report" (launcher/problem_report.py) and, when the player presses
Send, uploads it over a short control connection of its own -- no login needed, so a guest or a player who never got
online can send one too:

    client                                      server
    hello {caps: [..., "problem_reports"]}  ->  welcome {features: [..., "problem_reports"], reports: {max_bytes, v}}
    report_begin {size, sha256, meta}       ->  report_go {id}          (or an error: too big, rate limited, full)
    report_data {id} + exactly `size` bytes ->  report_done {id, sent}  (checked, stored; the webhook goes after)

Every other line stays under proto.MAX_LINE: the zip's bytes are read by h_report_data itself (readexactly), never as
a line. A server without this module has no "problem_reports" feature; the launcher then offers Save only.

The server never writes a member of the zip anywhere: it reads the central directory and inflates each member into
nothing (a counted, CRC-checked read with hard caps) to refuse anything that is not a report of the expected layout
or that would unpack to more than it says (zip bombs). Stored as <dir>/<YYYY-MM-DD>/<id>.zip + <id>.json; the oldest
go first when the folder passes T5L_REPORT_TOTAL_MB or a report is older than T5L_REPORT_KEEP_DAYS.

Optional push: T5L_REPORT_WEBHOOK = a Discord webhook URL (only in the server's environment, never in a client).
Each new report is posted there with its facts and the zip attached when it fits T5L_REPORT_WEBHOOK_MAX_KB (Discord:
8 MB on a server without boosts); a bigger one is posted without the file (`t5lobby-admin reports get ID`).
"""
import asyncio
import datetime
import hashlib
import io
import json
import logging
import os
import re
import secrets
import time
import urllib.error
import urllib.request
import uuid
import zipfile

from .. import proto
from ..proto import LobbyError
from .ratelimit import KeyedBuckets, TokenBucket

log = logging.getLogger("t5lobby")

FEATURE = "problem_reports"
CAP = FEATURE
VERSION = 1
GAME = "T5DR Online"              # (t4lobby: "Tekken 4 Online")
ADMIN = "t5lobby-admin"
DAY = 86400.0

E_REPORT_OFF = "reports_off"      # this server takes no reports (or its folder is not writable)
E_REPORT_SIZE = "report_size"     # too big / empty
E_REPORT_BAD = "report_bad"       # not a report zip of the expected layout, or the bytes do not match
E_REPORT_FULL = "report_full"     # the server's report folder is full for today

CHUNK = 64 * 1024                 # bytes read at once from the socket
PART_TIMEOUT = 30.0               # seconds the client may stall between two chunks
MIN_RATE = 2048                   # bytes/s the whole upload must average (plus a minute)

# What the zip may hold. Names as problem_report.py writes them (contents.txt, system.txt, logs/game-*.log, online/...,
# replay/*.t5replay, desync/*.bin, compile/*.log): letters, digits, '_', '-', '.', at most 4 folders deep, one of the
# extensions below. No folder entries, no absolute paths, no '..'.
MAX_MEMBERS = 200
MAX_MEMBER_BYTES = 32 << 20       # one file, unpacked
MAX_TOTAL_BYTES = 64 << 20        # all files, unpacked (the launcher's own cap is 20 MB)
MAX_RATIO = 1000                  # unpacked / packed, for members over 1 MB
EXTENSIONS = (".txt", ".log", ".json", ".ini", ".csv", ".md", ".bin", ".t5replay", ".t4replay", ".1", ".2", ".3")
_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,127}$")
REQUIRED = "contents.txt"

META_LIMITS = {"game": 32, "version": 32, "build_id": 80, "os": 160, "description": 1000, "contact": 80, "name": 32,
               "name_kind": 16, "launcher": 48, "language": 16}


# ----------------------------------------------------------------------------- checks (no files written)

def check_zip(data):
    """-> [(name, unpacked size)] for a report zip, or ValueError(why). Reads every member into nothing, counting."""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except (zipfile.BadZipFile, ValueError, OSError) as e:
        raise ValueError(f"not a zip file ({e})") from None
    infos = zf.infolist()
    if not 1 <= len(infos) <= MAX_MEMBERS:
        raise ValueError(f"{len(infos)} files in the zip (1 to {MAX_MEMBERS})")
    names = set()
    total = 0
    for zi in infos:
        name = zi.filename
        parts = name.split("/")
        if (name in names or len(name) > 200 or zi.is_dir() or len(parts) > 5
                or not all(_SEGMENT.match(p) and p not in (".", "..") for p in parts)
                or not name.lower().endswith(EXTENSIONS)):
            raise ValueError(f"unexpected file name {name[:80]!r}")
        names.add(name)
        if zi.flag_bits & 0x1:
            raise ValueError(f"{name}: encrypted")
        if zi.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            raise ValueError(f"{name}: compression method {zi.compress_type}")
        if zi.file_size > MAX_MEMBER_BYTES:
            raise ValueError(f"{name}: {zi.file_size} bytes unpacked")
        if zi.file_size > (1 << 20) and zi.file_size > MAX_RATIO * max(1, zi.compress_size):
            raise ValueError(f"{name}: packed {zi.compress_size} -> {zi.file_size} bytes")
        total += zi.file_size
        if total > MAX_TOTAL_BYTES:
            raise ValueError("more than 64 MB unpacked")
    if REQUIRED not in names:
        raise ValueError(f"no {REQUIRED}")
    out = []
    for zi in infos:      # the sizes above are what the zip says; this is what it really holds (and its CRC)
        n = 0
        try:
            with zf.open(zi) as f:
                while True:
                    block = f.read(CHUNK)
                    if not block:
                        break
                    n += len(block)
                    if n > zi.file_size or n > MAX_MEMBER_BYTES:
                        raise ValueError(f"{zi.filename}: more data than the zip says")
        except (zipfile.BadZipFile, EOFError, OSError, RuntimeError, NotImplementedError) as e:
            raise ValueError(f"{zi.filename}: {e}") from None
        except Exception as e:      # noqa: BLE001 -- zlib.error and anything else a broken stream raises
            if isinstance(e, ValueError) and "more data" in str(e):
                raise
            raise ValueError(f"{zi.filename}: {type(e).__name__}") from None
        if n != zi.file_size:
            raise ValueError(f"{zi.filename}: {n} bytes, the zip says {zi.file_size}")
        out.append((zi.filename, n))
    return out


def clean_meta(meta):
    """The facts the launcher sends next to the zip, as plain short strings (anything else dropped)."""
    out = {}
    if isinstance(meta, dict):
        for k, limit in META_LIMITS.items():
            v = meta.get(k)
            if isinstance(v, (str, int, float)) and not isinstance(v, bool):
                v = proto.clean_text(str(v).replace("\r", " ").replace("\n", " ").strip(), limit)
                if v:
                    out[k] = v
    return out


def new_id(exists=lambda _rid: False):
    for _ in range(100):
        rid = "".join(secrets.choice(proto.CODE_ALPHABET) for _ in range(6))
        if not exists(rid):
            return rid
    return uuid.uuid4().hex[:12].upper()


VALID_ID = re.compile(r"^[A-Z0-9]{6,12}$")


# ----------------------------------------------------------------------------- the folder (server and admin tool)

def report_dir(cfg_dir, db):
    """Where reports live: T5L_REPORT_DIR, else 'reports' next to the database; None for an in-memory database."""
    if cfg_dir:
        return os.path.abspath(cfg_dir)
    if not db or db == ":memory:":
        return None
    return os.path.join(os.path.dirname(os.path.abspath(db)), "reports")


class ReportFolder:
    def __init__(self, path):
        self.path = path

    def _days(self):
        try:
            return sorted(d for d in os.listdir(self.path)
                          if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) and os.path.isdir(os.path.join(self.path, d)))
        except OSError:
            return []

    def all(self):
        """[(meta dict, zip path)] oldest first."""
        out = []
        for d in self._days():
            dd = os.path.join(self.path, d)
            try:
                names = os.listdir(dd)
            except OSError:
                continue
            for n in names:
                if not n.endswith(".json"):
                    continue
                try:
                    with open(os.path.join(dd, n), encoding="utf-8") as f:
                        meta = json.load(f)
                except (OSError, ValueError):
                    continue
                if isinstance(meta, dict) and VALID_ID.match(str(meta.get("id", ""))):
                    out.append((meta, os.path.join(dd, meta["id"] + ".zip")))
        out.sort(key=lambda m: (m[0].get("time", 0), m[0].get("id", "")))
        return out

    def find(self, rid):
        rid = str(rid).strip().lstrip("#").upper()
        if not VALID_ID.match(rid):
            return None
        for d in reversed(self._days()):
            p = os.path.join(self.path, d, rid + ".json")
            if os.path.isfile(p):
                try:
                    with open(p, encoding="utf-8") as f:
                        return json.load(f), os.path.join(self.path, d, rid + ".zip")
                except (OSError, ValueError):
                    return None
        return None

    def exists(self, rid):
        return self.find(rid) is not None

    def store(self, rid, data, meta, now=None):
        now = now or time.time()
        day = datetime.datetime.fromtimestamp(now, datetime.timezone.utc).strftime("%Y-%m-%d")
        dd = os.path.join(self.path, day)
        os.makedirs(dd, mode=0o750, exist_ok=True)
        zpath = os.path.join(dd, rid + ".zip")
        for path, blob in ((zpath, data), (os.path.join(dd, rid + ".json"),
                                           json.dumps(meta, indent=2, ensure_ascii=False).encode("utf-8"))):
            tmp = path + ".part"
            with open(tmp, "wb") as f:
                f.write(blob)
            os.replace(tmp, path)
        return zpath

    def save_meta(self, meta, zpath):
        path = zpath[:-4] + ".json"
        tmp = path + ".part"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)

    def delete(self, meta, zpath):
        for p in (zpath, zpath[:-4] + ".json"):
            try:
                os.remove(p)
            except FileNotFoundError:
                pass
        try:
            os.rmdir(os.path.dirname(zpath))         # (only when the day's folder is empty now)
        except OSError:
            pass

    def total_bytes(self):
        return sum(os.path.getsize(z) for _m, z in self.all() if os.path.isfile(z))

    def today_count(self, now=None):
        now = now or time.time()
        return sum(1 for m, _z in self.all() if now - float(m.get("time", 0)) < DAY)

    def prune(self, total_bytes, keep_days, now=None, keep=()):
        """Oldest first: past keep_days, then until the folder holds at most total_bytes. -> ids removed."""
        now = now or time.time()
        rows = [(m, z) for m, z in self.all() if m.get("id") not in keep]
        gone = []
        size = {m["id"]: (os.path.getsize(z) if os.path.isfile(z) else 0) for m, z in rows}
        total = sum(size.values())
        for m, z in rows:
            old = keep_days > 0 and now - float(m.get("time", 0)) > keep_days * DAY
            if old or (total_bytes > 0 and total > total_bytes):
                self.delete(m, z)
                total -= size[m["id"]]
                gone.append(m["id"])
        return gone


# ----------------------------------------------------------------------------- the Discord webhook

def _human(n):
    return f"{n / (1 << 20):.1f} MB" if n >= 1 << 20 else f"{max(1, n // 1024)} KB"


def webhook_text(meta, attached, game=GAME, admin=ADMIN):
    """The message the owner reads in his channel (Discord: 2000 characters at most)."""
    rid = meta.get("id", "?")
    first = f"**New problem report #{rid}** -- {meta.get('game') or game} {meta.get('version') or '?'}"
    lines = [first,
             f"Build: `{meta.get('build_id') or '?'}`   OS: {meta.get('os') or '?'}",
             "Player: " + (meta.get("name") or "(no lobby name)")
             + (f" ({meta['name_kind']})" if meta.get("name_kind") else "")
             + (f"   Contact: {meta['contact']}" if meta.get("contact") else ""),
             f"Size: {_human(int(meta.get('size', 0)))}, {meta.get('files', '?')} files"
             + ("" if attached else f" -- too big to attach here: `{admin} reports get {rid}` on the server")]
    desc = meta.get("description") or ""
    if desc:
        lines.append("> " + desc.replace("\n", " "))
    text = "\n".join(lines)
    return text[:1990]


def _multipart(fields, files):
    boundary = "----t5report" + uuid.uuid4().hex
    out = io.BytesIO()
    for name, value in fields:
        out.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n"
                  "Content-Type: application/json\r\n\r\n".encode())
        out.write(value.encode("utf-8") + b"\r\n")
    for name, filename, ctype, blob in files:
        out.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"; filename=\"{filename}\"\r\n"
                  f"Content-Type: {ctype}\r\n\r\n".encode())
        out.write(blob + b"\r\n")
    out.write(f"--{boundary}--\r\n".encode())
    return out.getvalue(), "multipart/form-data; boundary=" + boundary


def webhook_url_ok(url):
    """https only (Discord), or plain http to this machine (tests)."""
    if not isinstance(url, str):
        return False
    if url.startswith("https://"):
        return True
    return bool(re.match(r"^http://(127\.0\.0\.1|localhost|\[::1\])(:\d+)?/", url))


def post_webhook(url, text, zpath=None, max_bytes=8000 * 1024, timeout=30.0, sleep=time.sleep):
    """Post one report to a Discord webhook (blocking: the server calls it on a worker thread). The zip goes along
    when it is at most max_bytes; a refusal for its size (413) sends the text alone. -> (ok, attached, why)."""
    if not webhook_url_ok(url):
        return False, False, "T5L_REPORT_WEBHOOK is not an https URL"
    blob = None
    if zpath:
        try:
            if os.path.getsize(zpath) <= max_bytes:
                with open(zpath, "rb") as f:
                    blob = f.read()
        except OSError:
            blob = None
    tries = 0
    while True:
        tries += 1
        payload = json.dumps({"content": webhook_text_with(text, blob is not None), "allowed_mentions": {"parse": []},
                              "username": "Problem reports"})
        files = [("files[0]", os.path.basename(zpath), "application/zip", blob)] if blob is not None else []
        body, ctype = _multipart([("payload_json", payload)], files)
        req = urllib.request.Request(url, data=body, method="POST",
                                     headers={"Content-Type": ctype, "User-Agent": "t5lobby-reports/1"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                r.read(4096)
            return True, blob is not None, ""
        except urllib.error.HTTPError as e:
            if e.code == 413 and blob is not None:
                blob = None
                continue
            if e.code == 429 and tries < 3:
                try:
                    wait = float(json.loads(e.read(4096).decode("utf-8", "replace")).get("retry_after", 2))
                except (ValueError, AttributeError):
                    wait = 2.0
                sleep(min(max(wait, 0.5), 15.0))
                continue
            return False, False, f"HTTP {e.code}"
        except (urllib.error.URLError, OSError, ValueError) as e:
            if tries < 2:
                sleep(2.0)
                continue
            return False, False, type(e).__name__


def webhook_text_with(text, attached):
    """`text` is webhook_text(meta, True): when the file did not go along, say where it is instead."""
    if attached or "too big to attach" in text:
        return text
    head, sep, rest = text.partition("\nSize: ")
    if not sep:
        return text
    size_line, nl, tail = rest.partition("\n")
    rid = re.search(r"#([A-Z0-9]+)", head)
    note = f" -- not attached: `{ADMIN} reports get {rid.group(1) if rid else '?'}` on the server"
    return head + sep + size_line + note + nl + tail


# ----------------------------------------------------------------------------- the server part

class ReportsMixin:
    """LobbyServer's report handlers. Needs self.cfg (report_* fields), self.akey(); Conn objects get .report."""

    def _reports_init(self):
        cfg = self.cfg
        self._report_folder = None
        path = report_dir(cfg.report_dir, cfg.db) if cfg.reports else None
        if path:
            try:
                os.makedirs(path, mode=0o750, exist_ok=True)
                self._report_folder = ReportFolder(path)
            except OSError as e:
                log.warning("problem reports off: %s is not usable (%s)", path, e)
        per_addr = max(1, cfg.report_per_address_day)
        per_name = max(1, cfg.report_per_name_day)
        self._report_addr = KeyedBuckets(rate=per_addr / DAY, burst=per_addr)
        self._report_name = KeyedBuckets(rate=per_name / DAY, burst=per_name)
        self._report_day = TokenBucket(rate=max(1, cfg.report_per_day) / DAY, burst=max(1, cfg.report_per_day))
        self._report_busy = 0                       # uploads in progress (each holds up to report_max_kb in memory)
        if self._report_folder is not None and cfg.report_webhook and not webhook_url_ok(cfg.report_webhook):
            log.warning("T5L_REPORT_WEBHOOK is not an https URL: reports are stored, nothing is posted")

    def reports_on(self):
        return getattr(self, "_report_folder", None) is not None

    def report_hello(self, conn, msg):
        """hello {purpose: "report", caps: ["problem_reports"], build: {...}} -> a short welcome. The build is only
        recorded (as the launcher gives it): the server's accepted builds (T5L_BUILDS) do not apply to a report."""
        caps = msg.get("caps")
        conn.caps = frozenset({CAP}) if isinstance(caps, list) and CAP in caps[:32] else frozenset()
        build = msg.get("build") if isinstance(msg.get("build"), dict) else {}
        conn.release = proto.clean_text(build.get("release", ""), 32)
        conn.build_id = proto.clean_text(build.get("id", ""), 64)
        conn.report_only = True
        conn.helloed = True
        return {"t": "welcome", "server": getattr(self, "SERVER_NAME", "lobby"), "proto": proto.PROTO_VERSION,
                "purpose": "report", "features": [FEATURE] if self.reports_on() else [],
                **self.reports_welcome(conn)}

    def reports_welcome(self, conn):
        if not self.reports_on() or CAP not in conn.caps:
            return {}
        return {"reports": {"v": VERSION, "max_bytes": self.cfg.report_max_kb * 1024}}

    def _report_refuse(self, code, msg, **extra):
        self._count("reports_refused")
        raise LobbyError(code, msg, **extra)

    async def h_report_begin(self, conn, msg):
        if not conn.helloed:
            raise LobbyError(proto.E_STATE, "hello first")
        if not self.reports_on() or CAP not in conn.caps:
            raise LobbyError(E_REPORT_OFF, "this server takes no problem reports")
        if getattr(conn, "report", None) is not None:
            raise LobbyError(proto.E_STATE, "one report at a time")
        size = msg.get("size")
        digest = msg.get("sha256")
        if type(size) is not int or not 22 <= size <= self.cfg.report_max_kb * 1024:
            self._report_refuse(E_REPORT_SIZE, f"a report is at most {self.cfg.report_max_kb // 1024} MB",
                                max_bytes=self.cfg.report_max_kb * 1024)
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise LobbyError(proto.E_BAD_REQUEST, "sha256: 64 lowercase hex digits")
        meta = clean_meta(msg.get("meta"))
        p = conn.player
        if p is not None:                           # sent over a logged-in connection: the server knows who
            meta["name"], meta["name_kind"] = p.name, "guest" if p.guest else "account, logged in"
        elif meta.get("name"):
            meta["name_kind"] = {"account": "account, as the launcher says",
                                 "guest": "guest, as the launcher says"}.get(meta.get("name_kind"), "as the launcher says")
        name_key = proto.name_key(meta.get("name", "")) or "-"
        if self._report_busy >= max(1, self.cfg.report_concurrent):
            self._report_refuse(proto.E_BUSY, "the server is taking other reports; try again in a minute", retry=60)
        if not self._report_addr.peek_ok(conn.akey) or (name_key != "-" and not self._report_name.peek_ok(name_key)):
            wait = max(self._report_addr.wait(conn.akey), self._report_name.wait(name_key) if name_key != "-" else 0)
            self._report_refuse(proto.E_RATE, "enough reports from this PC for today; save it instead and send it later",
                                retry=int(wait) + 1)
        if not self._report_day.take():
            self._report_refuse(E_REPORT_FULL, "the server has taken all reports it can today; save it instead")
        self._report_addr.take(conn.akey)
        if name_key != "-":
            self._report_name.take(name_key)
        rid = new_id(self._report_folder.exists)
        conn.report = {"id": rid, "size": size, "sha256": digest, "meta": meta, "t": time.monotonic()}
        return {"t": "report_go", "id": rid, "chunk": CHUNK}

    async def h_report_data(self, conn, msg):
        rep = getattr(conn, "report", None)
        if rep is None or msg.get("id") != rep["id"]:
            raise LobbyError(proto.E_STATE, "report_begin first")
        conn.report = None
        size = rep["size"]
        self._report_busy += 1
        try:
            buf = bytearray()
            deadline = time.monotonic() + 60.0 + size / MIN_RATE
            try:
                while len(buf) < size:
                    left = deadline - time.monotonic()
                    if left <= 0:
                        raise asyncio.TimeoutError
                    buf += await asyncio.wait_for(conn.reader.readexactly(min(CHUNK, size - len(buf))),
                                                  min(PART_TIMEOUT, left))
            except (asyncio.TimeoutError, asyncio.IncompleteReadError, ConnectionError, OSError):
                self._count("reports_broken")
                log.info("problem report %s: upload broke off after %d of %d bytes", rep["id"], len(buf), size)
                return False                        # the stream is out of step now: close
            data = bytes(buf)
            del buf
            if hashlib.sha256(data).hexdigest() != rep["sha256"]:
                self._report_refuse(E_REPORT_BAD, "the report arrived damaged; try again")
            try:
                members = await asyncio.to_thread(check_zip, data)
            except ValueError as e:
                log.info("problem report %s refused: %s", rep["id"], e)
                self._report_refuse(E_REPORT_BAD, "this is not a report zip of the expected layout")
            meta = dict(rep["meta"], id=rep["id"], time=time.time(), size=size, sha256=rep["sha256"],
                        files=len(members), members=[[n, s] for n, s in members],
                        via="logged in" if conn.player is not None else "report connection",
                        release=getattr(conn, "release", ""), build_seen=getattr(conn, "build_id", "") or "",
                        webhook="off" if not self.cfg.report_webhook else "pending")
            meta.setdefault("game", self.REPORT_GAME)
            folder = self._report_folder
            try:
                zpath = await asyncio.to_thread(folder.store, rep["id"], data, meta)
                gone = await asyncio.to_thread(folder.prune, self.cfg.report_total_mb << 20, self.cfg.report_keep_days,
                                               None, (rep["id"],))
            except OSError as e:
                log.warning("problem report %s could not be stored: %s", rep["id"], e)
                self._report_refuse(E_REPORT_OFF, "the server could not store the report; save it instead")
            if gone:
                log.info("problem reports: %d old report(s) removed (T5L_REPORT_TOTAL_MB / _KEEP_DAYS)", len(gone))
            self._count("reports_received")
            self.note("report", id=rep["id"], size=size, files=len(members))
            log.info("problem report %s received: %s %s, %d bytes, %d files", rep["id"], meta.get("game", ""),
                     meta.get("version", ""), size, len(members))
            if self.cfg.report_webhook:
                self._spawn(self._report_post(meta, zpath))
            return {"t": "report_done", "id": rep["id"], "webhook": bool(self.cfg.report_webhook)}
        finally:
            self._report_busy -= 1

    async def _report_post(self, meta, zpath):
        ok, attached, why = await asyncio.to_thread(post_webhook, self.cfg.report_webhook,
                                                    webhook_text(meta, True, self.REPORT_GAME, self.REPORT_ADMIN),
                                                    zpath, self.cfg.report_webhook_max_kb * 1024)
        meta = dict(meta, webhook=("posted with the zip" if attached else "posted without the zip") if ok
                    else "failed: " + why)
        self._count("reports_posted" if ok else "reports_post_failed")
        if not ok:
            log.warning("problem report %s: the webhook did not take it (%s); `%s reports send %s` tries again",
                        meta["id"], why, self.REPORT_ADMIN, meta["id"])
        try:
            await asyncio.to_thread(self._report_folder.save_meta, meta, zpath)
        except OSError:
            pass
        self.note("report_post", id=meta["id"], ok=ok, attached=attached)

    REPORT_GAME = GAME
    REPORT_ADMIN = ADMIN
