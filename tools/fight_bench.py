#!/usr/bin/env python3
"""Fight benchmark: boot straight into a fight, measure, stop the game.

    python tools/fight_bench.py [--exe build/cmake/t5dr.exe] [--cpus N|0xMASK]
                                [--fight lil,ask,20,3] [--secs 42] [--skip 24]
                                [--out build/fight-bench/NAME] [NAME=VALUE ...]

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

    class THREADENTRY32(ctypes.Structure):
        _fields_ = [("dwSize", W.DWORD), ("cntUsage", W.DWORD), ("th32ThreadID", W.DWORD),
                    ("th32OwnerProcessID", W.DWORD), ("tpBasePri", W.LONG), ("tpDeltaPri", W.LONG),
                    ("dwFlags", W.DWORD)]

    def ft(t):
        return (t.dwHighDateTime << 32 | t.dwLowDateTime) / 1e7

    def thread_times(pid):
        """{tid: (name, cpu seconds)} for the threads of pid."""
        out = {}
        snap = k32.CreateToolhelp32Snapshot(0x4, 0)
        te = THREADENTRY32()
        te.dwSize = ctypes.sizeof(te)
        ok = k32.Thread32First(snap, ctypes.byref(te))
        while ok:
            if te.th32OwnerProcessID == pid:
                h = k32.OpenThread(0x0800, False, te.th32ThreadID)   # QUERY_LIMITED_INFORMATION
                if h:
                    c, e, kt, ut = W.FILETIME(), W.FILETIME(), W.FILETIME(), W.FILETIME()
                    if k32.GetThreadTimes(h, ctypes.byref(c), ctypes.byref(e), ctypes.byref(kt), ctypes.byref(ut)):
                        name = ctypes.c_wchar_p()
                        nm = ""
                        if k32.GetThreadDescription(h, ctypes.byref(name)) >= 0 and name.value is not None:
                            nm = name.value
                            k32.LocalFree(ctypes.cast(name, ctypes.c_void_p))
                        out[te.th32ThreadID] = (nm or "(unnamed)", ft(kt) + ft(ut))
                    k32.CloseHandle(h)
            ok = k32.Thread32Next(snap, ctypes.byref(te))
        k32.CloseHandle(snap)
        return out

    def sys_times():
        i, k, u = W.FILETIME(), W.FILETIME(), W.FILETIME()
        k32.GetSystemTimes(ctypes.byref(i), ctypes.byref(k), ctypes.byref(u))
        return ft(i), ft(k) + ft(u)          # kernel time includes idle


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--exe", default=os.path.join(ROOT, "build", "cmake", "t5dr.exe"))
    ap.add_argument("--vfs", default=os.environ.get("PS3_VFS_ROOT", os.path.join(ROOT, "game", "vfs")))
    ap.add_argument("--cpus", default="", help="N logical processors (0..N-1) or 0xMASK")
    ap.add_argument("--fight", default="lil,ask,20,3")
    ap.add_argument("--secs", type=float, default=42.0, help="end of the window, s after fight start")
    ap.add_argument("--skip", type=float, default=24.0, help="start of the window, s after fight start")
    ap.add_argument("--out", default="", help="directory for logs (default build/fight-bench/<time>)")
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
    })
    for kv in a.env:
        k, v = kv.split("=", 1)
        env[k] = v
    open(env["PS3_PAD_FILE"], "w").close()

    mask = None
    if a.cpus:
        mask = int(a.cpus, 16) if a.cpus.lower().startswith("0x") else (1 << int(a.cpus)) - 1
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
        p = subprocess.Popen([os.path.abspath(a.exe), os.path.join(vfs, "PS3_GAME", "USRDIR", "EBOOT.elf")],
                             env=env, cwd=out, stdout=log, stderr=subprocess.STDOUT)
    finally:
        if old:
            k32.SetProcessAffinityMask(me, old)

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
    fight_qpc = fight_t = None
    tt = []
    pad = list(PAD)
    try:
        while p.poll() is None:
            now = time.time()
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
                    tt.append((time.perf_counter(), thread_times(p.pid), sys_times()))
                if IS_WIN and len(tt) == 1 and rel >= a.secs - 1:
                    tt.append((time.perf_counter(), thread_times(p.pid), sys_times()))
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
    print("cpus=%s frames=%d fps=%.2f frame ms p50=%.2f p95=%.2f p99=%.2f max=%.1f, over 17.5 ms: %d" % (
        hex(mask) if mask else "all", len(dts), fps, pct(dts, 50), pct(dts, 95), pct(dts, 99),
        max(dts) if dts else 0, sum(d > 17.5 for d in dts)))
    if gpu:
        print("GPU ms per frame: p10 %.3f median %.3f (timestamps; other programs on the GPU inflate them)" % (
            pct(gpu, 10), statistics.median(gpu)))
    if len(tt) == 2:
        span = tt[1][0] - tt[0][0]
        rows = {}
        for tid, (nm, t) in tt[1][1].items():
            d = t - tt[0][1].get(tid, (nm, 0.0))[1]
            r = rows.setdefault(nm, [0, 0.0])
            r[0] += 1
            r[1] += d
        tot = sum(v[1] for v in rows.values()) / span
        mach = ((tt[1][2][1] - tt[0][2][1]) - (tt[1][2][0] - tt[0][2][0])) / span
        print("game CPU %.2f processors; other load %.1f processors" % (tot, mach - tot))
        for nm, (n, d) in sorted(rows.items(), key=lambda kv: -kv[1][1])[:10]:
            print("  %6.1f%%  x%-3d %s" % (100.0 * d / span, n, nm))
    print("logs:", out)


if __name__ == "__main__":
    main()
