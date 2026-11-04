"""Independent room tables, without sockets, a game, or starting a lobby server."""
import asyncio
import os
import sys
import time
import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from t5lobby import proto
from t5lobby.server.mmfilters import MatchFiltersMixin
from t5lobby.server.rooms import Room, RoomsMixin
from t5lobby.server.rematch import RematchMixin


CAPS = {"private_rooms", "room_tables", "sets", "casual_sets", "spectate"}


def player(name):
    p = NS(id=name, name=name, build_id="test", online=True, match=None, room=None, set=None,
           status="room", guest=True, watching=None, conn=NS(caps=CAPS, closed=False))
    p.brief = lambda: {"id": name, "name": name}
    p.send = Mock()
    return p


class Harness(RoomsMixin, RematchMixin):
    _room_tags = MatchFiltersMixin._room_tags   # 1.2.1: room_create reads the area / language tags (mmfilters.py)
    def __init__(self, count=6, size=6):
        self.players = {n: player(n) for n in "ABCDEFGH"[:count]}
        self.r = Room(self.players["A"], "Tables", False, size, first_to=3, mode="tables")
        self.r.members = list(self.players.values())
        self.r.line = list(self.r.members)
        for p in self.r.members:
            p.room = self.r
            p.conn.player = p
        self.rooms = {self.r.id: self.r}
        self.cfg = NS(room_next_seconds=8, room_max_size=8)
        self.draining = False
        self.dirty = False
        self.invites = {}
        self._set_free = Mock()
        self._is_blocked = lambda a, b: False
        self._casual_sides = lambda a, b: (a, b)
        self._spec_room_match = lambda r, table=None: None
        self._can = lambda p, cap: True
        self._refuse_draining = Mock()
        self._room_training_opt = lambda conn, msg, ranked: bool(msg.get("training"))
        self._abandon_set = Mock()
        self._check_speed = Mock()
        self._block_key = lambda p: p.id
        self._room_training_check = Mock()
        self._end_set = Mock()
        self._decline_recent = Mock()
        self.create_match = Mock(side_effect=self.create)

    def create(self, a, b, **kw):
        table = kw["table"]
        gs = NS(casual=True, state="active", players=[a, b], current=None, rated=False,
                table=table, matches=[], outcome=None, info=lambda: {"first_to": kw["first_to"]})
        m = NS(id="m" + str(table.id), players=[a, b], state="ready", room=kw["room"], table=table, set=gs)
        gs.current = m
        gs.matches = [m]
        table.set = gs
        for p in (a, b):
            p.match, p.set, p.status = m, gs, "match"
        return m

    def fire(self, table):
        if table.next_timer is not None:
            table.next_timer.cancel()
        self._room_table_next(table)

    def close(self):
        for table in self.r.tables:
            if table.next_timer is not None:
                table.next_timer.cancel()


class TableCoreTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.srv = Harness()
        self.r = self.srv.r
        self.addCleanup(self.srv.close)

    async def test_all_free_pairs_start_as_separate_normal_matches(self):
        self.srv._room_schedule(self.r, 1)
        self.assertEqual([[q.id for q in t.pair] for t in self.r.tables], [["A", "B"], ["C", "D"], ["E", "F"]])
        for table in self.r.tables:
            self.srv.fire(table)
        self.assertEqual(self.srv.create_match.call_count, 3)
        self.assertEqual(len({t.match.id for t in self.r.tables}), 3)
        self.assertIsNone(self.r.match)
        self.assertIsNone(self.r.set)
        for call in self.srv.create_match.call_args_list:
            self.assertIs(call.kwargs["room"], self.r)
            self.assertEqual(call.kwargs["first_to"], 3)
            self.assertFalse(call.kwargs["ranked"])

    async def test_drain_cancels_reservation_and_explicit_resume_can_schedule_it_again(self):
        self.srv._room_schedule(self.r, 1)
        table = self.r.tables[0]
        self.srv.draining = True
        self.srv.fire(table)
        self.assertEqual(table.pair, [])
        self.assertIsNone(table.next_timer)
        self.srv.create_match.assert_not_called()
        self.srv.draining = False
        self.srv._room_line(self.r, self.r.owner, True)
        self.assertEqual([q.id for q in table.pair], ["A", "B"])
        self.assertIsNotNone(table.next_timer)
        self.srv.fire(table)
        self.assertIsNotNone(table.match)

    async def test_active_set_keeps_only_its_table_between_games(self):
        self.srv._room_schedule(self.r, 1)
        table = self.r.tables[0]
        self.srv.fire(table)
        m = table.match
        table.match = None
        m.set.current = None
        for q in m.players:
            q.match, q.status = None, "room"
        self.srv._room_match_over(self.r, m, "confirmed", 0)
        self.srv._room_schedule(self.r)
        self.assertEqual([q.id for q in table.pair], ["A", "B"])
        self.assertIsNone(table.next_timer)
        self.assertEqual([q.id for q in self.r.tables[1].pair], ["C", "D"])
        self.assertFalse(self.srv._room_table_free(self.r, m.players[0]))
        self.assertEqual(self.r.status(), "playing")

    async def test_host_rearranges_pending_pairs_atomically(self):
        self.srv._room_schedule(self.r, 1)
        reply = await self.srv.h_room_pair(self.r.owner.conn, {"table": 1, "players": ["A", "C"]})
        self.assertEqual(reply["room"]["tables"][0]["players"], ["A", "C"])
        pairs = [q.id for t in self.r.tables for q in t.pair]
        self.assertEqual(len(pairs), len(set(pairs)))
        self.assertEqual(sorted(pairs), list("ABCDEF"))

    async def test_host_cannot_steal_a_running_table_or_pair_an_away_player(self):
        self.srv._room_schedule(self.r, 1)
        self.srv.fire(self.r.tables[0])
        before = [list(t.pair) for t in self.r.tables]
        with self.assertRaises(proto.LobbyError):
            await self.srv.h_room_pair(self.r.owner.conn, {"table": 2, "players": ["A", "C"]})
        self.assertEqual(before, [t.pair for t in self.r.tables])
        self.srv._room_line(self.r, self.srv.players["E"], False)
        with self.assertRaises(proto.LobbyError):
            await self.srv.h_room_pair(self.r.owner.conn, {"table": 3, "players": ["E", "F"]})

    async def test_only_host_can_pair_and_ids_are_strict(self):
        with self.assertRaises(proto.LobbyError):
            await self.srv.h_room_pair(self.srv.players["B"].conn, {"table": 1, "players": ["C", "D"]})
        for table in (None, True, "1", 0, 4):
            with self.subTest(table=table), self.assertRaises(proto.LobbyError):
                await self.srv.h_room_pair(self.r.owner.conn, {"table": table, "players": ["C", "D"]})
        for pair in (["C", "C"], ["C"], ["C", "Missing"], "CD", [True, "C"]):
            with self.subTest(pair=pair), self.assertRaises(proto.LobbyError):
                await self.srv.h_room_pair(self.r.owner.conn, {"table": 1, "players": pair})

    async def test_sit_out_clears_reservation_and_does_not_move_another_match(self):
        self.srv._room_schedule(self.r, 1)
        self.srv.fire(self.r.tables[1])
        other = self.r.tables[1].match
        self.srv._room_line(self.r, self.srv.players["A"], False)
        self.assertNotIn(self.srv.players["A"], [q for t in self.r.tables for q in t.pair])
        self.assertIs(self.r.tables[1].match, other)
        self.srv._room_line(self.r, self.srv.players["A"], True)
        self.assertIn(self.srv.players["A"], [q for t in self.r.tables for q in t.pair])

    async def test_setup_capacity_failure_sits_pair_out_instead_of_retrying(self):
        self.srv._room_schedule(self.r, 1)
        self.srv.fire(self.r.tables[0])
        table = self.r.tables[0]
        m = table.match
        table.match = None
        m.set.state = "ended"
        for q in m.players:
            q.match, q.status = None, "room"
        self.srv._room_match_cancelled(self.r, m, "relay_full", None)
        self.assertFalse(any(q in self.r.line for q in m.players))
        self.assertIsNone(table.next_timer)
        self.assertEqual(table.pair, [])
        for q in m.players:
            self.assertEqual(q.send.call_args.args[0]["code"], "room_away")

    async def test_whole_set_releases_only_its_table_once(self):
        self.srv._room_schedule(self.r, 1)
        for table in self.r.tables:
            self.srv.fire(table)
        table, other = self.r.tables[:2]
        m = table.match
        table.match = None
        m.set.state = "ended"
        m.set.current = None
        for q in m.players:
            q.match, q.status = None, "room"
        self.srv._room_set_over(self.r, m.set, "confirmed", m.players[0])
        order = list(self.r.line)
        self.srv._room_set_over(self.r, m.set, "confirmed", m.players[0])
        self.assertEqual(order, self.r.line)
        self.assertEqual([q.id for q in self.r.line][-2:], ["A", "B"])
        self.assertEqual([q.id for q in other.match.players], ["C", "D"])
        self.assertIsNotNone(table.next_timer)
        self.assertIsNone(table.set)  # the next pair must not display the previous pair's score

    async def test_single_game_capability_fallback_closes_legacy_set_before_refilling(self):
        self.srv._room_schedule(self.r, 1)
        table = self.r.tables[0]
        self.srv.fire(table)
        m = table.match
        table.match = None
        m.set.casual = False
        m.set.current = None
        for q in m.players:
            q.match, q.status = None, "room"
        self.srv._end_set.side_effect = lambda gs, reason: setattr(gs, "state", "ended")
        self.srv._room_match_over(self.r, m, "confirmed", 0)
        self.srv._end_set.assert_called_once_with(m.set, "expired")
        self.assertIsNotNone(table.next_timer)
        self.assertEqual([q.id for q in table.pair], ["A", "B"])

    async def test_table_count_uses_room_limit_including_odd_sizes(self):
        for size in (2, 3, 4, 7, 8):
            r = Room(self.r.owner, "Bounded", False, size, mode="tables")
            self.assertEqual([t.id for t in r.tables], list(range(1, size // 2 + 1)))
            self.assertTrue(r.community)

    async def test_old_client_join_and_ranked_training_create_are_refused(self):
        old = player("Old")
        old.status = "idle"
        old.conn.caps = {"private_rooms"}
        with self.assertRaisesRegex(proto.LobbyError, "newer launcher"):
            self.srv._room_may_join(self.r, old)
        for extra in ({"ranked": True}, {"training": True}):
            host = player("Host")
            host.status = "idle"
            host.conn.player = host
            with self.assertRaises(proto.LobbyError):
                await self.srv.h_room_create(host.conn, {"mode": "tables", **extra})

    async def test_public_and_member_views_expose_tables_without_lock_secrets(self):
        self.srv._room_schedule(self.r, 1)
        self.srv.fire(self.r.tables[0])
        self.r.lock, self.r.secret, self.r.code_key = "code", "secret-password", b"secret-code"
        self.r.tables[0].watch = True
        public = self.r.public()
        view = self.srv._room_view(self.r, self.srv.players["F"])
        self.assertIsInstance(public["tables"], list)
        self.assertFalse(public["tables"][0]["watch"])
        self.assertEqual(view["tables"][0]["set"]["first_to"], 3)
        self.assertEqual(view["playing"], ["A", "B"])
        self.assertNotIn("secret-password", str(public) + str(view))
        self.assertNotIn("secret-code", str(public) + str(view))

    async def test_swapped_match_sides_keep_names_aligned_with_set_score(self):
        self.srv._casual_sides = lambda a, b: (b, a)
        self.srv._room_schedule(self.r, 1)
        table = self.r.tables[0]
        self.srv.fire(table)
        table.set.info = lambda: {"first_to": 3, "wins": [1, 0]}
        view = self.srv._room_view(self.r, self.srv.players["F"])
        self.assertEqual(view["tables"][0]["players"], ["B", "A"])
        self.assertEqual(view["tables"][0]["set"]["wins"], [1, 0])
        self.assertEqual(self.r.public()["tables"][0]["players"], ["B", "A"])
        # The same ordering survives the countdown between games of the FT set.
        table.match = None
        table.set.current = None
        view = self.srv._room_view(self.r, self.srv.players["F"])
        self.assertEqual(view["tables"][0]["players"], ["B", "A"])
        self.assertEqual(view["tables"][0]["set"]["wins"], [1, 0])

    async def test_private_room_kick_clears_idle_reservation_and_preserves_other_match(self):
        self.r.lock = "code"
        self.srv._count = Mock()
        self.srv._room_schedule(self.r, 1)
        self.srv.fire(self.r.tables[0])
        other = self.r.tables[0].match
        removed = self.srv.players["E"]
        self.assertIn(removed, self.r.tables[2].pair)
        await self.srv.h_room_kick(self.r.owner.conn, {"player": removed.id})
        self.assertNotIn(removed, self.r.members)
        self.assertNotIn(removed, [q for t in self.r.tables for q in t.pair])
        self.assertIs(self.r.tables[0].match, other)
        self.assertEqual(removed.send.call_args.args[0]["code"], "room_kicked")
        with self.assertRaisesRegex(proto.LobbyError, "removed you"):
            self.srv._room_may_join(self.r, removed)

    async def test_password_bar_rejects_guesses_before_budget_and_preserves_matches(self):
        self.r.lock = "password"
        self.srv._count = Mock()
        self.srv.room_guess_room = Mock()
        self.srv.room_guess_room.peek_ok.return_value = True
        self.srv.room_guess_lane = Mock()
        self.srv._room_schedule(self.r, 1)
        self.srv.fire(self.r.tables[0])
        other = self.r.tables[0].match
        network = "203.0.113.7"
        self.r.wrong.append((time.monotonic(), network))
        reply = await self.srv.h_room_bar(self.r.owner.conn, {})
        self.assertEqual(reply["barred"], 1)
        peek_count = self.srv.room_guess_room.peek_ok.call_count
        with self.assertRaisesRegex(proto.LobbyError, "turned away"):
            self.srv._guess_room_key(self.r, network)
        self.assertEqual(self.srv.room_guess_room.peek_ok.call_count, peek_count)
        self.srv.room_guess_room.take.assert_not_called()
        self.srv.room_guess_lane.take.assert_not_called()
        self.assertIs(self.r.tables[0].match, other)

    async def test_becoming_private_removes_outsiders_from_every_table_stream(self):
        self.srv._room_schedule(self.r, 1)
        for table in self.r.tables[:2]:
            self.srv.fire(table)
        outsider = player("Outsider")
        member = self.srv.players["F"]
        self.srv.streams = {str(t.id): NS(match=t.match, viewers=[outsider, member])
                            for t in self.r.tables[:2]}
        self.srv._spec_unwatch = Mock()
        self.r.lock = "code"
        self.srv._room_spec_check(self.r)
        self.assertEqual(self.srv._spec_unwatch.call_count, 2)
        for call in self.srv._spec_unwatch.call_args_list:
            self.assertIs(call.args[0], outsider)
            self.assertEqual(call.args[1], "not_allowed")

    async def test_room_watch_action_tracks_personalized_table_visibility(self):
        self.srv._room_schedule(self.r, 1)
        self.srv.fire(self.r.tables[0])
        match = self.r.tables[0].match
        self.srv._spec_room_match = lambda r, table=None: match if table is self.r.tables[0] else None
        self.srv._spec_refusal = lambda viewer, m: None
        view = self.srv._room_view(self.r, self.srv.players["F"])
        self.assertTrue(view["watch"])
        self.assertTrue(view["tables"][0]["watch"])
        self.assertFalse(self.srv._room_view(self.r, self.srv.players["A"])["watch"])

    async def test_blocked_pair_is_skipped_for_auto_and_rejected_for_host(self):
        self.srv._is_blocked = lambda a, b: {a.id, b.id} == {"A", "B"}
        self.srv._room_schedule(self.r, 1)
        self.assertEqual([q.id for q in self.r.tables[0].pair], ["A", "C"])
        with self.assertRaises(proto.LobbyError):
            await self.srv.h_room_pair(self.r.owner.conn, {"table": 1, "players": ["A", "B"]})


if __name__ == "__main__":
    unittest.main()
