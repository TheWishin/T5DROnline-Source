"""Ranked costume chosen in the launcher (1.2.3, docs/RANKED.md "Costumes in ranked"): with the "ranked_costume" cap
on both clients a rated set has no select screen -- every game, the first too, starts with the launchers' fighters and
costumes (`fight.buttons`); a client without the cap keeps the in-game pick of game 1. Also the launcher side:
the costume table (fighters.costume_buttons), the remembered costume per fighter (tk_costume), the client sending it
only to a server that takes it, and the match driver's own in-game pick (remembered for casual)."""
import types
import unittest

import util
from util import ServerThread, client, expect
from t5lobby import fighters, proto, tk_costume
from t5lobby.client import LobbyClient
from t5lobby.match_driver import MatchDriver
from t5lobby.proto import LobbyError
from t5lobby.server import Config


class Base(unittest.TestCase):
    server_cfg = {"set_next_seconds": 0.3}

    def setUp(self):
        self.s = ServerThread(**self.server_cfg).start()
        self.clients = []

    def tearDown(self):
        for c in self.clients:
            c.close()
        self.s.stop()

    def acc(self, name, costume_cap=True, **kw):
        c = client(self.s, name, password="pw-" + name, register=True, auto_ready=True, ingame_pick=True, sets=True,
                   ranked_costume=costume_cap, **kw)
        self.clients.append(c)
        return c

    def ranked(self, a, b, ca=("jin", 2), cb=("steve", 3)):
        a.ranked_match(ca[0], costume=ca[1])
        b.ranked_match(cb[0], costume=cb[1])
        return expect(a, "match_start"), expect(b, "match_start")

    @staticmethod
    def mine(ev):
        f = ev["fight"]
        return (f["p1"], f["p2"]) if ev["slot"] == 0 else (f["p2"], f["p1"])

    @staticmethod
    def my_buttons(ev):
        b = ev["fight"].get("buttons") or [0, 0]
        return (b[0], b[1]) if ev["slot"] == 0 else (b[1], b[0])

    def play(self, a, b, ev, winner, desync=None):
        for c in (a, b):
            try:
                c.report_result(winner, [3, 1] if winner == 0 else [1, 3], ev["match"], source="game", desync=desync)
            except LobbyError:
                if not desync:
                    raise
        return expect(a, "match_result"), expect(b, "match_result")

    def next_game(self, a, b, keep=True):
        for c in (a, b):
            c.set_next(None, keep=keep)
        return expect(a, "match_start", 20.0), expect(b, "match_start", 20.0)


class LauncherPickTest(Base):
    def test_features_and_default(self):
        a = self.acc("Alice")
        self.assertIn("ranked_costume", a.welcome["features"])
        self.assertIn("ranked_costume", a.welcome["caps"])
        self.assertTrue(a.costume_ok())
        self.assertTrue(Config().ranked_launcher_pick)
        self.assertFalse(Config.from_env({"T5L_RANKED_LAUNCHER_PICK": "0"}).ranked_launcher_pick)

    def test_every_game_of_the_set_starts_with_the_launchers_fighters_and_costumes(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        ea, eb = self.ranked(a, b)
        self.assertEqual((ea["set"]["rated"], ea["set"]["number"]), (True, 1))
        for ev in (ea, eb):
            self.assertNotIn("pick", ev["fight"])                  # no select screen, game 1 too
        self.assertEqual(self.mine(ea), ("jin", "steve"))
        self.assertEqual(self.my_buttons(ea), (2, 3))              # Alice RP (Jin's third), Bob LK
        self.assertEqual(ea["fight"]["buttons"], eb["fight"]["buttons"])   # the same line on both PCs
        self.play(a, b, ea, 0)
        e2, _ = self.next_game(a, b)
        self.assertNotIn("pick", e2["fight"])
        self.assertEqual((self.mine(e2), self.my_buttons(e2)), (("jin", "steve"), (2, 3)))
        self.play(a, b, e2, 1)
        e3, _ = self.next_game(a, b, keep=False)                   # game 3 over a new connection
        self.assertEqual((e3["set"]["number"], self.mine(e3), self.my_buttons(e3)), (3, ("jin", "steve"), (2, 3)))
        self.play(a, b, e3, 0)
        se = expect(a, "set_end")
        self.assertEqual((se["status"], se["games"]), ("confirmed", 3))
        hist = a.profile("Alice", 5)["history"]
        self.assertEqual({(h["you_char"], h["opp_char"]) for h in hist}, {("jin", "steve")})

    def test_set_char_carries_the_costume(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        a.set_char("xiaoyu", 4)                                    # her fourth costume
        b.set_char("kuma", 1)
        a.ranked_match("xiaoyu")                                   # (queue without a costume keeps it)
        b.ranked_match("kuma")
        ea, _ = expect(a, "match_start"), expect(b, "match_start")
        self.assertEqual((self.mine(ea), self.my_buttons(ea)), (("xiaoyu", "kuma"), (4, 1)))

    def test_random_is_drawn_once_for_the_whole_set_with_the_default_costume(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        ea, eb = self.ranked(a, b, ca=(fighters.RANDOM, 3), cb=("lili", 1))
        drawn = self.mine(ea)[0]
        self.assertNotEqual(drawn, fighters.RANDOM)
        self.assertEqual(self.my_buttons(ea), (0, 1))              # Random: the game's default costume
        self.play(a, b, ea, 0)
        e2, _ = self.next_game(a, b)
        self.assertEqual((self.mine(e2), self.my_buttons(e2)), ((drawn, "lili"), (0, 1)))

    def test_default_costumes_send_no_buttons(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        ea, _ = self.ranked(a, b, ca=("jin", 0), cb=("steve", 0))
        self.assertNotIn("pick", ea["fight"])
        self.assertNotIn("buttons", ea["fight"])

    def test_a_costume_change_during_the_set_waits_for_the_next_set(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        ea, _ = self.ranked(a, b)
        self.play(a, b, ea, 0)
        a.set_char("jin", 3)                                       # same fighter, another costume: taken, not used
        e2, _ = self.next_game(a, b)
        self.assertEqual(self.my_buttons(e2), (2, 3))
        with self.assertRaises(LobbyError) as e:
            a.set_char("paul", 1)                                  # the fighter stays locked
        self.assertEqual(e.exception.code, proto.E_STATE)

    def test_a_replayed_game_1_keeps_the_launchers_picks(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        ea, _ = self.ranked(a, b)
        ra, _ = self.play(a, b, ea, 0, desync=9)                   # void: game 1 again
        self.assertEqual((ra["status"], ra["set"]["number"]), ("void", 1))
        e1, _ = self.next_game(a, b)
        self.assertEqual(e1["set"]["number"], 1)
        self.assertNotIn("pick", e1["fight"])
        self.assertEqual((self.mine(e1), self.my_buttons(e1)), (("jin", "steve"), (2, 3)))

    def test_bad_costumes_are_refused(self):
        a = self.acc("Alice")
        for bad in (5, -1, True, "2", 1.0):
            with self.assertRaises(LobbyError) as e:
                a._call({"t": "set_char", "char": "jin", "costume": bad})
            self.assertEqual(e.exception.code, proto.E_BAD_REQUEST)
        with self.assertRaises(LobbyError):
            a._call({"t": "queue", "mode": "ranked", "char": "jin", "costume": 9})


class MixedTest(Base):
    def test_a_client_without_the_cap_keeps_the_in_game_pick_of_game_1(self):
        a, b = self.acc("Alice"), self.acc("Bob", costume_cap=False)
        self.assertFalse(b.costume_ok())
        ea, eb = self.ranked(a, b)
        self.assertEqual((ea["fight"]["pick"], eb["fight"]["pick"]), (30, 30))
        self.assertNotIn("buttons", ea["fight"])
        # game 1 picked in the game: the set keeps that, even if the other launcher could pick
        picked = ["kazuya", "lili"] if ea["slot"] == 0 else ["lili", "kazuya"]
        costumes = [2, 4] if ea["slot"] == 0 else [4, 2]
        for c in (a, b):
            c.report_result(0, [3, 1], ea["match"], source="game", chars=picked, costumes=costumes)
        expect(a, "match_result"), expect(b, "match_result")
        e2, _ = self.next_game(a, b)
        self.assertEqual((self.mine(e2), e2["fight"]["buttons"]), (("kazuya", "lili"), costumes))


class OffTest(Base):
    server_cfg = {"set_next_seconds": 0.3, "ranked_launcher_pick": False}

    def test_the_server_can_switch_it_off(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        ea, _ = self.ranked(a, b)
        self.assertEqual(ea["fight"]["pick"], 30)
        self.assertNotIn("buttons", ea["fight"])


class CasualTest(Base):
    def test_quick_matches_keep_the_in_game_select(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        a.quick_match("jin", costume=2)
        b.quick_match("steve", costume=3)
        ea = expect(a, "match_start")
        self.assertEqual(ea["fight"]["pick"], 30)
        self.assertNotIn("buttons", ea["fight"])


class ClientUnitTest(unittest.TestCase):
    def client(self, features, cap=True):
        c = LobbyClient("127.0.0.1:1", util.BUILD, ranked_costume=cap)
        c.welcome = {"features": features}
        sent = []
        c._call = lambda msg: sent.append(msg) or {}
        return c, sent

    def test_costume_only_to_a_server_that_takes_it(self):
        c, sent = self.client(["ranked_costume"])
        c.set_char("jin", 2)
        c.ranked_match("jin", costume=3)
        self.assertEqual(sent[0], {"t": "set_char", "char": "jin", "costume": 2})
        self.assertEqual(sent[1]["costume"], 3)
        for features, cap in ((["ingame_pick"], True), (["ranked_costume"], False)):
            c, sent = self.client(features, cap)
            c.set_char("jin", 2)
            c.ranked_match("jin", costume=3)
            self.assertNotIn("costume", sent[0])
            self.assertNotIn("costume", sent[1])

    def test_out_of_range_sends_the_default(self):
        c, sent = self.client(["ranked_costume"])
        c.set_char("jin", 7)
        self.assertEqual(sent[0]["costume"], 0)


class CostumeTableTest(unittest.TestCase):
    def test_buttons_per_fighter(self):
        """docs/DIRECTFIGHT.md "Mirror matches": two costumes LP/LK, eight a third on RP, Xiaoyu and Asuka four,
        Kuma punch, Panda kick; in the game's model order."""
        self.assertEqual(fighters.costume_buttons("steve"), (1, 3))
        for k in ("law", "yoshimitsu", "jin", "lee", "anna", "ganryu", "bruce", "raven"):
            self.assertEqual(fighters.costume_buttons(k), (1, 3, 2), k)
        self.assertEqual(fighters.costume_buttons("xiaoyu"), (1, 3, 2, 4))
        self.assertEqual(fighters.costume_buttons("asuka"), (1, 3, 2, 4))
        self.assertEqual(fighters.costume_buttons("kuma"), (1,))
        self.assertEqual(fighters.costume_buttons("panda"), (3,))
        self.assertEqual(fighters.costume_buttons(fighters.RANDOM), ())
        self.assertEqual(fighters.costume_buttons("jinpachi"), ())
        for f in fighters.table().selectable():
            self.assertTrue(fighters.costume_buttons(f["key"]), f["key"])

    def test_costume_button_falls_back_to_costume_1(self):
        self.assertEqual(fighters.costume_button("kuma", 3), 1)    # a kick would be Panda
        self.assertEqual(fighters.costume_button("panda", 1), 3)
        self.assertEqual(fighters.costume_button("steve", 2), 1)   # RP = LP for a two-costume fighter
        self.assertEqual(fighters.costume_button("xiaoyu", 4), 4)
        self.assertEqual(fighters.costume_button(fighters.RANDOM, 2), 0)


class RememberTest(unittest.TestCase):
    def test_per_fighter(self):
        cfg = {}
        self.assertEqual(tk_costume.remembered(cfg, "jin"), 1)
        self.assertTrue(tk_costume.remember(cfg, "jin", 2))
        self.assertFalse(tk_costume.remember(cfg, "jin", 2))      # nothing new: no save
        self.assertFalse(tk_costume.remember(cfg, "kuma", 3))     # not one of Kuma's
        self.assertEqual(cfg["costumes"], {"jin": 2})
        self.assertEqual(tk_costume.remembered(cfg, "jin"), 2)
        self.assertEqual(tk_costume.remembered(cfg, "steve"), 1)
        self.assertEqual(tk_costume.remembered({"costumes": {"steve": True}}, "steve"), 1)
        self.assertEqual(tk_costume.remembered({"costumes": "x"}, "steve"), 1)

    def test_labels(self):
        names = tk_costume.labels("jin")
        self.assertEqual(len(names), 3)
        self.assertIn("LP", names[0])
        self.assertIn("LK", names[1])
        self.assertIn("RP", names[2])
        self.assertEqual(tk_costume.labels(fighters.RANDOM), [])

    def test_button_suffix(self):
        tab = types.SimpleNamespace(cfg={"costumes": {"jin": 2}}, key="jin")
        tab._char_key = lambda: tab.key
        self.assertEqual(tk_costume.suffix(tab), " · 3")          # RP = Jin's third costume
        tab.key = "steve"
        self.assertEqual(tk_costume.suffix(tab), " · 1")
        for key in ("kuma", fighters.RANDOM):
            tab.key = key
            self.assertEqual(tk_costume.suffix(tab), "")
        self.assertEqual(tk_costume.number("xiaoyu", 4), 4)
        self.assertEqual(tk_costume.number("steve", 2), 0)

    def test_remember_pick_saves_once(self):
        tab = types.SimpleNamespace(cfg={}, saved=0)
        tab._save_cfg = lambda: setattr(tab, "saved", tab.saved + 1)
        tk_costume.remember_pick(tab, ("lili", 3))
        tk_costume.remember_pick(tab, ("lili", 3))
        tk_costume.remember_pick(tab, None)
        self.assertEqual((tab.cfg["costumes"], tab.saved), ({"lili": 3}, 1))


class DriverOwnPickTest(unittest.TestCase):
    def own(self, slot, pick=30, chars=(9, 33), buttons=(2, 3)):
        d = MatchDriver.__new__(MatchDriver)
        d.table = fighters.table()
        d.match_ev = {"slot": slot, "fight": {"pick": pick}}
        d.fight_chars = list(chars)
        d.fight_buttons = list(buttons) if buttons else None
        return d._own_pick()

    def test_own_side(self):
        self.assertEqual(self.own(0), ("jin", 2))
        self.assertEqual(self.own(1), ("lili", 3))

    def test_nothing_without_an_in_game_pick_or_a_button(self):
        self.assertIsNone(self.own(0, pick=0))
        self.assertIsNone(self.own(0, buttons=(0, 3)))
        self.assertIsNone(self.own(0, buttons=None))
        self.assertIsNone(self.own(None))


if __name__ == "__main__":
    unittest.main()
