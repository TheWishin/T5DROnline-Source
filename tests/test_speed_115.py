"""1.1.5 speed (ps3recomp patch 0075, docs/RENDER_PERF.md "2-core mode and slow graphics cards"): the honest
[slow-frames] verdict and what the launcher and the problem report read from it, two frames in flight on a
dedicated graphics card, the 2-core mode's switches, the slow-GPU test hook and the shader warm-up after BUILD
GAME. The launcher parses lines the runtime prints, so both sides are checked against each other here. No game or
GPU needed."""
import json
import os
import re
import sys
import tempfile
import unittest
from unittest import mock

from helpers import ROOT

# appended, not in front: test_smoke imports its own "run" late, and lobby/ has a run.py too
for _d in ("launcher", "lobby", "tools"):
    if os.path.join(ROOT, _d) not in sys.path:
        sys.path.append(os.path.join(ROOT, _d))
import core  # noqa: E402
import problem_report as report  # noqa: E402

PATCH = os.path.join(ROOT, "patches", "ps3recomp", "0075-speed-115.patch")


def patch_text():
    with open(PATCH, encoding="utf-8") as f:
        return f.read()


def added(text):
    """The lines a patch adds, without the leading '+'."""
    return "\n".join(ln[1:] for ln in text.splitlines() if ln.startswith("+") and not ln.startswith("+++"))


HEAD = ("[slow-frames] last 30 s: 614 frames, 581 slow (over 20.9 ms): CPU 29 (game 23, render translation 6, vblank "
        "thread late 0), GPU 543, present 9; 353 late for their vblank, shown when translated; median per frame: game "
        "22.1 ms, translation 26.6, GPU wait 20.0, present 5.7; ... | on AC power (no battery: a desktop PC)")
# What 1.1.4 printed on the i3-3240 + old GT 730 (tier 1) at 0.5x: GPU 66 % busy, told to lower the resolution.
OLD_I3 = HEAD + " | GPU-bound: the graphics need 32.2 ms a frame -- a lower Internal resolution is what helps"
# What patch 0075 prints for the same window (one frame in flight, RSX_FRAMES_IN_FLIGHT=1) ...
TURN_I3 = (HEAD + " | CPU and GPU in turn: the game needs 24.5 ms a frame and the render translation 6.6, then the "
           "frame waits 20.0 ms for the graphics card (an old graphics card: resource binding tier 1), busy 66 % of "
           "the time with 1 frame in flight")
# ... and with two frames in flight, the default on a dedicated card, when the card is then the limit.
CARD_I3 = (HEAD + " | GPU-bound: the graphics card needs 33.0 ms a frame at Lowest (0.5x) -- the card itself is the "
           "limit (an old graphics card: resource binding tier 1), a lower Internal resolution saves little")
CPU_2C = (HEAD + " | CPU-bound: the game needs 22.1 ms a frame and the render translation 6.6 (2 processor cores: "
          "2-core mode); the graphics card is busy 30 % of the time (resource binding tier 2) -- a lower Internal "
          "resolution does not help")
GPU_4K = (HEAD + " | GPU-bound: the graphics need 22.9 ms a frame -- a lower Internal resolution is what helps")


class Verdict(unittest.TestCase):
    def test_runtime_prints_what_the_launcher_reads(self):
        # the old verdict keeps its words (the launcher's regex), now only where a lower resolution helps
        self.assertIn('" | GPU-bound: the graphics need %.1f ms a frame%s -- a lower "', patch_text())
        p = added(patch_text())
        for want in ('" | GPU-bound: the graphics card needs %.1f ms a frame at %s -- "',
                     '"the card itself is the limit%s, a lower Internal resolution saves little"',
                     '"Internal resolution Lowest may help a little; the card itself is the limit%s"',
                     "slowish && busy >= 0.85 && rscale > 0.99f",
                     "const int slowish = (slow + n_late) * 10 >= frames && slow + n_late >= 10;",
                     '" | CPU and GPU in turn: the game needs %.1f ms a frame and the "',
                     '"render translation %.1f, then the frame waits %.1f ms for the graphics card%s, busy %.0f %% "',
                     '" | CPU-bound: the game needs %.1f ms a frame and the render "',
                     '"translation %.1f%s; the graphics card is busy %.0f %% of the time%s -- a lower Internal "',
                     '" (an old graphics card: resource binding tier 1)"'):
            self.assertIn(want, p)
        # a lower resolution only with the GPU near 100 % busy, and above Native or on integrated graphics
        self.assertIn("slowish && busy >= 0.85 && (igpu || rscale > 1.01f)", p)
        self.assertNotIn("n_gpu * 2 >= slow", p)

    def test_launcher_reads_each_verdict(self):
        self.assertTrue(core.SLOW_GPU_BOUND.match(GPU_4K))
        self.assertFalse(core.SLOW_GPU_BOUND.match(CARD_I3))
        self.assertTrue(core.SLOW_CARD_BOUND.match(CARD_I3))
        self.assertEqual(core.SLOW_CPU_BOUND.match(CPU_2C).groups(), ("22.1", "6.6"))
        self.assertEqual(core.SLOW_CPU_BOUND.match(TURN_I3).groups(), ("24.5", "6.6"))
        self.assertIsNone(core.SLOW_CPU_BOUND.match(CARD_I3))

    def test_speed_hint_after_a_game(self):
        self.assertIn("Internal resolution in Settings", core.speed_hint([GPU_4K]))
        card = core.speed_hint([CARD_I3, CARD_I3, TURN_I3])
        self.assertIn("graphics card", card)
        self.assertNotIn("choose a lower", card)
        cpu = core.speed_hint([CPU_2C])
        self.assertIn("processor", cpu)
        self.assertIn("does not help", cpu)
        self.assertIn("processor", core.speed_hint([TURN_I3]))
        self.assertIsNone(core.speed_hint([HEAD]))
        # 1.1.4's line for the same PC still reads as before (old logs in a report)
        self.assertIn("GPU-bound", core.speed_hint([OLD_I3]))

    def test_problem_report_lines(self):
        out = report.speed_diagnosis([CARD_I3, TURN_I3, CPU_2C], [])
        text = " ".join(out)
        self.assertIn("graphics card itself was the limit in 1 of the last 3", text)
        self.assertIn("at Lowest (0.5x)", text)
        self.assertIn("processor was the limit in 2 of the last 3", text)
        self.assertIn("in 1 of them the frames also waited for the graphics card", text)
        self.assertNotIn("lower Internal resolution is what helps", text)
        self.assertEqual(report.speed_diagnosis([HEAD], []), [])

    def test_catalogs(self):
        for lang in ("de", "es", "fr", "ja", "ko", "pt_br"):
            with open(os.path.join(ROOT, "lobby", "t5lobby", f"i18n_{lang}.py"), encoding="utf-8") as f:
                cat = f.read()
            for key in ("Fights were slower than 60 fps because of the graphics card: it is too slow for this game. "
                        "Internal resolution Lowest helps a little at most.",
                        "Fights were slower than 60 fps because of the processor: close other programs while you "
                        "play. A lower Internal resolution does not help."):
                self.assertIn(f'"{key}":', cat, lang)


class Warmup(unittest.TestCase):
    """tools/shader_warmup.py and how the build and the Build tab run it."""

    def setUp(self):
        import shader_warmup
        self.w = shader_warmup

    def test_fights_cover_the_stage_select_and_every_fighter(self):
        # (Jinpachi, id 35, is locked offline: his warm-up fight never started)
        lines = self.w.fight_lines(18)
        self.assertEqual([s for s, _, _, _ in lines], list(range(17, 35)))
        self.assertEqual(sorted(set(f for _, p1, p2, _ in lines for f in (p1, p2))), list(range(35)))
        self.assertNotIn(35, [f for _, p1, p2, _ in self.w.fight_lines(99) for f in (p1, p2)])   # Jinpachi: locked
        self.assertEqual(lines[0][3], "0,1,17,1")
        self.assertEqual(len(self.w.fight_lines(99)), 33)        # 18 + the 15 Tekken 5 stages

    def test_no_game_no_warmup(self):
        import io
        from contextlib import redirect_stdout
        with tempfile.TemporaryDirectory() as d, redirect_stdout(io.StringIO()) as out:
            with mock.patch.object(sys, "argv", ["shader_warmup.py", "--out", d]):
                self.assertEqual(self.w.main(), 0)
        self.assertIn("no built game", out.getvalue())

    def test_once_per_build(self):
        import io
        from contextlib import redirect_stdout
        with tempfile.TemporaryDirectory() as d:
            exe = os.path.join(d, "build", "cmake", "t5dr.exe")
            elf = os.path.join(d, "game", "vfs", "PS3_GAME", "USRDIR", "EBOOT.elf")
            for f in (exe, elf):
                os.makedirs(os.path.dirname(f), exist_ok=True)
                open(f, "wb").close()
            cache = os.path.join(d, self.w.CACHE)
            os.makedirs(cache)
            with open(os.path.join(cache, self.w.MARKER), "w") as f:
                json.dump({"exe": self.w.exe_stamp(exe)}, f)
            argv = ["shader_warmup.py", "--out", d]
            no_game = AssertionError("started a game")
            with redirect_stdout(io.StringIO()) as out, mock.patch.object(sys, "argv", argv), \
                    mock.patch.object(self.w.subprocess, "Popen", side_effect=no_game):
                self.assertEqual(self.w.main(), 0)
            self.assertIn("already done for this build", out.getvalue())

    def test_build_tab_progress(self):
        step, ev = core.build_line_events(None, "[shaders]")
        self.assertEqual(step, "shaders")
        self.assertIn(("step", "shaders"), ev)
        _, ev = core.build_line_events("shaders", "[warmup] fight 4 of 18: stage 20, fighters 6 and 7")
        self.assertIn(("sub", 3 / 18), ev)
        _, ev = core.build_line_events("shaders", "  already done")
        self.assertIn(("skip", "shaders"), ev)
        self.assertIn("shaders", core.STEP_TITLES)
        self.assertIn("shaders", core.STEP_WEIGHT)

    def test_launcher_asks_for_it(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIn("--warmup", core.BuildRun("a.pkg", "b.rap", d).cmd)

    def test_shipped(self):
        import package_release
        self.assertIn("tools/shader_warmup.py", package_release.OUR_FILES)


class Runtime(unittest.TestCase):
    def test_frames_in_flight_default(self):
        p = added(patch_text())
        self.assertIn('else if (g_ld_gpu_uma == 0) { v = 2; g_ld_fif_why = "a dedicated graphics card"; }', p)
        self.assertIn('"[pacing] frames in flight: 1 (%s)', p)
        self.assertIn("RSX_FRAMES_IN_FLIGHT=1 = one", p)

    def test_two_core_switches(self):
        p = patch_text()
        for want in ("PS3_TWO_CORE", "PS3_TWO_CORE_OWN", "PS3_TWO_CORE_GAME", "hsp_two_core(",
                     "2-core mode (PS3_TWO_CORE)", "int host_sched_two_core(void)"):
            self.assertIn(want, p)
        # measured slower on a 2-core stand-in: off unless asked
        self.assertIn("#define HS_TWO_OWN_DEFAULT 0", p)

    def test_slow_gpu_hook_is_test_only(self):
        p = added(patch_text())
        self.assertIn('getenv("RSX_TEST_SLOW_GPU")', p)
        self.assertIn("if (g_ld_sg_cfg) {   /* RSX_TEST_SLOW_GPU (test hook) */", p)
        self.assertIn("    ld_frame_end_extras();", p)          # before every present (not the FIFO flip method)

    def test_texture_fast_path(self):
        p = added(patch_text())
        for want in ("static void decode_argb8_identity(", "o[x] = (v >> 8) | (v << 24);", 'getenv("RSX_TEX_FAST")',
                     'getenv("RSX_TEX_FAST_CHECK")', "(remap & 0xFFFFu) == 0xAAE4u", "base_fmt == TEX_FMT_A8R8G8B8"):
            self.assertIn(want, p)

    def test_ring_guard_per_slot(self):
        self.assertIn("static u64* g_ldg_blk[LD_SLOTS_MAX][LDG_N];", added(patch_text()))

    def test_files_it_touches(self):
        files = re.findall(r"(?m)^diff --git a/(\S+)", patch_text())
        self.assertEqual(sorted(files), sorted(set(files)))
        for f in files:
            self.assertTrue(f.startswith(("libs/video/", "runtime/")), f)

    def test_documented(self):
        with open(os.path.join(ROOT, "docs", "RENDER_PERF.md"), encoding="utf-8") as f:
            doc = f.read()
        self.assertIn("## 2-core mode and slow graphics cards (patch 0075, branch `speed-115`)", doc)
        for want in ("PS3_TWO_CORE", "RSX_FRAMES_IN_FLIGHT", "RSX_TEST_SLOW_GPU", "CPU-bound"):
            self.assertIn(want, doc)


if __name__ == "__main__":
    unittest.main()
