"""Casual FT launcher regressions using fake calls/widgets only: no sockets, server or game."""
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

import util  # noqa: F401 -- repository import path and safe test environment
from t5lobby import i18n, proto, sets
from t5lobby.client import LobbyClient
from t5lobby.match_driver import MatchDriver, hud_values


class Var:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class CasualSetClientTest(unittest.TestCase):
    def client(self, **kw):
        c = LobbyClient("127.0.0.1:1", util.BUILD, sets=True, **kw)
        c.welcome = {"features": ["casual_sets", "challenges2"], "caps": ["casual_sets", "sets"]}
        c._call = mock.Mock(return_value={"challenge": "c1", "room": {"id": "r1"}})
        return c

    def test_every_target_goes_to_challenge_room_and_invite(self):
        c = self.client()
        for n in proto.CASUAL_FIRST_TO:
            with self.subTest(first_to=n):
                c.send_challenge("p2", first_to=n)
                self.assertEqual(c._call.call_args.args[0]["first_to"], n)
                c.create_room(first_to=n)
                self.assertEqual(c._call.call_args.args[0]["first_to"], n)
                c.invite("Bob", first_to=n)
                self.assertEqual(c._call.call_args.args[0]["first_to"], n)

    def test_old_server_and_disabled_cap_get_original_single_game_messages(self):
        for c in (self.client(), self.client(casual_sets=False)):
            if c.casual_sets:
                c.welcome = {"features": ["challenges2"], "caps": ["sets"]}
            self.assertFalse(c.casual_sets_ok())
            c.send_challenge("p2", first_to=10)
            self.assertNotIn("first_to", c._call.call_args.args[0])
            c.create_room(first_to=10)
            self.assertNotIn("first_to", c._call.call_args.args[0])
            c.invite("Bob", first_to=10)
            self.assertNotIn("first_to", c._call.call_args.args[0])
        self.assertFalse(LobbyClient("127.0.0.1:1", util.BUILD, sets=False).casual_sets)

    def test_invalid_target_is_not_coerced_and_ranked_rooms_have_no_target(self):
        c = self.client()
        for bad in (True, False, "3", 3.0, 4, 0, -1, 11, None):
            with self.subTest(target=bad), self.assertRaises(proto.LobbyError):
                c.send_challenge("p2", first_to=bad)
        c.create_room(ranked=True, first_to=10)
        self.assertNotIn("first_to", c._call.call_args.args[0])
        c.invite("Bob", kind="room", first_to=10)
        self.assertNotIn("first_to", c._call.call_args.args[0])

    def test_friend_invite_uses_the_launcher_preference(self):
        c = self.client()
        c.casual_first_to = 5
        c.invite("Bob")
        self.assertEqual(c._call.call_args.args[0]["first_to"], 5)


class CasualSetPresentationTest(unittest.TestCase):
    def setUp(self):
        self.old_language = i18n.language()
        i18n.set_language("en")

    def tearDown(self):
        i18n.set_language(self.old_language)

    def info(self, **kw):
        return dict({"casual": True, "rated": False, "first_to": 5, "wins_needed": 5,
                     "best_of": 9, "wins": [2, 1], "number": 4, "state": "active"}, **kw)

    def test_score_target_countdown_and_perspective(self):
        s = self.info(next={"number": 4, "in": 4.2})
        self.assertEqual(sets.status_text(s, 1), "FT5 -- Set 1-2 -- game 4 of 9 -- starts in 5 s")
        self.assertEqual(sets.status_text(self.info(state="ended")), "FT5 -- Set 2-1")
        self.assertEqual(sets.status_text({"ranked": False, "wins": [2, 1]}), "")
        self.assertEqual(sets.status_text({"rated": True, "best_of": 3, "wins": [1, 0], "number": 2}),
                         "Set 1-0 -- game 2 of 3")

    def test_casual_result_has_no_rating_and_abandonment_keeps_games(self):
        won = {"casual": True, "status": "confirmed", "result": "win", "wins": [5, 3]}
        self.assertEqual(sets.result_text(won), "You won the set 5-3")
        won["result"] = "loss"
        self.assertEqual(sets.result_text(won), "You lost the set 5-3")
        self.assertEqual(sets.result_text({"casual": True, "status": "void", "wins": [2, 1]}),
                         "The casual set ended 2-1. Completed games keep their results; no rating change.")

    def test_challenge_target_is_visible_before_accepting_without_delay_metadata(self):
        from t5lobby.tk_challenges import ChallengesUI

        ui = ChallengesUI.__new__(ChallengesUI)
        self.assertEqual(ui.card_line({"first_to": 10}), "FT10")
        self.assertEqual(ui.card_line({"first_to": 2, "delay": {"frames": 1, "auto": False}}),
                         "FT2 -- Input delay 1 (chosen by the challenger)")
        self.assertEqual(ui.card_line({}), "")

    def test_room_summary_displays_requested_target_and_effective_table_score(self):
        from t5lobby.tk_rooms import RoomsUI

        ui = RoomsUI(SimpleNamespace(client=SimpleNamespace(me={"id": "p1"})))
        room = {"name": "Friends", "first_to": 10, "size": 3, "rotation": "winner", "owner_id": "p1",
                "players": [{"id": "p1", "name": "Alice"}, {"id": "p2", "name": "Bob"}],
                "playing": ["p1", "p2"], "line": ["p1", "p2"], "set": self.info()}
        text = ui.summary(room)
        self.assertIn("FT10", text)
        self.assertIn("FT5 -- Set 2-1", text)
        self.assertIn("Playing: Alice vs Bob", text)
        self.assertIn("FT10", ui.list_state(room))

    def test_selector_saves_preference_and_new_clients_use_it(self):
        from t5lobby.tk_casual import CasualUI

        c = SimpleNamespace(set_casual_prefs=mock.Mock())
        tab = SimpleNamespace(client=c, cfg={}, _save_cfg=mock.Mock())
        ui = CasualUI.__new__(CasualUI)
        ui.tab, ui.side, ui.stage, ui.set_var = tab, None, "random", Var("FT3")
        ui.on_set_change()
        self.assertEqual((ui.first_to, c.casual_first_to, tab.cfg["casual_first_to"]), (3, 3, 3))
        ui.skip_var = Var(True)
        c2 = SimpleNamespace(set_casual_prefs=mock.Mock(), set_auto_skip_after_round=mock.Mock())
        ui.new_client(c2)
        self.assertEqual(c2.casual_first_to, 3)
        c2.set_casual_prefs.assert_called_once_with(None, "random")
        c2.set_auto_skip_after_round.assert_called_once_with(True)

    def test_driver_automatically_acknowledges_next_casual_game(self):
        calls = []
        client = SimpleNamespace(set_next=lambda *a: calls.append(a))
        directory = tempfile.TemporaryDirectory(dir=util.HERE)
        self.addCleanup(directory.cleanup)
        drv = MatchDriver(client, lambda env: self.fail("must not launch a game"), directory.name,
                          table=object(), mode="process", ingame_rematch=False)
        drv.connected_game = lambda: True
        drv.note = mock.Mock()
        ev = {"t": "match_result", "match": "m1", "set": self.info(next={"in": 5}), "rematch_window": 0}
        drv.on_event(ev)
        self.assertEqual(calls, [("m1", True)])
        drv.note.assert_called_once_with("set_next", match="m1", set=ev["set"])

    def test_between_game_leave_does_not_describe_ranked_loss(self):
        from t5lobby.tk_tab import OnlineTab

        tab = OnlineTab.__new__(OnlineTab)
        tab.set_bar, tab.lag = (self.info(), 0, 123), None
        tab.show_bar = mock.Mock()
        tab._set_bar_text = lambda: "FT5 -- Set 2-1"
        tab._show_set_bar()
        self.assertEqual(tab.show_bar.call_args.args[1][0][0], "Leave set")
        tab.ask_yes_no = mock.Mock(return_value=True)
        tab.parent, tab.client = None, SimpleNamespace(leave_set=mock.Mock())
        tab.hide_bar, tab.call = mock.Mock(), mock.Mock()
        tab._leave_set()
        title, question = tab.ask_yes_no.call_args.args
        self.assertEqual(title, "Leave the casual set")
        self.assertIn("Completed games keep their results", question)
        self.assertNotIn("counts as losing", question)
        self.assertIsNone(tab.set_bar)

    def test_both_sides_get_same_hud_score_without_character_changes(self):
        ev = {"players": [{"name": "Alice", "tier": 11}, {"name": "Bob", "tier": 4}], "set": self.info()}
        self.assertEqual(hud_values(ev), (["Alice [2]", "Bob [1]"], [11, 4]))


if __name__ == "__main__":
    unittest.main()
