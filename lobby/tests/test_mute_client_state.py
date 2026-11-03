"""Personal mute state without sockets, a Tk root, server or game."""
import asyncio
import unittest
from unittest.mock import AsyncMock, Mock

import util  # noqa: F401 -- import path only; no server is started
from t5lobby.buildid import BuildInfo
from t5lobby.client import LobbyClient
from t5lobby.private_chat import Conversations
from t5lobby.proto import LobbyError


class MuteClientStateTest(unittest.TestCase):
    def client(self, guest=False, names=()):
        c = LobbyClient("127.0.0.1:7781", BuildInfo("test", "test", "test"), guest_mutes=names)
        c.me = {"id": "me", "name": "Tester", "guest": guest}
        return c

    def supported(self, c):
        c.welcome = {"caps": ["mutes"], "features": ["mutes"]}

    def test_negotiated_account_mutes_use_server_rows(self):
        c = self.client()
        c._call = Mock()
        with self.assertRaises(LobbyError):
            c.mute("Rival")
        c._call.assert_not_called()
        c.welcome = {"caps": ["mutes"], "features": []}
        self.assertFalse(c.mutes_ok())
        self.supported(c)
        row = {"name": "Rival", "guest": False, "since": 7}
        c._call.return_value = {"t": "muted", "name": "Rival", "muted": True, "rows": [row]}
        c.mute("Rival")
        c._call.assert_called_once_with({"t": "mute", "name": "Rival", "muted": True})
        self.assertTrue(c.is_muted("RIVAL"))
        self.assertEqual(c.mute_rows, [row])
        c._call.return_value = {"t": "muted", "name": "Rival", "muted": False, "rows": []}
        c.unmute("Rival")
        self.assertFalse(c.is_muted("Rival"))

    def test_guest_local_mutes_work_on_older_servers_and_emit_for_persistence(self):
        c = self.client(guest=True, names=["Rival"])
        asyncio.run(c._mutes_after_login({}))
        self.assertTrue(c.is_muted("Rival"))
        c._call = Mock()
        c.mute("Other")
        c._call.assert_not_called()
        self.assertEqual(c._guest_mutes, ["Rival", "Other"])
        self.assertEqual(c.events.get_nowait()["t"], "mutes")
        c.unmute("rival")
        self.assertEqual(c._guest_mutes, ["Other"])

    def test_replay_failure_and_partial_replies_cannot_erase_guest_choices(self):
        c = self.client(guest=True, names=["Rival", "Other"])
        self.supported(c)
        c._request = AsyncMock(side_effect=LobbyError("rate_limited", "slow down"))
        async def replay():
            await c._mutes_after_login({"mutes": []})
            await c._mute_replay_task
        asyncio.run(replay())
        c._request.assert_awaited_once_with({"t": "mute", "name": "Rival", "muted": True})
        self.assertEqual(c._guest_mutes, ["Rival", "Other"])
        c._call = Mock(return_value={"rows": [{"name": "Third"}]})
        c.mute("Third")
        self.assertEqual(c._guest_mutes, ["Rival", "Other", "Third"])
        c._call.side_effect = LobbyError("rate_limited", "slow down")
        with self.assertRaises(LobbyError):
            c.unmute("Other")
        self.assertEqual(c._guest_mutes, ["Rival", "Other", "Third"])
        c._call.side_effect = None
        c.unmute("Other")
        self.assertEqual(c._guest_mutes, ["Rival", "Third"])
        asyncio.run(c._on_mutes({"t": "mutes", "rows": []}))
        self.assertEqual(c._guest_mutes, ["Rival", "Third"])

    def test_account_login_replaces_previous_user_state(self):
        c = self.client(names=["GuestOnly"])
        c._set_mute_rows([{"name": "Previous"}])
        asyncio.run(c._mutes_after_login({"mutes": [{"name": "Rival", "guest": False}]}))
        self.assertFalse(c.is_muted("Previous"))
        self.assertFalse(c.is_muted("GuestOnly"))
        self.assertTrue(c.is_muted("Rival"))

    def test_muted_envelopes_never_reach_chat_unread_mentions_or_invite_state(self):
        async def run():
            c = self.client(guest=True)
            c._set_mute_rows([{"name": "Rival"}], emit=False)
            for kind in ("chat", "room_chat", "private_message", "invited", "challenged"):
                await c._dispatch({"t": kind, "from": {"name": "Rival"}, "text": "@Tester",
                                   "mentions": ["me"], "invite": "invite1"})
            self.assertTrue(c.events.empty())
            self.assertEqual(c.invites, {})
            await c._dispatch({"t": "chat", "from": {"name": "Friendly"}, "text": "hello"})
            self.assertEqual(c.events.get_nowait()["text"], "hello")
        asyncio.run(run())

    def test_muting_removes_already_pending_invites(self):
        c = self.client(guest=True)
        c.invites["old"] = {"t": "invited", "from": {"name": "Rival"}}
        c.mute("Rival")
        self.assertEqual(c.invites, {})

    def test_private_mute_alias_uses_the_shared_list_when_supported(self):
        c = self.client()
        self.supported(c)
        c.mute = Mock(return_value={"muted": True})
        self.assertEqual(c.private_mute("Rival"), {"muted": True})
        c.mute.assert_called_once_with("Rival", True)

    def test_admin_mute_deadline_survives_the_request_error(self):
        async def run(until):
            c = self.client()
            future = asyncio.get_running_loop().create_future()
            c._pending[7] = future
            await c._dispatch({"t": "error", "re": 7, "code": "not_allowed",
                               "msg": "Chat is muted for this account.", "muted_until": until})
            return future.exception()
        error = asyncio.run(run(1800000000.0))
        self.assertEqual(error.extra["muted_until"], 1800000000.0)
        for invalid in (True, "1800000000", float("nan"), float("inf"), -1):
            self.assertNotIn("muted_until", asyncio.run(run(invalid)).extra)

    def test_guest_mute_list_is_bounded_without_silently_losing_entries(self):
        c = self.client(guest=True)
        c._set_mute_rows([{"name": "Rival" + str(i)} for i in range(200)], emit=False)
        with self.assertRaises(LobbyError):
            c.mute("NewRival")
        self.assertEqual(len(c.mute_rows), 200)
        self.assertFalse(c.is_muted("NewRival"))

    def test_login_exposes_only_active_valid_admin_mute_deadline(self):
        c = self.client()
        until = 32503680000.0
        asyncio.run(c._mutes_after_login({"chat_moderation": {"muted_until": until}}))
        self.assertEqual(c.chat_moderation, {"muted_until": until})
        self.assertEqual(c.events.get_nowait(), {"t": "chat_moderation", "muted_until": until})
        for invalid in (None, True, "32503680000", float("nan"), float("inf"), 1):
            asyncio.run(c._mutes_after_login({"chat_moderation": {"muted_until": invalid}}))
            self.assertEqual(c.chat_moderation, {})

    def test_muting_private_conversation_clears_old_unread_marker(self):
        model = Conversations()
        row = model.open("Rival")
        row["unread"] = 4
        model.set_muted("Rival", True)
        self.assertEqual(model.unread, 0)
        model.set_muted("Rival", False)
        self.assertEqual(model.unread, 0)


if __name__ == "__main__":
    unittest.main()
