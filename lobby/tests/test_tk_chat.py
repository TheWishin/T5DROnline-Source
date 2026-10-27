"""The lobby chat shows who wrote what (1.1.7, from player feedback): each sender's name in bold in a colour of
their own (from the name: the same on every PC), your own in the accent colour, above their lines and again when
another sender comes between; the launcher's and the server's lines muted. A real server, a second client and the
Online tab in a real Tk main loop."""
import time
import unittest

from test_tk_tab import TkBase, tk
from util import client

from t5lobby import theme


@unittest.skipIf(tk is None, "no tkinter")
class ChatLook(TkBase):
    def test_names_colours_and_groups(self):
        tab = self.tab
        tab.server_var.set(self.s.addr)
        tab.name_var.set("Tester")
        tab.do_login("guest")
        self.pump(lambda: tab.client is not None and tab.client.me is not None)
        me = tab.client.me["name"]
        self.other = client(self.s, "Rival")
        tab.chat_line("Hosting. Friends paste this as their Server (copied to the clipboard):\n  203.0.113.7:7781")

        said = []

        def say(text):
            tab.chat_var.set(text)
            tab.do_chat()
            said.append(text)
        # a real main loop: the lines go out through the server and come back as events
        self.root.after(50, lambda: say("anyone up for ranked?"))
        self.root.after(400, lambda: say("I main Hwoarang"))
        self.root.after(800, lambda: self.other.chat("me! give me a sec"))
        self.root.after(1200, lambda: self.other.chat("loading the game"))
        self.root.after(1600, lambda: say("gg, again?"))
        t_end = time.monotonic() + 15

        def poll():
            text = tab.chat_log.get("1.0", "end")
            if text.count("\n") >= 10 or time.monotonic() > t_end:
                self.root.quit()
            else:
                self.root.after(50, poll)
        self.root.after(100, poll)
        self.root.mainloop()

        lines = tab.chat_log.get("1.0", "end-1c").split("\n")
        self.assertEqual(lines, ["Hosting. Friends paste this as their Server (copied to the clipboard):",
                                 "  203.0.113.7:7781",
                                 me, "anyone up for ranked?", "I main Hwoarang",
                                 "Rival", "me! give me a sec", "loading the game",
                                 me, "gg, again?", ""])
        log = tab.chat_log

        def tags(line_no):
            return set(log.tag_names(f"{line_no}.0"))
        self.assertIn("chat_sys", tags(1))
        self.assertIn("chat_sys", tags(2))
        for head in (3, 6, 9):
            self.assertIn("chat_head", tags(head))
        for msg in (4, 5, 7, 8, 10):
            self.assertEqual({t for t in tags(msg) if t.startswith("chat_")}, {"chat_msg"})
        mine = [t for t in tags(3) if t.startswith("chat_name_")]
        rival = [t for t in tags(6) if t.startswith("chat_name_")]
        self.assertEqual(log.tag_cget(mine[0], "foreground"), theme.C["accent_hi"])         # you: the accent
        self.assertEqual(log.tag_cget(rival[0], "foreground"), theme.name_color("Rival"))    # them: their colour
        self.assertEqual(tags(9), tags(3))                                                   # the same for you again
        # bold names, muted system lines, space before another sender
        self.assertEqual(str(log.tag_cget("chat_head", "font")), str(tab.view.th.fonts["bold"]))
        self.assertEqual(log.tag_cget("chat_sys", "foreground"), theme.C["muted"])
        self.assertGreater(int(log.tag_cget("chat_head", "spacing1")), 0)

    def test_name_colours(self):
        names = ["Rival", "Mika", "Tester", "jin_main_99", "가나다", "テスト", "Ünal", "x", "A" * 40]
        for n in names:
            c = theme.name_color(n)
            self.assertEqual(c, theme.name_color(n))                                 # stable
            self.assertEqual(c, theme.name_color(" " + n.upper() + " ") if n.isascii() else c)   # case, spaces
            self.assertGreaterEqual(theme.contrast(c, theme.C["surface"]), 4.5, n)   # readable on the card
            self.assertNotEqual(c, theme.C["accent_hi"])
        many = {theme.name_color(f"player{i}") for i in range(40)}
        self.assertGreater(len(many), 25)                                            # players look different


if __name__ == "__main__":
    unittest.main()
