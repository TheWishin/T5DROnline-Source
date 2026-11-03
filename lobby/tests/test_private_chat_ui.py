"""Private chat tests use memory and mocked calls only: no server, game, or Tk root."""
import ast
from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import util  # noqa: F401 (sets the lobby package path; does not start a server)
from t5lobby.client import LobbyClient
from t5lobby.private_chat import Conversations, MAX_CONVERSATIONS, MAX_LINES
from t5lobby.proto import LobbyError
from t5lobby.tk_private_chat import PrivateChat


def envelope(number, sender="Rival", recipient="Tester", text="hello"):
    return {"t": "private_message", "id": str(number), "from": {"id": sender, "name": sender},
            "to": {"id": recipient, "name": recipient}, "text": text, "time": 123,
            "receipt": "test receipt"}


class PrivateConversations(unittest.TestCase):
    def test_own_view_unread_and_duplicate(self):
        model = Conversations()
        incoming = envelope(1)
        self.assertTrue(model.receive(incoming, "Tester"))
        self.assertEqual(model.unread, 1)
        self.assertFalse(model.receive(incoming, "Tester"))
        self.assertEqual(model.unread, 1)
        model.select("Rival")
        self.assertEqual(model.unread, 0)
        self.assertTrue(model.receive(envelope(2, "Tester", "Rival", "reply"), "Tester"))
        self.assertEqual(model.unread, 0)
        self.assertEqual([line["text"] for line in model.rows["rival"]["lines"]], ["hello", "reply"])
        model.receive(envelope(3), "Tester", visible=True)
        self.assertEqual(model.unread, 0)
        model.receive(envelope(4), "Tester", visible=False)
        self.assertEqual(model.unread, 1)

    def test_bounded_memory_and_mute(self):
        model = Conversations()
        for i in range(MAX_LINES + 20):
            model.receive(envelope(i), "Tester")
        self.assertEqual(len(model.rows["rival"]["lines"]), MAX_LINES)
        self.assertEqual(model.rows["rival"]["lines"][0]["id"], "20")
        model.set_muted("Rival", True)
        self.assertFalse(model.receive(envelope(999), "Tester"))
        self.assertEqual(len(model.rows["rival"]["lines"]), MAX_LINES)
        for i in range(MAX_CONVERSATIONS + 2):
            model.open(f"Player{i}")
        self.assertEqual(len(model.rows), MAX_CONVERSATIONS)
        self.assertTrue(model.open("Rival")["muted"])
        model.set_muted("Rival", False)
        self.assertFalse(model.open("Rival")["muted"])
        model.select("Rival")
        for i in range(MAX_CONVERSATIONS + 2):
            model.open(f"NewPlayer{i}")
        self.assertIn("rival", model.rows)

    def test_report_contains_only_chosen_original_lines(self):
        model = Conversations()
        for i in range(12):
            model.receive(envelope(i), "Tester")
        chosen = model.report_lines("Rival", [1, 3])
        self.assertEqual([line["id"] for line in chosen], ["1", "3"])
        self.assertEqual(chosen[0]["receipt"], "test receipt")
        self.assertEqual(model.report_lines("Rival", []), [])
        self.assertEqual(model.report_lines("Rival", list(range(6))), [])
        self.assertEqual(model.report_lines("Rival", [200]), [])

    def test_reset_discards_transcript(self):
        ui = PrivateChat(SimpleNamespace(client=None))
        ui.model.receive(envelope(1), "Tester")
        ui.model.set_muted("Rival", True)
        ui.name = "Rival"
        old_window = ui.window = Mock()
        ui.reset()
        self.assertEqual(len(ui.model.rows), 0)
        self.assertEqual(ui.model.unread, 0)
        self.assertEqual(ui.model.muted, set())
        self.assertIsNone(ui.name)
        self.assertIsNone(ui.window)
        old_window.destroy.assert_called_once_with()

    def test_list_and_profile_entry_points_and_inbox_open(self):
        c = SimpleNamespace(me={"name": "Tester"}, private_chat_ok=lambda: True,
                            players=[{"id": "player-id", "name": "Rival", "badge": "dev"}])
        tv = Mock()
        tv.selection.return_value = ["player-id"]
        tv.item.return_value = ("[DEV] Rival", "rank")
        ui = PrivateChat(SimpleNamespace(client=c, tv_players=tv, profile_name="ProfilePlayer",
                                        _you_suffix=lambda: " (you)"))
        with patch.object(ui, "show") as show:
            ui.selected_player()
            show.assert_called_once_with("Rival")
            tv.item.assert_not_called()  # rendered badge text is never a request identity
            show.reset_mock()
            ui.profile()
            show.assert_called_once_with("ProfilePlayer")
        # The inbox opens the retained conversation and clears its unread marker.
        ui.model.receive(envelope(1), "Tester")
        ui.name = "Rival"
        ui.window = Mock()
        with patch.object(ui, "draw"), patch.object(ui, "refresh"):
            ui.show()
        self.assertEqual(ui.model.unread, 0)
        ui.window.deiconify.assert_called_once_with()

    def test_visible_entry_buttons_are_wired_to_private_actions(self):
        source = Path(__file__).parents[1] / "t5lobby" / "tk_views.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        commands = set()
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "button" and isinstance(node.func.value, ast.Attribute)
                    and node.func.value.attr == "private_chat" and len(node.args) > 1
                    and isinstance(node.args[1], ast.Attribute)):
                commands.add(node.args[1].attr)
        self.assertTrue({"selected_player", "profile", "show"}.issubset(commands))

    def test_returning_focus_reads_active_conversation_without_redrawing_report(self):
        ui = PrivateChat(SimpleNamespace(client=None))
        ui.model.select("Rival")
        ui.model.receive(envelope(1), "Tester", visible=False)
        ui.name, ui.names = "Rival", ["Rival"]
        ui.window, ui.peers, ui.lines = Mock(), Mock(), Mock()
        ui.window.state.return_value = "normal"
        ui.window.focus_get.return_value.winfo_toplevel.return_value = Mock()  # another window
        with patch.object(ui, "refresh") as refresh, patch.object(ui, "draw") as draw:
            ui.mark_read()
            self.assertEqual(ui.model.unread, 1)
            ui.window.focus_get.return_value.winfo_toplevel.return_value = ui.window
            ui.mark_read()
            self.assertEqual(ui.model.unread, 0)
            refresh.assert_called_once_with()
            ui.mark_read()  # repeated FocusIn notifications do not redraw/reselect
            refresh.assert_called_once_with()
            draw.assert_not_called()
        ui.lines.assert_not_called()
        ui.lines.delete.assert_not_called()
        ui.peers.insert.assert_called_once_with(0, "Rival")

    def test_history_has_vertical_and_horizontal_scrollbars_without_tk_root(self):
        from t5lobby import tk_private_chat as widgets
        tab = SimpleNamespace(parent=Mock(), new_window=Mock(return_value=Mock()), client=None)
        ui = PrivateChat(tab)
        with patch.object(widgets.tk, "Listbox", side_effect=[Mock(), Mock()]), \
                patch.object(widgets.tk, "StringVar"), patch.object(widgets.ttk, "Frame"), \
                patch.object(widgets.ttk, "Label"), patch.object(widgets.ttk, "Entry"), \
                patch.object(widgets.ttk, "Button"), \
                patch.object(widgets.ttk, "Scrollbar", side_effect=[Mock(), Mock(), Mock()]) as scrollbar:
            ui.build()
        ui.window.bind.assert_called_once()
        self.assertEqual(ui.window.bind.call_args.args[0], "<FocusIn>")
        scroll_calls = scrollbar.call_args_list
        self.assertEqual([call.kwargs["orient"] for call in scroll_calls],
                         ["vertical", "vertical", "horizontal"])
        self.assertEqual(scroll_calls[1].kwargs["command"], ui.lines.yview)
        self.assertEqual(scroll_calls[2].kwargs["command"], ui.lines.xview)
        self.assertEqual(scroll_calls[0].kwargs["command"], ui.peers.yview)

    def test_logout_disconnect_and_launcher_close_clear_private_session(self):
        source = Path(__file__).parents[1] / "t5lobby" / "tk_tab.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        methods = {node.name: node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}

        def calls(method, name, receiver=None):
            return [node for node in ast.walk(methods[method]) if isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute) and node.func.attr == name
                    and (receiver is None or (isinstance(node.func.value, ast.Attribute)
                                              and node.func.value.attr == receiver))]

        self.assertTrue(calls("_reset_lobby_view", "reset", "private_chat"))
        self.assertTrue(calls("do_logout", "_reset_lobby_view"))
        self.assertTrue(calls("on_event", "_reset_lobby_view"))
        self.assertTrue(calls("on_close", "reset", "private_chat"))

    def test_client_capability_gate_and_selected_report_payload(self):
        # No constructor / sockets: exercise real request wrappers with only a fake transport.
        c = LobbyClient.__new__(LobbyClient)
        c.private_chat = True
        c.welcome = {"caps": [], "features": []}
        c._call = Mock()
        with self.assertRaises(LobbyError):
            c.private_message("Rival", "hello")
        c._call.assert_not_called()
        c.welcome = {"caps": ["private_chat"], "features": ["private_chat"]}
        c.private_message("Rival", "hello")
        c._call.assert_called_with({"t": "private_message", "name": "Rival", "text": "hello"})
        c.private_mute("Rival")
        c._call.assert_called_with({"t": "private_mute", "name": "Rival", "muted": True})
        chosen = [envelope(2)]
        c.private_report("Rival", chosen)
        c._call.assert_called_with({"t": "private_report", "name": "Rival", "lines": chosen, "reason": ""})


if __name__ == "__main__":
    unittest.main()
