"""Widgets drawn over each other (1.1.7): 1.1.6's Online tab put "Strict (ranked: +-150 rating)" at the left and
the casual side / stage row at the right of the same grid cells; in German and Japanese they ran into each other at
100 % and 150 %. The cut-off walk (tests/i18n_layout.py) now also reports two widgets of one grid row whose
columns overlap and that need more than the row has ("overlap"), and the row moves below "Strict" when both do not
fit (tk_views.place_casual_row)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import tkinter as tk
    from tkinter import ttk
except ImportError:      # pragma: no cover
    tk = None


@unittest.skipIf(tk is None, "no tkinter")
class Overlap(unittest.TestCase):
    def test_the_check_sees_an_overlap(self):
        import i18n_layout
        try:
            root = tk.Tk()
        except tk.TclError as e:
            self.skipTest(f"no display: {e}")
        self.addCleanup(root.destroy)
        root.withdraw()
        f = ttk.Frame(root)
        f.pack()
        f.columnconfigure(0, weight=1)
        ttk.Button(f, text="x" * 30).grid(row=0, column=0)                  # what makes the frame this wide
        left = ttk.Label(f, text="a left label of some length")
        right = ttk.Label(f, text="and a right one, also long enough")
        left.grid(row=1, column=0, sticky="w")
        right.grid(row=1, column=0, sticky="e")
        root.update_idletasks()
        found = [p for p in i18n_layout.problems(root) if p[0] == "overlap"]
        self.assertEqual(len(found), 1, found)
        right.grid_configure(row=2)                                          # on a row of its own: fine
        root.update_idletasks()
        self.assertEqual([p for p in i18n_layout.problems(root) if p[0] == "overlap"], [])
        right.configure(text="x")                                            # short enough to share the row
        right.grid_configure(row=1)
        root.update_idletasks()
        self.assertEqual([p for p in i18n_layout.problems(root) if p[0] == "overlap"], [])

    def test_strict_and_the_casual_row_never_overlap(self):
        import i18n_layout
        for lang in ("de", "ja", "en"):
            for scale in (100, 150):
                with self.subTest(lang=lang, scale=scale):
                    w = i18n_layout.Walk(lang, scale).run()
                    self.assertEqual([k for k in w.cut if k[1] == "overlap"], [])
                    self.assertIn("online lobby", w.screens)


if __name__ == "__main__":
    unittest.main()
