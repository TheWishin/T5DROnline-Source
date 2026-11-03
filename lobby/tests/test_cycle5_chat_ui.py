"""Private moderation retains its selected session and peer; no Tk or transport."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import util  # noqa: F401 -- import path only; no server helper is invoked
from t5lobby.private_chat import Conversations
from t5lobby.tk_private_chat import PrivateChat


class PrivateReportOwnershipTest(unittest.TestCase):
    def controller(self):
        client = SimpleNamespace(me={"name": "Tester"}, private_chat_ok=lambda: True,
                                 private_report=Mock(), block=Mock())
        tab = SimpleNamespace(client=client, call=Mock(), status=Mock(),
                              ask_yes_no=Mock(return_value=True))
        ui = PrivateChat(tab)
        ui.name = "Rival"
        line = {"t": "private_message", "id": "selected", "from": {"name": "Rival"},
                "to": {"name": "Tester"}, "text": "chosen line", "receipt": "receipt", "time": 1}
        ui.model.receive(line, "Tester")
        ui.window, ui.lines = Mock(), Mock()
        ui._drawn_line_ids = ["selected"]
        ui.lines.curselection.return_value = (0,)
        return ui, tab, line

    def test_replaced_or_logged_out_session_cannot_receive_old_selected_lines(self):
        for replacement in (None, SimpleNamespace(private_report=Mock())):
            with self.subTest(replacement=replacement):
                ui, tab, _line = self.controller()

                def confirm(*_args, **_kwargs):
                    tab.client = replacement
                    return True

                tab.ask_yes_no.side_effect = confirm
                ui.report()
                tab.call.assert_not_called()

    def test_reset_transcript_cancels_pending_confirmation_even_with_same_client(self):
        ui, tab, _line = self.controller()

        def confirm(*_args, **_kwargs):
            ui.model = Conversations()
            ui.name = None
            return True

        tab.ask_yes_no.side_effect = confirm
        ui.report()
        tab.call.assert_not_called()

    def test_confirmed_report_keeps_original_peer_and_only_selected_lines(self):
        ui, tab, line = self.controller()
        client = tab.client

        def confirm(*_args, **_kwargs):
            ui.name = "Other"
            return True

        tab.ask_yes_no.side_effect = confirm
        ui.report()
        self.assertEqual(tab.call.call_args.args, (client.private_report, "Rival", [line]))
        tab.call.call_args.kwargs["then"]({})
        tab.status.assert_called_once_with("Report sent to moderators.")

    def test_old_acknowledgment_does_not_report_success_for_replacement_session(self):
        ui, tab, _line = self.controller()
        ui.report()
        done = tab.call.call_args.kwargs["then"]
        tab.client = SimpleNamespace(me={"name": "Other"})
        done({})
        tab.status.assert_not_called()

    def test_block_confirmation_cannot_act_on_replaced_or_logged_out_session(self):
        for replacement in (None, SimpleNamespace(block=Mock())):
            with self.subTest(replacement=replacement):
                ui, tab, _line = self.controller()

                def confirm(*_args, **_kwargs):
                    tab.client = replacement
                    return True

                tab.ask_yes_no.side_effect = confirm
                ui.block()
                tab.call.assert_not_called()

    def test_reset_transcript_cancels_pending_block_confirmation(self):
        ui, tab, _line = self.controller()

        def confirm(*_args, **_kwargs):
            ui.model = Conversations()
            ui.name = None
            return True

        tab.ask_yes_no.side_effect = confirm
        ui.block()
        tab.call.assert_not_called()

    def test_confirmed_block_keeps_original_peer(self):
        ui, tab, _line = self.controller()
        client = tab.client

        def confirm(*_args, **_kwargs):
            ui.name = "Other"
            return True

        tab.ask_yes_no.side_effect = confirm
        ui.block()
        tab.call.assert_called_once_with(client.block, "Rival")


if __name__ == "__main__":
    unittest.main()
