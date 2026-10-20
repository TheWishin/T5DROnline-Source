"""The Online tab's private and community rooms (tk_rooms.py), driven like a player would against a real server and
other clients (nothing is shown: the windows are withdrawn, questions are answered by the test, the clipboard is in
memory and must stay empty): the Create room window with a password, an invite code or several players; joining a
locked room (the password asked in a masked field, a wrong one refused); Join room with nothing selected takes an
invite code; Copy invite code fills the launcher's own field and never the clipboard; the room row (who plays, the
line, Sit out / Back in line); the host's Room settings (a new password, removing a player)."""
import time
import unittest

import util  # noqa: F401
from util import client, expect

from test_tk_tab import TkBase, tk

PW = "Zebra Quokka 77"


@unittest.skipIf(tk is None, "no tkinter")
class TkRoomsTest(TkBase):
    server_cfg = {"room_next_seconds": 0.5}

    def setUp(self):
        super().setUp()
        self.others = []

    def tearDown(self):
        for c in self.others:
            c.close()
        super().tearDown()

    def login(self, name="Roomer"):
        tab = self.tab
        tab.server_var.set(self.s.addr)
        tab.name_var.set(name)
        tab.do_login("guest")
        self.pump(lambda: tab.client is not None and tab.client.me is not None)
        self.pump(lambda: str(tab.actions["room"].cget("state")) == "normal")

    def peer(self, name, **kw):
        c = client(self.s, name, **kw)
        self.others.append(c)
        return c

    def create(self, size="2", access="Anybody", password="", hidden=False, rotation="Winner stays"):
        tab = self.tab
        tab.actions["room"].invoke()
        w = tab.rooms_ui.window
        self.assertIsNotNone(w)
        w.vars["size"].set(size)
        w.vars["rotation"].set(rotation)
        w.vars["access"].set(access)
        w.vars["password"].set(password)
        w.vars["hidden"].set(1 if hidden else 0)
        self.root.update()
        w.create_button.invoke()
        return w

    def test_create_a_password_room_and_the_list(self):
        tab = self.tab
        self.login()
        other = self.peer("Rival")
        w = self.create(access="Private (password)", password="abc")              # too short: said in the window
        self.assertIn("4-64 characters", w.err.cget("text"))
        self.assertIsNone(tab.client.my_room)
        w.vars["password"].set(PW)
        w.create_button.invoke()
        self.pump(lambda: tab.client.my_room is not None and tab.rooms_ui.window is None)
        self.assertEqual(w.vars["password"].get() if w.winfo_exists() else "", "")
        r = tab.client.my_room
        self.assertEqual(r["lock"], "password")
        self.pump(lambda: "private (password)" in tab.rooms_ui.text.get())
        self.assertIn("Your room: Roomer's room", tab.rooms_ui.text.get())
        self.assertEqual(str(tab.actions["room_code"].cget("state")), "disabled")   # (a password room has no code)
        # the other player's list: locked; the tab's own list too
        t_end = time.monotonic() + 10
        while time.monotonic() < t_end and not any(x["id"] == r["id"] for x in other.rooms):
            time.sleep(0.05)
        self.assertTrue(any(x["id"] == r["id"] and x["private"] for x in other.rooms))
        self.pump(lambda: tab.tv_rooms.exists(r["id"]))
        self.assertIn("private", tab.tv_rooms.item(r["id"], "values")[2])
        self.assertIn("closed", tab.tv_rooms.item(r["id"], "tags"))
        self.assertEqual(self._clip, [])

    def test_join_a_locked_room(self):
        tab = self.tab
        self.login()
        host = self.peer("Hostess")
        room = host.create_room("Locked", private="password", password=PW)
        self.pump(lambda: tab.tv_rooms.exists(room["id"]))
        asked = []
        tab.ask_string = lambda *a, **k: asked.append((a, k)) or "wrong-pass"
        tab.tv_rooms.selection_set(room["id"])
        self.root.update()
        tab.actions["join"].invoke()
        self.pump(lambda: "wrong room password" in tab.status_var.get())
        self.assertEqual(asked[0][1].get("show"), "*")                          # typed into a masked field
        self.assertIn("“Locked” is private", asked[0][0][1])
        tab.ask_string = lambda *a, **k: PW
        tab.actions["join"].invoke()
        self.pump(lambda: (tab.client.my_room or {}).get("id") == room["id"])
        expect(host, "match_found")                                             # a classic room: the match starts

    def test_invite_code_copy_never_the_clipboard(self):
        tab = self.tab
        self.login()
        self.create(size="3", access="Private (invite code)", hidden=True)
        self.pump(lambda: tab.client.my_room is not None and tab.client.room_code)
        self.pump(lambda: any("Press Copy invite code" in x for x in self.app.statuses))
        self.assertEqual(tab.rooms_ui.code_var.get(), "")                       # not shown before the press
        self.pump(lambda: str(tab.actions["room_code"].cget("state")) == "normal")
        tab.actions["room_code"].invoke()
        self.root.update()
        self.assertEqual(tab.rooms_ui.code_var.get(), tab.client.room_code)
        self.assertTrue(tab.rooms_ui.code_entry.selection_present())
        self.assertEqual(str(tab.rooms_ui.code_entry.cget("exportselection")), "0")
        self.assertEqual(self._clip, [], "nothing went to the clipboard")
        self.assertIn("Ctrl+C", tab.status_var.get())
        # a new code (Room settings): the field empties; the next press shows the new one
        old = tab.client.room_code
        tab.actions["room_settings"].invoke()
        tab.rooms_ui.window.code_button.invoke()
        self.pump(lambda: tab.client.room_code != old and tab.rooms_ui.code_var.get() == "")
        tab.rooms_ui.close_window()
        tab.actions["room_code"].invoke()
        self.assertEqual(tab.rooms_ui.code_var.get(), tab.client.room_code)
        self.assertEqual(self._clip, [])
        # a friend types the code into Join room with nothing selected
        guest = self.peer("Guesty")
        guest.join_room(code=tab.client.room_code)
        self.pump(lambda: "Guesty" in tab.rooms_ui.text.get())

    def test_join_with_a_code_and_nothing_selected(self):
        tab = self.tab
        self.login()
        host = self.peer("Hostess")
        host.create_room("Hidden", private="code", hidden=True, size=4)
        tab.ask_string = lambda *a, **k: host.room_code.lower()
        tab.actions["join"].invoke()
        self.pump(lambda: (tab.client.my_room or {}).get("name") == "Hidden")
        self.assertEqual(tab.client.room_code, host.room_code)

    def test_community_room_row_and_sit_out(self):
        tab = self.tab
        self.login()
        self.create(size="4", rotation="Everyone in turn")
        self.pump(lambda: tab.client.my_room is not None)
        room = tab.client.my_room
        a = self.peer("Amy", auto_ready=True)
        b = self.peer("Ben", auto_ready=True)
        a.join_room(room["id"])
        b.join_room(room["id"])
        # the tab is first in line: its ready check comes up; it sits out instead
        self.pump(lambda: self.bar_button("Decline") is not None)
        self.bar_button("Decline").invoke()
        self.pump(lambda: "Amy vs Ben" in tab.rooms_ui.text.get() or "(sitting out)" in tab.rooms_ui.text.get())
        self.pump(lambda: "Roomer (sitting out)" in tab.rooms_ui.text.get())
        self.pump(lambda: tab.actions["room_line"].cget("text") == "Back in line")
        self.assertIn("Everyone in turn", tab.rooms_ui.text.get())
        tab.actions["room_line"].invoke()
        self.pump(lambda: "Back in line: you play when it is your turn." in tab.status_var.get())
        self.pump(lambda: tab.actions["room_line"].cget("text") == "Sit out")

    def test_host_settings_password_and_remove(self):
        tab = self.tab
        self.login()
        self.create(size="3", access="Private (password)", password=PW)
        self.pump(lambda: tab.client.my_room is not None)
        rid = tab.client.my_room["id"]
        x = self.peer("Xena")
        x.join_room(rid, password=PW)
        self.pump(lambda: "Xena" in tab.rooms_ui.text.get())
        self.pump(lambda: str(tab.actions["room_settings"].cget("state")) == "normal")
        tab.actions["room_settings"].invoke()
        w = tab.rooms_ui.window
        w.vars["password"].set("Walrus Mango!")
        w.save_button.invoke()
        self.pump(lambda: "Room settings saved." in tab.status_var.get())
        y = self.peer("Yuri")
        with self.assertRaises(Exception):
            y.join_room(rid, password=PW)
        y.join_room(rid, password="Walrus Mango!")
        # remove Xena (asked first)
        asked = []
        tab.ask_yes_no = lambda *a, **k: asked.append(a) or True
        names = list(w.players.get(0, "end"))
        self.assertIn("Xena", names)
        w.players.selection_set(names.index("Xena"))
        w.kick_button.invoke()
        self.pump(lambda: "Removed Xena from the room." in tab.status_var.get())
        self.assertIn("They cannot come back into it.", asked[0][1])
        ev = expect(x, "notice")
        while ev.get("code") != "room_kicked":
            ev = expect(x, "notice")

    def test_classic_without_private_rooms_on_the_server(self):
        """A server without the feature: Create room makes a room at once, as before (no window)."""
        import t5lobby.server.lobby as lobby_mod
        orig_f, orig_c = lobby_mod.FEATURES, lobby_mod.CAPS
        lobby_mod.FEATURES = [f for f in orig_f if f != "private_rooms"]
        lobby_mod.CAPS = orig_c - {"private_rooms"}
        try:
            tab = self.tab
            self.login()
            tab.actions["room"].invoke()
            self.assertIsNone(tab.rooms_ui.window)
            self.pump(lambda: (tab.client.me or {}).get("status") == "room")
        finally:
            lobby_mod.FEATURES, lobby_mod.CAPS = orig_f, orig_c


if __name__ == "__main__":
    unittest.main()
