"""Spectator limits (hardening 1.1.4, docs/SPECTATE.md "Limits"; security review 3's open finding: about 50 guest
connections from about 7 addresses took every stream slot of the server). With many lobby clients against a real
server: per address (IPv4, IPv6 /64), per IPv6 /56 and /48; guests hold at most half of a match's places and start
streams only while the server shows fewer than half of its maximum; the last stream slots and every place at a full
match go to close viewers first -- friends of the players and members of the match's room (a close viewer takes the
place of the newest guest, who is told "bumped")."""
import os
import time
import unittest

import util  # noqa: F401 -- (sets up the paths and the test environment)
from util import expect

from t5lobby import proto, spectate
from t5lobby.proto import LobbyError

from test_spectate import Base, match_rec, session_rec

MANY = dict(max_per_ip=1000, max_clients=2000, conn_rate=1000.0, conn_burst=1000, max_prelogin=1000,
            state_rate=100.0, state_burst=200)


class LimitBase(Base):
    server_cfg = dict(MANY)

    def guest(self, name, ip):
        """A guest launcher (spectate cap) whose connection the server sees from `ip`."""
        d = os.path.join(self.tmp, name)
        c = util.client(self.s, name, spectate=True, live_dir=os.path.join(d, "live"), watch_dir=os.path.join(d, "watch"),
                        auto_ready=True)
        self.clients.append(c)
        self.from_ip(name, ip)
        return c

    def from_ip(self, name, ip):
        def move():
            conn = self.s.srv.by_name[name.lower()].conn
            conn.ip = ip
            conn.akey = proto.address_key(ip, self.s.srv.cfg.ipv6_prefix)
        self.s.call(move)

    def room_match(self, a, b, name):
        """A classic room's match between a and b, its live file fed (so the stream keeps coming): its room id."""
        room = a.create_room(name)
        b.join_room(room["id"])
        sa = expect(a, "match_start", 30)
        expect(b, "match_start", 30)
        self.feed(spectate.live_path(a.live_dir, sa["stream"]), spectate.MAGIC + session_rec() + match_rec(0))
        return room["id"]

    def wait_watch(self, viewer, rid, want=True, timeout=10.0):
        t_end = time.monotonic() + timeout
        while time.monotonic() < t_end:
            if any(r["id"] == rid and bool(r.get("watch")) == want for r in viewer.rooms):
                return
            time.sleep(0.05)
        raise AssertionError(f"room {rid}: watch never {want}")

    def try_watch(self, c, **kw):
        try:
            c.watch(**kw)
            return "ok"
        except LobbyError as e:
            return e.code

    def streams(self):
        return self.s.call(lambda: len(self.s.srv.streams))

    def viewers_of(self, rid):
        def f():
            r = self.s.srv.rooms.get(rid)
            st = self.s.srv.streams.get(r.match.stream_id) if r is not None and r.match is not None else None
            return [v.name for v in st.viewers] if st is not None else []
        return self.s.call(f)


class StreamSlotsTest(LimitBase):
    server_cfg = dict(MANY, max_streams=20, spec_reserved_streams=4)

    def test_fifty_guests_from_seven_addresses(self):
        """The finding, scaled to 20 stream slots: 52 guest connections from 7 addresses try to watch 20 room matches.
        They get at most 2 matches per address and start at most 10 streams (half the server's); friends and
        strangers with accounts still find a slot, a friend even when everybody else has filled the rest."""
        pairs = []
        for i in range(20):
            a, b = self.acc(f"P{i:02d}a"), self.acc(f"P{i:02d}b")
            pairs.append((a, b, self.room_match(a, b, f"Dojo {i}")))
        guests = [self.guest(f"G{k:02d}", f"198.51.100.{k % 7 + 1}") for k in range(52)]
        self.wait_watch(guests[0], pairs[-1][2])
        got = {}
        for k, g in enumerate(guests):                               # every guest tries match after match
            for i in range(20):
                code = self.try_watch(g, room=pairs[(k + i) % 20][2])
                got[code] = got.get(code, 0) + 1
                if code == "ok":
                    break
        watching = self.s.call(lambda: sum(1 for p in self.s.srv.players.values() if p.watching is not None))
        self.assertLessEqual(watching, 14, "2 per address")
        self.assertLessEqual(self.streams(), 10, "guests start streams only while fewer than half the slots are used")
        per_addr = self.s.call(lambda: [sum(1 for st in self.s.srv.streams.values() for v in st.viewers
                                            if v.conn is not None and v.conn.ip == f"198.51.100.{n}")
                                        for n in range(1, 8)])
        self.assertTrue(all(n <= 2 for n in per_addr), per_addr)
        self.assertIn("rate_limited", got)                          # the per-address limit said no
        # a stranger with an account: a match nobody watches yet (a slot below the reserved ones)
        stranger = self.acc("Stan")
        self.from_ip("Stan", "203.0.113.9")
        free = [rid for _a, _b, rid in pairs if not self.viewers_of(rid)]
        self.assertEqual(self.try_watch(stranger, room=free[0]), "ok")
        # fill every slot that is not reserved with accounts from many addresses
        k = 0
        for rid in free[1:]:
            if self.streams() >= 16:
                break
            c = self.acc(f"Acc{k:02d}")
            self.from_ip(f"Acc{k:02d}", f"203.0.113.{20 + k}")
            self.assertEqual(self.try_watch(c, room=rid), "ok")
            k += 1
        self.assertEqual(self.streams(), 16)
        late = self.acc("Lou")
        self.from_ip("Lou", "203.0.113.200")
        left = [rid for _a, _b, rid in pairs if not self.viewers_of(rid)]
        self.assertEqual(self.try_watch(late, room=left[0]), "server_full")      # the reserved slots: not for him
        # a friend of a player of a match nobody watches: one of the reserved slots
        a, _b, rid = next(p for p in pairs if p[2] == left[0])
        fay = self.acc("Fay")
        self.from_ip("Fay", "198.51.100.1")                         # (even from a guessers' address)
        self.befriend(fay, a)
        self.assertEqual(self.try_watch(fay, room=rid), "ok")
        self.assertEqual(self.streams(), 17)


class MatchPlacesTest(LimitBase):
    def test_guests_hold_half_the_places_and_friends_and_members_come_first(self):
        """One community room's match (8 places): guests from many addresses get 4, accounts the rest; a friend of a
        player and a member of the room each take the place of the newest guest (spec_end "bumped")."""
        a, b, c = self.acc("Amy"), self.acc("Ben"), self.acc("Cal")
        room = a.create_room("Community", size=3)
        rid = room["id"]
        b.join_room(rid)
        c.join_room(rid)
        srv = self.s.srv
        self.assertTrue(self.s.wait_for(lambda: srv.rooms[rid].match is not None
                                        and srv.rooms[rid].match.state == "playing", 30), "the room's first match")
        playing, sid = self.s.call(lambda: ([q.name for q in srv.rooms[rid].match.players],
                                            srv.rooms[rid].match.stream_id))
        by = {x.me["name"]: x for x in (a, b, c)}
        streamer = by[playing[0]]                                    # (P1's launcher sends the stream)
        member = next(x for n, x in by.items() if n not in playing)
        self.feed(spectate.live_path(streamer.live_dir, sid), spectate.MAGIC + session_rec() + match_rec(0))
        guests = [self.guest(f"G{k}", f"192.0.2.{k + 1}") for k in range(8)]
        self.wait_watch(guests[0], rid)
        codes = [self.try_watch(g, room=rid) for g in guests]
        self.assertEqual(codes.count("ok"), 4, codes)               # half of the 8 places
        self.assertEqual(codes[4:], ["server_full"] * 4)
        accs = []
        for k in range(4):
            x = self.acc(f"A{k}")
            self.from_ip(f"A{k}", f"203.0.113.{k + 1}")
            accs.append(x)
            self.assertEqual(self.try_watch(x, room=rid), "ok")
        late = self.acc("Lee")
        self.assertEqual(self.try_watch(late, room=rid), "server_full")         # full for a stranger
        # a friend of a player: the newest guest makes room
        fay = self.acc("Fay")
        self.befriend(fay, streamer)
        self.assertEqual(self.try_watch(fay, room=rid), "ok")
        self.assertEqual(expect(guests[3], "spec_end", 10)["reason"], "bumped")
        names = self.viewers_of(rid)
        self.assertNotIn("G3", names)
        self.assertIn("Fay", names)
        # the room's third member (not playing): the next newest guest
        self.assertEqual(self.try_watch(member, room=rid), "ok")
        self.assertEqual(expect(guests[2], "spec_end", 10)["reason"], "bumped")
        self.assertEqual(len(self.viewers_of(rid)), 8)
        # with no guest left, a close viewer takes the newest stranger's place; with only close viewers, nobody's
        for g in guests[:2]:
            g.unwatch()
        self.wait_for_viewers(rid, 6)
        for x in (late,):
            self.assertEqual(self.try_watch(x, room=rid), "ok")
        lia = self.acc("Lia")
        self.assertEqual(self.try_watch(lia, room=rid), "ok")
        self.assertEqual(len(self.viewers_of(rid)), 8)
        g2 = self.acc("Gil")
        self.befriend(g2, streamer)
        self.assertEqual(self.try_watch(g2, room=rid), "ok")
        self.assertEqual(expect(lia, "spec_end", 10)["reason"], "bumped")        # the newest account
        # only close viewers: a friend finds the match full
        for x in (late, *accs):
            x.unwatch()
        self.wait_for_viewers(rid, 3)                                # Fay, the member, Gil
        for k in range(5):
            f = self.acc(f"F{k}")
            self.befriend(f, streamer)
            self.assertEqual(self.try_watch(f, room=rid), "ok")
        last = self.acc("Fin")
        self.befriend(last, streamer)
        self.assertEqual(self.try_watch(last, room=rid), "server_full")

    def wait_for_viewers(self, rid, n, timeout=10.0):
        t_end = time.monotonic() + timeout
        while time.monotonic() < t_end:
            if len(self.viewers_of(rid)) == n:
                return
            time.sleep(0.05)
        raise AssertionError(f"never {n} viewers: {self.viewers_of(rid)}")


class NetworkTest(LimitBase):
    server_cfg = dict(MANY, spec_guest_share=1.0)

    def test_ipv6_per_64_56_and_48(self):
        """IPv6: 2 per /64, 4 per /56 (however many /64s), 8 per /48; IPv4: 2 per address."""
        pairs = []
        for i in range(12):
            a, b = self.acc(f"P{i:02d}a"), self.acc(f"P{i:02d}b")
            pairs.append(self.room_match(a, b, f"R{i}"))
        n = 0

        def watcher(ip):
            nonlocal n
            n += 1
            return self.guest(f"W{n:03d}", ip)

        self.wait_watch(self.acc("Obs"), pairs[-1])
        codes = [self.try_watch(watcher("2001:db8:7:100::1"), room=pairs[i]) for i in range(3)]   # one /64
        self.assertEqual(codes, ["ok", "ok", "rate_limited"])
        codes = [self.try_watch(watcher(f"2001:db8:7:1{i + 1:02x}::1"), room=pairs[3 + i]) for i in range(4)]
        self.assertEqual(codes, ["ok", "ok", "rate_limited", "rate_limited"])     # the /56: 4 in all
        codes = [self.try_watch(watcher(f"2001:db8:7:{i + 2:x}00::1"), room=pairs[3 + i]) for i in range(6)]
        self.assertEqual(codes, ["ok", "ok", "ok", "ok", "rate_limited", "rate_limited"])   # the /48: 8 in all
        self.assertEqual(self.try_watch(watcher("2001:db8:8::1"), room=pairs[9]), "ok")      # the next /48
        codes = [self.try_watch(watcher("192.0.2.77"), room=pairs[i]) for i in range(10, 12)]
        codes.append(self.try_watch(watcher("192.0.2.77"), room=pairs[0]))
        self.assertEqual(codes, ["ok", "ok", "rate_limited"])       # an IPv4 address: 2
        # leaving one frees its count at once; switching to another match is not a second one
        w = self.clients[-3]
        w.unwatch()
        self.assertEqual(self.try_watch(watcher("192.0.2.77"), room=pairs[0]), "ok")


if __name__ == "__main__":
    unittest.main()
