"""Abuse and durability review for the public launch (docs/HOSTING.md "Abuse protection",
docs/RANKED.md "Results and match integrity"): one test (or a few) per issue found.

    ranked     lone desync claims, early/forged results, leaving after reporting, a "disconnect"
               against a finished game, repeat disputers, accounts on one address, lobby drops
    logins     parallel guesses, the name lockout and its owner, the password worker queue
    floods     unauthenticated connections, TLS handshakes that never finish
    messages   huge numbers, broken text (lone surrogates), expensive requests, lobby-wide chat
    names      look-alike names, reserved names in disguise, chat and room text
    relay      only game traffic, packet size, sessions per address, session lifetime
    durability crash mid-write, restart with running matches, drain, certificate pair, backups
"""
import json
import os
import random
import socket
import ssl
import subprocess
import sys
import tempfile
import textwrap
import threading
import time
import unittest

import util
from util import BUILD, ServerThread, client, expect
from t5lobby import proto
from t5lobby.proto import LobbyError
from t5lobby.server import backup as bk
from t5lobby.server import selfsigned
from t5lobby.server.fileutil import atomic_write
from t5lobby.server.store import Store

RAWS = []


class raw:
    """A bare control connection for misbehaving on purpose."""

    def __init__(self, s, timeout=5):
        self.sock = socket.create_connection(("127.0.0.1", s.srv.port), timeout=timeout)
        self.buf = b""
        RAWS.append(self)

    def send(self, msg):
        self.sock.sendall(proto.encode(msg) if isinstance(msg, dict) else msg)

    def recv(self, skip=("lobby_state", "lobby_delta", "notice", "server_notice")):
        while True:
            while b"\n" not in self.buf:
                try:
                    d = self.sock.recv(65536)
                except (ConnectionError, socket.timeout, OSError):
                    return None
                if not d:
                    return None
                self.buf += d
            line, self.buf = self.buf.split(b"\n", 1)
            m = json.loads(line)
            if m.get("t") not in skip:
                return m

    def login(self, name):
        self.send({"t": "hello", "proto": proto.PROTO_VERSION, "build": BUILD.as_wire()})
        assert self.recv()["t"] == "welcome"
        self.send({"t": "login", "mode": "guest", "name": name})
        r = self.recv()
        assert r["t"] == "login_ok", r
        return self

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


class Base(unittest.TestCase):
    server_cfg = {}

    def setUp(self):
        self.s = ServerThread(**self.server_cfg).start()
        self.clients = []

    def tearDown(self):
        for c in self.clients:
            c.close()
        while RAWS:
            RAWS.pop().close()
        self.s.stop()

    def c(self, name=None, password=None, register=False, **kw):
        from t5lobby.client import LobbyClient
        kw.setdefault("relay_bridge", False)       # the relay tests check the server's relay itself (util.client)
        c = LobbyClient(self.s.addr, BUILD, **kw)
        try:
            c.connect()
            if name:
                if register:
                    c.register(name, password)
                elif password:
                    c.login(name, password)
                else:
                    c.login_guest(name)
        except BaseException:
            c.close()                           # a refused login leaves no connection behind
            raise
        self.clients.append(c)
        return c

    def acc(self, name, **kw):
        return self.c(name, password="pw-" + name, register=True, auto_ready=True, **kw)

    def ranked(self, a, b):
        a.ranked_match()
        b.ranked_match()
        return expect(a, "match_start", 20.0), expect(b, "match_start", 20.0)

    def setup_match(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        ea, eb = self.ranked(a, b)
        return a, b, ea, eb

    def account(self, name):
        return self.s.call(lambda: dict(self.s.srv.store.account(name)))

    def cfg(self, **kw):
        def setall():
            for k, v in kw.items():
                setattr(self.s.srv.cfg, k, v)
        self.s.call(setall)

    @staticmethod
    def full(slot):
        return [3, 1] if slot == 0 else [1, 3]

    def no_event(self, c, types, seconds):
        ev = c.next_event(seconds, types)
        self.assertIsNone(ev, f"unexpected {ev}")


# ============================================================================== ranked manipulation
class DesyncClaimTest(Base):
    def test_lone_claim_waits_and_a_contradicted_claim_is_blamed(self):
        a, b, ea, eb = self.setup_match()
        # Alice is losing and says "desync" (a modified launcher; the stock one reports what the game counted)
        a.report_result(ea["slot"], None, source="game", desync=12, hash="1111")
        self.no_event(b, ("match_result",), 0.8)          # no longer voided on the spot
        b.report_result(eb["slot"], self.full(eb["slot"]), source="game", desync=0, hash="2222")
        ev = expect(a, "match_result")
        self.assertEqual((ev["status"], ev["reason"], ev["blame"]), ("void", "desync_claim", "you"))
        self.assertEqual(a.profile()["voids_24h"], 1)       # a strike
        self.assertEqual(self.account("Bob")["rating"], 1500)

    def test_claim_with_the_same_end_state_changes_nothing(self):
        a, b, ea, eb = self.setup_match()
        w = eb["slot"]
        a.report_result(w, self.full(w), source="game", desync=3, hash="abcd")
        b.report_result(w, self.full(w), source="game", desync=0, hash="abcd")
        ev = expect(a, "match_result")
        self.assertEqual((ev["status"], ev["winner"]), ("confirmed", w))

    def test_desync_both_games_saw_is_void_without_blame(self):
        a, b, ea, eb = self.setup_match()
        a.report_result(ea["slot"], None, source="game", desync=40)
        b.report_result(eb["slot"], None, source="game", desync=38)
        ev = expect(a, "match_result")
        self.assertEqual((ev["status"], ev["reason"], ev["blame"]), ("void", "desync", None))

    def test_repeated_lone_claims_turn_into_losses(self):
        self.cfg(strike_limit=1)
        a, b = self.acc("Alice"), self.acc("Bob")
        for expected in ("void", "forfeit"):
            ea, eb = self.ranked(a, b)
            a.report_result(ea["slot"], None, source="game", desync=5)
            b.report_result(eb["slot"], self.full(eb["slot"]), source="game", desync=0)
            ev = expect(b, "match_result")
            expect(a, "match_result")
            self.assertEqual(ev["status"], expected)
        self.assertEqual(self.account("Alice")["losses"], 1)


class EarlyReportTest(Base):
    """A lone report does not count against an opponent who is online and may still be fighting."""
    server_cfg = {"max_match_seconds": 6.0, "result_timeout": 1.0}

    def test_forged_early_win_costs_the_honest_player_nothing(self):
        a, b, ea, eb = self.setup_match()
        a.report_result(ea["slot"], self.full(ea["slot"]), source="game")    # "I won" a second into the match
        self.assertIsNone(b.next_event(2.5, ("match_result",)))             # before: a void + strike for Bob
        b.report_result(eb["slot"], self.full(eb["slot"]), source="game")    # Bob's game ends: he won
        ev = expect(b, "match_result")
        self.assertEqual(ev["status"], "disputed")
        self.assertIsNone(ev["blame"])
        self.assertEqual(b.profile()["voids_24h"], 0)

    def test_withheld_report_is_still_settled(self):
        a, b, ea, eb = self.setup_match()
        a.report_result(ea["slot"], self.full(ea["slot"]), source="game")
        ev = expect(a, "match_result", timeout=12)                          # T5L_MAX_MATCH_SECONDS after the start
        self.assertEqual((ev["status"], ev["reason"], ev["blame"]), ("void", "no_report", "opponent"))

    def test_lone_report_against_own_interest_needs_no_wait(self):
        a, b, ea, eb = self.setup_match()
        a.report_result(eb["slot"], None, source="game")
        ev = expect(a, "match_result", timeout=4)
        self.assertEqual(ev["status"], "onesided")


class LeaveAfterReportTest(Base):
    def test_winner_who_reported_and_logged_out_does_not_lose(self):
        a, b, ea, eb = self.setup_match()
        a.report_result(ea["slot"], self.full(ea["slot"]), source="game")
        time.sleep(0.3)
        a.close()                     # logs out: before, leave_match made the reported win a forfeit (a loss)
        ev = expect(b, "match_result", timeout=10)
        self.assertNotEqual(ev["status"], "forfeit")
        self.assertEqual(self.account("Alice")["losses"], 0)

    def test_winner_who_reported_and_lost_the_lobby_does_not_lose(self):
        a, b, ea, eb = self.setup_match()
        a.reconnect_window = 0
        a.report_result(ea["slot"], self.full(ea["slot"]), source="game")
        time.sleep(0.3)
        a._loop.call_soon_threadsafe(a._writer.transport.abort)
        ev = expect(b, "match_result", timeout=10)
        self.assertNotEqual((ev["status"], ev["reason"]), ("forfeit", "disconnect"))
        self.assertEqual(self.account("Alice")["losses"], 0)


class DisconnectReportTest(Base):
    def test_disconnect_against_a_finished_game_counts(self):
        a, b, ea, eb = self.setup_match()
        a.report_result(None, None, source="disconnect", reason="peer_timeout")     # the loser's way out
        b.report_result(eb["slot"], self.full(eb["slot"]), source="game", desync=0)
        ev = expect(a, "match_result")
        self.assertEqual((ev["status"], ev["winner"], ev["reason"]), ("onesided", eb["slot"], "disconnect"))
        self.assertEqual(self.account("Alice")["losses"], 1)

    def test_disconnect_against_an_unfinished_game_is_void(self):
        a, b, ea, eb = self.setup_match()
        a.report_result(None, None, source="disconnect")
        b.report_result(eb["slot"], [2, 1] if eb["slot"] == 0 else [1, 2], source="game", desync=0)
        ev = expect(a, "match_result")
        self.assertEqual((ev["status"], ev["reason"], ev["blame"]), ("void", "connection", None))

    def test_connection_void_blames_the_side_that_lost_the_lobby(self):
        a, b, ea, eb = self.setup_match()
        a._loop.call_soon_threadsafe(a._writer.transport.abort)     # Alice's internet goes ...
        expect(a, "reconnected", timeout=15)                         # ... and comes back
        a.report_result(None, None, source="disconnect", match_id=ea["match"])
        b.report_result(None, None, source="disconnect")
        ev = expect(a, "match_result")
        self.assertEqual((ev["status"], ev["reason"], ev["blame"]), ("void", "connection", "you"))


class DisputeRepeatTest(Base):
    server_cfg = {"dispute_limit": 1}

    def test_the_repeat_disputer_loses(self):
        a, b, c = self.acc("Alice"), self.acc("Bob"), self.acc("Carol")
        ea, eb = self.ranked(a, b)
        a.report_result(ea["slot"], None, source="game")
        b.report_result(eb["slot"], None, source="game")
        self.assertEqual(expect(a, "match_result")["status"], "disputed")
        expect(b, "match_result")
        ea, ec = self.ranked(a, c)
        a.report_result(ea["slot"], None, source="game")             # Alice disputes again, Carol never did
        c.report_result(ec["slot"], None, source="game")
        ev = expect(c, "match_result")
        self.assertEqual((ev["status"], ev["reason"], ev["winner"]), ("forfeit", "dispute_repeat", ec["slot"]))

    def test_forged_hash_is_a_dispute_not_a_desync(self):
        a, b, ea, eb = self.setup_match()
        a.report_result(ea["slot"], None, source="game", desync=0, hash="f00d")
        b.report_result(eb["slot"], self.full(eb["slot"]), source="game", desync=0, hash="beef")
        ev = expect(a, "match_result")
        self.assertEqual((ev["status"], ev["reason"]), ("disputed", "hash_mismatch"))


class SameAddressTest(Base):
    server_cfg = {"ranked_same_ip": False}

    def test_ranked_queue_never_pairs_one_address(self):
        a, b = self.acc("Alice"), self.acc("Bob")       # both on 127.0.0.1: one household, or one player's alt
        a.ranked_match()
        b.ranked_match()
        self.assertIsNone(a.next_event(3.0, ("match_found",)))
        a.cancel_queue()
        b.cancel_queue()
        a.quick_match()
        b.quick_match()
        self.assertFalse(expect(a, "match_found")["ranked"])

    def test_ranked_room_on_one_address_is_unranked(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        r = a.create_room("dojo", ranked=True)
        b.join_room(r["id"])
        ev = expect(a, "match_found")
        self.assertFalse(ev["ranked"])
        self.assertEqual(expect(a, "notice")["code"], "same_address")


# ============================================================================== logins
class LoginAbuseTest(Base):
    server_cfg = {"max_per_ip": 32, "conn_burst": 100, "conn_rate": 50.0, "scrypt_n": 1 << 14}

    def wrong_logins(self, n):
        conns = []
        for _ in range(n):
            r = raw(self.s, timeout=20)
            r.send({"t": "hello", "proto": proto.PROTO_VERSION, "build": BUILD.as_wire()})
            assert r.recv()["t"] == "welcome"
            conns.append(r)
        for r in conns:                    # all at once, on separate connections
            r.send({"t": "login", "mode": "account", "name": "Victim", "password": "guess-123"})
        return [r.recv()["code"] for r in conns]

    def test_parallel_guesses_cannot_pass_the_limit(self):
        self.acc("Victim")
        codes = self.wrong_logins(12)
        self.assertLessEqual(codes.count(proto.E_AUTH), 5)      # 5, then one a minute; before: all 12 checked
        self.assertIn(proto.E_RATE, codes)

    def test_name_lockout_spares_an_address_the_account_used(self):
        v = self.acc("Victim")
        v.close()
        self.s.call(lambda: self.s.srv.good_logins.clear())
        for _ in range(5):
            self.s.call(lambda: self.s.srv.login_fail.take("name:victim"))    # someone elsewhere guessed 5 times
        with self.assertRaises(LobbyError) as cm:
            self.c("Victim", password="pw-Victim")
        self.assertEqual(cm.exception.code, proto.E_RATE)
        self.s.call(lambda: self.s.srv.good_logins.setdefault("victim", {}).update({"127.0.0.1": time.monotonic()}))
        self.c("Victim", password="pw-Victim")                             # the owner's own address still works

    def test_password_changes_are_rate_limited(self):
        """A logged-in account with its own (right) password used to be able to keep the server's password
        hashing busy for everybody (two scrypt runs per change, nothing counted a success)."""
        v = self.acc("Victim")
        pw = ["pw-Victim", "pw-Second", "pw-Third", "pw-Fourth"]
        for i in range(3):
            v.change_password(pw[i], pw[i + 1])
        hashed = self.s.call(lambda: self.s.srv.pw_waiting)
        with self.assertRaises(LobbyError) as cm:
            v.change_password(pw[3], "pw-Fifth")
        self.assertEqual(cm.exception.code, proto.E_RATE)
        with self.assertRaises(LobbyError) as cm:
            v.new_recovery_codes(pw[3])                              # the same budget
        self.assertEqual(cm.exception.code, proto.E_RATE)
        self.assertEqual(self.s.call(lambda: self.s.srv.pw_waiting), hashed)

    def test_password_work_is_queued_with_a_bound(self):
        self.acc("Victim")
        self.cfg(pw_concurrency=1, pw_queue=2, scrypt_n=1 << 15)
        self.s.call(lambda: self.s.srv.login_fail.b.clear())
        codes = self.wrong_logins(5)
        self.assertIn(proto.E_RATE, codes)
        self.assertGreaterEqual(self.s.call(lambda: self.s.srv.counters.get("pw_busy", 0)), 1)


# ============================================================================== every message type, fuzzed
class MessageFuzzTest(unittest.TestCase):
    """Every handler (h_*) gets random fields of random types -- None, huge and negative numbers, NaN,
    paths, 5000-character and broken Unicode strings, nested lists and objects, the ids of real matches --
    from two logged-in players. Expected: each bad request is a polite error ("bad field" and the like),
    never an exception the dispatcher did not foresee, and the server keeps serving. (A longer run during
    the security audit, 100,000 messages: 10 matches formed on the way, no unforeseen exception.)"""

    def test_random_messages(self):
        import asyncio
        import re
        from t5lobby.server.ratelimit import TokenBucket
        s = ServerThread(conn_rate=1000.0, conn_burst=1000, max_per_ip=100, max_prelogin=100).start()
        clients = []
        try:
            src_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "t5lobby",
                                    "server", "lobby.py")
            with open(src_path, encoding="utf-8") as f:
                src = f.read()
            handlers = sorted(set(re.findall(r"async def h_(\w+)\(", src)) - {"logout"})
            fields = sorted(set(re.findall(r'msg(?:\.get\(|\[)"(\w+)"', src)))
            rng = random.Random(20261019)

            def value(depth=0):
                k = rng.randrange(12)
                if k == 0:
                    return None
                if k == 1:
                    return rng.choice([0, 1, -1, 3, 2 ** 31, 2 ** 63, -2 ** 63, 10 ** 30])
                if k == 2:
                    return rng.choice([0.5, -1.0, 1e308, float("nan"), float("inf")])
                if k == 3:
                    return rng.choice(["", "x", "m1", "..\\..\\x", "a" * 5000, "\u202e\u0000\ud800", "random", "jin",
                                       "s20", "ranked", "quick", "host", "relay", "Alice"])
                if k == 4 and depth < 3:
                    return [value(depth + 1) for _ in range(rng.randrange(5))]
                if k == 5 and depth < 3:
                    return {rng.choice(fields): value(depth + 1) for _ in range(rng.randrange(4))}
                if k == 6:
                    return [[rng.choice(["10.0.0.1", "127.0.0.1", "8.8.8.8", "x"]), rng.randrange(-5, 70000)]
                            for _ in range(rng.randrange(12))]
                if k == 7:
                    return {"usw": rng.random() * 100, "main": -1, "x": "y"}
                if k == 8:
                    return rng.randrange(-3, 6)
                if k == 9:
                    return ["127.0.0.1", rng.randrange(-5, 70000)]
                return rng.choice(["m", "p", "r", "c", "s"]) + os.urandom(6).hex()

            def login_all():
                for c in clients:
                    c.close()
                clients.clear()
                for name in ("Alice", "Bob"):
                    clients.append(client(s, name))

            login_all()
            unforeseen = []
            sent = 0
            for _ in range(3000):
                live = s.call(lambda: {c.player.name: c for c in s.srv.conns if c.player is not None})
                if len(live) < 2:
                    login_all()
                    continue
                conn = live[rng.choice(sorted(live))]
                msg = {"t": rng.choice(handlers)}
                for _ in range(rng.randrange(6)):
                    msg[rng.choice(fields)] = value()
                if rng.random() < 0.3:
                    mid = s.call(lambda: next(iter(s.srv.matches), None))
                    if mid:
                        msg["match"] = mid
                line = proto.encode(msg)

                async def go(conn=conn, line=line, msg=msg):
                    conn.heavy = TokenBucket(1e9, 1e9)      # (the rate limits are tested elsewhere)
                    conn.state = TokenBucket(1e9, 1e9)
                    conn.errors = 0
                    try:
                        await s.srv._dispatch(conn, line)
                    except Exception as e:                  # noqa: BLE001 -- what this test looks for
                        unforeseen.append((msg["t"], repr(e)[:200]))
                asyncio.run_coroutine_threadsafe(go(), s.loop).result(10)
                sent += 1
            self.assertEqual(unforeseen, [])
            self.assertGreater(sent, 2500)
            login_all()                                        # still serving
            self.assertEqual(clients[0].me["name"], "Alice")
        finally:
            for c in clients:
                c.close()
            s.stop()


# ============================================================================== UDP control packets
class UdpTotalTest(unittest.TestCase):
    """The server-wide cap on UDP control packets (T5L_UDP_CTL_PPS) is there against reflection: only the
    ping is answered to anybody. A spoofed flood that uses it up must not stop registrations and relay binds,
    which are answered only for a token the server handed out."""

    class Lobby:
        def __init__(self, token):
            self.token = token
            self.bound = []

        def udp_register(self, token, addr, probe):
            return token == self.token

        def udp_relay_bound(self, sid, side, addr):
            self.bound.append((sid, side, addr))

    class Transport:
        def __init__(self):
            self.sent = []

        def sendto(self, data, addr):
            self.sent.append((data, addr))

    def test_flood_of_pings_does_not_block_registration_and_binds(self):
        from t5lobby.server import Config
        from t5lobby.server.ratelimit import TokenBucket
        from t5lobby.server.udp import UdpService
        tok = proto.new_token()
        lobby = self.Lobby(tok)
        svc = UdpService(lobby, Config(db=":memory:"))
        svc.ctl_global = TokenBucket(0.001, 1)
        svc.ctl_global.take()                                        # the total is used up (a spoofed flood)
        tr = self.Transport()
        svc.on_datagram(0, tr, proto.pk_ping(proto.U_SPING, 1, 1.0), ("198.51.100.7", 4000))
        self.assertEqual(tr.sent, [])                                # pings: not answered now
        svc.on_datagram(0, tr, proto.pk_token(proto.U_REGISTER, tok), ("198.51.100.8", 4001))
        self.assertEqual(proto.un_token_ack(tr.sent[-1][0])[0], proto.U_REG_ACK)
        rtok = [proto.new_token(), proto.new_token()]
        svc.open_relay("m1", rtok)
        svc.on_datagram(0, tr, proto.pk_token(proto.U_RELAY_BIND, rtok[0]), ("198.51.100.9", 4002))
        self.assertEqual(proto.un_token_ack(tr.sent[-1][0])[0], proto.U_RELAY_ACK)
        self.assertEqual(lobby.bound, [("m1", 0, ("198.51.100.9", 4002))])
        n = len(tr.sent)
        svc.on_datagram(0, tr, proto.pk_token(proto.U_REGISTER, proto.new_token()), ("198.51.100.10", 4003))
        self.assertEqual(len(tr.sent), n)                            # an unknown token gets nothing


# ============================================================================== connection floods
class FloodTest(Base):
    server_cfg = {"max_prelogin": 3, "max_per_ip": 32, "conn_burst": 100}

    def test_unauthenticated_connections_are_capped(self):
        idle = [raw(self.s) for _ in range(3)]
        time.sleep(0.3)
        extra = raw(self.s)
        m = extra.recv()
        self.assertEqual((m["code"], m["msg"]), (proto.E_FULL, "server busy, try again in a moment"))
        idle[0].login("Late")            # a connection that logs in no longer counts
        time.sleep(0.2)
        raw(self.s).login("Next")


class SlowReaderTest(Base):
    server_cfg = {"max_pending_kb": 64}

    def sloth(self):
        r = raw(self.s)
        r.login("Sloth")                                   # ... and from now on it reads nothing
        return r, self.s.call(lambda: next(c for c in self.s.srv.conns if c.player and c.player.name == "Sloth"))

    def test_a_client_that_never_reads_is_dropped_and_frees_its_slot(self):
        r, c = self.sloth()

        def flood():
            for _ in range(200):
                c.send_raw(b'{"t":"chat","text":"' + b"x" * 1000 + b'"}\n')
        self.s.call(flood)
        # Gone on the server -- connection, player and the address's slot -- although the peer never
        # closed its socket.
        self.assertTrue(self.s.wait_for(lambda: len(self.s.srv.conns) == 0 and not self.s.srv.ip_conns, 5))
        self.assertGreaterEqual(self.s.call(lambda: self.s.srv.counters["dropped_slow_readers"]), 1)
        self.c("Next")

    def test_a_peer_that_never_takes_its_data_cannot_hold_the_connection(self):
        # A peer with a zero TCP window: every write waits in drain() for good (simulated: on Windows'
        # loopback the kernel buffers absorb anything a test can send). The graceful close used to wait
        # for that writer for ever -- connection, player and address slot never came back.
        r, c = self.sloth()
        asyncio_event = None

        def jam():
            import asyncio
            nonlocal asyncio_event
            asyncio_event = asyncio.Event()
            c.writer.drain = asyncio_event.wait            # never set
            c.send_raw(b'{"t":"pong"}\n')
        self.s.call(jam)
        time.sleep(0.2)
        r.close()                                          # the reader side ends; the writer is still jammed
        self.assertTrue(self.s.wait_for(lambda: len(self.s.srv.conns) == 0 and not self.s.srv.ip_conns, 15))


class TlsHandshakeTest(unittest.TestCase):
    """With TLS the handshake used to run before any limit (60 s each, uncounted): a slowloris held
    sockets for free. Now it starts after the address checks and has its own timeout."""

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp(prefix="t5tls")
        cls.cert, cls.key, cls.fp = selfsigned.write_pair(cls.dir, "lobby.test", days=30)

    def test_stalled_handshakes_count_and_time_out(self):
        if sys.version_info < (3, 11):
            self.skipTest("late TLS needs Python 3.11 (3.10: handshake timeout only)")
        s = ServerThread(tls_cert=self.cert, tls_key=self.key, max_per_ip=3, tls_handshake_timeout=1.0).start()
        try:
            stalled = [socket.create_connection(("127.0.0.1", s.srv.port), timeout=5) for _ in range(3)]
            time.sleep(0.3)
            extra = socket.create_connection(("127.0.0.1", s.srv.port), timeout=9)
            t0 = time.monotonic()
            for st in stalled:
                self.assertEqual(st.recv(10), b"")                # closed by the server ...
            self.assertLess(time.monotonic() - t0, 4.0)           # ... after the 1 s handshake timeout
            self.assertEqual(extra.recv(10), b"")                 # refused (three from here already), closed
            self.assertGreaterEqual(s.call(lambda: s.srv.counters["refused_connections"]), 1)
            c = client(s, "Tess", tls_fingerprint=self.fp)        # a real client gets in now
            c.close()
            for st in stalled + [extra]:
                st.close()
        finally:
            s.stop()


# ============================================================================== messages
class MessageAbuseTest(Base):
    def test_huge_numbers_keep_the_connection(self):
        r = raw(self.s).login("Numbers")
        r.send({"t": "leaderboard", "offset": 10 ** 40, "rid": 1})    # before: OverflowError, the task died
        self.assertEqual(r.recv()["rows"], [])
        r.send({"t": "ping", "rid": 3})
        self.assertEqual(r.recv()["t"], "pong")

    def test_an_unforeseen_error_keeps_the_connection(self):
        r = raw(self.s).login("Oddball")

        async def broken(conn, msg):
            raise RuntimeError("nobody thought of this")
        self.s.call(lambda: setattr(self.s.srv, "h_blocks", broken))
        r.send({"t": "blocks", "rid": 1})
        self.assertEqual(r.recv()["code"], proto.E_BAD_REQUEST)
        r.send({"t": "ping", "rid": 2})
        self.assertEqual(r.recv()["t"], "pong")

    def test_broken_text_in_a_build_name_does_not_stop_the_lobby(self):
        w = self.c("Watcher")
        bad = raw(self.s)
        wire = dict(BUILD.as_wire(), release="x")
        surrogate = b'"release":"' + bytes([92]) + b'ud800"'          # \ud800: valid JSON, not encodable as UTF-8
        line = proto.encode({"t": "hello", "proto": proto.PROTO_VERSION, "build": wire}).replace(
            b'"release":"x"', surrogate)
        bad.send(line)
        self.assertEqual(bad.recv()["t"], "welcome")
        bad.send({"t": "login", "mode": "guest", "name": "Breaker"})
        self.assertEqual(bad.recv()["t"], "login_ok")
        # every other client keeps getting lobby updates, with the newcomer in them
        for name in ("Breaker", "Later"):
            if name == "Later":
                self.c("Later")
            t_end = time.monotonic() + 5
            while time.monotonic() < t_end and not any(p["name"] == name for p in w.players):
                time.sleep(0.05)
            self.assertTrue(any(p["name"] == name for p in w.players), name)

    def test_expensive_requests_are_rate_limited(self):
        self.cfg(heavy_rate=0.5, heavy_burst=3)
        r = raw(self.s).login("Curious")
        codes = []
        for i in range(8):
            r.send({"t": "leaderboard", "rid": i})
            m = r.recv()
            codes.append(m.get("code") or m["t"])
        self.assertEqual(codes[:3], ["leaderboard"] * 3)
        self.assertIn(proto.E_RATE, codes)
        r.send({"t": "ping", "rid": 99})
        self.assertEqual(r.recv()["t"], "pong")                     # still connected

    def test_lobby_wide_chat_cap(self):
        from t5lobby.server.ratelimit import TokenBucket
        self.s.call(lambda: setattr(self.s.srv, "chat_total", TokenBucket(1.0, 2.0)))
        a, b, c = self.c("Ann"), self.c("Ben"), self.c("Cid")
        for x in (a, b, c):
            for _ in range(3):
                x.chat("hello")
        time.sleep(0.5)
        n = self.s.call(lambda: self.s.srv.counters["chat_lines"])
        self.assertLessEqual(n, 3)                                   # burst 2 + about one a second


# ============================================================================== names and text
class NameRulesTest(Base):
    server_cfg = {"conn_burst": 50}

    def test_look_alike_names_are_refused(self):
        self.acc("Wishin")
        for name in ("W1shin", "WIshin", "Wish.in", "wishln"):
            with self.assertRaises(LobbyError) as cm:
                self.c(name)
            self.assertEqual(cm.exception.code, proto.E_NAME_TAKEN, name)
        with self.assertRaises(LobbyError) as cm:
            self.c("Wish-in", password="pw-xxxxx", register=True)
        self.assertEqual(cm.exception.code, proto.E_NAME_TAKEN)
        self.c("Kazuya")                                             # a guest online ...
        with self.assertRaises(LobbyError):
            self.c("Kazuya.", password="pw-xxxxx", register=True)        # ... cannot be copied either
        self.c("Kazuya2")                                            # a different name is fine

    def test_reserved_names_in_disguise(self):
        for name in ("Adm1n", "M0derat0r", "5ystem", "0fficial_TV", "Serv3r"):
            with self.assertRaises(LobbyError) as cm:
                self.c(name)
            self.assertEqual(cm.exception.code, proto.E_BAD_NAME, name)

    def test_existing_look_alike_accounts_still_log_in(self):
        from t5lobby.server.store import hash_password
        pw = hash_password("secret-1", 1 << 10)
        self.s.call(lambda: (self.s.srv.store.create_account("Paul", pw), self.s.srv.store.create_account("PauI", pw)))
        self.c("Paul", password="secret-1").close()
        self.c("PauI", password="secret-1")

    def test_chat_and_room_text_are_cleaned(self):
        a, b = self.c("Ann"), self.c("Ben")
        rlo, acute, zwsp = chr(0x202E), chr(0x301), chr(0x200B)
        a.chat("hi" + rlo + "dlrow A" + acute * 50 + chr(7) + "!")
        ev = expect(b, "chat")
        self.assertEqual(ev["text"], "hidlrow A" + acute * 2 + "!")
        room = a.create_room("my" + rlo + "room" + zwsp)
        self.assertEqual(room["name"], "myroom")


class HelperTest(unittest.TestCase):
    def test_address_keys(self):
        self.assertEqual(proto.address_key("2001:db8:1:2:3:4:5:6"), "2001:db8:1:2::/64")
        self.assertEqual(proto.address_key("2001:db8:1:2:ffff::1"), proto.address_key("2001:db8:1:2::9"))
        self.assertEqual(proto.address_key("::ffff:10.1.2.3"), "10.1.2.3")
        self.assertEqual(proto.address_key("192.0.2.7"), "192.0.2.7")

    def test_skeletons(self):
        same = ["Wishin", "Wish-in", "W1shin", "WIshin", "wishln", "W i s h i n"]
        self.assertEqual(len({proto.name_skeleton(n) for n in same}), 1)
        self.assertNotEqual(proto.name_skeleton("Wishin"), proto.name_skeleton("Wishing"))
        self.assertEqual(proto.name_skeleton("Ma rn"), proto.name_skeleton("Mam"))
        self.assertFalse(proto.reserved_name("Hostile"))
        self.assertFalse(proto.reserved_name("Tekken Fan"))

    def test_unencodable_text_never_breaks_a_message(self):
        self.assertEqual(proto.encode({"x": "a" + chr(0xD800) + "b"}), b'{"x":"a?b"}' + b"\n")


# ============================================================================== relay
class RelayAbuseTest(Base):
    server_cfg = {"force_relay": True}

    def relayed_pair(self, na="Alice", nb="Bob"):
        a = self.c(na, auto_ready=True)
        b = self.c(nb, auto_ready=True)
        a.quick_match()
        b.quick_match()
        ta, tb = expect(a, "match_start")["ticket"], expect(b, "match_start")["ticket"]
        self.assertEqual(ta.path, "relay")
        return a, b, ta, tb

    def socks(self, *tickets):
        out = []
        for t in tickets:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.bind((util.GAME_IP, t.local_port))
            proto.disable_udp_connreset(s)
            s.settimeout(0.4)
            out.append(s)
        return out

    def test_relay_carries_game_traffic_only(self):
        a, b, ta, tb = self.relayed_pair()
        sa, sb = self.socks(ta, tb)
        try:
            sa.sendto(b"T5NP" + b"\x02" * 100, ta.peer)                    # game traffic: forwarded
            self.assertTrue(sb.recvfrom(4096)[0].startswith(b"T5NP"))
            sa.sendto(b"GET / HTTP/1.1\r\nHost: example.org\r\n\r\n", ta.peer)    # a tunnel: dropped
            sa.sendto(b"T5NP" + b"\x00" * 4000, ta.peer)                   # larger than netplay ever sends
            with self.assertRaises(socket.timeout):
                sb.recvfrom(8192)
            self.assertEqual(self.s.call(lambda: self.s.srv.udp.stats["relay_refused"]), 2)
        finally:
            sa.close()
            sb.close()

    def test_relay_sessions_per_address(self):
        self.cfg(max_relays_per_ip=1)
        self.relayed_pair()
        c = self.c("Cid", auto_ready=True)
        d = self.c("Dee", auto_ready=True)
        c.quick_match()
        d.quick_match()
        ev = expect(c, ("match_cancel", "match_start"), 20)
        self.assertEqual((ev["t"], ev.get("reason")), ("match_cancel", "relay_full"))

    def test_relay_closes_when_its_match_has_run_too_long(self):
        self.relayed_pair()
        self.assertEqual(self.s.call(lambda: len(self.s.srv.udp.relays)), 1)
        self.cfg(relay_max_seconds=0.5)
        time.sleep(0.8)
        self.s.call(self.s.srv._expire_long_relays)
        self.assertEqual(self.s.call(lambda: len(self.s.srv.udp.relays)), 0)


# ============================================================================== ranked sets (best of 3)
class SetAbuseTest(Base):
    """A player behind in a ranked set must not be able to end it without a loss by making the next
    game's connection setup fail: the server's own evidence (UDP registration, the relay's view of
    who pings and who answers) names the side that failed, and that side loses the set. A void only
    when it cannot be told."""
    server_cfg = {"set_next_seconds": 0.3, "register_timeout": 2.0, "relay_timeout": 5.0}

    def acc(self, name, **kw):
        return self.c(name, password="pw-" + name, register=True, auto_ready=True, sets=True, **kw)

    def lead(self, a, b):
        """Alice wins game 1 of a ranked set against Bob: 1-0."""
        ea, eb = self.ranked(a, b)
        self.assertTrue(ea["set"]["rated"])
        w = ea["slot"]
        for c, e in ((a, ea), (b, eb)):
            c.report_result(w, self.full(w), match_id=e["match"], source="game", desync=0)
        expect(a, "match_result")
        expect(b, "match_result")
        return ea, eb

    @staticmethod
    def block_udp(c):
        async def ignore(msg):
            return False                   # the game socket never contacts the server (firewall, on purpose)
        c._on_nat_begin = ignore

    @staticmethod
    def mute_on_relay(c):
        async def stall(msg):
            gs = c._gs
            real = gs.datagram_received

            def ack_only(data, addr):
                # Muted from the start: only the relay's bind acknowledgement gets through. (Muted after the bind,
                # a loaded PC let the peer's first ping in meanwhile; one pong made the server unable to tell who
                # failed, and the set ended void instead of a loss.)
                if proto.udp_type(data) == proto.U_RELAY_ACK:
                    real(data, addr)
            gs.datagram_received = ack_only
            await gs.relay_bind((c.server_ip, int(msg["udp_port"])))
            gs.datagram_received = lambda data, addr: None   # bound, but answers nothing and reports nothing
        c._nat_relay = stall

    def test_blocked_udp_in_the_next_game_loses_the_set(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        self.lead(a, b)
        self.block_udp(b)                      # Bob is behind: game 2 can never connect
        sb = expect(b, "set_end", 15)
        self.assertEqual((sb["reason"], sb["status"], sb["result"], sb["by"]), ("no_connection", "forfeit", "loss", "you"))
        sa = expect(a, "set_end", 5)
        self.assertEqual((sa["status"], sa["result"]), ("forfeit", "win"))
        self.assertGreater(sa["rating"]["delta"], 0)
        self.assertEqual(self.account("Bob")["losses"], 1)

    def test_not_answering_through_the_relay_loses_the_set(self):
        self.cfg(force_relay=True)
        a, b = self.acc("Alice"), self.acc("Bob")
        self.lead(a, b)
        self.mute_on_relay(b)
        sb = expect(b, "set_end", 20)
        self.assertEqual((sb["reason"], sb["status"], sb["result"]), ("no_connection", "forfeit", "loss"))
        self.assertEqual(expect(a, "set_end", 5)["result"], "win")

    def test_a_failed_setup_nobody_can_be_blamed_for_is_void(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        self.lead(a, b)
        self.block_udp(a)
        self.block_udp(b)                      # neither side reaches the server: cannot be told
        sb = expect(b, "set_end", 15)
        self.assertEqual((sb["status"], sb["result"], sb["rating"]), ("void", None, None))
        self.assertEqual(self.account("Alice")["rating"], 1500)

    def test_a_contradicted_desync_claim_in_a_later_game_loses_the_set(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        self.lead(a, b)
        ea, eb = expect(a, "match_start", 20), expect(b, "match_start", 20)
        b.report_result(eb["slot"], None, match_id=eb["match"], source="game", desync=9)   # Bob, behind: "desync"
        a.report_result(ea["slot"], self.full(ea["slot"]), match_id=ea["match"], source="game", desync=0)
        sb = expect(b, "set_end", 10)
        self.assertEqual((sb["status"], sb["result"], sb["outcome_reason"]), ("forfeit", "loss", "desync_claim"))

    def test_relay_evidence(self):
        from types import SimpleNamespace
        from t5lobby.server.udp import RelaySession
        srv = self.s.srv
        p0, p1 = SimpleNamespace(name="P0"), SimpleNamespace(name="P1")

        def culprit(ep, pings=(0, 0), pongs=(0, 0), pkts=(0, 0), reason="no_connection", by=None, state="relay"):
            s = RelaySession("m1", [b"a" * 16, b"b" * 16], 100, 100)
            s.ep, s.pings, s.pongs, s.pkts = list(ep), list(pings), list(pongs), list(pkts)
            m = SimpleNamespace(relay=s, state=state, players=[p0, p1])
            return srv._setup_culprit(m, reason, by)
        e = ("127.0.0.1", 5000)
        self.assertIs(culprit([e, None]), p1)                                        # never bound
        self.assertIsNone(culprit([None, None]))
        self.assertIs(culprit([e, e], pings=(5, 0), pongs=(0, 0), pkts=(5, 0)), p1)  # got pings, answered none
        self.assertIs(culprit([e, e], pings=(5, 5), pongs=(5, 0), pkts=(10, 5)), p1)  # pings, but no answers
        self.assertIsNone(culprit([e, e], pings=(5, 5), pongs=(5, 5), pkts=(10, 10)))  # both fine: cannot tell
        self.assertIs(culprit([e, e], pkts=(3, 0)), p1)                              # sent nothing at all
        self.assertIs(culprit([None, None], reason="udp_unreachable", by=p0, state="nat"), p0)
        self.assertIsNone(culprit([e, e], reason="relay_full"))


# ============================================================================== durability
CRASH_CHILD = textwrap.dedent('''
    import sys, time
    sys.path.insert(0, sys.argv[2])
    from t5lobby import rating as glicko
    from t5lobby.server.store import Store
    st = Store(sys.argv[1])
    pending = []
    if sys.argv[4] == "deferred":
        st.defer_commits(pending.append)    # what the server does (loop.call_soon)
    ids = [st.account(n)["id"] for n in ("A", "B")]
    print("ready", flush=True)
    i = 0
    while True:
        i += 1
        # one ranked result, as LobbyServer._finish writes it: both ratings, then the match row
        st.set_rating(ids[0], glicko.Rating(1500 + i % 7, 300, 0.06), "win")
        st.set_rating(ids[1], glicko.Rating(1500 - i % 7, 300, 0.06), "loss")
        st.save_match({"id": "m%s-%d" % (sys.argv[3], i), "created": time.time(), "ended": time.time(),
                       "ranked": True, "p1_name": "A", "p2_name": "B", "p1_account": ids[0], "p2_account": ids[1],
                       "status": "confirmed", "winner": 0})
        while pending:
            pending.pop(0)()                # the end of the event-loop callback: commit
''')


def crash_writes(db, kills, mode, seed=5):
    """Kill a process that writes ranked results at random moments; -> kills that left half a result."""
    st = Store(db)
    st.create_account("A", "x")
    st.create_account("B", "x")
    st.close()
    lobby = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    rnd = random.Random(seed)
    torn = 0
    for k in range(kills):
        p = subprocess.Popen([sys.executable, "-c", CRASH_CHILD, db, lobby, str(k), mode],
                             stdout=subprocess.PIPE, text=True)
        assert p.stdout.readline().strip() == "ready"
        time.sleep(rnd.uniform(0.05, 0.4))
        p.kill()                             # TerminateProcess / SIGKILL: no clean-up of any kind
        p.wait(10)
        p.stdout.close()
        c = Store(db)
        assert c.db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        games = c.db.execute("SELECT SUM(games) FROM accounts").fetchone()[0]
        matches = c.db.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
        if games != 2 * matches:
            torn += 1
            c.db.execute("UPDATE accounts SET games = 0")      # start the next round consistent again
            c.db.execute("DELETE FROM matches")
        c.close()
    return torn


class DurabilityTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="t5dur")
        self.db = os.path.join(self.dir, "t5lobby.db")

    def test_crash_mid_write_never_leaves_half_a_result(self):
        self.assertEqual(crash_writes(self.db, 8, "deferred"), 0)

    def test_restart_voids_the_matches_that_were_running(self):
        s = ServerThread(db=self.db).start()
        a = b = None
        try:
            a = client(s, "Alice", password="pw-Alice", register=True, auto_ready=True)
            b = client(s, "Bob", password="pw-Bob", register=True, auto_ready=True)
            a.ranked_match()
            b.ranked_match()
            ev = expect(a, "match_start", 20)
            expect(b, "match_start", 20)
            mid = ev["match"]
        finally:
            s.stop()                         # (the server goes away; the match row still says "playing")
        self.assertEqual(Store(self.db).match_row(mid)["status"], "playing")
        s2 = ServerThread(db=self.db).start()
        try:
            row = s2.call(lambda: s2.srv.store.match_row(mid))
            self.assertEqual((row["status"], row["reason"], row["blame"]), ("void", "server_restart", None))
            acc = s2.call(lambda: dict(s2.srv.store.account("Alice")))
            self.assertEqual((acc["rating"], acc["games"]), (1500, 0))
        finally:
            for c in (a, b):
                if c is not None:
                    c.close()
            s2.stop()

    def test_drain_lets_running_matches_finish(self):
        from t5lobby.server import admin
        s = ServerThread(db=self.db, admin_poll=0.2, status_port=-1).start()
        try:
            a = client(s, "Alice", password="pw-Alice", register=True, auto_ready=True)
            b = client(s, "Bob", password="pw-Bob", register=True, auto_ready=True)
            c = client(s, "Cid")
            a.ranked_match()
            b.ranked_match()
            ea, eb = expect(a, "match_start", 20), expect(b, "match_start", 20)
            self.assertEqual(admin.main(["--db", self.db, "drain"]), 0)
            self.assertTrue(s.wait_for(lambda: s.srv.draining, 5))
            with self.assertRaises(LobbyError) as cm:
                c.quick_match()
            self.assertIn("restarts", cm.exception.msg)
            url = f"http://127.0.0.1:{s.srv.status_http.port}/status"
            res = {}
            th = threading.Thread(target=lambda: res.update(code=admin.main(
                ["--db", self.db, "--status-url", url, "drain", "--wait", "20"])))
            th.start()
            time.sleep(1.0)
            self.assertTrue(th.is_alive())                     # a match still runs
            w = ea["slot"]
            a.report_result(w, [3, 0] if w == 0 else [0, 3], source="game")
            b.report_result(w, [3, 0] if w == 0 else [0, 3], source="game")
            self.assertEqual(expect(a, "match_result")["status"], "confirmed")
            th.join(15)
            self.assertEqual(res.get("code"), 0)
            for x in (a, b, c):
                x.close()
        finally:
            s.stop()
        s2 = ServerThread(db=self.db).start()                  # a restart ends the drain
        try:
            self.assertFalse(s2.srv.draining)
            self.assertIsNone(s2.call(lambda: s2.srv.store.get_flag("drain")))
        finally:
            s2.stop()

    def test_half_a_certificate_pair_is_made_again(self):
        d = os.path.join(self.dir, "tls")
        os.makedirs(d)
        with open(os.path.join(d, "key.pem"), "w") as f:
            f.write("-----BEGIN PRIVATE KEY-----\ntruncated")         # what a crash mid-write used to leave
        cert, key, fp = selfsigned.write_pair(d, "t5lobby")
        self.assertTrue(selfsigned.usable_pair(cert, key))
        with self.assertRaises(FileExistsError):                       # a working pair is never replaced
            selfsigned.write_pair(d, "t5lobby")
        self.assertEqual(selfsigned.fingerprint(cert), fp)

    def test_atomic_write_keeps_the_old_file_on_failure(self):
        path = os.path.join(self.dir, "host.json")
        atomic_write(path, '{"v": 1}')
        real = os.replace

        def boom(*a):
            raise OSError("disk full")
        os.replace = boom
        try:
            with self.assertRaises(OSError):
                atomic_write(path, '{"v": 2}')
        finally:
            os.replace = real
        with open(path) as f:
            self.assertEqual(json.load(f), {"v": 1})
        self.assertEqual(os.listdir(self.dir), ["host.json"])

    def test_interrupted_backup_leaves_nothing_behind(self):
        st = Store(self.db)
        st.create_account("A", "x")
        st.close()
        dest = os.path.join(self.dir, "backups")
        os.makedirs(dest)
        open(os.path.join(dest, "t5lobby-20260101-000000.db.part"), "w").close()   # killed mid-backup
        path = bk.backup_db(self.db, dest, keep=3)
        self.assertEqual(os.listdir(dest), [os.path.basename(path)])
        self.assertEqual(bk.verify(path)["accounts"], 1)
        with open(os.path.join(self.dir, "broken.db"), "wb") as f:
            f.write(b"not a database" * 100)
        with self.assertRaises(Exception):
            bk.backup_db(os.path.join(self.dir, "broken.db"), dest, keep=3)
        self.assertEqual([n for n in os.listdir(dest) if n.endswith(".part")], [])


if __name__ == "__main__":
    unittest.main()
