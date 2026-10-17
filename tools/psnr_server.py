#!/usr/bin/env python3
"""A small stand-in for PSN's matchmaking rooms, speaking the psnr wire protocol
(github.com/sp00nznet/psnr, docs/api.md) so the recompiled game's sceNpMatching
module can use either this or the real Go psnr server.

    python tools/psnr_server.py [--port 36100] [--bind 0.0.0.0] [-v]

What it does: one TCP connection per player (HELLO first), rooms scoped by the
title's communication id (NPWR00045 for T5DR), room search, join/leave/kick,
room data and messages, member join/leave pushes, and a UDP probe on the same
port so a player behind a router gets a public endpoint. Game traffic never
goes through here: once two players are in a room, the game sends its packets
straight to the address this server handed out.

Everything is big-endian. Frames: u8 type | u16 length | payload. Requests and
replies start with u32 req. Pushes (0xA0-0xAF) carry no req.
"""
import argparse
import asyncio
import logging
import socket
import struct
import sys
import time

log = logging.getLogger("psnr")

# message types
HELLO, HEARTBEAT = 0x01, 0x02
CREATE_ROOM, SEARCH_ROOMS, JOIN_ROOM, LEAVE_ROOM, SET_ROOM_DATA, ROOM_MESSAGE, KICK_MEMBER = (
    0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x16)
RECORD_SCORE, GET_RANKING, GET_RANKING_BY_ID = 0x20, 0x21, 0x22
HELLO_ACK, ERROR, ROOM_JOINED, ROOM_LIST, OK = 0x81, 0x8F, 0x90, 0x91, 0x93
SCORE_RECORDED, RANKING = 0xB0, 0xB1
MEMBER_JOINED, MEMBER_LEFT, ROOM_DATA, ROOM_MSG, KICKED = 0xA1, 0xA2, 0xA3, 0xA4, 0xA5

E_BAD_REQUEST, E_NOT_FOUND, E_ROOM_FULL, E_NOT_OWNER, E_NOT_IN_ROOM, E_LIMIT, E_NO_HELLO, E_NAME_TAKEN = (
    1, 2, 3, 4, 5, 6, 7, 8)

IDLE_TIMEOUT = 90.0
MAX_ROOMS = 256


class Reader:
    def __init__(self, data):
        self.d, self.o = data, 0

    def u8(self):
        v = self.d[self.o]; self.o += 1; return v

    def u16(self):
        v = struct.unpack_from(">H", self.d, self.o)[0]; self.o += 2; return v

    def u32(self):
        v = struct.unpack_from(">I", self.d, self.o)[0]; self.o += 4; return v

    def u64(self):
        v = struct.unpack_from(">Q", self.d, self.o)[0]; self.o += 8; return v

    def s64(self):
        v = struct.unpack_from(">q", self.d, self.o)[0]; self.o += 8; return v

    def fixed(self, n):
        v = self.d[self.o:self.o + n]; self.o += n
        if len(v) != n:
            raise ValueError("short")
        return v

    def blob(self):
        n = self.u16(); return bytes(self.fixed(n))

    def cstr(self, n):
        return self.fixed(n).split(b"\0", 1)[0].decode("ascii", "replace")


def blob(b):
    return struct.pack(">H", len(b)) + b


def fixed(s, n):
    b = s.encode("ascii", "replace")[:n]
    return b + b"\0" * (n - len(b))


class Player:
    def __init__(self, server, reader, writer):
        self.server = server
        self.r, self.w = reader, writer
        self.user_id = 0
        self.online_id = ""
        self.comm_id = ""
        self.p2p_port = 0
        self.tcp_ip = writer.get_extra_info("peername")[0]
        self.public_ep = None      # (ip, port) seen on the UDP probe
        self.local_ip = None
        self.token = 0
        self.last_seen = time.monotonic()
        self.rooms = {}            # room_id -> member_id
        self.member_data = {}      # room_id -> bytes

    def send(self, mtype, payload):
        if self.w.is_closing():
            return
        self.w.write(struct.pack(">BH", mtype, len(payload)) + payload)

    def reply(self, mtype, req, payload=b""):
        self.send(mtype, struct.pack(">I", req) + payload)

    def error(self, req, code):
        self.reply(ERROR, req, struct.pack(">I", code))

    def address_for(self, viewer):
        """(ip, port) at which `viewer` should send this player's P2P traffic."""
        if self.public_ep and viewer.public_ip() != self.public_ip():
            return self.public_ep
        if self.public_ep and self.local_ip and self.local_ip != "0.0.0.0":
            return (self.local_ip, self.p2p_port)
        return (self.tcp_ip, self.p2p_port)

    def public_ip(self):
        return self.public_ep[0] if self.public_ep else self.tcp_ip

    def member_bytes(self, room, viewer):
        mid = self.rooms[room.id]
        ip, port = self.address_for(viewer)
        return (struct.pack(">HI", mid, self.user_id) + fixed(self.online_id, 16)
                + socket.inet_aton(ip) + struct.pack(">HB", port, 1 if room.owner is self else 0)
                + blob(self.member_data.get(room.id, b"")))


class Room:
    def __init__(self, rid, comm_id, owner, maxn, flags, external, internal):
        self.id = rid
        self.comm_id = comm_id
        self.owner = owner
        self.max = maxn
        self.flags = flags
        self.external = external
        self.internal = internal
        self.members = []          # Players in join order
        self.next_member = 1
        self.created = time.time()

    def full(self):
        return len(self.members) >= self.max

    def joined_bytes(self, viewer):
        out = struct.pack(">QHHBI", self.id, viewer.rooms[self.id], self.owner.rooms[self.id], self.max, self.flags)
        out += blob(self.external) + blob(self.internal) + struct.pack(">B", len(self.members))
        for m in self.members:
            out += m.member_bytes(self, viewer)
        return out

    def list_bytes(self, viewer):
        # Extension over psnr (announced by HELLO_ACK flags bit 1): each entry also
        # carries the owner's user id and P2P address, so a title can ping a room's
        # host from the room browser before joining (Tekken 5 DR shows the ping).
        ip, port = self.owner.address_for(viewer)
        return (struct.pack(">Q", self.id) + fixed(self.owner.online_id, 16)
                + struct.pack(">BBI", len(self.members), self.max, self.flags) + blob(self.external)
                + struct.pack(">I", self.owner.user_id) + socket.inet_aton(ip) + struct.pack(">H", port))


class Server:
    def __init__(self, verbose):
        self.players = {}          # user_id -> Player
        self.rooms = {}            # room_id -> Room
        self.next_user = 1
        self.next_room = 1
        self.verbose = verbose
        self.udp = None
        self.scores = {}           # (comm_id, board) -> {online_id: (score, comment, when)}
        self.orders = {}

    # ---- TCP ----
    async def handle(self, reader, writer):
        p = Player(self, reader, writer)
        try:
            while True:
                try:
                    hdr = await asyncio.wait_for(reader.readexactly(3), IDLE_TIMEOUT)
                except asyncio.TimeoutError:
                    log.info("%s idle, dropped", p.online_id or p.tcp_ip)
                    break
                mtype, n = struct.unpack(">BH", hdr)
                body = await reader.readexactly(n) if n else b""
                p.last_seen = time.monotonic()
                try:
                    self.dispatch(p, mtype, body)
                except (ValueError, struct.error, IndexError) as e:
                    log.warning("bad %02x from %s: %s", mtype, p.online_id or p.tcp_ip, e)
                    if len(body) >= 4:
                        p.error(struct.unpack(">I", body[:4])[0], E_BAD_REQUEST)
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError, OSError):
            pass
        finally:
            self.disconnect(p)
            writer.close()

    def dispatch(self, p, mtype, body):
        if mtype == HEARTBEAT:
            return
        rd = Reader(body)
        req = rd.u32()
        if mtype == HELLO:
            return self.on_hello(p, req, rd)
        if not p.user_id:
            return p.error(req, E_NO_HELLO)
        h = {CREATE_ROOM: self.on_create, SEARCH_ROOMS: self.on_search, JOIN_ROOM: self.on_join,
             LEAVE_ROOM: self.on_leave, SET_ROOM_DATA: self.on_set_data, ROOM_MESSAGE: self.on_message,
             KICK_MEMBER: self.on_kick, RECORD_SCORE: self.on_record_score,
             GET_RANKING: self.on_get_ranking, GET_RANKING_BY_ID: self.on_get_ranking_by_id}.get(mtype)
        if not h:
            return p.error(req, E_BAD_REQUEST)
        h(p, req, rd)

    def on_hello(self, p, req, rd):
        comm = rd.cstr(12)
        name = rd.cstr(16)
        port = rd.u16()
        for other in list(self.players.values()):
            if other.online_id.lower() == name.lower():
                if other.tcp_ip == p.tcp_ip:
                    log.info("%s reconnected from %s; closing the old connection", name, p.tcp_ip)
                    self.disconnect(other)
                    other.w.close()
                else:
                    return p.error(req, E_NAME_TAKEN)
        p.user_id = self.next_user; self.next_user += 1
        p.online_id, p.comm_id, p.p2p_port = name, comm, port
        p.token = (int(time.time() * 1000) * 2654435761 + p.user_id) & 0xFFFFFFFF
        self.players[p.user_id] = p
        log.info("hello %s (%s) user %u from %s, p2p port %u", name, comm, p.user_id, p.tcp_ip, port)
        # flags: bit 0 relay (not here), bit 1 room lists carry the owner's address
        p.reply(HELLO_ACK, req, struct.pack(">I", p.user_id) + socket.inet_aton(p.tcp_ip)
                + struct.pack(">IB", p.token, 0x02))

    def on_create(self, p, req, rd):
        maxn = rd.u8(); flags = rd.u32()
        external = rd.blob(); internal = rd.blob(); mdata = rd.blob()
        if len(self.rooms) >= MAX_ROOMS:
            return p.error(req, E_LIMIT)
        if maxn < 1:
            maxn = 1
        room = Room(self.next_room, p.comm_id, p, maxn, flags, external, internal)
        self.next_room += 1
        self.rooms[room.id] = room
        self.add_member(room, p, mdata)
        log.info("room %u created by %s (max %u, flags %#x, %u B external)", room.id, p.online_id, maxn,
                 flags, len(external))
        p.reply(ROOM_JOINED, req, room.joined_bytes(p))

    def on_search(self, p, req, rd):
        start = rd.u16(); maxn = rd.u16()
        rooms = [r for r in sorted(self.rooms.values(), key=lambda r: r.id)
                 if r.comm_id == p.comm_id and not r.full()]
        page = rooms[start:start + maxn] if maxn else rooms[start:]
        out = struct.pack(">HH", len(rooms), len(page))
        for r in page:
            out += r.list_bytes(p)
        if self.verbose:
            log.info("search by %s: %u room(s), %u listed", p.online_id, len(rooms), len(page))
        p.reply(ROOM_LIST, req, out)

    def on_join(self, p, req, rd):
        rid = rd.u64(); mdata = rd.blob()
        room = self.rooms.get(rid)
        if not room or room.comm_id != p.comm_id:
            return p.error(req, E_NOT_FOUND)
        if rid in p.rooms:
            return p.reply(ROOM_JOINED, req, room.joined_bytes(p))
        if room.full():
            return p.error(req, E_ROOM_FULL)
        self.add_member(room, p, mdata)
        log.info("%s joined room %u (%u/%u)", p.online_id, rid, len(room.members), room.max)
        p.reply(ROOM_JOINED, req, room.joined_bytes(p))
        for m in room.members:
            if m is not p:
                m.send(MEMBER_JOINED, struct.pack(">Q", rid) + p.member_bytes(room, m))

    def add_member(self, room, p, mdata):
        p.rooms[room.id] = room.next_member
        room.next_member += 1
        p.member_data[room.id] = mdata
        room.members.append(p)

    def remove_member(self, room, p, kicked=False):
        mid = p.rooms.pop(room.id, None)
        p.member_data.pop(room.id, None)
        if p in room.members:
            room.members.remove(p)
        if not room.members:
            del self.rooms[room.id]
            log.info("room %u closed", room.id)
            return
        if room.owner is p:
            room.owner = room.members[0]
            log.info("room %u: owner is now %s", room.id, room.owner.online_id)
        for m in room.members:
            m.send(MEMBER_LEFT, struct.pack(">QHH", room.id, mid, room.owner.rooms[room.id]))

    def on_leave(self, p, req, rd):
        rid = rd.u64()
        room = self.rooms.get(rid)
        if not room or rid not in p.rooms:
            return p.error(req, E_NOT_IN_ROOM)
        log.info("%s left room %u", p.online_id, rid)
        self.remove_member(room, p)
        p.reply(OK, req)

    def on_set_data(self, p, req, rd):
        rid = rd.u64(); which = rd.u8(); data = rd.blob()
        room = self.rooms.get(rid)
        if not room or rid not in p.rooms:
            return p.error(req, E_NOT_IN_ROOM)
        if room.owner is not p:
            return p.error(req, E_NOT_OWNER)
        if which == 0:
            room.external = data
        elif which == 1:
            room.internal = data
        elif which == 2 and len(data) == 4:
            room.flags = struct.unpack(">I", data)[0]
        else:
            return p.error(req, E_BAD_REQUEST)
        p.reply(OK, req)
        for m in room.members:
            if m is not p:
                m.send(ROOM_DATA, struct.pack(">QB", rid, which) + blob(data))

    def on_message(self, p, req, rd):
        rid = rd.u64(); to = rd.u16(); data = rd.blob()
        room = self.rooms.get(rid)
        if not room or rid not in p.rooms:
            return p.error(req, E_NOT_IN_ROOM)
        frm = p.rooms[rid]
        for m in room.members:
            if m is p:
                continue
            if to == 0 or m.rooms[rid] == to:
                m.send(ROOM_MSG, struct.pack(">QHH", rid, frm, to) + blob(data))
        p.reply(OK, req)

    def on_kick(self, p, req, rd):
        rid = rd.u64(); mid = rd.u16()
        room = self.rooms.get(rid)
        if not room or rid not in p.rooms:
            return p.error(req, E_NOT_IN_ROOM)
        if room.owner is not p:
            return p.error(req, E_NOT_OWNER)
        victim = next((m for m in room.members if m.rooms[rid] == mid), None)
        if not victim:
            return p.error(req, E_NOT_FOUND)
        log.info("%s kicked %s from room %u", p.online_id, victim.online_id, rid)
        victim.send(KICKED, struct.pack(">Q", rid))
        self.remove_member(room, victim, kicked=True)
        p.reply(OK, req)

    # ---- leaderboards (minimal) ----
    def on_record_score(self, p, req, rd):
        board = rd.u32(); order = rd.u8(); score = rd.s64(); comment = rd.blob()
        key = (p.comm_id, board)
        self.orders.setdefault(key, order)
        rows = self.scores.setdefault(key, {})
        old = rows.get(p.online_id)
        better = old is None or (score < old[0] if self.orders[key] else score > old[0])
        if better:
            rows[p.online_id] = (score, comment[:64], int(time.time()))
        p.reply(SCORE_RECORDED, req, struct.pack(">I", self.rank_of(key, p.online_id)))

    def ranking(self, key):
        rows = self.scores.get(key, {})
        rev = not self.orders.get(key, 0)
        return sorted(rows.items(), key=lambda kv: (-kv[1][0] if rev else kv[1][0], kv[1][2]))

    def rank_of(self, key, name):
        for i, (n, _) in enumerate(self.ranking(key), 1):
            if n == name:
                return i
        return 0

    def on_get_ranking(self, p, req, rd):
        board = rd.u32(); start = rd.u32(); count = rd.u16()
        key = (p.comm_id, board)
        ranked = self.ranking(key)
        page = ranked[max(start - 1, 0):max(start - 1, 0) + min(count, 100)]
        out = struct.pack(">IH", len(ranked), len(page))
        for i, (name, (score, comment, when)) in enumerate(page, max(start, 1)):
            out += struct.pack(">I", i) + fixed(name, 16) + struct.pack(">q", score) + blob(comment) + struct.pack(">Q", when)
        p.reply(RANKING, req, out)

    def on_get_ranking_by_id(self, p, req, rd):
        board = rd.u32(); n = rd.u16()
        key = (p.comm_id, board)
        names = [rd.cstr(16) for _ in range(min(n, 100))]
        rows = self.scores.get(key, {})
        out = struct.pack(">IH", len(rows), len(names))
        for name in names:
            if name in rows:
                score, comment, when = rows[name]
                out += struct.pack(">I", self.rank_of(key, name)) + fixed(name, 16) + struct.pack(">q", score) + blob(comment) + struct.pack(">Q", when)
            else:
                out += struct.pack(">I", 0) + fixed(name, 16) + struct.pack(">q", 0) + blob(b"") + struct.pack(">Q", 0)
        p.reply(RANKING, req, out)

    def disconnect(self, p):
        if p.user_id and self.players.get(p.user_id) is p:
            del self.players[p.user_id]
            for rid in list(p.rooms):
                room = self.rooms.get(rid)
                if room:
                    self.remove_member(room, p)
            log.info("%s disconnected", p.online_id)

    # ---- UDP ----
    def on_udp(self, data, addr):
        if len(data) < 5 or data[:4] != b"PSNR":
            return
        t = data[4]
        if t == 0x01 and len(data) >= 17:         # PROBE user_id u32 | token u32 | local_ip [4]
            uid, token = struct.unpack(">II", data[5:13])
            p = self.players.get(uid)
            if not p or p.token != token:
                return
            if p.public_ep != addr:
                log.info("%s's P2P socket seen at %s:%u", p.online_id, addr[0], addr[1])
            p.public_ep = addr
            p.local_ip = socket.inet_ntoa(data[13:17])
            self.udp.sendto(b"PSNR\x81" + socket.inet_aton(addr[0]) + struct.pack(">H", addr[1]), addr)


class UdpProto(asyncio.DatagramProtocol):
    def __init__(self, server):
        self.server = server

    def connection_made(self, transport):
        self.server.udp = transport
        sock = transport.get_extra_info("socket")
        if sock is not None and sys.platform == "win32":
            try:   # a peer's closed port otherwise raises WSAECONNRESET on the next recv
                sock.ioctl(socket.SIO_UDP_CONNRESET, False)
            except (AttributeError, OSError):
                pass

    def datagram_received(self, data, addr):
        try:
            self.server.on_udp(data, addr)
        except Exception:
            log.exception("udp packet from %s", addr)

    def error_received(self, exc):
        pass


async def main_async(a):
    server = Server(a.verbose)
    loop = asyncio.get_running_loop()
    await loop.create_datagram_endpoint(lambda: UdpProto(server), local_addr=(a.bind, a.port))
    srv = await asyncio.start_server(server.handle, a.bind, a.port)
    log.info("psnr (python) clients on %s:%u", a.bind, a.port)
    async with srv:
        await srv.serve_forever()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bind", default="127.0.0.1", help="0.0.0.0 to serve other machines")
    ap.add_argument("--port", type=int, default=36100)
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", stream=sys.stdout)
    try:
        asyncio.run(main_async(a))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
