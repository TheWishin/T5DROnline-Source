"""Game-free launcher focus and consent regressions, with no windows or sockets."""
import types
import unittest
from unittest import mock

import util  # noqa: F401 -- adds the local lobby package to sys.path
from t5lobby import tk_tab
from t5lobby.client import LobbyClient
from t5lobby.proto import LobbyError


class IngameFocusTest(unittest.TestCase):
    def tab(self, active):
        tab = object.__new__(tk_tab.OnlineTab)
        tab._fronted = None
        tab.set_bar = None
        tab.driver = types.SimpleNamespace(ingame_ui_active=active, ticket=None)
        tab.parent = types.SimpleNamespace(master=None)
        tab.bring_forward = mock.Mock()
        return tab

    def test_only_acknowledged_healthy_prompt_keeps_launcher_behind(self):
        tab = self.tab(True)
        tab._come_forward(("result", "match1"))
        tab.bring_forward.assert_not_called()
        self.assertIsNone(tab._fronted)
        tab.driver.ingame_ui_active = False
        tab._come_forward(("result", "match1"))
        tab.bring_forward.assert_called_once_with(tab.parent)

    def test_manual_result_recovery_keeps_launcher_fallback(self):
        tab = self.tab(True)
        tab._come_forward(("ask", "match1"))
        tab.bring_forward.assert_called_once_with(tab.parent)

    def test_prompt_ack_wait_is_bounded_by_driver_fallback(self):
        tab = self.tab(False)
        tab.driver.ingame_ui_pending = True
        tab._come_forward(("result", "match1"))
        tab.bring_forward.assert_not_called()
        tab.driver.ingame_ui_pending = False
        tab._come_forward(("result", "match1"))
        tab.bring_forward.assert_called_once_with(tab.parent)

    def test_old_driver_and_disabled_overlay_keep_existing_focus(self):
        tab = self.tab(False)
        del tab.driver.ingame_ui_active
        tab._come_forward(("rematch", "match1"))
        tab.bring_forward.assert_called_once_with(tab.parent)

    def test_translated_texts_and_key_hints_go_to_the_driver(self):
        tab = self.tab(True)
        tab.app = types.SimpleNamespace(settings=types.SimpleNamespace(out_dir=None, env_overrides=lambda: {}))
        tab.driver.ingame_labels = mock.Mock()
        ev = {"t": "match_result", "status": "confirmed", "match": "match1",
              "rematch_ui": {"policy": "both_confirm", "actions": ["accept", "decline"]}}
        with mock.patch.dict("os.environ", {"PS3_CONTROLS": ""}):
            self.assertTrue(tab._offer_ingame_ui(ev))
        labels = tab.driver.ingame_labels.call_args.args[0]
        self.assertEqual(labels["title"], "Rematch?")
        self.assertEqual(labels["opp_accept"].format(name="Bob"), "Bob wants a rematch!")
        self.assertEqual(labels["auto"].format(seconds=3), "Rematch starts in 3 s unless you decline.")
        self.assertEqual((labels["key_confirm"], labels["key_cancel"]), ("Z", "X"))     # the default keyboard
        self.assertEqual(labels["result_void"], "No result")

    def test_other_events_change_nothing(self):
        tab = self.tab(True)
        tab.driver.ingame_labels = mock.Mock()
        self.assertFalse(tab._offer_ingame_ui({"t": "rematch", "match": "match1", "state": "waiting"}))
        tab.driver.ingame_labels.assert_not_called()

    def test_vote_in_the_game_answers_the_launcher_question(self):
        tab = self.tab(True)
        tab._notify_driver = mock.Mock()
        tab.view = mock.Mock()
        tab.hide_bar = mock.Mock()
        tab.status = mock.Mock()
        tab.cfg = {}
        tab.driver.last_fps = None
        tab.on_driver({"kind": "ingame_vote", "match": "match1", "accept": True})
        tab.view.rematch_sent.assert_called_once_with(True)
        tab.hide_bar.assert_called_once()


class RuleConsentTest(unittest.TestCase):
    def client(self):
        # No LobbyClient constructor/network worker: exercise request construction only.
        c = object.__new__(LobbyClient)
        c.ingame_rematch = c.auto_skip_after_round = True
        c.welcome = {"caps": ["ingame_rematch_v1", "auto_skip_after_round_v1"],
                     "features": ["casual_choice"], "ingame_rematch": {"v": 1}}
        c.connected, c.me = True, {"id": "p1"}
        c.casual_prefs = (None, "random")
        c.skip_after_round = False
        c._fire = mock.Mock()
        c._call = mock.Mock(return_value={"room": {"id": "r1"}})
        return c

    def test_skip_consent_is_explicit_and_survives_side_changes(self):
        c = self.client()
        c.set_casual_prefs(0, "random")
        self.assertIs(c._fire.call_args.args[0]["auto_skip_after_round"], False)
        c.set_auto_skip_after_round(True)
        c.set_casual_prefs(1, "random")
        self.assertIs(c._fire.call_args.args[0]["auto_skip_after_round"], True)
        self.assertEqual(c._fire.call_args.args[0]["side"], 1)

    def test_old_server_gets_no_new_preference_and_cannot_set_room_rule(self):
        c = self.client()
        c.welcome.pop("ingame_rematch")
        c.set_auto_skip_after_round(True)
        self.assertNotIn("auto_skip_after_round", c._fire.call_args.args[0])
        with self.assertRaises(LobbyError):
            c.room_rules("auto_unless_declined")
        c._call.assert_not_called()

    def test_server_owns_room_rule_change(self):
        c = self.client()
        c.room_rules("both_confirm", True)
        c._call.assert_called_once_with({"t": "room_rules", "rematch_policy": "both_confirm",
                                         "auto_skip_after_round": True})


if __name__ == "__main__":
    unittest.main()
