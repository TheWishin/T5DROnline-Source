"""Per-thread CPU of a running t5dr.exe over an interval, with the thread names
the runtime gives its host threads (SetThreadDescription) where it does.

    python tools/soak/threads.py PID [seconds]

Read-only: OpenThread(QUERY_LIMITED_INFORMATION) on the threads of that one process.
"""
import ctypes
import ctypes.wintypes as wt
import sys
import time

k32 = ctypes.WinDLL("kernel32", use_last_error=True)


class TE32(ctypes.Structure):
    _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ThreadID", wt.DWORD),
                ("th32OwnerProcessID", wt.DWORD), ("tpBasePri", ctypes.c_long), ("tpDeltaPri", ctypes.c_long),
                ("dwFlags", wt.DWORD)]


k32.CreateToolhelp32Snapshot.restype = wt.HANDLE
k32.Thread32First.argtypes = [wt.HANDLE, ctypes.POINTER(TE32)]
k32.Thread32Next.argtypes = [wt.HANDLE, ctypes.POINTER(TE32)]
k32.OpenThread.restype = wt.HANDLE
k32.OpenThread.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
k32.GetThreadTimes.argtypes = [wt.HANDLE] + [ctypes.POINTER(wt.FILETIME)] * 4
k32.CloseHandle.argtypes = [wt.HANDLE]
k32.GetThreadPriority.argtypes = [wt.HANDLE]
try:
    k32.GetThreadDescription.argtypes = [wt.HANDLE, ctypes.POINTER(ctypes.c_wchar_p)]
except AttributeError:
    pass
k32.LocalFree.argtypes = [ctypes.c_void_p]


def threads_of(pid):
    snap = k32.CreateToolhelp32Snapshot(0x4, 0)
    out = []
    e = TE32()
    e.dwSize = ctypes.sizeof(TE32)
    ok = k32.Thread32First(snap, ctypes.byref(e))
    while ok:
        if e.th32OwnerProcessID == pid:
            out.append(e.th32ThreadID)
        ok = k32.Thread32Next(snap, ctypes.byref(e))
    k32.CloseHandle(snap)
    return out


def info(tid):
    h = k32.OpenThread(0x0800, False, tid)       # THREAD_QUERY_LIMITED_INFORMATION
    if not h:
        return None
    try:
        c, x, k, u = wt.FILETIME(), wt.FILETIME(), wt.FILETIME(), wt.FILETIME()
        k32.GetThreadTimes(h, ctypes.byref(c), ctypes.byref(x), ctypes.byref(k), ctypes.byref(u))
        cpu = (((k.dwHighDateTime << 32) | k.dwLowDateTime) + ((u.dwHighDateTime << 32) | u.dwLowDateTime)) / 1e7
        name = ""
        p = ctypes.c_wchar_p()
        if hasattr(k32, "GetThreadDescription") and k32.GetThreadDescription(h, ctypes.byref(p)) >= 0 and p.value:
            name = p.value
            k32.LocalFree(ctypes.cast(p, ctypes.c_void_p))
        return cpu, name, k32.GetThreadPriority(h)
    finally:
        k32.CloseHandle(h)


def sample(pid, secs=5.0):
    a = {t: info(t) for t in threads_of(pid)}
    time.sleep(secs)
    rows = []
    for t in threads_of(pid):
        b = info(t)
        if not b:
            continue
        cpu0 = a.get(t)[0] if a.get(t) else b[0]
        rows.append((round(100.0 * (b[0] - cpu0) / secs, 1), t, b[1], b[2]))
    rows.sort(reverse=True)
    return rows


if __name__ == "__main__":
    pid = int(sys.argv[1])
    secs = float(sys.argv[2]) if len(sys.argv) > 2 else 5.0
    rows = sample(pid, secs)
    print(f"{'cpu%':>6} {'tid':>6} {'prio':>4}  name")
    for pct, tid, name, prio in rows:
        if pct >= 0.5:
            print(f"{pct:6.1f} {tid:6d} {prio:4d}  {name}")
    print(f"total {sum(r[0] for r in rows):.1f} % of one core, {len(rows)} threads")
