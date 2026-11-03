"""Release privacy regressions; all scanner inputs stay in memory."""
import contextlib
import io
import unittest

from helpers import load_tool


package = load_tool("package_release")
perf = load_tool("perf_compare")


class ReleasePlayerData(unittest.TestCase):
    def test_custom_replay_paths_and_interrupted_writes_are_rejected(self):
        for name in ("custom/match.t5replay", "custom/MATCH.T5REPLAY",
                     "custom/match.t5replay.tmp", "custom/match.t5replay.bak"):
            with self.subTest(name=name):
                self.assertTrue(package.classify(name, b""))

    def test_abandoned_atomic_settings_temp_is_rejected_in_any_folder(self):
        for name in (".launcher-settings-a1.tmp", "custom/.launcher-settings-b2.tmp",
                     r"release\custom\.launcher-settings-c3.tmp"):
            with self.subTest(name=name):
                self.assertTrue(package.classify(name, b"{}"))

    def test_renamed_replay_and_live_stream_signatures_are_rejected(self):
        # Signature prefixes only: no game data, saved match or log is created.
        for prefix in (b"T5REPLAY ", b"T5LIVE ", b"T5RP"):
            with self.subTest(prefix=prefix):
                bad, count, size = package.scan_files([("custom/renamed.data", prefix)], [], {})
                self.assertTrue(bad)
                self.assertEqual((count, size), (1, len(prefix)))

    def test_player_data_folders_are_rejected(self):
        for directory in ("replays", "saves", "savedata", "screenshots"):
            with self.subTest(directory=directory):
                self.assertTrue(package.classify("release/" + directory + "/renamed.data", b""))

    def test_zip_backslash_names_are_checked_on_every_host(self):
        # Backslashes are valid ZIP member bytes even on a POSIX packaging host.
        self.assertTrue(package.classify(r"release\custom\match.t5replay", b""))
        self.assertTrue(package.classify(r"release\custom\eboot.bin", b""))

    def test_source_mentions_of_signatures_remain_allowed(self):
        self.assertEqual(package.classify("launcher/replays.py", b'MAGIC = b"T5REPLAY 1\\n"'), [])


class PerformanceEvidence(unittest.TestCase):
    def compare(self, before, after):
        with contextlib.redirect_stdout(io.StringIO()):
            return perf.compare(before, after)

    def e2e(self, matches):
        return {"kind": "e2e", "name": "pair", "status": "PASS", "failed": [], "matches": matches}

    def test_no_runs_or_dropped_runs_cannot_pass(self):
        self.assertEqual(self.compare({}, {}), 1)
        before = {"e2e/pair": self.e2e([{"fps": [60, 60], "same_hash": True}])}
        self.assertEqual(self.compare(before, {}), 1)

    def test_e2e_pass_requires_match_hash_evidence(self):
        for matches in ([], [{"fps": [60, 60], "same_hash": False}]):
            result = {"e2e/pair": self.e2e(matches)}
            self.assertEqual(self.compare(result, result), 1)
        result = {"e2e/pair": self.e2e([{"fps": [60, 60], "same_hash": True}])}
        self.assertEqual(self.compare(result, result), 0)

    def test_zero_mismatch_counts_do_not_override_different_final_hashes(self):
        result = {"rollback/60/1": {"kind": "rollback", "rtt": 60, "jitter": 0, "loss": 0,
                                   "host": {"mismatch": 0, "hash": "a"},
                                   "join": {"mismatch": 0, "hash": "b"}}}
        self.assertEqual(self.compare(result, result), 1)

    def test_after_only_failing_scenarios_cannot_hide_behind_common_pass(self):
        before = {"e2e/pair": self.e2e([{"fps": [60, 60], "same_hash": True}])}
        extra = self.e2e([{"fps": [60, 60], "same_hash": True}])
        extra.update(name="new pair", status="FAIL", failed=["desync"])
        after = {**before, "e2e/new": extra}
        self.assertEqual(self.compare(before, after), 1)
        extra = {"kind": "rollback", "rtt": 120, "jitter": 0, "loss": 0,
                 "host": {"mismatch": 1, "hash": "a"}, "join": {"mismatch": 1, "hash": "b"}}
        self.assertEqual(self.compare(before, {**before, "rollback/new": extra}), 1)

    def test_repeated_e2e_preserves_every_failure_and_missing_evidence(self):
        passed = self.e2e([{"fps": [60, 60], "same_hash": True}])
        before = {"e2e/pair": passed}
        self.assertEqual(self.compare(before, {"e2e/pair/1": passed, "e2e/pair/2": passed}), 0)
        for earlier in (self.e2e([]), self.e2e([{"fps": [60, 60], "same_hash": False}]),
                        {**passed, "failed": ["failed check"]},
                        {**passed, "status": "FAIL", "failed": ["failed check"]}):
            after = {"e2e/pair/1": earlier, "e2e/pair/2": passed}
            self.assertEqual(self.compare(before, after), 1)


if __name__ == "__main__":
    unittest.main()
