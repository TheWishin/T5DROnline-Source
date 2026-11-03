"""No pause online and the skips by both players' START (docs/NETPLAY.md "No pause online", "Skipping intros
and replays online"; src/netplay/no_pause.h).

* tests/c/no_pause_test.cpp is the rule on its own against a model of the game: the window after a
  decision, slot symmetry, and two PCs in lockstep, under rollback (late inputs, predictions,
  re-simulations) and in a replay -- the same inputs reach both games, the pause menu never opens,
  the post-match skip by START still works, intros, round replays and the way to the next round are
  skipped once both players pressed START and never by one player alone; START+SELECT never reaches the
  game, even from scripts, repeated rollback boundaries or replay input, while SELECT alone is preserved.
  Built with clang-cl; skipped without a C++ compiler.
* The source checks: every place in src/netplay/t5_hooks.cpp that hands a frame's inputs to the
  game runs the rule first, and the local devices' START is taken out before it is sent except in a
  skip part."""
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
        exe = os.path.join(cls.tmp.name, "no_pause_test.exe")
        src = os.path.join(ROOT, "tests", "c", "no_pause_test.cpp")
        cmd = (f'"{vcvars}" >nul 2>&1 && "{clang}" /nologo /std:c++17 /EHsc /O2 /W3 "{src}" /Fe:"{exe}" '
               f'/Fo:"{os.path.join(cls.tmp.name, "no_pause_test.obj")}"')
        r = subprocess.run(f'cmd /s /c "{cmd}"', capture_output=True, text=True, timeout=900)
        if not os.path.isfile(exe):
            raise AssertionError("could not build tests/c/no_pause_test.cpp: " + (r.stdout + r.stderr)[-2000:])
        cls.exe = exe

    def test_model(self):
        r = subprocess.run([self.exe], capture_output=True, text=True, timeout=600, cwd=self.tmp.name)
        out = r.stdout[-3000:] + r.stderr[-2000:]
        self.assertEqual(r.returncode, 0, out)
        self.assertRegex(r.stdout, r"(?m)^PASS \d+ checks$", out)
        for part in ("window ok", "parts ok", "symmetry ok", "soft reset ok", "lockstep, rollback, replay ok", "automatic skips ok",
                     "offline skips ok"):
            self.assertIn(part, r.stdout)


class Source(unittest.TestCase):
    def test_changed_simulation_requires_a_new_code_id(self):
        """The reset filter changes simulated pad inputs; a launcher must rebuild the old host,
        including when the reset fix is carried independently of the renderer patch."""
        build = read("tools/build_game.py")
        version = re.search(r"(?m)^CODE_VERSION\s*=\s*(\d+)", build)
        self.assertIsNotNone(version)
        self.assertGreaterEqual(int(version.group(1)), 11, "integrated version 10 predates the online reset policy")
        start = build.index("def code_id():")
        code_id = build[start:build.index("\n\ndef ", start)]
        self.assertIn('h.update(f"{CODE_VERSION}:{PS3RECOMP_COMMIT}:{CODE_END}".encode())', code_id)

    def test_online_pad_handover_always_suppresses_soft_reset(self):
        """The final pad write covers injected menu input before netplay starts, passive/scripted
        samples and the live/replayed frame cache alike. Offline and legacy recordings retain their policy."""
        src = read("src/netplay/t5_hooks.cpp")
        start = src.index("void write_pad_data(")
        writer = src[start:src.index("\n}\n", start)]
        self.assertRegex(writer, r"const uint16_t buttons\s*=\s*g_offline\s*\|\|\s*!rp::play_soft_reset_guard\(\)\s*\?\s*in\.buttons\s*:\s*"
                                 r"np::NoPauseRule::suppress_soft_reset\(in\.buttons\);")
        self.assertIn("(buttons & 0xFF)", writer)
        self.assertIn("(buttons >> 8)", writer)
        self.assertNotRegex(writer, r"wr16\([^\n]*in\.buttons")
        self.assertEqual(src.count("rp::play_soft_reset_guard()"), 4)
        self.assertIn("np::NoPauseRule::apply(v, in, rp::play_soft_reset_guard());", src)
        start = src.index("void h_cellPadGetData(")
        reader = src[start:src.index("\n}\n", start)]
        passive, active = reader.split("} else if (port < 2) {", 1)
        self.assertIn("if (g_passive && port < 2)", passive)
        self.assertEqual(passive.count("np::poll_now("), 1)  # stateful cursor: sample only requested port
        self.assertIn("np::poll_now((int)port)", passive)
        self.assertIn("write_pad_data(ea, in);", passive)   # scalar guard on the final requested pad
        self.assertNotIn("np::poll_now(", active)
        self.assertIn("if (injected & (1u << p)) in[p].buttons = g_inject[p].load();", active)
        self.assertIn("else if (active) in[p] = g_cur[p];", active)
        self.assertRegex(active, r"if \(!g_offline && rp::play_soft_reset_guard\(\)\) np::NoPauseRule::suppress_soft_reset\(in\);\s*"
                                 r"write_pad_data\(ea, in\[port\]\);")
        start = src.index("void no_pause_rule(")
        rule = src[start:src.index("\n}\n", start)]
        rule = re.sub(r"/\*.*?\*/", "", rule, flags=re.S)
        self.assertRegex(rule, r"if \(!g_directfight\)\s*\{\s*"
                               r"if \(rp::play_soft_reset_guard\(\)\) np::NoPauseRule::suppress_soft_reset\(in\);\s*return;")


    def test_every_input_hand_over_runs_the_rule(self):
        """g_cur (what cellPadGetData gives the game during a session) gets a frame's inputs only
        right after no_pause_rule() ran on them -- lockstep, rollback (live and re-simulated) and
        replay frames all pass these two places."""
        src = read("src/netplay/t5_hooks.cpp")
        handovers = [m.start() for m in re.finditer(r"g_cur\[0\] = in\[0\];", src)]
        self.assertEqual(len(handovers), 2, "the places that hand a frame's inputs to the game changed")
        for pos in handovers:
            before = src[max(0, pos - 400):pos]
            # (the training rule may follow it: match_rules.h -- it writes the game state, never an input)
            self.assertRegex(before, r"no_pause_rule\((run|f), in, [^)]*\);[^\n]*\n\s*"
                                     r"(training_rule\((run|f), in, [^)]*\);[^\n]*\n\s*)?$",
                             "no rule before: " + before[-200:])
        self.assertIn("np::NoPauseRule", src)

    def test_local_devices_never_send_start(self):
        core = read("src/netplay/netplay_core.cpp")

        def body(sig):
            b = core[core.index(sig):]
            return b[:b.index("\n}\n")]
        # every local sample (a port: device_input; the online player's controller: player_input, local_pad.cpp)
        # goes through pad_into, which drops START
        self.assertRegex(body("void pad_into("), r"if \(g_no_start\.load\([^)]*\)\) b &= \(uint16_t\)~B_START;")
        for sig in ("void device_input(", "void player_input("):
            self.assertIn("pad_into(d, in);", body(sig), sig)
        hooks = read("src/netplay/t5_hooks.cpp")
        self.assertIn("np::set_no_start(g_directfight);", hooks)
        # START leaves this PC only while the live boundary shows a skip part, decided at every live boundary
        # before this PC's sample is taken (the rollback loop's boundary, lockstep's begin_frame)
        gate = hooks[hooks.index("void start_gate("):]
        gate = gate[:gate.index("\n}\n")]
        self.assertIn("np::set_no_start(part == np::NoPauseRule::kNone);", gate)
        self.assertIn("part_of(np_state_now())", gate)
        self.assertRegex(hooks, r"start_gate\(f\);[^\n]*\n\s*uint32_t run = rb::net::on_boundary\(f, scene, in\);")
        self.assertRegex(hooks, r"start_gate\(f\);[^\n]*\n\s*np::begin_frame\(f, h, in,")

    def test_rule_is_the_same_for_both_slots(self):
        """the rule's inputs: the frame, what the game shows, the two inputs -- nothing about which PC
        or slot runs it"""
        hdr = read("src/netplay/no_pause.h")
        code = re.sub(r"/\*.*?\*/", "", hdr, flags=re.S)
        self.assertNotRegex(code, r"local_slot|slot|Mode::|enabled\(|replaying\(")
        self.assertIn("static unsigned apply(Verdict v, PadInput in[2], bool soft_reset_guard = true)", hdr)
        self.assertIn("Verdict record(uint32_t f, const State& st, const PadInput in[2], bool auto_skip_after_round = false)", hdr)

    def test_automatic_skip_is_part_of_the_deterministic_rule(self):
        hdr = read("src/netplay/no_pause.h")
        self.assertIn("auto_skip_after_round && pt == kAfter && !st.decided", hdr)
        self.assertIn("% kPressEvery < kPressFrames", hdr)
        hooks = read("src/netplay/t5_hooks.cpp")
        self.assertIn("rules.auto_skip_after_round", hooks)


if __name__ == "__main__":
    unittest.main()
