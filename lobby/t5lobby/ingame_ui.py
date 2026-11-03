"""Version 1 host menu channel, independent of the persistent fight command sequence.

The worker owns file I/O. The launcher thread owns dispatch; an action is reserved before
dispatch and remains pending until its asynchronous lobby call has finished. This is a
local UI request, never authority to start a fight or inject a simulated pad input.
"""
import copy
import json
import os
import queue
import secrets
import threading
import time


VERSION = 1
CAP = "ingame_rematch_v1"
MAX_BYTES = 16384
HEALTH_SECONDS = 3.0
ACTIONS = frozenset(("accept", "decline", "next", "ready", "sit_out", "back_to_line", "lobby"))


def _integer(value):
    return isinstance(value, int) and not isinstance(value, bool) and 0 < value <= 0x7fffffff


def _object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate UI field")
        value[key] = item
    return value


def _bad_constant(_value):
    raise ValueError("nonfinite UI value")


def _read(path):
    try:
        with _open_shared(path) as stream:
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            return None
        value = json.loads(raw, object_pairs_hook=_object, parse_constant=_bad_constant)
        return value if isinstance(value, dict) else None
    except (OSError, ValueError, UnicodeError, RecursionError):
        return None


def _open_shared(path):
    if os.name != "nt":
        return open(path, "rb")
    import ctypes
    import msvcrt
    from ctypes import wintypes
    create = ctypes.windll.kernel32.CreateFileW
    create.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                       wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE)
    create.restype = wintypes.HANDLE
    handle = create(path, 0x80000000, 1 | 2 | 4, None, 3, 0x80, None)
    if handle == ctypes.c_void_p(-1).value:
        raise OSError(ctypes.get_last_error(), "cannot read UI channel")
    try:
        fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    except OSError:
        close = ctypes.windll.kernel32.CloseHandle
        close.argtypes = (wintypes.HANDLE,)
        close(handle)
        raise
    return os.fdopen(fd, "rb")


class IngameUI:
    def __init__(self, directory, session, clock=time.monotonic, worker=True):
        self.dir = os.path.abspath(directory)
        self.session = str(session)
        self.generation = secrets.token_hex(16)
        self.clock = clock
        self.lock = threading.RLock()
        self.events = queue.Queue()
        self.stop = threading.Event()
        self.revision = 1
        self.ready_sequence = 0
        self.ready_revision = -1
        self.ready_at = None
        self.seen = 0
        self.pending = None
        self.deadline = 0.0
        self.display_deadline = None
        self.required_revision = 0
        self.document = self._base()
        self.document.update(rev=1, prompt="", match="", kind="hidden", allowed=[],
                             remaining_ms=0, ack_seq=0, ack_status="")
        self.thread = None
        if worker:
            self.thread = threading.Thread(target=self._work, daemon=True, name="t5-ingame-ui")
            self.thread.start()

    def _base(self):
        return {"v": VERSION, "generation": self.generation, "session": self.session}

    def environment(self):
        return {"T5_INGAME_REMATCH": "1", "T5_UI_DIR": self.dir,
                "T5_UI_GENERATION": self.generation, "T5_UI_SESSION": self.session}

    @property
    def healthy(self):
        with self.lock:
            return self.ready_at is not None and self.clock() - self.ready_at < HEALTH_SECONDS

    @property
    def active(self):
        with self.lock:
            return (self.healthy and self.ready_revision >= self.required_revision
                    and self.document["kind"] != "hidden" and self.clock() < self.deadline)

    def offer(self, match, kind, actions, seconds, labels=None, room_mode="casual", policy="both_confirm"):
        if not isinstance(match, str) or not 0 < len(match) <= 40:
            return False
        if not isinstance(seconds, (float, int)) or isinstance(seconds, bool) or not 0 < seconds <= 120:
            return False
        with self.lock:
            self.revision += 1
            self.deadline = self.clock() + seconds
            self.display_deadline = None
            ack = {k: self.document[k] for k in ("ack_seq", "ack_status")}
            self.document = dict(self._base(), rev=self.revision, prompt=str(self.revision), match=match,
                                 kind=kind, allowed=list(dict.fromkeys(a for a in actions if isinstance(a, str) and a in ACTIONS)),
                                 remaining_ms=int(seconds * 1000), room_mode=room_mode, policy=policy, **ack)
            self.labels(labels or {})
            self.required_revision = self.revision
        return True

    def labels(self, values, require_ready=True):
        with self.lock:
            changed = False
            for key in ("title", "body", "confirm", "cancel", "next", "waiting"):
                if isinstance(values.get(key), str):
                    value = values[key][:512 if key == "body" else 160]
                    if self.document.get(key) != value:
                        changed = True
                        self.document[key] = value
            if changed:
                self.revision += 1
                self.document["rev"] = self.revision
                if require_ready:
                    self.required_revision = self.revision

    def countdown(self, seconds=None):
        with self.lock:
            self.display_deadline = self.clock() + seconds if seconds is not None else None
            self.revision += 1
            self.document["rev"] = self.revision

    def hide(self):
        with self.lock:
            self.revision += 1
            self.document.update(rev=self.revision, kind="hidden", allowed=[], remaining_ms=0)
            self.deadline = 0.0

    def waiting(self):
        with self.lock:
            self.display_deadline = None
            self.revision += 1
            self.document.update(rev=self.revision, kind="waiting", allowed=[])
            self.document["body"] = self.document.get("waiting", self.document.get("body", ""))

    def complete(self, sequence, success):
        with self.lock:
            if self.pending is not None and self.pending["seq"] == sequence:
                self.document.update(ack_seq=sequence, ack_status="ok" if success else "rejected")
                self.pending = None
                self.revision += 1
                self.document["rev"] = self.revision

    def _identity(self, value):
        return (isinstance(value, dict) and type(value.get("v")) is int and value["v"] == VERSION
                and value.get("generation") == self.generation and value.get("session") == self.session)

    def receive(self, value):
        """Reserve one validated action. Also used by deterministic, game-free regression tests."""
        with self.lock:
            if not self._identity(value) or not _integer(value.get("seq")):
                return
            sequence = value["seq"]
            if sequence <= self.seen or self.pending is not None:
                return
            if value.get("prompt") != self.document["prompt"] or value.get("match") != self.document["match"]:
                # The game retains its one outstanding request across prompt changes.
                # Reject stale requests from this launch explicitly so it can re-arm.
                self.seen = sequence
                self.revision += 1
                self.document.update(ack_seq=sequence, ack_status="rejected", rev=self.revision)
                return
            self.seen = sequence
            if (self.clock() >= self.deadline or not self.active
                    or value.get("action") not in self.document["allowed"]):
                self.document.update(ack_seq=sequence, ack_status="rejected")
                self.revision += 1
                self.document["rev"] = self.revision
                return
            self.pending = copy.deepcopy(value)
            self.events.put(("action", copy.deepcopy(value)))

    def pump(self):
        """One worker iteration; no launcher callbacks and no simulation work."""
        ready = _read(os.path.join(self.dir, "ui_ready.json"))
        with self.lock:
            if self._identity(ready) and ready.get("cap") == CAP and ready.get("ready") is False:
                self.ready_at = None
            if (self._identity(ready) and ready.get("cap") == CAP and ready.get("ready") is True
                    and _integer(ready.get("seq")) and ready["seq"] > self.ready_sequence):
                self.ready_sequence = ready["seq"]
                revision = ready.get("rev")
                if isinstance(revision, int) and not isinstance(revision, bool) and revision >= 0:
                    self.ready_revision = revision
                self.ready_at = self.clock()
            if self.document["kind"] != "hidden" and self.clock() >= self.deadline:
                self.hide()
                self.events.put(("expired", None))
        self.receive(_read(os.path.join(self.dir, "ui_action.json")))
        with self.lock:
            document = copy.deepcopy(self.document)
            deadline = self.display_deadline if self.display_deadline is not None else self.deadline
            document["remaining_ms"] = max(0, int((deadline - self.clock()) * 1000))
        try:
            raw = json.dumps(document, ensure_ascii=False).encode("utf-8")
        except (ValueError, UnicodeError):
            return
        if len(raw) > MAX_BYTES:
            return
        try:
            os.makedirs(self.dir, exist_ok=True)
            path = os.path.join(self.dir, "ui.json")
            with open(path + ".tmp", "wb") as stream:
                stream.write(raw)
            os.replace(path + ".tmp", path)
        except OSError:
            pass                 # stale capability triggers the launcher's ordinary fallback

    def _work(self):
        while not self.stop.is_set():
            self.pump()
            self.stop.wait(0.1)

    def close(self):
        self.stop.set()
        if self.thread is not None:
            self.thread.join(timeout=1.0)
