"""Exercise unittest's supported entry points without running server or Tk fixtures."""
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
TESTS = ROOT / "lobby" / "tests"

# Run in fresh interpreters: an earlier test's `import util` must not hide a
# broken entry point. Keep unittest's real filename/module/discovery parsing,
# but inspect its loaded suite instead of running any of its test fixtures.
LOAD_ONLY = r'''
import importlib
import runpy
import socket
import sys
import unittest

def forbidden_network(*args, **kwargs):
    raise AssertionError("import checks must not open or contact a server")

socket.socket.bind = forbidden_network
socket.socket.connect = forbidden_network
socket.socket.connect_ex = forbidden_network
socket.create_connection = forbidden_network

def inspect_suite(suite):
    count = 0
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            count += inspect_suite(test)
        else:
            if isinstance(test, unittest.loader._FailedTest):
                raise AssertionError(str(test._exception))
            count += 1
    return count

def load_only(program):
    assert inspect_suite(program.test) > 0, "no tests were loaded"

mode, *names = sys.argv[1:]
if mode == "direct":
    for name in names:
        module = importlib.import_module(name)
        assert inspect_suite(unittest.defaultTestLoader.loadTestsFromModule(module)) > 0
else:
    unittest.TestProgram.runTests = load_only
    sys.argv = ["python -m unittest", *names]
    runpy.run_module("unittest", run_name="__main__")
'''


class TestEntryPointImports(unittest.TestCase):
    def check_imports(self, mode, *names, cwd=ROOT):
        completed = subprocess.run(
            [sys.executable, "-E", "-B", "-c", LOAD_ONLY, mode, *names],
            cwd=cwd, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

    def test_repository_root_file_names_load_helpers_and_sibling_tests(self):
        self.check_imports(
            "unittest", "lobby/tests/test_room_tables_ui.py",
            "lobby/tests/test_tk_chat.py", "lobby/tests/test_tk_handicap.py",
        )

    def test_repository_root_module_names_load_helpers_and_sibling_tests(self):
        self.check_imports(
            "unittest", "lobby.tests.test_room_tables_ui",
            "lobby.tests.test_tk_chat", "lobby.tests.test_tk_handicap",
        )

    def test_discovery_still_loads_shared_helpers(self):
        for pattern in ("test_room_tables_ui.py", "test_tk_chat.py"):
            with self.subTest(pattern=pattern):
                self.check_imports("unittest", "discover", "-s", "lobby/tests", "-p", pattern)

    def test_legacy_direct_imports_from_tests_directory_still_work(self):
        self.check_imports(
            "direct", "test_room_tables_ui", "test_tk_chat", "test_tk_handicap", cwd=TESTS,
        )


if __name__ == "__main__":
    unittest.main()
