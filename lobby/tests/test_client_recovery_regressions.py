"""Control-stream shutdown regressions using fakes; no listener or server contact."""
import asyncio
import unittest
from unittest import mock

import util  # noqa: F401 -- shared import path only
from t5lobby.client import LobbyClient
from t5lobby.proto import LobbyError


class ClientRecoveryRegressions(unittest.TestCase):
    def test_reader_waits_for_stream_shutdown_on_eof_reset_and_cancellation(self):
        async def check(failure):
            client = LobbyClient("127.0.0.1:7781", util.BUILD)
            client._closing = True
            client.connected = True
            client._reader = mock.Mock(readuntil=mock.AsyncMock(side_effect=failure))
            client._writer = mock.Mock(wait_closed=mock.AsyncMock())
            pending = asyncio.get_running_loop().create_future()
            client._pending[1] = pending

            async def closed():
                # Commands with an unknown outcome must fail before stream cleanup waits.
                self.assertTrue(pending.done())
                self.assertEqual(pending.exception().code, "disconnected")

            client._writer.wait_closed.side_effect = closed
            await client._read_loop()
            client._writer.close.assert_called_once_with()
            client._writer.wait_closed.assert_awaited_once_with()
            self.assertFalse(client.connected)
            self.assertIsInstance(pending.exception(), LobbyError)

        for failure in (asyncio.IncompleteReadError(b"", None), ConnectionResetError("cut"),
                        asyncio.CancelledError()):
            with self.subTest(failure=type(failure).__name__):
                asyncio.run(check(failure))

    def test_stream_shutdown_error_still_reports_disconnected(self):
        async def check(failure):
            client = LobbyClient("127.0.0.1:7781", util.BUILD, reconnect=0)
            client._reader = mock.Mock(readuntil=mock.AsyncMock(
                side_effect=asyncio.IncompleteReadError(b"", None)))
            client._writer = mock.Mock(wait_closed=mock.AsyncMock(side_effect=failure))
            await client._read_loop()
            client._writer.wait_closed.assert_awaited_once_with()
            self.assertEqual(client.events.get_nowait()["t"], "disconnected")

        for failure in (ConnectionResetError("cut during shutdown"), asyncio.TimeoutError()):
            with self.subTest(failure=type(failure).__name__):
                asyncio.run(check(failure))

    def test_stalled_stream_shutdown_aborts_the_transport(self):
        async def check():
            client = LobbyClient("127.0.0.1:7781", util.BUILD, reconnect=0)
            client._reader = mock.Mock(readuntil=mock.AsyncMock(
                side_effect=asyncio.IncompleteReadError(b"", None)))
            client._writer = mock.Mock(wait_closed=mock.AsyncMock())

            async def expired(awaitable, timeout):
                self.assertEqual(timeout, 2)
                # Model the shutdown deadline without sleeping or leaving a coroutine open.
                awaitable.close()
                raise asyncio.TimeoutError()

            with mock.patch("t5lobby.client.asyncio.wait_for", side_effect=expired):
                await client._read_loop()
            client._writer.close.assert_called_once_with()
            client._writer.transport.abort.assert_called_once_with()
            self.assertEqual(client.events.get_nowait()["t"], "disconnected")

        asyncio.run(check())

    def test_cancelled_stream_shutdown_aborts_and_preserves_cancellation(self):
        async def check():
            client = LobbyClient("127.0.0.1:7781", util.BUILD, reconnect=0)
            client._reader = mock.Mock(readuntil=mock.AsyncMock(
                side_effect=asyncio.IncompleteReadError(b"", None)))
            client._writer = mock.Mock(wait_closed=mock.AsyncMock(side_effect=asyncio.CancelledError()))
            with self.assertRaises(asyncio.CancelledError):
                await client._read_loop()
            client._writer.transport.abort.assert_called_once_with()
            self.assertTrue(client.events.empty())

        asyncio.run(check())


if __name__ == "__main__":
    unittest.main()
