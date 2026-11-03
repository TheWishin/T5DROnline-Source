"""Host integration-fixture ownership, with fake processes and in-memory pipes."""
import ast
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


def host_test_fixture():
    # Isolate the fixture body: importing the integration suite also probes
    # optional executables on the host. This check only exercises early EOF.
    path = Path(__file__).with_name("test_hosting.py")
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    host = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "HostTest")
    test = next(node for node in host.body if isinstance(node, ast.FunctionDef)
                and node.name == "test_host_mode_end_to_end")
    namespace = dict(os=os, tempfile=tempfile, subprocess=subprocess, sys=sys,
                     LOBBY=str(path.parent.parent))
    exec(compile(ast.Module(body=[test], type_ignores=[]), str(path), "exec"), namespace)
    return namespace["test_host_mode_end_to_end"]


class HostProcessCleanupTest(unittest.TestCase):
    def run_failed_host_fixture(self, returncode, wait_error=None):
        case = unittest.TestCase()
        proc = mock.Mock()
        proc.stdin = io.StringIO()
        proc.stdout = io.StringIO()  # EOF before ready exercises the failure finalizer.
        proc.poll.return_value = returncode
        proc.wait.return_value = 0
        proc.wait.side_effect = wait_error
        err = io.StringIO()
        try:
            with mock.patch.object(tempfile, "mkdtemp", return_value="unused-host-fixture"), \
                    mock.patch("builtins.open", return_value=err), \
                    mock.patch.object(subprocess, "Popen", return_value=proc):
                with self.assertRaises(type(wait_error) if wait_error else AssertionError):
                    host_test_fixture()(case)
            self.assertTrue(proc.stdin.closed, "the fixture owns the child's stdin pipe")
            self.assertTrue(proc.stdout.closed, "the fixture owns the child's stdout pipe")
            return proc
        finally:
            case.doCleanups()
            proc.stdin.close()
            proc.stdout.close()

    def test_failed_host_is_reaped_and_both_pipes_closed(self):
        proc = self.run_failed_host_fixture(None)
        proc.kill.assert_called_once_with()
        proc.wait.assert_called_once_with(15)

    def test_already_exited_host_still_releases_both_pipes(self):
        proc = self.run_failed_host_fixture(1)
        proc.kill.assert_not_called()
        proc.wait.assert_called_once_with(15)

    def test_pipes_close_even_when_reaping_times_out(self):
        self.run_failed_host_fixture(None, subprocess.TimeoutExpired("fake-host", 15))


if __name__ == "__main__":
    unittest.main()
