"""The launcher's command line --search ranked / --search casual (1.1.5, GitHub #25): the starter passes its own
arguments on, the launcher reads them (an unknown option or value never stops it), opens the Online tab and asks the
tab to search (lobby/tests/test_tk_tab.py test_search_from_the_command_line covers the tab with a real server); a
restart after an update does not search again. The search waits for the game state (SearchWaitsForTheGameState)."""
import gc
import importlib.machinery
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for sub in ("tools", "lobby", "launcher"):
    p = os.path.join(ROOT, sub)
    if p not in sys.path:
        sys.path.insert(0, p)


_launcher = []


def load_launcher():
    """Once per process: every load's App wraps Tk's callback class once more (guard_tk_callbacks)."""
    if not _launcher:
        path = os.path.join(ROOT, "launcher", "t5dr_launcher.pyw")
        loader = importlib.machinery.SourceFileLoader("t5dr_launcher_search", path)
        spec = importlib.util.spec_from_loader("t5dr_launcher_search", loader)
        mod = importlib.util.module_from_spec(spec)
        loader.exec_module(mod)
        _launcher.append(mod)
    return _launcher[0]


class FakeApp:
    def __init__(self):
        self.calls = []
        self.restart_requested = False
        self.lowprio_var = self.force_var = None

    def after(self, _ms, fn):
        fn()

    def search_on_start(self, mode):
        self.calls.append(mode)

    def mainloop(self):
        pass


class SearchArgument(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.L = load_launcher()
        except ImportError as e:            # (no tkinter)
            raise unittest.SkipTest(str(e))

    def run_main(self, *argv):
        app = FakeApp()
        logged = []
        with mock.patch.object(sys, "argv", ["t5dr_launcher.pyw", *argv]), \
                mock.patch.object(self.L, "App", lambda offscreen=False: app), \
                mock.patch.object(self.L, "enable_dpi_awareness", lambda: None), \
                mock.patch.object(self.L.core, "log", logged.append):
            self.L.main()
        return app.calls, logged

    def test_ranked_and_casual(self):
        self.assertEqual(self.run_main("--search", "ranked")[0], ["ranked"])
        self.assertEqual(self.run_main("--search", "Casual")[0], ["casual"])
        self.assertEqual(self.run_main("--search=ranked")[0], ["ranked"])
        self.assertEqual(self.run_main()[0], [])

    def test_never_stops_the_launcher(self):
        calls, logged = self.run_main("--search", "tournament")
        self.assertEqual(calls, [])
        self.assertTrue(any("neither ranked nor casual" in l for l in logged), logged)
        calls, logged = self.run_main("--search", "ranked", "--from-an-old-shortcut")
        self.assertEqual(calls, ["ranked"])
        self.assertTrue(any("ignored --from-an-old-shortcut" in l for l in logged), logged)

    def test_restart_does_not_search_again(self):
        self.assertEqual(self.L.without_search(["x.pyw", "--search", "ranked", "--force"]), ["x.pyw", "--force"])
        self.assertEqual(self.L.without_search(["x.pyw", "--search=casual"]), ["x.pyw"])

    def test_starter_passes_its_arguments_on(self):
        with open(os.path.join(ROOT, "launcher", "stub", "t5dr_stub.c"), encoding="utf-8") as f:
            src = f.read()
        self.assertIn("cat(cmd, args, 3 * PATH_CAP)", src)            # the child-process build
        self.assertIn("argv[argn++] = __wargv[i]", src)                 # T5DR_STUB_INPROCESS


class SearchWaitsForTheGameState(unittest.TestCase):
    """The real main() with the real App, its real timers and the real Tk main loop (the worker thread's after() needs
    it): the game state comes from a thread some time after the launcher's timers, and until then App.game_state() says
    "not ok". v1.1.9 asked the tab before that, so every --search on a built game ended at "Build the game first".
    The lobby server is local; the game state's folder is never read and no game starts."""
    STATE_TAKES = 0.5                       # (longer than main's 300 ms timer: the order that failed)
    READY = {"ok": True, "text": "Ready (test)."}

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="t5search-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        env = mock.patch.dict(os.environ, T5_ONLINE_DIR=os.path.join(self.dir, "online"), T5_LANG="en", T5_PAD_NAV="0",
                              T5_NOTIFY="0", T5_FW_CHECK="0", T5_PORTMAP="0", T5DR_NO_UPDATE_CHECK="1", T5_DISCORD="0",
                              T5_NET_BIND="127.0.0.1",
                              # (an OpenRecomp-FGC window open on this PC would hold the saved login back:
                              # lobby/tests/util.py turns the check off only when imported, inside this patch)
                              T5_COEXIST_CHECK="0")
        env.start()
        self.addCleanup(env.stop)
        try:
            self.L = L = load_launcher()
        except ImportError as e:            # (no tkinter)
            self.skipTest(str(e))
        real_settings = L.core.Settings
        for name, value in (("Settings", lambda: real_settings(os.path.join(self.dir, "launcher.json"))),
                            ("LAUNCHER_LOG", os.path.join(self.dir, "launcher.log"))):
            p = mock.patch.object(L.core, name, value)
            p.start()
            self.addCleanup(p.stop)
        for name in ("refresh_prereqs", "refresh_inputs", "refresh_rank_art"):
            p = mock.patch.object(L.App, name, lambda app: None)
            p.start()
            self.addCleanup(p.stop)
        self.app = None
        self.server = None
        self.thread_errors = []

    def tearDown(self):
        app = self.app
        if app is not None:
            app.online.on_close()
            for aid in app.tk.splitlist(app.tk.call("after", "info")):       # no timer into a window that is gone
                app.tk.call("after", "cancel", aid)
            app.destroy()
        self.app = None
        gc.collect()                        # (the Tk objects die here, on the main thread)
        if self.server is not None:
            self.server.stop()

    def saved_login(self, addr, name=None, token=None):
        """online.json as a player's launcher left it: this server, and a remembered login if there is one."""
        os.makedirs(os.environ["T5_ONLINE_DIR"])
        cfg = {"server": addr}
        if token:
            cfg["sessions"] = {addr: {"name": name, "token": token, "saved": time.time()}}
        with open(os.path.join(os.environ["T5_ONLINE_DIR"], "online.json"), "w") as f:
            json.dump(cfg, f)

    def account(self):
        """A local server and an account with a remembered login. -> its name on the server."""
        if os.path.join(ROOT, "lobby", "tests") not in sys.path:
            sys.path.append(os.path.join(ROOT, "lobby", "tests"))
        import util
        self.BUILD = util.BUILD
        self.server = util.ServerThread().start()
        c = util.client(self.server)
        me = c.register("Searcher", "secret-pw1", remember=True)
        token = c.session
        c.close()
        self.saved_login(self.server.addr, me["name"], token)
        return me["name"].lower()

    def hidden_window(self, parent):
        w = self.L.tk.Toplevel(parent)
        w.withdraw()
        return w

    def make_app(self):
        try:
            self.app = self.L.App(offscreen=False)
        except self.L.tk.TclError as e:
            self.skipTest(f"no display: {e}")
        self.app.withdraw()
        self.app.settings[self.L.first_start.CONTROLS_HINT_KEY] = True    # (its modal dialog would wait for a click)
        tab = self.app.online
        tab._build_info = lambda: (getattr(self, "BUILD", None), None)
        tab.new_window = self.hidden_window
        tab.bring_forward = lambda w: None
        tab.bring_game_forward = lambda pid: None
        self.assertTrue(tab.server_var.get().startswith("127.0.0.1:"), "only a local server in this test")
        return self.app

    def run_main(self, state, until, *argv, timeout=20.0):
        """main() --search ... with a game state that takes STATE_TAKES seconds, until until() (or the timeout)."""
        def game_state(_out):
            time.sleep(self.STATE_TAKES)
            if isinstance(state, Exception):
                raise state
            return state

        end = time.monotonic() + timeout

        def poll():
            if until() or time.monotonic() > end:
                self.app.quit()
            else:
                self.app.after(30, poll)
        self.app.after(30, poll)
        with mock.patch.object(sys, "argv", ["t5dr_launcher.pyw", *argv]), \
                mock.patch.object(self.L, "App", lambda offscreen=False: self.app), \
                mock.patch.object(self.L, "enable_dpi_awareness", lambda: None), \
                mock.patch.object(self.L, "log_thread_errors", lambda: None), \
                mock.patch.object(threading, "excepthook", lambda a: self.thread_errors.append(a.exc_value)), \
                mock.patch.object(self.L.core, "game_state", game_state):
            self.L.main()

    def test_tab_is_asked_after_the_state_is_known(self):
        self.saved_login("127.0.0.1:1")
        app = self.make_app()
        asked = []
        app.online.search_on_start = lambda mode: asked.append((mode, app.game_state().get("ok")))
        self.run_main(self.READY, lambda: asked, "--search", "ranked")
        self.assertEqual(asked, [("ranked", True)])
        self.assertEqual(app._selected_tab(), "online")
        app.refresh_game_state = lambda: None
        app._show_game_state(self.READY)                                # (a later refresh: no second search)
        self.assertEqual(len(asked), 1)

    def searching(self, name):
        """-> a function: is this account in the server's queue?"""
        srv = self.server
        return lambda: srv.call(lambda: srv.srv.by_name[name].status if name in srv.srv.by_name else None) == "queue"

    def check_search(self, arg, queue):
        found = self.searching(self.account())
        app = self.make_app()
        self.run_main(self.READY, found, "--search", arg)
        self.assertTrue(found(), app.online.status_var.get())
        self.assertNotIn("Build the game", app.online.status_var.get())
        self.assertEqual(app.online.cfg.get("last_search"), queue)
        self.assertEqual(app._selected_tab(), "online")

    def test_ranked_on_a_built_game_with_a_saved_login(self):
        self.check_search("ranked", "ranked")

    def test_casual_on_a_built_game_with_a_saved_login(self):
        self.check_search("casual", "quick")

    def test_a_click_on_the_online_tab_before_the_state_is_known(self):
        """The player (or a pad) opens the tab in that first moment: the login the tab tries when it is shown finds
        no game yet. The search still logs in."""
        found = self.searching(self.account())
        app = self.make_app()
        app.after(0, lambda: app.nb.select(app.tabs["online"]))
        self.run_main(self.READY, found, "--search", "ranked")
        self.assertTrue(found(), app.online.status_var.get())

    def test_a_game_that_is_not_built_gets_the_hint(self):
        self.saved_login("127.0.0.1:1", "Searcher", "token")            # (nothing listens there: it must not try)
        app = self.make_app()
        hint = lambda: "Build the game first" in app.online.status_var.get()
        self.run_main({"ok": False, "text": "Not built (test)."}, hint, "--search", "ranked")
        self.assertTrue(hint(), app.online.status_var.get())
        self.assertEqual(app._selected_tab(), "online")
        self.assertIsNone(app.online.client)
        self.assertIsNone(app.online._pending_search)

    def test_a_state_that_cannot_be_read_does_not_swallow_the_search(self):
        self.saved_login("127.0.0.1:1", "Searcher", "token")
        app = self.make_app()
        hint = lambda: "Build the game first" in app.online.status_var.get()
        self.run_main(OSError("the file is locked (test)"), hint, "--search", "ranked")
        self.assertTrue(hint(), app.online.status_var.get())
        self.assertEqual([str(e) for e in self.thread_errors], ["the file is locked (test)"])   # (in launcher.log)


if __name__ == "__main__":
    unittest.main()
