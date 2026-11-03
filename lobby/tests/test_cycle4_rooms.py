"""Room moderation controls retain their opening room and session; no Tk or server."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import util  # noqa: F401 -- local package path only; no server helper is invoked
from t5lobby import tk_rooms


class Variable:
    def __init__(self, _master, value=None):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value

    def trace_add(self, *_args):
        pass


class RoomModerationOwnershipTest(unittest.TestCase):
    def window(self):
        room = {"id": "original", "players": [{"id": "peer", "name": "Peer"}],
                "lock": "password", "guesses": {"wrong": 1, "networks": 1}}
        client = SimpleNamespace(my_room=room, me={"id": "host", "status": "room"})
        tab = SimpleNamespace(client=client, view=SimpleNamespace(px=lambda value: value, body=Mock()),
                              status=Mock())
        ui = SimpleNamespace(tab=tab, close_window=Mock(), kick=Mock(), bar_guessers=Mock())
        window = Mock()

        def button(*_args, **kwargs):
            widget = Mock()
            widget.command = kwargs.get("command")
            return widget

        with patch.object(tk_rooms, "_window", return_value=(window, Mock())), \
                patch.object(tk_rooms, "_room_rules_supported", return_value=False), \
                patch.object(tk_rooms.tk, "StringVar", Variable), \
                patch.object(tk_rooms.tk, "IntVar", Variable), \
                patch.object(tk_rooms.tk, "Listbox") as listbox, \
                patch.object(tk_rooms.ttk, "Label"), patch.object(tk_rooms.ttk, "Entry"), \
                patch.object(tk_rooms.ttk, "Combobox"), patch.object(tk_rooms.ttk, "Checkbutton"), \
                patch.object(tk_rooms.ttk, "Button", side_effect=button):
            listbox.return_value.curselection.return_value = (0,)
            tk_rooms.settings_window(ui, room)
        return tab, ui, window

    def test_stale_room_cannot_remove_players_or_bar_another_rooms_guessers(self):
        for replacement in (None, {"id": "different"}):
            with self.subTest(room=replacement):
                tab, ui, window = self.window()
                tab.client.my_room = replacement
                window.kick_button.command()
                window.bar_button.command()
                ui.kick.assert_not_called()
                ui.bar_guessers.assert_not_called()

    def test_replacement_session_cannot_use_old_moderation_controls(self):
        tab, ui, window = self.window()
        tab.client = SimpleNamespace(my_room={"id": "original"})
        window.kick_button.command()
        window.bar_button.command()
        ui.kick.assert_not_called()
        ui.bar_guessers.assert_not_called()

    def test_current_room_still_allows_moderation(self):
        _tab, ui, window = self.window()
        window.kick_button.command()
        window.bar_button.command()
        ui.kick.assert_called_once_with("peer", "Peer")
        ui.bar_guessers.assert_called_once_with()

    def test_confirming_removal_in_current_room_still_dispatches(self):
        client = SimpleNamespace(my_room={"id": "original"}, room_kick=Mock())
        tab = SimpleNamespace(client=client, parent=object(), call=Mock(), status=Mock(),
                              ask_yes_no=Mock(return_value=True))
        tk_rooms.RoomsUI(tab).kick("peer", "Peer")
        self.assertEqual(tab.call.call_args.args, (client.room_kick, "peer"))

    def test_room_change_during_confirmation_cannot_remove_player_from_new_room(self):
        for replace_session in (False, True):
            with self.subTest(replace_session=replace_session):
                client = SimpleNamespace(my_room={"id": "original"}, room_kick=Mock())
                tab = SimpleNamespace(client=client, parent=object(), call=Mock(), status=Mock())

                def confirm(*_args, **_kwargs):
                    if replace_session:
                        tab.client = SimpleNamespace(my_room={"id": "original"}, room_kick=Mock())
                    else:
                        client.my_room = {"id": "different"}
                    return True

                tab.ask_yes_no = confirm
                tk_rooms.RoomsUI(tab).kick("peer", "Peer")
                tab.call.assert_not_called()


if __name__ == "__main__":
    unittest.main()
