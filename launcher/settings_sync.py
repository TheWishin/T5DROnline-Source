"""One settings file per user for Tekken 5 DR, read and written by T5DR's own launcher and by OpenRecomp.

The same module is in both programs (T5DR: launcher/settings_sync.py, OpenRecomp: openrecomp/settings_sync.py); keep
the two copies identical (docs/SETTINGS_SYNC.md). Standard library only.

The file is settings.json next to online.json: %APPDATA%\\T5DROnline (T5_SETTINGS_DIR, then T5_ONLINE_DIR, move it).

    {"format": "t5dr-settings", "version": 1, "updated": <unix time>, "updated_by": "<program>",
     "values":   {"display": "borderless", ...},     every shared setting somebody saved
     "stamps":   {"display": <unix time>, ...},      when each one was last changed
     "installs": {"<install id>": {"seen": {...}}}}  the shared values this install's launcher.json had at the last sync

launcher.json stays in every T5DR folder: it keeps what belongs to that folder (LOCAL_KEYS) and a copy of the shared
values, so a T5DR launcher that does not know settings.json (1.2.2 and older) still shows them. What such a launcher
changes is found by comparing its launcher.json with "seen" and taken over at the next start of either program.
Fields this version does not know are written back unchanged, in the file and inside "values"."""
import hashlib
import json
import os
import tempfile
import time

FORMAT = "t5dr-settings"
VERSION = 1
FILE_NAME = "settings.json"
BACKUP_DIR = "settings-backup"
MAX_INSTALLS = 8               # "seen" is kept for the folders used last
MAX_BACKUPS = 20
LOCK_ERRORS = (5, 32, 33)      # access denied, sharing violation, lock violation: an antivirus or the other launcher

# What stays with one T5DR folder or one launcher and is never written to the shared file:
LOCAL_KEYS = frozenset((
    "pkg", "rap", "out",                    # this folder's package, licence and build output
    "language",                             # each launcher has its own language choice
    "background",                           # test switch of T5DR's launcher
    "clock_hint_shown", "controls_hint_shown", "gpu_build_warning",   # hints one launcher showed
))


def shared_key(key):
    return isinstance(key, str) and key not in LOCAL_KEYS


def shared_part(values):
    return {k: v for k, v in (values or {}).items() if shared_key(k)}


def shared_dir(environ=None):
    env = os.environ if environ is None else environ
    for name in ("T5_SETTINGS_DIR", "T5_ONLINE_DIR"):
        if env.get(name):
            return os.path.abspath(env[name])
    return os.path.join(env.get("APPDATA") or os.path.expanduser("~"), "T5DROnline")


def install_id(root):
    """A short name for one T5DR folder (the folder of its launcher.json)."""
    path = os.path.normcase(os.path.realpath(os.path.abspath(root)))
    return hashlib.sha256(path.encode("utf-8", "surrogatepass")).hexdigest()[:16]


def locked(error):
    return isinstance(error, PermissionError) or getattr(error, "winerror", None) in LOCK_ERRORS


def _stamp():
    return time.strftime("%Y%m%d-%H%M%S")


def read_json(path, seconds=2.0, sleep=time.sleep):
    """-> (object, "ok") | (None, "missing" | "corrupt" | "locked"). A held file is tried again for `seconds`; one
    that does not parse a few times too (the other launcher may be replacing it right now)."""
    deadline = time.monotonic() + seconds
    doubts = 0
    delay = 0.05
    while True:
        try:
            with open(path, "rb") as stream:
                value = json.loads(stream.read().decode("utf-8"))
            if isinstance(value, dict):
                return value, "ok"
            state = "corrupt"
        except FileNotFoundError:
            return None, "missing"
        except OSError:
            state = "locked"
        except (ValueError, RecursionError):
            state = "corrupt"
        doubts += state == "corrupt"
        if doubts >= 3 or time.monotonic() >= deadline:
            return None, state
        sleep(delay)
        delay = min(delay * 2, 0.4)


def write_json(path, value, seconds=2.0, sleep=time.sleep):
    """Write through a temporary file in the same folder; os.replace is tried again for `seconds` while another
    program holds the target. -> True when the file was replaced. Never writes in place: a reader must not see half
    a file. Raises nothing."""
    temporary = None
    try:
        folder = os.path.dirname(os.path.abspath(path))
        os.makedirs(folder, exist_ok=True)
        handle, temporary = tempfile.mkstemp(prefix=".settings-", suffix=".tmp", dir=folder)
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=1)
            stream.flush()
            os.fsync(stream.fileno())
        deadline = time.monotonic() + seconds
        delay = 0.05
        while True:
            try:
                os.replace(temporary, path)
                temporary = None
                return True
            except OSError as error:
                if not locked(error) or time.monotonic() >= deadline:
                    return False
                sleep(delay)
                delay = min(delay * 2, 0.4)
    except (OSError, TypeError, ValueError):
        return False
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except OSError:
                pass


def _mtime(path):
    try:
        return os.path.getmtime(path) if path else 0.0
    except OSError:
        return 0.0


class Store:
    """The shared file in one folder. `who` is written as "updated_by"."""

    def __init__(self, folder=None, who="", seconds=2.0, sleep=time.sleep, now=time.time):
        self.folder = os.path.abspath(folder or shared_dir())
        self.path = os.path.join(self.folder, FILE_NAME)
        self.who = who
        self.seconds = seconds
        self.sleep = sleep
        self.now = now
        self.notes = []            # what happened, for the launcher's log

    def read(self):
        """-> (document or None, state). A file that is not a settings object is moved aside (settings.json.corrupt-*)
        and reads as missing; a held file reads as "locked" and nothing is changed."""
        doc, state = read_json(self.path, self.seconds, self.sleep)
        if state == "ok" and not isinstance(doc.get("values"), dict):
            state = "corrupt"
        if state == "corrupt":
            aside = f"{self.path}.corrupt-{_stamp()}"
            count = 1
            while os.path.exists(aside):
                count += 1
                aside = f"{self.path}.corrupt-{_stamp()}-{count}"
            try:
                os.replace(self.path, aside)
                self.notes.append(f"settings: {self.path} could not be read; it is kept as {aside}")
            except OSError:
                return None, "locked"
            return None, "missing"
        if state != "ok":
            return None, state
        for field in ("stamps", "installs"):
            if not isinstance(doc.get(field), dict):
                doc[field] = {}
        return doc, "ok"

    def new(self):
        return {"format": FORMAT, "version": VERSION, "values": {}, "stamps": {}, "installs": {}}

    def write(self, doc):
        doc["format"] = FORMAT
        version = doc.get("version")
        doc["version"] = version if type(version) is int and version > VERSION else VERSION
        doc["updated"] = self.now()
        doc["updated_by"] = self.who
        installs = doc["installs"]
        for name in sorted(installs, key=lambda n: _used(installs[n]))[:-MAX_INSTALLS]:
            del installs[name]
        return write_json(self.path, doc, self.seconds, self.sleep)

    def backup(self, path, label):
        """Copy a file that is about to lose its say into settings-backup/<label>-<time>.bak. -> the copy or None."""
        try:
            with open(path, "rb") as stream:
                data = stream.read()
        except OSError:
            return None
        folder = os.path.join(self.folder, BACKUP_DIR)
        try:
            os.makedirs(folder, exist_ok=True)
            target = os.path.join(folder, f"{label}-{_stamp()}.bak")
            count = 1
            while os.path.exists(target):
                count += 1
                target = os.path.join(folder, f"{label}-{_stamp()}-{count}.bak")
            with open(target, "wb") as stream:
                stream.write(data)
            old = sorted(n for n in os.listdir(folder) if n.endswith(".bak"))
            for name in old[:-MAX_BACKUPS]:
                os.unlink(os.path.join(folder, name))
            self.notes.append(f"settings: {path} is kept as {target}")
            return target
        except OSError:
            return None


def _used(entry):
    used = entry.get("used") if isinstance(entry, dict) else None
    return used if isinstance(used, (int, float)) and not isinstance(used, bool) else 0


def _seen(doc, install, create=False):
    entry = doc["installs"].get(install)
    if not isinstance(entry, dict) or not isinstance(entry.get("seen"), dict):
        if not create:
            return None
        entry = doc["installs"][install] = {"seen": {}}
    return entry["seen"]


def _number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else 0


class Result:
    def __init__(self, values, state, wrote=False, imported=(), migrated=()):
        self.values = values          # the shared values to use ({} = nothing shared yet)
        self.state = state            # "ok" | "missing" (no shared file yet) | "locked" (could not be read: local values)
        self.wrote = wrote
        self.imported = tuple(imported)      # keys taken from launcher.json (changed by a launcher without the file)
        self.migrated = tuple(migrated)      # keys taken from `extra` (OpenRecomp's own old overrides)


def sync(store, install, local, local_path=None, extra=None, extra_path=None):
    """Bring the shared file and one T5DR folder together at a launcher's start.

    local: the object in that folder's launcher.json (None: there is none). extra: settings a launcher kept for
    itself before this file existed (OpenRecomp's overrides), with the file they are in.

    No shared file yet: launcher.json's values are the start. With `extra` the file is made now: where both name a
    setting and differ, the file written last wins (both are copied to settings-backup first). Without `extra`
    nothing is written here; the first save() makes the file.

    Shared file there: its values win, except a setting whose launcher.json value differs from "seen" -- a launcher
    that does not know the file changed it -- and whose launcher.json is newer than the setting's stamp. A folder seen
    for the first time gives only the settings the file does not have yet (its launcher.json is copied to
    settings-backup first). `extra` values win where their file is newer than the setting's stamp."""
    local_shared = shared_part(local)
    extra_shared = shared_part(extra)
    doc, state = store.read()
    if state == "locked":
        store.notes.append(f"settings: {store.path} is held by another program; this folder's own values are used")
        return Result(dict(local_shared, **extra_shared), "locked")
    local_time, extra_time = _mtime(local_path), _mtime(extra_path)
    if doc is None:
        if not extra_shared:
            return Result(local_shared, "missing")
        doc = store.new()
        values, stamps = doc["values"], doc["stamps"]
        for key, value in local_shared.items():
            values[key] = value
            stamps[key] = local_time
        migrated = []
        for key, value in extra_shared.items():
            if key not in values or values[key] == value or extra_time >= local_time:
                if values.get(key, extra) != value:
                    migrated.append(key)
                values[key] = value
                stamps[key] = extra_time
        if local_path and local_shared:
            store.backup(local_path, f"launcher-{install}")
        store.backup(extra_path, f"own-{install}")
        if local is not None:
            _seen(doc, install, True).update(local_shared)
            doc["installs"][install]["used"] = store.now()
        wrote = store.write(doc)
        if not wrote:
            store.notes.append(f"settings: {store.path} could not be written")
        return Result(dict(values), "ok" if wrote else "locked", wrote, (), migrated)
    values, stamps = doc["values"], doc["stamps"]
    seen = _seen(doc, install)
    before = json.dumps([values, seen], sort_keys=True, default=str)
    imported, migrated = [], []
    if seen is None and local_shared and any(values.get(k, v) != v for k, v in local_shared.items()):
        store.backup(local_path, f"launcher-{install}")
    for key, value in local_shared.items():
        if key not in values:
            values[key] = value
            stamps[key] = local_time
        elif (seen is not None and key in seen and value != seen[key] and value != values[key]
              and local_time >= _number(stamps.get(key))):
            values[key] = value
            stamps[key] = local_time
            imported.append(key)
    if extra_shared:
        store.backup(extra_path, f"own-{install}")
        for key, value in extra_shared.items():
            if key not in values or (values[key] != value and extra_time >= _number(stamps.get(key))):
                values[key] = value
                stamps[key] = extra_time
                migrated.append(key)
    wrote = False
    if local is not None:
        seen = _seen(doc, install, True)
        seen.clear()
        seen.update(local_shared)
    if json.dumps([values, seen], sort_keys=True, default=str) != before:
        if local is not None:
            doc["installs"][install]["used"] = store.now()
        wrote = store.write(doc)
        if not wrote:
            store.notes.append(f"settings: {store.path} could not be written")
    if imported:
        store.notes.append("settings: taken from launcher.json (changed by a launcher without the shared file): "
                           + ", ".join(sorted(imported)))
    return Result(dict(values), "ok", wrote, imported, migrated)


def save(store, install, changes, local=None, local_path=None, mirrored=None):
    """Write changed shared settings into the file, on top of what is in it now (another launcher's changes since
    this one started stay). -> True when they are in the file.

    No file yet: it is made from `local` (this folder's launcher.json object as it was before the change; the file is
    copied to settings-backup) plus the changes. `mirrored`: the shared values this folder's launcher.json holds
    after the caller wrote it (None: launcher.json was not written)."""
    changes = shared_part(changes)
    doc, state = store.read()
    if state == "locked":
        store.notes.append(f"settings: {store.path} is held by another program; not saved there")
        return False
    now = store.now()
    if doc is None:
        doc = store.new()
        base = shared_part(local)
        if base:
            stamp = _mtime(local_path) or now
            doc["values"].update(base)
            doc["stamps"].update({key: stamp for key in base})
            _seen(doc, install, True).update(base)
            if local_path:
                store.backup(local_path, f"launcher-{install}")
    elif not changes and mirrored is None:
        return True
    before = json.dumps([doc["values"], _seen(doc, install)], sort_keys=True, default=str)
    for key, value in changes.items():
        if doc["values"].get(key, doc) != value:
            doc["stamps"][key] = now
        doc["values"][key] = value
    if mirrored is not None:
        _seen(doc, install, True).update(shared_part(mirrored))
    if os.path.exists(store.path) and json.dumps([doc["values"], _seen(doc, install)], sort_keys=True,
                                                 default=str) == before:
        return True
    if install in doc["installs"]:
        doc["installs"][install]["used"] = now
    if store.write(doc):
        return True
    store.notes.append(f"settings: {store.path} could not be written")
    return False


def mirror(path, changes, seconds=2.0, sleep=time.sleep):
    """Put changed shared settings into a folder's launcher.json too, for a T5DR launcher that only reads that file.
    Every other field stays as it is. -> True when launcher.json now has them (False: no readable launcher.json, or
    it is held; nothing was changed)."""
    changes = shared_part(changes)
    current, state = read_json(path, seconds, sleep)
    if state != "ok":
        return False
    if all(key in current and current[key] == value for key, value in changes.items()):
        return True
    current.update(changes)
    return write_json(path, current, seconds, sleep)
