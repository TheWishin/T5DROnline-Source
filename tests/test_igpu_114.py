"""Integrated graphics in 1.1.4 (docs/RENDER_PERF.md "4K on integrated graphics", "1.1.4: Auto by default on
integrated graphics"): Internal resolution Auto is the default when the last game rendered on integrated graphics
(a step the player chose stays), the warning for a step above Auto's fires whatever the fight's verdict, and the
Play tab's one-time note about a processor running well under its normal clock. No game or GPU needed."""
import json
import os
import shutil
import sys
import tempfile
import unittest

from helpers import ROOT

sys.path.insert(0, os.path.join(ROOT, "launcher"))
sys.path.insert(0, os.path.join(ROOT, "lobby"))
import core  # noqa: E402

GPU_780M = ("[gpu] adapter: AMD Radeon 780M Graphics (vendor 1002, 8101 MB, feature level 12_2, resource binding "
            "tier 3, heap tier 2, integrated) -- the high-performance GPU")
GPU_3090 = ("[gpu] adapter: NVIDIA GeForce RTX 3090 (vendor 10DE, 24322 MB, feature level 12_2, resource binding "
            "tier 3, heap tier 2, dedicated) -- the high-performance GPU")


def slow_line(frames=1795, slow=140, clock="processors at 2.26 GHz on average (81 % of their 2.79)",
              power='on AC power (no battery: a desktop PC), power plan "Balanced", processor clock limit 2795 of '
                    '2795 MHz', verdict=""):
    """A [slow-frames] line as patch 0063 prints it (the 780M player's 1.1.3 online fights: 4K, GPU busy 61 %, not
    GPU-bound, 6-10 % of the frames late, the processors at 81 % of their clock on the Balanced plan)."""
    return (f"[slow-frames] last 30 s: {frames} frames, {slow} slow (over 20.9 ms): CPU {slow} (game {slow}, render "
            f"translation 0, vblank thread late 0), GPU 0, present 0; {slow} late for their vblank, shown when "
            "translated; median per frame: game 12.0 ms, translation 3.6, GPU wait 0.0, present 0.5; game part "
            "12.0 ms on average: main thread running 11.2, waiting for the renderer 0.0, for other game threads 0.8 "
            "(its processor time 10.9 ms a frame); GPU busy 10.2 ms a frame (61 % of the time, integrated "
            "graphics); worst 41.2 ms (CPU, game); vblank clock 59.90 Hz; other programs 1.2 of 16 logical "
            "processors busy, the game 2.1 (of 16 it may use)" + (f"; {clock}" if clock else "") + f" | {power}"
            + verdict)


class Default(unittest.TestCase):
    def out_with(self, gpu_line):
        d = tempfile.mkdtemp(prefix="t5dr-igpu114")
        self.addCleanup(shutil.rmtree, d, True)
        if gpu_line:
            os.makedirs(os.path.join(d, "logs"))
            with open(os.path.join(d, "logs", "game-20261021-120000.log"), "w", encoding="utf-8") as f:
                f.write("[sched] power saving off\n" + gpu_line + "\n")
        return d

    def settings(self, out, **saved):
        p = os.path.join(out, "launcher.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(dict(saved, out=out), f)
        return core.Settings(p)

    def test_auto_on_integrated_graphics(self):
        for saved in ({}, {"internal_res": "native"}, {"internal_res": "native", "settings_version": 1}):
            s = self.settings(self.out_with(GPU_780M), **saved)
            self.assertFalse(s["internal_res_set"], saved)
            self.assertEqual(s.internal_res_choice(), "auto", saved)
            self.assertEqual(s.env_overrides()["PS3_INTERNAL_RES"], "auto", saved)

    def test_native_elsewhere(self):
        for gpu in (GPU_3090, None):            # a discrete card, or no game log yet
            s = self.settings(self.out_with(gpu))
            self.assertEqual(s.internal_res_choice(), "native")
            self.assertNotIn("PS3_INTERNAL_RES", s.env_overrides())
        self.assertEqual(core.DEFAULTS["internal_res"], "native")

    def test_a_chosen_step_stays(self):
        out = self.out_with(GPU_780M)
        # 1.1.3 and older: a step other than Native was the player's choice (Native was the default)
        for step in ("4k", "1440p", "1080p", "lower", "auto"):
            s = self.settings(out, internal_res=step)
            self.assertTrue(s["internal_res_set"], step)
            self.assertEqual(s.internal_res_choice(), step)
        # 1.1.4: Native picked in Settings stays Native on integrated graphics
        s = self.settings(out, internal_res="native", internal_res_set=True, settings_version=1)
        self.assertEqual(s.internal_res_choice(), "native")
        self.assertNotIn("PS3_INTERNAL_RES", s.env_overrides())
        s = self.settings(out, internal_res="4k", internal_res_set=True, settings_version=1)
        self.assertEqual(s.env_overrides()["PS3_INTERNAL_RES"], "4k")
        # Extra settings still win
        s = self.settings(out, extra_env="PS3_INTERNAL_RES=native")
        self.assertEqual(s.env_overrides()["PS3_INTERNAL_RES"], "native")

    def test_saved_with_the_version(self):
        out = self.out_with(GPU_780M)
        s = self.settings(out, internal_res="native")
        s.save()
        with open(s.path, encoding="utf-8") as f:
            saved = json.load(f)
        self.assertEqual(saved["settings_version"], core.SETTINGS_VERSION)
        self.assertIs(saved["internal_res_set"], False)
        self.assertEqual(core.Settings(s.path).internal_res_choice(), "auto")

    def test_launcher_marks_a_click_as_a_choice(self):
        with open(os.path.join(ROOT, "launcher", "t5dr_launcher.pyw"), encoding="utf-8") as f:
            src = f.read()
        self.assertIn("self.internal_res_var = tk.StringVar(value=self.settings.internal_res_choice())", src)
        i = src.index("def _internal_res_changed")
        body = src[i:src.index("\n    def ", i + 10)]
        self.assertIn('self.settings["internal_res_set"] = True', body)
        self.assertIn('style="warn.TLabel"', src)
        self.assertIn("core.igpu_res_text(t(core.INTERNAL_RES[key][0])", body)


class Hints(unittest.TestCase):
    def test_above_auto_on_integrated_graphics(self):
        text = core.igpu_res_text("4K (3x)", "1080p (1.5x)")
        self.assertIn("slows the processor", text)
        self.assertIn("Auto in Settings -> Internal resolution: 1080p (1.5x) here.", text)
        self.assertEqual(core.igpu_res_better("4k", (1920, 1080), True), "1080p")
        self.assertEqual(core.igpu_res_better("1440p", (2560, 1440), True), "1080p")   # fits the screen: still
        self.assertIsNone(core.igpu_res_better("1440p", (2560, 1440), False))

    def test_clock_hint(self):
        text = core.clock_hint([slow_line(slow=3), slow_line(), slow_line(slow=180,
                                clock="processors at 2.30 GHz on average (83 % of their 2.79)")])
        self.assertEqual(text, "Your processor ran at 2.28 GHz (82 % of its normal speed): set Windows power mode "
                               "to Best performance.")
        # the GPU-bound verdict after the power part does not hide it
        self.assertIsNotNone(core.clock_hint([slow_line(verdict=" | GPU-bound: the graphics need 22.9 ms a frame")]))

    def test_no_clock_hint(self):
        cases = {
            "full clock": [slow_line(clock="processors at 4.60 GHz on average (102 % of their 4.50)")],
            "just under": [slow_line(clock="processors at 4.10 GHz on average (91 % of their 4.50)")],
            "few late frames": [slow_line(slow=60)],              # 3 % of 1795
            "under 10 late": [slow_line(frames=150, slow=9)],
            "on battery": [slow_line(power='on battery (battery 80 %), power plan "Balanced"')],
            "no clock in the line": [slow_line(clock="")],
            "no lines": [],
        }
        for why, lines in cases.items():
            self.assertIsNone(core.clock_hint(lines), why)

    def test_runtime_prints_what_the_launcher_reads(self):
        with open(os.path.join(ROOT, "patches", "ps3recomp", "0063-igpu-4k-stall.patch"), encoding="utf-8") as f:
            p = f.read()
        self.assertIn('"processors at %.2f GHz on average (%.0f %% of their %.2f)"', p)
        # the clock right before " | " and the power text
        self.assertIn('clk[0] ? "; " : "", clk, pw[0] ? pw : "power state unknown", verdict);', p)
        self.assertIn('"%s%s%s%s | %s%s\\n"', p)
        with open(os.path.join(ROOT, "patches", "ps3recomp", "0047-laptop-power-saving.patch"),
                  encoding="utf-8") as f:
            self.assertIn('HS_PUT("on AC power");', f.read())

    def test_play_tab_says_it_once(self):
        with open(os.path.join(ROOT, "launcher", "t5dr_launcher.pyw"), encoding="utf-8") as f:
            src = f.read()
        i = src.index("def _speed_notes")
        body = src[i:src.index("\n    def ", i + 10)]
        self.assertIn('if not self.settings["clock_hint_shown"]:', body)
        self.assertIn('self.settings["clock_hint_shown"] = True', body)
        self.assertIn("core.igpu_res_better(", body)
        self.assertNotIn("powercfg", src)           # no Windows setting is changed by the launcher
        self.assertIs(core.DEFAULTS["clock_hint_shown"], False)


if __name__ == "__main__":
    unittest.main()
