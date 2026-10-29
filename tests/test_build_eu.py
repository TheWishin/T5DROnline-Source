"""1.1.9: tools/build_game.py with the European release (NPEA00019 v01.00) next to the US one -- without the game.
The program table (PROGRAMS), the decrypt step's title/version/SHA-1 checks for both programs, an output folder
that held the other program, the steps that follow the program (vfs path, lift code end, sound core arguments,
no PGO profile, the stamp's "online": false), the launcher's package line and the problem check (docs/EU.md)."""
import argparse
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock

from helpers import ROOT, load_tool, put
from test_build_game import fake_self, make_sfo, mkput

EU_SHA1 = "586baa2074e3d259b303879fc7cbea1000041b60"
EU_CID = "EP9000-NPEA00019_00-0000000000000000"


class ProgramTable(unittest.TestCase):
    def setUp(self):
        self.bg = load_tool("build_game")

    def test_both_programs(self):
        bg = self.bg
        self.assertEqual(list(bg.PROGRAMS), [bg.ELF_SHA1, EU_SHA1])         # the US one first (it plays online)
        self.assertEqual(bg.TITLE_IDS, ("NPUB30009", "NPEA00019"))
        for sha, p in bg.PROGRAMS.items():
            self.assertRegex(sha, r"^[0-9a-f]{40}$")
            for k in ("key", "title_id", "version", "region", "name", "content_ids", "pkg_size", "code_end",
                      "spu_extra", "pgo", "online"):
                self.assertIn(k, p, (sha, k))
            int(p["code_end"], 16)
            self.assertEqual(p["version"], "01.00")
            for cid in p["content_ids"]:
                self.assertIn(p["title_id"], cid)
            name, funcs = p["spu_extra"].split("=")
            self.assertEqual(name, "bnuscore")
            self.assertEqual(len(funcs.split(",")), 13)                      # the 12 named effects + 1
        us, eu = bg.PROGRAMS[bg.ELF_SHA1], bg.PROGRAMS[EU_SHA1]
        self.assertIs(bg.US_PROGRAM, us)
        self.assertEqual((us["code_end"], us["spu_extra"]), (bg.CODE_END, bg.SPU_CORE_EXTRA_FUNCS))
        self.assertEqual((us["online"], us["pgo"]), (True, True))
        self.assertEqual((eu["online"], eu["pgo"]), (False, False))          # another program: offline, no profile
        self.assertNotEqual(eu["code_end"], us["code_end"])
        self.assertIn(EU_CID, bg.ALL_CONTENT_IDS)
        self.assertIn("NPEA00019", bg.SUPPORTED_TEXT)
        self.assertIn("NPUB30009", bg.SUPPORTED_TEXT)

    def test_program_of(self):
        bg = self.bg
        self.assertIs(bg.program_of(content_id=EU_CID), bg.PROGRAMS[EU_SHA1])
        self.assertIs(bg.program_of(content_id=bg.CONTENT_ID), bg.US_PROGRAM)
        self.assertIs(bg.program_of(title_id="NPEA00019"), bg.PROGRAMS[EU_SHA1])
        self.assertIsNone(bg.program_of(content_id="UP0000-BLUS00000_00-0000000000000000"))
        # the European "Online" edition is a known other version, not a supported program
        self.assertIsNone(bg.program_of(content_id="UP0700-NPEA00019_00-TEKKEN5DRO000000"))
        self.assertIn("UP0700-NPEA00019_00-TEKKEN5DRO000000", bg.OTHER_VERSIONS)


class EuSteps(unittest.TestCase):
    def setUp(self):
        self.bg = load_tool("build_game")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.bg.P = self.bg.Paths(self.tmp.name, os.path.join(self.tmp.name, "ps3recomp"))
        self.quiet = redirect_stdout(io.StringIO())
        self.out = self.quiet.__enter__()
        self.addCleanup(self.quiet.__exit__, None, None, None)
        real = self.bg.sha1
        # a fake program stands for each real one: its content says which (the SHA-1 pins cannot be met)
        self.progs = {b"EU program": EU_SHA1, b"US program": self.bg.ELF_SHA1}

        def sha1(path):
            with open(path, "rb") as f:
                return self.progs.get(f.read(), None) or real(path)
        p = mock.patch.object(self.bg, "sha1", sha1)
        p.start()
        self.addCleanup(p.stop)

    def args(self, **kw):
        return argparse.Namespace(**{"pkg": None, "rap": None, "force": False, **kw})

    def stage(self, title_id, program_cid, sfo=None):
        usr = os.path.join(self.bg.P.pkg_dir, "USRDIR")
        os.makedirs(usr, exist_ok=True)
        mkput(os.path.join(usr, "EBOOT.BIN"), fake_self(program_cid))
        mkput(os.path.join(self.bg.P.pkg_dir, "PARAM.SFO"),
            make_sfo(sfo or {"TITLE": "TEKKEN 5 DARK RESURRECTION", "TITLE_ID": title_id, "VERSION": "01.00"}))
        rap = os.path.join(self.tmp.name, program_cid + ".rap")
        mkput(rap, b"\1" * 16)
        return rap

    def decrypt_to(self, content):
        calls = []

        def fake_run(cmd, **kw):
            calls.append(os.path.basename(str(cmd[1])))
            if "unself.py" in str(cmd[1]):
                mkput(self.bg.P.elf, content)
            return "content id x, license type 2\n"
        return calls, mock.patch.object(self.bg, "run", fake_run)

    def test_decrypt_accepts_the_european_program(self):
        # before 1.1.9: "This package is ... (NPEA00019). The port needs Tekken 5: Dark Resurrection Online (US)"
        rap = self.stage("NPEA00019", EU_CID)
        calls, run = self.decrypt_to(b"EU program")
        with run:
            self.bg.step_decrypt(self.args(rap=rap))
        self.assertEqual(calls, ["unself.py"])
        self.assertIs(self.bg.built_program(), self.bg.PROGRAMS[EU_SHA1])
        self.assertIn("program OK: SHA-1 %s (NPEA00019 v01.00, EU)" % EU_SHA1, self.out.getvalue())
        self.assertIn("it plays offline", self.out.getvalue())

    def test_decrypt_refuses_an_unknown_european_program(self):
        rap = self.stage("NPEA00019", EU_CID)
        _, run = self.decrypt_to(b"another EU build")
        with run, self.assertRaises(self.bg.BuildError) as cm:
            self.bg.step_decrypt(self.args(rap=rap))
        self.assertIn("different version", str(cm.exception))
        self.assertIn("NPEA00019 v01.00", str(cm.exception))                # names what is supported
        self.assertFalse(os.path.exists(self.bg.P.elf))

    def test_decrypt_names_the_european_online_edition(self):
        # VERSION 02.00 / APP_VER 01.00 and its own program: the version message before any decrypting
        rap = self.stage("NPEA00019", "UP0700-NPEA00019_00-TEKKEN5DRO000000",
                         {"TITLE": "T5 ONLINE", "TITLE_ID": "NPEA00019", "APP_VER": "01.00", "VERSION": "02.00"})
        with mock.patch.object(self.bg, "run", lambda *a, **k: self.fail("must not decrypt")), \
                self.assertRaises(self.bg.BuildError) as cm:
            self.bg.step_decrypt(self.args(rap=rap))
        self.assertIn("version 02.00 (Online) of the game", str(cm.exception))

    def eu_pkg(self):
        pkg = os.path.join(self.tmp.name, "eu.pkg")
        mkput(pkg, b"\x7fPKG" + bytes(0x2C) + EU_CID.encode().ljust(0x24, b"\0") + bytes(0x40))
        return pkg

    def test_a_us_folder_given_the_european_package_starts_from_it(self):
        # the US program decrypted and unpacked here before; the EU package chosen now: before 1.1.9 "already
        # done" kept the US game
        rap = self.stage("NPUB30009", self.bg.CONTENT_ID)
        mkput(self.bg.P.elf, b"US program")
        mkput(self.bg.P.unpacked_stamp, "us.pkg\n")
        self.assertIs(self.bg.built_program(), self.bg.US_PROGRAM)
        pkg = self.eu_pkg()
        taken = []

        def fake_run(cmd, **kw):
            cmd = [str(c) for c in cmd]
            if "pkg_extract.py" in cmd[1]:
                taken.append(cmd[-1])
                if cmd[-1] == "PARAM.SFO":
                    mkput(os.path.join(self.bg.P.pkg_dir, "PARAM.SFO"),
                        make_sfo({"TITLE": "T5", "TITLE_ID": "NPEA00019", "VERSION": "01.00"}))
                else:
                    mkput(os.path.join(self.bg.P.pkg_dir, "USRDIR", "EBOOT.BIN"), fake_self(EU_CID))
            if "unself.py" in cmd[1]:
                mkput(self.bg.P.elf, b"EU program")
            return ""
        with mock.patch.object(self.bg, "run", fake_run):
            self.bg.step_decrypt(self.args(rap=rap, pkg=pkg))
        self.assertEqual(taken, ["PARAM.SFO", "EBOOT.BIN"])
        self.assertFalse(os.path.exists(self.bg.P.unpacked_stamp))       # the unpack step unpacks the EU package
        self.assertIs(self.bg.built_program(), self.bg.PROGRAMS[EU_SHA1])
        self.assertFalse(self.bg.other_package(self.args(pkg=pkg)))      # and now it is the same game

    def test_steps_follow_the_program(self):
        mkput(self.bg.P.elf, b"EU program")
        usr = os.path.join(self.bg.P.pkg_dir, "USRDIR")
        os.makedirs(usr)
        mkput(os.path.join(usr, "T55DATA1.BIN"), b"data")
        mkput(os.path.join(self.bg.P.pkg_dir, "PARAM.SFO"), b"sfo")
        self.bg.step_vfs(self.args())
        self.assertTrue(os.path.exists(os.path.join(self.bg.P.hdd0, "game", "NPEA00019", "USRDIR", "T55DATA1.BIN")))
        self.assertFalse(os.path.exists(os.path.join(self.bg.P.hdd0, "game", "NPUB30009")))
        # the lift: the EU program's code end, and a stamp no US lift is mistaken for
        cmds = []
        with mock.patch.object(self.bg, "run", lambda cmd, **kw: cmds.append([str(c) for c in cmd])):
            self.bg.step_lift(self.args())
        lift = next(c for c in cmds if c[1].endswith("ppu_lifter.py"))
        self.assertEqual(lift[lift.index("--code-end") + 1], "0x30388C")
        with open(os.path.join(self.bg.P.recomp, ".lifter.sha1")) as f:
            self.assertTrue(f.read().strip().endswith(":program=eu"))
        # the sound core: the EU core's effect functions, and a stamp that names the program
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
        self.assertEqual(core[core.index("--extra-funcs") + 1], self.bg.PROGRAMS[EU_SHA1]["spu_extra"])
        self.assertEqual(self.bg.stamp_program(os.path.join(self.bg.P.spu, ".core_lift_args")), "eu")
        # the game DLL: no PGO profile (it names the US program's functions)
        cmds.clear()
        with mock.patch.object(self.bg, "run", lambda cmd, **kw: cmds.append([str(c) for c in cmd])), \
                mock.patch.object(self.bg.prereqs, "portable_llvm", lambda: self.tmp.name), \
                mock.patch.object(self.bg, "HOST_DIR", self.tmp.name):
            self.bg.compile_game_dll(self.args())
        dll = next(c for c in cmds if c[1].endswith("build_game_dll.py"))
        self.assertEqual(dll[dll.index("--profile") + 1], "none")
        with open(self.bg.P.stamp) as f:
            stamp = json.load(f)
        self.assertEqual((stamp["title"], stamp["elf_sha1"], stamp["region"], stamp["online"]),
                         ("NPEA00019", EU_SHA1, "EU", False))

    def test_us_steps_unchanged(self):
        mkput(self.bg.P.elf, b"US program")
        cmds = []
        with mock.patch.object(self.bg, "run", lambda cmd, **kw: cmds.append([str(c) for c in cmd])):
            self.bg.step_lift(self.args())
        lift = next(c for c in cmds if c[1].endswith("ppu_lifter.py"))
        self.assertEqual(lift[lift.index("--code-end") + 1], self.bg.CODE_END)
        with open(os.path.join(self.bg.P.recomp, ".lifter.sha1")) as f:
            self.assertNotIn("program=", f.read())                      # a US build keeps its lift
        cmds.clear()
        with mock.patch.object(self.bg, "run", lambda cmd, **kw: cmds.append([str(c) for c in cmd])), \
                mock.patch.object(self.bg.prereqs, "portable_llvm", lambda: self.tmp.name), \
                mock.patch.object(self.bg, "HOST_DIR", self.tmp.name):
            self.bg.compile_game_dll(self.args())
        self.assertNotIn("--profile", next(c for c in cmds if c[1].endswith("build_game_dll.py")))
        with open(self.bg.P.stamp) as f:
            stamp = json.load(f)
        self.assertEqual((stamp["title"], stamp["elf_sha1"]), ("NPUB30009", self.bg.ELF_SHA1))
        self.assertNotIn("online", stamp)                               # as before: Windows writes no key

    def test_another_programs_sound_core_is_lifted_afresh(self):
        # a US sound core (stamp without program=) in a folder that now holds the EU program: extracted again,
        # never relifted from the US image with the EU arguments
        mkput(self.bg.P.elf, b"EU program")
        mkput(os.path.join(self.bg.P.spu, "spu_workloads.c"), "us core")
        mkput(os.path.join(self.bg.P.spu, ".core_lift_args"), self.bg.SPU_CORE_EXTRA_FUNCS + "\n")
        cmds = []

        def spu_run(cmd, **kw):
            cmd = [str(c) for c in cmd]
            cmds.append(cmd)
            if cmd[1].endswith("extract_spu_images.py"):
                mkput(os.path.join(cmd[cmd.index("--output") + 1], "spu_0000.elf"), b"core")
        with mock.patch.object(self.bg, "run", spu_run):
            self.bg.step_spu(self.args())
        self.assertTrue(cmds[0][1].endswith("extract_spu_images.py"), cmds[0])
        self.assertNotIn("--relift", cmds[1])


class LauncherLines(unittest.TestCase):
    def setUp(self):
        for sub in ("tools", "lobby", "launcher"):
            d = os.path.join(ROOT, sub)
            if d not in sys.path:
                sys.path.insert(0, d)
        import core
        import problem_check
        self.core, self.pc = core, problem_check
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def pkg(self, cid):
        p = os.path.join(self.tmp.name, cid + ".pkg")
        mkput(p, b"\x7fPKG" + bytes(0x2C) + cid.encode().ljust(0x24, b"\0") + bytes(0x40))
        return p

    def test_european_package_is_green_and_says_offline(self):
        ok, level, text = self.core.describe_pkg(self.pkg(EU_CID))
        self.assertEqual((ok, level), (True, "ok"), text)
        self.assertIn("the European version: it plays offline only for now", text)
        self.assertIn("comes in a later update", text)
        rap = os.path.join(self.tmp.name, EU_CID + ".rap")
        mkput(rap, b"\1" * 16)
        self.assertEqual(self.core.describe_rap(rap)[1], "ok")
        ok, level, text = self.core.describe_pkg(self.pkg("EP9000-NPEA00019_00-0000000000000001"))
        self.assertEqual(level, "warn", text)

    def test_find_candidates_takes_the_european_pair(self):
        mkput(os.path.join(self.tmp.name, "dl", "a.pkg"),
            b"\x7fPKG" + bytes(0x2C) + EU_CID.encode().ljust(0x24, b"\0") + bytes(0x40))
        mkput(os.path.join(self.tmp.name, "dl", EU_CID + ".rap"), b"\1" * 16)
        mkput(os.path.join(self.tmp.name, "dl", "UP0700-NPUB30009_00-UPDATE0000010000.rap"), b"\1" * 16)
        pkg, rap = self.core.find_candidates([self.tmp.name])
        self.assertEqual(os.path.basename(pkg), "a.pkg")
        self.assertEqual(os.path.basename(rap), EU_CID + ".rap")

    def test_game_state_ready_for_the_european_build(self):
        out = os.path.join(self.tmp.name, "native")
        mkput(os.path.join(out, "game", "EBOOT.elf"), b"EU program")
        mkput(self.core.game_exe(out), b"exe")
        mkput(os.path.join(out, "build", "t5dr_build.json"), json.dumps({"code_id": self.core.build_game.code_id()}))
        with mock.patch.object(self.core.build_game, "sha1", lambda p: EU_SHA1):
            st = self.core.game_state(out)
        self.assertTrue(st["ok"], st["text"])
        self.assertIn("NPEA00019 v01.00", st["text"])

    def test_problem_check_names_both_releases(self):
        out = os.path.join(self.tmp.name, "native")
        mkput(os.path.join(out, "build.log"), "[decrypt]\n  PARAM.SFO: T5 / NPEA00019 / version 01.00\n"
            "  program content ID: UP0700-NPEA00019_00-TEKKEN5DRO000000\nERROR: This package is version 02.00\n")
        with mock.patch.object(self.pc.report, "last_build_failed", lambda d: True):
            found = self.pc.check_build(out)
        self.assertEqual([f.key for f in found], ["package_version"])
        title, seen, fix = found[0].text()
        self.assertIn("02.00", title)
        self.assertIn("NPEA00019", fix)
        self.assertIn("599,050,576", fix)
        # the European 01.00 package itself is no version problem
        mkput(os.path.join(out, "build.log"), "[decrypt]\n  PARAM.SFO: T5 / NPEA00019 / version 01.00\n"
            f"  program content ID: {EU_CID}\nERROR: something else\n")
        with mock.patch.object(self.pc.report, "last_build_failed", lambda d: True):
            self.assertEqual([f.key for f in self.pc.check_build(out)], [])

    def test_problem_check_says_the_european_game_is_offline_for_now(self):
        # 1.1.9 (stage 1): "Check my problem" names a European build as offline only, online in a later update
        out = os.path.join(self.tmp.name, "native")
        self.assertEqual(self.pc.check_edition(out), [])                          # nothing built
        mkput(os.path.join(out, "build", "t5dr_build.json"), json.dumps({"code_id": "x", "title": "NPUB30009"}))
        self.assertEqual(self.pc.check_edition(out), [])                          # the US game: nothing to say
        mkput(os.path.join(out, "build", "t5dr_build.json"), json.dumps({"code_id": "x", "title": "NPEA00019",
                                                                         "online": False}))
        found = [f for f in self.pc.check(out, facts={}, fw={}) if f.key == "eu_offline"]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].kind, "hint")
        title, seen, fix = found[0].text()
        self.assertIn("offline only for now", title)
        self.assertIn("NPEA00019", fix)
        self.assertIn("later update", fix)
        self.assertIn("never play each other online", fix)


if __name__ == "__main__":
    unittest.main()
