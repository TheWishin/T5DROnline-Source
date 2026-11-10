"""The profile card's picture (tk_profile_pic.py, docs/ONLINE.md "Profile picture"): this player's customized
fighter, on this PC only. The launcher is asked for it while the tab is idle; it appears on this player's own card
and on no other player's; nothing of it goes to the lobby server (the client has no call for it, the server no
message); the setting off shows none; a guest, a busy launcher and an Online tab without the launcher do nothing."""
import hashlib
import unittest

from util import client
from t5lobby import picfmt, tk_profile_pic
from t5lobby.client import LobbyClient
from t5lobby.server import lobby as server_lobby

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
        local = {"lili": [(3, b"a")], "kazuya": [(2, b"b"), (1, b"c")]}
        self.assertEqual(tk_profile_pic.choose(local), ("lili", 3, b"a"))                       # any
        self.assertEqual(tk_profile_pic.choose(local, main="kazuya"), ("kazuya", 2, b"b"))      # the main fighter
        self.assertEqual(tk_profile_pic.choose(local, main="jin", picked="kazuya")[0], "kazuya")  # the picked one
        self.assertEqual(tk_profile_pic.choose(local, main="jin", picked="random")[0], "lili")
        self.assertIsNone(tk_profile_pic.choose({}))
        self.assertIsNone(tk_profile_pic.choose({"jin": []}, main="jin"))


class LocalOnlyTest(unittest.TestCase):
    def test_nothing_of_a_picture_is_in_the_lobby_protocol(self):
        for name in ("pic_put", "pic_get", "pic_del", "pics_ok"):
            self.assertFalse(hasattr(LobbyClient, name), name)
        self.assertNotIn("profile_pics", server_lobby.CAPS)
        self.assertNotIn("profile_pics", server_lobby.FEATURES)
        for name in ("h_pic_put", "h_pic_part", "h_pic_get", "h_pic_del"):
            self.assertFalse(hasattr(server_lobby.LobbyServer, name), name)


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

    def take_once(self, tab):
        pic = tab.view.profile_pic
        pic._next, pic.last = 0.0, None
        self.pump(lambda: pic.last is not None and not pic._running)
        return pic

    def test_own_picture_on_the_own_card_only(self):
        asked = []
        data = png(3)

        def take(fighter, fighter_id, opponent_id):
            asked.append((fighter, fighter_id, opponent_id))
            return {"state": "ok", "pics": [(2, data)], "ran": 1}
        self.app.profile_picture = take
        bob = client(self.s, "Bob", password="bob-pw1", register=True)
        bob.close()
        tab = self.login()
        tab.char_var.set("Kazuya")
        tab.on_char()
        pic = tab.view.profile_pic
        self.assertEqual(pic.frame.winfo_manager(), "")                       # nothing before a picture
        self.take_once(tab)
        self.assertEqual(pic.last[0], "ok")
        kaz = tab.table.fighter("kazuya")["id"]
        self.assertEqual(asked, [("kazuya", kaz, tab.table.fighter("paul")["id"])])
        self.assertEqual(pic.local, {"kazuya": [(2, data)]})
        self.assertFalse(pic.upkeep())                                        # not again right away
        tab.show_profile(None)                                                # this player's own card
        self.pump(lambda: pic.shown_sha == hashlib.sha256(data).hexdigest())
        self.assertEqual(pic.frame.winfo_manager(), "grid")
        self.assertEqual((pic.image.width(), pic.image.height()), pic.card_size())      # shrunk for the card
        self.assertEqual(pic.caption.cget("text"), "Kazuya, costume 2")
        win = pic.show_full()                                                 # a click: the whole picture
        self.assertEqual((pic.full_image.width(), pic.full_image.height()), (picfmt.MAX_W, picfmt.MAX_H))
        self.assertEqual(pic.full, data)
        win.destroy()
        tab.show_profile("Bob")                                               # another player's card: never one
        self.pump(lambda: "Bob" in tab.prof_title.get())
        self.root.update()
        self.assertEqual(pic.frame.winfo_manager(), "")
        self.assertIsNone(pic.image)
        self.assertIsNone(pic.show_full())
        # the fighter is no longer customized: its picture goes
        self.app.profile_picture = lambda *a: {"state": "none", "pics": [], "ran": 0}
        self.take_once(tab)
        self.assertEqual(pic.last[0], "none")
        self.assertEqual(pic.local, {})

    def test_setting_off_shows_none_and_takes_none(self):
        self.app.profile_picture = lambda *a: {"state": "ok", "pics": [(1, png(4))], "ran": 0}
        tab = self.login()
        tab.char_var.set("Kazuya")
        tab.on_char()
        pic = self.take_once(tab)
        self.assertEqual(len(pic.local), 1)
        self.app.settings["profile_pic"] = False
        calls = []
        self.app.profile_picture = lambda *a: calls.append(a)
        pic._next = 0.0
        self.assertFalse(pic.upkeep())                                        # the launcher is never asked
        self.assertEqual((calls, pic.local), ([], {}))
        tab.show_profile(None)
        self.pump(lambda: "Champ" in tab.prof_title.get())
        self.root.update()
        self.assertEqual(pic.frame.winfo_manager(), "")

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
        self.take_once(tab)
        self.assertEqual(pic.last[0], "busy")                                 # a game or a build runs: later
        self.take_once(tab)
        self.assertEqual(pic.last[0], "failed")
        pic._next = 0.0
        self.assertFalse(pic.upkeep())                                        # a failure waits ten minutes
        self.assertEqual(len(calls), 2)
        self.assertEqual(pic.local, {})

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


if __name__ == "__main__":
    unittest.main()
