"""The Online tab's Friends page and invites, driven like a player would against a real server and a second client
(nothing is shown: the window is withdrawn, questions are answered by the test, the clipboard is in memory):
adding a friend by name, answering a request, who is online / in a match / offline, removing, inviting a friend to
a casual match or to the room with the friend's one-click accept, a guest and a server without friends; and Discord
Rich Presence fed by the tab's state through a fake Discord pipe (test_discord.FakeDiscord)."""
import json
import time
import unittest
from unittest import mock

import util  # noqa: F401
from util import ServerThread, client, expect

from test_discord import APP, FakeDiscord
from test_tk_tab import TkBase, tk

from t5lobby import discord_rpc


def texts(tv):
    return {iid: tv.item(iid, "values") for iid in tv.get_children()}


@unittest.skipIf(tk is None, "no tkinter")
class TkFriendsTest(TkBase):
    def login(self, name="Ranker"):
        tab = self.tab
        tab.server_var.set(self.s.addr)
        tab.name_var.set(name)
        tab.pw_var.set("secret-pw1")
        tab.ask_string = lambda *a, **k: "secret-pw1"            # "type the password again"
        tab.do_login("register")
        self.pump(lambda: tab.client is not None and tab.client.me is not None)
        self.pump(lambda: tab.codes_window is not None)
        tab.codes_window.destroy()
        self.pump(lambda: tab.client.friend_list is not None)

    def rival(self, **kw):
        self.other = client(self.s, "Rival", password="rival-pw1", register=True, **kw)
        return self.other

    def befriend(self):
        """The tab asks Rival, Rival accepts."""
        tab = self.tab
        tab.nb.select(3)
        tab.friend_name_var.set("Rival")
        self.pump(lambda: str(tab.friend_actions["add"].cget("state")) == "normal")
        tab.friend_actions["add"].invoke()
        self.pump(lambda: "Friend request sent to Rival" in tab.status_var.get())
        self.assertEqual(tab.friend_name_var.get(), "")
        self.assertIn("out:Rival", texts(tab.tv_requests))
        expect(self.other, "friend_request")
        self.other.answer_friend("Ranker", True)
        self.pump(lambda: "Rival accepted your friend request." in tab.status_var.get())
        self.pump(lambda: "f:Rival" in texts(tab.tv_friends))

    def test_add_a_friend_and_see_them_online(self):
        tab = self.tab
        self.login()
        tab.nb.select(3)                                          # the Friends page
        self.root.update()
        self.assertIn("No friends yet", tab.friends_note_var.get())
        self.rival(auto_ready=True)
        self.befriend()
        row = texts(tab.tv_friends)["f:Rival"]
        self.assertEqual(row[0], "Rival")
        self.assertEqual(row[2], "in lobby")
        self.assertEqual(tab.friends_count_var.get(), "1 online · 1 of 100")
        self.assertIn("Your friends see when you are online", tab.friends_note_var.get())
        self.other.quick_match()
        self.pump(lambda: texts(tab.tv_friends)["f:Rival"][2] == "searching")
        self.other.cancel_queue()
        self.pump(lambda: texts(tab.tv_friends)["f:Rival"][2] == "in lobby")
        self.other.close()
        self.other = None
        self.pump(lambda: texts(tab.tv_friends)["f:Rival"][2].startswith("offline, last seen "))
        self.assertEqual(tab.friends_count_var.get(), "0 online · 1 of 100")
        tab.tv_friends.selection_set("f:Rival")
        self.root.update()
        self.assertEqual(str(tab.friend_actions["invite"].cget("state")), "disabled")       # offline: no invite
        self.assertEqual(str(tab.friend_actions["remove"].cget("state")), "normal")

    def test_answer_a_request_and_remove(self):
        tab = self.tab
        self.login()
        self.rival()
        self.other.add_friend("Ranker")
        self.pump(lambda: "Rival wants to be your friend: see the Friends tab." in tab.status_var.get())
        self.assertEqual(tab.nb.tab(tab.friends_page, "text"), "Friends (1)")
        self.assertEqual(tab.requests_count_var.get(), "1")
        self.assertEqual(texts(tab.tv_requests)["in:Rival"][1], "wants to be your friend")
        tab.nb.select(3)
        tab.tv_requests.selection_set("in:Rival")
        self.pump(lambda: str(tab.friend_actions["accept"].cget("state")) == "normal")
        self.assertEqual(str(tab.friend_actions["cancel_request"].cget("state")), "disabled")
        tab.friend_actions["accept"].invoke()
        self.pump(lambda: "f:Rival" in texts(tab.tv_friends) and not texts(tab.tv_requests))
        self.assertEqual(tab.nb.tab(tab.friends_page, "text"), "Friends")
        asked = []
        tab.ask_yes_no = lambda *a, **k: asked.append(a) or True
        tab.tv_friends.selection_set("f:Rival")
        self.root.update()
        tab.friend_actions["remove"].invoke()
        self.pump(lambda: not texts(tab.tv_friends))
        self.assertIn("Remove Rival from your friends?", asked[0][1])
        self.assertIn("Rival is no longer your friend.", tab.status_var.get())
        self.assertEqual(self.other.friends_list()["friends"], [])

    def test_a_friend_invites_the_tab_one_click(self):
        tab = self.tab
        self.login()
        self.rival()
        self.befriend()
        self.other.invite("Ranker", "casual")
        self.pump(lambda: self.bar_button("Accept") is not None)
        self.assertIn("Rival", tab.bar_text.get())
        self.assertIn("invites you to a casual match", tab.bar_text.get())
        self.assertEqual(tab.view._bar_kind_now(), "invite")
        self.assertIn("cross", tab.bar_pad)                      # A / Cross accepts with a controller too
        self.bar_button("Accept").invoke()                        # the one click: no second question
        self.pump(lambda: len(self.app.games) == 1)
        env = self.app.games[0].env
        self.assertIn("T5_NET_PEER", env)
        ev = expect(self.other, "match_found")
        self.assertEqual((ev["origin"], ev["ready_check"]), ("invite", False))
        self.assertIsNone(tab.invite)

    def test_an_invite_that_ends(self):
        tab = self.tab
        self.login()
        self.rival()
        self.befriend()
        r = self.other.invite("Ranker")
        self.pump(lambda: self.bar_button("Decline") is not None)
        self.other.cancel_invite(r["invite"])
        self.pump(lambda: not tab.view._bar_on and tab.invite is None)                 # the question is gone
        self.assertIn("The invite from Rival ended.", tab.status_var.get())
        time.sleep(2.1)                                           # (one invite per 2 s)
        self.s.call(lambda: self.s.srv.retry_after.clear())       # (and after taking it back: T5L_INVITE_RETRY_SECONDS)
        self.other.invite("Ranker")
        self.pump(lambda: self.bar_button("Decline") is not None)
        self.bar_button("Decline").invoke()
        states = [expect(self.other, "invite_update")["state"] for _ in range(2)]     # (the first: the cancel)
        self.assertEqual(states, ["cancelled", "declined"])
        self.assertEqual(self.app.games, [])

    def short_hold(self, seconds):
        """A server that holds an invite back `seconds` after a no (T5L_INVITE_RETRY_SECONDS; 30 by default)."""
        self.s.stop()
        self.s = ServerThread(invite_retry_seconds=seconds).start()

    def invite_buttons(self):
        acts = self.tab.friend_actions
        return [(str(acts[k].cget("text")), str(acts[k].cget("state"))) for k in ("invite", "invite_room")]

    def test_invite_a_friend_from_the_page(self):
        tab = self.tab
        self.short_hold(2.5)
        self.login()
        self.rival()
        self.befriend()
        tab.tv_friends.selection_set("f:Rival")
        self.pump(lambda: str(tab.friend_actions["invite"].cget("state")) == "normal")
        self.assertEqual(str(tab.friend_actions["invite_room"].cget("state")), "disabled")   # not in a room
        tab.friend_actions["invite"].invoke()
        ev = expect(self.other, "invited")
        self.assertEqual((ev["from"]["name"], ev["kind"]), ("Ranker", "casual"))
        self.pump(lambda: "Invite sent to Rival" in tab.status_var.get())
        self.pump(lambda: str(tab.friend_actions["invite"].cget("text")) == "Cancel the invite")
        self.other.answer_invite(ev["invite"], False)
        self.pump(lambda: "Rival declined your invite." in tab.status_var.get())
        # held back after the no (the server's seconds, counted down), then free again
        self.assertIn(self.invite_buttons(), ([("Invite in 3 s", "disabled"), ("Invite to my room", "disabled")],
                                              [("Invite in 2 s", "disabled"), ("Invite to my room", "disabled")]))
        self.pump(lambda: str(tab.friend_actions["invite"].cget("text")) == "Invite to a match", timeout=6)
        self.assertEqual(str(tab.friend_actions["invite"].cget("state")), "normal")
        # to the room: the friend joins it with one click and the match starts
        tab.actions["room"].invoke()
        tab.rooms_ui.window.create_button.invoke()                        # (Create room's window: an open room for two)
        self.pump(lambda: str(tab.friend_actions["invite_room"].cget("state")) == "normal")
        tab.friend_actions["invite_room"].invoke()
        ev = expect(self.other, "invited")
        self.assertEqual(ev["kind"], "room")
        self.other.answer_invite(ev["invite"], True)
        self.pump(lambda: len(self.app.games) == 1)
        self.assertEqual(self.app.games[0].env["T5_NET_MODE"], "host")      # the room's owner is P1

    def test_the_invite_buttons_count_the_wait_down(self):
        # (1.1.3) After a no the lobby holds the next invite to that friend back (T5L_INVITE_RETRY_SECONDS) and used to
        # say so only in the status line, after the next click. Both invite buttons are off now, and the one this
        # player would use (in a room: the room's) counts down the seconds the server said -- per friend, also when
        # the invite was taken back, and from the refusal when an invite went out anyway (the server stays the
        # authority).
        tab = self.tab
        self.login()
        self.rival()
        self.befriend()
        third = client(self.s, "Third", password="third-pw1", register=True)
        self.addCleanup(third.close)
        third.add_friend("Ranker")
        self.pump(lambda: "in:Third" in texts(tab.tv_requests))
        tab.tv_requests.selection_set("in:Third")
        self.pump(lambda: str(tab.friend_actions["accept"].cget("state")) == "normal")
        tab.friend_actions["accept"].invoke()
        self.pump(lambda: "f:Third" in texts(tab.tv_friends))
        tab.actions["room"].invoke()                                       # in a room: both invite buttons count
        tab.rooms_ui.window.create_button.invoke()
        tab.tv_friends.selection_set("f:Rival")
        self.pump(lambda: str(tab.friend_actions["invite_room"].cget("state")) == "normal")
        tab.friend_actions["invite_room"].invoke()
        ev = expect(self.other, "invited")
        self.pump(lambda: str(tab.friend_actions["invite"].cget("text")) == "Cancel the invite")
        tab.friend_actions["invite"].invoke()                              # taken back: held back as well
        self.pump(lambda: str(tab.friend_actions["invite_room"].cget("text")).startswith("Invite in "))
        self.assertIn(self.invite_buttons(), ([("Invite to a match", "disabled"), ("Invite in 30 s", "disabled")],
                                              [("Invite to a match", "disabled"), ("Invite in 29 s", "disabled")]))
        first = tab.client.invite_wait("Rival")
        self.pump(lambda: tab.client.invite_wait("Rival") < first, timeout=3)
        self.pump(lambda: self.invite_buttons()[1][0] == f"Invite in {tab.client.invite_wait('Rival')} s")
        tab.tv_friends.selection_set("f:Third")                            # another friend: free
        self.pump(lambda: self.invite_buttons() == [("Invite to a match", "disabled"), ("Invite to my room", "normal")])
        tab.tv_friends.selection_set("f:Rival")
        self.pump(lambda: self.invite_buttons()[1][1] == "disabled")
        # a launcher that missed the update (or a stale list): the server refuses, says the seconds, the buttons follow
        tab.client.invite_waits.clear()
        self.pump(lambda: self.invite_buttons()[1] == ("Invite to my room", "normal"))
        time.sleep(2.1)                                                    # (one invite per 2 s)
        tab.friend_actions["invite_room"].invoke()
        self.pump(lambda: "try again in" in tab.status_var.get())
        self.pump(lambda: self.invite_buttons()[1][1] == "disabled" and self.invite_buttons()[1][0].startswith("Invite in 2"))
        self.assertIsNone(self.other.next_event(0.3, ("invited",)))       # no second question on Rival's screen
        self.assertEqual(ev["kind"], "room")

    def test_a_guest_and_a_server_without_friends(self):
        tab = self.tab
        tab.server_var.set(self.s.addr)
        tab.do_login("guest")
        self.pump(lambda: tab.client is not None and tab.client.me is not None)
        tab.nb.select(3)
        self.pump(lambda: "Friends need an account" in tab.friends_note_var.get())
        self.assertEqual(str(tab.friend_actions["add"].cget("state")), "disabled")
        tab.client.me["guest"] = False                            # as if an account on a server without the feature
        tab.client.welcome["features"] = [f for f in tab.client.welcome["features"] if f != "friends"]
        tab._fill_friends()
        self.assertIn("This lobby server has no friends list", tab.friends_note_var.get())
        self.assertEqual(str(tab.friend_actions["add"].cget("state")), "disabled")


@unittest.skipIf(tk is None, "no tkinter")
class TkDiscordTest(TkBase):
    """Rich Presence follows the tab: in the lobby, searching ranked, in a ranked match (fighters, set score),
    and goes away when the setting is turned off."""

    def setUp(self):
        super().setUp()
        self.fake = FakeDiscord().start()
        self.addCleanup(self.fake.stop)
        self.tab.discord_paths = [self.fake.path]                 # never the real Discord's pipes
        patch = mock.patch.multiple(discord_rpc.DiscordPresence, MIN_INTERVAL=0.05, RETRY=0.2, LOST_RETRY=0.2)
        patch.start()
        self.addCleanup(patch.stop)

    def details(self):
        return [a["details"] if a else None for a in self.fake.activities]

    def test_presence_follows_the_tab(self):
        tab = self.tab
        self.app.settings["discord_presence"] = True
        self.app.settings["discord_app_id"] = APP
        tab.server_var.set(self.s.addr)
        tab.name_var.set("Ranker")
        tab.pw_var.set("secret-pw1")
        tab.ask_string = lambda *a, **k: "secret-pw1"
        tab.char_var.set("Lili")
        tab.do_login("register")
        self.pump(lambda: tab.codes_window is not None)
        tab.codes_window.destroy()
        self.pump(lambda: "In lobby" in self.details())
        self.assertEqual(self.fake.frames[0][1]["client_id"], APP)
        self.assertIn("timestamps", self.fake.activities[-1])
        self.other = client(self.s, "Rival", password="rival-pw1", register=True, auto_ready=True, sets=True)
        self.other.set_char("asuka")
        self.pump(lambda: str(tab.actions["ranked"].cget("state")) == "normal")
        tab.actions["ranked"].invoke()
        self.pump(lambda: "Searching ranked" in self.details())
        self.other.ranked_match("asuka")
        self.pump(lambda: self.bar_button("Accept") is not None)
        self.bar_button("Accept").invoke()
        self.pump(lambda: len(self.app.games) == 1)
        want = "In match: Lili vs Asuka (Ranked, Set 0-0)"
        self.pump(lambda: want in self.details())
        start = [a for a in self.fake.activities if a and a["details"] == want][0]["timestamps"]["start"]
        self.assertLessEqual(abs(start - time.time()), 30)
        self.app.settings["discord_presence"] = False             # turned off in Settings
        self.pump(lambda: self.fake.activities[-1] is None)
        self.assertIsNone(tab.presence)

    def test_server_text_never_reaches_the_discord_status(self):
        # (security review 2) the status is public on the player's Discord profile; the fighter keys and the set score
        # come from the lobby server -- any server a player adds. An unknown key went there as it came.
        import types
        tab = self.tab
        tab.server_var.set(self.s.addr)
        tab.do_login("guest")
        self.pump(lambda: tab.client is not None and tab.client.me is not None)
        saved = tab.driver
        try:
            tab.driver = types.SimpleNamespace(ticket=object())
            for fight, wins in ((("visit evil.example for free coins", "jin"), [1, 0]), ((["x"], "jin"), [1, 0]),
                                (("lili", "asuka"), ["<b>9</b>", 0]), (("lili", "asuka"), [True, 0])):
                tab._match_info = {"match": "m1", "ranked": True, "slot": 0, "fight": fight,
                                   "set": {"rated": True, "wins": wins}}
                details = tab._presence_wanted()["details"]
                self.assertNotIn("evil", details)
                self.assertNotIn("<b>", details)
                self.assertNotIn("True", details)
            tab._match_info = {"match": "m1", "ranked": True, "slot": 1, "fight": ("lili", "asuka"),
                               "set": {"rated": True, "wins": [2, 1]}}
            self.assertEqual(tab._presence_wanted()["details"], "In match: Asuka vs Lili (Ranked, Set 1-2)")
        finally:
            tab.driver = saved
            tab._match_info = None

    def test_off_by_default(self):
        tab = self.tab
        self.app.settings["discord_app_id"] = APP                 # (an id alone does not turn it on)
        tab.server_var.set(self.s.addr)
        tab.do_login("guest")
        self.pump(lambda: tab.client is not None and tab.client.me is not None)
        for _ in range(5):
            tab._poll()
        time.sleep(0.3)
        self.assertIsNone(tab.presence)
        self.assertEqual(self.fake.connections, 0)

    def test_no_application_id_does_nothing(self):
        tab = self.tab
        self.app.settings["discord_presence"] = True
        with mock.patch.object(discord_rpc, "CONFIG_FILE", "nonexistent.json"), \
                mock.patch.dict("os.environ", {"T5_DISCORD_APP_ID": ""}):
            tab.server_var.set(self.s.addr)
            tab.do_login("guest")
            self.pump(lambda: tab.client is not None and tab.client.me is not None)
            for _ in range(5):
                tab._poll()
        self.assertIsNone(tab.presence)
        self.assertEqual(self.fake.connections, 0)


if __name__ == "__main__":
    unittest.main()
