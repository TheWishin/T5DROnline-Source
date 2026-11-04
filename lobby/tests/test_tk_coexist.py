"""Launcher coexistence with fake processes, locks, clients and widgets; no network."""
import errno
import os
import tempfile
import types
import unittest
from unittest import mock

import util  # noqa: F401
from t5lobby import coexist, i18n, tk_tab, tk_views
from t5lobby.client import LobbyClient
from t5lobby.buildid import BuildInfo


class Var:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class DetectionTests(unittest.TestCase):
    def detector(self, **kwargs):
        detector = coexist.Detector(directory="fake-temp", **kwargs)
        detector.enabled = True
        return detector

    def test_window_slots_use_openrecomp_names_and_all_sixteen_slots(self):
        held = mock.Mock(side_effect=lambda path: path.endswith("window-15.lock"))
        detector = self.detector(held=held)
        self.assertTrue(detector.openrecomp_open())
        self.assertEqual(held.call_args_list, [mock.call(os.path.join(
            "fake-temp", "OpenRecomp-FGC-presence", f"window-{n}.lock")) for n in range(16)])
        held.side_effect = None
        held.return_value = False
        self.assertFalse(detector.openrecomp_open())  # stale, unlocked files are absent windows

    def test_game_reservation_or_process_from_any_launcher(self):
        for locked, process in ((True, False), (False, True), (False, False)):
            with self.subTest(locked=locked, process=process):
                scan = mock.Mock(return_value=process)
                held = mock.Mock(return_value=locked)
                detector = self.detector(scan=scan, held=held, clock=lambda: 0)
                detector.refresh()
                detector._next = 10  # consume the result without starting a real thread
                detector.poll()
                self.assertEqual(detector.game_running, locked or process)
                held.assert_called_once_with(os.path.join(
                    "fake-temp", "OpenRecomp-FGC-launches", "t5dr.lock"))
                self.assertEqual(scan.call_count, 0 if locked else 1)

    @unittest.skipUnless(os.name == "nt", "Windows tasklist format")
    def test_image_check_uses_exact_name_case_insensitively_and_no_console(self):
        for output, expected in (('"T5DR.EXE","42","Console"\n', True),
                                 ('"not-t5dr.exe","42"\n', False),
                                 ('INFO: No tasks are running which match the specified criteria.', False)):
            run = mock.Mock(return_value=types.SimpleNamespace(returncode=0, stdout=output))
            self.assertEqual(coexist.game_process_running(run), expected)
            args, kwargs = run.call_args
            self.assertEqual(args[0], ["tasklist", "/FI", "IMAGENAME eq t5dr.exe", "/FO", "CSV", "/NH"])
            self.assertEqual(kwargs["creationflags"], coexist.subprocess.CREATE_NO_WINDOW)
        self.assertFalse(coexist.game_process_running(mock.Mock(side_effect=OSError())))
        self.assertFalse(coexist.game_process_running(mock.Mock(
            return_value=types.SimpleNamespace(returncode=1, stdout='"t5dr.exe"'))))

    @unittest.skipUnless(os.name == "nt", "Windows byte lock probe")
    def test_lock_probe_is_read_only_and_stale_files_do_not_count(self):
        import msvcrt
        stream = mock.MagicMock()
        stream.__enter__.return_value = stream
        with mock.patch("builtins.open", return_value=stream) as opened, \
                mock.patch.object(msvcrt, "locking") as locking:
            self.assertFalse(coexist.lock_held("fake.lock"))
            opened.assert_called_once_with("fake.lock", "rb")
            stream.write.assert_not_called()
            locking.side_effect = OSError(errno.EACCES, "held")
            self.assertTrue(coexist.lock_held("fake.lock"))
            locking.side_effect = OSError(errno.EBADF, "unreadable")
            self.assertFalse(coexist.lock_held("fake.lock"))
        with mock.patch("builtins.open", side_effect=FileNotFoundError):
            self.assertFalse(coexist.lock_held("missing.lock"))

    def test_slow_scan_is_throttled_and_never_runs_on_tk_thread(self):
        detector = self.detector(scan=mock.Mock(), held=lambda _p: False, clock=lambda: 10)
        with mock.patch.object(coexist.threading, "Thread") as thread:
            detector.poll()
            detector.poll()
            thread.assert_called_once()
            detector.scan.assert_not_called()
            detector.refresh()
            detector.poll()
            thread.assert_called_once()  # completed, but not time for another scan

    def test_process_start_and_exit_are_reflected_and_failed_scans_do_not_stick(self):
        scan = mock.Mock(side_effect=[False, True, False, OSError("unavailable")])
        detector = self.detector(scan=scan, held=lambda _p: False, clock=lambda: 0)
        detector._next = 10
        for expected in (False, True, False, False):
            detector.refresh()
            detector.poll()
            self.assertEqual(detector.game_running, expected)

    def test_disabled_checks_never_touch_processes_or_locks(self):
        scan, held = mock.Mock(), mock.Mock()
        detector = self.detector(scan=scan, held=held)
        detector.enabled = False
        detector.poll()
        self.assertFalse(detector.openrecomp_open())
        scan.assert_not_called()
        held.assert_not_called()


class OnlineTests(unittest.TestCase):
    def setUp(self):
        i18n.set_language("en")
        self.addCleanup(i18n.set_language, "en")
        self.tab = object.__new__(tk_tab.OnlineTab)
        tab = self.tab
        tab.client = mock.Mock(connected=True, me={"id": "me", "status": "queue"})
        tab.coexist = mock.Mock(game_running=True, window_open=False)
        tab.coexist.openrecomp_open.return_value = False
        tab.coexist_var = Var()
        tab._outside_unqueue = None
        tab.status = mock.Mock()
        tab.call = mock.Mock()

    def test_quick_and_ranked_search_leave_once_keep_connection_and_explain(self):
        tab = self.tab
        for mode in ("quick", "ranked"):
            with self.subTest(mode=mode):
                c = tab.client
                c.me.update(status="queue", queue=mode)
                tab._outside_unqueue = None
                tab.call.reset_mock()
                tab._coexist_tick()
                tab._coexist_tick()
                tab.call.assert_called_once()
                self.assertEqual(tab.call.call_args.args, (c.cancel_queue,))
                tab._queue_status("must not replace the explanation")
                self.assertIn("another launcher", tab.status.call_args.args[0])
                tab.call.call_args.kwargs["then"]({})
                c.close.assert_not_called()
                self.assertIs(tab.client, c)
                self.assertTrue(c.connected)
                self.assertIn("still logged in", tab.status.call_args.args[0])
                c.me["status"] = "idle"
                tab._coexist_tick()
                self.assertIsNone(tab._outside_unqueue)

    def test_no_cancellation_when_idle_playing_disconnected_or_no_game(self):
        tab = self.tab
        for status in ("idle", "playing", "match", "room"):
            tab.client.me["status"] = status
            tab._coexist_tick()
        tab.client.me["status"] = "queue"
        tab.client.connected = False
        tab._coexist_tick()
        tab.client.connected = True
        tab.coexist.game_running = False
        tab._coexist_tick()
        tab.call.assert_not_called()

    def test_own_persistent_or_spectator_game_never_stops_a_search(self):
        """Integration 1.2.1: this launcher's own game (kept open between matches, or watching) is a t5dr.exe too."""
        tab = self.tab
        tab.driver = mock.Mock()
        tab.driver.game_running.return_value = True
        tab._coexist_tick()
        tab.call.assert_not_called()
        self.assertFalse(tab._game_elsewhere())
        tab.driver.game_running.return_value = False
        tab.spec = types.SimpleNamespace(active=True)
        tab._coexist_tick()
        tab.call.assert_not_called()
        tab.spec = types.SimpleNamespace(active=False)
        self.assertTrue(tab._game_elsewhere())
        tab._coexist_tick()
        tab.call.assert_called_once()

    def test_cannot_reenter_either_queue_while_game_is_known_to_be_running(self):
        for mode in ("quick", "ranked"):
            self.tab.do_queue(mode)
        self.tab.call.assert_not_called()
        self.assertIn("still logged in", self.tab.status.call_args.args[0])

    def test_failed_unqueue_can_retry_and_late_reply_cannot_change_new_login(self):
        tab = self.tab
        tab._coexist_tick()
        tab.call.call_args.kwargs["fail"]()
        tab._coexist_tick()
        self.assertEqual(tab.call.call_count, 2)
        done = tab.call.call_args.kwargs["then"]
        tab.client = mock.Mock()
        tab.status.reset_mock()
        done({})
        tab.status.assert_not_called()

    def test_build_hint_counts_only_other_incompatible_queued_players(self):
        tab = self.tab
        c = object.__new__(LobbyClient)
        c.build = BuildInfo("elf", "code", "test")
        c.me = {"id": "me", "status": "queue", "compat_group": "approved"}
        c.welcome = {"caps": ["compat_groups"], "compat_group": "approved"}
        tab.client = c
        # Exercise the client's own rule: different build in the approved group is compatible.
        tab._last_lobby = {"queue": {"quick": 5, "ranked": 2}, "players": [
            {"id": "me", "status": "queue", "build": "other"},
            {"id": "same", "status": "queue", "build": c.build.build_id},
            {"id": "group", "status": "queue", "build": "other", "compat_group": "approved"},
            {"id": "old-quick", "status": "queue", "build": "old"},
            {"id": "old-ranked", "status": "queue", "build": "older"},
            {"id": "idle", "status": "idle", "build": "old"}]}
        tab._queue_status()
        self.assertIn("2 other player(s)", tab.status.call_args.args[0])
        self.assertIn("2 in the ranked queue, 5 quick", tab.status.call_args.args[0])
        tab._last_lobby["players"] = []
        tab._queue_status()
        self.assertNotIn("different build", tab.status.call_args.args[0])
        c.me["status"] = "idle"
        tab.status.reset_mock()
        tab._queue_status()
        tab.status.assert_not_called()

    def test_queue_reply_shows_search_text_before_lobby_snapshot_arrives(self):
        tab = self.tab
        tab.client.me["status"] = "idle"
        tab._queue_status("Searching for an opponent...")
        tab.status.assert_called_once_with("Searching for an opponent...")

    def saved_login_tab(self):
        tab = self.tab
        tab.client = None
        tab._auto_tried = False
        tab._login_busy = False
        tab._kicked = False
        tab._saved_session = mock.Mock(return_value={"name": "Player", "token": "fake-token"})
        tab.app = mock.Mock()
        tab.app.game_state.return_value = {"ok": True}
        tab.name_var = Var("Player")
        tab.do_login = mock.Mock()
        tab.coexist.openrecomp_open.return_value = True
        return tab

    def test_open_window_blocks_saved_login_and_retry_even_after_window_closes(self):
        tab = self.saved_login_tab()
        tab.try_saved_login()
        self.assertEqual(tab.coexist_var.get(),
                         "OpenRecomp-FGC is open: you can be online in one launcher at a time.")
        tab.do_login.assert_not_called()
        tab._relogin_at = 0
        tab._relogin_tick()
        self.assertIsNone(tab._relogin_at)
        tab.coexist.openrecomp_open.return_value = False
        tab.try_saved_login()
        tab.do_login.assert_not_called()  # opening/closing another launcher cannot steal the login
        self.assertFalse(tab._coexist_note())
        self.assertEqual(tab.coexist_var.get(), "")

    def test_saved_login_still_works_without_openrecomp(self):
        tab = self.saved_login_tab()
        tab.coexist.openrecomp_open.return_value = False
        tab.try_saved_login()
        tab.do_login.assert_called_once_with("session", session="fake-token")

    def test_manual_login_is_allowed_with_openrecomp_open(self):
        tab = self.saved_login_tab()
        tab.do_login = types.MethodType(tk_tab.OnlineTab.do_login, tab)
        tab._relogin_at = None
        tab.pw_var = Var("fake-password")
        tab.server_var = Var("fake-server")
        tab.remember_var = Var(True)
        tab._build_info = lambda: (mock.sentinel.build, None)
        tab._save_cfg = mock.Mock()
        tab._new_client = mock.Mock()
        tab.do_login("account")
        self.assertTrue(tab._login_busy)
        tab._new_client.assert_called_once_with("fake-server", mock.sentinel.build)
        tab.call.assert_called_once()  # connection work captured, never executed

    def test_note_is_visible_on_online_tab_and_disappears_when_window_closes(self):
        view = object.__new__(tk_views.OnlineView)
        view.tab = self.tab
        view.px = lambda n: n
        view.coexist_label = mock.Mock()
        self.tab.coexist.openrecomp_open.return_value = True
        self.tab._coexist_note()
        view._show_coexist()
        view.coexist_label.grid.assert_called_once_with(row=5, column=0, sticky="we", pady=(8, 0))
        self.tab.coexist.openrecomp_open.return_value = False
        self.tab._coexist_note()
        view._show_coexist()
        view.coexist_label.grid_forget.assert_called_once()

    def test_new_texts_exist_and_format_in_all_seven_languages(self):
        for lang in i18n.LANGUAGES:
            i18n.set_language(lang)
            i18n.clear_missing()
            self.tab.coexist.openrecomp_open.return_value = True
            self.tab._coexist_note()
            self.tab._coexist_tick()
            self.tab._last_lobby = {"players": [{"id": "other", "status": "queue"}]}
            self.tab.client.compatible.return_value = False
            self.tab._outside_unqueue = None
            self.tab._queue_status()
            self.assertIn("1", self.tab.status.call_args.args[0])
            self.assertFalse(i18n.missing(), lang)


class WidgetTests(unittest.TestCase):
    def test_injected_presence_note_in_real_online_view_without_login_or_processes(self):
        import tkinter as tk
        from test_tk_tab import FakeApp

        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.dict(os.environ, {"T5_ONLINE_DIR": directory}):
            root = tk.Tk()
            root.withdraw()
            tab = None
            try:
                detector = mock.Mock(game_running=False, window_open=True)
                detector.openrecomp_open.return_value = True
                tab = tk_tab.OnlineTab(root, FakeApp(directory), detector=detector)
                tab._saved_session = mock.Mock(return_value={"name": "Player", "token": "fake"})
                tab.do_login = mock.Mock()
                tab.on_show()
                tab._poll()
                self.assertEqual(tab.view.coexist_label.winfo_manager(), "grid")
                self.assertIn("OpenRecomp-FGC is open", tab.coexist_var.get())
                tab.do_login.assert_not_called()
                detector.window_open = False
                detector.openrecomp_open.return_value = False
                tab._poll()
                self.assertEqual(tab.view.coexist_label.winfo_manager(), "")
                self.assertIsNone(tab.client)
            finally:
                if tab is not None:
                    tab.on_close()
                root.destroy()
                tab = root = None
                import gc
                gc.collect()


if __name__ == "__main__":
    unittest.main()
