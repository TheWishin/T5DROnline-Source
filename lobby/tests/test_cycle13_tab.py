"""Late hosting readiness preserves an active login without Tk, processes or sockets."""
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


def controller(client=None):
    source = Path(__file__).parents[1] / "t5lobby" / "tk_tab.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "OnlineTab")
    cls.body = [node for node in cls.body if isinstance(node, ast.FunctionDef)
                and node.name in {"_host_event", "_server_key"}]
    namespace = {"DEFAULT_SERVER": "default", "tk": SimpleNamespace(TclError=RuntimeError),
                 "t": lambda text, **kwargs: text.format(**kwargs)}
    exec(compile(ast.Module(body=[cls], type_ignores=[]), str(source), "exec"), namespace)
    tab = namespace["OnlineTab"]()
    tab.host_proc = object()
    tab.host_info = None
    tab.client = client
    tab.server_var = Variable("Server-A")
    tab.parent, tab.view = Mock(), Mock()
    tab.chat_line, tab.status = Mock(), Mock()
    return tab


READY = {"event": "ready", "local": "127.0.0.1:7781#PIN", "port": 7781,
         "internet": "host.example:7781#PIN", "mapped": True}


class HostingServerOwnershipTest(unittest.TestCase):
    def test_host_ready_after_login_retains_accounts_server(self):
        client = SimpleNamespace(me={"name": "Tester"}, session="server-a-token")
        tab = controller(client)
        tab._host_event(tab.host_proc, READY)
        self.assertIs(tab.client, client)
        self.assertEqual(tab.server_var.get(), "Server-A")
        self.assertEqual(tab._server_key(), "server-a")
        self.assertIs(tab.host_info, READY)
        tab.view.hosting.assert_called_once_with(READY)
        tab.parent.clipboard_append.assert_called_once_with(READY["internet"])

    def test_host_ready_while_logged_out_selects_local_server(self):
        tab = controller()
        tab._host_event(tab.host_proc, READY)
        self.assertEqual(tab.server_var.get(), READY["local"])
        self.assertIs(tab.host_info, READY)
        tab.view.hosting.assert_called_once_with(READY)

    def test_old_host_ready_cannot_change_server_or_host_info(self):
        tab = controller()
        tab._host_event(object(), READY)
        self.assertEqual(tab.server_var.get(), "Server-A")
        self.assertIsNone(tab.host_info)
        tab.view.hosting.assert_not_called()


if __name__ == "__main__":
    unittest.main()
