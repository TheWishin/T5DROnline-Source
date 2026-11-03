"""Additional control listener: local sockets only, no game or certificate/key files.

TLS is replaced at the StreamWriter boundary so these tests exercise shared protocol,
session and admission state while checking that both sockets use the same TLS context.
Actual certificate handshakes/pinning still need the existing TLS tests or deployment.
"""
import asyncio
import socket
import unittest
from unittest import mock

import util
from util import BUILD, FAST
from t5lobby import proto
from t5lobby.server import Config, LobbyServer
from t5lobby.server import lobby


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class TcpListenerTest(unittest.TestCase):
    def setUp(self):
        self.loop = proto.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.servers = []
        self.writers = []
        self.context = mock.Mock()
        self.ssl_patch = mock.patch.object(lobby.ssl, "create_default_context", return_value=self.context)
        self.ssl_patch.start()
        # Exercise the late-handshake path even when running this test on 3.10;
        # the final test explicitly covers start_server's older TLS path as well.
        self.version_patch = mock.patch.object(lobby.sys, "version_info", (3, 11))
        self.version_patch.start()
        self.addCleanup(self.version_patch.stop)
        self.tls_patch = mock.patch.object(asyncio.StreamWriter, "start_tls", create=True,
                                           new_callable=mock.AsyncMock)
        self.start_tls = self.tls_patch.start()
        self.addCleanup(self.ssl_patch.stop)
        self.addCleanup(self.tls_patch.stop)

    def tearDown(self):
        async def cleanup():
            for writer in self.writers:
                writer.close()
            for writer in self.writers:
                await writer.wait_closed()
            for srv in self.servers:
                await srv.stop()
            await asyncio.sleep(0)
        self.loop.run_until_complete(cleanup())
        self.loop.close()
        asyncio.set_event_loop(None)

    def server(self, **overrides):
        # Reserve both numbers together so the primary's ephemeral allocation cannot
        # accidentally choose the fallback's number and exercise the duplicate case.
        with socket.socket() as primary, socket.socket() as alternate:
            primary.bind(("127.0.0.1", 0))
            alternate.bind(("127.0.0.1", 0))
            cfg = dict(FAST, tls_cert="mock-cert", tls_key="mock-key")
            cfg.update(port=primary.getsockname()[1], tcp_fallback_port=alternate.getsockname()[1])
        cfg.update(overrides)
        srv = LobbyServer(Config(**cfg))
        self.servers.append(srv)
        return srv

    async def connection(self, port):
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        self.writers.append(writer)
        return reader, writer

    async def request(self, conn, msg):
        reader, writer = conn
        writer.write(proto.encode(dict(msg, rid=1)))
        await writer.drain()
        while True:
            line = await asyncio.wait_for(reader.readline(), 2)
            self.assertTrue(line, "control connection closed")
            reply = proto.decode(line)
            if reply.get("re") == 1 or reply["t"] == "error":
                return reply

    async def hello(self, conn):
        return await self.request(conn, {"t": "hello", "proto": proto.PROTO_VERSION, "build": BUILD.as_wire()})

    def test_default_disabled_and_environment_setting(self):
        self.assertEqual(Config().tcp_fallback_port, 0)
        self.assertEqual(Config.from_env({"T5L_TCP_FALLBACK_PORT": "443"}).tcp_fallback_port, 443)
        srv = self.server(tcp_fallback_port=0, tls_cert="", tls_key="")
        self.loop.run_until_complete(srv.start())
        self.assertIsNone(srv.tcp_fallback)
        self.assertEqual(srv.tcp_fallback_port, 0)
        self.context.load_cert_chain.assert_not_called()

    def test_both_ports_share_protocol_udp_and_session_resume(self):
        async def check():
            srv = self.server()
            await srv.start()
            a = await self.connection(srv.port)
            first = await self.hello(a)
            self.assertEqual(first["t"], "welcome")
            logged = await self.request(a, {"t": "login", "mode": "guest", "name": "Alice"})
            a[1].close()
            await a[1].wait_closed()
            for _ in range(100):
                if not srv.conns:
                    break
                await asyncio.sleep(0.01)
            self.assertFalse(srv.conns)
            b = await self.connection(srv.tcp_fallback_port)
            second = await self.hello(b)
            self.assertEqual(second["udp_port"], first["udp_port"])
            self.assertEqual(second["udp_port2"], first["udp_port2"])
            resumed = await self.request(b, {"t": "login", "mode": "resume", "token": logged["token"]})
            self.assertEqual(resumed["you"]["id"], logged["you"]["id"])
            self.assertEqual(len(srv.players), 1)
            self.assertEqual(self.start_tls.await_count, 2)
            for call in self.start_tls.await_args_list:
                self.assertIs(call.args[0], self.context)
                self.assertEqual(call.kwargs["ssl_handshake_timeout"], srv.cfg.tls_handshake_timeout)
            self.context.load_cert_chain.assert_called_once_with("mock-cert", "mock-key")
            with mock.patch.object(srv, "_tls_files_mtime", return_value=(1, 1)):
                self.assertTrue(srv.reload_tls(force=True))
            self.assertIs(srv.sslctx, self.context)
            self.assertEqual(self.context.load_cert_chain.call_count, 2)
            ports = (srv.port, srv.tcp_fallback_port)
            await srv.stop()
            for port in ports:
                with self.assertRaises(OSError):
                    await asyncio.wait_for(asyncio.open_connection("127.0.0.1", port), 1)
        self.loop.run_until_complete(check())

    def test_admission_limit_is_shared_between_ports(self):
        async def check():
            srv = self.server(max_per_ip=1)
            await srv.start()
            a = await self.connection(srv.port)
            await self.hello(a)
            b = await self.connection(srv.tcp_fallback_port)
            reply = proto.decode(await asyncio.wait_for(b[0].readline(), 2))
            self.assertEqual(reply["code"], proto.E_FULL)
            self.assertEqual(len(srv.conns), 1)
            # The refused socket uses the same context to report "server full",
            # while only the admitted socket becomes a Conn.
            self.assertEqual(self.start_tls.await_count, 2)
            self.assertIs(self.start_tls.await_args_list[1].args[0], self.context)
        self.loop.run_until_complete(check())

    def test_duplicate_port_is_one_listener(self):
        port = free_port()
        srv = self.server(port=port, tcp_fallback_port=port)
        self.loop.run_until_complete(srv.start())
        self.assertEqual(srv.port, port)
        self.assertEqual(srv.tcp_fallback_port, port)
        self.assertIsNone(srv.tcp_fallback)

    def test_fallback_requires_tls_and_valid_port(self):
        async def check():
            for cfg in ({"tls_cert": ""}, {"tcp_fallback_port": -1}, {"tcp_fallback_port": 65536}):
                srv = self.server(**cfg)
                with self.assertRaises(ValueError):
                    await srv.start()
                self.assertIsNone(srv.tcp)
                self.assertIsNone(srv.tcp_fallback)
                self.assertIsNone(srv.udp.main)
                self.assertIsNone(srv.tours._task)
        self.loop.run_until_complete(check())

    def test_failed_fallback_bind_closes_primary_and_started_tasks(self):
        async def check():
            with socket.socket() as busy:
                busy.bind(("127.0.0.1", 0))
                busy.listen()
                srv = self.server(tcp_fallback_port=busy.getsockname()[1])
                with self.assertRaises(OSError):
                    await srv.start()
                self.assertFalse(srv.tcp.is_serving())
                self.assertIsNone(srv.tcp_fallback)
                self.assertIsNone(srv.udp.main)
                self.assertIsNone(srv.tours._task)
                self.assertFalse(srv.tasks)
                with self.assertRaises(OSError):
                    await asyncio.wait_for(asyncio.open_connection("127.0.0.1", srv.port), 1)
        self.loop.run_until_complete(check())

    def test_older_python_passes_same_context_to_both_listeners(self):
        async def check():
            srv = self.server()
            real_start = asyncio.start_server
            calls = []

            async def record(callback, host, port, **kwargs):
                calls.append((callback, kwargs.copy()))
                # A context stand-in cannot perform encryption; preserve real local
                # binds and inspect the SSL arguments before stripping them.
                kwargs.pop("ssl")
                kwargs.pop("ssl_handshake_timeout")
                return await real_start(callback, host, port, **kwargs)

            with mock.patch.object(lobby.sys, "version_info", (3, 10)), \
                    mock.patch.object(asyncio, "start_server", side_effect=record):
                await srv.start()
            self.assertEqual(len(calls), 2)
            for callback, kwargs in calls:
                self.assertEqual(callback, srv._accept)
                self.assertIs(kwargs["ssl"], self.context)
                self.assertEqual(kwargs["ssl_handshake_timeout"], srv.cfg.tls_handshake_timeout)
                self.assertEqual(kwargs["limit"], proto.MAX_LINE + 2)
        self.loop.run_until_complete(check())


if __name__ == "__main__":
    unittest.main()
