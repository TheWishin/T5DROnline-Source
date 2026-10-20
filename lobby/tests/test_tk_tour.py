"""The Online tab's tournaments (docs/TOURNAMENTS.md, t5lobby/tk_tour.py), driven like a player would against a real
server, with withdrawn windows: the Tournaments page lists them, Sign up, the card "Your tournament set is ready" with
Accept, the set's games in the tab's (fake) game, the bracket on its canvas, the Create window, the organizer's
buttons, and the page in German."""
import os
import time
import unittest

import util  # noqa: F401  (sys.path, T5_PAD_NAV)
from util import client

try:
    import tkinter as tk
    import test_tk_tab as tkt
except ImportError:      # pragma: no cover
    tk = None

from t5lobby import i18n, tour_text
from t5lobby.server.store import hash_password

TOUR = dict(set_next_seconds=0.3, tour_tick=0.05, tour_noshow=30.0, max_per_ip=40, conn_burst=60, conn_rate=20.0,
            state_burst=200, state_rate=50.0)


@unittest.skipIf(tk is None, "no tkinter")
class TkTourBase(tkt.TkBase if tk is not None else unittest.TestCase):
    server_cfg = TOUR

    def setUp(self):
        super().setUp()
        self.others = {}

    def tearDown(self):
        for c in self.others.values():
            c.close()
        super().tearDown()

    def player(self, name):
        pw = "pw-" + name.lower() + "-x"
        self.s.call(lambda: self.s.srv.store.create_account(name, hash_password(pw, n=1 << 10)))
        c = client(self.s, name, password=pw, sets=True, tournaments=True)
        self.others[name] = c
        return c

    def login(self, name="Tabby"):
        tab = self.tab
        tab.server_var.set(self.s.addr)
        tab.name_var.set(name)
        tab.pw_var.set("secret-pw1")
        tab.ask_string = lambda *a, **k: "secret-pw1"
        tab.do_login("register")
        self.pump(lambda: tab.client is not None and tab.client.me is not None)
        self.pump(lambda: tab.codes_window is not None)
        tab.codes_window.destroy()

    def show_page(self):
        tab = self.tab
        tab.nb.select(tab.tours_page)
        self.root.update()
        tab._on_subtab()
        self.pump(lambda: tab.tours.page_shown)

    def page_button(self, key):
        b = self.tab.tours.page["buttons"][key]
        return b if b.winfo_manager() else None

    def drain(self, c, on=None):
        """The other launchers: accept calls, say set_next between games; `on(ev)` sees every event."""
        while True:
            ev = c.next_event(0)
            if ev is None:
                return
            if ev["t"] == "tour_call" and not ev["accepted"][0]:
                try:
                    c.tour_accept(ev["tournament"]["id"], ev["set"]["id"])
                except Exception:      # noqa: BLE001 -- an older call
                    pass
            elif ev["t"] == "match_result" and (ev.get("set") or {}).get("next"):
                try:
                    c.set_next(None, keep=False)
                except Exception:      # noqa: BLE001
                    pass
            if on:
                on(ev)

    def pump_all(self, cond, timeout=20.0):
        def step():
            for c in self.others.values():
                self.drain(c)
            return cond()
        return self.pump(step, timeout)


class TkTourFlowTest(TkTourBase):
    def test_sign_up_the_call_a_set_and_the_bracket(self):
        tab = self.tab
        self.login()
        org = self.player("Org")
        rival = self.player("Rival")
        t = org.tour_create("Tab Cup", fmt="single", set_wins=2, start=time.time() + 600, max_players=8)
        rival.tour_join(t["id"])
        self.show_page()
        self.pump(lambda: len(tab.tours.page["tree"].get_children()) == 1)
        tv = tab.tours.page["tree"]
        self.assertIn("Tab Cup", tv.item(t["id"], "values")[0])
        self.assertEqual(tv.item(t["id"], "values")[1], "Sign-up")
        tv.selection_set(t["id"])
        self.pump(lambda: tab.tours.detail is not None and self.page_button("join") is not None)
        self.assertEqual(str(tab.tours.page["title"].cget("text")), "Tab Cup")
        self.assertIsNone(self.page_button("start"))             # not the organizer
        self.page_button("join").invoke()
        self.pump(lambda: self.page_button("leave") is not None)
        self.assertIn("You are signed up.", str(tab.tours.page["you"].cget("text")))
        self.assertEqual(tab.status_var.get(), "You are signed up.")
        # the organizer starts it: the tab gets the call
        org.tour_admin(t["id"], "start")
        self.pump_all(lambda: self.bar_button("Accept") is not None)
        self.assertIn("Your tournament set is ready", tab.bar_text.get())
        self.assertIn("vs Rival", tab.bar_text.get())
        self.root.update()
        self.assertEqual((tab.view._stage, tab.view._bar_kind), ("bar", "tour_call"))
        self.assertIsNotNone(tab.view.ring)                      # the no-show countdown
        self.assertIn("started", tab.status_var.get())          # "The tournament Tab Cup has started: ..."
        # another question takes the bar for a while (a challenge, a result ...): the call comes back after it
        tab.show_bar("Something else", [("Fine", tab.hide_bar)])
        self.root.update()
        self.assertNotEqual(tab.view._bar_kind_now(), "tour_call")
        self.bar_button("Fine").invoke()
        self.pump(lambda: self.bar_button("Accept") is not None and tab.view._bar_kind_now() == "tour_call")
        self.bar_button("Accept").invoke()
        # the set: the tab's fake game, two games won
        for n in (1, 2):
            self.pump_all(lambda: len(self.app.games) >= n and self.app.games[n - 1].running())
            g = self.app.games[n - 1]
            slot = 0 if g.env["T5_NET_MODE"] == "host" else 1
            self.pump_all(lambda: f"game {n} of 3" in tab.set_var.get())
            if n == 1:
                self.assertIn("Tournament set vs Rival", tab.match_var.get())
                self.assertEqual(str(tab.view.m_pill.cget("text")), "TOURNAMENT")
            g.done = True
            self.pump_all(lambda: self.bar_button("I won") is not None)
            self.bar_button("I won").invoke()
            rival.report_result(slot, None)
        self.pump_all(lambda: "You won the set 2-0" in tab.status_var.get()
                      or "You won the tournament" in tab.status_var.get())
        self.pump_all(lambda: (tab.tours.detail or {}).get("state") == "finished")
        texts = tab.tours.bracket.texts
        self.assertTrue(any(x in ("1  Tabby", "2  Tabby") for x in texts), texts)     # seed + name on the canvas
        self.assertTrue(any(x in ("1  Rival", "2  Rival") for x in texts), texts)
        self.assertIn("2", texts)                                # Tabby's score
        self.assertIn("W1-1", tab.tours.bracket.boxes)
        self.assertIn("1. Tabby", str(tab.tours.page["standings"].cget("text")))
        self.assertIn("You finished place 1.", str(tab.tours.page["you"].cget("text")))
        self.pump_all(lambda: "You won the tournament Tab Cup!" in tab.status_var.get())


class TkTourCreateTest(TkTourBase):
    def test_the_create_window(self):
        tab = self.tab
        self.login()
        self.show_page()
        self.pump(lambda: str(tab.tours.page["create"].cget("state")) == "normal")
        tab.tours.page["create"].invoke()
        w = tab.tours.create_win
        self.assertIsNotNone(w)
        self.assertEqual(w.state(), "withdrawn")                 # (the test's windows are never shown)
        v = w.tour_vars
        v["name"].set("Night Cup")
        v["format"].set("Single elimination")
        v["sets"].set("First to 3 games (best of 5)")
        v["players"].set("32")
        v["checkin"].set("Check-in 15 minutes before")
        v["seeding"].set("Seeded by rating")
        v["at"].set("25:99")
        w.tour_create()
        self.assertIn("HH:MM", str(w.tour_error.cget("text")))   # a bad time: said, nothing sent
        v["at"].set("")
        v["start"].set("in 2 hours")
        w.tour_create()
        self.pump(lambda: tab.tours.detail is not None and tab.tours.detail.get("name") == "Night Cup")
        d = tab.tours.detail
        self.assertEqual((d["format"], d["set_wins"], d["max_players"], d["checkin_minutes"], d["seeding"]),
                         ("single", 3, 32, 15, "rating"))
        self.assertAlmostEqual(d["start"], time.time() + 7200, delta=60)
        self.assertFalse(w.winfo_exists())
        self.pump(lambda: self.page_button("start") is not None)    # the organizer's buttons
        self.assertIsNotNone(self.page_button("cancel"))
        self.assertIn("Tournament Night Cup created.", tab.status_var.get())


class TkTourOrganizerTest(TkTourBase):
    def test_start_report_reset_and_disqualify(self):
        tab = self.tab
        self.login("Boss")
        a, b, c, d = (self.player(n) for n in ("Ana", "Bo", "Cy", "Di"))
        t = tab.client.tour_create("Boss Cup", start=time.time() + 600)
        for x in (a, b, c, d):
            x.tour_join(t["id"])
        self.show_page()                                         # (nobody accepts: the organizer decides)
        tab.tours.select(t["id"])
        self.pump(lambda: self.page_button("start") is not None)
        tab.ask_yes_no = lambda *a, **k: True
        self.page_button("start").invoke()
        self.pump(lambda: (tab.tours.detail or {}).get("state") == "running")
        self.pump(lambda: "W1-1" in tab.tours.bracket.boxes)
        tools = tab.tours.page["set_tools"]
        self.assertEqual(str(tools["win0"].cget("state")), "disabled")      # no set picked yet
        x0, y0, x1, y1 = tab.tours.bracket.boxes["W1-1"]
        tab.tours.select_set("W1-1")                              # (a click on the box)
        self.root.update()
        self.assertEqual(str(tools["win0"].cget("state")), "normal")
        row = tab.tours._set_row()
        self.assertEqual(row["live"], "called")
        name0 = row["p"][0]
        self.assertEqual(str(tools["win0"].cget("text")), f"{name0} wins")
        tools["win0"].invoke()
        self.pump(lambda: (tab.tours._set_row() or {}).get("state") == "done")
        self.assertEqual(tab.tours._set_row()["winner"], 0)
        self.assertEqual(tab.tours._set_row()["reason"], "organizer")
        tools["reset"].invoke()
        self.pump(lambda: (tab.tours._set_row() or {}).get("state") == "open")
        self.pump(lambda: (tab.tours._set_row() or {}).get("live") == "called")
        tab.ask_string = lambda *a, **k: name0
        tools["dq"].invoke()
        self.pump(lambda: (tab.tours._set_row() or {}).get("reason") == "dq")
        self.assertEqual(tab.tours._set_row()["winner"], 1)
        ents = {e["name"]: e for e in tab.tours.detail["entrants"]}
        self.assertEqual(ents[name0]["dq"], "organizer")
        self.assertIn("disqualified by the organizer", str(tab.tours.page["players"].cget("text")))
        self.assertIn("DISQUALIFIED", tab.tours.bracket.texts)
        self.page_button("cancel").invoke()
        self.pump(lambda: (tab.tours.detail or {}).get("state") == "cancelled")


class TkTourWatchTest(TkTourBase):
    def test_watch_a_set_from_the_bracket(self):
        """The Tournaments page's Watch (docs/SPECTATE.md "Tournaments"): a set being played, both players allow
        spectators -> the clicked set can be watched in this PC's game, the Spectating card says TOURNAMENT."""
        tab = self.tab
        self.login("Tabby")
        org = self.player("Org")
        ps = []
        for n in ("Ana", "Bo"):
            pw = "pw-" + n.lower() + "-x"
            self.s.call(lambda n=n, pw=pw: self.s.srv.store.create_account(n, hash_password(pw, n=1 << 10)))
            c = client(self.s, n, password=pw, sets=True, tournaments=True, spectate=True,
                       live_dir=os.path.join(self.dir, n, "live"), watch_dir=os.path.join(self.dir, n, "watch"))
            c.set_spectate_prefs(True, False)
            self.others[n] = c
            ps.append(c)
        t = org.tour_create("Watch Cup", fmt="single", start=time.time() + 600)
        for c in ps:
            c.tour_join(t["id"])
        org.tour_admin(t["id"], "start")
        # both accept; nobody reports a result: the set's first game is being played
        self.pump_all(lambda: self.s.call(lambda: all(
            (self.s.srv.by_name[n].match is not None and self.s.srv.by_name[n].match.state == "playing")
            for n in ("ana", "bo"))), timeout=30)
        self.show_page()
        tab.tours.select(t["id"])
        self.pump_all(lambda: "W1-1" in tab.tours.bracket.boxes)
        tab.tours.select_set("W1-1")
        watch = tab.tours.page["watch"]
        self.pump_all(lambda: (tab.tours._set_row() or {}).get("watch") and str(watch.cget("state")) == "normal",
                      timeout=30)
        watch.invoke()
        self.pump_all(lambda: tab.spec.w is not None and tab.spec.w.get("game") is not None)
        self.assertEqual((tab.spec.w["tournament"] or {}).get("set"), "W1-1")
        self.assertEqual(self.app.games[-1].env.get("T5_NET_MODE"), "replay")     # this PC's game plays the stream
        self.root.update()
        tab.spec.update_card()
        self.assertEqual(str(tab.spec.pill.cget("text")), "TOURNAMENT")
        self.assertEqual(str(watch.cget("state")), "disabled")                    # (watching already)
        tab.spec.stop()
        self.pump_all(lambda: str(watch.cget("state")) == "normal")


class TkTourGermanTest(TkTourBase):
    def test_the_page_in_german(self):
        tab = self.tab
        self.login()
        org = self.player("Org")
        rival = self.player("Rival")
        t = org.tour_create("Pokal", fmt="double", start=time.time() + 600, checkin_minutes=10)
        rival.tour_join(t["id"])
        tab.client.tour_join(t["id"])
        org.tour_join(t["id"])
        org.tour_admin(t["id"], "start")
        full = tab.client.tour_get(t["id"])
        calls = []
        t_end = time.monotonic() + 10
        while time.monotonic() < t_end and not calls:
            ev = tab.client.next_event(0.1)
            if ev is not None and ev["t"] == "tour_call":
                calls.append(ev)
        i18n.set_language("de")
        i18n.clear_missing()
        try:
            from t5lobby.tk_tab import OnlineTab
            root2 = tk.Toplevel(self.root)
            root2.withdraw()
            tab2 = OnlineTab(root2, self.app)
            tab2.tours.rows = [full]
            tab2.tours.selected = full["id"]
            tab2.tours.detail = full
            tab2.tours.render_list()
            tab2.tours.select_set("W1-1")
            call = next((e for e in calls if e["t"] == "tour_call"), None)
            if call is not None:
                tab2.client = tab.client
                tab2.tours.on_event(call)
                tab2.view.refresh()
                tab2.client = None
            root2.update()
            self.assertEqual(i18n.missing(), [])
            self.assertEqual(tab2.nb.tab(tab2.tours_page, "text"), "Turniere")
            labels = " ".join(tab2.tours.bracket.texts)
            self.assertIn("GRAND FINAL", labels)
            self.assertIn("LOSERS-FINALE", labels)
            self.assertIn("Double Elimination", str(tab2.tours.page["info"].cget("text")))
            self.assertEqual(tour_text.round_label({"bracket": "W", "round": 1, "rounds": 2, "format": "single"}),
                             "Halbfinale")
            tab2.on_close()
            root2.destroy()
        finally:
            i18n.set_language("en")


class TourTextTest(unittest.TestCase):
    def test_round_names(self):
        single = {"format": "single", "rounds": 4, "losers_rounds": 0}
        self.assertEqual([tour_text.round_label(dict(single, bracket="W", round=r)) for r in (1, 2, 3, 4)],
                         ["Round 1", "Quarter-final", "Semi-final", "Final"])
        double = {"format": "double", "rounds": 3, "losers_rounds": 4}
        self.assertEqual([tour_text.round_label(dict(double, bracket="W", round=r)) for r in (1, 2, 3)],
                         ["Winners round 1", "Winners semi-final", "Winners final"])
        self.assertEqual([tour_text.round_label(dict(double, bracket="L", round=r)) for r in (1, 2, 3, 4)],
                         ["Losers round 1", "Losers round 2", "Losers semi-final", "Losers final"])
        self.assertEqual(tour_text.round_label(dict(double, bracket="GF", round=2)), "Grand final reset")

    def test_notices(self):
        ev = {"t": "tour_notice", "tournament": {"id": "t1", "name": "Cup"}}
        self.assertEqual(tour_text.notice_text(dict(ev, code="finished", place=1)), "You won the tournament Cup!")
        self.assertEqual(tour_text.notice_text(dict(ev, code="dq", reason="no_show")),
                         "You are out of Cup: did not show up.")
        self.assertEqual(tour_text.notice_text(dict(ev, code="eliminated", place=5)), "You are out of Cup: place 5.")
        self.assertIn("not enough players", tour_text.notice_text(dict(ev, code="cancelled", reason="not_enough")))

    def test_parse_clock(self):
        from t5lobby.tk_tour import parse_clock
        now = time.mktime((2026, 10, 19, 20, 0, 0, 0, 0, -1))
        self.assertEqual(time.localtime(parse_clock("21:30", now))[3:5], (21, 30))
        self.assertGreater(parse_clock("21:30", now), now)
        tomorrow = parse_clock("19:00", now)
        self.assertGreater(tomorrow - now, 20 * 3600)
        self.assertIsNone(parse_clock("25:00", now))
        self.assertIsNone(parse_clock("x", now))
        self.assertIsNone(parse_clock("", now))


if __name__ == "__main__":
    unittest.main()
