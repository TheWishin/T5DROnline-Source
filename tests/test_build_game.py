"""tools/build_game.py without a package: the pins, the output layout,
argument parsing and step order, the deps step's commands (patches in name
order), and the steps that must refuse to run without their inputs or with the
wrong game."""
import argparse
import io
import os
import shutil
import struct
import subprocess
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
        self.assertEqual(self.bg.STEPS, ["deps", "keys", "decrypt", "unpack", "vfs", "lift", "spu", "compile",
                                         "shaders"])
        # 1.1.5: the shader warm-up runs only when asked (--warmup, the launcher; or named in --steps)
        self.assertEqual(self.bg.DEFAULT_STEPS, self.bg.STEPS[:-1])
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


class PackageCheck(unittest.TestCase):
    """The launcher's line under the chosen .pkg (core.describe_pkg): both PSN content IDs of the supported
    package are green; another Tekken 5 DR package is a warning."""

    def setUp(self):
        for sub in ("tools", "lobby", "launcher"):
            d = os.path.join(ROOT, sub)
            if d not in sys.path:
                sys.path.insert(0, d)
        import core
        self.core = core
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def pkg(self, cid):
        p = os.path.join(self.tmp.name, cid + ".pkg")
        put(p, b"\x7fPKG" + bytes(0x2C) + cid.encode().ljust(0x24, b"\0") + bytes(0x40))
        return p

    def test_both_content_ids_are_supported(self):
        for cid in ("UP0700-NPUB30009_00-UPDATE0000010000", "UP0700-NPUB30009_00-0000000000010000"):
            ok, level, text = self.core.describe_pkg(self.pkg(cid))
            self.assertEqual((ok, level), (True, "ok"), text)
            self.assertIn(cid, text)

    def test_another_version_warns(self):
        ok, level, text = self.core.describe_pkg(self.pkg("UP0700-NPUB30009_00-UPDATE0000020000"))
        self.assertEqual((ok, level), (True, "warn"), text)


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
        self.assertEqual([s for s, _ in calls], load_tool("build_game").DEFAULT_STEPS)
        a = calls[0][1]
        self.assertEqual((a.pkg, a.rap, a.force), ("a.pkg", "b.rap", False))
        self.assertIn("[deps]", out)
        self.assertIn("[done]", out)

    def test_warmup_adds_the_shader_step(self):
        calls, code, _, _ = self.run_main(["--pkg", "a.pkg", "--rap", "b.rap", "--warmup"])
        self.assertEqual(code, 0)
        self.assertEqual([s for s, _ in calls], load_tool("build_game").STEPS)
        calls, code, _, _ = self.run_main(["--steps", "compile", "--warmup"])
        self.assertEqual([s for s, _ in calls], ["compile", "shaders"])

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

    def test_redo_every_step_keeps_the_bundled_ps3recomp(self):
        # "Redo every step" (--force) used to delete the release's ps3recomp copy and git-clone it again, which
        # failed on its read-only .git pack files ("Access is denied").
        os.makedirs(self.deps)
        put(os.path.join(self.deps, ".t5dr-vendored.json"),
            '{"commit": "%s", "patches": "%s"}' % (self.bg.PS3RECOMP_COMMIT, self.bg.patch_digest()))
        with mock.patch.object(self.bg, "run", lambda *a, **k: self.fail("must not fetch")), \
             mock.patch.object(self.bg.prereqs, "python_crypto", lambda: True):
            self.bg.step_deps(self.args(force=True))
        self.assertTrue(os.path.exists(os.path.join(self.deps, ".t5dr-vendored.json")))

    def test_vendored_copy_with_git_files_is_never_prepared_again(self):
        # A release's copy (it may carry .git files) whose stamp names another series: an error, nothing touched --
        # the developer-checkout path (re-prepare) is never taken for it.
        os.makedirs(os.path.join(self.deps, ".git"))
        put(os.path.join(self.deps, ".t5dr-vendored.json"), '{"commit": "%s", "patches": "stale"}'
            % self.bg.PS3RECOMP_COMMIT)
        mkput(os.path.join(self.deps, "runtime", "x.c"), "release\n")
        with mock.patch.object(self.bg, "run", lambda *a, **k: self.fail("must not run anything")), \
             mock.patch.object(self.bg, "reprepare_checkout", lambda *a, **k: self.fail("must not re-prepare")), \
             mock.patch.object(self.bg.prereqs, "python_crypto", lambda: True):
            self.assertBuildError(lambda: self.bg.step_deps(self.args()), "does not match this version")
        self.assertEqual(get(os.path.join(self.deps, "runtime", "x.c")).replace(b"\r", b""), b"release\n")

    def test_rmtree_removes_read_only_files(self):
        d = os.path.join(self.tmp.name, "checkout", ".git", "objects", "pack")
        os.makedirs(d)
        f = os.path.join(d, "pack-1.idx")
        put(f, b"x")
        os.chmod(f, 0o444)
        self.bg.rmtree(os.path.join(self.tmp.name, "checkout"))
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, "checkout")))

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

    def fake_pkg(self, size=None):
        pkg = os.path.join(self.tmp.name, "game.pkg")
        hdr = bytearray(0x60)
        hdr[0:4] = b"\x7fPKG"
        hdr[0x30:0x30 + len(self.bg.CONTENT_ID)] = self.bg.CONTENT_ID.encode()
        put(pkg, bytes(hdr) + bytes((size or 0x60) - 0x60))
        return pkg

    def test_decrypt_takes_a_damaged_leftover_program_out_again(self):
        # An earlier run stopped while taking EBOOT.BIN out: an empty file stays behind. The next run must
        # take it out of the package again instead of failing with "not a SELF" for good.
        rap = self.stage_package(self.bg.TITLE_ID)
        eboot = os.path.join(self.bg.P.pkg_dir, "USRDIR", "EBOOT.BIN")
        put(eboot, b"")
        calls = []

        def fake_run(cmd, **kw):
            cmd = [str(c) for c in cmd]
            calls.append(os.path.basename(cmd[1]))
            if "pkg_extract.py" in cmd[1] and cmd[-1] == "EBOOT.BIN":
                put(eboot, b"SCE\0" + bytes(0x2000))
            if "unself.py" in cmd[1]:
                put(self.bg.P.elf, b"decrypted")
            return ""
        with mock.patch.object(self.bg, "run", fake_run):
            self.assertBuildError(lambda: self.bg.step_decrypt(self.args(rap=rap, pkg=self.fake_pkg())),
                                  "different version")       # the fake program is not the pinned one
        self.assertEqual(calls, ["pkg_extract.py", "pkg_extract.py", "unself.py"])

    def test_decrypt_names_an_incomplete_package(self):
        rap = self.stage_package(self.bg.TITLE_ID)
        eboot = os.path.join(self.bg.P.pkg_dir, "USRDIR", "EBOOT.BIN")
        put(eboot, b"SCE\0" + bytes(0x2000))

        def failing_unself(cmd, **kw):
            raise subprocess.CalledProcessError(1, cmd, output="not a SELF")
        with mock.patch.object(self.bg, "run", failing_unself):
            self.assertBuildError(lambda: self.bg.step_decrypt(self.args(rap=rap, pkg=self.fake_pkg(0x1000))),
                                  "the download is incomplete")
            self.assertBuildError(lambda: self.bg.step_decrypt(self.args(rap=rap)), "Redo every step")

    def test_decrypt_takes_an_already_decrypted_program(self):
        # A re-packed package with the program already decrypted: no unself, the SHA-1 pin decides.
        rap = self.stage_package(self.bg.TITLE_ID)
        put(os.path.join(self.bg.P.pkg_dir, "USRDIR", "EBOOT.BIN"), b"\x7fELF" + bytes(0x2000))
        with mock.patch.object(self.bg, "run", lambda *a, **k: self.fail("must not decrypt")):
            self.assertBuildError(lambda: self.bg.step_decrypt(self.args(rap=rap)), "different version")
        self.assertFalse(os.path.exists(self.bg.P.elf))

    def test_sha1(self):
        p = os.path.join(self.tmp.name, "f")
        put(p, b"abc")
        self.assertEqual(self.bg.sha1(p), "a9993e364706816aba3e25717850c26c9cd0d89d")

    # -- another version (1.1.5: two players' v01.01 packages got ".rap does not belong") --

    def stage_version(self, sfo, program):
        rap = self.stage_package(self.bg.TITLE_ID)
        put(os.path.join(self.bg.P.pkg_dir, "PARAM.SFO"), make_sfo(sfo))
        put(os.path.join(self.bg.P.pkg_dir, "USRDIR", "EBOOT.BIN"), fake_self(program))
        return rap

    def test_decrypt_refuses_v0101_before_decrypting(self):
        rap = self.stage_version({"TITLE": "T5", "TITLE_ID": self.bg.TITLE_ID, "APP_VER": "01.01", "VERSION": "01.00"},
                                 "UP0700-NPUB30009_00-0000000000000000")
        with mock.patch.object(self.bg, "run", lambda *a, **k: self.fail("must not decrypt")):
            self.assertBuildError(lambda: self.bg.step_decrypt(self.args(rap=rap)),
                                  "This package is version 01.01 of the game (program content ID "
                                  "UP0700-NPUB30009_00-0000000000000000). The port supports only version 01.00")

    def test_decrypt_knows_the_v0101_program(self):
        # PARAM.SFO without APP_VER, but the program is the one of v01.01: the version message, not the .rap one
        rap = self.stage_version({"TITLE": "T5", "TITLE_ID": self.bg.TITLE_ID, "VERSION": "01.00"},
                                 "UP0700-NPUB30009_00-0000000000000000")
        with mock.patch.object(self.bg, "run", lambda *a, **k: self.fail("must not decrypt")):
            self.assertBuildError(lambda: self.bg.step_decrypt(self.args(rap=rap)), "version 01.01 of the game")

    def test_wrong_rap_names_the_programs_content_id(self):
        cid = "UP0700-NPUB30009_00-0000000000010000"
        rap = self.stage_version({"TITLE": "T5", "TITLE_ID": self.bg.TITLE_ID, "VERSION": "01.00"}, cid)

        def wrong_rap(cmd, **kw):
            raise subprocess.CalledProcessError(1, cmd, output="metadata did not decrypt (wrong .rap for this package?)")
        with mock.patch.object(self.bg, "run", wrong_rap):
            self.assertBuildError(lambda: self.bg.step_decrypt(self.args(rap=rap)),
                                  f"does not belong to this package. Use the .rap whose name matches the package's "
                                  f"content ID ({cid}).")

    def test_self_content_id(self):
        self.assertEqual(self.bg.self_content_id(fake_self("UP0000-TEST00000_00-0000000000000001")),
                         "UP0000-TEST00000_00-0000000000000001")
        self.assertIsNone(self.bg.self_content_id(b"SCE\0" + bytes(0x100)))     # no NPD header
        self.assertIsNone(self.bg.self_content_id(b"\x7fELF" + bytes(0x100)))
        self.assertIsNone(self.bg.self_content_id(b"SCE\0"))                    # cut short
        p = os.path.join(self.tmp.name, "EBOOT.BIN")
        put(p, fake_self(self.bg.CONTENT_ID))
        self.assertEqual(self.bg.self_content_id(p), self.bg.CONTENT_ID)
        self.assertEqual(self.bg.sfo_version({"VERSION": "01.00"}), "01.00")
        self.assertEqual(self.bg.sfo_version({"APP_VER": "01.01", "VERSION": "01.00"}), "01.01")
        self.assertEqual(self.bg.sfo_version({}), "?")

    def test_unpack_names_a_package_cut_short(self):
        pkg = self.fake_pkg(0x1000)

        def cut(cmd, **kw):
            raise subprocess.CalledProcessError(1, cmd, output="  X: only 5 of 9 bytes are in the package\n"
                                                "the package is cut short: 1 file(s) incomplete -- download it again")
        with mock.patch.object(self.bg, "run", cut):
            self.assertBuildError(lambda: self.bg.step_unpack(self.args(pkg=pkg)),
                                  "The package is 4,096 bytes, the supported one is 619,430,240 bytes: the download "
                                  "is incomplete")


def fake_self(content_id):
    """The start of a PS3 program (SELF) with an NPDRM header naming `content_id`, behind another supplemental
    header, where unself.py and build_game.self_content_id find it."""
    b = bytearray(0x1000)                                         # (program_kind: shorter is "damaged")
    b[0:4] = b"SCE\0"
    struct.pack_into(">QQ", b, 0x58, 0x100, 0x20 + 0x90)          # supplemental headers: offset, size
    b[0x100:0x120] = struct.pack(">IIQ", 1, 0x20, 1) + bytes(0x10)
    npd = b"NPD\0" + struct.pack(">II", 3, 2) + bytes(4) + content_id.encode().ljust(0x30, b"\0")
    b[0x120:0x1B0] = struct.pack(">IIQ", 3, 0x90, 0) + npd.ljust(0x80, b"\0")
    return bytes(b)


def mkput(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    put(path, data)


def git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "core.autocrlf=false", *args],
                   cwd=cwd, check=True, capture_output=True)


@unittest.skipUnless(shutil.which("git"), "needs git")
class DepsSeries(unittest.TestCase):
    """The deps step with a developer's git checkout, for real: git, tools/prepare_ps3recomp.py, a small upstream
    repository standing in for ps3recomp at the pin, and a patch series that grows. 1.1.6: the main checkout's
    deps lacked 0071-0081 and the step said "already done"."""

    def setUp(self):
        self.bg = load_tool("build_game")
        self.tmp = tempfile.TemporaryDirectory(prefix="t5dr_deps_")
        self.addCleanup(self.tmp.cleanup)
        t = self.tmp.name
        self.upstream = os.path.join(t, "upstream")
        os.makedirs(self.upstream)
        git(self.upstream, "init", "-q", "-b", "main")
        mkput(os.path.join(self.upstream, "runtime", "a.c"), "int a = 1;\n")
        git(self.upstream, "add", "-A")
        git(self.upstream, "commit", "-q", "-m", "pin")
        pin = subprocess.run(["git", "rev-parse", "--short=7", "HEAD"], cwd=self.upstream, capture_output=True,
                             text=True, check=True).stdout.strip()
        # the series: 0001 changes a.c, 0002 (added later) adds b.c
        self.p1 = "--- a/runtime/a.c\n+++ b/runtime/a.c\n@@ -1 +1 @@\n-int a = 1;\n+int a = 2;\n"
        self.p2 = "--- /dev/null\n+++ b/runtime/b.c\n@@ -0,0 +1 @@\n+int b = 2;\n"
        self.old_series = os.path.join(t, "patches-old")
        self.series = os.path.join(t, "patches")
        mkput(os.path.join(self.old_series, "0001-a.patch"), self.p1)
        mkput(os.path.join(self.series, "0001-a.patch"), self.p1)
        mkput(os.path.join(self.series, "0002-b.patch"), self.p2)
        self.deps = os.path.join(t, "deps", "ps3recomp")
        self.bg.P = self.bg.Paths(os.path.join(t, "out"), self.deps)
        for name, value in (("PATCH_DIR", self.series), ("PS3RECOMP_COMMIT", pin), ("PS3RECOMP_BRANCH", "main"),
                            ("PS3RECOMP_URL", os.path.join(t, "nowhere"))):     # never the network
            p = mock.patch.object(self.bg, name, value)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(self.bg.prereqs, "python_crypto", lambda: True)
        p.start()
        self.addCleanup(p.stop)
        self.pin = pin

    def prepare(self, patches):
        """A checkout made the way developers make one: tools/prepare_ps3recomp.py (stamped)."""
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "prepare_ps3recomp.py"), "--dest", self.deps,
                            "--source", self.upstream, "--commit", self.pin, "--patches", patches],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def deps_step(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.bg.step_deps(argparse.Namespace(pkg=None, rap=None, force=False))
        return out.getvalue()

    def olds(self):
        return [n for n in os.listdir(os.path.dirname(self.deps)) if n.startswith("ps3recomp.old-")]

    def test_current_series_is_already_done(self):
        self.prepare(self.series)
        with mock.patch.object(self.bg, "run", lambda *a, **k: self.fail("must not run anything")):
            self.assertIn("already done", self.deps_step())

    def test_a_new_patch_prepares_the_checkout_again(self):
        self.prepare(self.old_series)
        self.assertFalse(os.path.exists(os.path.join(self.deps, "runtime", "b.c")))
        out = self.deps_step()
        self.assertNotIn("already done", out)
        self.assertIn("new 0002-b.patch", out)
        self.assertEqual(get(os.path.join(self.deps, "runtime", "b.c")).replace(b"\r\n", b"\n"), b"int b = 2;\n")
        self.assertEqual(get(os.path.join(self.deps, "runtime", "a.c")).replace(b"\r\n", b"\n"), b"int a = 2;\n")
        self.assertEqual(self.olds(), [])                       # untouched by hand: the old tree is gone
        self.assertEqual(self.bg.read_prepared_stamp(self.deps)["series"], ["0001-a.patch", "0002-b.patch"])
        self.assertIn("already done", self.deps_step())          # and now it is current

    def test_an_edited_patch_counts_too(self):
        self.prepare(self.series)
        mkput(os.path.join(self.series, "0002-b.patch"), self.p2.replace("int b = 2;", "int b = 3;"))
        self.assertIn("edited", self.deps_step())
        self.assertEqual(get(os.path.join(self.deps, "runtime", "b.c")).replace(b"\r\n", b"\n"), b"int b = 3;\n")

    def test_changes_of_your_own_are_kept_aside(self):
        self.prepare(self.old_series)
        mkput(os.path.join(self.deps, "runtime", "a.c"), "int a = 42;  /* my work */\n")
        out = self.deps_step()
        (old,) = self.olds()
        self.assertIn(old, out)
        self.assertEqual(get(os.path.join(os.path.dirname(self.deps), old, "runtime", "a.c")).replace(b"\r", b""),
                         b"int a = 42;  /* my work */\n")
        self.assertTrue(os.path.exists(os.path.join(self.deps, "runtime", "b.c")))

    def test_a_checkout_from_before_the_stamp(self):
        self.prepare(self.old_series)
        os.remove(os.path.join(self.deps, ".git", self.bg.PREPARED_STAMP))
        out = self.deps_step()
        self.assertIn("patches missing (at least): 0002-b.patch", out)
        self.assertTrue(os.path.exists(os.path.join(self.deps, "runtime", "b.c")))
        self.assertEqual(len(self.olds()), 1)                    # no stamp: it may hold changes, kept
        # one with every patch in is taken as it is, and stamped
        os.remove(os.path.join(self.deps, ".git", self.bg.PREPARED_STAMP))
        with mock.patch.object(self.bg, "run", lambda *a, **k: self.fail("must not run anything")):
            self.assertIn("every patch of the series is in", self.deps_step())
            self.assertIn("already done", self.deps_step())


class PackageFacts(unittest.TestCase):
    """The Build tab reads PARAM.SFO and the program's content ID straight from the chosen package (build_game.
    package_facts, with ps3recomp's pkg_extract.py keystream): a v01.01 package is red before anything is built."""

    @classmethod
    def setUpClass(cls):
        import test_pkg_pieces
        cls.mod = test_pkg_pieces.load("def _keystream(", "tools/pkg_extract.py and pycryptodome")
        cls.make_pkg = staticmethod(test_pkg_pieces.make_pkg)
        cls.tree = os.path.dirname(os.path.dirname(cls.mod.__file__))
        for sub in ("tools", "lobby", "launcher"):
            d = os.path.join(ROOT, sub)
            if d not in sys.path:
                sys.path.insert(0, d)
        import core
        cls.core = core

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        bg = self.core.build_game
        p = mock.patch.object(bg, "P", bg.Paths(self.tmp.name, self.tree))
        p.start()
        self.addCleanup(p.stop)

    def pkg(self, name, sfo, program, cid=None, rev=0x8000):
        path = os.path.join(self.tmp.name, name + ".pkg")
        self.make_pkg(self.mod, path, [("PARAM.SFO", make_sfo(sfo)), ("USRDIR/EBOOT.BIN", fake_self(program)),
                                       ("USRDIR/T55DATA1.BIN", bytes(5000))], rev=rev)
        with open(path, "r+b") as f:                       # the content ID in the package's own header
            f.seek(0x30)
            f.write((cid or self.core.build_game.CONTENT_ID).encode().ljust(0x24, b"\0"))
        return path

    def test_facts(self):
        bg = self.core.build_game
        p = self.pkg("ok", {"TITLE": "T5", "TITLE_ID": bg.TITLE_ID, "VERSION": "01.00"}, bg.CONTENT_ID)
        self.assertEqual(bg.package_facts(p), {"title": "T5", "title_id": bg.TITLE_ID, "version": "01.00",
                                               "program": bg.CONTENT_ID})
        self.assertEqual(self.core.describe_pkg(p)[:2], (True, "ok"))

    def test_v0101_is_red(self):
        bg = self.core.build_game
        for sfo in ({"TITLE": "T5", "TITLE_ID": bg.TITLE_ID, "APP_VER": "01.01", "VERSION": "01.00"},
                    {"TITLE": "T5", "TITLE_ID": bg.TITLE_ID, "VERSION": "01.00"}):
            p = self.pkg("v0101-%d" % len(sfo), sfo, "UP0700-NPUB30009_00-0000000000000000")
            ok, level, text = self.core.describe_pkg(p)
            self.assertEqual((ok, level), (False, "error"), text)
            self.assertIn("version 01.01 of the game", text)

    def test_unknown_program_warns(self):
        bg = self.core.build_game
        p = self.pkg("other", {"TITLE": "T5", "TITLE_ID": bg.TITLE_ID, "VERSION": "01.00"},
                     "UP0700-NPUB30009_00-0000000000020000")
        ok, level, text = self.core.describe_pkg(p)
        self.assertEqual(level, "warn", text)
        self.assertIn("UP0700-NPUB30009_00-0000000000020000", text)

    def test_unreadable_inside_falls_back_to_the_header(self):
        bg = self.core.build_game
        p = self.pkg("debug", {"TITLE": "T5", "TITLE_ID": bg.TITLE_ID, "APP_VER": "01.01"},
                     "UP0700-NPUB30009_00-0000000000000000", rev=0)
        self.assertIsNone(bg.package_facts(p))                     # a debug package: not read this way
        self.assertEqual(self.core.describe_pkg(p)[:2], (True, "ok"))    # the header's content ID decides, as before
        with mock.patch.object(bg, "P", bg.Paths(self.tmp.name, os.path.join(self.tmp.name, "nothing"))):
            q = self.pkg("nodeps", {"TITLE": "T5", "TITLE_ID": bg.TITLE_ID, "APP_VER": "01.01"}, bg.CONTENT_ID)
            self.assertIsNone(bg.package_facts(q))

    def release_tree(self):
        """A ps3recomp tree whose tools/pkg_extract.py is the release's: package_release's strip_pkg_keys makes the
        keys a lookup in T5DR_KEYS while it is imported (SystemExit without them)."""
        tree = os.path.join(self.tmp.name, "release-deps")
        os.makedirs(os.path.join(tree, "tools"))
        dst = os.path.join(tree, "tools", "pkg_extract.py")
        with open(self.mod.__file__, encoding="utf-8") as f:
            put(dst, f.read())
        with redirect_stdout(io.StringIO()):
            load_tool("package_release").strip_pkg_keys(dst)
        with open(dst, encoding="utf-8") as f:
            self.assertIn('raise SystemExit(f"package key', f.read())
        return tree

    def test_release_pkg_extract_without_keys_never_ends_the_launcher(self):
        # 1.1.5: the launcher closed 2 s after its start -- the Build tab's peek imported the release's
        # pkg_extract.py with no T5DR_KEYS, and its SystemExit went through `except Exception`.
        bg = self.core.build_game
        tree = self.release_tree()
        with mock.patch.object(bg, "P", bg.Paths(os.path.join(self.tmp.name, "out"), tree)), \
                mock.patch.dict(os.environ, {}, clear=False), mock.patch.dict(bg._PKG_TOOL, {}, clear=True):
            os.environ.pop("T5DR_KEYS", None)
            p = self.pkg("rel", {"TITLE": "T5", "TITLE_ID": bg.TITLE_ID, "VERSION": "01.00"}, bg.CONTENT_ID)
            self.assertIsNone(bg.package_facts(p))
            self.assertEqual(self.core.describe_pkg(p)[:2], (True, "ok"))     # the header decides, as before 1.1.5
            self.assertNotIn("T5DR_KEYS", os.environ)

    def test_release_pkg_extract_reads_the_players_key_file(self):
        bg = self.core.build_game
        tree = self.release_tree()
        out = os.path.join(self.tmp.name, "out")
        paths = bg.Paths(out, tree)
        os.makedirs(os.path.dirname(paths.keys))
        put(paths.keys, "PKG_AES_KEY=%s\nPKG_AES_KEY2=%s\n" % (self.mod.PS3_GPKG_KEY.hex(), self.mod.PSP_PKG_KEY.hex()))
        with mock.patch.object(bg, "P", paths), mock.patch.dict(os.environ, {}, clear=False), \
                mock.patch.dict(bg._PKG_TOOL, {}, clear=True):
            os.environ.pop("T5DR_KEYS", None)
            p = self.pkg("rel", {"TITLE": "T5", "TITLE_ID": bg.TITLE_ID, "VERSION": "01.00"}, bg.CONTENT_ID)
            self.assertEqual(bg.package_facts(p)["version"], "01.00")
            self.assertNotIn("T5DR_KEYS", os.environ)                      # only for the import


if __name__ == "__main__":
    unittest.main()
