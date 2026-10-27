"""A build step that hangs is visible (1.1.5, GitHub #27: a BUILD GAME seemed stuck all night). Every step that
printed nothing for its own time (core.QUIET_S) gets a hint in the Build tab naming the step and the program it
started last; the hint also goes to the log view, build.log and launcher.log once per quiet stretch. The translation
step keeps its own words (test_lift_robust). While the build runs Windows does not go to sleep. No game needed."""
import io
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for sub in ("tools", "lobby", "launcher"):
    p = os.path.join(ROOT, sub)
    if p not in sys.path:
        sys.path.insert(0, p)

import core  # noqa: E402
from t5lobby import i18n  # noqa: E402


class FakeProc:
    pid = 0

    def __init__(self, lines):
        self.stdout = io.BytesIO("".join(ln + "\n" for ln in lines).encode("utf-8"))

    def wait(self, timeout=None):
        return 0

    def poll(self):
        return 0


def drain(b):
    out = []
    while not b.events.empty():
        out.append(b.events.get_nowait())
    return out


class Tool(unittest.TestCase):
    def test_started_tool(self):
        st = core.started_tool
        self.assertEqual(st(r'  > C:\T5DR\python\python.exe "C:\T5DR\deps\ps3recomp\tools\pkg_extract.py" '
                            r'"C:\Users\A B\x.pkg" C:\T5DR\native\game\pkg'), "pkg_extract.py")
        self.assertEqual(st(r'  > "C:\Program Files\LLVM\bin\clang-cl.exe" /c x.cpp'), "clang-cl.exe")
        self.assertEqual(st("  > git -c core.longpaths=true clone x"), "git")
        self.assertIsNone(st("[unpack]"))
        self.assertIsNone(st("  PS3LOGO.DAT  (5120 bytes)"))


class Hint(unittest.TestCase):
    def tearDown(self):
        i18n.set_language("en")

    def test_every_step_has_a_time(self):
        self.assertEqual(set(core.QUIET_S), set(core.build_game.STEPS))
        self.assertEqual(core.QUIET_S["lift"], core.LIFT_QUIET_S)
        for step, limit in core.QUIET_S.items():
            self.assertIsNone(core.step_quiet_hint(step, limit - 0.1), step)
            self.assertIsNotNone(core.step_quiet_hint(step, limit), step)
        self.assertIsNone(core.step_quiet_hint(None, 99999))

    def test_step_titles(self):
        for step, title in core.STEP_TITLES.items():
            self.assertEqual(core.step_title(step), title)          # (written out twice: the same English)

    def test_words(self):
        h = core.step_quiet_hint("unpack", 185, "pkg_extract.py")
        self.assertEqual(h, 'The step "Unpack" has printed nothing for 3 minutes. On a slow or busy PC it may still be '
                            "working. If nothing changes, press Cancel and then BUILD GAME again; build.log has the "
                            "details. Last program started: pkg_extract.py.")
        self.assertIn("translation step", core.step_quiet_hint("lift", 200, "ppu_lifter.py"))
        self.assertTrue(core.step_quiet_hint("lift", 200, "ppu_lifter.py").endswith("ppu_lifter.py."))
        self.assertNotIn("Last program", core.step_quiet_hint("compile", 700))

    def test_german(self):
        i18n.set_language("de")
        i18n.clear_missing()
        h = core.step_quiet_hint("compile", 660, "build_game_dll.py")
        self.assertEqual(i18n.missing(), [])
        self.assertIn("Kompilieren", h)
        self.assertIn("11 Minuten", h)
        self.assertIn("build_game_dll.py", h)


class Run(unittest.TestCase):
    def test_tool_and_hint_in_the_logs(self):
        with tempfile.TemporaryDirectory() as d:
            b = core.BuildRun(None, None, d)
            b.proc = FakeProc(["[decrypt]", "  already done", "[unpack]",
                               r'  > C:\py\python.exe C:\x\tools\pkg_extract.py a.pkg out', "  PARAM.SFO  (976 bytes)"])
            with mock.patch.object(core, "keep_awake") as awake:
                b._pump()
            self.assertEqual([c.args for c in awake.call_args_list], [(True,), (False,)])
            self.assertEqual((b.step, b.tool), ("unpack", "pkg_extract.py"))
            drain(b)
            log = io.StringIO()
            b._log = log
            logged = []
            with mock.patch.object(core, "log", logged.append):
                self.assertIsNone(b.quiet_hint(now=b.last_output + 100))
                h = b.quiet_hint(now=b.last_output + 200)
                self.assertIsNotNone(b.quiet_hint(now=b.last_output + 260))     # the detail line keeps it ...
            self.assertIn("Unpack", h)
            self.assertEqual(drain(b), [("line", "[launcher] " + h)])          # ... the logs get it once
            self.assertEqual(log.getvalue(), "[launcher] " + h + "\n")
            self.assertEqual(logged, ["build: step unpack printed nothing for 200 s (pkg_extract.py)"])
            # the next step starts with no program of its own yet
            b.proc = FakeProc(["[vfs]"])
            b._pump()
            self.assertEqual((b.step, b.tool), ("vfs", None))

    def test_keep_awake(self):
        if os.name != "nt":
            self.skipTest("Windows only")
        calls = []
        fake = mock.Mock()
        fake.kernel32.SetThreadExecutionState = lambda flags: calls.append(flags)
        with mock.patch.object(core.ctypes, "windll", fake):
            core.keep_awake(True)
            core.keep_awake(False)
        self.assertEqual(calls, [0x80000001, 0x80000000])


if __name__ == "__main__":
    unittest.main()
