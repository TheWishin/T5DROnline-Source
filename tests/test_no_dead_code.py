"""No statement after a return / raise / continue / break in the same block, in the launcher, the lobby client and
the tools (1.1.7 shipped without the chat's input row: a method was added in the middle of the chat card's build,
and the lines after its `return` never ran -- no test drove that input)."""
import ast
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FOLDERS = ("launcher", os.path.join("lobby", "t5lobby"), "tools")


def unreachable(path):
    """[(line, what)] of statements that follow a return/raise/continue/break in the same block."""
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read(), path)
    out = []
    for node in ast.walk(tree):
        for field in ("body", "orelse", "finalbody", "handlers"):
            block = getattr(node, field, None)
            if not isinstance(block, list):
                continue
            for st, nxt in zip(block, block[1:]):
                if isinstance(st, (ast.Return, ast.Raise, ast.Continue, ast.Break)):
                    out.append((nxt.lineno, f"after the {type(st).__name__.lower()} in line {st.lineno}"))
    return out


class DeadCode(unittest.TestCase):
    def test_nothing_after_a_return(self):
        found = []
        for folder in FOLDERS:
            for dp, _dirs, files in os.walk(os.path.join(ROOT, folder)):
                for name in files:
                    if name.endswith((".py", ".pyw")):
                        p = os.path.join(dp, name)
                        found += [f"{os.path.relpath(p, ROOT)}:{line} {what}" for line, what in unreachable(p)]
        self.assertEqual(found, [], "code that never runs")

    def test_the_check_finds_it(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x.py")
            with open(p, "w", encoding="utf-8") as f:
                f.write("def f():\n    return 1\n    print('never')\n")
            self.assertEqual([line for line, _ in unreachable(p)], [3])


if __name__ == "__main__":
    unittest.main()
