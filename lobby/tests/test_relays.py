"""Regional relays (docs/ONLINE.md "Regional relays", docs/HOSTING.md "Adding a relay server").

Covers: the control channel (HMAC, replay, clock, node id, central address), relays.json, the relay-only node
(sessions, short-lived bind tokens, game packets only, size cap, sessions per address, lease, idle sweep,
full), the central server's choice (smallest sum of both players' round trips, an older client gets the
central relay, a dead node is skipped, a refusing or silent node falls back to the next), the relay list
pushed to clients when relays.json changes, the relay bridge's direct upgrade from a regional relay, the
admin status lines, and compatibility with the newest release tag's client and server (from git).

The round trips are made with the UDP delay proxies of lobby/tools/relay_e2e.py (one per player and relay).
"""
import asyncio
import contextlib
import io
import json
import os
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import unittest
from unittest import mock

import util  # noqa: F401 -- sys.path, T5_PORTMAP=0
from util import BUILD, ServerThread, expect
from t5lobby import proto, relayctl
from t5lobby.client import LobbyClient
from t5lobby.nat import RelayBridge
from t5lobby.server import Config
from t5lobby.server.relaynode import RelayNode
from t5lobby.server.relays import RelayPool, parse

HERE = os.path.dirname(os.path.abspath(__file__))
LOBBY = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(LOBBY, "tools"))
import relay_e2e  # noqa: E402
from relay_e2e import UdpDelay, routed  # noqa: E402

SECRET = b"0123456789abcdef0123456789abcdef0123456789abcdef"


# ============================================================================== helpers
class NodeThread:
    """A relay-only node on its own thread (127.0.0.1, any free port)."""

    def __init__(self, secret=SECRET, **cfg):
        kw = dict(host="127.0.0.1", udp_port=0, udp_port2=0, status_port=0, relay_id="usw", log_level="WARNING",
                  db=":memory:")
        kw.update(cfg)
        self.cfg = Config(**kw)
        self.secret = secret
        self.loop = proto.new_event_loop()
        self.node = None
        self._ready = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        asyncio.set_event_loop(self.loop)
        self.node = RelayNode(self.cfg, self.secret)
        self.loop.run_until_complete(self.node.start())
        self._ready.set()
        self.loop.run_forever()

    def start(self):
        self.thread.start()
        if not self._ready.wait(10):
            raise RuntimeError("node did not start")
        return self

    @property
    def addr(self):
        return ("127.0.0.1", self.node.port)

    def call(self, fn, *args):
        async def wrap():
            return fn(*args)
        return asyncio.run_coroutine_threadsafe(wrap(), self.loop).result(10)

    def stop(self):
        if self.loop.is_closed():
            return
        asyncio.run_coroutine_threadsafe(self.node.stop(), self.loop).result(10)
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(10)
        self.loop.close()


def ctl(addr, op, secret=SECRET, node="usw", sock=None, raw=None, timeout=1.0, **fields):
    """One control request from a plain socket -> the node's answer (dict) or None."""
    own = sock is None
    s = sock or socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        if own:
            s.bind(("127.0.0.1", 0))
        s.settimeout(timeout)
        msg = relayctl.request(op, node, **fields)
        data = raw if raw is not None else relayctl.pack(secret, relayctl.REQUEST, msg)
        s.sendto(data, addr)
        try:
            got, _a = s.recvfrom(4096)
        except socket.timeout:
            return None
        r = relayctl.unpack(secret, got)
        return r[1] if r and r[0] == relayctl.REPLY else None
    finally:
        if own:
            s.close()


def bind(sock, addr, token, timeout=1.0):
    """RELAY_BIND from `sock` -> the endpoint the relay saw, or None (no answer)."""
    sock.settimeout(timeout)
    sock.sendto(proto.pk_token(proto.U_RELAY_BIND, token), addr)
    try:
        data, _a = sock.recvfrom(256)
    except socket.timeout:
        return None
    return proto.un_token_ack(data)[2]


def udp():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    proto.disable_udp_connreset(s)
    return s


# ============================================================================== the control channel
class ControlChannelTest(unittest.TestCase):
    def test_pack_and_unpack(self):
        d = relayctl.pack(SECRET, relayctl.REQUEST, {"op": "status", "id": "abcdef0123456789"})
        self.assertEqual(relayctl.unpack(SECRET, d), (relayctl.REQUEST, {"op": "status", "id": "abcdef0123456789"}))
        self.assertIsNone(relayctl.unpack(b"x" * 48, d))                         # another secret
        bad = bytearray(d)
        bad[10] ^= 1
        self.assertIsNone(relayctl.unpack(SECRET, bytes(bad)))                   # changed on the way
        self.assertIsNone(relayctl.unpack(SECRET, d[:-1]))
        self.assertIsNone(relayctl.unpack(SECRET, b"T5RC\x02\x01" + d[6:]))       # another version
        self.assertIsNone(relayctl.unpack(SECRET, d + b"\x00" * 1500))           # oversized
        lst = relayctl.pack(SECRET, relayctl.REQUEST, [1, 2])
        self.assertIsNone(relayctl.unpack(SECRET, lst))                          # not an object

    def test_secret_files(self):
        tmp = tempfile.mkdtemp()
        try:
            p = os.path.join(tmp, "s", "relay.secret")
            text = relayctl.write_secret(p)
            self.assertEqual(len(text), 64)
            self.assertEqual(relayctl.write_secret(p), text)                     # kept: both machines hold it
            self.assertEqual(relayctl.load_secret(p), text.encode())
            short = os.path.join(tmp, "short")
            with open(short, "w") as f:
                f.write("tooshort\n")
            with self.assertRaises(ValueError):
                relayctl.load_secret(short)
            with self.assertRaises(ValueError):
                relayctl.load_secret(os.path.join(tmp, "missing"))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_relays_json(self):
        tmp = tempfile.mkdtemp()
        try:
            with open(os.path.join(tmp, "usw.secret"), "w") as f:
                f.write(SECRET.decode() + "\n")
            doc = {"format": "t5dr-relays/1", "relays": [
                {"id": "usw", "name": "Oregon (US West)", "host": "203.0.113.7", "secret_file": "usw.secret"},
                {"id": "ase", "host": "198.51.100.2", "port": 7790, "secret_file": "usw.secret", "enabled": False}]}
            nodes = parse(json.dumps(doc), tmp)
            self.assertEqual([(n.id, n.name, n.host, n.port, n.enabled) for n in nodes],
                             [("usw", "Oregon (US West)", "203.0.113.7", 7781, True), ("ase", "ase", "198.51.100.2",
                                                                                         7790, False)])
            self.assertEqual(nodes[0].secret, SECRET)
            bad = [
                {"relays": [{"id": "main", "host": "x", "secret_file": "usw.secret"}]},      # reserved id
                {"relays": [{"id": "Bad Id", "host": "x", "secret_file": "usw.secret"}]},
                {"relays": [{"id": "a", "host": "x", "secret_file": "usw.secret"}] * 2},     # twice
                {"relays": [{"id": "a", "host": "x", "port": 0, "secret_file": "usw.secret"}]},
                {"relays": [{"id": "a", "host": "x"}]},                                      # no secret
                {"relays": [{"id": "a", "host": "x", "secret_file": "nope.secret"}]},
                {"format": "t5dr-relays/9", "relays": []},
            ]
            for d in bad:
                with self.assertRaises(ValueError, msg=d):
                    parse(json.dumps(d), tmp)
            # the default secret file for entries without one; a bare list works too
            self.assertEqual(len(parse(json.dumps([{"id": "b", "host": "x"}]), tmp,
                                       os.path.join(tmp, "usw.secret"))), 1)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


# ============================================================================== the relay node
class _Node(unittest.TestCase):
    node_cfg = {}

    def setUp(self):
        self.n = NodeThread(**self.node_cfg).start()
        self.socks = []

    def tearDown(self):
        for s in self.socks:
            s.close()
        self.n.stop()

    def sock(self):
        s = udp()
        self.socks.append(s)
        return s

    def open(self, sid="00112233aabbccdd", lease=600):
        toks = [proto.new_token(), proto.new_token()]
        r = ctl(self.n.addr, "open", sid=sid, tokens=[t.hex() for t in toks], lease=lease)
        self.assertTrue(r and r["ok"], r)
        return toks

    def sessions(self):
        return self.n.call(lambda: len(self.n.node.udp.relays))


class NodeTest(_Node):
    def test_status_and_authentication(self):
        r = ctl(self.n.addr, "status")
        self.assertTrue(r["ok"])
        self.assertEqual((r["sessions"], r["id"]), (0, "usw"))
        self.assertIsNone(ctl(self.n.addr, "status", secret=b"y" * 48, timeout=0.3))   # wrong secret: silence
        self.assertIsNone(ctl(self.n.addr, "status", node="ase", timeout=0.3))         # meant for another node
        # a recorded request played back: silence
        s = self.sock()
        msg = relayctl.request("status", "usw")
        data = relayctl.pack(SECRET, relayctl.REQUEST, msg)
        self.assertTrue(ctl(self.n.addr, "status", sock=s, raw=data)["ok"])
        self.assertIsNone(ctl(self.n.addr, "status", sock=s, raw=data, timeout=0.3))
        # an old request (or a node whose clock is off): one answer that says so, and nothing done
        old = relayctl.request("open", "usw", sid="0011223344556677", tokens=["00" * 16, "11" * 16])
        old["ts"] -= 600
        r = ctl(self.n.addr, "open", raw=relayctl.pack(SECRET, relayctl.REQUEST, old))
        self.assertEqual(r["error"], "clock")
        self.assertEqual(self.sessions(), 0)
        st = self.n.call(self.n.node.status)
        self.assertGreaterEqual(st["counters"]["ctl_refused"], 3)
        # a stranger's ping is answered (that is how players measure the node), registrations are not
        p = self.sock()
        p.settimeout(1)
        p.sendto(proto.pk_ping(proto.U_SPING, 7, 1.5), self.n.addr)
        self.assertEqual(proto.udp_type(p.recvfrom(100)[0]), proto.U_SPONG)
        p.sendto(proto.pk_token(proto.U_REGISTER, proto.new_token()), self.n.addr)
        p.settimeout(0.3)
        with self.assertRaises(socket.timeout):
            p.recvfrom(100)

    def test_session_forwards_game_packets_only(self):
        toks = self.open()
        a, b = self.sock(), self.sock()
        self.assertEqual(bind(a, self.n.addr, toks[0]), a.getsockname())
        self.assertEqual(bind(b, self.n.addr, toks[1]), b.getsockname())
        self.assertIsNone(bind(self.sock(), self.n.addr, proto.new_token(), 0.3))     # a stranger's token
        a.sendto(b"T5NP" + b"\x01" * 40, self.n.addr)
        b.settimeout(1)
        self.assertEqual(b.recvfrom(100)[0], b"T5NP" + b"\x01" * 40)
        b.sendto(b"T5NP" + b"\x02" * 40, self.n.addr)
        a.settimeout(1)
        self.assertEqual(a.recvfrom(100)[0][:5], b"T5NP\x02")
        # not the game's packets, or too big: dropped (no free tunnel)
        a.sendto(b"GET / HTTP/1.1\r\n\r\n", self.n.addr)
        a.sendto(b"T5NP" + b"\x00" * 3000, self.n.addr)
        b.settimeout(0.3)
        with self.assertRaises(socket.timeout):
            b.recvfrom(4096)
        r = ctl(self.n.addr, "info", sid="00112233aabbccdd")
        self.assertEqual((r["bound"], r["pkts"]), ([True, True], [1, 1]))
        self.assertEqual(r["dropped"][0], 2)
        r = ctl(self.n.addr, "close", sid="00112233aabbccdd")
        self.assertTrue(r["ok"])
        self.assertEqual(self.sessions(), 0)
        a.sendto(b"T5NP" + b"\x03" * 40, self.n.addr)                    # closed: nothing goes through
        with self.assertRaises(socket.timeout):
            b.recvfrom(100)
        # a closed session's id cannot come back (its tokens are spent)
        r = ctl(self.n.addr, "open", sid="00112233aabbccdd", tokens=[proto.new_token().hex(), proto.new_token().hex()])
        self.assertEqual(r["error"], "closed")

    def test_open_is_idempotent(self):
        toks = [proto.new_token().hex(), proto.new_token().hex()]
        for _ in range(2):         # (the answer to the first was lost: the server asks again)
            self.assertTrue(ctl(self.n.addr, "open", sid="aa00aa00aa00aa00", tokens=toks, lease=60)["ok"])
        other = [proto.new_token().hex(), proto.new_token().hex()]
        self.assertEqual(ctl(self.n.addr, "open", sid="aa00aa00aa00aa00", tokens=other)["error"], "exists")
        self.assertEqual(ctl(self.n.addr, "open", sid="bb00bb00bb00bb00", tokens=toks)["error"], "exists")
        self.assertEqual(ctl(self.n.addr, "open", sid="not-hex!", tokens=other)["error"], "bad_request")

    def test_idle_sessions_go(self):
        toks = self.open()
        bind(self.sock(), self.n.addr, toks[0])
        bind(self.sock(), self.n.addr, toks[1])
        now = time.monotonic()
        self.n.call(lambda: self.n.node.sweep(now + 60))
        self.assertEqual(self.sessions(), 1)
        self.n.call(lambda: self.n.node.sweep(now + 125))           # 2 minutes without a packet
        self.assertEqual(self.sessions(), 0)
        self.assertEqual(self.n.call(lambda: self.n.node.counters["sessions_idle"]), 1)


class NodeLimitsTest(_Node):
    node_cfg = {"relay_bind_seconds": 0.5, "max_relays_per_ip": 1, "max_relays": 2}

    def test_bind_tokens_are_short_lived(self):
        toks = self.open()
        time.sleep(0.7)
        self.assertIsNone(bind(self.sock(), self.n.addr, toks[0], 0.3))
        self.n.call(self.n.node.sweep)                       # never bound in time: closed
        self.assertEqual(self.sessions(), 0)
        self.assertEqual(self.n.call(lambda: self.n.node.counters["sessions_unbound"]), 1)

    def test_sessions_per_address_and_full(self):
        t1 = self.open("1111111111111111")
        t2 = self.open("2222222222222222")
        r = ctl(self.n.addr, "open", sid="3333333333333333", tokens=[proto.new_token().hex(), proto.new_token().hex()])
        self.assertEqual(r["error"], "full")
        self.assertIsNotNone(bind(self.sock(), self.n.addr, t1[0]))
        self.assertIsNotNone(bind(self.sock(), self.n.addr, t1[1]))           # (the same session: fine)
        self.assertIsNone(bind(self.sock(), self.n.addr, t2[0], 0.3))         # a 2nd session from 127.0.0.1
        self.assertGreaterEqual(self.n.call(lambda: self.n.node.counters["binds_refused"]), 1)


class NodeLeaseTest(_Node):
    node_cfg = {"relay_max_seconds": 1.0}

    def test_lease_and_renew(self):
        toks = self.open(lease=600)                     # the node caps it at its own 1 s
        bind(self.sock(), self.n.addr, toks[0])
        bind(self.sock(), self.n.addr, toks[1])
        time.sleep(0.6)
        self.assertTrue(ctl(self.n.addr, "renew", sid="00112233aabbccdd", lease=600)["ok"])   # 1 s from now
        time.sleep(0.6)
        self.n.call(self.n.node.sweep)
        self.assertEqual(self.sessions(), 1)              # renewed: still there 1.2 s after it opened
        time.sleep(0.6)
        self.n.call(self.n.node.sweep)
        self.assertEqual(self.sessions(), 0)
        self.assertEqual(self.n.call(lambda: self.n.node.counters["sessions_expired"]), 1)
        self.assertEqual(ctl(self.n.addr, "renew", sid="00112233aabbccdd")["error"], "unknown")


class NodeCentralOnlyTest(_Node):
    node_cfg = {"relay_central": ["192.0.2.1"]}

    def test_control_only_from_the_central_server(self):
        self.assertIsNone(ctl(self.n.addr, "status", timeout=0.3))
        self.assertEqual(self.n.call(lambda: self.n.node.counters["ctl_refused"]), 1)


def game_link(t_host, t_join, timeout=5.0):
    """What the netplay layer does with the tickets (like test_lobby.game_link, but patient and deaf to the
    lobby's own packets still on their way through a slow relay: the last peer pings of the measurement)."""
    socks = []
    try:
        for t in (t_host, t_join):
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.bind(("0.0.0.0", t.local_port))
            proto.disable_udp_connreset(s)
            s.settimeout(0.1)
            socks.append(s)
        h, j = socks
        hello = b"T5NP\x01\x01\x02\x01hello"
        src = got = None
        t_end = time.monotonic() + timeout
        while time.monotonic() < t_end and got is None:
            if src is None:
                j.sendto(hello, t_join.peer)
            for sock, want in ((h, hello), (j, None)):
                try:
                    while True:
                        data, a = sock.recvfrom(2048)
                        if sock is h and data == hello and src is None:
                            src = a
                            h.sendto(b"T5NP\x01\x01\x02\x00answer", src)
                        elif sock is j and data.endswith(b"answer"):
                            got = a
                except (socket.timeout, OSError):
                    pass
        assert src is not None, "host never heard the joiner"
        assert got is not None, "the joiner never got the host's answer"
        return src, got
    finally:
        for s in socks:
            s.close()


# ============================================================================== the central server's choice
class Regional(unittest.TestCase):
    """A central server with two in-process nodes and players behind delay proxies."""
    rtt = {"main": (60, 60), "usw": (6, 80), "usc": (24, 24)}       # sums: 120, 86, 48
    server_cfg = {"force_relay": True}
    node_cfgs = {"usw": {}, "usc": {}}

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="t5relays-")
        sf = os.path.join(self.tmp, "relay.secret")
        with open(sf, "w") as f:
            f.write(SECRET.decode())
        self.nodes = {rid: NodeThread(relay_id=rid, **cfg).start() for rid, cfg in self.node_cfgs.items()}
        self.rj = os.path.join(self.tmp, "relays.json")
        self.write_relays(self.nodes)
        cfg = dict(relays=self.rj, relay_secret_file=sf, relay_check_seconds=0.2, relay_dead_seconds=1.0)
        cfg.update(self.server_cfg)
        self.s = ServerThread(**cfg).start()
        self.clients = []
        self.proxies = []
        self.assertTrue(self.s.wait_for(lambda: all(n.alive for n in self.s.srv.relays.nodes.values()), 10))

    def write_relays(self, nodes, extra=()):
        doc = {"relays": [{"id": rid, "name": rid.upper(), "host": "127.0.0.1", "port": n.node.port}
                          for rid, n in nodes.items()] + list(extra)}
        tmp = self.rj + ".tmp"
        with open(tmp, "w") as f:
            json.dump(doc, f)
        os.replace(tmp, self.rj)

    def tearDown(self):
        for c in self.clients:
            c.close()
        self.s.stop()
        for n in self.nodes.values():
            n.stop()
        for p in self.proxies:
            p.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def player(self, name, side, cls=None, **kw):
        """A client whose relays (and its UDP ping to the server) go through delay proxies."""
        cls = cls or routed(LobbyClient)
        kw.setdefault("relay_bridge", False)
        c = cls(self.s.addr, BUILD, auto_ready=True, **kw)
        routes = {}
        targets = {"main": ("127.0.0.1", self.s.srv.udp.port),
                   **{rid: n.addr for rid, n in self.nodes.items()}}
        for rid, target in targets.items():
            px = UdpDelay(target, self.rtt.get(rid, (0, 0))[side], f"{rid}/{name}")
            px.start()
            self.proxies.append(px)
            routes[rid] = px.addr
        c.routes = routes
        c.connect()
        c.login_guest(name)
        self.clients.append(c)
        return c

    def measured(self, c, ids, timeout=10):
        t_end = time.monotonic() + timeout
        while time.monotonic() < t_end:
            if all(i in c.relay_rtts for i in ids) and c.server_rtt is not None:
                pid = c.me["id"]
                if self.s.call(lambda: all(i in self.s.srv.players[pid].relay_rtt for i in ids)):
                    return
            time.sleep(0.05)
        self.fail(f"{c.me['name']} did not measure {ids}: {c.relay_rtts}")

    def pair(self, a, b):
        a.quick_match()
        b.quick_match()
        ea = expect(a, "match_start", 30)
        eb = expect(b, "match_start", 30)
        return ea, eb

    def choice(self):
        evs = [e for e in self.s.call(lambda: list(self.s.srv.events)) if e[1] == "relay_choice"]
        return evs[-1][2]


class ChoiceTest(Regional):
    def test_smallest_sum_wins_and_the_match_plays_through_it(self):
        a, b = self.player("Alice", 0), self.player("Bob", 1)
        for c in (a, b):
            self.measured(c, ["usw", "usc"])
        ea, eb = self.pair(a, b)
        self.assertEqual(ea["path"], "relay")
        self.assertEqual((ea["relay"]["id"], eb["relay"]["id"]), ("usc", "usc"))
        self.assertEqual(ea["relay"]["port"], self.nodes["usc"].node.port)
        ch = self.choice()
        self.assertEqual(ch["relay"], "usc")
        self.assertEqual([rid for _ms, rid in ch["options"]], ["usc", "usw", "main"])
        self.assertGreater(ea["rtt_ms"], 40)                          # the path's round trip: through usc
        ta, tb = ea["ticket"], eb["ticket"]
        host, join = (ta, tb) if ta.role == "host" else (tb, ta)
        game_link(host, join)
        info = self.nodes["usc"].call(lambda: [s.stats() for s in self.nodes["usc"].node.udp.relays.values()])
        self.assertEqual(len(info), 1)
        self.assertGreaterEqual(sum(info[0]["pkts"]), 2)              # the games' packets went through usc
        self.assertEqual(self.nodes["usw"].call(lambda: len(self.nodes["usw"].node.udp.relays)), 0)
        self.assertEqual(self.s.call(lambda: len(self.s.srv.udp.relays)), 0)
        self.assertEqual(self.s.call(lambda: self.s.srv.counters["relay_regional"]), 1)
        # the match ends: the node's session closes (after the rematch window, like ours)
        mid = ea["match"]
        a.report_result(0, [3, 1], match_id=mid)
        b.report_result(0, [3, 1], match_id=mid)
        self.assertEqual(expect(a, "match_result")["status"], "confirmed")
        m = self.s.call(lambda: self.s.srv.recent[mid])
        self.s.call(lambda: self.s.srv._close_kept_relay(m))
        self.assertTrue(self._wait_node_empty("usc"))

    def _wait_node_empty(self, rid, timeout=5):
        t_end = time.monotonic() + timeout
        while time.monotonic() < t_end:
            if self.nodes[rid].call(lambda: len(self.nodes[rid].node.udp.relays)) == 0:
                return True
            time.sleep(0.05)
        return False

    def test_old_client_gets_the_central_relay(self):
        a = self.player("Alice", 0)
        b = self.player("Bob", 1, relays=False)              # a 1.1.0 launcher, as far as relays go
        self.measured(a, ["usw", "usc"])
        self.assertNotIn("relays", b.welcome)
        ea, eb = self.pair(a, b)
        self.assertNotIn("relay", ea)
        self.assertNotIn("relay", eb)
        self.assertEqual(eb["relay_port"], self.s.srv.udp.port)
        self.assertEqual(self.choice()["relay"], "main")
        ta, tb = ea["ticket"], eb["ticket"]
        game_link(*((ta, tb) if ta.role == "host" else (tb, ta)))

    def test_dead_node_is_skipped(self):
        a, b = self.player("Alice", 0), self.player("Bob", 1)
        for c in (a, b):
            self.measured(c, ["usw", "usc"])
        self.nodes["usc"].stop()
        self.assertTrue(self.s.wait_for(lambda: not self.s.srv.relays.nodes["usc"].alive, 10))
        st = {r["id"]: r for r in self.s.call(self.s.srv.status)["relays"]}
        self.assertFalse(st["usc"]["alive"])
        self.assertTrue(st["usw"]["alive"])
        ea, _eb = self.pair(a, b)
        self.assertEqual(ea["relay"]["id"], "usw")

    def test_silent_node_falls_back_at_once(self):
        # usc dies, and the server has not noticed yet: its session request goes unanswered -> the next one
        a, b = self.player("Alice", 0), self.player("Bob", 1)
        for c in (a, b):
            self.measured(c, ["usw", "usc"])
        self.s.call(lambda: setattr(self.s.cfg, "relay_dead_seconds", 3600.0))
        self.nodes["usc"].stop()
        self.assertTrue(self.s.call(lambda: self.s.srv.relays.nodes["usc"].alive))
        ea, _eb = self.pair(a, b)
        self.assertEqual(ea["relay"]["id"], "usw")
        self.assertEqual(self.s.call(lambda: self.s.srv.counters["relay_fallbacks"]), 1)
        self.assertFalse(self.s.call(lambda: self.s.srv.relays.nodes["usc"].alive))   # marked down by the failure

    def test_list_changes_reach_the_clients(self):
        a = self.player("Alice", 0)
        self.measured(a, ["usw", "usc"])
        extra = NodeThread(relay_id="ase").start()
        try:
            self.nodes["ase"] = extra
            self.write_relays(self.nodes)
            t_end = time.monotonic() + 10
            while time.monotonic() < t_end and "ase" not in a.relay_rtts:
                time.sleep(0.05)
            self.assertIn("ase", a.relay_rtts)
            self.assertEqual([r["id"] for r in a.welcome["relays"]], ["usw", "usc", "ase"])
            # a broken file keeps the last good list
            with open(self.rj, "w") as f:
                f.write("{broken")
            time.sleep(0.6)
            self.assertEqual(len(self.s.srv.relays.nodes), 3)
            self.assertIn("not valid JSON", self.s.call(self.s.srv.status)["relays_error"])
        finally:
            del self.nodes["ase"]
            extra.stop()

    def test_admin_status_lines(self):
        from t5lobby.server import admin
        out = io.StringIO()
        with mock.patch.object(admin, "_fetch", lambda url, timeout=3.0: (200, json.dumps(self.s.call(self.s.srv.status)))), \
                contextlib.redirect_stdout(out):
            self.assertEqual(admin.main(["status"]), 0)
        text = out.getvalue()
        self.assertIn("relay usw", text)
        self.assertIn("relay usc", text)
        self.assertIn("up,", text)
        out = io.StringIO()
        node = self.nodes["usw"]
        with mock.patch.object(admin, "_fetch", lambda url, timeout=3.0: (200, json.dumps(node.call(node.node.status)))), \
                contextlib.redirect_stdout(out):
            self.assertEqual(admin.main(["status"]), 0)
        self.assertIn("relay node usw", out.getvalue())
        from t5lobby.server.status import prometheus
        prom = prometheus(self.s.call(self.s.srv.status))
        self.assertIn('t5lobby_relay_node_up{relay="usw"} 1', prom)
        self.assertIn("t5relay_sessions 0", node.call(node.node.metrics))


class FullNodeTest(Regional):
    node_cfgs = {"usw": {}, "usc": {"max_relays": 0}}

    def test_full_node_falls_back_to_the_next(self):
        a, b = self.player("Alice", 0), self.player("Bob", 1)
        for c in (a, b):
            self.measured(c, ["usw", "usc"])
        ea, _eb = self.pair(a, b)
        self.assertEqual(ea["relay"]["id"], "usw")
        self.assertEqual(self.s.call(lambda: self.s.srv.counters["relay_fallbacks"]), 1)
        self.assertTrue(self.s.call(lambda: self.s.srv.relays.nodes["usc"].alive))     # full is not dead


class UpgradeFromRegionalTest(Regional):
    server_cfg = {}                     # punching first (blocked below), then the relay

    def test_regional_relay_then_direct(self):
        with mock.patch.object(RelayBridge, "FIRST_BURST", 6.0), \
                mock.patch("t5lobby.client.local_ipv4s", lambda ip: []):
            a = self.player("Alice", 0, relay_bridge=True, block_direct=True)
            b = self.player("Bob", 1, relay_bridge=True, block_direct=True)
            for c in (a, b):
                self.measured(c, ["usw", "usc"])
            ea, eb = self.pair(a, b)
            ta, tb = ea["ticket"], eb["ticket"]
            self.assertEqual((ta.path, ea["relay"]["id"]), ("relay", "usc"))
            self.assertEqual(ta.peer[0], "127.0.0.1")
            self.assertEqual(a._bridge.relay, a.routes["usc"])          # the bridge talks to the regional relay
            for c in (a, b):
                c._bridge.gs.block_direct = False
            host, join = (ta, tb) if ta.role == "host" else (tb, ta)
            socks = []
            for t_ in (host, join):
                k = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                k.bind(("0.0.0.0", t_.local_port))
                k.settimeout(0.05)
                socks.append(k)
            relayed_before = None
            try:
                t_end = time.monotonic() + 25
                got = [0, 0]
                while time.monotonic() < t_end and not (a.upgrades and b.upgrades and min(got) > 20):
                    for i, (k, t_) in enumerate(zip(socks, (host, join))):
                        k.sendto(b"T5NP" + bytes([i]) + b"game", t_.peer)
                    for i, k in enumerate(socks):
                        try:
                            while True:
                                d, _a = k.recvfrom(100)
                                if d[:4] == b"T5NP" and (a.upgrades and b.upgrades):
                                    got[i] += 1
                        except (socket.timeout, OSError):
                            pass
                    if relayed_before is None and not (a.upgrades or b.upgrades):
                        n = self.nodes["usc"].call(lambda: sum(sum(s.pkts) for s in self.nodes["usc"].node.udp.relays.values()))
                        if n > 10:
                            relayed_before = n
            finally:
                for k in socks:
                    k.close()
        self.assertGreater(relayed_before or 0, 10)                   # the games talked through usc first
        self.assertEqual(a.upgrades[-1][1], "direct")
        self.assertEqual(b.upgrades[-1][1], "direct")
        self.assertGreater(min(got), 20)                               # and kept talking across the switch
        self.assertTrue(self.s.wait_for(lambda: self.s.srv.counters["relay_upgrades"] == 1, 5))


# ============================================================================== older releases (git)
_OLD = {}


def _old_tree(test, ref):
    """(client module, server module) of the git tag `ref`, imported once per process under another name."""
    if ref in _OLD:
        return _OLD[ref]
    git = shutil.which("git")
    if not git:
        test.skipTest("no git")
    r = subprocess.run([git, "-C", os.path.dirname(LOBBY), "archive", "--format=tar", ref, "lobby/t5lobby"],
                       capture_output=True, timeout=60)
    if r.returncode != 0:
        test.skipTest(f"no {ref} in this checkout")
    tmp = tempfile.mkdtemp(prefix="t5relay-old-")
    _TMP.append(tmp)
    tarfile.open(fileobj=io.BytesIO(r.stdout)).extractall(tmp, filter="data")
    import natsim
    name = "t5lobby_relold"
    natsim.load_pkg(name, os.path.join(tmp, "lobby", "t5lobby"))
    import importlib
    _OLD[ref] = (importlib.import_module(name + ".client"), importlib.import_module(name + ".server"))
    return _OLD[ref]


_TMP = []


def tearDownModule():
    for d in _TMP:
        shutil.rmtree(d, ignore_errors=True)


REF = os.environ.get("T5L_COMPAT_REF", "v1.1.0")


class OldClientTest(Regional):
    def test_release_client_on_a_server_with_regional_relays(self):
        oldc, _olds = _old_tree(self, REF)
        a = self.player("Alice", 0)
        self.measured(a, ["usw", "usc"])
        b = oldc.LobbyClient(self.s.addr, BUILD, auto_ready=True)
        b.connect()
        b.login_guest("Bob")
        self.clients.append(b)
        ea, eb = self.pair(a, b)
        self.assertEqual(self.choice()["relay"], "main")
        self.assertEqual(eb["ticket"].peer, ("127.0.0.1", self.s.srv.udp.port))     # as it always did
        ta, tb = ea["ticket"], eb["ticket"]
        game_link(*((ta, tb) if ta.role == "host" else (tb, ta)))


class OldServerTest(unittest.TestCase):
    def test_new_clients_on_a_release_server(self):
        _oldc, olds = _old_tree(self, REF)
        loop = proto.new_event_loop()
        srv = olds.LobbyServer(olds.Config(**dict(util.FAST, force_relay=True)))
        ready = threading.Event()

        def run():
            asyncio.set_event_loop(loop)
            loop.run_until_complete(srv.start())
            ready.set()
            loop.run_forever()
        th = threading.Thread(target=run, daemon=True)
        th.start()
        clients = []
        try:
            self.assertTrue(ready.wait(10))
            for name in ("Alice", "Bob"):
                c = LobbyClient(f"127.0.0.1:{srv.port}", BUILD, auto_ready=True, relay_bridge=False)
                c.connect()
                c.login_guest(name)
                clients.append(c)
                self.assertNotIn("relays", c.welcome.get("caps", []))
            for c in clients:
                c.quick_match()
            ea, eb = (expect(c, "match_start", 30) for c in clients)
            self.assertEqual(ea["ticket"].peer, ("127.0.0.1", srv.udp.port))
            ta, tb = ea["ticket"], eb["ticket"]
            game_link(*((ta, tb) if ta.role == "host" else (tb, ta)))
        finally:
            for c in clients:
                c.close()
            asyncio.run_coroutine_threadsafe(srv.stop(), loop).result(10)
            loop.call_soon_threadsafe(loop.stop)
            th.join(10)
            loop.close()


# ============================================================================== the e2e tool (processes)
class EndToEndTest(unittest.TestCase):
    def test_relay_e2e_best(self):
        """lobby/tools/relay_e2e.py: central + two nodes as processes, stub games through the chosen node."""
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = relay_e2e.main(["--scenarios", "best,dead", "--seconds", "2"])
        self.assertEqual(rc, 0, out.getvalue())


if __name__ == "__main__":
    unittest.main()
