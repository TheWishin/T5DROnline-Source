"""Release notice translations checked from source, without clients or sockets."""
import ast
from pathlib import Path
import string
import unittest


LOBBY = Path(__file__).resolve().parents[1] / "lobby" / "t5lobby"
NOTICE = ('T5DR Online {latest} is out. Update the launcher (it offers the update '
          'when it starts, or press "Check for updates").')


class ReleaseNoticeCatalogs(unittest.TestCase):
    def test_notice_is_known_and_translated_in_every_language(self):
        known = ast.parse((LOBBY / "i18n_known.py").read_text(encoding="utf-8"))
        server = next(node.value for node in known.body if isinstance(node, ast.Assign)
                      and any(isinstance(target, ast.Name) and target.id == "SERVER"
                              for target in node.targets))
        self.assertIn(NOTICE, [ast.literal_eval(node.args[0]) for node in server.elts])
        for language in ("de", "es", "fr", "ja", "ko", "pt_br"):
            with self.subTest(language=language):
                tree = ast.parse((LOBBY / f"i18n_{language}.py").read_text(encoding="utf-8"))
                node = next(item.value for item in tree.body if isinstance(item, ast.Assign)
                            and any(isinstance(target, ast.Name) and target.id == "MESSAGES"
                                    for target in item.targets))
                messages = ast.literal_eval(node)
                self.assertEqual([ast.literal_eval(key) for key in node.keys].count(NOTICE), 1)
                translation = messages[NOTICE]
                self.assertTrue(translation.strip())
                self.assertNotEqual(translation, NOTICE)
                fields = [field for _, field, _, _ in string.Formatter().parse(translation)
                          if field is not None]
                self.assertEqual(fields, ["latest"])


if __name__ == "__main__":
    unittest.main()
