"""Offline group policy and matchmaking regression tests; no sockets or game required."""
import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

import util  # noqa: F401
from t5lobby.buildid import BuildInfo
from t5lobby.client import LobbyClient
from t5lobby.compatibility import BuildGroups, CAP, REGIONS, compatible
from t5lobby.proto import LobbyError
from t5lobby import proto
from t5lobby.server import Config, LobbyServer
from t5lobby.server.lobby import Player
from t5lobby.server.rooms import Room


US = BuildInfo("be80165b84e30b6334baa6d6331b9db4ffd5a6a4", "offline-fixture-us")
EU = BuildInfo("a26bc6e037e5a8faf40250849acfa8a40d027fff", "offline-fixture-eu")
SPEC = json.dumps({"fixture-only": {"net": 4, "builds": [US.build_id, EU.build_id]}})


class PolicyTest(unittest.TestCase):
    def test_group_is_server_allowlisted_and_capability_gated(self):
        groups = BuildGroups(SPEC)
        self.assertEqual(groups.group(US.build_id, 4, [CAP]), "fixture-only")
        self.assertEqual(groups.group(EU.build_id, 4, [CAP]), "fixture-only")
        self.assertEqual(groups.group(EU.build_id, 4, []), "")
        self.assertEqual(groups.group(EU.build_id, 3, [CAP]), "")
        self.assertEqual(groups.group("0" * 16, 4, [CAP]), "")
        self.assertEqual(BuildGroups().group(US.build_id, 4, [CAP]), "")

    def test_invalid_or_overlapping_policy_is_rejected(self):
        for spec in ('[]', '{"bad group":{}}', '{"x":{"net":true,"builds":["0000000000000000"]}}',
                     '{"x":{"net":4,"builds":["not-an-id"]}}',
                     '{"x":{"net":4,"builds":["0000000000000000"]},'
                     '"y":{"net":4,"builds":["0000000000000000"]}}'):
            with self.subTest(spec=spec), self.assertRaises(ValueError):
                BuildGroups(spec)

    def test_region_uses_program_fingerprint(self):
        self.assertEqual(REGIONS[US.elf_sha1], "US")
        self.assertEqual(REGIONS[EU.elf_sha1], "EU")

    def test_client_old_server_and_old_member_fall_back_to_exact(self):
        c = LobbyClient("127.0.0.1:1", US)
        c.welcome = {"caps": [CAP], "compat_group": "fixture-only"}
        self.assertTrue(c.compatible({"build": EU.build_id, "compat_group": "fixture-only"}))
        self.assertFalse(c.compatible({"build": EU.build_id}))
        c.welcome = {"caps": []}
        self.assertFalse(c.compatible({"build": EU.build_id, "compat_group": "fixture-only"}))
        self.assertTrue(c.compatible({"build": US.build_id}))


class MatchmakingTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.srv = LobbyServer(Config(**util.FAST, compat_groups=SPEC))

    async def asyncTearDown(self):
        self.srv.store.close()

    def player(self, name, build, cap=True):
        conn = SimpleNamespace(build_id=build.build_id, release="fixture", ip="127.0.0.1", caps={CAP} if cap else set(),
                               sent=[])
        conn.compat_group = self.srv.build_groups.group(build.build_id, build.net, conn.caps)
        conn.region = REGIONS[build.elf_sha1]
        conn.send = conn.sent.append
        p = Player(conn, name, guest=True)
        conn.player = p
        self.srv.players[p.id] = p
        return p

    async def test_hello_ignores_client_claimed_id_group_and_region(self):
        conn = SimpleNamespace(player=None, ip="127.0.0.1",
                               writer=SimpleNamespace(get_extra_info=lambda _key: None))
        build = dict(US.as_wire(), id=EU.build_id, compat_group="forged", region="EU")
        welcome = await self.srv.h_hello(conn, {"proto": proto.PROTO_VERSION, "build": build, "caps": [CAP]})
        self.assertEqual(welcome["build"], US.build_id)
        self.assertEqual(welcome["compat_group"], "fixture-only")
        self.assertEqual(welcome["region"], "US")
        unknown = BuildInfo(US.elf_sha1, "unapproved-fixture")
        await self.srv.h_hello(conn, {"proto": proto.PROTO_VERSION,
                                     "build": dict(unknown.as_wire(), compat_group="fixture-only"), "caps": [CAP]})
        self.assertEqual(conn.compat_group, "")

    async def test_client_refuses_mismatched_continuation_before_emitting_it(self):
        c = LobbyClient("127.0.0.1:1", US)
        c.welcome = {"caps": [CAP], "compat_group": "fixture-only"}
        c.match = {"match": "mfixture", "state": "ready"}
        c._send = AsyncMock()
        events = []
        c._emit = events.append
        await c._on_match_start({"match": "mfixture", "build": EU.build_id,
                                 "compat_group": "other", "continue": True})
        self.assertEqual(c.match["state"], "ready")
        self.assertEqual(events[0]["code"], "version_mismatch")
        c._send.assert_awaited_once_with({"t": "leave_match", "match": "mfixture"})

    async def test_approved_cross_build_queue_and_match_validation(self):
        a, b = self.player("A", US), self.player("B", EU)
        self.srv._enqueue(a, "quick", 0)
        self.srv._enqueue(b, "quick", 0)
        made = self.srv.match_queue()
        self.assertEqual(len(made), 1)
        self.assertEqual(a.match.compat_group, "fixture-only")
        self.assertEqual(a.public()["region"], "US")
        self.assertEqual(b.public()["region"], "EU")
        self.srv.cancel_match(a.match, "test_done")

    async def test_old_clients_still_pair_exactly_and_cannot_cross(self):
        old = self.player("Old", US, cap=False)
        same = self.player("Same", US)
        eu = self.player("EU", EU)
        self.assertTrue(compatible(old, same))
        self.assertFalse(compatible(old, eu))
        with self.assertRaises(LobbyError):
            self.srv.create_match(old, eu, False, "challenge")
        with self.assertRaises(LobbyError):
            await self.srv.h_challenge(old.conn, {"player": eu.id})

    async def test_room_cannot_mix_an_old_member_with_other_builds(self):
        host, old, eu = self.player("Host", US), self.player("Old", US, cap=False), self.player("EU", EU)
        room = Room(host, "fixture", False, size=8)
        self.srv._room_may_join(room, eu)
        room.members.append(old)
        self.assertEqual(room.public()["compat_group"], "")
        with self.assertRaises(LobbyError):
            self.srv._room_may_join(room, eu)

    async def test_group_membership_does_not_bypass_table_capability_or_lose_metadata(self):
        host, eu = self.player("Host", US), self.player("EU", EU)
        host.conn.caps.update({"private_rooms", "room_tables", "sets", "casual_sets"})
        room = Room(host, "fixture", False, size=4, first_to=3, mode="tables")
        # An approved simulation group does not grant unrelated launcher features.
        with self.assertRaisesRegex(LobbyError, "simultaneous room tables"):
            self.srv._room_may_join(room, eu)
        eu.conn.caps.update({"private_rooms", "room_tables", "sets", "casual_sets", "input_delay8"})
        self.srv._room_may_join(room, eu)
        room.members.append(eu)
        public = room.public()
        self.assertEqual(public["compat_group"], "fixture-only")
        self.assertEqual(public["mode"], "tables")
        self.assertEqual(public["first_to"], 3)
        self.assertEqual(len(public["tables"]), 2)
        self.assertTrue(eu.public()["input_delay8"])
        self.assertIn("badge", eu.public())
        self.assertEqual(eu.brief()["region"], "EU")
