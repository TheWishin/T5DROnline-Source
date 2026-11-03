"""Synthetic frame logs only: Present call-entry cadence is distinct from dt_us and scanout.

These tests never launch a game, create a server, or require a dependency/build tree.
"""
import contextlib
import importlib.util
import io
import json
import os
import tempfile
import unittest

from helpers import ROOT


spec = importlib.util.spec_from_file_location("perf_compare", os.path.join(ROOT, "tools", "perf_compare.py"))
perf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(perf)


def frame(number, interval=16683.333333, **changes):
    returned = interval + 10 if isinstance(interval, (int, float)) else interval
    row = {"frame": str(number), "flip_sequence": str(number), "generation": "1", "slot": str(number),
           "present_interval_us": str(interval), "present_return_interval_us": str(returned),
           "present_interval_valid": "1", "present_status": "success", "intentional_skip_ticks": "0",
           "present_target_qpc": str(number * 100000), "submit_ready_qpc": str(number * 100000 - 1000),
           "dt_us": "19000"}
    row.update({key: str(value) for key, value in changes.items()})
    return row


class PresentationCadence(unittest.TestCase):
    def test_actual_entry_column_and_return_are_distinct_from_legacy_dt(self):
        report, series = perf.pacing_report([frame(1), frame(2), frame(3)])
        self.assertEqual(report["all_valid"]["count"], 2)
        self.assertAlmostEqual(report["all_valid"]["p50_ms"], 16.683333333)
        self.assertAlmostEqual(report["return_intervals"]["p50_ms"], 16.693333333)
        self.assertEqual(report["ready_on_time_steady"]["count"], 2)
        self.assertEqual(series[0]["invalid_reason"], "first")

    def test_alternating_intervals_report_negative_neighbor_correlation(self):
        report, _ = perf.pacing_report([frame(n, 14000 if n % 2 else 19000) for n in range(1, 101)])
        self.assertAlmostEqual(report["all_valid"]["neighbor_correlation"], -1)
        self.assertEqual(report["all_valid"]["outside_tolerance"], 99)
        self.assertGreater(report["all_valid"]["stddev_ms"], 2)

    def test_no_correlation_across_missing_rows_or_generation_reset(self):
        rows = [frame(1), frame(2, 14000), frame(4, 19000), frame(5, 14000),
                frame(6, 19000, generation=2), frame(7, 14000, generation=2)]
        report, series = perf.pacing_report(rows)
        self.assertEqual(report["counters"]["discontinuities"], 2)
        self.assertEqual(report["counters"]["missing_rows_from_frame_counter"], 1)
        self.assertEqual(report["counters"]["missing_flips"], 1)
        self.assertEqual(report["all_valid"]["count"], 3)
        self.assertEqual(report["all_valid"]["neighbor_pairs"], 0)
        self.assertIsNone(report["all_valid"]["neighbor_correlation"])
        self.assertFalse(series[2]["interval_valid"])
        self.assertFalse(series[4]["interval_valid"])

    def test_late_and_skipped_frames_remain_in_all_population(self):
        rows = [frame(1), frame(2, 20001, submit_ready_qpc=200001), frame(3, 33341, intentional_skip_ticks=2),
                frame(4), frame(5)]
        report, _ = perf.pacing_report(rows)
        self.assertEqual(report["all_valid"]["count"], 4)
        self.assertEqual(report["ready_on_time_steady"]["count"], 1)
        self.assertEqual(report["counters"]["local_ready_misses"], 1)
        self.assertEqual(report["counters"]["intentional_skip_frames"], 1)
        self.assertEqual(report["counters"]["intentional_skip_ticks"], 2)
        self.assertEqual(report["max_consecutive_over_17_5_ms"], 2)
        self.assertEqual(report["all_valid"]["over_20_ms"], 2)
        self.assertEqual(report["all_valid"]["over_33_4_ms"], 0)

    def test_rare_tail_is_visible_above_p99(self):
        rows = [frame(n, 40000 if n > 996 else 16683.333333) for n in range(1, 1001)]
        report, _ = perf.pacing_report(rows)
        metrics = report["all_valid"]
        self.assertAlmostEqual(metrics["p99_ms"], 16.683333333)
        self.assertAlmostEqual(metrics["p99_5_ms"], 16.683333333)
        self.assertEqual(metrics["p99_9_ms"], 40)
        self.assertEqual(metrics["over_33_4_ms"], 4)
        self.assertEqual(report["worst_frames"][0]["entry_interval_us"], 40000)

    def test_old_logs_have_no_fabricated_present_cadence(self):
        report, series = perf.pacing_report([{"frame": "1", "dt_us": "14000"},
                                            {"frame": "2", "dt_us": "19000"}])
        self.assertEqual(report["all_valid"]["count"], 0)
        self.assertEqual(report["counters"]["unknown_present_status"], 2)
        self.assertEqual(report["counters"]["missing_target_rows"], 2)
        self.assertIsNone(report["all_valid"]["p50_ms"])
        self.assertIsNone(series[1]["entry_interval_us"])
        json.dumps(report, allow_nan=False)

    def test_explicit_invalid_occlusion_and_device_error_break_intervals(self):
        rows = [frame(1), frame(2, present_interval_valid=0), frame(3, present_status="occluded"),
                frame(4), frame(5, present_status="device_error"), frame(6), frame(7)]
        report, series = perf.pacing_report(rows)
        self.assertEqual(report["all_valid"]["count"], 1)
        self.assertEqual(report["counters"]["unsuccessful_presents"], 2)
        self.assertEqual(series[1]["invalid_reason"], "runtime_invalid")
        self.assertEqual(series[3]["invalid_reason"], "present_status")

    def test_nonfinite_and_missing_cells_are_invalid(self):
        report, _ = perf.pacing_report([frame(1), frame(2, "nan"), frame(3, "inf"), frame(4, "")],
                                      {"qpc_frequency": "nan"})
        self.assertEqual(report["all_valid"]["count"], 0)
        self.assertIsNone(report["qpc_frequency"])
        json.dumps(report, allow_nan=False)

    def test_baseline_has_entry_metrics_without_inventing_release_targets(self):
        rows = [frame(1, pace_mode=0, present_target_qpc=0, submit_ready_qpc=0),
                frame(2, pace_mode=0, present_target_qpc=0, submit_ready_qpc=0)]
        report, _ = perf.pacing_report(rows)
        self.assertEqual(report["all_valid"]["count"], 1)
        self.assertEqual(report["ready_on_time_steady"]["count"], 0)
        self.assertEqual(report["counters"]["missing_target_rows"], 2)

    def test_mode_switch_and_timer_errors_are_visible(self):
        rows = [frame(1, pace_mode=0), frame(2, pace_mode=2),
                frame(3, pace_mode=2, target_late_us=700, timer_wake_error_us=650, timer_fallback=1)]
        report, series = perf.pacing_report(rows)
        self.assertEqual(report["all_valid"]["count"], 1)
        self.assertEqual(report["counters"]["discontinuities"], 1)
        self.assertEqual(report["counters"]["entry_late_over_tolerance"], 1)
        self.assertEqual(report["counters"]["timer_wake_late_over_tolerance"], 1)
        self.assertEqual(report["counters"]["timer_fallback_frames"], 1)
        self.assertEqual(report["phase_distributions"]["timer_wake_error_us"]["max_ms"], .65)
        self.assertTrue(series[2]["steady"])  # retain wake jitter instead of filtering it away

    def test_logging_drop_counter_is_cumulative_and_gaps_are_not_hidden(self):
        report, series = perf.pacing_report([frame(1, trace_dropped=0), frame(2, trace_dropped=1),
                                            frame(4, trace_dropped=1), frame(5, trace_dropped=3)])
        self.assertEqual(report["counters"]["trace_dropped"], 3)
        self.assertEqual(report["counters"]["missing_rows_from_frame_counter"], 1)
        self.assertEqual(report["all_valid"]["count"], 2)
        self.assertEqual(series[2]["trace_dropped"], "1")

    def test_missing_return_does_not_become_an_entry_sample(self):
        report, _ = perf.pacing_report([frame(1), frame(2, present_return_interval_us=""), frame(3)])
        self.assertEqual(report["all_valid"]["count"], 2)
        self.assertEqual(report["return_intervals"]["count"], 1)
        self.assertEqual(report["counters"]["invalid_return_intervals"], 2)

    def test_readonly_command_accepts_comments_and_exports_series(self):
        with tempfile.TemporaryDirectory() as folder:
            source = os.path.join(folder, "synthetic.csv")
            series = os.path.join(folder, "series.csv")
            content = ("# qpc_frequency=10000000\n# synthetic, not a player capture\n"
                       "frame,flip_sequence,generation,present_status,present_interval_us,present_interval_valid\n"
                       "1,1,1,success,0,0\n2,2,1,success,16683.333,1\n")
            with open(source, "w", encoding="utf-8") as stream:
                stream.write(content)
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(perf.report_pacing(source, series), 0)
            report = json.loads(output.getvalue())
            self.assertEqual(report["qpc_frequency"], 10000000)
            self.assertEqual(report["all_valid"]["count"], 1)
            with open(source, encoding="utf-8") as stream:
                self.assertEqual(stream.read(), content)
            with open(series, encoding="utf-8") as stream:
                self.assertIn("entry_interval_us", stream.readline())
            with self.assertRaises(ValueError):
                perf.report_pacing(source, source)
            with self.assertRaises(ValueError):
                perf.report_pacing(source, tolerance_us=-1)


if __name__ == "__main__":
    unittest.main()
