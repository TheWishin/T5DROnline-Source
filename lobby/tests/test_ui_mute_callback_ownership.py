"""Mute callbacks retain their requesting session; no Tk root, server or game."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


def controller(manager=False):
    source = Path(__file__).parents[1] / "t5lobby" / "tk_tab.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "OnlineTab")
    cls.body = [node for node in cls.body if isinstance(node, ast.FunctionDef)
                and node.name in {"do_muted", "toggle_mute", "_muted_window"}]
    namespace = {"t": lambda text, **kwargs: text.format(**kwargs),
                 "tk": SimpleNamespace(TclError=RuntimeError, Listbox=Mock()),
                 "ttk": SimpleNamespace(Label=Mock(), Button=Mock())}
    exec(compile(ast.Module(body=[cls], type_ignores=[]), str(source), "exec"), namespace)
    tab = namespace["OnlineTab"]()
    tab.client = SimpleNamespace(me={"name": "Tester"}, mutes=Mock(), mute=Mock(), unmute=Mock())
    tab.call = Mock()
    if not manager:
        tab._muted_window = Mock()
    tab._is_muted = Mock(return_value=False)
    tab._mutes_changed, tab.status = Mock(), Mock()
    tab.view = SimpleNamespace(px=lambda value: value, card=Mock(return_value=Mock()))
    tab.parent, tab.new_window = Mock(), Mock(return_value=Mock())
    return tab, namespace


class MuteCallbackOwnershipTest(unittest.TestCase):
    def test_list_reply_from_logged_out_or_replaced_client_is_discarded(self):
        for replacement in (None, SimpleNamespace(me={"name": "Other"})):
            with self.subTest(replacement=replacement):
                tab, _ = controller()
                tab.do_muted()
                done = tab.call.call_args.kwargs["then"]
                tab.client = replacement
                done({"rows": [{"name": "Rival"}]})
                tab._muted_window.assert_not_called()

    def test_list_reply_from_current_client_opens_manager(self):
        tab, _ = controller()
        tab.do_muted()
        reply = {"rows": [{"name": "Rival"}]}
        tab.call.call_args.kwargs["then"](reply)
        tab._muted_window.assert_called_once_with(reply)

    def test_old_mute_ack_does_not_refresh_or_report_for_new_session(self):
        tab, _ = controller()
        tab.toggle_mute("Rival")
        done = tab.call.call_args.kwargs["then"]
        tab.client = SimpleNamespace(me={"name": "Other"})
        done({"muted": True})
        tab._mutes_changed.assert_not_called()
        tab.status.assert_not_called()

    def test_current_mute_ack_still_refreshes_and_reports(self):
        tab, _ = controller()
        tab.toggle_mute("Rival")
        tab.call.call_args.kwargs["then"]({"muted": True})
        tab._mutes_changed.assert_called_once_with()
        tab.status.assert_called_once_with("Muted Rival.")

    def test_old_unmute_ack_does_not_change_manager_or_report_for_new_session(self):
        tab, namespace = controller(manager=True)
        tab._muted_window({"rows": [{"name": "Rival"}]})
        lb = namespace["tk"].Listbox.return_value
        lb.curselection.return_value = (0,)
        namespace["ttk"].Button.call_args_list[0].kwargs["command"]()
        done = tab.call.call_args.kwargs["then"]
        tab.client = SimpleNamespace(me={"name": "Other"})
        done({"muted": False})
        lb.delete.assert_not_called()
        tab._mutes_changed.assert_not_called()
        tab.status.assert_not_called()


if __name__ == "__main__":
    unittest.main()
