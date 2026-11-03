"""Experimental advantage comparison: fake frames/memory and source safety contracts.

The two standalone C++ programs need only the headers in this checkout. They
never load game data, call the game, or use a network. The source tests below
also run without a compiler. Build/run this suite only when authorized; adding
it does not execute it.
"""
import os
import re
import shutil
import subprocess
import tempfile
import unittest

from helpers import ROOT


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as stream:
        return stream.read()


def code_only(source):
    source = re.sub(r"/\*.*?\*/|//[^\n]*", " ", source, flags=re.S)
    return re.sub(r'"(?:\\.|[^"\\])*"', '""', source)


def body(source, signature):
    """Extract a C++ function body after comments/strings have been removed."""
    match = re.search(signature + r"\s*\{", source)
    if match is None:
        raise AssertionError("missing function: " + signature)
    start = match.end()
    depth = 1
    for index in range(start, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start:index]
    raise AssertionError("unclosed function: " + signature)


class FakeFramesAndMemory(unittest.TestCase):
    """Portable standalone harnesses; no ps3recomp or game installation needed."""

    @classmethod
    def setUpClass(cls):
        compiler = next((shutil.which(name) for name in ("c++", "g++", "clang++")
                         if shutil.which(name)), None)
        msvc = False
        if compiler is None and os.name == "nt":
            compiler = shutil.which("clang-cl") or shutil.which("cl")
            msvc = compiler is not None
        if compiler is None:
            raise unittest.SkipTest("no C++ compiler on PATH (configure the compiler environment first)")
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.executables = {}
        for stem in ("advantage_shadow_test", "advantage_shadow_reader_test"):
            source = os.path.join(ROOT, "tests", "c", stem + ".cpp")
            executable = os.path.join(cls.tmp.name, stem + (".exe" if os.name == "nt" else ""))
            if msvc:
                command = [compiler, "/nologo", "/EHsc", "/std:c++17", "/W3", source,
                           "/Fe:" + executable, "/Fo:" + os.path.join(cls.tmp.name, stem + ".obj")]
            else:
                command = [compiler, "-std=c++17", "-Wall", "-Wextra", source, "-o", executable]
            result = subprocess.run(command, capture_output=True, text=True, timeout=120, cwd=cls.tmp.name)
            if result.returncode != 0:
                raise AssertionError("could not build " + stem + ":\n" +
                                     (result.stdout + result.stderr)[-6000:])
            cls.executables[stem] = executable

    def check_harness(self, stem):
        result = subprocess.run([self.executables[stem]], capture_output=True, text=True,
                                timeout=30, cwd=self.tmp.name)
        output = (result.stdout + result.stderr)[-6000:]
        self.assertEqual(result.returncode, 0, output)
        self.assertRegex(result.stdout, r"(?m)^PASS\b", output)

    def test_fake_frame_sequences(self):
        self.check_harness("advantage_shadow_test")

    def test_fake_guest_memory(self):
        self.check_harness("advantage_shadow_reader_test")


class SourceContracts(unittest.TestCase):
    def setUp(self):
        self.runtime = read("src/training/training.cpp")
        self.code = code_only(self.runtime)

    def test_comparison_requires_explicit_exact_opt_in(self):
        self.assertRegex(self.code, r"\bbool\s+adv_compare\s*=\s*false\s*;")
        self.assertIn('getenv("T5_TRAINING_ADV_COMPARE")', self.runtime)
        self.assertRegex(self.runtime, r'g_cfg\.adv_compare\s*=\s*ac\s*&&\s*!strcmp\(ac,\s*"1"\)')

    def test_comparison_gate_requires_offline_practice_and_working_log(self):
        gate = body(self.code, r"bool shadow_allowed\([^)]*\)")
        for condition in ("g_cfg.adv_compare", "g_cfg.log", "mode == kFrames", "phase == 17",
                          "gt == kGtPractice", "g_cfg.adv_offline", "!netplay",
                          "!g_cfg.online_game", "!g_cfg.local_net"):
            self.assertIn(condition, gate)
        self.assertNotIn("||", gate, "none of the safety conditions may be bypassed")
        frame = body(self.code, r"static bool frame_body\(\)")
        self.assertRegex(frame, r"if\s*\(shadow_allowed\(mode, phase, gt, netplay\)\)\s*shadow_frame\(\);")
        self.assertEqual(len(re.findall(r"\bshadow_frame\(\);", self.code)), 1)

    def test_netplay_control_and_replay_launches_are_ineligible(self):
        init = body(self.code, r"void init\(\)")
        self.assertRegex(self.code, r"\bbool\s+adv_offline\s*=\s*false\s*;")
        for variable, environment in (("nm", "T5_NET_MODE"), ("ctl", "T5_CTL_DIR"),
                                      ("replay", "T5_REPLAY_FILE")):
            self.assertRegex(self.runtime, variable + r'\s*=\s*getenv\("' + environment + r'"\)')
        self.assertIn("g_cfg.adv_offline = !(nm && *nm) && !(ctl && *ctl) && !(replay && *replay);", init)

    def test_gaps_reset_comparison_history(self):
        frame = body(self.code, r"static bool frame_body\(\)")
        self.assertRegex(frame, r'if\s*\(!fight\)\s*\{\s*shadow_reset\(""\);')
        self.assertRegex(frame, r'if\s*\(off\)\s*\{\s*shadow_reset\(""\);\s*hide\(\);\s*return true;')
        self.assertRegex(frame, r'else\s+shadow_reset\(""\);')
        reset = body(self.code, r"void shadow_reset\([^)]*\)")
        self.assertIn("g_adv_compare.reset();", reset)
        self.assertIn("g_adv_active = false;", reset)

    def test_guest_callback_checks_complete_readable_span_before_copying(self):
        callback = body(self.code, r"bool shadow_read_memory\([^)]*\)")
        self.assertIn("guest < 0x10000u", callback)
        self.assertIn("0x100000000ull", callback)
        self.assertIn("UINTPTR_MAX - guest", callback)
        self.assertIn("UINTPTR_MAX - start", callback)
        self.assertIn("for (uintptr_t p = start; p < end;)", callback)
        for guard in ("MEM_COMMIT", "PAGE_GUARD", "PAGE_NOACCESS", "PAGE_READONLY", "PAGE_EXECUTE_READ"):
            self.assertIn(guard, callback)
        self.assertIn("next <= p", callback)
        self.assertLess(callback.index("VirtualQuery("), callback.index("memcpy("))
        self.assertIn("memcpy(out, (const void*)start, bytes);", callback)

    def test_old_results_keep_move_anchor_and_explicit_unavailable_new_value(self):
        logger = body(self.code, r"void shadow_log_old\([^)]*\)")
        self.assertIn("r.active_frame", logger)
        self.assertIn("anchor.tick == r.active_frame", logger)
        self.assertIn("anchor.live >= g_adv_since", logger)
        self.assertIn("old=%+d old_status=%s new=unavailable new_status=%s", self.runtime)
        self.assertIn("sample_poll=%llu", self.runtime)
        self.assertNotRegex(self.code, r"g_results\s*\[[^]]+\]\s*=\s*g_adv")

    def test_old_move_poll_ring_uses_trackers_one_based_ticks_and_sample_lifetime(self):
        self.assertIn("uint64_t g_old_tick = 1;", self.code)
        frame = body(self.code, r"static bool frame_body\(\)")
        self.assertIn("g_old_tick = 1;", frame)
        self.assertIn("g_old_poll[g_old_tick % kOldPollHistory]", frame)
        for field in ("poll.tick = g_old_tick;", "poll.live = g_live;", "poll.known = true;"):
            self.assertIn(field, frame)
        self.assertLess(frame.index("poll.tick = g_old_tick;"), frame.index("++g_old_tick;"))
        self.assertLess(frame.index("++g_old_tick;"), frame.index("g_track.frame(s)"))
        shadow_frame = body(self.code, r"void shadow_frame\(\)")
        self.assertIn("g_adv_since = g_live;", shadow_frame)
        self.assertLess(shadow_frame.index("g_adv_since = g_live;"), shadow_frame.index("g_adv_active = true;"))

    def test_existing_live_frame_hook_excludes_resimulation(self):
        hooks = code_only(read("src/netplay/t5_hooks.cpp"))
        calls = re.findall(r"[^\n]*t5_training_frame\(ctx\);[^\n]*", hooks)
        self.assertEqual(len(calls), 1, calls)
        self.assertIn("if (!rb::net::bypass())", calls[0])

    def test_comparison_coexists_with_existing_diagnostics_and_boot_cover(self):
        frame = body(self.code, r"static bool frame_body\(\)")
        anchor = frame.index("poll.tick = g_old_tick;")
        self.assertLess(anchor, frame.index("n = g_track.frame(s, &diagnostic);"))
        self.assertLess(anchor, frame.index("else n = g_track.frame(s);"))
        self.assertIn("log_diagnostic(s, raw, diagnostic, n);", frame)
        self.assertEqual(frame.count("shadow_log_old(r);"), 1)
        cover = body(self.code, r"void t5_boot_cover_publish\(void\)")
        self.assertIn("g_old_tick = 1;", cover)
        self.assertIn("memset(g_old_poll, 0, sizeof g_old_poll);", cover)
        self.assertRegex(cover, r"if \(g_in_fight\) \{\s*shadow_reset\(\"\"\);")
        hook = body(self.code, r"void t5_training_frame\([^)]*\)")
        self.assertLess(hook.index("t5_boot_cover_publish();"), hook.index("if (!g_init) init();"))

    def test_pure_tracker_has_no_guest_memory_or_game_calls(self):
        source = code_only(read("src/training/advantage_shadow_logic.h"))
        self.assertNotRegex(source, r"\bvm_base\b|VirtualQuery|ppu_guest_call|gcall\s*\(|\bwr(?:8|16|32|64)\s*\(")

    def test_production_rejects_conflicting_pointer_mapping(self):
        reader = read("src/training/advantage_shadow_reader.h")
        production = body(code_only(reader), r"inline bool read_sample\([^)]*\)")
        self.assertIn("out = Sample", production)
        self.assertIn("reader_detail::scalars(", production)
        self.assertIn("return false;", production)
        self.assertNotIn("return true;", production)
        self.assertNotRegex(production, r"\bmove\s*\(|resolve_move|read_fixture_sample|out\.valid\s*=\s*true")
        self.assertIn('"mapping_conflict_position_x"', reader)
        self.assertNotIn("read_fixture_sample(", self.code)
        self.assertNotIn("resolve_move(", self.code)


if __name__ == "__main__":
    unittest.main()
