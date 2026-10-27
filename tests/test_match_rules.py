"""Online training and the health handicap (docs/NETPLAY.md "Online training and the health handicap";
src/netplay/match_rules.h).

* tests/c/match_rules_test.cpp is the training rule on its own against a model of a fight: refill after a combo,
  the round timer held, SELECT held to give up, slot symmetry, and two PCs in lockstep, under rollback (late inputs,
  predictions, re-simulations, sync points) and in a replay -- the same game state on both. Built with clang-cl;
  skipped without a C++ compiler.
* The source checks: the hooks run the rule on every frame that runs (live, re-simulated, played back) right after
  the no-pause rule, clear its history at every sync point, the driver reads train= / life= from the fight line,
  writes the handicap before the game mode's set-up and latches the rules at FIGHT START, and the replay keeps them
  per match (format 5)."""
import os
import re
import shutil
import subprocess
import tempfile
import unittest

from helpers import ROOT
from test_ps_hid import find_vcvars

LLVM = r"C:\Program Files\LLVM"


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


class RuleModel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.name != "nt":
            raise unittest.SkipTest("built with clang-cl")
        vcvars = find_vcvars()
        clang = shutil.which("clang-cl") or (os.path.join(LLVM, "bin", "clang-cl.exe")
                                             if os.path.isfile(os.path.join(LLVM, "bin", "clang-cl.exe")) else None)
        if not vcvars or not clang:
            raise unittest.SkipTest("no clang-cl / Visual Studio build tools")
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        exe = os.path.join(cls.tmp.name, "match_rules_test.exe")
        src = os.path.join(ROOT, "tests", "c", "match_rules_test.cpp")
        cmd = (f'"{vcvars}" >nul 2>&1 && "{clang}" /nologo /std:c++17 /EHsc /O2 /W3 "{src}" /Fe:"{exe}" '
               f'/Fo:"{os.path.join(cls.tmp.name, "match_rules_test.obj")}"')
        r = subprocess.run(f'cmd /s /c "{cmd}"', capture_output=True, text=True, timeout=900)
        if not os.path.isfile(exe):
            raise AssertionError("could not build tests/c/match_rules_test.cpp: " + (r.stdout + r.stderr)[-2000:])
        cls.exe = exe

    def test_model(self):
        r = subprocess.run([self.exe], capture_output=True, text=True, timeout=600, cwd=self.tmp.name)
        out = r.stdout[-3000:] + r.stderr[-2000:]
        self.assertEqual(r.returncode, 0, out)
        self.assertRegex(r.stdout, r"(?m)^PASS \d+ checks$", out)
        for part in ("rules ok", "refill ok", "give-up ok", "symmetry ok", "lockstep ok", "rollback ok", "replay ok"):
            self.assertIn(part, r.stdout)


class Source(unittest.TestCase):
    def test_hooks_run_the_rule_on_every_frame(self):
        src = read("src/netplay/t5_hooks.cpp")
        # the rollback loop (live and re-simulated frames, replays) and lockstep: right after the no-pause rule
        self.assertRegex(src, r"no_pause_rule\(run, in, run >= f\);[^\n]*\n\s*training_rule\(run, in, run >= f\);")
        self.assertRegex(src, r"no_pause_rule\(f, in, true\);\s*\n\s*training_rule\(f, in, true\);")
        self.assertEqual(len(re.findall(r"training_rule\((run|f), in,", src)), 2)
        # every sync point clears the history (the frames are numbered anew), and so does frame 0
        self.assertEqual(src.count("g_scenes++;"), src.count("g_scenes++;\n        training_reset();") +
                         src.count("g_scenes++;\n            training_reset();") +
                         src.count("g_scenes++;\r\n        training_reset();") +
                         src.count("g_scenes++;\r\n            training_reset();"))
        self.assertIn("training_reset(); }   /* frame 0", src)
        body = src[src.index("void training_rule("):]
        body = body[:body.index("\n}\n") if "\n}\n" in body else body.index("\r\n}\r\n")]
        self.assertIn("if (!g_directfight || !(t5_df_rules() & 1)) return;", body)
        self.assertIn("rd32(kRoundState) == 5", body)

    def test_driver_reads_and_applies_the_rules(self):
        df = read("src/directfight/df_fight.cpp")
        self.assertIn('_stricmp(k.c_str(), "train") == 0', df)
        self.assertIn('_stricmp(k.c_str(), "life") == 0', df)
        self.assertIn("if (f.rules.training) f.rounds = 1;", df)
        # the handicap: next to the rounds, at the game mode's first frame (before its set-up builds the fighters)
        self.assertRegex(df, r"wr8\(kRoundsToWin, \(uint8_t\)g_cfg\.rounds\);(.|\n)*?wr32\(kLifeP1, (.|\n)*?wr32\(kLifeP2, ")
        self.assertIn("constexpr uint32_t kLifeP1       = 0x1008EBF4;", df)
        self.assertIn("constexpr uint32_t kLifeP2       = 0x1008EBF8;", df)
        # latched at FIGHT START, before netplay starts; into the replay
        start = df[df.index("g_rules = g_cfg.rules;"):]
        self.assertLess(start.index("g_rules.pack()"), start.index("t5_netplay_start();"))

    def test_replay_keeps_the_rules(self):
        rp = read("src/netplay/replay.cpp")
        self.assertIn("constexpr uint32_t kVersion = 5;", rp)
        self.assertIn("put32(b, m.ft.rules);", rp)
        self.assertIn("if (ver >= 5) m.ft.rules = r.u32();", rp)
        self.assertIn('*line += " train=1";', rp)

    def test_rule_is_the_same_for_both_slots(self):
        hdr = read("src/netplay/match_rules.h")
        code = re.sub(r"/\*.*?\*/", "", hdr, flags=re.S)
        self.assertNotRegex(code, r"local_slot|slot|Mode::|enabled\(|replaying\(")
        self.assertIn("Action step(uint32_t f, const State& s, const PadInput in[2])", hdr)


if __name__ == "__main__":
    unittest.main()
