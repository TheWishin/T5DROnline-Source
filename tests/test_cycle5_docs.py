"""Static documentation regressions; no project imports or network activity."""
import ast
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


class GuestMuteLimitDocumentation(unittest.TestCase):
    def test_distinguishes_server_limit_from_fixed_local_guest_limit(self):
        tree = ast.parse((ROOT / "lobby/t5lobby/client.py").read_text(encoding="utf-8"))
        mute = next(node for node in ast.walk(tree)
                    if isinstance(node, ast.FunctionDef) and node.name == "_mute")
        local_limit = next(
            node.comparators[0].value for node in ast.walk(mute)
            if isinstance(node, ast.Compare) and len(node.ops) == 1
            and isinstance(node.ops[0], ast.GtE)
            and isinstance(node.left, ast.Call)
            and isinstance(node.left.func, ast.Name) and node.left.func.id == "len"
            and len(node.left.args) == 1 and isinstance(node.left.args[0], ast.Name)
            and node.left.args[0].id == "rows"
            and isinstance(node.comparators[0], ast.Constant))
        document = (ROOT / "docs/PRIVATE_CHAT.md").read_text(encoding="utf-8")
        text = re.sub(r"\s+", " ", document)
        self.assertIn("Server mute lists use `T5L_MAX_BLOCKS`", text)
        self.assertIn(f"launcher keeps at most {local_limit} local guest names", text)
        self.assertIn("even if the server sets a different limit", text)


if __name__ == "__main__":
    unittest.main()
