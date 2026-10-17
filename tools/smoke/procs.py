"""Process helpers for the smoke suite (ctypes, no psutil).

The suite must only ever touch processes it started: other agents and the
owner run their own t5dr.exe on the same PC. So:

  * the game is started with subprocess.Popen and stopped through that handle;
  * anything the game itself spawned is found by parent PID (descendants()),
    and only if it was created after the game (a stale parent PID that Windows
    reused is not ours);
  * everything else named t5dr.exe or a compiler is only *counted*
    (contention()) -- fps and audio measured next to it are unreliable.

descendants() and contention() are pure functions over a process list, so the
tests can check the selection without Windows.
"""
import ctypes
import os
import sys
from collections import namedtuple

Proc = namedtuple("Proc", "pid ppid name")

# Processes whose presence makes fps/audio numbers unreliable: other game
# instances and parallel compiles (see build/AGENT_BRIEF.md).
GAME_NAMES = ("t5dr.exe",)
BUILD_NAMES = ("clang-cl.exe", "clang.exe", "lld-link.exe", "link.exe", "cl.exe", "ninja.exe")

IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    import ctypes.wintypes as wt

    class _PE32(ctypes.Structure):
        _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ProcessID", wt.DWORD),
                    ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wt.DWORD),
                    ("cntThreads", wt.DWORD), ("th32ParentProcessID", wt.DWORD),
                    ("pcPriClassBase", ctypes.c_long), ("dwFlags", wt.DWORD),
                    ("szExeFile", ctypes.c_wchar * 260)]

    class _PMC(ctypes.Structure):
        _fields_ = [("cb", wt.DWORD), ("PageFaultCount", wt.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
                    ("PrivateUsage", ctypes.c_size_t)]

    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _psapi = ctypes.WinDLL("psapi", use_last_error=True)
    _k32.CreateToolhelp32Snapshot.restype = wt.HANDLE
    _k32.CreateToolhelp32Snapshot.argtypes = [wt.DWORD, wt.DWORD]
    _k32.Process32FirstW.argtypes = [wt.HANDLE, ctypes.POINTER(_PE32)]
    _k32.Process32NextW.argtypes = [wt.HANDLE, ctypes.POINTER(_PE32)]
    _k32.OpenProcess.restype = wt.HANDLE
    _k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
    _k32.CloseHandle.argtypes = [wt.HANDLE]
    _k32.GetProcessTimes.argtypes = [wt.HANDLE] + [ctypes.POINTER(wt.FILETIME)] * 4
    _k32.TerminateProcess.argtypes = [wt.HANDLE, wt.UINT]
    _psapi.GetProcessMemoryInfo.argtypes = [wt.HANDLE, ctypes.POINTER(_PMC), wt.DWORD]

    _QUERY = 0x1000          # PROCESS_QUERY_LIMITED_INFORMATION
    _VM_READ = 0x0010
    _TERMINATE = 0x0001
    _INVALID = wt.HANDLE(-1).value


def list_processes():
    """Every process as Proc(pid, ppid, lower-case exe name). [] off Windows."""
    if not IS_WINDOWS:
        return []
    snap = _k32.CreateToolhelp32Snapshot(0x2, 0)          # TH32CS_SNAPPROCESS
    if not snap or snap == _INVALID:
        return []
    out = []
    try:
        e = _PE32()
        e.dwSize = ctypes.sizeof(_PE32)
        ok = _k32.Process32FirstW(snap, ctypes.byref(e))
        while ok:
            out.append(Proc(e.th32ProcessID, e.th32ParentProcessID, e.szExeFile.lower()))
            ok = _k32.Process32NextW(snap, ctypes.byref(e))
    finally:
        _k32.CloseHandle(snap)
    return out


def create_time(pid):
    """Process creation time (FILETIME ticks) or None."""
    if not IS_WINDOWS:
        return None
    h = _k32.OpenProcess(_QUERY, False, pid)
    if not h:
        return None
    try:
        c, e, k, u = wt.FILETIME(), wt.FILETIME(), wt.FILETIME(), wt.FILETIME()
        if not _k32.GetProcessTimes(h, ctypes.byref(c), ctypes.byref(e), ctypes.byref(k), ctypes.byref(u)):
            return None
        return (c.dwHighDateTime << 32) | c.dwLowDateTime
    finally:
        _k32.CloseHandle(h)


def memory(pid):
    """(working set MB, private MB) of a process, or None."""
    if not IS_WINDOWS:
        return None
    h = _k32.OpenProcess(_QUERY | _VM_READ, False, pid)
    if not h:
        return None
    try:
        c = _PMC()
        c.cb = ctypes.sizeof(_PMC)
        if not _psapi.GetProcessMemoryInfo(h, ctypes.byref(c), c.cb):
            return None
        return c.WorkingSetSize / 2 ** 20, c.PrivateUsage / 2 ** 20
    finally:
        _k32.CloseHandle(h)


def terminate(pid):
    """TerminateProcess(pid). Only call it for a PID descendants() returned."""
    if not IS_WINDOWS:
        return False
    h = _k32.OpenProcess(_TERMINATE, False, pid)
    if not h:
        return False
    try:
        return bool(_k32.TerminateProcess(h, 1))
    finally:
        _k32.CloseHandle(h)


def descendants(procs, root_pid, created=None):
    """Processes below root_pid in the parent tree (children, grandchildren...).

    `created` maps pid -> creation time; when given, a child created before
    its parent is dropped: its parent PID is stale and Windows reused it."""
    children = {}
    for p in procs:
        if p.pid != p.ppid:
            children.setdefault(p.ppid, []).append(p)
    out, stack, seen = [], [root_pid], {root_pid}
    while stack:
        parent = stack.pop()
        for c in children.get(parent, ()):
            if c.pid in seen:
                continue
            if created is not None:
                pc, cc = created.get(parent), created.get(c.pid)
                if pc is not None and cc is not None and cc < pc:
                    continue
            seen.add(c.pid)
            out.append(c)
            stack.append(c.pid)
    return out


def contention(procs, ours):
    """What else is running that skews fps/audio: {'games': n, 'builds': n,
    'names': sorted list}. `ours` is the set of PIDs this suite started."""
    games = [p for p in procs if p.name in GAME_NAMES and p.pid not in ours]
    builds = [p for p in procs if p.name in BUILD_NAMES and p.pid not in ours]
    names = sorted({p.name for p in games + builds})
    return {"games": len(games), "builds": len(builds), "names": names}


def kill_tree(popen, timeout=10.0):
    """Stop a game we started: its own descendants first (found by parent PID,
    created after it), then the process itself through the Popen handle."""
    if popen is None:
        return
    procs = list_processes()
    kids = descendants(procs, popen.pid, {p.pid: create_time(p.pid) for p in procs})
    for k in kids:
        terminate(k.pid)
    if popen.poll() is None:
        popen.kill()
    try:
        popen.wait(timeout)
    except Exception:
        pass


if IS_WINDOWS:
    class _BLI(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wt.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wt.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wt.DWORD), ("SchedulingClass", wt.DWORD)]

    class _IOC(ctypes.Structure):
        _fields_ = [(n, ctypes.c_uint64) for n in ("r", "w", "o", "rb", "wb", "ob")]

    class _JELI(ctypes.Structure):
        _fields_ = [("Basic", _BLI), ("Io", _IOC), ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t)]

    _k32.CreateJobObjectW.restype = wt.HANDLE
    _k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wt.LPCWSTR]
    _k32.SetInformationJobObject.argtypes = [wt.HANDLE, ctypes.c_int, ctypes.c_void_p, wt.DWORD]
    _k32.AssignProcessToJobObject.argtypes = [wt.HANDLE, wt.HANDLE]


class Job:
    """A Windows job object with KILL_ON_JOB_CLOSE: when the handle closes --
    close() or this Python process dying for any reason -- every process in
    it ends. Only the game we started (and what it spawns) is ever put in."""

    def __init__(self, handle):
        self.handle = handle

    def close(self):
        if self.handle and IS_WINDOWS:
            _k32.CloseHandle(self.handle)
        self.handle = None


def kill_on_close_job(pid):
    """Put `pid` into a new kill-on-close job. Returns a Job or None (not on
    Windows, or the process could not be assigned -- the suite still stops
    the game itself through kill_tree())."""
    if not IS_WINDOWS:
        return None
    job = _k32.CreateJobObjectW(None, None)
    if not job:
        return None
    info = _JELI()
    info.Basic.LimitFlags = 0x2000                    # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not _k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):
        _k32.CloseHandle(job)
        return None
    h = _k32.OpenProcess(0x0100 | 0x0001, False, pid)   # SET_QUOTA | TERMINATE
    ok = bool(h) and bool(_k32.AssignProcessToJobObject(job, h))
    if h:
        _k32.CloseHandle(h)
    if not ok:
        _k32.CloseHandle(job)
        return None
    return Job(job)


def cpu_count():
    return os.cpu_count() or 1
