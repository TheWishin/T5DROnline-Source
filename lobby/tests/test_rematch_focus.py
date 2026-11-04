"""Rematch queue ordering and notification focus rules, using fake windows only.

The tab drains lobby events before driver notes. An offered rematch can therefore
reach on_driver after match_start has already hidden the in-game question.
"""
import queue
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import util  # noqa: F401 -- local lobby package, real notifications disabled
from test_driver_ingame_ui import Client, Game, LABELS, result
from t5lobby import notify, tk_tab, winfront
from t5lobby.ingame_ui import IngameUI
from t5lobby.match_driver import GameLog, MatchDriver


class RematchFocusTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.now = 100.0
        self.client = Client()
        self.client.set_next = mock.Mock()
        self.driver = MatchDriver(self.client, mock.Mock(side_effect=AssertionError("no new game")),
                                  directory.name, mode="persistent", ingame_rematch=False)
        self.driver.game = Game()
        self.driver.game.proc = SimpleNamespace(pid=4242)
        self.driver.game_state = "over"
        self.driver.glog = GameLog(None)
        self.driver.glog.connected = True
        self.driver.match_ev = {"opponent": {"name": "Bob"}}
        self.driver.session_ticket = SimpleNamespace(slot=0, opponent={"name": "Bob"})
        self.driver.ui = IngameUI(directory.name, "m1", clock=lambda: self.now, worker=False)
        self.addCleanup(self.driver.ui.close)
        self.driver.ingame_labels(LABELS)
        clock = mock.patch("t5lobby.match_driver.time.monotonic", side_effect=lambda: self.now)
        clock.start()
        self.addCleanup(clock.stop)

        tab = self.tab = object.__new__(tk_tab.OnlineTab)
        tab.driver = self.driver
        tab.app = SimpleNamespace(game=self.driver.game, settings={})
        tab.parent = SimpleNamespace(master=None,
                                     winfo_toplevel=lambda: SimpleNamespace(state=lambda: "normal"))
        tab.game_in_front = mock.Mock(return_value=True)
        tab.launcher_in_front = mock.Mock(return_value=False)
        tab._tab_viewable = lambda: True
        tab.bring_forward = mock.Mock()
        tab.bring_game_forward = mock.Mock()
        tab.new_window = mock.Mock(side_effect=AssertionError("no popup window"))
        tab._fronted = tab._game_fronted = tab.set_bar = None
        tab._challenge_rung = {}
        tab.cfg = {}
        tab.view = mock.Mock()
        tab.casual = SimpleNamespace(offer=lambda note: ("", []))
        tab.show_bar = mock.Mock()
        tab.hide_bar = mock.Mock()
        tab.status = mock.Mock()
        tab._set_actions = mock.Mock()
        self.play = mock.Mock()
        self.flash = mock.Mock()
        tab.notifier = notify.Notifier(enabled=lambda: True, away=tab._notify_away,
                                       play=self.play, flash=self.flash, clock=lambda: self.now)

    def drain_notes(self):
        kinds = []
        while True:
            try:
                note = self.driver.notes.get_nowait()
            except queue.Empty:
                return kinds
            kinds.append(note["kind"])
            self.tab.on_driver(note)

    def offer(self, **kwargs):
        self.driver.ingame_rematch = True
        ev = result(**kwargs)
        self.driver.on_event(ev)
        self.driver.ui.ready_at = self.now
        self.driver.ui.ready_revision = self.driver.ui.document["rev"]
        self.driver._watch_ingame_ui()
        self.assertTrue(self.driver.ingame_ui_active)
        self.tab._come_forward(("result", "m1"))
        return ev

    def assert_no_attention(self):
        self.tab.bring_forward.assert_not_called()
        self.tab.bring_game_forward.assert_not_called()
        self.tab.new_window.assert_not_called()
        self.flash.assert_not_called()
        self.play.assert_not_called()

    def test_ingame_accept_and_deferred_offer_never_raise_a_window(self):
        self.offer()
        self.driver.on_event({"t": "rematch", "match": "m1", "state": "offered", "from": {"name": "Bob"}})
        self.driver.rematch("m1", True)
        self.driver.on_event({"t": "rematch", "match": "m1", "state": "accepted"})
        self.driver.on_event({"t": "match_found", "match": "m2", "keep": True, "rematch_of": "m1"})
        self.driver.on_event({"t": "match_start", "match": "m2", "continue": True,
                              "opponent": {"name": "Bob"}, "fight": {}})
        # All those lobby events precede driver notes in OnlineTab._tick.
        self.assertFalse(self.driver.ingame_ui_active)
        self.assertEqual(self.driver.game_state, "over")
        self.assertIn("rematch_offer", self.drain_notes())
        for state in ("pick", "loading", "fight"):
            self.tab.on_driver({"kind": "game_state", "match": "m2", "state": state})
        self.assertEqual(self.client.calls, [("rematch", "m1", True, True)])
        self.assert_no_attention()

    def test_next_set_game_and_stale_offer_remain_behind_game(self):
        self.driver.on_event(result(rematch_ui=None, set={"casual": True, "next": {"in": 3}}))
        self.assertEqual(self.client.set_next.call_args.args, ("m1", True))
        self.driver.on_event({"t": "match_start", "match": "m2", "continue": True,
                              "opponent": {"name": "Bob"}, "fight": {}})
        self.assertIn("set_next", self.drain_notes())
        self.tab.on_driver({"kind": "rematch_offer", "match": "m1", "opponent": "Bob"})
        self.tab.on_driver({"kind": "game_state", "match": "m2", "state": "loading"})
        self.assert_no_attention()

    def test_overlay_fallback_cannot_activate_launcher_while_game_runs(self):
        for active in (False, True):
            with self.subTest(game_foreground=active):
                self.tab.game_in_front.return_value = active
                self.tab.on_driver({"kind": "ingame_ui_fallback", "match": "m1"})
                self.tab._come_forward(("ask", "m1"))
        self.assert_no_attention()

    def test_match_challenge_and_rematch_notifications_are_quiet_in_game(self):
        self.tab.notifier.notify = mock.Mock(wraps=self.tab.notifier.notify)
        for ev in ({"t": "match_found", "match": "m2", "ready_check": True},
                   {"t": "challenged", "challenge": "c1", "from": {"id": 2, "name": "Bob"}},
                   {"t": "invited", "invite": "i1"}):
            self.tab._notify_event(ev)
            self.now += 10
        self.tab._notify_driver({"kind": "rematch_offer", "match": "m1"})
        self.assertEqual([call.args[0] for call in self.tab.notifier.notify.call_args_list],
                         [notify.MATCH, notify.CHALLENGE, notify.INVITE])
        with mock.patch.object(tk_tab.notify, "flash_window") as flash_window:
            self.assertFalse(self.tab._notify_flash())
            flash_window.assert_not_called()
        self.assert_no_attention()

    def test_background_notification_flashes_without_raising(self):
        self.tab.game_in_front.return_value = False
        self.tab._notify_event({"t": "match_found", "match": "m2", "ready_check": True})
        self.flash.assert_called_once_with()
        self.tab.bring_forward.assert_not_called()
        self.tab.bring_game_forward.assert_not_called()

    def test_background_challenge_plays_its_sound_and_flashes_without_raising(self):
        self.tab.game_in_front.return_value = False
        challenge = self.tab.notifier.challenge = mock.Mock(return_value=True)
        self.tab._notify_event({"t": "challenged", "challenge": "c1", "from": {"id": 2, "name": "Bob"}})
        challenge.assert_called_once_with()
        self.flash.assert_called_once_with()
        self.assertEqual(self.tab._challenge_rung, {"bob": self.now})
        self.play.assert_not_called()
        self.tab.bring_forward.assert_not_called()
        self.tab.bring_game_forward.assert_not_called()

    def test_game_foreground_wins_over_stale_launcher_foreground_check(self):
        self.tab.launcher_in_front.return_value = True
        self.tab.on_driver({"kind": "game_state", "match": "m2", "state": "loading"})
        self.assert_no_attention()


    def test_parked_game_is_revealed_without_activating_over_another_app(self):
        self.tab.game_in_front.return_value = False
        with mock.patch.object(winfront, "show_game_window") as show:
            self.tab._game_forward(("loading", "m2"))
            self.tab._game_forward(("loading", "m2"))
        show.assert_called_once_with(4242)
        self.assert_no_attention()

    def test_parked_game_takes_focus_when_launcher_is_foreground(self):
        self.tab.game_in_front.return_value = False
        self.tab.launcher_in_front.return_value = True
        with mock.patch.object(winfront, "show_game_window") as show:
            self.tab._game_forward(("loading", "m2"))
        show.assert_called_once_with(4242)
        self.tab.bring_game_forward.assert_called_once_with(4242)
        self.tab.bring_forward.assert_not_called()

    def test_foreground_game_and_background_setting_do_not_restore_game(self):
        for foreground, background in ((True, False), (False, True)):
            with self.subTest(foreground=foreground, background=background):
                self.tab._game_fronted = None
                self.tab.game_in_front.return_value = foreground
                self.tab.launcher_in_front.return_value = True
                self.tab.app.settings["background"] = background
                with mock.patch.object(winfront, "show_game_window") as show:
                    self.tab._game_forward(("loading", "m2"))
                show.assert_not_called()
                self.assert_no_attention()


class ForegroundProcessTest(unittest.TestCase):
    def user32(self, foreground_pid, hwnd=0x1234):
        # A strict fake has no activation, ShowWindow, or FlashWindow methods.
        user32 = mock.Mock(spec=["GetForegroundWindow", "GetWindowThreadProcessId"])
        user32.GetForegroundWindow.return_value = hwnd

        def get_pid(window, pid):
            self.assertEqual(window, hwnd)
            pid._obj.value = foreground_pid
            return 17
        user32.GetWindowThreadProcessId.side_effect = get_pid
        return user32

    def test_process_check_is_read_only_and_compares_process_not_window_class(self):
        for owner, expected in ((4242, True), (99, False)):
            with self.subTest(owner=owner):
                user32 = self.user32(owner)
                with mock.patch.object(winfront.os, "name", "nt"), \
                        mock.patch.object(winfront.ctypes, "WinDLL", return_value=user32, create=True):
                    self.assertIs(winfront.process_in_front(4242), expected)
                self.assertEqual([call[0] for call in user32.method_calls],
                                 ["GetForegroundWindow", "GetWindowThreadProcessId"])

    def test_no_foreground_window_or_pid_is_false(self):
        user32 = self.user32(4242, hwnd=0)
        with mock.patch.object(winfront.os, "name", "nt"), \
                mock.patch.object(winfront.ctypes, "WinDLL", return_value=user32, create=True):
            self.assertFalse(winfront.process_in_front(4242))
            self.assertFalse(winfront.process_in_front(None))
        user32.GetWindowThreadProcessId.assert_not_called()


if __name__ == "__main__":
    unittest.main()
