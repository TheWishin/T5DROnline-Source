"""Parallel table match/set ownership without sockets, game processes or a running server."""
import asyncio
import collections
import os
import sys
import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from t5lobby import proto
from t5lobby.server.config import Config
from t5lobby.server.lobby import CAPS, FEATURES, LobbyServer


def player(name):
    p = NS(id=name, name=name, char="jin", account_id=None, guest=True,
           build_id="test", online=True, conn=NS(caps={"sets", "casual_sets", "room_tables"}),
           set=None, match=None, room=None, status="room", record=[0, 0, 0])
    p.brief = lambda: {"id": name, "name": name}
    p.public = p.brief
    p.send = Mock()
    return p


def server():
    s = object.__new__(LobbyServer)
    s.cfg = Config()
    s.matches, s.recent, s.rooms, s.invites, s.challenges = {}, {}, {}, {}, {}
    s.counters = collections.Counter()
    s.store = Mock()
    s.tours = Mock()
    for name in ("_rules_new_match", "_spec_new_match", "_speed_notice", "_timer", "note", "_count",
                 "_release", "_cancel_timers", "_save", "_set_schedule_next",
                 "_room_match_over", "_room_match_cancelled", "_room_set_over"):
        setattr(s, name, Mock())
    s._est_ping = lambda a, b: (1, True, "direct")
    s._ping_info = Mock(return_value={"known": True})
    s._ping_seen_by = lambda ping, blind: ping
    s._rules_found = lambda m, side: {}
    s._rules_finish = lambda m, *args: args
    s._picked = Mock(return_value=None)
    return s


class ParallelMatchLifecycleTest(unittest.TestCase):
    def setUp(self):
        self.s = server()
        self.players = [player(n) for n in "ABCD"]
        # Real rooms inherit their owner's build for invite compatibility checks.
        self.room = NS(id="r1", training=False, ranked=False, community=True, match=None, set=None,
                       build_id=self.players[0].build_id)
        self.tables = [NS(id=n, room=self.room, match=None, set=None) for n in (1, 2)]
        self.s.rooms[self.room.id] = self.room
        self.room.members = self.players
        for p in self.players:
            p.room = self.room

    def match(self, number):
        a, b = self.players[2 * number:2 * number + 2]
        return self.s.create_match(a, b, False, "room", room=self.room,
                                   table=self.tables[number], first_to=3)

    def finish(self, m):
        m.chars, m.stage, m.path = ["jin", "paul"], "s20", "direct"
        with patch("t5lobby.server.lobby.asyncio.get_running_loop", return_value=Mock()):
            self.s._finish(m, "confirmed", 0, [3, 1])

    def test_feature_and_pairing_use_existing_state_rate_limit(self):
        self.assertIn("room_tables", CAPS)
        self.assertIn("room_tables", FEATURES)
        self.assertIn("room_pair", LobbyServer.STATE)

    def test_two_matches_have_disjoint_connections_and_sets(self):
        m1, m2 = self.match(0), self.match(1)
        self.assertIs(m1.room, self.room)
        self.assertIs(m2.room, self.room)
        self.assertIs(self.tables[0].match, m1)
        self.assertIs(self.tables[1].match, m2)
        self.assertIs(self.tables[0].set, m1.set)
        self.assertIs(self.tables[1].set, m2.set)
        self.assertIs(m1.set.table, self.tables[0])
        self.assertIs(m2.set.table, self.tables[1])
        self.assertIsNone(self.room.match)
        self.assertIsNone(self.room.set)
        self.assertIsNot(m1.set, m2.set)
        self.assertEqual(m1.set.first_to, 3)
        self.assertEqual(m2.set.first_to, 3)
        self.assertTrue(set(m1.tokens).isdisjoint(m2.tokens))
        self.assertNotEqual(m1.key, m2.key)
        self.assertNotEqual(m1.tag, m2.tag)
        self.assertEqual(len(self.s.matches), 2)

    def test_cancellation_releases_only_its_table(self):
        m1, m2 = self.match(0), self.match(1)
        self.s.cancel_match(m1, "declined", by=m1.players[0])
        self.assertIsNone(self.tables[0].match)
        self.assertEqual(m1.set.state, "ended")
        self.assertIs(self.tables[1].match, m2)
        self.assertEqual(m2.set.state, "active")
        self.assertIs(m2.players[0].match, m2)
        self.assertEqual(m2.state, "ready")
        self.assertNotIn(m1.id, self.s.matches)
        self.assertIn(m2.id, self.s.matches)
        self.s._release.assert_called_once_with(m1)
        self.s._room_match_cancelled.assert_called_once_with(self.room, m1, "declined", m1.players[0])

    def test_finishing_one_game_keeps_other_table_and_per_table_score(self):
        m1, m2 = self.match(0), self.match(1)
        self.finish(m1)
        self.assertIsNone(self.tables[0].match)
        self.assertIs(self.tables[0].set, m1.set)
        self.assertEqual(m1.set.score(), [1, 0])
        self.assertEqual(m2.set.score(), [0, 0])
        self.assertIs(self.tables[1].match, m2)
        self.assertEqual(m2.players[0].record, [0, 0, 0])
        self.assertEqual(m1.players[0].record, [1, 0, 0])
        self.assertIsNone(self.room.match)

    def test_next_set_game_inherits_its_slot_without_clobbering_room(self):
        m1, m2 = self.match(0), self.match(1)
        self.finish(m1)
        # This exercises create_match's real inheritance and attachment through the
        # actual automatic-set entry point; NAT setup alone is replaced by a mock.
        self.s._start_nat = Mock()
        self.s._set_next(m1.set)
        next_game = self.tables[0].match
        self.assertIsNot(next_game, m1)
        self.assertIs(next_game.table, self.tables[0])
        self.assertIs(next_game.room, self.room)
        self.assertIs(next_game.set, m1.set)
        self.assertEqual(next_game.set.score(), [1, 0])
        self.assertIs(next_game.set.current, next_game)
        self.assertIs(self.tables[1].match, m2)
        self.assertIsNone(self.room.match)
        self.assertIsNone(self.room.set)

    def test_between_game_leave_runs_table_callback_while_another_table_plays(self):
        m1, m2 = self.match(0), self.match(1)
        self.finish(m1)
        # A legacy room-wide pointer must not decide if this table's set ended.
        self.room.match = m2
        self.s._end_set(m1.set, "left", by=m1.players[0])
        self.assertEqual(m1.set.state, "ended")
        self.assertIs(self.tables[1].match, m2)
        self.s._room_set_over.assert_called_once_with(self.room, m1.set, "void", None)

    def test_legacy_room_keeps_room_level_set_ownership(self):
        a, b = self.players[:2]
        m = self.s.create_match(a, b, False, "room", room=self.room, first_to=2)
        self.assertIsNone(m.table)
        self.assertIsNone(m.set.table)
        self.assertIs(self.room.set, m.set)

    def invite_players(self):
        host, friend = self.players[:2]
        host.account_id, friend.account_id = 1, 2
        host.friends, friend.friends = {2}, {1}
        friend.status = "idle"
        friend.room = None
        friend.conn.caps = {"friends"}
        friend.conn.closed = False
        self.room.members = [host]
        self.room.size, self.room.mode, self.room.kicked = 4, "tables", {}
        self.s.draining = False
        self.s._is_blocked = lambda a, b: False
        self.s._refuse_draining = Mock()
        self.s._abandon_set = Mock()
        self.s._end_invite = Mock()
        self.s._leave_queue = Mock()
        return host, friend

    def test_old_friend_is_not_offered_an_unusable_room_invite(self):
        host, friend = self.invite_players()
        self.s.by_name = {friend.name.lower(): friend}
        with self.assertRaises(proto.LobbyError) as raised:
            asyncio.run(self.s.h_invite(NS(player=host), {"name": friend.name, "kind": "room"}))
        self.assertEqual(raised.exception.code, proto.E_NOT_ALLOWED)
        self.assertIn("update", raised.exception.msg)
        self.assertEqual(self.s.invites, {})
        friend.send.assert_not_called()

    def test_stale_invite_cannot_bypass_table_cap_or_mutate_player_state(self):
        host, friend = self.invite_players()
        invite = NS(id="i1", src=host, dst=friend, kind="room", room=self.room)
        self.s.invites[invite.id] = invite
        with self.assertRaises(proto.LobbyError) as raised:
            asyncio.run(self.s.h_invite_answer(NS(player=friend), {"invite": invite.id, "accept": True}))
        self.assertEqual(raised.exception.code, proto.E_NOT_ALLOWED)
        self.assertIn("update", raised.exception.msg)
        self.s._abandon_set.assert_not_called()
        self.s._end_invite.assert_not_called()
        self.s._leave_queue.assert_not_called()
        self.assertEqual(self.room.members, [host])
        self.assertIsNone(friend.room)
        self.assertEqual(friend.status, "idle")


if __name__ == "__main__":
    unittest.main()
