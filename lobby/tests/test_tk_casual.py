"""The Online tab's casual choices (tk_casual.py; docs/ONLINE.md "Sides and stages by choice"), driven like a player
would against a real server and another client (nothing is shown): the side and stage choices under the character
(hidden on a server without them), kept in online.json and sent to the server; a challenger's wishes in the question;
the side and stage on the match card; Rematch: swap sides (Triangle) after a casual match, and the opponent's offer
with the sides swapped; no Swap sides after a quick match."""
import time
import unittest

import util  # noqa: F401
from util import client, expect

from test_tk_tab import TkBase, tk


@unittest.skipIf(tk is None, "no tkinter")
class TkCasualTest(TkBase):
    def login(self, name="Caster"):
        tab = self.tab
        tab.server_var.set(self.s.addr)
        tab.name_var.set(name)
        tab.do_login("guest")
        self.pump(lambda: tab.client is not None and tab.client.me is not None)
        self.pump(lambda: tab.casual.row.winfo_manager() == "grid")

    def wish(self):
        pid = self.tab.client.me["id"]
        p = self.s.call(lambda: self.s.srv.players.get(pid))
        return getattr(p, "casual_side", None), getattr(p, "casual_stage", "random")

    def choose(self, side_label, stage_label):
        cas = self.tab.casual
        cas.side_var.set(side_label)
        cas.stage_var.set(stage_label)
        cas.on_change()

    def challenge_from_rival(self, **kw):
        """Rival challenges the tab; the tab accepts. -> (the tab's game, the challenge question's text)."""
        tab = self.tab
        self.other = client(self.s, "Rival", **kw)
        self.pump(lambda: len(tab.tv_players.get_children()) == 2)
        self.other.challenge(tab.client.me["id"])
        self.pump(lambda: self.bar_button("Accept") is not None)
        text = tab.bar_text.get()
        self.bar_button("Accept").invoke()
        self.pump(lambda: len(self.app.games) == 1)
        return self.app.games[0], text

    def play_to_the_rematch_question(self, game):
        tab = self.tab
        slot = 0 if game.env["T5_NET_MODE"] == "host" else 1
        game.done = True
        self.pump(lambda: self.bar_button("I won") is not None)
        self.bar_button("I won").invoke()
        self.other.report_result(slot, None)
        self.pump(lambda: self.bar_button("Rematch Rival") is not None)
        return slot

    def test_the_choices_go_to_the_server_and_stay(self):
        tab = self.tab
        self.login()
        cas = tab.casual
        self.assertEqual(cas.side_var.get(), "Any side")
        self.assertEqual(cas.stage_var.get(), "Random stage")
        names = list(cas.stage_cb.cget("values"))
        self.assertEqual(names[0], "Random stage")
        self.assertIn("Ghetto Pit", names)
        self.assertIn("Western Gate", names)
        self.assertNotIn("Stage 17", names)                      # every stage has its name
        self.choose("P2 (right)", "Ghetto Pit")
        self.pump(lambda: self.wish() == (1, "s20"))
        self.assertEqual((tab.cfg["casual_side"], tab.cfg["casual_stage"]), (1, "s20"))
        # a new login sends them again (they live in online.json)
        tab.do_logout()
        self.pump(lambda: tab.client is None)
        self.assertEqual(tab.casual.row.winfo_manager(), "")         # hidden while logged out
        self.login("Caster2")
        self.pump(lambda: self.wish() == (1, "s20"))
        self.assertEqual(tab.casual.side_var.get(), "P2 (right)")

    def test_a_challenge_with_wishes_and_swap_sides(self):
        tab = self.tab
        self.login()
        self.choose("P2 (right)", "Industrial Complex")
        self.pump(lambda: self.wish() == (1, "s33"))
        self.other = client(self.s, "Rival")
        self.other.set_casual_prefs(0, "s33")
        self.pump(lambda: len(tab.tv_players.get_children()) == 2)
        self.other.challenge(tab.client.me["id"])
        self.pump(lambda: self.bar_button("Accept") is not None)
        self.assertIn("Rival", tab.bar_text.get())
        self.assertIn("wants to be P1 on Industrial Complex", tab.bar_text.get())
        self.bar_button("Accept").invoke()
        self.pump(lambda: len(self.app.games) == 1)
        game = self.app.games[0]
        self.assertEqual(game.env["T5_NET_MODE"], "join")             # the tab asked for P2, Rival for P1
        self.pump(lambda: "(P2 on Industrial Complex)" in tab.match_var.get())
        self.play_to_the_rematch_question(game)
        swap = self.bar_button("Rematch: swap sides")
        self.assertIsNotNone(swap)
        self.assertIn("triangle", tab.bar_pad)                       # (Y on a pad)
        swap.invoke()
        off = expect(self.other, "rematch")
        self.assertEqual((off["state"], off.get("swap")), ("offered", True))
        self.other.rematch(off["match"], True)
        self.pump(lambda: len(self.app.games) >= 1 and tab.driver.ticket is not None
                  and tab.driver.ticket.role == "host", timeout=30)
        self.pump(lambda: "(P1 on Industrial Complex)" in tab.match_var.get())

    def card(self):
        """Every text on the bar's card (the challenge / invite question)."""
        self.root.update()
        out = []

        def walk(w):
            for c in w.winfo_children():
                if "text" in c.keys():
                    out.append(str(c.cget("text")))
                walk(c)
        walk(self.tab.view.bar_visual)
        return out

    def test_the_card_shows_the_wishes(self):
        """1.1.7: the challenger's and a friend's side / stage wishes are on the card before the answer (they were only
        in the bar's text, which the redesigned card does not show)."""
        tab = self.tab
        self.login()
        self.other = client(self.s, "Rival")
        self.other.set_casual_prefs(1, "s27")
        self.pump(lambda: len(tab.tv_players.get_children()) == 2)
        self.other.challenge(tab.client.me["id"])
        self.pump(lambda: self.bar_button("Accept") is not None)
        self.assertIn("wants to be P2 on Aurora Australis", self.card())
        self.assertIn("wants to be P2 on Aurora Australis", tab.bar_text.get())        # (and the text, as before)
        self.bar_button("Decline").invoke()
        self.pump(lambda: tab.challenge is None)
        friend = {"id": "p-fr", "name": "Friend", "guest": False, "rating": 1500, "rank": "1st Dan", "tier": 10,
                  "provisional": False, "placement": None}
        for i, (wish, line) in enumerate(((None, None), ({"side": None, "stage": "random"}, None),
                                          ({"side": 0, "stage": "random"}, "wants to be P1"),
                                          ({"side": None, "stage": "s20"}, "wants to play on Ghetto Pit"))):
            tab.client.events.put({"t": "invited", "invite": f"i{i}", "kind": "casual", "from": friend, "wish": wish})
            self.pump(lambda: (tab.invite or {}).get("invite") == f"i{i}")
            card = self.card()
            self.assertIn("Friend", card)
            wishes = [x for x in card if x.startswith("wants to") and not x.startswith("wants to play you")]
            self.assertEqual(wishes, [line] if line else [])                   # nothing when both are left open
            tab._answer_invite(False)

    def test_the_opponent_asks_for_the_swap(self):
        tab = self.tab
        self.login()
        game, text = self.challenge_from_rival()
        self.assertNotIn("wants", text)                               # Rival left both open
        mid = tab.driver.ticket.match_id
        self.play_to_the_rematch_question(game)
        self.other.rematch(mid, True, swap=True)
        self.pump(lambda: "with the sides swapped" in tab.bar_text.get())
        self.assertIsNone(self.bar_button("Rematch: swap sides"))     # (asked already)

    def test_no_swap_after_a_quick_match(self):
        tab = self.tab
        self.login()
        self.other = client(self.s, "Rival", auto_ready=True)
        self.pump(lambda: len(tab.tv_players.get_children()) == 2)
        tab.actions["quick"].invoke()
        self.other.quick_match()
        self.pump(lambda: self.bar_button("Accept") is not None)
        self.bar_button("Accept").invoke()
        self.pump(lambda: len(self.app.games) == 1)
        self.play_to_the_rematch_question(self.app.games[0])
        self.assertIsNone(self.bar_button("Rematch: swap sides"))
        self.assertNotIn("(P", tab.match_var.get())


@unittest.skipIf(tk is None, "no tkinter")
class TkCasualOldServerTest(TkBase):
    def test_hidden_without_the_feature(self):
        tab = self.tab
        import t5lobby.server.lobby as lobby_mod            # (an older server: the new one without the feature)
        saved = list(lobby_mod.FEATURES)
        lobby_mod.FEATURES[:] = [f for f in saved if f != "casual_choice"]
        try:
            tab.server_var.set(self.s.addr)
            tab.name_var.set("Oldie")
            tab.do_login("guest")
            self.pump(lambda: tab.client is not None and tab.client.me is not None)
            for _ in range(10):
                self.root.update()
                time.sleep(0.02)
            self.assertEqual(tab.casual.row.winfo_manager(), "")
        finally:
            lobby_mod.FEATURES[:] = saved


if __name__ == "__main__":
    unittest.main()
