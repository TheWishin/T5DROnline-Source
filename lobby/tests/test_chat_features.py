"""1.2.0 launcher chat regression tests: fake widgets and notifications, no server, game, sound or window."""
import types
import unittest
from unittest import mock

import util  # noqa: F401 -- test path and disabled platform hooks
from t5lobby import chat, i18n, notify, proto, tk_tab


class CompletionTests(unittest.TestCase):
    def setUp(self):
        self.completion = chat.Completion()
        self.players = [{"id": "a", "name": "Mika"}, {"id": "b", "name": "Mi Ka!?"},
                        {"id": "c", "name": "[Miro]"}, {"id": "d", "name": "Zed"}]

    def test_tab_cycles_case_insensitive_current_server_names(self):
        result = self.completion.complete("hi @mi", 6, self.players)
        self.assertEqual(result, ("hi @Mi Ka!? ", 12))
        result = self.completion.complete(*result, self.players)
        self.assertEqual(result, ("hi @Mika ", 9))
        self.assertEqual(self.completion.complete(*result, self.players), ("hi @Mi Ka!? ", 12))

    def test_spaces_and_punctuation_are_part_of_a_name(self):
        self.assertEqual(self.completion.complete("@mi k", 5, self.players), ("@Mi Ka!? ", 9))
        self.assertEqual(self.completion.complete("@[", 2, self.players), ("@[Miro] ", 8))
        self.assertEqual(self.completion.complete("(@mik", 5, self.players), ("(@Mika ", 7))

    def test_completes_at_cursor_preserving_following_text(self):
        self.assertEqual(self.completion.complete("hi @mik see you", 7, self.players), ("hi @Mika see you", 8))
        self.assertEqual(self.completion.complete("@mik!", 4, self.players), ("@Mika !", 6))

    def test_unknown_names_and_email_keep_normal_tab_behavior(self):
        for text in ("hello", "mail@mi", "\u00e9@mi", "@@mi", "@unknown", "@mi no such name"):
            self.assertIsNone(self.completion.complete(text, len(text), self.players))

    def test_roster_update_invalidates_cycle_and_never_invents_names(self):
        result = self.completion.complete("@mi", 3, self.players)
        self.assertEqual(result[0], "@Mi Ka!? ")
        self.assertIsNone(self.completion.complete(*result, [{"id": "a", "name": "Mika"}]))
        self.assertEqual(self.completion.complete("@", 1, [{"name": "Known"}, {"name": "bad\nname"}]),
                         ("@Known ", 7))


class AuthoritativePresentationTests(unittest.TestCase):
    def setUp(self):
        self.tab = tk_tab.OnlineTab.__new__(tk_tab.OnlineTab)
        self.tab.client = types.SimpleNamespace(me={"id": "me", "name": "Tester"},
                                                mentions_ok=lambda: True, badges_ok=lambda: True,
                                                players=[{"id": "rival", "name": "Rival"}])
        self.event = {"t": "chat", "from": {"id": "rival", "name": "Rival"},
                      "text": "@Tester", "time": 10, "mentions": ["me"]}

    def test_badge_depends_only_on_server_field_and_negotiation(self):
        with mock.patch.object(i18n, "_cat", {}):
            self.assertEqual(chat.display_name({"name": "DEV [dev]"}), "DEV [dev]")
            self.assertFalse(chat.dev_badge({"name": "DEV", "badge": "admin"}))
            self.assertEqual(self.tab._player_badge({"name": "Anyone", "badge": "dev"}), "dev")
            self.assertFalse(proto.valid_name(chat.display_name({"name": "Anyone", "badge": "dev"})))
            self.tab.client.badges_ok = lambda: False
            self.assertEqual(self.tab._player_badge({"name": "Anyone", "badge": "dev"}), "")

    def test_text_and_forged_names_do_not_decide_who_is_mentioned(self):
        self.assertTrue(self.tab._chat_mentions_me(self.event))
        for mentions in ([], ["other"], "me", None):
            self.assertFalse(self.tab._chat_mentions_me(dict(self.event, mentions=mentions)))
        self.assertFalse(self.tab._chat_mentions_me(dict(self.event, **{"from": {"id": "me", "name": "Tester"}})))
        self.tab.client.mentions_ok = lambda: False
        self.assertFalse(self.tab._chat_mentions_me(self.event))

    def test_target_alert_uses_existing_setting_coalescing_and_duplicate_guard(self):
        played, flashed = mock.Mock(), mock.Mock()
        self.tab.notifier = notify.Notifier(play=played, flash=flashed, away=lambda: True, clock=lambda: 10)
        self.tab._notify_event(self.event)
        played.assert_called_once_with()
        flashed.assert_called_once_with()
        self.tab._notify_event(self.event)
        self.tab._notify_event(dict(self.event, time=11))
        played.assert_called_once_with()            # duplicate event and nearby chats coalesce
        self.tab.notifier.enabled = lambda: False
        self.tab.notifier.clock = lambda: 20
        self.tab._notify_event(dict(self.event, time=20))
        played.assert_called_once_with()

    def test_ordinary_own_and_unnegotiated_chat_do_not_alert(self):
        self.tab.notifier = mock.Mock()
        self.tab._notify_event(dict(self.event, mentions=[]))
        self.tab._notify_event(dict(self.event, **{"from": {"id": "me"}}))
        self.tab.client.mentions_ok = lambda: False
        self.tab._notify_event(self.event)
        self.tab.notifier.notify.assert_not_called()

    def test_chat_header_badge_is_separately_tagged_and_target_line_highlighted(self):
        self.tab.chat_log = mock.Mock()
        self.tab.view = types.SimpleNamespace(chat_name_tag=lambda _name, _mine: "chat_name_test")
        self.tab.chat_line("hello", sender="Rival", badge="dev", mentioned=True)
        inserts = [call.args for call in self.tab.chat_log.insert.call_args_list]
        self.assertEqual(inserts[0][:2], ("end", "Rival"))
        self.assertTrue({"chat_head", "chat_name_test"}.issubset(inserts[0][2]))
        self.assertTrue({"chat_head", "chat_dev"}.issubset(inserts[1][2]))
        self.assertIn("\u25c6", inserts[1][1])
        self.assertEqual(inserts[-1][:2], ("end", "hello\n"))
        self.assertTrue({"chat_msg", "chat_mention"}.issubset(inserts[-1][2]))
        self.assertIn(self.tab._mute_content_tag("Rival"), inserts[-1][2])
        self.tab.chat_log.insert.reset_mock()
        self.tab.chat_line("cleared", sender="Rival", badge="")
        self.assertEqual(self.tab.chat_log.insert.call_args_list[0].args[1], "Rival")
        self.assertFalse(any("chat_dev" in call.args[2] for call in self.tab.chat_log.insert.call_args_list))

    def test_completion_handler_is_gated_and_moves_cursor(self):
        self.tab.chat_var = mock.Mock()
        self.tab.chat_var.get.return_value = "@ri"
        widget = mock.Mock()
        widget.index.return_value = 3
        self.assertEqual(self.tab.complete_mention(types.SimpleNamespace(widget=widget)), "break")
        self.tab.chat_var.set.assert_called_once_with("@Rival ")
        widget.icursor.assert_called_once_with(7)
        self.tab.client.mentions_ok = lambda: False
        self.assertIsNone(self.tab.complete_mention(types.SimpleNamespace(widget=widget)))

    def test_profile_uses_raw_server_name_despite_badge_and_you_suffix(self):
        self.tab.tv_players = mock.Mock()
        self.tab.tv_players.selection.return_value = ["rival"]
        self.tab.show_profile = mock.Mock()
        self.tab._profile_of_selected()
        self.tab.show_profile.assert_called_once_with("Rival")
        self.tab.tv_players.item.assert_not_called()


if __name__ == "__main__":
    unittest.main()
