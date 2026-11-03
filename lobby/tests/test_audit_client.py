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
    """The channel's own expiry (worker) never decides anything: the driver's question ends by its countdown and the
    lobby's verdict, once (docs/REMATCH_1.2.0.md)."""

    def setUp(self):
        self.now = 100.0
        self.clock_patch = mock.patch("t5lobby.match_driver.time.monotonic", side_effect=lambda: self.now)
        self.clock_patch.start()
        self.addCleanup(self.clock_patch.stop)
        self.driver = MatchDriver.__new__(MatchDriver)
        self.driver.ui = IngameUI(os.path.dirname(__file__), "session", clock=lambda: self.now, worker=False)
        self.driver.game = SimpleNamespace(running=lambda: True)
        self.driver.glog = None
        self.driver.notes = queue.Queue()
        self.driver._ui_completions = queue.Queue()
        self.driver._ui_labels = {}
        self.driver._ui_was_active = False
        self.driver._rq = None
        self.driver.match_ev = {"opponent": {"name": "Bob"}}
        self.driver.session_ticket = None
        self.driver.rematch_sent, self.driver.rematch_declined = set(), set()
        self.driver.mode = "persistent"
        self.driver._set_over = mock.Mock()

    def offer(self, mid):
        ev = {"t": "match_result", "match": mid, "status": "confirmed", "rematch_window": 10,
              "rematch_ui": {"v": 1, "kind": "rematch", "policy": "both_confirm", "timeout": 10,
                             "actions": ["accept", "decline"]}}
        self.assertFalse(self.driver.offer_ingame_ui(ev))      # (not shown yet: the game acknowledges it first)
        self.driver.ui.ready_at = self.now
        self.driver.ui.ready_revision = self.driver.ui.document["rev"]

    def stale_expiry(self):
        self.driver.ui.events.put(("expired", None))

    def test_old_expiry_cannot_cancel_a_newer_question(self):
        self.offer("new")
        self.stale_expiry()
        self.driver._watch_ingame_ui()
        self.driver._set_over.assert_not_called()
        self.assertEqual(self.driver.ui.document["kind"], "rematch")
        self.assertNotIn("ingame_ui_fallback", [n["kind"] for n in self.driver.notes.queue])

    def test_old_expiry_without_a_question_does_nothing(self):
        self.stale_expiry()
        self.driver._watch_ingame_ui()
        self.driver._set_over.assert_not_called()
        self.assertTrue(self.driver.notes.empty())

    def test_current_question_running_out_releases_session_and_falls_back(self):
        self.offer("m1")
        self.driver._watch_ingame_ui()
        self.now += 10.1
        self.driver.ui.ready_at = self.now
        self.driver._watch_ingame_ui()                     # "time is up" for a moment
        self.driver._set_over.assert_not_called()
        self.now += 3.1
        self.driver.ui.ready_at = self.now
        self.driver._watch_ingame_ui()
        self.driver._set_over.assert_called_once_with()
        self.assertIn("ingame_ui_fallback", [n["kind"] for n in self.driver.notes.queue])


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
