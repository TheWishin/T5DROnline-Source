"""Terminal lobby events mapped to a timed runtime notice and a parked game, with fakes only."""
import tempfile
import types
import unittest
from unittest import mock

import util  # noqa: F401
from t5lobby.ingame_ui import IngameUI
from t5lobby.match_driver import MatchDriver, RETURN_SECONDS, OPPONENT_LEFT, MATCH_ENDED
from t5lobby.tk_tab import OnlineTab


class MatchReturnTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.now = 100.0
        self.clock = mock.patch("t5lobby.match_driver.time.monotonic", side_effect=lambda: self.now)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.client = types.SimpleNamespace(match=None)
        self.driver = MatchDriver(self.client, None, self.tmp.name, mode="persistent", ingame_rematch=False)
        self.driver.game = types.SimpleNamespace(running=lambda: True, proc=types.SimpleNamespace(pid=123))
        self.driver.ctl = mock.Mock()
        self.driver.ui = IngameUI(self.tmp.name, "m1", clock=lambda: self.now, worker=False)
        self.addCleanup(self.driver.ui.close)
        self.driver.session = "m1"

    def tick(self, seconds):
        self.now += seconds
        self.driver._watch_return()

    def notes(self):
        out = []
        while not self.driver.notes.empty():
            out.append(self.driver.notes.get_nowait())
        return out

    def test_quit_disconnect_forfeit_and_peer_loss_get_english_notice(self):
        for event in (
            {"t": "match_result", "match": "m1", "reason": "quit", "blame": "opponent"},
            {"t": "match_result", "match": "m1", "reason": "disconnect"},
            {"t": "match_result", "match": "m1", "status": "forfeit"},
            {"t": "match_result", "match": "m1", "reason": "peer_timeout"},
            {"t": "set_end", "reason": "left", "by": "opponent"},
        ):
            with self.subTest(event=event):
                self.driver._cancel_return()
                self.driver.on_event(event)
                doc = self.driver.ui.snapshot()
                self.assertEqual((doc["kind"], doc["body"], doc["allowed"]), ("notice", OPPONENT_LEFT, []))
                self.notes()
                self.tick(RETURN_SECONDS - 0.1)
                self.assertEqual(self.notes(), [])
                self.tick(0.1)
                self.assertEqual([n["kind"] for n in self.notes()], ["return_to_lobby"])
                self.assertEqual(self.driver.ui.snapshot()["kind"], "hidden")
                self.assertTrue(self.driver.game_running())

    def test_normal_end_without_next_game_returns_but_next_game_and_rematch_wait(self):
        self.driver.on_event({"t": "match_result", "match": "m1", "status": "confirmed"})
        self.assertEqual(self.driver.ui.snapshot()["body"], MATCH_ENDED)
        self.driver._cancel_return()
        self.client.set_next = mock.Mock()
        self.driver.on_event({"t": "match_result", "match": "m1", "set": {"rated": True, "next": {"in": 3}}})
        self.assertFalse(self.driver.returning_to_lobby)
        self.driver.on_event({"t": "match_result", "match": "m1", "rematch_window": 10})
        self.assertFalse(self.driver.returning_to_lobby)
        self.assertEqual(self.driver._hold_until, self.now + 10)

    def test_duplicate_set_result_and_our_own_quit(self):
        self.driver.on_event({"t": "set_end", "reason": "left", "by": "opponent"})
        deadline = self.driver._return[1]
        self.tick(2)
        self.driver.on_event({"t": "match_result", "match": "m1", "status": "forfeit"})
        self.assertEqual(self.driver._return[1], deadline)
        self.driver._cancel_return()
        self.driver.on_event({"t": "match_result", "match": "m1", "reason": "quit", "blame": "you"})
        self.assertEqual(self.driver.ui.snapshot()["body"], MATCH_ENDED)

    def test_committed_next_match_cancels_pending_return(self):
        self.driver.on_event({"t": "match_result", "match": "m1", "reason": "quit"})
        self.driver.on_event({"t": "match_found", "match": "m2", "keep": True})
        self.notes()
        self.tick(10)
        self.assertFalse(self.driver.returning_to_lobby)
        self.assertEqual(self.notes(), [])

    def test_legacy_rematch_decline_and_expiry_use_the_same_return(self):
        for state in ("declined", "expired"):
            with self.subTest(state=state):
                self.driver._cancel_return()
                self.driver.on_event({"t": "rematch", "match": "m1", "state": state})
                self.assertTrue(self.driver.returning_to_lobby)
                self.assertEqual(self.driver.ui.snapshot()["body"], MATCH_ENDED)

    def test_launcher_hides_and_keeps_persistent_game_without_stealing_focus(self):
        for foreground in (False, True):
            with self.subTest(foreground=foreground):
                tab = object.__new__(OnlineTab)
                tab.driver = self.driver
                tab.parent = types.SimpleNamespace(master=None)
                tab.bring_forward = mock.Mock()
                with mock.patch("t5lobby.tk_tab.winfront.game_in_front", return_value=foreground), \
                        mock.patch("t5lobby.tk_tab.winfront.hide_game_window", return_value=True) as hide:
                    tab._return_to_lobby("m1")
                hide.assert_called_once_with(123)
                self.assertEqual(tab.bring_forward.call_count, int(foreground))
                self.assertTrue(self.driver.game_running())

    def test_process_game_is_closed_after_capturing_its_foreground(self):
        self.driver.mode = "process"
        self.driver.stop_game = mock.Mock()
        tab = object.__new__(OnlineTab)
        tab.driver = self.driver
        tab.parent = types.SimpleNamespace(master=None)
        tab.bring_forward = mock.Mock()
        with mock.patch("t5lobby.tk_tab.winfront.game_in_front", return_value=True), \
                mock.patch("t5lobby.tk_tab.winfront.hide_game_window", return_value=True):
            tab._return_to_lobby("m1")
        self.driver.stop_game.assert_called_once()
        tab.bring_forward.assert_called_once_with(tab.parent)

    def test_queued_return_notice_preserves_set_result_but_other_statuses_still_show(self):
        self.driver.on_event({"t": "set_end", "reason": "decided"})
        notice = next(n for n in self.notes() if n["kind"] == "status")
        self.assertTrue(notice["return_notice"])
        tab = object.__new__(OnlineTab)
        tab.driver = None
        tab.status = mock.Mock()
        tab._notify_driver = mock.Mock()
        tab._set_actions = mock.Mock()
        for result in (None, {"set_end": None}, {"set_end": {"games": 2}}):
            for is_return in (False, True):
                with self.subTest(result=result, return_notice=is_return):
                    tab.view = types.SimpleNamespace(result_info=result, after_driver=mock.Mock())
                    tab.status.reset_mock()
                    tab.on_driver(dict(notice, return_notice=is_return))
                    self.assertEqual(tab.status.call_count, int(not (is_return and result and result.get("set_end"))))


if __name__ == "__main__":
    unittest.main()
