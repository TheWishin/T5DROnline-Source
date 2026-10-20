#!/usr/bin/env python3
"""A slower processor on this PC, for thread-placement tests (docs/RENDER_PERF.md "Thread placement").

    python tools/slow_core.py --cpus 0x55 [--busy 60] [--period-us 4000] [--secs 120]

Starts one busy process per logical processor of --cpus, each pinned to its processor at a thread
priority above every thread of a game started below normal (TIME_CRITICAL in a normal-priority
process; the game's audio mixer is the only thread of the same level). All of them take the
processor for the first --busy percent of each --period-us, on the same QueryPerformanceCounter
clock, so the processors are taken and given back together: the game then has all of them for the
rest of each period -- like processors running at (100 - busy) % of their speed, with every thread
of the game slowed alike, and not like fewer processors (which the affinity mask models).

Runs until --secs have passed or this script is killed (a kill-on-close job ends the busy
processes with it). Prints each busy process's measured share at the end. Windows' timers wake a
little late, so the share is a few percent below --busy.

Touches no system setting: only processes of its own, pinned with an affinity mask.
"""
import argparse
import ctypes
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CHILD = r"""
import ctypes, sys, time
from ctypes import wintypes as W
k = ctypes.WinDLL('kernel32')
k.GetCurrentThread.restype = W.HANDLE
k.SetThreadPriority.argtypes = [W.HANDLE, ctypes.c_int]
k.CreateWaitableTimerExW.restype = W.HANDLE
k.CreateWaitableTimerExW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, W.DWORD, W.DWORD]
k.SetWaitableTimer.argtypes = [W.HANDLE, ctypes.POINTER(ctypes.c_longlong), ctypes.c_long, ctypes.c_void_p,
                               ctypes.c_void_p, W.BOOL]
k.WaitForSingleObject.argtypes = [W.HANDLE, W.DWORD]
period, busy, end = int(sys.argv[1]) * 1000, int(sys.argv[2]) * 1000, time.perf_counter_ns() + int(sys.argv[3]) * 10**9
k.SetThreadPriority(k.GetCurrentThread(), 15)                     # THREAD_PRIORITY_TIME_CRITICAL
tm = k.CreateWaitableTimerExW(None, None, 2, 0x1F0003)            # high resolution
pc = time.perf_counter_ns
while True:
    now = pc()
    if now >= end:
        break
    ph = now % period
    if ph < busy:
        stop = now - ph + busy
        while pc() < stop:
            pass
    else:
        due = ctypes.c_longlong(-max(1, (period - ph) // 100))    # 100 ns units, relative
        k.SetWaitableTimer(tm, ctypes.byref(due), 0, None, None, False)
        k.WaitForSingleObject(tm, 0xFFFFFFFF)
"""


def parse_mask(v):
    return int(v, 16) if v.lower().startswith("0x") else (1 << int(v)) - 1


def start(mask, busy, period_us, secs):
    """Start the busy processes; returns them (each has ._t5_job when the kill-on-close job worked)."""
    from ctypes import wintypes as W
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.SetProcessAffinityMask.argtypes = [W.HANDLE, ctypes.c_size_t]
    try:
        sys.path.insert(0, os.path.join(ROOT, "tools", "smoke"))
        import procs as _procs
    except Exception:       # noqa: BLE001
        _procs = None
    out = []
    lp = 0
    m = mask
    while m:
        if m & 1:
            p = subprocess.Popen([sys.executable, "-c", CHILD, str(period_us), str(period_us * busy // 100),
                                  str(int(secs))], creationflags=subprocess.CREATE_SUSPENDED
                                 if hasattr(subprocess, "CREATE_SUSPENDED") else 0x4)
            k32.SetProcessAffinityMask(W.HANDLE(int(p._handle)), 1 << lp)
            if _procs is not None:
                p._t5_job = _procs.kill_on_close_job(p.pid)
            resume(p.pid)
            out.append((lp, p))
        m >>= 1
        lp += 1
    return out


def resume(pid):
    ntdll = ctypes.WinDLL("ntdll")
    k32 = ctypes.WinDLL("kernel32")
    k32.OpenProcess.restype = ctypes.c_void_p
    h = k32.OpenProcess(0x0800, False, pid)               # PROCESS_SUSPEND_RESUME
    if h:
        ntdll.NtResumeProcess(ctypes.c_void_p(h))
        k32.CloseHandle(ctypes.c_void_p(h))


def cpu_seconds(p):
    from ctypes import wintypes as W
    k32 = ctypes.WinDLL("kernel32")
    c, e, kt, ut = W.FILETIME(), W.FILETIME(), W.FILETIME(), W.FILETIME()
    k32.GetProcessTimes(W.HANDLE(int(p._handle)), ctypes.byref(c), ctypes.byref(e), ctypes.byref(kt), ctypes.byref(ut))
    f = lambda t: (t.dwHighDateTime << 32 | t.dwLowDateTime) / 1e7  # noqa: E731
    return f(kt) + f(ut)


def main():
    if os.name != "nt":
        sys.exit("Windows only")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cpus", required=True, help="N logical processors (0..N-1) or 0xMASK")
    ap.add_argument("--busy", type=int, default=60, help="percent of each period the processors are taken")
    ap.add_argument("--period-us", type=int, default=4000)
    ap.add_argument("--secs", type=float, default=120.0)
    a = ap.parse_args()
    if not 1 <= a.busy <= 90:
        sys.exit("--busy must be 1..90")
    t0 = time.perf_counter()
    procs = start(parse_mask(a.cpus), a.busy, a.period_us, a.secs)
    try:
        for _lp, p in procs:
            p.wait(timeout=a.secs + 30)
    finally:
        span = time.perf_counter() - t0
        for lp, p in procs:
            if p.poll() is None:
                p.kill()
            print("LP %d: busy %.1f %% of the time" % (lp, 100.0 * cpu_seconds(p) / max(span, 1e-3)))


if __name__ == "__main__":
    main()
