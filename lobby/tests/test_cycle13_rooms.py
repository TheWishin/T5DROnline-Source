"""Room acknowledgements cannot close a replacement dialog; no Tk or server."""
from contextlib import ExitStack
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import util  # noqa: F401 -- package path only; no server helper is invoked
from t5lobby import tk_rooms


class Variable:
    def __init__(self, _parent, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value

    def trace_add(self, *_args):
        pass


class RoomAcknowledgementOwnershipTest(unittest.TestCase):
    def pending(self, action):
        room = {"id": "room", "owner_id": "host", "mode": "tables", "size": 4,
                "players": [{"id": "one", "name": "One"}, {"id": "two", "name": "Two"}],
                "line": ["one", "two"], "tables": [{"id": 1, "players": []}]}
        client = SimpleNamespace(welcome={}, my_room=room, rooms=[], me={"id": "host"},
                                 create_room=Mock(), room_pair=Mock(), training_ok=lambda: False)
        tab = SimpleNamespace(client=client, view=SimpleNamespace(px=lambda value: value, body=Mock()),
                              status=Mock(), call=Mock())
        ui = tk_rooms.RoomsUI(tab)
        window = Mock()

        def button(*_args, **kwargs):
            widget = Mock()
            widget.command = kwargs.get("command")
            return widget

        with ExitStack() as stack:
            stack.enter_context(patch.object(tk_rooms, "_window", return_value=(window, Mock())))
            stack.enter_context(patch.object(tk_rooms.tk, "StringVar", Variable))
            stack.enter_context(patch.object(tk_rooms.tk, "IntVar", Variable))
            for name in ("Label", "Entry", "Combobox", "Checkbutton"):
                stack.enter_context(patch.object(tk_rooms.ttk, name))
            stack.enter_context(patch.object(tk_rooms.ttk, "Button", side_effect=button))
            if action == "create":
                tk_rooms.create_window(ui)
                ui.window = window
                window.create_button.command()
            else:
                tk_rooms.tables_window(ui, room)
                ui.window = window
                window.player_vars[0].set("One")
                window.player_vars[1].set("Two")
                window.pair_button.command()
        ui.close_window = Mock()
        return ui, window, tab.call.call_args.kwargs["then"]

    def test_delayed_acknowledgement_does_not_close_a_new_dialog(self):
        for action in ("create", "pair"):
            with self.subTest(action=action):
                ui, _old, done = self.pending(action)
                replacement = object()
                ui.window = replacement
                done({})
                ui.close_window.assert_not_called()
                self.assertIs(ui.window, replacement)

    def test_acknowledgement_after_reset_does_not_close_another_window(self):
        for action in ("create", "pair"):
            with self.subTest(action=action):
                ui, _old, done = self.pending(action)
                ui.tab.client = None
                ui.window = None  # logout/disconnect resets the room windows
                done({})
                ui.close_window.assert_not_called()

    def test_acknowledgement_still_closes_its_own_dialog(self):
        for action in ("create", "pair"):
            with self.subTest(action=action):
                ui, _window, done = self.pending(action)
                done({})
                ui.close_window.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
