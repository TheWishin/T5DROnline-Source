"""Static documentation contracts; never import a client or open sockets."""
import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def maximum_list_length(node):
    if isinstance(node, ast.List):
        return len(node.elts)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return maximum_list_length(node.left) + maximum_list_length(node.right)
    if isinstance(node, ast.IfExp):
        return max(maximum_list_length(node.body), maximum_list_length(node.orelse))
    raise AssertionError(f"unrecognized capability expression: {ast.dump(node)}")


class IntegrationCapabilityDocumentation(unittest.TestCase):
    def test_guests_only_hosting_discloses_private_report_storage(self):
        document = (ROOT / "docs/HOSTING.md").read_text(encoding="utf-8")
        self.assertNotIn("stores nothing about people except unranked match records", document)
        self.assertIn("Guests can also submit selected private-chat reports", document)
        self.assertIn("`purge-guests` does not delete private reports", document)
        self.assertIn("[private-report retention policy](PRIVATE_CHAT.md)", document)

    def test_fully_enabled_capability_count_matches_client(self):
        tree = ast.parse((ROOT / "lobby/t5lobby/client.py").read_text(encoding="utf-8"))
        hello = next(node for node in ast.walk(tree) if isinstance(node, ast.Dict)
                     and any(isinstance(key, ast.Constant) and key.value == "t"
                             and isinstance(value, ast.Constant) and value.value == "hello"
                             for key, value in zip(node.keys, node.values)))
        caps = next(value for key, value in zip(hello.keys, hello.values)
                    if isinstance(key, ast.Constant) and key.value == "caps")
        count = maximum_list_length(caps)
        self.assertLessEqual(count, 32)
        document = (ROOT / "docs/INTEGRATION_1.2.0.md").read_text(encoding="utf-8")
        self.assertIn(f"Fully enabled clients now send **{count}**", document)
        self.assertIn("`compat_groups`, `private_chat` and `mutes`", document)


if __name__ == "__main__":
    unittest.main()
