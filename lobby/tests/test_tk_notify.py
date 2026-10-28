"""The Online tab's chime and taskbar flash (t5lobby/notify.py) on the events of a real lobby: a match found (the Accept
prompt), a challenge (1.1.7), someone joining the room this player hosts, this player's turn in a community room, a
friend's invite, a tournament set that is ready, the opponent's rematch question -- each tells a player who is
elsewhere once, a player who looks nothing, and the setting switches it off. Lobby updates, chat and the like never
do.

Nothing makes a sound or flashes a window here: the tab's notifier gets a fake player and a fake flash, the clock is
the test's, and "the player is elsewhere" is a switch (the tab's own rule: test_the_players_attention). The windows
are withdrawn, as in every tab test; T5_NOTIFY=0 (util.py) keeps even the real hooks quiet."""
import json
import time
import types
import unittest
from unittest import mock

import util  # noqa: F401
from util import client, expect

from test_tk_tab import TkBase, tk
from test_tk_tour import TkTourBase

from t5lobby import notify, padnav, tk_tab


class NotifyMixin:
    def hook_up(self):
        """Fake player and flash, the test's clock, and a switch for 'the player is elsewhere'."""
        self.played, self.flashed, self.logged, self.calls = [], [], [], []
        self.now = 1000.0
        self.elsewhere = True
        n = self.tab.notifier
        n.play = lambda: self.played.append(self.now)
        n.flash = lambda: self.flashed.append(self.now)
        n.log = self.logged.append
        n.clock = lambda: self.now
        n.away = lambda: self.elsewhere
        real = n.notify

        def spy(kind, key=None):
            fired = real(kind, key)
            self.calls.append((kind, key, fired))
            return fired
        n.notify = spy

    def told(self):
        """How many times the player was told (a chime and a flash each)."""
        self.assertEqual(len(self.played), len(self.flashed))
        return len(self.played)

    def later(self, seconds=30):
        self.now += seconds

    def kinds(self, fired=None):
        return [k for k, _key, f in self.calls if fired is None or f == fired]

    def settle(self, rounds=15):
        for _ in range(rounds):
            self.root.update()
            time.sleep(0.02)


@unittest.skipIf(tk is None, "no tkinter")
class MatchFoundTest(NotifyMixin, TkBase):
    def setUp(self):
        super().setUp()
        self.hook_up()

    def start_search(self):
        tab = self.tab
        tab.server_var.set(self.s.addr)
        tab.do_login("guest")
        self.pump(lambda: tab.client is not None and tab.client.me is not None)
        self.other = client(self.s, "Rival", auto_ready=True)
        self.pump(lambda: len(tab.tv_players.get_children()) == 2)

    def find_match(self):
        self.pump(lambda: str(self.tab.actions["quick"].cget("state")) == "normal")   # (after a declined match: later)
        self.tab.actions["quick"].invoke()
        self.other.quick_match()
        self.pump(lambda: self.bar_button("Accept") is not None)

    def test_the_accept_prompt_chimes_once_and_flashes(self):
        tab = self.tab
        self.start_search()
        self.settle()
        self.assertEqual(self.calls, [])                          # logging in and the lobby's updates: nothing
        self.find_match()
        self.assertEqual(self.told(), 1)
        self.assertEqual(self.logged, ["notify: match"])
        self.assertEqual(self.calls, [("match", tab.match["match"], True)])
        self.settle(40)                                           # lobby updates, polls: no second chime
        tab.on_event({"t": "chat", "from": {"name": "Rival"}, "text": "gl"})
        tab.on_event(dict(tab.match))                             # the very same match_found again
        self.assertEqual(self.told(), 1)
        self.bar_button("Accept").invoke()
        self.pump(lambda: len(self.app.games) == 1)
        self.pump(lambda: tab.view._stage == "match")
        self.settle()
        self.assertEqual(self.told(), 1)                          # accepted, revealed, started: all quiet
        self.assertEqual(self.kinds(), ["match", "match"])        # (the repeated one was recognized)
        self.assertEqual(self.kinds(fired=True), ["match"])

    def test_a_player_who_looks_hears_nothing(self):
        self.elsewhere = False
        self.start_search()
        self.find_match()
        self.assertEqual(self.told(), 0)
        self.assertEqual(self.logged, [])

    def test_off_in_settings(self):
        tab = self.tab
        self.app.settings["notify"] = False
        self.start_search()
        self.find_match()
        self.assertEqual(self.told(), 0)
        self.bar_button("Decline").invoke()                       # no match after all ...
        self.pump(lambda: tab.match is None and self.bar_button("Accept") is None)
        expect(self.other, "match_cancel")
        self.app.settings["notify"] = True                        # ... and on again: the next one counts
        self.later()
        self.find_match()
        self.assertEqual(self.told(), 1)

    def test_a_match_that_starts_by_itself_is_quiet(self):
        """No Accept prompt (a friend's accepted invite, a ranked set's next game, a rematch both wanted): no chime."""
        tab = self.tab
        self.start_search()
        tab.on_event({"t": "match_found", "match": "m0000000000000001", "ready_check": False, "blind": False,
                      "origin": "invite", "ranked": False, "opponent": {"name": "Rival", "rating": 1500, "guest": True},
                      "slot": 0, "role": "host"})
        self.assertEqual(self.calls, [])
        self.assertEqual(self.told(), 0)

    def test_the_rematch_question_chimes_once(self):
        tab = self.tab
        self.start_search()
        self.find_match()
        self.assertEqual(self.told(), 1)
        self.bar_button("Accept").invoke()
        self.pump(lambda: len(self.app.games) == 1)
        self.pump(lambda: tab.view._stage == "match")
        g = self.app.games[0]
        slot = 0 if g.env["T5_NET_MODE"] == "host" else 1
        with open(g.env["T5_NET_RESULT_FILE"], "w") as f:
            json.dump({"winner": slot, "score": [3, 1] if slot == 0 else [1, 3]}, f)
        self.other.report_result(slot, [3, 1] if slot == 0 else [1, 3])
        self.pump(lambda: tab.last_result is not None)
        self.settle()
        self.assertEqual(self.told(), 1)                          # the result card: the window comes forward, no chime
        self.later()
        ev = expect(self.other, "match_result")
        self.other.rematch(ev["match"], True)                     # the opponent asks for a rematch
        self.pump(lambda: self.told() == 2)
        self.assertEqual(self.kinds(fired=True), ["match", "rematch"])
        self.assertEqual(self.calls[-1][1], ev["match"])
        self.settle(40)
        for _ in range(5):
            tab._poll()
        self.assertEqual(self.told(), 2)                          # once
        tab.on_driver({"t": "driver", "kind": "rematch_offer", "match": ev["match"], "opponent": "Rival", "timeout": 20})
        self.later()
        self.assertEqual(self.told(), 2)                          # the same question again: not news


@unittest.skipIf(tk is None, "no tkinter")
class RoomsTest(NotifyMixin, TkBase):
    server_cfg = {"room_next_seconds": 0.5}

    def setUp(self):
        super().setUp()
        self.hook_up()
        self.others = []

    def tearDown(self):
        for c in self.others:
            c.close()
        super().tearDown()

    def peer(self, name, **kw):
        c = client(self.s, name, **kw)
        self.others.append(c)
        return c

    def login(self, name="Roomer"):
        tab = self.tab
        tab.server_var.set(self.s.addr)
        tab.name_var.set(name)
        tab.do_login("guest")
        self.pump(lambda: tab.client is not None and tab.client.me is not None)
        self.pump(lambda: str(tab.actions["room"].cget("state")) == "normal")

    def create(self, size, rotation="Winner stays"):
        tab = self.tab
        tab.actions["room"].invoke()
        w = tab.rooms_ui.window
        self.assertIsNotNone(w)
        w.vars["size"].set(str(size))
        w.vars["rotation"].set(rotation)
        w.vars["access"].set("Anybody")
        self.root.update()
        w.create_button.invoke()
        self.pump(lambda: tab.client.my_room is not None and tab.rooms_ui.window is None)
        return tab.client.my_room

    def test_someone_joins_my_community_room(self):
        tab = self.tab
        self.login()
        room = self.create(4, "Everyone in turn")
        self.settle()
        self.assertEqual(self.calls, [])                          # my own room opening is not news
        amy = self.peer("Amy", auto_ready=True)
        amy.join_room(room["id"])
        self.pump(lambda: "join" in self.kinds())
        self.assertEqual(self.kinds()[0], "join")
        self.pump(lambda: self.bar_button("Accept") is not None)  # one second later: our match with Amy, to accept
        self.assertEqual(self.told(), 1)                          # ... the same moment for the player: one chime
        self.assertEqual(self.kinds(fired=True), ["join"])
        self.assertIn("match", self.kinds(fired=False))
        # Ben joins a minute later: the host hears it again
        self.bar_button("Decline").invoke()
        self.pump(lambda: self.bar_button("Accept") is None)
        self.later()
        ben = self.peer("Ben", auto_ready=True)
        ben.join_room(room["id"])
        self.pump(lambda: self.told() == 2)
        self.assertEqual(self.kinds(fired=True)[-1], "join")
        self.assertEqual(self.logged[-1], "notify: join")

    def test_someone_joins_my_classic_room_one_chime_for_it_and_the_match(self):
        tab = self.tab
        self.login()
        room = self.create(2)
        self.settle()
        amy = self.peer("Amy", auto_ready=True)
        amy.join_room(room["id"])
        self.pump(lambda: self.bar_button("Accept") is not None)
        self.settle(30)
        self.assertEqual(self.told(), 1)
        self.assertIn("match", self.kinds())
        self.assertEqual(sorted(set(self.kinds())), ["join", "match"])

    def test_a_visitor_hears_about_his_turn_and_not_about_joins(self):
        tab = self.tab
        self.login("Visitor")
        amy = self.peer("Amy", auto_ready=True)
        room = amy.create_room(None, size=4, rotation="queue")
        tab.call(tab.client.join_room, room["id"])                # the tab joins Amy's room: its turn is next
        self.pump(lambda: self.told() == 1)
        self.assertEqual(self.kinds(fired=True), ["turn"])
        self.assertEqual(self.logged, ["notify: turn"])
        self.pump(lambda: self.bar_button("Accept") is not None)  # the countdown ran out: the ready check (same moment)
        self.bar_button("Decline").invoke()
        self.pump(lambda: self.bar_button("Accept") is None)
        self.later()
        ben = self.peer("Ben", auto_ready=True)
        ben.join_room(room["id"])
        self.pump(lambda: tab.client.my_room and len(tab.client.my_room["players"]) == 3)
        self.settle(30)
        self.assertNotIn("join", self.kinds())                    # a visitor is not told who comes in
        self.assertEqual(self.told(), 1)

    def test_leaving_the_room_forgets_it(self):
        tab = self.tab
        self.login()
        room = self.create(4)
        self.assertEqual(tab.room_watch.room_id, room["id"])
        tab.client.leave_room()
        self.pump(lambda: tab.room_watch.room_id is None)

    def test_a_room_of_my_own_when_i_am_looking(self):
        self.elsewhere = False
        self.login()
        room = self.create(4)
        amy = self.peer("Amy", auto_ready=True)
        amy.join_room(room["id"])
        self.pump(lambda: self.bar_button("Accept") is not None)
        self.assertEqual(self.told(), 0)
        self.assertIn("join", self.kinds())


@unittest.skipIf(tk is None, "no tkinter")
class InviteTest(NotifyMixin, TkBase):
    def setUp(self):
        super().setUp()
        self.hook_up()

    def test_a_friends_invite_chimes_once(self):
        tab = self.tab
        tab.server_var.set(self.s.addr)
        tab.name_var.set("Ranker")
        tab.pw_var.set("secret-pw1")
        tab.ask_string = lambda *a, **k: "secret-pw1"
        tab.do_login("register")
        self.pump(lambda: tab.client is not None and tab.client.me is not None)
        self.pump(lambda: tab.codes_window is not None)
        tab.codes_window.destroy()
        self.pump(lambda: tab.client.friend_list is not None)
        self.other = client(self.s, "Rival", password="rival-pw1", register=True, auto_ready=True)
        tab.nb.select(tab.friends_page)
        tab.friend_name_var.set("Rival")
        self.pump(lambda: str(tab.friend_actions["add"].cget("state")) == "normal")
        tab.friend_actions["add"].invoke()
        self.pump(lambda: "Friend request sent to Rival" in tab.status_var.get())
        expect(self.other, "friend_request")
        self.other.answer_friend("Ranker", True)
        self.pump(lambda: "Rival accepted your friend request." in tab.status_var.get())
        self.settle()
        self.assertEqual(self.calls, [])                          # a friend request, a friend coming online: quiet
        self.other.invite("Ranker", "casual")
        self.pump(lambda: self.bar_button("Accept") is not None)
        self.assertEqual(self.told(), 1)
        self.assertEqual(self.logged, ["notify: invite"])
        self.assertEqual(self.calls, [("invite", tab.invite["invite"], True)])
        self.later()
        tab.on_event(dict(tab.invite))                            # the same invite again: not news
        self.settle(30)
        self.assertEqual(self.told(), 1)
        self.bar_button("Accept").invoke()                        # accepted: the match starts by itself, quietly
        self.pump(lambda: len(self.app.games) == 1)
        self.assertEqual(self.told(), 1)


@unittest.skipIf(tk is None, "no tkinter")
class TournamentTest(NotifyMixin, TkTourBase):
    def setUp(self):
        super().setUp()
        self.hook_up()

    def test_a_tournament_set_that_is_ready_chimes_once(self):
        tab = self.tab
        self.login()
        org = self.player("Org")
        rival = self.player("Rival")
        t = org.tour_create("Tab Cup", fmt="single", set_wins=2, start=time.time() + 600, max_players=8)
        rival.tour_join(t["id"])
        tab.client.tour_join(t["id"])
        self.settle()
        self.assertEqual(self.calls, [])                          # signing up, the lists: quiet
        org.tour_admin(t["id"], "start")
        self.pump_all(lambda: self.bar_button("Accept") is not None)
        self.assertEqual(self.told(), 1)
        call = tab.tours.call
        self.assertEqual(self.calls, [("tour", (t["id"], call["set"]["id"]), True)])
        self.assertEqual(self.logged, ["notify: tour"])
        self.later()
        tab.on_event(dict(call))                                  # the call again (the server repeats it): not news
        self.settle(30)
        self.assertEqual(self.told(), 1)
        self.assertEqual(self.kinds(fired=True), ["tour"])        # (the server may well send the call more than once)
        self.assertGreaterEqual(len(self.kinds()), 2)


@unittest.skipIf(tk is None, "no tkinter")
class ChallengeTest(NotifyMixin, TkBase):
    """1.1.7, a player: "in the challenge request make it play a sound so I can have it minimized and know I got
    challenged"."""

    def setUp(self):
        super().setUp()
        self.hook_up()

    def login_and_get_challenged(self):
        tab = self.tab
        tab.server_var.set(self.s.addr)
        tab.do_login("guest")
        self.pump(lambda: tab.client is not None and tab.client.me is not None)
        self.other = client(self.s, "Tazaz")
        self.pump(lambda: len(tab.tv_players.get_children()) == 2)
        self.settle()
        self.assertEqual(self.calls, [])                          # logging in, the list, a player coming: quiet
        self.other.challenge(tab.client.me["id"])
        self.pump(lambda: self.bar_button("Accept") is not None)
        return tab.challenge

    def test_a_challenge_chimes_once_and_flashes(self):
        tab = self.tab
        cid = self.login_and_get_challenged()
        self.assertEqual(self.told(), 1)
        self.assertEqual(self.logged, ["notify: challenge"])
        self.assertEqual(self.calls, [("challenge", cid, True)])
        self.later()
        tab.on_event(dict(tab.challenge_ev))                      # the very same challenge again: not news
        self.settle(30)
        self.assertEqual(self.told(), 1)
        self.bar_button("Decline").invoke()
        self.settle()
        self.assertEqual(self.told(), 1)

    def test_a_player_who_looks_hears_nothing(self):
        self.elsewhere = False
        cid = self.login_and_get_challenged()
        self.assertEqual(self.told(), 0)
        self.assertEqual(self.logged, [])
        self.assertEqual(self.calls, [("challenge", cid, False)])

    def test_off_in_settings(self):
        self.app.settings["notify"] = False
        self.login_and_get_challenged()
        self.assertEqual(self.told(), 0)

    def test_the_same_challenger_rings_once_a_minute(self):
        """Anybody in the lobby can challenge: one challenger cannot ring the bell over and over."""
        tab = self.tab
        self.login_and_get_challenged()
        self.assertEqual(self.told(), 1)
        frm = dict(tab.challenge_ev["from"])
        for i, wait in enumerate((30, 25)):                        # 30 s, 55 s later: new challenges, same player
            self.later(wait)
            tab.on_event({"t": "challenged", "challenge": f"again-{i}", "from": dict(frm, name=frm["name"].upper())})
            self.assertEqual(self.told(), 1)
        self.later(6)                                              # a minute after the chime
        tab.on_event({"t": "challenged", "challenge": "again-2", "from": frm})
        self.assertEqual(self.told(), 2)
        self.later(5)                                              # another player: their own minute
        tab.on_event({"t": "challenged", "challenge": "amy-1", "from": dict(frm, id="p-amy", name="Amy")})
        self.assertEqual(self.told(), 3)
        self.assertEqual(self.kinds(fired=True), ["challenge"] * 3)

    def test_unheard_does_not_count(self):
        """A challenge the player saw (no chime) does not start the minute: the next one rings."""
        tab = self.tab
        self.elsewhere = False
        self.login_and_get_challenged()
        frm = dict(tab.challenge_ev["from"])
        self.elsewhere = True
        self.later(5)
        tab.on_event({"t": "challenged", "challenge": "again", "from": frm})
        self.assertEqual(self.told(), 1)


@unittest.skipIf(tk is None, "no tkinter")
class AttentionTest(TkBase):
    """The tab's own rule for 'the player is elsewhere' and its hooks."""

    def away(self, state="normal", front=False, viewable=True):
        tab = self.tab
        top = types.SimpleNamespace(state=lambda: state)
        with mock.patch.object(self.root, "winfo_toplevel", lambda: top), \
                mock.patch.object(tab, "launcher_in_front", lambda: front), \
                mock.patch.object(tab, "_tab_viewable", lambda: viewable):
            return tab._notify_away()

    def test_the_players_attention(self):
        self.assertFalse(self.away(state="withdrawn"))                          # never shown: no taskbar button
        self.assertTrue(self.away(front=False))                                 # another program in front (or a dialog)
        self.assertTrue(self.away(state="iconic", front=False))                 # minimized
        self.assertFalse(self.away(front=True, viewable=True))                  # looking at the Online tab
        self.assertTrue(self.away(front=True, viewable=False))                  # the launcher is in front, on Settings
        self.assertFalse(self.tab._notify_away())                               # (this test's own window is withdrawn)

    def test_the_setting_is_read_when_it_matters(self):
        self.assertTrue(self.tab._notify_enabled())                             # on by default (no value saved)
        self.app.settings["notify"] = False
        self.assertFalse(self.tab._notify_enabled())
        self.app.settings["notify"] = True
        self.assertTrue(self.tab._notify_enabled())

    def test_the_flash_goes_to_the_launchers_window(self):
        seen = []
        with mock.patch.object(padnav, "toplevel_hwnd", lambda w: 0x4242), \
                mock.patch.object(notify, "flash_window", lambda hwnd: seen.append(hwnd) or True):
            self.assertTrue(self.tab._notify_flash())
        self.assertEqual(seen, [0x4242])

    def test_real_hooks_make_no_noise_in_a_test(self):
        self.assertFalse(notify.play_chime())                                   # T5_NOTIFY=0 (util.py)
        self.assertFalse(notify.flash_window(0x4242))

    def test_a_broken_event_never_breaks_the_tab(self):
        tab = self.tab
        tab.notifier.notify = mock.Mock(side_effect=RuntimeError("boom"))
        tab._notify_event({"t": "invited", "invite": 1})
        tab._notify_event({"t": "challenged", "challenge": 1, "from": None})
        tab._notify_event({"t": "match_found", "match": "m", "ready_check": True})
        tab._notify_event({"t": "room", "room": "not a room"})
        tab._notify_driver({"kind": "rematch_offer", "match": "m"})
        tab._notify_event({})


if __name__ == "__main__":
    unittest.main()
