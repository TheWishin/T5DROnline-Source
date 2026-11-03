"""Screen-side choice regressions. Not executed during the no-build/no-run review."""
import os
import subprocess
import tempfile
import unittest

from helpers import ROOT
from test_always_left import build, compiler


class ScreenSide(unittest.TestCase):
    def test_policy_matrix(self):
        vcvars, clang = compiler()
        with tempfile.TemporaryDirectory() as d:
            exe = os.path.join(d, "screen_side_test.exe")
            build(vcvars, clang, os.path.join(ROOT, "tests", "c", "screen_side_test.cpp"), exe,
                  "/std:c++17 /EHsc")
            result = subprocess.run([exe], capture_output=True, text=True, timeout=120)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_runtime_reads_session_choice_and_reuses_renderer(self):
        with open(os.path.join(ROOT, "src", "netplay", "always_left.cpp"), encoding="utf-8") as f:
            src = f.read()
        self.assertIn('al::parse_side(t5_env("T5_SCREEN_SIDE"), t5_env("T5_ALWAYS_LEFT"))', src)
        self.assertIn("f.side = sess.side;", src)
        self.assertIn("rsx_live_draw_set_always_left(a ? 1 : 0);", src)
        self.assertIn("port != g_mirrored_port.load", src)


if __name__ == "__main__":
    unittest.main()
