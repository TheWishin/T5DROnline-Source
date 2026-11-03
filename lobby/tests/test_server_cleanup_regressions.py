"""Server shutdown regressions using fake streams only: no listeners or game data."""
import asyncio
from types import SimpleNamespace
import unittest
from unittest import mock

import util  # noqa: F401 -- repository test imports and offline defaults
from t5lobby.server import Config, LobbyServer
from t5lobby.server.lobby import Conn


class ServerCleanupTest(unittest.IsolatedAsyncioTestCase):
    async def test_writer_loop_awaits_transport_close(self):
        writer = mock.Mock()
        writer.get_extra_info.return_value = ("127.0.0.1", 12345)
        writer.wait_closed = mock.AsyncMock()
        srv = SimpleNamespace(cfg=Config(), counters={"tcp_out_bytes": 0})
        conn = Conn(srv, mock.Mock(), writer)
        conn.close()

        await conn.writer_loop()

        writer.close.assert_called_once()
        writer.wait_closed.assert_awaited_once()

    async def test_writer_close_connection_error_is_already_closed(self):
        writer = mock.Mock()
        writer.get_extra_info.return_value = ("127.0.0.1", 12345)
        writer.wait_closed = mock.AsyncMock(side_effect=ConnectionResetError("reset"))
        srv = SimpleNamespace(cfg=Config(), counters={"tcp_out_bytes": 0})
        conn = Conn(srv, mock.Mock(), writer)
        conn.close()

        await conn.writer_loop()

        writer.wait_closed.assert_awaited_once()

    async def test_cancelled_transport_close_aborts_instead_of_leaking_buffer(self):
        writer = mock.Mock()
        writer.get_extra_info.return_value = ("127.0.0.1", 12345)
        entered = asyncio.Event()

        async def wait_closed():
            entered.set()
            await asyncio.Future()

        writer.wait_closed = mock.AsyncMock(side_effect=wait_closed)
        srv = SimpleNamespace(cfg=Config(), counters={"tcp_out_bytes": 0})
        conn = Conn(srv, mock.Mock(), writer)
        conn.close()
        task = asyncio.create_task(conn.writer_loop())
        try:
            await asyncio.wait_for(entered.wait(), 1.0)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            writer.transport.abort.assert_called_once()
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def test_stop_awaits_cancelled_background_cleanup_before_database_close(self):
        srv = LobbyServer(Config(db=":memory:", name_blocklist=""))
        cleaned = []
        closed_after_cleanup = []

        async def background():
            try:
                await asyncio.Future()
            finally:
                await asyncio.sleep(0)
                cleaned.append(True)

        task = srv._spawn(background())
        await asyncio.sleep(0)
        original_close = srv.store.close

        def close_store():
            closed_after_cleanup.append(bool(cleaned))

        try:
            with mock.patch.object(srv.store, "close", side_effect=close_store):
                await srv.stop()
            self.assertTrue(task.done(), "stop returned before background cleanup finished")
            self.assertEqual(closed_after_cleanup, [True])
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            original_close()

    async def test_stop_joins_connection_handler_before_database_close(self):
        srv = LobbyServer(Config(db=":memory:", name_blocklist=""))
        srv._late_tls = False
        reader = asyncio.StreamReader()
        writer = mock.Mock()
        writer.get_extra_info.return_value = ("127.0.0.1", 12345)
        writer.close.side_effect = reader.feed_eof
        writer.wait_closed = mock.AsyncMock()
        writer.drain = mock.AsyncMock()
        task = asyncio.create_task(srv._accept(reader, writer))
        try:
            await asyncio.sleep(0)
            self.assertEqual(len(srv.conns), 1)
            with mock.patch.object(srv.store, "close") as close_store:
                await srv.stop()
                self.assertTrue(task.done(), "stop left the connection handler pending")
                self.assertFalse(srv.conns)
                writer.wait_closed.assert_awaited()
                close_store.assert_called_once()
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            srv.store.close()

    async def test_cancelled_tls_handshake_releases_connection_and_writer(self):
        srv = LobbyServer(Config(db=":memory:", name_blocklist=""))
        srv._late_tls = True
        writer = mock.Mock()
        writer.get_extra_info.return_value = ("127.0.0.1", 12345)
        writer.wait_closed = mock.AsyncMock()
        entered = asyncio.Event()

        async def handshake(*args, **kwargs):
            entered.set()
            await asyncio.Future()

        writer.start_tls = mock.AsyncMock(side_effect=handshake)
        task = asyncio.create_task(srv._accept(mock.Mock(), writer))
        try:
            await asyncio.wait_for(entered.wait(), 1.0)
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            self.assertFalse(srv.conns)
            self.assertFalse(srv.ip_conns)
            self.assertEqual(srv.handshakes, 0)
            writer.close.assert_called_once()
            writer.wait_closed.assert_awaited_once()
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            await srv.stop()

    async def test_tls_refusal_is_tracked_until_stream_cleanup_finishes(self):
        srv = LobbyServer(Config(db=":memory:", name_blocklist=""))
        srv._late_tls = True
        writer = mock.Mock()
        writer.start_tls = mock.AsyncMock()
        writer.drain = mock.AsyncMock()
        writer.wait_closed = mock.AsyncMock()
        try:
            srv._refuse(writer, "full", "server full", tell=True)
            tasks = list(srv._bg)
            self.assertEqual(len(tasks), 1, "TLS refusal cleanup was orphaned")
            await asyncio.gather(*tasks)
            writer.wait_closed.assert_awaited_once()
            self.assertEqual(srv.handshakes, 0)
        finally:
            await srv.stop()

    async def test_stop_closes_tls_refusal_cancelled_before_first_task_step(self):
        srv = LobbyServer(Config(db=":memory:", name_blocklist=""))
        srv._late_tls = True
        writer = mock.Mock()
        writer.start_tls = mock.AsyncMock()
        writer.drain = mock.AsyncMock()
        writer.wait_closed = mock.AsyncMock()
        srv._refuse(writer, "full", "server full", tell=True)

        await srv.stop()

        writer.close.assert_called()
        self.assertFalse(srv._bg)


if __name__ == "__main__":
    unittest.main()
