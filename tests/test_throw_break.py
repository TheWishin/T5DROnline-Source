"""Native deterministic throw-break rule tests; made-up commands, no game or network."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from helpers import ROOT
from test_ps_hid import find_vcvars


class ThrowBreakRuleTest(unittest.TestCase):
    def test_native_rule(self):
        if os.name != "nt":
            self.skipTest("built with clang-cl")
        vcvars = find_vcvars()
        clang = shutil.which("clang-cl") or r"C:\Program Files\LLVM\bin\clang-cl.exe"
        if not vcvars or not os.path.isfile(clang):
            self.skipTest("no clang-cl / Visual Studio build tools")
        with tempfile.TemporaryDirectory() as tmp:
            exe = os.path.join(tmp, "throw_break_test.exe")
            obj = os.path.join(tmp, "throw_break_test.obj")
            src = os.path.join(ROOT, "tests", "c", "throw_break_test.cpp")
            cmd = (f'"{vcvars}" >nul 2>&1 && "{clang}" /nologo /std:c++17 /EHsc /O2 /W3 '
                   f'"{src}" /Fe:"{exe}" /Fo:"{obj}"')
            build = subprocess.run(f'cmd /s /c "{cmd}"', capture_output=True, text=True, timeout=120, cwd=tmp)
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            run = subprocess.run([exe], capture_output=True, text=True, timeout=30, cwd=tmp)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertRegex(run.stdout, r"(?m)^PASS \d+ checks$")
            for proof in ("endpoints, early/wrong presses ok", "scope restoration and guards ok",
                          "two PCs, lockstep, rollback and replay ok"):
                self.assertIn(proof, run.stdout)
            print(run.stdout, end="")


class IntegrationTest(unittest.TestCase):
    def test_both_simulation_handovers_apply_the_current_policy(self):
        source = (Path(ROOT) / "src/netplay/t5_hooks.cpp").read_text(encoding="utf-8")
        self.assertEqual(source.count("throw_break_rule();"), 2)
        for frame in ("run", "f"):
            self.assertRegex(source, rf"training_rule\({frame}, in, [^;]+;[^\n]*\n\s*throw_break_rule\(\);\s*"
                                    r"g_cur\[0\] = in\[0\];\s*g_cur\[1\] = in\[1\];\s*keyread_tick\(\);")
        begin = source.index("void throw_break_rule()")
        end = source.index("\n}", begin)
        rule = source[begin:end]
        for gate in ("np::enabled()", "t5_df_game_mode() != 0", "== 17", "rd32(kRoundState) == 5",
                     "!rd8(kMatchOver)", "rp::play_throw_break_rule()"):
            self.assertIn(gate, rule)
        self.assertIn("np::replaying() ? rp::play_input_delay() : np::delay()", rule)
        self.assertIn("t5_throw_break_frame(false, 0);", source)
        self.assertIn("t5_throw_break_install();", source)

    def test_rebuild_and_replay_version_preserve_old_simulation(self):
        build = (Path(ROOT) / "tools/build_game.py").read_text(encoding="utf-8")
        self.assertGreaterEqual(int(re.search(r"(?m)^CODE_VERSION\s*=\s*(\d+)", build).group(1)), 12)
        replay = (Path(ROOT) / "src/netplay/replay.cpp").read_text(encoding="utf-8")
        self.assertIn("constexpr uint32_t kVersion = 8;", replay)
        self.assertIn("m.throw_break_rule = ver >= 8;", replay)
        self.assertIn("m.throw_break_rule = d.matches[k].throw_break_rule;", replay)
        self.assertIn("return d.rollback && d.rb_delay >= 0 ? d.rb_delay : d.delay;", replay)

    def test_evaluator_detour_has_a_portable_hook_slot(self):
        slots = (Path(ROOT) / "src/rollback/hook_slots.txt").read_text(encoding="utf-8")
        self.assertRegex(slots, r"(?m)^000EF7BC\b")
        runtime = (Path(ROOT) / "src/netplay/throw_break.cpp").read_text(encoding="utf-8")
        self.assertIn("const uint32_t kEvaluate = T5A(0x000EF7BC);", runtime)
        self.assertIn("if (enabled && !installed)", runtime)
        self.assertIn("abort();", runtime)
        self.assertIn('t5game::hooks_ok("online throw breaks")', runtime)
        self.assertIn("read32(move + 0x14) == list", runtime)


if __name__ == "__main__":
    unittest.main()
