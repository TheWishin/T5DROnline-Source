"""Pending invite visibility follows personal mutes without Tk or a server."""
import unittest
from unittest.mock import Mock

from test_mute_lobby_ui import controller


class PendingInviteMuteTest(unittest.TestCase):
    def tab(self):
        tab, _namespace = controller()
        tab.invite = {"t": "invited", "invite": "pending", "from": {"name": "Rival"}}
        tab.challenge, tab.match = None, None
        tab.hide_bar = Mock()
        tab.client.is_muted.side_effect = lambda name: name == "Rival"
        return tab

    def test_muting_sender_removes_already_visible_invite_and_actions(self):
        tab = self.tab()
        tab._mutes_changed()
        self.assertIsNone(tab.invite)
        tab.hide_bar.assert_called_once_with()
        tab.call.assert_not_called()

    def test_muting_inviter_keeps_another_challenge_or_match_bar(self):
        for state in ("challenge", "match"):
            with self.subTest(state=state):
                tab = self.tab()
                setattr(tab, state, "other")
                tab._mutes_changed()
                self.assertIsNone(tab.invite)
                tab.hide_bar.assert_not_called()

    def test_an_unmuted_invite_stays_visible(self):
        tab = self.tab()
        tab.client.is_muted.side_effect = lambda _name: False
        original = tab.invite
        tab._mutes_changed()
        self.assertIs(tab.invite, original)
        tab.hide_bar.assert_not_called()


if __name__ == "__main__":
    unittest.main()
