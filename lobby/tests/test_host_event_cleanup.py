"""Hosted subprocess cleanup without Tk, processes, sockets, or game data."""
import gc
import io
import queue
import subprocess
from types import SimpleNamespace
import unittest
import weakref
from unittest import mock

import util  # noqa: F401 -- local package path and isolated test environment
from t5lobby.tk_tab import OnlineTab


class HostEventCleanupTest(unittest.TestCase):
    def tab(self, proc):
        tab = OnlineTab.__new__(OnlineTab)
        tab.host_proc = proc
        tab._closed = False
        tab.host_info = {"port": 7781}
        tab.host_args = []
        tab.map_var = SimpleNamespace(get=lambda: False)
        tab.b_host = mock.Mock()
        tab.status = mock.Mock()
        tab.view = mock.Mock()
        tab.ui_q = queue.Queue()
        return tab

    def reader(self, tab, proc):
        workers = []

        class DeferredThread:
            def __init__(self, target, **_kwargs):
                self.target = target

            def start(self):
                workers.append(self.target)

        with mock.patch("t5lobby.tk_tab.subprocess.Popen", return_value=proc), \
                mock.patch("t5lobby.tk_tab.threading.Thread", DeferredThread):
            tab.do_host()
        return workers.pop()

    def process(self):
        proc = mock.Mock()
        proc.stdout = io.StringIO('{"event": "stopped"}\n')
        proc.stdin = io.StringIO()
        proc.poll.return_value = 0
        proc.returncode = 0
        return proc

    def test_pending_reader_does_not_keep_tab_alive(self):
        proc = self.process()
        tab = self.tab(None)
        ui_q = tab.ui_q
        reader = self.reader(tab, proc)
        tab_ref = weakref.ref(tab)
        del tab
        gc.collect()
        self.assertIsNone(tab_ref())
        reader()
        self.assertTrue(proc.stdout.closed)
        self.assertTrue(proc.stdin.closed)
        while not ui_q.empty():
            ui_q.get_nowait()()  # callbacks safely ignore the destroyed owner

    def test_queued_events_do_not_keep_tab_alive(self):
        proc = self.process()
        tab = self.tab(None)
        ui_q = tab.ui_q
        self.reader(tab, proc)()
        self.assertFalse(ui_q.empty())
        tab_ref = weakref.ref(tab)
        del tab
        gc.collect()
        self.assertIsNone(tab_ref())
        while not ui_q.empty():
            ui_q.get_nowait()()

    def test_stopped_message_keeps_child_owned_until_its_exit(self):
        proc = mock.Mock()
        proc.poll.return_value = None
        tab = self.tab(proc)
        tab._host_event(proc, {"event": "stopped"})
        self.assertIs(tab.host_proc, proc)
        tab.stop_hosting(wait=3.0)
        proc.wait.assert_called_once_with(3.0)

    def test_closed_tab_ignores_already_queued_events(self):
        proc = self.process()
        tab = self.tab(None)
        self.reader(tab, proc)()
        tab._closed = True
        tab._host_event = mock.Mock()
        while not tab.ui_q.empty():
            tab.ui_q.get_nowait()()
        tab._host_event.assert_not_called()

    def test_reader_closes_pipes_and_reaps_before_announcing_exit(self):
        proc = self.process()
        tab = self.tab(None)
        reader = self.reader(tab, proc)
        self.assertIs(tab.host_proc, proc)
        reader()
        self.assertTrue(proc.stdout.closed)
        self.assertTrue(proc.stdin.closed)
        proc.wait.assert_called_once_with()
        while not tab.ui_q.empty():
            tab.ui_q.get_nowait()()
        self.assertIsNone(tab.host_proc)

    def test_timeout_kills_and_reaps_child(self):
        proc = mock.Mock()
        proc.wait.side_effect = [subprocess.TimeoutExpired("host", 3.0), 0]
        tab = self.tab(proc)
        tab.stop_hosting(wait=3.0)
        proc.kill.assert_called_once_with()
        self.assertEqual(proc.wait.call_count, 2)
        self.assertEqual(proc.wait.call_args, mock.call())

    def test_broken_stop_pipe_is_closed(self):
        proc = mock.Mock()
        proc.stdin.write.side_effect = OSError("broken pipe")
        tab = self.tab(proc)
        tab.stop_hosting()
        proc.stdin.close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
