"""Spectating live matches (docs/SPECTATE.md): who may watch (friends of a player, anybody for a room's match),
the players' privacy setting (on by default, ranked only when both allow ranked), blocks, the limit per match;
the live stream going from the streamer's file through the server to every spectator's file byte for byte, a
spectator who joins late getting it from the session's start, a rematch in the running session keeping the
stream (and a room's stream watchable between its match and the rematch); the server's bounds (piece size, order, rate, buffer); and older launchers that never see any of it."""
import os
import shutil
import struct
import tempfile
import time
import unittest

import util
from util import ServerThread, client, expect

from t5lobby import spectate
from t5lobby.proto import LobbyError

SPEC_EVENTS = ("watching", "spec_ready", "spec_end", "spectators", "spec_want", "spec_stop", "spec_data")


def rec(t, payload):
    return struct.pack("<BI", t, len(payload)) + payload


def s16(text):
    b = text.encode()
    return struct.pack("<H", len(b)) + b


def session_rec(rollback=True):
    return rec(spectate.R_SESSION, struct.pack("<8I", 1, 1 if rollback else 0, 0, 2, 1, 1234, 5678, 60)
               + s16("build") + s16("2026-10-19T00:00:00Z"))


def match_rec(k, p1=17, p2=6, stage=27, winner=-1, costumes=None):
    """A MATCH record as this build's game writes it (replay format 3: costume flags, then the two custom costume
    blocks when there are any -- docs/DIRECTFIGHT.md "Custom costumes online")."""
    flags = 0 if winner < 0 else 5
    tail = struct.pack("<I", 0) if costumes is None else struct.pack("<I", 1) + costumes[0] + costumes[1]
    return rec(spectate.R_MATCH, struct.pack("<I6I", k, 0, 0, 0, 0, 0, flags)
               + struct.pack("<12i", p1, p2, 0, 0, 1, 2, stage, 1, 0, winner, 1 if winner == 0 else 0,
                             1 if winner == 1 else 0) + struct.pack("<Q", 0) + s16("Alice") + s16("Bob") + tail)


def inputs_rec(first, n, seed=0):
    cols = bytes(((f * 7 + c + seed) % 5 == 0) * 0x10 for c in range(12) for f in range(n))
    return rec(spectate.R_INPUTS, struct.pack("<2I", first, n) + cols)


def end_rec(why="over"):
    return rec(spectate.R_END, s16(why))


class Base(unittest.TestCase):
    server_cfg = {}

    def setUp(self):
        self.s = ServerThread(**self.server_cfg).start()
        from t5lobby.server.ratelimit import KeyedBuckets
        self.s.call(lambda: setattr(self.s.srv, "registrations", KeyedBuckets(rate=100.0, burst=100)))
        self.tmp = tempfile.mkdtemp(prefix="t5spec")
        self.clients = []

    def tearDown(self):
        for c in self.clients:
            c.close()
        self.s.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def acc(self, name, allow=True, ranked=False, register=True, cap=True, **kw):
        d = os.path.join(self.tmp, name)
        kw.setdefault("auto_ready", True)
        if cap:
            kw.update(spectate=True, live_dir=os.path.join(d, "live"), watch_dir=os.path.join(d, "watch"))
        c = client(self.s, name, password=name.lower() + "-pw1", register=register, **kw)
        if cap and allow is not None:
            c.set_spectate_prefs(allow, ranked)
        self.clients.append(c)
        return c

    def befriend(self, a, b):
        a.add_friend(b.me["name"])
        expect(b, "friend_request")
        b.answer_friend(a.me["name"], True)
        t_end = time.monotonic() + 10
        while time.monotonic() < t_end:
            if any(f["name"] == b.me["name"] for f in (a.friend_list or {}).get("friends") or ()) and \
                    any(f["name"] == a.me["name"] for f in (b.friend_list or {}).get("friends") or ()):
                return
            time.sleep(0.02)
        raise AssertionError("not friends")

    def play(self, a, b, ranked=False):
        """A match between a and b (a challenge, accepted): both match_start events."""
        if ranked:
            a.ranked_match()
            b.ranked_match()
        else:
            cid = a.challenge(self.s.call(lambda: self.s.srv.by_name[b.me["name"].lower()].id))
            expect(b, "challenged")
            b.answer_challenge(cid, True)
        return expect(a, "match_start", 30), expect(b, "match_start", 30)

    def watch_flag(self, viewer, name, want, timeout=10.0):
        t_end = time.monotonic() + timeout
        while time.monotonic() < t_end:
            for f in (viewer.friend_list or {}).get("friends") or ():
                if f["name"] == name and f.get("watch") == want:
                    return
            time.sleep(0.05)
        raise AssertionError(f"{name}'s watch flag never became {want}: {viewer.friend_list}")

    @staticmethod
    def feed(path, data):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "ab") as f:
            f.write(data)

    @staticmethod
    def wait_file(path, data, timeout=15.0):
        t_end = time.monotonic() + timeout
        got = b""
        while time.monotonic() < t_end:
            try:
                with open(path, "rb") as f:
                    got = f.read()
            except OSError:
                got = b""
            if got == data:
                return
            time.sleep(0.05)
        raise AssertionError(f"{path}: {len(got)} bytes, expected {len(data)}")


class WatchTest(Base):
    def test_friend_watches_and_a_late_one_gets_it_from_the_start(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        v, w = self.acc("Vic"), self.acc("Wes")
        self.befriend(v, a)
        self.befriend(w, b)
        self.assertTrue(v.has_spectate())
        self.assertIn("spectate", v.welcome["features"])
        sa, sb = self.play(a, b)
        sid = sa["stream"]
        self.assertEqual(sid, sa["match"])                    # a new session: its first match's id
        self.assertEqual(sb["stream"], sid)
        self.watch_flag(v, "Alice", True)
        live = spectate.live_path(a.live_dir, sid)           # what the host's game would write
        head = spectate.MAGIC + session_rec() + match_rec(0)
        self.feed(live, head)
        r = v.watch(name="Alice")
        self.assertEqual((r["stream"], r["match"], r["spectators"]), (sid, sa["match"], 1))
        self.assertEqual([p["name"] for p in r["players"]], ["Alice", "Bob"])
        self.assertEqual(expect(a, "spectators")["count"], 1)
        ready = expect(v, "spec_ready", 15)
        self.assertEqual(len(ready["matches"]), 1)
        self.assertEqual(ready["matches"][0]["stage"], 27)
        body = b"".join(inputs_rec(f, 60, f) for f in range(0, 600, 60))
        self.feed(live, body)
        self.wait_file(ready["path"], head + body)
        # Wes joins 600 frames late: everything from the session's start, then the rest as it comes
        r2 = w.watch(name="Bob")
        self.assertEqual(r2["spectators"], 2)
        wready = expect(w, "spec_ready", 15)
        self.wait_file(wready["path"], head + body)
        more = inputs_rec(600, 60, 3) + match_rec(0, winner=1) + end_rec("session over")
        self.feed(live, more)
        for c, path in ((v, ready["path"]), (w, wready["path"])):
            ev = expect(c, "spec_end", 15)
            self.assertEqual(ev["reason"], "over")
            self.wait_file(path, head + body + more)
        self.assertTrue(self.s.wait_for(lambda: not self.s.srv.streams))
        p = spectate.LiveParser()
        with open(ready["path"], "rb") as f:
            p.feed(f.read())
        self.assertTrue(p.ended)
        self.assertEqual((p.frames, p.matches[0]["winner"]), (660, 1))

    def test_a_rematch_in_the_running_games_keeps_the_stream(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        v = self.acc("Vic")
        self.befriend(v, a)
        sa, _sb = self.play(a, b)
        sid = sa["stream"]
        live = spectate.live_path(a.live_dir, sid)
        head = spectate.MAGIC + session_rec() + match_rec(0)
        self.feed(live, head)
        v.watch(name="Alice")
        ready = expect(v, "spec_ready", 15)
        for c in (a, b):
            c.report_result(0, [1, 0], match_id=sa["match"])
        expect(a, "match_result", 15)
        a.rematch(sa["match"], True, keep=True)
        b.rematch(sa["match"], True, keep=True)
        sa2 = expect(a, "match_start", 20)
        self.assertNotEqual(sa2["match"], sa["match"])
        self.assertTrue(sa2["continue"])
        self.assertEqual(sa2["stream"], sid)                  # the same netplay session: the same stream
        more = match_rec(0, winner=0) + match_rec(1) + inputs_rec(0, 120)
        self.feed(live, more)
        self.wait_file(ready["path"], head + more)
        self.assertEqual(self.s.call(lambda: self.s.srv.streams[sid].match.id), sa2["match"])


    def test_the_relay_fallback_keeps_the_stream(self):
        """docs/NETPLAY.md "When Windows Firewall blocks the game": a game that heard nothing moves the match onto
        the relay and both games start the session again -- the same match, the same stream id, the same live file.
        The first session never shook hands (its file holds the magic and nothing else), so the spectators already
        watching get the new session through the same stream; the server keeps the stream while the match is on
        its way to the relay."""
        from unittest import mock
        a = self.acc("Alice", relay_bridge=True)
        b = self.acc("Bob", relay_bridge=True)
        v = self.acc("Vic")
        self.befriend(v, a)
        with mock.patch("t5lobby.client.local_ipv4s", lambda ip: []):
            sa, _sb = self.play(a, b)
            self.assertEqual(sa["path"], "direct")
            sid = sa["stream"]
            live = spectate.live_path(a.live_dir, sid)
            self.feed(live, spectate.MAGIC)                  # the host's game: no handshake yet, nothing but the magic
            r = v.watch(name="Alice")
            self.assertEqual(r["stream"], sid)
            self.assertTrue(self.s.wait_for(lambda: len(self.s.srv.streams[sid].buf) > 0, 15))
            # the server ticks while the match moves onto the relay (no data for a while): the stream stays
            def tick_while_moving():
                m = self.s.srv.by_name["alice"].match
                st = self.s.srv.streams[sid]
                old_state, old_fb = m.state, m.fallback
                m.state, m.fallback = "relay", True
                st.t_data -= 30
                self.s.srv._spec_tick()
                ended = st.ended
                m.state, m.fallback = old_state, old_fb
                return ended
            self.assertIsNone(self.s.call(tick_while_moving))
            self.assertTrue(a.nat_fallback(sa["match"]))
            sa2 = expect(a, "match_start", 20)
            self.assertEqual((sa2["match"], sa2["path"], sa2["stream"]), (sa["match"], "relay", sid))
        # the game started again for the match writes the same file anew (CREATE_ALWAYS + the magic), then its session
        blk = (bytes(range(256)) + bytes(8), bytes(0x108))
        with open(live, "wb") as f:
            f.write(spectate.MAGIC)
        body = session_rec() + match_rec(0, costumes=blk) + inputs_rec(0, 120)
        self.feed(live, body)
        ready = expect(v, "spec_ready", 20)
        self.wait_file(ready["path"], spectate.MAGIC + body)
        self.assertEqual(ready["matches"][0]["costumes"], [blk[0].hex(), blk[1].hex()])
        self.assertIsNone(self.s.call(lambda: self.s.srv.streams[sid].ended))


class RulesTest(Base):
    def test_who_may_watch(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        friend, stranger = self.acc("Fay"), self.acc("Sam")
        self.befriend(friend, b)
        sa, _ = self.play(a, b)
        with self.assertRaises(LobbyError) as e:
            stranger.watch(name="Alice")                       # not a friend, not a room
        self.assertEqual(e.exception.code, "not_allowed")
        with self.assertRaises(LobbyError) as e:
            a.watch(name="Bob")                                # a player of that match
        self.assertEqual(e.exception.code, "bad_state")
        self.watch_flag(friend, "Bob", True)
        friend.watch(name="Bob")                               # a friend of either player
        # blocked: a player who blocked the viewer is never watched by it
        friend.unwatch()
        b.block("Fay")
        with self.assertRaises(LobbyError):
            friend.watch(name="Alice")

    def test_privacy_switch_and_ranked_default(self):
        a, b = self.acc("Alice"), self.acc("Bob", allow=False)
        v = self.acc("Vic")
        self.befriend(v, a)
        sa, _ = self.play(a, b)
        self.watch_flag(v, "Alice", False)
        with self.assertRaises(LobbyError) as e:
            v.watch(name="Alice")
        self.assertIn("do not allow", e.exception.msg)
        b.set_spectate_prefs(True, False)
        self.watch_flag(v, "Alice", True)
        live = spectate.live_path(a.live_dir, sa["stream"])
        self.feed(live, spectate.MAGIC + session_rec() + match_rec(0))
        v.watch(name="Alice")
        expect(v, "spec_ready", 15)
        b.set_spectate_prefs(False, False)                    # turned off mid-match: the spectators stop at once
        self.assertEqual(expect(v, "spec_end", 10)["reason"], "not_allowed")
        expect(a, "spec_stop", 10)

    def test_ranked_needs_both_to_allow_ranked(self):
        a, b = self.acc("Alice"), self.acc("Bob")             # the default: casual yes, ranked no
        v = self.acc("Vic")
        self.befriend(v, a)
        sa, _ = self.play(a, b, ranked=True)
        self.assertTrue(sa["ranked"])
        with self.assertRaises(LobbyError):
            v.watch(name="Alice")
        a.set_spectate_prefs(True, True)
        with self.assertRaises(LobbyError):
            v.watch(name="Alice")                              # Bob still says no for ranked
        b.set_spectate_prefs(True, True)
        self.watch_flag(v, "Alice", True)
        v.watch(name="Alice")

    def test_rooms_are_public_and_the_limit(self):
        self.s.call(lambda: setattr(self.s.srv.cfg, "max_spectators", 1))
        a, b = self.acc("Alice"), self.acc("Bob")
        x, y = self.acc("Xan"), self.acc("Yul")
        room = a.create_room("Dojo")
        b.join_room(room["id"])
        expect(a, "match_start", 30)
        t_end = time.monotonic() + 10
        while time.monotonic() < t_end and not any(r.get("watch") for r in x.rooms if r["id"] == room["id"]):
            time.sleep(0.05)
        self.assertTrue(any(r.get("watch") for r in x.rooms if r["id"] == room["id"]))
        r = x.watch(room=room["id"])                           # nobody's friend: a room's match is public
        self.assertEqual(r["room"], "Dojo")
        with self.assertRaises(LobbyError) as e:
            y.watch(room=room["id"])                           # T5L_MAX_SPECTATORS
        self.assertEqual(e.exception.code, "server_full")

    def test_own_match_ends_the_watching(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        v, o = self.acc("Vic"), self.acc("Oli")
        self.befriend(v, a)
        sa, _ = self.play(a, b)
        self.feed(spectate.live_path(a.live_dir, sa["stream"]), spectate.MAGIC + session_rec() + match_rec(0))
        v.watch(name="Alice")
        expect(v, "spec_ready", 15)
        cid = v.challenge(self.s.call(lambda: self.s.srv.by_name["oli"].id))
        expect(o, "challenged")
        o.answer_challenge(cid, True)
        self.assertEqual(expect(v, "spec_end", 15)["reason"], "your_match")
        self.assertIsNone(self.s.call(lambda: self.s.srv.by_name["vic"].watching))


class RoomGapTest(Base):
    """Between a room's match and its rematch (1.1.4): the players' games keep the netplay session, so the room
    stays watchable from the Rooms list while the session's stream is alive -- a newcomer joins the spectators
    already watching and follows the stream into the rematch with them. Same privacy rules; a session nobody
    watched has no stream to join, and a declined rematch ends the set and with it the room's Watch."""

    def room_entry(self, viewer, rid, pred, timeout=10.0):
        """The room's entry in viewer's Rooms list once pred(entry) holds."""
        t_end = time.monotonic() + timeout
        while time.monotonic() < t_end:
            for e in viewer.rooms or ():
                if e["id"] == rid and pred(e):
                    return e
            time.sleep(0.05)
        raise AssertionError(f"room {rid}: {[e for e in viewer.rooms or () if e['id'] == rid]}")

    def room_match(self, watch=True):
        """Alice and Bob's room match, Xan (nobody's friend) watching it from the Rooms list, then its result from
        both. -> (alice, bob, xan, room id, Alice's match_start, the live file, Xan's file, the data so far)"""
        a, b, x = self.acc("Alice"), self.acc("Bob"), self.acc("Xan")
        rid = a.create_room("Dojo")["id"]
        b.join_room(rid)
        sa = expect(a, "match_start", 30)
        live = spectate.live_path(a.live_dir, sa["stream"])
        head = spectate.MAGIC + session_rec() + match_rec(0) + inputs_rec(0, 120)
        self.feed(live, head)
        path = None
        if watch:
            self.room_entry(x, rid, lambda e: e["status"] == "playing" and e.get("watch"))
            x.watch(room=rid)
            path = expect(x, "spec_ready", 15)["path"]
            self.wait_file(path, head)
        for c in (a, b):
            c.report_result(0, [1, 0], match_id=sa["match"])
        for c in (a, b):
            expect(c, "match_result", 15)
        return a, b, x, rid, sa, live, path, head

    def test_a_newcomer_between_the_match_and_its_rematch(self):
        a, b, x, rid, sa, live, xpath, head = self.room_match()
        y = self.acc("Yul")
        # the room's entry once the match is over (status no longer "playing"): still watchable
        e = self.room_entry(y, rid, lambda e: e["status"] != "playing")
        self.assertTrue(e["watch"])
        after = match_rec(0, winner=0)                         # the result screen, in the running session
        self.feed(live, after)
        r = y.watch(room=rid)
        self.assertEqual((r["stream"], r["match"], r["spectators"], r["room"]),
                         (sa["stream"], sa["match"], 2, "Dojo"))
        ypath = expect(y, "spec_ready", 15)["path"]
        self.wait_file(ypath, head + after)                    # the session from its start, like any late join
        self.wait_file(xpath, head + after)
        # the rematch in the running games: both spectators follow the stream into it
        a.rematch(sa["match"], True, keep=True)
        b.rematch(sa["match"], True, keep=True)
        sa2 = expect(a, "match_start", 20)
        self.assertEqual(sa2["stream"], sa["stream"])
        more = match_rec(1) + inputs_rec(120, 120, 5)
        self.feed(live, more)
        for path in (xpath, ypath):
            self.wait_file(path, head + after + more)
        self.assertEqual(self.s.call(lambda: len(self.s.srv.streams[sa["stream"]].viewers)), 2)
        self.room_entry(y, rid, lambda e: e["status"] == "playing" and e.get("watch"))

    def test_switching_spectators_off_between_the_match_and_its_rematch(self):
        a, b, x, rid, sa, live, xpath, head = self.room_match()
        y = self.acc("Yul")
        self.room_entry(y, rid, lambda e: e["status"] != "playing" and e.get("watch"))
        b.set_spectate_prefs(False, False)                     # in the gap too: the spectators stop at once
        self.assertEqual(expect(x, "spec_end", 10)["reason"], "not_allowed")
        self.room_entry(y, rid, lambda e: not e.get("watch"))
        with self.assertRaises(LobbyError) as e:
            y.watch(room=rid)
        self.assertEqual(e.exception.code, "bad_state")

    def test_a_declined_rematch_ends_the_watch(self):
        a, b, x, rid, sa, live, xpath, head = self.room_match()
        y = self.acc("Yul")
        self.room_entry(y, rid, lambda e: e["status"] != "playing" and e.get("watch"))
        b.rematch(sa["match"], False)                          # the set is over, so is the session
        self.room_entry(y, rid, lambda e: not e.get("watch"))
        with self.assertRaises(LobbyError) as e:
            y.watch(room=rid)
        self.assertEqual(e.exception.code, "bad_state")

    def test_a_session_nobody_watched_has_no_stream_to_join(self):
        a, b, x, rid, sa, live, _path, _head = self.room_match(watch=False)
        self.assertFalse(self.room_entry(x, rid, lambda e: e["status"] != "playing")["watch"])
        with self.assertRaises(LobbyError) as e:
            x.watch(room=rid)
        self.assertEqual(e.exception.code, "bad_state")
        self.assertEqual(self.s.call(lambda: len(self.s.srv.streams)), 0)
        # the rematch starts: watchable again (a new viewer starts the stream of the running session)
        a.rematch(sa["match"], True, keep=True)
        b.rematch(sa["match"], True, keep=True)
        expect(a, "match_start", 20)
        self.room_entry(x, rid, lambda e: e["status"] == "playing" and e.get("watch"))
        self.assertEqual(x.watch(room=rid)["stream"], sa["stream"])


class BoundsTest(Base):
    def test_the_streamer_is_bounded(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        v = self.acc("Vic")
        self.befriend(v, a)
        sa, _ = self.play(a, b)
        sid = sa["stream"]
        a._uploads.clear()                                     # the test sends the pieces itself
        self.s.call(lambda: setattr(self.s.srv.cfg, "spectate_buffer_kb", 8))
        a.live_dir = None                                      # (no upload task of its own)
        v.watch(name="Alice")
        want = expect(a, "spec_want", 10)
        self.assertEqual((want["stream"], want["from"]), (sid, 0))
        import base64
        a._fire({"t": "spec_data", "stream": sid, "off": 0, "data": base64.b64encode(b"x" * 5500).decode()})  # too big
        self.assertEqual(expect(v, "spec_end", 10)["reason"], "stopped")
        self.assertTrue(self.s.wait_for(lambda: not self.s.srv.streams))
        v.watch(name="Alice")                                  # a new stream; this time over the buffer
        expect(a, "spec_want", 10)
        st = self.s.call(lambda: self.s.srv.streams[sid])
        for k in range(3):
            a._fire({"t": "spec_data", "stream": sid, "off": k * 4000, "data": base64.b64encode(b"y" * 4000).decode()})
        self.assertTrue(self.s.wait_for(lambda: st.ended == "too_long"))
        # (Vic's launcher found the pieces are no zlib stream before that: "damaged")
        self.assertIn(expect(v, "spec_end", 10)["reason"], ("too_long", "damaged"))
        self.assertLessEqual(self.s.call(lambda: len(st.buf)), 8 * 1024)

    def test_a_piece_from_somebody_else_is_ignored(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        v = self.acc("Vic")
        self.befriend(v, a)
        sa, _ = self.play(a, b)
        a.live_dir = None
        v.watch(name="Alice")
        expect(a, "spec_want", 10)
        import base64
        b._fire({"t": "spec_data", "stream": sa["stream"], "off": 0, "data": base64.b64encode(b"z" * 10).decode()})
        time.sleep(0.3)
        self.assertEqual(self.s.call(lambda: len(self.s.srv.streams[sa["stream"]].buf)), 0)


class OlderTest(Base):
    def test_older_launchers_see_nothing_and_cannot_be_watched(self):
        a = self.acc("Alice")
        old = self.acc("Olaf", cap=False)
        v = self.acc("Vic")
        self.befriend(v, a)
        sa, so = self.play(a, old)
        self.assertNotIn("stream", so)                         # no stream id for a launcher without the cap
        self.assertIn("stream", sa)
        self.watch_flag(v, "Alice", False)                     # Olaf could not say yes: nobody watches
        with self.assertRaises(LobbyError):
            v.watch(name="Alice")
        self.assertFalse(old.has_spectate())
        t_end = time.monotonic() + 1.0
        while time.monotonic() < t_end:
            ev = old.next_event(0.1)
            if ev is not None:
                self.assertNotIn(ev.get("t"), SPEC_EVENTS)
        for f in (old.friend_list or {}).get("friends") or ():
            self.assertNotIn("watch", f)


class UnaskedTest(Base):
    def test_a_watching_nobody_asked_for_makes_no_file(self):
        # (security review 3) a server sending `watching` by itself (no watch request) made the launcher open a new file
        # and unpack up to 64 MB into it from a few KB -- again and again with new stream ids
        a = self.acc("Alice")
        sid = "m0123456789ab"

        def push():
            pl = self.s.srv.by_name["alice"]
            pl.conn.send({"t": "watching", "stream": sid, "match": sid, "players": [], "began": 0, "spectators": 1})
            pl.conn.send({"t": "watching", "stream": sid, "match": sid, "players": [], "re": 999})
        self.s.call(push)
        time.sleep(1.0)
        self.assertIsNone(a.spec_watch)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "Alice", "watch", f"watch-{sid}.t5live")))


class ParserTest(unittest.TestCase):
    def test_pieces_of_any_size_and_end(self):
        data = spectate.MAGIC + session_rec() + match_rec(0) + inputs_rec(0, 100) + end_rec("x")
        p = spectate.LiveParser()
        out = b"".join(p.feed(data[i:i + 7]) for i in range(0, len(data), 7))
        self.assertEqual(out, data)
        self.assertTrue(p.ready and p.ended)
        self.assertEqual((p.frames, p.end_why, p.session["rollback"]), (100, "x", True))

    def test_costume_blocks_in_the_match_record(self):
        blk = (bytes((i * 7) & 0xFF for i in range(0x108)), bytes((i * 3 + 1) & 0xFF for i in range(0x108)))
        p = spectate.LiveParser()
        p.feed(spectate.MAGIC + session_rec() + match_rec(0, costumes=blk) + match_rec(1))
        self.assertIsNone(p.bad)
        self.assertEqual(p.matches[0]["costumes"], [blk[0].hex(), blk[1].hex()])
        self.assertIsNone(p.matches[1]["costumes"])
        p = spectate.LiveParser()                               # blocks announced but cut short: damaged
        p.feed(spectate.MAGIC + session_rec() + match_rec(0, costumes=(blk[0][:0x10], b"")))
        self.assertIn("costume", p.bad or "")

    def test_bad_streams(self):
        p = spectate.LiveParser()
        p.feed(b"NOTLIVE!\n" + b"x" * 20)
        self.assertIsNotNone(p.bad)
        p = spectate.LiveParser()
        p.feed(spectate.MAGIC + struct.pack("<BI", 2, 1 << 30))
        self.assertIsNotNone(p.bad)
        p = spectate.LiveParser()
        p.feed(spectate.MAGIC + inputs_rec(5, 10))             # inputs that do not start where the last ended
        self.assertIsNotNone(p.bad)

    def test_hashes_far_out_of_order(self):
        # (security review 3) the spectator's game sorts each HASH into place: a hand-made stream of hashes, each one
        # older than the last, kept it busy for hours. A few frames back (a rollback recorded a frame again) is fine.
        def hash_rec(f):
            return rec(spectate.R_HASH, struct.pack("<IQ", f, 0x1234))
        p = spectate.LiveParser()
        p.feed(spectate.MAGIC + session_rec() + match_rec(0) + hash_rec(600) + hash_rec(660) + hash_rec(540)
               + hash_rec(7200) + hash_rec(7200 - spectate.HASH_BACK))
        self.assertIsNone(p.bad)
        p.feed(hash_rec(100))
        self.assertIn("out of order", p.bad or "")

    def test_uploader_to_receiver(self):
        d = tempfile.mkdtemp(prefix="t5spec")
        try:
            src, dst = os.path.join(d, "a.t5live"), os.path.join(d, "b.t5live")
            data = spectate.MAGIC + session_rec() + match_rec(0) + b"".join(inputs_rec(f, 60, f) for f in range(0, 6000, 60))
            with open(src, "wb") as f:
                f.write(data[:5000])
            up, rx = spectate.Uploader(src), spectate.Receiver(dst)
            for off, piece in up.take(100000):
                self.assertTrue(rx.add(off, piece))
            with open(src, "ab") as f:
                f.write(data[5000:] + end_rec())
            while not up.done:
                for off, piece in up.take(spectate.CHUNK):
                    self.assertLessEqual(len(piece), spectate.CHUNK)
                    self.assertTrue(rx.add(off, piece))
            rx.close()
            with open(dst, "rb") as f:
                self.assertEqual(f.read(), data + end_rec())
            self.assertLess(up.sent, len(data) / 3)               # held inputs compress well
            # a receiver whose stream stops early ends its file with an END record (the game ends there)
            rx2 = spectate.Receiver(os.path.join(d, "c.t5live"))
            up2 = spectate.Uploader(src)
            pieces = up2.take(spectate.CHUNK)
            rx2.add(*pieces[0])
            self.assertFalse(rx2.add(pieces[0][0] + 99999, b"x"))  # out of order
            rx2.close("stopped")
            p = spectate.LiveParser()
            with open(os.path.join(d, "c.t5live"), "rb") as f:
                p.feed(f.read())
            self.assertTrue(p.ended)
            self.assertEqual(p.end_why, "stopped")
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
