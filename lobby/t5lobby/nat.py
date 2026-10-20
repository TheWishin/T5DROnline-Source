"""Client side of NAT traversal, on the UDP socket the game will use.

While the lobby owns the game socket it:
  1. registers it with the server (the server sees its public endpoint; a second
     server port tells whether the NAT maps per destination = "symmetric"),
  2. punches: sends U_PUNCH to every candidate endpoint of the peer at the same
     time as the peer does the same toward us, until a packet carrying
     F_HEARD arrives (= both directions work). With a server that plans the
     punch (protocol "nat2", docs/NETPLAY.md "Getting a direct connection") both
     sides start at the same moment, punch for several seconds at a steady
     rate, and also walk a range of predicted ports when the peer's NAT maps
     every destination to a new port ("symmetric"),
  3. or binds to the server's relay when punching fails,
  4. measures the round trip to the chosen peer endpoint (U_PPING / U_PPONG),
and then hands the port (or the socket) to the game. It answers the peer's
punches and pings until it is closed, so both sides can finish their checks.

On the relay path between two clients that both speak "nat2" the socket stays
here instead: RelayBridge carries the game's packets (the game talks to it on
127.0.0.1) to the relay, keeps trying the direct path in the background, and
moves the match onto it as soon as it works both ways. The game's packets themselves never wait for the
lobby client's event loop: a thread of the bridge's own forwards them (RelayBridge, "The pump").
"""
import asyncio
import ipaddress
import os
import select
import socket
import statistics
import sys
import threading
import time

from . import proto

def bind_ip():
    """The address the game socket binds: every interface ("0.0.0.0"), or T5_NET_BIND when it is an IPv4
    address. Only test tools set it (127.0.0.1: two players on this PC, nothing reaches the network, no
    Windows Firewall prompt; the game reads the same variable, src/netplay/net_bind.h). A player's launcher
    never sets it."""
    v = os.environ.get("T5_NET_BIND", "").strip()
    if not v:
        return "0.0.0.0"
    try:
        return str(ipaddress.IPv4Address(v))
    except ValueError:
        return "0.0.0.0"


KIND_RANK = {"local": 0, "mapped": 1, "public": 1, "reflexive": 2, "predicted": 2, "relay": 3}

# T5_NET_TEST_INBOUND (tests only; docs/NETPLAY.md "When Windows Firewall blocks the game"): Windows Firewall
# blocking this program, emulated on its UDP sockets -- the game has the same switch (src/netplay/netplay_core.cpp
# test_inbound_pass). The real firewall is never touched.
TEST_INBOUND_MODES = ("stateful", "block")


def test_inbound_mode(value=None):
    """'stateful' / 'block' / None (off) from `value`, or from T5_NET_TEST_INBOUND when value is None."""
    v = os.environ.get("T5_NET_TEST_INBOUND", "") if value is None else (value or "")
    v = str(v).strip().lower()
    return v if v in TEST_INBOUND_MODES else None


class InboundFilter:
    """What reaches one UDP socket of a program the firewall blocks (tests only).

    stateful: only datagrams from an address:port this socket has sent to get in -- Windows Firewall for a
    blocked program (Cancel on its question, or a block rule): its own packets go out and the replies to them
    come back, anything unsolicited is dropped. block: nothing gets in but datagrams from `local` (127.0.0.1;
    stricter than Windows: a firewall that blocks the program completely). The NAT simulator, where every
    datagram comes from its simulated internet, sets `local` empty."""

    def __init__(self, mode, local=("127.0.0.1",)):
        self.mode = mode
        self.local = frozenset(local)
        self.sent = set()
        self.dropped = 0
        self.first_drops = []            # (address, port) of the first few dropped senders, for logs and tests

    def sent_to(self, addr):
        if self.mode == "stateful":
            self.sent.add((str(addr[0]), int(addr[1])))

    def passes(self, addr):
        a = (str(addr[0]), int(addr[1]))
        ok = a in self.sent if self.mode == "stateful" else a[0] in self.local
        if not ok:
            self.dropped += 1
            if len(self.first_drops) < 8 and a not in self.first_drops:
                self.first_drops.append(a)
        return ok


def make_inbound_filter(mode):
    mode = test_inbound_mode(mode) if mode is not None else test_inbound_mode()
    return InboundFilter(mode) if mode else None


def local_ipv4s(target_ip):
    """This PC's IPv4 addresses worth offering to a peer behind the same router."""
    if bind_ip() != "0.0.0.0":
        return [bind_ip()]          # T5_NET_BIND: the game socket is reachable only there
    out = []

    def add(ip):
        if ip and ip not in out and not ip.startswith(("0.", "169.254.")):
            out.append(ip)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect((target_ip, 9))       # no packet is sent; picks the outgoing interface
            add(s.getsockname()[0])
        finally:
            s.close()
    except OSError:
        pass
    try:
        for ai in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET, socket.SOCK_DGRAM):
            add(ai[4][0])
    except OSError:
        pass
    if not target_ip.startswith("127."):
        out = [ip for ip in out if not ip.startswith("127.")]
    return out


def open_udp_socket(port=0):
    """Bind a UDP socket on all interfaces (T5_NET_BIND: that address, see bind_ip); falls back to any free
    port when `port` is taken."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.bind((bind_ip(), port))
    except OSError:
        if not port:
            s.close()
            raise
        s.bind((bind_ip(), 0))
    proto.disable_udp_connreset(s)
    s.setblocking(False)
    return s


class GameSocket(asyncio.DatagramProtocol):
    def __init__(self, server, port2, token, tag, side, block_direct=False, inbound=None):
        self.server = server                 # (ip, udp_port)
        self.server2 = (server[0], port2) if port2 else None
        self.token = token
        self.tag = tag
        self.side = side
        self.block_direct = block_direct     # testing: ignore the peer unless it comes through the relay
        # testing: T5_NET_TEST_INBOUND -- this program blocked by the firewall (InboundFilter; None = off)
        self.inbound = inbound if isinstance(inbound, InboundFilter) else make_inbound_filter(inbound)
        self.relay = None                    # the relay this socket bound to (the lobby server's, or a regional one)
        self.relay_token = None              # ... and the token it bound with (a regional relay has its own)
        self.transport = None
        self.sock = None
        self.port = 0
        self.waiters = {}
        self.heard = {}                      # addr -> first time we got a punch from it
        self.confirmed = {}                  # addr -> time we got F_HEARD from it
        self.last_ok = {}                    # addr -> LAST time we got F_HEARD from it (relay bridge)
        self.last_rx = {}                    # addr -> last time anything from it arrived
        self.on_game = None                  # relay bridge: callback(data, addr) for the game's own packets
        self.plan = ([], [])                 # (candidates, scan) of the last punch: what a relay bridge retries
        self.confirm_event = asyncio.Event()
        self.closed = asyncio.get_running_loop().create_future()
        self.seq = 0
        self.dup = None
        self.stats = {"rx": 0, "tx": 0, "pongs": 0}
        # a low-TTL punch sets the socket's TTL around its one send: a relay bridge's pump thread sending the game's
        # packets on the same socket takes this lock too, so none of them leaves with the punch's TTL (and dies)
        self.ttl_lock = threading.Lock()

    @classmethod
    async def open(cls, port, *args, keep_dup=False, **kw):
        loop = asyncio.get_running_loop()
        self = cls(*args, **kw)
        sock = open_udp_socket(port)
        if keep_dup:
            self.dup = sock.dup()            # survives transport.close(): for socket handover
        await loop.create_datagram_endpoint(lambda: self, sock=sock)
        self.sock = sock
        try:
            self.ttl0 = sock.getsockopt(socket.IPPROTO_IP, socket.IP_TTL) or 64
        except OSError:
            self.ttl0 = 64
        self.port = sock.getsockname()[1]
        return self

    # ---------------------------------------------------------------- transport
    def connection_made(self, transport):
        self.transport = transport

    def connection_lost(self, exc):
        if not self.closed.done():
            self.closed.set_result(True)

    def error_received(self, exc):
        pass

    def send(self, data, addr, ttl=None):
        """ttl: send this one packet with a small IP TTL -- it opens this side's NAT toward `addr` and dies a
        hop or two later, before it reaches the peer's router (see punch(), ttl_open)."""
        if self.transport is None or self.transport.is_closing():
            return
        if self.inbound is not None:
            self.inbound.sent_to(addr)
        if ttl is None:
            self.transport.sendto(data, addr)
        else:
            # On the socket itself, not through the transport: a packet the transport queued would leave
            # later with the TTL already put back.
            try:
                with self.ttl_lock:
                    self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_TTL, ttl)
                    try:
                        self.sock.sendto(data, addr)
                    finally:
                        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_TTL, self.ttl0)
            except OSError:
                return
        self.stats["tx"] += 1

    async def close(self):
        if self.transport is not None:
            self.transport.close()
            await asyncio.wait_for(asyncio.shield(self.closed), 2)

    def _wait(self, key):
        fut = asyncio.get_running_loop().create_future()
        self.waiters[key] = fut
        return fut

    def _resolve(self, key, value):
        fut = self.waiters.pop(key, None)
        if fut is not None and not fut.done():
            fut.set_result(value)

    def datagram_received(self, data, addr):
        if self.inbound is not None and not self.inbound.passes(addr):
            return                           # (the emulated firewall dropped it: this program never sees it)
        self.stats["rx"] += 1
        self.last_rx[addr] = time.monotonic()
        kind = proto.udp_type(data)
        if kind is None:
            if self.on_game is not None and data[:4] == proto.GAME_MAGIC:
                self.on_game(data, addr)
            return
        from_server = addr == self.server or addr == self.server2 or addr == self.relay
        if kind in (proto.U_REG_ACK, proto.U_PROBE_ACK, proto.U_RELAY_ACK) and from_server:
            if len(data) == proto.TOKEN_ACK.size:
                _k, tok, seen = proto.un_token_ack(data)
                if tok == self.token or (kind == proto.U_RELAY_ACK and tok == self.relay_token):
                    self._resolve(kind, seen)
            return
        if kind == proto.U_SPONG and from_server and len(data) == proto.PING.size:
            _m, _k, _v, seq, t = proto.PING.unpack(data)
            self._resolve(("s", seq), time.perf_counter() - t)
            return
        if self.block_direct and addr != self.server and addr != self.relay:
            return
        if kind == proto.U_PUNCH and len(data) == proto.PUNCH.size:
            _m, _k, _v, tag, side, flags, seq = proto.PUNCH.unpack(data)
            if tag != self.tag or side == self.side:
                return
            now = time.monotonic()
            if addr not in self.heard:
                self.heard[addr] = now
            self.send(proto.pk_punch(self.tag, self.side, proto.F_HEARD, seq), addr)
            if flags & proto.F_HEARD:
                self.last_ok[addr] = now
                if addr not in self.confirmed:
                    self.confirmed[addr] = now
                    self.confirm_event.set()
        elif kind in (proto.U_PPING, proto.U_PPONG) and len(data) == proto.PPING.size:
            _m, _k, _v, tag, side, seq, t = proto.PPING.unpack(data)
            if tag != self.tag or side == self.side:
                return
            if kind == proto.U_PPING:
                self.send(proto.pk_pping(proto.U_PPONG, self.tag, self.side, seq, t), addr)
            else:
                self.stats["pongs"] += 1
                self._resolve(("p", seq), (time.perf_counter() - t, addr))

    # ---------------------------------------------------------------- steps
    async def register(self, timeout=4.0, probe_wait=1.0):
        """-> (public endpoint, probe endpoint or None), or None when the server never answered.
        probe_wait: seconds from the start to wait for the probe port's answer once the main port's is in
        (the probe port may be firewalled)."""
        reg = self._wait(proto.U_REG_ACK)
        prb = self._wait(proto.U_PROBE_ACK) if self.server2 else None
        t_end = time.monotonic() + timeout
        public = None
        while time.monotonic() < t_end:
            if not reg.done():
                self.send(proto.pk_token(proto.U_REGISTER, self.token), self.server)
            if prb is not None and not prb.done():
                self.send(proto.pk_token(proto.U_PROBE, self.token), self.server2)
            await asyncio.wait([f for f in (reg, prb) if f is not None and not f.done()] or [reg],
                               timeout=0.15)
            if reg.done():
                public = reg.result()
                if prb is None or prb.done():
                    break
                if public and time.monotonic() > t_end - timeout + probe_wait:
                    break                  # the probe port may be firewalled; don't wait for it
        if public is None:
            return None
        probe = prb.result() if prb is not None and prb.done() else None
        return public, probe

    def _punch_to(self, addr, low_ttl=False):
        self.seq += 1
        pkt = proto.pk_punch(self.tag, self.side, proto.F_HEARD if addr in self.heard else 0, self.seq)
        if low_ttl:
            for ttl in self.OPEN_TTLS:
                self.send(pkt, addr, ttl=ttl)
        else:
            self.send(pkt, addr)

    OPEN_TTLS = (2, 3)       # past this PC's router (and a second NAT right behind it), never as far as the peer's

    async def punch(self, candidates, timeout=3.0, linger=0.12, interval=0.03, scan=(), scan_period=0.8,
                    slow_start=0.0, slow_interval=0.2, ttl_open=0.0, peer_open=None, ttl_open_max=2.0):
        """candidates: [(ip, port, kind)]. -> (addr, kind) of the best two-way path, or None.

        Every candidate (and every address a punch came from) gets a punch each `interval` seconds -- the
        first `slow_start` seconds only each `slow_interval`: a router that counts unsolicited packets must
        not take the first ones, sent before the peer's own punches opened its NAT, for a flood. `scan`:
        [(ip, [ports])] predicted endpoints of a NAT that maps every destination to a new port, walked in
        order: the first pass quickly (each new destination opens a mapping on a symmetric NAT of ours, in
        the same order as the peer walks over our ports), then once every `scan_period` seconds.
        `ttl_open`: for the first seconds every punch goes out with a TTL of 2 and 3 only. That opens this
        side's NAT toward the peer without reaching the peer's router, so when the full punches start (both
        sides start together) each router has already sent toward the other: none of them sees an
        unsolicited packet first -- some routers then move their side to another port, answer with an ICMP
        error that closes the other side's mapping, or count it as a flood. `peer_open`: an asyncio.Event
        set when the server says the peer has started too; the low-TTL phase then lasts until it is set
        (at most `ttl_open_max` seconds), so a peer whose message TCP had to send again still opens its
        NAT before the first full punch gets there."""
        kinds = {(ip, port): kind for ip, port, kind in candidates}
        scan_list = []
        for ip, ports in scan:
            for port in ports:
                if (ip, port) not in kinds:
                    kinds[(ip, port)] = "predicted"
                    scan_list.append((ip, port))
        scanned = set(scan_list)
        regular = [a for a in kinds if a not in scanned]
        if candidates or scan:              # (a retry with nothing new keeps the plan for a relay bridge)
            self.plan = (list(candidates), [(ip, list(ports)) for ip, ports in scan])
        t0 = time.monotonic()
        due = {}
        scan_i = 0                          # first pass: the next scan port never punched yet
        tick = 0.015
        first_ok = None
        opened = t0 if ttl_open <= 0 else None    # when the full punches began
        while True:
            now = time.monotonic()
            low = now - t0 < ttl_open or (
                ttl_open > 0 and peer_open is not None and not peer_open.is_set() and now - t0 < ttl_open_max)
            if not low and opened is None:
                opened = now                        # the full punches start: a fresh pass over everything
                due.clear()
                scan_i = 0
            step = interval if low else (slow_interval if now - opened < slow_start else interval)
            for addr in regular + [a for a in self.heard if a not in kinds]:
                if due.get(addr, 0.0) <= now:
                    self._punch_to(addr, low_ttl=low and addr not in self.heard)
                    due[addr] = now + step
            if scan_list:
                # first pass in order, 4 new destinations per tick; then each port again every scan_period
                for _ in range(4):
                    if scan_i >= len(scan_list):
                        break
                    addr = scan_list[scan_i]
                    self._punch_to(addr, low_ttl=low)
                    due[addr] = now + scan_period
                    scan_i += 1
                for addr in scan_list[:scan_i]:
                    if due.get(addr, 0.0) <= now:
                        self._punch_to(addr, low_ttl=low)
                        due[addr] = now + scan_period
            if self.confirmed and first_ok is None:
                first_ok = now
            if first_ok is not None and (now - first_ok >= linger or
                                         any(kinds.get(a) == "local" for a in self.confirmed)):
                break
            if now - t0 >= timeout:
                break
            self.confirm_event.clear()
            try:
                await asyncio.wait_for(self.confirm_event.wait(), tick if scan_list else min(interval, step))
            except asyncio.TimeoutError:
                pass
        if not self.confirmed:
            return None
        best = min(self.confirmed, key=lambda a: (KIND_RANK.get(kinds.get(a, "reflexive"), 9), self.confirmed[a]))
        # Keep the peer's side of the handshake complete: a few more F_HEARD punches.
        for _ in range(3):
            self.send(proto.pk_punch(self.tag, self.side, proto.F_HEARD, self.seq), best)
        return best, kinds.get(best, "reflexive")

    def punch_targets(self):
        """Every endpoint of the last plan (candidates, predicted ports) and every address heard from."""
        cands, scan = self.plan
        targets = [(ip, port) for ip, port, _k in cands]
        targets += [(ip, p) for ip, ports in scan for p in ports]
        targets += [a for a in self.heard if a not in targets]
        return list(dict.fromkeys(targets))

    async def relay_bind(self, relay, timeout=4.0, token=None):
        """Bind this socket into the match's relay session: the lobby server's (with the match token) or a
        regional relay node's (with the bind token the server handed out for it). -> True once acknowledged."""
        self.relay = tuple(relay)
        self.relay_token = token or self.token
        ack = self._wait(proto.U_RELAY_ACK)
        t_end = time.monotonic() + timeout
        while time.monotonic() < t_end and not ack.done():
            self.send(proto.pk_token(proto.U_RELAY_BIND, self.relay_token), self.relay)
            await asyncio.wait([ack], timeout=0.1)
        return ack.done()

    async def measure(self, addr, n=12, interval=0.02, timeout=4.0, need=3):
        """Round trips to the peer (through `addr`). -> (median ms, jitter ms, samples) or None."""
        rtts = []
        t_end = time.monotonic() + timeout
        pending = []
        keys = []
        while time.monotonic() < t_end and len(rtts) < n:
            self.seq += 1
            keys.append(("p", self.seq))
            fut = self._wait(keys[-1])
            pending.append(fut)
            self.send(proto.pk_pping(proto.U_PPING, self.tag, self.side, self.seq, time.perf_counter()), addr)
            await asyncio.sleep(interval)
            for f in [f for f in pending if f.done()]:
                pending.remove(f)
                rtts.append(f.result()[0] * 1000.0)
        await asyncio.sleep(min(0.25, max(0.0, t_end - time.monotonic())))
        rtts += [f.result()[0] * 1000.0 for f in pending if f.done()]
        for f in pending:
            if not f.done():
                f.cancel()
        for k in keys:
            self.waiters.pop(k, None)
        if len(rtts) < need:
            return None
        rtts.sort()
        med = statistics.median(rtts)
        p90 = rtts[min(len(rtts) - 1, int(round(0.9 * (len(rtts) - 1))))]
        return med, max(0.0, p90 - med), len(rtts)


def free_udp_port():
    """A UDP port that is free on this PC right now (for the game behind a relay bridge)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.bind((bind_ip(), 0))
        return s.getsockname()[1]
    finally:
        s.close()


class RelayBridge(asyncio.DatagramProtocol):
    """The relay path between two "nat2" clients, through this launcher.

    The game binds `game_port` and talks to 127.0.0.1:`port` (its T5_NET_PEER). Its packets go out on the
    punched game socket: to the lobby server's relay at first, straight to the opponent's game socket once
    the direct path works both ways (a punch carrying F_HEARD came from there within the last 2 s).
    Whatever the opponent's game sends arrives on
    the game socket, through the relay or directly, and is handed to the game -- the game always sees one
    peer address, 127.0.0.1:`port`, so it never has to follow anything. The opponent's launcher does the
    same, so each side switches on its own and packets from either path count all the time. When the
    direct path is quiet for 2.5 s the bridge goes back to the relay, which a peer ping every 5 s keeps
    open (the server sweeps relay sessions idle for 2 minutes).

    The direct path is tried in bursts: 3 s of punches (the first half second with a low TTL, as in the
    punch phase) every 40 s, both launchers at the same server time (the match's start time + 35 s, then
    every 40 s). The silence in between matters: what made the punch phase fail on many routers -- a
    connection entry left by an early punch, a flood block -- lasts 30 s from the last packet and would
    never end under a steady trickle.

    The pump (relay-smooth, 1.1.4). The game's packets used to be forwarded by the lobby client's event loop,
    one per loop pass, behind whatever else that loop did (the lobby's messages, timers), on a thread of normal
    priority -- next to a game whose threads run above normal and keep a 4-core PC busy, a packet could wait a
    whole time slice before the launcher forwarded it, on both PCs of a relayed match, and arrive bunched with
    the next ones: deeper rollbacks, more stalls and time-sync sleeps on exactly the matches that already have
    the longest round trip. Now a thread of the bridge's own, at the priority of the game's own network thread
    (src/netplay rx_thread: THREAD_PRIORITY_HIGHEST), waits on both sockets and forwards every game packet the
    moment it arrives; everything else that arrives on the game socket (punches, pings, the relay's answers)
    goes to the event loop as before. While a bridge pumps, the interpreter hands the GIL over after 1 ms
    instead of 5 (sys.setswitchinterval), so a launcher thread busy in Python holds the pump up 1 ms at most.
    T5_RELAY_PUMP=0: the old way (tests, comparisons)."""

    SWITCH_FRESH = 2.0
    DIRECT_QUIET = 2.5
    KEEP_DIRECT = 1.0
    RELAY_KEEPALIVE = 5.0
    FIRST_BURST = 35.0
    BURST_PERIOD = 40.0
    BURST = 3.0
    BURST_OPEN = 0.5
    BURST_INTERVAL = 0.05
    TICK = 0.25

    def __init__(self, gs, relay, on_switch=None, first_burst=None):
        self.gs = gs
        self.next_burst = first_burst if first_burst is not None else time.monotonic() + self.FIRST_BURST
        self.bursts = 0
        self.relay = tuple(relay)
        self.on_switch = on_switch
        self.upstream = self.relay
        self.transport = None
        self.port = 0
        self.game_port = 0
        self.game = None
        self.task = None
        self.closed = False
        self.switches = []           # (time.time(), "direct" | "relay", addr)
        self.stats = {"to_game": 0, "from_game": 0, "direct_in": 0, "relay_in": 0, "strangers": 0}
        self.sock = None             # the socket the game talks to (127.0.0.1)
        self.pump = None             # _Pump while it forwards the game's packets

    @classmethod
    async def open(cls, gs, relay, on_switch=None, game_port=0, first_burst=None):
        """first_burst: time.monotonic() of the first burst (default: 35 s from now)."""
        self = cls(gs, relay, on_switch, first_burst)
        loop = asyncio.get_running_loop()
        self.game_port = game_port or free_udp_port()
        self.game = ("127.0.0.1", self.game_port)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.bind(("127.0.0.1", 0))
        proto.disable_udp_connreset(s)
        s.setblocking(False)
        await loop.create_datagram_endpoint(lambda: self, sock=s)
        self.sock = s
        self.port = s.getsockname()[1]
        gs.on_game = self._from_net
        if os.environ.get("T5_RELAY_PUMP", "1") != "0":
            _Pump.start_for(self, loop)
        self.task = asyncio.ensure_future(self._run())
        return self

    @property
    def path(self):
        return "relay" if self.upstream == self.relay else "direct"

    # ------------------------------------------------------------- the game's side (127.0.0.1)
    def connection_made(self, transport):
        self.transport = transport

    def error_received(self, exc):
        pass

    def datagram_received(self, data, addr):
        if addr != self.game or data[:4] != proto.GAME_MAGIC:
            return
        self.stats["from_game"] += 1
        self.gs.send(data, self.upstream)

    def _game_to_net(self, data, addr):
        """The pump: a packet from the game's side, out on the game socket at once."""
        if addr != self.game or data[:4] != proto.GAME_MAGIC:
            return
        self.stats["from_game"] += 1
        gs = self.gs
        up = self.upstream
        if gs.inbound is not None:
            gs.inbound.sent_to(up)
        try:
            with gs.ttl_lock:
                gs.sock.sendto(data, up)
        except OSError:
            return                    # (a full send buffer, an unreachable address: lost, like on the wire)
        gs.stats["tx"] += 1

    def _net_in(self, data, addr):
        """The pump: a packet on the game socket. The opponent's game packets go to the game at once (and count
        for the path's liveness like before); anything else is the event loop's (GameSocket.datagram_received)."""
        gs = self.gs
        if data[:4] != proto.GAME_MAGIC or proto.udp_type(data) is not None:
            self.pump.loop.call_soon_threadsafe(gs.datagram_received, data, addr)
            return
        if gs.inbound is not None and not gs.inbound.passes(addr):
            return
        gs.stats["rx"] += 1
        gs.last_rx[addr] = time.monotonic()
        self._from_net(data, addr)

    # ------------------------------------------------------------- the network's side (game socket)
    def _from_net(self, data, addr):
        if addr == self.relay:
            self.stats["relay_in"] += 1
        elif addr in self.gs.heard or addr in self.gs.confirmed or addr == self.upstream:
            self.stats["direct_in"] += 1
        else:
            self.stats["strangers"] += 1          # only the opponent's endpoints; the game checks the key too
            return
        if self.pump is not None:
            try:
                self.sock.sendto(data, self.game)
            except OSError:
                return
            self.stats["to_game"] += 1
        elif self.transport is not None and not self.transport.is_closing():
            self.transport.sendto(data, self.game)
            self.stats["to_game"] += 1

    def _switch(self, addr):
        self.upstream = tuple(addr) if addr else self.relay
        self.switches.append((time.time(), self.path, addr))
        if self.on_switch is not None:
            try:
                self.on_switch(self.path, addr)
            except Exception:      # noqa: BLE001 -- a UI callback must not stop the bridge
                pass

    async def _run(self):
        gs = self.gs
        last_keep = last_direct = time.monotonic()
        burst_t0 = None
        due = {}
        while not self.closed:
            await asyncio.sleep(self.BURST_INTERVAL if burst_t0 is not None else self.TICK)
            now = time.monotonic()
            if self.upstream == self.relay:
                if burst_t0 is None and now >= self.next_burst:
                    burst_t0, due = now, {}
                    self.bursts += 1
                    while self.next_burst <= now:
                        self.next_burst += self.BURST_PERIOD
                if burst_t0 is not None:
                    low = now - burst_t0 < self.BURST_OPEN
                    for addr in gs.punch_targets():
                        if due.get(addr, 0.0) <= now:
                            gs._punch_to(addr, low_ttl=low and addr not in gs.heard)
                            due[addr] = now + self.BURST_INTERVAL
                    if now - burst_t0 >= self.BURST:
                        burst_t0 = None
                fresh = [a for a, t in gs.last_ok.items() if now - t < self.SWITCH_FRESH and a != self.relay]
                if fresh:
                    burst_t0 = None
                    self._switch(max(fresh, key=lambda a: gs.last_ok[a]))
                    last_direct = now
            else:
                up = self.upstream
                if now - last_direct >= self.KEEP_DIRECT:
                    gs._punch_to(up)                  # answered with F_HEARD: the path still works both ways
                    last_direct = now
                if now - gs.last_rx.get(up, 0.0) > self.DIRECT_QUIET:
                    self._switch(None)
            if now - last_keep >= self.RELAY_KEEPALIVE:
                gs.seq += 1
                gs.send(proto.pk_pping(proto.U_PPING, gs.tag, gs.side, gs.seq, time.perf_counter()), self.relay)
                last_keep = now

    async def close(self):
        if self.closed:
            return
        self.closed = True
        if self.pump is not None:
            await asyncio.get_running_loop().run_in_executor(None, self.pump.finish)
        if self.task is not None:
            self.task.cancel()
            try:
                await self.task
            except (asyncio.CancelledError, Exception):     # noqa: BLE001
                pass
        if self.transport is not None:
            self.transport.close()
        self.gs.on_game = None
        try:
            await self.gs.close()
        except (asyncio.TimeoutError, OSError):
            pass


def raise_thread_priority(level=2):
    """The calling thread to THREAD_PRIORITY_HIGHEST (2) inside its process's class (Windows; elsewhere a no-op).
    -> True when Windows took it. (Through a kernel32 of its own with the handle typed: windll.kernel32's
    GetCurrentThread() comes back as a 32-bit int and the call fails with "invalid handle".)"""
    if os.name != "nt":
        return False
    try:
        import ctypes
        k32 = ctypes.WinDLL("kernel32")
        k32.GetCurrentThread.restype = ctypes.c_void_p
        k32.SetThreadPriority.argtypes = (ctypes.c_void_p, ctypes.c_int)
        return bool(k32.SetThreadPriority(k32.GetCurrentThread(), level))
    except (OSError, AttributeError):
        return False


class _Pump(threading.Thread):
    """RelayBridge's packet pump (see "The pump" there): both of the bridge's sockets, taken off the event loop
    (pause_reading), read by this thread alone."""

    WAIT = 0.05                  # the longest select() -- how soon finish() is noticed
    SWITCH_INTERVAL = 0.001
    _active = 0                  # pumps running in this process (the switch interval is the process's)
    _saved_interval = None
    _lock = threading.Lock()

    def __init__(self, bridge, loop):
        super().__init__(daemon=True, name="relay-bridge pump")
        self.bridge, self.loop = bridge, loop
        self.stop = False
        self.raised = False
        self.counted = False
        self.ready = threading.Event()

    @classmethod
    def start_for(cls, bridge, loop):
        """Start a pump for `bridge` (bridge.pump), or leave the forwarding to the event loop: a transport that
        cannot pause its reading (another event loop). -> the pump or None."""
        trs = [bridge.transport, bridge.gs.transport]
        if bridge.gs.sock is None or not all(tr is not None and hasattr(tr, "pause_reading") for tr in trs):
            return None
        paused = []
        try:
            for tr in trs:
                tr.pause_reading()
                paused.append(tr)
        except (AttributeError, RuntimeError, NotImplementedError):
            for tr in paused:
                try:
                    tr.resume_reading()
                except Exception:      # noqa: BLE001
                    pass
            return None
        self = cls(bridge, loop)
        bridge.pump = self
        with cls._lock:
            if cls._active == 0:
                cls._saved_interval = sys.getswitchinterval()
                sys.setswitchinterval(min(cls._saved_interval, cls.SWITCH_INTERVAL))
            cls._active += 1
            self.counted = True
        self.start()
        self.ready.wait(1.0)         # (its priority is set from the thread itself, first thing)
        return self

    def _raise_priority(self):
        if os.name != "nt":
            return
        self.raised = raise_thread_priority()

    def run(self):
        self._raise_priority()
        self.ready.set()
        b = self.bridge
        game, net = b.sock, b.gs.sock
        socks = [game, net]
        while not self.stop:
            try:
                ready, _, _ = select.select(socks, [], [], self.WAIT)
            except (OSError, ValueError):
                break                # a socket closed under us: the bridge is going away
            for s in ready:
                for _ in range(64):  # what came in meanwhile, then the other socket
                    try:
                        data, addr = s.recvfrom(65535)
                    except (BlockingIOError, InterruptedError):
                        break
                    except OSError:
                        break        # (ICMP errors are off on both sockets; a closed one ends the loop above)
                    try:
                        if s is game:
                            b._game_to_net(data, addr)
                        else:
                            b._net_in(data, addr)
                    except RuntimeError:
                        return       # the event loop is closed: so is the bridge
                    except Exception:      # noqa: BLE001 -- one bad packet must not stop the match's traffic
                        pass

    def finish(self):
        """Stop and wait (from any thread but this one); the switch interval goes back with the last pump."""
        self.stop = True
        if self.is_alive() and threading.current_thread() is not self:
            self.join(1.0)
        with _Pump._lock:
            if self.counted:
                self.counted = False
                _Pump._active -= 1
                if _Pump._active == 0 and _Pump._saved_interval is not None:
                    sys.setswitchinterval(_Pump._saved_interval)


async def server_rtt(server, n=5, timeout=0.5, inbound=None):
    """UDP round trip to the lobby server in ms (median of n), or None. inbound: T5_NET_TEST_INBOUND (tests)."""
    loop = asyncio.get_running_loop()
    got = {}
    waiters = {}
    fw = make_inbound_filter(inbound)

    class P(asyncio.DatagramProtocol):
        def datagram_received(self, data, addr):
            if fw is not None and not fw.passes(addr):
                return
            if proto.udp_type(data) == proto.U_SPONG and len(data) == proto.PING.size:
                _m, _k, _v, seq, t = proto.PING.unpack(data)
                got[seq] = (time.perf_counter() - t) * 1000.0
                w = waiters.pop(seq, None)
                if w and not w.done():
                    w.set_result(True)

    sock = open_udp_socket(0)
    tr, _p = await loop.create_datagram_endpoint(P, sock=sock)
    try:
        base = int.from_bytes(os.urandom(2), "big") << 8
        for i in range(n):
            seq = base + i
            waiters[seq] = loop.create_future()
            if fw is not None:
                fw.sent_to(server)
            tr.sendto(proto.pk_ping(proto.U_SPING, seq, time.perf_counter()), server)
            try:
                await asyncio.wait_for(asyncio.shield(waiters[seq]), timeout)
            except asyncio.TimeoutError:
                pass
            await asyncio.sleep(0.02)
    finally:
        tr.close()
    return statistics.median(got.values()) if got else None
