"""Made-up replay metadata: automatic skips survive file scrubbing and live stream parsing.

No game, sockets or runtime are needed. Binary fixtures are generated in temporary files;
there are no player recordings or game assets in this test.
"""
import os
import struct
import sys
import tempfile
import unittest

from helpers import ROOT
from test_replays import make_file, NEUTRAL

sys.path.insert(0, os.path.join(ROOT, "launcher"))
sys.path.insert(0, os.path.join(ROOT, "lobby"))
import replays  # noqa: E402
from t5lobby import spectate  # noqa: E402


def string(value):
    raw = value.encode("utf-8")
    return struct.pack("<H", len(raw)) + raw


def record(kind, data):
    return struct.pack("<BI", kind, len(data)) + data


def stream(version, rules=2, costumes=False, index=0, guarded=True, result=False):
    session = struct.pack("<8I", version, 1, 0, 2, 1, 7, 7, 60) + string("test") + string("")
    match = struct.pack("<I6I", index, 0, 0, 0, 0, 0, 5 if result else 0)
    match += struct.pack("<12i", 9, 33, 0, 0, 1, 2, 20, 3, 0, 1 if result else -1, 0, 2 if result else 0)
    match += struct.pack("<Q", 0) + string("test-a") + string("test-b")
    match += struct.pack("<I", int(costumes))
    if costumes:
        match += bytes(spectate.COSTUME_BLOCK) * 2
    if rules is not None:
        match += struct.pack("<I", rules)
    guard = struct.pack("<BI", spectate.R_RULES_GUARD, spectate.RULES_GUARD_SIZE) if version >= 2 and guarded else b""
    return spectate.MAGIC + guard + record(spectate.R_SESSION, session) + record(spectate.R_MATCH, match)


class ReplayRules(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = os.path.join(self.directory.name, "synthetic" + replays.EXT)

    def write(self, version, rules=2):
        make_file(self.path, [[NEUTRAL], [NEUTRAL]],
                  [{"start": 0, "end": 0, "p1": 9, "p2": 33, "stage": 20,
                    "winner": None, "rules": rules}], version=version)

    def test_format_six_decodes_agreed_skip_without_losing_other_rules(self):
        self.write(6, 3 | (80 << 8) | (120 << 16))
        match = replays.read_payload(self.path)["matches"][0]
        self.assertTrue(match["auto_skip_after_round"])
        self.assertTrue(match["training"])
        self.assertEqual(match["life"], [80, 120])

    def test_old_files_never_enable_the_previously_reserved_bit(self):
        for version in range(1, 6):
            with self.subTest(version=version):
                self.write(version)
                self.assertFalse(replays.read_payload(self.path)["matches"][0]["auto_skip_after_round"])

    def test_scrubbing_preserves_version_six_skip_rules(self):
        self.write(6)
        clean = replays.strip_names(self.path)
        with open(self.path, "wb") as output:
            output.write(clean)
        match = replays.read_payload(self.path)["matches"][0]
        self.assertTrue(match["auto_skip_after_round"])
        self.assertEqual(match["names"], ["", ""])

    def test_format_seven_marks_reset_filter_and_scrubbing_preserves_it(self):
        self.write(7)
        self.assertTrue(replays.read_payload(self.path)["soft_reset_guard"])
        clean = replays.strip_names(self.path)
        with open(self.path, "wb") as output:
            output.write(clean)
        replay = replays.read_payload(self.path)
        self.assertTrue(replay["soft_reset_guard"])
        self.assertTrue(replay["matches"][0]["auto_skip_after_round"])
        self.assertEqual(replay["matches"][0]["names"], ["", ""])

    def test_formats_one_to_six_keep_legacy_reset_input(self):
        for version in range(1, 7):
            with self.subTest(version=version):
                self.write(version)
                self.assertFalse(replays.read_payload(self.path)["soft_reset_guard"])

    def test_throw_timing_only_changes_in_format_eight_and_survives_scrubbing(self):
        for version in range(1, 9):
            with self.subTest(version=version):
                self.write(version)
                self.assertEqual(replays.read_payload(self.path)["throw_break_rule"], version >= 8)
                clean = replays.strip_names(self.path)
                with open(self.path, "wb") as output:
                    output.write(clean)
                self.assertEqual(replays.read_payload(self.path)["throw_break_rule"], version >= 8)

    def test_future_or_invalid_versions_are_not_silently_decoded(self):
        for version in (0, 10):
            self.write(version)
            with self.assertRaises(replays.ReplayError):
                replays.read_payload(self.path)
            with self.assertRaises(replays.ReplayError):
                replays.strip_names(self.path)


class LiveRules(unittest.TestCase):
    def test_enabled_rematch_upgrades_before_publishing_its_rules(self):
        parser = spectate.LiveParser()
        parser.feed(stream(1, 0))
        enabled = stream(2, 2, index=1)[len(spectate.MAGIC):]
        guard = enabled[:5]
        self.assertEqual(parser.feed(guard), guard)
        self.assertFalse(parser.ready)
        copied = b"".join(parser.feed(enabled[i:i + 2]) for i in range(5, len(enabled), 2))
        self.assertEqual(copied, enabled[5:])
        self.assertTrue(parser.ready)
        self.assertFalse(parser.matches[0]["auto_skip_after_round"])
        self.assertTrue(parser.matches[1]["auto_skip_after_round"])

    def test_legacy_size_limit_stops_before_an_enabled_rematch(self):
        """The old native parser ignored unknown SESSION versions; its size limit is the fail-closed barrier."""
        raw = stream(1, 0) + stream(2, 2, index=1)[len(spectate.MAGIC):]
        offset = len(spectate.MAGIC)
        matches = 0
        while offset + 5 <= len(raw):
            kind, size = struct.unpack_from("<BI", raw, offset)
            if size > 1 << 24:       # old native lp_feed_checked rejects before waiting for a body
                break
            matches += int(kind == spectate.R_MATCH)
            offset += 5 + size
        self.assertEqual(matches, 1)
        self.assertEqual(raw[offset], spectate.R_RULES_GUARD)
        self.assertEqual(struct.unpack_from("<I", raw, offset + 1)[0], (1 << 24) + 1)

    def test_modern_sessions_keep_rules_through_fragmented_records_and_costumes(self):
        for version, costumes in ((2, False), (2, True), (3, False), (3, True), (4, False), (4, True)):
            with self.subTest(version=version, costumes=costumes):
                parser = spectate.LiveParser()
                raw = stream(version, 3 | (80 << 8) | (120 << 16), costumes)
                copied = b"".join(parser.feed(raw[i:i + 3]) for i in range(0, len(raw), 3))
                self.assertEqual(copied, raw)
                self.assertTrue(parser.ready)
                self.assertIsNone(parser.bad)
                match = parser.matches[0]
                self.assertTrue(match["auto_skip_after_round"])
                self.assertTrue(match["training"])
                self.assertEqual(match["life"], [80, 120])
                self.assertEqual(match["costumes"] is not None, costumes)
                self.assertEqual(match["soft_reset_guard"], version >= 3)
                self.assertEqual(match["throw_break_rule"], version >= 4)

    def test_guarded_session_upgrades_record_reset_policy_per_match(self):
        for older, newer in ((1, 2), (1, 3), (2, 3), (1, 4), (2, 4), (3, 4)):
            with self.subTest(older=older, newer=newer):
                parser = spectate.LiveParser()
                parser.feed(stream(older, 0))
                parser.feed(stream(newer, 0, index=1)[len(spectate.MAGIC):])
                self.assertIsNone(parser.bad)
                self.assertTrue(parser.ready)
                self.assertEqual([m["soft_reset_guard"] for m in parser.matches],
                                 [older >= 3, newer >= 3])
                self.assertEqual([m["throw_break_rule"] for m in parser.matches],
                                 [older >= 4, newer >= 4])
                self.assertFalse(parser.matches[-1]["auto_skip_after_round"])

    def test_result_after_session_upgrade_keeps_original_input_policy(self):
        parser = spectate.LiveParser()
        parser.feed(stream(1, 2))  # This bit was reserved in SESSION1.
        parser.feed(stream(3, 2, result=True)[len(spectate.MAGIC):])
        self.assertIsNone(parser.bad)
        old = parser.matches[0]
        self.assertFalse(old["soft_reset_guard"])
        self.assertFalse(old["auto_skip_after_round"])
        self.assertTrue(old["complete"] and old["have_result"])
        self.assertEqual((old["winner"], old["score"]), (1, [0, 2]))
        parser.feed(stream(3, 2, index=1, guarded=False)[len(spectate.MAGIC):])
        self.assertIsNone(parser.bad)
        self.assertTrue(parser.matches[1]["soft_reset_guard"])
        self.assertTrue(parser.matches[1]["auto_skip_after_round"])

    def test_session_three_rejects_unguarded_upgrade_and_guarded_repeat_or_downgrade(self):
        for older, newer, guarded in ((1, 3, False), (2, 3, False),
                                      (3, 3, True), (3, 2, True), (3, 1, False)):
            with self.subTest(older=older, newer=newer, guarded=guarded):
                parser = spectate.LiveParser()
                parser.feed(stream(older, 0))
                parser.feed(stream(newer, 0, index=1, guarded=guarded)[len(spectate.MAGIC):])
                self.assertIsNotNone(parser.bad)
                self.assertEqual(len(parser.matches), 1)

    def test_session_three_can_repeat_unguarded_for_delay_updates(self):
        parser = spectate.LiveParser()
        parser.feed(stream(3, 0))
        parser.feed(stream(3, 0, index=1, guarded=False)[len(spectate.MAGIC):])
        self.assertIsNone(parser.bad)
        self.assertTrue(parser.ready)
        self.assertTrue(all(match["soft_reset_guard"] for match in parser.matches))

    def test_throw_policy_survives_result_after_session_four_upgrade(self):
        parser = spectate.LiveParser()
        parser.feed(stream(3, 0))
        parser.feed(stream(4, 0, result=True)[len(spectate.MAGIC):])
        self.assertIsNone(parser.bad)
        self.assertFalse(parser.matches[0]["throw_break_rule"])
        self.assertTrue(parser.matches[0]["have_result"])
        parser.feed(stream(4, 0, index=1, guarded=False)[len(spectate.MAGIC):])
        self.assertIsNone(parser.bad)
        self.assertTrue(parser.matches[1]["throw_break_rule"])

    def test_session_four_upgrade_requires_guard_and_cannot_downgrade(self):
        for older, newer, guarded in ((1, 4, False), (2, 4, False), (3, 4, False),
                                      (4, 4, True), (4, 3, True), (4, 1, False)):
            with self.subTest(older=older, newer=newer, guarded=guarded):
                parser = spectate.LiveParser()
                parser.feed(stream(older, 0))
                parser.feed(stream(newer, 0, index=1, guarded=guarded)[len(spectate.MAGIC):])
                self.assertIsNotNone(parser.bad)
                self.assertEqual(len(parser.matches), 1)

    def test_session_one_defaults_skip_off_with_or_without_legacy_rule_word(self):
        for rules in (None, 2):
            parser = spectate.LiveParser()
            parser.feed(stream(1, rules))
            self.assertTrue(parser.ready)
            self.assertFalse(parser.matches[0]["auto_skip_after_round"])

    def test_unknown_session_is_rejected_before_match_publication(self):
        for version in (0, 6):
            parser = spectate.LiveParser()
            parser.feed(stream(version))
            self.assertFalse(parser.ready)
            self.assertIsNotNone(parser.bad)
            self.assertEqual(parser.matches, [])

    def test_modern_sessions_require_explicit_match_rules(self):
        for version in (2, 3, 4):
            with self.subTest(version=version):
                parser = spectate.LiveParser()
                parser.feed(stream(version, None))
                self.assertFalse(parser.ready)
                self.assertIsNotNone(parser.bad)

    def test_unguarded_upgrade_and_downgrade_are_rejected(self):
        parser = spectate.LiveParser()
        parser.feed(stream(1, 0))
        parser.feed(stream(2, 2, index=1, guarded=False)[len(spectate.MAGIC):])
        self.assertIsNotNone(parser.bad)
        self.assertEqual(len(parser.matches), 1)
        parser = spectate.LiveParser()
        parser.feed(stream(2, 2))
        parser.feed(stream(1, 0, index=1)[len(spectate.MAGIC):])
        self.assertIsNotNone(parser.bad)

    def test_guard_requires_session_upgrade_and_cannot_weaken_size_limit(self):
        guard = struct.pack("<BI", spectate.R_RULES_GUARD, spectate.RULES_GUARD_SIZE)
        for tail in (guard, record(spectate.R_MATCH, b""), stream(1, 0)[len(spectate.MAGIC):],
                     struct.pack("<BI", spectate.R_RULES_GUARD, spectate.RULES_GUARD_SIZE + 1)):
            with self.subTest(tail=tail[:5]):
                parser = spectate.LiveParser()
                parser.feed(spectate.MAGIC + guard + tail)
                self.assertIsNotNone(parser.bad)
                self.assertFalse(parser.ready)


if __name__ == "__main__":
    unittest.main()
