"""Contain one CI child and its descendants for bounded cleanup.

Use ``popen_kwargs`` when starting the child, then call ``attach`` before
allowing it to launch descendants. The caller supplies that startup gate.
Closing the container also cleans up descendants left after a normal exit.
"""
import ctypes
import os
import signal


class ProcessTree:
    def __init__(self):
        self._proc = None
        self._job = None
        self._closed = False
        self.popen_kwargs = {} if os.name == "nt" else {"start_new_session": True}
        if os.name == "nt":
            self._create_job()

    def _create_job(self):
        from ctypes import wintypes

        class BasicLimits(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_longlong),
                ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class IoCounters(ctypes.Structure):
            _fields_ = [(name, ctypes.c_ulonglong) for name in (
                "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
            )]

        class ExtendedLimits(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", BasicLimits),
                ("IoInfo", IoCounters),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        api.CreateJobObjectW.restype = wintypes.HANDLE
        api.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                               ctypes.c_void_p, wintypes.DWORD]
        api.SetInformationJobObject.restype = wintypes.BOOL
        api.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        api.AssignProcessToJobObject.restype = wintypes.BOOL
        api.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        api.TerminateJobObject.restype = wintypes.BOOL
        api.CloseHandle.argtypes = [wintypes.HANDLE]
        api.CloseHandle.restype = wintypes.BOOL
        self._api = api
        job = api.CreateJobObjectW(None, None)
        if not job:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE
        if not api.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            error = ctypes.WinError(ctypes.get_last_error())
            api.CloseHandle(job)
            raise error
        self._job = job

    def attach(self, proc):
        """Attach a gated Popen child; terminate it if assignment fails."""
        if self._closed or self._proc is not None:
            raise RuntimeError("process container is closed or already attached")
        if os.name == "nt":
            if not self._api.AssignProcessToJobObject(self._job, int(proc._handle)):
                error = ctypes.WinError(ctypes.get_last_error())
                proc.kill()
                proc.wait(timeout=5)
                raise error
        self._proc = proc

    def terminate(self):
        """Request immediate termination of the contained process tree."""
        if self._closed:
            return
        if os.name == "nt":
            if self._job and not self._api.TerminateJobObject(self._job, 124):
                raise ctypes.WinError(ctypes.get_last_error())
        elif self._proc is not None:
            try:
                os.killpg(self._proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    def close(self):
        """Release containment, terminating descendants even after child exit."""
        if self._closed:
            return
        if os.name == "nt":
            if self._job and not self._api.CloseHandle(self._job):
                raise ctypes.WinError(ctypes.get_last_error())
            self._job = None
        else:
            self.terminate()
        self._closed = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
