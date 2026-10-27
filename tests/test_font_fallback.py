"""The launcher's layout without its fonts (1.1.7): on Wine / Proton or an old Windows 10 without Bahnschrift (and
without Segoe UI), Tk draws the texts in wider faces, and es / fr / pt-BR texts were cut off in 1 to 43 places.
theme.width_factor draws such a stand-in smaller by how much wider it is, so every text keeps the room the layout
has for it. The cut-off walk of tests/i18n_layout.py (the real launcher, withdrawn) with the faces hidden from Tk:
nothing cut off in any language at 100 % and 150 %."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

try:
    import tkinter as tk
    import tkinter.font as tkfont
except ImportError:      # pragma: no cover
    tk = None


def _have(*families):
    try:
        r = tk.Tk()
    except tk.TclError:
        return False
    try:
        fams = set(tkfont.families(r))
    finally:
        r.destroy()
    return all(f in fams for f in families)


@unittest.skipIf(tk is None or os.name != "nt", "Windows with tkinter")
class WithoutTheLaunchersFonts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not _have("Segoe UI", "Bahnschrift SemiBold Condensed"):
            raise unittest.SkipTest("needs Segoe UI and Bahnschrift to hide them")
        import i18n_layout
        cls.layout = i18n_layout

    def check(self, hidden, langs, scales=(100, 150)):
        for scale in scales:
            english = self.layout.Walk("en", scale, hidden).run()
            with self.subTest(lang="en", scale=scale, hidden=hidden):
                self.assertEqual(self.layout.compare(english), [])
            for lang in langs:
                with self.subTest(lang=lang, scale=scale, hidden=hidden):
                    w = self.layout.Walk(lang, scale, hidden).run()
                    self.assertEqual(self.layout.compare(w, english), [],
                                     f"cut off in {lang} at {scale} % without {hidden}")

    def test_without_bahnschrift_and_segoe_ui_every_language(self):
        self.check(("Bahnschrift", "Segoe UI"), ("de", "es", "fr", "pt-BR", "ja", "ko"))

    def test_without_bahnschrift(self):
        # (R's finding: es / fr / pt-BR were cut off in 1 to 43 places)
        self.check(("Bahnschrift",), ("es", "fr", "pt-BR"))

    def test_width_factor(self):
        from t5lobby import theme
        r = tk.Tk()
        self.addCleanup(r.destroy)
        self.assertGreater(theme.width_factor(r, "Bahnschrift SemiBold Condensed", "display"), 0.995)   # ours
        k = theme.width_factor(r, "Segoe UI Semibold", "display")             # the usual stand-in: much wider
        self.assertTrue(0.6 < k < 0.8, k)
        self.assertGreater(theme.width_factor(r, "Bahnschrift Light Condensed", "display"), 0.995)   # narrower
        self.assertLess(theme.width_factor(r, "Verdana", "text"), 0.95)


if __name__ == "__main__":
    unittest.main()
