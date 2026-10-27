"""The Build, Play offline and Settings tabs in the Online tab's look (launcher/tab_look.py, 1.1.5): cards with their
title inside, every control on the card's ground -- also a style the launcher sets later -- and nothing changes
without the dark theme."""
import os
import shutil
import sys
import tempfile
import unittest

from helpers import ROOT

sys.path.insert(0, os.path.join(ROOT, "launcher"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_i18n as ti  # noqa: E402

CARD_OK = ("Card.", "CardBody.", "Tile.")


def card_style(style):
    return style.startswith(CARD_OK) or ".Card." in style


@unittest.skipIf(ti.tk is None, "no tkinter")
class TabLookTest(ti.Base):
    def launcher(self, language="en"):
        import core
        from t5lobby import i18n
        self.dir = tempfile.mkdtemp(prefix="t5dr-look")
        self.addCleanup(shutil.rmtree, self.dir, True)
        os.environ["T5_ONLINE_DIR"] = os.path.join(self.dir, "user")
        self.addCleanup(os.environ.pop, "T5_ONLINE_DIR", None)
        st = core.Settings(os.path.join(self.dir, "launcher.json"))
        st["language"] = language
        st["out"] = os.path.join(self.dir, "native")
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
            i18n.set_language("en")
        self.addCleanup(close)
        return app

    def walk(self, w):
        for c in w.winfo_children():
            yield c
            yield from self.walk(c)

    def test_cards_and_their_controls(self):
        app = self.launcher()
        if getattr(app, "theme", None) is None:
            self.skipTest("no dark theme (lobby/ missing)")
        look = app.tab_look
        frames = [w for key in ("build", "settings") for w in self.walk(app.tabs[key])
                  if w.winfo_class() == "TLabelframe"]
        self.assertGreaterEqual(len(frames), 10)
        for lf in frames:
            self.assertEqual(str(lf.cget("style")), "Card.TLabelframe")
        self.assertIn("Your game", [str(lf.cget("text")) for lf in frames])      # (the title as it was written)
        play = [w for w in app.tabs["play"].winfo_children() if w.winfo_class() == "TFrame"][0]
        self.assertEqual(str(play.cget("style")), "Card.TFrame")
        bad = []
        for card in look.cards:
            for w in self.walk(card):
                cls = w.winfo_class()
                if not hasattr(w, "cget") or cls in look_keep() or cls in ("TLabelframe",):
                    continue
                try:
                    style = str(w.cget("style")) or cls
                except ti.tk.TclError:
                    continue                                    # (a tk widget)
                if not card_style(style):
                    bad.append(f"{w} {cls} {style}")
        self.assertEqual(bad, [])
        # styles the launcher sets later land on the card's variant
        app.pkg_lbl.configure(style="ok.TLabel")
        self.assertEqual(str(app.pkg_lbl.cget("style")), "Card.ok.TLabel")
        step = next(iter(app.step_lbls.values()))
        step.configure(style="StepRun.TLabel")
        self.assertTrue(card_style(str(step.cget("style"))), step.cget("style"))
        from tkinter import ttk
        st = ttk.Style(app)
        self.assertEqual(st.lookup(str(step.cget("style")), "background"), app.theme.C["surface"])
        self.assertEqual(st.lookup(str(step.cget("style")), "foreground"), st.lookup("StepRun.TLabel", "foreground"))
        app.state_lbl.config(style="warn.TLabel")
        self.assertEqual(str(app.state_lbl.cget("style")), "Card.warn.TLabel")
        # a wrapping check box keeps its wrap length on the card
        wrapped = [w for c in look.cards for w in self.walk(c) if ".Card.TCheckbutton" in str(getattr(w, "cget",
                   lambda k: "")("style") if w.winfo_class() == "TCheckbutton" else "")]
        self.assertTrue(wrapped)
        s = str(wrapped[0].cget("style"))
        self.assertEqual(st.lookup(s, "wraplength"), st.lookup(s.replace(".Card.", "."), "wraplength"))

    def test_without_the_theme_nothing_changes(self):
        import tab_look

        class App:
            theme = None
            tabs = {"build": None}
        self.assertIsNone(tab_look.apply(App()))


class ShippedTest(unittest.TestCase):
    def test_every_launcher_module_is_in_the_release_zip(self):
        # a module the launcher imports and the zip lacks: the released launcher does not start at all
        import glob
        from helpers import load_tool
        package = load_tool("package_release")
        ours = set(package.OUR_FILES)
        mods = {"launcher/" + os.path.basename(p) for p in glob.glob(os.path.join(ROOT, "launcher", "*.py"))}
        self.assertEqual(sorted(mods - ours), [])


def look_keep():
    import tab_look
    return tab_look.KEEP


if __name__ == "__main__":
    unittest.main()
