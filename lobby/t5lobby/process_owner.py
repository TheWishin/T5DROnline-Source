"""Launcher-owned Windows children, including their descendants.

The child starts suspended, enters a kill-on-close job, then resumes. Job handles
are not inherited: Windows closes the launcher's last handle even on a crash.
"""
import ctypes
import subprocess
import sys
import threading
from ctypes import wintypes

CREATE_SUSPENDED = 0x00000004
_jobs = set()  # Keep ownership alive until release(), or launcher process exit.


class _Job:
    def __init__(self):
        self._close_lock = threading.Lock()
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel = kernel
        for name, args, result in (
            ("CreateJobObjectW", (ctypes.c_void_p, wintypes.LPCWSTR), wintypes.HANDLE),
            ("SetInformationJobObject", (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD), wintypes.BOOL),
            ("AssignProcessToJobObject", (wintypes.HANDLE, wintypes.HANDLE), wintypes.BOOL),
            ("CloseHandle", (wintypes.HANDLE,), wintypes.BOOL),
        ):
            fn = getattr(kernel, name)
            fn.argtypes, fn.restype = args, result

        class BasicLimits(ctypes.Structure):
            _fields_ = [("process_time", ctypes.c_int64), ("job_time", ctypes.c_int64),
                        ("flags", wintypes.DWORD), ("min_ws", ctypes.c_size_t),
                        ("max_ws", ctypes.c_size_t), ("active", wintypes.DWORD),
                        ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD),
                        ("scheduling", wintypes.DWORD)]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [("basic", BasicLimits), ("io", ctypes.c_uint64 * 6),
                        ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
                        ("peak_process", ctypes.c_size_t), ("peak_job", ctypes.c_size_t)]

        self.handle = kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = ExtendedLimits()
        limits.basic.flags = 0x00002000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            error = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise error

    def assign(self, proc):
        if not self.kernel.AssignProcessToJobObject(self.handle, int(proc._handle)):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        # stop() and the log-tail thread can observe the same exit together.
        # Serialize the handle close so a reused Windows handle is never closed.
        with self._close_lock:
            if self.handle:
                if not self.kernel.CloseHandle(self.handle):
                    raise ctypes.WinError(ctypes.get_last_error())
                self.handle = None
            _jobs.discard(self)


def _resume(proc):
    """Resume the sole initial thread without relying on Popen's closed thread handle."""
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)

    class ThreadEntry(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("usage", wintypes.DWORD),
                    ("tid", wintypes.DWORD), ("pid", wintypes.DWORD),
                    ("base_priority", wintypes.LONG), ("delta_priority", wintypes.LONG),
                    ("flags", wintypes.DWORD)]

    for name, args, result in (
        ("CreateToolhelp32Snapshot", (wintypes.DWORD, wintypes.DWORD), wintypes.HANDLE),
        ("Thread32First", (wintypes.HANDLE, ctypes.POINTER(ThreadEntry)), wintypes.BOOL),
        ("Thread32Next", (wintypes.HANDLE, ctypes.POINTER(ThreadEntry)), wintypes.BOOL),
        ("OpenThread", (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD), wintypes.HANDLE),
        ("ResumeThread", (wintypes.HANDLE,), wintypes.DWORD),
        ("CloseHandle", (wintypes.HANDLE,), wintypes.BOOL),
    ):
        fn = getattr(kernel, name)
        fn.argtypes, fn.restype = args, result
    snapshot = kernel.CreateToolhelp32Snapshot(0x00000004, 0)  # TH32CS_SNAPTHREAD
    if snapshot == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        entry = ThreadEntry()
        entry.size = ctypes.sizeof(entry)
        found = kernel.Thread32First(snapshot, ctypes.byref(entry))
        while found:
            if entry.pid == proc.pid:
                thread = kernel.OpenThread(0x0002, False, entry.tid)  # THREAD_SUSPEND_RESUME
                if not thread:
                    raise ctypes.WinError(ctypes.get_last_error())
                try:
                    if kernel.ResumeThread(thread) == 0xFFFFFFFF:
                        raise ctypes.WinError(ctypes.get_last_error())
                    return
                finally:
                    kernel.CloseHandle(thread)
            found = kernel.Thread32Next(snapshot, ctypes.byref(entry))
        raise OSError("Owned child has no initial thread")
    finally:
        kernel.CloseHandle(snapshot)


def popen(*args, **kwargs):
    if sys.platform != "win32":
        return subprocess.Popen(*args, **kwargs)
    job = _Job()
    proc = None
    try:
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | CREATE_SUSPENDED
        proc = subprocess.Popen(*args, **kwargs)
        job.assign(proc)
        _resume(proc)
        proc._t5_job = job
        _jobs.add(job)
        return proc
    except BaseException:
        try:
            if proc is not None:
                try:
                    proc.kill()
                    proc.wait(timeout=5)
                except (OSError, subprocess.TimeoutExpired):
                    pass  # Closing the job below still terminates assigned descendants.
        finally:
            job.close()
        raise


def release(proc):
    """Close an ownership job, terminating any remaining descendants as well."""
    job = getattr(proc, "_t5_job", None)
    if job is not None:
        job.close()
        proc._t5_job = None
