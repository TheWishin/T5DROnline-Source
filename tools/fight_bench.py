#!/usr/bin/env python3
"""Fight benchmark: boot straight into a fight, measure, stop the game.

    python tools/fight_bench.py [--exe build/cmake/t5dr.exe] [--cpus N|0xMASK]
                                [--fight lil,ask,20,3] [--secs 42] [--skip 24]
                                [--out build/fight-bench/NAME] [--polite]
                                [--priority normal|below|idle] [--ecoqos]
                                [--hog N [--hog-cpus MASK] [--hog-priority P]]
                                [--json FILE] [NAME=VALUE ...]

Boots the game in direct-fight mode (T5_FIGHT, docs/DIRECTFIGHT.md) with the
window minimised and P1 pressing buttons, and measures the window from fight
start + --skip to fight start + --secs: fps (from the presents), frame-time
p50/p95/p99, frames over 17.5 ms, GPU time per frame (D3D12 timestamps,
frame log column gpu_us) and the CPU time of every thread of the game.

--cpus limits the game to N logical processors (0..N-1) or to a mask, the
way a weaker PC would: the mask is set on this process right before the game
starts, so the game inherits it and sizes its thread pools from it (ps3recomp
patch 0027). On a PC with SMT, processors 2k and 2k+1 are one core, so
--cpus 4 is 2 cores / 4 threads and 0x55 is 4 cores without SMT.

Other programs running at the same time change the result a lot (see
docs/RENDER_PERF.md "Weaker PCs"); the "other load" line says how many
processors they kept busy during the window.

Per thread it prints the share of one processor, the CPU time per frame and
how often the thread was switched in (context switches a second: a thread
that wakes thousands of times a second keeps a laptop's cores out of their
sleep states, docs/RENDER_PERF.md "Laptops"). --polite mutes the game
(PS3_AUDIO_MUTE=1) and starts it at below-normal priority, for a PC someone
is using. --json writes every number to a file.

Weaker PCs without touching the system (docs/WEAK_PC.md): --priority starts
the game at another priority class (--polite: below normal); --hog N runs N
busy-loop processes of our own -- background programs -- on --hog-cpus (default
the game's processors) at --hog-priority (default below normal); --ecoqos puts
the game under EcoQoS (Windows' efficiency mode: lower clocks, like a slower
or power-limited processor) for the whole run. The renderer's split per frame
(draws, walker CPU, translation, D3D12 recording, present, GPU) comes from the
frame log. The game's main thread per frame (its CPU time and the game part,
release -> flip request; median and p99) comes from PS3_GAME_THREAD_LOG
(ps3recomp patch 0061; older builds leave it out).
"""
import argparse
import csv
import ctypes
import json
import os
import statistics
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IS_WIN = os.name == "nt"

# P1 presses in the fight (seconds after fight start): buttons and moves, so
# the fighters animate and hit each other like in a real match.
PAD = [(t / 4.0, b) for t, b in enumerate(
    ["RIGHT", "SQUARE", "", "TRIANGLE", "", "CROSS", "", "RIGHT", "CIRCLE", "", "LEFT", "",
     "SQUARE", "", "SQUARE TRIANGLE", ""] * 40)]


def pct(xs, p):
    xs = sorted(xs)
    if not xs:
        return float("nan")
    k = (len(xs) - 1) * p / 100.0
    f = int(k)
    c = min(f + 1, len(xs) - 1)
    return xs[f] + (xs[c] - xs[f]) * (k - f)


if IS_WIN:
    from ctypes import wintypes as W
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.GetCurrentProcess.restype = W.HANDLE
    k32.OpenThread.restype = W.HANDLE
    k32.OpenThread.argtypes = [W.DWORD, W.BOOL, W.DWORD]
    k32.CreateToolhelp32Snapshot.restype = W.HANDLE
    k32.SetProcessAffinityMask.argtypes = [W.HANDLE, ctypes.c_size_t]
    k32.GetProcessAffinityMask.argtypes = [W.HANDLE, ctypes.POINTER(ctypes.c_size_t),
                                           ctypes.POINTER(ctypes.c_size_t)]
    k32.GetThreadTimes.argtypes = [W.HANDLE] + [ctypes.POINTER(W.FILETIME)] * 4
    k32.GetSystemTimes.argtypes = [ctypes.POINTER(W.FILETIME)] * 3
    k32.CloseHandle.argtypes = [W.HANDLE]
    k32.GetThreadDescription.argtypes = [W.HANDLE, ctypes.POINTER(ctypes.c_wchar_p)]
    k32.LocalFree.argtypes = [ctypes.c_void_p]
    k32.SetProcessInformation.argtypes = [W.HANDLE, ctypes.c_int, ctypes.c_void_p, W.DWORD]

    class THREADENTRY32(ctypes.Structure):
        _fields_ = [("dwSize", W.DWORD), ("cntUsage", W.DWORD), ("th32ThreadID", W.DWORD),
                    ("th32OwnerProcessID", W.DWORD), ("tpBasePri", W.LONG), ("tpDeltaPri", W.LONG),
                    ("dwFlags", W.DWORD)]

    def ft(t):
        return (t.dwHighDateTime << 32 | t.dwLowDateTime) / 1e7

    ntdll = ctypes.WinDLL("ntdll")
    ntdll.NtQueryInformationThread.argtypes = [W.HANDLE, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_ulong,
                                               ctypes.c_void_p]
    psapi = ctypes.WinDLL("psapi")
    psapi.EnumProcessModules.argtypes = [W.HANDLE, ctypes.c_void_p, W.DWORD, ctypes.POINTER(W.DWORD)]
    psapi.GetModuleBaseNameW.argtypes = [W.HANDLE, W.HMODULE, W.LPWSTR, W.DWORD]
    psapi.GetModuleInformation.argtypes = [W.HANDLE, W.HMODULE, ctypes.c_void_p, W.DWORD]
    k32.OpenProcess.restype = W.HANDLE
    k32.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]

    def modules(pid):
        """[(base, size, name)] of the modules loaded in pid."""
        h = k32.OpenProcess(0x0410, False, pid)          # QUERY_INFORMATION | VM_READ
        if not h:
            return []
        out = []
        try:
            arr = (W.HMODULE * 1024)()
            need = W.DWORD()
            if psapi.EnumProcessModules(h, arr, ctypes.sizeof(arr), ctypes.byref(need)):
                for i in range(min(1024, need.value // ctypes.sizeof(W.HMODULE))):
                    nm = ctypes.create_unicode_buffer(260)
                    psapi.GetModuleBaseNameW(h, W.HMODULE(arr[i]), nm, 260)

                    class MI(ctypes.Structure):
                        _fields_ = [("base", ctypes.c_void_p), ("size", W.DWORD), ("entry", ctypes.c_void_p)]
                    mi = MI()
                    if psapi.GetModuleInformation(h, W.HMODULE(arr[i]), ctypes.byref(mi), ctypes.sizeof(mi)):
                        out.append((mi.base or 0, mi.size, nm.value))
        finally:
            k32.CloseHandle(h)
        return out

    _mods = {}

    def start_module(pid, h):
        """Module holding the thread's start address ("" if unknown)."""
        addr = ctypes.c_void_p()
        if ntdll.NtQueryInformationThread(h, 9, ctypes.byref(addr), ctypes.sizeof(addr), None) != 0:
            return ""
        a = addr.value or 0
        mods = _mods.get(pid)
        if mods is None:
            mods = _mods[pid] = modules(pid)
        for base, size, nm in mods:
            if base <= a < base + size:
                return nm
        return ""

    def thread_times(pid):
        """{tid: (name, cpu seconds)} for the threads of pid."""
        out = {}
        snap = k32.CreateToolhelp32Snapshot(0x4, 0)
        te = THREADENTRY32()
        te.dwSize = ctypes.sizeof(te)
        ok = k32.Thread32First(snap, ctypes.byref(te))
        while ok:
            if te.th32OwnerProcessID == pid:
                h = k32.OpenThread(0x0840, False, te.th32ThreadID)   # QUERY_(LIMITED_)INFORMATION
                if h:
                    c, e, kt, ut = W.FILETIME(), W.FILETIME(), W.FILETIME(), W.FILETIME()
                    if k32.GetThreadTimes(h, ctypes.byref(c), ctypes.byref(e), ctypes.byref(kt), ctypes.byref(ut)):
                        name = ctypes.c_wchar_p()
                        nm = ""
                        if k32.GetThreadDescription(h, ctypes.byref(name)) >= 0 and name.value is not None:
                            nm = name.value
                            k32.LocalFree(ctypes.cast(name, ctypes.c_void_p))
                        if not nm:
                            sm = start_module(pid, h)
                            nm = "(unnamed%s)" % (" " + sm if sm else "")
                        out[te.th32ThreadID] = (nm, ft(kt) + ft(ut))
                    k32.CloseHandle(h)
            ok = k32.Thread32Next(snap, ctypes.byref(te))
        k32.CloseHandle(snap)
        return out

    ntdll.NtQuerySystemInformation.argtypes = [ctypes.c_ulong, ctypes.c_void_p, ctypes.c_ulong,
                                               ctypes.POINTER(ctypes.c_ulong)]

    def thread_switches(pid):
        """{tid: context switches so far} for the threads of pid (SystemProcessInformation)."""
        size = 1 << 22
        for _ in range(6):
            buf = ctypes.create_string_buffer(size)
            need = ctypes.c_ulong(0)
            st = ntdll.NtQuerySystemInformation(5, buf, size, ctypes.byref(need)) & 0xFFFFFFFF
            if st == 0xC0000004:                     # STATUS_INFO_LENGTH_MISMATCH
                size = max(size * 2, need.value + (1 << 16))
                continue
            if st != 0:
                return {}
            raw = buf.raw
            off = 0
            while True:
                nxt = int.from_bytes(raw[off:off + 4], "little")
                nthr = int.from_bytes(raw[off + 4:off + 8], "little")
                upid = int.from_bytes(raw[off + 80:off + 88], "little")
                if upid == pid:
                    out = {}
                    for i in range(nthr):
                        t = off + 256 + 80 * i               # SYSTEM_THREAD_INFORMATION, x64
                        tid = int.from_bytes(raw[t + 48:t + 56], "little")
                        out[tid] = int.from_bytes(raw[t + 64:t + 68], "little")
                    return out
                if not nxt:
                    return {}
                off += nxt
        return {}

    def sys_times():
        i, k, u = W.FILETIME(), W.FILETIME(), W.FILETIME()
        k32.GetSystemTimes(ctypes.byref(i), ctypes.byref(k), ctypes.byref(u))
        return ft(i), ft(k) + ft(u)          # kernel time includes idle


def start_hogs(n, mask, prio):
    """n busy-loop processes pinned to mask (None: anywhere) at priority class prio; ended
    with the game, and by Windows if this script dies (kill-on-close job)."""
    try:
        sys.path.insert(0, os.path.join(ROOT, "tools", "smoke"))
        import procs as _procs
    except Exception:       # noqa: BLE001
        _procs = None
    hogs = []
    for _ in range(n):
        h = subprocess.Popen([sys.executable, "-c", "while True: pass"], creationflags=prio if IS_WIN else 0)
        if IS_WIN and mask:
            k32.SetProcessAffinityMask(W.HANDLE(int(h._handle)), mask)
        if _procs is not None:
            h._t5_job = _procs.kill_on_close_job(h.pid)
        hogs.append(h)
    return hogs


def set_ecoqos(pid):
    """EcoQoS for the whole process (PROCESS_POWER_THROTTLING_EXECUTION_SPEED on)."""
    h = k32.OpenProcess(0x0200, False, pid)          # PROCESS_SET_INFORMATION
    if not h:
        return False
    st = (ctypes.c_ulong * 3)(1, 1, 1)               # Version, ControlMask, StateMask
    ok = bool(k32.SetProcessInformation(h, 4, ctypes.byref(st), ctypes.sizeof(st)))
    k32.CloseHandle(h)
    return ok


def game_thread_window(path, lo, hi):
    """The game's main thread per displayed frame in the QPC window [lo, hi] from
    PS3_GAME_THREAD_LOG (ps3recomp patch 0061): CPU time (thread cycles between two
    flip requests) and the game part (release -> flip request), median and p99, ms."""
    try:
        lines = open(path).read().splitlines()
    except OSError:
        return {}
    if not lines or not lines[0].startswith("#"):
        return {}
    hdr = dict(kv.split("=") for kv in lines[0][1:].split())
    qf, tf = float(hdr["qpc_frequency"]), float(hdr["tsc_frequency"])
    cpu, part = [], []
    prev = None
    for ln in lines[1:]:
        f = ln.split()
        if len(f) < 5:
            continue
        seq, req, rel, cyc, tid = int(f[0]), int(f[1]), int(f[2]), int(f[3]), int(f[4])
        if prev and prev[4] == tid and seq == prev[0] + 1 and lo <= req <= hi:
            cpu.append(1000.0 * (cyc - prev[3]) / tf)
            if prev[1] <= rel <= req:
                part.append(1000.0 * (req - rel) / qf)
        prev = (seq, req, rel, cyc, tid)
    if not cpu:
        return {}
    return {"n": len(cpu), "cpu_p50": pct(cpu, 50), "cpu_p99": pct(cpu, 99), "cpu_mean": sum(cpu) / len(cpu),
            "part_p50": pct(part, 50) if part else float("nan"), "part_p99": pct(part, 99) if part else float("nan")}


def renderer_split(rows):
    """Medians per frame (ms) of the frame log's renderer columns, or {} without them."""
    if not rows or "fifo_cpu_us" not in rows[0]:
        return {}
    ph = ["ph_layout_us", "ph_fetch_us", "ph_upload_us", "ph_pso_us", "ph_const_us", "ph_texbind_us"]

    def med(f):
        xs = []
        for r in rows:
            try:
                xs.append(f(r))
            except (KeyError, TypeError, ValueError):
                pass
        return statistics.median(xs) if xs else float("nan")

    def num(k):
        return lambda r: float(r[k])
    out = {"draws": med(num("draws")),
           "fifo_cpu_ms": med(num("fifo_cpu_us")) / 1000.0,
           "xlat_ms": med(num("xlat_us")) / 1000.0,
           "draw_ms": med(num("draw_us")) / 1000.0,
           "d3d_ms": med(lambda r: float(r["draw_us"]) - sum(float(r[k]) for k in ph)) / 1000.0,
           "texbind_ms": med(num("ph_texbind_us")) / 1000.0,
           "pso_ms": med(num("ph_pso_us")) / 1000.0,
           "vertex_ms": med(lambda r: sum(float(r[k]) for k in ("ph_layout_us", "ph_fetch_us", "ph_upload_us"))) / 1000.0,
           "texhash_ms": med(num("texhash_us")) / 1000.0,
           "submit_ms": med(num("present_flush_us")) / 1000.0,
           "present_ms": med(num("present_call_us")) / 1000.0,
           "flush_wait_ms": med(num("flush_wait_us")) / 1000.0}
    if rows[0].get("ph_desc_us") not in (None, ""):
        # patch 0059 splits the recording after the texture binding: descriptor tables, RT binding and
        # barriers; the vertex-constant copy; the root/PSO/viewport/IA calls and the draw itself
        out["d3d_ms"] = med(lambda r: float(r["ph_desc_us"]) + float(r["ph_api_us"]) + float(r["ph_post_us"])) / 1000.0
        out["cbcopy_ms"] = med(num("ph_cbcopy_us")) / 1000.0
    if rows[0].get("game_us") not in (None, ""):
        out["game_ms"] = med(num("game_us")) / 1000.0
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--exe", default=os.path.join(ROOT, "build", "cmake", "t5dr.exe"))
    ap.add_argument("--vfs", default=os.environ.get("PS3_VFS_ROOT", os.path.join(ROOT, "game", "vfs")))
    ap.add_argument("--cpus", default="", help="N logical processors (0..N-1) or 0xMASK")
    ap.add_argument("--fight", default="lil,ask,20,3")
    ap.add_argument("--secs", type=float, default=42.0, help="end of the window, s after fight start")
    ap.add_argument("--skip", type=float, default=24.0, help="start of the window, s after fight start")
    ap.add_argument("--out", default="", help="directory for logs (default build/fight-bench/<time>)")
    ap.add_argument("--polite", action="store_true",
                    help="someone uses this PC: the game muted (PS3_AUDIO_MUTE=1) at below-normal priority")
    ap.add_argument("--json", default="", help="also write the results to this file")
    ap.add_argument("--priority", choices=["", "normal", "below", "idle"], default="",
                    help="the game's priority class (default: below with --polite, else normal)")
    ap.add_argument("--hog", type=int, default=0, help="N busy-loop processes next to the game (background programs)")
    ap.add_argument("--hog-cpus", default="", help="their processors: N (0..N-1) or 0xMASK (default: the game's)")
    ap.add_argument("--hog-priority", choices=["normal", "below", "idle"], default="below")
    ap.add_argument("--ecoqos", action="store_true",
                    help="run the game under EcoQoS (lower clocks): a slower-processor stand-in")
    ap.add_argument("env", nargs="*", help="extra NAME=VALUE for the game")
    a = ap.parse_args()

    out = os.path.abspath(a.out or os.path.join(ROOT, "build", "fight-bench", time.strftime("%Y%m%d-%H%M%S")))
    os.makedirs(out, exist_ok=True)
    vfs = os.path.abspath(a.vfs)
    env = dict(os.environ)
    env.update({
        "PS3_VFS_ROOT": vfs.replace("\\", "/"),
        "PS3_HDD0_ROOT": os.path.join(vfs, "dev_hdd0").replace("\\", "/"),
        "PS3_GCM_TICKER_PUMP": "1", "RSX_LIVE_DRAW": "1", "PS3_VERBOSE": "0",
        "PS3_WINDOW_BACKGROUND": "1", "PAD_NO_KEYBOARD": "1",
        "T5_FIGHT": a.fight,
        "T5_DF_STATUS_FILE": os.path.join(out, "status.json"),
        "PS3_FRAMELOG": os.path.join(out, "frames.csv"),
        "PS3_PAD_FILE": os.path.join(out, "pad.txt"),
        "PS3_GAME_THREAD_LOG": os.path.join(out, "game_thread.log"),
    })
    if a.polite:
        env["PS3_AUDIO_MUTE"] = "1"
    for kv in a.env:
        k, v = kv.split("=", 1)
        env[k] = v
    open(env["PS3_PAD_FILE"], "w").close()

    def parse_mask(v):
        return int(v, 16) if v.lower().startswith("0x") else (1 << int(v)) - 1

    mask = None
    if a.cpus:
        mask = parse_mask(a.cpus)
    prio_flag = {"normal": 0x20, "below": 0x4000, "idle": 0x40}
    hogs = start_hogs(a.hog, parse_mask(a.hog_cpus) if a.hog_cpus else mask,
                      prio_flag[a.hog_priority]) if a.hog else []
    me = old = None
    if mask and IS_WIN:
        me = k32.GetCurrentProcess()
        pm, sm = ctypes.c_size_t(), ctypes.c_size_t()
        k32.GetProcessAffinityMask(me, ctypes.byref(pm), ctypes.byref(sm))
        old = pm.value
        if not k32.SetProcessAffinityMask(me, mask):
            sys.exit("could not set the CPU mask %s" % hex(mask))
    log = open(os.path.join(out, "game.log"), "w")
    try:
        flags = subprocess.BELOW_NORMAL_PRIORITY_CLASS if (IS_WIN and a.polite) else 0
        if IS_WIN and a.priority:
            flags = prio_flag[a.priority]
        p = subprocess.Popen([os.path.abspath(a.exe), os.path.join(vfs, "PS3_GAME", "USRDIR", "EBOOT.elf")],
                             env=env, cwd=out, stdout=log, stderr=subprocess.STDOUT, creationflags=flags)
    finally:
        if old:
            k32.SetProcessAffinityMask(me, old)
    # if this script dies (killed by a driver's timeout), Windows ends the game with it
    job = None
    try:
        sys.path.insert(0, os.path.join(ROOT, "tools", "smoke"))
        import procs as _procs
        job = _procs.kill_on_close_job(p.pid)
    except Exception:       # noqa: BLE001 -- the bench still stops the game itself below
        job = None

    def setpad(s):
        tmp = env["PS3_PAD_FILE"] + ".tmp"
        with open(tmp, "w") as f:
            f.write(s)
        for _ in range(200):
            try:
                os.replace(tmp, env["PS3_PAD_FILE"])
                return
            except PermissionError:
                time.sleep(0.002)

    t0 = time.time()
    eco_t = 0.0
    fight_qpc = fight_t = None
    tt = []
    pad = list(PAD)
    try:
        while p.poll() is None:
            now = time.time()
            if a.ecoqos and IS_WIN and now - eco_t > 1.0:
                # the runtime turns power throttling off at start (host_sched.c); ours wins afterwards
                set_ecoqos(p.pid)
                eco_t = now
            if fight_t is None:
                if now - t0 > 150:
                    sys.exit("no fight after 150 s (see %s)" % os.path.join(out, "game.log"))
                try:
                    with open(env["T5_DF_STATUS_FILE"]) as f:
                        if json.load(f).get("state") == "fight":
                            fight_t, fight_qpc = now, time.perf_counter()
                except (OSError, ValueError):
                    pass
            else:
                rel = now - fight_t
                if IS_WIN and len(tt) == 0 and rel >= a.skip:
                    tt.append((time.perf_counter(), thread_times(p.pid), sys_times(), thread_switches(p.pid)))
                if IS_WIN and len(tt) == 1 and rel >= a.secs - 1:
                    tt.append((time.perf_counter(), thread_times(p.pid), sys_times(), thread_switches(p.pid)))
                if rel >= a.secs:
                    break
                while pad and pad[0][0] <= rel:
                    setpad(pad.pop(0)[1])
            time.sleep(0.01)
    finally:
        end_qpc = time.perf_counter()
        if p.poll() is None:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True)
            p.wait()
        for h in hogs:
            if h.poll() is None:
                h.kill()
                h.wait()
        log.close()

    # frames in the window (the frame log's qpc is QueryPerformanceCounter, like perf_counter)
    with open(os.path.join(out, "frames.csv")) as f:
        freq = int(f.readline().split("=")[1])
        rows = list(csv.DictReader(f))
    lo, hi = (fight_qpc + a.skip) * freq, end_qpc * freq
    w = [r for r in rows if lo <= float(r["qpc"]) <= hi]
    dts = [float(r["dt_us"]) / 1000.0 for r in w if float(r["dt_us"]) > 0]
    gpu = [float(r["gpu_us"]) / 1000.0 for r in w if r.get("gpu_us") and float(r["gpu_us"]) > 0]
    fps = len(dts) / (sum(dts) / 1000.0) if dts else 0.0
    res = {"cpus": hex(mask) if mask else "all", "frames": len(dts), "fps": fps,
           "priority": a.priority or ("below" if a.polite else "normal"), "ecoqos": a.ecoqos,
           "hog": a.hog, "hog_cpus": a.hog_cpus, "hog_priority": a.hog_priority if a.hog else "",
           "p50": pct(dts, 50), "p95": pct(dts, 95), "p99": pct(dts, 99), "max": max(dts) if dts else 0.0,
           "over_17_5": sum(d > 17.5 for d in dts), "env": a.env, "exe": os.path.abspath(a.exe), "out": out}
    print("cpus=%s frames=%d fps=%.2f frame ms p50=%.2f p95=%.2f p99=%.2f max=%.1f, over 17.5 ms: %d" % (
        res["cpus"], len(dts), fps, res["p50"], res["p95"], res["p99"], res["max"], res["over_17_5"]))
    split = renderer_split(w)
    if split:
        res["renderer"] = split
        print("renderer per frame (median): %(draws).0f draws; walker CPU %(fifo_cpu_ms).2f ms, translation "
              "%(xlat_ms).2f ms (draw recording %(draw_ms).2f: D3D12 calls%(cb)s %(d3d_ms).2f, "
              "texture/sampler binding %(texbind_ms).2f, PSO lookup %(pso_ms).2f, vertex %(vertex_ms).2f), "
              "submit %(submit_ms).2f, present call %(present_ms).2f%(game)s" % dict(
                  split, game=", game (release -> flip) %.2f ms" % split["game_ms"] if "game_ms" in split else "",
                  cb=" + constant copies" if "cbcopy_ms" not in split else ""))
    gt = game_thread_window(os.path.join(out, "game_thread.log"), lo, hi)
    if gt:
        res["game_thread"] = gt
        print("game thread per frame: CPU median %(cpu_p50).2f ms, p99 %(cpu_p99).2f; game part (release -> flip "
              "request) median %(part_p50).2f ms, p99 %(part_p99).2f (%(n)d frames)" % gt)
    slow = [ln.strip() for ln in open(os.path.join(out, "game.log"), errors="replace") if ln.startswith("[slow-frames]")]
    if slow:
        res["slow_frames"] = slow
    if gpu:
        res["gpu_p10"], res["gpu_median"] = pct(gpu, 10), statistics.median(gpu)
        print("GPU ms per frame: p10 %.3f median %.3f (timestamps; other programs on the GPU inflate them)" % (
            pct(gpu, 10), statistics.median(gpu)))
    if len(tt) == 2:
        span = tt[1][0] - tt[0][0]
        # frames presented while the CPU times were taken
        nfr = max(1, sum(1 for r in rows if tt[0][0] * freq <= float(r["qpc"]) <= tt[1][0] * freq))
        threads = {}
        for tid, (nm, t) in tt[1][1].items():
            d = t - tt[0][1].get(tid, (nm, 0.0))[1]
            sw = tt[1][3].get(tid, 0) - tt[0][3].get(tid, 0)
            r = threads.setdefault(nm, [0, 0.0, 0])
            r[0] += 1
            r[1] += d
            r[2] += max(0, sw)
        tot = sum(v[1] for v in threads.values()) / span
        mach = ((tt[1][2][1] - tt[0][2][1]) - (tt[1][2][0] - tt[0][2][0])) / span
        sw_tot = sum(v[2] for v in threads.values()) / span
        res.update({"span_s": span, "frames_in_cpu_window": nfr, "game_cpu": tot, "other_load": mach - tot,
                    "cpu_ms_per_frame": 1000.0 * tot * span / nfr, "switches_per_s": sw_tot,
                    "threads": {nm: {"n": n, "cpu_pct": 100.0 * d / span, "ms_per_frame": 1000.0 * d / nfr,
                                     "switches_per_s": sw / span}
                                for nm, (n, d, sw) in threads.items()}})
        print("game CPU %.2f processors (%.1f ms per frame), %.0f context switches/s; other load %.1f processors" % (
            tot, res["cpu_ms_per_frame"], sw_tot, mach - tot))
        for nm, (n, d, sw) in sorted(threads.items(), key=lambda kv: -kv[1][1])[:16]:
            print("  %6.1f%%  %6.2f ms/frame  %6.0f sw/s  x%-3d %s" % (100.0 * d / span, 1000.0 * d / nfr,
                                                                      sw / span, n, nm))
    if a.json:
        with open(a.json, "w") as f:
            json.dump(res, f, indent=1)
    print("logs:", out)


if __name__ == "__main__":
    main()
