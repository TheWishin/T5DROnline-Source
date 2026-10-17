"""The Online tab driven by a controller: a fake pad (no hardware), a fake clock for the pad thread's
polling rules, a real lobby server and a plain second client. The whole loop without the mouse: A searches,
A accepts the found match, the game runs, the result arrives, A offers the rematch; B declines, leaves,
stops the search. Nothing happens while the launcher is not in front, while the tab is not showing, with
the switch off, on a button that was not let go first, on a press that waited too long, or on a stick
button that is not Cross in the game's controls.ini."""
import json
import os
import unittest

import util  # noqa: F401  (the path, and T5_PAD_NAV=0: the tab does not start real pads by itself)
from util import client, expect

from test_padnav import FakeClock, FakePad
from test_tk_tab import TkBase, tk
from t5lobby import padnav
from t5lobby.padmap import DINPUT


@unittest.skipIf(tk is None, "no tkinter")
class PadTabBase(TkBase):
    server_cfg = {"blind_ready": True, "ready_timeout": 8.0}

    def setUp(self):
        super().setUp()
        self.clock = FakeClock()
        self.front = True            # the launcher's window is the foreground window
        self.visible = True          # ... and the Online tab is the one showing
        self.pad = FakePad()
        self.tab.pad_visible = lambda: self.visible
        self.nav = self.tab.start_pad([self.pad], foreground=lambda: self.front, clock=self.clock, thread=False)

    # --- the pad, at 60 Hz of fake time; the tab sees each press the moment it happens
    def run_pad(self, seconds):
        end = self.clock.t + seconds
        while self.clock.t < end - 1e-9:
            self.nav.step(self.clock.t)
            self.tab._pad_tick()
            self.clock.t += 1 / 60
        self.root.update()

    def hold(self, src, seconds=0.1, pad=None):
        pad = pad or self.pad
        pad.held.add(src)
        self.run_pad(seconds)
        pad.held.discard(src)

    def tap(self, src, pad=None, before=0.5, after=0.7):
        """Everything up for `before`, one clean press, then wait out the tab's cooldown."""
        self.run_pad(before)
        self.hold(src, 0.1, pad)
        self.run_pad(after)

    # --- the lobby
    def login_guest(self, name="TabUser"):
        tab = self.tab
        tab.server_var.set(self.s.addr)
        tab.name_var.set(name)
        tab.do_login("guest")
        self.pump(lambda: tab.client is not None and tab.client.me is not None)
        self.pump(lambda: str(tab.actions["quick"].cget("state")) == "normal")

    def login_account(self, name="Ranker"):
        tab = self.tab
        tab.server_var.set(self.s.addr)
        tab.name_var.set(name)
        tab.pw_var.set("secret-pw1")
        tab.ask_string = lambda *a, **k: "secret-pw1"
        tab.do_login("register")
        self.pump(lambda: tab.client is not None and tab.client.me is not None)
        self.pump(lambda: tab.codes_window is not None)
        tab.codes_window.destroy()
        self.pump(lambda: str(tab.actions["ranked"].cget("state")) == "normal")

    def status_of(self, name):
        return self.s.call(lambda: self.s.srv.by_name[name].status)

    def text(self, key):
        return str(self.tab.actions[key].cget("text"))

    def bar_texts(self):
        return [str(w.cget("text")) for w in self.tab.bar_buttons.winfo_children()] if self.tab.bar.winfo_manager() else []

    def found_match(self, name="Rival"):
        """The tab (a guest) is searching with the controller and `name` finds it: the ready bar is up."""
        self.login_guest()
        self.other = client(self.s, name, auto_ready=True)
        self.pump(lambda: len(self.tab.tv_players.get_children()) == 2)
        self.tap("A")                                              # A = Quick match
        self.pump(lambda: self.status_of("tabuser") == "queue")
        self.other.quick_match()
        self.pump(lambda: "Accept (A)" in self.bar_texts())


@unittest.skipIf(tk is None, "no tkinter")
class PadTabTest(PadTabBase):
    def test_a_searches_accepts_and_b_declines(self):
        tab = self.tab
        self.login_guest()
        self.other = client(self.s, "Rival", auto_ready=True)
        self.pump(lambda: len(tab.tv_players.get_children()) == 2)
        self.run_pad(0.5)
        self.assertEqual(self.text("quick"), "Quick match (A)")             # the names are on the buttons
        self.assertEqual(self.text("ranked"), "Ranked match")               # (guests: no ranked)
        self.assertIn("Controller:", tab.pad_info_var.get())
        self.tap("A")
        self.pump(lambda: self.status_of("tabuser") == "queue")             # A searched
        self.pump(lambda: self.text("cancel") == "Stop searching (B)")
        self.other.quick_match()
        self.pump(lambda: "Accept (A)" in self.bar_texts())
        self.assertIn("Decline (B)", self.bar_texts())
        self.assertEqual(self.text("cancel"), "Stop searching")             # the bar's buttons own A and B now
        self.tap("A")
        self.pump(lambda: len(self.app.games) == 1)                         # A accepted: the game started
        self.assertIn("T5_NET_MODE", self.app.games[0].env)

    def test_b_declines_a_found_match(self):
        self.found_match()
        self.tap("B")
        self.pump(lambda: "declined" in self.tab.status_var.get().lower())
        self.assertEqual(self.app.games, [])

    def test_b_stops_a_search(self):
        self.login_guest()
        self.tap("A")
        self.pump(lambda: self.status_of("tabuser") == "queue")
        self.pump(lambda: str(self.tab.actions["cancel"].cget("state")) == "normal")
        self.tap("B")
        self.pump(lambda: self.status_of("tabuser") == "idle")
        self.pump(lambda: self.text("quick") == "Quick match (A)")

    def test_an_account_searches_ranked_then_the_way_it_searched_last(self):
        self.login_account()
        self.run_pad(0.5)
        self.assertEqual(self.text("ranked"), "Ranked match (A)")
        self.assertEqual(self.text("quick"), "Quick match")
        self.tap("A")
        self.pump(lambda: self.status_of("ranker") == "queue")
        self.pump(lambda: str(self.tab.actions["cancel"].cget("state")) == "normal")
        self.tap("B")
        self.pump(lambda: self.status_of("ranker") == "idle")
        self.pump(lambda: str(self.tab.actions["quick"].cget("state")) == "normal")
        self.tab.actions["quick"].invoke()                                  # a quick match with the mouse once ...
        self.pump(lambda: self.status_of("ranker") == "queue")
        self.pump(lambda: str(self.tab.actions["cancel"].cget("state")) == "normal")
        self.tab.actions["cancel"].invoke()
        self.pump(lambda: self.status_of("ranker") == "idle")
        self.pump(lambda: str(self.tab.actions["quick"].cget("state")) == "normal")
        self.run_pad(0.2)
        self.assertEqual(self.text("quick"), "Quick match (A)")             # ... and A does the same from now on
        self.assertEqual(self.text("ranked"), "Ranked match")

    def test_triangle_does_nothing_there_is_no_stage_choice(self):
        self.login_guest()
        self.tap("Y")
        self.run_pad(0.5)
        self.assertEqual(self.status_of("tabuser"), "idle")

    def test_nothing_else_on_the_pad_does_anything(self):
        self.login_guest()
        for src in ("X", "LB", "START", "BACK", "DUP", "RT"):
            self.tap(src, after=0.1)
        self.assertEqual(self.status_of("tabuser"), "idle")

    # ------------------------------------------------------------------ when it must not act
    def test_mashing_does_not_accept(self):
        self.found_match()
        self.front = False                      # the fight is on
        self.run_pad(0.2)
        for _ in range(40):
            self.hold("A", 0.06)
            self.run_pad(0.06)
        self.front = True                       # the game is over; the launcher comes forward, still mashing
        for _ in range(40):
            self.hold("A", 0.06)
            self.hold("B", 0.03)
            self.run_pad(0.04)
        self.assertIn("Accept (A)", self.bar_texts())                       # no decision was made for the player
        self.assertEqual(self.app.games, [])
        self.assertNotIn("declined", self.tab.status_var.get().lower())
        self.tap("A")                                                       # let go for a moment: now it counts
        self.pump(lambda: len(self.app.games) == 1)

    def test_not_while_the_game_is_in_front(self):
        self.found_match()
        self.front = False
        reads = self.pad.reads
        for src in ("A", "B", "A"):
            self.tap(src)
        self.assertEqual(self.pad.reads, reads)                             # not even looked at
        self.assertEqual(self.app.games, [])
        self.assertIn("Accept (A)", self.bar_texts())
        self.assertNotIn("declined", self.tab.status_var.get().lower())

    def test_a_press_that_arrives_late_is_dropped(self):
        self.found_match()
        self.run_pad(0.5)
        self.nav.events.put(padnav.PadEvent("cross", self.clock.t - 5.0, "fake:0", "A"))   # waited 5 s for the Tk thread
        self.tab._pad_tick()
        self.assertEqual(self.app.games, [])
        self.assertIn("Accept (A)", self.bar_texts())

    def test_a_press_is_checked_again_when_the_tab_runs_it(self):
        self.found_match()
        self.run_pad(0.5)
        self.nav.events.put(padnav.PadEvent("cross", self.clock.t, "fake:0", "A"))
        self.front = False                      # the game came forward between the pad thread and the tab
        self.tab._pad_tick()
        self.assertEqual(self.app.games, [])

    def test_a_press_is_checked_against_the_tab_too(self):
        self.found_match()
        self.run_pad(0.5)
        self.nav.events.put(padnav.PadEvent("cross", self.clock.t, "fake:0", "A"))
        self.visible = False                    # another launcher tab came forward in the meantime
        self.tab._pad_tick()
        self.assertEqual(self.app.games, [])

    def test_not_while_the_tab_is_hidden(self):
        self.found_match()
        self.visible = False                    # another launcher tab
        self.tap("A")
        self.assertEqual(self.app.games, [])
        self.visible = True
        self.tap("A")                           # the tab is back; the press before it did not count
        self.pump(lambda: len(self.app.games) == 1)

    def test_the_switch(self):
        tab = self.tab
        self.found_match()
        tab.pad_var.set(0)
        tab._pad_toggle()
        self.assertEqual(self.bar_texts(), ["Accept", "Decline"])           # no names on the buttons
        self.assertEqual(tab.pad_info_var.get(), "Controller off.")
        self.tap("A")
        self.assertEqual(self.app.games, [])
        with open(os.path.join(os.environ["T5_ONLINE_DIR"], "online.json")) as f:
            self.assertFalse(json.load(f)["pad"])                           # remembered
        tab.pad_var.set(1)
        tab._pad_toggle()
        self.tap("A")
        self.pump(lambda: len(self.app.games) == 1)

    def test_an_unplugged_pad_takes_its_names_off(self):
        self.found_match()
        self.pad.plugged = False
        self.run_pad(0.3)
        self.assertEqual(self.bar_texts(), ["Accept", "Decline"])
        self.assertEqual(self.tab.pad_info_var.get(), "No controller found.")
        self.pad.plugged = True
        self.run_pad(0.3)
        self.assertEqual(self.bar_texts(), ["Accept (A)", "Decline (B)"])

    def test_two_presses_at_once_do_one_thing_at_most(self):
        tab = self.tab
        self.login_guest()
        hits = []
        tab.show_bar("question", [("Yes", lambda: hits.append("yes"), "cross"), ("No", lambda: hits.append("no"), "circle")])
        self.run_pad(0.5)
        for b in ("cross", "circle"):                                       # as if two pads pressed within a frame
            self.nav.events.put(padnav.PadEvent(b, self.clock.t, "fake:0", "x"))
        tab._pad_tick()
        self.assertEqual(hits, ["yes"])

    def test_questions_without_a_pad_answer_are_left_to_the_player(self):
        tab = self.tab
        self.found_match()
        self.tap("A")
        self.pump(lambda: len(self.app.games) == 1)
        self.app.games[0].done = True                                       # the game closed without a result file
        self.pump(lambda: self.bar_button("I won") is not None)
        self.tap("A")
        self.tap("B")
        self.assertIsNotNone(self.bar_button("I won"))                      # still waiting for the player
        self.assertEqual(self.status_of("tabuser"), "playing")
        self.assertEqual(tab.last_result, None)

    # ------------------------------------------------------------------ the loop after the match
    def play_one_match(self):
        """found_match() + A to accept + a result file written by the (fake) game."""
        self.found_match()
        self.tap("A")
        self.pump(lambda: len(self.app.games) == 1)
        env = self.app.games[0].env
        slot = 0 if env["T5_NET_MODE"] == "host" else 1
        with open(env["T5_NET_RESULT_FILE"], "w") as f:
            json.dump({"winner": slot, "score": [2, 1] if slot == 0 else [1, 2]}, f)
        self.app.games[0].done = True
        self.other.report_result(slot, [2, 1] if slot == 0 else [1, 2])
        self.pump(lambda: "Rematch Rival (A)" in self.bar_texts())

    def test_the_whole_loop_with_the_pad_only_rematch(self):
        self.play_one_match()
        self.assertIn("Leave (B)", self.bar_texts())
        self.tap("A")
        ev = expect(self.other, "rematch")
        self.assertEqual(ev["state"], "offered")                            # A offered the rematch

    def test_b_leaves_instead_of_a_rematch(self):
        self.play_one_match()
        self.tap("Y")                                                       # Triangle: nothing
        self.assertIn("Rematch Rival (A)", self.bar_texts())
        self.tap("B")
        ev = expect(self.other, "rematch")
        self.assertEqual(ev["state"], "declined")

    def test_a_rematch_offered_by_the_opponent(self):
        self.play_one_match()
        self.tab.hide_bar()
        self.tab.rematch_bar = None
        self.tab.on_driver({"kind": "rematch_offer", "opponent": "Rival"})
        self.pump(lambda: "Rematch (A)" in self.bar_texts())
        self.assertIn("No thanks (B)", self.bar_texts())


@unittest.skipIf(tk is None, "no tkinter")
class PadStickTest(PadTabBase):
    """A stick whose buttons were remapped in the game's controls.ini."""

    def test_the_stick_follows_controls_ini(self):
        stick = FakePad(DINPUT, "winmm:1", "Fight Stick", 0x0F0D, 0x00EE, None)
        self.tab.pad = None                     # (the base class started the XInput pad; it has no thread)
        with open(os.path.join(self.dir, "controls.ini"), "w") as f:      # <out>/controls.ini: the game's working directory
            f.write("[dinput]\nCROSS = B1\nCIRCLE = B4\n")
        self.nav = self.tab.start_pad([stick], foreground=lambda: self.front, clock=self.clock, thread=False)
        self.pad = stick
        self.found_match_with_stick()
        self.assertEqual(self.bar_texts(), ["Accept (B1)", "Decline (B4)"])
        self.tap("B2")                          # Cross in the preset, but not in this controls.ini
        self.tap("B3")
        self.assertEqual(self.app.games, [])
        self.assertIn("Accept (B1)", self.bar_texts())
        self.tap("B1")
        self.pump(lambda: len(self.app.games) == 1)

    def found_match_with_stick(self):
        self.login_guest()
        self.other = client(self.s, "Rival", auto_ready=True)
        self.pump(lambda: len(self.tab.tv_players.get_children()) == 2)
        self.tab.actions["quick"].invoke()
        self.pump(lambda: self.status_of("tabuser") == "queue")
        self.other.quick_match()
        self.pump(lambda: self.tab.bar.winfo_manager() != "")
        self.run_pad(0.5)                                   # the pad is looked at: the names go on the buttons

    def test_a_macro_button_is_not_a_cross(self):
        stick = FakePad(DINPUT, "winmm:1", "Fight Stick", 1, 2, None)
        self.tab.pad = None
        with open(os.path.join(self.dir, "controls.ini"), "w") as f:
            f.write("[dinput]\n3+4 = B2\n")                  # one button for Cross+Circle
        self.nav = self.tab.start_pad([stick], foreground=lambda: self.front, clock=self.clock, thread=False)
        self.pad = stick
        self.login_guest()
        self.tap("B2")
        self.run_pad(0.5)
        self.assertEqual(self.status_of("tabuser"), "idle")                # neither a search nor anything else
        self.assertEqual(self.text("quick"), "Quick match")                # and no Cross on a button that has none

    def test_the_stick_hat_as_cross(self):
        stick = FakePad(DINPUT, "winmm:1", "Fight Stick", 1, 2, None)
        self.tab.pad = None
        with open(os.path.join(self.dir, "controls.ini"), "w") as f:
            f.write("[dinput]\nCROSS = HAT_DOWN\n")
        self.nav = self.tab.start_pad([stick], foreground=lambda: self.front, clock=self.clock, thread=False)
        self.pad = stick
        self.login_guest()
        self.tap("HAT_DOWN")
        self.pump(lambda: self.status_of("tabuser") == "queue")


if __name__ == "__main__":
    unittest.main()
