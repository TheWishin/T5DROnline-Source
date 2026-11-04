"""Casual first-to rooms, with in-memory players and no server sockets or game process."""
import asyncio
import os
import sys
import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from t5lobby.proto import LobbyError
from t5lobby.server.lobby import LobbyServer
from t5lobby.server.mmfilters import MatchFiltersMixin
from t5lobby.server.rooms import Room, RoomsMixin
from t5lobby.server.rematch import RematchMixin


CAPS = {"sets", "casual_sets", "private_rooms"}


def player(name):
    p = NS(id=name, name=name, build_id="test", online=True, match=None, room=None,
           status="room", guest=True, watching=None)
    p.brief = lambda: {"id": name, "name": name}
    p.send = Mock()
    return p


class Harness(RoomsMixin, RematchMixin):
    _room_tags = MatchFiltersMixin._room_tags   # 1.3.0: room_create reads the area / language tags (mmfilters.py)
    _check_filtered_text = LobbyServer._check_filtered_text

    def __init__(self):
        self.chat_filter = Mock(blocked=Mock(return_value=False))
        self.rooms = {}
        self.draining = False
        self.dirty = False
        self.cfg = NS(room_max_size=8, ranked_rooms=True, guest_ranked=True, room_next_seconds=8)
        self._refuse_draining = Mock()
        self._room_training_opt = lambda conn, msg, ranked: bool(msg.get("training"))
        self._abandon_set = Mock()
        self._check_speed = Mock()
        self._set_free = Mock()
        self._is_blocked = lambda a, b: False
        self._casual_sides = lambda a, b: (a, b)
        self._room_view = lambda room, viewer: room.public()
        self.create_match = Mock(side_effect=lambda a, b, **kw: NS(players=[a, b], state="ready"))
        self._end_set = Mock()

    def room(self, rotation="winner", size=4, first_to=3):
        a, b, c, d = (player(n) for n in "ABCD")
        r = Room(a, "Table", False, size, rotation, first_to)
        r.members = [a, b, c, d][:size]
        r.line = list(r.members)
        for p in r.members:
            p.room = r
        self.rooms[r.id] = r
        return r, (a, b, c, d)


class RoomTargetTest(unittest.TestCase):
    def create(self, target=1, caps=CAPS, ranked=False, training=False):
        srv = Harness()
        p = player("Host")
        p.status = "idle"
        conn = NS(player=p, caps=caps, closed=False)
        reply = asyncio.run(srv.h_room_create(conn, {"first_to": target, "ranked": ranked,
                                                    "training": training}))
        return srv, next(iter(srv.rooms.values())), reply

    def test_all_targets_are_server_room_metadata(self):
        for target in (1, 2, 3, 5, 10):
            with self.subTest(target=target):
                _srv, r, reply = self.create(target)
                self.assertEqual(r.first_to, target)
                self.assertEqual(reply["room"]["first_to"], target)

    def test_invalid_targets_are_rejected_without_creating_room(self):
        for target in (True, False, 0, -1, 4, 11, "3", 3.0, None, [], {}):
            with self.subTest(target=target), self.assertRaises(LobbyError):
                self.create(target)

    def test_old_hosts_and_ranked_or_training_keep_single_game_setting(self):
        for caps, ranked, training in ((set(), False, False), ({"casual_sets"}, False, False),
                                       (CAPS, True, False), (CAPS, False, True)):
            with self.subTest(caps=caps, ranked=ranked, training=training):
                _srv, r, reply = self.create(10, caps, ranked, training)
                self.assertEqual(r.first_to, 1)
                if ranked or training:
                    self.assertNotIn("first_to", reply["room"])

    def test_room_start_passes_configured_target_to_core_capability_gate(self):
        srv = Harness()
        r, _players = srv.room(first_to=10)
        srv._room_start(r)
        self.assertEqual(srv.create_match.call_args.kwargs["first_to"], 10)
        self.assertIs(srv.create_match.call_args.kwargs["room"], r)


class CommunitySetTurnTest(unittest.TestCase):
    def setup_set(self, rotation="winner", swapped=False):
        srv = Harness()
        r, (a, b, c, d) = srv.room(rotation)
        sides = [b, a] if swapped else [a, b]
        first = NS(line_order=(a, b))
        gs = NS(casual=True, state="active", players=sides, matches=[first], outcome=None,
                current=None, rated=False)
        r.set = gs
        m = NS(set=gs, players=sides)
        srv._room_schedule = Mock()
        return srv, r, gs, m, (a, b, c, d)

    def test_between_games_does_not_rotate_or_offer_table_to_waiting_pair(self):
        srv, r, gs, m, players = self.setup_set()
        srv._room_match_over(r, m, "confirmed", 0)
        self.assertEqual(r.line, list(players))
        srv._room_schedule.assert_not_called()
        srv._room_start(r)
        srv.create_match.assert_not_called()
        self.assertEqual(r.status(), "playing")

    def test_schedule_does_not_start_another_pair_during_set_countdown(self):
        srv, r, gs, _m, _players = self.setup_set()
        # Exercise the actual scheduling method: an active set owns the table even
        # if two waiting players would otherwise be free for a second match.
        RoomsMixin._room_schedule(srv, r)
        self.assertIsNone(r.next_timer)
        self.assertIsNone(r.next_at)

    def test_winner_stays_uses_whole_set_winner_and_only_rotates_once(self):
        srv, r, gs, m, (a, b, c, d) = self.setup_set(swapped=True)
        gs.state = "ended"
        gs.outcome = {"status": "confirmed", "winner": a}
        # B wins the final individual game in this fixture; the room must use A,
        # the server's set winner, and the original line order despite side choice.
        srv._room_match_over(r, m, "confirmed", 0)
        self.assertEqual(r.line, [a, c, d, b])
        srv._room_set_over(r, gs, "confirmed", a)
        self.assertEqual(r.line, [a, c, d, b])
        srv._room_schedule.assert_called_once_with(r)

    def test_everyone_in_turn_moves_the_longer_seated_player_after_whole_set(self):
        srv, r, gs, m, (a, b, c, d) = self.setup_set("queue", swapped=True)
        gs.state = "ended"
        gs.outcome = {"status": "confirmed", "winner": a}
        srv._room_match_over(r, m, "confirmed", 0)
        self.assertEqual(r.line, [b, c, d, a])

    def test_unfinished_set_leave_has_no_set_winner_and_winner_rule_moves_both(self):
        srv, r, gs, _m, (a, b, c, d) = self.setup_set()
        gs.state = "ended"
        srv._room_set_over(r, gs, "void", None)
        self.assertEqual(r.line, [c, d, a, b])

    def test_unfinished_set_leave_preserves_everyone_in_turn_rule(self):
        srv, r, gs, _m, (a, b, c, d) = self.setup_set("queue")
        gs.state = "ended"
        srv._room_set_over(r, gs, "void", None)
        self.assertEqual(r.line, [b, c, d, a])

    def test_sitting_out_between_games_ends_the_set_as_casual_leave(self):
        srv, r, gs, _m, (a, b, c, d) = self.setup_set()
        srv._room_line(r, a, False)
        self.assertNotIn(a, r.line)
        srv._end_set.assert_called_once_with(gs, "left", by=a)

    def test_cancelled_next_game_moves_the_line_once(self):
        srv, r, gs, m, (a, b, c, d) = self.setup_set()
        gs.state = "ended"
        srv._room_match_cancelled(r, m, "connection_failed", None)
        self.assertEqual(r.line, [c, d, a, b])
        srv._room_set_over(r, gs, "void", None)
        self.assertEqual(r.line, [c, d, a, b])
        srv._room_schedule.assert_called_once_with(r)

    def test_legacy_single_game_still_rotates_after_each_result(self):
        srv, r, _gs, _m, (a, b, c, d) = self.setup_set()
        r.set = None
        m = NS(set=None, players=[a, b])
        srv._room_match_over(r, m, "confirmed", 1)
        self.assertEqual(r.line, [b, c, d, a])

    def test_member_view_keeps_players_and_score_visible_between_games(self):
        srv, r, gs, _m, (a, b, c, d) = self.setup_set()
        gs.info = lambda: {"casual": True, "first_to": 3, "wins": [1, 0], "state": "active"}
        srv._spec_room_match = lambda room: None
        view = RoomsMixin._room_view(srv, r, c)
        self.assertEqual(view["first_to"], 3)
        self.assertEqual(view["playing"], [a.id, b.id])
        self.assertEqual(view["set"]["wins"], [1, 0])
        self.assertEqual([p["state"] for p in view["players"]], ["playing", "playing", "line", "line"])


if __name__ == "__main__":
    unittest.main()
