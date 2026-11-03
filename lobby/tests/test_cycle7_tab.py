"""Saved login callbacks retain their server, with no sockets, Tk root or game."""
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


class AuthError(Exception):
    code = "auth"


def controller(remember=True):
    source = Path(__file__).parents[1] / "t5lobby" / "tk_tab.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "OnlineTab")
    cls.body = [node for node in cls.body if isinstance(node, ast.FunctionDef)
                and node.name in {"_server_key", "_remember_session", "do_login"}]
    namespace = {"DEFAULT_SERVER": "default", "time": SimpleNamespace(time=lambda: 123),
                 "LobbyError": AuthError, "proto": SimpleNamespace(E_AUTH="auth"),
                 "t": lambda text, **kwargs: text.format(**kwargs)}
    exec(compile(ast.Module(body=[cls], type_ignores=[]), str(source), "exec"), namespace)
    tab = namespace["OnlineTab"]()
    tab.client = None
    tab._login_busy = False
    tab.server_var = Variable(" Server-A ")
    tab.name_var, tab.pw_var = Variable("Tester"), Variable("password")
    tab.remember_var, tab.hint_var = Variable(remember), Variable("")
    tab.cfg = {"sessions": {"server-a": {"name": "Tester", "token": "old-a"},
                            "server-b": {"name": "Other", "token": "keep-b"}}}
    client = SimpleNamespace(session="new-a", ingame_pick=False, tls=False, recovery_codes=[],
                             connect=Mock(return_value={}), login_session=Mock(), close=Mock())
    tab._new_client = Mock(return_value=client)
    tab._build_info = Mock(return_value=(object(), None))
    for name in ("_save_cfg", "status", "_make_driver", "_set_account_view", "_show_me", "_set_actions",
                 "on_char", "on_life", "_run_pending_search", "call"):
        setattr(tab, name, Mock())
    tab._confirm_password = Mock(return_value=True)
    return tab, client


class SavedLoginServerOwnershipTest(unittest.TestCase):
    def test_success_saves_under_login_server_after_selection_changes(self):
        for mode in ("account", "register"):
            with self.subTest(mode=mode):
                tab, _client = controller()
                tab.do_login(mode)
                tab.server_var.set("Server-B")
                tab.call.call_args.kwargs["then"](({}, {"name": "Tester"}))
                self.assertEqual(tab._server_key(), "server-a")
                self.assertEqual(tab.cfg["sessions"]["server-a"]["token"], "new-a")
                self.assertEqual(tab.cfg["sessions"]["server-b"]["token"], "keep-b")

    def test_guest_and_saved_login_success_restore_connected_server(self):
        for mode in ("guest", "session"):
            with self.subTest(mode=mode):
                tab, _client = controller()
                tab.do_login(mode, session="old-a" if mode == "session" else None)
                tab.server_var.set("Server-B")
                tab.call.call_args.kwargs["then"](({}, {"name": "Tester"}))
                self.assertEqual(tab._server_key(), "server-a")
                self.assertEqual(tab.cfg["sessions"]["server-b"]["token"], "keep-b")

    def test_remember_off_forgets_only_login_server(self):
        tab, _client = controller(remember=False)
        tab.do_login("account")
        tab.server_var.set("Server-B")
        tab.call.call_args.kwargs["then"](({}, {"name": "Tester"}))
        self.assertEqual(tab.cfg["sessions"], {"server-b": {"name": "Other", "token": "keep-b"}})

    def test_auth_rejection_forgets_only_login_server(self):
        tab, client = controller()
        client.login_session.side_effect = AuthError()
        tab.do_login("session", session="old-a")
        tab.server_var.set("Server-B")
        callbacks = tab.call.call_args
        with self.assertRaises(AuthError):
            callbacks.args[0]()
        callbacks.kwargs["fail"]()
        self.assertEqual(tab.cfg["sessions"], {"server-b": {"name": "Other", "token": "keep-b"}})
        client.close.assert_called_once_with()

    def test_unreachable_server_keeps_both_saved_logins(self):
        tab, client = controller()
        client.connect.side_effect = OSError("offline")
        tab.do_login("session", session="old-a")
        tab.server_var.set("Server-B")
        callbacks = tab.call.call_args
        with self.assertRaises(OSError):
            callbacks.args[0]()
        callbacks.kwargs["fail"]()
        self.assertEqual({key: row["token"] for key, row in tab.cfg["sessions"].items()},
                         {"server-a": "old-a", "server-b": "keep-b"})

    def test_unspecified_key_keeps_existing_selected_server_behavior(self):
        tab, _client = controller()
        tab.server_var.set("Server-B")
        tab._remember_session("Other", "replacement-b")
        self.assertEqual(tab.cfg["sessions"]["server-b"]["token"], "replacement-b")
        self.assertEqual(tab.cfg["sessions"]["server-a"]["token"], "old-a")


if __name__ == "__main__":
    unittest.main()
