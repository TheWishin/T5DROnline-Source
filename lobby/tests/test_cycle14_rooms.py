"""Room creation acknowledgements retain their submitting session; no Tk or server."""
from types import SimpleNamespace
import unittest

import test_cycle13_rooms as cycle13
from t5lobby import tk_rooms


class RoomCreateStatusOwnershipTest(unittest.TestCase):
    def pending(self):
        return cycle13.RoomAcknowledgementOwnershipTest().pending("create")

    def test_old_session_acknowledgement_cannot_replace_current_status(self):
        for replacement in (None, SimpleNamespace()):
            with self.subTest(client=replacement):
                ui, _window, done = self.pending()
                ui.tab.client = replacement
                done({})
                ui.tab.status.assert_not_called()
                ui.close_window.assert_not_called()

    def test_current_session_still_reports_success_and_closes_its_dialog(self):
        ui, _window, done = self.pending()
        done({})
        ui.tab.status.assert_called_once_with(tk_rooms.t("Room created."))
        ui.close_window.assert_called_once_with()

    def test_same_session_success_keeps_replacement_dialog(self):
        ui, _old, done = self.pending()
        replacement = object()
        ui.window = replacement
        done({})
        ui.tab.status.assert_called_once_with(tk_rooms.t("Room created."))
        ui.close_window.assert_not_called()
        self.assertIs(ui.window, replacement)


if __name__ == "__main__":
    unittest.main()
