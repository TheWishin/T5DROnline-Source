"""The Online tab's health picker up to 150 % (1.1.7, a player request: "my friends and I like to play at 120 %";
tk_rules.py, docs/ONLINE.md "Training rooms and the health handicap"). A real server and the Online tab in a real
Tk main loop: with a game that plays more than 100 % (its binary has the marker) the picker offers 150 down to 30
and the server takes 120; with an older game it offers 100 down to 30, and a remembered 150 is sent as 100."""
import os
import time
import unittest

from test_tk_tab import TkBase, tk

from t5lobby import match_driver, tk_rules


@unittest.skipIf(tk is None, "no tkinter")
class Picker(TkBase):
    def login(self, life150):
        tab = self.tab
        tab._game_has_rules = lambda: True                    # (the fake app has no game build)
        tab._game_has_life150 = lambda: life150
        tab.server_var.set(self.s.addr)
        tab.name_var.set("Tester")
        tab.do_login("guest")
        self.pump(lambda: tab.client is not None and tab.client.me is not None)

    def server_life(self):
        return self.s.call(lambda: self.s.srv.by_name["tester"].life)

    def choose(self, label, want):
        """Pick `label` in the combobox the way a player does (the selection event), in the main loop, and wait
        until the server has `want`."""
        tab = self.tab
        t_end = time.monotonic() + 15

        def pick():
            tab.life_var.set(label)
            tab.life_cb.event_generate("<<ComboboxSelected>>")

        def poll():
            if self.server_life() == want or time.monotonic() > t_end:
                self.root.quit()
            else:
                self.root.after(50, poll)
        self.root.after(50, pick)
        self.root.after(100, poll)
        self.root.mainloop()

    def test_up_to_150(self):
        self.login(True)
        cb = self.tab.life_cb
        values = list(self.root.tk.splitlist(cb.cget("values")))
        self.assertEqual(values, [tk_rules.life_label(v) for v in range(150, 29, -10)])
        self.assertEqual(self.tab.client.life_max(), 150)
        self.choose(tk_rules.life_label(120), 120)
        self.assertEqual(self.server_life(), 120)
        self.choose(tk_rules.life_label(150), 150)
        self.assertEqual(self.server_life(), 150)
        self.assertEqual(self.tab.cfg.get("life"), 150)                # remembered in online.json

    def test_an_older_game_stays_at_100(self):
        self.tab.life_var.set(tk_rules.life_label(150))                # remembered from a PC with a newer game
        self.login(False)
        self.pump(lambda: self.tab.life_var.get() == tk_rules.life_label(100))
        values = list(self.root.tk.splitlist(self.tab.life_cb.cget("values")))
        self.assertEqual(values, [tk_rules.life_label(v) for v in range(100, 29, -10)])
        self.assertEqual(self.tab.client.life_max(), 100)
        self.assertNotIn("life150", self.tab.client.welcome["caps"])
        self.choose(tk_rules.life_label(70), 70)
        self.assertEqual(self.server_life(), 70)


class Marker(unittest.TestCase):
    """The launcher knows the game plays more than 100 % from the text the game's status carries (df_fight.cpp)."""

    def test_marker(self):
        import tempfile
        d = tempfile.mkdtemp()
        new, old = os.path.join(d, "new.exe"), os.path.join(d, "old.exe")
        with open(new, "wb") as f:
            f.write(b"\0" * 5000 + b'"training": %s, "life": [%d, %d], "life_max": 150%s}\n' + b"\0" * 100)
        with open(old, "wb") as f:
            f.write(b"\0" * 5000 + b'"training": %s, "life": [%d, %d]%s}\n' + b"\0" * 100)
        self.assertTrue(match_driver.game_supports_life150([new]))
        self.assertFalse(match_driver.game_supports_life150([old]))
        self.assertFalse(match_driver.game_supports_life150([os.path.join(d, "missing.exe")]))
        src = os.path.join(os.path.dirname(__file__), "..", "..", "src", "directfight", "df_fight.cpp")
        with open(src, encoding="utf-8") as f:
            text = f.read()
        self.assertIn('\\"life_max\\": 150', text)                    # the game writes the marker's text
        self.assertIn("static_assert(np::MatchRules::kLifeMax == 150", text)


if __name__ == "__main__":
    unittest.main()
