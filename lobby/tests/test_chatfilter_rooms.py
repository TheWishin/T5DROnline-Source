"""Room-name enforcement without a running server or game.

The matcher itself is tested separately; this harness checks that room creation
consults it before making a room, abandoning a set or hashing a password.
"""
import re
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import util  # noqa: F401 -- (sets up the lobby import path)
from t5lobby import proto
from t5lobby.proto import LobbyError
from t5lobby.server.mmfilters import MatchFiltersMixin
from t5lobby.server.rooms import RoomsMixin


class RoomHarness(RoomsMixin):
    _room_tags = MatchFiltersMixin._room_tags   # 1.2.1: room_create reads the area / language tags (mmfilters.py)
    def __init__(self):
        self.cfg = SimpleNamespace(room_max_size=8, ranked_rooms=True, guest_ranked=False)
        self.rooms = {}
        self.dirty = False
        self.checks = []
        self.blocked_terms = {"blockedword"}
        self._refuse_draining = Mock()
        self._room_training_opt = Mock(return_value=False)
        self._rematch_room_options = Mock(return_value=("both_confirm", False))
        self._abandon_set = Mock()
        self._room_hash = AsyncMock(return_value="test hash")
        self._room_view = lambda room, player: {"id": room.id, "name": room.name}

    def _check_filtered_text(self, text, context, player=None):
        self.checks.append((text, context, player))
        if any(re.search(r"\b" + re.escape(term) + r"\b", text, re.IGNORECASE)
               for term in self.blocked_terms):
            raise LobbyError(proto.E_NOT_ALLOWED, "This room name is not allowed.")


class RoomNameFilterTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.server = RoomHarness()
        self.player = SimpleNamespace(name="Alice", status="idle", guest=False,
                                      room=None, build_id="test-build")
        self.conn = SimpleNamespace(player=self.player, closed=False,
                                    caps=frozenset(("private_rooms",)))

    async def refused(self, msg):
        with self.assertRaises(LobbyError) as error:
            await self.server.h_room_create(self.conn, msg)
        self.assertEqual((error.exception.code, error.exception.msg),
                         (proto.E_NOT_ALLOWED, "This room name is not allowed."))
        self.assertEqual(self.server.rooms, {})
        self.assertEqual(self.player.status, "idle")
        self.assertIsNone(self.player.room)
        self.assertFalse(self.server.dirty)
        self.server._abandon_set.assert_not_called()
        self.server._room_hash.assert_not_awaited()

    async def test_rejected_before_private_password_hash_or_set_abandon(self):
        await self.refused({"name": "blockedword", "private": "password", "password": "safe-password"})
        self.assertEqual(self.server.checks, [("blockedword", "room", self.player)])

    async def test_old_clients_cannot_skip_room_name_check(self):
        self.conn.caps = frozenset()
        await self.refused({"name": "blockedword"})

    async def test_full_submission_checked_before_truncation(self):
        raw = "Friendly room " + "x" * 32 + " blockedword"
        self.assertNotIn("blockedword", proto.clean_text(raw, 32))
        await self.refused({"name": raw})

    async def test_cleaned_name_checked_when_controls_join_letters(self):
        await self.refused({"name": "blocked\x00word"})
        self.assertEqual([text for text, _, _ in self.server.checks],
                         ["blocked\x00word", "blockedword"])

    async def test_default_name_is_checked_without_changing_existing_account_name(self):
        self.player.name = "blockedword"
        await self.refused({})
        self.assertEqual(self.player.name, "blockedword")

    async def test_existing_account_can_choose_an_innocent_room_name(self):
        self.player.name = "blockedword"
        reply = await self.server.h_room_create(self.conn, {"name": "Friendly dojo"})
        self.assertEqual(reply["room"]["name"], "Friendly dojo")
        self.assertEqual(self.player.name, "blockedword")
        self.assertEqual(self.player.status, "room")
        self.assertEqual(len(self.server.rooms), 1)
        self.server._abandon_set.assert_called_once_with(self.player)

    async def test_innocent_default_name_keeps_existing_room_behavior(self):
        reply = await self.server.h_room_create(self.conn, {})
        self.assertEqual(reply["room"]["name"], "Alice's room")

    async def test_policy_reload_during_password_hash_prevents_publication(self):
        async def reload_policy(player, password):
            self.server.blocked_terms.add("newlyblocked")
            return "test hash"

        self.server._room_hash.side_effect = reload_policy
        with self.assertRaises(LobbyError) as error:
            await self.server.h_room_create(self.conn, {
                "name": "newlyblocked", "private": "password", "password": "safe-password"})
        self.assertEqual((error.exception.code, error.exception.msg),
                         (proto.E_NOT_ALLOWED, "This room name is not allowed."))
        self.server._room_hash.assert_awaited_once_with(self.player, "safe-password")
        self.assertEqual(self.server.checks, [("newlyblocked", "room", self.player),
                                             ("newlyblocked", "room", self.player)])
        self.assertEqual(self.server.rooms, {})
        self.assertEqual(self.player.status, "idle")
        self.assertIsNone(self.player.room)
        self.assertFalse(self.server.dirty)


if __name__ == "__main__":
    unittest.main()
