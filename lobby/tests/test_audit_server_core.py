"""Resume authority regressions: in-memory database and fake connections only."""
import asyncio
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from t5lobby import proto
from t5lobby.server import Config, LobbyServer
from t5lobby.server.store import PERMANENT


class ResumeAuthorityTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.srv = LobbyServer(Config(db=":memory:", scrypt_n=1 << 10))
        self.srv._send_active_notices = mock.Mock()
        self.srv._send_friends = mock.Mock()
        self.srv.tours.player_online = mock.Mock()
        self.conn = self.connection()
        reply = await self.srv.h_login(self.conn, {
            "mode": "register", "name": "Alice", "password": "offline-test-password"})
        self.player = self.conn.player
        self.token = reply["token"]
        self.srv.player_dropped(self.player)

    async def asyncTearDown(self):
        await asyncio.sleep(0)
        self.srv.store.close()

    @staticmethod
    def connection():
        return SimpleNamespace(helloed=True, closed=False, player=None, build_id="offline-test",
                               release="test", ip="127.0.0.1", akey="127.0.0.1",
                               caps=frozenset(), send=mock.Mock())

    async def test_detached_banned_account_cannot_resume_before_admin_poll(self):
        self.srv.store.ban_account("Alice", PERMANENT, "test")
        conn = self.connection()
        with self.assertRaises(proto.LobbyError) as caught:
            await self.srv.h_login(conn, {"mode": "resume", "token": self.token})
        self.assertEqual(caught.exception.code, proto.E_NOT_ALLOWED)
        self.assertIsNone(conn.player)
        self.assertIsNone(self.player.conn)
        self.assertNotIn(self.player.id, self.srv.players)
        self.assertNotIn("alice", self.srv.by_name)

    async def test_detached_deleted_account_cannot_restore_ghost_identity(self):
        self.srv.store.delete_account("Alice")
        conn = self.connection()
        with self.assertRaises(proto.LobbyError) as caught:
            await self.srv.h_login(conn, {"mode": "resume", "token": self.token})
        self.assertEqual(caught.exception.code, proto.E_AUTH)
        self.assertIsNone(conn.player)
        self.assertIsNone(self.player.conn)
        self.assertNotIn(self.token, self.srv.sessions)
        self.assertNotIn(self.player.id, self.srv.players)
        self.assertNotIn(self.player.account_id, self.srv.by_account)


if __name__ == "__main__":
    unittest.main()
