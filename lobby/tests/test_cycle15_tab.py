"""Repeated login actions retain pending or active login ownership, without Tk or sockets."""
import ast
from pathlib import Path
import unittest
from unittest.mock import Mock


class Variable:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


def controller():
    source = Path(__file__).parents[1] / "t5lobby" / "tk_tab.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "OnlineTab")
    cls.body = [node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == "do_login"]
    namespace = {"DEFAULT_SERVER": "default", "t": lambda text, **kwargs: text.format(**kwargs)}
    exec(compile(ast.Module(body=[cls], type_ignores=[]), str(source), "exec"), namespace)
    tab = namespace["OnlineTab"]()
    tab.client = None
    tab._login_busy = False
    tab.server_var, tab.name_var = Variable("Server-A"), Variable("Tester")
    tab.pw_var, tab.remember_var = Variable("password"), Variable(True)
    tab._build_info = Mock(return_value=(object(), None))
    tab._confirm_password = Mock(return_value=True)
    tab._new_client, tab._save_cfg, tab.status, tab.call = Mock(), Mock(), Mock(), Mock()
    return tab


class LoginExclusionTest(unittest.TestCase):
    def test_repeated_actions_create_only_one_pending_client(self):
        for first in ("guest", "account", "register", "session"):
            with self.subTest(first=first):
                tab = controller()
                tab.do_login(first, session="token")
                for mode in ("guest", "account", "register", "session"):
                    tab.do_login(mode, session="token")
                self.assertTrue(tab._login_busy)
                tab._new_client.assert_called_once()
                tab.call.assert_called_once()
                tab._save_cfg.assert_called_once()

    def test_active_client_cannot_be_replaced_by_another_login_action(self):
        for mode in ("guest", "account", "register", "session"):
            with self.subTest(mode=mode):
                tab = controller()
                original = tab.client = object()
                tab.do_login(mode, session="token")
                self.assertIs(tab.client, original)
                tab._new_client.assert_not_called()
                tab.call.assert_not_called()
                tab._confirm_password.assert_not_called()

    def test_login_started_during_confirmation_keeps_its_ownership(self):
        tab = controller()

        def confirm(_password):
            tab.do_login("account")
            return True

        tab._confirm_password.side_effect = confirm
        tab.do_login("register")
        tab._new_client.assert_called_once()
        tab.call.assert_called_once()
        self.assertTrue(tab._login_busy)

    def test_login_completed_during_confirmation_cannot_be_replaced(self):
        tab = controller()
        original = object()

        def confirm(_password):
            tab.client = original
            return True

        tab._confirm_password.side_effect = confirm
        tab.do_login("register")
        self.assertIs(tab.client, original)
        tab._new_client.assert_not_called()
        tab.call.assert_not_called()

    def test_failed_login_releases_the_next_attempt(self):
        tab = controller()
        tab.do_login("account")
        self.assertTrue(tab._login_busy)
        tab.call.call_args.kwargs["fail"]()
        self.assertFalse(tab._login_busy)
        tab.do_login("account")
        self.assertTrue(tab._login_busy)
        self.assertEqual(tab._new_client.call_count, 2)
        self.assertEqual(tab.call.call_count, 2)

    def test_rejected_confirmation_does_not_block_the_next_login(self):
        tab = controller()
        tab._confirm_password.return_value = False
        tab.do_login("register")
        self.assertFalse(tab._login_busy)
        tab._new_client.assert_not_called()
        tab.do_login("account")
        tab._new_client.assert_called_once()
        tab.call.assert_called_once()


if __name__ == "__main__":
    unittest.main()
