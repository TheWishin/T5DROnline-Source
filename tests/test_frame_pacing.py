"""Display observations must not silently become submission or guessed scanout times."""
import tempfile
from pathlib import Path
import unittest

from helpers import load_tool

fp = load_tool("frame_pacing")


def sample(pc, present_refresh, sync_refresh, sync_qpc, observed=None):
    return dict(pc=pc, present_refresh=present_refresh, sync_refresh=sync_refresh,
                sync_qpc=sync_qpc, observed_qpc=observed if observed is not None else sync_qpc)


class FramePacingTests(unittest.TestCase):
    def test_thresholds_are_strict_and_rates_use_observed_duration(self):
        result = fp.summary([15.7, 16.7, 17.7, 20, 25, 33, 34])
        self.assertEqual(result["over_ms"]["20"]["count"], 3)
        self.assertEqual(result["over_ms"]["25"]["count"], 2)
        self.assertEqual(result["over_ms"]["33"]["count"], 1)
        self.assertAlmostEqual(result["inside_15_7_17_7_percent"], 300 / 7)
        self.assertAlmostEqual(result["over_ms"]["20"]["per_minute"], 180 / .1621)
        self.assertAlmostEqual(result["p99_9_ms"], 33.994)
        self.assertIsNone(fp.summary([])["p99_ms"])

    def test_display_timestamp_uses_present_refresh_not_raw_sync_qpc(self):
        # Both observations share one sync anchor. Raw SyncQPCTime deltas are zero.
        samples = [sample(1, 100, 102, 102000), sample(2, 101, 102, 102000, 102001),
                   sample(3, 103, 104, 104000)]
        result = fp.display_pacing(samples, 60000, 100000, 103000, 60)
        self.assertTrue(result["complete"])
        self.assertAlmostEqual(result["metrics"]["p50_ms"], 25)
        self.assertAlmostEqual(result["metrics"]["p99_ms"], 33.1666666667)
        self.assertEqual(result["repeated_refreshes"], 1)
        self.assertEqual(result["skipped_present_count"], 0)
        self.assertEqual(result["skipped_presents_per_minute"], 0)
        self.assertEqual(result["refreshes_per_frame"], {"1": 1, "2": 1})

    def test_duplicates_and_missing_statistics_never_imply_skipped_frames(self):
        samples = [sample(1, 100, 100, 100000), sample(1, 100, 101, 101000),
                   sample(2, 101, 101, 101000, 101001), sample(4, 103, 103, 103000),
                   sample(5, 104, 104, 104000)]
        result = fp.display_pacing(samples, 60000, 100000, 104000, 60)
        self.assertFalse(result["complete"])
        self.assertEqual(result["duplicate_observations"], 1)
        self.assertEqual(result["unobserved_present_id_gaps"], 1)
        self.assertEqual(result["metrics"]["intervals"], 2)
        self.assertIsNone(result["skipped_present_count"])

    def test_statistics_gap_straddling_window_boundary_is_unknown(self):
        samples = [sample(1, 1, 1, 1000), sample(3, 3, 3, 3000),
                   sample(4, 4, 4, 4000), sample(5, 5, 5, 5000)]
        result = fp.display_pacing(samples, 60000, 2500, 4500, 60)
        self.assertFalse(result["complete"])
        self.assertEqual(result["gap_intervals_excluded"], 1)
        self.assertIsNone(result["skipped_present_count"])

    def test_interval_boundaries_exclude_startup_and_drain(self):
        samples = [sample(i + 1, i, i, i * 1000) for i in range(1, 7)]
        result = fp.display_pacing(samples, 60000, 2500, 5500, 60)
        self.assertEqual(result["metrics"]["intervals"], 2)
        self.assertTrue(result["bounds_covered"])

    def test_refresh_counter_wrap_and_reset_are_separate(self):
        samples = [sample(0xFFFFFFFE, 0xFFFFFFFE, 0xFFFFFFFE, 1000),
                   sample(0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 2000),
                   sample(1, 1, 1, 4000)]
        result = fp.display_pacing(samples, 60000, 1000, 4000, 60)
        self.assertEqual(result["counter_resets"], 0)
        self.assertEqual(result["gap_intervals_excluded"], 1)
        self.assertEqual(fp.counter_delta(1, 0xFFFFFFFF), 2)
        reset = fp.display_pacing([sample(10, 10, 10, 1000), sample(1, 1, 1, 2000)],
                                  60000, 1000, 2000, 60)
        self.assertEqual(reset["counter_resets"], 1)
        self.assertFalse(reset["complete"])

    def test_144_hz_expected_holds_are_not_labeled_judder(self):
        samples = [sample(1, 100, 100, 100000), sample(2, 102, 102, 102000),
                   sample(3, 105, 105, 105000)]
        result = fp.display_pacing(samples, 144000, 100000, 105000, 144)
        self.assertEqual(result["repeated_refreshes"], 3)
        self.assertIsNone(result["judder_extra_refreshes"])
        self.assertAlmostEqual(result["metrics"]["p50_ms"], 17.361111111)

    def test_inference_requires_independent_stable_anchors(self):
        samples = [sample(i, i, i, i * 1000) for i in range(1, 5)]
        period, _ = fp.infer_period(samples, 60000)
        self.assertEqual(period, 1000)
        self.assertIsNone(fp.infer_period(samples[:3], 60000)[0])
        samples[-1]["sync_qpc"] += 100
        self.assertIsNone(fp.infer_period(samples, 60000)[0])

    def test_occluded_frame_log_and_partial_tail_have_no_display_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "frames.csv"
            # DXGI can report advancing nonzero statistics even while occluded.
            path.write_bytes(b"# qpc_frequency=60000\nqpc,dt_us,present_status,dxgi_present_count,dxgi_sync_qpc\n"
                             b"1000,16667,occluded,1,1000\n2000,16667,occluded,2,2000\n3000,16667,occluded,3,3000\n"
                             b"4000,16667,occluded\n5000,166")
            result = fp.analyze(path)
            self.assertFalse(result["display"]["available"])
            self.assertEqual(result["parsing"]["malformed_rows"], 1)
            self.assertEqual(result["parsing"]["partial_tail_bytes"], 8)
            self.assertFalse(result["host_frame_intervals"]["display_evidence"])
            self.assertEqual(result["successful_present_entry_intervals"]["metrics"]["intervals"], 0)
            self.assertIsNone(result["host_pacer_diagnostics"]["intentional_skip_ticks"])

    def test_host_intentional_skips_are_not_display_skips(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "frames.csv"
            path.write_text("# qpc_frequency=60000\nqpc,dt_us,present_status,intentional_skip_ticks\n"
                            "1000,16667,occluded,0\n2000,16667,occluded,2\n3000,16667,occluded,1\n")
            result = fp.analyze(path)
            diagnostics = result["host_pacer_diagnostics"]
            self.assertEqual(diagnostics["intentional_skip_ticks"], 3)
            self.assertAlmostEqual(diagnostics["intentional_skip_ticks_per_minute"], 5400)
            self.assertFalse(diagnostics["display_evidence"])
            self.assertIsNone(result["display"]["skipped_present_count"])

    def test_latency_D_schema_and_frequency_match(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "latency.log"
            path.write_text("# qpc_frequency=60000\nD 1100 1 1 1 1000\nD 2100 2 2 2 2000\n"
                            "D 3100 3 3000\nD 4100 4")
            frequency, events, parse = fp.read_latency(path)
            self.assertEqual(frequency, 60000)
            self.assertEqual(events[0]["sync_qpc"], 1000)
            self.assertEqual(len(events), 2)
            self.assertEqual(parse["malformed_D_events"], 1)

    def test_latency_fight_spans_exclude_resim_and_interround_stalls(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "latency.log"
            path.write_text("# qpc_frequency=60000\n"
                            "N 1000 1 0 0 1\nP 1100 1 1 1\nD 1200 1 1 1 1000\n"
                            "N 2000 2 0 0 1\nP 2100 2 2 2\nD 2200 2 2 2 2000\n"
                            "N 3000 3 0 0 1\nP 3100 3 3 3\nD 3200 3 3 3 3000\n"
                            "N 4000 4 0 0 0\nN 10000 1 1 0 1\n"
                            "N 20000 5 0 0 1\nP 20100 4 4 4\nD 20200 4 20 20 20000\n"
                            "N 21000 6 0 0 1\nP 21100 5 5 5\nD 21200 5 21 21 21000\n"
                            "N 22000 7 0 0 1\nP 22100 6 6 6\nD 22200 6 22 22 22000\n"
                            "N 23000 8 0 0 0\n")
            windows = fp.latency_fight_windows(path)
            self.assertEqual(windows, [[1000, 3000], [20000, 22000]])
            result = fp.analyze_latency(path, display_hz=60, fights_only=True)
            self.assertEqual(result["present_return_intervals"]["metrics"]["intervals"], 2)
            self.assertAlmostEqual(result["display"]["metrics"]["p99_ms"], 1000 / 60)
            self.assertEqual(result["display"]["repeated_refreshes"], 0)
            path.write_text(path.read_text() + "# trace_dropped=1\n")
            self.assertFalse(fp.analyze_latency(path, display_hz=60, fights_only=True)["display"]["complete"])

    def test_online_summary_does_not_guess_display_from_DWM_clock(self):
        rollback = load_tool("rollback_net_test")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "latency.log"
            path.write_text("# qpc_frequency=60000\nN 1000 1 0 0 1\n"
                            "P 1100 1 1 1\nC 1100 1000 1000\n"
                            "P 2100 2 2 2\nC 2100 2000 1000\nN 3000 3 0 0 1\n")
            result = rollback.latlog_stats(path)
            self.assertFalse(result["display"]["available"])
            self.assertFalse(result["display_evidence"])
            self.assertNotIn("refreshes_per_frame", result)
            self.assertAlmostEqual(result["present_return_metrics"]["p99_ms"], 1000 / 60)

    def test_latency_D_must_match_nonoccluded_present_hresult(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "latency.log"
            path.write_text("# qpc_frequency=60000\n"
                            "# present_hresult=1 display_statistics=successful_nonoccluded_present_only\n"
                            "P 1100 1 1 1 142213121\nD 1200 1 1 1 1000\n"
                            "P 2100 2 2 2 0\nD 2200 2 2 2 2000\n"
                            "D 2250 3 3 3 3000\nP 3100 3 3 3 0\nD 3200 3 3 3 3000\n")
            _, events, parse = fp.read_latency(path)
            self.assertTrue(parse["display_visibility_verified"])
            self.assertEqual([event["pc"] for event in events], [2, 3])


if __name__ == "__main__":
    unittest.main()
