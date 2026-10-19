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
moves the match onto it as soon as it works both ways.
"""
import asyncio
import os
import socket
import statistics
import time

from . import proto

KIND_RANK = {"local": 0, "mapped": 1, "public": 1, "reflexive": 2, "predicted": 2, "relay": 3}


def local_ipv4s(target_ip):
    """This PC's IPv4 addresses worth offering to a peer behind the same router."""
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
    """Bind a UDP socket on all interfaces; falls back to any free port when `port` is taken."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.bind(("0.0.0.0", port))
    except OSError:
        if not port:
            s.close()
            raise
        s.bind(("0.0.0.0", 0))
    proto.disable_udp_connreset(s)
    s.setblocking(False)
    return s


class GameSocket(asyncio.DatagramProtocol):
    def __init__(self, server, port2, token, tag, side, block_direct=False):
        self.server = server                 # (ip, udp_port)
        self.server2 = (server[0], port2) if port2 else None
        self.token = token
        self.tag = tag
        self.side = side
        self.block_direct = block_direct     # testing: ignore the peer unless it comes through the relay
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
        if ttl is None:
            self.transport.sendto(data, addr)
        else:
            # On the socket itself, not through the transport: a packet the transport queued would leave
            # later with the TTL already put back.
            try:
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
        self.stats["rx"] += 1
        self.last_rx[addr] = time.monotonic()
        kind = proto.udp_type(data)
        if kind is None:
            if self.on_game is not None and data[:4] == proto.GAME_MAGIC:
                self.on_game(data, addr)
            return
        from_server = addr == self.server or addr == self.server2
        if kind in (proto.U_REG_ACK, proto.U_PROBE_ACK, proto.U_RELAY_ACK) and from_server:
            if len(data) == proto.TOKEN_ACK.size:
                _k, tok, seen = proto.un_token_ack(data)
                if tok == self.token:
                    self._resolve(kind, seen)
            return
        if kind == proto.U_SPONG and from_server and len(data) == proto.PING.size:
            _m, _k, _v, seq, t = proto.PING.unpack(data)
            self._resolve(("s", seq), time.perf_counter() - t)
            return
        if self.block_direct and addr != self.server:
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
                    slow_start=0.0, slow_interval=0.2, ttl_open=0.0):
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
        error that closes the other side's mapping, or count it as a flood."""
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
        opened = ttl_open <= 0
        while True:
            now = time.monotonic()
            low = now - t0 < ttl_open
            if not low and not opened:
                opened = True                       # the full punches start: a fresh pass over everything
                due.clear()
                scan_i = 0
            step = interval if low else (slow_interval if now - t0 - ttl_open < slow_start else interval)
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

    async def relay_bind(self, relay, timeout=4.0):
        ack = self._wait(proto.U_RELAY_ACK)
        t_end = time.monotonic() + timeout
        while time.monotonic() < t_end and not ack.done():
            self.send(proto.pk_token(proto.U_RELAY_BIND, self.token), relay)
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
        s.bind(("0.0.0.0", 0))
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
    never end under a steady trickle."""

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
        self.port = s.getsockname()[1]
        gs.on_game = self._from_net
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

    # ------------------------------------------------------------- the network's side (game socket)
    def _from_net(self, data, addr):
        if addr == self.relay:
            self.stats["relay_in"] += 1
        elif addr in self.gs.heard or addr in self.gs.confirmed or addr == self.upstream:
            self.stats["direct_in"] += 1
        else:
            self.stats["strangers"] += 1          # only the opponent's endpoints; the game checks the key too
            return
        if self.transport is not None and not self.transport.is_closing():
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


async def server_rtt(server, n=5, timeout=0.5):
    """UDP round trip to the lobby server in ms (median of n), or None."""
    loop = asyncio.get_running_loop()
    got = {}
    waiters = {}

    class P(asyncio.DatagramProtocol):
        def datagram_received(self, data, addr):
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
            tr.sendto(proto.pk_ping(proto.U_SPING, seq, time.perf_counter()), server)
            try:
                await asyncio.wait_for(asyncio.shield(waiters[seq]), timeout)
            except asyncio.TimeoutError:
                pass
            await asyncio.sleep(0.02)
    finally:
        tr.close()
    return statistics.median(got.values()) if got else None
