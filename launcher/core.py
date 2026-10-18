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
    "render_scale": "1",       # 3D resolution: 1 (original) | 0.75 (lower) | 0.5 (lowest), PS3_RENDER_SCALE
    "input_delay": "auto",     # online input delay: auto (by ping) | 0 | 1 | 2 frames, T5_RB_NET_DELAY
    "mute": False,
    "background": False,       # start minimized without focus (testing)
    "extra_env": "",           # NAME=VALUE lines
    "low_priority": False,     # build at below-normal priority: the PC stays responsive, the build is slower
}


class Settings(dict):
    def __init__(self, path=SETTINGS_FILE):
        super().__init__(DEFAULTS)
        self.path = path
        try:
            with open(path, encoding="utf-8") as f:
                self.update({k: v for k, v in json.load(f).items() if k in DEFAULTS})
        except (OSError, ValueError):
            pass

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
        if self["render_scale"] in RENDER_SCALES and self["render_scale"] != "1":
            env["PS3_RENDER_SCALE"] = self["render_scale"]
        if self["input_delay"] in INPUT_DELAYS:
            env["T5_RB_NET_DELAY"] = self["input_delay"]
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
        return False, "error", "No package chosen."
    if not os.path.exists(path):
        return False, "error", "File not found."
    try:
        cid = build_game.pkg_content_id(path)
    except OSError as e:
        return False, "error", f"Cannot read the file: {e}"
    size = os.path.getsize(path)
    if cid is None:
        return False, "error", "This is not a PS3 package (.pkg)."
    if cid == build_game.CONTENT_ID:
        return True, "ok", f"{cid}  ({size:,} bytes) -- the supported version"
    if build_game.TITLE_ID in cid:
        return True, "warn", (f"{cid}  ({size:,} bytes) -- Tekken 5 DR, but not the supported package "
                              f"({build_game.CONTENT_ID}). The build will most likely refuse it.")
    return True, "warn", f"{cid}  ({size:,} bytes) -- not Tekken 5 DR Online ({build_game.TITLE_ID})."


def describe_rap(path, pkg=None):
    if not path:
        return False, "error", "No license chosen."
    if not os.path.exists(path):
        return False, "error", "File not found."
    if os.path.getsize(path) != 16:
        return False, "error", "Not a PS3 license: a .rap file is exactly 16 bytes."
    name = os.path.basename(path)
    if build_game.CONTENT_ID in name:
        return True, "ok", f"{name} -- matches the supported package"
    if pkg:
        try:
            cid = build_game.pkg_content_id(pkg)
        except OSError:
            cid = None
        if cid and cid in name:
            return True, "ok", f"{name} -- matches the package"
    return True, "warn", f"{name} -- the name does not match the package's content ID; it may be the wrong license."


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


def install_warnings(root=ROOT, out=None):
    """Plain sentences about folder choices that break or slow the build/game (Build tab)."""
    warn = []
    out = out or os.path.join(root, "native")
    for label, path in (("This folder", root), ("The output folder", out)):
        n = len(os.path.abspath(path).encode("utf-8"))
        if n + PATH_ROOM > MAX_PATH:
            warn.append(f"{label} has a long path ({n} bytes). Windows allows only {MAX_PATH} characters for "
                        f"a file path, and the build writes files about {PATH_ROOM} characters deeper. Move the "
                        r"folder to a short path, for example C:\Games\T5DR.")
            break
    norm = os.path.normcase(os.path.abspath(root))
    for var in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        od = os.environ.get(var)
        if od and (norm + os.sep).startswith(os.path.normcase(os.path.abspath(od)) + os.sep):
            warn.append("This folder is inside OneDrive. OneDrive would upload about 1 GB of game data and can "
                        "lock files while the game is built. Move the folder out of OneDrive, for example to "
                        r"C:\Games\T5DR.")
            break
    pf = [os.environ.get(v) for v in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432")]
    if any(p and (norm + os.sep).startswith(os.path.normcase(p) + os.sep) for p in pf):
        warn.append("This folder is in Program Files, where Windows does not let programs write. "
                    r"Move it to a folder of your own, for example C:\Games\T5DR.")
    elif os.path.isdir(root) and not _writable(root):
        warn.append("Windows does not let the launcher write into this folder. Move it to a folder of your "
                    r"own, for example C:\Games\T5DR.")
    if norm.startswith("\\"):
        warn.append("This folder is on a network share. Building and playing from there is slow and was "
                    "not tested; copy it to a local drive.")
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
        st["text"] = "The game is not built yet. Open the Build tab, choose your .pkg and .rap, press BUILD GAME."
        return st
    st["built"] = True
    if not os.path.exists(elf):
        st["text"] = "t5dr.exe is there but the game data is missing. Build again."
        return st
    h = build_game.sha1(elf)
    st["elf_sha1"] = h
    if h != build_game.ELF_SHA1:
        st["text"] = (f"The decrypted program has SHA-1 {h[:12]}..., not the supported version. "
                      "Build again from the supported package.")
        return st
    info = {}
    try:
        with open(stamp) as f:
            info = json.load(f)
    except (OSError, ValueError):
        pass
    if info.get("code_id") != build_game.code_id():
        st["needs_rebuild"] = True
        st["text"] = ("Build the game once (about 2 minutes): this version of the launcher changes the game code. "
                      "Click BUILD GAME. Your unpacked game and saves are kept; only the code is translated and "
                      "compiled again.")
        return st
    st["ok"] = True
    when = info.get("built", "?").replace("T", " ")
    st["text"] = (f"Ready: {build_game.TITLE_ID} v{build_game.TITLE_VERSION}, program SHA-1 {h[:12]}... "
                  f"verified, built {when}.")
    return st


# --------------------------------------------------------------------------- build process

STEP_TITLES = {
    "deps": "Recompiler", "keys": "Key data", "decrypt": "Check & decrypt", "unpack": "Unpack",
    "vfs": "Game files", "lift": "Translate code", "spu": "Sound core", "compile": "Compile",
}
# Rough share of the total time per step (measured on a 16-core PC; see docs/RELEASE.md).
STEP_WEIGHT = {"deps": 1, "keys": 1, "decrypt": 2, "unpack": 12, "vfs": 1, "lift": 40, "spu": 8, "compile": 35}
RE_STEP = re.compile(r"^\[(\w+)\]\s*$")
RE_NINJA = re.compile(r"^\[(\d+)/(\d+)\]")
RE_FUNCS = re.compile(r"(\d+)/(\d+) functions")


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

    def start(self):
        env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
        if sys.executable.lower().endswith("pythonw.exe"):     # tools must not run windowless-python
            exe = os.path.join(os.path.dirname(sys.executable), "python.exe")
            if os.path.exists(exe):
                self.cmd[0] = exe
        self.proc = subprocess.Popen(self.cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     stdin=subprocess.DEVNULL, env=env, cwd=self.out,
                                     creationflags=(CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP |
                                                    (BELOW_NORMAL_PRIORITY_CLASS if self.low_priority else 0))
                                     if IS_WIN else 0)
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self):
        step = None
        with open(self.log_path, "w", encoding="utf-8", errors="replace") as log:
            log.write(f"# T5DR Online build log, {datetime.datetime.now():%Y-%m-%d %H:%M:%S}, "
                      f"launcher {release_info().get('version')}\n# {' '.join(self.cmd)}\n")
            for raw in iter(self.proc.stdout.readline, b""):
                line = raw.decode("utf-8", "replace").rstrip("\r\n")
                log.write(line + "\n")
                log.flush()
                self.events.put(("line", line))
                m = RE_STEP.match(line)
                if m and m.group(1) in STEP_TITLES:
                    step = m.group(1)
                    self.events.put(("step", step))
                elif line.strip().startswith("already done") or "nothing to fetch" in line:
                    self.events.put(("skip", step))
                elif line.startswith("ERROR:"):
                    self.events.put(("error", line[6:].strip()))
                elif step == "compile" and RE_NINJA.match(line):
                    n, d = map(int, RE_NINJA.match(line).groups())
                    self.events.put(("sub", n / max(d, 1)))
                elif step == "lift" and RE_FUNCS.search(line):
                    n, d = map(int, RE_FUNCS.search(line).groups())
                    # the lifter reports twice (translate, then write): weight 70/30
                    frac = n / max(d, 1)
                    self.events.put(("sub", 0.7 * frac if "lifted" in line else 0.7 + 0.3 * frac))
            code = self.proc.wait()
            log.write(f"# exit code {code}\n")
        self.events.put(("end", -1 if self.cancelled else code))

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
        return ("The graphics card stopped working for the game (the driver crashed, was reset or updated). "
                "Start the game again. If it happens again, update the graphics driver.")
    if code == 13 or "Direct3D 12 not available" in text or "needs a graphics card with Direct3D 12" in text:
        return ("This PC's graphics card or driver cannot run Direct3D 12. Install the newest graphics driver "
                "from AMD, Intel or NVIDIA.")
    if "[cpu] FATAL" in text:
        return ("This processor is too old for the game: it lacks the SSE4.1 instructions (processors from "
                "about 2008 on have them).")
    if code == 14 or "was built for -march=" in text:
        return ("The game was built on a PC with a newer processor (AVX2). Press BUILD GAME to build it again "
                "for this PC; your saves are kept.")
    if "[game-dll] cannot load" in text:
        return ("t5dr_game.dll could not be loaded (missing or blocked). Press BUILD GAME again, and look in "
                "the antivirus quarantine.")
    if code == 6 or "STUCK:" in text:
        # docs/DIRECTFIGHT.md "After a session ends": a persistent game that could not get back to
        # character select after a match ends itself; the next match starts a fresh one.
        return ("The game could not get back to character select after the last match and closed itself. "
                "It starts again for your next match.")
    crashed = "[CRASH]" in text or "[STACKOVERFLOW]" in text
    if code == 0 and not crashed:
        return None
    return (f"The game stopped (exit code {code}){' after a crash' if crashed else ''}. "
            "The game log has the details.")


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
        cmd, env, cwd = run_game.game_command(self.out, env_over)
        if not os.path.exists(cmd[0]):
            raise FileNotFoundError("t5dr.exe is not built yet")
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
        if IS_WIN and not env_over.get("PS3_WINDOW_BACKGROUND") and self.settings["display"] != "window":
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

# "3D resolution" (like Tekken 6 Native Online's option): the game draws below 1280 x 720 and the
# picture is scaled up to the window. Only the picture changes, never the game, so the two
# players of an online match may choose differently. docs/RENDER_PERF.md "Weaker PCs".
RENDER_SCALES = {
    "1": "Original",
    "0.75": "Lower",
    "0.5": "Lowest",
}

# Online input delay (like Tekken 6 Native Online's): frames between a press and the frame it
# takes effect in, on both PCs. Auto follows the ping the game measures (1 frame up to ~60 ms,
# 2 above). A fixed value counts only when both players chose the same; ranked matches use the
# server's value. docs/NETPLAY.md "Input delay".
INPUT_DELAYS = {
    "auto": "Auto (by ping)",
    "0": "0",
    "1": "1",
    "2": "2",
}

DISPLAY_MODES = [
    ("window", "Window, 1280 x 720 (native; larger with Windows display scaling)"),
    ("window1080", "Window, 1920 x 1080"),
    ("window1440", "Window, 2560 x 1440"),
    ("maximized", "Maximized window"),
    ("borderless", "Borderless fullscreen (experimental)"),
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
