"""Native clipping and lifetime controls for the layout walk's measurements."""
import gc
import unittest
from unittest import mock

try:
    import tkinter as tk
    from tkinter import font as tkfont, ttk
except ImportError:  # pragma: no cover
    tk = None


@unittest.skipIf(tk is None, "no tkinter")
class LayoutMeasurements(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            if "no display" in str(error).lower() or "couldn't connect to display" in str(error).lower():
                self.skipTest(str(error))
            raise
        self.addCleanup(self.root.destroy)
        self.root.withdraw()
        self.fonts = []

    def font(self, size=10):
        font = tkfont.Font(root=self.root, family="Arial", size=size)
        self.fonts.append(font)
        return font

    def cuts(self, widget):
        import i18n_layout
        self.root.update_idletasks()
        return [cut for cut in i18n_layout.problems(self.root) if cut[1] == str(widget)]

    def check_temporary_font_lifetime(self, fail=False):
        import i18n_layout
        label = ttk.Label(self.root, text="Wide text " * 8, font=self.font(), width=2)
        label.pack()
        # Fail after the label has been measured and its traversal has returned.
        # This keeps an exception traceback from retaining that active frame's
        # own local font independently of the checker's screen cache.
        last = ttk.Frame(self.root)
        last.pack()
        self.root.update_idletasks()
        gc.collect()
        enabled = gc.isenabled()
        gc.disable()
        try:
            before = set(self.root.tk.call("font", "names"))
            if fail:
                with mock.patch.object(last, "winfo_class", side_effect=RuntimeError("late traversal failure")):
                    with self.assertRaisesRegex(RuntimeError, "late traversal failure"):
                        i18n_layout.problems(self.root)
            else:
                self.assertTrue(i18n_layout.problems(self.root))
            after = set(self.root.tk.call("font", "names"))
            self.assertEqual(after, before, "checker fonts must be released before cyclic GC")
        finally:
            if enabled:
                gc.enable()
            gc.collect()

    def test_temporary_fonts_released_without_cyclic_gc(self):
        self.check_temporary_font_lifetime()

    def test_temporary_fonts_released_after_traversal_error(self):
        self.check_temporary_font_lifetime(fail=True)

    def test_multiline_label_tracks_width_text_and_named_font(self):
        font = self.font()
        text = "short\n" + "Wide text " * 8
        label = ttk.Label(self.root, text=text, font=font, width=2)
        label.pack()
        cuts = self.cuts(label)
        self.assertEqual([cut[0] for cut in cuts], ["fixed"])
        self.assertEqual(cuts[0][3], font.measure(text.split("\n")[1]))
        before = cuts[0][3]
        font.configure(size=20)
        self.assertGreater(self.cuts(label)[0][3], before)
        label.configure(width=150)
        self.assertEqual(self.cuts(label), [])
        label.configure(width=2, text="i")
        self.assertEqual(self.cuts(label), [])
        label.configure(text=text)
        self.assertEqual([cut[0] for cut in self.cuts(label)], ["fixed"])

    def test_tree_headings_and_cells_follow_style_font_changes(self):
        heading, body = self.font(), self.font()
        style = ttk.Style(self.root)
        style.configure("Measurement.Treeview", font=body)
        style.configure("Measurement.Treeview.Heading", font=heading)
        tree = ttk.Treeview(self.root, columns=("value",), show="headings",
                            style="Measurement.Treeview")
        tree.pack()
        text = "Wide sample"
        tree.heading("value", text=text)
        row = tree.insert("", "end", values=(text,))
        tree.column("value", width=20, minwidth=0, stretch=False)
        self.assertEqual({cut[0] for cut in self.cuts(tree)}, {"heading", "cell"})
        tree.column("value", width=max(heading.measure(text), body.measure(text)) + 30)
        self.assertEqual(self.cuts(tree), [])
        heading.configure(size=30)
        self.assertEqual([cut[0] for cut in self.cuts(tree)], ["heading"])
        body.configure(size=30)
        self.assertEqual({cut[0] for cut in self.cuts(tree)}, {"heading", "cell"})
        tree.heading("value", text="i")
        tree.set(row, "value", "i")
        self.assertEqual(self.cuts(tree), [])

    def test_combobox_choices_track_width_values_and_font(self):
        font = self.font()
        longest = "Wide choice " * 8
        box = ttk.Combobox(self.root, font=font, values=("short", longest, longest), width=2)
        box.pack()
        cuts = self.cuts(box)
        self.assertEqual([cut[0] for cut in cuts], ["combo"])
        self.assertEqual(cuts[0][5], longest)
        before = cuts[0][3]
        font.configure(size=20)
        self.assertGreater(self.cuts(box)[0][3], before)
        box.configure(width=150)
        self.assertEqual(self.cuts(box), [])
        box.configure(width=4, values=("i", "ii"))
        self.assertEqual(self.cuts(box), [])
        box.configure(values=(longest,))
        self.assertEqual([cut[0] for cut in self.cuts(box)], ["combo"])


if __name__ == "__main__":
    unittest.main()
