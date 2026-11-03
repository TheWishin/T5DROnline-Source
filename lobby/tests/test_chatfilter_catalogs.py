"""Chat-filter notices remain ordinary, translatable server errors for every language."""
import unittest

import util  # noqa: F401 (sets sys.path)
from t5lobby import i18n, i18n_known


NOTICES = (
    "Message blocked: hate terms are not allowed.",
    "This name is not allowed.",
    "This room name is not allowed.",
    "Chat is muted for this account.",
    "Cannot load the chat filter. Check T5L_CHAT_FILTER_PATH.",
)


class ChatFilterCatalogTest(unittest.TestCase):
    def test_server_notices_are_known_and_translated_in_every_catalog(self):
        original = i18n.language()
        self.addCleanup(i18n.set_language, original)
        for message in NOTICES:
            with self.subTest(message=message):
                self.assertIn(message, i18n_known.SERVER)
        for language in i18n.LANGUAGES:
            i18n.set_language(language)
            for message in NOTICES:
                with self.subTest(language=language, message=message):
                    translated = i18n.translate_message(message)
                    if language == "en":
                        self.assertEqual(translated, message)
                    else:
                        self.assertIn(message, i18n.catalog(language))
                        self.assertEqual(translated, i18n.catalog(language)[message])
                        self.assertNotEqual(translated, message)


if __name__ == "__main__":
    unittest.main()
