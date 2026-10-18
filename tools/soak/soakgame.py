"""One polite game for the offline soak (docs/SOAK.md): the smoke suite's Game
(tools/smoke/game.py: scripted pads, log tail, frame read-back, phases) started
the way every test game on the owner's PC must run --

  * muted: PS3_AUDIO_MUTE=1 (AUDIO_RATE and AUDIO_WAV still see the real mix),
  * minimized, never focused: PS3_WINDOW_BACKGROUND=1, PAD_NO_KEYBOARD=1,
  * below-normal priority (the process and everything it starts),
  * optionally limited to the first N logical processors (affinity + PS3_CPUS=N),

plus a resource sampler: every `sample_s` seconds the process's handle count,
thread count, private bytes, working set, GDI/USER objects and CPU seconds go
to resources.tsv (with the last [fps] value and the scenario phase).
"""
import ctypes
import ctypes.wintypes as wt
import os
import re
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(TOOLS, "smoke"))
sys.path.insert(1, TOOLS)

import frames as framelib  # noqa: E402
import procs  # noqa: E402
from game import Abort, Game, find_game_root  # noqa: E402,F401


def title_menu_check(im):
    """The title's main menu vs its PRESS START BUTTON line, by the red menu text in four
    rows below the logo (x 470-810; rows at y 512, 544, 576, 608 in a 1280x720 frame).
    The main menu shows four items (the highlighted one bright, the others dim red);
    PRESS START shows only the second row. Lightning flashes wash both out for a frame."""
    if im.size != (1280, 720):
        im = im.resize((1280, 720))
    px = im.load()
    bands = []
    for y0 in (512, 544, 576, 608):
        c = t = 0
        for y in range(y0, y0 + 20, 2):
            for x in range(470, 810, 2):
                r, g, b = px[x, y][:3]
                t += 1
                if r > 60 and r > 1.6 * g and r > 1.6 * b:
                    c += 1
        bands.append(round(c / t, 3))
    menu = sum(1 for v in bands if v > 0.02) >= 3
    hi = max(range(4), key=lambda i: bands[i]) if menu and max(bands) > 0.2 else None
    return {"bands": bands, "menu": menu, "hi": hi,
            "press_start": (not menu) and bands[1] > 0.3 and bands[0] < 0.02 and bands[3] < 0.02}


_fight_check = framelib.fight_check


def _fight_and_menu(im):
    d = _fight_check(im)
    try:
        d["title"] = title_menu_check(im)
    except Exception as e:          # analysis must never stop a run
        d["title"] = {"error": str(e)}
    return d


framelib.fight_check = _fight_and_menu

BELOW_NORMAL = 0x00004000
RE_MODE = re.compile(r"^\[df\] frame (\d+): mode cur=(\d+) next=(\d+) .*?\((\w+)\)")
RE_GTYPE = re.compile(r"^\[df\] frame (\d+): \[0x1008EBAC\] 0x[0-9A-F]+ -> 0x([0-9A-F]+)")

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_u32 = ctypes.WinDLL("user32", use_last_error=True)
_k32.OpenProcess.restype = wt.HANDLE
_k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
_k32.CloseHandle.argtypes = [wt.HANDLE]
_k32.GetProcessHandleCount.argtypes = [wt.HANDLE, ctypes.POINTER(wt.DWORD)]
_k32.SetProcessAffinityMask.argtypes = [wt.HANDLE, ctypes.c_size_t]
_k32.GetProcessTimes.argtypes = [wt.HANDLE] + [ctypes.POINTER(wt.FILETIME)] * 4
_u32.GetGuiResources.argtypes = [wt.HANDLE, wt.DWORD]


class _PE32(ctypes.Structure):
    _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ProcessID", wt.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wt.DWORD),
                ("cntThreads", wt.DWORD), ("th32ParentProcessID", wt.DWORD),
                ("pcPriClassBase", ctypes.c_long), ("dwFlags", wt.DWORD),
                ("szExeFile", ctypes.c_wchar * 260)]


_k32.CreateToolhelp32Snapshot.restype = wt.HANDLE
_k32.Process32FirstW.argtypes = [wt.HANDLE, ctypes.POINTER(_PE32)]
_k32.Process32NextW.argtypes = [wt.HANDLE, ctypes.POINTER(_PE32)]


def thread_count(pid):
    snap = _k32.CreateToolhelp32Snapshot(0x2, 0)
    if not snap or snap == wt.HANDLE(-1).value:
        return None
    try:
        e = _PE32()
        e.dwSize = ctypes.sizeof(_PE32)
        ok = _k32.Process32FirstW(snap, ctypes.byref(e))
        while ok:
            if e.th32ProcessID == pid:
                return e.cntThreads
            ok = _k32.Process32NextW(snap, ctypes.byref(e))
    finally:
        _k32.CloseHandle(snap)
    return None


class _FT(ctypes.Structure):
    _fields_ = [("lo", wt.DWORD), ("hi", wt.DWORD)]


_k32.GetSystemTimes.argtypes = [ctypes.POINTER(_FT)] * 3


def system_times():
    """(idle, kernel+user) in 100-ns units, summed over all processors."""
    i, k, u = _FT(), _FT(), _FT()
    if not _k32.GetSystemTimes(ctypes.byref(i), ctypes.byref(k), ctypes.byref(u)):
        return None
    f = lambda t: (t.hi << 32) | t.lo  # noqa: E731
    return f(i), f(k) + f(u)            # kernel time includes idle


def resources(pid):
    """{'handles', 'threads', 'gdi', 'user', 'cpu_s', 'private_mb', 'ws_mb'} or None."""
    h = _k32.OpenProcess(0x1000 | 0x0400 | 0x0010, False, pid)   # QUERY_LIMITED | QUERY | VM_READ
    if not h:
        return None
    try:
        n = wt.DWORD()
        handles = n.value if _k32.GetProcessHandleCount(h, ctypes.byref(n)) else None
        gdi = _u32.GetGuiResources(h, 0)
        user = _u32.GetGuiResources(h, 1)
        c, e, k, u = wt.FILETIME(), wt.FILETIME(), wt.FILETIME(), wt.FILETIME()
        cpu = None
        if _k32.GetProcessTimes(h, ctypes.byref(c), ctypes.byref(e), ctypes.byref(k), ctypes.byref(u)):
            cpu = (((k.dwHighDateTime << 32) | k.dwLowDateTime) + ((u.dwHighDateTime << 32) | u.dwLowDateTime)) / 1e7
    finally:
        _k32.CloseHandle(h)
    m = procs.memory(pid)
    return {"handles": handles, "threads": thread_count(pid), "gdi": gdi, "user": user,
            "cpu_s": None if cpu is None else round(cpu, 1),
            "private_mb": None if not m else round(m[1], 1), "ws_mb": None if not m else round(m[0], 1)}


class SoakGame(Game):
    """Game with the polite start and the resource sampler. Extra args:
    cpus (None = all), sample_s (resource sample interval)."""

    def __init__(self, test_dir, cpus=None, sample_s=10.0, env=None, mute=True, console=False, cpu_offset=0, **kw):
        e = {"PS3_WINDOW_BACKGROUND": "1", "PAD_NO_KEYBOARD": "1", "AUDIO_RATE": "1"}
        if mute:
            e["PS3_AUDIO_MUTE"] = "1"
        if console:
            e["PS3_DEBUG"] = os.path.join(os.path.abspath(test_dir), "dbg.txt").replace("\\", "/")
        if cpus:
            e["PS3_CPUS"] = str(cpus)
        e.update(env or {})
        super().__init__(test_dir, env=e, **kw)
        self.cpus = cpus
        self.cpu_offset = cpu_offset
        self.sample_s = sample_s
        self.res = []                  # (t, phase, dict)
        self.last_fps = None
        # The direct-fight probe's notes (T5_DF_PROBE=1, T5_DF_WATCH=1008EBAC): the game's mode
        # manager (cur mode + class) and the game-type word, for navigation (docs/SOAK.md).
        self.mode, self.mode_name, self.game_type = None, None, None
        self.mode_log = []             # (t, frame, cur, next, name)
        feed = self.scan.feed

        def feed_hook(line, t=None, phase=None):
            if line.startswith("[df] frame "):
                m = RE_MODE.match(line)
                if m:
                    cur = int(m.group(2))
                    if cur != self.mode:
                        self.mode, self.mode_name = cur, m.group(4)
                        self.mode_log.append((t, int(m.group(1)), cur, int(m.group(3)), m.group(4)))
                        self.event("mode", f"{cur} {m.group(4)} (frame {m.group(1)})")
                else:
                    m = RE_GTYPE.match(line)
                    if m:
                        self.game_type = int(m.group(2), 16)
                        self.event("game-type", f"{self.game_type} (frame {m.group(1)})")
            return feed(line, t, phase)
        self.scan.feed = feed_hook

    def start(self):
        self.prepare_dirs()
        argv, env, cwd = self.command()
        self.argv = argv
        self.logf = open(self.log_path, "wb")
        self.t0 = time.perf_counter()
        self._log_pos = 0
        self._ev = open(os.path.join(self.dir, "events.tsv"), "w", buffering=1, encoding="utf-8")
        self.phases.append([self.phase_name, "boot", 0.0, None])
        try:
            if not os.path.isfile(argv[0]):
                raise OSError(f"no such file: {argv[0]}")
            self.proc = subprocess.Popen(argv, env=env, cwd=cwd, stdout=self.logf, stderr=subprocess.STDOUT,
                                         creationflags=BELOW_NORMAL)
            self._job = procs.kill_on_close_job(self.proc.pid)
        except OSError as e:
            self.start_error = f"could not start {argv[0]}: {e}"
            self.event("start-error", str(e))
            self.logf.close()
            self._ev.close()
            raise Abort(self.start_error)
        if self.cpus:
            h = _k32.OpenProcess(0x0200 | 0x0400, False, self.proc.pid)   # SET_INFORMATION | QUERY
            ok = bool(h) and bool(_k32.SetProcessAffinityMask(h, ctypes.c_size_t(((1 << self.cpus) - 1) << self.cpu_offset)))
            if h:
                _k32.CloseHandle(h)
            self.event("affinity", f"{self.cpus} logical processors from {self.cpu_offset}: {'ok' if ok else 'FAILED'}")
        self.event("start", f"pid={self.proc.pid} exe={argv[0]} below-normal")
        self._resf = open(os.path.join(self.dir, "resources.tsv"), "w", buffering=1, encoding="utf-8")
        self._resf.write("t\tphase\thandles\tthreads\tprivate_mb\tws_mb\tgdi\tuser\tcpu_s\tfps\tsys_busy_pct\t"
                         "other_games\tbuilds\n")
        for fn in (self._tail, self._sampler, self._framer, self._res_sampler):
            th = threading.Thread(target=fn, daemon=True)
            th.start()
            self._threads.append(th)
        return self

    def _res_sampler(self):
        last = system_times()
        while not self._stop.is_set() and self.alive():
            r = resources(self.proc.pid)
            now = system_times()
            busy = None
            if last and now and now[1] > last[1]:
                busy = round(100.0 * (1.0 - (now[0] - last[0]) / (now[1] - last[1])), 1)
            last = now
            if r:
                t = round(self.now(), 1)
                fps = self.scan.fps[-1].value if self.scan.fps else None
                c = procs.contention(procs.list_processes(), {self.proc.pid})
                r.update(sys_busy=busy, games=c["games"], builds=c["builds"])
                self.res.append((t, self.phase_name, r, fps))
                try:
                    self._resf.write(f"{t}\t{self.phase_name}\t{r['handles']}\t{r['threads']}\t{r['private_mb']}\t"
                                     f"{r['ws_mb']}\t{r['gdi']}\t{r['user']}\t{r['cpu_s']}\t{fps}\t{busy}\t"
                                     f"{c['games']}\t{c['builds']}\n")
                except ValueError:
                    return
            self._stop.wait(self.sample_s)

    def console(self, cmd, timeout=3.0):
        """One command to the runtime's debug console (PS3_DEBUG=<file>, started with
        console=True): write it, wait until the console consumed it (it empties the file).
        Returns True when consumed."""
        path = self.extra_env.get("PS3_DEBUG")
        if not path:
            return False
        with open(path, "w") as f:
            f.write(cmd + "\n")
        end = time.perf_counter() + timeout
        while time.perf_counter() < end:
            try:
                if os.path.getsize(path) == 0:
                    return True
            except OSError:
                pass
            time.sleep(0.05)
        return False

    def stop(self):
        res = super().stop()
        try:
            self._resf.close()
        except Exception:
            pass
        return res
