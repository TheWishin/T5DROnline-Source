"""tests/ci_unittest.py, the wrapper CI runs the suites with (docs/CI.md "Reading a red run without logs"): the
time per module, the skip reasons, an annotation per failure at once, and a test process that dies is reported
with the test it was running -- the push job was red from the 1.1.5 merge on with nothing to go by."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from helpers import ROOT

WRAPPER = os.path.join(ROOT, "tests", "ci_unittest.py")

MODULES = {
    "test_alpha.py": '''
import time, unittest
class A(unittest.TestCase):
    def test_ok(self):
        time.sleep(0.3)
    def test_fails(self):
        self.assertEqual(1, 2, "one is not two")
    @unittest.skip("needs a font this PC lacks")
    def test_skipped(self):
        pass
''',
    "test_beta.py": '''
import unittest
class B(unittest.TestCase):
    def test_ok(self):
        pass
    def test_sub(self):
        for i in range(2):
            with self.subTest(i=i):
                if i:
                    self.skipTest("needs a font this PC lacks")
''',
}
CRASH = '''
import os, unittest
class C(unittest.TestCase):
    def test_a_first(self):
        pass
    def test_b_dies(self):
        os._exit(3)          # as an interpreter abort ends the process: no result, no summary
'''


class Wrapper(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="t5dr_ci_wrap_")
        for name, src in MODULES.items():
            with open(os.path.join(self.d, name), "w", encoding="utf-8") as f:
                f.write(src)

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def run_wrapper(self, *args, gha=True):
        env = {k: v for k, v in os.environ.items() if k not in ("GITHUB_ACTIONS", "T5DR_CI_PROGRESS")}
        if gha:
            env["GITHUB_ACTIONS"] = "true"
        r = subprocess.run([sys.executable, WRAPPER, "-v", "-s", self.d, *args], capture_output=True, text=True,
                           env=env, timeout=120, cwd=self.d)
        return r.returncode, r.stdout, r.stderr

    def test_times_skips_and_annotations(self):
        rc, out, err = self.run_wrapper()
        self.assertEqual(rc, 1, out + err)
        table = out[out.index("== time per module"):]
        lines = table.splitlines()
        self.assertRegex(lines[1], r"^\s+0\.\d s\s+\d+\.\d %  test_alpha \(3 tests\)$")     # slowest first
        self.assertIn("test_beta (2 tests)", lines[2])
        self.assertIn("2 x needs a font this PC lacks (test_alpha, test_beta)", table)
        self.assertIn("::error title=unittest FAIL%3A test_alpha.A.test_fails::", out)
        self.assertIn("one is not two", out)
        self.assertIn("::notice title=unittest discover", out)
        self.assertIn("slowest: test_alpha", out)
        self.assertIn("::warning title=unittest discover", out)
        self.assertIn("::error title=unittest summary::1 of 5 tests did not pass: FAIL test_alpha.A.test_fails", out)
        self.assertNotIn("without finishing", out)

    def test_no_annotations_off_github(self):
        rc, out, _ = self.run_wrapper(gha=False)
        self.assertEqual(rc, 1)
        self.assertNotIn("::error", out)
        self.assertIn("== time per module", out)

    def test_a_dead_test_process_is_named(self):
        with open(os.path.join(self.d, "test_crash.py"), "w", encoding="utf-8") as f:
            f.write(CRASH)
        rc, out, err = self.run_wrapper()
        self.assertNotEqual(rc, 0)
        self.assertIn("the test process ended without finishing: exit code 3", out, out + err)
        self.assertIn("during test_crash.C.test_b_dies", out)
        self.assertIn("::error title=unittest process died::", out)
        self.assertIn("test_alpha", out[out.index("slowest modules so far"):])
        # the failure before the crash was annotated when it happened
        self.assertIn("::error title=unittest FAIL%3A test_alpha.A.test_fails::", out)

    def test_in_process_is_the_plain_run(self):
        rc, out, err = self.run_wrapper("--in-process", "test_beta", gha=False)
        self.assertEqual(rc, 0, out + err)
        self.assertIn("Ran 2 tests", out + err)


if __name__ == "__main__":
    unittest.main()
