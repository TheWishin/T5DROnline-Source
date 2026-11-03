"""Fake router cleanup without starting its HTTP or SSDP servers."""
import ast
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock


def router_stop():
    # Load just the fixture method: importing test_hosting also probes this PC
    # for optional executables unrelated to this offline cleanup check.
    path = Path(__file__).with_name("test_hosting.py")
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    router = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "FakeIgd")
    stop = next(node for node in router.body if isinstance(node, ast.FunctionDef) and node.name == "stop")
    namespace = {}
    exec(compile(ast.Module(body=[stop], type_ignores=[]), str(path), "exec"), namespace)
    return namespace["stop"]


class FakeRouterCleanupTest(unittest.TestCase):
    def test_stop_releases_http_listener_after_stopping_serve_loop(self):
        calls = mock.Mock()
        router = SimpleNamespace(running=True, http=calls.http, ssdp=calls.ssdp)

        router_stop()(router)

        self.assertFalse(router.running)
        self.assertEqual(calls.mock_calls, [
            mock.call.http.shutdown(), mock.call.http.server_close(), mock.call.ssdp.close(),
        ])


if __name__ == "__main__":
    unittest.main()
