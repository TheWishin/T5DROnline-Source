"""Personal-mute UI copy is translated with matching placeholders in every catalog."""
import ast
from pathlib import Path
import string
import unittest

import util  # noqa: F401 -- sets the lobby import path; no server is started
from t5lobby import i18n


MUTE_TEXTS = (
    "Chat is muted until {until}.",
    "Personal mute is unavailable on this server.",
    "Muted players...",
    "Muted players",
    "Mute",
    "Unmute",
    "Muted {name}.",
    "Unmuted {name}.",
    "Mute hides their lobby, room and private chat, mentions and invites for you. You can still play together. Block also prevents matches and ends friendship. Accounts remember mutes on this server; guests remember them on this device.",
    "Mute hides this player's chat, mentions and invites for you. Block also prevents matches and private messages.",
)


def fields(text):
    return {field for _, field, _, _ in string.Formatter().parse(text)
            if field is not None}


class MuteCatalogTest(unittest.TestCase):
    def test_every_catalog_translates_personal_mute_actions_and_explanation(self):
        original = i18n.language()
        self.addCleanup(i18n.set_language, original)
        for language in i18n.LANGUAGES:
            i18n.set_language(language)
            for message in MUTE_TEXTS:
                with self.subTest(language=language, message=message):
                    translated = i18n.t(message)
                    if language == "en":
                        self.assertEqual(translated, message)
                    else:
                        self.assertIn(message, i18n.catalog(language))
                        self.assertNotEqual(translated, message)
                    self.assertEqual(fields(translated), fields(message))

    def test_mute_entries_do_not_shadow_other_catalog_entries(self):
        directory = Path(i18n.__file__).parent
        for module in i18n.CATALOGS.values():
            tree = ast.parse((directory / (module + ".py")).read_text(encoding="utf-8"))
            messages = next(node.value for node in tree.body
                            if isinstance(node, ast.Assign)
                            and any(isinstance(target, ast.Name) and target.id == "MESSAGES"
                                    for target in node.targets))
            keys = [node.value for node in messages.keys if isinstance(node, ast.Constant)]
            for message in MUTE_TEXTS:
                with self.subTest(module=module, message=message):
                    self.assertEqual(keys.count(message), 1)


if __name__ == "__main__":
    unittest.main()
