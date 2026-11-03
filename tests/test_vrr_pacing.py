"""Patch 0103 host-only policy/wait regressions; no upstream tree or game.

The compiled tests extract the exact new headers from the patch. They use a
fake clock/OS, never game data, sockets or real wall-clock waits. Authored for
maintainer execution; do not run when the task prohibits builds/runs.
"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "patches/ps3recomp/0103-vrr-pacing.patch"


def added_file(patch, path):
    marker = f"diff --git a/{path} b/{path}\n"
    section = patch.split(marker, 1)[1].split("\ndiff --git ", 1)[0]
    return "\n".join(line[1:] for line in section.splitlines()
                     if line.startswith("+") and not line.startswith("+++")) + "\n"


class Integration(unittest.TestCase):
    def setUp(self):
        self.patch = PATCH.read_text(encoding="utf-8")
        self.added = "\n".join(s[1:] for s in self.patch.splitlines()
                               if s.startswith("+") and not s.startswith("+++"))

    def test_default_off_and_unsupported_inline_paths(self):
        self.assertIn('getenv("PS3_VRR_PACING")', self.added)
        self.assertIn("e && *e == '2' ? 2 : 0", self.added)
        for gate in ("!g_ldp.fs_exclusive", "!g_ld_lock_mode", "g_xo_on > 0",
                     "DXGI_PRESENT_ALLOW_TEARING", "GetForegroundWindow() == g_ldp.hwnd"):
            self.assertIn(gate, self.added)
        self.assertIn("pace.present_target_qpc = 0", self.added)
        self.assertIn("vrr_heartbeat_next", self.added)

    def test_immutable_packet_real_present_and_safe_ownership(self):
        self.assertIn("packet->target = pace", self.added)
        self.assertIn("g_rq_on_present_target", self.added)
        self.assertIn("else g_rq_on_present(((const rq_u32*)p)->v)", self.added)
        self.assertIn("ps->entry = ld_pf_qpc()", self.added)
        self.assertIn("ps->returned = ld_pf_qpc()", self.added)
        self.assertIn("ps->entry - ps->previous_entry", self.added)
        self.assertNotIn("-    if (work) rsx_live_draw_sync();", self.patch)
        for forbidden in ("vm_write", "guest_write", "vm_memcpy_to", "vm_memset"):
            self.assertNotIn(forbidden, self.added)

    def test_network_hold_and_true_release_snapshot(self):
        self.assertIn("cellGcm_vrr_external_hold", self.added)
        self.assertIn("pace->external_hold_serial ==", self.added)
        self.assertIn("rsx_live_draw_pace_actual_release(release_qpc.QuadPart", self.added)
        self.assertIn("release_after_flip", self.added)

    def test_logging_is_bounded_and_disk_writer_separate(self):
        self.assertIn("LD_PF_ROWS = 256", self.added)
        self.assertIn("ld_pf_enqueue(row", self.added)
        self.assertIn("fwrite(g_pf_rows[slot].text", self.added)
        self.assertIn("g_pf_dropped++", self.added)
        self.assertIn("present_interval_us", self.added)
        self.assertIn("trace_dropped", self.added)


class FakeClockAndOS(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cc = shutil.which("cc") or shutil.which("clang") or shutil.which("gcc")
        if not cls.cc:
            raise unittest.SkipTest("C11 compiler needed for game-free fake-clock tests")

    def compile_and_check(self, source, header, fake_os=False):
        patch = PATCH.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d)
            (tmp / header).write_text(added_file(patch, "runtime/platform/" + header), encoding="utf-8")
            exe = tmp / ("vrr-test.exe" if os.name == "nt" else "vrr-test")
            cmd = [self.cc, "-std=c11", "-O2", "-I", str(tmp)]
            if fake_os:
                cmd += ["-I", str(ROOT / "tests/c/vrr_fake")]
            cmd += [str(ROOT / "tests/c" / source), "-o", str(exe)]
            build = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("PASS:", result.stdout)

    def test_exact_policy_with_fake_clock(self):
        self.compile_and_check("vrr_pacer_test.c", "host_pacer.h")

    def test_exact_windows_wait_with_fake_os(self):
        self.compile_and_check("vrr_wait_test.c", "host_pacer_win.h", fake_os=True)


if __name__ == "__main__":
    unittest.main()
