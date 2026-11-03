"""The real CI command reports abnormal exits after the unittest summary."""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest

from helpers import ROOT


WRAPPER = os.path.join(ROOT, "tests", "ci_unittest.py")
SCOPE = os.path.join(ROOT, "_ci_scope_temp")


class ShutdownCrash(unittest.TestCase):
    def run_suite(self, *, fails=False, exit_code=None):
        os.makedirs(SCOPE, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="ci_shutdown_", dir=SCOPE) as folder:
            source = textwrap.dedent("""\
                import atexit, os, unittest
                class Case(unittest.TestCase):
                    def test_result(self):
                        if FAILS:
                            self.fail("failure before shutdown")
                """)
            source = "FAILS = %r\n" % fails + source
            if exit_code is not None:
                source += "atexit.register(lambda: os._exit(%d))\n" % exit_code
            with open(os.path.join(folder, "test_shutdown.py"), "w", encoding="utf-8") as stream:
                stream.write(source)
            env = dict(os.environ)
            for name in ("T5DR_CI_PROGRESS", "T5DR_CI_DEADLINE", "T5DR_CI_TIMEOUT"):
                env.pop(name, None)
            env.update(TEMP=folder, TMP=folder, TMPDIR=folder,
                       PYTHONDONTWRITEBYTECODE="1", GITHUB_ACTIONS="true")
            result = subprocess.run(
                [sys.executable, "-B", WRAPPER, "--timeout", "15", "-s", folder],
                cwd=folder, env=env, capture_output=True, text=True, timeout=25)
            output = result.stdout + result.stderr
            self.assertIn("Ran 1 test", output)
            self.assertIn("== time per module", output)
            if fails:
                self.assertIn("AssertionError: failure before shutdown", output)
            return result.returncode, output

    def assert_shutdown_crash(self, *, fails=False, exit_code=3):
        rc, output = self.run_suite(fails=fails, exit_code=exit_code)
        self.assertEqual(rc, exit_code or 1, output)
        self.assertIn("the test process ended without finishing: exit code %d" % exit_code, output)
        self.assertIn("during shutdown", output)
        self.assertIn("::error title=unittest process died::", output)

    def test_crash_after_success_summary_is_reported(self):
        self.assert_shutdown_crash()

    def test_crash_after_failure_summary_is_reported(self):
        self.assert_shutdown_crash(fails=True)

    def test_failure_exit_after_success_summary_is_reported(self):
        self.assert_shutdown_crash(exit_code=1)

    def test_success_exit_after_failure_summary_still_fails(self):
        self.assert_shutdown_crash(fails=True, exit_code=0)

    def test_normal_success_has_no_crash_diagnostic(self):
        rc, output = self.run_suite()
        self.assertEqual(rc, 0, output)
        self.assertNotIn("process died", output)
        self.assertNotIn("without finishing", output)

    def test_normal_failure_has_no_crash_diagnostic(self):
        rc, output = self.run_suite(fails=True)
        self.assertEqual(rc, 1, output)
        self.assertNotIn("process died", output)
        self.assertNotIn("without finishing", output)


if __name__ == "__main__":
    unittest.main()
