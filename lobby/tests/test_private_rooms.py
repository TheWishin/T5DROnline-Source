"""Private and community rooms (docs/ONLINE.md "Rooms", server/rooms.py): a room locked with a password or an invite
code, listed as locked or hidden; joining with the right and a wrong password; the wrong-guess limits per player, per
address and per room (with the seconds to wait); the host's kick and lock changes; a friend's invite as the key; the
older launcher that never sees a locked room and is refused one; who may watch a private room's match; a community
room whose members take turns (winner stays / everyone in turn, sitting out after a missed ready check); and that
the password never shows up in a list, a message, the status JSON or the log."""
import asyncio
import logging
import time
import unittest

import util  # noqa: F401 -- (sets up the paths and the test environment)
from util import ServerThread, client, expect

from t5lobby.proto import LobbyError
from t5lobby.server import rooms as rooms_mod
from t5lobby.server.ratelimit import KeyedBuckets

PW = "Zebra Quokka 77"
PW_UNICODE = "철권의밤 パスワード"


class LogCatcher(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.lines = []

    def emit(self, record):
        try:
            self.lines.append(record.getMessage())
        except Exception:      # noqa: BLE001
            self.lines.append(str(record.msg))


class Base(unittest.TestCase):
    server_cfg = {"room_next_seconds": 0.5}

    def setUp(self):
        self.s = ServerThread(**self.server_cfg).start()
        # many players from one address in these tests: no per-address registration limit, and password changes
        # as often as a test needs
        self.s.call(lambda: setattr(self.s.srv, "registrations", KeyedBuckets(rate=100.0, burst=100)))
        self.s.call(lambda: setattr(self.s.srv, "pw_ops", KeyedBuckets(rate=100.0, burst=100)))
        self.clients = []
        self.logs = LogCatcher()
        logging.getLogger("t5lobby").addHandler(self.logs)
        self._level = logging.getLogger("t5lobby").level
        logging.getLogger("t5lobby").setLevel(logging.DEBUG)

    def tearDown(self):
        logging.getLogger("t5lobby").removeHandler(self.logs)
        logging.getLogger("t5lobby").setLevel(self._level)
        for c in self.clients:
            c.close()
        self.s.stop()

    def c(self, name, **kw):
        c = client(self.s, name, **kw)
        self.clients.append(c)
        return c

    def acc(self, name, **kw):
        return self.c(name, password=name.lower() + "-pw1", register=True, **kw)

    def srv(self):
        return self.s.srv

    def room_of(self, name):
        return self.s.call(lambda: (self.srv().by_name.get(name.lower()) or object()).__dict__.get("room"))

    def wait(self, pred, timeout=10.0, what="condition"):
        t_end = time.monotonic() + timeout
        while time.monotonic() < t_end:
            if pred():
                return
            time.sleep(0.03)
        raise AssertionError(f"timed out waiting for {what}")

    def listed(self, c, room_id):
        return any(r["id"] == room_id for r in c.rooms)

    def run_coro(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self.s.loop).result(15)

    def assert_no_secret(self, *secrets):
        """Nothing the server logged, keeps for its status JSON, or put in its event notes holds a secret."""
        status = repr(self.s.call(self.srv().status))
        events = repr(self.s.call(lambda: list(self.srv().events)))
        logs = "\n".join(self.logs.lines)
        for sec in secrets:
            for where, text in (("status", status), ("events", events), ("log", logs)):
                self.assertNotIn(sec, text, f"a secret in the {where}")
                if " " in sec:
                    for word in sec.split():
                        if len(word) >= 5:
                            self.assertNotIn(word, text, f"part of a secret in the {where}")


# ============================================================================== create, list, join
class CreateJoinTest(Base):
    def test_password_room_listed_as_locked_and_joined(self):
        a, b, old = self.c("Alice"), self.c("Bob"), self.c("Olaf", private_rooms=False)
        room = a.create_room("Friday night", private="password", password=PW)
        self.assertEqual((room["lock"], room["private"], room["hidden"]), ("password", True, False))
        self.assertNotIn(PW, repr(room))
        rid = room["id"]
        self.wait(lambda: self.listed(b, rid), what="the room in a new launcher's list")
        entry = next(r for r in b.rooms if r["id"] == rid)
        self.assertEqual((entry["private"], entry["lock"], entry["name"], entry["owner"]["name"], len(entry["members"])),
                         (True, "password", "Friday night", "Alice", 1))
        self.assertFalse(entry["watch"])
        time.sleep(0.5)
        self.assertFalse(self.listed(old, rid), "an older launcher never sees a locked room")
        # the stored secret is a salted hash, never the password
        secret = self.s.call(lambda: self.srv().rooms[rid].secret)
        self.assertTrue(secret.startswith("scrypt$"))
        self.assertNotIn(PW, secret)
        with self.assertRaises(LobbyError) as e:
            b.join_room(rid)                                          # no password
        self.assertEqual(e.exception.code, "auth_failed")
        with self.assertRaises(LobbyError) as e:
            b.join_room(rid, password="zebra quokka 77")               # wrong (case matters)
        self.assertEqual((e.exception.code, e.exception.msg), ("auth_failed", "wrong room password"))
        self.assertIsNone(self.room_of("Bob"))
        joined = b.join_room(rid, password=PW)
        self.assertEqual(joined["id"], rid)
        expect(a, "match_found")                                      # a classic room: the match starts at once
        expect(b, "match_found")
        self.assert_no_secret(PW)

    def test_unicode_password_and_the_rules(self):
        a, b = self.c("Alice"), self.c("Bob")
        for bad in ("abc", " lead", "trail ", "x" * 65, "tab\there", "zero​width", "nul\x00l", 1234, None):
            with self.assertRaises(LobbyError) as e:
                a.create_room("x", private="password", password=bad)
            self.assertEqual(e.exception.code, "bad_request", bad)
            self.assertNotIn(str(bad), e.exception.msg)
        room = a.create_room("Korea / Japan", private="password", password=PW_UNICODE)
        # NFC: the same password typed as decomposed jamo / kana with a combining mark is the same password
        import unicodedata
        b.join_room(room["id"], password=unicodedata.normalize("NFD", PW_UNICODE))
        self.assertEqual(self.room_of("Bob").id, room["id"])

    def test_invite_code_room_hidden_and_listed(self):
        a, b, c = self.c("Alice"), self.c("Bob"), self.c("Cid")
        room = a.create_room("Secret dojo", private="code", hidden=True, size=4)
        code = a.room_code
        self.assertRegex(code, r"^[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}$")
        self.assertNotIn(code, repr(room))
        self.assertTrue(room["hidden"])
        time.sleep(0.6)
        self.assertFalse(self.listed(b, room["id"]), "a hidden room is in nobody's list")
        self.assertIsNone(next(p for p in b.players if p["name"] == "Alice")["room"],
                          "nor does the player list say which room")
        with self.assertRaises(LobbyError) as e:
            b.join_room(room["id"])                                   # not by its id
        self.assertEqual(e.exception.code, "not_found")
        with self.assertRaises(LobbyError) as e:
            b.join_room(code="ABCD-EFGH-JKMN")
        self.assertEqual((e.exception.code, e.exception.msg), ("auth_failed", "no room has that invite code"))
        b.join_room(code=code.lower().replace("-", " "))              # typed in any case, any separators
        self.assertEqual(self.room_of("Bob").id, room["id"])
        self.assertEqual(b.room_code, code)                           # (kept as the host wrote it)
        # members see the room's view (pushed), never the code; only the host got it
        self.wait(lambda: (b.my_room or {}).get("id") == room["id"], what="Bob's room view")
        self.assertNotIn(code, repr(b.my_room))
        # the host makes a new code: the old one stops working
        a.room_lock("code")
        new = a.room_code
        self.assertNotEqual(new, code)
        with self.assertRaises(LobbyError):
            c.join_room(code=code)
        c.join_room(code=new)
        # listed instead of hidden
        a.room_lock(hidden=False)
        self.wait(lambda: any(r["id"] == room["id"] and r["lock"] == "code" for r in b.rooms), what="listed")
        self.assert_no_secret(code, new)

    def test_private_rooms_are_casual(self):
        a = self.acc("Alice")
        for kw in ({"private": "password", "password": PW}, {"private": "code"}, {"hidden": True}, {"size": 3}):
            with self.assertRaises(LobbyError) as e:
                a.create_room("r", ranked=True, **kw)
            self.assertEqual(e.exception.code, "not_allowed", kw)
        room = a.create_room("ranked one", ranked=True)
        with self.assertRaises(LobbyError):
            a.room_lock("password", PW)                               # nor can a ranked room be locked later
        self.assertIsNone(self.s.call(lambda: self.srv().rooms[room["id"]].lock))

    def test_sizes(self):
        a = self.c("Alice")
        for size in (1, 9, "3", True):
            with self.assertRaises(LobbyError):
                a.create_room("r", size=size)


# ============================================================================== wrong guesses
class GuessLimitTest(Base):
    def test_per_player_with_the_wait(self):
        a, b = self.c("Alice"), self.c("Bob")
        room = a.create_room("r", private="password", password=PW)
        for _ in range(5):                                            # T5L_ROOM_GUESSES
            with self.assertRaises(LobbyError) as e:
                b.join_room(room["id"], password="nope-nope")
            self.assertEqual(e.exception.code, "auth_failed")
        with self.assertRaises(LobbyError) as e:
            b.join_room(room["id"], password=PW)                      # even the right one, until the wait is over
        self.assertEqual(e.exception.code, "rate_limited")
        self.assertIn("try again in", e.exception.msg)
        self.assertTrue(1 <= e.exception.extra.get("retry", 0) <= 30, e.exception.extra)
        self.assertIsNone(self.room_of("Bob"))
        # wrong invite codes count on the same budget
        with self.assertRaises(LobbyError) as e:
            b.join_room(code="ABCD-EFGH-JKMN")
        self.assertEqual(e.exception.code, "rate_limited")

    def test_per_address_and_per_room(self):
        a = self.c("Alice")
        room = a.create_room("r", private="password", password=PW)
        guessers = [self.c(f"G{i}") for i in range(3)]              # one address (127.0.0.1): 10 for all of them
        wrong = 0
        for g in guessers[:2]:
            for _ in range(5):
                with self.assertRaises(LobbyError) as e:
                    g.join_room(room["id"], password="wrong-one")
                self.assertEqual(e.exception.code, "auth_failed")
                wrong += 1
        with self.assertRaises(LobbyError) as e:
            guessers[2].join_room(room["id"], password="wrong-one")   # a fresh player, the same address
        self.assertEqual(e.exception.code, "rate_limited")
        self.assertEqual(wrong, 10)

    def test_per_room(self):
        """Many players from many addresses together: the room's own limit (4 x T5L_ROOM_GUESSES), and the right
        password is refused too until the wait is over; another room is not affected."""
        a, g = self.c("Alice"), self.c("Gus")
        room = a.create_room("r", private="password", password=PW)
        srv = self.srv()
        r = self.s.call(lambda: srv.rooms[room["id"]])
        p = self.s.call(lambda: srv.by_name["gus"])
        self.s.call(lambda: setattr(srv, "room_guess", KeyedBuckets(rate=100.0, burst=1000)))    # (not per player)

        class FakeConn:
            closed = False
            caps = frozenset(("private_rooms",))

            def __init__(self, akey):
                self.akey = akey

        n = 0
        while True:
            try:
                self.run_coro(srv._room_check_password(r, p, FakeConn(f"10.1.{n}.1"), "wrong-one"))
            except LobbyError as e:
                if e.code == "rate_limited":
                    self.assertGreater(e.extra["retry"], 0)
                    break
                self.assertEqual(e.code, "auth_failed")
            n += 1
            self.assertLess(n, 40, "the room's own limit never came")
        self.assertTrue(20 <= n <= 21, n)                             # (one may have come back meanwhile)
        with self.assertRaises(LobbyError) as e:
            g.join_room(room["id"], password=PW)
        self.assertEqual(e.exception.code, "rate_limited")
        other = self.c("Ann").create_room("other", private="password", password=PW)
        g.join_room(other["id"], password=PW)

    def test_a_right_password_is_given_back(self):
        a = self.c("Alice")
        room = a.create_room("r", private="password", password=PW, size=8)
        a.room_line(False)                                            # (no pair, no match: they come and go)
        for i in range(7):                                            # more right ones than the budget: never limited
            g = self.c(f"Joiner{i}")
            g.join_room(room["id"], password=PW)
            g.leave_room()
            g.join_room(room["id"], password=PW)


# ============================================================================== the host
class HostTest(Base):
    def test_kick_and_no_way_back(self):
        a, b, c = self.c("Alice"), self.c("Bob"), self.c("Cid")
        room = a.create_room("r", private="password", password=PW, size=4)
        b.join_room(room["id"], password=PW)
        c.join_room(room["id"], password=PW)
        with self.assertRaises(LobbyError) as e:
            b.room_kick(self.s.call(lambda: self.srv().by_name["cid"].id))
        self.assertEqual(e.exception.code, "not_allowed")             # only the host
        with self.assertRaises(LobbyError):
            a.room_kick(a.me["id"])
        # (the first two are in their ready check by now: the host removes the one who waits)
        cid = self.s.call(lambda: self.srv().by_name["cid"].id)
        a.room_kick(cid)
        ev = expect(c, "notice")
        while ev.get("code") != "room_kicked":
            ev = expect(c, "notice")
        self.assertEqual(ev["msg"], "the room's host removed you from this room")
        self.assertIsNone(self.room_of("Cid"))
        with self.assertRaises(LobbyError) as e:
            c.join_room(room["id"], password=PW)
        self.assertIn("removed you", e.exception.msg)

    def test_kick_not_while_playing(self):
        a, b = self.c("Alice", auto_ready=True), self.c("Bob", auto_ready=True)
        room = a.create_room("r", private="password", password=PW)
        b.join_room(room["id"], password=PW)
        expect(a, "match_start", 30)
        with self.assertRaises(LobbyError) as e:
            a.room_kick(self.s.call(lambda: self.srv().by_name["bob"].id))
        self.assertEqual(e.exception.msg, "you can remove that player after their match")

    def test_password_change_and_removal(self):
        a, b, c, d = self.c("Alice"), self.c("Bob"), self.c("Cid"), self.c("Dee")
        room = a.create_room("r", private="password", password=PW, size=5)
        with self.assertRaises(LobbyError):
            b.room_lock("password", "other-pw")                       # not the host
        a.room_lock("password", "Walrus Mango!")
        with self.assertRaises(LobbyError):
            b.join_room(room["id"], password=PW)                      # the old one is gone
        b.join_room(room["id"], password="Walrus Mango!")
        a.room_lock("none")                                           # open now
        self.wait(lambda: any(r["id"] == room["id"] and not r.get("private") for r in c.rooms), what="unlocked")
        c.join_room(room["id"])
        a.room_lock("code")                                           # an invite code instead
        with self.assertRaises(LobbyError):
            d.join_room(room["id"])
        d.join_room(room["id"], code=a.room_code)
        self.assertEqual(len(self.s.call(lambda: self.srv().rooms[room["id"]].members)), 4)
        self.assert_no_secret(PW, "Walrus Mango!", a.room_code)

    def test_the_host_leaves(self):
        a, b = self.c("Alice"), self.c("Bob")
        room = a.create_room("r", private="code", size=3)
        a.room_line(False)                                            # (no match starts: Alice can leave any time)
        b.join_room(code=a.room_code)
        a.leave_room()
        self.wait(lambda: (b.my_room or {}).get("owner_id") == b.me["id"], what="Bob hosts now")
        b.room_lock("code")                                           # the new host makes a code of its own
        self.assertTrue(b.room_code)
        b.leave_room()
        self.wait(lambda: self.s.call(lambda: room["id"] not in self.srv().rooms), what="the room is gone")
        self.assertEqual(self.s.call(lambda: len(self.srv().room_codes)), 0)


# ============================================================================== friends, older launchers
class InviteOldTest(Base):
    def befriend(self, a, b):
        a.add_friend(b.me["name"])
        expect(b, "friend_request")
        b.answer_friend(a.me["name"], True)
        self.wait(lambda: any(f["name"] == b.me["name"] for f in (a.friend_list or {}).get("friends") or ()),
                  what="friends")

    def test_a_friends_invite_is_the_key(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        self.befriend(a, b)
        room = a.create_room("r", private="password", password=PW)
        inv = a.invite("Bob", "room")
        ev = expect(b, "invited")
        self.assertEqual((ev["room"]["id"], ev["room"]["private"]), (room["id"], True))
        self.assertNotIn(PW, repr(ev))
        b.answer_invite(inv["invite"], True)                         # no password asked
        self.assertEqual(self.room_of("Bob").id, room["id"])

    def test_an_invite_never_brings_blocked_players_together(self):
        # (security review 3) joining a room is refused when a member and the joiner blocked one another, but a friend's
        # invite let anybody in: into a community room (up to 8) whose line then paired the two -- the one thing a
        # block promises never to happen. The invite and its accept check every member now.
        a, b, c = self.acc("Alice"), self.acc("Bob"), self.acc("Cid")
        self.befriend(a, b)
        room = a.create_room("Community", size=4)
        c.join_room(room["id"])
        c.block("Bob")                                               # Cid never wants to meet Bob
        with self.assertRaises(LobbyError) as e:
            a.invite("Bob", "room")
        self.assertEqual(e.exception.code, "not_allowed")
        c.unblock("Bob")
        inv = a.invite("Bob", "room")                                # (no block: fine)
        expect(b, "invited")
        c.block("Bob")                                               # ... and Cid blocks him before he accepts
        with self.assertRaises(LobbyError):
            b.answer_invite(inv["invite"], True)
        self.assertIsNone(self.room_of("Bob"))
        with self.assertRaises(LobbyError):                          # (joining was refused already)
            b.join_room(room["id"])

    def test_blocked_players_are_never_paired_by_the_line(self):
        # (the line itself, should two who blocked one another ever be in one room: the next free pair without a block)
        import types
        from t5lobby.server.rooms import Room
        srv = self.srv()

        def run():
            def mk(n):
                return types.SimpleNamespace(name=n, id="p" + n, online=True, match=None, status="room", set=None,
                                             account_id=None, blocks={}, build_id="b", conn=None, guest=True)
            a, b, c = mk("Ann"), mk("Ben"), mk("Cat")
            r = Room(a, "x", False, size=4)
            r.members, r.line = [a, b, c], [a, b, c]
            for q in (a, b, c):
                q.room = r
            before = [q.name for q in srv._room_next_pair(r)]
            b.blocks["g:ann"] = {"name": "Ann", "guest": True, "since": 0}
            after = [q.name for q in srv._room_next_pair(r)]
            c.blocks["g:ann"] = {"name": "Ann", "guest": True, "since": 0}
            last = [q.name for q in srv._room_next_pair(r)]
            return before, after, last
        self.assertEqual(self.s.call(run), (["Ann", "Ben"], ["Ann", "Cat"], ["Ben", "Cat"]))

    def test_no_invite_back_after_a_kick(self):
        a, b, c = self.acc("Alice"), self.acc("Bob"), self.acc("Cid")
        self.befriend(a, b)
        room = a.create_room("r", private="password", password=PW, size=3)
        c.join_room(room["id"], password=PW)
        b.join_room(room["id"], password=PW)
        a.room_kick(self.s.call(lambda: self.srv().by_name["bob"].id))
        self.wait(lambda: self.room_of("Bob") is None, what="Bob out")
        with self.assertRaises(LobbyError) as e:
            a.invite("Bob", "room")
        self.assertIn("removed", e.exception.msg)

    def test_older_launcher(self):
        a, old = self.c("Alice"), self.c("Olaf", private_rooms=False)
        self.assertFalse(old.private_rooms_ok())
        with self.assertRaises(LobbyError):
            old.create_room("x", private="password", password=PW)     # the client says so itself
        locked = a.create_room("locked", private="password", password=PW)
        a2 = self.c("Ann")
        open_room = a2.create_room("open")
        self.wait(lambda: self.listed(old, open_room["id"]), what="the open room in the old list")
        self.assertFalse(self.listed(old, locked["id"]))
        with self.assertRaises(LobbyError) as e:
            old.join_room(locked["id"])                               # an id it got some other way
        self.assertEqual(e.exception.msg, "private rooms need a newer launcher; update it")
        # an old launcher's room_create with the new fields: a classic open room, as before
        r = old._call({"t": "room_create", "name": "mine", "size": 5, "private": "password", "password": "x"})
        self.assertEqual((r["room"].get("size", 2), r["room"].get("lock")), (2, None))

    def test_old_server(self):
        """A new launcher on a server without private rooms: the lobby works, the new options are refused locally."""
        import t5lobby.server.lobby as lobby_mod
        feats = [f for f in lobby_mod.FEATURES if f != "private_rooms"]
        caps = lobby_mod.CAPS - {"private_rooms"}
        orig_f, orig_c = lobby_mod.FEATURES, lobby_mod.CAPS
        lobby_mod.FEATURES, lobby_mod.CAPS = feats, caps
        try:
            a = self.c("Alice")
            self.assertFalse(a.private_rooms_ok())
            with self.assertRaises(LobbyError):
                a.create_room("x", private="code")
            a.create_room("plain")
        finally:
            lobby_mod.FEATURES, lobby_mod.CAPS = orig_f, orig_c


# ============================================================================== spectating
class SpectateTest(Base):
    def test_members_only(self):
        import os
        import shutil
        import tempfile
        tmp = tempfile.mkdtemp(prefix="t5priv")
        self.addCleanup(shutil.rmtree, tmp, True)

        def kw(n):
            return dict(spectate=True, auto_ready=True, live_dir=os.path.join(tmp, n, "live"),
                        watch_dir=os.path.join(tmp, n, "watch"))
        a, b, m, x = (self.c(n, **kw(n)) for n in ("Alice", "Bob", "Mia", "Xan"))
        for c in (a, b, m, x):
            c.set_spectate_prefs(True, False)
        room = a.create_room("r", private="password", password=PW, size=3)
        b.join_room(room["id"], password=PW)
        expect(a, "match_start", 30)
        m.join_room(room["id"], password=PW)                          # a member waiting for her turn
        srv = self.srv()
        mt = self.s.call(lambda: srv.rooms[room["id"]].match)
        self.assertIsNone(self.s.call(lambda: srv._spec_refusal(srv.by_name["mia"], mt)))
        err = self.s.call(lambda: srv._spec_refusal(srv.by_name["xan"], mt))
        self.assertEqual(err.msg, "only the room's players can watch its match")
        self.wait(lambda: (m.my_room or {}).get("watch") is True, what="Mia's room view says Watch")
        with self.assertRaises(LobbyError):
            x.watch(room=room["id"])
        m.watch(room=room["id"])
        # an open room's match is anybody's to watch; locking it sends non-members away
        a.room_lock("none")
        self.wait(lambda: any(r["id"] == room["id"] and r.get("watch") for r in x.rooms), what="watchable")
        x.watch(room=room["id"])
        a.room_lock("password", "new-pass")
        ev = expect(x, "spec_end", 10)
        self.assertEqual(ev["reason"], "not_allowed")
        self.assertIsNotNone(self.s.call(lambda: srv.by_name["mia"].watching))    # the member keeps watching


# ============================================================================== community rooms
class CommunityTest(Base):
    def play(self, winner_name, *clients):
        """The running room match: both report `winner_name` as the winner."""
        evs = [expect(c, "match_start", 30) for c in clients]
        slot = {c.me["name"]: ev["slot"] for c, ev in zip(clients, evs)}
        w = slot[winner_name]
        for c in clients:
            c.report_result(w, [3, 1] if w == 0 else [1, 3])
        for c in clients:
            res = expect(c, "match_result", 15)
            self.assertEqual(res["status"], "confirmed")
            self.assertEqual(res["rematch_window"], 0)               # the room picks the next match
        return evs

    def players(self, room_id):
        m = self.s.call(lambda: self.srv().rooms[room_id].match)
        return [p.name for p in m.players] if m else []

    def line(self, room_id):
        return self.s.call(lambda: [p.name for p in self.srv().rooms[room_id].line])

    def test_winner_stays(self):
        a, b, c = (self.c(n, auto_ready=True) for n in ("Alice", "Bob", "Cid"))
        room = a.create_room("Community", size=4, rotation="winner")
        b.join_room(room["id"])
        c.join_room(room["id"])
        self.play("Alice", a, b)                                      # Alice vs Bob: Alice wins
        self.assertEqual(self.line(room["id"])[:3], ["Alice", "Cid", "Bob"])
        self.play("Cid", a, c)                                        # Alice vs Cid (after the pause): Cid wins
        self.assertEqual(self.line(room["id"])[:3], ["Cid", "Bob", "Alice"])
        evs = self.play("Bob", c, b)                                  # Cid vs Bob, Cid hosts (the one who stayed)
        self.assertEqual(evs[0]["role"], "host")
        with self.assertRaises(LobbyError):
            b.rematch(evs[1]["match"], True)                          # no rematch votes in a community room

    def test_everyone_in_turn_and_sitting_out(self):
        a, b, c = (self.c(n, auto_ready=True) for n in ("Alice", "Bob", "Cid"))
        d = self.c("Dee")                                             # answers its ready checks by hand
        room = a.create_room("Turns", size=4, rotation="queue", private="code")
        for x in (b, d, c):
            x.join_room(code=a.room_code)
        self.play("Alice", a, b)                                      # Alice (first at the table) to the back
        self.assertEqual(self.line(room["id"]), ["Bob", "Dee", "Cid", "Alice"])
        ev = expect(d, "match_found", 15)                             # Bob vs Dee: Dee declines
        self.assertTrue(ev["ready_check"])
        d.ready(False, ev["match"])
        n = expect(d, "notice", 10)
        while n.get("code") != "room_away":
            n = expect(d, "notice", 10)
        self.assertNotIn("Dee", self.line(room["id"]))
        self.wait(lambda: self.players(room["id"]) == ["Bob", "Cid"], what="Bob vs Cid next")
        self.wait(lambda: any(p["name"] == "Dee" and p["state"] == "away" for p in (d.my_room or {}).get("players", [])),
                  what="Dee shows as sitting out")
        d.room_line(True)                                             # back in line, at its end
        self.assertEqual(self.line(room["id"])[-1], "Dee")
        with self.assertRaises(LobbyError):
            self.c("Eve").room_line(False)                            # not in a room

    def test_the_members_view(self):
        a, b, c = (self.c(n, auto_ready=True) for n in ("Alice", "Bob", "Cid"))
        room = a.create_room("View", size=3)
        b.join_room(room["id"])
        c.join_room(room["id"])
        expect(c, "room")
        self.wait(lambda: (c.my_room or {}).get("playing") and len(c.my_room.get("players", ())) == 3,
                  what="Cid sees who plays")
        v = c.my_room
        self.assertEqual(v["size"], 3)
        self.assertEqual(v["rotation"], "winner")
        self.assertEqual(sorted(p["state"] for p in v["players"]), ["line", "playing", "playing"])
        self.assertEqual(v["owner_id"], a.me["id"])
        with self.assertRaises(LobbyError):
            self.c("Dan").join_room(room["id"])                       # full
        self.play("Bob", a, b)
        self.wait(lambda: (c.my_room or {}).get("next") is not None or (c.my_room or {}).get("playing"),
                  what="the next match announced")

    def test_classic_room_unchanged(self):
        """Two-player rooms (and older launchers' rooms) work as before: rematch votes, Ready again."""
        a, b = self.c("Alice", auto_ready=True), self.c("Bob", auto_ready=True)
        room = a.create_room("dojo")
        self.assertEqual(room["size"], 2)
        b.join_room(room["id"])
        ta = expect(a, "match_start", 30)["ticket"]
        expect(b, "match_start", 30)
        a.report_result(0, [3, 0])
        b.report_result(0, [3, 0])
        self.assertEqual(expect(a, "match_result")["rematch_window"], self.s.cfg.rematch_window)
        a.rematch(ta.match_id, True)
        b.rematch(ta.match_id, True)
        expect(a, "match_start", 30)
        self.wait(lambda: self.s.call(lambda: self.srv().rooms[room["id"]].status()) == "playing",
                  what="the room shows playing during the rematch")


class UnitTest(unittest.TestCase):
    def test_password_rules(self):
        ok = ("abcd", "x" * 64, "Tekken 5 DR", PW_UNICODE, "Übung macht", "Ñandú!", "密码密码")
        for pw in ok:
            self.assertIsNotNone(rooms_mod.clean_room_password(pw), pw)
        for pw in ("abc", "x" * 65, " a b c", "abcd ", "ab\ncd", "ab‮cd", "\ud800abc", b"abcd", None,
                   "😀" * 65):
            self.assertIsNone(rooms_mod.clean_room_password(pw), repr(pw))

    def test_codes(self):
        seen = set()
        for _ in range(200):
            code = rooms_mod.new_code()
            self.assertEqual(rooms_mod.normalize_code(code), code.replace("-", ""))
            seen.add(code)
        self.assertEqual(len(seen), 200)
        self.assertIsNone(rooms_mod.normalize_code("ABCD-EFGH-IJK0"))   # I and 0 are not in the alphabet
        self.assertIsNone(rooms_mod.normalize_code("short"))
        self.assertIsNone(rooms_mod.normalize_code(None))


if __name__ == "__main__":
    unittest.main()
