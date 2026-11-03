"""TCP delay-proxy ownership, using in-memory readers and writers only."""
import asyncio
import importlib.util
from pathlib import Path
import unittest
from unittest import mock


SPEC = importlib.util.spec_from_file_location(
    "natsim_cleanup", Path(__file__).resolve().parents[1] / "tools" / "natsim.py",
)
natsim = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(natsim)


class ProxyCleanupTest(unittest.IsolatedAsyncioTestCase):
    def writer(self):
        writer = mock.Mock()
        writer.wait_closed = mock.AsyncMock()
        writer.is_closing.return_value = False
        return writer

    def proxy(self):
        proxy = natsim.TcpDelayProxy(("unused", 1), lambda: 0)
        proxy.server = mock.Mock()
        proxy.server.wait_closed = mock.AsyncMock()
        return proxy

    async def test_shutdown_closes_both_sides_and_joins_pending_pumps(self):
        proxy = self.proxy()
        client_writer, server_writer = self.writer(), self.writer()
        client_reader, server_reader = asyncio.StreamReader(), asyncio.StreamReader()
        with mock.patch.object(natsim.asyncio, "open_connection", mock.AsyncMock(
                return_value=(server_reader, server_writer))):
            await proxy._conn(client_reader, client_writer)
        # Let both pumps and their child writers block before shutdown.
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        await proxy.close()
        self.assertFalse(proxy.tasks)
        for writer in (client_writer, server_writer):
            writer.close.assert_called()
            writer.wait_closed.assert_awaited()
        proxy.server.wait_closed.assert_awaited_once()

    async def test_shutdown_closes_accepted_socket_during_upstream_connect(self):
        proxy = self.proxy()
        client_writer = self.writer()
        connecting = asyncio.Event()

        async def open_connection(*args):
            connecting.set()
            await asyncio.Future()

        with mock.patch.object(natsim.asyncio, "open_connection", open_connection):
            handler = asyncio.create_task(proxy._conn(asyncio.StreamReader(), client_writer))
            try:
                await connecting.wait()
                await proxy.close()
                client_writer.close.assert_called_once()
                client_writer.wait_closed.assert_awaited_once()
                self.assertTrue(handler.done())
            finally:
                handler.cancel()
                await asyncio.gather(handler, return_exceptions=True)

    async def test_shutdown_closes_writers_before_pumps_take_first_step(self):
        proxy = self.proxy()
        client_writer, server_writer = self.writer(), self.writer()
        with mock.patch.object(natsim.asyncio, "open_connection", mock.AsyncMock(
                return_value=(asyncio.StreamReader(), server_writer))):
            await proxy._conn(asyncio.StreamReader(), client_writer)
        await proxy.close()
        for writer in (client_writer, server_writer):
            writer.close.assert_called_once()
            writer.wait_closed.assert_awaited_once()
        self.assertFalse(proxy.tasks)

    async def test_already_accepted_callback_does_not_open_after_shutdown(self):
        proxy = self.proxy()
        await proxy.close()
        writer = self.writer()
        with mock.patch.object(natsim.asyncio, "open_connection", mock.AsyncMock()) as open_connection:
            await proxy._conn(asyncio.StreamReader(), writer)
        open_connection.assert_not_awaited()
        writer.close.assert_called_once()
        writer.wait_closed.assert_awaited_once()

    async def test_refused_upstream_waits_for_accepted_socket_to_close(self):
        proxy = self.proxy()
        client_writer = self.writer()
        with mock.patch.object(natsim.asyncio, "open_connection", mock.AsyncMock(
                side_effect=ConnectionRefusedError())):
            await proxy._conn(asyncio.StreamReader(), client_writer)
        client_writer.close.assert_called_once()
        client_writer.wait_closed.assert_awaited_once()

    async def test_eof_waits_for_writer_close_and_tolerates_reset(self):
        proxy = self.proxy()
        reader, writer = asyncio.StreamReader(), self.writer()
        reader.feed_eof()
        writer.wait_closed.side_effect = ConnectionResetError()
        await proxy._pump(reader, writer)
        await asyncio.gather(*proxy.tasks)
        writer.close.assert_called_once()
        writer.wait_closed.assert_awaited_once()

    async def test_shutdown_aborts_writer_whose_buffer_never_drains(self):
        proxy = self.proxy()
        proxy.close_timeout = 0.001
        writer = self.writer()

        async def wait_closed():
            await asyncio.Future()

        writer.wait_closed.side_effect = wait_closed
        proxy.writers.add(writer)
        await asyncio.wait_for(proxy.close(), 1)
        writer.close.assert_called_once()
        writer.transport.abort.assert_called_once()
        self.assertFalse(proxy.writers)

    async def test_cancelling_close_aborts_before_releasing_writer(self):
        proxy = self.proxy()
        writer = self.writer()
        waiting = asyncio.Event()

        async def wait_closed():
            waiting.set()
            await asyncio.Future()

        writer.wait_closed.side_effect = wait_closed
        proxy.writers.add(writer)
        closing = asyncio.create_task(proxy._close_writer(writer))
        await waiting.wait()
        closing.cancel()
        await asyncio.gather(closing, return_exceptions=True)
        writer.transport.abort.assert_called_once()
        self.assertFalse(proxy.writers)


if __name__ == "__main__":
    unittest.main()
