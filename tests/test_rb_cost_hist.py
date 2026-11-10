"""Rollback cost samples (1.2.3): trimmed means and the kept value's capped step (src/rollback/rb_cost_hist.h).

A long-session run (two persistent games, 21 matches) had one window whose re-simulated frame read 18 ms instead of
5 (one rollback met a stall); the kept value went to 12 ms, this PC's capacity to 0, and the Balanced online feel
added an input delay frame to the next matches. The C test checks the estimator; the checks below that the rollback
loop and the netplay core use it.
"""
import os
import re
import subprocess
import tempfile
import unittest

from helpers import ROOT
from test_always_left import build, compiler


def text(*p):
    with open(os.path.join(ROOT, *p), encoding="utf-8") as f:
        return f.read().replace("\r\n", "\n")


class CostHist(unittest.TestCase):
    def test_c_unit_test_passes(self):
        vcvars, clang = compiler()
        with tempfile.TemporaryDirectory() as d:
            exe = os.path.join(d, "rb_cost_hist_test.exe")
            build(vcvars, clang, os.path.join(ROOT, "tests", "c", "rb_cost_hist_test.cpp"), exe, "/std:c++17 /EHsc")
            r = subprocess.run([exe], capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout[-3000:])
        self.assertRegex(r.stdout, r"(?m)^PASS \d+ checks$")

    def test_rollback_loop_hands_over_trimmed_means(self):
        src = text("src", "rollback", "rb_net.cpp")
        start = src.index("void cost_flush(bool session_end)")
        fn = src[start:src.index("\n}\n", start)]
        self.assertIn("np::rb_cost_note(live, restore, resim)", fn)
        self.assertIn("g_cost.resim_h.trimmed()", fn)
        self.assertIn("g_cost.reset();", fn)
        self.assertNotIn("g_cost = CostAcc()", src)          # 32 KB of histograms: no temporary
        # every sample site feeds its histogram
        for h in ("live_h.add(ms)", "wall_h.add(ms)", "restore_h.add(g_cost.last_rms)", "resim_h.add("):
            self.assertIn(h, src)

    def test_kept_value_step_is_capped(self):
        src = text("src", "netplay", "netplay_core.cpp")
        start = src.index("void rb_cost_note(")
        fn = src[start:src.index("\n}\n", start)]
        self.assertEqual(len(re.findall(r"rb::cost_keep\(true, g_cost\.\w+, \w+\)", fn)), 3)
        self.assertNotIn("0.5 * (g_cost.resim_ms + resim_ms)", fn)


if __name__ == "__main__":
    unittest.main()
