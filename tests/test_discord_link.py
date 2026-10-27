"""The launcher's "Community Discord" button (1.1.7): in the header next to "Check for updates", it opens the
community's invite (core.DISCORD_URL, one place) in the default browser; a PC without a browser gets the address in
the status bar. The report window names it too. Real Tk, a real main loop; the browser call is a stand-in here."""
import os
import shutil
import tempfile
import time
import unittest
from unittest import mock

import test_i18n as ti
from test_i18n import core


@unittest.skipIf(ti.tk is None, "no tkinter")
class DiscordLink(ti.Base):
    def app(self, lang="en"):
        d = tempfile.mkdtemp(prefix="t5dr-discord")
        self.addCleanup(shutil.rmtree, d, True)
        os.environ["T5_ONLINE_DIR"] = os.path.join(d, "user")
        self.addCleanup(os.environ.pop, "T5_ONLINE_DIR", None)
        st = core.Settings(os.path.join(d, "launcher.json"))
        st["out"] = os.path.join(d, "native")
        st["language"] = lang
        self.addCleanup(core.apply_language, {"language": "en"})
        mod = ti.load_launcher()
        try:
            app = mod.App(offscreen=False, settings=st)
        except ti.tk.TclError as e:
            self.skipTest(f"no display: {e}")
        app.withdraw()
        ti.cancel_timers(app)

        def close():
            ti.cancel_timers(app)
            app.online.on_close()
            app.destroy()
        self.addCleanup(close)
        return app

    def click(self, app, btn):
        """The button pressed and released inside the main loop (what a mouse click does to a ttk button)."""
        def press():
            btn.invoke()
            app.after(50, app.quit)
        app.after(20, press)
        app.after(5000, app.quit)
        t0 = time.monotonic()
        app.mainloop()
        self.assertLess(time.monotonic() - t0, 4.5)

    def test_the_button_opens_the_invite(self):
        self.assertEqual(core.DISCORD_URL, "https://discord.gg/4DwDHAkk2x")
        app = self.app()
        btn = app.discord_btn
        self.assertEqual(str(btn.cget("text")), "Community Discord")
        self.assertIs(btn.master, app.updater.button.master)              # in the header, beside the updates
        opened = []
        with mock.patch("webbrowser.open", lambda url, *a, **k: opened.append(url) or True):
            self.click(app, btn)
        self.assertEqual(opened, [core.DISCORD_URL])
        self.assertNotIn("discord.gg", app.status.get())

    def test_no_browser_shows_the_address(self):
        app = self.app()
        with mock.patch("webbrowser.open", lambda url, *a, **k: False):
            self.click(app, app.discord_btn)
        self.assertIn(core.DISCORD_URL, app.status.get())

    def test_translated(self):
        app = self.app("de")
        self.assertEqual(str(app.discord_btn.cget("text")), "Community-Discord")


if __name__ == "__main__":
    unittest.main()
