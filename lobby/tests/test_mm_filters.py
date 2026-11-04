"""Search options, areas and languages (docs/ONLINE.md "Search options, areas and languages", server/mmfilters.py).

Covers: max_ping / no_wifi / steady hold for both players of a pair (either player's options can refuse it), unknown
Wi-Fi and unknown speed never refuse anybody, an older launcher (no options) is matched as before; netinfo sets Wi-Fi,
area and language; auto area from the nearest relay (relays.json "area", the central's T5L_AREA) within 100 ms; the
lobby list and rooms carry area / lang; bad values are refused; Wi-Fi is never in the lobby list.
"""
import time
import unittest

import util  # noqa: F401 -- sys.path, T5_PORTMAP=0
from t5lobby.proto import LobbyError
from t5lobby.rating import Rating
from t5lobby.server import Config, LobbyServer
from t5lobby.server import relays as relays_mod
from t5lobby.server.lobby import FEATURES, Player
from t5lobby.server.mmfilters import clean_area, clean_lang
from t5lobby.server.relays import RelayNodeRef


class FakeConn:
    def __init__(self, caps=("relays",), build="b1"):
        self.build_id, self.release, self.ip = build, "", "127.0.0.1"
        self.caps = frozenset(caps)
        self.sent = []
        self.closed = False
        self.player = None

    def send(self, msg):
        self.sent.append(msg)


class Base(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.srv = LobbyServer(Config(**util.FAST))
        n = RelayNodeRef("usw", "Oregon", "192.0.2.1", 7781, b"x" * 32, area="na")
        n.ip, n.alive = "192.0.2.1", True
        self.srv.relays.nodes["usw"] = n

    async def asyncTearDown(self):
        self.srv.store.close()

    def player(self, name, rtt=20.0, relays=None, fps=None, wifi=None):
        c = FakeConn()
        p = Player(c, name, guest=True)
        c.player = p
        p.rating = Rating(1500, 80)
        p.server_rtt = rtt
        p.relay_rtt = dict(relays or {})
        p.fps, p.wifi = fps, wifi
        self.srv.players[p.id] = p
        return p

    async def queue(self, p, **options):
        msg = {"t": "queue", "mode": "quick"}
        msg.update(options)
        return await self.srv.h_queue(p.conn, msg)

    def pairs(self):
        return [{a.name, b.name} for a, b, _m in self.srv.match_queue(time.monotonic())]


class FilterTest(Base):
    async def test_feature_announced(self):
        self.assertIn("mm_filters", FEATURES)
        self.assertIn("forget_me", FEATURES)

    async def test_no_options_matches_as_before(self):
        a, b = self.player("A", 30), self.player("B", 40, wifi=True, fps=30)
        await self.queue(a)
        await self.queue(b)
        self.assertEqual(self.pairs(), [{"A", "B"}])

    async def test_max_ping_of_either_side(self):
        a, b = self.player("A", 30), self.player("B", 40)          # estimate 70 ms through the central server
        await self.queue(a, max_ping=60)
        await self.queue(b)
        self.assertEqual(self.pairs(), [])
        self.srv._leave_queue(a)
        await self.queue(a, max_ping=100)
        self.assertEqual(self.pairs(), [{"A", "B"}])

    async def test_max_ping_holds_for_the_other_too(self):
        a, b = self.player("A", 30), self.player("B", 40)
        await self.queue(a)
        await self.queue(b, max_ping=60)
        self.assertEqual(self.pairs(), [])
        self.srv._leave_queue(b)
        await self.queue(b, max_ping=100)
        self.assertEqual(self.pairs(), [{"A", "B"}])

    async def test_no_wifi(self):
        a, b, c = self.player("A"), self.player("B", wifi=True), self.player("C", wifi=None)
        await self.queue(a, no_wifi=True)
        await self.queue(b)
        self.assertEqual(self.pairs(), [])
        await self.queue(c)                                          # not known: not held against C
        self.assertEqual(self.pairs(), [{"A", "C"}])

    async def test_steady(self):
        a, slow, new = self.player("A"), self.player("Slow", fps=48.0), self.player("New", fps=None)
        await self.queue(a, steady=True)
        await self.queue(slow)
        self.assertEqual(self.pairs(), [])
        await self.queue(new)
        self.assertEqual(self.pairs(), [{"A", "New"}])

    async def test_bad_values_refused(self):
        a = self.player("A")
        for bad in (55, "100", True, 0):
            with self.assertRaises(LobbyError):
                await self.queue(a, max_ping=bad)

    async def test_reply_names_the_options(self):
        a = self.player("A")
        r = await self.queue(a, max_ping=60, no_wifi=True)
        self.assertEqual(r["filters"], {"max_ping": 60, "no_wifi": True, "steady": False})
        r = await self.queue(a)
        self.assertNotIn("filters", r)


class AreaTest(Base):
    async def test_auto_area_from_the_nearest_relay(self):
        p = self.player("A", rtt=150, relays={"usw": 30})
        self.srv._update_area(p)
        self.assertEqual(p.area, "na")
        self.assertEqual(p.public()["area"], "na")

    async def test_central_area_and_too_far(self):
        p = self.player("A", rtt=25, relays={"usw": 160})
        self.srv._update_area(p)
        self.assertEqual(p.area, "eu")                               # T5L_AREA default
        far = self.player("Far", rtt=250, relays={"usw": 180})
        self.srv._update_area(far)
        self.assertEqual(far.area, "")
        self.assertNotIn("area", far.public())

    async def test_netinfo_choice_and_language(self):
        p = self.player("A", rtt=25)
        r = await self.srv.h_netinfo(p.conn, {"t": "netinfo", "wifi": True, "area": "sa", "lang": "pt-br"})
        self.assertEqual(r, {"t": "netinfo", "area": "sa", "lang": "pt-BR"})
        self.assertIs(p.wifi, True)
        pub = p.public()
        self.assertEqual((pub["area"], pub["lang"]), ("sa", "pt-BR"))
        self.assertNotIn("wifi", pub)                               # never shown to anybody
        await self.srv.h_netinfo(p.conn, {"t": "netinfo", "wifi": "yes", "area": "auto"})
        self.assertIsNone(p.wifi)
        self.assertEqual(p.area, "eu")
        for bad in ({"area": "mars"}, {"lang": "english!"}, {"lang": "x"}):
            with self.assertRaises(LobbyError):
                await self.srv.h_netinfo(p.conn, dict({"t": "netinfo"}, **bad))

    async def test_clean(self):
        self.assertEqual(clean_area("EU"), "eu")
        self.assertEqual(clean_area(""), "auto")
        self.assertIsNone(clean_area("auto", allow_auto=False))
        self.assertEqual(clean_lang("de"), "de")
        self.assertEqual(clean_lang("PT-br"), "pt-BR")
        self.assertEqual(clean_lang(""), "")
        self.assertIsNone(clean_lang("de_DE"))

    async def test_relays_json_area(self):
        import json, os, tempfile
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "s.secret"), "wb") as f:
                f.write(b"k" * 32)
            text = json.dumps({"relays": [{"id": "use", "host": "192.0.2.9", "secret_file": "s.secret",
                                           "area": "NA"}]})
            nodes = relays_mod.parse(text, d)
            self.assertEqual(nodes[0].area, "na")
            with self.assertRaises(ValueError):
                relays_mod.parse(json.dumps({"relays": [{"id": "x", "host": "192.0.2.9", "secret_file": "s.secret",
                                                         "area": "moon"}]}), d)

    async def test_room_tags(self):
        p = self.player("A", rtt=25)
        p.lang = "de"
        self.srv._update_area(p)
        p.conn.caps = frozenset(("private_rooms",))
        await self.srv.h_room_create(p.conn, {"t": "room_create", "name": "x"})
        room = p.room
        self.assertEqual((room.area, room.lang), ("eu", "de"))
        self.assertEqual(room.public()["area"], "eu")
        self.srv._leave_room(p)
        q = self.player("B", rtt=25)
        q.conn.caps = frozenset(("private_rooms",))
        await self.srv.h_room_create(q.conn, {"t": "room_create", "name": "y", "area": "as", "lang": "ko"})
        self.assertEqual((q.room.area, q.room.lang), ("as", "ko"))


if __name__ == "__main__":
    unittest.main()
