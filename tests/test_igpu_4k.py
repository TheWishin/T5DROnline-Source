"""4K on integrated graphics (ps3recomp patch 0063, docs/RENDER_PERF.md "4K on integrated graphics"): the
launcher's hints (Internal resolution above the screen on integrated graphics, Auto, the GPU-bound note after a
game), Power saving Auto reaching the game, the problem report's speed lines, and the runtime texts they read --
the launcher parses lines the runtime prints, so both sides are checked against each other here. No game or GPU
needed."""
import os
import sys
import tempfile
import unittest

from helpers import ROOT

sys.path.insert(0, os.path.join(ROOT, "launcher"))
sys.path.insert(0, os.path.join(ROOT, "lobby"))
import core  # noqa: E402
import problem_report as report  # noqa: E402

PATCH = os.path.join(ROOT, "patches", "ps3recomp", "0063-igpu-4k-stall.patch")


def patch_text():
    with open(PATCH, encoding="utf-8") as f:
        return f.read()


# What 1.1.2's runtime printed on the 780M player's PC (the format of patch 0047, unchanged).
GPU_780M = ("[gpu] adapter: AMD Radeon 780M Graphics (vendor 1002, 8101 MB, feature level 12_2, resource binding "
            "tier 3, heap tier 2, integrated) -- the high-performance GPU")
GPU_3090 = ("[gpu] adapter: NVIDIA GeForce RTX 3090 (vendor 10DE, 24322 MB, feature level 12_2, resource binding "
            "tier 3, heap tier 2, dedicated) -- the high-performance GPU")
SLOW_BOUND = ("[slow-frames] last 30 s: 1104 frames, 1088 slow (over 20.9 ms): CPU 22 (game 16, render translation 5, "
              "vblank thread late 1), GPU 1061, present 5; median per frame: game 9.0 ms, translation 17.6, GPU wait "
              "13.9, present 0.3; game part 9.1 ms on average: main thread running 8.6, waiting for the renderer "
              "0.0, for other game threads 0.6 (its processor time 8.3 ms a frame); GPU busy 22.9 ms a frame (84 % of the time, "
              "integrated graphics) | on AC power | GPU-bound: the graphics need 22.9 ms a frame (integrated "
              "graphics) -- a lower Internal resolution is what helps")
SLOW_IGPU = ("[slow-frames] last 30 s: 1220 frames, 768 slow (over 20.9 ms): ... | on AC power | integrated graphics "
             "busy 64 % of the time: they share the processor's power and memory, so a lower Internal resolution "
             "also speeds up the game's own work")
SLOW_PLAIN = "[slow-frames] last 30 s: 1795 frames, 3 slow (over 20.9 ms): ... | on AC power"


class Launcher(unittest.TestCase):
    def test_gpu_from_the_last_log(self):
        d = tempfile.mkdtemp(prefix="t5dr-igpu")
        os.makedirs(os.path.join(d, "logs"))
        for name, gpu in (("game-20261020-110000.log", GPU_3090), ("game-20261020-120000.log", GPU_780M)):
            with open(os.path.join(d, "logs", name), "w", encoding="utf-8") as f:
                f.write("[sched] power saving off (PS3_LAPTOP=0)\n" + gpu + "\n[display] internal resolution 4K\n")
        self.assertEqual(core.last_gpu(d), ("AMD Radeon 780M Graphics", True))       # the newest log
        self.assertIsNone(core.last_gpu(tempfile.mkdtemp()))
        self.assertEqual(core.GPU_LINE.match(GPU_3090).group(2), "dedicated")

    def test_runtime_prints_what_the_launcher_reads(self):
        p = patch_text()
        # the verdicts at the end of a [slow-frames] line
        self.assertIn('" | GPU-bound: the graphics need %.1f ms a frame%s -- a lower "', p)
        self.assertIn('" | integrated graphics busy %.0f %% of the time: they share the "', p)
        self.assertTrue(core.SLOW_GPU_BOUND.match(SLOW_BOUND))
        self.assertTrue(core.SLOW_IGPU_BUSY.match(SLOW_IGPU))
        self.assertTrue(report.SLOW_VERDICT_GPU.search(SLOW_BOUND))
        self.assertTrue(report.SLOW_VERDICT_IGPU.search(SLOW_IGPU))

    def test_hint_on_integrated_graphics_above_the_screen(self):
        self.assertEqual(core.igpu_res_better("4k", (1920, 1080), True), "1080p")
        self.assertEqual(core.igpu_res_better("4k", (2560, 1440), True), "1080p")      # 1440p screen: 1080p cap
        self.assertEqual(core.igpu_res_better("1440p", (1920, 1080), True), "1080p")
        self.assertEqual(core.igpu_res_better("1080p", (1366, 768), True), "native")
        # 1.1.4: above Auto's step, not only above the screen (a busy built-in GPU slows the processor too)
        self.assertEqual(core.igpu_res_better("1440p", (2560, 1440), True), "1080p")
        self.assertEqual(core.igpu_res_better("4k", None, True), "1080p")             # Auto: at most 1080p
        for key, screen, igpu in (("4k", (1920, 1080), False),      # a discrete card: no hint
                                  ("1080p", (1920, 1080), True),    # matches the screen
                                  ("native", (1280, 720), True),
                                  ("auto", (1920, 1080), True),     # Auto never goes above the screen
                                  ("1080p", (2560, 1440), True),    # Auto's own step
                                  ("1080p", None, True)):
            self.assertIsNone(core.igpu_res_better(key, screen, igpu), (key, screen, igpu))

    def test_auto_step(self):
        cases = {((1920, 1080), True): "1080p", ((2560, 1440), True): "1080p", ((3840, 2160), True): "1080p",
                 ((1366, 768), True): "native", ((2560, 1440), False): "1440p", ((3840, 2160), False): "4k",
                 ((1280, 720), False): "native"}
        for (screen, igpu), step in cases.items():
            self.assertEqual(core.internal_res_auto(*screen, igpu), step, (screen, igpu))

    def test_auto_is_a_choice_not_the_default(self):
        d = tempfile.mkdtemp(prefix="t5dr-igpu")
        p = os.path.join(d, "launcher.json")
        self.assertEqual(core.Settings(p)["internal_res"], "native")
        with open(p, "w", encoding="utf-8") as f:
            f.write('{"internal_res": "auto"}')
        s = core.Settings(p)
        self.assertEqual(s["internal_res"], "auto")
        self.assertEqual(s.env_overrides()["PS3_INTERNAL_RES"], "auto")
        self.assertIn("auto", core.INTERNAL_RES_HINTS)
        self.assertNotIn("auto", core.INTERNAL_RES_STEPS)
        self.assertIn('_stricmp(e, "auto") == 0', patch_text())

    def test_speed_hint_after_a_game(self):
        self.assertIn("GPU-bound", core.speed_hint([SLOW_PLAIN, SLOW_BOUND]))
        self.assertIn("integrated", core.speed_hint([SLOW_IGPU]))
        self.assertIsNone(core.speed_hint([SLOW_PLAIN]))
        self.assertIsNone(core.speed_hint([]))
        d = tempfile.mkdtemp(prefix="t5dr-igpu")
        log = os.path.join(d, "game.log")
        with open(log, "w", encoding="utf-8") as f:
            f.write("[fps] 38.0\n" + SLOW_BOUND + "\n[fps] 37.9\n")
        self.assertEqual(core.slow_frame_lines(log), [SLOW_BOUND])


class Report(unittest.TestCase):
    def test_speed_lines(self):
        facts = [GPU_780M, "[display] internal resolution 4K (3x) from PS3_INTERNAL_RES: display buffers 3840x2160"]
        out = report.speed_diagnosis([SLOW_PLAIN, SLOW_IGPU], facts, [(1920, 1080)])
        self.assertEqual(len(out), 2)
        self.assertIn("Integrated graphics busy up to 64 %", out[0])
        self.assertIn("1080p would match it", out[1])
        out = report.speed_diagnosis([SLOW_BOUND], [GPU_3090], [(1920, 1080)])
        self.assertEqual(len(out), 1)
        self.assertIn("GPU-bound in 1 of the last 1", out[0])
        self.assertEqual(report.speed_diagnosis([SLOW_PLAIN], [GPU_780M], [(1920, 1080)]), [])
        # 1080p internal on a 1080p screen: nothing to say
        self.assertEqual(report.speed_diagnosis([], [GPU_780M, "[display] internal resolution 1080p (1.5x) from x"],
                                                [(1920, 1080)]), [])

    def test_long_slow_frames_lines_are_kept(self):
        d = tempfile.mkdtemp(prefix="t5dr-igpu")
        log = os.path.join(d, "game.log")
        long_line = SLOW_BOUND + " " + "x" * 200
        with open(log, "w", encoding="utf-8") as f:
            f.write(long_line + "\n")
        got = report.run_lines_from_log(log)
        self.assertEqual(got, [long_line])           # the verdict at the end is not cut off


class Runtime(unittest.TestCase):
    def test_patch_contents(self):
        p = patch_text()
        # frames in flight: a switch, one slot by default (two were slower on integrated graphics)
        self.assertIn("v = e && *e == '2' ? 2 : 1;", p)
        # GPU timestamps on unless RSX_GPU_TIME=0 ([slow-frames] GPU busy)
        self.assertIn("if (e && *e == '0') return;", p)
        # the main thread's waits by kind, bracketed in every blocking call
        for f in ("sys_semaphore.c", "sys_event.c", "sys_lwsync.c", "sys_cond.c", "sys_mutex.c", "sys_timer.c",
                  "cellGcmSys.c"):
            self.assertRegex(p, r"diff --git a/\S*%s" % f.replace(".", r"\."))
        self.assertIn("host_sched_main_wait_end(s->rsx_posted ? HS_WAIT_RSX : HS_WAIT_GAME, mw0);", p)
        self.assertIn("host_sched_main_wait_end(HS_WAIT_FLIP, mw0);", p)
        # a semaphore posted from a GCM handler is the renderer's
        self.assertIn("s->rsx_posted = host_sched_in_gcm_handler();", p)
        # the real processor clock from PDH, by English counter names (works on any Windows language)
        self.assertIn('L"\\\\Processor Information(_Total)\\\\% Processor Performance"', p)

    def test_the_clock_query_is_set_up_off_the_vblank_ticker(self):
        """review-113: host_sched_clock_text's caller is the vblank ticker ([slow-frames]); the PDH query's set-up
        (PdhOpenQuery + PdhAddEnglishCounter, ~0.3-0.4 s the first time in a process) ran right there and froze the
        game's clock once per run. The set-up is a thread of its own now; the function itself only collects."""
        p = patch_text()
        i = p.index("+int host_sched_clock_text(char* buf, int len)")
        body = p[i:p.index("\n+}\n", i)]
        self.assertIn("CreateThread(NULL, 0, hs_clock_setup", body)
        for call in ("LoadLibraryA(", "open(NULL", "add(", "PdhAddEnglishCounter"):
            self.assertNotIn(call, body)
        setup = p[p.index("+static DWORD WINAPI hs_clock_setup"):i]
        self.assertIn('LoadLibraryA("pdh.dll")', setup)
        self.assertIn("InterlockedExchange(&s_clk_state, 1)", setup)


if __name__ == "__main__":
    unittest.main()
