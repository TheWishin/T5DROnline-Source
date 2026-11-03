"""Private-window callback ownership, using fake widgets only; no Tk root or sockets."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import util  # noqa: F401 -- imports the repository's lobby package
from t5lobby.tk_private_chat import PrivateChat
from t5lobby import tk_rooms


class FocusWindow:
    def __init__(self):
        self.pending = {}
        self.destroyed = False

    def after_idle(self, callback):
        ident = f"idle#{len(self.pending)}"
        self.pending[ident] = callback
        return ident

    def after_cancel(self, ident):
        del self.pending[ident]

    def destroy(self):
        # Tk destroys registered commands without cancelling after scripts.
        self.destroyed = True


class PrivateWindowLifetimeTest(unittest.TestCase):
    def ui(self):
        ui = PrivateChat(SimpleNamespace(client=None))
        ui.window = FocusWindow()
        return ui

    def test_close_cancels_pending_focus_idle_before_destroy(self):
        ui = self.ui()
        window = ui.window
        ui._queue_mark_read(window)
        self.assertEqual(len(window.pending), 1)
        ui.close()
        self.assertEqual(window.pending, {})
        self.assertTrue(window.destroyed)
        self.assertIsNone(ui._focus_after)

    def test_repeated_focus_events_share_one_idle(self):
        ui = self.ui()
        ui._queue_mark_read(ui.window)
        ui._queue_mark_read(ui.window)
        self.assertEqual(len(ui.window.pending), 1)
        callback, = ui.window.pending.values()
        with patch.object(ui, "mark_read") as mark:
            callback()
            mark.assert_called_once_with()
        self.assertIsNone(ui._focus_after)

    def test_old_window_idle_cannot_mark_reopened_window_read(self):
        ui = self.ui()
        old = ui.window
        ui._queue_mark_read(old)
        callback, = old.pending.values()
        ui.close()
        ui.window = FocusWindow()
        ui._queue_mark_read(ui.window)
        current = ui._focus_after
        with patch.object(ui, "mark_read") as mark:
            callback()  # even an already-dispatched stale callback has no ownership
            mark.assert_not_called()
        self.assertEqual(ui._focus_after, current)


class RoomWindowLifetimeTest(unittest.TestCase):
    def test_native_close_clears_room_window_before_next_table_poll(self):
        window = Mock()
        view = SimpleNamespace(card=Mock(return_value=Mock()), px=lambda value: value)
        tab = SimpleNamespace(parent=Mock(), view=view, client=None, new_window=Mock(return_value=window))
        ui = tk_rooms.RoomsUI(tab)
        with patch.object(tk_rooms.ttk, "Label"):
            ui.window, _card = tk_rooms._window(ui, "Room tables")
        window.protocol.assert_called_once_with("WM_DELETE_WINDOW", ui.close_window)
        # Invoke the real window-manager action; tick must no longer find a
        # refresh_tables callback on a destroyed window.
        window.protocol.call_args.args[1]()
        self.assertIsNone(ui.window)
        window.destroy.assert_called_once_with()
        ui.tick()
        window.refresh_tables.assert_not_called()


class RoomSaveOwnershipTest(unittest.TestCase):
    def setup_save(self):
        client = SimpleNamespace(my_room={"id": "original"}, room_lock=Mock(), room_rules=Mock())
        calls = []
        tab = SimpleNamespace(client=client,
                              call=lambda fn, *args, then=None: calls.append((fn, then)))
        done = Mock()
        tk_rooms._save_settings(tab, None, None, False, {"auto_skip_after_round": True}, done)
        return tab, client, calls, done

    def test_replaced_client_cannot_receive_old_room_rule_request(self):
        tab, _client, calls, done = self.setup_save()
        tab.client = SimpleNamespace(my_room={"id": "original"}, room_rules=Mock())
        calls[0][1]({})
        self.assertEqual(len(calls), 1)
        done.assert_not_called()

    def test_joining_another_room_cancels_second_step(self):
        _tab, client, calls, done = self.setup_save()
        client.my_room = {"id": "different"}
        calls[0][1]({})
        self.assertEqual(len(calls), 1)
        done.assert_not_called()

    def test_final_ack_from_left_room_does_not_report_success(self):
        _tab, client, calls, done = self.setup_save()
        calls[0][1]({})
        self.assertEqual(len(calls), 2)
        client.my_room = None
        calls[1][1]({})
        done.assert_not_called()


if __name__ == "__main__":
    unittest.main()
