"""Failure tracebacks survive an abruptly terminated real CI test child."""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest

from helpers import ROOT


WRAPPER = os.path.join(ROOT, "tests", "ci_unittest.py")
SCOPE = os.path.join(ROOT, "_ci_scope_temp")


class CrashOutput(unittest.TestCase):
    def run_suite(self, source, *, gha=False):
        os.makedirs(SCOPE, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="ci_crash_", dir=SCOPE) as folder:
            with open(os.path.join(folder, "test_fatal.py"), "w", encoding="utf-8") as stream:
                stream.write(textwrap.dedent(source))
            env = dict(os.environ)
            for name in ("GITHUB_ACTIONS", "T5DR_CI_PROGRESS", "T5DR_CI_DEADLINE", "T5DR_CI_TIMEOUT"):
                env.pop(name, None)
            env.update(TEMP=folder, TMP=folder, TMPDIR=folder, PYTHONDONTWRITEBYTECODE="1")
            if gha:
                env["GITHUB_ACTIONS"] = "true"
            result = subprocess.run(
                [sys.executable, "-B", WRAPPER, "--timeout", "15", "-s", folder],
                cwd=folder, env=env, capture_output=True, text=True, timeout=25)
            output = result.stdout + result.stderr
            self.assertEqual(result.returncode, 3, output)
            self.assertIn("the test process ended without finishing", output)
            return output

    def test_failure_before_fatal_exit_is_readable_without_annotations(self):
        output = self.run_suite('''
            import os, unittest
            class Cases(unittest.TestCase):
                def test_a_failure(self):
                    self.fail("failure retained before fatal exit")
                def test_z_exit(self):
                    os._exit(3)
        ''')
        self.assertIn("FAIL: test_a_failure", output)
        self.assertIn("Traceback (most recent call last):", output)
        self.assertIn("AssertionError: failure retained before fatal exit", output)
        self.assertNotIn("::error", output)

    def test_error_before_fatal_exit_is_readable_without_annotations(self):
        output = self.run_suite('''
            import os, unittest
            class Cases(unittest.TestCase):
                def test_a_error(self):
                    raise RuntimeError("error retained before fatal exit")
                def test_z_exit(self):
                    os._exit(3)
        ''')
        self.assertIn("ERROR: test_a_error", output)
        self.assertIn("RuntimeError: error retained before fatal exit", output)

    def test_subtest_failure_and_error_are_flushed_before_fatal_exit(self):
        output = self.run_suite('''
            import os, unittest
            class Cases(unittest.TestCase):
                def test_a_subtests(self):
                    with self.subTest(case="assertion"):
                        self.fail("subtest assertion retained")
                    with self.subTest(case="exception"):
                        raise ValueError("subtest exception retained")
                def test_z_exit(self):
                    os._exit(3)
        ''')
        self.assertIn("FAIL: test_a_subtests", output)
        self.assertIn("case='assertion'", output)
        self.assertIn("AssertionError: subtest assertion retained", output)
        self.assertIn("ERROR: test_a_subtests", output)
        self.assertIn("case='exception'", output)
        self.assertIn("ValueError: subtest exception retained", output)

    def test_fixture_error_survives_later_teardown_crash(self):
        output = self.run_suite('''
            import os, unittest
            class AFixture(unittest.TestCase):
                @classmethod
                def setUpClass(cls):
                    raise RuntimeError("fixture error retained")
                def test_unused(self):
                    pass
            class ZCrash(unittest.TestCase):
                def test_ok(self):
                    pass
                @classmethod
                def tearDownClass(cls):
                    os._exit(3)
        ''')
        self.assertIn("ERROR: setUpClass", output)
        self.assertIn("RuntimeError: fixture error retained", output)
        self.assertIn("tearDownClass test_fatal.ZCrash", output)

    def test_tracebacks_beyond_annotation_limit_survive_fatal_exit(self):
        output = self.run_suite('''
            import os, unittest
            class Cases(unittest.TestCase):
                def test_a_subtests(self):
                    for number in range(11):
                        with self.subTest(number=number):
                            self.fail("retained failure number %d" % number)
                def test_z_exit(self):
                    os._exit(3)
        ''', gha=True)
        self.assertEqual(output.count("::error title=unittest FAIL%3A"), 8, output)
        for number in range(11):
            self.assertIn("AssertionError: retained failure number %d" % number, output)
        self.assertIn("FAIL: test_a_subtests", output)


if __name__ == "__main__":
    unittest.main()
