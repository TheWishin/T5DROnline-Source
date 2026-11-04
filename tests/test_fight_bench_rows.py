"""fight_bench reads the game's frame log after killing the game: a last row cut short must be left out, not crash."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

from helpers import ROOT

spec = importlib.util.spec_from_file_location("fight_bench_rows", os.path.join(ROOT, "tools", "fight_bench.py"))
fb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fb)


class FrameRowTest(unittest.TestCase):
    def test_num(self):
        self.assertTrue(fb._num("758322437572"))
        self.assertTrue(fb._num("16.5"))
        for v in (None, "", "12x", "0x0000"):
            self.assertFalse(fb._num(v), v)

    def test_tail_requires_complete_row_and_handles_mid_row_seek(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "frames.csv"
            path.write_bytes(b"# qpc_frequency=1000\r\nframe,qpc,dt_us\r\n"
                             b"1,100,16000\r\n2,200,16000\r\n3,300,16")
            self.assertEqual(fb.frame_log_tail(path), (1000, 200))
            self.assertEqual(fb.frame_log_tail(path, tail_bytes=35), (1000, 200))
            # Having QPC and dt_us is insufficient when later columns are absent.
            path.write_bytes(b"# qpc_frequency=1000\nframe,qpc,dt_us,draws\n"
                             b"1,100,16000,800\n2,200,16000\n")
            self.assertEqual(fb.frame_log_tail(path), (1000, 100))
            self.assertEqual(fb.read_frame_log(path)[1],
                             [{"frame": "1", "qpc": "100", "dt_us": "16000", "draws": "800"}])

    def test_drain_keeps_original_cutoff_and_excludes_extra_frames(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "frames.csv"
            header = b"# qpc_frequency=1000\nframe,qpc,dt_us\n"
            path.write_bytes(header + b"1,100,16000\n2,200,1")

            class Clock:
                now = 0.0

                def sleep(self, seconds):
                    self.now += seconds
                    if self.now >= .2:
                        path.write_bytes(header + b"1,100,16000\n2,200,16000\n3,300,999999\n")

            clock = Clock()
            drain = fb.drain_frame_log(path, .15, lambda: True,
                                       clock=lambda: clock.now, sleep=clock.sleep)
            self.assertEqual(drain["status"], "complete")
            self.assertEqual(drain["cutoff_qpc"], 150)
            self.assertEqual(drain["last_complete_qpc"], 300)
            self.assertAlmostEqual(drain["wait_s"], .2)
            frequency, rows = fb.read_frame_log(path)
            self.assertEqual(frequency, 1000)
            window = fb.frame_window(rows, 100, drain["cutoff_qpc"])
            self.assertEqual([row["frame"] for row in window], ["1"])
            self.assertEqual(fb.frame_window(rows, 200, 200), [rows[1]])

    def test_drain_times_out_and_stops_when_own_process_exits(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "frames.csv"
            path.write_text("# qpc_frequency=1000\nframe,qpc,dt_us\n1,100,16000\n")

            class Clock:
                now = 0.0

                def sleep(self, seconds):
                    self.now += seconds

            clock = Clock()
            result = fb.drain_frame_log(path, .2, lambda: True, timeout=.25,
                                        clock=lambda: clock.now, sleep=clock.sleep)
            self.assertEqual(result["status"], "timeout")
            self.assertFalse(result["complete"])
            self.assertAlmostEqual(result["wait_s"], .25)
            self.assertEqual(result["unlogged_tail_ms"], 100)
            result = fb.drain_frame_log(path, .2, lambda: False,
                                        clock=lambda: clock.now, sleep=clock.sleep)
            self.assertEqual(result["status"], "process_exited")
            self.assertEqual(result["wait_s"], 0)
            missing = Path(tmp) / "missing.csv"
            result = fb.drain_frame_log(missing, .2, lambda: False,
                                        clock=lambda: clock.now, sleep=clock.sleep)
            self.assertEqual(result["status"], "process_exited")
            self.assertIsNone(result["last_complete_qpc"])


if __name__ == "__main__":
    unittest.main()
