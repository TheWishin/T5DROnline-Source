"""Community tournaments (docs/TOURNAMENTS.md).

1. brackets (bracket.py, no server): seeding, byes for odd counts, the losers bracket of double elimination, the
   grand final and its reset, walkovers after a disqualification, places, undoing a set
2. the server: creating (settings, limits), sign-up and check-in, the start (seeding, too few players)
3. calls: "Your tournament set is ready", accepting, the queue held back, no-shows (one, both)
4. a set's games as the lobby plays them: a quit at 0-0, a desync replay, a crash (called again with its score),
   a dispute (waits for the organizer), ratings (casual unless T5L_TOUR_RATED)
5. the organizer: report, override, reset, disqualify; T5L_TOUR_ADMINS; the hosts and admins of
   `t5lobby-admin tour-host` (the commands, the rules, picked up by a running server, told to the launcher)
6. a server restart in the middle of a set: the tournament resumes, the set is called again with its score
7. the status port's JSON for streamers; an older client gets none of it
8. end to end: 8 stub clients play a whole double-elimination bracket on a local lobby (grand final reset)
9. the Online tab (withdrawn windows): the list, sign-up, the call card, a set, the bracket, the create window,
   the organizer's buttons, German
"""
import json
import os
import random
import tempfile
import time
import unittest
import urllib.request

import util
from util import ServerThread, client
from t5lobby import i18n, tour_text
from t5lobby.proto import LobbyError
from t5lobby.server.bracket import EMPTY, Bracket, BracketError, seed_positions
from t5lobby.server.store import hash_password


# ============================================================================== 1. brackets
def play_out(b, rnd, pick=None):
    """Decide every open set until the bracket is finished (pick(set) -> winner side, else random)."""
    n = 0
    while not b.finished():
        op = b.open_sets()
        assert op, "a bracket got stuck"
        s = rnd.choice(op)
        w = pick(s) if pick else rnd.randint(0, 1)
        b.report(s.id, w, [2, rnd.randint(0, 1)] if w == 0 else [rnd.randint(0, 1), 2])
        n += 1
        assert n < 1000
    return n


def losses_of(b):
    out = {}
    for s in b.sets.values():
        if s.played and s.winner is not None and s.p[1 - s.winner] is not EMPTY:
            lo = s.p[1 - s.winner]
            out[lo] = out.get(lo, 0) + 1
    return out


class BracketTest(unittest.TestCase):
    def test_seed_positions(self):
        self.assertEqual(seed_positions(8), [1, 8, 4, 5, 2, 7, 3, 6])
        for size in (2, 4, 8, 16, 32, 64):
            pos = seed_positions(size)
            self.assertEqual(sorted(pos), list(range(1, size + 1)))
            half = size // 2
            self.assertIn(1, pos[:half])                    # seeds 1 and 2 meet only in the final
            self.assertIn(2, pos[half:])
            for i in range(0, size, 2):
                self.assertEqual(pos[i] + pos[i + 1], size + 1)        # 1 v 8, 4 v 5, ...

    def test_byes_go_to_the_top_seeds(self):
        for n in (3, 5, 6, 7, 9, 13, 17, 33, 63):
            b = Bracket.build("single", [f"p{i}" for i in range(1, n + 1)])
            first = [s for s in b.sets.values() if s.bracket == "W" and s.round == 1]
            byes = [s for s in first if s.reason == "bye"]
            self.assertEqual(len(byes), b.size - n, n)
            self.assertEqual(sorted(s.winner_entrant() for s in byes),
                             sorted(f"p{i}" for i in range(1, b.size - n + 1)), n)     # the top seeds
            self.assertFalse([s for s in first if s.reason == "empty"], n)   # never two byes against each other
            for s in byes:                                   # already in round 2
                self.assertTrue(any(x.known[side] and x.p[side] == s.winner_entrant()
                                    for x in b.sets.values() if x.round == 2 and x.bracket == "W"
                                    for side in (0, 1)))

    def test_single_elimination_plays_every_entrant_out(self):
        for n in range(2, 66):
            rnd = random.Random(n)
            b = Bracket.build("single", list(range(1, n + 1)))
            self.assertEqual(play_out(b, rnd), n - 1)
            champ = b.champion()
            self.assertEqual({e: 1 for e in range(1, n + 1) if e != champ}, losses_of(b))

    def test_double_elimination_structure(self):
        b = Bracket.build("double", list(range(1, 9)))
        count = {}
        for s in b.sets.values():
            count[(s.bracket, s.round)] = count.get((s.bracket, s.round), 0) + 1
        self.assertEqual(count, {("W", 1): 4, ("W", 2): 2, ("W", 3): 1, ("L", 1): 2, ("L", 2): 2, ("L", 3): 1,
                                 ("L", 4): 1, ("GF", 1): 1, ("GF", 2): 1})
        self.assertEqual(b.sets["L1-1"].src, [("lose", "W1-1"), ("lose", "W1-2")])
        # the losers of the winners' round 2 drop in reversed, so two players do not meet again at once
        self.assertEqual(b.sets["L2-1"].src, [("win", "L1-1"), ("lose", "W2-2")])
        self.assertEqual(b.sets["L2-2"].src, [("win", "L1-2"), ("lose", "W2-1")])
        self.assertEqual(b.sets["L4-1"].src, [("win", "L3-1"), ("lose", "W3-1")])
        self.assertEqual(b.sets["GF1"].src, [("win", "W3-1"), ("win", "L4-1")])
        self.assertEqual(b.losers_rounds, 4)

    def test_two_players_double(self):
        b = Bracket.build("double", ["a", "b"])
        self.assertEqual(list(b.sets), ["W1-1", "GF1", "GF2"])
        b.report("W1-1", 0)
        self.assertEqual(b.sets["GF1"].p, ["a", "b"])          # the loser of W1 is the losers' finalist
        b.report("GF1", 1)                                     # b wins: both have lost once -> the reset
        self.assertEqual(b.sets["GF2"].state, "open")
        b.report("GF2", 1)
        self.assertEqual(b.champion(), "b")

    def test_double_elimination_plays_every_entrant_out(self):
        for n in range(2, 66):
            rnd = random.Random(1000 + n)
            b = Bracket.build("double", list(range(1, n + 1)))
            played = play_out(b, rnd)
            self.assertIn(played, (2 * n - 2, 2 * n - 1), n)
            champ = b.champion()
            losses = losses_of(b)
            self.assertTrue(all(losses.get(e) == 2 for e in range(1, n + 1) if e != champ), (n, losses))
            self.assertLessEqual(losses.get(champ, 0), 1)

    def test_grand_final_reset(self):
        # the losers' champion wins the grand final: both have lost once, the reset decides
        b = Bracket.build("double", list(range(1, 5)))
        top = lambda s: 0 if s.bracket != "GF" else 1        # noqa: E731 -- side 0 everywhere, the losers side in GF1
        while b.sets["GF1"].state != "done":
            b.report(b.open_sets()[0].id, top(b.open_sets()[0]))
        gf1 = b.sets["GF1"]
        gf2 = b.sets["GF2"]
        self.assertEqual(gf2.state, "open")
        self.assertEqual(gf2.p, gf1.p)
        self.assertFalse(b.finished())
        b.report("GF2", 0)
        self.assertEqual(b.champion(), gf1.p[0])
        # the winners' champion wins the grand final: no reset
        b = Bracket.build("double", list(range(1, 5)))
        while not b.finished():
            b.report(b.open_sets()[0].id, 0)
        self.assertEqual(b.sets["GF2"].reason, "skipped")
        self.assertEqual(b.champion(), b.sets["GF1"].p[0])
        self.assertEqual(b.champion(), 1)                    # (seed 1 won every set)

    def test_no_reset_for_a_disqualified_winners_champion(self):
        b = Bracket.build("double", ["a", "b", "c", "d"])
        while b.sets["GF1"].state != "open":
            b.report(b.open_sets()[0].id, 0)
        champ_w = b.sets["GF1"].p[0]
        sid = b.disqualify(champ_w)
        self.assertEqual(sid, "GF1")
        b.forfeit("GF1", 0)
        self.assertTrue(b.finished())
        self.assertEqual(b.sets["GF2"].reason, "skipped")
        self.assertEqual(b.champion(), b.sets["GF1"].p[1])

    def test_places(self):
        b = Bracket.build("single", list(range(1, 9)))
        play_out(b, random.Random(1), pick=lambda s: 0)
        self.assertEqual(sorted(p for _e, p in b.standings()), [1, 2, 3, 3, 5, 5, 5, 5])
        b = Bracket.build("double", list(range(1, 9)))
        play_out(b, random.Random(2), pick=lambda s: 0)
        self.assertEqual(sorted(p for _e, p in b.standings()), [1, 2, 3, 4, 5, 5, 7, 7])
        self.assertEqual(b.standings()[0], (1, 1))

    def test_disqualified_players_give_walkovers(self):
        b = Bracket.build("single", ["a", "b", "c", "d"])
        b.report("W1-1", 0)                                  # a is through to the final, waiting for W1-2
        self.assertIsNone(b.disqualify("a"))                 # not in an open set: placed as nobody
        b.report("W1-2", 0)
        self.assertTrue(b.finished())
        self.assertEqual(b.sets["W2-1"].reason, "bye")
        self.assertEqual(b.champion(), b.sets["W1-2"].winner_entrant())
        self.assertNotIn("a", dict(b.standings()))
        with self.assertRaises(BracketError):
            b.disqualify("nobody")

    def test_a_reset_never_brings_back_a_disqualified_player(self):
        """review-113: a set put back (reset) came back open with a player disqualified since -- the set this player
        lost by the disqualification, or a walkover that had waited for an opponent -- and the tournament called the
        disqualified player to play it again (a win then eliminated an innocent opponent)."""
        b = Bracket.build("single", ["a", "b", "c", "d"])
        sid = b.disqualify("b")                               # b is in the open W1-2 (b v c): forfeited
        self.assertEqual(sid, "W1-2")
        b.forfeit(sid, b.sets[sid].p.index("b"), "dq")
        self.assertEqual(b.sets[sid].reason, "dq")
        b.reset(sid)                                          # (the organizer's reset of that forfeit)
        s = b.sets[sid]
        self.assertEqual((s.state, s.reason, s.winner_entrant()), ("done", "bye", "c"))
        for x in b.open_sets():
            self.assertNotIn("b", x.p)
        # a walkover decided for a player while the other side was nobody, that player disqualified, the walkover's
        # source put back and played again: the set must not open with the disqualified player
        b = Bracket.build("single", list("abcdefgh"))
        b.double_forfeit("W1-4")                              # (c v f: nobody) -> W2-2 is b's walkover once W1-3 is in
        b.report("W1-3", 0)
        self.assertEqual(b.sets["W2-2"].reason, "bye")
        out = b.sets["W2-2"].winner_entrant()
        b.disqualify(out)
        b.reset("W1-4")
        b.report("W1-4", 0)
        for s in b.open_sets():
            self.assertNotIn(out, s.p)
        self.assertEqual(b.sets["W2-2"].reason, "bye")
        self.assertEqual(b.sets["W2-2"].winner_entrant(), b.sets["W1-4"].winner_entrant())

    def test_reset_and_its_blocker(self):
        b = Bracket.build("single", ["a", "b", "c", "d"])
        b.report("W1-1", 0)
        self.assertIsNone(b.reset_blocker("W1-1"))
        changed = b.reset("W1-1")
        self.assertIn("W2-1", changed)
        self.assertEqual(b.sets["W1-1"].state, "open")
        self.assertEqual(b.sets["W2-1"].known, [False, False])
        b.report("W1-1", 1)
        b.report("W1-2", 0)
        b.report("W2-1", 0)
        self.assertEqual(b.reset_blocker("W1-1"), "W2-1")     # the final was played from it
        b2 = Bracket.from_dict(json.loads(json.dumps(b.to_dict())))
        self.assertEqual(b2.champion(), b.champion())
        self.assertEqual([s.to_dict() for s in b2.sets.values()], [s.to_dict() for s in b.sets.values()])

    def test_errors(self):
        with self.assertRaises(BracketError):
            Bracket.build("single", ["a"])
        with self.assertRaises(BracketError):
            Bracket.build("triple", ["a", "b"])
        b = Bracket.build("single", ["a", "b", "c"])
        with self.assertRaises(BracketError):
            b.report("W2-1", 0)                              # not open yet
        with self.assertRaises(BracketError):
            b.report("W1-2", 2)


# ============================================================================== the server: a field of players
TOUR = dict(set_next_seconds=0.2, tour_tick=0.05, tour_noshow=8.0, max_per_ip=40, conn_burst=60, conn_rate=20.0,
            state_burst=200, state_rate=50.0)


class Field:
    """Accounts with launchers that know tournaments, driven like players: accept calls, play the set's games
    (both report the winner `plan` names), say set_next between games."""

    def __init__(self, server, names, create=True, **kw):
        self.s = server
        self.c = {}
        self.log = {n: [] for n in names}
        self.accept = {n: True for n in names}
        self.plan = lambda sid, number: 0              # winner side (0 = P1 = the set's side 0)
        self.special = {}                              # (set id, game number) -> "quit" | "crash" | "desync" | ...
        self.done = set()
        for n in names:
            pw = "pw-" + n.lower() + "-x"
            if create:
                server.call(lambda n=n, pw=pw: server.srv.store.create_account(n, hash_password(pw, n=1 << 10)))
            kw.setdefault("sets", True)
            kw.setdefault("tournaments", True)
            self.c[n] = client(server, n, password=pw, **kw)
        self.starts = {}                               # match id -> {slot: (name, event)}

    def close(self):
        for c in self.c.values():
            c.close()

    def events(self, name, kind):
        return [e for e in self.log[name] if e["t"] == kind]

    def last(self, name, kind):
        ev = self.events(name, kind)
        return ev[-1] if ev else None

    def pump(self):
        for n, c in list(self.c.items()):
            while True:
                ev = c.next_event(0)
                if ev is None:
                    break
                self.log[n].append(ev)
                k = ev["t"]
                if k == "tour_call" and self.accept.get(n) and not ev["accepted"][0]:
                    try:
                        c.tour_accept(ev["tournament"]["id"], ev["set"]["id"])
                    except LobbyError:
                        pass                           # (an older call: the set has started meanwhile)
                elif k == "match_start":
                    self.starts.setdefault(ev["match"], {})[ev["slot"]] = (n, ev)
                    if len(self.starts[ev["match"]]) == 2:
                        self._play(ev["match"])
                elif k == "match_result":
                    st = ev.get("set") or {}
                    if st.get("next"):
                        try:
                            c.set_next(None, keep=True)
                        except LobbyError:
                            pass

    def _play(self, mid):
        both = self.starts[mid]
        ev = both[0][1]
        tset = (ev.get("set") or {}).get("tournament") or {}
        number = (ev.get("set") or {}).get("number") or 1
        key = (tset.get("set"), number)
        what = self.special.pop(key, None)
        w = self.plan(tset.get("set"), number)
        p0, p1 = self.c[both[0][0]], self.c[both[1][0]]
        def rep(c, *a, **k):
            try:
                c.report_result(*a, match_id=mid, **k)
            except LobbyError:
                pass                                   # (the organizer decided the set meanwhile, ...)
        if what == "hold":
            return                                     # the game goes on (and on)
        winner, loser = (p0, p1)[w], (p1, p0)[w]
        if what == "quit":                             # the loser quits the game (closes it)
            loser.leave_match(mid)
        elif what == "crash":                          # the loser's game dies; the winner's lost its opponent
            rep(loser, None, None, source="crash", reason="exit 1")
            rep(winner, None, None, source="disconnect", reason="peer_timeout")
        elif what == "desync":
            for c in (p0, p1):
                rep(c, w, [3, 1] if w == 0 else [1, 3], source="game", desync=7)
        elif what == "dispute":
            rep(p0, 0, [3, 1], source="game")
            rep(p1, 1, [1, 3], source="game")
        else:
            for c in (p0, p1):
                rep(c, w, [3, 1] if w == 0 else [1, 3], source="game")

    def run(self, pred, timeout=40.0):
        t_end = time.monotonic() + timeout
        while time.monotonic() < t_end:
            self.pump()
            if pred():
                return True
            time.sleep(0.02)
        raise AssertionError("timed out")


class TourBase(unittest.TestCase):
    server_cfg = {}
    names = ("Ann", "Ben", "Cat", "Dan")

    def setUp(self):
        cfg = dict(TOUR)
        cfg.update(self.server_cfg)
        self.s = ServerThread(**cfg).start()
        self.f = Field(self.s, self.names)
        self.org = self.f.c[self.names[0]]

    def tearDown(self):
        self.f.close()
        self.s.stop()

    def srv(self, fn):
        return self.s.call(fn)

    def tour(self, tid):
        return self.s.call(lambda: self.s.srv.tours.tours[tid])

    def create(self, fmt="single", start_in=0.5, players=None, wait=True, seeds=None, **kw):
        """A tournament of `players` (all names) starting in `start_in` s. Seeded by rating, the ratings set so that the
        seeds follow `seeds` -- by default the order of `players`, and with four of them so that the first round is
        players[0] v players[1] and players[2] v players[3]."""
        players = list(players or self.names)
        if seeds is None:
            seeds = [players[0], players[2], players[3], players[1]] if len(players) == 4 else players
        if "seeding" not in kw:
            kw["seeding"] = "rating"
            for i, n in enumerate(seeds):
                self.s.call(lambda n=n, r=2000 - 10 * i: self.s.srv.store._x(
                    "UPDATE accounts SET rating = ? WHERE name = ?", (r, n)))
        t = self.org.tour_create("Test Cup", fmt=fmt, start=time.time() + start_in, **kw)
        for n in players:
            self.f.c[n].tour_join(t["id"])
        if wait and start_in < 5:
            self.wait_state(t["id"], "running")
        return t["id"]

    def wait_state(self, tid, state, timeout=30.0):
        self.f.run(lambda: self.tour(tid).state == state, timeout)
        if state == "finished":                        # (the last messages of the last set, then the end)
            t = self.tour(tid)
            names = [e.name for e in t.entrants.values() if e.seed is not None and not e.dq]
            self.f.run(lambda: all(any(x["code"] == "finished" for x in self.f.events(n, "tour_notice"))
                                   for n in names), 10)

    def bset(self, tid, sid):
        return self.s.call(lambda: self.s.srv.tours.tours[tid].bracket.sets[sid])

    def winner_name(self, tid, sid):
        s = self.bset(tid, sid)
        return self.tour(tid).name_of(s.winner_entrant())

    def account(self, name):
        return self.s.call(lambda: dict(self.s.srv.store.account(name)))


# ============================================================================== 2. creating, sign-up, check-in
class CreateTest(TourBase):
    def test_create_and_list(self):
        t = self.org.tour_create("Friday Cup", fmt="double", set_wins=3, start=time.time() + 600, max_players=8,
                                 checkin_minutes=5, seeding="rating")
        self.assertEqual((t["state"], t["format"], t["best_of"], t["max_players"], t["organizer"]),
                         ("signup", "double", 5, 8, "Ann"))
        self.assertTrue(t["can_manage"])
        rows = self.f.c["Ben"].tour_list()
        self.assertTrue(rows["can_create"])
        self.assertEqual([r["name"] for r in rows["rows"]], ["Friday Cup"])
        self.assertFalse(rows["rows"][0]["can_manage"])
        self.assertFalse(rows["rows"][0]["you"]["entrant"])
        # the server keeps it
        row = self.srv(lambda: dict(self.s.srv.store._x("SELECT * FROM tournaments").fetchone()))
        self.assertEqual((row["name"], row["state"], row["set_wins"]), ("Friday Cup", "signup", 3))

    def test_bad_fields(self):
        now = time.time()
        for kw, bit in ((dict(name="x"), "name"), (dict(fmt="triple"), "format"), (dict(set_wins=4), "first to"),
                        (dict(max_players=12), "player limit"), (dict(checkin_minutes=7), "check-in"),
                        (dict(seeding="age"), "seeding"), (dict(start=now - 3600), "passed"),
                        (dict(start=now + 30 * 86400), "within")):
            args = dict(name="Cup", fmt="single", set_wins=2, start=now + 60, max_players=8, checkin_minutes=0,
                        seeding="random")
            args.update(kw)
            with self.assertRaises(LobbyError) as cm:
                self.org.tour_create(args.pop("name"), **args)
            self.assertIn(bit, cm.exception.msg)

    def test_limits_per_organizer_and_guests(self):
        self.org.tour_create("One", start=time.time() + 600)
        self.org.tour_create("Two", start=time.time() + 600)
        with self.assertRaises(LobbyError) as cm:
            self.org.tour_create("Three", start=time.time() + 600)
        self.assertIn("you already run 2 tournaments", cm.exception.msg)
        g = client(self.s, "Guesty", tournaments=True)
        try:
            self.assertFalse(g.tour_list()["can_create"])
            self.assertEqual(len(g.tour_list()["rows"]), 2)     # guests may look
            with self.assertRaises(LobbyError):
                g.tour_create("Guest Cup", start=time.time() + 600)
            with self.assertRaises(LobbyError):
                g.tour_join(g.tour_list()["rows"][0]["id"])
        finally:
            g.close()

    def test_without_the_cap_no_sign_up(self):
        t = self.org.tour_create("Cup", start=time.time() + 600)
        pw = "pw-old-x"
        self.s.call(lambda: self.s.srv.store.create_account("Old", hash_password(pw, n=1 << 10)))
        old = client(self.s, "Old", password=pw, sets=True)          # an older launcher: no "tournaments" cap
        try:
            self.assertNotIn("tournaments", old.welcome)
            with self.assertRaises(LobbyError) as cm:
                old.tour_join(t["id"])
            self.assertIn("update the launcher", cm.exception.msg)
        finally:
            old.close()


class OrganizerSettingTest(TourBase):
    server_cfg = {"tour_organizers": "Ben", "tour_admins": ["dan"]}

    def test_only_the_listed_accounts_create(self):
        with self.assertRaises(LobbyError) as cm:
            self.org.tour_create("Cup", start=time.time() + 600)
        self.assertIn("organizers", cm.exception.msg)
        self.assertFalse(self.org.tour_list()["can_create"])
        t = self.f.c["Ben"].tour_create("Ben's Cup", start=time.time() + 600)
        self.assertTrue(self.f.c["Dan"].tour_list()["can_create"])          # an admin may too
        # an admin runs every tournament; another account does not
        with self.assertRaises(LobbyError):
            self.f.c["Cat"].tour_admin(t["id"], "cancel")
        self.assertEqual(self.f.c["Dan"].tour_admin(t["id"], "cancel")["state"], "cancelled")


class NoOrganizersTest(TourBase):
    server_cfg = {"tour_organizers": "none"}

    def test_nobody_creates(self):
        self.assertFalse(self.org.tour_list()["can_create"])
        with self.assertRaises(LobbyError):
            self.org.tour_create("Cup", start=time.time() + 600)


class SignupTest(TourBase):
    def test_join_leave_and_full(self):
        t = self.org.tour_create("Cup", start=time.time() + 600, max_players=8)
        for n in self.names:
            self.f.c[n].tour_join(t["id"])
        self.assertEqual(self.f.c["Ann"].tour_get(t["id"])["players"], 4)
        self.f.c["Dan"].tour_leave(t["id"])
        full = self.f.c["Ann"].tour_get(t["id"])
        self.assertEqual([e["name"] for e in full["entrants"]], ["Ann", "Ben", "Cat"])
        self.s.call(lambda: setattr(self.s.srv.tours.tours[t["id"]], "max_players", 3))
        with self.assertRaises(LobbyError) as cm:
            self.f.c["Dan"].tour_join(t["id"])
        self.assertIn("full", cm.exception.msg)

    def test_check_in_decides_who_plays(self):
        tid = self.org.tour_create("Cup", start=time.time() + 2.0, checkin_minutes=5)["id"]
        self.assertEqual(self.tour(tid).state, "checkin")            # (the window is open already)
        for n in ("Ann", "Ben", "Cat"):
            self.f.c[n].tour_join(tid)                           # joining during check-in checks in
        cat, ben = self.account("Cat")["id"], self.account("Ben")["id"]
        self.s.call(lambda: setattr(self.s.srv.tours.tours[tid].entrants[cat], "checked_in", None))
        self.f.c["Cat"].tour_checkin(tid)
        self.s.call(lambda: setattr(self.s.srv.tours.tours[tid].entrants[ben], "checked_in", None))  # Ben forgets
        self.wait_state(tid, "running")
        full = self.org.tour_get(tid)
        seeded = sorted(e["name"] for e in full["entrants"] if e["seed"])
        self.assertEqual(seeded, ["Ann", "Cat"])
        self.f.run(lambda: any(e["code"] == "no_checkin" for e in self.f.events("Ben", "tour_notice")))

    def test_check_in_window_opens(self):
        tid = self.org.tour_create("Cup", start=time.time() + 300.5, checkin_minutes=5)["id"]
        self.assertEqual(self.tour(tid).state, "signup")
        self.f.c["Ben"].tour_join(tid)
        with self.assertRaises(LobbyError):
            self.f.c["Ben"].tour_checkin(tid)
        self.f.run(lambda: self.tour(tid).state == "checkin", 5)
        self.f.run(lambda: any(e["code"] == "checkin_open" for e in self.f.events("Ben", "tour_notice")))
        self.f.c["Ben"].tour_checkin(tid)

    def test_too_few_players_cancel(self):
        tid = self.org.tour_create("Cup", start=time.time() + 0.3)["id"]
        self.f.c["Ben"].tour_join(tid)
        self.wait_state(tid, "cancelled")
        self.assertEqual(self.tour(tid).reason, "not_enough")
        self.f.run(lambda: any(e["code"] == "cancelled" for e in self.f.events("Ben", "tour_notice")))

    def test_organizer_starts_early_and_seeding_by_rating(self):
        for n, r in (("Ann", 1400), ("Ben", 1800), ("Cat", 1500), ("Dan", 1650)):
            self.s.call(lambda n=n, r=r: self.s.srv.store._x("UPDATE accounts SET rating = ? WHERE name = ?", (r, n)))
        tid = self.create(start_in=600, seeding="rating")
        self.f.accept = {n: False for n in self.names}
        with self.assertRaises(LobbyError):
            self.f.c["Ben"].tour_admin(tid, "start")             # not the organizer
        self.org.tour_admin(tid, "start")
        full = self.org.tour_get(tid)
        self.assertEqual(full["state"], "running")
        seeds = {e["name"]: e["seed"] for e in full["entrants"]}
        self.assertEqual(seeds, {"Ben": 1, "Dan": 2, "Cat": 3, "Ann": 4})
        w1 = {s["id"]: s["p"] for s in full["bracket"]["sets"]}
        self.assertEqual(w1["W1-1"], ["Ben", "Ann"])             # 1 v 4
        self.assertEqual(w1["W1-2"], ["Dan", "Cat"])             # 2 v 3


# ============================================================================== 3. calls, no-shows
class CallTest(TourBase):
    server_cfg = {"tour_noshow": 4.0}

    def test_call_accept_and_play(self):
        self.f.accept = {n: False for n in self.names}          # (before create(): its wait pumps the calls already)
        tid = self.create()
        self.f.run(lambda: self.f.last("Ann", "tour_call") is not None)
        call = self.f.last("Ann", "tour_call")
        self.assertEqual((call["set"]["id"], call["best_of"], call["opponent"]["name"], call["side"]),
                         ("W1-1", 3, "Ben", 0))
        self.assertGreater(call["deadline"], 0)
        # a player whose set is called cannot queue or open a room meanwhile
        with self.assertRaises(LobbyError) as cm:
            self.f.c["Ann"].quick_match()
        self.assertIn("your tournament set is ready", cm.exception.msg)
        with self.assertRaises(LobbyError):
            self.f.c["Ann"].create_room("x")
        self.f.c["Ann"].tour_accept(tid, "W1-1")
        self.f.run(lambda: (self.f.last("Ben", "tour_call") or {}).get("accepted") == [False, True])
        with self.assertRaises(LobbyError):
            self.f.c["Cat"].tour_accept(tid, "W1-1")             # not Cat's set
        self.f.accept["Ben"] = True
        self.f.accept.update(Cat=True, Dan=True)
        self.f.c["Ben"].tour_accept(tid, "W1-1")
        self.f.run(lambda: self.bset(tid, "W1-1").state == "done")
        self.assertEqual(self.bset(tid, "W1-1").score, [2, 0])
        self.assertEqual(self.winner_name(tid, "W1-1"), "Ann")
        ends = [e["reason"] for e in self.f.events("Ann", "tour_call_end")]
        self.assertIn("started", ends)
        found = [e for e in self.f.events("Ann", "match_found")]
        self.assertEqual(found[0]["origin"], "tournament")
        self.assertFalse(found[0]["ready_check"])                # accepted already: no ready check
        self.wait_state(tid, "finished")
        self.assertEqual(self.tour(tid).champion, "Ann")

    def test_a_queued_player_leaves_the_queue_when_called(self):
        self.f.accept = {n: False for n in self.names}
        tid = self.create(start_in=2.0, wait=False)
        self.f.c["Cat"].quick_match()
        self.wait_state(tid, "running")
        self.f.run(lambda: self.f.last("Cat", "tour_call") is not None)
        self.assertEqual(self.s.call(lambda: self.s.srv.by_name["cat"].status), "idle")

    def test_no_show_loses_and_is_out(self):
        self.f.accept["Ben"] = False                             # Ben never accepts (set before create(): its wait
        tid = self.create()                                      # pumps the calls already)
        self.f.run(lambda: self.bset(tid, "W1-1").state == "done", 15)
        s = self.bset(tid, "W1-1")
        self.assertEqual((s.reason, self.winner_name(tid, "W1-1")), ("no_show", "Ann"))
        ben = self.tour(tid).entrants[self.account("Ben")["id"]]
        self.assertEqual(ben.dq, "no_show")
        self.f.run(lambda: any(e["code"] == "dq" for e in self.f.events("Ben", "tour_notice")))
        self.assertIn("no_show", [e["reason"] for e in self.f.events("Ann", "tour_call_end")])
        self.wait_state(tid, "finished")

    def test_both_no_show_gives_the_next_opponent_a_walkover(self):
        self.f.accept.update(Cat=False, Dan=False)               # W1-2: nobody comes
        tid = self.create()
        self.f.run(lambda: self.tour(tid).state == "finished", 20)
        self.assertEqual(self.bset(tid, "W1-2").reason, "no_show")
        self.assertIsNone(self.bset(tid, "W1-2").winner)
        final = self.bset(tid, "W2-1")
        self.assertEqual(final.reason, "bye")                    # Ann (W1-1's winner) walks over
        self.assertEqual(self.tour(tid).champion, "Ann")

    def test_a_called_player_who_logs_in_again_gets_the_call(self):
        self.f.accept = {n: False for n in self.names}
        tid = self.create()
        self.f.run(lambda: self.f.last("Dan", "tour_call") is not None)
        self.f.c["Dan"].close()
        pw = "pw-dan-x"
        self.f.c["Dan"] = client(self.s, "Dan", password=pw, sets=True, tournaments=True)
        self.f.log["Dan"] = []
        self.f.run(lambda: self.f.last("Dan", "tour_call") is not None)
        self.assertEqual(self.f.last("Dan", "tour_call")["set"]["id"], "W1-2")


# ============================================================================== 4. the games of a set
class SetRulesTest(TourBase):
    def test_a_quit_at_zero_loses_the_set(self):
        self.f.special[("W1-1", 1)] = "quit"                     # Ben (the loser) closes his game in game 1
        tid = self.create()
        self.f.run(lambda: self.bset(tid, "W1-1").state == "done")
        s = self.bset(tid, "W1-1")
        self.assertEqual((self.winner_name(tid, "W1-1"), s.reason), ("Ann", "forfeit"))
        self.wait_state(tid, "finished")

    def test_a_desynced_game_is_played_again(self):
        self.f.special[("W1-1", 1)] = "desync"
        tid = self.create()
        self.f.run(lambda: self.bset(tid, "W1-1").state == "done")
        games = self.bset(tid, "W1-1").data["games"]
        self.assertEqual([g["status"] for g in games], ["void", "confirmed", "confirmed"])
        self.assertEqual(self.bset(tid, "W1-1").score, [2, 0])

    def test_a_crash_calls_the_set_again_with_its_score(self):
        self.f.special[("W1-1", 2)] = "crash"                    # 1-0, then Ben's game dies in game 2
        tid = self.create()
        self.f.run(lambda: self.bset(tid, "W1-1").state == "done")
        calls = [e for e in self.f.events("Ann", "tour_call") if e["set"]["id"] == "W1-1"]
        again = [e for e in calls if e["replay"]]
        self.assertTrue(again, "the set was called again")
        self.assertEqual(again[0]["score"], [1, 0])              # with the score it had
        s = self.bset(tid, "W1-1")
        self.assertEqual((s.score, s.data["voids"]), ([2, 0], 1))
        self.assertEqual(self.winner_name(tid, "W1-1"), "Ann")

    def test_a_dispute_waits_for_the_organizer(self):
        self.f.special[("W1-2", 1)] = "dispute"
        tid = self.create()
        self.f.run(lambda: self.bset(tid, "W1-2").data.get("live") == "attention")
        self.assertEqual(self.bset(tid, "W1-2").data["why"], "disputed")
        self.f.run(lambda: any(e["code"] == "attention" for e in self.f.events("Ann", "tour_notice")))
        self.assertIn("attention", [e["reason"] for e in self.f.events("Cat", "tour_call_end")])
        full = self.org.tour_get(tid)
        row = next(s for s in full["bracket"]["sets"] if s["id"] == "W1-2")
        self.assertEqual((row["live"], row["why"]), ("attention", "disputed"))
        self.org.tour_admin(tid, "report", set="W1-2", winner=1, score=[1, 2])
        self.assertEqual(self.winner_name(tid, "W1-2"), "Dan")
        self.assertEqual(self.bset(tid, "W1-2").reason, "organizer")
        self.wait_state(tid, "finished")

    def test_sets_are_casual(self):
        tid = self.create(players=("Ann", "Ben"))
        before = self.account("Ann")["rating"]
        self.wait_state(tid, "finished")
        ann, ben = self.account("Ann"), self.account("Ben")
        self.assertEqual((ann["rating"], ann["ranked_games"]), (before, 0))
        self.assertEqual((ann["wins"], ben["losses"]), (1, 1))  # the record counts the set, once
        res = self.f.events("Ann", "match_result")
        self.assertTrue(all(r["rating"] is None and not r["ranked"] for r in res))
        self.assertEqual(res[-1]["rematch_window"], 0)          # no rematch after a tournament set
        se = self.f.last("Ann", "set_end")
        self.assertEqual((se["result"], se["tournament"]["set"]), ("win", "W1-1"))


class RatedSetTest(TourBase):
    server_cfg = {"tour_rated": True}

    def test_the_setting_rates_each_set_once(self):
        tid = self.create(players=("Ann", "Ben"))
        self.wait_state(tid, "finished")
        ann = self.account("Ann")
        # ONE Glicko-2 update for the set (the players logged in as new accounts: 1500 each)
        from t5lobby import rating as glicko
        want, _ = glicko.match(glicko.Rating(), glicko.Rating(), 1.0)
        self.assertAlmostEqual(ann["rating"], want.r, places=3)
        self.assertEqual(ann["ranked_games"], 1)
        res = self.f.events("Ann", "match_result")
        self.assertEqual([r["rating"] is not None for r in res], [False, True])


# ============================================================================== 5. the organizer
class OrganizerTest(TourBase):
    names = ("Ann", "Ben", "Cat", "Dan", "Eve")

    def test_override_reset_and_disqualify(self):
        self.f.accept = {n: False for n in self.names}
        tid = self.create(players=("Ben", "Cat", "Dan", "Eve"))    # Ann organizes, does not play
        self.f.run(lambda: self.f.last("Ben", "tour_call") is not None)
        full = self.org.tour_get(tid)
        pairs = {s["id"]: s["p"] for s in full["bracket"]["sets"] if s["bracket"] == "W" and s["round"] == 1}
        # decide W1-1 by hand while it is called
        self.org.tour_admin(tid, "report", set="W1-1", winner=0)
        a, b = pairs["W1-1"]
        self.assertEqual(self.winner_name(tid, "W1-1"), a)
        self.f.run(lambda: "decided" in [e["reason"] for e in self.f.events(b, "tour_call_end")])
        # override it: the other one goes through (the final has not been played)
        self.org.tour_admin(tid, "override", set="W1-1", winner=1)
        self.assertEqual(self.winner_name(tid, "W1-1"), b)
        with self.assertRaises(LobbyError):
            self.org.tour_admin(tid, "report", set="W1-1", winner=0)   # decided: override it instead
        # reset it: played again from 0-0, called again
        self.org.tour_admin(tid, "reset", set="W1-1")
        self.assertEqual(self.bset(tid, "W1-1").state, "open")
        self.f.run(lambda: self.bset(tid, "W1-1").data.get("live") == "called")
        # disqualify one player of W1-2: the other wins it
        c, d = pairs["W1-2"]
        self.org.tour_admin(tid, "dq", player=d)
        self.assertEqual((self.winner_name(tid, "W1-2"), self.bset(tid, "W1-2").reason), (c, "dq"))
        self.f.run(lambda: any(e["code"] == "dq" for e in self.f.events(d, "tour_notice")))
        with self.assertRaises(LobbyError):
            self.org.tour_admin(tid, "dq", player=d)             # out already
        with self.assertRaises(LobbyError):
            self.f.c[c].tour_admin(tid, "reset", set="W1-1")     # only the organizer
        # play the rest
        self.f.accept = {n: True for n in self.names}
        for n in (a, b):
            call = self.f.last(n, "tour_call")
            if call and call["set"]["id"] == "W1-1":
                try:
                    self.f.c[n].tour_accept(tid, "W1-1")
                except LobbyError:
                    pass
        self.wait_state(tid, "finished")
        # a played set whose result the final used cannot be reset any more
        with self.assertRaises(LobbyError):
            self.org.tour_admin(tid, "reset", set="W1-1")

    def test_a_reset_set_never_calls_a_disqualified_player(self):
        """review-113: the organizer's reset of a set a disqualification decided opened it again with the disqualified
        player in it and called both to play it (a win then knocked the other one out). Now it is the other player's
        walkover again; an override (a winner to choose) is refused."""
        self.f.accept = {n: False for n in self.names}
        tid = self.create(players=("Ben", "Cat", "Dan", "Eve"))    # Ann organizes, does not play
        self.f.run(lambda: self.f.last("Ben", "tour_call") is not None)
        full = self.org.tour_get(tid)
        c, d = next(s["p"] for s in full["bracket"]["sets"] if s["id"] == "W1-2")
        self.org.tour_admin(tid, "dq", player=d)
        self.assertEqual((self.winner_name(tid, "W1-2"), self.bset(tid, "W1-2").reason), (c, "dq"))
        calls = len(self.f.events(d, "tour_call"))
        with self.assertRaises(LobbyError):
            self.org.tour_admin(tid, "override", set="W1-2", winner=0)
        self.assertEqual(self.bset(tid, "W1-2").reason, "dq")          # (refused before anything changed)
        self.org.tour_admin(tid, "reset", set="W1-2")
        s = self.bset(tid, "W1-2")
        self.assertEqual((s.state, s.reason, self.winner_name(tid, "W1-2")), ("done", "bye", c))
        self.assertNotEqual(s.data.get("live"), "called")
        time.sleep(0.5)
        self.assertEqual(len(self.f.events(d, "tour_call")), calls)    # never called again

    def test_withdrawing_in_the_middle_of_a_set(self):
        tid = self.create(players=("Ben", "Cat"))
        self.f.run(lambda: self.bset(tid, "W1-1").data.get("live") == "playing")
        self.f.c["Cat"].tour_leave(tid)                          # withdraws: out, the set goes to Ben
        self.wait_state(tid, "finished")
        self.assertEqual(self.tour(tid).champion, "Ben")
        self.assertEqual(self.tour(tid).entrants[self.account("Cat")["id"]].dq, "withdrew")

    def test_cancel(self):
        tid = self.create(players=("Ben", "Cat"))
        self.f.run(lambda: self.bset(tid, "W1-1").data.get("live") == "playing")
        self.org.tour_admin(tid, "cancel")
        self.assertEqual(self.tour(tid).state, "cancelled")
        self.f.run(lambda: any(e["code"] == "cancelled" for e in self.f.events("Ben", "tour_notice")))
        self.f.run(lambda: self.f.last("Ben", "set_end") is not None)


# ============================================================================== 5b. abuse (security review 2)
class AbuseCreateTest(TourBase):
    server_cfg = {"tour_admins": ["dan"], "tour_max_open": 3, "tour_get_rate": 0.2, "tour_get_burst": 3}

    def test_a_start_time_that_is_no_number(self):
        # NaN passed "has passed" and "within 14 days" alike; SQLite cannot keep it (NULL in a NOT NULL column): the
        # tournament stayed in memory, unsaved, never started, and held a slot until the next restart
        for bad in (float("nan"), float("inf"), float("-inf")):
            with self.assertRaises(LobbyError):
                self.org.tour_create("Cup", start=bad)
        self.assertEqual(self.srv(lambda: len(self.s.srv.tours.tours)), 0)

    def test_the_limits_count_per_address_and_spare_the_admins(self):
        # throw-away accounts (T5L_TOUR_ORGANIZERS=any) filled the server-wide limit (T5L_TOUR_MAX_OPEN) with
        # tournaments 14 days ahead: nobody else could make one. T5L_TOUR_PER_ORGANIZER now counts per internet address
        # too (the test players all come from 127.0.0.1), and T5L_TOUR_ADMINS are not held back by either.
        self.org.tour_create("One", start=time.time() + 600)
        self.org.tour_create("Two", start=time.time() + 600)
        with self.assertRaises(LobbyError) as cm:
            self.f.c["Ben"].tour_create("Ben's", start=time.time() + 600)       # another account, the same address
        self.assertIn("internet address", cm.exception.msg)
        self.s.call(lambda: setattr(self.s.srv.cfg, "tour_per_organizer", 5))
        self.f.c["Ben"].tour_create("Ben's", start=time.time() + 600)
        with self.assertRaises(LobbyError) as cm:
            self.f.c["Cat"].tour_create("Cat's", start=time.time() + 600)       # the server is full (3)
        self.assertIn("as many tournaments as it takes", cm.exception.msg)
        t = self.f.c["Dan"].tour_create("Admin's", start=time.time() + 600)   # an admin always may
        self.assertEqual(t["state"], "signup")

    def test_names_that_pass_for_the_server(self):
        for name in ("Official T5DR Cup", "Admin Weekly", "Moderator night"):
            with self.assertRaises(LobbyError) as cm:
                self.org.tour_create(name, start=time.time() + 600)
            self.assertEqual(cm.exception.code, "bad_name")
        self.org.tour_create("Friday Night Cup", start=time.time() + 600)
        self.assertEqual(self.f.c["Dan"].tour_create("Official Weekly", start=time.time() + 600)["name"],
                         "Official Weekly")                                     # the server's own admins may

    def test_tour_get_has_a_rate_limit(self):
        # a 64-player bracket is ~60 KB of JSON; tour_get was in no rate-limit bucket (20 a second per connection)
        t = self.org.tour_create("Cup", start=time.time() + 600)
        for _ in range(3):
            self.org.tour_get(t["id"])
        with self.assertRaises(LobbyError) as cm:
            self.org.tour_get(t["id"])
        self.assertEqual(cm.exception.code, "rate_limited")

    def test_a_disqualified_player_cannot_sign_up_again(self):
        # leaving and signing up again cleared the organizer's disqualification before the start
        t = self.org.tour_create("Cup", start=time.time() + 600)
        ben = self.f.c["Ben"]
        ben.tour_join(t["id"])
        self.org.tour_admin(t["id"], "dq", player="Ben")
        with self.assertRaises(LobbyError) as cm:
            ben.tour_leave(t["id"])
        self.assertIn("took you off", cm.exception.msg)
        self.assertEqual(ben.tour_join(t["id"])["you"]["dq"], "organizer")


class OwnSetTest(TourBase):
    server_cfg = {"tour_admins": ["dan"]}

    def test_an_organizer_does_not_decide_a_set_they_play(self):
        # with T5L_TOUR_ORGANIZERS=any anybody organizes -- and may play in their own tournament: Ann (organizer, in
        # W1-1 against Ben) could report her own set as won, reset a lost one or disqualify her opponent
        self.f.accept = {n: False for n in self.names}
        tid = self.create()                                     # W1-1 Ann v Ben, W1-2 Cat v Dan
        self.f.run(lambda: self.bset(tid, "W1-1").data.get("live") == "called")
        for op, kw in (("report", dict(set="W1-1", winner=0)), ("override", dict(set="W1-1", winner=0)),
                       ("reset", dict(set="W1-1")), ("dq", dict(player="Ben"))):
            with self.assertRaises(LobbyError) as cm:
                self.org.tour_admin(tid, op, **kw)
            self.assertEqual(cm.exception.code, "not_allowed", op)
        self.assertEqual(self.bset(tid, "W1-1").state, "open")
        self.org.tour_admin(tid, "report", set="W1-2", winner=0)   # a set she does not play: hers to decide
        self.assertEqual(self.winner_name(tid, "W1-2"), "Cat")
        self.f.c["Dan"].tour_admin(tid, "report", set="W1-1", winner=1)    # a server tournament admin decides hers
        self.assertEqual(self.winner_name(tid, "W1-1"), "Ben")


class DrainTest(TourBase):
    server_cfg = {"tour_noshow": 5.0}

    def drain(self, on):
        # as `admin drain` / `drain --off` does it: the flag in the database (the admin poll reads it back every
        # T5L_ADMIN_POLL seconds), and at once
        def go():
            self.s.srv.store.set_flag("drain", time.time() if on else None)
            self.s.srv.set_draining(on)
        self.s.call(go)

    def test_a_drain_holds_the_start_and_the_no_show_clock(self):
        # `admin drain` (before a restart): no new match -- a tournament neither starts nor calls or starts a set, and
        # nobody is disqualified as a no-show for the drain (the clocks stand still); drain off: the tournament goes on
        self.f.accept = {n: False for n in self.names}
        self.drain(True)
        tid = self.create(start_in=0.3, wait=False)
        time.sleep(1.0)
        self.assertEqual(self.tour(tid).state, "signup")                      # its start time passed: held
        self.org.tour_admin(tid, "start")                                     # the organizer starts it: no calls
        self.assertEqual([self.bset(tid, x).data.get("live") for x in ("W1-1", "W1-2")], [None, None])
        self.drain(False)                                                     # drain off: the sets are called
        self.f.run(lambda: all(self.bset(tid, x).data.get("live") == "called" for x in ("W1-1", "W1-2")))
        self.drain(True)
        t = self.tour(tid)
        due = {}
        for x in ("W1-1", "W1-2"):
            for aid in self.bset(tid, x).p:                                   # all accept during the drain ...
                self.f.c[t.name_of(aid)].tour_accept(tid, x)
            due[x] = self.bset(tid, x).data["deadline"]
        time.sleep(6.0)                                                      # ... longer than the no-show time
        for x in ("W1-1", "W1-2"):
            s = self.bset(tid, x)
            self.assertEqual((s.state, s.data.get("live"), s.data.get("accepted")), ("open", "called", [True, True]))
        self.assertEqual([e.dq for e in self.tour(tid).entrants.values()], [None] * 4)
        t0 = time.time()
        self.f.accept = {n: True for n in self.names}                         # (the final: the field accepts again)
        self.drain(False)                                                     # the clocks go on: the sets start
        self.f.run(lambda: all(self.bset(tid, x).data.get("live") != "called" for x in ("W1-1", "W1-2")))
        self.wait_state(tid, "finished")
        self.assertEqual([e.dq for e in self.tour(tid).entrants.values()], [None] * 4)
        self.assertGreater(t0, max(due.values()))                             # (the drain outlasted the no-show time)

    def test_a_set_being_played_finishes_during_a_drain(self):
        tid = self.create(players=("Ann", "Ben"))
        self.f.run(lambda: self.bset(tid, "W1-1").data.get("live") == "playing")
        self.drain(True)
        self.wait_state(tid, "finished")                                      # (the set's next game starts by itself)
        self.assertEqual(self.bset(tid, "W1-1").score, [2, 0])


class BlamedVoidTest(TourBase):
    def test_crashing_twice_loses_the_set(self):
        # a game ended by one player's own doing (a crash) called the set again with its score: a losing player could
        # kill the game for a do-over, T5L_TOUR_RETRIES times a set. One is forgiven (T5L_TOUR_BLAMED_VOIDS), not two.
        self.f.special[("W1-1", 2)] = "crash"                    # 1-0, then Ben's game "dies" in game 2 ...
        tid = self.create()
        self.f.run(lambda: int(self.bset(tid, "W1-1").data.get("voids") or 0) == 1)
        self.f.special[("W1-1", 2)] = "crash"                    # ... and again in the replay
        self.f.run(lambda: self.bset(tid, "W1-1").state == "done")
        s = self.bset(tid, "W1-1")
        self.assertEqual((self.winner_name(tid, "W1-1"), s.reason), ("Ann", "forfeit"))
        self.assertEqual(s.data["blamed"], [0, 2])
        self.assertEqual(s.score, [1, 0])


# ============================================================================== 5c. tournament hosts (admin tool)
def run_admin(*args, env=None):
    """t5lobby-admin ARGS -> (exit code, what it printed); the T5L_TOUR_* settings it reads only from `env`."""
    import contextlib
    import io
    from unittest import mock
    from t5lobby.server import admin
    out = io.StringIO()
    with contextlib.redirect_stdout(out), mock.patch.dict(os.environ, env or {}):
        for k in ("T5L_TOUR_MAX_HOSTS", "T5L_TOUR_ADMINS", "T5L_TOUR_ORGANIZERS"):
            if k not in (env or {}):
                os.environ.pop(k, None)
        try:
            rc = admin.main(list(args))
        except SystemExit as e:
            rc = e.code if isinstance(e.code, int) else (print(e.code) or 1)
    return rc, out.getvalue()


class HostCommandTest(unittest.TestCase):
    """`t5lobby-admin tour-host add NAME [--admin]`, `tour-host remove NAME`, `tour-hosts` on the database."""

    def setUp(self):
        from t5lobby.server.store import Store
        d = tempfile.mkdtemp(prefix="tourhosts")
        self.db = os.path.join(d, "t5lobby.db")
        st = Store(self.db)
        for n in ("Ann", "Ben", "Cat", "Dan", "Eve"):
            st.create_account(n, "pw-hash")
        self.ids = {n: st.account(n)["id"] for n in ("Ann", "Ben", "Cat", "Dan", "Eve")}
        st.close()

    def admin(self, *args, **env):
        return run_admin("--db", self.db, *args, env={k: str(v) for k, v in env.items()})

    def hosts(self):
        from t5lobby.server import tournaments
        from t5lobby.server.store import Store
        st = Store(self.db)
        try:
            return {name: role for _aid, (name, role) in tournaments.db_hosts(st).items()}
        finally:
            st.close()

    def test_add_list_and_remove(self):
        rc, out = self.admin("tour-host", "add", "ann")                 # (any case: the account's own name is kept)
        self.assertEqual(rc, 0, out)
        self.assertIn("Ann is now a tournament host", out)
        self.assertIn("1 of 20 host slots used", out)
        rc, out = self.admin("tour-host", "add", "Ben", "--admin")
        self.assertEqual(rc, 0, out)
        self.assertIn("Ben is now a tournament admin", out)
        self.assertIn("1 of 20 host slots used", out)                   # admins take no host slot
        self.assertEqual(self.hosts(), {"Ann": "host", "Ben": "admin"})
        rc, out = self.admin("tour-hosts", T5L_TOUR_ADMINS="wishin", T5L_TOUR_ORGANIZERS="none")
        self.assertEqual(rc, 0, out)
        lines = out.splitlines()
        self.assertTrue(lines[0].startswith("admin  Ben"), out)
        self.assertTrue(lines[1].startswith("host   Ann"), out)
        self.assertIn("wishin", lines[2])
        self.assertIn("T5L_TOUR_ADMINS", lines[2])
        self.assertIn("1 of 20 host slots used; T5L_TOUR_ORGANIZERS=none", out)
        rc, out = self.admin("tour-host", "add", "Ann")
        self.assertIn("a tournament host already", out)
        rc, out = self.admin("tour-host", "remove", "Ann")
        self.assertEqual(rc, 0, out)
        self.assertIn("Ann is no longer a tournament host", out)
        rc, out = self.admin("tour-host", "remove", "Ann")
        self.assertEqual(rc, 1)
        self.assertIn("not a tournament host or admin", out)
        self.assertEqual(self.hosts(), {"Ben": "admin"})
        rc, out = self.admin("tour-host", "remove", "Ben", "--admin")
        self.assertEqual(rc, 1)
        self.assertIn("--admin goes with add", out)

    def test_unknown_and_invalid_names(self):
        rc, out = self.admin("tour-host", "add", "Nobody")
        self.assertEqual(rc, 1)
        self.assertIn("no account named 'Nobody'", out)
        rc, out = self.admin("tour-host", "add", "bad/name")
        self.assertEqual(rc, 1)
        self.assertIn("not a valid player name", out)
        self.assertEqual(self.hosts(), {})

    def test_the_host_limit(self):
        for n in ("Ann", "Ben"):
            self.assertEqual(self.admin("tour-host", "add", n, T5L_TOUR_MAX_HOSTS=2)[0], 0)
        rc, out = self.admin("tour-host", "add", "Cat", T5L_TOUR_MAX_HOSTS=2)
        self.assertEqual(rc, 1)
        self.assertIn("all 2 host slots are used: remove one first", out)
        rc, out = self.admin("tour-host", "add", "Cat", "--admin", T5L_TOUR_MAX_HOSTS=2)
        self.assertEqual(rc, 0, out)                                    # an admin is not counted
        rc, out = self.admin("tour-host", "add", "Cat", T5L_TOUR_MAX_HOSTS=2)
        self.assertEqual(rc, 1, out)                                    # admin -> host needs a slot ...
        rc, out = self.admin("tour-host", "add", "Ann", "--admin", T5L_TOUR_MAX_HOSTS=2)
        self.assertIn("Ann is now a tournament admin (was host)", out)  # ... host -> admin frees one
        self.assertIn("1 of 2 host slots used", out)
        self.assertEqual(self.admin("tour-host", "add", "Dan", T5L_TOUR_MAX_HOSTS=2)[0], 0)
        self.assertEqual(self.hosts(), {"Ann": "admin", "Ben": "host", "Cat": "admin", "Dan": "host"})
        self.assertIn("2 of 20 host slots used", self.admin("tour-hosts")[1])

    def test_a_deleted_account_frees_its_slot_and_a_reused_id_is_no_host(self):
        from t5lobby.server import tournaments
        from t5lobby.server.store import Store
        self.admin("tour-host", "add", "Eve")
        self.admin("tour-host", "add", "Dan", "--admin")
        st = Store(self.db)
        st.delete_account("Eve")
        # a server without the fixed account ids (1.1.2 after a rollback) gives Dan's id to a newcomer
        st.db.execute("DELETE FROM accounts WHERE name = 'Dan'")
        st.db.execute("INSERT INTO accounts (id, name, pw, created, rating, rd, vol) VALUES (?, 'Newcomer', 'x', ?, "
                      "1500, 350, 0.06)", (self.ids["Dan"], time.time() + 1))
        self.assertEqual(tournaments.db_hosts(st), {})
        st.close()
        rc, out = self.admin("tour-hosts")
        self.assertIn("0 of 20 host slots used", out)
        self.assertNotIn("Newcomer", out)
        st = Store(self.db)
        self.assertEqual(st._x("SELECT COUNT(*) FROM tour_hosts").fetchone()[0], 0)    # (the rows are gone)
        st.close()


HINT = "Tournament hosts only: DM wishin for one of the 20 host slots."


class HostServerTest(TourBase):
    """The server with T5L_TOUR_ORGANIZERS=none: the hosts and admins of the admin tool, picked up without a restart."""
    server_cfg = {"tour_organizers": "none", "tour_admins": ["dan"], "admin_poll": 0.2, "tour_per_organizer": 1,
                  "tour_host_hint": HINT}

    def setUp(self):
        d = tempfile.mkdtemp(prefix="tourhosts")
        self.server_cfg = dict(self.server_cfg, db=os.path.join(d, "t5lobby.db"))
        super().setUp()

    def admin(self, *args):
        rc, out = run_admin("--db", self.s.cfg.db, *args)
        self.assertEqual(rc, 0, out)
        return out

    def access(self, name, n):
        """The n-th tour_access pushed to `name`."""
        self.f.run(lambda: len(self.f.events(name, "tour_access")) >= n, 10)
        return self.f.events(name, "tour_access")[n - 1]

    def test_hosts_create_admins_run_everything_without_a_restart(self):
        ann, ben, cat = self.org, self.f.c["Ben"], self.f.c["Cat"]
        lst = ann.tour_list()
        self.assertFalse(lst["can_create"])                         # `none`: nobody but the admins ...
        self.assertEqual(lst["create_hint"], HINT)                  # ... and the server says how to become a host
        self.assertNotIn("create_hint", self.f.c["Dan"].tour_list())       # (T5L_TOUR_ADMINS may create)
        g = client(self.s, "Guesty", tournaments=True)
        try:
            self.assertNotIn("create_hint", g.tour_list())          # (a guest cannot become a host)
        finally:
            g.close()
        with self.assertRaises(LobbyError):
            ann.tour_create("Ann Cup", start=time.time() + 600)
        # the owner adds Ann as a host while she is online: she is told within T5L_ADMIN_POLL, no new login
        self.admin("tour-host", "add", "Ann")
        self.assertEqual(self.access("Ann", 1), {"t": "tour_access", "can_create": True})
        self.assertTrue(ann.tour_list()["can_create"])
        self.assertNotIn("create_hint", ann.tour_list())
        t = ann.tour_create("Ann Cup", start=time.time() + 600)
        with self.assertRaises(LobbyError) as cm:                   # a host has the normal limits (here: 1)
            ann.tour_create("Ann Cup 2", start=time.time() + 600)
        self.assertIn("you already run 1 tournaments", cm.exception.msg)
        self.assertFalse(ben.tour_list()["can_create"])             # not a host: still not
        self.assertEqual(self.f.events("Ben", "tour_access"), [])   # (and told nothing)
        with self.assertRaises(LobbyError):
            ben.tour_admin(t["id"], "cancel")
        # Ben becomes an admin: runs Ann's tournament and is not held by the limits
        self.admin("tour-host", "add", "Ben", "--admin")
        self.assertTrue(self.access("Ben", 1)["can_create"])
        self.assertTrue(ben.tour_get(t["id"])["can_manage"])
        for n in ("Official Ben Cup", "Ben Cup 2"):
            ben.tour_create(n, start=time.time() + 600)             # (a reserved name too, like T5L_TOUR_ADMINS)
        self.assertFalse(cat.tour_get(t["id"])["can_manage"])
        # removed again: refused at once, the launcher is told
        self.admin("tour-host", "remove", "Ann")
        ev = self.access("Ann", 2)
        self.assertEqual((ev["can_create"], ev["create_hint"]), (False, HINT))
        with self.assertRaises(LobbyError):
            ann.tour_create("Ann Cup 3", start=time.time() + 600)
        self.assertTrue(ann.tour_get(t["id"])["can_manage"])        # her tournament stays hers
        self.admin("tour-host", "remove", "Ben")
        self.assertFalse(self.access("Ben", 2)["can_create"])
        with self.assertRaises(LobbyError):
            ben.tour_admin(t["id"], "cancel")
        self.assertEqual(ann.tour_admin(t["id"], "cancel")["state"], "cancelled")

    def test_a_restart_keeps_them(self):
        self.admin("tour-host", "add", "Cat")
        self.f.close()
        self.s.stop()
        self.s = ServerThread(**dict(TOUR, **self.server_cfg)).start()
        self.f = Field(self.s, ("Cat",), create=False)
        self.assertEqual(self.s.call(lambda: dict(self.s.srv.tours.hosts)), {self.account("Cat")["id"]: "host"})
        self.assertTrue(self.f.c["Cat"].tour_list()["can_create"])


class HostRuleTest(unittest.TestCase):
    """may_organize / _is_admin with the database's hosts and admins and every T5L_TOUR_ORGANIZERS rule (no network)."""

    class P:
        def __init__(self, aid, name):
            self.account_id, self.name = aid, name

    def manager(self, **cfg):
        from t5lobby.server import tournaments
        from t5lobby.server.config import Config
        from t5lobby.server.store import Store

        class Srv:
            pass
        srv = Srv()
        srv.cfg = Config(**dict(util.FAST, **cfg))
        srv.store = Store(":memory:")
        self.addCleanup(srv.store.close)
        srv.players = {}
        for n in ("Ann", "Ben", "Cat", "Dan"):
            srv.store.create_account(n, "pw-hash")
        m = tournaments.TourManager(srv)
        self.ids = {n: srv.store.account(n)["id"] for n in ("Ann", "Ben", "Cat", "Dan")}
        tournaments.set_host(srv.store, self.ids["Ann"], "Ann", "host")
        tournaments.set_host(srv.store, self.ids["Ben"], "Ben", "admin")
        self.assertEqual(m.reload_hosts(), {self.ids["Ann"], self.ids["Ben"]})
        return m

    def p(self, name):
        return self.P(self.ids[name], name)

    def test_every_rule(self):
        for rule, cat in (("none", False), ("any", True), ("Cat", True), ("Dan", False)):
            m = self.manager(tour_organizers=rule, tour_admins=["dan"])
            self.assertTrue(m.may_organize(self.p("Ann")), rule)            # a host
            self.assertTrue(m.may_organize(self.p("Ben")), rule)            # an admin
            self.assertEqual(m.may_organize(self.p("Cat")), cat, rule)      # nobody special: the rule decides
            self.assertTrue(m.may_organize(self.p("Dan")), rule)            # T5L_TOUR_ADMINS
            self.assertEqual([m._is_admin(self.p(n)) for n in ("Ann", "Ben", "Cat", "Dan")],
                             [False, True, False, True], rule)
            self.assertFalse(m.may_organize(self.P(None, "Ann")))           # a guest of that name: never
            self.assertFalse(m._is_admin(self.P(None, "Ben")))

    def test_reload_sees_changes_only(self):
        from t5lobby.server import tournaments
        m = self.manager(tour_organizers="none")
        self.assertEqual(m.reload_hosts(), set())
        tournaments.remove_host(m.store, self.ids["Ann"])
        tournaments.set_host(m.store, self.ids["Cat"], "Cat", "admin")
        self.assertEqual(m.reload_hosts(), {self.ids["Ann"], self.ids["Cat"]})
        self.assertFalse(m.may_organize(self.p("Ann")))
        self.assertTrue(m._is_admin(self.p("Cat")))


# ============================================================================== 6. a server restart
class RestartTest(unittest.TestCase):
    def test_a_running_tournament_resumes(self):
        d = tempfile.mkdtemp(prefix="tour")
        db = os.path.join(d, "lobby.db")
        cfg = dict(TOUR, db=db)
        s = ServerThread(**cfg).start()
        f = Field(s, ("Ann", "Ben"))
        try:
            tid = f.c["Ann"].tour_create("Restart Cup", start=time.time() + 0.3)["id"]
            for n in ("Ann", "Ben"):
                f.c[n].tour_join(tid)
            # game 1 is played (1-0), then the server stops while game 2 runs
            f.special[("W1-1", 2)] = "hold"
            f.run(lambda: len(f.starts) == 2)
            sid = s.call(lambda: s.srv.tours.tours[tid].bracket.sets["W1-1"].data.get("lobby_set"))
            self.assertTrue(sid)
        finally:
            for c in f.c.values():
                c.reconnect_window = 0
            s.stop()
            f.close()
        s = ServerThread(**cfg).start()
        try:
            t = s.call(lambda: s.srv.tours.tours[tid])
            self.assertEqual(t.state, "running")
            bs = s.call(lambda: t.bracket.sets["W1-1"])
            self.assertEqual((bs.data["live"], bs.data["carry"]), ("called", [1, 0]))
            self.assertEqual(s.call(lambda: s.srv.store.set_row(sid))["status"], "void")
            f = Field(s, ("Ann", "Ben"), create=False)          # the launchers log in again
            f.run(lambda: s.call(lambda: t.state) == "finished")
            self.assertEqual(s.call(lambda: t.bracket.sets["W1-1"].score), [2, 0])
            first = s.call(lambda: t.name_of(t.bracket.sets["W1-1"].p[0]))       # (side 0 wins every game)
            self.assertEqual(s.call(lambda: t.champion), first)
            calls = [e for e in f.events(first, "tour_call")]
            self.assertEqual(calls[0]["score"], [1, 0])          # it went on at 1-0
            self.assertTrue(calls[0]["replay"])
            f.close()
        finally:
            s.stop()

    def test_the_tables_migrate_once(self):
        d = tempfile.mkdtemp(prefix="tour")
        db = os.path.join(d, "lobby.db")
        from t5lobby.server import tournaments
        from t5lobby.server.store import Store
        st = Store(db)
        self.assertEqual(tournaments.migrate(st.db), [1, 2])
        self.assertEqual(tournaments.migrate(st.db), [])
        self.assertEqual(st.get_flag(tournaments.SCHEMA_KEY), "2")
        st.close()


# ============================================================================== 7. streamers' JSON, older clients
class HttpTest(TourBase):
    server_cfg = {"status_port": -1}                             # (-1: the status endpoint on a free port)

    def get(self, path):
        port = self.s.call(lambda: self.s.srv.status_http.port)
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as r:
            return r.status, r.headers, json.loads(r.read().decode("utf-8"))

    def test_the_brackets_as_json(self):
        tid = self.create()
        self.wait_state(tid, "finished")
        code, headers, body = self.get("/tournaments")
        self.assertEqual(code, 200)
        self.assertEqual(headers.get("Access-Control-Allow-Origin"), "*")
        self.assertEqual(body["tournaments"][0]["name"], "Test Cup")
        code, _h, one = self.get("/tournaments/" + tid)
        self.assertEqual((one["state"], one["champion"]), ("finished", "Ann"))
        self.assertEqual(len(one["bracket"]["sets"]), 3)
        self.assertEqual(one["standings"][0], {"name": "Ann", "place": 1})
        text = json.dumps(one)
        self.assertNotIn("account", text)                        # names only
        self.assertNotIn("127.0.0.1", text)
        with self.assertRaises(urllib.error.HTTPError):
            self.get("/tournaments/nope")


class OldClientTest(TourBase):
    def test_no_tournament_messages_without_the_cap(self):
        pw = "pw-old-x"
        self.s.call(lambda: self.s.srv.store.create_account("Old", hash_password(pw, n=1 << 10)))
        old = client(self.s, "Old", password=pw, sets=True)
        try:
            tid = self.create(players=("Ann", "Ben"))
            self.wait_state(tid, "finished")
            got = []
            while True:
                ev = old.next_event(0.2)
                if ev is None:
                    break
                got.append(ev["t"])
            self.assertFalse([k for k in got if k.startswith("tour_")])
        finally:
            old.close()


# ============================================================================== 7b. the launchers' glue with stub games
class TourDriverTest(TourBase):
    """Four launchers' match drivers with stub games (lobby/tools/stub_game.py, persistent mode): the calls are
    accepted, the games run, their result files are reported -- the bracket fills from what the games say."""

    def launch_stub(self, d):
        import subprocess
        import sys

        stub = os.path.join(os.path.dirname(util.HERE), "tools", "stub_game.py")

        class G:
            def __init__(self, env):
                self.log_path = os.path.join(d, f"game-{time.monotonic_ns()}.log")
                full = dict(os.environ, T5_STUB_SECONDS="0.5")
                full.update(env)
                with open(self.log_path, "w") as lf:
                    self.proc = subprocess.Popen([sys.executable, stub], env=full, stdout=lf, stderr=lf)

            def running(self):
                return self.proc.poll() is None

            def stop(self):
                if self.running():
                    self.proc.kill()
                    self.proc.wait(5)
        return G

    def test_a_bracket_played_by_the_match_driver(self):
        from t5lobby.match_driver import MatchDriver
        drivers = {}
        for n in self.names:
            d = tempfile.mkdtemp(prefix=f"tour{n}")
            drivers[n] = MatchDriver(self.f.c[n], self.launch_stub(d), d, mode="persistent", ask_manual=False)
        tid = self.create(fmt="single")
        try:
            t_end = time.monotonic() + 120
            while time.monotonic() < t_end and self.tour(tid).state != "finished":
                for n, c in self.f.c.items():
                    while True:
                        ev = c.next_event(0)
                        if ev is None:
                            break
                        self.f.log[n].append(ev)
                        if ev["t"] == "tour_call" and not ev["accepted"][0]:
                            try:
                                c.tour_accept(ev["tournament"]["id"], ev["set"]["id"])
                            except LobbyError:
                                pass
                        drivers[n].on_event(ev)
                    drivers[n].poll()
                time.sleep(0.05)
        finally:
            for drv in drivers.values():
                drv.close()
        self.assertEqual(self.tour(tid).state, "finished")
        rows = self.s.call(lambda: [dict(r) for r in self.s.srv.store._x(
            "SELECT status, reports FROM matches WHERE set_id IS NOT NULL").fetchall()])
        self.assertGreaterEqual(len(rows), 6)                    # three sets, two games or more each
        for r in rows:
            self.assertEqual(r["status"], "confirmed")
            self.assertEqual({rep["source"] for rep in json.loads(r["reports"])}, {"game"})   # the games' results
        full = self.org.tour_get(tid)
        self.assertTrue(all(s["reason"] is None and max(s["score"]) == 2 for s in full["bracket"]["sets"]))
        self.assertEqual(full["standings"][0]["name"], full["champion"])


# ============================================================================== 8. end to end: 8 players
class EndToEndTest(TourBase):
    names = ("Ann", "Ben", "Cat", "Dan", "Eve", "Fay", "Gus", "Hal")

    def test_double_elimination_with_eight_players(self):
        t0 = time.monotonic()
        # side 0 wins every game -- except the grand final, which the losers' champion takes 2-1: the reset is played
        gf = {("GF1", 1): 1, ("GF1", 2): 0, ("GF1", 3): 1}
        self.f.plan = lambda sid, number: gf.get((sid, number), 0)
        self.f.special[("L1-1", 1)] = "desync"                   # one replay on the way
        tid = self.create(fmt="double", start_in=0.5)            # (after the plans: its wait pumps the calls already)
        self.wait_state(tid, "finished", timeout=150)
        full = self.org.tour_get(tid)
        sets = {s["id"]: s for s in full["bracket"]["sets"]}
        self.assertEqual(len(sets), 15)
        self.assertTrue(all(s["state"] == "done" for s in sets.values()))
        self.assertEqual(sets["GF1"]["score"], [1, 2])
        self.assertEqual(sets["GF2"]["state"], "done")
        self.assertIsNone(sets["GF2"]["reason"])                 # played, not skipped
        played = [s for s in sets.values() if s["reason"] is None]
        self.assertEqual(len(played), 15)                        # 2n - 1 with the reset
        champ = full["champion"]
        self.assertEqual(sets["GF2"]["p"][sets["GF2"]["winner"]], champ)
        places = {r["name"]: r["place"] for r in full["standings"]}
        self.assertEqual(sorted(places.values()), [1, 2, 3, 4, 5, 5, 7, 7])
        self.assertEqual(places[champ], 1)
        # every player was told where they finished
        for n in self.names:
            fin = [e for e in self.f.events(n, "tour_notice") if e["code"] == "finished"]
            self.assertEqual(len(fin), 1, n)
            self.assertEqual(fin[0]["place"], places[n])
        # the games: every one of them a lobby match with a result from both games (one desync replay)
        rows = self.s.call(lambda: [dict(r) for r in self.s.srv.store._x(
            "SELECT status, origin FROM matches WHERE set_id IS NOT NULL").fetchall()])
        self.assertEqual(sum(1 for r in rows if r["status"] == "void"), 1)
        self.assertEqual(sum(1 for r in rows if r["status"] == "confirmed"), 2 * 14 + 3)
        self.assertTrue({r["origin"] for r in rows} <= {"tournament", "set"})
        print(f"\n  8-player double elimination: {len(rows)} games in {time.monotonic() - t0:.1f} s")


# ============================================================================== 10. with spectating and the relay fallback
class SpectateSetTest(TourBase):
    """A tournament set's game can be watched (docs/SPECTATE.md "Tournaments"): the bracket says so for a set being
    played when both players allow spectators, anybody whose launcher shows tournaments may watch it, the players'
    own setting still decides."""
    names = ("Ann", "Ben")

    def setUp(self):
        import shutil
        cfg = dict(TOUR)
        cfg.update(self.server_cfg)
        self.s = ServerThread(**cfg).start()
        self.tmp = tempfile.mkdtemp(prefix="t5tourspec")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        kw = dict(spectate=True, live_dir=os.path.join(self.tmp, "live"), watch_dir=os.path.join(self.tmp, "watch"))
        self.f = Field(self.s, self.names, **kw)
        for c in self.f.c.values():
            c.set_spectate_prefs(True, False)
        self.org = self.f.c["Ann"]
        self.others = []

    def tearDown(self):
        for c in self.others:
            c.close()
        super().tearDown()

    def viewer(self, name, **kw):
        pw = "pw-" + name.lower() + "-x"
        self.s.call(lambda: self.s.srv.store.create_account(name, hash_password(pw, n=1 << 10)))
        kw.setdefault("spectate", True)
        c = client(self.s, name, password=pw, live_dir=os.path.join(self.tmp, name, "live"),
                   watch_dir=os.path.join(self.tmp, name, "watch"), **kw)
        self.others.append(c)
        return c

    def row(self, c, tid, sid):
        return next(s for s in c.tour_get(tid)["bracket"]["sets"] if s["id"] == sid)

    def test_watch_a_set_being_played(self):
        self.f.special[("W1-1", 1)] = "hold"                     # game 1 goes on: there is something to watch
        vic = self.viewer("Vic", tournaments=True)
        old = self.viewer("Olaf", tournaments=False)            # spectating, but no tournaments in this launcher
        tid = self.create(players=["Ann", "Ben"])
        self.f.run(lambda: self.srv(lambda: (self.s.srv.by_name["ann"].match or None) is not None and
                                    self.s.srv.by_name["ann"].match.state == "playing"), 30)
        mid = self.srv(lambda: self.s.srv.by_name["ann"].match.id)
        t_end = time.monotonic() + 10
        while not self.row(vic, tid, "W1-1").get("watch") and time.monotonic() < t_end:
            self.f.pump()
            time.sleep(0.6)                                      # (tour_get: 2 a second)
        row = self.row(vic, tid, "W1-1")
        self.assertEqual((row["live"], row["watch"]), ("playing", True))
        # the bracket's change reached the launchers (tour_changed), so a shown page fetches Watch in time
        self.assertTrue(any(e.get("id") == tid for e in self.f.events("Ann", "tour_changed")))
        r = vic.watch(tournament=tid, set_id="W1-1")
        self.assertEqual((r["match"], r["stream"]), (mid, mid))
        self.assertEqual(r["tournament"], {"id": tid, "name": "Test Cup", "set": "W1-1"})
        self.assertEqual(sorted(p["name"] for p in r["players"]), ["Ann", "Ben"])
        self.f.run(lambda: any(e.get("count") == 1 for e in self.f.events("Ann", "spectators")), 10)
        vic.unwatch()
        # no tournaments in the launcher, not a friend: not this way (a room or a friend would be)
        with self.assertRaises(LobbyError) as cm:
            old.watch(tournament=tid, set_id="W1-1")
        self.assertIn("only friends", cm.exception.msg)
        with self.assertRaises(LobbyError) as cm:
            vic.watch(tournament=tid, set_id="W9-9")
        self.assertIn("no such set", cm.exception.msg)
        with self.assertRaises(LobbyError):
            vic.watch(tournament="nope", set_id="W1-1")
        # a player who switches spectators off: nobody watches the set
        self.f.c["Ben"].set_spectate_prefs(False, False)
        t_end = time.monotonic() + 10
        while self.row(vic, tid, "W1-1").get("watch") and time.monotonic() < t_end:
            time.sleep(0.6)
        self.assertFalse(self.row(vic, tid, "W1-1").get("watch"))
        with self.assertRaises(LobbyError) as cm:
            vic.watch(tournament=tid, set_id="W1-1")
        self.assertIn("do not allow", cm.exception.msg)
        # a player of the set cannot watch it
        self.f.c["Ben"].set_spectate_prefs(True, False)
        with self.assertRaises(LobbyError) as cm:
            self.f.c["Ann"].watch(tournament=tid, set_id="W1-1")
        self.assertIn("you are playing", cm.exception.msg)


class FallbackSetTest(TourBase):
    """The relay fallback (docs/NETPLAY.md "When Windows Firewall blocks the game") in a tournament set: the game that
    heard nothing moves the set's game onto the relay, the same game is played there (not counted twice), the set and
    the bracket go on as if nothing happened."""
    names = ("Ann", "Ben")

    def setUp(self):
        cfg = dict(TOUR)
        cfg.update(self.server_cfg)
        self.s = ServerThread(**cfg).start()
        self.f = Field(self.s, self.names, relay_bridge=True)
        self.org = self.f.c["Ann"]

    def test_fallback_in_game_one(self):
        from unittest import mock
        self.f.special[("W1-1", 1)] = "hold"                     # game 1: the games hear nothing (no result)
        with mock.patch("t5lobby.client.local_ipv4s", lambda ip: []):      # (a direct path, not the LAN)
            tid = self.create(players=["Ann", "Ben"])
            self.f.run(lambda: len(self.f.events("Ann", "match_start")) == 1 and
                       len(self.f.events("Ben", "match_start")) == 1, 30)
            first = self.f.last("Ann", "match_start")
            self.assertEqual((first["path"], (first["set"] or {}).get("number")), ("direct", 1))
            self.assertEqual(first["set"]["tournament"]["set"], "W1-1")
            self.assertTrue(self.f.c["Ann"].nat_fallback(first["match"]))
            # the same game again on the relay: both launchers get its second match_start; then it is played
            self.f.run(lambda: len(self.f.events("Ann", "match_start")) >= 2 and
                       len(self.f.events("Ben", "match_start")) >= 2, 30)
            again = [e for e in self.f.events("Ann", "match_start")][1]
            self.assertEqual((again["match"], again["path"]), (first["match"], "relay"))
            self.assertEqual((again["set"] or {}).get("number"), 1)              # still game 1 of the set
            self.assertEqual((again["set"] or {}).get("tournament"), first["set"]["tournament"])
            self.wait_state(tid, "finished", timeout=60)
        s = self.bset(tid, "W1-1")
        self.assertEqual((s.state, s.score), ("done", [2, 0]))
        self.assertEqual(self.winner_name(tid, "W1-1"), "Ann")
        games = s.data.get("games") or []
        self.assertEqual([g.get("number") for g in games], [1, 2])               # the fallback is no game of its own
        self.assertEqual([g.get("status") for g in games], ["confirmed", "confirmed"])
        self.assertEqual(self.srv(lambda: self.s.srv.counters["game_fallbacks"]), 1)
        rows = self.s.call(lambda: [dict(r) for r in self.s.srv.store._x(
            "SELECT id, status, path FROM matches WHERE set_id IS NOT NULL ORDER BY created").fetchall()])
        self.assertEqual([(r["status"], r["path"]) for r in rows][0], ("confirmed", "relay"))
        self.assertEqual(len(rows), 2)
        self.assertEqual(self.tour(tid).champion, "Ann")
