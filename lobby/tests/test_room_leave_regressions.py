"""Room notification lifetimes with fake widgets and queues; no server or game."""
import queue
import types
import unittest
from unittest import mock

import util  # noqa: F401 -- local lobby package path; no server is started
from t5lobby import notify, tk_tab


class RoomLeaveNotificationTest(unittest.TestCase):
    def tab(self):
        tab = object.__new__(tk_tab.OnlineTab)
        tab._closed = False
        tab._after = None
        tab.parent = mock.Mock()
        tab.view = mock.Mock()
        tab.ui_q = queue.Queue()
        tab.results_q = queue.Queue()
        tab._callbacks = {}
        tab._set_actions = mock.Mock()
        tab.fw_q = queue.Queue()
        tab.driver = None
        tab.casual = mock.Mock()
        tab.spec = mock.Mock()
        tab.rooms_ui = mock.Mock()
        tab.tours = mock.Mock()
        for name in ("_coexist_tick", "_tick_ready", "_tick_set", "_invite_wait_tick", "_relogin_tick",
                     "_presence_tick", "_show_notice", "_pad_tick", "_records_tick"):
            setattr(tab, name, mock.Mock())
        tab.notifier = mock.Mock()
        tab.room_watch = notify.RoomWatch()
        room = {"id": "r1", "owner_id": "p1", "players": [{"id": "p1", "name": "Host"}],
                "next": {"players": ["p1", "p2"]}}
        tab.client = types.SimpleNamespace(my_room=room, me={"id": "p1"}, events=queue.Queue())
        tab.room_watch.update(room, "p1")
        tab.on_event = lambda ev: tk_tab.OnlineTab._notify_event(tab, ev)
        return tab

    def assert_forgotten(self, tab):
        self.assertIsNone(tab.room_watch.room_id)
        self.assertEqual(tab.room_watch.members, set())
        self.assertFalse(tab.room_watch.turn)

    def test_acknowledged_leave_without_lobby_broadcast_forgets_room(self):
        # A room created and left between broadcast ticks can leave no delta:
        # the server's public lists are the same as at the preceding tick.
        tab = self.tab()
        tab.client.my_room = None  # leave_room's successful reply was received
        tab._poll()
        self.assert_forgotten(tab)
        tab.notifier.notify.assert_not_called()

    def test_lobby_event_before_leave_reply_is_not_required_again(self):
        tab = self.tab()
        tab.on_event({"t": "lobby_state", "players": [], "rooms": []})
        self.assertEqual(tab.room_watch.room_id, "r1")
        tab.client.my_room = None  # the request returns after that event
        tab._poll()               # no second event needs to arrive
        self.assert_forgotten(tab)

    def test_queued_room_update_cannot_restore_an_acknowledged_leave(self):
        tab = self.tab()
        old_room = tab.client.my_room
        tab.client.my_room = None
        tab.client.events.put({"t": "room", "room": old_room})
        tab._poll()
        self.assert_forgotten(tab)

    def test_create_completing_during_results_reaches_the_room_watch_this_poll(self):
        tab = self.tab()
        room = tab.client.my_room
        tab.client.my_room = None
        tab.room_watch.reset()
        closed = []

        def created(_room):
            # The client thread completed this request after the first event
            # drain. Its response event is now queued when the UI closes Create.
            tab.client.my_room = room
            tab.client.events.put({"t": "room", "room": room})
            closed.append(True)

        tab._callbacks[1] = (created, None)
        tab.results_q.put((1, True, room))
        tab._poll()
        self.assertEqual(closed, [True])
        self.assertEqual(tab.room_watch.room_id, "r1")
        self.assertEqual(tab.room_watch.members, {"p1"})
        self.assertTrue(tab.room_watch.turn)

    def test_leave_completing_during_results_forgets_room_this_poll(self):
        tab = self.tab()

        def left(_reply):
            tab.client.my_room = None

        tab._callbacks[1] = (left, None)
        tab.results_q.put((1, True, {"t": "ok"}))
        tab._poll()
        self.assert_forgotten(tab)
        tab.notifier.notify.assert_not_called()

    def test_events_already_queued_still_precede_request_callbacks(self):
        tab = self.tab()
        seen = []
        tab.client.events.put({"t": "match_start"})
        tab.on_event = lambda _ev: seen.append("match_start")
        tab._callbacks[1] = (lambda _reply: seen.append("watch_callback"), None)
        tab.results_q.put((1, True, {}))
        tab._poll()
        self.assertEqual(seen, ["match_start", "watch_callback"])
        tab.spec.before_event.assert_called_once_with({"t": "match_start"})

    def test_poll_preserves_the_current_room_and_notification_baseline(self):
        tab = self.tab()
        tab._poll()
        self.assertEqual(tab.room_watch.room_id, "r1")
        self.assertEqual(tab.room_watch.members, {"p1"})
        self.assertTrue(tab.room_watch.turn)
        tab.notifier.notify.assert_not_called()

    def test_ordinary_lobby_event_and_disconnect_still_forget_room(self):
        for event in ({"t": "lobby_state"}, {"t": "disconnected"}):
            with self.subTest(event=event):
                tab = self.tab()
                tab.client.my_room = None
                tab.on_event(event)
                self.assert_forgotten(tab)


if __name__ == "__main__":
    unittest.main()
