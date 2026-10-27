"""The Online tab's character select grid (tk_charsel.py, 1.1.5): the fighter button opens a grid of Random and every
selectable fighter, the chosen one lit, the player's main starred; arrow keys move, Enter / a click / the controller's
Cross picks, Esc / Circle closes; a ranked set's lock greys the button and closes the grid; tab.char_cb keeps the old
list's states."""
import unittest

from util import client

try:
    import tkinter as tk
    from test_tk_tab import TkBase
    from t5lobby import fighters, tk_charsel
except ImportError:      # pragma: no cover
    tk = None
    TkBase = unittest.TestCase


@unittest.skipIf(tk is None, "no tkinter")
class CharSelectTest(TkBase):
    def login(self):
        tab = self.tab
        tab.server_var.set(self.s.addr)
        tab.name_var.set("Picker")
        tab.do_login("guest")
        self.pump(lambda: tab.client is not None and tab.client.me is not None)
        return tab

    def test_grid_pick_and_keys(self):
        tab = self.login()
        sel = tab.charsel
        self.assertEqual(str(tab.char_cb.cget("state")), "readonly")
        self.assertIn("▾", str(sel.button.cget("text")))
        sel.button.invoke()
        self.root.update()
        self.assertTrue(sel.is_open())
        keys = [k for k, _n, _b in sel.tiles]
        self.assertEqual(keys[0], fighters.RANDOM)
        # Random first, then A to Z by the name shown (owner)
        names = {f["key"]: f["name"] for f in tab.table.selectable()}
        self.assertEqual(keys[1:], sorted(names, key=lambda k: names[k].casefold()))
        self.assertEqual(sel.columns, tk_charsel.COLUMNS)                  # (no pictures here: names only)
        lit = [k for k, _n, b in sel.tiles if str(b.cget("style")) == "Card.Accent.TButton"]
        self.assertEqual(lit, [tab._char_key()])
        # arrow keys: right, then down one row (COLUMNS tiles further)
        sel._focus(0)
        self.root.update()
        sel._move(0, 0, 1)
        self.root.update()
        self.assertEqual(sel.focused()[0], keys[1])
        sel._move(1, 1, 0)
        self.root.update()
        self.assertEqual(sel.focused()[0], keys[1 + tk_charsel.COLUMNS])
        # the controller's Cross picks the focused tile
        plan = tab._pad_plan()
        self.assertEqual(set(plan), {"cross", "circle"})
        sent = []
        tab.client.set_char = lambda key: sent.append(key)
        plan["cross"][1]()
        self.pump(lambda: sent)
        self.assertFalse(sel.is_open())
        self.assertEqual(tab._char_key(), keys[1 + tk_charsel.COLUMNS])
        self.assertEqual(sent, [keys[1 + tk_charsel.COLUMNS]])
        self.assertEqual(tab.cfg["char"], keys[1 + tk_charsel.COLUMNS])        # remembered
        self.assertTrue(str(sel.button.cget("text")).startswith(tab.char_var.get()))
        # a click on a tile picks it too; Random is the first tile
        sel.open()
        self.root.update()
        sel.tiles[0][2].invoke()
        self.assertEqual(tab._char_key(), fighters.RANDOM)
        # Esc and Circle close without a change
        sel.open()
        self.root.update()
        tile = sel.tiles[3][2]
        self.assertIn("<Key-Escape>", tile.bind())                       # (a hidden window gets no key events)
        self.assertEqual(sel._escape(), "break")
        self.assertFalse(sel.is_open())
        sel.open()
        tab._pad_plan()["circle"][1]()
        self.assertFalse(sel.is_open())
        self.assertEqual(tab._char_key(), fighters.RANDOM)

    def test_main_is_starred(self):
        tab = self.login()
        tab.client.me["main"] = "lili"
        sel = tab.charsel
        sel.open()
        self.root.update()
        starred = [k for k, _n, b in sel.tiles if str(b.cget("text")).endswith(tk_charsel.STAR)]
        self.assertEqual(starred, ["lili"])
        sel.close()

    def test_pictures_from_the_cache(self):
        import os
        import tempfile
        from t5lobby import fighter_art, rank_art
        tab = self.login()
        sel = tab.charsel
        d = tempfile.mkdtemp(prefix="t5dr-faces")
        for g in range(fighter_art.COUNT):                             # stand-ins: one colour each
            px = bytes((g * 7 % 256, 90, 160, 255)) * (fighter_art.SIZE * fighter_art.SIZE)
            with open(fighter_art.face_path(d, g), "wb") as f:
                f.write(rank_art.png_bytes(px, fighter_art.SIZE, fighter_art.SIZE))
        with open(os.path.join(d, "fighters.json"), "w") as f:
            f.write('{"format": %d, "count": %d}' % (fighter_art.FORMAT, fighter_art.COUNT))
        faces = fighter_art.FACES
        saved = (faces.folder, set(faces.sizes), dict(faces.images))
        self.addCleanup(lambda: (setattr(faces, "folder", saved[0]), setattr(faces, "sizes", saved[1]),
                                 setattr(faces, "images", saved[2])))
        faces.folder, faces.sizes, faces.images = d, set(), {}
        os.environ["T5_FIGHTER_ART"] = d                                   # (a fixed folder: the tab keeps it)
        self.addCleanup(os.environ.pop, "T5_FIGHTER_ART", None)
        sel.open()
        self.root.update()
        self.assertEqual(sel.columns, tk_charsel.COLUMNS)                  # not made at this size yet
        faces.prepare_now([sel.pic_size])                                   # (the thread's work, here at once)
        self.root.update()
        self.assertTrue(sel.is_open())                                      # filled in while open
        self.assertEqual(sel.columns, tk_charsel.COLUMNS_PICTURES)
        by_key = {k: b for k, _n, b in sel.tiles}
        self.assertTrue(str(by_key["jin"].cget("image")))
        self.assertEqual(str(by_key["jin"].cget("compound")), "top")
        self.assertTrue(str(by_key[fighters.RANDOM].cget("image")))        # an empty picture: the names line up
        self.assertTrue(str(by_key["jin"].cget("style")).startswith("Fighter."))
        sel._focus(0)
        sel._move(0, 1, 0)                                                  # down: 9 tiles further now
        self.assertEqual(sel.cursor, tk_charsel.COLUMNS_PICTURES)
        sel.close()

    def test_a_ranked_set_locks_it(self):
        tab = self.login()
        sel = tab.charsel
        sel.open()
        tab.char_cb.configure(state="disabled")           # (what _set_actions does while a set runs)
        self.assertFalse(sel.is_open())
        self.assertEqual(str(tab.char_cb.cget("state")), "disabled")
        self.assertEqual(str(sel.button.cget("state")), "disabled")
        sel.open()
        self.assertFalse(sel.is_open())                    # locked: it does not open
        tab.char_cb.configure(state="readonly")
        self.assertEqual(str(tab.char_cb.cget("state")), "readonly")
        sel.open()
        self.assertTrue(sel.is_open())
        sel.close()


if __name__ == "__main__":
    unittest.main()
