"""Friends and invites (docs/ONLINE.md "Friends and invites"): requests the other side must accept, the list with who is
online / in a match / offline, removing, invites to a casual match or a room with a one-click accept; the
limits (requests per day, waiting requests, list size, one invite at a time), blocks ending a friendship, guests
kept out; the database migration that adds the tables; and older launchers and servers (1.1.0 from git, and a
client without the "friends" cap like 1.1.1) that never see one of the new messages."""
import asyncio
import io
import os
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile
import threading
import time
import unittest

import util
from util import BUILD, ServerThread, client, expect

from t5lobby import proto
from t5lobby.client import LobbyClient
from t5lobby.proto import LobbyError
from t5lobby.server import store as store_mod
from t5lobby.server.store import SCHEMA, Store

FRIEND_EVENTS = ("friends", "friend_status", "friend_request", "friend_update", "invited", "invite_update")
LOBBY = os.path.dirname(util.HERE)


def server(**cfg):
    """A test server on which one address may create many accounts (the tests make a few each)."""
    from t5lobby.server.ratelimit import KeyedBuckets
    s = ServerThread(**cfg).start()
    s.call(lambda: setattr(s.srv, "registrations", KeyedBuckets(rate=100.0, burst=100)))
    return s


def drain(c):
    """Every event waiting in the client's queue."""
    out = []
    while True:
        ev = c.next_event(0)
        if ev is None:
            return out
        out.append(ev)


def wait_list(c, pred, timeout=10.0):
    """Until the client's merged friends list satisfies pred (it arrives by push)."""
    t_end = time.monotonic() + timeout
    while time.monotonic() < t_end:
        fl = c.friend_list
        if fl is not None and pred(fl):
            return fl
        time.sleep(0.02)
    raise AssertionError(f"friends list not as expected: {c.friend_list}")


def names(rows):
    return sorted(r["name"] for r in rows or ())


def status_of(c, name):
    for f in (c.friend_list or {}).get("friends") or ():
        if f["name"] == name:
            return f["status"]
    return None


class Base(unittest.TestCase):
    server_cfg = {}

    def setUp(self):
        self.s = server(**self.server_cfg)
        self.clients = []

    def tearDown(self):
        for c in self.clients:
            c.close()
        self.s.stop()

    def acc(self, name, register=True, **kw):
        c = client(self.s, name, password=name.lower() + "-pw1", register=register, **kw)
        self.clients.append(c)
        return c

    def guest(self, name, **kw):
        c = client(self.s, name, **kw)
        self.clients.append(c)
        return c

    def befriend(self, a, b):
        a.add_friend(b.me["name"])
        expect(b, "friend_request")
        b.answer_friend(a.me["name"], True)
        wait_list(a, lambda fl: b.me["name"] in names(fl["friends"]))
        wait_list(b, lambda fl: a.me["name"] in names(fl["friends"]))


class RequestTest(Base):
    def test_request_accept_and_the_list(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        self.assertTrue(a.has_friends())
        self.assertIn("friends", a.welcome["features"])
        self.assertEqual(a.welcome["friend_limits"]["max"], 100)
        wait_list(a, lambda fl: fl["friends"] == [] and fl["incoming"] == [])        # pushed after login
        r = a.add_friend("bob")                                                       # any case
        self.assertEqual((r["name"], r["state"]), ("Bob", "pending"))
        ev = expect(b, "friend_request")
        self.assertEqual(ev["name"], "Alice")
        wait_list(b, lambda fl: names(fl["incoming"]) == ["Alice"])
        wait_list(a, lambda fl: names(fl["outgoing"]) == ["Bob"])
        self.assertEqual(a.add_friend("Bob")["state"], "pending")                    # asking twice counts once
        b.answer_friend("Alice", True)
        self.assertEqual(expect(a, "friend_update")["state"], "accepted")
        fl = wait_list(a, lambda fl: names(fl["friends"]) == ["Bob"] and fl["outgoing"] == [])
        bob = fl["friends"][0]
        self.assertEqual((bob["status"], bob["activity"], bob["invite"]), ("online", "idle", "ok"))
        self.assertIn("rank", bob)
        wait_list(b, lambda fl: names(fl["friends"]) == ["Alice"] and fl["incoming"] == [])
        self.assertEqual(names(b.friends_list()["friends"]), ["Alice"])                # asked for, the same
        self.assertEqual(self.s.call(lambda: self.s.srv.store.friend_count(self.s.srv.by_name["alice"].account_id)), 1)
        self.assertEqual(a.add_friend("Bob")["state"], "friends")

    def test_both_ask_and_are_friends_at_once(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        a.add_friend("Bob")
        self.assertEqual(b.add_friend("Alice")["state"], "friends")
        wait_list(a, lambda fl: names(fl["friends"]) == ["Bob"])

    def test_decline_then_wait_before_asking_again(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        a.add_friend("Bob")
        expect(b, "friend_request")
        b.answer_friend("Alice", False)
        self.assertEqual(expect(a, "friend_update")["state"], "declined")
        wait_list(a, lambda fl: fl["outgoing"] == [])
        with self.assertRaises(LobbyError) as e:
            a.add_friend("Bob")
        self.assertIn("declined your last request; you can ask again in 7 day(s)", e.exception.msg)
        b.add_friend("Alice")                                                         # the other way round is fine
        expect(a, "friend_request")

    def test_cancel_and_remove(self):
        a, b, c = self.acc("Alice"), self.acc("Bob"), self.acc("Cid")
        a.add_friend("Cid")
        wait_list(c, lambda fl: names(fl["incoming"]) == ["Alice"])
        a.cancel_friend_request("Cid")
        wait_list(c, lambda fl: fl["incoming"] == [])
        with self.assertRaises(LobbyError):
            c.answer_friend("Alice", True)
        with self.assertRaises(LobbyError):
            a.cancel_friend_request("Cid")
        self.befriend(a, b)
        b.remove_friend("Alice")
        wait_list(a, lambda fl: fl["friends"] == [])
        wait_list(b, lambda fl: fl["friends"] == [])
        with self.assertRaises(LobbyError) as e:
            b.remove_friend("Alice")
        self.assertEqual(e.exception.code, proto.E_NOT_FOUND)

    def test_no_such_account_and_not_yourself(self):
        a = self.acc("Alice")
        self.guest("Visitor")
        for name in ("Nobody", "Visitor", "x"):                                       # a guest is no account
            with self.assertRaises(LobbyError) as e:
                a.add_friend(name)
            self.assertEqual(e.exception.code, proto.E_NOT_FOUND)
        with self.assertRaises(LobbyError):
            a.add_friend("alice")

    def test_guests_cannot_have_friends(self):
        self.acc("Alice")
        g = self.guest("Visitor")
        self.assertTrue(g.has_friends())                     # the server has them ...
        for fn in (lambda: g.add_friend("Alice"), g.friends_list, lambda: g.invite("Alice")):
            with self.assertRaises(LobbyError) as e:          # ... but not for guests
                fn()
            self.assertEqual(e.exception.code, proto.E_NOT_ALLOWED)
            self.assertIn("guests cannot have friends", e.exception.msg)
        time.sleep(0.5)
        self.assertEqual([ev for ev in drain(g) if ev["t"] in FRIEND_EVENTS], [])
        self.assertIsNone(g.friend_list)

    def test_profile_says_what_the_other_is(self):
        a, b, c = self.acc("Alice"), self.acc("Bob"), self.acc("Cid")
        self.assertIsNone(a.profile("Bob").get("friend"))
        a.add_friend("Bob")
        self.assertEqual(a.profile("Bob")["friend"], "asked")
        self.assertEqual(b.profile("Alice")["friend"], "asks")
        b.answer_friend("Alice", True)
        self.assertEqual(a.profile("Bob")["friend"], "friends")
        self.assertNotIn("friend", a.profile("Alice"))                                 # yourself
        self.assertIsNone(c.profile("Alice").get("friend"))

    def test_last_seen_is_for_friends(self):
        # (security review 2) when an account was last online: its friends' list says it, and a profile tells it only
        # to the account itself and its friends -- not to anybody who opens the profile
        a, b, c = self.acc("Alice"), self.acc("Bob"), self.acc("Cid")
        self.befriend(a, b)
        self.assertIn("last_seen", a.profile("Alice"))
        self.assertIn("last_seen", b.profile("Alice"))
        self.assertNotIn("last_seen", c.profile("Alice"))
        self.assertIn("member_since", c.profile("Alice"))                            # (the rest of the profile stays)

    def test_asking_again_after_taking_it_back_does_not_pop_up(self):
        # (security review 2) "add, take back, add ..." put "X wants to be your friend" on the other's screen up to
        # 20 times a day: a request again within a day of taking one back waits in the list but is not announced
        a, b = self.acc("Alice"), self.acc("Bob")
        a.add_friend("Bob")
        expect(b, "friend_request")
        a.cancel_friend_request("Bob")
        wait_list(b, lambda fl: fl["incoming"] == [])
        drain(b)
        self.assertEqual(a.add_friend("Bob")["state"], "pending")
        wait_list(b, lambda fl: names(fl["incoming"]) == ["Alice"])                   # it is there to answer
        time.sleep(0.5)
        self.assertEqual([e for e in drain(b) if e["t"] == "friend_request"], [])     # but it did not pop up
        b.answer_friend("Alice", True)
        wait_list(a, lambda fl: names(fl["friends"]) == ["Bob"])
        c = self.acc("Cid")                                                           # someone else's first request
        c.add_friend("Bob")
        expect(b, "friend_request")

    def test_friendships_survive_a_restart(self):
        d = tempfile.mkdtemp()
        db = os.path.join(d, "lobby.db")
        self.s.stop()
        self.s = server(db=db)
        try:
            a, b = self.acc("Alice"), self.acc("Bob")
            self.befriend(a, b)
            for c in (a, b):
                c.close()
            self.clients = []
            self.s.stop()
            self.s = server(db=db)
            a = self.acc("Alice", register=False)
            fl = wait_list(a, lambda fl: names(fl["friends"]) == ["Bob"])
            self.assertEqual(fl["friends"][0]["status"], "offline")
            b = self.acc("Bob", register=False)
            wait_list(a, lambda fl: status_of(a, "Bob") == "online")
        finally:
            for c in self.clients:
                c.close()
            self.clients = []
            self.s.stop()
            self.s = server()
            shutil.rmtree(d, ignore_errors=True)


class PresenceTest(Base):
    def test_online_in_match_offline(self):
        a, b = self.acc("Alice"), self.acc("Bob", auto_ready=True)
        self.befriend(a, b)
        c = self.acc("Cid", auto_ready=True)
        b.quick_match()
        ev = expect(a, "friend_status")
        self.assertEqual((ev["name"], ev["status"], ev["activity"]), ("Bob", "online", "queue"))
        c.quick_match()
        wait_list(a, lambda fl: status_of(a, "Bob") == "in_match")
        self.assertEqual(next(f for f in a.friend_list["friends"] if f["name"] == "Bob")["invite"], "busy")
        expect(b, "match_start", 20)
        b.leave_match()
        wait_list(a, lambda fl: status_of(a, "Bob") == "online")
        b.close()
        self.clients.remove(b)
        wait_list(a, lambda fl: status_of(a, "Bob") == "offline")
        st = [f for f in a.friend_list["friends"] if f["name"] == "Bob"][0]
        self.assertEqual((st["activity"], st["invite"]), (None, "offline"))
        b = self.acc("Bob", register=False)
        wait_list(a, lambda fl: status_of(a, "Bob") == "online")
        # a stranger never hears about Bob
        self.assertEqual([ev for ev in drain(c) if ev["t"] == "friend_status"], [])

    def test_a_friend_on_another_build_or_an_older_launcher(self):
        a = self.acc("Alice")
        b = self.acc("Bob")
        self.befriend(a, b)
        b.close()
        self.clients.remove(b)
        old = client(self.s, "Bob", password="bob-pw1", friends=False)            # like 1.1.1: no "friends" cap
        self.clients.append(old)
        wait_list(a, lambda fl: [f["invite"] for f in fl["friends"]] == ["update"])
        with self.assertRaises(LobbyError) as e:
            a.invite("Bob")
        self.assertIn("too old for invites", e.exception.msg)
        old.close()
        self.clients.remove(old)
        other = client(self.s, "Bob", password="bob-pw1", build=util.OTHER_BUILD)
        self.clients.append(other)
        wait_list(a, lambda fl: [f["invite"] for f in fl["friends"]] == ["version"])
        with self.assertRaises(LobbyError) as e:
            a.invite("Bob")
        self.assertEqual(e.exception.code, proto.E_VERSION)


class LimitTest(Base):
    server_cfg = {"friend_requests_day": 3, "friend_pending": 2, "max_friends": 2}

    def test_requests_per_day_waiting_and_list_size(self):
        a = self.acc("Alice")
        bob, cid, dan, eve = (self.acc(n) for n in ("Bob", "Cid", "Dan", "Eve"))
        a.add_friend("Bob")
        a.add_friend("Cid")
        with self.assertRaises(LobbyError) as e:                  # 2 waiting already
            a.add_friend("Dan")
        self.assertIn("2 of your friend requests are waiting for an answer", e.exception.msg)
        bob.answer_friend("Alice", True)
        a.add_friend("Dan")                                       # the 3rd request today
        with self.assertRaises(LobbyError) as e:
            a.add_friend("Eve")
        self.assertEqual(e.exception.code, proto.E_RATE)
        self.assertIn("3 friend requests a day", e.exception.msg)
        wait_list(a, lambda fl: fl["requests_left"] == 0)
        dan.answer_friend("Alice", True)                          # 2 friends: the list is full
        wait_list(a, lambda fl: names(fl["friends"]) == ["Bob", "Dan"])
        with self.assertRaises(LobbyError) as e:                  # (asked before it was full)
            cid.answer_friend("Alice", True)
        self.assertIn("that player's friends list is full", e.exception.msg)
        eve.add_friend("Alice")
        with self.assertRaises(LobbyError) as e:
            a.answer_friend("Eve", True)
        self.assertIn("your friends list is full (2)", e.exception.msg)

    def test_a_full_inbox(self):
        a = self.acc("Alice")
        for n in ("Bob", "Cid"):
            self.acc(n).add_friend("Alice")
        with self.assertRaises(LobbyError) as e:
            self.acc("Dan").add_friend("Alice")
        self.assertIn("too many friend requests waiting", e.exception.msg)
        wait_list(a, lambda fl: names(fl["incoming"]) == ["Bob", "Cid"])

    def test_requests_run_out(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        a.add_friend("Bob")
        st = self.s.srv.store
        self.s.call(lambda: st._x("UPDATE friend_requests SET created = created - 15 * 86400"))
        self.assertEqual(b.friends_list()["incoming"], [])                           # 14 days: gone
        self.assertEqual(self.s.call(lambda: st.expire_friend_requests(time.time() - 14 * 86400))[0], 1)
        self.assertEqual(a.add_friend("Bob")["state"], "pending")                    # and may be asked again


class AddressLimitTest(Base):
    server_cfg = {"friend_requests_address": 3}

    def test_requests_per_address(self):
        # (security review 2) the per-account limits times every account one address can make: one internet address
        # sends T5L_FRIEND_REQUESTS_ADDRESS requests a day, all its accounts together (the test players share 127.0.0.1)
        a, m = self.acc("Alice"), self.acc("Mallory")
        for n in ("Bob", "Cid", "Dan", "Eve"):
            self.acc(n)
        a.add_friend("Bob")
        a.add_friend("Cid")
        m.add_friend("Dan")
        with self.assertRaises(LobbyError) as e:
            m.add_friend("Eve")
        self.assertEqual(e.exception.code, proto.E_RATE)
        self.assertIn("this internet address", e.exception.msg)
        self.assertEqual(a.add_friend("Bob")["state"], "pending")                    # (asked already: not counted)


class BlockTest(Base):
    def test_a_block_ends_the_friendship(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        self.befriend(a, b)
        a.block("Bob")
        wait_list(a, lambda fl: fl["friends"] == [])
        wait_list(b, lambda fl: fl["friends"] == [])
        self.assertFalse(self.s.call(lambda: self.s.srv.store.are_friends(
            self.s.srv.by_name["alice"].account_id, self.s.srv.by_name["bob"].account_id)))
        with self.assertRaises(LobbyError) as e:
            a.add_friend("Bob")
        self.assertIn("you blocked that player", e.exception.msg)
        # Bob's request goes nowhere, and he cannot tell: it looks like one nobody answers
        drain(a)
        self.assertEqual(b.add_friend("Alice")["state"], "pending")
        wait_list(b, lambda fl: names(fl["outgoing"]) == ["Alice"])
        time.sleep(0.5)
        self.assertEqual([ev for ev in drain(a) if ev["t"] == "friend_request"], [])
        self.assertEqual(a.friends_list()["incoming"], [])
        with self.assertRaises(LobbyError):
            a.answer_friend("Bob", True)
        self.assertNotEqual(a.profile("Bob").get("friend"), "asks")
        a.unblock("Bob")
        self.assertEqual(names(a.friends_list()["friends"]), [])                      # unblocking is not befriending

    def test_a_block_cancels_the_requests_and_invites(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        a.add_friend("Bob")
        wait_list(b, lambda fl: names(fl["incoming"]) == ["Alice"])
        b.block("Alice")
        wait_list(b, lambda fl: fl["incoming"] == [])
        wait_list(a, lambda fl: fl["outgoing"] == [])
        b.unblock("Alice")
        self.assertEqual(b.friends_list()["incoming"], [])                           # (it does not come back)
        c, d = self.acc("Cid"), self.acc("Dan")
        self.befriend(c, d)
        inv = c.invite("Dan")
        expect(d, "invited")
        d.block("Cid")
        ev = expect(c, "invite_update")
        self.assertEqual((ev["invite"], ev["state"]), (inv["invite"], "cancelled"))


class InviteTest(Base):
    def friends(self):
        a, b = self.acc("Alice"), self.acc("Bob")
        self.befriend(a, b)
        drain(a)
        drain(b)
        return a, b

    def test_casual_invite_one_click(self):
        a, b = self.friends()
        b.quick_match()                                                   # searching does not stop an invite
        r = a.invite("Bob", "casual")
        self.assertEqual((r["name"], r["kind"]), ("Bob", "casual"))
        ev = expect(b, "invited")
        self.assertEqual((ev["invite"], ev["from"]["name"], ev["kind"]), (r["invite"], "Alice", "casual"))
        self.assertIn(r["invite"], b.invites)
        b.answer_invite(r["invite"], True)
        self.assertEqual(expect(a, "invite_update")["state"], "accepted")
        fa, fb = expect(a, "match_found"), expect(b, "match_found")
        for f in (fa, fb):
            self.assertEqual((f["origin"], f["ready_check"], f["ranked"]), ("invite", False, False))
        self.assertEqual(fa["opponent"]["name"], "Bob")
        sa, sb = expect(a, "match_start", 20), expect(b, "match_start", 20)
        self.assertEqual({sa["role"], sb["role"]}, {"host", "join"})
        self.assertEqual(self.s.call(lambda: self.s.srv.queues["quick"]), [])      # Bob left the queue for it
        self.assertEqual(self.s.call(lambda: self.s.srv.counters["invites_accepted"]), 1)

    def test_room_invite(self):
        a, b = self.friends()
        with self.assertRaises(LobbyError) as e:
            a.invite("Bob", "room")
        self.assertIn("create a room first", e.exception.msg)
        room = a.create_room("Alice's dojo")
        r = a.invite("Bob", "room")
        ev = expect(b, "invited")
        self.assertEqual((ev["kind"], ev["room"]["name"]), ("room", "Alice's dojo"))
        got = b.answer_invite(r["invite"], True)
        self.assertEqual(got["room"]["id"], room["id"])
        fb = expect(b, "match_found")
        self.assertEqual((fb["origin"], fb["ready_check"]), ("invite", False))     # no second question
        sa = expect(a, "match_start", 20)
        self.assertEqual(sa["role"], "host")                                       # the room's owner is P1
        self.assertEqual(self.s.call(lambda: self.s.srv.by_name["bob"].room.id), room["id"])

    def test_decline_cancel_expire(self):
        a, b = self.friends()
        r = a.invite("Bob")
        expect(b, "invited")
        b.answer_invite(r["invite"], False)
        self.assertEqual(expect(a, "invite_update")["state"], "declined")
        time.sleep(2.1)                                                   # (one invite per 2 s)
        with self.assertRaises(LobbyError) as e:                          # a no holds the next one back a while
            a.invite("Bob")
        self.assertEqual(e.exception.code, proto.E_RATE)
        self.assertIn("try again in", e.exception.msg)
        self.s.call(lambda: self.s.srv.retry_after.clear())               # (T5L_INVITE_RETRY_SECONDS later)
        r = a.invite("Bob")
        expect(b, "invited")
        a.cancel_invite(r["invite"])
        ev = expect(b, "invite_update")
        self.assertEqual((ev["state"], ev["name"]), ("cancelled", "Alice"))
        self.assertEqual(b.invites, {})
        with self.assertRaises(LobbyError) as e:
            b.answer_invite(r["invite"], True)
        self.assertIn("that invite is over", e.exception.msg)

    def test_no_invite_spam(self):
        # (security review 2) invite, take it back, invite ... put the question (with A as its answer) up on the
        # friend's screen every 2 s; and so did inviting again right after a no
        self.s.stop()
        self.s = server(invite_retry_seconds=1.5)
        a, b = self.friends()
        c = self.acc("Cid")
        self.befriend(a, c)
        drain(a)
        r = a.invite("Bob")
        expect(b, "invited")
        a.cancel_invite(r["invite"])
        expect(b, "invite_update")
        time.sleep(2.1)                                                   # past the 2 s between any two invites
        self.s.call(lambda: self.s.srv.retry_after.update(
            {k: v + 2.0 for k, v in self.s.srv.retry_after.items()}))     # (still held back)
        with self.assertRaises(LobbyError) as e:
            a.invite("Bob")
        self.assertIn("try again in", e.exception.msg)
        a.invite("Cid")                                                   # another friend: fine
        r = expect(c, "invited")
        c.answer_invite(r["invite"], False)
        self.s.call(lambda: self.s.srv.retry_after.pop(("invite", self.s.srv.by_name["alice"].account_id,
                                                        self.s.srv.by_name["bob"].account_id)))
        time.sleep(2.1)
        r = a.invite("Bob")                                               # Bob's hold is over
        expect(b, "invited")
        b.answer_invite(r["invite"], True)
        expect(b, "match_found")

    def test_the_wait_after_a_no_is_the_servers(self):
        # (1.1.3) A no holds the next invite to that friend back (T5L_INVITE_RETRY_SECONDS), and the launcher used to
        # learn it only from the refusal of the next try. The server says how long: `retry` in the invite_update to
        # the inviter, in the friends list and friend_status, and with the refusal. The client keeps that number
        # (invite_wait) for the invite buttons; it guesses none, and the server still refuses what it holds back.
        a, b = self.friends()
        self.assertEqual(a.invite_wait("Bob"), 0)
        r = a.invite("Bob")
        expect(b, "invited")
        b.answer_invite(r["invite"], False)
        ev = expect(a, "invite_update")
        self.assertEqual(ev["state"], "declined")
        self.assertIn(ev["retry"], (29, 30))
        self.assertIn(a.invite_wait("bob"), (29, 30))                       # (any spelling of the name)
        self.assertNotIn("retry", expect(b, "invite_update"))              # Bob's next invite to Alice is not held
        self.assertEqual(b.invite_wait("Alice"), 0)
        self.assertIn([f["retry"] for f in a.friends_list()["friends"]], ([29], [30]))
        self.assertEqual([f["retry"] for f in b.friends_list()["friends"]], [0])
        b.create_room("Bob's dojo")                                       # a presence change: friend_status
        st = expect(a, "friend_status")
        self.assertEqual((st["name"], st["activity"]), ("Bob", "room"))
        self.assertIn(st["retry"], (28, 29, 30))
        b.leave_room()
        time.sleep(2.1)                                                   # (one invite per 2 s)
        with self.assertRaises(LobbyError) as e:                          # the server refuses it, with the seconds
            a.invite("Bob")
        self.assertEqual(e.exception.code, proto.E_RATE)
        self.assertTrue(25 <= e.exception.extra["retry"] <= 28, e.exception.extra)
        self.assertIn("try again in", e.exception.msg)
        a.create_room("Alice's dojo")                                     # a room invite: the same wait
        with self.assertRaises(LobbyError) as e:
            a.invite("Bob", "room")
        self.assertTrue(25 <= e.exception.extra["retry"] <= 28, e.exception.extra)
        self.assertTrue(25 <= a.invite_wait("Bob") <= 28)

    def test_the_wait_counts_down_and_ends(self):
        self.s.stop()
        self.s = server(invite_retry_seconds=1.5)
        a, b = self.friends()
        r = a.invite("Bob")
        expect(b, "invited")
        a.cancel_invite(r["invite"])                                      # taking it back holds the next one too
        ev = expect(a, "invite_update")
        self.assertEqual((ev["state"], ev["retry"]), ("cancelled", 2))
        self.assertEqual(a.invite_wait("Bob"), 2)
        time.sleep(2.1)
        self.assertEqual(a.invite_wait("Bob"), 0)
        r = a.invite("Bob")                                               # over on both sides at the same time
        expect(b, "invited")
        b.answer_invite(r["invite"], True)
        ev = expect(a, "invite_update")
        self.assertEqual((ev["state"], ev["retry"]), ("accepted", 0))    # a yes holds nothing back
        self.assertEqual(a.invite_wait("Bob"), 0)

    def test_a_retry_the_client_cannot_use(self):
        a, _b = self.friends()
        for bad in (None, "30", True, -1, float("nan"), [30]):
            a._note_invite_wait("Bob", bad)
            self.assertEqual(a.invite_wait("Bob"), 0, bad)
        a._note_invite_wait("Bob", 10 ** 9)                              # a day at most (a button, not a ban)
        self.assertEqual(a.invite_wait("Bob"), 86400)
        a._note_invite_wait("Bob", 0)                                     # the server says: now
        self.assertEqual(a.invite_wait("Bob"), 0)

    def test_a_ranked_room_invite_keeps_the_ready_check(self):
        # (security review 2) a room invite starts the room's match at once -- in a ranked room that was a rated
        # match (with ranked sets: a best of 3, lost by leaving it) the invited friend never saw called ranked: the
        # invite names the room only, by its owner's free text. A ranked room's match keeps its ready check.
        a, b = self.friends()
        room = a.create_room("just for fun", ranked=True)
        r = a.invite("Bob", "room")
        ev = expect(b, "invited")
        self.assertTrue(ev["room"]["ranked"])
        got = b.answer_invite(r["invite"], True)
        self.assertEqual(got["room"]["id"], room["id"])
        fa, fb = expect(a, "match_found"), expect(b, "match_found")
        for f in (fa, fb):
            self.assertEqual((f["origin"], f["ready_check"], f["ranked"]), ("room", True, True))
        b.ready(False, fb["match"])                                       # Bob says no: nothing is played
        self.assertEqual(expect(b, "match_cancel")["reason"], "declined")

    def test_an_invite_runs_out(self):
        self.s.stop()
        self.s = server(invite_seconds=0.6)
        a, b = self.friends()
        a.invite("Bob")
        expect(b, "invited")
        self.assertEqual(expect(b, "invite_update")["state"], "expired")
        self.assertEqual(expect(a, "invite_update")["state"], "expired")

    def test_who_can_be_invited(self):
        a, b = self.friends()
        c = self.acc("Cid")
        with self.assertRaises(LobbyError) as e:
            a.invite("Cid")                                               # not a friend
        self.assertIn("that friend is not online", e.exception.msg)
        a.invite("Bob")
        with self.assertRaises(LobbyError) as e:
            a.invite("Bob")
        self.assertIn("one invite at a time", e.exception.msg)
        self.befriend(c, b)
        b.create_room("busy")
        time.sleep(2.1)
        with self.assertRaises(LobbyError) as e:
            c.invite("Bob")
        self.assertIn("that friend is busy right now", e.exception.msg)
        b.close()
        self.clients.remove(b)
        time.sleep(2.1)
        with self.assertRaises(LobbyError) as e:
            c.invite("Bob")
        self.assertIn("that friend is not online", e.exception.msg)
        ev = expect(a, "invite_update")                                   # Bob left: Alice's invite ended
        self.assertEqual(ev["state"], "cancelled")

    def test_a_stale_invite_ends_as_cancelled(self):
        a, b = self.friends()
        r = a.invite("Bob")
        expect(b, "invited")
        a.create_room("elsewhere")                                # Alice is busy now
        with self.assertRaises(LobbyError) as e:
            b.answer_invite(r["invite"], True)
        self.assertIn("the invite is no longer possible", e.exception.msg)
        ev = expect(a, "invite_update")
        self.assertEqual((ev["invite"], ev["state"]), (r["invite"], "cancelled"))   # not "accepted"
        self.assertEqual(self.s.call(lambda: self.s.srv.counters["invites_accepted"]), 0)

    def test_a_queue_match_ends_the_invite(self):
        a, b = self.friends()
        c = self.acc("Cid", auto_ready=True)
        r = a.invite("Bob")
        expect(b, "invited")
        b.auto_ready = True
        b.quick_match()
        c.quick_match()
        ev = expect(a, "invite_update", 15)
        self.assertEqual((ev["invite"], ev["state"]), (r["invite"], "cancelled"))


# ============================================================================== the database
class MigrationTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)

    def old_db(self, version=0):
        """A database as 1.1.1 left it: every table of the old schema, an account, a block, no version."""
        p = os.path.join(self.dir, "lobby.db")
        st = Store(p)
        st.close()
        conn = sqlite3.connect(p)
        conn.executescript("DROP TABLE friends; DROP TABLE friend_requests;")
        conn.execute(f"PRAGMA user_version = {version}")
        conn.execute("INSERT INTO accounts (name, pw, created, rating, rd, vol) VALUES ('Old', 'x', 1, 1500, 350, 0.06)")
        conn.execute("INSERT INTO accounts (name, pw, created, rating, rd, vol) VALUES ('Pal', 'x', 1, 1500, 350, 0.06)")
        conn.execute("INSERT INTO blocks (account_id, blocked_id, blocked_name, created) VALUES (1, 2, 'Pal', 1)")
        conn.commit()
        conn.close()
        return p

    def tables(self, st):
        return {r[0] for r in st.db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}

    def test_a_new_database_has_the_newest_schema(self):
        st = Store(":memory:")
        self.assertEqual(st.schema_version(), store_mod.SCHEMA_VERSION)
        self.assertTrue({"friends", "friend_requests"} <= self.tables(st))
        st.close()

    def test_an_old_database_is_upgraded_once(self):
        p = self.old_db()
        st = Store(p)
        self.assertEqual(st.migrated, [1])
        self.assertEqual(st.schema_version(), 1)
        self.assertTrue({"friends", "friend_requests"} <= self.tables(st))
        self.assertIsNotNone(st.account("Old"))                       # the data stays
        self.assertTrue(st.is_blocked_by(1, 2))
        self.assertTrue(st.add_friendship(1, 2))
        st.close()
        st = Store(p)
        self.assertEqual(st.migrated, [])                             # nothing to do the second time
        self.assertTrue(st.are_friends(2, 1))
        st.close()

    def test_the_oldest_schema_too(self):
        p = os.path.join(self.dir, "first.db")
        conn = sqlite3.connect(p)
        conn.executescript(SCHEMA)                                    # (the first release's tables, no columns added)
        conn.close()
        st = Store(p)
        self.assertEqual(st.schema_version(), 1)
        self.assertEqual(st.friend_count(1), 0)
        st.close()

    def test_a_failed_step_changes_nothing(self):
        st = Store(os.path.join(self.dir, "x.db"))
        bad = store_mod.MIGRATIONS + [(2, "broken", "CREATE TABLE half (a); INSERT INTO nowhere VALUES (1);")]
        with self.assertLogs("t5lobby.store", "ERROR"):
            with self.assertRaises(sqlite3.Error):
                st._migrate(bad)
        self.assertEqual(st.schema_version(), 1)
        self.assertNotIn("half", self.tables(st))
        self.assertFalse(st.db.in_transaction)
        st.close()

    def test_a_newer_database_is_used_as_it_is(self):
        p = self.old_db(version=7)
        with self.assertLogs("t5lobby.store", "WARNING") as cm:
            st = Store(p)
        self.assertIn("newer than this server", "\n".join(cm.output))
        self.assertEqual(st.schema_version(), 7)
        self.assertIsNotNone(st.account("Old"))
        st.close()

    def test_deleting_an_account_takes_its_friends(self):
        st = Store(":memory:")
        for n in ("Ann", "Ben", "Cat"):
            st.create_account(n, "x")
        ids = {n: st.account(n)["id"] for n in ("Ann", "Ben", "Cat")}
        st.add_friendship(ids["Ann"], ids["Ben"])
        st.add_friend_request(ids["Ann"], ids["Cat"])
        st.delete_account("Ann")
        self.assertEqual(st.friend_count(ids["Ben"]), 0)
        self.assertEqual(st._x("SELECT COUNT(*) FROM friend_requests").fetchone()[0], 0)
        self.assertEqual(st.stats()["friendships"], 0)
        st.close()

    def test_the_release_server_opens_an_upgraded_database(self):
        """Going back to the 1.1.0 server after an update (a rollback of the VPS) must still work."""
        oldc, olds, oldstore = _old_tree(self, "v1.1.0")
        p = self.old_db()
        Store(p).close()                                              # upgraded
        st = oldstore.Store(p)
        self.assertIsNotNone(st.account("Old"))
        st.close()
        self.assertEqual(Store(p).schema_version(), 1)


# ============================================================================== older launchers and servers
_OLD = {}
_TMP = []


def _old_tree(test, ref):
    """(client, server, store) modules of the git revision `ref`, imported once per process under another name."""
    if ref in _OLD:
        return _OLD[ref]
    git = shutil.which("git")
    if not git:
        test.skipTest("no git")
    r = subprocess.run([git, "-C", os.path.dirname(LOBBY), "archive", "--format=tar", ref, "lobby/t5lobby"], capture_output=True,
                       timeout=60)
    if r.returncode != 0:
        test.skipTest(f"no {ref} in this checkout")
    tmp = tempfile.mkdtemp(prefix="t5friends-old-")
    _TMP.append(tmp)
    tarfile.open(fileobj=io.BytesIO(r.stdout)).extractall(tmp, filter="data")
    import importlib
    import sys
    sys.path.insert(0, os.path.join(LOBBY, "tools"))
    import natsim
    name = "t5lobby_friendsold_" + "".join(ch for ch in ref if ch.isalnum())
    natsim.load_pkg(name, os.path.join(tmp, "lobby", "t5lobby"))
    _OLD[ref] = (importlib.import_module(name + ".client"), importlib.import_module(name + ".server"),
                 importlib.import_module(name + ".server.store"))
    return _OLD[ref]


def tearDownModule():
    for d in _TMP:
        shutil.rmtree(d, ignore_errors=True)


# The releases a new server must keep working with: 1.1.0 (tag) and 1.1.1 (main before friends; no tag yet).
OLD_REFS = [r for r in os.environ.get("T5L_COMPAT_REFS", "v1.1.0,a21c3ab").split(",") if r]


class OldClientTest(Base):
    def check_old(self, make):
        """An older launcher (account with friends and requests, invites going on around it): no message it does not
        know, and its quick match still works."""
        a, b = self.acc("Alice"), self.acc("Bob")
        self.befriend(a, b)
        old = make()
        self.clients.append(old)
        a.add_friend(old.me["name"])
        b.add_friend(old.me["name"])
        old2 = self.s.call(lambda: self.s.srv.by_name["old"].account_id)
        aid = self.s.call(lambda: self.s.srv.by_name["alice"].account_id)
        self.s.call(lambda: self.s.srv.store.add_friendship(old2, aid))    # (as if it had accepted with 1.1.2)
        self.s.call(lambda: self.s.srv.by_name["old"].friends.add(aid))
        self.s.call(lambda: self.s.srv.by_name["alice"].friends.add(old2))
        b.quick_match()
        a.invite("Bob")
        expect(b, "invited")
        time.sleep(1.0)                                                   # presence changes go out with the lobby
        evs = []
        while True:
            ev = old.next_event(0.1)
            if ev is None:
                break
            evs.append(ev)
        self.assertEqual([ev["t"] for ev in evs if ev["t"] in FRIEND_EVENTS], [])
        self.assertTrue(evs)                                              # (it did get its lobby lists)
        self.assertEqual([f["invite"] for f in a.friends_list()["friends"] if f["name"] == "Old"], ["update"])
        with self.assertRaises(LobbyError):
            a.invite("Old")
        # the old launcher still plays
        c = self.acc("Cid", auto_ready=True)
        old.auto_ready = True
        b.cancel_queue()
        old.quick_match()
        c.quick_match()
        expect(old, "match_start", 20)
        expect(c, "match_start", 20)

    def test_a_client_without_the_cap(self):
        self.check_old(lambda: client(self.s, "Old", password="old-pw1", register=True, friends=False))

    def test_release_clients_from_git(self):
        for ref in OLD_REFS:
            with self.subTest(ref=ref):
                oldc, _s, _st = _old_tree(self, ref)

                def make(oldc=oldc):
                    c = oldc.LobbyClient(self.s.addr, BUILD, relay_bridge=False) if "relay_bridge" in \
                        oldc.LobbyClient.__init__.__code__.co_varnames else oldc.LobbyClient(self.s.addr, BUILD)
                    c.connect()
                    c.register("Old", "old-pw1")
                    self.assertNotIn("friends", c.welcome.get("caps", []))
                    return c
                self.check_old(make)
                for c in self.clients:
                    c.close()
                self.clients = []
                self.s.stop()
                self.s = server()


class OldServerTest(unittest.TestCase):
    def test_new_clients_on_a_release_server(self):
        _oldc, olds, _st = _old_tree(self, "v1.1.0")
        loop = proto.new_event_loop()
        srv = olds.LobbyServer(olds.Config(**util.FAST))
        ready = threading.Event()

        def run():
            asyncio.set_event_loop(loop)
            loop.run_until_complete(srv.start())
            ready.set()
            loop.run_forever()
        th = threading.Thread(target=run, daemon=True)
        th.start()
        clients = []
        try:
            self.assertTrue(ready.wait(10))
            for name in ("Alice", "Bob"):
                c = LobbyClient(f"127.0.0.1:{srv.port}", BUILD, auto_ready=True, relay_bridge=False)
                c.connect()
                c.register(name, name.lower() + "-pw1")
                clients.append(c)
                self.assertFalse(c.has_friends())                     # the launcher hides its friends page
                self.assertNotIn("friends", c.welcome.get("caps", []))
            with self.assertRaises(LobbyError) as e:                  # (asked anyway: refused, nothing breaks)
                clients[0].add_friend("Bob")
            self.assertEqual(e.exception.code, proto.E_BAD_REQUEST)
            for c in clients:
                c.quick_match()
            for c in clients:
                expect(c, "match_start", 30)
        finally:
            for c in clients:
                c.close()
            asyncio.run_coroutine_threadsafe(srv.stop(), loop).result(10)
            loop.call_soon_threadsafe(loop.stop)
            th.join(10)
            loop.close()

    def test_the_invite_wait_on_a_1_1_2_server(self):
        # A 1.1.2 server sends no `retry`: nothing to count down after a no, the invite buttons stay as they were;
        # its refusal of the next invite says the seconds in its text, and the 1.1.3 client takes them from there.
        _oldc, olds, _st = _old_tree(self, os.environ.get("T5L_COMPAT_SERVER_112", "df72a78"))
        loop = proto.new_event_loop()
        srv = olds.LobbyServer(olds.Config(**util.FAST))
        ready = threading.Event()

        def run():
            asyncio.set_event_loop(loop)
            loop.run_until_complete(srv.start())
            ready.set()
            loop.run_forever()
        th = threading.Thread(target=run, daemon=True)
        th.start()
        clients = []
        try:
            self.assertTrue(ready.wait(10))
            for name in ("Alice", "Bob"):
                c = LobbyClient(f"127.0.0.1:{srv.port}", BUILD, relay_bridge=False)
                c.connect()
                c.register(name, name.lower() + "-pw1")
                clients.append(c)
            a, b = clients
            self.assertTrue(a.has_friends())
            a.add_friend("Bob")
            expect(b, "friend_request")
            b.answer_friend("Alice", True)
            wait_list(a, lambda fl: names(fl["friends"]) == ["Bob"])
            r = a.invite("Bob")
            expect(b, "invited")
            b.answer_invite(r["invite"], False)
            ev = expect(a, "invite_update")
            self.assertNotIn("retry", ev)
            self.assertEqual(a.invite_wait("Bob"), 0)                     # nothing guessed
            time.sleep(2.1)
            with self.assertRaises(LobbyError) as e:
                a.invite("Bob")
            self.assertIn("try again in", e.exception.msg)
            self.assertTrue(25 <= e.exception.extra["retry"] <= 28, e.exception.extra)
            self.assertTrue(25 <= a.invite_wait("Bob") <= 28)
        finally:
            for c in clients:
                c.close()
            asyncio.run_coroutine_threadsafe(srv.stop(), loop).result(10)
            loop.call_soon_threadsafe(loop.stop)
            th.join(10)
            loop.close()


if __name__ == "__main__":
    unittest.main()
