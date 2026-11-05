"""tools/build_game.py with the European Online edition (NPEA00019 v02.00 / v02.01) -- without the game. Since 1.2.1
both programs are accepted without an opt-in (1.2.0's T5DR_EU_ONLINE=1 / --eu-online changes nothing now): v02.01
with its .rap, v02.00 with its free license and no .rap; the later steps follow the program (code end, sound core,
the stamp); a US or EU v01.00 build still needs its .rap. The refusals name the edition the player has and what the
port builds (a 1.2.0 player's log: "version 01.00" for a v02.01 package, "supports only ... v01.00") (docs/EU.md)."""
import argparse
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from helpers import load_tool
from test_build_game import fake_self, make_sfo, mkput

E201_SHA1 = "ff07efe07be23a30e37601049f4e849ddc2cff02"
E200_SHA1 = "a26bc6e037e5a8faf40250849acfa8a40d027fff"
E201_CID = "EP9000-NPEA00019_00-TEKKENRETAIL0000"
E200_CID = "UP0700-NPEA00019_00-TEKKEN5DRO000000"
EU_SHA1 = "586baa2074e3d259b303879fc7cbea1000041b60"


def free_self(content_id):
    """fake_self with NPD license type 3 (free)."""
    b = bytearray(fake_self(content_id))
    i = b.index(b"NPD\0")
    b[i + 8:i + 12] = (3).to_bytes(4, "big")
    return bytes(b)


def load_build_game(opt_in):
    with mock.patch.dict(os.environ, {"T5DR_EU_ONLINE": "1"} if opt_in else {}, clear=False):
        if not opt_in:
            os.environ.pop("T5DR_EU_ONLINE", None)
        return load_tool("build_game")


class Defaults(unittest.TestCase):
    def test_accepted_without_an_opt_in(self):
        for opt_in in (False, True):
            bg = load_build_game(opt_in)
            self.assertEqual(list(bg.PROGRAMS), [bg.ELF_SHA1, EU_SHA1, E201_SHA1, E200_SHA1])   # the US one first
            for sha, cid, ver in ((E201_SHA1, E201_CID, "02.01"), (E200_SHA1, E200_CID, "02.00")):
                p = bg.PROGRAMS[sha]
                self.assertIs(bg.program_of(content_id=cid), p)
                self.assertNotIn(cid, bg.OTHER_VERSIONS)
                self.assertIn(cid, bg.ALL_CONTENT_IDS)
                self.assertEqual((p["version"], p["sfo"]["VERSION"], p["sfo"]["APP_VER"]), (ver, ver, "01.00"))
                self.assertEqual((p["online"], p["pgo"], p["code_end"]), (False, False, "0x3D7884"))
                self.assertNotIn("experimental", p)
                self.assertEqual(len(p["spu_extra"].split("=")[1].split(",")), 13)
            # title ID alone still means the EU v01.00 game (the first NPEA00019 entry)
            self.assertIs(bg.program_of(title_id="NPEA00019"), bg.PROGRAMS[EU_SHA1])
            self.assertIs(bg.US_PROGRAM, bg.PROGRAMS[bg.ELF_SHA1])
            self.assertEqual(list(bg.OTHER_VERSIONS), ["UP0700-NPUB30009_00-0000000000000000"])
        os.environ.pop("T5DR_EU_ONLINE", None)

    def test_supported_text_names_every_edition_and_what_it_does(self):
        bg = load_build_game(False)
        t = bg.SUPPORTED_TEXT
        self.assertIn("US PSN (NPUB30009 v01.00): online and offline", t)
        self.assertIn("European PSN (NPEA00019 v02.00 or v02.01): offline only for now", t)
        self.assertIn("European PSN (NPEA00019 v01.00): offline only", t)
        self.assertNotIn("01.01", t)

    def test_flag_is_kept_for_scripts(self):
        bg = load_build_game(False)
        with mock.patch.dict(os.environ, {}, clear=False):
            bg.enable_eu_online()
            self.assertEqual(os.environ.get("T5DR_EU_ONLINE"), "1")
        self.assertIn(E201_SHA1, bg.PROGRAMS)

    def test_online_gate_is_written_for_both_eu_versions_only(self):
        # Address coverage alone does not qualify a build for the lobby: EU-vs-EU
        # rollback and lockstep pairs must pass before either version is enabled.
        bg = load_build_game(False)
        with tempfile.TemporaryDirectory() as out:
            bg.P = bg.Paths(out, os.path.join(out, "ps3recomp"))
            os.makedirs(os.path.dirname(bg.P.stamp), exist_ok=True)
            for sha, online in ((E201_SHA1, False), (E200_SHA1, False), (bg.ELF_SHA1, True)):
                with self.subTest(sha=sha), mock.patch.object(bg, "built_program", return_value=bg.PROGRAMS[sha]), \
                        mock.patch.object(bg, "code_id", return_value="fixture-code"):
                    bg.write_stamp("fixture-compiler")
                    with open(bg.P.stamp) as f:
                        stamp = json.load(f)
                    self.assertEqual(stamp["elf_sha1"], sha)
                    self.assertIs(stamp.get("online", True), online)
                    if online:
                        self.assertNotIn("online", stamp)  # US stamp stays unchanged.

    def test_sfo_version_text(self):
        bg = load_build_game(False)
        self.assertEqual(bg.sfo_version_text({"VERSION": "02.01", "APP_VER": "01.00"}), "01.00 (VERSION 02.01)")
        self.assertEqual(bg.sfo_version_text({"VERSION": "01.00"}), "01.00")
        self.assertEqual(bg.sfo_version_text({"VERSION": "01.00", "APP_VER": "01.00"}), "01.00")
        us = bg.US_PROGRAM
        self.assertTrue(bg.sfo_matches({"VERSION": "01.00"}, us))
        self.assertFalse(bg.sfo_matches({"VERSION": "01.00", "APP_VER": "01.01"}, us))
        e = bg.PROGRAMS[E201_SHA1]
        self.assertTrue(bg.sfo_matches({"VERSION": "02.01", "APP_VER": "01.00"}, e))
        self.assertFalse(bg.sfo_matches({"VERSION": "02.00", "APP_VER": "01.00"}, e))

    def test_self_license_type(self):
        bg = load_build_game(False)
        self.assertEqual(bg.self_license_type(fake_self(E201_CID)), 2)
        self.assertEqual(bg.self_license_type(free_self(E200_CID)), 3)
        self.assertEqual(bg.self_content_id(free_self(E200_CID)), E200_CID)
        self.assertIsNone(bg.self_license_type(b"\x7fELF" + bytes(60)))


class Steps(unittest.TestCase):
    opt_in = True

    def setUp(self):
        self.bg = load_build_game(self.opt_in)
        env = mock.patch.dict(os.environ, {"T5DR_EU_ONLINE": "1"} if self.opt_in else {})
        env.start()
        self.addCleanup(env.stop)
        if not self.opt_in:
            os.environ.pop("T5DR_EU_ONLINE", None)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.bg.P = self.bg.Paths(self.tmp.name, os.path.join(self.tmp.name, "ps3recomp"))
        self.quiet = redirect_stdout(io.StringIO())
        self.out = self.quiet.__enter__()
        self.addCleanup(self.quiet.__exit__, None, None, None)
        real = self.bg.sha1
        self.progs = {b"EU201 program": E201_SHA1, b"EU200 program": E200_SHA1, b"US program": self.bg.ELF_SHA1}

        def sha1(path):
            with open(path, "rb") as f:
                return self.progs.get(f.read(), None) or real(path)
        p = mock.patch.object(self.bg, "sha1", sha1)
        p.start()
        self.addCleanup(p.stop)

    def args(self, **kw):
        return argparse.Namespace(**{"pkg": None, "rap": None, "force": False, **kw})

    def stage(self, cid, sfo, free=False):
        usr = os.path.join(self.bg.P.pkg_dir, "USRDIR")
        os.makedirs(usr, exist_ok=True)
        mkput(os.path.join(usr, "EBOOT.BIN"), free_self(cid) if free else fake_self(cid))
        mkput(os.path.join(self.bg.P.pkg_dir, "PARAM.SFO"), make_sfo(sfo))
        rap = os.path.join(self.tmp.name, cid + ".rap")
        mkput(rap, b"\1" * 16)
        return rap

    def decrypt_to(self, content):
        calls = []

        def fake_run(cmd, **kw):
            cmd = [str(c) for c in cmd]
            calls.append(cmd)
            if "unself.py" in cmd[1]:
                mkput(self.bg.P.elf, content)
            return "content id x, license type 2\n"
        return calls, mock.patch.object(self.bg, "run", fake_run)

    SFO201 = {"TITLE": "TEKKEN 5 DARK RESURRECTION ONLINE", "TITLE_ID": "NPEA00019", "VERSION": "02.01",
              "APP_VER": "01.00"}
    SFO200 = dict(SFO201, VERSION="02.00")

    def test_v0201_with_its_rap(self):
        rap = self.stage(E201_CID, self.SFO201)
        calls, run = self.decrypt_to(b"EU201 program")
        with run:
            self.bg.step_decrypt(self.args(rap=rap))
        unself = next(c for c in calls if c[1].endswith("unself.py"))
        self.assertEqual(unself[3], rap)
        self.assertIs(self.bg.built_program(), self.bg.PROGRAMS[E201_SHA1])
        out = self.out.getvalue()
        self.assertIn("version 01.00 (VERSION 02.01)", out)
        self.assertIn("it plays offline; online play awaits EU-vs-EU validation", out)
        self.assertNotIn("practice tools and the training overlay need the US version", out)

    def test_v0201_needs_its_rap(self):
        self.stage(E201_CID, self.SFO201)
        _, run = self.decrypt_to(b"EU201 program")
        with run, self.assertRaises(self.bg.BuildError) as cm:
            self.bg.step_decrypt(self.args())
        self.assertIn("Choose your license file", str(cm.exception))

    def test_v0200_free_license_without_rap(self):
        self.stage(E200_CID, self.SFO200, free=True)
        calls, run = self.decrypt_to(b"EU200 program")
        with run:
            self.bg.step_decrypt(self.args())
        unself = next(c for c in calls if c[1].endswith("unself.py"))
        self.assertEqual(unself[3], "-")
        self.assertIs(self.bg.built_program(), self.bg.PROGRAMS[E200_SHA1])
        self.assertIn("free license", self.out.getvalue())

    def test_wrong_sfo_version_refused(self):
        rap = self.stage(E201_CID, self.SFO200)          # the v02.01 program's content ID, a v02.00 PARAM.SFO
        with mock.patch.object(self.bg, "run", lambda *a, **k: self.fail("must not decrypt")), \
                self.assertRaises(self.bg.BuildError) as cm:
            self.bg.step_decrypt(self.args(rap=rap))
        self.assertIn("This package is version 02.00 of the game (program content ID " + E201_CID, str(cm.exception))
        self.assertIn("The port builds: ", str(cm.exception))

    def test_us_still_needs_its_rap(self):
        self.stage(self.bg.CONTENT_ID, {"TITLE": "T5", "TITLE_ID": "NPUB30009", "VERSION": "01.00"})
        _, run = self.decrypt_to(b"US program")
        with run, self.assertRaises(self.bg.BuildError) as cm:
            self.bg.step_decrypt(self.args())
        self.assertIn("Choose your license file", str(cm.exception))

    def test_us_free_self_is_not_a_reason_to_skip_the_rap(self):
        # only EU Online v02.00 may come without one
        self.stage(self.bg.CONTENT_ID, {"TITLE": "T5", "TITLE_ID": "NPUB30009", "VERSION": "01.00"}, free=True)
        _, run = self.decrypt_to(b"US program")
        with run, self.assertRaises(self.bg.BuildError) as cm:
            self.bg.step_decrypt(self.args())
        self.assertIn("Choose your license file", str(cm.exception))

    def test_steps_follow_the_program(self):
        mkput(self.bg.P.elf, b"EU201 program")
        usr = os.path.join(self.bg.P.pkg_dir, "USRDIR")
        os.makedirs(usr)
        mkput(os.path.join(usr, "T55DATA1.BIN"), b"data")
        mkput(os.path.join(self.bg.P.pkg_dir, "PARAM.SFO"), b"sfo")
        self.bg.step_vfs(self.args())
        self.assertTrue(os.path.exists(os.path.join(self.bg.P.hdd0, "game", "NPEA00019", "USRDIR", "T55DATA1.BIN")))
        cmds = []
        with mock.patch.object(self.bg, "run", lambda cmd, **kw: cmds.append([str(c) for c in cmd])):
            self.bg.step_lift(self.args())
        lift = next(c for c in cmds if c[1].endswith("ppu_lifter.py"))
        self.assertEqual(lift[lift.index("--code-end") + 1], "0x3D7884")
        with open(os.path.join(self.bg.P.recomp, ".lifter.sha1")) as f:
            self.assertTrue(f.read().strip().endswith(":program=eu_online:live-immediates=" + self.bg.sha1(self.bg.EU_LIVE_IMMEDIATES)))
        cmds.clear()
        os.makedirs(os.path.join(self.bg.P.spu, "images"), exist_ok=True)

        def spu_run(cmd, **kw):
            cmd = [str(c) for c in cmd]
            cmds.append(cmd)
            if cmd[1].endswith("extract_spu_images.py"):
                mkput(os.path.join(cmd[cmd.index("--output") + 1], "spu_0000.elf"), b"core")
        with mock.patch.object(self.bg, "run", spu_run):
            self.bg.step_spu(self.args())
        core = next(c for c in cmds if c[1].endswith("build_spu_workloads.py"))
        self.assertEqual(core[core.index("--extra-funcs") + 1], self.bg.EU_ONLINE_SPU_EXTRA)
        cmds.clear()
        with mock.patch.object(self.bg, "run", lambda cmd, **kw: cmds.append([str(c) for c in cmd])), \
                mock.patch.object(self.bg.prereqs, "portable_llvm", lambda: self.tmp.name), \
                mock.patch.object(self.bg, "HOST_DIR", self.tmp.name):
            self.bg.compile_game_dll(self.args())
        dll = next(c for c in cmds if c[1].endswith("build_game_dll.py"))
        self.assertEqual(dll[dll.index("--profile") + 1], "none")
        with open(self.bg.P.stamp) as f:
            stamp = json.load(f)
        self.assertEqual((stamp["title"], stamp["elf_sha1"], stamp["version"], stamp.get("online", True)),
                         ("NPEA00019", E201_SHA1, "02.01", False))


class StepsWithoutOptIn(Steps):
    """No opt-in (1.2.1: the default) -- the same as with 1.2.0's opt-in still set by a script."""
    opt_in = False


class PlayerLog120(unittest.TestCase):
    """A player's 1.2.0 build (launcher.log, release launcher): the EU Online v02.01 package was refused after 1 s with
    the message OLD below. The same package (its PARAM.SFO as the player's: the title with the trademark sign,
    VERSION 02.01, APP_VER 01.00, its .rap) builds now; another program of that content ID is named for what it is."""
    SFO = {"TITLE": "TEKKEN\u21225 DARK RESURRECTION ONLINE", "TITLE_ID": "NPEA00019", "VERSION": "02.01",
           "APP_VER": "01.00"}
    OLD = ('This copy is a different version of the game: "TEKKEN\u21225 DARK RESURRECTION ONLINE" version 01.00, content '
           'ID EP9000-NPEA00019_00-TEKKENRETAIL0000 (program SHA-1 ff07efe07be2...). The port supports only Tekken 5: '
           'Dark Resurrection (PS3, EU PSN, NPEA00019 v01.00), content ID EP9000-NPEA00019_00-0000000000000000.')

    def setUp(self):
        self.t = StepsWithoutOptIn("test_v0201_with_its_rap")
        self.t.setUp()
        self.addCleanup(self.t.doCleanups)

    def test_the_package_builds_now(self):
        rap = self.t.stage(E201_CID, self.SFO)
        calls, run = self.t.decrypt_to(b"EU201 program")
        with run:
            self.t.bg.step_decrypt(self.t.args(rap=rap))
        self.assertIs(self.t.bg.built_program(), self.t.bg.PROGRAMS[E201_SHA1])
        out = self.t.out.getvalue()
        self.assertIn("program OK: SHA-1 " + E201_SHA1 + " (NPEA00019 v02.01, EU)", out)
        self.assertNotIn("different version", out)

    def test_another_program_of_that_content_id_is_named_for_what_it_is(self):
        rap = self.t.stage(E201_CID, self.SFO)
        calls, run = self.t.decrypt_to(b"some other program")
        with run, self.assertRaises(self.t.bg.BuildError) as cm:
            self.t.bg.step_decrypt(self.t.args(rap=rap))
        msg = str(cm.exception)
        self.assertNotEqual(msg, self.OLD)
        self.assertIn("This copy's program is not one the port knows", msg)
        self.assertIn("version 01.00 (VERSION 02.01)", msg)          # both numbers, not "01.00" alone
        self.assertNotIn("supports only", msg)
        self.assertIn("European PSN (NPEA00019 v02.00 or v02.01): offline only for now", msg)


class SoundCoreThread(unittest.TestCase):
    """EU Online's sound core thread: sys_spu_thread_initialize(spu_num 0xFF) -- US 1. lv2 numbers threads 0..255
    (a 256-entry map); our runtime refused >= 8, so the EU Online build ran silent (patch 0108)."""

    def test_runtime_patch_takes_spu_num_up_to_255_and_keeps_low_numbers(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "patches", "ps3recomp", "0108-spu-thread-num.patch"), encoding="utf-8") as f:
            patch = f.read()
        lines = patch.splitlines()
        added = "|".join(l[1:] for l in lines if l.startswith("+") and not l.startswith("+++"))
        removed = "|".join(l[1:] for l in lines if l.startswith("-") and not l.startswith("---"))
        self.assertIn("if (thread_num >= 8) LV2_RET(ctx, CELL_EINVAL);", removed)
        self.assertIn("if (thread_num >= 256) LV2_RET(ctx, CELL_EINVAL);", added)
        self.assertIn("if (spu_num >= 8) {", added)          # only numbers >= 8 take another slot
        self.assertIn("t->spu_num     = spu_num;", added)
        self.assertIn("if (g->init_mask & (1u << thread_num)) LV2_RET(ctx, CELL_EBUSY);", added)


if __name__ == "__main__":
    unittest.main()
