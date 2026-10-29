"""Challenges, 1.1.9 (players asked for it): several open challenges at once to different players, the first one
accepted wins and the others are withdrawn on both sides; the challenger picks the casual input delay (or auto, from
the ping) and both see it before the answer; the match and its rematches use it."""
import time
import unittest

from util import ServerThread, client, expect

from t5lobby import proto
from t5lobby.client import LobbyError


class Base(unittest.TestCase):
    def setUp(self):
        self.s = ServerThread().start()
        self.clients = []

    def tearDown(self):
        for c in self.clients:
            c.close()
        self.s.stop()

    def c(self, name):
        c = client(self.s, name)
        self.clients.append(c)
        return c

    def gap(self):
        time.sleep(0.75)                      # (one challenge every 0.7 s)


class ChallengesTest(Base):
    def test_several_at_once_first_accepted_wins(self):
        a, b, c, d = self.c("Alice"), self.c("Bob"), self.c("Cid"), self.c("Dora")
        e = self.c("Eve")
        rb = a.send_challenge(b.me["id"], 2)
        self.assertEqual(rb["delay"], {"frames": 2, "auto": False})
        self.assertEqual(rb["to"]["name"], "Bob")
        self.gap()
        rc = a.send_challenge(c.me["id"])
        self.assertTrue(rc["delay"]["auto"])
        self.gap()
        rd = a.send_challenge(d.me["id"], 0)
        ev_b, ev_c = expect(b, "challenged"), expect(c, "challenged")
        self.assertEqual(ev_b["delay"], {"frames": 2, "auto": False})       # the receiver sees it before answering
        self.assertTrue(ev_c["delay"]["auto"])
        self.assertIn(ev_c["delay"]["frames"], (1, 2, 3, 4))                  # (from the ping: local, 1)
        expect(d, "challenged")
        ce = e.challenge(a.me["id"])                     # somebody challenges Alice meanwhile
        expect(a, "challenged")
        self.gap()
        with self.assertRaises(LobbyError) as x:         # the same player twice: no
            a.challenge(b.me["id"])
        self.assertEqual(x.exception.code, proto.E_RATE)
        b.answer_challenge(rb["challenge"], accept=True)
        got = {}
        while True:                                      # Alice: every update, then the match
            ev = expect(a, ("challenge_update", "match_found"))
            if ev["t"] == "match_found":
                break
            got[ev["challenge"]] = ev["state"]
        expect(b, "match_found")
        # the others are withdrawn, and both sides of each hear it
        for who, cid in ((c, rc["challenge"]), (d, rd["challenge"]), (e, ce)):
            up = expect(who, "challenge_update")
            self.assertEqual((up["challenge"], up["state"]), (cid, "withdrawn"))
        self.assertEqual(got.get(rb["challenge"]), "accepted")
        for cid in (rc["challenge"], rd["challenge"], ce):
            self.assertEqual(got.get(cid), "withdrawn")
        self.assertEqual(self.s.call(lambda: len(self.s.srv.challenges)), 0)
        sa, sb = expect(a, "match_start", 20), expect(b, "match_start", 20)
        self.assertEqual((sa["ticket"].input_delay, sb["ticket"].input_delay), (2, 2))   # the chosen delay, both

    def test_cancel_one_keeps_the_others(self):
        a, b, c = self.c("Alice"), self.c("Bob"), self.c("Cid")
        cb = a.challenge(b.me["id"], 2)
        self.gap()
        cc = a.challenge(c.me["id"], 1)
        expect(b, "challenged")
        expect(c, "challenged")
        a.cancel_challenge(cb)
        self.assertEqual(expect(b, "challenge_update")["state"], "cancelled")
        self.assertEqual(self.s.call(lambda: list(self.s.srv.challenges)), [cc])
        c.answer_challenge(cc, accept=True)
        sa, sc = expect(a, "match_start", 20), expect(c, "match_start", 20)
        self.assertEqual((sa["ticket"].input_delay, sc["ticket"].input_delay), (1, 1))
        # a rematch (new session or not) keeps the challenge's delay
        m = self.s.call(lambda: self.s.srv.matches[sa["match"]])
        self.assertEqual(m.casual_delay, 1)

    def test_auto_keeps_the_old_rule(self):
        a, b = self.c("Alice"), self.c("Bob")
        cid = a.challenge(b.me["id"])                  # auto: the players' own settings, as before
        expect(b, "challenged")
        b.answer_challenge(cid, accept=True)
        sa = expect(a, "match_start", 20)
        self.assertIsNone(sa["ticket"].input_delay)

    def test_limits(self):
        players = [self.c(f"Gina{i}") for i in range(7)]
        a = players[0]
        for q in players[1:6]:
            a.challenge(q.me["id"])
            self.gap()
        with self.assertRaises(LobbyError) as x:        # five open at most
            a.challenge(players[6].me["id"])
        self.assertEqual(x.exception.code, proto.E_RATE)
        b = players[1]
        with self.assertRaises(LobbyError) as x:        # a delay out of range
            b.send_challenge(players[6].me["id"], 3)
        self.assertEqual(x.exception.code, proto.E_BAD_REQUEST)
        b.challenge(players[6].me["id"])
        with self.assertRaises(LobbyError) as x:        # right after another one: too fast
            b.challenge(players[5].me["id"])
        self.assertEqual(x.exception.code, proto.E_RATE)

    def test_old_client_without_delay(self):
        a, b = self.c("Alice"), self.c("Bob")
        a.welcome["features"] = [f for f in a.welcome["features"] if f != "challenges2"]   # (as an older launcher)
        r = a.send_challenge(b.me["id"], 0)             # the delay is not sent to a server without the feature
        self.assertEqual(r["delay"], {"frames": 1, "auto": True})


if __name__ == "__main__":
    unittest.main()
