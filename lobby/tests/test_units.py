"""Unit tests without a running server: rating math, wire format, delay suggestion, rate limits,
password hashing, build ids."""
import unittest

import util  # noqa: F401  (sets sys.path)
from t5lobby import proto, rating
from t5lobby.buildid import BuildInfo
from t5lobby.handover import MatchTicket, read_result_file
from t5lobby.server.ratelimit import TokenBucket
from t5lobby.server.store import Store, check_password, hash_password


class GlickoTest(unittest.TestCase):
    def test_glickman_example(self):
        # The worked example from Glickman's "Example of the Glicko-2 system".
        p = rating.Rating(1500, 200, 0.06)
        new = rating.update(p, [(rating.Rating(1400, 30), 1), (rating.Rating(1550, 100), 0),
                                (rating.Rating(1700, 300), 0)])
        self.assertAlmostEqual(new.r, 1464.06, places=1)
        self.assertAlmostEqual(new.rd, 151.52, places=1)
        self.assertAlmostEqual(new.vol, 0.05999, places=4)

    def test_match_is_zero_sum_for_equal_players(self):
        a, b = rating.match(rating.Rating(), rating.Rating(), 1.0)
        self.assertGreater(a.r, 1500)
        self.assertLess(b.r, 1500)
        self.assertAlmostEqual(a.r - 1500, 1500 - b.r, places=6)
        self.assertLess(a.rd, 350)

    def test_upset_moves_more(self):
        strong, weak = rating.Rating(1800, 60), rating.Rating(1400, 60)
        s_win, _ = rating.match(strong, weak, 1.0)
        s_loss, _ = rating.match(strong, weak, 0.0)
        self.assertLess(s_win.r - strong.r, strong.r - s_loss.r)

    def test_inflate(self):
        r = rating.inflate(rating.Rating(1600, 50, 0.06), 70)
        self.assertGreater(r.rd, 50)
        self.assertEqual(r.r, 1600)


class ProtoTest(unittest.TestCase):
    def test_line_codec(self):
        m = {"t": "chat", "text": "héllo"}
        self.assertEqual(proto.decode(proto.encode(m).rstrip(b"\n")), m)
        for bad in (b"[1]", b"{}", b'{"t": 5}', b"nope"):
            with self.assertRaises(ValueError):
                proto.decode(bad)

    def test_names(self):
        for ok in ("Kazuya", "Jin K", "a_b-c.d", "[T5]Law!"):
            self.assertTrue(proto.valid_name(ok), ok)
        for bad in ("x", "a" * 17, " lead", "trail ", "two  sp", "tab\tx", "émile", "", None, 5):
            self.assertFalse(proto.valid_name(bad), bad)

    def test_udp_packets(self):
        tok = proto.new_token()
        reg = proto.pk_token(proto.U_REGISTER, tok)
        ack = proto.pk_token_ack(proto.U_REG_ACK, tok, ("203.0.113.7", 40000))
        self.assertEqual(len(reg), 32)
        self.assertLessEqual(len(ack), len(reg))           # no amplification
        self.assertEqual(proto.udp_type(reg), proto.U_REGISTER)
        self.assertEqual(proto.un_token_ack(ack), (proto.U_REG_ACK, tok, ("203.0.113.7", 40000)))
        self.assertIsNone(proto.udp_type(b"T5NP\x02\x01" + bytes(20)))   # game packets are not ours
        self.assertEqual(len(proto.pk_ping(proto.U_SPING, 1, 0.5)), proto.PING.size)

    def test_delay(self):
        self.assertEqual(proto.suggest_delay(0.3), 2)       # LAN / same PC
        self.assertEqual(proto.suggest_delay(40, 2), 3)
        self.assertEqual(proto.suggest_delay(100, 5), 5)
        self.assertEqual(proto.suggest_delay(1000, 50), 10)  # clamped

    def test_hostport(self):
        self.assertEqual(proto.parse_hostport("example.org"), ("example.org", proto.DEFAULT_PORT))
        self.assertEqual(proto.parse_hostport("1.2.3.4:99"), ("1.2.3.4", 99))
        self.assertEqual(proto.parse_hostport("[::1]:5"), ("::1", 5))


class MiscTest(unittest.TestCase):
    def test_token_bucket(self):
        b = TokenBucket(rate=10, burst=3)
        t = b.t
        self.assertTrue(all(b.take(1, t) for _ in range(3)))
        self.assertFalse(b.take(1, t))
        self.assertTrue(b.take(1, t + 0.11))

    def test_password_hash(self):
        h = hash_password("hunter22", n=1 << 10)
        self.assertTrue(h.startswith("scrypt$"))
        self.assertNotIn("hunter22", h)
        self.assertTrue(check_password("hunter22", h))
        self.assertFalse(check_password("hunter23", h))
        self.assertNotEqual(h, hash_password("hunter22", n=1 << 10))   # salted
        self.assertFalse(check_password("x", "garbage"))

    def test_store_accounts(self):
        st = Store(":memory:")
        self.assertIsNotNone(st.create_account("Paul", "h"))
        self.assertIsNone(st.create_account("PAUL", "h"))             # names are case-insensitive
        self.assertEqual(st.account("paul")["name"], "Paul")

    def test_build_id(self):
        a = BuildInfo("aa", "bb")
        self.assertEqual(a.build_id, BuildInfo("AA", "BB").build_id)
        self.assertNotEqual(a.build_id, BuildInfo("aa", "bc").build_id)
        self.assertNotEqual(a.build_id, BuildInfo("aa", "bb", net=2).build_id)
        self.assertEqual(BuildInfo.wire_id(dict(a.as_wire(), id="forged")), a.build_id)

    def test_ticket_env(self):
        t = MatchTicket("m1", "join", 1, 50001, ("198.51.100.4", 50002), "direct", 31.0, 2.0, 3)
        env = t.game_env(result_file="r.json")
        self.assertEqual(env["T5_NET_MODE"], "join")
        self.assertEqual(env["T5_NET_PORT"], "50001")
        self.assertEqual(env["T5_NET_PEER"], "198.51.100.4:50002")
        self.assertEqual(env["T5_NET_DELAY"], "3")
        self.assertEqual(env["T5_NET_RESULT_FILE"], "r.json")

    def test_result_file(self):
        import json
        import os
        import tempfile
        d = tempfile.mkdtemp()
        p = os.path.join(d, "r.json")
        self.assertIsNone(read_result_file(p))
        with open(p, "w") as f:
            json.dump({"winner": 1, "score": [2, 3]}, f)
        self.assertEqual(read_result_file(p), (1, [2, 3]))


if __name__ == "__main__":
    unittest.main()
