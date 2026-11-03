"""Password changes retain their session and server, without sockets, Tk or game."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock


class Variable:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def controller(remember=True):
    source = Path(__file__).parents[1] / "t5lobby" / "tk_tab.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "OnlineTab")
    cls.body = [node for node in cls.body if isinstance(node, ast.FunctionDef)
                and node.name in {"_server_key", "_saved_session", "_remember_session", "do_passwd"}]
    namespace = {"DEFAULT_SERVER": "default", "time": SimpleNamespace(time=lambda: 123),
                 "t": lambda text, **kwargs: text.format(**kwargs)}
    exec(compile(ast.Module(body=[cls], type_ignores=[]), str(source), "exec"), namespace)
    tab = namespace["OnlineTab"]()
    tab.server_var = Variable("Server-A")
    tab.cfg = {"sessions": {"server-b": {"name": "Other", "token": "keep-b"}}}
    if remember:
        tab.cfg["sessions"]["server-a"] = {"name": "Tester", "token": "old-a"}
    tab.client = SimpleNamespace(me={"name": "Tester"}, session="new-a", change_password=Mock())
    tab.parent = object()
    tab.ask_string = Mock(side_effect=["old-password", "new-password", "new-password"])
    tab._save_cfg, tab.status, tab.call = Mock(), Mock(), Mock()
    return tab


class PasswordChangeOwnershipTest(unittest.TestCase):
    def test_reply_updates_original_server_after_selection_changes(self):
        tab = controller()
        tab.do_passwd()
        tab.server_var.set("Server-B")
        tab.call.call_args.kwargs["then"]({})
        self.assertEqual(tab.cfg["sessions"]["server-a"]["token"], "new-a")
        self.assertEqual(tab.cfg["sessions"]["server-b"]["token"], "keep-b")
        self.assertEqual(tab.call.call_args.args[1:], ("old-password", "new-password", True))

    def test_reply_without_remember_does_not_forget_another_server(self):
        tab = controller(remember=False)
        tab.do_passwd()
        tab.server_var.set("Server-B")
        tab.call.call_args.kwargs["then"]({})
        self.assertEqual(tab.cfg["sessions"], {"server-b": {"name": "Other", "token": "keep-b"}})
        self.assertEqual(tab.call.call_args.args[1:], ("old-password", "new-password", False))

    def test_current_session_still_saves_refreshed_token(self):
        tab = controller()
        tab.do_passwd()
        tab.call.call_args.kwargs["then"]({})
        self.assertEqual(tab.cfg["sessions"]["server-a"]["token"], "new-a")
        self.assertEqual(tab.cfg["sessions"]["server-b"]["token"], "keep-b")
        tab._save_cfg.assert_called_once_with()

    def test_session_change_during_any_prompt_cannot_send_passwords(self):
        for prompt in range(3):
            for replacement in (None, SimpleNamespace(change_password=Mock())):
                with self.subTest(prompt=prompt, replacement=replacement):
                    tab = controller()
                    answers = iter(["old-password", "new-password", "new-password"])
                    calls = 0

                    def answer(*_args, **_kwargs):
                        nonlocal calls
                        if calls == prompt:
                            tab.client = replacement
                        calls += 1
                        return next(answers)

                    tab.ask_string.side_effect = answer
                    tab.do_passwd()
                    tab.call.assert_not_called()

    def test_stale_reply_cannot_restore_forgotten_session_or_write_new_session(self):
        for replacement in (None, SimpleNamespace(me={"name": "Other"})):
            with self.subTest(replacement=replacement):
                tab = controller()
                tab.do_passwd()
                tab.client = replacement
                tab.cfg["sessions"].pop("server-a")
                tab.server_var.set("Server-B")
                tab.call.call_args.kwargs["then"]({})
                self.assertEqual(tab.cfg["sessions"], {"server-b": {"name": "Other", "token": "keep-b"}})
                tab._save_cfg.assert_not_called()
                tab.status.assert_not_called()

    def test_remember_choice_uses_server_before_prompts(self):
        tab = controller(remember=False)

        def answer(*_args, **_kwargs):
            tab.server_var.set("Server-B")
            return "password"

        tab.ask_string.side_effect = answer
        tab.do_passwd()
        self.assertEqual(tab.call.call_args.args[1:], ("password", "password", False))

    def test_tokenless_or_malformed_saved_rows_are_not_remembered(self):
        for saved in ({"name": "Tester"}, {"token": ""}, "not-a-session", None):
            with self.subTest(saved=saved):
                tab = controller()
                tab.cfg["sessions"]["server-a"] = saved
                tab.do_passwd()
                self.assertEqual(tab.call.call_args.args[1:], ("old-password", "new-password", False))

    def test_disconnected_action_does_not_open_password_prompts(self):
        tab = controller()
        tab.client = None
        tab.do_passwd()
        tab.ask_string.assert_not_called()
        tab.call.assert_not_called()


if __name__ == "__main__":
    unittest.main()
