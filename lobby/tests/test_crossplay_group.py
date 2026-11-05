"""1.2.1: the crossplay group a release declares (US + EU Online); offline policy tests plus one real-server pairing.

The declared group (build stamp / release.json "crossplay", sent in the hello with the edition) is accepted by the
server only for a program in compatibility.CROSSPLAY_EDITIONS, only with the compat_groups capability, and only
while T5L_CROSSPLAY is on (T5L_CROSSPLAY_GROUPS can narrow it). Different groups, an unknown or EU v01.00 program,
an old client or a 1.2.0 launcher (no declaration) keep exact matching."""
import json
import os
import tempfile
import unittest
from types import SimpleNamespace

import util
from util import ServerThread, client, expect
from t5lobby import proto
from t5lobby.buildid import BuildInfo
from t5lobby.client import LobbyClient
from t5lobby.compatibility import CAP, CROSSPLAY_EDITIONS, CrossplayPolicy, compatible
from t5lobby.proto import LobbyError
from t5lobby.server import Config, LobbyServer
Cfg = Config
from t5lobby.server.lobby import Player
from t5lobby.server.rooms import Room

US_ELF = "be80165b84e30b6334baa6d6331b9db4ffd5a6a4"
EU_ELF = "ff07efe07be23a30e37601049f4e849ddc2cff02"
EU200_ELF = "a26bc6e037e5a8faf40250849acfa8a40d027fff"
EU100_ELF = "586baa2074e3d259b303879fc7cbea1000041b60"      # the EU v01.00 game: other fighter data, never grouped
G = "t5x-0123456789ab"
G2 = "t5x-ba9876543210"


def build(elf, code, group=G, edition=None, net=4):
    ed = CROSSPLAY_EDITIONS.get(elf, "") if edition is None else edition
    return BuildInfo(elf, code, "test", net, edition=ed if group else "", crossplay=group)


US = build(US_ELF, "aaaaaaaaaaaaaaaa")
EU = build(EU_ELF, "bbbbbbbbbbbbbbbb")
EU200 = build(EU200_ELF, "cccccccccccccccc")


class PolicyTest(unittest.TestCase):
    def test_declaration_of_a_known_program_is_accepted_with_net_in_the_group(self):
        p = CrossplayPolicy()
        for b in (US, EU, EU200):
            self.assertEqual(p.group(b.as_wire(), {CAP}), G + "-n4")
        self.assertEqual(p.group(build(US_ELF, "x", net=5).as_wire(), {CAP}), G + "-n5")

    def test_nothing_accepted_without_capability_program_or_a_well_formed_claim(self):
        p = CrossplayPolicy()
        w = US.as_wire()
        self.assertEqual(p.group(w, set()), "")                                    # 1.1.x launcher: no capability
        self.assertEqual(p.group(build(EU100_ELF, "x").as_wire(), {CAP}), "")      # EU v01.00 is another game
        self.assertEqual(p.group(build("0" * 40, "x").as_wire(), {CAP}), "")       # unknown program
        self.assertEqual(p.group(build(US_ELF, "x", group="").as_wire(), {CAP}), "")   # declares nothing (1.2.0)
        for bad in ("T5X-0123456789ab", "t5x-0123456789a", "t5x-0123456789abc", "t5x-0123456789zz", "x", 7, None, ["t5x"]):
            with self.subTest(claim=bad):
                self.assertEqual(p.group(dict(w, crossplay=bad), {CAP}), "")
        for net in (0, -1, True, "4", None):
            with self.subTest(net=net):
                self.assertEqual(p.group(dict(w, net=net), {CAP}), "")
        self.assertEqual(p.group(None, {CAP}), "")
        self.assertEqual(p.group("t5x", {CAP}), "")

    def test_a_declared_edition_must_be_the_programs_own(self):
        p = CrossplayPolicy()
        self.assertEqual(p.group(dict(US.as_wire(), edition="EU-Online"), {CAP}), "")
        self.assertEqual(p.group(dict(EU.as_wire(), edition="US"), {CAP}), "")
        self.assertEqual(p.group(dict(US.as_wire(), edition=""), {CAP}), G + "-n4")
        w = US.as_wire()
        w.pop("edition", None)
        self.assertEqual(p.group(w, {CAP}), G + "-n4")

    def test_operator_switch_and_allowlist(self):
        self.assertEqual(CrossplayPolicy(False).group(US.as_wire(), {CAP}), "")
        p = CrossplayPolicy(True, [G.upper(), " "])
        self.assertEqual(p.group(US.as_wire(), {CAP}), G + "-n4")
        self.assertEqual(p.group(build(US_ELF, "x", group=G2).as_wire(), {CAP}), "")
        with self.assertRaises(ValueError):
            CrossplayPolicy(True, ["not-a-group"])

    def test_config_reads_the_environment(self):
        c = Cfg.from_env({"T5L_CROSSPLAY": "0", "T5L_CROSSPLAY_GROUPS": G + "," + G2.upper()})
        self.assertFalse(c.crossplay)
        self.assertEqual(c.crossplay_groups, [G, G2])
        self.assertTrue(Cfg.from_env({}).crossplay)

    def test_wire_is_unchanged_without_a_declaration(self):
        plain = BuildInfo(US_ELF, "aaaaaaaaaaaaaaaa", "test")
        self.assertEqual(plain.as_wire(), {"id": plain.build_id, "elf": US_ELF, "code": "aaaaaaaaaaaaaaaa",
                                           "net": 4, "release": "test"})
        self.assertEqual(US.as_wire()["crossplay"], G)
        self.assertEqual(US.as_wire()["edition"], "US")
        self.assertEqual(US.build_id, BuildInfo(US_ELF, "aaaaaaaaaaaaaaaa", "test").build_id)   # not part of the id
        self.assertEqual(BuildInfo.wire_id(US.as_wire()), US.build_id)

    def test_the_launcher_reads_the_declaration_from_the_build_stamp(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "game"))
            os.makedirs(os.path.join(d, "build"))
            with open(os.path.join(d, "game", "EBOOT.elf"), "wb") as f:
                f.write(b"not a real program")
            stamp = os.path.join(d, "build", "t5dr_build.json")
            with open(stamp, "w") as f:
                json.dump({"code_id": "aaaaaaaaaaaaaaaa", "edition": "EU-Online", "crossplay": G}, f)
            b = BuildInfo.from_out_dir(d, "1.2.1")
            self.assertEqual((b.edition, b.crossplay), ("EU-Online", G))
            self.assertEqual(b.as_wire()["crossplay"], G)
            with open(stamp, "w") as f:                                  # a build made before 1.2.1
                json.dump({"code_id": "aaaaaaaaaaaaaaaa"}, f)
            b = BuildInfo.from_out_dir(d, "1.2.0")
            self.assertEqual((b.edition, b.crossplay), ("", ""))
            self.assertNotIn("crossplay", b.as_wire())
            with open(stamp, "w") as f:                                  # a stamp that is not a string: ignored
                json.dump({"code_id": "aaaaaaaaaaaaaaaa", "edition": "US", "crossplay": {"group": G}}, f)
            self.assertEqual(BuildInfo.from_out_dir(d).crossplay, "")

    def test_build_game_declares_it_for_exactly_the_crossplay_programs(self):
        import sys
        tools = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "tools")
        sys.path.insert(0, tools)
        try:
            import build_game as bg
        finally:
            sys.path.remove(tools)
        declared = {sha for sha, p in bg.PROGRAMS.items() if p.get("crossplay")}
        self.assertEqual(declared, set(CROSSPLAY_EDITIONS))
        for sha in declared:
            self.assertEqual(bg.PROGRAMS[sha]["edition"], CROSSPLAY_EDITIONS[sha])
            self.assertTrue(bg.PROGRAMS[sha]["online"], sha)             # the launcher may log them in
        self.assertFalse(bg.PROGRAMS[EU100_ELF].get("crossplay"))
        self.assertFalse(bg.PROGRAMS[EU100_ELF]["online"])
        self.assertRegex(bg.crossplay_group(), r"^t5x-[0-9a-f]{12}$")
        self.assertEqual(bg.crossplay_group(), bg.crossplay_group())


class ServerTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.srv = LobbyServer(Config(**util.FAST))

    async def asyncTearDown(self):
        self.srv.store.close()

    async def hello(self, b, caps=(CAP,)):
        conn = SimpleNamespace(player=None, ip="127.0.0.1", sent=[],
                               writer=SimpleNamespace(get_extra_info=lambda _key: None))
        conn.send = conn.sent.append
        welcome = await self.srv.h_hello(conn, {"proto": proto.PROTO_VERSION, "build": b.as_wire(), "caps": list(caps)})
        return conn, welcome

    async def player(self, name, b, caps=(CAP,)):
        conn, welcome = await self.hello(b, caps)
        conn.build_id = BuildInfo.wire_id(b.as_wire())
        p = Player(conn, name, guest=True)
        conn.player = p
        self.srv.players[p.id] = p
        return p, welcome

    async def test_hello_derives_the_group_and_ignores_forged_fields(self):
        conn, welcome = await self.hello(US)
        self.assertEqual(welcome["compat_group"], G + "-n4")
        self.assertEqual(welcome["region"], "US")
        _, welcome = await self.hello(EU)
        self.assertEqual((welcome["compat_group"], welcome["region"]), (G + "-n4", "EU"))
        _, welcome = await self.hello(EU, caps=())
        self.assertEqual(welcome["compat_group"], "")
        # the wire id is recomputed from elf/code/net, so a claimed "id" and "compat_group" mean nothing
        forged = dict(US.as_wire(), id=EU.build_id, compat_group="t5x-ffffffffffff-n4")
        conn = SimpleNamespace(player=None, ip="127.0.0.1", writer=SimpleNamespace(get_extra_info=lambda _key: None))
        welcome = await self.srv.h_hello(conn, {"proto": proto.PROTO_VERSION, "build": forged, "caps": [CAP]})
        self.assertEqual((welcome["build"], welcome["compat_group"]), (US.build_id, G + "-n4"))

    async def test_us_and_eu_online_pair_in_the_queue_and_by_challenge(self):
        a, _ = await self.player("US", US)
        b, _ = await self.player("EU", EU)
        c, _ = await self.player("EU200", EU200)
        self.assertTrue(compatible(a, b) and compatible(b, c) and compatible(a, c))
        for mode, (x, y) in (("quick", (a, b)), ("ranked", (b, c))):
            self.srv._enqueue(x, mode, 0)
            self.srv._enqueue(y, mode, 0)
            made = self.srv.match_queue()
            self.assertEqual(len(made), 1, mode)
            self.assertEqual(x.match.compat_group, G + "-n4")
            self.srv.cancel_match(x.match, "test_done")
        d, _ = await self.player("US2", US)
        m = self.srv.create_match(d, c, False, "challenge")
        self.assertIs(d.match, m)
        self.srv.cancel_match(m, "test_done")

    async def test_other_groups_other_nets_and_unknown_programs_never_meet(self):
        us, _ = await self.player("US", US)
        for name, other in (("G2", build(EU_ELF, "d" * 16, group=G2)),
                            ("net3", build(EU_ELF, "e" * 16, net=3)),
                            ("nodecl", build(EU_ELF, "f" * 16, group="")),
                            ("eu100", build(EU100_ELF, "1" * 16)),
                            ("unknown", build("1" * 40, "2" * 16))):
            with self.subTest(name):
                p, _ = await self.player(name, other)
                self.assertFalse(compatible(us, p))
                with self.assertRaises(LobbyError):
                    self.srv.create_match(us, p, False, "challenge")
                with self.assertRaises(LobbyError):
                    await self.srv.h_challenge(us.conn, {"player": p.id})
                self.srv._enqueue(us, "quick", 0)
                self.srv._enqueue(p, "quick", 0)
                self.assertEqual(self.srv.match_queue(), [])
                self.srv._leave_queue(us)
                self.srv._leave_queue(p)

    async def test_a_server_with_the_switch_off_or_another_allowlist_keeps_exact_builds(self):
        for kw in ({"crossplay": False}, {"crossplay_groups": [G2]}):
            srv = LobbyServer(Config(**util.FAST, **kw))
            try:
                conns = []
                for b in (US, EU):
                    conn = SimpleNamespace(player=None, ip="127.0.0.1",
                                           writer=SimpleNamespace(get_extra_info=lambda _key: None))
                    w = await srv.h_hello(conn, {"proto": proto.PROTO_VERSION, "build": b.as_wire(), "caps": [CAP]})
                    self.assertEqual(w["compat_group"], "", kw)
                    conns.append(conn)
            finally:
                srv.store.close()

    async def test_old_clients_stay_exact_and_cannot_cross(self):
        old, _ = await self.player("Old", US, caps=())                  # 1.1.x launcher: no capability
        old120, _ = await self.player("Old120", BuildInfo(US_ELF, "aaaaaaaaaaaaaaaa", "1.2.0"))   # declares nothing
        same, _ = await self.player("Same", US)
        eu, _ = await self.player("EU", EU)
        self.assertTrue(compatible(old, same) and compatible(old120, same))   # the very same build id
        self.assertFalse(compatible(old, eu))
        self.assertFalse(compatible(old120, eu))
        with self.assertRaises(LobbyError):
            self.srv.create_match(old, eu, False, "challenge")

    async def test_rooms_check_every_member(self):
        host, _ = await self.player("Host", US)
        eu, _ = await self.player("EU", EU)
        old, _ = await self.player("Old", US, caps=())
        room = Room(host, "crossplay", False, size=8)
        self.srv._room_may_join(room, eu)                               # an EU Online player may join
        room.members.append(eu)
        self.assertEqual(room.public()["compat_group"], G + "-n4")
        with self.assertRaises(LobbyError):
            self.srv._room_may_join(room, old)                          # an old client is exact with the host only
        old_room = Room(old, "old", False, size=8)
        with self.assertRaises(LobbyError):
            self.srv._room_may_join(old_room, eu)


class LiveServerTest(unittest.TestCase):
    """Real server, real clients: the launcher's hello carries the declaration, match_start reaches both players."""

    def setUp(self):
        self.s = ServerThread().start()
        self.clients = []

    def tearDown(self):
        for c in self.clients:
            c.close()
        self.s.stop()

    def c(self, name, b):
        c = client(self.s, name, build=b, auto_ready=True)
        self.clients.append(c)
        return c

    def test_us_and_eu_online_get_a_match_with_one_build_id(self):
        a, b = self.c("Alice", US), self.c("Bob", EU)
        self.assertEqual(a.welcome["compat_group"], G + "-n4")
        self.assertEqual(b.welcome["compat_group"], G + "-n4")
        self.assertTrue(a.compatible({"build": EU.build_id, "compat_group": G + "-n4"}))
        self.assertFalse(a.compatible({"build": EU.build_id, "compat_group": G2 + "-n4"}))
        a.quick_match()
        b.quick_match()
        ta = expect(a, "match_start", 15)["ticket"]
        tb = expect(b, "match_start", 15)["ticket"]
        self.assertEqual(ta.match_id, tb.match_id)
        self.assertEqual(ta.build, tb.build)                            # T5_NET_BUILD is one id for both games
        self.assertEqual(ta.game_env()["T5_NET_BUILD"], tb.game_env()["T5_NET_BUILD"])
        self.assertIn(ta.build, (US.build_id, EU.build_id))

    def test_another_group_waits_in_the_queue(self):
        a, b = self.c("Alice", US), self.c("Bob", build(EU_ELF, "d" * 16, group=G2))
        a.quick_match()
        b.quick_match()
        self.assertIsNone(a.next_event(3, ("match_start",)))
        self.assertIsNone(b.next_event(0.5, ("match_start",)))


if __name__ == "__main__":
    unittest.main()
