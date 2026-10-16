"""End-to-end tests: a real server and several clients on localhost.

Covers: login (guest, account, lockout), lobby list, chat, quick match with hole punching
(LAN candidates and public endpoint), forced relay (client-side and server-side), the game's
handshake over the handed-over ports, rooms + ready check + rematch, challenges, result
reporting and Glicko-2 updates (confirmed, disputed, one-sided), version checks, rate limits,
UDP-blocked cancellation, session resume and socket handover."""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

import util
from util import BUILD, OTHER_BUILD, ServerThread, client, expect
from t5lobby import proto
from t5lobby.proto import LobbyError
from t5lobby.server import Config, LobbyServer


def game_link(t_host, t_join):
    """Do what the netplay layer does with the tickets: bind T5_NET_PORT, the joiner sends HELLO to
    T5_NET_PEER, the host answers whoever said hello. Returns (address the host heard from,
    address the joiner got the answer from)."""
    socks = []
    try:
        for t in (t_host, t_join):
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.bind(("0.0.0.0", t.local_port))
            proto.disable_udp_connreset(s)
            s.settimeout(0.2)
            socks.append(s)
        h, j = socks
        hello = b"T5NP\x01\x01\x02\x01hello"
        src = None
        for _ in range(25):
            j.sendto(hello, t_join.peer)
            try:
                data, src = h.recvfrom(2048)
                if data == hello:
                    break
            except socket.timeout:
                continue
        assert src is not None, "host never heard the joiner"
        h.sendto(b"T5NP\x01\x01\x02\x00answer", src)
        data, src2 = j.recvfrom(2048)
        assert data.endswith(b"answer")
        return src, src2
    finally:
        for s in socks:
            s.close()


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

    def c(self, name=None, **kw):
        c = client(self.s, name, **kw)
        self.clients.append(c)
        return c

    def pair(self, **kw):
        a = self.c("Alice", auto_ready=True, **kw.pop("a", {}))
        b = self.c("Bob", auto_ready=True, **kw.pop("b", {}))
        return a, b

    def start_quick(self, a, b, timeout=15):
        a.quick_match()
        b.quick_match()
        ea = expect(a, "match_start", timeout)
        eb = expect(b, "match_start", timeout)
        return ea["ticket"], eb["ticket"]

    def player(self, name):
        return self.s.call(lambda: self.s.srv.by_name.get(name.lower()))


# ============================================================================== login / lobby
class LoginTest(Base):
    def test_guest_login_and_lobby_list(self):
        a = self.c("Alice")
        b = self.c("Bob")
        self.assertTrue(a.me["guest"])
        self.assertEqual(a.me["build"], BUILD.build_id)
        self.assertIsNotNone(a.server_rtt)
        room = b.create_room("Bob's place")
        t_end = time.time() + 5
        while time.time() < t_end:
            ev = expect(a, "lobby_state")
            names = {p["name"] for p in ev["players"]}
            if names == {"Alice", "Bob"} and ev["rooms"]:
                break
        self.assertEqual(names, {"Alice", "Bob"})
        self.assertEqual(ev["rooms"][0]["id"], room["id"])
        self.assertEqual(ev["rooms"][0]["status"], "open")
        bob = [p for p in ev["players"] if p["name"] == "Bob"][0]
        self.assertEqual(bob["status"], "room")
        self.assertIsNotNone(bob["rtt"])

    def test_name_rules(self):
        self.c("Alice")
        x = self.c()
        with self.assertRaises(LobbyError) as e:
            x.login_guest("alice")                     # case-insensitive duplicate
        self.assertEqual(e.exception.code, proto.E_NAME_TAKEN)
        with self.assertRaises(LobbyError) as e:
            x.login_guest("<script>")
        self.assertEqual(e.exception.code, proto.E_BAD_NAME)

    def test_accounts(self):
        a = self.c("Heihachi", password="mishima1", register=True)
        self.assertFalse(a.me["guest"])
        a.close()
        self.clients.remove(a)
        # the password is stored salted and hashed, never in clear
        row = self.s.call(lambda: dict(self.s.srv.store.account("heihachi")))
        self.assertTrue(row["pw"].startswith("scrypt$"))
        self.assertNotIn("mishima1", json.dumps(row))
        g = self.c()
        with self.assertRaises(LobbyError) as e:
            g.login_guest("Heihachi")                  # guests cannot take an account's name
        self.assertEqual(e.exception.code, proto.E_NAME_TAKEN)
        with self.assertRaises(LobbyError) as e:
            g.register("HEIHACHI", "whatever1")
        self.assertEqual(e.exception.code, proto.E_NAME_TAKEN)
        ok = self.c("Heihachi", password="mishima1")
        self.assertEqual(ok.me["name"], "Heihachi")

    def test_password_lockout(self):
        self.c("Lee", password="silver99", register=True).close()
        x = self.c()
        codes = []
        for _ in range(6):
            try:
                x.login("Lee", "wrong-pass")
            except LobbyError as e:
                codes.append(e.code)
        self.assertEqual(codes[:5], [proto.E_AUTH] * 5)
        self.assertEqual(codes[5], proto.E_RATE)
        with self.assertRaises(LobbyError) as e:
            x.login("Lee", "silver99")                 # locked out even with the right password
        self.assertEqual(e.exception.code, proto.E_RATE)

    def test_chat(self):
        a = self.c("Alice")
        b = self.c("Bob")
        a.chat("hi\x07 there")
        ev = expect(b, "chat")
        self.assertEqual(ev["text"], "hi there")
        self.assertEqual(ev["from"]["name"], "Alice")


# ============================================================================== matches and NAT
class MatchTest(Base):
    def test_quick_match_lan_punch_and_game_link(self):
        a, b = self.pair()
        ta, tb = self.start_quick(a, b)
        self.assertEqual(ta.match_id, tb.match_id)
        self.assertEqual({ta.role, tb.role}, {"host", "join"})
        self.assertEqual(ta.path, "lan")               # same PC: the local candidates win
        self.assertEqual(ta.peer[1], tb.local_port)
        self.assertEqual(tb.peer[1], ta.local_port)
        self.assertGreaterEqual(ta.delay, 2)
        self.assertEqual(ta.delay, tb.delay)
        self.assertEqual(ta.seed, tb.seed)
        host, join = (ta, tb) if ta.role == "host" else (tb, ta)
        env = join.game_env()
        self.assertEqual(env["T5_NET_MODE"], "join")
        self.assertEqual(env["T5_NET_PEER"], f"{join.peer[0]}:{join.peer[1]}")
        heard, answered = game_link(host, join)
        self.assertEqual(heard[1], join.local_port)
        self.assertEqual(answered, join.peer)

    def test_public_endpoint_punch(self):
        # No local candidates: the punch has to go through the endpoints the server observed.
        with mock.patch("t5lobby.client.local_ipv4s", lambda ip: []):
            a, b = self.pair()
            ta, tb = self.start_quick(a, b)
        self.assertEqual(ta.path, "direct")
        self.assertEqual(ta.peer, ("127.0.0.1", tb.local_port))
        host, join = (ta, tb) if ta.role == "host" else (tb, ta)
        game_link(host, join)

    def test_local_candidates_must_be_private(self):
        # A client cannot make its opponent punch toward public hosts by claiming them as "local".
        with mock.patch("t5lobby.client.local_ipv4s", lambda ip: ["8.8.8.8", "10.1.2.3", "169.254.1.1"]):
            a, b = self.pair()
            ta, tb = self.start_quick(a, b)
        self.assertEqual(ta.path, "direct")            # 10.1.2.3 leads nowhere; the public endpoint works
        infos = self.s.call(lambda: [i["addrs"] for i in self.s.srv.by_name["alice"].match.nat_info])
        for addrs in infos:
            self.assertEqual([ip for ip, _port in addrs], ["10.1.2.3"])

    def test_forced_relay_when_punch_fails(self):
        # Bob ignores every direct packet from Alice: punching fails both ways -> relay.
        a, b = self.pair(b={"block_direct": True})
        ta, tb = self.start_quick(a, b, timeout=20)
        self.assertEqual(ta.path, "relay")
        relay = ("127.0.0.1", self.s.srv.udp.port)
        self.assertEqual(ta.peer, relay)
        self.assertEqual(tb.peer, relay)
        self.assertLess(ta.rtt_ms, 50)
        host, join = (ta, tb) if ta.role == "host" else (tb, ta)
        heard, answered = game_link(host, join)
        self.assertEqual(heard, relay)                 # the host sees the relay as its peer
        self.assertEqual(answered, relay)
        stats = self.s.call(lambda: self.s.srv.udp.relays[ta.match_id].stats())
        self.assertGreaterEqual(sum(stats["pkts"]), 2)

    def test_server_forced_relay(self):
        self.s.srv.cfg.force_relay = True
        a, b = self.pair()
        ta, tb = self.start_quick(a, b)
        self.assertEqual(ta.path, "relay")
        host, join = (ta, tb) if ta.role == "host" else (tb, ta)
        game_link(host, join)

    def test_relay_drops_strangers(self):
        self.s.srv.cfg.force_relay = True
        a, b = self.pair()
        ta, tb = self.start_quick(a, b)
        x = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        x.bind(("127.0.0.1", 0))
        x.settimeout(0.3)
        h = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        h.bind(("0.0.0.0", ta.local_port))
        h.settimeout(0.3)
        try:
            for _ in range(5):
                x.sendto(b"T5NPstranger", ta.peer)     # not a bound endpoint (and not quiet-relatchable)
            with self.assertRaises(socket.timeout):
                h.recvfrom(100)
        finally:
            x.close()
            h.close()

    def test_decline_requeues_the_other(self):
        a = self.c("Alice")
        b = self.c("Bob")
        a.quick_match()
        b.quick_match()
        expect(a, "match_found")
        expect(b, "match_found")
        a.ready()
        b.ready(accept=False)
        ca = expect(a, "match_cancel")
        cb = expect(b, "match_cancel")
        self.assertEqual(ca["reason"], "declined")
        self.assertFalse(ca["you"])
        self.assertTrue(cb["you"])
        self.assertEqual(self.player("Alice").status, "queue")
        self.assertEqual(self.player("Bob").status, "idle")

    def test_ready_timeout(self):
        self.s.srv.cfg.ready_timeout = 0.5
        a = self.c("Alice", auto_ready=True)
        b = self.c("Bob")
        a.quick_match()
        b.quick_match()
        self.assertEqual(expect(b, "match_cancel")["reason"], "ready_timeout")
        self.assertEqual(self.player("Alice").status, "queue")

    def test_udp_blocked(self):
        self.s.srv.cfg.register_timeout = 1.0
        a, b = self.pair()

        async def no_udp(self_, timeout=4.0):
            return None
        with mock.patch("t5lobby.nat.GameSocket.register", no_udp):
            a.quick_match()
            b.quick_match()
            ev = expect(a, "match_cancel")
        self.assertEqual(ev["reason"], "udp_unreachable")

    def test_room_ready_check_and_rematch(self):
        a = self.c("Alice")
        b = self.c("Bob")
        room = a.create_room("dojo")
        b.join_room(room["id"])
        fa = expect(a, "match_found")
        expect(b, "match_found")
        self.assertEqual(fa["role"], "host")           # the room owner hosts
        self.assertTrue(fa["ready_check"])
        b.ready(accept=False)
        expect(a, "match_cancel")
        self.assertEqual(self.player("Alice").status, "room")
        self.assertEqual(self.player("Bob").status, "room")
        a.rematch()
        expect(a, "match_found")
        expect(b, "match_found")
        a.ready()
        b.ready()
        ta = expect(a, "match_start")["ticket"]
        tb = expect(b, "match_start")["ticket"]
        self.assertEqual(ta.role, "host")
        a.report_result(0, [3, 1])
        b.report_result(0, [3, 1])
        self.assertEqual(expect(a, "match_result")["status"], "confirmed")
        self.assertEqual(self.player("Bob").status, "room")
        self.assertEqual(tb.match_id, ta.match_id)

    def test_challenge(self):
        a = self.c("Alice")
        b = self.c("Bob")
        bob_id = b.me["id"]
        cid = a.challenge(bob_id)
        ev = expect(b, "challenged")
        self.assertEqual(ev["from"]["name"], "Alice")
        b.answer_challenge(cid, accept=False)
        self.assertEqual(expect(a, "challenge_update")["state"], "declined")
        time.sleep(2.1)                                # one challenge per 2 s
        cid = a.challenge(bob_id)
        expect(b, "challenged")
        b.answer_challenge(cid, accept=True)
        fa = expect(a, "match_found")
        self.assertFalse(fa["ready_check"])            # accepting was the ready check
        self.assertEqual(fa["role"], "host")
        expect(a, "match_start")
        expect(b, "match_start")

    def test_share_socket_handover(self):
        if os.name != "nt":
            self.skipTest("WSADuplicateSocket is Windows only")
        a, b = self.pair(a={"handover": "share"})
        ta, tb = self.start_quick(a, b)
        self.assertIn("T5_NET_SOCKET_FILE", ta.game_env())
        peer = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        peer.bind(("0.0.0.0", tb.local_port))
        peer.settimeout(5)
        path = os.path.join(tempfile.mkdtemp(), "sock.hex")
        code = ("import os,socket,sys,time\n"
                "p=sys.argv[1]\n"
                "while not os.path.exists(p): time.sleep(0.01)\n"
                "s=socket.fromshare(bytes.fromhex(open(p).read()))\n"
                "s.sendto(b'T5NP-from-game', (sys.argv[2], int(sys.argv[3])))\n")
        child = subprocess.Popen([sys.executable, "-c", code, path, ta.peer[0], str(ta.peer[1])])
        try:
            ta.share_socket(child.pid, path)
            data, src = peer.recvfrom(100)
            self.assertEqual(data, b"T5NP-from-game")
            self.assertEqual(src[1], ta.local_port)      # the game sent from the punched socket itself
            self.assertEqual(child.wait(10), 0)
        finally:
            peer.close()
            if child.poll() is None:
                child.kill()


# ============================================================================== results and rating
class ResultTest(Base):
    def ranked_pair(self):
        a = self.c("Alice", password="alice-pw", register=True, auto_ready=True)
        b = self.c("Bob", password="bob-pw1", register=True, auto_ready=True)
        a.ranked_match()
        b.ranked_match()
        ta = expect(a, "match_start")["ticket"]
        tb = expect(b, "match_start")["ticket"]
        self.assertTrue(ta.ranked)
        return a, b, ta, tb

    def account(self, name):
        return self.s.call(lambda: dict(self.s.srv.store.account(name)))

    def test_confirmed_result_updates_rating(self):
        a, b, ta, tb = self.ranked_pair()
        winner = ta.slot                                # Alice wins
        score = [3, 1] if winner == 0 else [1, 3]
        a.report_result(winner, score)
        self.assertEqual(expect(b, "notice")["code"], "result_pending")
        b.report_result(winner, score)
        ra = expect(a, "match_result")
        rb = expect(b, "match_result")
        self.assertEqual(ra["status"], "confirmed")
        self.assertGreater(ra["rating"]["delta"], 0)
        self.assertLess(rb["rating"]["delta"], 0)
        acc_a, acc_b = self.account("Alice"), self.account("Bob")
        self.assertAlmostEqual(acc_a["rating"], ra["rating"]["after"]["r"], places=0)
        self.assertGreater(acc_a["rating"], 1500)
        self.assertLess(acc_b["rating"], 1500)
        self.assertEqual((acc_a["wins"], acc_a["losses"], acc_b["wins"], acc_b["losses"]), (1, 0, 0, 1))
        row = self.s.call(lambda: self.s.srv.store.match_row(ta.match_id))
        self.assertEqual(row["status"], "confirmed")
        self.assertEqual(json.loads(row["score"]), score)
        self.assertEqual(self.player("Alice").status, "idle")

    def test_disputed_result_changes_nothing(self):
        a, b, ta, tb = self.ranked_pair()
        a.report_result(ta.slot, None)                 # both claim the win
        b.report_result(tb.slot, None)
        self.assertEqual(expect(a, "match_result")["status"], "disputed")
        self.assertEqual(self.account("Alice")["rating"], 1500)
        self.assertEqual(self.account("Alice")["games"], 0)

    def test_onesided_when_opponent_leaves(self):
        a, b, ta, tb = self.ranked_pair()
        a.report_result(ta.slot, [3, 0] if ta.slot == 0 else [0, 3])
        b.close()                                      # Bob rage-quits the lobby without reporting
        ev = expect(a, "match_result", timeout=10)
        self.assertEqual(ev["status"], "onesided")
        self.assertGreater(ev["rating"]["delta"], 0)
        self.assertLess(self.account("Bob")["rating"], 1500)

    def test_no_report_is_void(self):
        a, b, ta, tb = self.ranked_pair()
        a.report_result(ta.slot, None)                 # Bob is still online but never confirms
        self.assertEqual(expect(a, "match_result", timeout=10)["status"], "void")
        self.assertEqual(self.account("Alice")["rating"], 1500)

    def test_guest_cannot_queue_ranked(self):
        g = self.c("Guesty")
        with self.assertRaises(LobbyError) as e:
            g.ranked_match()
        self.assertEqual(e.exception.code, proto.E_NOT_ALLOWED)

    def test_resume_after_disconnect(self):
        a, b, ta, tb = self.ranked_pair()
        token = a.token
        a._loop.call_soon_threadsafe(a._writer.transport.abort)   # the launcher's connection breaks
        expect(a, "disconnected")
        a2 = self.c()
        me = a2.resume(token)
        self.assertEqual(me["name"], "Alice")
        ev = expect(a2, "match_start")
        self.assertTrue(ev.get("resumed"))
        a2.report_result(ta.slot, None, match_id=ta.match_id)
        b.report_result(ta.slot, None)
        self.assertEqual(expect(a2, "match_result")["status"], "confirmed")


# ============================================================================== version checks
class VersionTest(Base):
    def test_cross_build_never_paired(self):
        a = self.c("Alice", auto_ready=True)
        b = self.c("Bob", build=OTHER_BUILD, auto_ready=True)
        a.quick_match()
        b.quick_match()
        self.assertIsNone(a.next_event(1.5, ("match_found",)))
        a.cancel_queue()
        b.cancel_queue()
        with self.assertRaises(LobbyError) as e:
            a.challenge(b.me["id"])
        self.assertEqual(e.exception.code, proto.E_VERSION)
        room = b.create_room()
        with self.assertRaises(LobbyError) as e:
            a.join_room(room["id"])
        self.assertEqual(e.exception.code, proto.E_VERSION)

    def test_build_allow_list(self):
        self.s.srv.cfg.builds = [BUILD.build_id]
        self.c("Alice")
        with self.assertRaises(LobbyError) as e:
            self.c("Mallory", build=OTHER_BUILD)
        self.assertEqual(e.exception.code, proto.E_VERSION)

    def test_protocol_mismatch(self):
        r = raw(self.s)
        r.send({"t": "hello", "proto": 99, "build": BUILD.as_wire()})
        msg = r.recv()
        self.assertEqual(msg["code"], proto.E_PROTO)
        self.assertIsNone(r.recv())                    # and the server hangs up


# ============================================================================== abuse protection
RAWS = []


class raw:
    """A bare control connection for misbehaving on purpose."""

    def __init__(self, s):
        self.sock = socket.create_connection(("127.0.0.1", s.srv.port), timeout=5)
        self.buf = b""
        RAWS.append(self)

    def send(self, msg):
        self.sock.sendall(proto.encode(msg))

    def send_raw(self, data):
        self.sock.sendall(data)

    def recv(self):
        while b"\n" not in self.buf:
            try:
                d = self.sock.recv(65536)
            except (ConnectionError, socket.timeout):
                return None
            if not d:
                return None
            self.buf += d
        line, self.buf = self.buf.split(b"\n", 1)
        return json.loads(line)

    def close(self):
        self.sock.close()


class AbuseTest(Base):
    def login(self, name):
        r = raw(self.s)
        r.send({"t": "hello", "proto": proto.PROTO_VERSION, "build": BUILD.as_wire()})
        self.assertEqual(r.recv()["t"], "welcome")
        r.send({"t": "login", "mode": "guest", "name": name})
        self.assertEqual(r.recv()["t"], "login_ok")
        return r

    def test_flood_gets_rate_limited_then_banned(self):
        r = self.login("Flooder")
        r.send_raw(b"".join(proto.encode({"t": "ping"}) for _ in range(200)))
        codes = []
        while True:
            m = r.recv()
            if m is None:
                break
            if m["t"] == "error":
                codes.append((m["code"], m["msg"]))
        self.assertIn((proto.E_RATE, "slow down"), codes)
        self.assertEqual(codes[-1], (proto.E_RATE, "flooding: disconnected"))
        r2 = raw(self.s)                               # the address is banned for a while
        self.assertEqual(r2.recv()["code"], proto.E_RATE)

    def test_connection_cap_per_ip(self):
        self.s.srv.cfg.max_per_ip = 3
        conns = [raw(self.s) for _ in range(3)]
        time.sleep(0.2)
        extra = raw(self.s)
        self.assertEqual(extra.recv()["code"], proto.E_FULL)
        for c in conns:
            c.close()

    def test_garbage_and_long_lines(self):
        r = raw(self.s)
        r.send_raw(b"this is not json\n")
        self.assertEqual(r.recv()["code"], proto.E_BAD_REQUEST)
        r.send({"t": "queue"})                          # not logged in
        self.assertEqual(r.recv()["code"], proto.E_STATE)
        r.send_raw(b"{" + b"x" * (proto.MAX_LINE + 100))
        self.assertEqual(r.recv()["msg"], "line too long")
        self.assertIsNone(r.recv())

    def test_login_timeout(self):
        self.s.srv.cfg.login_timeout = 0.5
        r = raw(self.s)
        self.assertEqual(r.recv()["msg"], "login timeout")
        self.assertIsNone(r.recv())

    def test_udp_ping_is_rate_limited_and_not_amplified(self):
        u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        u.settimeout(0.5)
        addr = ("127.0.0.1", self.s.srv.udp.port)
        for i in range(400):
            u.sendto(proto.pk_ping(proto.U_SPING, i, 0.0), addr)
        got = 0
        try:
            while True:
                d, _ = u.recvfrom(100)
                self.assertEqual(len(d), proto.PING.size)
                got += 1
        except socket.timeout:
            pass
        u.close()
        self.assertGreater(got, 50)
        self.assertLess(got, 400)
        # unknown tokens get no answer at all
        u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        u.settimeout(0.3)
        u.sendto(proto.pk_token(proto.U_REGISTER, b"\0" * 16), addr)
        with self.assertRaises(socket.timeout):
            u.recvfrom(100)
        u.close()


# ============================================================================== matchmaker (no network)
class FakeConn:
    def __init__(self, build="b1"):
        self.build_id, self.release, self.ip = build, "", "127.0.0.1"
        self.sent = []

    def send(self, msg):
        self.sent.append(msg)


class MatchmakerTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.srv = LobbyServer(Config(**util.FAST))

    async def asyncTearDown(self):
        self.srv.store.close()

    def player(self, name, r, rtt=20.0, build="b1"):
        from t5lobby.server.lobby import Player
        from t5lobby.rating import Rating
        p = Player(FakeConn(build), name, guest=False)
        p.rating = Rating(r, 80)
        p.server_rtt = rtt
        self.srv.players[p.id] = p
        return p

    async def test_ranked_pairs_by_rating(self):
        now = time.monotonic()
        a = self.player("A", 1500)
        b = self.player("B", 2100)
        c = self.player("C", 1530)
        for i, p in enumerate((a, b, c)):
            self.srv._enqueue(p, "ranked", now - 1 + i * 0.01)
        made = self.srv.match_queue(now)
        self.assertEqual(len(made), 1)
        self.assertEqual({made[0][0].name, made[0][1].name}, {"A", "C"})
        self.assertEqual(b.status, "queue")
        # B's window widens with waiting: 100 + 25/s -> covers 570 points after ~19 s
        self.assertEqual(self.srv.match_queue(now + 10), [])
        d = self.player("D", 1600)
        self.srv._enqueue(d, "ranked", now)
        self.assertEqual(self.srv.match_queue(now + 2), [])
        made = self.srv.match_queue(now + 25)
        self.assertEqual({made[0][0].name, made[0][1].name}, {"B", "D"})

    async def test_ranked_respects_ping(self):
        now = time.monotonic()
        a = self.player("A", 1500, rtt=20)
        far = self.player("Far", 1500, rtt=150)        # 170 ms estimated: too far for a fresh queue
        near = self.player("Near", 1560, rtt=25)
        for p in (a, far, near):
            self.srv._enqueue(p, "ranked", now)
        made = self.srv.match_queue(now)
        self.assertEqual({made[0][0].name, made[0][1].name}, {"A", "Near"})

    async def test_quick_prefers_low_ping_and_same_build(self):
        now = time.monotonic()
        a = self.player("A", 1500, rtt=10)
        x = self.player("X", 1500, rtt=5, build="b2")
        far = self.player("Far", 1500, rtt=200)
        near = self.player("Near", 1500, rtt=30)
        for p in (a, x, far, near):
            self.srv._enqueue(p, "quick", now)
        made = self.srv.match_queue(now)
        self.assertEqual(len(made), 1)
        self.assertEqual({made[0][0].name, made[0][1].name}, {"A", "Near"})
        host = made[0][0] if made[0][0].server_rtt <= made[0][1].server_rtt else made[0][1]
        self.assertEqual(host.match.players[0], host)  # lower server RTT hosts
        self.assertEqual(x.status, "queue")


if __name__ == "__main__":
    unittest.main()
