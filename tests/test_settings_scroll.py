"""The Settings tab scrolls (launcher/t5dr_launcher.pyw, VScroll): it is taller than the window at 133 % display
scaling and more (even at 100 % with all its boxes), so without scrolling the bottom of it -- Unlocks, the Controls
table -- could not be reached. The mouse wheel over any part of it scrolls it, a control that gets the focus is
scrolled into view, and it never scrolls sideways.

Withdrawn windows only (nothing on screen): positions a mapped window would have are given to the code under test
where it needs them. tests/i18n_layout.py checks the real tab in every language at 100, 133 and 150 %.
"""
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(ROOT, "tests") not in sys.path:
    sys.path.insert(0, os.path.join(ROOT, "tests"))

try:
    import tkinter as tk
    from tkinter import ttk

    import i18n_layout
except ImportError:          # (no tkinter in this Python)
    tk = None


@unittest.skipIf(tk is None, "no tkinter")
class VScrollTests(unittest.TestCase):
    """The scrolling area on its own: 40 buttons, a text box, in a withdrawn window."""

    @classmethod
    def setUpClass(cls):
        cls.mod = i18n_layout.load_launcher()

    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as e:
            self.skipTest(f"no display for Tk: {e}")
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        frame = ttk.Frame(self.root)
        frame.pack(fill="both", expand=True)
        self.area = self.mod.VScroll(frame)
        self.buttons = [ttk.Button(self.area.inner, text=f"button {i}") for i in range(40)]
        for b in self.buttons:
            b.pack(anchor="w")
        self.text = tk.Text(self.area.inner, height=3, width=20)
        self.text.pack()
        self.area.adopt()
        self.root.update_idletasks()
        self.area.refresh()
        self.height = self.area.inner.winfo_reqheight()

    def top(self):
        return self.area.canvas.canvasy(0)

    def wheel(self, widget, notches):
        widget.event_generate("<MouseWheel>", delta=-120 * notches)

    def test_the_region_is_all_of_the_content(self):
        inner = self.area.inner
        self.assertEqual([float(v) for v in str(self.area.canvas.cget("scrollregion")).split()],
                         [0, 0, inner.winfo_reqwidth(), inner.winfo_reqheight()])
        self.assertEqual(int(self.area.canvas.cget("width")), inner.winfo_reqwidth())
        self.assertGreater(self.height, 800)

    def test_the_wheel_scrolls_the_page_from_any_control(self):
        self.wheel(self.buttons[3], 1)
        self.assertEqual(self.top(), self.area.step)
        self.wheel(self.text, 2)                 # (over the text box too: the page, not the box)
        self.assertEqual(self.top(), 3 * self.area.step)
        self.wheel(self.area.bar, -1)            # (and over the scrollbar)
        self.assertEqual(self.top(), 2 * self.area.step)
        self.wheel(self.buttons[0], -10)
        self.assertEqual(self.top(), 0)          # not above the top

    def test_the_wheel_reaches_the_last_pixel(self):
        for _ in range(200):
            self.wheel(self.buttons[-1], 3)
        self.assertEqual(self.area.canvas.yview()[1], 1.0)
        self.assertEqual(self.top(), self.height - self.area.canvas.winfo_height())

    def test_a_focused_control_is_scrolled_into_view(self):
        canvas, inner, b = self.area.canvas, self.area.inner, self.buttons[30]
        view_h, h = 300, 30                      # where a mapped window would have them
        at = {"y": 700}
        with mock.patch.object(canvas, "winfo_height", lambda: view_h), \
                mock.patch.object(inner, "winfo_rooty", lambda: 100 - int(self.top())), \
                mock.patch.object(b, "winfo_rooty", lambda: 100 - int(self.top()) + at["y"]), \
                mock.patch.object(b, "winfo_height", lambda: h):
            b.event_generate("<FocusIn>")        # below the view: its bottom (and a margin) at the bottom
            self.assertEqual(self.top(), at["y"] + h + self.area.margin - view_h)
            before = self.top()
            b.event_generate("<FocusIn>")        # in view: nothing moves
            self.assertEqual(self.top(), before)
            self.area.scroll_to(self.height)
            self.assertEqual(self.top(), self.height - view_h)
            at["y"] = 300
            b.event_generate("<FocusIn>")        # above the view: its top (and a margin) at the top
            self.assertEqual(self.top(), at["y"] - self.area.margin)

    def test_never_sideways(self):
        canvas = self.area.canvas
        self.assertEqual(str(canvas.cget("xscrollcommand")), "")
        canvas.event_generate("<Configure>", width=500, height=300)
        self.assertEqual(int(float(canvas.itemcget(self.area.item, "width"))), 500)

    def test_a_control_added_later_gets_the_wheel_too(self):
        late = ttk.Button(self.area.inner, text="late")
        late.pack()
        self.assertNotIn(self.area.tag, late.bindtags())
        self.area.adopt(late)
        self.assertEqual(late.bindtags()[0], self.area.tag)
        self.wheel(late, 1)
        self.assertEqual(self.top(), self.area.step)


@unittest.skipIf(tk is None, "no tkinter")
class SettingsTabTests(unittest.TestCase):
    """The real launcher's Settings tab (built withdrawn by tests/i18n_layout.py) at 100, 133 and 150 %."""

    def look(self, walk):
        app = walk.app
        area = app.settings_scroll
        self.assertEqual(i18n_layout.scroll_problems(area), [])
        tab = app.tabs["settings"]
        self.assertEqual(set(tab.winfo_children()), {area.canvas, area.bar})     # all of it inside the area
        last = area.inner
        while last.winfo_children():             # the deepest last widget: the Controls box's last note
            last = last.winfo_children()[-1]
        for _ in range(100):
            last.event_generate("<MouseWheel>", delta=-360)
        self.assertEqual(area.canvas.yview()[1], 1.0)
        self.found.append((walk.scale, area.inner.winfo_reqheight()))

    def test_every_scale(self):
        for scale in i18n_layout.SCALES:
            self.found = []
            walk = i18n_layout.Walk("en", scale)
            try:
                with mock.patch.object(i18n_layout.Walk, "_online", lambda w: self.look(w)), \
                        mock.patch.object(i18n_layout.Walk, "_windows", lambda w, d: None):
                    walk.run()
            except tk.TclError as e:
                self.skipTest(f"no display for Tk: {e}")
            with self.subTest(scale=scale):
                self.assertEqual(walk.shown, [])
                self.assertEqual(len(self.found), 1)
                # taller than the window's room (the reason it scrolls), at every scale
                self.assertGreater(self.found[0][1], i18n_layout.SCREEN_H - 80 if scale > 100 else 840)


if __name__ == "__main__":
    unittest.main()
