"""Direct connections that work whenever the two NATs allow it (docs/NETPLAY.md "Getting a direct connection").

Covers: PCP (and its fallback to NAT-PMP), the game port's router forward (GamePortMapper, never against
the real router), low-TTL punches, the server's punch plan (predicted ports of a symmetric NAT, the router
forward as a candidate, older clients), the second chance of a side that failed while the other got
through, the relay bridge (a relayed match that moves onto the direct path while the games play), and the
NAT simulator (lobby/tools/natsim.py): every pair of NAT types through real lobby code; with an older lobby
tree from git (tag v1.0.0, when the checkout has it) new and old clients and servers in every mix."""
import asyncio
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

import util
from util import ServerThread, client, expect
from t5lobby import nat, portmap, proto
from t5lobby.nat import RelayBridge

HERE = os.path.dirname(os.path.abspath(__file__))
LOBBY = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(LOBBY, "tools"))


# ============================================================================== fake routers
class FakePcpRouter(threading.Thread):
    """Port 5351 of a router on 127.0.0.1: PCP (RFC 6887) MAP / ANNOUNCE, or (natpmp_only) a NAT-PMP router
    that answers a PCP request with its own "unsupported version" and serves NAT-PMP."""

    def __init__(self, natpmp_only=False, ext_ip="203.0.113.9", taken=()):
        super().__init__(daemon=True)
        self.natpmp_only, self.ext_ip, self.taken = natpmp_only, ext_ip, set(taken)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", 0))
        self.port = self.sock.getsockname()[1]
        self.maps = {}
        self.requests = []
        self.running = True

    def run(self):
        self.sock.settimeout(0.1)
        while self.running:
            try:
                data, src = self.sock.recvfrom(1100)
            except (socket.timeout, OSError):
                continue
            self.requests.append(data)
            if data[0] == 2 and not self.natpmp_only:
                self._pcp(data, src)
            elif data[0] == 2:
                self.sock.sendto(struct.pack("!BBHI", 0, 128 + (data[1] & 0x7F), 1, 0), src)
            elif data[:2] == b"\x00\x00":
                self.sock.sendto(struct.pack("!BBHI4s", 0, 128, 0, 1, socket.inet_aton(self.ext_ip)), src)
            elif len(data) == 12 and data[1] in (1, 2):
                _v, op, _r, ip, ep, life = struct.unpack("!BBHHHI", data)
                if life:
                    self.maps[("UDP" if op == 1 else "TCP", ip)] = (ep, life)
                else:
                    self.maps.pop(("UDP" if op == 1 else "TCP", ip), None)
                self.sock.sendto(struct.pack("!BBHIHHI", 0, 128 + op, 0, 1, ip, ep, life), src)

    def _pcp(self, data, src):
        op = data[1] & 0x7F
        life = struct.unpack_from("!I", data, 4)[0]
        head = struct.pack("!BBBBII12x", 2, 0x80 | op, 0, 0, life, 1)
        if op == 0:
            self.sock.sendto(head, src)
            return
        nonce, proto_, int_port, ext_port = data[24:36], data[36], *struct.unpack_from("!HH", data, 40)
        if ext_port in self.taken:
            ext_port = ext_port + 1000
        if life:
            self.maps[("UDP" if proto_ == 17 else "TCP", int_port)] = (ext_port, life, nonce)
        else:
            self.maps.pop(("UDP" if proto_ == 17 else "TCP", int_port), None)
        body = nonce + struct.pack("!B3xHH", proto_, int_port, ext_port) + \
            b"\x00" * 10 + b"\xff\xff" + socket.inet_aton(self.ext_ip)
        self.sock.sendto(head + body, src)

    def stop(self):
        self.running = False
        self.sock.close()


class PortMapTest(unittest.TestCase):
    def test_pcp_map_and_delete(self):
        r = FakePcpRouter(taken={40000})
        r.start()
        try:
            m = portmap.PortMapper(gateway="127.0.0.1", local_ip="127.0.0.1", natpmp_port=r.port)
            self.assertTrue(m.discover())
            self.assertEqual(m.backend.name, "PCP")
            self.assertEqual(m.add("UDP", 40000), 41000)            # the router gave another port
            self.assertEqual(m.external_ip(), "203.0.113.9")
            self.assertEqual(r.maps[("UDP", 40000)][:2], (41000, 3600))
            m.remove_all()
            self.assertEqual(r.maps, {})
        finally:
            r.stop()

    def test_pcp_falls_back_to_natpmp_at_once(self):
        r = FakePcpRouter(natpmp_only=True)
        r.start()
        try:
            m = portmap.PortMapper(gateway="127.0.0.1", local_ip="127.0.0.1", natpmp_port=r.port)
            t0 = time.monotonic()
            self.assertTrue(m.discover())
            self.assertLess(time.monotonic() - t0, 0.5)             # the "unsupported version" answer, no timeout
            self.assertEqual(m.backend.name, "NAT-PMP")
            m.add("UDP", 40001)
            self.assertIn(("UDP", 40001), r.maps)
            m.remove_all()
        finally:
            r.stop()

    def test_game_port_mapper(self):
        calls = []

        class Router:
            def add(self, proto_, ext, port, ip, life):
                calls.append(("add", proto_, ext, port, life))
                return ext, life

            def remove(self, proto_, ext, port):
                calls.append(("remove", proto_, ext, port))

            def external_ip(self):
                return "198.51.100.7"
        g = portmap.GamePortMapper(backend_factory=Router, lifetime=600).start()
        self.assertTrue(g.done.wait(5))
        self.assertEqual(g.map(51000), ("198.51.100.7", 51000))
        self.assertEqual(calls[-1], ("add", "UDP", 51000, 51000, 600))
        g.renew()                                                   # not half the lease yet: nothing
        self.assertEqual(len(calls), 1)
        g.current = g.current[:3] + (time.monotonic() - 400, 600)
        g.renew()
        self.assertEqual(calls[-1][0], "add")
        self.assertEqual(g.map(51001), ("198.51.100.7", 51001))   # the next match: the old forward goes
        self.assertIn(("remove", "UDP", 51000, 51000), calls)
        g.unmap()
        self.assertEqual(calls[-1], ("remove", "UDP", 51001, 51001))

    def test_game_port_mapper_refuses_permanent_forwards(self):
        removed = []

        class PermanentOnly:
            def add(self, proto_, ext, port, ip, life):
                return ext, 0

            def remove(self, proto_, ext, port):
                removed.append(ext)

            def external_ip(self):
                return None
        g = portmap.GamePortMapper(backend_factory=PermanentOnly).start()
        g.done.wait(5)
        self.assertIsNone(g.map(52000))
        self.assertEqual(removed, [52000])

    def test_kill_switch_keeps_the_real_router_alone(self):
        self.assertEqual(os.environ.get("T5_PORTMAP"), "0")        # set by util for every test
        with mock.patch.object(portmap.PortMapper, "discover", side_effect=AssertionError("router contacted")):
            g = portmap.GamePortMapper().start()
            self.assertTrue(g.done.wait(1))
            self.assertFalse(g.ready())
            self.assertIsNone(g.map(53000))

    def test_client_maps_only_for_a_lobby_on_the_internet(self):
        s = ServerThread().start()
        try:
            c = client(s, "Mapper", port_mapping=True)
            try:
                self.assertIsNone(c._mapper)                        # lobby on 127.0.0.1: no router between
            finally:
                c.close()
        finally:
            s.stop()


# ============================================================================== low-TTL punches
class LowTtlTest(unittest.TestCase):
    def test_ttl_is_put_back(self):
        async def go():
            rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            rx.bind(("127.0.0.1", 0))
            rx.settimeout(1.0)
            gs = await nat.GameSocket.open(0, ("127.0.0.1", 9), 0, b"t" * 16, b"tag12345", 0)
            try:
                ttl0 = gs.sock.getsockopt(socket.IPPROTO_IP, socket.IP_TTL)
                gs._punch_to(rx.getsockname(), low_ttl=True)
                self.assertEqual(gs.sock.getsockopt(socket.IPPROTO_IP, socket.IP_TTL), ttl0)
                got = [rx.recvfrom(100)[0] for _ in nat.GameSocket.OPEN_TTLS]     # loopback: no hops
                self.assertTrue(all(proto.udp_type(g) == proto.U_PUNCH for g in got))
            finally:
                await gs.close()
                rx.close()
        loop = proto.new_event_loop()
        try:
            loop.run_until_complete(go())
        finally:
            loop.close()


# ============================================================================== the server's plan
class PlanTest(unittest.TestCase):
    def setUp(self):
        self.s = ServerThread().start()

    def tearDown(self):
        self.s.stop()

    def view(self, pub, prb, n=24):
        class M:
            public_ep = [("198.51.100.1", pub), None]
            probe_ep = [("198.51.100.1", prb) if prb else None, None]
            nat_info = [{"nat": "unknown"}, None]
        self.s.srv.cfg.predict_ports = n
        return self.s.call(lambda: (self.s.srv._nat_view(M, 0), self.s.srv._predicted(M, 0)))

    def test_prediction(self):
        (sym, step), pred = self.view(40000, 40001)
        self.assertTrue(sym)
        self.assertEqual(step, 1)
        self.assertEqual(pred[:3], [40002, 40003, 40004])
        self.assertEqual(len(pred), 24)
        (sym, step), pred = self.view(40010, 40007)                  # counting down
        self.assertEqual(pred[:2], [40006, 40005])
        self.assertEqual(self.view(40000, 52000)[1], [])             # random ports: nothing to guess
        self.assertEqual(self.view(40000, 40000)[1], [])             # same port: not symmetric
        self.assertEqual(self.view(40000, None)[1], [])              # no probe answer
        self.assertEqual(self.view(65530, 65531)[1], [65532, 65533, 65534, 65535])


# ============================================================================== end to end on this PC
class E2E(unittest.TestCase):
    server_cfg = {}

    def setUp(self):
        self.s = ServerThread(**self.server_cfg).start()
        self.clients = []

    def tearDown(self):
        for c in self.clients:
            c.close()
        self.s.stop()

    def pair(self, a=None, b=None):
        ca = client(self.s, "Alice", auto_ready=True, **(a or {}))
        cb = client(self.s, "Bob", auto_ready=True, **(b or {}))
        self.clients += [ca, cb]
        ca.quick_match()
        cb.quick_match()
        ta = expect(ca, "match_start", 30)["ticket"]
        tb = expect(cb, "match_start", 30)["ticket"]
        return ca, cb, ta, tb

    def match(self, name="alice"):
        return self.s.call(lambda: self.s.srv.by_name[name].match)


class PunchTest(E2E):
    def test_new_pair_gets_a_plan(self):
        with mock.patch("t5lobby.client.local_ipv4s", lambda ip: []):
            ca, cb, ta, tb = self.pair()
        self.assertEqual(ta.path, "direct")
        plan = self.s.call(lambda: self.s.srv.by_name["alice"].match.nat_plan)
        self.assertEqual([p["nat2"] for p in plan], [True, True])
        from test_lobby import game_link
        game_link(*((ta, tb) if ta.role == "host" else (tb, ta)))

    def test_new_and_old_client(self):
        # nat2=False: a client that does not know the plan (1.0.0 / 1.1.0) -- old candidates, old window
        with mock.patch("t5lobby.client.local_ipv4s", lambda ip: []):
            ca, cb, ta, tb = self.pair(b={"nat2": False})
        self.assertEqual(ta.path, "direct")
        plan = self.s.call(lambda: self.s.srv.by_name["alice"].match.nat_plan)
        self.assertEqual([p["nat2"] for p in plan], [True, False])

    def test_second_chance_for_a_side_that_gave_up(self):
        # Bob's first punch "fails" at once (its window ended before Alice's punches came, say); Alice gets
        # through (Bob's socket still answers her punches), so the server lets Bob punch once more.
        real = nat.GameSocket.punch
        calls = {"n": 0}

        async def flaky(gs, *a, **kw):
            if gs.side == 1 and calls["n"] == 0:
                calls["n"] += 1
                await asyncio.sleep(0.2)
                return None
            return await real(gs, *a, **kw)
        with mock.patch("t5lobby.client.local_ipv4s", lambda ip: []), \
                mock.patch.object(nat.GameSocket, "punch", flaky):
            ca, cb, ta, tb = self.pair()
        self.assertEqual(ta.path, "direct")
        self.assertEqual(self.s.call(lambda: self.s.srv.counters["punch_retries"]), 1)


class RelayBridgeTest(E2E):
    server_cfg = {"force_relay": True}

    def test_relay_through_the_bridge(self):
        ca, cb, ta, tb = self.pair(a={"relay_bridge": True}, b={"relay_bridge": True})
        self.assertEqual(ta.path, "relay")
        self.assertEqual(ta.peer[0], "127.0.0.1")
        self.assertNotEqual(ta.peer[1], self.s.srv.udp.port)        # the bridge on this PC, not the relay
        self.assertIsNotNone(ca._bridge)
        from test_lobby import game_link
        host, join = (ta, tb) if ta.role == "host" else (tb, ta)
        heard, answered = game_link(host, join)
        self.assertEqual(heard[0], "127.0.0.1")
        stats = self.s.call(lambda: self.s.srv.udp.relays[ta.match_id].stats())
        self.assertGreaterEqual(sum(stats["pkts"]), 2)              # through the server's relay

    def test_bridge_takes_only_the_games_packets(self):
        ca, cb, ta, tb = self.pair(a={"relay_bridge": True}, b={"relay_bridge": True})
        g = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        g.bind(("0.0.0.0", tb.local_port))
        g.settimeout(0.5)
        x = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        x.bind(("127.0.0.1", 0))
        try:
            x.sendto(b"T5NP" + b"" * 50, ta.peer)               # another program on this PC: not the game
            with self.assertRaises(socket.timeout):
                g.recvfrom(4096)
            self.assertEqual(ca._bridge.stats["from_game"], 0)
        finally:
            g.close()
            x.close()

    def test_old_peer_gets_no_bridge(self):
        ca, cb, ta, tb = self.pair(a={"relay_bridge": True}, b={"relay_bridge": True, "nat2": False})
        self.assertEqual(ta.peer, ("127.0.0.1", self.s.srv.udp.port))
        self.assertIsNone(ca._bridge)


class RelayUpgradeTest(E2E):
    def test_relayed_match_moves_onto_the_direct_path(self):
        # Direct packets are ignored while the lobby punches (relay), then the path "opens": the bridges'
        # first burst finds it and both move the game traffic off the relay -- the games see no change.
        with mock.patch.object(RelayBridge, "FIRST_BURST", 6.0), \
                mock.patch("t5lobby.client.local_ipv4s", lambda ip: []):
            ca, cb, ta, tb = self.pair(a={"relay_bridge": True, "block_direct": True},
                                       b={"relay_bridge": True, "block_direct": True})
            self.assertEqual(ta.path, "relay")
            for c in (ca, cb):
                c._bridge.gs.block_direct = False
            host, join = (ta, tb) if ta.role == "host" else (tb, ta)
            socks = []
            for t_ in (host, join):
                k = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                k.bind(("0.0.0.0", t_.local_port))
                k.settimeout(0.05)
                socks.append(k)
            try:
                t_end = time.monotonic() + 25
                got = [0, 0]
                while time.monotonic() < t_end and not (ca.upgrades and cb.upgrades and min(got) > 20):
                    for i, (k, t_) in enumerate(zip(socks, (host, join))):
                        k.sendto(b"T5NP" + bytes([i]) + b"game", t_.peer)
                    for i, k in enumerate(socks):
                        try:
                            while True:
                                d, _a = k.recvfrom(100)
                                if d[:4] == b"T5NP" and (ca.upgrades and cb.upgrades):
                                    got[i] += 1
                        except (socket.timeout, OSError):
                            pass
            finally:
                for k in socks:
                    k.close()
        self.assertEqual(ca.upgrades[-1][1], "direct")
        self.assertEqual(cb.upgrades[-1][1], "direct")
        self.assertGreater(min(got), 20)                               # the games kept talking across the switch
        self.assertGreater(ca._bridge.stats["direct_in"], 0)
        self.assertTrue(self.s.wait_for(lambda: self.s.srv.counters["relay_upgrades"] == 1, 5))


# ============================================================================== the NAT simulator
class NatSimTest(unittest.TestCase):
    """A few pairs through simulated NATs (natsim.py has the full matrix: python tools/natsim.py)."""

    def run_sim(self, pairs, trials, server="new", a="new", b="new", maps=(False, False), base=None):
        import natsim
        trees = {"new": natsim.Tree("t5lobby", os.path.join(LOBBY, "t5lobby"))}
        if base:
            trees["base"] = natsim.Tree("t5lobby_base", os.path.join(base, "t5lobby"))
        sim = natsim.Sim(trees, server, rng_seed=5)
        sim.start_server()
        loop = proto.new_event_loop()
        try:
            res = loop.run_until_complete(natsim.run_matrix(sim, pairs, trials, 6, a, b, maps, progress=False))
        finally:
            sim.stop_server()
            loop.close()
            for tr in trees.values():
                tr.unpatch()
        return res

    def test_symmetric_and_router_forward(self):
        res = self.run_sim([("port", "symmetric"), ("symrand", "port")], 3, maps=(True, False))
        by = {}
        for r in res:
            by.setdefault((r["a"], r["b"]), []).append(r)
        # port prediction: the port-restricted side finds the symmetric side's next port
        self.assertGreaterEqual(sum(r["path"] == "direct" for r in by[("port", "symmetric")]), 2)
        # random ports, but a router that forwards the port: always direct
        self.assertEqual([r["path"] for r in by[("symrand", "port")]], ["direct"] * 3)
        self.assertTrue(all(r["game"] for r in res), res)

    def test_old_tree_from_git(self):
        """Clients and servers of the last release tag against this tree, every mix (skipped without git or
        without the tag in the checkout)."""
        ref = os.environ.get("T5L_COMPAT_REF", "v1.0.0")
        git = shutil.which("git")
        if not git:
            self.skipTest("no git")
        root = os.path.dirname(LOBBY)
        tmp = tempfile.mkdtemp(prefix="t5lobby-compat-")
        try:
            r = subprocess.run([git, "-C", root, "archive", "--format=tar", ref, "lobby/t5lobby"],
                               capture_output=True, timeout=60)
            if r.returncode != 0:
                self.skipTest(f"no {ref} in this checkout")
            import io
            import tarfile
            tarfile.open(fileobj=io.BytesIO(r.stdout)).extractall(tmp, filter="data")
            base = os.path.join(tmp, "lobby")
            for server, a, b in (("new", "base", "new"), ("base", "new", "new"), ("base", "base", "new")):
                res = self.run_sim([("port", "port"), ("port", "symrand")], 2, server, a, b, base=base)
                self.assertTrue(all(r["game"] for r in res), (server, a, b, res))
                self.assertTrue(all(r["path"] == "direct" for r in res if r["b"] == "port" and r["a"] == "port"),
                                (server, a, b, res))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
