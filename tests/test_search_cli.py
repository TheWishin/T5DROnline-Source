"""The launcher's command line --search ranked / --search casual (1.1.5, GitHub #25): the starter passes its own
arguments on, the launcher reads them (an unknown option or value never stops it), opens the Online tab and asks the
tab to search (lobby/tests/test_tk_tab.py test_search_from_the_command_line covers the tab with a real server); a
restart after an update does not search again."""
import importlib.machinery
import importlib.util
import os
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for sub in ("tools", "lobby", "launcher"):
    p = os.path.join(ROOT, sub)
    if p not in sys.path:
        sys.path.insert(0, p)


def load_launcher():
    path = os.path.join(ROOT, "launcher", "t5dr_launcher.pyw")
    loader = importlib.machinery.SourceFileLoader("t5dr_launcher_search", path)
    spec = importlib.util.spec_from_loader("t5dr_launcher_search", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


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


if __name__ == "__main__":
    unittest.main()
