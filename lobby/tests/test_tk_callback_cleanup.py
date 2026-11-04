"""OnlineTab polling lifecycle with a fake scheduler: no Tk, sockets or game."""
import queue
from types import SimpleNamespace
import unittest
from unittest import mock

import util  # noqa: F401 -- local package path and safe test environment
from t5lobby.tk_tab import OnlineTab


class Scheduler:
    def __init__(self):
        self.pending = {}
        self.sequence = 0

    def winfo_exists(self):
        return True

    def after(self, delay, callback):
        self.sequence += 1
        token = f"after#{self.sequence}"
        self.pending[token] = callback
        return token

    def after_cancel(self, token):
        self.pending.pop(token, None)


class PollCleanupTest(unittest.TestCase):
    def tab(self):
        tab = OnlineTab.__new__(OnlineTab)
        tab.parent = Scheduler()
        tab._closed = False
        tab._after = tab.parent.after(100, tab._poll)
        tab.view = SimpleNamespace(box=tab.parent, tick=mock.Mock(), close=mock.Mock())
        tab.ui_q = queue.Queue()
        tab.results_q = queue.Queue()
        tab.fw_q = queue.Queue()
        tab._callbacks = {}
        tab.client = tab.driver = tab.pad = None
        tab.tours = SimpleNamespace(tick=mock.Mock())
        tab.spec = SimpleNamespace(poll=mock.Mock(), stop=mock.Mock())
        tab.rooms_ui = SimpleNamespace(tick=mock.Mock())
        # _build_ui creates this controller before the first poll is scheduled.
        tab.private_chat = SimpleNamespace(reset=mock.Mock())
        for name in ("_coexist_tick", "_tick_ready", "_tick_set", "_invite_wait_tick", "_relogin_tick",
                     "_presence_tick", "_show_notice", "_pad_tick", "_stop_presence", "stop_hosting"):
            setattr(tab, name, mock.Mock())
        return tab

    def test_manual_polls_do_not_leave_untracked_timers_on_close(self):
        tab = self.tab()
        tab._poll()
        tab._poll()
        self.assertEqual(len(tab.parent.pending), 1)
        tab.on_close()
        self.assertEqual(tab.parent.pending, {})

    def test_closed_tab_cannot_start_polling_again(self):
        tab = self.tab()
        tab.on_close()
        tab._poll()
        self.assertEqual(tab.parent.pending, {})
        tab.view.tick.assert_not_called()

    def test_close_while_polling_does_not_rearm_timer(self):
        tab = self.tab()
        tab.view.tick.side_effect = tab.on_close
        tab._poll()
        self.assertEqual(tab.parent.pending, {})

    def test_repeated_close_does_not_repeat_shutdown(self):
        tab = self.tab()
        tab.on_close()
        tab.on_close()
        tab.private_chat.reset.assert_called_once_with()
        tab.spec.stop.assert_called_once_with()
        tab.view.close.assert_called_once_with()
        tab._stop_presence.assert_called_once_with(wait=True)
        tab.stop_hosting.assert_called_once_with(wait=3.0)


if __name__ == "__main__":
    unittest.main()
