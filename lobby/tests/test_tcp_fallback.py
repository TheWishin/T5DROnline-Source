"""Loopback control-port recovery, without the game, remote hosts or certificate/key files.

The socket and lobby protocol are real. Only the TLS boundary is replaced: the tests inspect
the context/hostname and supply certificate bytes to exercise the real SHA-256 pin check.
Real TLS interoperability remains a deployment check (test_tls.py needs temporary key files).
"""
import asyncio
import hashlib
import socket
import ssl
import unittest
from unittest import mock

import util
from util import BUILD, LobbyClient, ServerThread, expect
from t5lobby import proto


CERT = b"loopback certificate stand-in; not a real certificate or key"
FP = hashlib.sha256(CERT).hexdigest()
OPEN_CONNECTION = asyncio.open_connection


class TlsWriter:
    def __init__(self, writer, certificate):
        self.writer = writer
        self.certificate = certificate

    def __getattr__(self, name):
        return getattr(self.writer, name)

    def get_extra_info(self, name, default=None):
        if name == "ssl_object":
            return self
        return self.writer.get_extra_info(name, default)

    def getpeercert(self, binary_form=False):
        assert binary_form
        return self.certificate


class TcpFallbackTest(unittest.TestCase):
    def setUp(self):
        self.s = ServerThread(reconnect_grace=8.0).start()
        self.clients = []
        self.listeners = []
        self.raw_writers = []
        self.attempts = []
        self.certificates = {}
        self.stalled_opens = set()

        async def open_tls(host, port, *, ssl=None, server_hostname=None, **kw):
            self.attempts.append((host, port, ssl, server_hostname))
            if port in self.stalled_opens:
                # A dropped SYN/TLS handshake: cancellable by the client's endpoint timeout.
                await asyncio.get_running_loop().create_future()
            reader, writer = await OPEN_CONNECTION(host, port, **kw)
            if ssl is not None:
                writer = TlsWriter(writer, self.certificates.get(port, CERT))
            return reader, writer

        self.open_patch = mock.patch("t5lobby.client.asyncio.open_connection", side_effect=open_tls)
        self.context_patch = mock.patch("t5lobby.client.ssl.create_default_context",
                                        side_effect=lambda: ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT))
        self.open_patch.start()
        self.context_patch.start()

    def tearDown(self):
        for c in self.clients:
            c.close()

        async def cleanup():
            for writer in self.raw_writers:
                writer.close()
            for listener in self.listeners:
                listener.close()
                await listener.wait_closed()

        asyncio.run_coroutine_threadsafe(cleanup(), self.s.loop).result(5)
        self.s.stop()
        self.context_patch.stop()
        self.open_patch.stop()

    def listen(self, handler=None):
        async def start():
            listener = await asyncio.start_server(handler or self.s.srv._accept, "127.0.0.1", 0)
            self.listeners.append(listener)
            return listener.sockets[0].getsockname()[1]
        return asyncio.run_coroutine_threadsafe(start(), self.s.loop).result(5)

    def make_client(self, primary=None, fallback=None, **kw):
        kw.setdefault("tls_fingerprint", FP)
        kw.setdefault("tcp_fallback_port", fallback if fallback is not None else self.listen())
        c = LobbyClient(f"127.0.0.1:{primary or self.s.srv.port}", BUILD, request_timeout=0.3,
                        nat2=False, relays=False, **kw)
        self.clients.append(c)
        return c

    def ports(self):
        return [attempt[1] for attempt in self.attempts]

    def assert_tls_preserved(self, pinned=True):
        for host, port, context, hostname in self.attempts:
            self.assertEqual(host, "127.0.0.1")
            self.assertEqual(hostname, host)
            self.assertIsInstance(context, ssl.SSLContext)
            self.assertEqual(context.verify_mode, ssl.CERT_NONE if pinned else ssl.CERT_REQUIRED)
            self.assertEqual(context.check_hostname, not pinned)

    def test_default_is_443_only_for_tls_and_never_duplicates_primary(self):
        self.assertEqual(LobbyClient("127.0.0.1:7781", BUILD, tls=True)._tcp_ports(), [7781, 443])
        self.assertEqual(LobbyClient("127.0.0.1:7781", BUILD)._tcp_ports(), [7781])
        self.assertEqual(LobbyClient("127.0.0.1:443", BUILD, tls=True)._tcp_ports(), [443])
        self.assertEqual(LobbyClient("127.0.0.1:7781", BUILD, tls=True,
                                     tcp_fallback_port=0)._tcp_ports(), [7781])

    def test_healthy_primary_does_not_try_fallback(self):
        c = self.make_client()
        c.connect(timeout=0.3)
        self.assertEqual(self.ports(), [self.s.srv.port])
        self.assert_tls_preserved()

    def test_refused_primary_uses_same_protocol_and_pinned_fallback(self):
        # A bound socket that does not listen reserves a port while refusing TCP connections.
        with socket.socket() as refused:
            refused.bind(("127.0.0.1", 0))
            port = refused.getsockname()[1]
            c = self.make_client(primary=port)
            welcome = c.connect(timeout=0.3)
        self.assertEqual(self.ports(), [port, c.tcp_fallback_port])
        self.assertEqual(c.tcp_port, c.tcp_fallback_port)
        self.assertEqual(welcome["udp_port"], self.s.srv.udp.port)
        c.login_guest("Alice")
        self.assertEqual(c.me["name"], "Alice")
        self.assert_tls_preserved()

    def test_silent_primary_exhausts_its_budget_then_falls_back(self):
        self.stalled_opens.add(self.s.srv.port)
        c = self.make_client()
        c.connect(timeout=0.05)
        self.assertEqual(self.ports(), [self.s.srv.port, c.tcp_fallback_port])
        self.assertTrue(c.connected)

    def test_hello_timeout_and_eof_use_fallback_without_disconnected_event(self):
        for close in (False, True):
            with self.subTest(close=close):
                async def no_welcome(reader, writer):
                    self.raw_writers.append(writer)
                    await reader.readuntil(b"\n")
                    if close:
                        writer.close()

                port = self.listen(no_welcome)
                c = self.make_client(primary=port)
                c.connect(timeout=0.3)
                self.assertEqual(c.tcp_port, c.tcp_fallback_port)
                self.assertIsNone(c.next_event(timeout=0, types="disconnected"))

    def test_ca_context_and_hostname_are_kept_on_fallback(self):
        self.stalled_opens.add(self.s.srv.port)
        c = self.make_client(tls=True, tls_fingerprint=None)
        c.connect(timeout=0.05)
        self.assert_tls_preserved(pinned=False)

    def test_wrong_fallback_pin_fails_before_hello(self):
        self.stalled_opens.add(self.s.srv.port)
        c = self.make_client()
        self.certificates[c.tcp_fallback_port] = b"a different certificate"
        with self.assertRaises(proto.LobbyError) as caught:
            c.connect(timeout=0.05)
        self.assertEqual(caught.exception.code, "tls_mismatch")
        self.assertFalse(c.connected)
        self.assertIsNone(c._loop)
        self.assertEqual(self.s.call(lambda: self.s.srv.counters["logins_guest"]), 0)

    def test_primary_pin_failure_does_not_retry_another_endpoint(self):
        c = self.make_client()
        self.certificates[self.s.srv.port] = b"a different certificate"
        with self.assertRaises(proto.LobbyError) as caught:
            c.connect(timeout=0.3)
        self.assertEqual(caught.exception.code, "tls_mismatch")
        self.assertEqual(self.ports(), [self.s.srv.port])

    def test_version_refusal_is_not_a_transport_retry(self):
        async def refuse(reader, writer):
            self.raw_writers.append(writer)
            hello = proto.decode(await reader.readuntil(b"\n"))
            writer.write(proto.encode({"t": "error", "code": proto.E_VERSION,
                                       "msg": "incompatible build", "re": hello["rid"]}))
            await writer.drain()

        port = self.listen(refuse)
        c = self.make_client(primary=port)
        with self.assertRaises(proto.LobbyError) as caught:
            c.connect(timeout=0.3)
        self.assertEqual(caught.exception.code, proto.E_VERSION)
        self.assertEqual(self.ports(), [port])

    def test_primary_cut_prefers_fallback_and_resumes_same_session(self):
        c = self.make_client()
        c.connect(timeout=0.3)
        c.login_guest("Alice")
        token, player = c.token, c.me["id"]
        # Inject the Windows reset into the real socket reader, after an established login.
        # The primary listener remains healthy: retrying it first would conceal this regression.
        c._loop.call_soon_threadsafe(c._reader.set_exception,
                                    ConnectionResetError(10054, "connection reset by peer"))
        expect(c, "reconnecting")
        expect(c, "reconnected", timeout=8)
        self.assertEqual(self.ports(), [self.s.srv.port, c.tcp_fallback_port])
        self.assertEqual((c.token, c.me["id"]), (token, player))
        self.assertEqual(c.tcp_port, c.tcp_fallback_port)
        self.assertEqual(self.s.call(lambda: len(self.s.srv.players)), 1)
        self.assertEqual(self.s.call(lambda: self.s.srv.counters["logins_guest"]), 1)
        self.assert_tls_preserved()

    def test_unavailable_fallback_can_resume_on_primary(self):
        c = self.make_client()
        c.connect(timeout=0.3)
        c.login_guest("Alice")
        # Reconnect's fallback is unavailable, but the original endpoint is still usable.
        # Use a refused socket so this test does not wait for a real handshake timeout.
        with socket.socket() as refused:
            refused.bind(("127.0.0.1", 0))
            c.tcp_fallback_port = refused.getsockname()[1]
            c._loop.call_soon_threadsafe(c._writer.transport.abort)
            expect(c, "reconnected", timeout=8)
        self.assertEqual(self.ports(), [self.s.srv.port, c.tcp_fallback_port, self.s.srv.port])
        self.assertEqual(c.tcp_port, self.s.srv.port)

    def test_account_resumes_on_fallback_without_resending_credentials(self):
        c = self.make_client()
        c.connect(timeout=0.3)
        c.register("Alice", "local-test-password", remember=True)
        token, player, remembered = c.token, c.me["id"], c.session
        resumes = []

        async def record_login(conn, msg):
            resumes.append((msg["mode"], set(msg)))
            return await original(conn, msg)

        original = self.s.srv.h_login
        self.s.call(setattr, self.s.srv, "h_login", record_login)
        c._loop.call_soon_threadsafe(c._writer.transport.abort)
        expect(c, "reconnected", timeout=8)
        self.assertEqual(c.tcp_port, c.tcp_fallback_port)
        self.assertEqual((c.token, c.me["id"], c.session), (token, player, remembered))
        self.assertEqual(resumes, [("resume", {"t", "mode", "token", "rid"})])
        self.assertEqual(self.s.call(lambda: self.s.srv.counters["logins_account"]), 1)
        self.assertFalse(c.me["guest"])

    def test_interrupted_state_change_is_failed_and_never_replayed(self):
        c = self.make_client()
        c.connect(timeout=0.3)
        c.login_guest("Alice")
        calls = []
        original = self.s.srv.h_room_create

        async def create_then_cut(conn, msg):
            calls.append(msg["rid"])
            reply = await original(conn, msg)
            # The server applied the action, but the reply cannot reach this client. Retrying
            # automatically would perform an action twice with an unknown first outcome.
            conn.writer.transport.abort()
            return reply

        self.s.call(setattr, self.s.srv, "h_room_create", create_then_cut)
        with self.assertRaises(proto.LobbyError) as caught:
            c.create_room("One room")
        self.assertEqual(caught.exception.code, "disconnected")
        expect(c, "reconnected", timeout=8)
        self.assertEqual(c.tcp_port, c.tcp_fallback_port)
        c.refresh()
        self.assertEqual(len(calls), 1)
        self.assertEqual(c._pending, {})


if __name__ == "__main__":
    unittest.main()
