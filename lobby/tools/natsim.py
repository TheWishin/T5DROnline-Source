"""NAT simulator: the real lobby server and real LobbyClients behind simulated home routers.

Each "home" is a LobbyClient plus a NAT object that lives on the client's event loop. The client's
game socket (t5lobby.nat.GameSocket) does not send on its own socket: every packet goes to the NAT,
which maps it to a public endpoint -- a real UDP socket on a loopback address of its own
(127.<n>.<m>.1, one per NAT) -- and sends it from there after a simulated delay (or drops it). What
comes back to a public socket is filtered the way the NAT type says and handed to whatever owns the
internal port: the lobby's game socket, or the stub game after the handover. The lobby server is the
real one (its UDP side, probe port and relay included); the control channel (TCP) goes through a
delay proxy, so the two clients receive the server's messages with a realistic, uneven delay.

NAT types (RFC 4787 terms):
    full        endpoint-independent mapping, endpoint-independent filtering   (full cone)
    restricted  endpoint-independent mapping, address-dependent filtering      (restricted cone)
    port        endpoint-independent mapping, address+port-dependent filtering (port-restricted cone)
    symmetric   address+port-dependent mapping and filtering, sequential ports (with other traffic
                taking a port now and then)
    symrand     like symmetric, random ports (CGNAT-like; port prediction cannot help)
    port-guard  "port" with a flood guard: an address that sends more than 20 unsolicited packets in
                2 s is blocked for 30 s (consumer routers' DoS / port-scan protection)
    port-poison "port" on a Linux-style router whose WAN side takes unsolicited UDP: a punch that arrives
                before this side sent anything toward its sender leaves a connection entry behind (30 s,
                refreshed by every further punch), so this side's own packets toward that sender must
                leave from another port -- which the other side's port-restricted NAT then drops
A home may also have a router that answers UPnP/NAT-PMP/PCP (mapping=True): the client's mapping
request then makes a static port forward on the NAT (endpoint-independent filtering for that port).

A home's PC may also have a firewall that blocks the game and/or the launcher (--fw-a / --fw-b, docs/NETPLAY.md
"When Windows Firewall blocks the game"): "stateful" lets in only what comes from an address:port that
program's socket sent to (Windows Firewall for a blocked program), "block" lets in nothing from the network
(the relay bridge's 127.0.0.1 still works). The launcher side is t5lobby's own test switch
(LobbyClient(test_inbound=...), nat.InboundFilter); the stub game filters the same way.

Usage (from lobby/):
    python tools/natsim.py --trials 50 --parallel 8                     # every pair of types, this tree
    python tools/natsim.py --fw-a stateful --fw-b stateful:game         # firewalls: both programs at A, the game at B
    python tools/natsim.py --base ../../base/lobby --server base --a base --b base   # an older tree
    python tools/natsim.py --pairs port:symmetric,full:port --trials 10 -v

Prints a table (direct / LAN, relay, failed, game link working, setup time) and writes --json.
"""
import argparse
import hashlib
import asyncio
import collections
import concurrent.futures
import importlib
import importlib.util
import itertools
import json
import os
import random
import socket
import statistics
import struct
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
LOBBY = os.path.dirname(HERE)

SERVER_IP = "127.0.0.1"
TYPES = {
    "full": dict(mapping="eim", filtering="eif", alloc="preserve"),
    "restricted": dict(mapping="eim", filtering="adf", alloc="preserve"),
    "port": dict(mapping="eim", filtering="apdf", alloc="preserve"),
    "symmetric": dict(mapping="apdm", filtering="apdf", alloc="sequential"),
    "symrand": dict(mapping="apdm", filtering="apdf", alloc="random"),
    "port-guard": dict(mapping="eim", filtering="apdf", alloc="preserve", guard=True),
    "port-poison": dict(mapping="eim", filtering="apdf", alloc="preserve", poison=True),
}
BASIC = ("full", "restricted", "port", "symmetric")


# ============================================================================ loading two lobby trees
def load_pkg(name, pkg_dir):
    """Import the t5lobby package in `pkg_dir` under the module name `name` (it uses relative imports
    only, so an older copy can sit next to this one in the same process)."""
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, os.path.join(pkg_dir, "__init__.py"),
                                                  submodule_search_locations=[pkg_dir])
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


class Tree:
    """One lobby version: its client, nat, server modules, patched to run behind simulated NATs."""

    def __init__(self, name, pkg_dir):
        self.name = name
        load_pkg(name, pkg_dir)
        self.proto = importlib.import_module(name + ".proto")
        self.nat = importlib.import_module(name + ".nat")
        self.client = importlib.import_module(name + ".client")
        self.buildid = importlib.import_module(name + ".buildid")
        self.server = importlib.import_module(name + ".server")
        try:
            self.portmap = importlib.import_module(name + ".portmap")
        except ImportError:
            self.portmap = None
        self._patch()

    def _patch(self):
        """Route the game sockets of simulated homes through their NAT; everything else (a client that is
        not in a simulated home) keeps the real behaviour, so tests can run next to the simulation."""
        GS = self.nat.GameSocket
        self._orig = {"open": GS.__dict__["open"], "send": GS.__dict__["send"],
                      "local": self.client.local_ipv4s, "rtt": self.client.server_rtt}
        orig_open = GS.open.__func__
        orig_send = GS.send
        orig_local = self.client.local_ipv4s
        orig_rtt = self.client.server_rtt

        async def sim_open(cls, port, *a, **kw):
            gs = await orig_open(cls, port, *a, **kw)
            home = HOMES.get(id(asyncio.get_running_loop()))
            gs._sim_home = home
            if home is not None:
                home.nat.attach(gs.port, gs.datagram_received)
                if getattr(gs, "inbound", None) is not None:
                    gs.inbound.local = frozenset()     # (here every datagram comes from the simulated internet)
            return gs
        GS.open = classmethod(sim_open)

        def sim_send(self, data, addr, *a, **kw):
            home = getattr(self, "_sim_home", None)
            if home is None:                       # not a simulated home: the real socket
                return orig_send(self, data, addr, *a, **kw)
            if self.transport is None or self.transport.is_closing():
                return
            if getattr(self, "inbound", None) is not None:
                self.inbound.sent_to(addr)
            home.nat.outbound(self.port, data, addr, ttl=kw.get("ttl"))
            self.stats["tx"] += 1
        GS.send = sim_send

        def sim_local(target_ip):
            home = HOMES.get(id(asyncio.get_running_loop()))
            return [home.private_ip] if home else orig_local(target_ip)
        self.client.local_ipv4s = sim_local

        async def sim_server_rtt(server, *a, **kw):      # (the real one pings past the simulated network)
            home = HOMES.get(id(asyncio.get_running_loop()))
            if home is None:
                return await orig_rtt(server, *a, **kw)
            return 2 * home.nat.net.server_ms + home.nat.net.server_jitter
        self.client.server_rtt = sim_server_rtt

    def unpatch(self):
        GS = self.nat.GameSocket
        GS.open = self._orig["open"]
        GS.send = self._orig["send"]
        self.client.local_ipv4s = self._orig["local"]
        self.client.server_rtt = self._orig["rtt"]


HOMES = {}            # id(client loop) -> Home


# ============================================================================ the simulated internet
class Net:
    def __init__(self, rng, server_ms=75.0, server_jitter=20.0, home_ms=8.0, home_jitter=6.0, loss=0.02,
                 tcp_rto=0.03):
        self.rng = rng
        self.tcp_rto = tcp_rto
        self.server_ms, self.server_jitter = server_ms, server_jitter
        self.home_ms, self.home_jitter = home_ms, home_jitter
        self.loss = loss
        self.lock = threading.Lock()

    def one_way(self, to_server):
        with self.lock:
            if self.rng.random() < self.loss:
                return None
            if to_server:
                return (self.server_ms + self.rng.uniform(0, self.server_jitter)) / 1000.0
            return (self.home_ms + self.rng.uniform(0, self.home_jitter)) / 1000.0

    def tcp_delay(self):
        """One way on the control channel: like UDP to the server, and now and then a lost segment that TCP
        sends again after its retransmission timeout (everything behind it waits too)."""
        with self.lock:
            d = (self.server_ms + self.rng.uniform(0, self.server_jitter)) / 1000.0
            if self.rng.random() < self.tcp_rto:
                d += self.rng.uniform(0.25, 1.0)
            return d

    def rand(self):
        with self.lock:
            return self.rng.random()

    def randint(self, a, b):
        with self.lock:
            return self.rng.randint(a, b)


class Wire:
    """Delivers delayed packets at the right moment. asyncio's timers on Windows run on GetTickCount64
    (15.6 ms steps: a 10 ms delay would be 0 or 16 ms), so the delays run on one thread of their own
    with perf_counter and 1 ms sleeps."""

    def __init__(self):
        import heapq
        self.heapq = heapq
        self.heap = []
        self.seq = itertools.count()
        self.lock = threading.Lock()
        self.thread = threading.Thread(target=self._run, name="natsim-wire", daemon=True)
        self.thread.start()

    def later(self, delay, fn, *args):
        with self.lock:
            self.heapq.heappush(self.heap, (time.perf_counter() + delay, next(self.seq), fn, args))

    def _run(self):
        while True:
            now = time.perf_counter()
            due = []
            with self.lock:
                while self.heap and self.heap[0][0] <= now:
                    due.append(self.heapq.heappop(self.heap))
            for _t, _s, fn, args in due:
                try:
                    fn(*args)
                except Exception:      # noqa: BLE001 -- a closed socket or loop
                    pass
            time.sleep(0.001)


WIRE = None


def wire():
    global WIRE
    if WIRE is None:
        WIRE = Wire()
    return WIRE


class Mapping:
    __slots__ = ("key", "int_port", "ext_port", "sock", "eps", "ips", "replied", "last_out", "static")

    def __init__(self, key, int_port, ext_port, sock, static=False):
        self.key, self.int_port, self.ext_port, self.sock = key, int_port, ext_port, sock
        self.eps, self.ips = {}, {}         # remote endpoint / address -> last packet of that flow
        self.replied = set()                # remote endpoints that answered (a "replied" connection entry)
        self.last_out = time.monotonic()
        self.static = static


class Nat:
    """One home router. Runs on the home client's event loop (all calls from that thread)."""

    def __init__(self, loop, net, public_ip, private_ip, mapping="eim", filtering="apdf", alloc="preserve",
                 guard=False, poison=False, timeout=120.0, hops=1):
        self.loop, self.net = loop, net
        self.public_ip, self.private_ip = public_ip, private_ip
        self.mapping, self.filtering, self.alloc, self.guard = mapping, filtering, alloc, guard
        self.poison = poison
        self.poisoned = {}                  # (ext port, remote endpoint) -> until (port-poison)
        self.events = []                    # (time, what, ...) for -v
        self.timeout = timeout
        self.hops = hops                    # TTL needed to leave this home (1 = the router is the first hop)
        self.maps = {}                      # key -> Mapping
        self.by_ext = {}                    # ext port -> Mapping
        self.internal = {}                  # internal port -> receiver(data, src)
        self.next_port = 20000 + net.randint(0, 3000) * 10
        self.unsolicited = collections.defaultdict(collections.deque)   # src ip -> times (guard)
        self.blocked = {}                   # src ip -> until
        self.stats = collections.Counter()
        self.closed = False

    # -------------------------------------------------------------- inside
    def attach(self, int_port, receiver):
        self.internal[int_port] = receiver

    def outbound(self, int_port, data, dst, ttl=None):
        if self.closed:
            return
        dst = (str(dst[0]), int(dst[1]))
        if not dst[0].startswith("127."):
            self.stats["unroutable"] += 1   # a private address of the peer's LAN: nothing there here
            return
        if dst[0] == self.public_ip:
            self.stats["hairpin"] += 1
            return
        if ttl is not None and ttl <= self.hops:
            self.stats["ttl_expired_home"] += 1
            return
        m = self._mapping_for(int_port, dst)
        if m is None:
            return
        if self.poison and not m.static:
            m2 = self.maps.get((int_port, dst))
            if m2 is not None and not self._fresh(m2, dst):
                self._drop(m2)                                          # its (unreplied) entry timed out
                m2 = None
            if m2 is None and not self._fresh(m, dst) and self.poisoned.get((m.ext_port, dst), 0) > time.monotonic():
                m2 = self._new_mapping((int_port, dst), int_port)       # the port toward dst is taken
                self.stats["poisoned_flows"] += 1
                self.events.append((round(time.time() % 1000, 3), "poisoned_flow", dst, ttl))
            if m2 is not None:
                m = m2
        now = time.monotonic()
        if dst not in m.eps and dst[0] != SERVER_IP:
            self.events.append((round(time.time() % 1000, 3), "first_out", dst, ttl, data[4] if len(data) > 4 else None))
        if not self._fresh(m, dst):
            m.replied.discard(dst)          # a new connection entry
        m.eps[dst] = now
        m.ips[dst[0]] = now
        m.last_out = now
        to_server = dst[0] == SERVER_IP
        if ttl is not None and not to_server and ttl < 8:
            # left the home, died on the way: the mapping exists now, the peer never sees it
            self.stats["ttl_expired_path"] += 1
            return
        d = self.net.one_way(to_server)
        if d is None:
            self.stats["lost"] += 1
            return
        wire().later(d, self._send_now, m, data, dst)

    def _send_now(self, m, data, dst):      # (wire thread)
        if self.closed:
            return
        try:
            m.sock.sendto(data, dst)
            self.stats["out"] += 1
        except OSError:
            self.stats["send_err"] += 1

    def _key(self, int_port, dst):
        if self.mapping == "eim":
            return int_port
        if self.mapping == "adm":
            return (int_port, dst[0])
        return (int_port, dst)

    def _mapping_for(self, int_port, dst):
        key = self._key(int_port, dst)
        m = self.maps.get(key)
        now = time.monotonic()
        if m is not None and not m.static and now - m.last_out > self.timeout:
            self._drop(m)
            m = None
        if m is None:
            st = self.by_ext.get(int_port)
            if st is not None and st.static and st.int_port == int_port:
                return st                 # a port forward (UPnP) is also the outgoing mapping
            m = self._new_mapping(key, int_port)
        return m

    def _bind(self, port):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.bind((self.public_ip, port))
        except OSError:
            s.close()
            return None
        s.setblocking(False)
        _no_connreset(s)
        return s

    def _new_mapping(self, key, int_port, ext_port=None, static=False):
        sock = None
        if ext_port is not None:
            sock = self._bind(ext_port) if ext_port not in self.by_ext else None
        else:
            if self.alloc == "preserve" and int_port not in self.by_ext:
                sock = self._bind(int_port)
                ext_port = int_port
            if sock is None and self.alloc == "random":
                for _ in range(50):
                    p = self.net.randint(10000, 60000)
                    if p not in self.by_ext:
                        sock = self._bind(p)
                        if sock:
                            ext_port = p
                            break
            while sock is None:
                if self.alloc == "sequential" and self.net.rand() < 0.25:
                    self.next_port += self.net.randint(1, 3)      # another device took a port meanwhile
                p = self.next_port
                self.next_port += 1
                if self.next_port > 64000:
                    self.next_port = 20000
                if p not in self.by_ext:
                    sock = self._bind(p)
                    ext_port = p
        if sock is None:
            return None
        m = Mapping(key, int_port, ext_port, sock, static)
        self.maps[key] = m
        self.by_ext[ext_port] = m
        self.loop.add_reader(sock.fileno(), self._readable, m)
        self.stats["mappings"] += 1
        return m

    def _drop(self, m):
        self.maps.pop(m.key, None)
        if self.by_ext.get(m.ext_port) is m:
            del self.by_ext[m.ext_port]
        try:
            self.loop.remove_reader(m.sock.fileno())
        except (ValueError, OSError):
            pass
        m.sock.close()

    # -------------------------------------------------------------- port forwards (UPnP / NAT-PMP / PCP)
    def add_forward(self, int_port, ext_port):
        if ext_port in self.by_ext and self.by_ext[ext_port].static:
            return ext_port
        if ext_port in self.by_ext:
            ext_port = 0
        if not ext_port:
            for _ in range(100):
                p = self.net.randint(30000, 60000)
                if p not in self.by_ext:
                    ext_port = p
                    break
        m = self._new_mapping(("static", ext_port), int_port, ext_port=ext_port, static=True)
        return m.ext_port if m else None

    def remove_forward(self, ext_port):
        m = self.by_ext.get(ext_port)
        if m is not None and m.static:
            self._drop(m)

    # -------------------------------------------------------------- outside
    def _readable(self, m):
        while True:
            try:
                data, src = m.sock.recvfrom(4096)
            except (BlockingIOError, InterruptedError):
                return
            except OSError:
                return
            self._inbound(m, data, src)

    UNREPLIED = 30.0     # Linux conntrack: a UDP flow nobody answered lives 30 s, an answered one 120 s
    REPLIED = 120.0

    def _fresh(self, m, dst):
        t = m.eps.get(dst)
        return t is not None and time.monotonic() - t < (self.REPLIED if dst in m.replied else self.UNREPLIED)

    def _allowed(self, m, src):
        if m.static or self.filtering == "eif":
            return True
        if self.filtering == "adf":
            t = m.ips.get(src[0])
            return t is not None and time.monotonic() - t < self.REPLIED
        return self._fresh(m, src)

    def _inbound(self, m, data, src):
        now = time.monotonic()
        if self.closed:
            return
        if not m.static and now - m.last_out > self.timeout:
            self.stats["expired_in"] += 1
            return
        if self.blocked.get(src[0], 0) > now:
            self.stats["guard_blocked"] += 1
            return
        if not self._allowed(m, src):
            self.stats["filtered"] += 1
            if self.poison:
                if (m.ext_port, src) not in self.poisoned:
                    self.events.append((round(time.time() % 1000, 3), "poison_in", src, data[4] if len(data) > 4 else None))
                self.poisoned[(m.ext_port, src)] = now + 30.0
            if self.guard:
                q = self.unsolicited[src[0]]
                q.append(now)
                while q and now - q[0] > 2.0:
                    q.popleft()
                if len(q) > 20:
                    self.blocked[src[0]] = now + 30.0
                    self.stats["guard_trips"] += 1
            return
        recv = self.internal.get(m.int_port)
        if recv is None:
            self.stats["no_receiver"] += 1
            return
        if src in m.eps:
            m.eps[src] = now
            m.replied.add(src)
        delay = 0.0
        if src[0] == SERVER_IP:
            delay = self.net.one_way(True)
            if delay is None:
                self.stats["lost"] += 1
                return
        self.stats["in"] += 1
        if delay:
            wire().later(delay, self._deliver_threadsafe, m.int_port, data, src)
        else:
            self._deliver(m.int_port, data, src)

    def _deliver_threadsafe(self, int_port, data, src):
        if not self.closed:
            self.loop.call_soon_threadsafe(self._deliver, int_port, data, src)

    def _deliver(self, int_port, data, src):
        recv = self.internal.get(int_port)
        if recv is not None and not self.closed:
            recv(data, src)

    def close(self):
        self.closed = True
        for m in list(self.maps.values()):
            self._drop(m)


def _no_connreset(sock):
    if os.name != "nt":
        return
    try:
        sock.ioctl(socket.SIO_UDP_CONNRESET, False)
    except (OSError, AttributeError, ValueError):
        pass


class FakeRouter:
    """What a client's port-mapping code talks to in the simulation (UPnP / NAT-PMP / PCP alike):
    a port forward on the home's NAT. Calls arrive on any thread; the NAT is touched on its loop."""
    name = "PCP"

    def __init__(self, home):
        self.home = home

    def _on_loop(self, fn, *a):
        fut = concurrent.futures.Future()

        def run():
            try:
                fut.set_result(fn(*a))
            except Exception as e:      # noqa: BLE001
                fut.set_exception(e)
        self.home.loop.call_soon_threadsafe(run)
        return fut.result(5)

    def external_ip(self):
        return self.home.nat.public_ip

    def add(self, proto, ext_port, int_port, client_ip, lifetime):
        if proto != "UDP":
            return ext_port, lifetime
        got = self._on_loop(self.home.nat.add_forward, int_port, ext_port)
        return got, lifetime

    def remove(self, proto, ext_port, int_port):
        self._on_loop(self.home.nat.remove_forward, ext_port)


class Home:
    def __init__(self, tree, client, nat, private_ip):
        self.tree, self.client, self.nat, self.private_ip = tree, client, nat, private_ip
        self.loop = client._loop


# ============================================================================ control channel delay
class TcpDelayProxy:
    """127.0.0.1:<port> -> the lobby server, every chunk delayed by one_way() in order."""

    def __init__(self, target, one_way):
        self.target, self.one_way = target, one_way
        self.server = None
        self.port = 0
        self.tasks = set()

    async def start(self):
        self.server = await asyncio.start_server(self._conn, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]
        return self

    async def _conn(self, cr, cw):
        try:
            sr, sw = await asyncio.open_connection(*self.target)
        except OSError:
            cw.close()
            return
        for a, b in ((cr, sw), (sr, cw)):
            t = asyncio.ensure_future(self._pump(a, b))
            self.tasks.add(t)
            t.add_done_callback(self.tasks.discard)

    async def _pump(self, r, w):
        loop = asyncio.get_running_loop()
        q = asyncio.Queue()

        async def writer():
            while True:
                due, data = await q.get()
                if data is None:
                    break
                wait = due - loop.time()
                if wait > 0:
                    await asyncio.sleep(wait)
                if w.is_closing():
                    break
                w.write(data)
            w.close()
        wt = asyncio.ensure_future(writer())
        self.tasks.add(wt)
        wt.add_done_callback(self.tasks.discard)
        try:
            while True:
                data = await r.read(65536)
                if not data:
                    break
                q.put_nowait((loop.time() + self.one_way(), data))
        except (ConnectionError, OSError):
            pass
        finally:
            q.put_nowait((loop.time(), None))

    async def close(self):
        self.server.close()
        for t in list(self.tasks):
            t.cancel()


# ============================================================================ stub game
class SimFirewall:
    """A firewall on the home's PC for one program's socket (the stub game's; the launcher's is t5lobby's own
    nat.InboundFilter): "stateful" lets in only datagrams from where this socket sent to (Windows Firewall
    blocking the program), "block" nothing from the network. The same rule as the game's T5_NET_TEST_INBOUND."""

    def __init__(self, mode):
        self.mode = mode
        self.sent = set()
        self.dropped = 0

    def sent_to(self, addr):
        self.sent.add((str(addr[0]), int(addr[1])))

    def passes(self, addr):
        ok = self.mode == "stateful" and (str(addr[0]), int(addr[1])) in self.sent
        if not ok:
            self.dropped += 1
        return ok


def fw_spec(text):
    """'stateful' / 'block' / 'stateful:game' / 'block:launcher' -> {"mode", "game", "launcher"} or None."""
    if not text:
        return None
    mode, _c, who = str(text).partition(":")
    if mode not in ("stateful", "block") or who not in ("", "game", "launcher", "both"):
        raise ValueError(f"firewall {text!r}: expected stateful|block[:game|launcher|both]")
    return {"mode": mode, "game": who in ("", "game", "both"), "launcher": who in ("", "launcher", "both")}


def fw_label(spec):
    if not spec:
        return ""
    who = "" if spec["game"] and spec["launcher"] else ("game" if spec["game"] else "launcher")
    return "[fw " + spec["mode"] + (" " + who if who else "") + "]"


class StubGame:
    """What the netplay layer does with the ticket, as far as addresses go: binds T5_NET_PORT (here: takes
    the internal port over at the NAT), sends to T5_NET_PEER every 30 ms, accepts the opponent's packets
    from any address (they carry the match id) and follows the opponent to a new address. fw: the home PC's
    firewall blocks the game ("stateful" / "block"; packets from the relay bridge on 127.0.0.1 always pass)."""

    def __init__(self, home, ticket, tag, relay_port, fw=None):
        self.home, self.ticket, self.tag = home, ticket, tag
        self.relay_port = relay_port
        self.peer = tuple(ticket.peer)
        self.rx = 0
        self.srcs = collections.Counter()
        self.sock = None
        self.fw = SimFirewall(fw) if fw else None

    def receive_net(self, data, src):
        """A datagram from the network (through the home's NAT): the PC's firewall first."""
        if self.fw is not None and not self.fw.passes(src):
            return
        self.receive(data, src)

    def receive(self, data, src):
        if data[:4] != b"T5NP" or data[4:12] != self.tag or data[12] == self.ticket.slot:
            return
        self.rx += 1
        self.srcs[src] += 1
        if src != self.peer:
            self.peer = src                  # netplay_core relatch_locked()

    async def run(self, seconds=2.0, need=10):
        local = self.peer[0] == "127.0.0.1" and self.peer[1] != self.relay_port   # a relay bridge on this PC
        loop = asyncio.get_running_loop()
        if local:   # a forwarder on this PC: a real socket
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.bind(("127.0.0.1", self.ticket.local_port))
            s.setblocking(False)
            _no_connreset(s)
            self.sock = s

            def readable():
                while True:
                    try:
                        d, a = s.recvfrom(4096)
                    except (BlockingIOError, OSError):
                        return
                    self.receive(d, a)
            loop.add_reader(s.fileno(), readable)
        else:
            self.home.nat.attach(self.ticket.local_port, self.receive_net)
        seq = 0
        t_end = loop.time() + seconds
        try:
            while loop.time() < t_end:
                seq += 1
                pkt = b"T5NP" + self.tag + bytes([self.ticket.slot]) + struct.pack("!I", seq)
                if self.sock is not None:
                    self.sock.sendto(pkt, self.peer)
                else:
                    if self.fw is not None:
                        self.fw.sent_to(self.peer)
                    self.home.nat.outbound(self.ticket.local_port, pkt, self.peer)
                await asyncio.sleep(0.03)
        finally:
            if self.sock is not None:
                loop.remove_reader(self.sock.fileno())
                self.sock.close()
        return self.rx >= need


# ============================================================================ one trial
class Sim:
    def __init__(self, trees, server_tree, rng_seed=1, verbose=False, server_cfg=None, net_cfg=None):
        self.trees = trees
        self.server_tree = server_tree
        self.rng = random.Random(rng_seed)
        self.verbose = verbose
        self.server_cfg = server_cfg or {}
        self.play_seconds = 2.0              # how long the stub games play a relayed match (a bridge may upgrade)
        self.fallback = True                 # a game that heard nothing on the direct path asks for the relay
        self.net_cfg = net_cfg or {}
        self.ip_seq = itertools.count(1)
        self.name_seq = itertools.count(1)
        self.pool = concurrent.futures.ThreadPoolExecutor(max_workers=96)
        self.srv = None
        self.srv_loop = None
        self.build = None

    # -------------------------------------------------------------- server
    def start_server(self):
        tr = self.trees[self.server_tree]
        cfg = dict(host="127.0.0.1", port=0, udp_port=0, udp_port2=-1, db=":memory:", scrypt_n=1 << 10,
                   ready_timeout=10.0, result_timeout=2.0, log_level="ERROR", min_match_seconds=0.0,
                   reconnect_grace=2.0, status_port=0, pair_cooldown=0.0, blind_ready=False,
                   max_per_ip=10000, max_clients=10000, conn_rate=10000.0, conn_burst=10000,
                   max_prelogin=10000, max_relays=10000, max_relays_per_ip=0, max_match_seconds=0.0,
                   state_rate=1000.0, state_burst=1000, udp_ctl_pps=100000, idle_timeout=600.0)
        cfg.update(self.server_cfg)
        import dataclasses
        known = {f.name for f in dataclasses.fields(tr.server.Config)}
        cfg = {k: v for k, v in cfg.items() if k in known}      # (an older server has fewer settings)
        self.srv_loop = tr.proto.new_event_loop()
        ready = threading.Event()
        failed = []

        def run():
            asyncio.set_event_loop(self.srv_loop)
            try:
                self.srv = tr.server.LobbyServer(tr.server.Config(**cfg))
                self.srv_loop.run_until_complete(self.srv.start())
            except Exception as e:     # noqa: BLE001
                failed.append(e)
                ready.set()
                return
            ready.set()
            self.srv_loop.run_forever()
        threading.Thread(target=run, daemon=True).start()
        if not ready.wait(10) or failed:
            raise RuntimeError(f"server did not start: {failed}")
        self.build = tr.buildid.BuildInfo("be80165b84e30b6334baa6d6331b9db4ffd5a6a4", "0123456789abcdef", "sim")

    def stop_server(self):
        fut = asyncio.run_coroutine_threadsafe(self.srv.stop(), self.srv_loop)
        try:
            fut.result(10)
        except Exception:     # noqa: BLE001
            pass
        self.srv_loop.call_soon_threadsafe(self.srv_loop.stop)

    # -------------------------------------------------------------- homes
    async def make_home(self, tree_name, nat_type, mapping_router=False, fw=None):
        tree = self.trees[tree_name]
        n = next(self.ip_seq)
        public_ip = f"127.{10 + n // 250}.{n % 250}.1"
        private_ip = f"192.168.{n % 250}.10"
        net = Net(random.Random(self.rng.random()), **self.net_cfg)
        proxy = await TcpDelayProxy(("127.0.0.1", self.srv.port), net.tcp_delay).start()
        kw = {}
        if mapping_router is not None and _accepts(tree.client.LobbyClient, "port_mapping"):
            kw["port_mapping"] = bool(mapping_router)
        if _accepts(tree.client.LobbyClient, "test_inbound"):
            kw["test_inbound"] = fw["mode"] if fw and fw["launcher"] else ""
        elif fw and fw["launcher"]:
            raise RuntimeError(f"tree {tree_name}: no T5_NET_TEST_INBOUND in its lobby client (a firewall on the "
                               "launcher cannot be simulated)")
        c = tree.client.LobbyClient(f"127.0.0.1:{proxy.port}", self.build, auto_ready=True, **kw)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(self.pool, c.connect)
        home = Home(tree, c, None, private_ip)
        home.fw = fw
        spec = dict(TYPES[nat_type])
        home.nat = await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(
            _make_nat(c._loop, net, public_ip, private_ip, spec), c._loop))
        home.proxy = proxy
        home.router = FakeRouter(home) if mapping_router else None
        if hasattr(c, "_sim_router"):
            pass
        c._router_factory = (lambda h=home: h.router)        # read by clients that can map ports
        HOMES[id(c._loop)] = home
        name = f"Sim{next(self.name_seq)}x{self.rng.randrange(1 << 16):04x}"
        await loop.run_in_executor(self.pool, c.login_guest, name)
        return home

    async def close_home(self, home):
        loop = asyncio.get_running_loop()
        try:
            home.loop.call_soon_threadsafe(home.nat.close)
        except RuntimeError:
            pass
        try:
            await loop.run_in_executor(self.pool, home.client.close)
        except Exception:     # noqa: BLE001
            pass
        HOMES.pop(id(home.loop), None)
        await home.proxy.close()

    # -------------------------------------------------------------- the trial
    async def trial(self, type_a, type_b, tree_a, tree_b, map_a=False, map_b=False, fw_a=None, fw_b=None):
        loop = asyncio.get_running_loop()
        res = {"a": type_a + fw_label(fw_a), "b": type_b + fw_label(fw_b), "tree_a": tree_a, "tree_b": tree_b,
               "path": None, "game": False}
        a = b = None
        try:
            a = await self.make_home(tree_a, type_a, map_a, fw_a)
            b = await self.make_home(tree_b, type_b, map_b, fw_b)
            t0 = time.monotonic()
            cid = await loop.run_in_executor(self.pool, a.client.challenge, b.client.me["id"])
            ev = await loop.run_in_executor(self.pool, b.client.next_event, 15, ("challenged",))
            if ev is None:
                res["error"] = "no challenge"
                return res
            await loop.run_in_executor(self.pool, b.client.answer_challenge, cid, True)
            evs = await asyncio.gather(*(loop.run_in_executor(self.pool, h.client.next_event, 45,
                                                              ("match_start", "match_cancel")) for h in (a, b)))
            res["setup_s"] = round(time.monotonic() - t0, 2)
            if any(e is None or e["t"] != "match_start" for e in evs):
                res["error"] = "cancel: " + ",".join(str(e and e.get("reason")) for e in evs)
                return res
            ta, tb = evs[0]["ticket"], evs[1]["ticket"]
            res["path"] = ta.path if ta.path == tb.path else f"{ta.path}/{tb.path}"
            res["rtt"] = round(ta.rtt_ms, 1)
            t0s = [(h.client.match or {}).get("punch_t0") for h in (a, b)]
            if all(t0s):
                res["skew_ms"] = round(1000 * (t0s[0] - t0s[1]), 1)
            res["offsets"] = [None if h.client.__dict__.get("clock_offset") is None
                              else round(1000 * h.client.clock_offset, 1) for h in (a, b)]
            tag = hashlib.sha1(ta.match_id.encode()).digest()[:8]
            await asyncio.sleep(0.05 + self.rng.random() * 0.6)       # the game takes over the port
            gfw = [h.fw["mode"] if h.fw and h.fw["game"] else None for h in (a, b)]
            ga, gb = (StubGame(a, ta, tag, self.srv.udp.port, gfw[0]),
                      StubGame(b, tb, tag, self.srv.udp.port, gfw[1]))
            secs = self.play_seconds if ta.path == "relay" else 2.0
            fa = asyncio.run_coroutine_threadsafe(ga.run(secs), a.loop)
            fb = asyncio.run_coroutine_threadsafe(gb.run(secs), b.loop)
            ok = await asyncio.gather(asyncio.wrap_future(fa), asyncio.wrap_future(fb))
            if not all(ok) and ta.path in ("direct", "lan") and self.fallback:
                # A game heard nothing on the direct path (a firewall blocks it): what the match driver does
                # (match_driver._watch_direct) -- the side whose game heard nothing asks for the relay, both launchers
                # get a second match_start (a new ticket through the relay bridge) and the games start again.
                deaf = [h for h, g in ((a, ga), (b, gb)) if g.rx == 0] or [a]
                fn = getattr(deaf[0].client, "nat_fallback", None)
                agreed = fn is not None and await loop.run_in_executor(self.pool, fn, ta.match_id)
                res["fallback"] = bool(agreed)
                if agreed:
                    evs = await asyncio.gather(*(loop.run_in_executor(self.pool, h.client.next_event, 20,
                                                                      ("match_start", "match_cancel")) for h in (a, b)))
                    if any(e is None or e["t"] != "match_start" for e in evs):
                        res["error"] = "fallback: " + ",".join(str(e and (e.get("reason") or e["t"])) for e in evs)
                        return res
                    ta, tb = evs[0]["ticket"], evs[1]["ticket"]
                    res["path"] = "fallback/" + (ta.path if ta.path == tb.path else f"{ta.path}/{tb.path}")
                    res["setup_s"] = round(time.monotonic() - t0, 2)
                    ga, gb = (StubGame(a, ta, tag, self.srv.udp.port, gfw[0]),
                              StubGame(b, tb, tag, self.srv.udp.port, gfw[1]))
                    fa = asyncio.run_coroutine_threadsafe(ga.run(self.play_seconds), a.loop)
                    fb = asyncio.run_coroutine_threadsafe(gb.run(self.play_seconds), b.loop)
                    ok = await asyncio.gather(asyncio.wrap_future(fa), asyncio.wrap_future(fb))
            res["game"] = all(ok)
            res["rx"] = [ga.rx, gb.rx]
            res["bridge"] = [getattr(h.client, "_bridge", None) is not None for h in (a, b)]
            if ga.fw or gb.fw:
                res["fw_dropped"] = [g.fw.dropped if g.fw else 0 for g in (ga, gb)]
            srcs = set(ga.srcs) | set(gb.srcs)
            res["game_via"] = "relay" if any(s[0] == SERVER_IP for s in srcs) and not any(
                s[0] != SERVER_IP for s in srcs) else ("direct" if srcs else "-")
            if self.verbose and ta.path == "relay":
                for h, tk in ((a, ta), (b, tb)):
                    br = getattr(h.client, "_bridge", None)
                    print("   bridge", tk.peer, br and (br.bursts, br.path, br.stats, dict(br.gs.last_ok),
                                                     len(br.gs.punch_targets())), flush=True)
            ups = [list(getattr(h.client, "upgrades", None) or []) for h in (a, b)]
            if any(ups):
                res["upgrades"] = ups
                res["upgraded"] = all(u and u[-1][1] == "direct" for u in ups)
            if self.verbose:
                print(res, a.nat.stats, b.nat.stats, flush=True)
                if res.get("path") == "relay":
                    print("   A", a.nat.public_ip, a.nat.events[:6])
                    print("   B", b.nat.public_ip, b.nat.events[:6])
            return res
        except Exception as e:     # noqa: BLE001
            res["error"] = f"{type(e).__name__}: {e}"
            return res
        finally:
            if self.verbose and res.get("error"):
                print("FAIL", res, a and a.nat.stats, b and b.nat.stats, flush=True)
            for h in (a, b):
                if h is not None:
                    await self.close_home(h)


def _accepts(cls, kw):
    import inspect
    try:
        return kw in inspect.signature(cls.__init__).parameters
    except (TypeError, ValueError):
        return False


async def _make_nat(loop, net, public_ip, private_ip, spec):
    return Nat(asyncio.get_running_loop(), net, public_ip, private_ip, **spec)


# ============================================================================ the matrix
def summarize(results):
    rows = collections.OrderedDict()
    for r in results:
        k = (r["a"], r["b"])
        d = rows.setdefault(k, collections.Counter())
        d["n"] += 1
        p = r.get("path")
        if p in ("direct", "lan"):
            d["direct"] += 1
        elif p == "relay":
            d["relay"] += 1
        elif str(p).startswith("fallback/"):
            d["fallback"] += 1                 # direct first, then the relay: the game heard nothing directly
        else:
            d["failed"] += 1
        if r.get("game"):
            d["game"] += 1
        if r.get("upgraded"):
            d["upgraded"] += 1
        d.setdefault("setup", [])
        if r.get("setup_s") is not None:
            d["setup"].append(r["setup_s"])
    return rows


def print_table(rows, title=""):
    if title:
        print(title)
    print(f"{'pair':28s} {'n':>4s} {'direct':>8s} {'relay':>6s} {'upgr':>5s} {'fallbk':>6s} {'fail':>5s} "
          f"{'game ok':>8s} {'setup s':>8s}")
    for (a, b), d in rows.items():
        n = d["n"]
        st = statistics.median(d["setup"]) if d["setup"] else float("nan")
        print(f"{a + ' + ' + b:28s} {n:4d} {100.0 * d['direct'] / n:7.0f}% {d['relay']:6d} {d['upgraded']:5d} "
              f"{d['fallback']:6d} {d['failed']:5d} {d['game']:8d} {st:8.1f}")


async def run_matrix(sim, pairs, trials, parallel, tree_a, tree_b, maps=(False, False), progress=True,
                     fws=(None, None)):
    sem = asyncio.Semaphore(parallel)
    results = []
    done = [0]
    total = len(pairs) * trials

    async def one(a, b):
        async with sem:
            r = await sim.trial(a, b, tree_a, tree_b, *maps, *fws)
            results.append(r)
            done[0] += 1
            if progress and done[0] % 10 == 0:
                print(f"  {done[0]}/{total}", flush=True)

    jobs = [one(a, b) for a, b in pairs for _ in range(trials)]
    random.Random(7).shuffle(jobs)
    await asyncio.gather(*jobs)
    return results


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--base", default=os.path.normpath(os.path.join(LOBBY, "..", "..", "base", "lobby")),
                    help="lobby/ folder of the older tree (for --server/--a/--b base)")
    ap.add_argument("--server", default="new", choices=("new", "base"))
    ap.add_argument("--a", default="new", choices=("new", "base"))
    ap.add_argument("--b", default="new", choices=("new", "base"))
    ap.add_argument("--types", default=",".join(BASIC))
    ap.add_argument("--pairs", default="", help="a:b,c:d (default: every unordered pair of --types)")
    ap.add_argument("--trials", type=int, default=50)
    ap.add_argument("--parallel", type=int, default=8)
    ap.add_argument("--map-a", action="store_true", help="home A's router answers UPnP/NAT-PMP/PCP")
    ap.add_argument("--map-b", action="store_true")
    ap.add_argument("--fw-a", default="", help="home A's PC has a firewall that blocks the game and the launcher: "
                    "stateful (Windows Firewall: replies only) or block (nothing from the network); "
                    "MODE:game or MODE:launcher blocks only that program")
    ap.add_argument("--fw-b", default="")
    ap.add_argument("--no-fallback", action="store_true", help="a game that hears nothing on the direct path does not "
                    "ask for the relay (the 1.1.2 behaviour)")
    ap.add_argument("--loss", type=float, default=0.02, help="UDP loss on every leg")
    ap.add_argument("--tcp-rto", type=float, default=0.03, help="share of control messages delayed by a TCP resend")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--play", type=float, default=2.0, help="seconds the stub games play a relayed match")
    ap.add_argument("--json", default="")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)

    trees = {"new": Tree("t5lobby", os.path.join(LOBBY, "t5lobby"))}
    if "base" in (a.server, a.a, a.b):
        trees["base"] = Tree("t5lobby_base", os.path.join(a.base, "t5lobby"))
    if a.pairs:
        pairs = [tuple(p.split(":")) for p in a.pairs.split(",")]
    else:
        types = a.types.split(",")
        pairs = [(x, y) for i, x in enumerate(types) for y in types[i:]]
    sim = Sim(trees, a.server, rng_seed=a.seed, verbose=a.verbose, net_cfg={"loss": a.loss, "tcp_rto": a.tcp_rto})
    sim.play_seconds = a.play
    sim.fallback = not a.no_fallback
    sim.start_server()
    loop = trees["new"].proto.new_event_loop()
    asyncio.set_event_loop(loop)
    t0 = time.monotonic()
    try:
        results = loop.run_until_complete(run_matrix(sim, pairs, a.trials, a.parallel, a.a, a.b,
                                                     (a.map_a, a.map_b), fws=(fw_spec(a.fw_a), fw_spec(a.fw_b))))
    finally:
        sim.stop_server()
    rows = summarize(results)
    print_table(rows, f"server {a.server}, A {a.a}, B {a.b}, {a.trials} trials per pair, "
                      f"{time.monotonic() - t0:.0f} s")
    errs = collections.Counter(r.get("error") for r in results if r.get("error"))
    if errs:
        print("errors:", dict(errs))
    if a.json:
        with open(a.json, "w") as f:
            json.dump({"args": vars(a), "results": results}, f, indent=1, default=str)
    return 0


if __name__ == "__main__":
    sys.exit(main())
