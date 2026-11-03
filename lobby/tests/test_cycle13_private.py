"""Evicted private transcripts follow shared unmutes without Tk or transport."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import util  # noqa: F401 -- package path only; no server helper is invoked
from t5lobby.private_chat import MAX_CONVERSATIONS
from t5lobby.tk_private_chat import PrivateChat


class EvictedPrivateMuteTest(unittest.TestCase):
    def controller(self, shared=True):
        muted = {"rival"}
        client = SimpleNamespace(
            me={"name": "Tester", "guest": False}, private_chat_ok=lambda: True,
            mutes_ok=lambda: shared, is_muted=lambda name: name.lower() in muted)
        ui = PrivateChat(SimpleNamespace(client=client))
        ui.model.open("Rival")
        ui.model.set_muted("Rival", True)
        for i in range(MAX_CONVERSATIONS):
            ui.model.open(f"Player{i}")
        self.assertNotIn("rival", ui.model.rows)
        ui.draw = Mock()
        return ui, muted

    def incoming(self):
        return {"t": "private_message", "id": "first-after-unmute",
                "from": {"name": "Rival"}, "to": {"name": "Tester"}, "text": "hello"}

    def test_first_incoming_line_after_evicted_shared_unmute_is_retained(self):
        ui, muted = self.controller()
        muted.clear()
        ui.event(self.incoming())
        row = ui.model.rows["rival"]
        self.assertFalse(row["muted"])
        self.assertEqual([line["id"] for line in row["lines"]], ["first-after-unmute"])
        self.assertEqual(row["unread"], 1)
        ui.draw.assert_called_once_with()

    def test_still_muted_evicted_peer_remains_suppressed(self):
        ui, _muted = self.controller()
        ui.refresh()
        ui.event(self.incoming())
        self.assertIn("rival", ui.model.muted)
        self.assertNotIn("rival", ui.model.rows)
        ui.draw.assert_not_called()

    def test_legacy_private_mute_survives_eviction_and_refresh(self):
        ui, muted = self.controller(shared=False)
        muted.clear()  # Legacy private mutes are independent of the shared list.
        ui.refresh()
        ui.event(self.incoming())
        self.assertIn("rival", ui.model.muted)
        self.assertNotIn("rival", ui.model.rows)
        ui.draw.assert_not_called()


if __name__ == "__main__":
    unittest.main()
