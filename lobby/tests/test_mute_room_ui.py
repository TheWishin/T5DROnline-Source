"""Offline room member mute controls: no Tk root, socket, server or game."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import util  # noqa: F401 -- establish the lobby package import path only
from t5lobby import tk_rooms
from t5lobby.tk_rooms import RoomsUI


class RoomMuteControls(unittest.TestCase):
    def setUp(self):
        self.room = {"id": "room", "players": [
            {"id": "me", "name": "Tester"},
            {"id": "peer", "name": "Rival", "badge": "dev"}]}
        self.muted = set()
        self.client = SimpleNamespace(
            me={"id": "me", "name": "Tester", "status": "room"}, my_room=self.room,
            is_muted=lambda name: name.lower() in self.muted, private_chat_ok=lambda: True)
        self.tab = SimpleNamespace(client=self.client, toggle_mute=Mock(),
                                   private_chat=SimpleNamespace(show=Mock()))
        self.ui = RoomsUI(self.tab)
        self.ui.px = lambda value: value
        self.ui.members_frame = Mock()
        self.ui.members_frame.winfo_children.return_value = []

    def test_every_other_member_has_direct_mute_and_message_buttons(self):
        with patch.object(tk_rooms.ttk, "Label") as label, \
                patch.object(tk_rooms.ttk, "Button") as button:
            self.ui._refresh_members(self.room)
            label.assert_called_once_with(self.ui.members_frame, text="Rival", style="Card.Small.TLabel")
            self.assertEqual([call.kwargs["text"] for call in button.call_args_list],
                             ["Mute", "Message player"])
            button.call_args_list[0].kwargs["command"]()
            self.tab.toggle_mute.assert_called_once_with("Rival")
            button.call_args_list[1].kwargs["command"]()
            self.tab.private_chat.show.assert_called_once_with("Rival")

    def test_mute_state_updates_without_room_membership_change(self):
        with patch.object(tk_rooms.ttk, "Label"), patch.object(tk_rooms.ttk, "Button") as button:
            self.ui._refresh_members(self.room)
            self.muted.add("rival")
            self.ui._refresh_members(self.room)
            self.assertEqual(button.call_args_list[2].kwargs["text"], "Unmute")
            self.assertEqual(button.call_count, 4)
            self.ui._refresh_members(self.room)
            self.assertEqual(button.call_count, 4)  # unchanged rows keep keyboard focus

    def test_stale_room_member_controls_do_not_act(self):
        self.room["players"] = self.room["players"][:1]
        self.ui.toggle_mute("Rival")
        self.ui.message_player("Rival")
        self.tab.toggle_mute.assert_not_called()
        self.tab.private_chat.show.assert_not_called()
        self.client.my_room = None
        self.ui.toggle_mute("Rival")
        self.tab.toggle_mute.assert_not_called()

    def test_private_entry_is_disabled_on_older_server(self):
        self.client.private_chat_ok = lambda: False
        with patch.object(tk_rooms.ttk, "Label"), patch.object(tk_rooms.ttk, "Button") as button:
            self.ui._refresh_members(self.room)
            self.assertEqual(button.call_args_list[1].kwargs["state"], "disabled")
            button.call_args_list[1].kwargs["command"]()
            self.tab.private_chat.show.assert_not_called()

    def test_muted_list_event_refreshes_room_buttons(self):
        with patch.object(self.ui, "refresh") as refresh:
            self.ui.on_event({"t": "mutes"})
            refresh.assert_called_once_with()

    def test_leaving_room_clears_old_controls(self):
        old = Mock()
        self.ui.members_frame.winfo_children.return_value = [old]
        self.ui._refresh_members(None)
        old.destroy.assert_called_once_with()
        self.assertEqual(self.ui._members_shown, (None, ()))


if __name__ == "__main__":
    unittest.main()
