"""Static 1.2.0 catalog regressions: no launcher imports, game, build or network.

The complete extraction suite lives in test_i18n.py. These checks can also run
on a machine without Tk or native build tools and cover the new settings and
first-start/prebuild messages, including their formatting placeholders.
"""
import ast
from pathlib import Path
import string
import unittest


ROOT = Path(__file__).resolve().parents[1]
CATALOGS = ("de", "es", "fr", "ja", "ko", "pt_br")
REQUIRED = {
    "Screen side", "As dealt", "Always left", "Always right",
    "Casual matches only: show your fighter on the chosen side and swap left/right controls when mirrored. "
    "Ranked and Quick matches keep the dealt side. Offline: Versus previews the chosen side.",
    "Launcher button bindings and macros take priority over the game's Controller Setup. "
    "Set them in Settings > Set up controllers… in the launcher.",
    "Graphics compatibility warning",
    "Could not stop the shader warm-up",
    "This PC lists older Intel graphics ({gpus}). Intel HD 4400-class graphics may lack a working Direct3D 12 "
    "driver and may not run the game. Building the game does not add graphics support. If this PC has another "
    "graphics card, select it in Windows Graphics settings. Continue building?",
}


def catalog(lang):
    path = ROOT / "lobby" / "t5lobby" / f"i18n_{lang}.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    assignment = next(node for node in tree.body if isinstance(node, ast.Assign)
                      and any(isinstance(target, ast.Name) and target.id == "MESSAGES"
                              for target in node.targets))
    keys = [ast.literal_eval(key) for key in assignment.value.keys]
    return ast.literal_eval(assignment.value), keys


def fields(text):
    return sorted(name for _, name, _, _ in string.Formatter().parse(text) if name is not None)


class Release120Catalogs(unittest.TestCase):
    def test_new_player_text_is_translated_in_every_catalog(self):
        for lang in CATALOGS:
            messages, _ = catalog(lang)
            for key in REQUIRED:
                with self.subTest(lang=lang, key=key):
                    self.assertIn(key, messages)
                    self.assertTrue(messages[key].strip())
                    self.assertNotEqual(messages[key], key)
                    self.assertEqual(fields(messages[key]), fields(key))

    def test_no_duplicate_keys_hide_a_translation(self):
        for lang in CATALOGS:
            _, keys = catalog(lang)
            for key in REQUIRED:
                with self.subTest(lang=lang, key=key):
                    self.assertEqual(keys.count(key), 1)


if __name__ == "__main__":
    unittest.main()
