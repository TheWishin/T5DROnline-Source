"""Client audit regressions: in-memory UI channels, no game, files or sockets."""
import os
import queue
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from t5lobby.ingame_ui import IngameUI
from t5lobby.match_driver import MatchDriver, _Continued


class StaleUIExpiryTest(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.driver = MatchDriver.__new__(MatchDriver)
        self.driver.ui = IngameUI(os.path.dirname(__file__), "session", clock=lambda: self.now, worker=False)
        self.driver.game = SimpleNamespace(running=lambda: True)
        self.driver.notes = queue.Queue()
        self.driver._ui_completions = queue.Queue()
        self.driver._ui_auto_at = None
        self.driver._ui_auto_delay = None
        self.driver._ui_room_next_at = None
        self.driver._ui_was_active = False
        self.driver._ui_offered_at = self.now
        self.driver._set_over = mock.Mock()
        self.clock_patch = mock.patch("t5lobby.match_driver.time.monotonic", side_effect=lambda: self.now)
        self.clock_patch.start()
        self.addCleanup(self.clock_patch.stop)

    def expire(self):
        self.driver.ui.offer("old", "rematch", ["accept"], 20)
        self.driver.ui.hide()
        # Model the worker's notification before the UI thread drains it.
        self.driver.ui.events.put(("expired", None))

    def test_old_expiry_cannot_cancel_replacement_ready_prompt(self):
        self.expire()
        channel = self.driver.ui
        channel.offer("new", "ready", ["ready", "decline"], 15)
        channel.ready_at = self.now
        channel.ready_revision = channel.document["rev"]
        self.driver._watch_ingame_ui()
        self.driver._set_over.assert_not_called()
        self.assertEqual(channel.document["kind"], "ready")
        notes = list(self.driver.notes.queue)
        self.assertNotIn("ingame_ui_fallback", [note["kind"] for note in notes])

    def test_old_expiry_after_match_start_does_not_emit_fallback(self):
        self.expire()
        self.driver._ui_offered_at = None  # match_start has hidden and released the menu
        self.driver._watch_ingame_ui()
        self.driver._set_over.assert_not_called()
        self.assertTrue(self.driver.notes.empty())

    def test_current_expiry_still_releases_session_and_falls_back(self):
        self.expire()
        self.driver._watch_ingame_ui()
        self.driver._set_over.assert_called_once_with()
        self.assertIn("ingame_ui_fallback", [note["kind"] for note in self.driver.notes.queue])


class ContinuedDelayTest(unittest.TestCase):
    def environment(self, fixed, event):
        previous = SimpleNamespace(input_delay=fixed, game_env=lambda result_file=None:
                                   {"T5_RB_NET_DELAY": str(fixed)} if fixed is not None else {})
        ticket = _Continued("next", event, previous)
        driver = MatchDriver.__new__(MatchDriver)
        driver.result_path = None
        driver.fight_line = lambda ev: None
        driver.fight_path = None
        driver.always_left = None
        driver.screen_side = None
        driver.extra_env = {}
        driver.ui = None
        driver.input_delay = "0"
        driver.client = SimpleNamespace(live_dir=None)
        return driver.match_env(event, ticket)

    def test_ranked_continuation_keeps_server_delay_over_local_preference(self):
        self.assertEqual(self.environment(2, {"ranked": True})["T5_RB_NET_DELAY"], "2")

    def test_continuation_uses_current_server_delay_when_provided(self):
        self.assertEqual(self.environment(2, {"ranked": True, "input_delay": 3})["T5_RB_NET_DELAY"], "3")

    def test_casual_continuation_still_uses_local_preference(self):
        self.assertEqual(self.environment(None, {})["T5_RB_NET_DELAY"], "0")

if __name__ == "__main__":
    unittest.main()
