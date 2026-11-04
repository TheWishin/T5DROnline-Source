"""Combined room/rematch regressions with fake players; no listener, game, build or network."""
import asyncio
import unittest
from types import SimpleNamespace as NS
from unittest.mock import Mock

import util  # noqa: F401 -- repository import paths only
from t5lobby.proto import LobbyError
from t5lobby.server.config import Config
from t5lobby.server.lobby import LobbyServer
from t5lobby.server.rematch import CAP, SKIP_CAP, RematchMixin
from t5lobby.server.mmfilters import MatchFiltersMixin
from t5lobby.server.rooms import Room, RoomsMixin


CAPS = {CAP, SKIP_CAP, "private_rooms", "sets", "casual_sets", "room_tables"}


def player(name):
    p = NS(id=name, name=name, build_id="test", online=True, match=None, room=None,
           status="idle", guest=True, watching=None, auto_skip_after_round=True)
    p.conn = NS(player=p, caps=set(CAPS), closed=False)
    p.brief = lambda: {"id": name, "name": name}
    p.send = Mock()
    return p


class Harness(RoomsMixin, RematchMixin):
    _room_tags = MatchFiltersMixin._room_tags   # 1.3.0: room_create reads the area / language tags (mmfilters.py)
    _set_next = LobbyServer._set_next
    _check_filtered_text = LobbyServer._check_filtered_text

    def __init__(self, enabled=True):
        self.cfg = Config(ingame_rematch=enabled, auto_skip=enabled)     # (the skip rule's own opt-in, on here)
        self.chat_filter = Mock(blocked=Mock(return_value=False))
        self.rooms = {}
        self.dirty = False
        self._refuse_draining = Mock()
        self._room_training_opt = lambda conn, msg, ranked: False
        self._abandon_set = Mock()
        self._check_speed = Mock()
        self._spec_room_match = lambda room, table=None: None
        self._direct_again = lambda match: False
        self.create_match = Mock(return_value=NS(table=None, state="ready"))

    def room(self, size=2, mode="line"):
        a, b = player("A"), player("B")
        r = Room(a, "Room", False, size=size, first_to=3, mode=mode)
        r.members = [a, b]
        r.line = [a, b]
        self.rooms[r.id] = r
        for p in r.members:
            p.room, p.status = r, "room"
        m = NS(id="old", room=r, players=[a, b], ranked=False, origin="room", set=None)
        return r, m, a, b


class IntegratedRoomRematchTest(unittest.TestCase):
    def create(self, fields, enabled=True):
        srv = Harness(enabled)
        owner = player("Host")
        reply = asyncio.run(srv.h_room_create(owner.conn, fields))
        return srv, next(iter(srv.rooms.values())), owner, reply

    def test_room_creation_obeys_filter_before_changing_room_or_set_state(self):
        srv = Harness()
        owner = player("Host")
        owner.account_id = None
        srv.chat_filter.blocked.return_value = True
        with self.assertRaisesRegex(LobbyError, "This room name is not allowed"):
            asyncio.run(srv.h_room_create(owner.conn, {"name": "Rejected room", "first_to": 3}))
        srv.chat_filter.blocked.assert_called_once_with("Rejected room")
        self.assertEqual(srv.rooms, {})
        self.assertEqual(owner.status, "idle")
        self.assertIsNone(owner.room)
        self.assertFalse(srv.dirty)
        srv._abandon_set.assert_not_called()

    def test_classic_room_keeps_first_to_and_rematch_rules_together(self):
        _srv, room, _owner, reply = self.create({
            "first_to": 3, "rematch_policy": "auto_unless_declined", "auto_skip_after_round": True})
        self.assertEqual(room.first_to, 3)
        self.assertEqual(room.rematch_policy, "auto_unless_declined")
        self.assertTrue(room.auto_skip_after_round)
        self.assertEqual(reply["room"]["first_to"], 3)
        self.assertEqual(reply["room"]["rematch_policy"], "auto_unless_declined")
        self.assertTrue(reply["room"]["auto_skip_after_round"])

    def test_disabled_feature_keeps_classic_and_table_creation_compatible(self):
        for mode in ("line", "tables"):
            with self.subTest(mode=mode):
                srv, room, owner, reply = self.create({"first_to": 3, "mode": mode}, enabled=False)
                self.assertEqual(room.first_to, 3)
                self.assertEqual(room.mode, mode)
                self.assertEqual(room.rematch_policy, "both_confirm")
                self.assertFalse(room.auto_skip_after_round)
                self.assertNotIn("rematch_policy", reply["room"])
                self.assertNotIn("auto_skip_after_round", reply["room"])
                owner.auto_skip_after_round = True
                match = NS(room=room, requested_ranked=False, tournament_origin=False)
                self.assertFalse(srv._rematch_skip_rule(match, owner, owner, False, "room"))

    def test_two_seat_tables_never_accept_classic_rematch_options(self):
        for rule in ({"rematch_policy": "auto_unless_declined"}, {"auto_skip_after_round": True}):
            with self.subTest(rule=rule), self.assertRaisesRegex(LobbyError, "classic casual room"):
                self.create(dict(rule, mode="tables", size=2))

    def test_table_result_never_offers_rotation_or_classic_votes(self):
        for size in (2, 4):
            srv = Harness()
            room, match, a, _b = srv.room(size=size, mode="tables")
            srv._rematch_ui_open(match)
            self.assertFalse(hasattr(match, "ui_deadline"))
            self.assertEqual(srv._rematch_ui_result(match, a), {})
            self.assertNotIn("rematch_policy", srv._room_view(room, a))
            with self.assertRaisesRegex(LobbyError, "classic casual room"):
                asyncio.run(srv.h_room_rules(a.conn, {"rematch_policy": "both_confirm"}))

    def test_active_casual_set_owns_classic_countdown_until_decided(self):
        srv = Harness()
        room, match, a, _b = srv.room()
        gs = NS(casual=True, automatic=True, rated=False, state="active", current=None)
        room.set = match.set = gs
        srv._rematch_ui_open(match)
        self.assertFalse(hasattr(match, "ui_deadline"))
        self.assertEqual(srv._rematch_ui_result(match, a), {})
        with self.assertRaisesRegex(LobbyError, "finish the match first"):
            asyncio.run(srv.h_room_rules(a.conn, {"rematch_policy": "auto_unless_declined"}))
        self.assertEqual(room.rematch_policy, "both_confirm")
        gs.state = "done"
        srv._rematch_ui_open(match)
        self.assertEqual(srv._rematch_ui_result(match, a)["rematch_ui"]["actions"], ["accept", "decline"])

    def test_active_community_set_keeps_seats_and_gets_no_question_in_the_game(self):
        srv = Harness()
        room, match, a, _b = srv.room(size=4)
        gs = NS(casual=True, automatic=True, rated=False, state="active")
        room.set = match.set = gs
        self.assertEqual(srv._rematch_ui_result(match, a), {})
        gs.state = "done"
        # 1.2.0: no question in the game for a community room (the room picks the next pair; its line actions stay
        # in the launcher)
        self.assertEqual(srv._rematch_ui_result(match, a), {})

    def test_result_snapshot_waits_for_casual_set_progression(self):
        for deciding in (False, True):
            with self.subTest(deciding=deciding):
                srv = Harness()
                room, match, a, b = srv.room()
                room.rematch_policy = "auto_unless_declined"
                match.chars, match.table, match.path = None, None, "direct"
                room.match = match
                gs = NS(casual=True, automatic=True, rated=False, state="active",
                        current=match, outcome=None)
                gs.info = lambda: {"casual": True, "state": gs.state}
                room.set = match.set = gs
                for p in (a, b):
                    p.match, p.status = match, "match"
                    p.public = p.brief
                srv.matches, srv.recent = {match.id: match}, {}
                srv._cancel_timers = Mock()
                srv._rules_finish = lambda m, *result: result
                srv._picked = lambda m: None
                srv._release = Mock()
                srv._save = Mock()
                srv._expire_recent = Mock()
                srv._announce_set_end = Mock()
                srv._count = Mock()
                srv.note = Mock()

                def progress(current, *result):
                    if deciding:
                        current.state = "done"
                        current.outcome = {"changes": None}

                srv._set_game_over = progress

                async def finish():
                    LobbyServer._finish(srv, match, "void", None, None)

                asyncio.run(finish())
                event = a.send.call_args.args[0]
                self.assertEqual(event["t"], "match_result")
                self.assertEqual("rematch_ui" in event, deciding)
                if deciding:
                    self.assertEqual(event["rematch_ui"]["policy"], "auto_unless_declined")
                    self.assertGreater(event["rematch_window"], 0)
                else:
                    self.assertFalse(hasattr(match, "ui_deadline"))
                    self.assertEqual(event["rematch_window"], 0)

    def test_set_next_reconnects_when_mutual_skip_consent_changes(self):
        for previous, consent, keep in ((True, False, False), (False, True, False), (True, True, True)):
            with self.subTest(previous=previous, consent=consent):
                srv = Harness()
                room, match, a, b = srv.room()
                room.auto_skip_after_round = True
                match.path, match.auto_skip_after_round = "direct", previous
                a.auto_skip_after_round = b.auto_skip_after_round = consent
                gs = NS(state="active", current=None, players=[a, b], fresh=False, last=match,
                        next_keep={a.id: True, b.id: True}, ranked=False, table=None)
                srv._set_next(gs)
                self.assertEqual(srv.create_match.call_args.kwargs["keep"], keep)
                self.assertIs(srv.create_match.call_args.kwargs["game_set"], gs)


if __name__ == "__main__":
    unittest.main()
