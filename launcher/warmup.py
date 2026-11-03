"""A bounded, disposable shader warm-up owned by the launcher, never a build step.

The worker checkpoints finished fights. Pausing closes its hidden game rather than
suspending a renderer while it holds driver resources; resuming starts the next
unfinished fight. No shader data is distributed with the launcher.
"""
import ctypes
import json
import os
import subprocess
import sys
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAUSE_FILE = os.path.join("logs", "warmup.pause")
CHILD_FILE = os.path.join("logs", "warmup.child")
CREATE_NO_WINDOW = 0x08000000
BELOW_NORMAL_PRIORITY_CLASS = 0x00004000
# Read by controller.start while its own lock is held; writes are serialized by
# _controllers_lock. No controller ever acquires that lock, avoiding inversion.
_global_holds = {}


def _stop_error():
    # core imports this module before it installs the lobby import path.
    try:
        from t5lobby.i18n import t
    except ImportError:
        def t(message):
            return message
    return OSError(t("Could not stop the shader warm-up"))


def _process_exited(pid):
    """Positively check exit without ever sending a signal to a recorded PID.

    A reused PID can only cause a conservative refusal while that unrelated
    process is alive. Access-denied and unknown wait results also fail closed.
    """
    if sys.platform != "win32":
        return False
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.OpenProcess(0x00100000 | 0x1000, False, pid)  # SYNCHRONIZE | QUERY_LIMITED_INFORMATION
    if not handle:
        return ctypes.get_last_error() == 87  # ERROR_INVALID_PARAMETER: PID no longer exists.
    try:
        return kernel.WaitForSingleObject(handle, 0) == 0  # WAIT_OBJECT_0: exited.
    finally:
        kernel.CloseHandle(handle)


def _recover_child(out):
    """Clear a stale marker only after its recorded child is confirmed gone."""
    path = os.path.join(out, CHILD_FILE)
    try:
        with open(path, encoding="ascii") as f:
            marker = json.load(f)
        pid = marker.get("pid") if isinstance(marker, dict) else None
        if type(pid) is not int or not 0 < pid <= 0xFFFFFFFF or not _process_exited(pid):
            return False
        os.remove(path)
        return True
    except FileNotFoundError:
        return True
    except (OSError, ValueError):
        return False


class BackgroundWarmup:
    def __init__(self, out):
        self.out = os.path.abspath(out)
        self.proc = None
        self.enabled = False
        self._holds = set()
        self._stop_failed = False
        self._lock = threading.RLock()

    @property
    def paused(self):
        return bool(self._holds) or bool(_global_holds) or self._stop_failed

    def start(self, force=False):
        """Queue at most six short fights; return as soon as the worker is started."""
        with self._lock:
            self.enabled = True
            if self.paused or sys.platform != "win32":
                return False
            if self.proc is not None and self.proc.poll() is None:
                return False
            if os.path.exists(os.path.join(self.out, CHILD_FILE)) and not _recover_child(self.out):
                return False  # A crashed worker has not confirmed its hidden game's exit.
            pause = os.path.join(self.out, PAUSE_FILE)
            try:
                os.makedirs(os.path.dirname(pause), exist_ok=True)
                try:
                    os.remove(pause)
                except FileNotFoundError:
                    pass
                python = sys.executable
                if python.lower().endswith("pythonw.exe"):
                    python = python[:-5] + ".exe"
                cmd = [python, os.path.join(ROOT, "tools", "shader_warmup.py"),
                       "--out", self.out, "--background", "--fights", "6",
                       "--fight-seconds", "3", "--minutes", "3"]
                if force:
                    cmd.append("--force")
                self.proc = subprocess.Popen(
                    cmd, cwd=self.out, stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    creationflags=CREATE_NO_WINDOW | BELOW_NORMAL_PRIORITY_CLASS)
            except OSError:
                # Optional work cannot turn a successful build into a failure.
                self.proc = None
                return False
            return True

    def pause(self):
        """Stop the hidden game before a real game starts; fail closed on failure.

        The real game must only be started after this method returns successfully.
        The worker normally acknowledges within a quarter second; the fallback
        kills its process tree if it is stuck in startup or driver work.
        """
        with self._lock:
            self._stop_failed = True
            self._stop()
            token = object()
            self._holds.add(token)
            self._stop_failed = False
            return token

    def _stop(self):
        proc = self.proc
        if proc is not None and proc.poll() is None:
            try:
                with open(os.path.join(self.out, PAUSE_FILE), "w", encoding="ascii") as f:
                    f.write("pause\n")
                proc.wait(timeout=1)
            except (OSError, subprocess.TimeoutExpired):
                try:
                    subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, timeout=5,
                                   creationflags=CREATE_NO_WINDOW, check=False)
                    proc.wait(timeout=1)
                except (OSError, subprocess.TimeoutExpired) as exc:
                    raise _stop_error() from exc
            if proc.poll() is None:
                raise _stop_error()
        if os.path.exists(os.path.join(self.out, CHILD_FILE)) and not _recover_child(self.out):
            # Never infer that the child exited merely from its worker's exit.
            raise _stop_error()
        self.proc = None

    def resume(self, token):
        with self._lock:
            if token not in self._holds:
                return False
            self._holds.remove(token)
            return self.start() if self.enabled else False

    def close(self):
        with self._lock:
            self.enabled = False
            self._stop_failed = True
            self._stop()
            self._stop_failed = False


_controllers = {}
_controllers_lock = threading.RLock()


def controller(out):
    key = os.path.normcase(os.path.abspath(out))
    with _controllers_lock:
        if key not in _controllers:
            _controllers[key] = BackgroundWarmup(out)
        return _controllers[key]


def start(out, force=False):
    return controller(out).start(force=force)


def pause(out):
    return controller(out).pause()


def resume(out, token):
    return controller(out).resume(token)


def close(out):
    return controller(out).close()


def pause_all(out=None):
    """Hold every output directory, including controllers created during a game."""
    with _controllers_lock:
        if out is not None:
            controller(out)  # Inspect stale child state even before this session's first build.
        token = object()
        held = []
        _global_holds[token] = held  # Gate new controllers before taking the snapshot.
        try:
            for item in _controllers.values():
                held.append((item, item.pause()))
        except OSError:
            del _global_holds[token]
            for item, local_token in held:
                item.resume(local_token)
            raise
        return token


def resume_all(token):
    with _controllers_lock:
        held = _global_holds.pop(token, None)
        if held is None:
            return
        for item, local_token in held:
            item.resume(local_token)
        # A player may have selected a new output while a real game was active.
        # Its newly-created controller was globally gated without a local token.
        for item in _controllers.values():
            if item.enabled:
                item.start()


def close_all(out=None):
    """Stop all known queues, including output folders the player selected earlier."""
    with _controllers_lock:
        if out is not None:
            controller(out)
        error = None
        for item in _controllers.values():
            try:
                item.close()
            except OSError as exc:
                error = error or exc
        if error is not None:
            raise error
