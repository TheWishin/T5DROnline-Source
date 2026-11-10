"""The profile card's picture (tk_profile_pic.py, docs/ONLINE.md "Profile picture"): another player's customized
fighter appears on their card; a profile without one shows none; this player's own picture is asked from the
launcher while the tab is idle and sent once; the setting off removes it; a guest, a busy launcher and an Online
tab without the launcher do nothing."""
import hashlib
import unittest

from util import client
from t5lobby import picfmt, tk_profile_pic

try:
    import tkinter as tk
    from test_tk_tab import TkBase
except ImportError:      # pragma: no cover
    tk = None
    TkBase = unittest.TestCase


def png(seed=1, w=picfmt.MAX_W, h=picfmt.MAX_H):
    px = bytearray()
    for y in range(h):
        for x in range(w):
            px += bytes(((x + seed * 30) & 255, (y * 2) & 255, (x + y) & 255))
    return picfmt.encode(w, h, bytes(px))


class ChooseTest(unittest.TestCase):
    def test_choose(self):
        rows = [{"fighter": "lili", "costume": 3, "sha": "a"}, {"fighter": "kazuya", "costume": 2, "sha": "b"},
                {"fighter": "kazuya", "costume": 1, "sha": "c"}]
        self.assertEqual(tk_profile_pic.choose({"pics": rows})["sha"], "a")                     # the newest
        self.assertEqual(tk_profile_pic.choose({"pics": rows, "main": "kazuya"})["sha"], "b")   # the main fighter's
        self.assertEqual(tk_profile_pic.choose({"pics": rows, "main": "jin"})["sha"], "a")
        for p in ({}, {"pics": []}, {"pics": None}, {"pics": ["x", {"fighter": "jin"}]}):
            self.assertIsNone(tk_profile_pic.choose(p))


@unittest.skipIf(tk is None, "no tkinter")
class ProfilePictureTest(TkBase):
    def login(self, mode="account"):
        tab = self.tab
        if mode == "account":
            c = client(self.s, "Champ", password="champ-pw1", register=True)
            c.close()
            tab.pw_var.set("champ-pw1")
        tab.server_var.set(self.s.addr)
        tab.name_var.set("Champ")
        tab.do_login(mode)
        self.pump(lambda: tab.client is not None and tab.client.me is not None)
        return tab

    def stored(self, name):
        def rows():
            row = self.s.srv.store.account(name)
            return [(r["fighter"], r["costume"], r["sha"]) for r in self.s.srv._pics.list(row["id"])]
        return self.s.call(rows)

    def test_another_players_picture_on_their_card(self):
        self.other = alice = client(self.s, "Alice", password="alice-pw1", register=True)
        data = png(1)
        alice.pic_put("kazuya", 2, data)
        bob = client(self.s, "Bob", password="bob-pw1", register=True)
        bob.close()
        tab = self.login()
        pic = tab.view.profile_pic
        self.assertEqual(pic.frame.winfo_manager(), "")                       # nothing before a profile
        tab.show_profile("Alice")
        self.pump(lambda: pic.shown_sha == hashlib.sha256(data).hexdigest())
        self.assertEqual(pic.frame.winfo_manager(), "grid")
        self.assertEqual((pic.image.width(), pic.image.height()), pic.card_size())      # shrunk for the card
        self.assertLessEqual(pic.image.width(), picfmt.MAX_W)
        self.assertEqual(pic.caption.cget("text"), "Kazuya, costume 2")
        win = pic.show_full()                                                 # a click: the whole picture
        self.assertEqual((pic.full_image.width(), pic.full_image.height()), (picfmt.MAX_W, picfmt.MAX_H))
        self.assertEqual(pic.full, data)
        win.destroy()
        tab.show_profile("Bob")                                               # a profile without a picture
        self.pump(lambda: "Bob" in tab.prof_title.get())
        self.root.update()
        self.assertEqual(pic.frame.winfo_manager(), "")
        self.assertIsNone(pic.image)
        self.assertIsNone(pic.show_full())
        alice.pic_put("kazuya", 2, png(5))                                    # she changed her costume
        tab.show_profile("Alice")
        self.pump(lambda: pic.shown_sha == hashlib.sha256(png(5)).hexdigest())

    def test_own_picture_is_taken_and_sent_once(self):
        asked = []
        data = png(3)

        def take(fighter, fighter_id, opponent_id):
            asked.append((fighter, fighter_id, opponent_id))
            return {"state": "ok", "pics": [(2, data)], "ran": 1}
        self.app.profile_picture = take
        tab = self.login()
        tab.char_var.set("Kazuya")
        tab.on_char()
        pic = tab.view.profile_pic
        pic._next = 0.0
        self.pump(lambda: pic.last is not None and not pic._running)
        self.assertEqual(pic.last[0], "sent")
        kaz = tab.table.fighter("kazuya")["id"]
        self.assertEqual(asked, [("kazuya", kaz, tab.table.fighter("paul")["id"])])
        self.assertEqual(self.stored("Champ"), [("kazuya", 2, hashlib.sha256(data).hexdigest())])
        self.assertFalse(tab.view.profile_pic.upkeep())                       # not again right away
        pic._next, pic.last = 0.0, None                                       # later: the server has it already
        self.pump(lambda: pic.last is not None and not pic._running)
        self.assertEqual(pic.last[0], "same")
        # the fighter is no longer customized: its picture leaves the server
        self.app.profile_picture = lambda *a: {"state": "none", "pics": [], "ran": 0}
        pic._next, pic.last = 0.0, None
        self.pump(lambda: pic.last is not None and not pic._running)
        self.assertEqual(pic.last[0], "none")
        self.assertEqual(self.stored("Champ"), [])

    def test_setting_off_removes_the_pictures(self):
        self.app.profile_picture = lambda *a: {"state": "ok", "pics": [(1, png(4))], "ran": 0}
        tab = self.login()
        tab.char_var.set("Kazuya")
        tab.on_char()
        pic = tab.view.profile_pic
        pic._next = 0.0
        self.pump(lambda: pic.last is not None and not pic._running)
        self.assertEqual(len(self.stored("Champ")), 1)
        self.app.settings["profile_pic"] = False
        calls = []
        self.app.profile_picture = lambda *a: calls.append(a)
        pic._next, pic.last = 0.0, None
        self.pump(lambda: pic.last is not None and not pic._running)
        self.assertEqual(pic.last[0], "off")
        self.assertEqual(self.stored("Champ"), [])
        pic._next = 0.0
        self.assertFalse(pic.upkeep())                                        # once; and the launcher was never asked
        self.assertEqual(calls, [])

    def test_busy_failed_and_random(self):
        answers = [None, {"state": "failed", "pics": [], "ran": 1, "error": "the game did not reach the fight in time"}]
        calls = []

        def take(*a):
            calls.append(a)
            return answers[min(len(calls), len(answers)) - 1]
        self.app.profile_picture = take
        tab = self.login()
        pic = tab.view.profile_pic
        pic._next = 0.0
        self.assertFalse(pic.upkeep())                                        # "Random": no fighter to picture
        self.assertEqual(calls, [])
        tab.char_var.set("Kazuya")
        tab.on_char()
        pic._next = 0.0
        self.pump(lambda: pic.last is not None and not pic._running)
        self.assertEqual(pic.last[0], "busy")                                 # a game or a build runs: later
        pic._next, pic.last = 0.0, None
        self.pump(lambda: pic.last is not None and not pic._running)
        self.assertEqual(pic.last[0], "failed")
        pic._next = 0.0
        self.assertFalse(pic.upkeep())                                        # a failure waits ten minutes
        self.assertEqual(len(calls), 2)
        self.assertEqual(self.stored("Champ"), [])

    def test_guest_and_no_launcher(self):
        tab = self.login("guest")
        pic = tab.view.profile_pic
        self.app.profile_picture = lambda *a: self.fail("a guest's picture was asked for")
        tab.char_var.set("Kazuya")
        pic._next = 0.0
        self.assertFalse(pic.upkeep())
        del self.app.profile_picture                                          # the lobby without the launcher
        pic._next = 0.0
        self.assertFalse(pic.upkeep())


@unittest.skipIf(tk is None, "no tkinter")
class OffServerTest(ProfilePictureTest):
    server_cfg = dict(profile_pics=False)

    def test_another_players_picture_on_their_card(self):
        self.app.profile_picture = lambda *a: self.fail("asked on a server without pictures")
        tab = self.login()
        tab.char_var.set("Kazuya")
        pic = tab.view.profile_pic
        pic._next = 0.0
        self.assertFalse(pic.upkeep())
        tab.show_profile(None)
        self.pump(lambda: "Champ" in tab.prof_title.get())
        self.assertEqual(pic.frame.winfo_manager(), "")

    test_own_picture_is_taken_and_sent_once = test_setting_off_removes_the_pictures = None
    test_busy_failed_and_random = test_guest_and_no_launcher = None


if __name__ == "__main__":
    unittest.main()
