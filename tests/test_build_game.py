"""tools/build_game.py without a package: the pins, argument parsing and step
order, the deps step's commands (patch series in name order), and the steps
that must refuse to run without their inputs."""
import argparse
import os
import re
import sys
import tempfile
import unittest
from unittest import mock

from helpers import ROOT, get, load_tool


class Pins(unittest.TestCase):
    def setUp(self):
        self.bg = load_tool("build_game")

    def test_pins_look_right(self):
        self.assertRegex(self.bg.PS3RECOMP_COMMIT, r"^[0-9a-f]{7,40}$")
        self.assertRegex(self.bg.ELF_SHA1, r"^[0-9a-f]{40}$")
        self.assertTrue(self.bg.PS3RECOMP_URL.startswith("https://github.com/"))
        self.assertEqual(self.bg.TITLE_ID, "NPUB30009")
        int(self.bg.CODE_END, 16)

    def test_every_step_has_a_function(self):
        self.assertEqual(self.bg.STEPS, ["deps", "keys", "unpack", "decrypt", "vfs", "lift", "spu", "compile"])
        for s in self.bg.STEPS:
            self.assertTrue(callable(getattr(self.bg, "step_" + s, None)), s)

    def test_outputs_stay_in_ignored_dirs(self):
        # Everything build_game writes must land where .gitignore keeps it
        # out of this public repository.
        ignored = get(os.path.join(ROOT, ".gitignore")).decode().split()
        for name in ("DEPS", "GAME", "OUT", "RECOMP", "CMAKE_BUILD", "SPU"):
            rel = os.path.relpath(getattr(self.bg, name), ROOT).replace(os.sep, "/")
            self.assertIn(rel.split("/")[0] + "/", ignored, f"{name} = {rel}")


class Arguments(unittest.TestCase):
    """main() parses argv and calls step_<name>(args) in pipeline order."""

    def run_main(self, argv):
        bg = load_tool("build_game")
        calls = []
        patches = {f"step_{s}": (lambda s: lambda a: calls.append((s, a)))(s) for s in bg.STEPS}
        cwd = os.getcwd()
        try:
            with mock.patch.object(sys, "argv", ["build_game.py"] + argv), \
                 mock.patch.dict(bg.__dict__, patches), mock.patch("builtins.print"):
                bg.main()
        finally:
            os.chdir(cwd)
        return calls

    def test_default_runs_every_step_in_order(self):
        calls = self.run_main(["--pkg", "a.pkg", "--rap", "b.rap"])
        self.assertEqual([s for s, _ in calls], load_tool("build_game").STEPS)
        a = calls[0][1]
        self.assertEqual((a.pkg, a.rap, a.force), ("a.pkg", "b.rap", False))

    def test_steps_run_in_pipeline_order_not_argv_order(self):
        calls = self.run_main(["--steps", "compile", "deps", "spu", "--force"])
        self.assertEqual([s for s, _ in calls], ["deps", "spu", "compile"])
        self.assertTrue(calls[0][1].force)
        self.assertIsNone(calls[0][1].pkg)

    def test_unknown_step_is_rejected(self):
        with mock.patch("sys.stderr"):
            with self.assertRaises(SystemExit) as cm:
                self.run_main(["--steps", "decrypt", "upload"])
        self.assertEqual(cm.exception.code, 2)


class Steps(unittest.TestCase):
    def setUp(self):
        self.bg = load_tool("build_game")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def args(self, **kw):
        return argparse.Namespace(**{"pkg": None, "rap": None, "force": False, **kw})

    def test_deps_clones_pin_and_applies_patches_in_name_order(self):
        cmds = []
        deps = os.path.join(self.tmp.name, "ps3recomp")
        with mock.patch.object(self.bg, "DEPS", deps), \
             mock.patch.object(self.bg, "run", lambda cmd, **kw: cmds.append([str(c) for c in cmd])):
            self.bg.step_deps(self.args())
        self.assertEqual(cmds[0][-4:], ["-b", self.bg.PS3RECOMP_BRANCH, self.bg.PS3RECOMP_URL, deps])
        self.assertEqual(cmds[1][-1], self.bg.PS3RECOMP_COMMIT)
        applied = [os.path.basename(c[-1]) for c in cmds if "apply" in c]
        series = sorted(n for n in os.listdir(os.path.join(ROOT, "patches", "ps3recomp")) if n.endswith(".patch"))
        self.assertEqual(applied, series)
        self.assertTrue(applied, "no patches found")
        self.assertIn("requirements.txt", cmds[-1][-1])

    def test_deps_skips_existing_checkout(self):
        deps = os.path.join(self.tmp.name, "ps3recomp")
        os.makedirs(os.path.join(deps, ".git"))
        with mock.patch.object(self.bg, "DEPS", deps), \
             mock.patch.object(self.bg, "run", lambda *a, **k: self.fail("must not run anything")):
            self.bg.step_deps(self.args())

    def test_unpack_needs_pkg(self):
        with mock.patch.object(self.bg, "PKG_DIR", os.path.join(self.tmp.name, "pkg")):
            with self.assertRaises(SystemExit) as cm:
                self.bg.step_unpack(self.args())
        self.assertIn("--pkg", str(cm.exception.code))

    def test_decrypt_needs_rap(self):
        with mock.patch.object(self.bg, "ELF", os.path.join(self.tmp.name, "EBOOT.elf")):
            with self.assertRaises(SystemExit) as cm:
                self.bg.step_decrypt(self.args())
        self.assertIn("--rap", str(cm.exception.code))

    def test_decrypt_rejects_other_versions(self):
        # A "decryptor" that writes the wrong program: the SHA-1 pin must stop it.
        elf = os.path.join(self.tmp.name, "EBOOT.elf")

        def fake_run(cmd, **kw):
            with open(elf, "wb") as f:
                f.write(b"not the supported version")
        with mock.patch.object(self.bg, "ELF", elf), mock.patch.object(self.bg, "run", fake_run):
            with self.assertRaises(SystemExit) as cm:
                self.bg.step_decrypt(self.args(rap="x.rap"))
        self.assertRegex(str(cm.exception.code), re.escape(self.bg.ELF_SHA1))

    def test_sha1(self):
        p = os.path.join(self.tmp.name, "f")
        with open(p, "wb") as f:
            f.write(b"abc")
        self.assertEqual(self.bg.sha1(p), "a9993e364706816aba3e25717850c26c9cd0d89d")


if __name__ == "__main__":
    unittest.main()
