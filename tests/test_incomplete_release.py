"""An incomplete release folder (1.1.7): a release install that lacks parts of the zip (deps/ps3recomp with its
.t5dr-vendored.json, toolchain/llvm, runtime/, python/) -- an "Extract All" cut short, or the launcher run from inside
the zip. 1.1.6 called it "ps3recomp source missing" and offered to install Git with winget (a player pressed it and
nothing changed). Now the Build tab says the folder is incomplete and to extract the zip again into a short path,
the build's deps step says the same, and "Install missing..." is only for tools that can really be installed."""
import argparse
import io
import os
import shutil
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from helpers import ROOT, load_tool

for _sub in ("tools", "lobby", "launcher"):
    _d = os.path.join(ROOT, _sub)
    if _d not in sys.path:
        sys.path.insert(0, _d)


def put(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def release_layout(d, without=()):
    """A release folder's skeleton (what package_release.py puts in the zip that prereqs looks at)."""
    put(os.path.join(d, "release.json"), '{"version": "1.1.7", "prebuilt_host": true}')
    files = {"deps": [os.path.join("deps", "ps3recomp", ".t5dr-vendored.json")],
             "llvm": [os.path.join("toolchain", "llvm", "bin", n) for n in ("clang-cl.exe", "lld-link.exe")],
             "runtime": [os.path.join("runtime", n) for n in ("t5dr.exe", "t5dr.lib")],
             "python": [os.path.join("python", n) for n in ("python.exe", "pythonw.exe")]}
    for part, names in files.items():
        if part not in without:
            for n in names:
                put(os.path.join(d, n), "{}")
    return d


@unittest.skipUnless(os.name == "nt", "the release layout checked here is the Windows one")
class Prereqs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="t5dr-incomplete")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.pr = load_tool("prereqs")

    def items(self, root, git="C:\\Program Files\\Git\\cmd\\git.exe"):
        with mock.patch.object(self.pr, "ROOT", root), \
                mock.patch.object(self.pr, "PF", os.path.join(self.tmp, "Program Files")), \
                mock.patch.object(self.pr.shutil, "which", lambda name: git if name == "git" else None), \
                mock.patch.object(self.pr, "_clang_version", lambda exe: (23, 1)):
            return {it["id"]: it for it in self.pr.check()}, self.pr.release_missing()

    def test_missing_ps3recomp_never_offers_git(self):
        root = release_layout(os.path.join(self.tmp, "T5DR"), without=("deps",))
        for git in (None, "C:\\Program Files\\Git\\cmd\\git.exe"):
            items, missing = self.items(root, git)
            self.assertFalse(items["ps3recomp"]["ok"])
            self.assertIsNone(items["ps3recomp"]["install"])
            self.assertIn("extract the release zip again", items["ps3recomp"]["detail"])
            self.assertFalse([it for it in items.values() if it["install"]], items)   # nothing to install at all
            self.assertEqual(missing, [os.path.join("deps", "ps3recomp")])

    def test_missing_runtime_never_offers_visual_studio(self):
        root = release_layout(os.path.join(self.tmp, "T5DR"), without=("runtime", "llvm"))
        items, missing = self.items(root)
        self.assertFalse(items["runtime"]["ok"])
        self.assertFalse(items["llvm"]["ok"])
        self.assertNotIn("msvc", items)
        self.assertFalse([it for it in items.values() if it["install"]], items)
        self.assertEqual(missing, [os.path.join("toolchain", "llvm"), "runtime"])

    def test_complete_release_and_dev_checkout(self):
        root = release_layout(os.path.join(self.tmp, "T5DR"))
        items, missing = self.items(root)
        self.assertEqual(missing, [])
        self.assertTrue(items["ps3recomp"]["ok"] and items["runtime"]["ok"] and items["llvm"]["ok"], items)
        dev = os.path.join(self.tmp, "checkout")                     # no release.json: Git is still offered there
        os.makedirs(dev)
        items, missing = self.items(dev, git=None)
        self.assertEqual(missing, [])
        self.assertEqual(items["ps3recomp"]["install"], "Git.Git")


@unittest.skipUnless(os.name == "nt", "the release layout checked here is the Windows one")
class DepsStep(unittest.TestCase):
    def test_deps_step_says_extract_again(self):
        bg = load_tool("build_game")
        tmp = tempfile.mkdtemp(prefix="t5dr-incomplete")
        self.addCleanup(shutil.rmtree, tmp, True)
        root = release_layout(os.path.join(tmp, "T5DR"), without=("deps",))
        with mock.patch.object(bg.prereqs, "ROOT", root), mock.patch.object(bg, "P", bg.Paths(
                os.path.join(root, "native"), os.path.join(root, "deps", "ps3recomp"))), \
                mock.patch.object(bg, "run", lambda *a, **k: self.fail("must not clone with Git")), \
                mock.patch.object(bg.shutil, "which", lambda name: "git"), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            with self.assertRaises(bg.BuildError) as cm:
                bg.step_deps(argparse.Namespace(pkg=None, rap=None, force=False))
        self.assertIn("This folder is incomplete (deps\\ps3recomp missing). Extract the release zip again with "
                      "\"Extract All\" into a short path such as C:\\T5DR", str(cm.exception))


try:
    import test_i18n as ti
except ImportError:      # pragma: no cover
    ti = None


@unittest.skipUnless(os.name == "nt" and ti is not None and ti.tk is not None, "Windows with tkinter")
class BuildTab(ti.Base if ti else unittest.TestCase):
    def test_build_tab_says_incomplete_and_offers_nothing(self):
        core = ti.core
        tmp = tempfile.mkdtemp(prefix="t5dr-incomplete")
        self.addCleanup(shutil.rmtree, tmp, True)
        root = release_layout(os.path.join(tmp, "T5DR"), without=("deps",))
        os.environ["T5_ONLINE_DIR"] = os.path.join(tmp, "user")
        self.addCleanup(os.environ.pop, "T5_ONLINE_DIR", None)
        st = core.Settings(os.path.join(root, "launcher.json"))
        st["out"] = os.path.join(root, "native")
        st["language"] = "en"
        for p in (mock.patch.object(core.prereqs, "ROOT", root), mock.patch.object(core, "ROOT", root),
                  mock.patch.object(core.prereqs.shutil, "which", lambda name: "git" if name == "git" else None),
                  mock.patch.object(core.prereqs, "_clang_version", lambda exe: (23, 1))):
            p.start()
            self.addCleanup(p.stop)
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
        app.after(10, app.refresh_prereqs)              # the real check, in its thread, in a real main loop
        t_end = time.monotonic() + 30

        def poll():
            if getattr(app, "prereq_items", None) or time.monotonic() > t_end:
                app.quit()
            else:
                app.after(50, poll)
        app.after(50, poll)
        app.mainloop()
        self.assertTrue(app.prereq_items)
        self.assertEqual(str(app.install_btn.cget("state")), "disabled")
        self.assertIn("This folder is incomplete", app.status.get())
        texts = "\n".join(ti.all_texts(app))
        self.assertIn("This folder is incomplete (deps\\ps3recomp missing). Extract the release zip again", texts)
        self.assertNotIn("Git", " ".join(app.tools_tv.item(i, "values")[1] for i in app.tools_tv.get_children()))


if __name__ == "__main__":
    unittest.main()
