"""Room credentials retain their prompting session, without Tk, sockets or game."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


def controller(lock="password", selected=True):
    source = Path(__file__).parents[1] / "t5lobby" / "tk_rooms.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "RoomsUI")
    cls.body = [node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == "join_selected"]
    namespace = {"t": lambda text, **kwargs: text.format(**kwargs),
                 "proto": SimpleNamespace(clean_room_password=lambda value: value), "PW_RULE": "rule"}
    exec(compile(ast.Module(body=[cls], type_ignores=[]), str(source), "exec"), namespace)
    ui = namespace["RoomsUI"]()
    client = SimpleNamespace(rooms=[{"id": "room-a", "name": "Room A", "private": bool(lock), "lock": lock}],
                             join_room=Mock())
    ui.tab = SimpleNamespace(client=client, parent=object(), call=Mock(), status=Mock(),
                             tv_rooms=SimpleNamespace(selection=lambda: ("room-a",) if selected else ()),
                             ask_string=Mock(return_value="room-secret"))
    ui.ok = lambda: True
    return ui


class RoomJoinOwnershipTest(unittest.TestCase):
    def test_session_change_during_prompt_cannot_send_room_credentials(self):
        for lock, selected in (("password", True), ("code", True), (None, False)):
            for disconnect in (False, True):
                with self.subTest(lock=lock, selected=selected, disconnect=disconnect):
                    ui = controller(lock, selected)
                    original = ui.tab.client
                    replacement = None if disconnect else SimpleNamespace(join_room=Mock())

                    def answer(*_args, **_kwargs):
                        ui.tab.client = replacement
                        return "room-secret"

                    ui.tab.ask_string.side_effect = answer
                    ui.join_selected()
                    ui.tab.call.assert_not_called()
                    original.join_room.assert_not_called()
                    if replacement is not None:
                        replacement.join_room.assert_not_called()

    def test_current_session_still_joins_with_password_or_code(self):
        for lock, selected, args in (("password", True, ("room-a", "room-secret")),
                                     ("code", True, ("room-a", None, "room-secret")),
                                     (None, False, (None, None, "room-secret")),
                                     (None, True, ("room-a",))):
            with self.subTest(lock=lock, selected=selected):
                ui = controller(lock, selected)
                ui.join_selected()
                ui.tab.call.assert_called_once_with(ui.tab.client.join_room, *args)

    def test_cancelled_prompt_does_not_dispatch(self):
        for lock, selected in (("password", True), ("code", True), (None, False)):
            with self.subTest(lock=lock, selected=selected):
                ui = controller(lock, selected)
                ui.tab.ask_string.return_value = None
                ui.join_selected()
                ui.tab.call.assert_not_called()

    def test_disconnected_action_does_not_open_room_prompt(self):
        ui = controller()
        ui.tab.client = None
        ui.join_selected()
        ui.tab.ask_string.assert_not_called()
        ui.tab.call.assert_not_called()


if __name__ == "__main__":
    unittest.main()
