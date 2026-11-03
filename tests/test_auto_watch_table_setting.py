"""Watching the room's table while waiting (docs/SPECTATE.md "Automatically watch your room's table"): on by
default, kept between launches, offered in Settings and in every launcher language."""
import ast
import json
import os
import string
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(ROOT, "launcher") not in sys.path:
    sys.path.append(os.path.join(ROOT, "launcher"))
import core

LOBBY = os.path.join(ROOT, "lobby", "t5lobby")
TEXTS = ("Automatically watch",
         "Automatically watch the match at my room's table while I wait for my turn",
         "Not while the game is being built.",
         "Not while your own game is open: it stays ready so your next match starts quickly.",
         "Your room's matches are shown automatically while you wait.",
         "Your room's matches are no longer shown automatically.")


def literal(path, name):
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError(f"{path}: no {name}")


class AutoWatchTableSettingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "launcher.json")

    def test_on_for_new_and_older_settings(self):
        self.assertIs(core.Settings(self.path)["auto_watch_table"], True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"spectators": True, "auto_spectate": False}, f)
        self.assertIs(core.Settings(self.path)["auto_watch_table"], True)

    def test_choice_is_remembered(self):
        for on in (False, True):
            s = core.Settings(self.path)
            s["auto_watch_table"] = on
            s.save()
            self.assertIs(core.Settings(self.path)["auto_watch_table"], on)
            self.assertIs(core.Settings(self.path)["auto_spectate"], False)   # the lobby-wide one stays off

    def test_a_broken_value_means_the_default(self):
        for bad in ("false", 0, None, [], {}):
            with self.subTest(value=bad):
                with open(self.path, "w", encoding="utf-8") as f:
                    json.dump({"auto_watch_table": bad}, f)
                self.assertIs(core.Settings(self.path)["auto_watch_table"], True)

    def test_settings_box_is_saved(self):
        with open(os.path.join(ROOT, "launcher", "t5dr_launcher.pyw"), encoding="utf-8") as f:
            tree = ast.parse(f.read())
        texts = {n.args[0].value for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                 and n.func.id == "t" and n.args and isinstance(n.args[0], ast.Constant)}
        self.assertIn(TEXTS[1], texts)
        save = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "save_settings")
        self.assertTrue(any(isinstance(n, ast.Subscript) and isinstance(n.ctx, ast.Store)
                            and isinstance(n.slice, ast.Constant) and n.slice.value == "auto_watch_table"
                            for n in ast.walk(save)))

    def test_every_catalog_has_the_texts(self):
        catalogs = literal(os.path.join(LOBBY, "i18n.py"), "CATALOGS")
        fields = lambda text: {f for _, f, _, _ in string.Formatter().parse(text) if f is not None}  # noqa: E731
        for lang, module in catalogs.items():
            cat = literal(os.path.join(LOBBY, module + ".py"), "MESSAGES")
            for key in TEXTS:
                with self.subTest(lang=lang, text=key):
                    self.assertTrue(cat.get(key, "").strip())
                    self.assertNotEqual(cat[key], key)
                    self.assertEqual(fields(cat[key]), fields(key))


if __name__ == "__main__":
    unittest.main()
