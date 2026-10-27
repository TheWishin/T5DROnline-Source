"""The launcher never closes because of its own helper code (1.1.7): an error -- SystemExit included -- in a button,
timer or binding is written to launcher.log and the window stays open; only the player's close ends it. 1.1.5
closed 2 s after its start because a helper's SystemExit left a timer callback (Tk's CallWrapper re-raises it and
mainloop() ends). Real Tk, real main loop."""
import os
import shutil
import tempfile
import threading
import time
import unittest

import test_i18n as ti
from test_i18n import core


@unittest.skipIf(ti.tk is None, "no tkinter")
class Guard(ti.Base):
    def app(self):
        d = tempfile.mkdtemp(prefix="t5dr-guard")
        self.addCleanup(shutil.rmtree, d, True)
        os.environ["T5_ONLINE_DIR"] = os.path.join(d, "user")
        self.addCleanup(os.environ.pop, "T5_ONLINE_DIR", None)
        st = core.Settings(os.path.join(d, "launcher.json"))
        st["out"] = os.path.join(d, "native")
        st["language"] = "en"
        mod = ti.load_launcher()
        try:
            app = mod.App(offscreen=False, settings=st)
        except ti.tk.TclError as e:
            self.skipTest(f"no display: {e}")
        app.withdraw()
        ti.cancel_timers(app)

        def close():
            ti.cancel_timers(app)
            try:
                app.online.on_close()
                app.destroy()
            except ti.tk.TclError:
                pass
        self.addCleanup(close)
        return mod, app

    def log(self):
        try:
            with open(self.launcher_log, encoding="utf-8") as f:
                return f.read()
        except OSError:
            return ""

    def test_systemexit_and_errors_in_callbacks_keep_the_window(self):
        mod, app = self.app()
        seen = []

        def helper_exits():                    # what 1.1.5's package check did inside a timer
            raise SystemExit("package key PKG_AES_KEY not found in T5DR_KEYS=''")

        def helper_fails():
            raise RuntimeError("a helper broke")

        def button_exits():
            raise SystemExit(2)
        btn = ti.tk.Button(app, command=button_exits)
        app.after(20, helper_exits)
        app.after(40, helper_fails)
        app.after(60, btn.invoke)              # a button's command
        app.after(80, lambda: app.event_generate("<<T5Guard>>"))
        app.bind("<<T5Guard>>", lambda _e: helper_exits())        # a binding
        app.after(400, lambda: (seen.append("still running"), app.quit()))
        t_end = time.monotonic() + 10
        app.after(10000, app.quit)              # (never hang the test run)
        app.mainloop()                          # (Tk's own loop: run_mainloop is only the second net)
        self.assertLess(time.monotonic(), t_end)
        self.assertEqual(seen, ["still running"])           # the loop ended by our quit, not by a SystemExit
        self.assertTrue(app.winfo_exists())
        log = self.log()
        self.assertEqual(log.count("error in the launcher (the window stays open)"), 4, log)
        self.assertIn("SystemExit: package key PKG_AES_KEY", log)
        self.assertIn("RuntimeError: a helper broke", log)
        self.assertIn("SystemExit: 2", log)

    def test_the_players_close_still_ends_it(self):
        mod, app = self.app()
        app.after(50, app.on_close)
        app.after(10000, app.quit)
        t0 = time.monotonic()
        mod.run_mainloop(app)
        self.assertLess(time.monotonic() - t0, 9)
        with self.assertRaises(ti.tk.TclError):
            app.winfo_exists()

    def test_thread_errors_are_logged(self):
        mod, _app = self.app()
        old = threading.excepthook
        self.addCleanup(setattr, threading, "excepthook", old)
        mod.log_thread_errors()

        def work():
            raise ValueError("a picture reader broke")
        t = threading.Thread(target=work, name="fighter-art")
        t.start()
        t.join(5)
        self.assertIn("error in the launcher's thread fighter-art", self.log())
        self.assertIn("ValueError: a picture reader broke", self.log())


if __name__ == "__main__":
    unittest.main()
