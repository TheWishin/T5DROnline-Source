"""Time played: how long the game process ran, summed per game in a small JSON file next to the launcher's settings.

The launcher counts while the process it started is alive (its own process handle, never the logs):

    store = Store(default_path(settings_dir, "T5DR_PLAYTIME_FILE"))
    session = track(proc, store, "t5dr")        # a daemon thread; ends by itself when the game does
    ...
    seconds = store.seconds("t5dr") + session.unsaved()

Rules:
- A session adds the time between two looks at the process (every BEAT seconds) and saves it at once, so a launcher
  that is killed loses at most one beat. A look that comes later than MAX_GAP after the one before (the PC slept or
  hibernated, the launcher was frozen) adds nothing for that stretch.
- A session is never longer than the process lived (Windows: its creation and exit times) nor than MAX_SESSION.
- The file is written to a temporary file beside it and renamed over it; the last good file is kept as
  playtime.json.bak when a session starts. An unreadable file is moved to playtime.json.bad and the copy is used.
- Nothing here is read by the game.
"""
import json
import os
import shutil
import tempfile
import threading
import time

FILE_NAME = "playtime.json"
VERSION = 1
BEAT = 30.0                    # seconds between two looks at the running game
MAX_GAP = 120.0                # a longer stretch between two looks is not counted (sleep, a frozen launcher)
MAX_SESSION = 24 * 3600.0      # one start of the game never counts more than this


def default_path(settings_dir, env_name=None):
    """playtime.json in the folder of the launcher's settings; `env_name` names a variable that overrides it (tests)."""
    override = os.environ.get(env_name) if env_name else None
    return override or os.path.join(settings_dir, FILE_NAME)


def split(seconds):
    """-> (hours, minutes), rounded down to the minute."""
    try:
        minutes = int(max(0.0, float(seconds)) // 60)
    except (TypeError, ValueError, OverflowError):
        minutes = 0
    return minutes // 60, minutes % 60


def text(seconds, template="Playtime: {hours} h {minutes} min"):
    """'Playtime: 12 h 5 min'. `template` is the (translated) sentence with {hours} and {minutes}."""
    hours, minutes = split(seconds)
    return template.format(hours=hours, minutes=minutes)


def _clean(data):
    """The games table of a loaded file, with only sane numbers; raises ValueError for anything else."""
    if not isinstance(data, dict) or not isinstance(data.get("games"), dict):
        raise ValueError("not a playtime file")
    games = {}
    for name, entry in data["games"].items():
        if not isinstance(name, str) or not isinstance(entry, dict):
            continue
        seconds, sessions = entry.get("seconds", 0), entry.get("sessions", 0)
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not 0 <= seconds < 1e12:
            seconds = 0.0
        if isinstance(sessions, bool) or not isinstance(sessions, int) or sessions < 0:
            sessions = 0
        last = entry.get("last_played")
        games[name] = {"seconds": float(seconds), "sessions": sessions,
                       "last_played": last if isinstance(last, str) else ""}
    return games


class Store:
    """The playtime file. Every change reads the file again first, so two launchers of one folder add up."""

    def __init__(self, path):
        self.path = os.path.abspath(path)
        self._lock = threading.Lock()

    def _read_file(self, path):
        with open(path, encoding="utf-8") as f:
            return _clean(json.load(f))

    def _load(self):
        try:
            return self._read_file(self.path)
        except FileNotFoundError:
            pass
        except (OSError, ValueError):
            try:                                   # keep the damaged file for the player, out of the way
                os.replace(self.path, self.path + ".bad")
            except OSError:
                pass
        try:
            return self._read_file(self.path + ".bak")
        except (OSError, ValueError):
            return {}

    def _write(self, games, path=None):
        path = path or self.path
        temporary = None
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            # a sibling file: the rename stays on one filesystem, and the old file is whole until it happens
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False, prefix=".playtime-",
                                             suffix=".tmp", dir=os.path.dirname(path)) as f:
                temporary = f.name
                json.dump({"version": VERSION, "games": games}, f, indent=1, sort_keys=True)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temporary, path)
            temporary = None
            return True
        except OSError:
            return False
        finally:
            if temporary is not None:
                try:
                    os.remove(temporary)
                except OSError:
                    pass

    def games(self):
        with self._lock:
            return self._load()

    def seconds(self, game):
        return self.games().get(game, {}).get("seconds", 0.0)

    def sessions(self, game):
        return self.games().get(game, {}).get("sessions", 0)

    def add(self, game, seconds, new_session=False):
        """Add `seconds` (may be negative: a session cut back to the process's lifetime) to a game's total.
        -> True when it is on disk."""
        with self._lock:
            games = self._load()
            entry = games.setdefault(game, {"seconds": 0.0, "sessions": 0, "last_played": ""})
            entry["seconds"] = round(max(0.0, entry["seconds"] + seconds), 3)
            if new_session:
                entry["sessions"] += 1
            entry["last_played"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            return self._write(games)

    def backup(self):
        """Keep the current file, when it is a good one, as playtime.json.bak."""
        with self._lock:
            try:
                self._read_file(self.path)
            except (OSError, ValueError):
                return False
            temporary = self.path + ".bak.tmp"
            try:
                shutil.copyfile(self.path, temporary)
                os.replace(temporary, self.path + ".bak")
                return True
            except OSError:
                return False


class Session:
    """One start of the game. start(), then beat() now and then while the process runs, then stop(). Every call
    saves what it counted. `clock` is a monotonic clock in seconds."""

    def __init__(self, store, game, clock=time.monotonic, max_gap=MAX_GAP, max_session=MAX_SESSION):
        self.store, self.game = store, game
        self.clock, self.max_gap, self.max_session = clock, max_gap, max_session
        self.counted = 0.0         # seconds of this session
        self._owed = 0.0           # counted, but the file could not be written yet
        self._new_owed = False     # the session itself is not in the file yet
        self._last = None          # the clock at the last look; None = not running
        self._lock = threading.Lock()

    def start(self):
        with self._lock:
            if self._last is not None:
                return
            self.store.backup()
            self._last = self.clock()
            self.counted = self._owed = 0.0
            self._new_owed = not self.store.add(self.game, 0.0, new_session=True)

    def _step(self):
        now = self.clock()
        gap = now - self._last
        self._last = now
        if not 0 < gap <= self.max_gap:            # slept, frozen, or a clock that went back: not played
            return 0.0
        gap = min(gap, max(0.0, self.max_session - self.counted))
        self.counted += gap
        return gap

    def _save(self, seconds):
        self._owed += seconds
        if (self._owed or self._new_owed) and self.store.add(self.game, self._owed, new_session=self._new_owed):
            self._owed = 0.0
            self._new_owed = False

    def beat(self):
        with self._lock:
            if self._last is not None:
                self._save(self._step())

    def stop(self, lifetime=None):
        """The game ended. `lifetime`: how long its process lived, in seconds, when known: the session is cut back
        to it. -> the session's seconds."""
        with self._lock:
            if self._last is None:
                return self.counted
            added = self._step()
            self._last = None
            if lifetime is not None and 0 <= lifetime < self.counted:
                added -= self.counted - lifetime
                self.counted = float(lifetime)
            self._save(added)
            return self.counted

    def unsaved(self):
        """Seconds played since the last save (for a display between two beats)."""
        with self._lock:
            if self._last is None:
                return self._owed
            gap = self.clock() - self._last
            return self._owed + (gap if 0 < gap <= self.max_gap else 0.0)

    def running(self):
        return self._last is not None


def process_lifetime(proc):
    """Seconds between the creation and the exit of an ended subprocess.Popen (Windows: from the process handle),
    else None."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes
        handle = getattr(proc, "_handle", None)
        if not handle:
            return None
        times = [wintypes.FILETIME() for _ in range(4)]
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
        k32.GetProcessTimes.restype = wintypes.BOOL
        if not k32.GetProcessTimes(int(handle), *[ctypes.byref(x) for x in times]):
            return None
        created = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
        ended = (times[1].dwHighDateTime << 32) | times[1].dwLowDateTime
        if not created or ended < created:
            return None
        return (ended - created) / 1e7
    except Exception:           # noqa: BLE001 -- the count must never stop a game
        return None


def track(proc, store, game, beat=BEAT, session=None):
    """Count a started game: a daemon thread looks at `proc` (a subprocess.Popen) every `beat` seconds until it has
    ended. -> the Session (its .thread is the watcher)."""
    session = session or Session(store, game)
    session.start()

    def watch():
        try:
            while True:
                try:
                    proc.wait(timeout=beat)
                    break
                except Exception as e:      # noqa: BLE001
                    if type(e).__name__ != "TimeoutExpired":
                        break
                    session.beat()
        finally:
            try:
                ended = proc.poll() is not None
            except Exception:               # noqa: BLE001
                ended = False
            session.stop(process_lifetime(proc) if ended else None)

    session.thread = threading.Thread(target=watch, name="playtime", daemon=True)
    session.thread.start()
    return session
