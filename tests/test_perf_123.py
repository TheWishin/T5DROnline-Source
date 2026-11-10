"""1.2.3 performance (ps3recomp patch 0123, docs/RENDER_PERF.md "1.2.3: frames held before the GPU starts them"):
a list's wait in the queue before the GPU starts it ("GPU queue" in [slow-frames]), the "GPU held" verdict for a
frame that waits for a mostly idle GPU (report YESB6Y: GT 730 Fermi on a 75 Hz screen, "GPU wait 23 ms" at 17 %
busy, called CPU-bound before), the vsync fallback for a display faster than the game, and what the launcher and
the problem report read from that line. No game or GPU needed: both sides are checked against each other."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from helpers import ROOT

for _d in ("launcher", "lobby", "tools"):
    if os.path.join(ROOT, _d) not in sys.path:
        sys.path.append(os.path.join(ROOT, _d))
import core  # noqa: E402
import problem_report as report  # noqa: E402

PATCH = os.path.join(ROOT, "patches", "ps3recomp", "0123-perf-123.patch")


def added():
    with open(PATCH, encoding="utf-8") as f:
        return "\n".join(ln[1:] for ln in f.read().splitlines() if ln.startswith("+") and not ln.startswith("+++"))


HEAD = ("[slow-frames] last 30 s: 1198 frames, 1047 slow (over 20.9 ms): CPU 3 (game 0, render translation 3, vblank "
        "thread late 0), GPU 1044, present 0; 79 late for their vblank, shown when translated; median per frame: game "
        "1.4 ms, translation 25.0, GPU wait 24.0, present 0.0; game part 1.4 ms on average: main thread running 1.3, "
        "waiting for the renderer 0.0, for other game threads 0.1 (its processor time 1.5 ms a frame); GPU busy 4.1 ms "
        "a frame (16 % of the time); GPU queue: 21.0 ms a frame held before the GPU started it (median 22.4 ms a "
        "list), 1190 of 1198 lists held 1 ms or more, 1101 of them until just after a display refresh; worst 30.4 ms "
        "(GPU); vblank clock 55.94 Hz | on AC power (no battery: a desktop PC)")
# what 1.2.2 printed for that window
OLD = (HEAD + " | CPU-bound: the game needs 1.4 ms a frame and the render translation 1.0; the graphics card is busy "
       "16 % of the time (an old graphics card: resource binding tier 1) -- a lower Internal resolution does not help")
# what patch 0123 prints for it
HELD = (HEAD + " | GPU held: the frame waits 24.0 ms for the graphics card, which works 4.1 ms of it (busy 16 % of "
        "the time), an old graphics card (resource binding tier 1); it starts a frame 22.4 ms after it gets it "
        "(37.5 fps = the 75 Hz display's refresh rate / 2) -- the graphics driver or the display holds the frames "
        "back, not the processor; a lower Internal resolution does not help; vsync is off from now on (no tearing)")
CPU = (HEAD + " | CPU-bound: the game needs 22.1 ms a frame and the render translation 6.6 (2 processor cores: "
       "2-core mode); the graphics card is busy 30 % of the time (resource binding tier 2) -- a lower Internal "
       "resolution does not help")


class Runtime(unittest.TestCase):
    def test_verdict_words(self):
        p = added()
        for want in ('" | GPU held: the frame waits %.1f ms for the graphics card, which "',
                     '"works %.1f ms of it (busy %.0f %% of the time)%s%s%s -- the graphics driver or the display "',
                     '"holds the frames back, not the processor; a lower Internal resolution does not help%s"',
                     '"; it starts a frame %.1f ms after it gets it"',
                     '" (%.1f fps = the %u Hz display\'s refresh rate / %d)"',
                     '"; vsync is off from now on (no tearing)"',
                     '"; GPU queue: %.1f ms a frame held before the GPU started "'):
            self.assertIn(want, p)
        # only when the frames wait (4 ms or more) and the GPU is mostly idle, never on integrated graphics
        self.assertIn("slowish && !igpu && busy >= 0 && busy < 0.5 && m_wait >= 4.0 && m_wait >= gpart", p)

    def test_hold_is_measured_against_the_list_before(self):
        p = added()
        # hold = start - max(submit, the previous list's end): a list behind a busy GPU is not held
        self.assertIn("const double avail = g_gh.prev_end > (double)submit ? g_gh.prev_end : (double)submit;", p)
        self.assertIn("GetClockCalibration", p)
        # one harvester at a time (the ticker and the walker both harvest)
        self.assertIn("TryAcquireSRWLockExclusive(&g_gh.lock)", p)

    def test_vsync_fallback_only_on_a_faster_unlocked_display(self):
        p = added()
        self.assertIn("g_ld_refresh_hz <= 61", p)
        self.assertIn("g_ld_lock_mode", p)
        self.assertIn('getenv("RSX_HOLD_VSYNC")', p)
        # never tearing: interval 0 with the present flags as they are (no ALLOW_TEARING added)
        self.assertIn("g_ld_present_interval = 0;", p)
        self.assertNotIn("g_ld_present_flags |= DXGI_PRESENT_ALLOW_TEARING", p)
        # a monitor change keeps it
        self.assertIn("g_ld_present_interval = slow || g_ld_hold_vsync_off ? 0 : g_ld_interval_cfg;", p)


class RingWrap(unittest.TestCase):
    """The title's command ring wraps about once a second; its callback (cellGcm_fifo_recycle) waits for the
    walker as before, but woken by it instead of polling with Sleep(1)."""
    def test_same_condition_woken_by_the_walker(self):
        p = added()
        self.assertIn("if (s_recycle_waiters) WakeByAddressAll((PVOID)&g_gcm_fifo_drained_ea);", p)
        self.assertIn("WaitOnAddress((volatile VOID*)&g_gcm_fifo_drained_ea, (PVOID)&seen, sizeof seen, 1);", p)
        self.assertIn('getenv("PS3_GCM_RECYCLE_WAKE")', p)
        # the old wait stays the fallback, and the loop's condition and bound are unchanged
        self.assertIn("            Sleep(1);", p)
        with open(PATCH, encoding="utf-8") as f:
            text = f.read()
        self.assertIn(" while (g_gcm_fifo_drained_ea != begin && spins < 2000) {", text)
        self.assertNotIn("-    while (g_gcm_fifo_drained_ea != begin && spins < 2000) {", text)


class Launcher(unittest.TestCase):
    def test_launcher_reads_the_new_verdict(self):
        self.assertEqual(core.SLOW_GPU_HELD.match(HELD).group(1), "24.0")
        self.assertIsNone(core.SLOW_CPU_BOUND.match(HELD))
        self.assertIsNone(core.SLOW_GPU_HELD.match(OLD))

    def test_speed_hint(self):
        hint = core.speed_hint([HELD, HELD, CPU])
        self.assertIn("graphics card waited for its driver or the screen", hint)
        self.assertIn("VSync Off", hint)
        self.assertNotIn("processor", hint)
        self.assertIn("processor", core.speed_hint([HELD, CPU, CPU]))

    def test_problem_report(self):
        text = " ".join(report.speed_diagnosis([HELD, CPU], []))
        self.assertIn("held back before the graphics card started them in 1 of the last 2", text)
        self.assertIn("busy at most 16 %", text)
        self.assertIn("processor was the limit in 1 of the last 2", text)

    def test_catalogs(self):
        key = ("Fights were slower than 60 fps: the graphics card waited for its driver or the screen and was mostly "
               "idle. Try VSync Off in Settings. A lower Internal resolution does not help.")
        for lang in ("de", "es", "fr", "ja", "ko", "pt_br"):
            with open(os.path.join(ROOT, "lobby", "t5lobby", f"i18n_{lang}.py"), encoding="utf-8") as f:
                self.assertIn('"%s":' % key, f.read(), lang)


def find_tree():
    """A ps3recomp tree with patch 0123 (PS3RECOMP_DIR, else deps/ps3recomp)."""
    for d in (os.environ.get("PS3RECOMP_DIR"), os.path.join(ROOT, "deps", "ps3recomp")):
        f = d and os.path.join(d, "libs", "video", "rsx_vp_decompiler.c")
        if f and os.path.isfile(f):
            with open(f, encoding="utf-8", errors="replace") as fh:
                if "rsx_vp_const_range" in fh.read():
                    return d
    return None


class ConstRange(unittest.TestCase):
    """tests/c/vp_const_range_test.c: the constants a vertex program can read, against the HLSL the
    decompiler makes of it (20,000 random programs), and two narrowed analyses it must catch."""
    @classmethod
    def setUpClass(cls):
        if os.name != "nt":
            raise unittest.SkipTest("built with the Windows C compiler")
        cls.tree = find_tree()
        if not cls.tree:
            raise unittest.SkipTest("no ps3recomp tree with patch 0123 (PS3RECOMP_DIR)")
        sys.path.insert(0, os.path.dirname(__file__))
        from test_xlat_cpu import find_vcvars
        vcvars = find_vcvars()
        llvm = os.path.join("C:" + os.sep, "Program Files", "LLVM", "bin", "clang-cl.exe")
        clang = shutil.which("clang-cl") or (llvm if os.path.isfile(llvm) else None)
        if not vcvars or not (clang or shutil.which("cl")):
            raise unittest.SkipTest("no Windows C compiler")
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        exe = os.path.join(cls.tmp.name, "vp_const_range_test.exe")
        inc = [os.path.join(cls.tree, *p) for p in (("libs", "video"), ("libs",), ("runtime",), ("include",))]
        src = os.path.join(ROOT, "tests", "c", "vp_const_range_test.c")
        cc = f'"{clang}"' if clang else "cl"
        flags = " ".join(f'/I "{d}"' for d in inc)
        cmd = (f'"{vcvars}" >nul 2>&1 && {cc} /nologo /O1 /W0 {flags} "{src}" /Fe:"{exe}" '
               f'/Fo:"{os.path.join(cls.tmp.name, "vp_const_range_test.obj")}"')
        r = subprocess.run(f'cmd /s /c "{cmd}"', capture_output=True, text=True, timeout=600)
        if not os.path.isfile(exe):
            raise AssertionError("could not build tests/c/vp_const_range_test.c: " + (r.stdout + r.stderr)[-1500:])
        cls.exe = exe

    def test_range_covers_every_read(self):
        r = subprocess.run([self.exe], capture_output=True, text=True, timeout=300, cwd=self.tmp.name)
        self.assertEqual(r.returncode, 0, r.stdout[-3000:])
        self.assertRegex(r.stdout, r"(?m)^PASS \d+ checks$")
        self.assertRegex(r.stdout, r"(?m)^MOV c\[37\]: exact 1 range 37\.\.37$")


class ConstRangeRuntime(unittest.TestCase):
    def test_reuse_needs_the_constants(self):
        p = added()
        # a block is reused only when it holds every constant this draw's program can read
        self.assertIn("for (int k = 0; k < 8; k++) missing |= need[k] & ~s_cb_mask[k];", p)
        self.assertIn("g.rsx.constants_gen == s_cb_gen && !missing &&", p)
        self.assertIn("memcpy(cbdst + c * 16u, g.rsx.constants[c], (e - c) * 16u);", p)
        self.assertIn("memcpy(s_cb_mask, need, sizeof(s_cb_mask));", p)
        self.assertIn('getenv("RSX_VP_CONST_RANGE")', p)
        # the ring still steps a whole block (the layout the shader's cbuffer expects)
        self.assertNotIn("g.cb_used += bytes", p)


if __name__ == "__main__":
    unittest.main()
