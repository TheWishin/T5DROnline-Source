"""Client side of NAT traversal, on the UDP socket the game will use.

While the lobby owns the game socket it:
  1. registers it with the server (the server sees its public endpoint; a second
     server port tells whether the NAT maps per destination = "symmetric"),
  2. punches: sends U_PUNCH to every candidate endpoint of the peer at the same
     time as the peer does the same toward us, until a packet carrying
     F_HEARD arrives (= both directions work),
  3. or binds to the server's relay when punching fails,
  4. measures the round trip to the chosen peer endpoint (U_PPING / U_PPONG),
and then hands the port (or the socket) to the game. It answers the peer's
punches and pings until it is closed, so both sides can finish their checks.
"""
import asyncio
import os
import socket
import statistics
import time

from . import proto

KIND_RANK = {"local": 0, "public": 1, "reflexive": 2, "relay": 3}


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

    def send(self, data, addr):
        if self.transport is not None and not self.transport.is_closing():
            self.transport.sendto(data, addr)
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
        kind = proto.udp_type(data)
        if kind is None:
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
            if addr not in self.heard:
                self.heard[addr] = time.monotonic()
            self.send(proto.pk_punch(self.tag, self.side, proto.F_HEARD, seq), addr)
            if flags & proto.F_HEARD and addr not in self.confirmed:
                self.confirmed[addr] = time.monotonic()
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
    async def register(self, timeout=4.0):
        """-> (public endpoint, probe endpoint or None), or None when the server never answered."""
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
                if public and time.monotonic() > t_end - timeout + 1.0:
                    break                  # the probe port may be firewalled; don't wait for it
        if public is None:
            return None
        probe = prb.result() if prb is not None and prb.done() else None
        return public, probe

    async def punch(self, candidates, timeout=3.0, linger=0.12, interval=0.03):
        """candidates: [(ip, port, kind)]. -> (addr, kind) of the best two-way path, or None."""
        kinds = {(ip, port): kind for ip, port, kind in candidates}
        t0 = time.monotonic()
        first_ok = None
        while True:
            now = time.monotonic()
            targets = list(kinds) + [a for a in self.heard if a not in kinds]
            for addr in targets:
                flags = proto.F_HEARD if addr in self.heard else 0
                self.seq += 1
                self.send(proto.pk_punch(self.tag, self.side, flags, self.seq), addr)
            if self.confirmed and first_ok is None:
                first_ok = now
            if first_ok is not None and (now - first_ok >= linger or
                                         any(kinds.get(a) == "local" for a in self.confirmed)):
                break
            if now - t0 >= timeout:
                break
            self.confirm_event.clear()
            try:
                await asyncio.wait_for(self.confirm_event.wait(), interval)
            except asyncio.TimeoutError:
                pass
        if not self.confirmed:
            return None
        best = min(self.confirmed, key=lambda a: (KIND_RANK.get(kinds.get(a, "reflexive"), 9), self.confirmed[a]))
        # Keep the peer's side of the handshake complete: a few more F_HEARD punches.
        for _ in range(3):
            self.send(proto.pk_punch(self.tag, self.side, proto.F_HEARD, self.seq), best)
        return best, kinds.get(best, "reflexive")

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
