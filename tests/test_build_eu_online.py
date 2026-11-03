"""1.2.0 experiment: tools/build_game.py with the European Online edition (NPEA00019 v02.00 / v02.01) -- without the
game. Off by default: both packages are named and refused before anything is decrypted, the program table is the
1.1.9 one. With the opt-in (T5DR_EU_ONLINE=1, --eu-online): both programs are accepted, v02.01 with its .rap, v02.00
with its free license and no .rap; the later steps follow the program (code end, sound core, offline stamp); a US or
EU v01.00 build still needs its .rap (docs/EU.md "EU Online")."""
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
    def tearDown(self):
        self.assertNotIn("T5DR_EU_ONLINE", os.environ, "a test left the opt-in on for the tests after it")

    def test_off_by_default(self):
        bg = load_build_game(False)
        self.assertEqual(list(bg.PROGRAMS), [bg.ELF_SHA1, EU_SHA1])            # the 1.1.9 table
        for cid in (E200_CID, E201_CID):
            self.assertIn(cid, bg.OTHER_VERSIONS)
            self.assertIsNone(bg.program_of(content_id=cid))
            self.assertNotIn(cid, bg.ALL_CONTENT_IDS)
        self.assertEqual(bg.OTHER_VERSIONS[E201_CID], "02.01 (Online)")
        self.assertNotIn("v02.0", bg.SUPPORTED_TEXT)

    def test_opt_in_table(self):
        bg = load_build_game(True)
        self.assertEqual(list(bg.PROGRAMS)[:2], [bg.ELF_SHA1, EU_SHA1])         # the US one stays first
        for sha, cid, ver in ((E201_SHA1, E201_CID, "02.01"), (E200_SHA1, E200_CID, "02.00")):
            p = bg.PROGRAMS[sha]
            self.assertIs(bg.program_of(content_id=cid), p)
            self.assertNotIn(cid, bg.OTHER_VERSIONS)
            self.assertEqual((p["version"], p["sfo"]["VERSION"], p["sfo"]["APP_VER"]), (ver, ver, "01.00"))
            self.assertEqual((p["online"], p["pgo"], p["experimental"], p["code_end"]), (False, False, True, "0x3D7884"))
            self.assertEqual(len(p["spu_extra"].split("=")[1].split(",")), 13)
        # title ID alone still means the EU v01.00 game (the first NPEA00019 entry)
        self.assertIs(bg.program_of(title_id="NPEA00019"), bg.PROGRAMS[EU_SHA1])
        self.assertIs(bg.US_PROGRAM, bg.PROGRAMS[bg.ELF_SHA1])

    def test_flag_enables_it(self):
        bg = load_build_game(False)
        with mock.patch.dict(os.environ, {}, clear=False):
            bg.enable_eu_online()
            self.assertEqual(os.environ.get("T5DR_EU_ONLINE"), "1")             # the tools it starts see it too
        self.assertIn(E201_SHA1, bg.PROGRAMS)

    def test_sfo_version_text(self):
        bg = load_build_game(False)
        self.assertEqual(bg.sfo_version_text({"VERSION": "02.01", "APP_VER": "01.00"}), "01.00 (VERSION 02.01)")
        self.assertEqual(bg.sfo_version_text({"VERSION": "01.00"}), "01.00")
        self.assertEqual(bg.sfo_version_text({"VERSION": "01.00", "APP_VER": "01.00"}), "01.00")
        us = bg.US_PROGRAM
        self.assertTrue(bg.sfo_matches({"VERSION": "01.00"}, us))
        self.assertFalse(bg.sfo_matches({"VERSION": "01.00", "APP_VER": "01.01"}, us))
        with mock.patch.dict(os.environ, {}, clear=False):
            bg.enable_eu_online()
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
        self.assertIn("accepted as an experiment", out)
        self.assertIn("it plays offline", out)

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
        self.assertIn("version 02.00 of the game", str(cm.exception))
        self.assertIn("supports only version 02.01", str(cm.exception))

    def test_us_still_needs_its_rap(self):
        self.stage(self.bg.CONTENT_ID, {"TITLE": "T5", "TITLE_ID": "NPUB30009", "VERSION": "01.00"})
        _, run = self.decrypt_to(b"US program")
        with run, self.assertRaises(self.bg.BuildError) as cm:
            self.bg.step_decrypt(self.args())
        self.assertIn("Choose your license file", str(cm.exception))

    def test_us_free_self_is_not_a_reason_to_skip_the_rap(self):
        # only the experimental programs may come without one
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
            self.assertTrue(f.read().strip().endswith(":program=eu_online"))
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
        self.assertEqual((stamp["title"], stamp["elf_sha1"], stamp["version"], stamp["online"]),
                         ("NPEA00019", E201_SHA1, "02.01", False))


class StepsWithoutOptIn(Steps):
    """The same packages without the opt-in: refused before decrypting, as in 1.1.9."""
    opt_in = False

    def test_v0201_with_its_rap(self):
        rap = self.stage(E201_CID, self.SFO201)
        with mock.patch.object(self.bg, "run", lambda *a, **k: self.fail("must not decrypt")), \
                self.assertRaises(self.bg.BuildError) as cm:
            self.bg.step_decrypt(self.args(rap=rap))
        self.assertIn("version 02.01 (Online) of the game", str(cm.exception))

    def test_v0201_needs_its_rap(self):
        self.stage(E201_CID, self.SFO201)
        with self.assertRaises(self.bg.BuildError) as cm:
            self.bg.step_decrypt(self.args())
        self.assertIn("Choose your license file", str(cm.exception))   # the 1.1.9 order: the .rap first

    def test_v0200_free_license_without_rap(self):
        self.stage(E200_CID, self.SFO200, free=True)
        with self.assertRaises(self.bg.BuildError) as cm:
            self.bg.step_decrypt(self.args())
        self.assertIn("Choose your license file", str(cm.exception))

    def test_wrong_sfo_version_refused(self):
        rap = self.stage(E201_CID, self.SFO200)
        with mock.patch.object(self.bg, "run", lambda *a, **k: self.fail("must not decrypt")), \
                self.assertRaises(self.bg.BuildError) as cm:
            self.bg.step_decrypt(self.args(rap=rap))
        self.assertIn("(Online) of the game", str(cm.exception))

    def test_steps_follow_the_program(self):
        mkput(self.bg.P.elf, b"EU201 program")
        self.assertIsNone(self.bg.built_program())                    # not a program this build knows


if __name__ == "__main__":
    unittest.main()
