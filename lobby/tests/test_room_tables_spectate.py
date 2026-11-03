"""Parallel table selection and spectator limits, using in-memory matches only."""
import asyncio
import os
import sys
import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from t5lobby import proto
from t5lobby.proto import LobbyError
from t5lobby.server.spectating import SpectateMixin, Stream
from t5lobby.spectate import ClientMixin


class Person:
    def __init__(self, name):
        self.id = self.name = name
        self.account_id = name
        self.friends = set()
        self.guest = False
        self.spec_allow = self.spec_ranked = True
        self.match = self.watching = None
        self.build_id = "test"
        self.conn = NS(ip=None, closed=False, pending=0)
        self.send = Mock()

    def brief(self):
        return {"id": self.id, "name": self.name}


class Harness(SpectateMixin):
    def __init__(self):
        self.rooms = {}
        self.streams = {}
        self.matches = {}
        self.recent = {}
        self.counters = {}
        self.dirty = False
        self.cfg = NS(max_spectators=2, max_streams=8, spec_reserved_streams=1,
                      spec_guest_share=0.5, spectate_rate_kb=64)
        self._can = lambda p, cap: True
        self._is_blocked = lambda a, b: False
        self._count = Mock()
        self.note = Mock()
        players = [Person(n) for n in "ABCD"]
        self.viewer = Person("Viewer")
        self.room = NS(id="room", name="Tables", mode="tables", match=None, set=None,
                       private=False, members=players + [self.viewer], watch=False)
        self.rooms[self.room.id] = self.room
        self.room.tables = []
        for i in range(2):
            table = NS(id=i + 1, room=self.room, match=None, set=None)
            match = NS(id=f"m{i}", stream_id=f"m{i}", room=self.room, table=table,
                       players=players[2 * i:2 * i + 2], state="playing", set=None,
                       ranked=False, build_id="test", started=1)
            table.match = match
            self.room.tables.append(table)
            self.matches[match.id] = match


class RoomTableSpectateTest(unittest.TestCase):
    def setUp(self):
        self.srv = Harness()
        self.r = self.srv.room

    def test_room_watch_requires_exact_table_and_never_falls_back(self):
        for table in self.r.tables:
            self.assertIs(self.srv._spec_target(self.srv.viewer, {"room": "room", "table": table.id}),
                          table.match)
        for selector in (None, True, False, "1", 1.0, 0, 3, [], {}):
            with self.subTest(selector=selector), self.assertRaises(LobbyError) as cm:
                self.srv._spec_target(self.srv.viewer, {"room": "room", "table": selector})
            self.assertEqual(cm.exception.code, proto.E_BAD_REQUEST)
        self.r.tables[0].match = None
        self.assertIsNone(self.srv._spec_target(self.srv.viewer, {"room": "room", "table": 1}))
        self.assertIsNone(self.srv._spec_room_match(self.r))

    def test_public_watch_flag_checks_every_table(self):
        self.r.tables[0].match.state = "ready"
        self.srv._spec_refresh_rooms()
        self.assertTrue(self.r.watch)
        self.assertEqual([table.watch for table in self.r.tables], [False, True])
        self.r.tables[1].match.state = "done"
        self.srv._spec_refresh_rooms()
        self.assertFalse(self.r.watch)
        self.assertEqual([table.watch for table in self.r.tables], [False, False])

    def test_private_tables_never_advertise_public_watch_flags(self):
        self.srv._spec_refresh_rooms()
        self.assertEqual([table.watch for table in self.r.tables], [True, True])
        self.r.private = True
        self.srv._spec_refresh_rooms()
        self.assertFalse(self.r.watch)
        self.assertEqual([table.watch for table in self.r.tables], [False, False])
        self.assertIsNone(self.srv._spec_refusal(self.srv.viewer, self.r.tables[0].match))

    def test_gap_stream_stays_with_selected_table(self):
        table = self.r.tables[0]
        m = table.match
        m.state = "done"
        m.set = NS(state="active")
        table.match = None
        table.set = NS(last=m)
        st = Stream(m.stream_id, m, m.players[0], 64, 1)
        self.srv.streams[st.id] = st
        self.assertIs(self.srv._spec_room_match(self.r, table), m)
        self.assertIs(self.srv._spec_room_match(self.r, self.r.tables[1]), self.r.tables[1].match)
        st.ended = "over"
        self.assertIsNone(self.srv._spec_room_match(self.r, table))

    def test_private_room_checks_actual_membership_for_each_table(self):
        self.r.private = True
        outsider = Person("Outsider")
        for table in self.r.tables:
            self.assertIsNone(self.srv._spec_refusal(self.srv.viewer, table.match))
            why = self.srv._spec_refusal(outsider, table.match)
            self.assertEqual(why.code, proto.E_NOT_ALLOWED)

    def test_watch_creates_independent_streams_and_returns_table(self):
        async def session():
            other = Person("Other")
            self.r.members.append(other)
            first = await self.srv.h_watch(NS(player=self.srv.viewer), {"room": "room", "table": 1})
            second = await self.srv.h_watch(NS(player=other), {"room": "room", "table": 2})
            self.assertEqual((first["table"], second["table"]), (1, 2))
            self.assertNotEqual(first["stream"], second["stream"])
            self.assertIs(self.srv.viewer.watching.match, self.r.tables[0].match)
            self.assertIs(other.watching.match, self.r.tables[1].match)
            self.assertEqual(len(self.srv.streams), 2)
            self.srv._spec_end(self.srv.viewer.watching, "over", flush=False)
            self.assertIsNone(self.srv.viewer.watching)
            self.assertIsNotNone(other.watching)
        asyncio.run(session())

    def test_server_stream_limit_is_shared_between_tables(self):
        async def session():
            self.srv.cfg.max_streams = 1
            await self.srv.h_watch(NS(player=self.srv.viewer), {"room": "room", "table": 1})
            why = self.srv._spec_refusal(Person("Other"), self.r.tables[1].match)
            self.assertEqual(why.code, proto.E_FULL)
        asyncio.run(session())

    def test_full_table_does_not_use_another_tables_spectator_places(self):
        table = self.r.tables[0]
        st = Stream(table.match.stream_id, table.match, table.match.players[0], 64, 1)
        st.viewers = {Person("One"): 0, Person("Two"): 0}
        self.srv.streams[st.id] = st
        outsider = Person("Outsider")
        self.assertEqual(self.srv._spec_refusal(outsider, table.match).code, proto.E_FULL)
        self.assertIsNone(self.srv._spec_refusal(outsider, self.r.tables[1].match))

    def test_classic_room_watch_keeps_legacy_shape(self):
        self.r.mode = "line"
        self.r.match = self.r.tables[0].match
        self.assertIs(self.srv._spec_target(self.srv.viewer, {"room": "room"}), self.r.match)


class WatchClientTest(unittest.TestCase):
    def test_optional_table_selector_is_sent_only_for_room(self):
        class Client(ClientMixin):
            request_timeout = 3

            def _run(self, coro, timeout):
                return asyncio.run(coro)

            async def _request(self, msg):
                return msg

        c = Client()
        c._spec_init(True)
        self.assertEqual(ClientMixin.watch(c, room="room", table=2),
                         {"t": "watch", "room": "room", "table": 2})
        self.assertEqual(ClientMixin.watch(c, room="room"), {"t": "watch", "room": "room"})
        self.assertEqual(ClientMixin.watch(c, name="A", table=2), {"t": "watch", "name": "A"})


if __name__ == "__main__":
    unittest.main()
