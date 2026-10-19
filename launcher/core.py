"""Launcher logic without any UI: settings, the build process, the game process.

The Tk front end (t5dr_launcher.pyw) and the online module (online.py) use
this; nothing here imports tkinter, so it can be tested from a console.
"""
import ctypes
import datetime
import glob
import hashlib
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
sys.path.insert(0, TOOLS)
import build_game  # noqa: E402  (constants, pkg/sfo readers, code_id)
import prereqs     # noqa: E402
import run_game    # noqa: E402

# The player's language (lobby/t5lobby/i18n.py): t("English text", name=value) and N_("text") to mark a text that
# is translated where it is shown. The launcher chooses the language once, at start (apply_language).
sys.path.append(os.path.join(ROOT, "lobby"))      # (appended: lobby/run.py must not hide another run module)
try:
    from t5lobby import i18n  # noqa: E402
    from t5lobby.i18n import N_, t, translate_message  # noqa: E402,F401
    I18N = True
except ImportError:     # lobby/ is missing from this copy: the launcher stays usable, in English
    I18N = False

    def N_(text):
        return text

    def t(text, /, **values):
        return text.format(**values) if values else text

    def translate_message(msg):
        return msg

IS_WIN = os.name == "nt"
CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_PROCESS_GROUP = 0x00000200
BELOW_NORMAL_PRIORITY_CLASS = 0x00004000   # inherited by every tool the build starts
SETTINGS_FILE = os.path.join(ROOT, "launcher.json")
LAUNCHER_LOG = os.path.join(ROOT, "launcher.log")     # what the launcher did; goes into the problem report
LAUNCHER_LOG_MAX = 512 * 1024                         # then it moves to launcher.log.1 (one old copy is kept)
ISSUES_URL = "https://github.com/TheWishin/T5DROnline/issues"
_log_lock = threading.Lock()


def log(msg, path=None):
    """Add one timestamped line to launcher.log. Never raises: a full disk must not stop the launcher."""
    path = path or LAUNCHER_LOG
    text = " | ".join(str(msg).rstrip().splitlines()) or "-"
    line = f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {text}\n"
    with _log_lock:
        try:
            try:
                if os.path.getsize(path) > LAUNCHER_LOG_MAX:
                    os.replace(path, path + ".1")
            except OSError:
                pass
            with open(path, "a", encoding="utf-8", errors="replace") as f:
                f.write(line)
        except OSError:
            pass


def release_info():
    """{'version': ..} from release.json (written by package_release.py), or a dev marker."""
    p = os.path.join(ROOT, "release.json")
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    return {"version": "dev", "name": "T5DR Online (development checkout)"}


# --------------------------------------------------------------------------- settings

DEFAULTS = {
    "pkg": "",
    "rap": "",
    "out": "",                 # empty: <package folder>/native
    "nickname": "",
    "display": "window",       # window | window1080 | window1440 | maximized | borderless
    "internal_res": "native",  # internal resolution: lowest | lower | native | 1080p | 1440p | 4k, PS3_INTERNAL_RES
    "vsync": "on",             # on | off (PS3_VSYNC=0): only how pictures reach the screen; the game stays at 60 fps
    "stage_blur": "on",        # on | off (PS3_STAGE_BLUR=0): the blur / glow some stages put on the picture
    "input_delay": "auto",     # online input delay: auto (by ping) | 0 | 1 | 2 frames, T5_RB_NET_DELAY
    "training": "frames",      # training overlay in Practice: off | inputs | frames (inputs + frame data), T5_TRAINING
    "training_all": False,     # ... also in the other offline modes (T5_TRAINING_ALL=1)
    "training_online": False,  # ... also online, this PC's own inputs only (T5_TRAINING_ONLINE=1)
    "router_ports": True,      # online: forward the game's port on the router for a match (PCP / NAT-PMP / UPnP)
    "language": "auto",        # auto (the Windows language) | en | de | es | ko | ja | pt-BR | fr -- applies at start
    "discord_presence": False, # online: show the lobby / search / match in Discord (Rich Presence, docs/ONLINE.md)
    "discord_app_id": "",      # ... with this Discord application instead of the release's (lobby data/discord.json)
    "mute": False,
    "background": False,       # start minimized without focus (testing)
    "extra_env": "",           # NAME=VALUE lines
    "low_priority": False,     # build at below-normal priority: the PC stays responsive, the build is slower
    "power_saving": "auto",    # auto | on | off: PS3_LAPTOP (POWER_SAVING)
    "unlock_stages": False,    # offline: the Tekken 5 stages without clearing Arcade (T5_UNLOCK_STAGES, docs/DIRECTFIGHT.md "Unlocks")
    "unlock_items": False,     # offline: every customization item free in the item shop (T5_UNLOCK_ITEMS)
}


# What the Settings box offers: Auto, then every language in its own name (those names are never translated).
LANGUAGE_CHOICES = [("auto", N_("Auto (Windows language)"))] + (list(i18n.LANGUAGES.items()) if I18N else [])


def clock(seconds):
    """m:ss for a number of seconds."""
    s = max(0, int(seconds))
    return f"{s // 60}:{s % 60:02d}"


def apply_language(settings):
    """Switch the texts to the language in the settings ('auto' = the Windows language). -> the language code."""
    return i18n.init(settings["language"]) if I18N else "en"


def ui_family(default="Segoe UI"):
    """The font family for texts in the launcher's language (Segoe UI; a Korean / Japanese font for those)."""
    return i18n.ui_family(default) if I18N else default


class Settings(dict):
    def __init__(self, path=SETTINGS_FILE):
        super().__init__(DEFAULTS)
        self.path = path
        try:
            with open(path, encoding="utf-8") as f:
                saved = json.load(f)
            self.update({k: v for k, v in saved.items() if k in DEFAULTS})
            # launcher.json of 0.1.8 .. 1.0.x: "3D resolution" (render_scale 1 / 0.75 / 0.5)
            if "internal_res" not in saved and "render_scale" in saved:
                self["internal_res"] = OLD_RENDER_SCALES.get(str(saved["render_scale"]), "native")
        except (OSError, ValueError, AttributeError):
            pass
        if self["internal_res"] not in INTERNAL_RES:
            self["internal_res"] = "native"
        if not isinstance(self["vsync"], str) or self["vsync"] not in VSYNC_MODES:
            self["vsync"] = "on"
        if not isinstance(self["power_saving"], str) or self["power_saving"] not in POWER_SAVING:
            self["power_saving"] = "auto"
        if not isinstance(self["stage_blur"], str) or self["stage_blur"] not in STAGE_BLUR_MODES:
            self["stage_blur"] = "on"
        if not isinstance(self["training"], str) or self["training"] not in TRAINING_MODES:
            self["training"] = "frames"

    def save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(dict(self), f, indent=1)
        except OSError:
            pass

    @property
    def out_dir(self):
        return os.path.abspath(self["out"] or os.path.join(ROOT, "native"))

    def env_overrides(self):
        env = {}
        if self["nickname"].strip():
            env["PS3_NICKNAME"] = self["nickname"].strip()[:16]
        if self["mute"]:
            env["PS3_NO_AUDIO"] = "1"
        if self["background"]:
            env["PS3_WINDOW_BACKGROUND"] = "1"
        if self["internal_res"] in INTERNAL_RES and self["internal_res"] != "native":
            env["PS3_INTERNAL_RES"] = self["internal_res"]
        if self["vsync"] == "off":
            env["PS3_VSYNC"] = "0"
        if self["power_saving"] in ("on", "off"):       # auto: the game decides (PS3_LAPTOP unset)
            env["PS3_LAPTOP"] = "1" if self["power_saving"] == "on" else "0"
        if self["stage_blur"] == "off":
            env["PS3_STAGE_BLUR"] = "0"
        if self["display"] == "borderless":
            # the game's own borderless fullscreen (Alt+Enter/F11 toggle it, Esc leaves it first,
            # it follows the monitor), not a restyled window from outside
            env["PS3_FULLSCREEN"] = "1"
        if self["input_delay"] in INPUT_DELAYS:
            env["T5_RB_NET_DELAY"] = self["input_delay"]
        if self["training"] in TRAINING_MODES:
            env["T5_TRAINING"] = self["training"]
            if self["training"] != "off":
                if self["training_all"]:
                    env["T5_TRAINING_ALL"] = "1"
                if self["training_online"]:
                    env["T5_TRAINING_ONLINE"] = "1"
                env["T5_TRAINING_LANG"] = i18n.resolve(self["language"]) if I18N else "en"
        # Unlocks count offline only: a game started for online play answers as a fresh save does,
        # whatever it is given (both PCs must build the same select screens and stage lists).
        if self["unlock_stages"]:
            env["T5_UNLOCK_STAGES"] = "1"
        if self["unlock_items"]:
            env["T5_UNLOCK_ITEMS"] = "1"
        for line in self["extra_env"].splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
        return env


# --------------------------------------------------------------------------- input files

def describe_pkg(path):
    """(ok, level, text) for the chosen package; level is 'ok', 'warn' or 'error'."""
    if not path:
        return False, "error", t("No package chosen.")
    if not os.path.exists(path):
        return False, "error", t("File not found.")
    try:
        cid = build_game.pkg_content_id(path)
    except OSError as e:
        return False, "error", t("Cannot read the file: {error}", error=e)
    size = os.path.getsize(path)
    if cid is None:
        return False, "error", t("This is not a PS3 package (.pkg).")
    if cid == build_game.CONTENT_ID:
        return True, "ok", t("{id}  ({size} bytes) -- the supported version", id=cid, size=f"{size:,}")
    if build_game.TITLE_ID in cid:
        return True, "warn", t("{id}  ({size} bytes) -- Tekken 5 DR, but not the supported package ({supported}). "
                               "The build will most likely refuse it.", id=cid, size=f"{size:,}",
                               supported=build_game.CONTENT_ID)
    return True, "warn", t("{id}  ({size} bytes) -- not Tekken 5 DR Online ({title_id}).", id=cid, size=f"{size:,}",
                           title_id=build_game.TITLE_ID)


def describe_rap(path, pkg=None):
    if not path:
        return False, "error", t("No license chosen.")
    if not os.path.exists(path):
        return False, "error", t("File not found.")
    if os.path.getsize(path) != 16:
        return False, "error", t("Not a PS3 license: a .rap file is exactly 16 bytes.")
    name = os.path.basename(path)
    if build_game.CONTENT_ID in name:
        return True, "ok", t("{name} -- matches the supported package", name=name)
    if pkg:
        try:
            cid = build_game.pkg_content_id(pkg)
        except OSError:
            cid = None
        if cid and cid in name:
            return True, "ok", t("{name} -- matches the package", name=name)
    return True, "warn", t("{name} -- the name does not match the package's content ID; it may be the wrong "
                           "license.", name=name)


# Known folders (SHGetKnownFolderPath): Downloads, Desktop and Documents are often not under
# %USERPROFILE% -- OneDrive moves Desktop/Documents to %OneDrive%\Desktop (\Dokumente on a German
# Windows), and anyone can relocate them (Properties > Location, e.g. to D:\).
KNOWN_FOLDERS = {
    "Downloads": "{374DE290-123F-4565-9164-39C4925E467B}",
    "Desktop": "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}",
    "Documents": "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}",
}
# A file that only exists in the cloud (OneDrive "Files On-Demand"): reading it starts a download.
CLOUD_ONLY = 0x00001000 | 0x00040000 | 0x00400000   # OFFLINE | RECALL_ON_OPEN | RECALL_ON_DATA_ACCESS


def known_folder(guid):
    """Path of a Windows known folder, or None."""
    if not IS_WIN:
        return None

    class GUID(ctypes.Structure):
        _fields_ = [("d1", ctypes.c_uint32), ("d2", ctypes.c_uint16), ("d3", ctypes.c_uint16),
                    ("d4", ctypes.c_ubyte * 8)]
    g = GUID()
    try:
        if ctypes.oledll.ole32.CLSIDFromString(ctypes.c_wchar_p(guid), ctypes.byref(g)):
            return None
        out = ctypes.c_wchar_p()
        shell32 = ctypes.windll.shell32
        if shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(out)) != 0:
            return None
        try:
            return out.value
        finally:
            ctypes.windll.ole32.CoTaskMemFree(out)
    except (OSError, AttributeError):
        return None


def candidate_roots():
    """Where find_candidates() looks: the real Downloads/Desktop/Documents (known folders), the
    plain %USERPROFILE% ones, OneDrive's, and the release folder -- each once."""
    home = os.path.expanduser("~")
    roots = []
    for name, guid in KNOWN_FOLDERS.items():
        roots += [known_folder(guid), os.path.join(home, name)]
    for var in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        od = os.environ.get(var)
        if od:
            roots += [os.path.join(od, d) for d in ("Desktop", "Documents", "Dokumente", "Downloads")]
    roots.append(ROOT)
    seen, out = set(), []
    for r in roots:
        if r and os.path.isdir(r) and os.path.normcase(os.path.abspath(r)) not in seen:
            seen.add(os.path.normcase(os.path.abspath(r)))
            out.append(r)
    return out


def cloud_only(path):
    """True for a OneDrive (or other cloud) placeholder whose data is not on this PC."""
    try:
        return bool(getattr(os.stat(path), "st_file_attributes", 0) & CLOUD_ONLY)
    except OSError:
        return False


def find_candidates(roots=None):
    """Look in the usual places for a .pkg/.rap pair the player probably wants. Files that are only
    in the cloud are skipped: reading one would download it (a .pkg is 600 MB)."""
    pkgs, raps = [], []
    for r in (roots if roots is not None else candidate_roots()):
        for pat, lst in (("*.pkg", pkgs), ("*.rap", raps)):
            for depth in ("", "*", os.path.join("*", "*")):
                lst.extend(glob.glob(os.path.join(r, depth, pat)))
    good = [p for p in pkgs if not cloud_only(p) and _safe_cid(p) == build_game.CONTENT_ID]
    rap = [r for r in raps if build_game.CONTENT_ID in os.path.basename(r) and not cloud_only(r)
           and os.path.getsize(r) == 16]
    return (good[0] if good else None), (rap[0] if rap else None)


# --------------------------------------------------------------------------- the install folder

# Deepest file the build and the game write below the release folder (native\gamedata\dev_hdd0\
# home\00000001\savedata\<folder>\<file>, the clang headers in toolchain\): about 100 characters.
# Windows' classic limit is 260 (MAX_PATH); parts of the runtime keep MAX_PATH buffers (UTF-8 bytes).
PATH_ROOM = 100
MAX_PATH = 260
EXAMPLE_DIR = r"C:\Games\T5DR"


def install_warnings(root=ROOT, out=None):
    """Plain sentences about folder choices that break or slow the build/game (Build tab)."""
    warn = []
    out = out or os.path.join(root, "native")
    for label, path in ((t("This folder"), root), (t("The output folder"), out)):
        n = len(os.path.abspath(path).encode("utf-8"))
        if n + PATH_ROOM > MAX_PATH:
            warn.append(t("{label} has a long path ({bytes} bytes). Windows allows only {max} characters for "
                          "a file path, and the build writes files about {room} characters deeper. Move the "
                          "folder to a short path, for example {example}.", label=label, bytes=n, max=MAX_PATH,
                          room=PATH_ROOM, example=EXAMPLE_DIR))
            break
    norm = os.path.normcase(os.path.abspath(root))
    for var in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        od = os.environ.get(var)
        if od and (norm + os.sep).startswith(os.path.normcase(os.path.abspath(od)) + os.sep):
            warn.append(t("This folder is inside OneDrive. OneDrive would upload about 1 GB of game data and can "
                          "lock files while the game is built. Move the folder out of OneDrive, for example to "
                          "{example}.", example=EXAMPLE_DIR))
            break
    pf = [os.environ.get(v) for v in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432")]
    if any(p and (norm + os.sep).startswith(os.path.normcase(p) + os.sep) for p in pf):
        warn.append(t("This folder is in Program Files, where Windows does not let programs write. "
                      "Move it to a folder of your own, for example {example}.", example=EXAMPLE_DIR))
    elif os.path.isdir(root) and not _writable(root):
        warn.append(t("Windows does not let the launcher write into this folder. Move it to a folder of your "
                      "own, for example {example}.", example=EXAMPLE_DIR))
    if norm.startswith("\\"):
        warn.append(t("This folder is on a network share. Building and playing from there is slow and was "
                      "not tested; copy it to a local drive."))
    return warn


def _writable(d):
    try:
        import tempfile
        with tempfile.TemporaryFile(dir=d):
            pass
        return True
    except OSError:
        return False


def _safe_cid(p):
    try:
        return build_game.pkg_content_id(p)
    except OSError:
        return None


# --------------------------------------------------------------------------- build state

def game_state(out):
    """What the Play tab shows: dict(built, ok, text, needs_rebuild, elf_sha1)."""
    exe = os.path.join(out, "build", "cmake", "t5dr.exe")
    elf = os.path.join(out, "game", "EBOOT.elf")
    stamp = os.path.join(out, "build", "t5dr_build.json")
    st = dict(built=False, ok=False, needs_rebuild=False, elf_sha1=None, text="")
    if not os.path.exists(exe):
        st["text"] = t("The game is not built yet. Open the Build tab, choose your .pkg and .rap, press BUILD GAME.")
        return st
    st["built"] = True
    if not os.path.exists(elf):
        st["text"] = t("t5dr.exe is there but the game data is missing. Build again.")
        return st
    h = build_game.sha1(elf)
    st["elf_sha1"] = h
    if h != build_game.ELF_SHA1:
        st["text"] = t("The decrypted program has SHA-1 {sha}..., not the supported version. "
                       "Build again from the supported package.", sha=h[:12])
        return st
    info = {}
    try:
        with open(stamp) as f:
            info = json.load(f)
    except (OSError, ValueError):
        pass
    if info.get("code_id") != build_game.code_id():
        st["needs_rebuild"] = True
        st["text"] = t("Build the game once (about 2 minutes): this version of the launcher changes the game code. "
                       "Click BUILD GAME. Your unpacked game and saves are kept; only the code is translated and "
                       "compiled again.")
        return st
    st["ok"] = True
    when = info.get("built", "?").replace("T", " ")
    st["text"] = t("Ready: {title_id} v{version}, program SHA-1 {sha}... verified, built {when}.",
                   title_id=build_game.TITLE_ID, version=build_game.TITLE_VERSION, sha=h[:12], when=when)
    return st


# --------------------------------------------------------------------------- build process

STEP_TITLES = {          # English; t(STEP_TITLES[step]) where it is shown
    "deps": N_("Recompiler"), "keys": N_("Key data"), "decrypt": N_("Check & decrypt"), "unpack": N_("Unpack"),
    "vfs": N_("Game files"), "lift": N_("Translate code"), "spu": N_("Sound core"), "compile": N_("Compile"),
}
# Rough share of the total time per step (measured on a 16-core PC; see docs/RELEASE.md).
STEP_WEIGHT = {"deps": 1, "keys": 1, "decrypt": 2, "unpack": 12, "vfs": 1, "lift": 40, "spu": 8, "compile": 35}
RE_STEP = re.compile(r"^\[(\w+)\]\s*$")
RE_NINJA = re.compile(r"^\[(\d+)/(\d+)\]")
RE_FUNCS = re.compile(r"(\d+)/(\d+) functions")
# The lift step printed nothing for this long: the Build tab says so. The lifter itself prints at least every ~30 s
# while it works (ps3recomp patch 0048: "... still lifting: 3 chunks left, elapsed 1.5m").
LIFT_QUIET_S = 180


def build_line_events(step, line):
    """What one line of build_game.py's output means for the Build tab: (the step it belongs to, [events])."""
    events = [("line", line)]
    m = RE_STEP.match(line)
    if m and m.group(1) in STEP_TITLES:
        step = m.group(1)
        events.append(("step", step))
    elif line.strip().startswith("already done") or "nothing to fetch" in line:
        events.append(("skip", step))
    elif line.startswith("ERROR:"):
        events.append(("error", line[6:].strip()))
    elif step == "compile" and RE_NINJA.match(line):
        n, d = map(int, RE_NINJA.match(line).groups())
        events.append(("sub", n / max(d, 1)))
    elif step == "lift" and RE_FUNCS.search(line):
        n, d = map(int, RE_FUNCS.search(line).groups())
        # the lifter reports twice (translate, then write): weight 70/30. Its other lines (the heartbeat, notices
        # about a stopped worker) never contain "<n>/<m> functions", so they leave the percentage alone.
        frac = n / max(d, 1)
        events.append(("sub", 0.7 * frac if "lifted" in line else 0.7 + 0.3 * frac))
    return step, events


def lift_quiet_hint(step, quiet_s):
    """The Build tab's hint once the translation step has printed nothing for LIFT_QUIET_S seconds, else None."""
    if step != "lift" or quiet_s < LIFT_QUIET_S:
        return None
    return t("The translation step has printed nothing for {minutes} minutes. On a slow or busy PC it may still be "
             "working. If nothing changes, close other programs, press Cancel and then BUILD GAME again; build.log "
             "has the details.", minutes=int(quiet_s // 60))


class BuildRun:
    """Runs tools/build_game.py in the background; events go to `self.events` (a Queue):
       ('line', text) ('step', name) ('skip', name) ('sub', fraction) ('error', text) ('end', code)."""

    def __init__(self, pkg, rap, out, force=False, steps=None, low_priority=False):
        self.out = out
        self.low_priority = low_priority
        self.events = queue.Queue()
        self.proc = None
        self.cancelled = False
        os.makedirs(out, exist_ok=True)
        self.log_path = os.path.join(out, "build.log")
        cmd = [sys.executable, os.path.join(TOOLS, "build_game.py"), "--out", out]
        if pkg:
            cmd += ["--pkg", pkg]
        if rap:
            cmd += ["--rap", rap]
        if force:
            cmd.append("--force")
        if steps:
            cmd += ["--steps"] + list(steps)
        self.cmd = cmd
        self.step = None                        # the step build_game.py is in
        self.last_output = time.monotonic()     # when it last printed a line
        self._quiet_noted = False               # the quiet hint went to the log view in this quiet stretch
        self._log = None                        # build.log while the build runs
        self._log_lock = threading.Lock()

    def start(self):
        # PYTHONUTF8: the build's tools write their files in UTF-8 on any Windows code page (cp949 broke the lift)
        env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
        if sys.executable.lower().endswith("pythonw.exe"):     # tools must not run windowless-python
            exe = os.path.join(os.path.dirname(sys.executable), "python.exe")
            if os.path.exists(exe):
                self.cmd[0] = exe
        self.proc = subprocess.Popen(self.cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     stdin=subprocess.DEVNULL, env=env, cwd=self.out,
                                     creationflags=(CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP |
                                                    (BELOW_NORMAL_PRIORITY_CLASS if self.low_priority else 0))
                                     if IS_WIN else 0)
        self.last_output = time.monotonic()
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self):
        with open(self.log_path, "w", encoding="utf-8", errors="replace") as log:
            with self._log_lock:
                log.write(f"# T5DR Online build log, {datetime.datetime.now():%Y-%m-%d %H:%M:%S}, "
                          f"launcher {release_info().get('version')}\n# {' '.join(self.cmd)}\n")
                self._log = log
            for raw in iter(self.proc.stdout.readline, b""):
                line = raw.decode("utf-8", "replace").rstrip("\r\n")
                with self._log_lock:
                    log.write(line + "\n")
                    log.flush()
                    self.last_output = time.monotonic()
                    self._quiet_noted = False
                    self.step, events = build_line_events(self.step, line)
                for ev in events:
                    self.events.put(ev)
            code = self.proc.wait()
            with self._log_lock:
                log.write(f"# exit code {code}\n")
                self._log = None
        self.events.put(("end", -1 if self.cancelled else code))

    def quiet_hint(self, now=None):
        """lift_quiet_hint() for this build (the Build tab asks on every tick). The first time in a quiet stretch
        it also goes to the log view and build.log as a "[launcher] ..." line."""
        now = time.monotonic() if now is None else now
        with self._log_lock:
            hint = lift_quiet_hint(self.step, now - self.last_output)
            if hint and not self._quiet_noted:
                self._quiet_noted = True
                line = "[launcher] " + hint
                self.events.put(("line", line))
                if self._log is not None:
                    try:
                        self._log.write(line + "\n")
                        self._log.flush()
                    except (OSError, ValueError):
                        pass
        return hint

    def cancel(self):
        if self.proc and self.proc.poll() is None:
            self.cancelled = True
            kill_tree(self.proc.pid)


def kill_tree(pid):
    if IS_WIN:
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True,
                       creationflags=CREATE_NO_WINDOW)
    else:
        os.kill(pid, 9)


# --------------------------------------------------------------------------- game process

def explain_exit(code, lines):
    """One plain sentence for the Play tab when the game ended on its own; None when it closed normally."""
    text = "\n".join(lines[-80:])
    if code == 12 or "[gpu] device lost" in text:
        return t("The graphics card stopped working for the game (the driver crashed, was reset or updated). "
                 "Start the game again. If it happens again, update the graphics driver.")
    if code == 13 or "Direct3D 12 not available" in text or "needs a graphics card with Direct3D 12" in text:
        return t("This PC's graphics card or driver cannot run Direct3D 12. Install the newest graphics driver "
                 "from AMD, Intel or NVIDIA.")
    if "[cpu] FATAL" in text:
        return t("This processor is too old for the game: it lacks the SSE4.1 instructions (processors from "
                 "about 2008 on have them).")
    if code == 14 or "was built for -march=" in text:
        return t("The game was built on a PC with a newer processor (AVX2). Press BUILD GAME to build it again "
                 "for this PC; your saves are kept.")
    if "[game-dll] cannot load" in text:
        return t("t5dr_game.dll could not be loaded (missing or blocked). Press BUILD GAME again, and look in "
                 "the antivirus quarantine.")
    if code == 6 or "STUCK:" in text:
        # docs/DIRECTFIGHT.md "After a session ends": a persistent game that could not get back to
        # character select after a match ends itself; the next match starts a fresh one.
        return t("The game could not get back to character select after the last match and closed itself. "
                 "It starts again for your next match.")
    crashed = "[CRASH]" in text or "[STACKOVERFLOW]" in text
    if code == 0 and not crashed:
        return None
    if crashed:
        return t("The game stopped after a crash (exit code {code}). The game log has the details.", code=code)
    return t("The game stopped (exit code {code}). The game log has the details.", code=code)


UNLOCK_ENV = ("T5_UNLOCK_STAGES", "T5_UNLOCK_ITEMS")
ONLINE_ENV = ("T5_CTL_DIR", "T5_NET_MODE", "T5_FIGHT", "T5_FIGHT_FILE")


def is_online_env(env):
    """A game started for online play (the lobby's persistent game, netplay, direct fight)."""
    return any(env.get(k) for k in ONLINE_ENV)


def saves_dir(out_dir):
    """Where the game keeps its saves (the runtime's ./gamedata in the output folder)."""
    return os.path.join(out_dir, "gamedata", "dev_hdd0", "home", "00000001", "savedata")


def online_saves_dir(out_dir):
    """The save folder of games started for online play (PS3_SAVEDATA_DIR; docs/NETPLAY.md "One save for online")."""
    return os.path.join(out_dir, "gamedata-online", "dev_hdd0", "home", "00000001", "savedata")


def backup_saves_once(out_dir, tag):
    """Copy the save folder to <out>/save-backups/<tag>-<time>/ the first time a feature that changes what the
    save keeps is used (free items: what is taken stays in the save). Copying it back undoes it. Only once per
    tag (a marker file); -> the backup folder, or None (nothing to copy, already done, or it failed)."""
    src = saves_dir(out_dir)
    root = os.path.join(out_dir, "save-backups")
    marker = os.path.join(root, f"{tag}.done")
    if os.path.exists(marker) or not os.path.isdir(src) or not os.listdir(src):
        return None
    dst = os.path.join(root, f"{tag}-{datetime.datetime.now():%Y%m%d-%H%M%S}")
    try:
        shutil.copytree(src, dst)
        with open(marker, "w", encoding="utf-8") as f:
            f.write(dst + "\n")
        return dst
    except OSError:
        return None


COSTUME_ONLINE_ENV = ("T5_CTL_DIR", "T5_NET_MODE")


def costume_env(out_dir, env_over):
    """Custom costumes online (docs/DIRECTFIGHT.md "Custom costumes online"): a game started for netplay sends
    its player's customization to the opponent -- the blocks of the player's own save (the system save the
    game loads offline, <out>/gamedata/.../NPUB30009-SYSNET/SYS-DATA), read by the game itself. An online game
    plays on a save of its own, so it is named here. T5_COSTUME_SAVE=0 in the extra environment sends none
    (the opponent then sees the default costumes, as before 1.1.3)."""
    if not any(env_over.get(k) for k in COSTUME_ONLINE_ENV) or "T5_COSTUME_SAVE" in env_over:
        return
    env_over["T5_COSTUME_SAVE"] = os.path.join(saves_dir(out_dir), "NPUB30009-SYSNET", "SYS-DATA")


class GameRun:
    """The running game: its process, log file and the last fps line."""

    def __init__(self, out, settings):
        self.out = out
        self.settings = settings
        self.proc = None
        self.log_path = None
        self.fps = None
        self.last_lines = []
        self.started = None

    def start(self, extra_env=None, monitor_point=None):
        env_over = self.settings.env_overrides()
        if monitor_point and "PS3_WINDOW_MONITOR" not in env_over:
            env_over["PS3_WINDOW_MONITOR"] = "%d,%d" % monitor_point   # open on the launcher's monitor
        env_over.update(extra_env or {})
        if is_online_env(env_over):
            for k in UNLOCK_ENV:            # the game ignores them online anyway; keep its log and reports plain
                env_over.pop(k, None)
            # An online game keeps a save of its own (patches/ps3recomp/0044): both PCs start from the same
            # fresh save -- the game copies its own OPTIONS (round time, difficulty, ...) and unlocks into the
            # match state -- and the player's offline save is never read or written by it.
            env_over.setdefault("PS3_SAVEDATA_DIR", online_saves_dir(self.out))
        elif env_over.get("T5_UNLOCK_ITEMS"):
            backup_saves_once(self.out, "free-items")
        costume_env(self.out, env_over)
        cmd, env, cwd = run_game.game_command(self.out, env_over)
        if not os.path.exists(cmd[0]):
            raise FileNotFoundError(t("t5dr.exe is not built yet"))
        logs = os.path.join(self.out, "logs")
        os.makedirs(logs, exist_ok=True)
        for old in sorted(glob.glob(os.path.join(logs, "game-*.log")))[:-9]:
            try:
                os.remove(old)
            except OSError:
                pass
        self.log_path = os.path.join(logs, f"game-{datetime.datetime.now():%Y%m%d-%H%M%S}.log")
        logf = open(self.log_path, "w", encoding="utf-8", errors="replace")
        si = None
        if IS_WIN and env_over.get("PS3_WINDOW_BACKGROUND"):
            # Also ask for minimized through STARTUPINFO. On its own this does NOT keep the
            # live-draw window down (measured: it still took the foreground); the runtime
            # must honour PS3_WINDOW_BACKGROUND itself -- patches/ps3recomp/0021.
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 7   # SW_SHOWMINNOACTIVE
        self.proc = subprocess.Popen(cmd, env=env, cwd=cwd, stdout=logf, stderr=subprocess.STDOUT,
                                     stdin=subprocess.DEVNULL, startupinfo=si,
                                     creationflags=CREATE_NO_WINDOW if IS_WIN else 0)
        logf.close()
        self.started = time.time()
        threading.Thread(target=self._tail, daemon=True).start()
        if IS_WIN and not env_over.get("PS3_WINDOW_BACKGROUND") and \
                self.settings["display"] not in ("window", "borderless"):
            threading.Thread(target=self._place_window, daemon=True).start()
        return self.proc.pid

    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def stop(self):
        if self.running():
            kill_tree(self.proc.pid)

    def _tail(self):
        with open(self.log_path, encoding="utf-8", errors="replace") as f:
            while True:
                line = f.readline()
                if not line:
                    if not self.running():
                        break
                    time.sleep(0.25)
                    continue
                line = line.rstrip()
                if line.startswith("[fps]"):
                    try:
                        self.fps = float(line.split()[1])
                    except (IndexError, ValueError):
                        pass
                self.last_lines = (self.last_lines + [line])[-200:]

    def _place_window(self):
        hwnd = None
        for _ in range(120):                       # the window appears after the runtime boots
            if not self.running():
                return
            hwnd = find_game_window(self.proc.pid)
            if hwnd:
                break
            time.sleep(0.25)
        if hwnd:
            time.sleep(0.5)
            place_window(hwnd, self.settings["display"])


# --------------------------------------------------------------------------- windows (Win32)

# "Internal resolution", like an emulator's: the size the game draws at (PS3_INTERNAL_RES; the
# runtime's PS3_RES_SCALE and PS3_RENDER_SCALE are aliases). Native is the PS3's 1280 x 720; above
# it the whole picture is drawn larger (sharper on big screens, more work for the graphics card);
# below it only the 3D scene is smaller (the HUD stays sharp), for weak graphics cards. Only the
# picture changes, never the game, so the two players of an online match may choose differently.
# docs/RENDER_PERF.md "Internal resolution".
INTERNAL_RES = {          # key: (English label, t(label) where it is shown; factor)
    "lowest": (N_("Lowest (0.5x)"), 0.5),
    "lower": (N_("Lower (0.75x)"), 0.75),
    "native": (N_("Native (720p)"), 1.0),
    "1080p": (N_("1080p (1.5x)"), 1.5),
    "1440p": (N_("1440p (2x)"), 2.0),
    "4k": (N_("4K (3x)"), 3.0),
}
INTERNAL_RES_LABELS = {k: v[0] for k, v in INTERNAL_RES.items()}
OLD_RENDER_SCALES = {"1": "native", "0.75": "lower", "0.5": "lowest"}

# Short hint per step: what it costs, in pixels the graphics card draws relative to Native (what
# decides on a weak card; a fast card also has a fixed cost per frame, so an RTX 3090 needs only
# ~1.3x / 1.7x / 3x Native's GPU time for 1080p / 1440p / 4K: docs/RENDER_PERF.md "Internal resolution").
INTERNAL_RES_HINTS = {   # English; t(hint) where it is shown
    "lowest": N_("The 3D scene at half size (a quarter of its pixels); HUD and text stay sharp. "
                 "For integrated graphics and old laptops."),
    "lower": N_("The 3D scene at 3/4 size (about half of its pixels); HUD and text stay sharp. "
                "For weak graphics cards."),
    "native": N_("The PS3's 1280 x 720. Light on any graphics card; the picture is scaled to your window."),
    "1080p": N_("1920 x 1080: 2.25x the pixels of Native. Sharp on Full HD screens. "
                "If fights drop below 60 fps, go one step down."),
    "1440p": N_("2560 x 1440: 4x the pixels of Native. For strong graphics cards. "
                "If fights drop below 60 fps, go one step down."),
    "4k": N_("3840 x 2160: 9x the pixels of Native. For very strong graphics cards "
             "(an RTX 3090 needs 1-2 ms of a 16.7 ms frame). If fights drop below 60 fps, go one step down."),
}


# VSync: how a finished picture reaches the screen. On (default): at the monitor's next refresh,
# no tearing (on a 59/60 Hz monitor the game follows the monitor's refresh: the display lock).
# Off: PS3_VSYNC=0, shown at once (tearing allowed): the lowest latency. The game's speed never
# changes: its frames are started by the runtime's own 59.94 Hz vblank clock (QPC), never by the
# present, so Off cannot make it run faster than 60. There is no frame rate choice: the game's
# simulation is tied to 60 frames per second, like on the PS3. Only the picture changes, so the
# two players of an online match may choose differently. The game's clock: docs/TROUBLESHOOTING.md
# "High refresh rate"; the runtime's switch: rsx_live_draw.c "PC display" (PS3_VSYNC=0).
VSYNC_MODES = {          # English; t(label) where it is shown
    "on": N_("On (smooth, default)"),
    "off": N_("Off (lowest latency, may tear)"),
}

# Power saving (PS3_LAPTOP, ps3recomp patch 0047, docs/RENDER_PERF.md "Laptops, handhelds and 8-core APUs"): the
# same game at the same 60 fps with less CPU around it -- no spinning waits, fewer worker threads --
# so a laptop's or handheld's processor stays under its heat and power limit and keeps its clock
# (on an APU the CPU and the graphics share one power budget). Auto: the game turns it on when the
# PC has a battery, battery saver or the "Power saver" plan is on, the processor is a mobile one,
# or it renders on integrated graphics. Only timing around the game changes, never the game, so
# the two players of an online match may choose differently.
POWER_SAVING = {         # English; t(label) where it is shown
    "auto": N_("Auto (laptops, handhelds, integrated graphics)"),
    "on": N_("On"),
    "off": N_("Off"),
}
# The same rule as the runtime's hs_mobile_cpu_name (host_sched.c): a model number with a mobile
# suffix (7840U, 6800H, 8845HS, 7945HX, 7700HQ, 1165G7, 1260P, 8100Y, Core Ultra 155H / 258V),
# Ryzen Z1/Z2 (handhelds) and Ryzen AI, N100-style parts.
MOBILE_CPU = re.compile(r"\b\d{3,5}(?:U|H|HS|HX|HQ|HK|HL|Y|P|V|G1|G4|G7)\b|Ryzen (?:Z\d|AI)\b|\bN\d{3,4}\b")
POWER_SAVER_PLAN = "a1841308-3541-4fab-bc81-f71556f20b4a"


def system_power_status():
    """(ac: True/False/None, battery_percent or None, has_battery, battery_saver) from Windows."""
    if not IS_WIN:
        return None, None, False, False

    class SPS(ctypes.Structure):
        _fields_ = [("ACLineStatus", ctypes.c_ubyte), ("BatteryFlag", ctypes.c_ubyte),
                    ("BatteryLifePercent", ctypes.c_ubyte), ("SystemStatusFlag", ctypes.c_ubyte),
                    ("BatteryLifeTime", ctypes.c_ulong), ("BatteryFullLifeTime", ctypes.c_ulong)]
    s = SPS()
    try:
        if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(s)):
            return None, None, False, False
    except (OSError, AttributeError):
        return None, None, False, False
    has = s.BatteryFlag not in (128, 255)
    ac = {0: False, 1: True}.get(s.ACLineStatus)
    return ac, (s.BatteryLifePercent if has and s.BatteryLifePercent <= 100 else None), has, bool(s.SystemStatusFlag & 1)


def active_power_plan():
    """The active power plan's GUID (lower case) from the registry, or ''."""
    if not IS_WIN:
        return ""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SYSTEM\CurrentControlSet\Control\Power\User\PowerSchemes") as k:
            return str(winreg.QueryValueEx(k, "ActivePowerScheme")[0]).lower()
    except OSError:
        return ""


def cpu_name():
    if not IS_WIN:
        return ""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as k:
            return " ".join(str(winreg.QueryValueEx(k, "ProcessorNameString")[0]).split())
    except OSError:
        return ""


def power_saving_auto(status=None, plan=None, cpu=None):
    """(on, reason) for 'Auto' on this PC, as far as the launcher can tell before the game runs (the
    game decides the same way and also turns it on when it finds integrated graphics). reason is an
    English text for t()."""
    ac, _pct, has_battery, saver = status if status is not None else system_power_status()
    if has_battery:
        return True, N_("this PC has a battery (laptop or handheld)")
    if saver:
        return True, N_("battery saver is on")
    if (plan if plan is not None else active_power_plan()) == POWER_SAVER_PLAN:
        return True, N_("the Power saver power plan is on")
    if MOBILE_CPU.search(cpu if cpu is not None else cpu_name()):
        return True, N_("a mobile processor")
    return False, None


# Stage blur / glow: some stages filter the whole picture -- a soft focus on the misty swamp (stage
# 34) and stages 24, 26 and 28, a glow around the sun on stage 20. On (default): as the game draws
# it, at every internal resolution like at Native. Off: PS3_STAGE_BLUR=0, those stages sharp and
# without the glow; the HUD and every other stage stay as they are. Only the picture changes, so the
# two players of an online match may choose differently. docs/RENDER_PERF.md "Stage blur and glow".
STAGE_BLUR_MODES = {     # English; t(label) where it is shown
    "on": N_("On (default)"),
    "off": N_("Off"),
}


# Training overlay (docs/TRAINING.md): the game draws, over its picture, the last inputs of each
# player with how many frames each was held, and after each exchange the startup of the move and
# the frame advantage (+3, -12). In Practice; the two options widen it to the other offline modes
# and to online matches (there only this PC's own inputs, no frame data). It only reads the game's
# memory, so it never changes a match. F2 in the game switches it for the session.
TRAINING_MODES = {       # English; t(label) where it is shown
    "off": N_("Off"),
    "inputs": N_("Inputs"),
    "frames": N_("Inputs + frame data"),
}


def internal_res_for_screen(width, height):
    """The highest step whose picture fits a screen or window of width x height pixels
    (a suggestion for the player; the game never picks it by itself)."""
    best = "native"
    for key, (_label, f) in INTERNAL_RES.items():
        if f > 1.0 and 1280 * f <= width + 8 and 720 * f <= height + 8:
            best = key
    return best


def screen_size(point=None):
    """(width, height) in physical pixels of the monitor at point (x, y) -- the game opens on the
    launcher's monitor -- or of the primary monitor; None when unknown."""
    if not IS_WIN:
        return None

    class RECT(ctypes.Structure):
        _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long), ("r", ctypes.c_long), ("b", ctypes.c_long)]

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("mon", RECT), ("work", RECT), ("flags", ctypes.c_ulong)]

    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
    try:
        with _PerMonitorDpi():
            u = ctypes.windll.user32
            u.MonitorFromPoint.restype = ctypes.c_void_p
            u.MonitorFromPoint.argtypes = [POINT, ctypes.c_ulong]
            mon = u.MonitorFromPoint(POINT(*(point or (0, 0))), 1)       # MONITOR_DEFAULTTOPRIMARY
            mi = MONITORINFO()
            mi.cb = ctypes.sizeof(mi)
            if not mon or not u.GetMonitorInfoW(ctypes.c_void_p(mon), ctypes.byref(mi)):
                return None
            return mi.mon.r - mi.mon.l, mi.mon.b - mi.mon.t
    except (AttributeError, OSError):
        return None

# Online input delay (like Tekken 6 Native Online's): frames between a press and the frame it
# takes effect in, on both PCs. Auto follows the ping the game measures (1 frame up to ~60 ms,
# 2 above). A fixed value counts only when both players chose the same; ranked matches use the
# server's value. docs/NETPLAY.md "Input delay".
INPUT_DELAYS = {         # English; t(label) where it is shown
    "auto": N_("Auto (by ping)"),
    "0": "0",
    "1": "1",
    "2": "2",
}

DISPLAY_MODES = [        # English; t(label) where it is shown
    ("window", N_("Window, 1280 x 720 (native; larger with Windows display scaling)")),
    ("window1080", N_("Window, 1920 x 1080")),
    ("window1440", N_("Window, 2560 x 1440")),
    ("maximized", N_("Maximized window")),
    ("borderless", N_("Borderless fullscreen (Alt+Enter or F11 switches in the game)")),
]


def find_game_window(pid):
    if not IS_WIN:
        return None
    user32 = ctypes.windll.user32
    found = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def cb(hwnd, _):
        p = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(ctypes.c_void_p(hwnd), ctypes.byref(p))
        if p.value == pid:
            cls = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(ctypes.c_void_p(hwnd), cls, 64)
            if cls.value.startswith("ps3recomp"):
                found.append(hwnd)
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return found[0] if found else None


class _PerMonitorDpi:
    """Physical pixels on every monitor while placing windows: t5dr.exe is per-monitor DPI aware,
    the launcher only system aware (a monitor with another scale would get scaled coordinates)."""

    def __enter__(self):
        self.old = None
        try:
            f = ctypes.windll.user32.SetThreadDpiAwarenessContext     # Windows 10 1607+
            f.restype = ctypes.c_void_p
            f.argtypes = [ctypes.c_void_p]
            self.old = f(ctypes.c_void_p(-4))                          # PER_MONITOR_AWARE_V2
        except (AttributeError, OSError):
            pass
        return self

    def __exit__(self, *exc):
        if self.old:
            ctypes.windll.user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(self.old))


def window_center(hwnd):
    """(x, y) in physical pixels of a window's centre (the game opens on that monitor), or None."""
    if not IS_WIN or not hwnd:
        return None

    class RECT(ctypes.Structure):
        _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long), ("r", ctypes.c_long), ("b", ctypes.c_long)]
    r = RECT()
    with _PerMonitorDpi():
        if not ctypes.windll.user32.GetWindowRect(ctypes.c_void_p(hwnd), ctypes.byref(r)):
            return None
    return (r.l + r.r) // 2, (r.t + r.b) // 2


def place_window(hwnd, mode):
    """Size the game window (in physical pixels: "1920 x 1080" is 1920 x 1080 pixels at any
    display scaling). The swap chain follows the client size and the present scales, so any
    size works."""
    with _PerMonitorDpi():
        _place_window(hwnd, mode)


def _place_window(hwnd, mode):
    user32 = ctypes.windll.user32
    h = ctypes.c_void_p(hwnd)

    class RECT(ctypes.Structure):
        _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long), ("r", ctypes.c_long), ("b", ctypes.c_long)]

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong), ("mon", RECT), ("work", RECT), ("flags", ctypes.c_ulong)]

    mi = MONITORINFO()
    mi.cb = ctypes.sizeof(mi)
    user32.GetMonitorInfoW(ctypes.c_void_p(user32.MonitorFromWindow(h, 2)), ctypes.byref(mi))
    GWL_STYLE, WS_OVERLAPPEDWINDOW, WS_POPUP, WS_VISIBLE = -16, 0x00CF0000, 0x80000000, 0x10000000
    SWP_NOZORDER, SWP_FRAMECHANGED = 0x0004, 0x0020
    user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    user32.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
    if mode == "maximized":
        user32.ShowWindow(h, 3)                 # SW_MAXIMIZE
        return
    if mode == "borderless":
        m = mi.mon
        user32.SetWindowLongPtrW(h, GWL_STYLE, WS_POPUP | WS_VISIBLE)
        user32.SetWindowPos(h, None, m.l, m.t, m.r - m.l, m.b - m.t, SWP_NOZORDER | SWP_FRAMECHANGED)
        return
    cw, ch = {"window1080": (1920, 1080), "window1440": (2560, 1440)}.get(mode, (1280, 720))
    w = mi.work
    # never bigger than the screen's work area, keep 16:9
    scale = min(1.0, (w.r - w.l - 16) / cw, (w.b - w.t - 40) / ch)
    cw, ch = int(cw * scale), int(ch * scale)
    rc = RECT(0, 0, cw, ch)
    user32.AdjustWindowRect(ctypes.byref(rc), WS_OVERLAPPEDWINDOW, False)
    ww, wh = rc.r - rc.l, rc.b - rc.t
    x = w.l + max(0, (w.r - w.l - ww) // 2)
    y = w.t + max(0, (w.b - w.t - wh) // 2)
    user32.SetWindowPos(h, None, x, y, ww, wh, SWP_NOZORDER)


def open_path(path):
    if IS_WIN and os.path.exists(path):
        os.startfile(path)  # noqa: S606 -- the player's own file/folder


def reveal_file(path):
    """Open the file's folder in Explorer with the file selected (the finished report)."""
    if IS_WIN and os.path.exists(path):
        subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
    elif os.path.isdir(os.path.dirname(path)):
        open_path(os.path.dirname(path))


def desktop_dir():
    """The Desktop folder (also when OneDrive or the player moved it), else the home folder."""
    d = known_folder(KNOWN_FOLDERS["Desktop"])
    if d and os.path.isdir(d):
        return d
    d = os.path.join(os.path.expanduser("~"), "Desktop")
    return d if os.path.isdir(d) else os.path.expanduser("~")


def file_sha1(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()
