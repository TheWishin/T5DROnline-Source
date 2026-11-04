"""Read-only presence checks shared with OpenRecomp-FGC's launcher conventions.

Window slots: other_launchers.py, game reservation: launch_guard.py, and the
image-name check: t5_online.game_process_running. Never create or modify locks:
only an OS-held lock counts, so files left by a closed window do not count.
"""
import csv
import errno
import io
import os
import queue
import subprocess
import tempfile
import threading
import time


def lock_held(path):
    try:
        stream = open(path, "rb")
    except OSError:
        return False
    with stream:
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            return error.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK)
        # Closing releases our temporary lock; no bytes are read or written.
    return False


def game_process_running(run=subprocess.run):
    """Any t5dr.exe, regardless of its install directory or which launcher owns it."""
    if os.name != "nt":
        return False
    try:
        result = run(["tasklist", "/FI", "IMAGENAME eq t5dr.exe", "/FO", "CSV", "/NH"],
                     capture_output=True, text=True, errors="replace",
                     creationflags=subprocess.CREATE_NO_WINDOW, timeout=5, check=False)
        return result.returncode == 0 and any(
            row and row[0].casefold() == "t5dr.exe"
            for row in csv.reader(io.StringIO(result.stdout)))
    except (OSError, subprocess.TimeoutExpired, csv.Error):
        return False


class Detector:
    """Injectable checks; slow process scans publish plain data, never Tk objects."""
    def __init__(self, scan=None, held=None, directory=None, clock=None, every=1.0):
        self.scan = scan or game_process_running
        self.held = held or lock_held
        self.directory = directory or tempfile.gettempdir()
        self.clock = clock or time.monotonic
        self.every = every
        self.game_running = False
        self.window_open = False
        self._next = 0.0
        self._busy = False
        self._results = queue.Queue()
        self.enabled = os.environ.get("T5_COEXIST_CHECK", "1") != "0"

    def openrecomp_open(self):
        self.window_open = self.enabled and any(self.held(os.path.join(
            self.directory, "OpenRecomp-FGC-presence", f"window-{n}.lock")) for n in range(16))
        return self.window_open

    def refresh(self):
        """Worker body, also callable synchronously with fake checks in tests."""
        try:
            game = self.held(os.path.join(self.directory, "OpenRecomp-FGC-launches", "t5dr.lock"))
            self._results.put(bool(game or self.scan()))
        except Exception:  # an unavailable process list is no evidence of a running game
            self._results.put(False)

    def poll(self):
        if not self.enabled:
            return
        try:
            self.game_running = self._results.get_nowait()
            self._busy = False
        except queue.Empty:
            pass
        if not self._busy and self.clock() >= self._next:
            self.openrecomp_open()
            self._busy = True
            self._next = self.clock() + self.every
            threading.Thread(target=self.refresh, name="t5dr-coexist", daemon=True).start()
