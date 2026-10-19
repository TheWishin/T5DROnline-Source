"""The Tekken 5 stages online (docs/RANKED.md "Characters and stages"): data/fighters.json lists them ("t5", the
game's stage ids 0-13 and 15), the stage drawn for a match is one of them only when the server enables it
(T5L_OLD_STAGES, default off) and both clients announce the old_stages cap; the stage select's own stages (17-34)
are drawn exactly as before otherwise."""
import unittest

import util  # noqa: F401  (puts lobby/ on the path)
from util import ServerThread, client, expect
from t5lobby import fighters
from t5lobby.server import Config


class TableTest(unittest.TestCase):
    def test_the_t5_stages(self):
        t = fighters.table()
        old = [s for s in t.stages if s.get("t5")]
        self.assertEqual([s["id"] for s in old], list(range(0, 14)) + [15])
        self.assertEqual([s["id"] for s in t.stages if not s.get("t5")], list(range(17, 35)))
        self.assertEqual(t.stage_name("t5s01"), "Tekken 5 stage 1")
        self.assertEqual(t.fight_env("paul", "law", "t5s15", 3), "0,1,15,3")
        self.assertTrue(t.valid_stage("t5s01"))

    def test_draw_without_them_is_unchanged(self):
        t = fighters.table()
        new = set(t.stage_pool())
        self.assertEqual(new, {s["key"] for s in t.stages if not s.get("t5")})
        for seed in range(400):
            self.assertIn(t.resolve("jin", "paul", "random", seed)[2], new)
        # the draw itself did not move: the same seeds give the same stages as with the old table (stage ids
        # 17-34 in the order of the file; the RNG draws two fighters, then one stage)
        import random
        keys = [s["key"] for s in t.stages if not s.get("t5")]
        for seed in (0, 1, 1234, 99999):
            rng = random.Random(seed)
            self.assertEqual(t.resolve("jin", "paul", "random", seed)[2], rng.choice(keys))

    def test_draw_with_them(self):
        t = fighters.table()
        got = {t.resolve("jin", "paul", "random", seed, old_stages=True)[2] for seed in range(600)}
        self.assertTrue(any(k.startswith("t5s") for k in got))
        self.assertTrue(any(k.startswith("s") for k in got))
        self.assertEqual(t.resolve("random", "jin", "random", 7, old_stages=True),
                         t.resolve("random", "jin", "random", 7, old_stages=True))     # the same on every PC


class ServerTest(unittest.TestCase):
    server_cfg = {}

    def setUp(self):
        self.s = ServerThread(**self.server_cfg).start()
        self.clients = []
        # record what the server asks the table for (the stage draw itself is random per match)
        self.calls = []
        table = self.s.srv.table
        orig = table.resolve

        def resolve(*a, **kw):
            self.calls.append(kw.get("old_stages", False))
            return orig(*a, **kw)
        table.resolve = resolve

    def tearDown(self):
        for c in self.clients:
            c.close()
        self.s.stop()

    def acc(self, name, **kw):
        c = client(self.s, name, password="pw-" + name, register=True, auto_ready=True, **kw)
        self.clients.append(c)
        return c

    def match(self, a, b):
        a.quick_match("jin")
        b.quick_match("paul")
        ea, eb = expect(a, "match_start"), expect(b, "match_start")
        self.assertEqual(ea["fight"]["stage"], eb["fight"]["stage"])
        return ea["fight"]["stage"]

    def test_off_by_default(self):
        self.assertFalse(Config().old_stages)
        self.assertTrue(Config.from_env({"T5L_OLD_STAGES": "1"}).old_stages)
        a, b = self.acc("Alice"), self.acc("Bob")
        self.assertIn("old_stages", a.welcome["caps"])
        st = self.match(a, b)
        self.assertFalse(st.startswith("t5s"), st)
        self.assertTrue(self.calls and not any(self.calls))


class OnTest(ServerTest):
    server_cfg = {"old_stages": True}

    def test_off_by_default(self):     # (the base test does not apply with the setting on)
        pass

    def test_drawn_when_both_clients_know_them(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        st = self.match(a, b)
        self.assertIn(st, {s["key"] for s in fighters.table().stages})
        self.assertIn(True, self.calls)                     # the stage was drawn from the pool with the T5 stages

    def test_never_with_an_older_client(self):
        a, b = self.acc("Alice"), self.acc("Bob", old_stages=False)
        self.assertNotIn("old_stages", b.welcome["caps"])
        st = self.match(a, b)
        self.assertFalse(st.startswith("t5s"), st)
        self.assertTrue(self.calls and not any(self.calls))


if __name__ == "__main__":
    unittest.main()
