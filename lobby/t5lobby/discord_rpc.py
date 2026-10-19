"""Discord Rich Presence over the Discord client's local IPC (docs/ONLINE.md "Discord Rich Presence").

Pure Python, no SDK. The Discord desktop app listens on a local pipe: on Windows the named pipes
\\\\.\\pipe\\discord-ipc-0 .. -9, elsewhere a Unix socket of the same name in $XDG_RUNTIME_DIR, $TMPDIR, /tmp
(and the Flatpak / Snap folders under them). Nothing goes over the network: Discord itself shows the activity
to the player's Discord friends. A frame is

    opcode (u32, little endian) | length (u32, little endian) | JSON (UTF-8)

with the opcodes 0 HANDSHAKE ({"v": 1, "client_id": APPLICATION_ID}), 1 FRAME (a command or its answer),
2 CLOSE, 3 PING, 4 PONG. After the handshake Discord answers with a DISPATCH READY frame; then

    {"cmd": "SET_ACTIVITY", "args": {"pid": <this process>, "activity": {...}}, "nonce": "<unique>"}

shows the activity under the player's name ("Playing T5DR Online -- In match: Jin vs Kazuya (Ranked, Set 1-0)",
with an elapsed timer from `timestamps.start`); the same command without "activity" takes it down.

It needs the id of a Discord application (created once by whoever ships the launcher, docs/ONLINE.md): the
`application_id` in data/discord.json, or launcher.json "discord_app_id", or T5_DISCORD_APP_ID.

DiscordPresence runs on its own thread. update(activity) only remembers what should show; the thread connects
when it can -- while Discord is not running it tries again every RETRY seconds, quietly: no error, no dialog,
one log line at most -- sends the newest activity (at most one SET_ACTIVITY per MIN_INTERVAL seconds: Discord
ignores more than 5 per 20 s), answers Discord's PING, and takes the activity down on close(). Every wait has a
timeout.
"""
import json
import os
import struct
import sys
import threading
import time
import uuid

from .i18n import t

OP_HANDSHAKE, OP_FRAME, OP_CLOSE, OP_PING, OP_PONG = 0, 1, 2, 3, 4
MAX_FRAME = 1 << 20
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "discord.json")


class DiscordError(OSError):
    """Discord is not there, closed the pipe, or answered something that is not its protocol."""


# ----------------------------------------------------------------------------- configuration
def valid_app_id(value):
    """A Discord application id is a "snowflake": 17-20 digits (accepting 15-22)."""
    s = str(value or "").strip()
    return s if s.isdigit() and 15 <= len(s) <= 22 else None


def load_config(settings=None, env=None, path=CONFIG_FILE):
    """{"application_id": str | None, "large_image": str, "large_text": str}: data/discord.json (what the release
    ships), then the launcher's settings ("discord_app_id"), then T5_DISCORD_APP_ID -- the last one set wins."""
    env = os.environ if env is None else env
    cfg = {"application_id": None, "large_image": "", "large_text": "T5DR Online"}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            cfg["application_id"] = valid_app_id(data.get("application_id"))
            for k in ("large_image", "large_text"):
                if isinstance(data.get(k), str):
                    cfg[k] = data[k].strip()[:64]
    except (OSError, ValueError):
        pass
    for value in ((settings or {}).get("discord_app_id"), env.get("T5_DISCORD_APP_ID")):
        if valid_app_id(value):
            cfg["application_id"] = valid_app_id(value)
    return cfg


def default_paths():
    """Where the Discord client listens, in the order Discord numbers them."""
    if os.name == "nt":
        return [rf"\\.\pipe\discord-ipc-{i}" for i in range(10)]
    bases = []
    for var in ("XDG_RUNTIME_DIR", "TMPDIR", "TMP", "TEMP"):
        if os.environ.get(var):
            bases.append(os.environ[var])
    bases.append("/tmp")
    out = []
    for base in bases:
        for sub in ("", "app/com.discordapp.Discord", "snap.discord", ".flatpak/com.discordapp.Discord/xdg-run"):
            d = os.path.join(base, sub) if sub else base
            out += [os.path.join(d, f"discord-ipc-{i}") for i in range(10)]
    return list(dict.fromkeys(out))


# ----------------------------------------------------------------------------- the pipe
class _WinPipe:
    """A client end of a Windows named pipe. Reads never block: PeekNamedPipe says what has arrived."""

    def __init__(self, path):
        import ctypes
        import msvcrt
        from ctypes import wintypes
        self._f = open(path, "r+b", buffering=0)        # CreateFile(OPEN_EXISTING): fails at once without Discord
        self._handle = msvcrt.get_osfhandle(self._f.fileno())
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._peek = k32.PeekNamedPipe
        self._peek.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD, wintypes.LPVOID,
                               ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID]
        self._peek.restype = wintypes.BOOL
        self._ctypes, self._dword = ctypes, wintypes.DWORD

    def available(self):
        n = self._dword(0)
        if not self._peek(self._handle, None, 0, None, self._ctypes.byref(n), None):
            raise DiscordError(f"the pipe is closed (error {self._ctypes.get_last_error()})")
        return n.value

    def recv(self, n, deadline):
        out = b""
        while len(out) < n:
            have = self.available()
            if have:
                chunk = self._f.read(min(have, n - len(out)))
                if not chunk:
                    raise DiscordError("the pipe is closed")
                out += chunk
                continue
            if time.monotonic() >= deadline:
                raise TimeoutError("no answer from Discord")
            time.sleep(0.01)
        return out

    def send(self, data):
        self._f.write(data)

    def close(self):
        try:
            self._f.close()
        except OSError:
            pass


class _UnixPipe:
    def __init__(self, path):
        import socket
        self._s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._s.settimeout(2.0)
        try:
            self._s.connect(path)
        except OSError:
            self._s.close()
            raise

    def available(self):
        import select
        r, _w, _x = select.select([self._s], [], [], 0)
        return 1 if r else 0

    def recv(self, n, deadline):
        out = b""
        while len(out) < n:
            left = deadline - time.monotonic()
            if left <= 0:
                raise TimeoutError("no answer from Discord")
            self._s.settimeout(left)
            try:
                chunk = self._s.recv(n - len(out))
            except TimeoutError:
                raise
            except OSError as e:
                raise DiscordError(str(e)) from None
            if not chunk:
                raise DiscordError("the socket is closed")
            out += chunk
        return out

    def send(self, data):
        self._s.settimeout(2.0)
        self._s.sendall(data)

    def close(self):
        try:
            self._s.close()
        except OSError:
            pass


def open_pipe(path):
    return _WinPipe(path) if path.startswith("\\\\") else _UnixPipe(path)


def encode(op, payload):
    data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return struct.pack("<II", op, len(data)) + data


class Connection:
    """One connection to the Discord client: handshake, commands, the frames that come back."""

    TIMEOUT = 3.0

    def __init__(self, pipe):
        self.pipe = pipe
        self.user = None

    @classmethod
    def open(cls, app_id, paths, timeout=TIMEOUT):
        """The first pipe that answers the handshake with READY. -> Connection; DiscordError when none does."""
        last = None
        for path in paths:
            try:
                pipe = open_pipe(path)
            except OSError as e:
                last = e
                continue
            conn = cls(pipe)
            try:
                conn.handshake(app_id, timeout)
                return conn
            except (OSError, TimeoutError, ValueError) as e:
                last = e
                conn.close()
        raise DiscordError(f"Discord is not running ({last})" if last else "Discord is not running")

    def read(self, deadline):
        op, n = struct.unpack("<II", self.pipe.recv(8, deadline))
        if n > MAX_FRAME:
            raise DiscordError("frame too large")
        body = self.pipe.recv(n, deadline) if n else b"{}"
        try:
            data = json.loads(body.decode("utf-8"))
        except ValueError:
            raise DiscordError("not JSON") from None
        if op == OP_CLOSE:
            raise DiscordError(f"Discord closed the connection: {str(data.get('message') or data)[:120]}")
        if op == OP_PING:
            self.pipe.send(encode(OP_PONG, data))
        return op, data

    def handshake(self, app_id, timeout=TIMEOUT):
        self.pipe.send(encode(OP_HANDSHAKE, {"v": 1, "client_id": str(app_id)}))
        deadline = time.monotonic() + timeout
        while True:
            op, data = self.read(deadline)
            if op == OP_FRAME and data.get("evt") == "READY":
                self.user = ((data.get("data") or {}).get("user") or {}).get("username")
                return data
            if op == OP_FRAME and data.get("evt") == "ERROR":
                raise DiscordError(f"Discord refused the handshake: {(data.get('data') or {}).get('message')}")

    def command(self, cmd, args, timeout=TIMEOUT):
        """Send a command and wait for its answer (the frame with the same nonce). -> the answer."""
        nonce = uuid.uuid4().hex
        self.pipe.send(encode(OP_FRAME, {"cmd": cmd, "args": args, "nonce": nonce}))
        deadline = time.monotonic() + timeout
        while True:
            op, data = self.read(deadline)
            if op == OP_FRAME and data.get("nonce") == nonce:
                return data

    def set_activity(self, activity, pid=None, timeout=TIMEOUT):
        args = {"pid": int(pid or os.getpid())}
        if activity:
            args["activity"] = activity
        return self.command("SET_ACTIVITY", args, timeout)

    def poll(self):
        """Read what Discord sent on its own (PING, events) without waiting."""
        while self.pipe.available():
            self.read(time.monotonic() + self.TIMEOUT)

    def close(self, say_bye=True):
        if say_bye:
            try:
                self.pipe.send(encode(OP_CLOSE, {}))
            except OSError:
                pass
        self.pipe.close()


# ----------------------------------------------------------------------------- what to show
def activity_for(kind, mode=None, ranked=False, fighters=None, set_score=None, start=None, large_image="",
                 large_text="T5DR Online"):
    """The activity for one state of the Online tab, or None (nothing to show).

    kind:      "lobby" | "search" | "match" (anything else: None)
    mode:      the search: "ranked" | "quick"
    fighters:  (this player's fighter, the opponent's) as names, or None while unknown
    set_score: (games won by this player, by the opponent) in a ranked set, or None
    start:     unix time the state began: Discord counts the time from there"""
    if kind == "lobby":
        details = t("In lobby")
    elif kind == "search":
        details = t("Searching ranked") if mode == "ranked" else t("Searching quick match")
    elif kind == "match":
        if ranked and set_score is not None:
            what = t("Ranked, Set {mine}-{theirs}", mine=set_score[0], theirs=set_score[1])
        elif ranked:
            what = t("Ranked")
        else:
            what = t("Casual")
        if fighters and all(fighters):
            details = t("In match: {mine} vs {theirs} ({what})", mine=fighters[0], theirs=fighters[1], what=what)
        else:
            details = t("In match ({what})", what=what)
    else:
        return None
    activity = {"details": details[:128], "instance": False}
    if start:
        activity["timestamps"] = {"start": int(start)}
    if large_image:
        activity["assets"] = {"large_image": large_image, "large_text": (large_text or "T5DR Online")[:128]}
    return activity


# ----------------------------------------------------------------------------- the presence thread
_UNSET = object()


class DiscordPresence:
    RETRY = 20.0          # seconds between attempts to reach Discord while it is not there
    LOST_RETRY = 5.0      # ... after a working connection broke (Discord restarted)
    MIN_INTERVAL = 4.0    # at most one SET_ACTIVITY per this many seconds (Discord: 5 per 20 s)

    def __init__(self, app_id, paths=None, log=None, clock=time.monotonic):
        self.app_id = valid_app_id(app_id)
        self.paths = list(paths) if paths else default_paths()
        self.log = log
        self.clock = clock
        self.conn = None
        self.user = None            # the Discord user name from READY (tests, a status line)
        self.sent = 0               # SET_ACTIVITY commands sent (tests)
        self.attempts = 0           # connection attempts (tests)
        self.last_error = None
        self._want = None
        self._shown = _UNSET        # what Discord shows now (_UNSET: unknown, e.g. after connecting)
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread = None
        self._logged_missing = False

    @property
    def connected(self):
        return self.conn is not None

    def start(self):
        if self._thread is None and self.app_id:
            self._thread = threading.Thread(target=self._run, name="discord-presence", daemon=True)
            self._thread.start()
        return self

    def update(self, activity):
        """What should show now (an activity_for() dict), or None for nothing. Returns at once."""
        with self._lock:
            changed = activity != self._want
            self._want = activity
        if changed:
            self._wake.set()

    def close(self, timeout=2.0):
        """Take the activity down, close the pipe, end the thread (waits at most `timeout`)."""
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout)

    def _note(self, text):
        if self.log is not None:
            try:
                self.log(text)
            except Exception:       # noqa: BLE001 -- logging must never break the presence
                pass

    def _run(self):
        next_try = 0.0
        last_send = -1e9
        while not self._stop.is_set():
            now = self.clock()
            if self.conn is None and now >= next_try:
                self.attempts += 1
                try:
                    self.conn = Connection.open(self.app_id, self.paths)
                    self.user = self.conn.user
                    self._shown = _UNSET
                    self._logged_missing = False
                    self._note("Discord Rich Presence: connected")
                except (OSError, TimeoutError, ValueError) as e:
                    self.last_error = str(e)
                    if not self._logged_missing:
                        self._logged_missing = True
                        self._note("Discord Rich Presence: Discord is not running here (trying again now and then)")
                    next_try = now + self.RETRY
            wait = max(0.05, next_try - now) if self.conn is None else 1.0
            if self.conn is not None:
                with self._lock:
                    want = self._want
                try:
                    self.conn.poll()
                    if want != self._shown:
                        due = last_send + self.MIN_INTERVAL
                        if now >= due:
                            answer = self.conn.set_activity(want)
                            self.sent += 1
                            last_send = now
                            self._shown = want
                            if answer.get("evt") == "ERROR":
                                self.last_error = str((answer.get("data") or {}).get("message"))
                                self._note(f"Discord Rich Presence: Discord refused the activity: {self.last_error}")
                        else:
                            wait = min(wait, due - now)
                except (OSError, TimeoutError, ValueError) as e:
                    self.last_error = str(e)
                    self._note("Discord Rich Presence: the connection to Discord ended")
                    self.conn.close(say_bye=False)
                    self.conn = None
                    next_try = now + self.LOST_RETRY
                    wait = self.LOST_RETRY
            self._wake.wait(min(max(wait, 0.05), 5.0))
            self._wake.clear()
        conn, self.conn = self.conn, None
        if conn is not None:
            try:
                if self._shown is not None:
                    conn.set_activity(None, timeout=1.0)        # take it down (Discord also does when the pipe closes)
            except (OSError, TimeoutError, ValueError):
                pass
            conn.close()


if __name__ == "__main__":       # python -m t5lobby.discord_rpc APP_ID: show "In lobby" for 30 s (a manual check)
    app = sys.argv[1] if len(sys.argv) > 1 else load_config()["application_id"]
    p = DiscordPresence(app, log=print).start()
    p.update(activity_for("lobby", start=time.time()))
    time.sleep(30)
    p.close()
