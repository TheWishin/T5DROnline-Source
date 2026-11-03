"""Recovery-code requests retain their account without sockets, Tk or game."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


def controller():
    source = Path(__file__).parents[1] / "t5lobby" / "tk_tab.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "OnlineTab")
    cls.body = [node for node in cls.body if isinstance(node, ast.FunctionDef)
                and node.name == "do_new_codes"]
    namespace = {"t": lambda text, **kwargs: text.format(**kwargs)}
    exec(compile(ast.Module(body=[cls], type_ignores=[]), str(source), "exec"), namespace)
    tab = namespace["OnlineTab"]()
    tab.client = SimpleNamespace(new_recovery_codes=Mock())
    tab.parent = object()
    tab.ask_string = Mock(return_value="account-password")
    tab.call, tab.show_codes = Mock(), Mock()
    return tab


class RecoveryCodeOwnershipTest(unittest.TestCase):
    def test_disconnected_action_does_not_open_password_prompt(self):
        tab = controller()
        tab.client = None
        tab.do_new_codes()
        tab.ask_string.assert_not_called()
        tab.call.assert_not_called()

    def test_session_change_during_prompt_cannot_send_password(self):
        for replacement in (None, SimpleNamespace(new_recovery_codes=Mock())):
            with self.subTest(replacement=replacement):
                tab = controller()

                def answer(*_args, **_kwargs):
                    tab.client = replacement
                    return "old-account-password"

                tab.ask_string.side_effect = answer
                tab.do_new_codes()
                tab.call.assert_not_called()

    def test_stale_reply_does_not_display_previous_accounts_codes(self):
        for replacement in (None, SimpleNamespace(new_recovery_codes=Mock())):
            with self.subTest(replacement=replacement):
                tab = controller()
                tab.do_new_codes()
                tab.client = replacement
                tab.call.call_args.kwargs["then"](["OLD-CODE"])
                tab.show_codes.assert_not_called()

    def test_current_account_can_request_and_display_codes(self):
        tab = controller()
        client = tab.client
        tab.do_new_codes()
        self.assertEqual(tab.call.call_args.args, (client.new_recovery_codes, "account-password"))
        codes = ["NEW-CODE"]
        tab.call.call_args.kwargs["then"](codes)
        tab.show_codes.assert_called_once_with(codes)

    def test_cancelled_prompt_does_not_request_codes(self):
        tab = controller()
        tab.ask_string.return_value = None
        tab.do_new_codes()
        tab.call.assert_not_called()


if __name__ == "__main__":
    unittest.main()
