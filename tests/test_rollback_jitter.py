"""Synthetic report inputs and pure C++ delay policy; no game or network needed."""
import os
import subprocess
import tempfile
import unittest

from helpers import ROOT, load_tool

report = load_tool("rollback_jitter_report")


class Report(unittest.TestCase):
    def test_depth_and_corrected_outputs(self):
        latency = ["# qpc_frequency=1000\n", "M 100 103 100 1.0\n",
                   "Q 115 103 100 18 13\n", "P 120\n", "M 140 110 105 1\n",
                   "Q 170 110 105 30 25\n", "P 180\n"]
        sound = ["N 100 grp=1 id=2 ch=-1 f=0 pos=0 out=0 -> 0 late=3\n",
                 "D 101 grp=1 id=3 (first run: 3 at 101) ch=-1 f=0 pos=0 out=0\n"]
        result = report.analyze(latency, sound)
        self.assertEqual(result["rollback_depth_frames"]["p95"], 5)
        self.assertEqual(result["restore_and_resim_ms"]["max"], 30)
        self.assertEqual(result["restore_and_resim_ms"]["p50"], 18)
        self.assertEqual(result["correction_done_to_next_present_ms"]["p50"], 5)
        self.assertEqual(result["corrected_sound_late_frames"]["max"], 3)
        self.assertEqual(result["sound_calls"], {"N": 1, "D": 1})

    def test_incomplete_and_malformed_are_visible(self):
        result = report.analyze(["M 10 10 8\n", "M 11 12 14\n", "Q 12 9 4\n"])
        self.assertEqual(result["incomplete_rollbacks"], 1)
        self.assertEqual(result["malformed_rollback_events"], 1)
        self.assertIsNone(result["rollback_depth_frames"]["p95"])

    def test_missing_present_is_not_a_zero_latency_sample(self):
        result = report.analyze(["M 10 10 8\n", "Q 12 10 8 3 2\n"])
        self.assertEqual(result["rollback_depth_frames"]["count"], 1)
        self.assertEqual(result["correction_done_to_next_present_ms"]["count"], 0)

    def test_percentile_is_nearest_rank(self):
        self.assertEqual(report.distribution(range(1, 21))["p95"], 19)


class Policy(unittest.TestCase):
    def test_native_policy(self):
        # Same compiler discovery as the existing no-game C++ harnesses.
        from test_always_left import compiler, build
        vcvars, clang = compiler()
        with tempfile.TemporaryDirectory() as directory:
            exe = os.path.join(directory, "rollback_delay_test.exe")
            build(vcvars, clang, os.path.join(ROOT, "tests", "c", "rollback_delay_test.cpp"),
                  exe, "/std:c++17 /EHsc")
            result = subprocess.run([exe], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS 8 checks", result.stdout)

    def test_wiring_default_off_and_wire_unchanged(self):
        with open(os.path.join(ROOT, "src", "netplay", "netplay_core.cpp"), encoding="utf-8") as source:
            text = source.read()
        self.assertIn("bool rb_adaptive_delay = false;", text)
        self.assertIn('env("T5_RB_NET_ADAPTIVE_DELAY")', text)
        self.assertIn("s.rb_adaptive_delay && s.mode == Mode::Host", text)
        self.assertIn("detail::jitter_delay(s.rtt_ms", text)
        self.assertIn("constexpr uint8_t  kVersion  = 4;", text)
        self.assertIn("if (s.rb_decided >= 0", text)


if __name__ == "__main__":
    unittest.main()
