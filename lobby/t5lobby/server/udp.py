"""The server's UDP side: ping, game-socket registration, NAT probe and the relay.

One port does everything (so a self-hoster forwards one TCP + one UDP port, plus
an optional second UDP port for the NAT probe). The relay needs no per-match
ports: once both game sockets have bound to a match's relay session, every
packet from one bound endpoint that is not addressed to the server itself is
sent on to the other endpoint, from the same port. The game therefore talks to
<server>:<udp_port> as if it were the opponent; the host side learns its peer
from the first packet, exactly as with a direct connection.
"""
import asyncio
import logging
import time

from .. import proto, relayctl
from .ratelimit import KeyedBuckets, TokenBucket

log = logging.getLogger("t5lobby.udp")


class RelaySession:
    __slots__ = ("match_id", "tokens", "ep", "last_rx", "buckets", "bytes", "pkts", "dropped", "created",
                 "closed", "pings", "pongs")

    def __init__(self, match_id, tokens, pps, kbps):
        self.match_id = match_id
        self.tokens = list(tokens)
        self.ep = [None, None]
        self.last_rx = [0.0, 0.0]
        # Per sending side: packets and bytes. Generous for the game (~60 pps of < 200 B each way),
        # tight enough that the relay is useless as a traffic cannon.
        self.buckets = [(TokenBucket(pps, pps * 2), TokenBucket(kbps * 128, kbps * 256)) for _ in range(2)]
        self.bytes = [0, 0]
        self.pkts = [0, 0]
        self.dropped = [0, 0]
        # The lobby's peer pings through the relay, per sending side: the server's own evidence of which
        # side does not answer when a relayed connection cannot be set up (LobbyServer._setup_culprit).
        self.pings = [0, 0]
        self.pongs = [0, 0]
        self.created = time.monotonic()
        self.closed = False

    def bound(self):
        return self.ep[0] is not None and self.ep[1] is not None

    def stats(self):
        return {"pkts": list(self.pkts), "bytes": list(self.bytes), "dropped": list(self.dropped)}


class _Proto(asyncio.DatagramProtocol):
    def __init__(self, svc, which):
        self.svc, self.which = svc, which
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport
        sock = transport.get_extra_info("socket")
        if sock is not None:
            proto.disable_udp_connreset(sock)

    def datagram_received(self, data, addr):
        try:
            self.svc.on_datagram(self.which, self.transport, data, addr)
        except Exception:   # never let one bad packet stop the endpoint
            log.exception("udp packet from %s", addr)

    def error_received(self, exc):
        log.debug("udp error: %s", exc)


class UdpService:
    """Owned by the LobbyServer, or by a RelayNode (server/relaynode.py: the relay alone, for a central lobby
    elsewhere). `lobby` provides udp_register(token, addr, probe) -> bool and udp_relay_bound(); a relay node
    also relay_control(data, addr, transport) for the central server's authenticated control datagrams
    (relayctl.py) and relay_bind_allowed(session, side, addr) -> bool."""

    def __init__(self, lobby, cfg):
        self.lobby = lobby
        self.cfg = cfg
        self.control = getattr(lobby, "relay_control", None)
        self.bind_allowed = getattr(lobby, "relay_bind_allowed", None)
        self.main = None
        self.probe = None
        self.relays = {}            # match id -> RelaySession
        self.relay_eps = {}         # (ip, port) -> (RelaySession, side)
        self.relay_tokens = {}      # token -> (RelaySession, side)
        self.ctl_buckets = KeyedBuckets(rate=100, burst=200)   # control packets per source IP
        # ... and from everybody together: spoofed sources cannot turn the pings into a flood
        self.ctl_global = TokenBucket(cfg.udp_ctl_pps, cfg.udp_ctl_pps * 2)
        self.stats = {"rx": 0, "relayed": 0, "relayed_bytes": 0, "dropped": 0, "relay_refused": 0}
        self.port = self.port2 = 0

    async def start(self, loop):
        tr, pr = await loop.create_datagram_endpoint(lambda: _Proto(self, 0),
                                                     local_addr=(self.cfg.host, self.cfg.udp_port))
        self.main = pr
        self.port = tr.get_extra_info("sockname")[1]
        self.port2 = 0
        if self.cfg.udp_port2:          # 0 = off, -1 = any free port (tests)
            try:
                tr2, pr2 = await loop.create_datagram_endpoint(
                    lambda: _Proto(self, 1), local_addr=(self.cfg.host, max(0, self.cfg.udp_port2)))
                self.probe = pr2
                self.port2 = tr2.get_extra_info("sockname")[1]
            except OSError as e:
                log.warning("second UDP port %s unavailable (%s): NAT type probe off", self.cfg.udp_port2, e)

    def close(self):
        for p in (self.main, self.probe):
            if p and p.transport:
                p.transport.close()

    # ------------------------------------------------------------------ relay sessions
    def open_relay(self, match_id, tokens):
        if len(self.relays) >= self.cfg.max_relays:
            return None
        s = RelaySession(match_id, tokens, self.cfg.relay_pps, self.cfg.relay_kbps)
        self.relays[match_id] = s
        for side, tok in enumerate(tokens):
            self.relay_tokens[tok] = (s, side)
        return s

    def close_relay(self, match_id):
        s = self.relays.pop(match_id, None)
        if not s:
            return None
        s.closed = True
        for tok in s.tokens:
            self.relay_tokens.pop(tok, None)
        for ep in s.ep:
            if ep is not None and self.relay_eps.get(ep, (None,))[0] is s:
                del self.relay_eps[ep]
        log.info("relay %s closed: %s", match_id, s.stats())
        return s.stats()

    def _bind(self, s, side, addr):
        old = s.ep[side]
        if old is not None and old != addr and self.relay_eps.get(old, (None,))[0] is s:
            del self.relay_eps[old]
        s.ep[side] = addr
        s.last_rx[side] = time.monotonic()
        self.relay_eps[addr] = (s, side)

    def _forward(self, transport, s, side, data, kind=None):
        now = time.monotonic()
        if kind == proto.U_PPING:
            s.pings[side] += 1
        elif kind == proto.U_PPONG:
            s.pongs[side] += 1
        s.last_rx[side] = now
        dst = s.ep[1 - side]
        pk, by = s.buckets[side]
        if dst is None or not pk.take(1, now) or not by.take(len(data), now):
            s.dropped[side] += 1
            self.stats["dropped"] += 1
            return
        s.pkts[side] += 1
        s.bytes[side] += len(data)
        self.stats["relayed"] += 1
        self.stats["relayed_bytes"] += len(data)
        transport.sendto(data, dst)

    def _relayable(self, data, kind):
        """The relay carries the two games' traffic and nothing else: netplay packets (T5NP), the
        lobby's peer packets (punch, peer ping) of the match, nothing larger than netplay's biggest
        packet. Anything else from a bound endpoint -- someone using the session as a free tunnel or
        proxy -- is dropped."""
        if len(data) > self.cfg.relay_max_bytes:
            return False
        return data[:4] == proto.GAME_MAGIC or kind in proto.PEER_TYPES

    def _try_relatch(self, transport, data, addr):
        """Game traffic from an unknown endpoint: a NAT that re-mapped the game's socket between the
        launcher's relay bind and the game's first packet. Accept it for the one bound side with that
        IP that has gone quiet, never for an address nobody bound from."""
        if data[:4] != proto.GAME_MAGIC:
            return False
        now = time.monotonic()
        hits = [(s, side) for s in self.relays.values() for side in (0, 1)
                if s.ep[side] is not None and s.ep[side][0] == addr[0] and now - s.last_rx[side] > 2.0]
        if len(hits) != 1:
            return False
        s, side = hits[0]
        log.info("relay %s: side %d moved %s -> %s", s.match_id, side, s.ep[side], addr)
        self._bind(s, side, addr)
        self._forward(transport, s, side, data)
        return True

    # ------------------------------------------------------------------ packets
    def on_datagram(self, which, transport, data, addr):
        self.stats["rx"] += 1
        kind = proto.udp_type(data)
        if which == 0:
            hit = self.relay_eps.get(addr)
            if hit is not None and kind not in proto.SERVER_TYPES:
                if self._relayable(data, kind):
                    self._forward(transport, hit[0], hit[1], data, kind)
                else:
                    hit[0].dropped[hit[1]] += 1
                    self.stats["dropped"] += 1
                    self.stats["relay_refused"] += 1
                return
        key = proto.address_key(addr[0], self.cfg.ipv6_prefix)
        if kind is None and self.control is not None and relayctl.is_control(data):
            if which == 0 and self.ctl_buckets.take(key) and self.ctl_global.take():
                self.control(data, addr, transport)
            else:
                self.stats["dropped"] += 1
            return
        if kind is None:
            relatch_ok = (which == 0 and self.relays and self._relayable(data, kind)
                          and self.ctl_buckets.take(key) and self.ctl_global.take())
            if relatch_ok and self._try_relatch(transport, data, addr):
                return
            self.stats["dropped"] += 1
            return
        # The total (ctl_global) is for what is answered to anybody: the ping. Registrations and relay binds
        # are answered only for a token the server handed out, so a spoofed flood that uses up the total
        # must not stop the players' own NAT setup and relay binds with it (1.1.2; before, it did).
        if kind not in proto.SERVER_TYPES or not self.ctl_buckets.take(key) or \
                (kind == proto.U_SPING and not self.ctl_global.take()):
            self.stats["dropped"] += 1
            return
        if kind == proto.U_SPING and len(data) == proto.PING.size:
            transport.sendto(bytes([*data[:4], proto.U_SPONG]) + data[5:], addr)
        elif kind in (proto.U_REGISTER, proto.U_PROBE) and len(data) == proto.TOKEN_PKT.size:
            token = proto.TOKEN_PKT.unpack(data)[3]
            probe = kind == proto.U_PROBE or which == 1
            if self.lobby.udp_register(token, addr, probe):
                ack = proto.U_PROBE_ACK if probe else proto.U_REG_ACK
                transport.sendto(proto.pk_token_ack(ack, token, addr), addr)
        elif kind == proto.U_RELAY_BIND and which == 0 and len(data) == proto.TOKEN_PKT.size:
            token = proto.TOKEN_PKT.unpack(data)[3]
            hit = self.relay_tokens.get(token)
            if hit is None:
                return
            s, side = hit
            if self.bind_allowed is not None and not self.bind_allowed(s, side, addr):
                self.stats["dropped"] += 1
                self.stats["relay_refused"] += 1
                return
            self._bind(s, side, addr)
            transport.sendto(proto.pk_token_ack(proto.U_RELAY_ACK, token, addr), addr)
            self.lobby.udp_relay_bound(s.match_id, side, addr)
        else:
            self.stats["dropped"] += 1

    def expire_idle(self, idle=120.0):
        """Relay sessions nobody used for `idle` seconds -> list of their match ids."""
        now = time.monotonic()
        dead = [mid for mid, s in self.relays.items()
                if now - max(s.last_rx[0], s.last_rx[1], s.created) > idle]
        return dead
