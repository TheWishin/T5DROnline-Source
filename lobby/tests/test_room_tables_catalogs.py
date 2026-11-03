"""Room table texts reach every language without a client, server, game or Tk window."""
import string
import unittest

import util  # noqa: F401 -- repository import path and safe test environment
from t5lobby import i18n


UI_TEXTS = (
    "One match, taking turns", "Several matches at once", "Room format:", "Tables...",
    "Room tables", "Table {table}: {players}", "Empty table", "Available: {names}",
    "Away: {names}", "Table:", "Player 1:", "Player 2:", "Set pair", "Watch table",
    "Select two different available players.", "Select a table.", "Available to play",
    "You are away until you press Available to play.", "You are available for a free table.",
)
MESSAGE_TEXTS = (
    "mode is line or tables",
    "table is 1 to {count}",
    "this server has no simultaneous room tables",
    "simultaneous room tables need a newer launcher; update it",
    "simultaneous room tables are casual and cannot be training rooms",
    "this room does not have simultaneous tables",
    "choose two different players for the table",
    "choose available players and an idle table",
    "you cannot pair these players",
)


def fields(text):
    return sorted(name for _literal, name, _format, _conversion in string.Formatter().parse(text)
                  if name is not None)


class RoomTableCatalogTest(unittest.TestCase):
    def setUp(self):
        self.old_language = i18n.language()
        self.addCleanup(i18n.set_language, self.old_language)

    def test_table_controls_exist_and_format_in_every_catalog(self):
        for lang in i18n.CATALOGS:
            catalog = i18n.catalog(lang)
            for text in UI_TEXTS + MESSAGE_TEXTS:
                with self.subTest(language=lang, text=text):
                    self.assertIn(text, catalog)
                    translated = catalog[text]
                    self.assertEqual(fields(text), fields(translated))
                    self.assertTrue(translated.strip())
                    translated.format(**{name: "Player" for name in fields(text)})

    def test_server_and_client_refusals_are_known_messages_in_every_language(self):
        for lang in i18n.CATALOGS:
            i18n.set_language(lang)
            for text in MESSAGE_TEXTS:
                with self.subTest(language=lang, text=text):
                    values = {name: "4" for name in fields(text)}
                    message = text.format(**values)
                    self.assertNotEqual(i18n.translate_message(message), message)
                    self.assertEqual(i18n.translate_message(message), i18n.catalog(lang)[text].format(**values))


if __name__ == "__main__":
    unittest.main()
