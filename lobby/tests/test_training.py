"""Training rooms and the health handicap (1.1.5; docs/ONLINE.md "Training rooms and the health handicap",
server/matchrules.py): a training room only from and for launchers with the `training` cap (an older one is refused
when it joins or is invited), its matches carry `training` and one round in match_start's `fight`, and whatever ends
them they have no result -- no rating, no record, no history, no blame; the rematch keeps the room's rules. The
health handicap: `set_life` (30-100 in steps of 10, the `handicap` cap), shown in the lobby list, in match_found
(this side's view) and in match_start's `fight` as [P1, P2]; never in ranked matches, never against a launcher
without the cap. 1.1.7: up to 150 % from a launcher with the `life150` cap; a launcher without it (1.1.5, 1.1.6)
never gets a value above 100 (a higher value plays as 100 in a match against it)."""

import unittest

import util  # noqa: F401 -- (sets up the paths and the test environment)
from util import ServerThread, client, expect

from t5lobby.proto import LobbyError
from t5lobby.server import matchrules


class Base(unittest.TestCase):
    server_cfg = {}

    def setUp(self):
        self.s = ServerThread(**self.server_cfg).start()
        self.clients = []

    def tearDown(self):
        for c in self.clients:
            c.close()
        self.s.stop()

    def c(self, name, rules=True, **kw):
        c = client(self.s, name, match_rules=rules, **kw)
        self.clients.append(c)
        return c

    def srv(self):
        return self.s.srv

    def player(self, name):
        return self.s.call(lambda: self.srv().by_name.get(name.lower()))


class TrainingRoomTest(Base):
    def test_features_and_caps(self):
        a = self.c("Alice")
        self.assertTrue(a.training_ok())
        self.assertTrue(a.handicap_ok())
        old = self.c("Old", rules=False)
        self.assertFalse(old.training_ok())
        self.assertFalse(old.handicap_ok())
        with self.assertRaises(LobbyError):
            old.create_room("r", training=True)                      # the client refuses before it asks
        with self.assertRaises(LobbyError) as e:                     # and the server refuses a hand-made request
            old._call({"t": "room_create", "name": "r", "training": True})
        self.assertIn("training rooms need a newer launcher", e.exception.msg)

    def test_the_cap_fits_in_a_full_hello(self):
        """A launcher announces every cap it has; the server reads only the first 16 -- match_rules must be among
        them (one cap for both features, sent last)."""
        a = self.c("Alice", blind_ready=True, ingame_pick=True, sets=True, tournaments=True, spectate=True)
        self.assertTrue(a.training_ok() and a.handicap_ok())
        caps = self.s.call(lambda: sorted(self.srv().by_name["alice"].conn.caps))
        self.assertIn("match_rules", caps)

    def test_training_room_match(self):
        a, b = self.c("Alice", auto_ready=True), self.c("Bob", auto_ready=True)
        room = a.create_room("Practice", training=True)
        self.assertTrue(room["training"])
        lst = self.s.call(lambda: [r.public() for r in self.srv().rooms.values()])
        self.assertTrue(lst[0]["training"])
        b.join_room(room["id"])
        fa = expect(a, "match_found", 15)
        self.assertTrue(fa["training"])
        ea, eb = expect(a, "match_start", 30), expect(b, "match_start", 30)
        for ev in (ea, eb):
            self.assertTrue(ev["fight"]["training"])
            self.assertEqual(ev["fight"]["rounds"], matchrules.TRAINING_ROUNDS)
            self.assertNotIn("life", ev["fight"])
            self.assertFalse(ev["ranked"])
        # a give-up: both games say P1 won 1-0 -- a training match has no result all the same
        rec = [list(self.player(n).record) for n in ("Alice", "Bob")]
        for c in (a, b):
            c.report_result(0, [1, 0])
        for c in (a, b):
            res = expect(c, "match_result", 15)
            self.assertEqual(res["status"], "training")
            self.assertIsNone(res["winner"])
            self.assertIsNone(res["blame"])
            self.assertIsNone(res["rating"])
            self.assertIsNone(res["reason"])                         # fought to its end: back to the select screen
            self.assertGreater(res["rematch_window"], 0)            # back to the select screen together
        self.assertEqual([list(self.player(n).record) for n in ("Alice", "Bob")], rec)
        self.assertEqual(self.s.call(lambda: self.srv().store.recent_matches(50)), [])   # no history either
        # the rematch keeps the room's rules
        a.rematch(ea["match"], True, keep=True)
        b.rematch(ea["match"], True, keep=True)
        e2 = expect(a, "match_start", 30)
        self.assertTrue(e2["fight"]["training"])
        self.assertTrue(e2["continue"])

    def test_leaving_a_training_match_is_no_loss(self):
        a, b = self.c("Alice", auto_ready=True), self.c("Bob", auto_ready=True)
        room = a.create_room("Practice", training=True)
        b.join_room(room["id"])
        ea = expect(a, "match_start", 30)
        expect(b, "match_start", 30)
        a.leave_match(ea["match"])
        for c in (a, b):
            res = expect(c, "match_result", 15)
            self.assertEqual(res["status"], "training")
            self.assertIsNone(res["blame"])
        self.assertEqual(list(self.player("Alice").record), [0, 0, 0])

    def test_leave_the_room_during_a_training_fight(self):
        """Leave any time: Leave room during the fight ends the match (no result, reason "left") and leaves; in any
        other room the match must be finished first."""
        a, b = self.c("Alice", auto_ready=True), self.c("Bob", auto_ready=True)
        room = a.create_room("Practice", training=True)
        b.join_room(room["id"])
        expect(a, "match_start", 30)
        expect(b, "match_start", 30)
        b.leave_room()
        for c in (a, b):
            res = expect(c, "match_result", 15)
            self.assertEqual((res["status"], res["reason"], res["blame"]), ("training", "left", None))
        self.assertEqual(self.player("Bob").status, "idle")
        self.assertEqual(self.player("Alice").status, "room")
        # an ordinary room: not during its match
        c, d = self.c("Cid", auto_ready=True), self.c("Dee", auto_ready=True)
        r2 = c.create_room("Casual")
        d.join_room(r2["id"])
        expect(c, "match_start", 30)
        with self.assertRaises(LobbyError) as e:
            d.leave_room()
        self.assertIn("finish the match first", e.exception.msg)

    def test_older_launcher_cannot_join_or_be_invited(self):
        a = self.c("Alice", password="alice-pw-1", register=True)
        old = self.c("Oldie", rules=False, password="oldie-pw-1", register=True)
        room = a.create_room("Practice", training=True)
        with self.assertRaises(LobbyError) as e:
            old.join_room(room["id"])
        self.assertIn("training rooms need a newer launcher", e.exception.msg)
        self.assertEqual(self.s.call(lambda: len(self.srv().rooms[room["id"]].members)), 1)
        # a friend's invite into it is refused too
        self.s.call(lambda: self.srv()._befriend(self.srv().by_name["alice"].account_id,
                                                  self.srv().by_name["oldie"].account_id))
        with self.assertRaises(LobbyError) as e:
            a.invite("Oldie", "room")
        self.assertIn("training rooms need a newer launcher", e.exception.msg)

    def test_not_ranked(self):
        a = self.c("Alice", password="alice-pw-1", register=True)
        with self.assertRaises(LobbyError) as e:
            a._call({"t": "room_create", "name": "r", "ranked": True, "training": True})
        self.assertIn("casual", e.exception.msg)


class HandicapTest(Base):
    def test_set_life_rules(self):
        a = self.c("Alice")
        self.assertEqual(a.set_life(70), 70)
        for bad in (25, 105, 75, 0, True, "80"):
            with self.assertRaises(LobbyError):
                a._call({"t": "set_life", "life": bad})
        self.assertEqual(self.player("Alice").life, 70)
        old = self.c("Old", rules=False)
        with self.assertRaises(LobbyError):
            old._call({"t": "set_life", "life": 50})
        # shown to everybody in the lobby list (the player entries)
        pub = self.s.call(lambda: self.srv().by_name["alice"].public())
        self.assertEqual(pub["life"], 70)
        self.assertNotIn("life", self.s.call(lambda: self.srv().by_name["old"].public()))

    def test_room_match_carries_both_values(self):
        a, b = self.c("Alice", auto_ready=True), self.c("Bob", auto_ready=True)
        a.set_life(60)
        room = a.create_room("Handicap")
        b.join_room(room["id"])
        fa, fb = expect(a, "match_found", 15), expect(b, "match_found", 15)
        self.assertEqual(fa["life"], {"you": 60, "opponent": 100})
        self.assertEqual(fb["life"], {"you": 100, "opponent": 60})
        self.assertNotIn("training", fa)
        ea, eb = expect(a, "match_start", 30), expect(b, "match_start", 30)
        life = [60, 100] if ea["slot"] == 0 else [100, 60]
        self.assertEqual(ea["fight"]["life"], life)
        self.assertEqual(eb["fight"]["life"], life)
        self.assertNotIn("training", ea["fight"])

    def test_quick_match_and_no_handicap_without_the_cap(self):
        a, b = self.c("Alice", auto_ready=True), self.c("Bob", auto_ready=True, rules=False)
        a.set_life(50)
        a.quick_match()
        b.quick_match()
        ea = expect(a, "match_start", 30)
        self.assertNotIn("life", ea["fight"])                        # Bob's game could not play it

    def test_never_in_ranked_or_tournament_matches(self):
        a, b = self.c("Alice"), self.c("Bob")
        p = self.srv().by_name.get
        a.set_life(50)
        b.set_life(80)
        fn = self.srv()._rules_apply_life
        self.assertEqual(self.s.call(lambda: fn(p("alice"), p("bob"), False, "queue")), [50, 80])
        self.assertIsNone(self.s.call(lambda: fn(p("alice"), p("bob"), True, "queue")))
        self.assertIsNone(self.s.call(lambda: fn(p("alice"), p("bob"), False, "tournament")))
        a.set_life(100)
        b.set_life(100)
        self.assertIsNone(self.s.call(lambda: fn(p("alice"), p("bob"), False, "queue")))


class Handicap150Test(Base):
    """1.1.7: the health handicap up to 150 % (the player request: "my friends and I like to play at 120 %")."""

    def new(self, name, **kw):
        kw.setdefault("life150", True)
        return self.c(name, **kw)

    def test_set_life_up_to_150(self):
        a = self.new("Alice")
        self.assertEqual(a.life_max(), 150)
        for v in (110, 120, 150, 30, 100):
            self.assertEqual(a.set_life(v), v)
        for bad in (160, 105, 155, 200):
            with self.assertRaises(LobbyError):
                a._call({"t": "set_life", "life": bad})
        self.assertEqual(self.player("Alice").life, 100)
        a.set_life(120)
        self.assertEqual(self.s.call(lambda: self.srv().by_name["alice"].public())["life"], 120)

    def test_an_older_launcher_stays_at_100(self):
        """A 1.1.6 launcher (match_rules, no life150): the server refuses more than 100 from it, and the 1.1.7
        client never asks for more than the server and its game allow."""
        old = self.new("Old", life150=False)
        self.assertEqual(old.life_max(), 100)
        with self.assertRaises(LobbyError) as e:
            old._call({"t": "set_life", "life": 120})
        self.assertIn("30 to 100", e.exception.msg)
        self.assertEqual(old.set_life(150), 100)          # (the client sends what it may: 100)
        self.assertEqual(self.player("Old").life, 100)

    def test_150_against_100(self):
        a, b = self.new("Alice", auto_ready=True), self.new("Bob", auto_ready=True)
        a.set_life(150)
        room = a.create_room("Handicap")
        b.join_room(room["id"])
        fa, fb = expect(a, "match_found", 15), expect(b, "match_found", 15)
        self.assertEqual(fa["life"], {"you": 150, "opponent": 100})
        self.assertEqual(fb["life"], {"you": 100, "opponent": 150})
        ea, eb = expect(a, "match_start", 30), expect(b, "match_start", 30)
        life = [150, 100] if ea["slot"] == 0 else [100, 150]
        self.assertEqual(ea["fight"]["life"], life)
        self.assertEqual(eb["fight"]["life"], life)

    def test_never_above_100_to_a_launcher_without_the_cap(self):
        """Alice (1.1.7) at 120 % meets Old (a 1.1.6 launcher at 50 %): the match plays 100 / 50 -- Old's
        launcher and game never see 120 (a 1.1.6 launcher would drop the whole life= from its fight line, its game
        would clamp it at 100)."""
        a, old = self.new("Alice", auto_ready=True), self.new("Old", auto_ready=True, life150=False)
        a.set_life(120)
        old.set_life(50)
        room = a.create_room("Mixed")
        old.join_room(room["id"])
        fa, fo = expect(a, "match_found", 15), expect(old, "match_found", 15)
        self.assertEqual(fa["life"], {"you": 100, "opponent": 50})
        self.assertEqual(fo["life"], {"you": 50, "opponent": 100})
        ea, eo = expect(a, "match_start", 30), expect(old, "match_start", 30)
        self.assertEqual(ea["fight"]["life"], eo["fight"]["life"])
        self.assertTrue(all(x <= 100 for x in eo["fight"]["life"]), eo["fight"])

    def test_the_guard_on_its_own(self):
        a, b, old = self.new("Alice"), self.new("Bob"), self.new("Old", life150=False)
        p = self.srv().by_name.get
        a.set_life(150)
        b.set_life(110)
        fn = self.srv()._rules_apply_life
        self.assertEqual(self.s.call(lambda: fn(p("alice"), p("bob"), False, "queue")), [150, 110])
        self.assertEqual(self.s.call(lambda: fn(p("bob"), p("alice"), False, "room")), [110, 150])
        self.assertIsNone(self.s.call(lambda: fn(p("alice"), p("old"), False, "queue")))   # 100 / 100
        self.assertIsNone(self.s.call(lambda: fn(p("alice"), p("bob"), True, "queue")))    # ranked: always 100
        self.assertIsNone(self.s.call(lambda: fn(p("alice"), p("bob"), False, "tournament")))

    def test_the_cap_fits_in_a_full_hello(self):
        a = self.new("Alice", blind_ready=True, ingame_pick=True, sets=True, tournaments=True, spectate=True)
        self.assertTrue(a.handicap_ok())
        self.assertEqual(a.life_max(), 150)

    def test_no_cap_without_match_rules(self):
        a = self.c("Alice", rules=False, life150=True)
        self.assertEqual(a.life_max(), 100)
        self.assertNotIn("life150", (a.welcome or {}).get("caps") or ())


class FightLineTest(unittest.TestCase):
    """The launcher's side: match_start's `fight` -> the fight line's train= / life= (match_driver.fight_rules)."""

    def test_rules_on_the_line(self):
        from t5lobby import match_driver
        f = match_driver.fight_rules
        self.assertEqual(f({"training": True, "life": [70, 100]}), " train=1 life=70|100")
        self.assertEqual(f({"training": True}), " train=1")
        self.assertEqual(f({"life": [100, 40]}), " life=100|40")
        self.assertEqual(f({"life": [100, 100]}), "")
        for bad in ({"training": 1}, {"life": [5, 100]}, {"life": [True, 50]}, {"life": "70|100"}, {"life": [70]}, None):
            self.assertEqual(f(bad), "", bad)
        # 1.1.7: up to 150 %
        self.assertEqual(f({"life": [150, 100]}), " life=150|100")
        self.assertEqual(f({"life": [110, 120]}), " life=110|120")
        self.assertEqual(f({"life": [160, 100]}), "")

    def test_hud_names_say_the_handicap(self):
        from t5lobby import match_driver
        ev = {"players": [{"name": "A_Very_Long_Name_X", "tier": 3}, {"name": "Bob", "tier": 4}],
              "fight": {"life": [70, 100]}}
        names, _tiers = match_driver.hud_values(ev)
        self.assertEqual(names, ["A_Very_Long 70%", "Bob"])
        self.assertTrue(all(len(n) <= 16 for n in names))
        ev["fight"] = {}
        self.assertEqual(match_driver.hud_values(ev)[0], ["A_Very_Long_Name", "Bob"])
        ev["fight"] = {"life": [150, 120]}                       # 1.1.7: three digits still fit in 16 characters
        names, _tiers = match_driver.hud_values(ev)
        self.assertEqual(names, ["A_Very_Long 150%", "Bob 120%"])
        self.assertTrue(all(len(n) <= 16 for n in names))

    def test_ui_texts(self):
        from t5lobby import tk_rules
        self.assertEqual(tk_rules.rules_parts({}), [])
        found = tk_rules.rules_parts({"training": True, "life": {"you": 70, "opponent": 100}})
        self.assertEqual(len(found), 2)
        self.assertIn("70", found[1])
        start = tk_rules.rules_parts({"fight": {"life": [100, 60]}}, slot=1)
        self.assertEqual(len(start), 1)
        self.assertIn("60", start[0])
        self.assertEqual(tk_rules.parse_life(tk_rules.life_label(80)), 80)
        self.assertEqual(tk_rules.parse_life("nonsense"), 100)
        self.assertEqual(tk_rules.clean_life(35), 100)
        # 1.1.7: 150 down to 30; 100 down to 30 for an older game or server
        self.assertEqual(tk_rules.parse_life(tk_rules.life_label(150)), 150)
        self.assertEqual(tk_rules.clean_life(120), 120)
        self.assertEqual(tk_rules.clean_life(160), 100)
        self.assertEqual(tk_rules.picker_values(150)[0], tk_rules.life_label(150))
        self.assertEqual(len(tk_rules.picker_values(150)), 13)
        self.assertEqual(tk_rules.picker_values(100)[0], tk_rules.life_label(100))
        self.assertEqual(len(tk_rules.picker_values(100)), 8)
        found = tk_rules.rules_parts({"life": {"you": 120, "opponent": 100}})
        self.assertEqual(len(found), 1)
        self.assertIn("120", found[0])


if __name__ == "__main__":
    unittest.main()
