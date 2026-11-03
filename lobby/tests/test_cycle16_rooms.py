"""Table pair controls retain their opening room and session; no Tk or server."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import test_cycle13_rooms as cycle13


class RoomPairSubmissionOwnershipTest(unittest.TestCase):
    def pending(self):
        ui, window, _done = cycle13.RoomAcknowledgementOwnershipTest().pending("pair")
        ui.tab.call.reset_mock()
        return ui, window

    def test_old_room_controls_cannot_pair_players_in_another_room(self):
        for room in (None, {"id": "different"}):
            with self.subTest(room=room):
                ui, window = self.pending()
                ui.tab.client.my_room = room
                window.pair_button.command()
                ui.tab.call.assert_not_called()

    def test_old_session_controls_cannot_pair_players_after_reconnect(self):
        for disconnected in (False, True):
            with self.subTest(disconnected=disconnected):
                ui, window = self.pending()
                ui.tab.client = None if disconnected else SimpleNamespace(
                    my_room={"id": "room"}, room_pair=Mock())
                window.pair_button.command()
                ui.tab.call.assert_not_called()

    def test_current_room_controls_still_pair_selected_players(self):
        ui, window = self.pending()
        window.pair_button.command()
        self.assertEqual(ui.tab.call.call_args.args,
                         (ui.tab.client.room_pair, 1, ["one", "two"]))


if __name__ == "__main__":
    unittest.main()
