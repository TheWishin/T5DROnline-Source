"""Personal mute and moderation handlers: fake peers, no sockets or lobby listener."""
import os
import sys
import time
import unittest
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from t5lobby import proto
from t5lobby.proto import LobbyError
from t5lobby.server.config import Config
from t5lobby.server.lobby import CAPS, FEATURES, LobbyServer, Player
from t5lobby.server.ratelimit import KeyedBuckets, TokenBucket
from t5lobby.server.store import Store


class PeerConnection:
    def __init__(self, caps=("mutes", "mentions")):
        self.caps = frozenset(caps)
        self.build_id = "test"
        self.release = "1.2.0"
        self.ip = self.akey = "fake-address"
        self.closed = False
        self.messages = []

    def send(self, message):
        self.messages.append(message)

    def send_raw(self, data):
        self.messages.append(proto.decode(data))


def immediate(coro):
    """These handlers do no I/O; avoid even the socket pair of an asyncio test loop."""
    try:
        coro.send(None)
    except StopIteration as result:
        return result.value
    finally:
        coro.close()
    raise AssertionError("handler unexpectedly waited for I/O")


class PersonalMuteDeliveryTest(unittest.TestCase):
    def setUp(self):
        self.socket_patch = mock.patch("socket.socket", side_effect=AssertionError("no network"))
        self.socket_patch.start()
        self.addCleanup(self.socket_patch.stop)
        self.server = object.__new__(LobbyServer)
        self.server.cfg = Config(db=":memory:")
        self.server.store = Store(":memory:")
        self.addCleanup(self.server.store.close)
        self.server.players, self.server.by_name, self.server.invites = {}, {}, {}
        self.server.challenges = {}
        self.server.chat_rate = KeyedBuckets(rate=0, burst=50)
        self.server.chat_total = TokenBucket(rate=0, burst=100)
        self.server.counters = {"chat_lines": 0}
        self.server.chat_filter = SimpleNamespace(blocked=lambda text: "forbidden" in text.lower())
        self.a = self.player("Alice", account=True)
        self.b = self.player("Bob", account=True)
        self.c = self.player("Cara", account=False)

    def player(self, name, account=False, caps=("mutes", "mentions")):
        row = self.server.store.create_account(name, "unused") if account else None
        conn = PeerConnection(caps)
        player = Player(conn, name, row is None, row)
        conn.player = player
        self.server.players[player.id] = player
        self.server.by_name[name.lower()] = player
        return player

    def mute(self, owner, target=None, **fields):
        if target is not None:
            fields["player"] = target.id
        return immediate(self.server.h_mute(owner.conn, fields))

    def chat(self, player, text):
        return immediate(self.server.h_chat(player.conn, {"text": text}))

    def test_lobby_room_and_mentions_are_suppressed_only_for_the_viewer(self):
        self.mute(self.b, self.a)
        self.a.status = "room"
        self.chat(self.a, "hello @Bob")
        self.assertFalse(self.b.conn.messages)
        self.assertEqual(self.c.conn.messages[0]["text"], "hello @Bob")
        self.assertEqual(self.c.conn.messages[0]["mentions"], [self.b.id])
        self.chat(self.b, "I can still speak")
        self.assertEqual(self.a.conn.messages[-1]["text"], "I can still speak")
        self.assertFalse(self.server._is_blocked(self.a, self.b))
        self.assertFalse(self.a.blocks or self.b.blocks)

    def test_account_and_guest_targets_are_loaded_for_a_fresh_account_session(self):
        self.mute(self.b, self.a)
        self.mute(self.b, self.c)
        replacement = Player(PeerConnection(), "Bob", False, self.server.store.account("Bob"))
        self.server._load_mutes(replacement)
        self.assertTrue(self.server._is_muted(replacement, self.a))
        self.assertTrue(self.server._is_muted(replacement, self.c))
        rows = self.server._mute_rows(replacement)
        self.assertEqual([(r["name"], r["guest"]) for r in rows], [("Alice", False), ("Cara", True)])
        self.assertTrue(all(r["since"] > 0 for r in rows))

    def test_offline_guest_replay_and_unmute_use_the_same_list(self):
        before = self.server.store.writes
        self.mute(self.c, name="Offline Guest")
        self.assertEqual(self.server.store.writes, before)
        result = immediate(self.server.h_mutes(self.c.conn, {}))
        self.assertEqual(result["rows"][0]["name"], "Offline Guest")
        self.mute(self.c, name="Offline Guest", muted=False)
        self.assertEqual(immediate(self.server.h_mutes(self.c.conn, {}))["rows"], [])

    def test_capability_gating_and_legacy_public_chat(self):
        self.assertIn("mutes", CAPS)
        self.assertIn("mutes", FEATURES)
        self.a.conn.caps = frozenset()
        with self.assertRaises(LobbyError):
            self.mute(self.a, self.b)
        self.chat(self.b, "old launcher")
        line = self.a.conn.messages[-1]
        self.assertEqual(line["t"], "chat")
        self.assertNotIn("mentions", line)
        self.assertNotIn("badge", line["from"])

    def test_invalid_self_and_capacity_requests_do_not_mutate_preferences(self):
        with self.assertRaises(LobbyError):
            self.mute(self.a, self.a)
        with self.assertRaises(LobbyError):
            self.mute(self.a, self.b, muted="true")
        self.server.cfg.max_blocks = 1
        self.mute(self.a, self.b)
        with self.assertRaises(LobbyError) as caught:
            self.mute(self.a, self.c)
        self.assertEqual(caught.exception.code, "private_limit")
        self.assertEqual(len(self.a.private_mutes), 1)

    def test_filter_and_live_admin_mute_never_publish_or_skip_rate_cost(self):
        with self.assertRaises(LobbyError):
            self.chat(self.a, "forbidden")
        self.assertEqual(self.server.store.chat_moderation(self.a.account_id)["blocked_count"], 1)
        until = time.time() + 3600
        self.server.store.mute_account("Alice", until)
        tokens = self.server.chat_rate.b[self.a.id].tokens
        self.a.conn.caps = frozenset()  # old or modified launcher still cannot publish
        with self.assertRaises(LobbyError) as caught:
            self.chat(self.a, "ordinary text")
        self.assertEqual(caught.exception.extra["muted_until"], until)
        self.assertLess(self.server.chat_rate.b[self.a.id].tokens, tokens)
        self.assertFalse(self.b.conn.messages or self.c.conn.messages)
        self.server.store.unmute_account("Alice")
        self.chat(self.a, "ordinary text")
        self.assertEqual(len(self.b.conn.messages), 1)

    def test_login_moderation_and_personal_preferences_are_capability_gated(self):
        self.mute(self.a, self.b)
        until = time.time() + 3600
        self.server.store.mute_account("Alice", until)
        fields = self.server._login_chat_fields(self.a.conn, self.a)
        self.assertEqual(fields["chat_moderation"], {"muted_until": until})
        self.assertEqual(fields["mutes"][0]["name"], "Bob")
        self.a.conn.caps = frozenset()
        self.assertEqual(self.server._login_chat_fields(self.a.conn, self.a), {})
        self.server.store.mute_account("Alice", time.time() - 1)
        self.a.conn.caps = frozenset(("mutes",))
        self.assertIsNone(self.server._login_chat_fields(self.a.conn, self.a)["chat_moderation"]["muted_until"])
        self.assertIsNone(self.server._login_chat_fields(self.c.conn, self.c)["chat_moderation"]["muted_until"])

    def test_raw_and_sanitized_content_are_checked(self):
        for text in ("hello " + " " * 210 + "forbidden", "forbid\x00den"):
            with self.assertRaises(LobbyError):
                self.chat(self.a, text)
        self.assertFalse(self.b.conn.messages)

    def test_mute_retracts_existing_invites_and_rejects_new_invites(self):
        pending = SimpleNamespace(src=self.a, dst=self.b)
        self.server.invites["fake"] = pending
        self.server._end_invite = mock.Mock()
        self.server.challenges["pending"] = pending
        self.server._end_challenge = mock.Mock()
        self.mute(self.b, self.a)
        self.server._end_invite.assert_called_once_with(pending, "cancelled")
        self.server._end_challenge.assert_called_once_with(pending, "cancelled")
        self.a.friends.add(self.b.account_id)
        self.b.conn.caps |= {"friends"}
        self.server._refuse_draining = mock.Mock()
        with self.assertRaises(LobbyError) as caught:
            immediate(self.server.h_invite(self.a.conn, {"name": "Bob"}))
        self.assertEqual(caught.exception.msg, "that player is not available")

    def test_saved_mute_silences_direct_challenge_for_old_launchers(self):
        self.mute(self.b, self.a)
        self.server._load_mutes(self.b)  # another login reloads server authority
        self.a.conn.caps = self.b.conn.caps = frozenset()
        self.server._refuse_draining = mock.Mock()
        with self.assertRaises(LobbyError) as caught:
            immediate(self.server.h_challenge(self.a.conn, {"player": self.b.id}))
        self.assertEqual(caught.exception.msg, "that player is not available")
        self.assertFalse(self.b.conn.messages)
        self.assertFalse(self.server.challenges)


if __name__ == "__main__":
    unittest.main()