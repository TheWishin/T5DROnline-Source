"""Guest mute synchronization must not hold up login; no sockets or game used."""
import asyncio
import unittest
from unittest.mock import AsyncMock, Mock

import util  # noqa: F401 -- import path only
from t5lobby.buildid import BuildInfo
from t5lobby.client import LobbyClient


class GuestMuteReplayAuditTest(unittest.IsolatedAsyncioTestCase):
    def client(self):
        client = LobbyClient("127.0.0.1:7781", BuildInfo("test", "test", "test"),
                             guest_mutes=["Rival", "Other"], nat2=False)
        client.me = {"id": "me", "name": "Tester", "guest": True}
        client.welcome = {"caps": ["mutes"], "features": ["mutes"]}
        self.addAsyncCleanup(self.cancel_replay, client)
        return client

    async def cancel_replay(self, client):
        task = getattr(client, "_mute_replay_task", None)
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def test_login_finishes_before_any_guest_mute_round_trip(self):
        client = self.client()

        async def request(message, timeout=None):
            if message["t"] == "login":
                return {"you": client.me, "token": "accepted-token"}
            self.fail("login waited for guest mute synchronization")

        client._request = AsyncMock(side_effect=request)
        client._measure_server = AsyncMock()
        client._server_relays = Mock(return_value=[])
        client._start_keepalive = Mock()
        client._start_port_mapper = Mock()
        client._spec_after_login = AsyncMock()
        client._casual_after_login = AsyncMock()
        result = await client._login_async({"t": "login", "mode": "guest", "name": "Tester"})
        self.assertEqual(result["name"], "Tester")
        self.assertEqual(client.token, "accepted-token")
        self.assertTrue(client.is_muted("Rival"))
        self.assertTrue(client.is_muted("Other"))
        self.assertEqual(client._request.await_count, 1)
        self.assertIn(client._mute_replay_task, client._tasks)

    async def test_lobby_row_refresh_does_not_stop_replay(self):
        client = self.client()

        async def request(message):
            if message["name"] == "Rival":
                await client._on_lobby_state({"players": [dict(client.me, status="idle")]})
            return {"t": "muted"}

        client._request = AsyncMock(side_effect=request)
        await client._mutes_after_login({})
        await client._mute_replay_task
        self.assertEqual([call.args[0]["name"] for call in client._request.await_args_list],
                         ["Rival", "Other"])

    async def test_replacement_login_cancels_pending_guest_replay(self):
        client = self.client()
        started = asyncio.Event()

        async def request(message):
            started.set()
            await asyncio.Event().wait()

        client._request = AsyncMock(side_effect=request)
        await client._mutes_after_login({})
        await started.wait()
        old_task = client._mute_replay_task
        client.me = {"id": "account", "name": "Account", "guest": False}
        await client._mutes_after_login({"mutes": []})
        self.assertTrue(old_task.cancelled())
        self.assertIsNone(client._mute_replay_task)
        self.assertEqual(client._request.await_count, 1)
        self.assertFalse(client.is_muted("Rival"))

    async def test_replay_skips_a_name_unmuted_during_previous_reply(self):
        client = self.client()

        async def request(message):
            client._set_mute_rows([{"name": "Rival"}], emit=False)
            return {"t": "muted"}

        client._request = AsyncMock(side_effect=request)
        await client._mutes_after_login({})
        await client._mute_replay_task
        client._request.assert_awaited_once_with({"t": "mute", "name": "Rival", "muted": True})

    async def test_disconnect_cancels_pending_replay_before_reconnect(self):
        client = self.client()
        started = asyncio.Event()

        async def request(message):
            started.set()
            await asyncio.Event().wait()

        client._request = AsyncMock(side_effect=request)
        await client._mutes_after_login({})
        await started.wait()
        old_task = client._mute_replay_task
        client._reader = Mock()
        client._reader.readuntil = AsyncMock(side_effect=asyncio.IncompleteReadError(b"", 1))
        client._writer = Mock()
        client._writer.wait_closed = AsyncMock()
        client._drop_game_socket = AsyncMock()
        client._closing = True
        await client._read_loop()
        self.assertTrue(old_task.cancelled())
        self.assertIsNone(client._mute_replay_task)
        self.assertEqual(client._request.await_count, 1)


if __name__ == "__main__":
    unittest.main()
