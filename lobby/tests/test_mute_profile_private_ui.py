"""Profile and private mute controls, without Tk windows, sockets, or game data."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import util  # noqa: F401 (imports only; never starts its server helper)
from t5lobby.tk_private_chat import PrivateChat
from t5lobby.tk_views import OnlineView


def message(number, sender="Rival"):
    return {"t": "private_message", "id": str(number), "from": {"name": sender},
            "to": {"name": "Tester"}, "text": "hello", "receipt": "test", "time": 1}


class ProfilePrivateMuteTest(unittest.TestCase):
    def client(self, muted=False):
        return SimpleNamespace(me={"name": "Tester"}, private_chat_ok=lambda: True,
                               is_muted=Mock(return_value=muted), mute=Mock())

    def test_private_button_uses_shared_player_mute(self):
        c = self.client()
        calls = []
        ui = PrivateChat(SimpleNamespace(client=c, call=lambda *a, **kw: calls.append((a, kw))))
        ui.name = "Rival"
        ui.model.open("Rival")
        ui.mute()
        self.assertEqual(calls[0][0], (c.mute, "Rival", True))
        c.is_muted.return_value = True
        with patch.object(ui, "draw") as draw:
            calls[0][1]["then"]({"muted": True})
        self.assertTrue(ui.model.rows["rival"]["muted"])
        draw.assert_called_once_with()
        ui.mute()
        self.assertEqual(calls[1][0], (c.mute, "Rival", False))

    def test_profile_mute_state_is_shared_and_self_is_disabled(self):
        c = self.client(True)
        view = OnlineView.__new__(OnlineView)
        view.tab = SimpleNamespace(client=c, profile_name="Rival", _is_muted=c.is_muted)
        view.profile_mute = Mock()
        view._update_profile_mute()
        self.assertEqual(view.profile_mute.configure.call_args.kwargs,
                         {"state": "normal", "text": "Unmute"})
        view.tab.profile_name = "Tester"
        view._update_profile_mute()
        self.assertEqual(view.profile_mute.configure.call_args.kwargs["state"], "disabled")
        view.tab.client = None
        view._update_profile_mute()
        self.assertEqual(view.profile_mute.configure.call_args.kwargs["state"], "disabled")

    def test_persisted_mute_suppresses_private_view_and_unread(self):
        ui = PrivateChat(SimpleNamespace(client=self.client(True)))
        with patch.object(ui, "draw") as draw:
            ui.event(message(1))
        self.assertEqual(ui.model.unread, 0)
        self.assertEqual(len(ui.model.rows), 0)
        draw.assert_not_called()

    def test_mute_event_sync_does_not_redraw_report_selection(self):
        c = self.client(False)
        ui = PrivateChat(SimpleNamespace(client=c))
        ui.model.receive(message(1), "Tester")
        c.is_muted.return_value = True
        with patch.object(ui, "draw") as draw:
            ui.event({"t": "mutes", "rows": [{"name": "Rival"}]})
        self.assertTrue(ui.model.rows["rival"]["muted"])
        draw.assert_not_called()

    def test_unmute_elsewhere_resets_private_view_mute(self):
        c = self.client(False)
        ui = PrivateChat(SimpleNamespace(client=c))
        ui.model.open("Rival")
        ui.model.set_muted("Rival", True)
        ui.refresh()
        self.assertFalse(ui.model.rows["rival"]["muted"])

    def test_report_selection_survives_new_lines_and_eviction(self):
        ui = PrivateChat(SimpleNamespace(client=self.client()))
        ui.name = "Rival"
        ui.model.receive(message(1), "Tester")
        ui.model.receive(message(2), "Tester")
        ui.window, ui.peers, ui.lines, ui.mute_button = Mock(), Mock(), Mock(), Mock()
        ui._drawn_name, ui._drawn_line_ids = "Rival", ["0", "1"]
        ui.lines.curselection.return_value = (1,)
        with patch.object(ui, "refresh"):
            ui.draw()
        self.assertEqual(ui._drawn_line_ids, ["1", "2"])
        ui.lines.selection_set.assert_called_once_with(0)

    def test_switching_conversation_does_not_copy_report_selection(self):
        ui = PrivateChat(SimpleNamespace(client=self.client()))
        ui.name = "Other"
        ui.model.receive(message(1, "Other"), "Tester")
        ui.window, ui.peers, ui.lines, ui.mute_button = Mock(), Mock(), Mock(), Mock()
        ui._drawn_name, ui._drawn_line_ids = "Rival", ["1"]
        ui.lines.curselection.return_value = (0,)
        with patch.object(ui, "refresh"):
            ui.draw()
        ui.lines.selection_set.assert_not_called()

    def test_muting_hides_prior_incoming_lines_and_unmute_restores_them(self):
        c = self.client(True)
        ui = PrivateChat(SimpleNamespace(client=c))
        ui.name = "Rival"
        ui.model.receive(message(1), "Tester")
        ui.window, ui.peers, ui.lines, ui.mute_button = Mock(), Mock(), Mock(), Mock()
        ui.lines.curselection.return_value = ()
        ui.sync_mutes()
        with patch.object(ui, "refresh"):
            ui.draw()
        ui.lines.insert.assert_not_called()
        self.assertEqual(len(ui.model.rows["rival"]["lines"]), 1)
        c.is_muted.return_value = False
        ui.sync_mutes()
        with patch.object(ui, "refresh"):
            ui.draw()
        ui.lines.insert.assert_called_once_with("end", "Rival: hello")

    def test_report_uses_visible_original_receipts_when_muted_lines_are_hidden(self):
        c = self.client(True)
        c.private_report = Mock()
        tab = SimpleNamespace(client=c, call=Mock(), ask_yes_no=Mock(return_value=True), status=Mock())
        ui = PrivateChat(tab)
        ui.name = "Rival"
        ui.model.receive(message(1), "Tester")
        outgoing = message(2)
        outgoing["from"], outgoing["to"] = {"name": "Tester"}, {"name": "Rival"}
        ui.model.receive(outgoing, "Tester")
        ui.window, ui.lines = Mock(), Mock()
        ui._drawn_line_ids = ["2"]
        ui.lines.curselection.return_value = (0,)
        ui.report()
        args = tab.call.call_args.args
        self.assertEqual(args[0], c.private_report)
        self.assertEqual(args[1], "Rival")
        self.assertEqual([line["id"] for line in args[2]], ["2"])
    def test_player_rows_and_profile_have_one_click_mute_hooks(self):
        path = Path(__file__).parents[1] / "t5lobby" / "tk_views.py"
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        self.assertIn('"ping", "mute"', source)
        attrs = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        self.assertTrue({"on_player_mute_click", "toggle_mute", "do_muted"}.issubset(attrs))


if __name__ == "__main__":
    unittest.main()
