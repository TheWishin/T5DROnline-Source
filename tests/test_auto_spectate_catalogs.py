"""The opt-in idle watching setting is translated in every launcher language.

Reads catalogs as syntax only: no launcher, game, Tk window or network connection.
"""
import ast
from pathlib import Path
import string
import unittest


ROOT = Path(__file__).resolve().parents[1]
LOBBY = ROOT / "lobby" / "t5lobby"
KEY = "Automatically watch matches while idle"


def literal_assignment(path, name):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == name for target in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError(f"{path.name}: no literal {name} assignment")


class AutoSpectateCatalogs(unittest.TestCase):
    def test_setting_has_a_translation_in_every_catalog(self):
        catalogs = literal_assignment(LOBBY / "i18n.py", "CATALOGS")
        for language, module in catalogs.items():
            with self.subTest(language=language):
                catalog = literal_assignment(LOBBY / (module + ".py"), "MESSAGES")
                self.assertIn(KEY, catalog)
                self.assertTrue(catalog[KEY].strip())
                self.assertNotEqual(catalog[KEY], KEY)
                fields = lambda text: {field for _, field, _, _ in string.Formatter().parse(text)
                                       if field is not None}
                self.assertEqual(fields(catalog[KEY]), fields(KEY))


if __name__ == "__main__":
    unittest.main()
