"""Logout remains final across a modal-loop disconnect, without Tk or sockets."""
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


def controller():
    source = Path(__file__).parents[1] / "t5lobby" / "tk_tab.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "OnlineTab")
    cls.body = [node for node in cls.body if isinstance(node, ast.FunctionDef)
                and node.name in {"_server_key", "_saved_session", "_remember_session", "do_logout", "_relogin_tick"}]
    thread = Mock()
    namespace = {"DEFAULT_SERVER": "default", "time": SimpleNamespace(time=lambda: 123, monotonic=lambda: 100),
                 "threading": SimpleNamespace(Thread=thread),
                 "t": lambda text, **kwargs: text.format(**kwargs)}
    exec(compile(ast.Module(body=[cls], type_ignores=[]), str(source), "exec"), namespace)
    tab = namespace["OnlineTab"]()
    tab.server_var = Variable("Server-A")
    tab.cfg = {"sessions": {"server-a": {"name": "Tester", "token": "old-a"},
                            "server-b": {"name": "Other", "token": "keep-b"}}}
    tab.client = SimpleNamespace(session="old-a", logout=Mock())
    tab._login_busy, tab._kicked = False, False
    tab._relogin_at, tab._relogin_until, tab._relogin_n = None, 200, 0
    tab.RELOGIN_EVERY = 10
    tab.parent = object()
    tab.spec = SimpleNamespace(stop=Mock())
    tab.driver = SimpleNamespace(close=Mock(), game_running=Mock(return_value=False))
    tab.name_var, tab.me_var = Variable("Tester"), Variable("Tester")
    for name in ("_save_cfg", "_reset_lobby_view", "_set_account_view", "_set_actions", "do_login"):
        setattr(tab, name, Mock())
    return tab, thread


class LogoutDisconnectTest(unittest.TestCase):
    def test_disconnect_during_confirmation_honors_logout_and_forget_choice(self):
        for forget in (False, True):
            with self.subTest(forget=forget):
                tab, thread = controller()
                original, driver = tab.client, tab.driver

                def answer(*_args, **_kwargs):
                    # A disconnected event schedules a retry while the dialog runs Tk's loop.
                    tab.client = None
                    tab._relogin_at = 90
                    tab._relogin_tick()
                    tab.do_login.assert_not_called()
                    tab.server_var.set("Server-B")
                    return forget

                tab.ask_yes_no = answer
                tab.do_logout()
                self.assertIsNone(tab.client)
                self.assertIsNone(tab._relogin_at)
                self.assertFalse(tab._login_busy)
                self.assertEqual("server-a" in tab.cfg["sessions"], not forget)
                self.assertEqual(tab.cfg["sessions"]["server-b"]["token"], "keep-b")
                self.assertIs(tab.driver, driver)
                driver.close.assert_not_called()
                tab.spec.stop.assert_not_called()
                tab._reset_lobby_view.assert_not_called()
                original.logout.assert_not_called()
                thread.assert_not_called()
                tab._relogin_tick()
                tab.do_login.assert_not_called()
                if forget:
                    tab._save_cfg.assert_called_once_with()
                else:
                    tab._save_cfg.assert_not_called()

    def test_confirmation_restores_previous_login_busy_state(self):
        for busy in (False, True):
            with self.subTest(busy=busy):
                tab, _thread = controller()
                tab._login_busy = busy

                def answer(*_args, **_kwargs):
                    self.assertTrue(tab._login_busy)
                    raise ValueError("dialog closed")

                tab.ask_yes_no = answer
                with self.assertRaisesRegex(ValueError, "dialog closed"):
                    tab.do_logout()
                self.assertEqual(tab._login_busy, busy)


if __name__ == "__main__":
    unittest.main()
