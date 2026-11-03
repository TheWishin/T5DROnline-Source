"""Account recovery retains its server without sockets, Tk or game execution."""
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


def controller(server=" Server-A "):
    source = Path(__file__).parents[1] / "t5lobby" / "tk_tab.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "OnlineTab")
    cls.body = [node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == "do_forgot"]
    namespace = {"DEFAULT_SERVER": "default", "t": lambda text, **kwargs: text.format(**kwargs)}
    exec(compile(ast.Module(body=[cls], type_ignores=[]), str(source), "exec"), namespace)
    tab = namespace["OnlineTab"]()
    tab.server_var, tab.name_var = Variable(server), Variable("Tester")
    tab.parent = object()
    tab._build_info = Mock(return_value=("test-build", None))
    tab._new_client = Mock(return_value=SimpleNamespace(connect=Mock(), recover=Mock(), close=Mock()))
    tab.ask_string = Mock(side_effect=["Tester", "AAAA-BBBB-CCCC", "new-password"])
    tab.call, tab.status = Mock(), Mock()
    return tab


class RecoveryServerOwnershipTest(unittest.TestCase):
    def test_server_change_during_any_prompt_keeps_original_destination(self):
        for server, expected in ((" Server-A ", "Server-A"), ("   ", "default")):
            for prompt in range(3):
                with self.subTest(server=server, prompt=prompt):
                    tab = controller(server)
                    answers = iter(["Tester", "AAAA-BBBB-CCCC", "new-password"])
                    calls = 0

                    def answer(*_args, **_kwargs):
                        nonlocal calls
                        if calls == prompt:
                            # A hosting-ready event can update the selector in a modal loop.
                            tab.server_var.set("Server-B")
                        calls += 1
                        return next(answers)

                    tab.ask_string.side_effect = answer
                    tab.do_forgot()
                    tab._new_client.assert_called_once_with(expected, "test-build")
                    client = tab._new_client.return_value
                    client.recover.return_value = {"name": "Tester", "codes_left": 9}
                    work = tab.call.call_args.args[0]
                    self.assertEqual(work(), {"name": "Tester", "codes_left": 9})
                    client.connect.assert_called_once_with()
                    client.recover.assert_called_once_with("Tester", "AAAA-BBBB-CCCC", "new-password")
                    client.close.assert_called_once_with()

    def test_cancelled_prompt_does_not_create_client(self):
        for prompt in range(3):
            with self.subTest(prompt=prompt):
                tab = controller()
                answers = ["Tester", "AAAA-BBBB-CCCC", "new-password"]
                answers[prompt] = None
                tab.ask_string.side_effect = answers
                tab.do_forgot()
                tab._new_client.assert_not_called()
                tab.call.assert_not_called()


if __name__ == "__main__":
    unittest.main()
