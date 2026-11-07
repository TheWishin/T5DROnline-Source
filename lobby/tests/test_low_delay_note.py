"""1.2.2: a challenge's manual input delay far below Auto is named on the card and in the chat (t5-flash-121).

Report: a casual set at 65 ms with the challenger's input delay 0 -- rollbacks all the time, the screens between the
fights slow (they wait for every frame's input), and the music stuck on one stage's theme. The launcher now says so
when the delay is two or more frames below what Auto picks for the ping. No sockets, server or game."""
import unittest

import util  # noqa: F401 -- repository import path and safe test environment
from t5lobby import i18n
from t5lobby.tk_challenges import ChallengesUI, low_delay_note


class LowDelayNoteTest(unittest.TestCase):
    def setUp(self):
        i18n.set_language("en")

    def test_the_report_case_is_named(self):
        note = low_delay_note({"frames": 0, "auto": False}, {"ms": 65, "known": True}, extended=True)
        self.assertIn("65 ms", note)
        self.assertIn("Auto: 2", note)

    def test_one_frame_below_auto_and_auto_itself_are_quiet(self):
        self.assertEqual(low_delay_note({"frames": 1, "auto": False}, {"ms": 65, "known": True}, extended=True), "")
        self.assertEqual(low_delay_note({"frames": 2, "auto": True}, {"ms": 65, "known": True}, extended=True), "")
        self.assertEqual(low_delay_note({"frames": 0, "auto": False}, {"ms": 20, "known": True}, extended=True), "")

    def test_far_pings_and_plain_numbers(self):
        self.assertIn("Auto: 4", low_delay_note({"frames": 1, "auto": False}, 170, extended=True))
        self.assertIn("Auto: 2", low_delay_note({"frames": 0, "auto": False}, 120, extended=False))

    def test_unknown_ping_or_delay_says_nothing(self):
        for d, ms in (({"frames": 0, "auto": False}, {"ms": 65, "known": False}), ({"frames": 0, "auto": False}, None),
                      ({"frames": None, "auto": True}, {"ms": 65, "known": True}), (None, 65), ("0", 65),
                      ({"frames": 0, "auto": False}, True)):
            self.assertEqual(low_delay_note(d, ms, extended=True), "", (d, ms))

    def test_card_line_adds_it_without_a_tab(self):
        ui = ChallengesUI.__new__(ChallengesUI)
        line = ui.card_line({"delay": {"frames": 0, "auto": False}, "ping": {"ms": 65, "known": True}})
        self.assertIn("Input delay 0 (chosen by the challenger)", line)
        self.assertIn("Low for 65 ms", line)


if __name__ == "__main__":
    unittest.main()
