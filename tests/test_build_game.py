"""tools/build_game.py without a package: the pins, the output layout,
argument parsing and step order, the deps step's commands (patches in name
order), and the steps that must refuse to run without their inputs or with the
wrong game."""
import argparse
import io
import os
import struct
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from helpers import ROOT, get, load_tool, put


def make_sfo(entries):
    """A PARAM.SFO with UTF-8 string entries, in the layout build_game.read_sfo reads."""
    keys, data, idx = b"", b"", b""
    for k, v in entries.items():
        raw = v.encode() + b"\0"
        idx += struct.pack("<HHIII", len(keys), 0x0204, len(raw), len(raw), len(data))
        keys += k.encode() + b"\0"
        data += raw
    key_tab = 0x14 + len(idx)
    data_tab = key_tab + len(keys)
    return b"\0PSF" + struct.pack("<IIII", 0x101, key_tab, data_tab, len(entries)) + idx + keys + data


class Pins(unittest.TestCase):
    def setUp(self):
        self.bg = load_tool("build_game")

    def test_pins_look_right(self):
        bg = self.bg
        self.assertRegex(bg.PS3RECOMP_COMMIT, r"^[0-9a-f]{7,40}$")
        self.assertRegex(bg.ELF_SHA1, r"^[0-9a-f]{40}$")
        self.assertTrue(bg.PS3RECOMP_URL.startswith("https://github.com/"))
        self.assertEqual(bg.TITLE_ID, "NPUB30009")
        self.assertIn(bg.TITLE_ID, bg.CONTENT_ID)
        int(bg.CODE_END, 16)

    def test_every_step_has_a_function(self):
        self.assertEqual(self.bg.STEPS, ["deps", "keys", "decrypt", "unpack", "vfs", "lift", "spu", "compile"])
        for s in self.bg.STEPS:
            self.assertTrue(callable(getattr(self.bg, "step_" + s, None)), s)

    def test_default_outputs_stay_in_ignored_dirs(self):
        # With no --out, everything build_game writes must land where
        # .gitignore keeps it out of this public repository.
        ignored = get(os.path.join(ROOT, ".gitignore")).decode().split()
        p = self.bg.Paths(ROOT)
        for name in ("deps", "keys", "game", "elf", "vfs", "build", "recomp", "cmake", "spu", "exe"):
            rel = os.path.relpath(getattr(p, name), ROOT).replace(os.sep, "/")
            self.assertIn(rel.split("/")[0] + "/", ignored, f"{name} = {rel}")

    def test_out_moves_everything(self):
        with tempfile.TemporaryDirectory() as d:
            p = self.bg.Paths(d)
            for name in ("keys", "game", "pkg_dir", "elf", "vfs", "build", "recomp", "cmake", "spu", "exe"):
                self.assertTrue(os.path.abspath(getattr(p, name)).startswith(os.path.abspath(d)), name)
            self.assertEqual(p.deps, os.path.join(ROOT, "deps", "ps3recomp"))   # not moved unless --deps

    def test_code_id_tracks_the_patches(self):
        bg = self.bg
        a = bg.code_id()
        self.assertRegex(a, r"^[0-9a-f]{16}$")
        with mock.patch.object(bg, "patch_digest", lambda: "something else"):
            self.assertNotEqual(bg.code_id(), a)


class Arguments(unittest.TestCase):
    """main() parses argv and calls step_<name>(args) in pipeline order."""

    def run_main(self, argv, steps=None):
        bg = load_tool("build_game")
        calls = []
        patches = {f"step_{s}": (lambda s: lambda a: calls.append((s, a)))(s) for s in bg.STEPS}
        patches.update(steps(bg) if steps else {})
        out, err = io.StringIO(), io.StringIO()
        cwd = os.getcwd()
        code = 0
        with tempfile.TemporaryDirectory() as d:
            try:
                with mock.patch.object(sys, "argv", ["build_game.py", "--out", d] + argv), \
                     mock.patch.dict(bg.__dict__, patches), redirect_stdout(out), redirect_stderr(err):
                    bg.main()
            except SystemExit as e:
                code = e.code
            finally:
                os.chdir(cwd)
        return calls, code, out.getvalue(), err.getvalue()

    def test_default_runs_every_step_in_order(self):
        calls, code, out, _ = self.run_main(["--pkg", "a.pkg", "--rap", "b.rap"])
        self.assertEqual(code, 0)
        self.assertEqual([s for s, _ in calls], load_tool("build_game").STEPS)
        a = calls[0][1]
        self.assertEqual((a.pkg, a.rap, a.force), ("a.pkg", "b.rap", False))
        self.assertIn("[deps]", out)
        self.assertIn("[done]", out)

    def test_steps_run_in_pipeline_order_not_argv_order(self):
        calls, code, _, _ = self.run_main(["--steps", "compile", "deps", "spu", "--force"])
        self.assertEqual(code, 0)
        self.assertEqual([s for s, _ in calls], ["deps", "spu", "compile"])
        self.assertTrue(calls[0][1].force)
        self.assertIsNone(calls[0][1].pkg)

    def test_unknown_step_is_rejected(self):
        _, code, _, _ = self.run_main(["--steps", "decrypt", "upload"])
        self.assertEqual(code, 2)

    def test_build_error_is_one_plain_line_and_exit_2(self):
        def failing_decrypt(bg):
            def boom(a):
                raise bg.BuildError("Choose your game package (.pkg) first.")
            return {"step_decrypt": boom}
        calls, code, _, err = self.run_main(["--steps", "decrypt", "vfs"], failing_decrypt)
        self.assertEqual(code, 2)
        self.assertEqual(err.strip(), "ERROR: Choose your game package (.pkg) first.")
        self.assertEqual(calls, [])                  # nothing after the failed step

    def test_code_id_flag(self):
        calls, code, out, _ = self.run_main(["--code-id"])
        self.assertEqual((calls, code), ([], 0))
        self.assertRegex(out.strip(), r"^[0-9a-f]{16}$")


class Steps(unittest.TestCase):
    def setUp(self):
        self.bg = load_tool("build_game")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.deps = os.path.join(self.tmp.name, "ps3recomp")
        self.bg.P = self.bg.Paths(self.tmp.name, self.deps)
        self.quiet = redirect_stdout(io.StringIO())
        self.quiet.__enter__()
        self.addCleanup(self.quiet.__exit__, None, None, None)

    def args(self, **kw):
        return argparse.Namespace(**{"pkg": None, "rap": None, "force": False, **kw})

    def assertBuildError(self, fn, text):
        with self.assertRaises(self.bg.BuildError) as cm:
            fn()
        self.assertIn(text, str(cm.exception))

    def test_deps_clones_pin_and_applies_patches_in_name_order(self):
        cmds = []
        with mock.patch.object(self.bg, "run", lambda cmd, **kw: cmds.append([str(c) for c in cmd])), \
             mock.patch.object(self.bg.prereqs, "python_crypto", lambda: True), \
             mock.patch.object(self.bg.shutil, "which", lambda name: "git"):
            self.bg.step_deps(self.args())
        self.assertEqual(cmds[0][-4:], ["-b", self.bg.PS3RECOMP_BRANCH, self.bg.PS3RECOMP_URL, self.deps])
        self.assertEqual(cmds[1][-1], self.bg.PS3RECOMP_COMMIT)
        applied = [os.path.basename(c[-1]) for c in cmds if "apply" in c]
        series = sorted(n for n in os.listdir(os.path.join(ROOT, "patches", "ps3recomp")) if n.endswith(".patch"))
        self.assertTrue(applied, "no patches found")
        self.assertEqual(applied, series)
        self.assertEqual(len(cmds), 2 + len(series))

    def test_deps_skips_existing_checkout(self):
        os.makedirs(os.path.join(self.deps, ".git"))
        with mock.patch.object(self.bg, "run", lambda *a, **k: self.fail("must not run anything")), \
             mock.patch.object(self.bg.prereqs, "python_crypto", lambda: True):
            self.bg.step_deps(self.args())

    def test_deps_vendored_copy_must_match_the_patches(self):
        os.makedirs(self.deps)
        stamp = os.path.join(self.deps, ".t5dr-vendored.json")
        put(stamp, '{"commit": "%s", "patches": "%s"}' % (self.bg.PS3RECOMP_COMMIT, self.bg.patch_digest()))
        with mock.patch.object(self.bg, "run", lambda *a, **k: self.fail("must not run anything")), \
             mock.patch.object(self.bg.prereqs, "python_crypto", lambda: True):
            self.bg.step_deps(self.args())                 # matches: nothing to fetch
            put(stamp, '{"commit": "%s", "patches": "stale"}' % self.bg.PS3RECOMP_COMMIT)
            self.assertBuildError(lambda: self.bg.step_deps(self.args()), "does not match this version")

    def test_decrypt_needs_a_16_byte_rap(self):
        self.assertBuildError(lambda: self.bg.step_decrypt(self.args()), "license file (.rap)")
        rap = os.path.join(self.tmp.name, "x.rap")
        put(rap, b"\1" * 15)
        self.assertBuildError(lambda: self.bg.step_decrypt(self.args(rap=rap)), "exactly 16 bytes")

    def test_need_pkg(self):
        self.assertBuildError(lambda: self.bg.need_pkg(self.args()), "package (.pkg)")
        self.assertBuildError(lambda: self.bg.need_pkg(self.args(pkg=os.path.join(self.tmp.name, "no.pkg"))),
                              "does not exist")
        bogus = os.path.join(self.tmp.name, "theme.pkg")
        put(bogus, b"PK\3\4" + bytes(200))
        self.assertBuildError(lambda: self.bg.need_pkg(self.args(pkg=bogus)), "is not a PS3 package")
        good = os.path.join(self.tmp.name, "game.pkg")
        hdr = bytearray(0x60)
        hdr[0:4] = b"\x7fPKG"
        hdr[0x30:0x30 + len(self.bg.CONTENT_ID)] = self.bg.CONTENT_ID.encode()
        put(good, bytes(hdr))
        self.assertEqual(self.bg.need_pkg(self.args(pkg=good)), self.bg.CONTENT_ID)

    def test_read_sfo(self):
        p = os.path.join(self.tmp.name, "PARAM.SFO")
        put(p, make_sfo({"TITLE": "Some Game", "TITLE_ID": "BLUS00000", "APP_VER": "01.00"}))
        self.assertEqual(self.bg.read_sfo(p), {"TITLE": "Some Game", "TITLE_ID": "BLUS00000", "APP_VER": "01.00"})
        put(p, b"not an sfo")
        self.assertEqual(self.bg.read_sfo(p), {})

    def stage_package(self, title_id):
        """EBOOT.BIN + PARAM.SFO already taken out of the package, as decrypt leaves them."""
        usr = os.path.join(self.bg.P.pkg_dir, "USRDIR")
        os.makedirs(usr)
        put(os.path.join(usr, "EBOOT.BIN"), b"SCE\0")
        put(os.path.join(self.bg.P.pkg_dir, "PARAM.SFO"),
            make_sfo({"TITLE": "Some Game", "TITLE_ID": title_id, "APP_VER": "01.00"}))
        rap = os.path.join(self.tmp.name, "x.rap")
        put(rap, b"\1" * 16)
        return rap

    def test_decrypt_refuses_another_title(self):
        rap = self.stage_package("BLUS00000")
        with mock.patch.object(self.bg, "run", lambda *a, **k: self.fail("must not decrypt")):
            self.assertBuildError(lambda: self.bg.step_decrypt(self.args(rap=rap)), "The port needs")

    def test_decrypt_refuses_another_version(self):
        # A "decryptor" that writes a different program: the SHA-1 pin must stop it.
        rap = self.stage_package(self.bg.TITLE_ID)
        os.makedirs(os.path.dirname(self.bg.P.elf), exist_ok=True)

        def fake_run(cmd, **kw):
            put(self.bg.P.elf, b"not the supported version")
            return "content id UP0000-OTHER0000_00-0000000000000000, license type 2\n"
        with mock.patch.object(self.bg, "run", fake_run):
            self.assertBuildError(lambda: self.bg.step_decrypt(self.args(rap=rap)), "different version")
        self.assertFalse(os.path.exists(self.bg.P.elf))      # the wrong program is not kept

    def test_sha1(self):
        p = os.path.join(self.tmp.name, "f")
        put(p, b"abc")
        self.assertEqual(self.bg.sha1(p), "a9993e364706816aba3e25717850c26c9cd0d89d")


if __name__ == "__main__":
    unittest.main()
