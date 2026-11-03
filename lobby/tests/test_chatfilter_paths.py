"""Chat/name enforcement through real handlers, without binding sockets or starting a server."""
import json
import os
import tempfile
import time
import unittest
from unittest import mock

import util  # noqa: F401 (sets sys.path)
from t5lobby import proto
from t5lobby.server import Config, LobbyServer
from t5lobby.server.lobby import Player
from t5lobby.server.ratelimit import TokenBucket
from t5lobby.server.store import PERMANENT


class Connection:
    """Capture output; no writer, transport, socket, or client involved."""
    def __init__(self):
        self.helloed = True
        self.player = None
        self.closed = False
        self.akey = self.ip = "127.0.0.1"
        self.build_id = "test"
        self.release = ""
        self.caps = frozenset()
        self.errors = 0
        self.messages = []
        self.raw = []
        self.heavy = TokenBucket(100, 100)
        self.state = TokenBucket(100, 100)

    def send(self, message):
        self.messages.append(message)

    def send_raw(self, data):
        self.raw.append(data)


class ChatFilterPathsTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        path = os.path.join(self.tmp.name, "terms.json")
        # Synthetic test token; tests do not depend on the reviewed production list.
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"version": 1, "terms": [{"term": "badword", "languages": ["en"]}]}, f)
        self.server = LobbyServer(Config(db=":memory:", chat_filter_path=path))
        self.sender = self.player("Alice", account=True)
        self.recipient = self.player("Bob")

    async def asyncTearDown(self):
        self.server.store.close()
        self.tmp.cleanup()

    def player(self, name, account=False):
        conn = Connection()
        row = self.server.store.create_account(name, "unused") if account else None
        p = Player(conn, name, not account, row)
        conn.player = p
        self.server.players[p.id] = p
        return conn

    def count(self):
        return self.server.store.chat_moderation(self.sender.player.account_id)["blocked_count"]

    async def send(self, text, **extra):
        msg = dict(extra, t="chat", text=text, rid=17)
        return await self.server._dispatch(self.sender, proto.encode(msg).rstrip(b"\n"))

    async def test_rejection_is_an_old_client_error_to_sender_only(self):
        self.assertTrue(await self.send("badword"))
        self.assertEqual(self.sender.messages, [{"t": "error", "code": proto.E_NOT_ALLOWED,
                                                "msg": "Message blocked: hate terms are not allowed.", "re": 17}])
        self.assertEqual(self.sender.raw, [])
        self.assertEqual(self.recipient.raw, [])
        self.assertEqual(self.recipient.messages, [])
        self.assertEqual(self.count(), 1)
        self.assertEqual(self.server.counters["chat_lines"], 0)

    async def test_unknown_scope_fields_cannot_skip_central_chat_check(self):
        for scope in ({"room": "r1"}, {"to": "Bob"}, {"private": True}):
            with self.subTest(scope=scope):
                await self.send("badword", **scope)
                self.assertEqual(self.sender.messages[-1]["code"], proto.E_NOT_ALLOWED)
        self.assertEqual(self.recipient.raw, [])
        self.assertEqual(self.count(), 3)

    async def test_filter_also_applies_while_in_a_room_or_playing(self):
        for status in ("room", "playing"):
            self.sender.player.status = status
            await self.send("badword")
            self.assertEqual(self.sender.messages[-1]["code"], proto.E_NOT_ALLOWED)
        self.assertEqual(self.recipient.raw, [])

    async def test_innocent_chat_keeps_existing_wire_message(self):
        await self.send("good game")
        sent = proto.decode(self.recipient.raw[0].rstrip(b"\n"))
        self.assertEqual((sent["t"], sent["text"]), ("chat", "good game"))
        self.assertEqual(self.count(), 0)
        self.assertEqual(self.server.counters["chat_lines"], 1)

    async def test_rejections_still_spend_existing_chat_rate_budget(self):
        for _ in range(5):
            await self.send("badword")
        await self.send("badword")
        self.assertEqual(self.sender.messages[-1]["code"], proto.E_RATE)
        self.assertEqual(self.count(), 5)
        self.assertEqual(self.recipient.raw, [])

    async def test_lobby_wide_rate_limit_remains_before_filter(self):
        self.server.chat_total = mock.Mock()
        self.server.chat_total.take.return_value = False
        await self.send("badword")
        self.assertEqual(self.sender.messages[-1]["code"], proto.E_RATE)
        self.assertEqual(self.count(), 0)

    async def test_raw_and_sanitized_chat_are_checked(self):
        # Reject a term even beyond the broadcast limit, and a word exposed by truncation.
        for text in ("hello " + " " * 205 + "badword", "a " * 96 + " " + "badwordX"):
            with self.subTest(text=text):
                await self.send(text)
                self.assertEqual(self.sender.messages[-1]["code"], proto.E_NOT_ALLOWED)
        self.assertEqual(self.count(), 2)
        self.assertEqual(self.recipient.raw, [])

    async def test_admin_mute_takes_effect_without_relogin_and_unmute_restores_chat(self):
        self.server.store.mute_account("Alice", PERMANENT)
        await self.send("good game")
        self.assertEqual(self.sender.messages[-1]["msg"], "Chat is muted for this account.")
        self.assertEqual(self.recipient.raw, [])
        self.server.store.unmute_account("Alice")
        await self.send("good game")
        self.assertEqual(len(self.recipient.raw), 1)
        self.assertEqual(self.count(), 0)

    async def test_expired_mute_does_not_block_chat(self):
        self.server.store.mute_account("Alice", time.time() - 1)
        await self.send("good game")
        self.assertEqual(len(self.recipient.raw), 1)

    async def test_new_guest_and_registration_names_rejected_before_creation(self):
        for mode in ("guest", "register"):
            conn = Connection()
            with mock.patch.object(self.server, "_pw", new_callable=mock.AsyncMock) as pw:
                with self.assertRaises(proto.LobbyError) as caught:
                    await self.server.h_login(conn, {"mode": mode, "name": "Badword", "password": "password"})
                self.assertEqual(caught.exception.msg, "This name is not allowed.")
                pw.assert_not_awaited()
            self.assertIsNone(conn.player)
            self.assertIsNone(self.server.store.account("Badword"))

    async def test_blocked_registration_attempt_spends_registration_rate_budget(self):
        self.server.registrations = mock.Mock()
        self.server.registrations.take.return_value = False
        with self.assertRaises(proto.LobbyError) as caught:
            await self.server.h_login(Connection(), {"mode": "register", "name": "Badword", "password": "password"})
        self.assertEqual(caught.exception.code, proto.E_RATE)

    async def test_registration_rechecks_policy_after_password_hash(self):
        async def updated_policy(*_args):
            with open(self.server.chat_filter.path, "w", encoding="utf-8") as f:
                json.dump({"version": 1, "terms": [{"term": "ordinary", "languages": ["en"]}]}, f)
            return "unused"

        with mock.patch.object(self.server, "_pw", side_effect=updated_policy):
            with self.assertRaises(proto.LobbyError) as caught:
                await self.server.h_login(Connection(), {"mode": "register", "name": "Ordinary", "password": "password"})
        self.assertEqual(caught.exception.msg, "This name is not allowed.")
        self.assertIsNone(self.server.store.account("Ordinary"))

    async def test_existing_account_name_is_left_alone_at_password_login(self):
        self.server.store.create_account("Badword", "unused")
        conn = Connection()
        with mock.patch.object(self.server, "_pw", new_callable=mock.AsyncMock, return_value=True):
            reply = await self.server.h_login(conn, {"mode": "account", "name": "Badword", "password": "password"})
        self.assertEqual(reply["t"], "login_ok")
        self.assertEqual(reply["you"]["name"], "Badword")

    async def test_existing_account_name_is_left_alone_at_session_login(self):
        account = self.server.store.create_account("Badword", "unused")
        token = self.server.store.create_session(account["id"], self.server.cfg.session_days)
        reply = await self.server.h_login(Connection(), {"mode": "session", "session": token})
        self.assertEqual(reply["t"], "login_ok")
        self.assertEqual(reply["you"]["name"], "Badword")

    async def test_existing_name_is_left_alone_at_session_resume(self):
        old = self.player("Badword", account=True)
        p = old.player
        p.conn = None
        self.server.sessions[p.token] = p
        reply = await self.server.h_login(Connection(), {"mode": "resume", "token": p.token})
        self.assertEqual(reply["t"], "login_ok")
        self.assertEqual(reply["you"]["name"], "Badword")

    async def test_disabled_filter_keeps_chat_and_manual_mute_behavior(self):
        self.server.chat_filter.enabled = False
        await self.send("badword")
        self.assertEqual(len(self.recipient.raw), 1)
        self.assertEqual(self.count(), 0)
        self.server.store.mute_account("Alice", PERMANENT)
        await self.send("good game")
        self.assertEqual(self.sender.messages[-1]["msg"], "Chat is muted for this account.")
        self.assertEqual(len(self.recipient.raw), 1)

    async def test_guest_chat_is_filtered_without_creating_an_account_counter(self):
        self.sender = self.recipient
        await self.send("badword")
        self.assertEqual(self.sender.messages[-1]["code"], proto.E_NOT_ALLOWED)
        self.assertEqual(self.server.store.chat_moderation(None)["blocked_count"], 0)


if __name__ == "__main__":
    unittest.main()
