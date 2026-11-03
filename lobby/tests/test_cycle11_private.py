"""Private mute compatibility without Tk windows, servers, or game data."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import util  # noqa: F401 -- package path only; no server helper is invoked
from t5lobby.tk_private_chat import PrivateChat


class PrivateMuteCompatibilityTest(unittest.TestCase):
    def controller(self, shared=False, guest=False):
        client = SimpleNamespace(
            me={"name": "Tester", "guest": guest}, private_chat_ok=lambda: True,
            mutes_ok=lambda: shared, is_muted=Mock(return_value=False),
            mute=Mock(return_value={"muted": True}), private_mute=Mock(return_value={"muted": True}))

        def call(action, *args, then):
            then(action(*args))

        ui = PrivateChat(SimpleNamespace(client=client, call=call))
        ui.name = "Rival"
        ui.model.open("Rival")
        return ui, client

    def test_old_server_account_mute_uses_private_request_and_survives_refresh(self):
        ui, client = self.controller()
        ui.mute()
        client.private_mute.assert_called_once_with("Rival", True)
        client.mute.assert_not_called()
        ui.refresh()
        self.assertTrue(ui.model.rows["rival"]["muted"])
        self.assertTrue(ui.is_muted("Rival"))
        client.is_muted.assert_not_called()

        # A later click must unmute the private preference, rather than mute again.
        client.private_mute.return_value = {"muted": False}
        ui.mute()
        client.private_mute.assert_called_with("Rival", False)
        ui.refresh()
        self.assertFalse(ui.is_muted("Rival"))

    def test_legacy_mute_still_suppresses_incoming_private_lines(self):
        ui, _client = self.controller()
        ui.model.set_muted("Rival", True)
        ui.refresh()
        ui.event({"t": "private_message", "id": "incoming", "from": {"name": "Rival"},
                  "to": {"name": "Tester"}, "text": "hidden"})
        self.assertEqual(ui.model.rows["rival"]["lines"], [])
        self.assertEqual(ui.model.unread, 0)

    def test_modern_accounts_and_legacy_guests_keep_shared_mutes(self):
        for shared, guest in ((True, False), (True, True), (False, True)):
            with self.subTest(shared=shared, guest=guest):
                ui, client = self.controller(shared, guest)
                ui.mute()
                client.mute.assert_called_once_with("Rival", True)
                client.private_mute.assert_not_called()
                client.is_muted.return_value = True
                ui.refresh()
                self.assertTrue(ui.model.rows["rival"]["muted"])
                self.assertTrue(ui.is_muted("Rival"))
                client.is_muted.return_value = False
                ui.refresh()
                self.assertFalse(ui.model.rows["rival"]["muted"])


if __name__ == "__main__":
    unittest.main()
