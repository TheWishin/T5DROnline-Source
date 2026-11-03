"""Account mute refresh/action ordering without sockets, a server or a game."""
import threading
import unittest
from unittest.mock import Mock

import util  # noqa: F401 -- import path only
from t5lobby.buildid import BuildInfo
from t5lobby.client import LobbyClient


class AccountMuteRefreshOrderingTest(unittest.TestCase):
    def test_pending_list_refresh_cannot_erase_a_later_mute(self):
        client = LobbyClient("127.0.0.1:7781", BuildInfo("test", "test", "test"), nat2=False)
        client.me = {"name": "Tester", "guest": False}
        client.welcome = {"caps": ["mutes"], "features": ["mutes"]}
        client._set_mute_rows([{"name": "Rival"}], emit=False)
        refresh_requested = threading.Event()
        release_refresh = threading.Event()
        action_started = threading.Event()
        action_requested = threading.Event()
        errors = []

        def request(message):
            if message["t"] == "mutes":
                refresh_requested.set()
                if not release_refresh.wait(3):
                    raise AssertionError("list refresh was not released")
                return {"t": "mutes", "rows": [{"name": "Rival"}]}
            action_requested.set()
            return {"t": "muted", "rows": [{"name": "Rival"}, {"name": "Other"}]}

        client._call = Mock(side_effect=request)

        def refresh():
            try:
                client.mutes()
            except BaseException as error:
                errors.append(error)

        def mute():
            action_started.set()
            try:
                client.mute("Other")
            except BaseException as error:
                errors.append(error)

        reader = threading.Thread(target=refresh, daemon=True)
        writer = threading.Thread(target=mute, daemon=True)
        reader.start()
        try:
            self.assertTrue(refresh_requested.wait(3))
            writer.start()
            self.assertTrue(action_started.wait(3))
            self.assertFalse(action_requested.wait(0.1))
        finally:
            release_refresh.set()
            reader.join(3)
            if writer.ident is not None:
                writer.join(3)
        self.assertFalse(reader.is_alive())
        self.assertFalse(writer.is_alive())
        self.assertEqual(errors, [])
        self.assertTrue(action_requested.is_set())
        self.assertTrue(client.is_muted("Rival"))
        self.assertTrue(client.is_muted("Other"))


if __name__ == "__main__":
    unittest.main()
