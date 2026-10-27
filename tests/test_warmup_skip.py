"""Skip warm-up (1.1.5): the Build tab's button while the Shaders step runs ends tools/shader_warmup.py at once; the
game is asked to quit, warmup.json says skipped, the exit code stays 0 -- the build ends as built and the game works."""
import io
import json
import os
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from unittest import mock

from helpers import ROOT

for _d in ("launcher", "lobby", "tools"):
    if os.path.join(ROOT, _d) not in sys.path:
        sys.path.append(os.path.join(ROOT, _d))
import core  # noqa: E402

_path = list(sys.path)
import shader_warmup as w  # noqa: E402
sys.path[:] = _path        # (it puts lobby/ in front: test_smoke's late "import run" would find lobby/run.py)


class FakeProc:
    def __init__(self, *a, **k):
        self.returncode = None
        self.killed = False

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.returncode = 0
        return 0

    def kill(self):
        self.killed = True
        self.returncode = -9


class FakeControl:
    sent = []

    def __init__(self, d):
        FakeControl.sent = []

    def send(self, cmd, **kw):
        FakeControl.sent.append(cmd)

    def state(self):
        return {}


class Skip(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.out = self.tmp.name
        self.exe = os.path.join(self.out, "build", "cmake", "t5dr.exe")
        elf = os.path.join(self.out, "game", "vfs", "PS3_GAME", "USRDIR", "EBOOT.elf")
        for f in (self.exe, elf):
            os.makedirs(os.path.dirname(f), exist_ok=True)
            open(f, "wb").close()
        self.skip = os.path.join(self.out, w.SKIP_FILE)

    def run_warmup(self, play):
        import t5lobby.match_driver as md
        argv = ["shader_warmup.py", "--out", self.out]
        with redirect_stdout(io.StringIO()) as out, mock.patch.object(sys, "argv", argv), \
                mock.patch.object(w.subprocess, "Popen", FakeProc), mock.patch.object(w, "play", play), \
                mock.patch.object(md, "Control", FakeControl), mock.patch.object(w.sys, "platform", "win32"):
            rc = w.main()
        return rc, out.getvalue()

    def marker(self):
        with open(os.path.join(self.out, w.CACHE, w.MARKER), encoding="utf-8") as f:
            return json.load(f)

    def test_skip_ends_the_warmup_and_the_build_goes_on(self):
        def play(ctl, status, p, lines, secs, t_end, pad, skip=None):
            self.assertEqual(skip, self.skip)
            raise w.Skipped(3)
        rc, out = self.run_warmup(play)
        self.assertEqual(rc, 0)                                          # never fails the build
        self.assertIn("skipped after 3 of 18 fights", out)
        self.assertEqual(FakeControl.sent, ["quit"])                      # the game was asked to quit
        m = self.marker()
        self.assertEqual((m["exe"], m["fights"], m["skipped"]), (w.exe_stamp(self.exe), 3, True))
        self.assertFalse(os.path.exists(self.skip))
        rc, out = self.run_warmup(lambda *a, **k: self.fail("ran again"))   # the next BUILD GAME: not again
        self.assertIn("already done for this build", out)

    def test_skipped_before_it_started(self):
        os.makedirs(os.path.dirname(self.skip), exist_ok=True)
        open(self.skip, "w").close()
        rc, out = self.run_warmup(lambda *a, **k: self.fail("started a game"))
        self.assertEqual(rc, 0)
        self.assertIn("skipped", out)

    def test_an_old_skip_file_is_not_this_builds(self):
        os.makedirs(os.path.dirname(self.skip), exist_ok=True)
        open(self.skip, "w").close()
        old = time.time() - 2 * w.STALE_SKIP
        os.utime(self.skip, (old, old))
        played = []
        rc, out = self.run_warmup(lambda *a, **k: (played.append(1), 18)[1])
        self.assertEqual(played, [1])
        self.assertIn("done: 18 of 18", out)
        self.assertNotIn("skipped", self.marker())

    def test_play_notices_the_file_within_a_quarter_second(self):
        os.makedirs(os.path.dirname(self.skip), exist_ok=True)
        status = os.path.join(self.out, "status.json")
        pad = os.path.join(self.out, "pad.txt")
        proc = FakeProc()
        ctl = FakeControl(self.out)
        lines = w.fight_lines(2)
        open(self.skip, "w").close()
        t0 = time.monotonic()
        with redirect_stdout(io.StringIO()), self.assertRaises(w.Skipped) as cm:
            w.play(ctl, status, proc, lines, 0.5, time.time() + 60, pad, self.skip)
        self.assertLess(time.monotonic() - t0, 2.0)
        self.assertEqual(cm.exception.args[0], 0)

    def test_the_launcher_writes_the_file_the_warmup_reads(self):
        self.assertEqual(core.BuildRun.WARMUP_SKIP, w.SKIP_FILE)
        b = core.BuildRun("a.pkg", "b.rap", self.out)
        self.assertFalse(b.skip_warmup())                                 # no build running: nothing
        b.proc = FakeProc()
        self.assertTrue(b.skip_warmup())
        self.assertTrue(os.path.exists(self.skip))


try:
    import test_i18n as ti
except ImportError:      # pragma: no cover
    ti = None


@unittest.skipIf(ti is None or ti.tk is None, "no tkinter")
class Button(ti.Base if ti else unittest.TestCase):
    def test_shown_only_while_the_warmup_runs(self):
        import shutil
        d = tempfile.mkdtemp(prefix="t5dr-skipbtn")
        self.addCleanup(shutil.rmtree, d, True)
        os.environ["T5_ONLINE_DIR"] = os.path.join(d, "user")
        self.addCleanup(os.environ.pop, "T5_ONLINE_DIR", None)
        st = core.Settings(os.path.join(d, "launcher.json"))
        st["out"] = os.path.join(d, "native")
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
        asked = []

        class Build:
            def skip_warmup(self):
                asked.append(1)
                return True
        self.assertEqual(app.skip_btn.winfo_manager(), "")
        app.build, app.cur_step = Build(), "compile"
        app.skip_warmup()
        self.assertEqual(asked, [])                                        # only in the Shaders step
        app.cur_step = "shaders"
        app._show_skip_btn(True)
        self.assertEqual(app.skip_btn.winfo_manager(), "grid")
        app.skip_btn.invoke()
        self.assertEqual(asked, [1])
        self.assertEqual(str(app.skip_btn.cget("state")), "disabled")
        app._show_skip_btn(False)
        self.assertEqual(app.skip_btn.winfo_manager(), "")


if __name__ == "__main__":
    unittest.main()
