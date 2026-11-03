"""Logout confirmation retains its session and server, without sockets, Tk or game."""
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


def controller(forget=True):
    source = Path(__file__).parents[1] / "t5lobby" / "tk_tab.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "OnlineTab")
    cls.body = [node for node in cls.body if isinstance(node, ast.FunctionDef)
                and node.name in {"_server_key", "_remember_session", "do_logout"}]
    thread = Mock()
    namespace = {"DEFAULT_SERVER": "default", "time": SimpleNamespace(time=lambda: 123),
                 "threading": SimpleNamespace(Thread=thread),
                 "t": lambda text, **kwargs: text.format(**kwargs)}
    exec(compile(ast.Module(body=[cls], type_ignores=[]), str(source), "exec"), namespace)
    tab = namespace["OnlineTab"]()
    tab.server_var = Variable("Server-A")
    tab.cfg = {"sessions": {"server-a": {"name": "Tester", "token": "old-a"},
                            "server-b": {"name": "Other", "token": "keep-b"}}}
    tab.client = SimpleNamespace(session="old-a", logout=Mock())
    tab._login_busy = False
    tab.parent = object()
    tab.ask_yes_no = Mock(return_value=forget)
    tab.spec, tab.driver = SimpleNamespace(stop=Mock()), SimpleNamespace(close=Mock())
    tab.me_var = Variable("Tester")
    for name in ("_save_cfg", "_reset_lobby_view", "_set_account_view", "_set_actions"):
        setattr(tab, name, Mock())
    return tab, thread


class LogoutOwnershipTest(unittest.TestCase):
    def test_session_change_during_confirmation_cannot_log_out_replacement(self):
        for replacement in (SimpleNamespace(session="new-b", logout=Mock()),):
            with self.subTest(replacement=replacement):
                tab, thread = controller()
                original, driver = tab.client, tab.driver

                def answer(*_args, **_kwargs):
                    tab.client = replacement
                    tab.server_var.set("Server-B")
                    return True

                tab.ask_yes_no.side_effect = answer
                tab.do_logout()
                self.assertIs(tab.client, replacement)
                self.assertIs(tab.driver, driver)
                self.assertEqual(tab.cfg["sessions"]["server-a"]["token"], "old-a")
                self.assertEqual(tab.cfg["sessions"]["server-b"]["token"], "keep-b")
                tab.spec.stop.assert_not_called()
                driver.close.assert_not_called()
                original.logout.assert_not_called()
                thread.assert_not_called()
                tab._save_cfg.assert_not_called()
                tab._reset_lobby_view.assert_not_called()

    def test_selector_change_forgets_only_original_server(self):
        tab, _thread = controller()

        def answer(*_args, **_kwargs):
            tab.server_var.set("Server-B")
            return True

        tab.ask_yes_no.side_effect = answer
        tab.do_logout()
        self.assertEqual(tab.cfg["sessions"], {"server-b": {"name": "Other", "token": "keep-b"}})
        tab._save_cfg.assert_called_once_with()

    def test_current_session_logs_out_with_original_forget_choice(self):
        for forget in (True, False):
            with self.subTest(forget=forget):
                tab, thread = controller(forget=forget)
                original, driver = tab.client, tab.driver
                tab.do_logout()
                self.assertIsNone(tab.client)
                self.assertIsNone(tab.driver)
                tab.spec.stop.assert_called_once_with()
                driver.close.assert_called_once_with()
                thread.return_value.start.assert_called_once_with()
                thread.call_args.kwargs["target"]()
                original.logout.assert_called_once_with(forget=forget)
                self.assertEqual("server-a" in tab.cfg["sessions"], not forget)
                self.assertEqual(tab.cfg["sessions"]["server-b"]["token"], "keep-b")
                tab._reset_lobby_view.assert_called_once_with()
                tab._set_account_view.assert_called_once_with(False)
                tab._set_actions.assert_called_once_with()
                self.assertEqual(tab.me_var.get(), "Not connected.")


if __name__ == "__main__":
    unittest.main()
