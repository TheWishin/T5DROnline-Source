"""Computed translation keys through their production callers, without a server or game."""
import gc
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[1]
for directory in ("launcher", "lobby"):
    sys.path.insert(0, str(ROOT / directory))

import core  # noqa: E402
import first_start  # noqa: E402
import gpu_error  # noqa: E402
from t5lobby import i18n  # noqa: E402

try:
    import tkinter as tk
except ImportError:
    tk = None


class ComputedTranslations(unittest.TestCase):
    def setUp(self):
        self.addCleanup(i18n.set_language, i18n.language())

    def test_advice_and_first_start_hint_in_every_catalog(self):
        for language in i18n.CATALOGS:
            with self.subTest(language=language):
                i18n.set_language(language)
                i18n.clear_missing()
                catalog = i18n.catalog(language)
                advice = core.explain_exit(12, [], gpu_adapter="Intel HD Graphics 4400")
                self.assertEqual(advice, catalog[gpu_error.HD4400_ADVICE])
                self.assertNotEqual(advice, gpu_error.HD4400_ADVICE)

                shown, saved = [], []
                settings = {}
                self.assertTrue(first_start.show_controls_hint(
                    settings, shown.append, lambda: saved.append(dict(settings))))
                self.assertEqual(shown, [catalog[first_start.CONTROLS_HINT]])
                self.assertNotEqual(shown[0], first_start.CONTROLS_HINT)
                self.assertEqual(saved, [{first_start.CONTROLS_HINT_KEY: True}])
                self.assertEqual(i18n.missing(), [])

    @unittest.skipIf(tk is None, "no tkinter")
    def test_private_chat_computed_button_labels_in_every_catalog(self):
        from t5lobby.tk_private_chat import PrivateChat

        try:
            root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"no display: {error}")
        root.withdraw()

        def new_window(parent):
            window = tk.Toplevel(parent)
            window.withdraw()
            return window

        chat = default = inbox = None
        try:
            for language in i18n.CATALOGS:
                with self.subTest(language=language):
                    i18n.set_language(language)
                    i18n.clear_missing()
                    catalog = i18n.catalog(language)
                    chat = PrivateChat(SimpleNamespace(parent=root, new_window=new_window))
                    default = chat.button(root, lambda: None)
                    inbox = chat.button(root, lambda: None, "Private messages")
                    self.assertEqual(str(default.cget("text")), catalog["Message player"])
                    self.assertEqual(str(inbox.cget("text")), catalog["Private messages"])
                    chat.build()
                    self.assertEqual([str(button.cget("text")) for button in chat.controls],
                                     [catalog[key] for key in
                                      ("Send", "Mute", "Block player", "Report selected lines")])
                    self.assertEqual(chat.window.state(), "withdrawn")
                    self.assertEqual(i18n.missing(), [])
                    chat.close()
                    default.destroy()
                    inbox.destroy()
                    chat = default = inbox = None
        finally:
            if chat is not None:
                chat.close()
            root.destroy()
            chat = default = inbox = root = None
            gc.collect()


if __name__ == "__main__":
    unittest.main()
