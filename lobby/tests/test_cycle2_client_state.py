"""Guest unmute/replay ordering without a server, sockets or game."""
import asyncio
import unittest
from unittest.mock import AsyncMock, Mock

import util  # noqa: F401 -- import path only
from t5lobby.buildid import BuildInfo
from t5lobby.client import LobbyClient
from t5lobby.proto import LobbyError


class GuestUnmuteReplayOrderingTest(unittest.TestCase):
    def client(self):
        client = LobbyClient("127.0.0.1:7781", BuildInfo("test", "test", "test"), nat2=False)
        client.me = {"name": "Tester", "guest": True}
        client.welcome = {"caps": ["mutes"], "features": ["mutes"]}
        client._set_mute_rows(["Rival", "Other"], emit=False)
        client._mute_replay_generation = object()
        client._request = AsyncMock(return_value={"t": "muted"})
        return client

    def replay(self, client, names):
        asyncio.run(client._replay_guest_mutes(names, client._mute_replay_generation))

    def test_unmute_skips_stale_replay_until_local_update_finishes(self):
        client = self.client()
        client._call = Mock(side_effect=lambda _message: self.replay(client, ["Rival", "Other"]))
        set_rows = client._set_mute_rows

        def update(rows, emit=True):
            # The server has replied, but the local row still says muted here.
            self.replay(client, ["Rival"])
            set_rows(rows, emit=emit)

        client._set_mute_rows = Mock(side_effect=update)
        reply = client.unmute("rival")
        client._call.assert_called_once_with({"t": "mute", "name": "rival", "muted": False})
        client._request.assert_awaited_once_with({"t": "mute", "name": "Other", "muted": True})
        self.assertFalse(reply["muted"])
        self.assertFalse(client.is_muted("Rival"))
        self.assertTrue(client.is_muted("Other"))

    def test_failed_unmute_keeps_row_and_allows_later_replay(self):
        client = self.client()

        def fail(_message):
            self.replay(client, ["Rival"])
            raise LobbyError("rate_limited", "slow down")

        client._call = Mock(side_effect=fail)
        with self.assertRaises(LobbyError):
            client.unmute("rival")
        self.assertTrue(client.is_muted("Rival"))
        client._request.assert_not_awaited()
        self.replay(client, ["Rival"])
        client._request.assert_awaited_once_with({"t": "mute", "name": "Rival", "muted": True})

    def test_overlapping_unmute_failure_does_not_clear_another_calls_guard(self):
        client = self.client()

        def request(_message):
            if client._call.call_count == 1:
                with self.assertRaises(LobbyError):
                    client.unmute("RIVAL")
                self.replay(client, ["Rival"])
                return {"t": "muted"}
            raise LobbyError("rate_limited", "slow down")

        client._call = Mock(side_effect=request)
        client.unmute("rival")
        client._request.assert_not_awaited()
        self.assertFalse(client.is_muted("Rival"))


if __name__ == "__main__":
    unittest.main()
