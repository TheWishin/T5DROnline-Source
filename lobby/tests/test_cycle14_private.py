"""Delayed private sends preserve newer drafts; no Tk, transport or game."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import util  # noqa: F401 -- package path only; no server helper is invoked
from t5lobby.tk_private_chat import PrivateChat


class Draft:
    def __init__(self, text):
        self.text = text

    def get(self):
        return self.text

    def set(self, text):
        self.text = text


class PrivateSendDraftTest(unittest.TestCase):
    def controller(self):
        client = SimpleNamespace(me={"name": "Tester"}, private_chat_ok=lambda: True,
                                 private_message=Mock())
        tab = SimpleNamespace(client=client, call=Mock())
        ui = PrivateChat(tab)
        ui.name, ui.text = "Rival", Draft("hello")
        ui.draw = Mock()
        ui.send()
        tab.call.assert_called_once_with(client.private_message, "Rival", "hello",
                                         then=tab.call.call_args.kwargs["then"])
        return ui, tab.call.call_args.kwargs["then"]

    def acknowledge(self, done):
        done({"message": {"t": "private_message", "id": "accepted",
                          "from": {"name": "Tester"}, "to": {"name": "Rival"},
                          "text": "hello"}})

    def assert_recorded(self, ui):
        self.assertEqual([line["id"] for line in ui.model.rows["rival"]["lines"]], ["accepted"])
        ui.draw.assert_called_once_with()

    def test_current_unchanged_draft_is_cleared_after_acceptance(self):
        ui, done = self.controller()
        self.assertEqual(ui.model.rows, {})
        self.acknowledge(done)
        self.assertEqual(ui.text.get(), "")
        self.assert_recorded(ui)

    def test_edited_draft_is_retained_after_acceptance(self):
        ui, done = self.controller()
        ui.text.set("new draft")
        self.acknowledge(done)
        self.assertEqual(ui.text.get(), "new draft")
        self.assert_recorded(ui)

    def test_other_recipient_identical_draft_is_retained(self):
        ui, done = self.controller()
        ui.name = "Other"
        self.acknowledge(done)
        self.assertEqual(ui.text.get(), "hello")
        self.assert_recorded(ui)

    def test_reopened_window_identical_draft_is_retained(self):
        ui, done = self.controller()
        # build() creates a fresh StringVar when a closed window is reopened.
        ui.text = Draft("hello")
        self.acknowledge(done)
        self.assertEqual(ui.text.get(), "hello")
        self.assert_recorded(ui)


if __name__ == "__main__":
    unittest.main()
