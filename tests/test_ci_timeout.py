"""Exercise CI's real command with synthetic hangs, including interpreter exit.

These tests start only Python processes.  Every timeout has an independent
outer deadline so a broken CI watchdog cannot hang its own regression suite.
"""
import ctypes
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest

from helpers import ROOT


WRAPPER = os.path.join(ROOT, "tests", "ci_unittest.py")
SCOPE = os.path.join(ROOT, "_ci_scope_temp")


class WindowsJob:
    """An independent owner of the test's processes, used only for cleanup."""
    def __init__(self):
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
        self.kernel.CreateJobObjectW.restype = ctypes.c_void_p
        self.kernel.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self.kernel.TerminateJobObject.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        self.kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        self.handle = self.kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())

    def assign(self, proc):
        if not self.kernel.AssignProcessToJobObject(self.handle, int(proc._handle)):
            raise ctypes.WinError(ctypes.get_last_error())

    def stop(self):
        if self.handle:
            self.kernel.TerminateJobObject(self.handle, 1)

    def close(self):
        self.stop()
        self.kernel.CloseHandle(self.handle)
        self.handle = None


def stop_tree(proc, job):
    """Emergency cleanup belongs to the test, independent of the code under test."""
    if os.name == "nt":
        job.stop()
    else:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def process_running(pid):
    if os.name == "nt":
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        kernel.WaitForSingleObject.restype = ctypes.c_ulong
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.OpenProcess(0x100000, False, pid)  # SYNCHRONIZE
        if not handle:
            error = ctypes.get_last_error()
            if error == 87:  # ERROR_INVALID_PARAMETER: this PID no longer exists
                return False
            raise ctypes.WinError(error)
        try:
            return kernel.WaitForSingleObject(handle, 0) == 258  # WAIT_TIMEOUT
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    # On Linux an exited child may briefly remain a zombie, pending reaping.
    try:
        with open(f"/proc/{pid}/stat", encoding="utf-8") as f:
            return f.read().rsplit(")", 1)[1].split()[0] != "Z"
    except (OSError, IndexError):
        return True


class Timeout(unittest.TestCase):
    def setUp(self):
        os.makedirs(SCOPE, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="ci_timeout_", dir=SCOPE)
        self.addCleanup(self.temp.cleanup)
        self.directory = self.temp.name

    def run_command(self, source, *args, gha=True, timeout_env="1"):
        with open(os.path.join(self.directory, "test_hang.py"), "w", encoding="utf-8") as f:
            f.write(source)
        env = {k: v for k, v in os.environ.items()
               if k not in ("GITHUB_ACTIONS", "T5DR_CI_PROGRESS", "T5DR_CI_TIMEOUT")}
        env.update(TMP=self.directory, TEMP=self.directory,
                   TMPDIR=self.directory, PYTHONDONTWRITEBYTECODE="1")
        if timeout_env is not None:
            env["T5DR_CI_TIMEOUT"] = timeout_env
        if gha:
            env["GITHUB_ACTIONS"] = "true"
        command = [sys.executable, "-B", WRAPPER, "-v", "-s", self.directory, *args]
        job = WindowsJob() if os.name == "nt" else None
        if job:
            self.addCleanup(job.close)
        proc = subprocess.Popen(command, cwd=self.directory, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, start_new_session=os.name != "nt")
        if job:
            try:
                job.assign(proc)
            except OSError:
                proc.kill()
                proc.wait(timeout=5)
                raise
        else:
            self.addCleanup(stop_tree, proc, None)
        try:
            output, _ = proc.communicate(timeout=8)
        except subprocess.TimeoutExpired:
            stop_tree(proc, job)
            output, _ = proc.communicate(timeout=5)
            self.fail("CI wrapper exceeded the independent 8s deadline:\n" + output)
        finally:
            if proc.poll() is None:
                stop_tree(proc, job)
                proc.wait(timeout=5)
        return proc.returncode, output

    def run_hang(self, source, *args, gha=True):
        rc, output = self.run_command(source, *args, gha=gha)
        self.assertEqual(rc, 124, output)
        self.assertIn("timeout", output.lower(), output)
        self.assertIn("Timeout (", output, "missing real child stack dump:\n" + output)
        if gha:
            self.assertIn("::error title=unittest timeout::", output)
        else:
            self.assertNotIn("::error", output)
        return output

    def test_import_hang(self):
        output = self.run_hang("import time\nprint('import entered', flush=True)\ntime.sleep(120)\n")
        self.assertIn("import entered", output)
        self.assertIn("loading", output.lower())

    def test_class_setup_hang(self):
        output = self.run_hang('''
import time, unittest
class H(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        time.sleep(120)
    def test_wait(self):
        pass
''')
        self.assertIn("setUpClass", output)
        self.assertIn("test_hang.H", output)

    def test_class_teardown_hang(self):
        output = self.run_hang('''
import time, unittest
class H(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        time.sleep(120)
    def test_wait(self):
        pass
''')
        self.assertIn("tearDownClass", output)
        self.assertIn("test_hang.H", output)

    def test_module_setup_hang(self):
        output = self.run_hang('''
import time, unittest
def setUpModule():
    time.sleep(120)
class H(unittest.TestCase):
    def test_wait(self):
        pass
''')
        self.assertIn("during setUpModule test_hang", output)
        self.assertIn("in setUpModule", output)

    def test_module_setup_after_previous_module_names_new_module(self):
        with open(os.path.join(self.directory, "test_alpha.py"), "w", encoding="utf-8") as f:
            f.write('''
import unittest
class A(unittest.TestCase):
    def test_ok(self):
        pass
''')
        output = self.run_hang('''
import time, unittest
def setUpModule():
    time.sleep(120)
class H(unittest.TestCase):
    def test_wait(self):
        pass
''')
        self.assertIn("test_ok (test_alpha.A.test_ok) ... ok", output)
        self.assertIn("during setUpModule test_hang", output)
        self.assertNotIn("during tearDownModule test_alpha", output)
        self.assertIn("in setUpModule", output)

    def test_module_teardown_hang(self):
        output = self.run_hang('''
import time, unittest
def tearDownModule():
    time.sleep(120)
class H(unittest.TestCase):
    def test_wait(self):
        pass
''')
        self.assertIn("tearDownModule test_hang", output)
        self.assertIn("in tearDownModule", output)

    def test_test_body_hang(self):
        output = self.run_hang('''
import threading, time, unittest
def background_wait():
    time.sleep(120)
class H(unittest.TestCase):
    def test_wait(self):
        threading.Thread(target=background_wait, daemon=True).start()
        time.sleep(120)
''', gha=False)
        self.assertIn("test_hang.H.test_wait", output)
        self.assertIn("in background_wait", output)

    def test_shutdown_hang_after_success_summary(self):
        output = self.run_hang('''
import atexit, time, unittest
atexit.register(lambda: time.sleep(120))
class H(unittest.TestCase):
    def test_wait(self):
        pass
''')
        self.assertIn("Ran 1 test", output)
        self.assertIn("\nOK", output)
        self.assertIn("shutdown", output.lower())

    def test_timeout_stops_descendant(self):
        output = self.run_hang('''
import os, subprocess, sys, time, unittest
class H(unittest.TestCase):
    def test_wait(self):
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
        with open("descendant.pid", "w", encoding="ascii") as f:
            f.write(str(child.pid))
        time.sleep(120)
''')
        self.assertIn("test_hang.H.test_wait", output)
        self.assert_descendant_stopped()

    def assert_descendant_stopped(self):
        with open(os.path.join(self.directory, "descendant.pid"), encoding="ascii") as f:
            pid = int(f.read())
        deadline = time.monotonic() + 2
        while process_running(pid) and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertFalse(process_running(pid), "timeout left the synthetic descendant running")

    def test_normal_exit_stops_descendant(self):
        rc, output = self.run_command('''
import subprocess, sys, unittest
class H(unittest.TestCase):
    def test_ok(self):
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
        with open("descendant.pid", "w", encoding="ascii") as f:
            f.write(str(child.pid))
''', timeout_env=None, gha=False)
        self.assertEqual(rc, 0, output)
        self.assertIn("Ran 1 test", output)
        # The independent job cleanup runs after this assertion, so it cannot
        # make a leaking production runner appear to pass.
        self.assert_descendant_stopped()

    def test_normal_run_uses_default_without_false_timeout(self):
        rc, output = self.run_command('''
import unittest
class H(unittest.TestCase):
    def test_ok(self):
        pass
''', timeout_env=None, gha=False)
        self.assertEqual(rc, 0, output)
        self.assertIn("Ran 1 test", output)
        self.assertNotIn("test timeout", output)

    def test_positive_cli_timeout_overrides_environment(self):
        rc, output = self.run_command('''
import time, unittest
class H(unittest.TestCase):
    def test_ok(self):
        time.sleep(0.1)
''', "--timeout", "2", timeout_env="invalid", gha=False)
        self.assertEqual(rc, 0, output)
        self.assertIn("Ran 1 test", output)

    def test_invalid_cli_deadlines_are_rejected(self):
        for value in ("0", "-1", "nan", "inf", "invalid"):
            with self.subTest(value=value):
                rc, output = self.run_command("", "--timeout", value, gha=False)
                self.assertEqual(rc, 2, output)
                self.assertIn("finite positive number", output)

    def test_invalid_environment_deadlines_are_rejected(self):
        for value in ("0", "-1", "nan", "inf", "invalid"):
            with self.subTest(value=value):
                rc, output = self.run_command("", timeout_env=value, gha=False)
                self.assertEqual(rc, 2, output)
                self.assertIn("finite positive number", output)


if __name__ == "__main__":
    unittest.main()
