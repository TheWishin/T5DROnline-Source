"""Idle session recovery using in-memory state only; no listeners or game data."""
import asyncio
import os
import sys
import time
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from t5lobby import proto
from t5lobby.server import Config, LobbyServer


class IdleResumeTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.srv = LobbyServer(Config(db=":memory:", resume_window=10, scrypt_n=1 << 10))
        self.srv._send_active_notices = mock.Mock()
        self.srv._send_friends = mock.Mock()
        self.srv.tours.player_online = mock.Mock()

    async def asyncTearDown(self):
        await asyncio.sleep(0)
        self.srv.store.close()

    def conn(self, caps=()):
        return SimpleNamespace(helloed=True, closed=False, player=None, build_id="offline-test",
                               release="test", ip="127.0.0.1", akey="127.0.0.1",
                               caps=frozenset(caps), send=mock.Mock())

    async def login(self, name="Alice", **fields):
        conn = self.conn()
        reply = await self.srv.h_login(conn, dict(t="login", mode="guest", name=name, **fields))
        return conn, reply

    async def test_idle_guest_resumes_same_identity_without_visible_ghost(self):
        conn, logged = await self.login()
        player = conn.player
        self.srv.player_dropped(player)
        self.assertNotIn(player.id, self.srv.players)
        self.assertNotIn(player.name.lower(), self.srv.by_name)
        self.assertNotIn(proto.name_skeleton(player.name), self.srv.by_skel)
        resumed_conn = self.conn()
        resumed = await self.srv.h_login(resumed_conn, {"mode": "resume", "token": logged["token"]})
        self.assertEqual(resumed["t"], "login_ok")
        self.assertEqual(resumed["you"]["id"], logged["you"]["id"])
        self.assertEqual(resumed["token"], logged["token"])
        self.assertTrue(resumed["resumed"])
        self.assertIs(resumed_conn.player, player)
        self.assertIs(self.srv.players[player.id], player)
        self.assertIs(self.srv.by_name["alice"], player)
        self.assertIs(self.srv.by_skel[proto.name_skeleton("Alice")], player)
        self.assertEqual(self.srv.counters["logins_guest"], 1)

    async def test_idle_account_keeps_remembered_session_without_password_replay(self):
        conn = self.conn()
        logged = await self.srv.h_login(conn, {"mode": "register", "name": "Alice",
                                               "password": "offline-test-password", "remember": True})
        player, session = conn.player, conn.player.session
        self.srv.player_dropped(player)
        self.assertNotIn(player.account_id, self.srv.by_account)
        resumed = await self.srv.h_login(self.conn(), {"mode": "resume", "token": logged["token"]})
        self.assertEqual(resumed["you"]["id"], player.id)
        self.assertEqual(player.session, session)
        self.assertIs(self.srv.by_account[player.account_id], player)
        self.assertEqual(self.srv.counters["logins_account"], 1)

    async def test_fresh_guest_login_invalidates_detached_token_permanently(self):
        old_conn, old = await self.login()
        self.srv.player_dropped(old_conn.player)
        new_conn, new = await self.login()
        self.assertNotEqual(old["you"]["id"], new["you"]["id"])
        self.srv.player_dropped(new_conn.player, final=True)
        with self.assertRaises(proto.LobbyError) as caught:
            await self.srv.h_login(self.conn(), {"mode": "resume", "token": old["token"]})
        self.assertEqual(caught.exception.code, proto.E_AUTH)

    async def test_fresh_account_login_invalidates_detached_token_permanently(self):
        conn = self.conn()
        old = await self.srv.h_login(conn, {"mode": "register", "name": "Alice",
                                           "password": "offline-test-password", "remember": True})
        self.srv.player_dropped(conn.player)
        new_conn = self.conn()
        new = await self.srv.h_login(new_conn, {"mode": "account", "name": "Alice",
                                               "password": "offline-test-password"})
        self.assertNotEqual(old["you"]["id"], new["you"]["id"])
        self.assertNotIn(old["token"], self.srv.sessions)
        self.srv.player_dropped(new_conn.player, final=True)
        with self.assertRaises(proto.LobbyError) as caught:
            self.srv._resume(self.conn(), old["token"])
        self.assertEqual(caught.exception.code, proto.E_AUTH)

    async def test_final_drop_does_not_leave_a_resumable_idle_session(self):
        conn, logged = await self.login()
        self.srv.player_dropped(conn.player, final=True)
        self.assertNotIn(logged["token"], self.srv.sessions)
        with self.assertRaises(proto.LobbyError):
            self.srv._resume(self.conn(), logged["token"])

    async def test_expired_detached_token_is_refused_before_housekeeping(self):
        conn, logged = await self.login()
        player = conn.player
        self.srv.player_dropped(player)
        player.dropped_at = time.monotonic() - self.srv.cfg.resume_window - 1
        with self.assertRaises(proto.LobbyError) as caught:
            self.srv._resume(self.conn(), logged["token"])
        self.assertEqual(caught.exception.code, proto.E_AUTH)
        self.assertNotIn(logged["token"], self.srv.sessions)

    async def test_housekeeping_expires_idle_tokens_outside_active_player_index(self):
        conn, logged = await self.login()
        player = conn.player
        self.srv.player_dropped(player)
        player.dropped_at = time.monotonic() - self.srv.cfg.resume_window - 1
        self.assertIs(self.srv.sessions[logged["token"]], player)
        self.assertNotIn(player.id, self.srv.players)
        # Run exactly one maintenance pass without waiting, binding, or reading
        # deployment files. The second sleep cancels the periodic coroutine.
        with mock.patch("t5lobby.server.lobby.asyncio.sleep", new=mock.AsyncMock(
                side_effect=[None, asyncio.CancelledError()])), \
                mock.patch.object(self.srv, "reload_tls"), \
                mock.patch.object(self.srv, "_maybe_backup"), \
                mock.patch.object(self.srv, "_maybe_log_status"), \
                mock.patch.object(self.srv, "_db_upkeep"):
            with self.assertRaises(asyncio.CancelledError):
                await self.srv._tick_housekeeping()
        self.assertNotIn(logged["token"], self.srv.sessions)

    async def test_resume_does_not_replace_an_active_conflicting_name(self):
        conn, logged = await self.login()
        player = conn.player
        self.srv.player_dropped(player)
        other = SimpleNamespace()
        self.srv.by_name["alice"] = other
        with self.assertRaises(proto.LobbyError):
            self.srv._resume(self.conn(), logged["token"])
        self.assertIs(self.srv.by_name["alice"], other)
        self.assertIsNone(player.conn)

    async def test_resume_refuses_skeleton_collision_without_displacing_owner(self):
        conn, logged = await self.login()
        player = conn.player
        self.srv.player_dropped(player)
        other = SimpleNamespace()
        skeleton = proto.name_skeleton(player.name)
        self.srv.by_skel[skeleton] = other
        with self.assertRaises(proto.LobbyError):
            self.srv._resume(self.conn(), logged["token"])
        self.assertIs(self.srv.by_skel[skeleton], other)
        self.assertIsNone(player.conn)

    async def test_resume_does_not_replace_an_active_account_owner(self):
        conn = self.conn()
        logged = await self.srv.h_login(conn, {"mode": "register", "name": "Alice",
                                               "password": "offline-test-password"})
        player = conn.player
        self.srv.player_dropped(player)
        other = SimpleNamespace()
        self.srv.by_account[player.account_id] = other
        with self.assertRaises(proto.LobbyError):
            self.srv._resume(self.conn(), logged["token"])
        self.assertIs(self.srv.by_account[player.account_id], other)
        self.assertIsNone(player.conn)

    async def test_wrong_build_does_not_consume_detached_token(self):
        conn, logged = await self.login()
        player = conn.player
        self.srv.player_dropped(player)
        wrong = self.conn()
        wrong.build_id = "different-build"
        with self.assertRaises(proto.LobbyError):
            self.srv._resume(wrong, logged["token"])
        self.assertIs(self.srv.sessions[logged["token"]], player)
        self.assertEqual(self.srv._resume(self.conn(), logged["token"])["you"]["id"], player.id)


if __name__ == "__main__":
    unittest.main()
