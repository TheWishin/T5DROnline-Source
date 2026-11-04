"""Guard the production live renderer's capture wiring and GPU buffer lifetime."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_clips_ring import ROOT, PATCH, find_vcvars


def live_section():
    patch = PATCH.read_text(encoding="utf-8")
    marker = "diff --git a/libs/video/rsx_live_draw.c b/libs/video/rsx_live_draw.c\n"
    return patch.split(marker, 1)[1].split("\ndiff --git ", 1)[0]


def added_live_source():
    return "\n".join(line[1:] for line in live_section().splitlines()
                     if line.startswith("+") and not line.startswith("+++"))


class LiveClipWiring(unittest.TestCase):
    def test_actual_composed_present_submits_capture_before_signalling(self):
        section = live_section()
        self.assertIn("ld_present_body", section)
        call = section.index("const int clip_slot = ld_clips_record(bb, g_ldp.bb_w, g_ldp.bb_h)")
        flush = section.index("ld_flush(LD_FLUSH_PRESENT)", call)
        signal = section.index("g.queue->lpVtbl->Signal(", flush)
        self.assertLess(call, flush)
        self.assertLess(flush, signal)
        source = added_live_source()
        self.assertIn("LDL->lpVtbl->CopyTextureRegion", source)
        self.assertIn("LDL->lpVtbl->ResourceBarrier", source)
        self.assertIn("#define LD_CLIP_READBACKS 3", source)
        self.assertIn("g_ld_clip_fence->lpVtbl->GetCompletedValue", source)
        self.assertIn("padh_peek_cached", source)
        self.assertNotIn("WaitForSingleObject", source)
        self.assertNotIn("SetEventOnCompletion", source)

    @unittest.skipUnless(os.name == "nt", "Windows SDK capture-lifetime harness")
    def test_inflight_readbacks_survive_failed_present_or_shutdown_flush(self):
        source = added_live_source()
        declarations = source[source.index("#define LD_CLIP_READBACKS"):source.index("static void ld_clips_controls")]
        start = source.index("static void ld_clips_release(void)")
        opening = source.index("{", start)
        depth, end = 1, opening + 1
        while depth:
            depth += (source[end] == "{") - (source[end] == "}")
            end += 1
        release = source[start:end]
        scratch = ROOT / "build/clips/live-tests"
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as directory:
            work = Path(directory)
            (work / "clips_live_release.h").write_text(declarations + release, encoding="utf-8")
            clang = shutil.which("clang-cl") or r"C:\Program Files\LLVM\bin\clang-cl.exe"
            vcvars = find_vcvars()
            self.assertIsNotNone(vcvars, "Windows SDK toolchain required")
            exe = work / "lifetime.exe"
            command = (f'@echo off\ncall "{vcvars}" >nul 2>&1\n'
                       f'"{clang}" /nologo /TC /O2 /MT /I"{work}" '
                       f'"{ROOT / "tests/c/clips_live_test.c"}" /Fo"{work / "lifetime.obj"}" '
                       f'/Fe"{exe}"\n')
            script = work / "build.cmd"
            script.write_text(command, encoding="ascii")
            built = subprocess.run(["cmd.exe", "/c", str(script)], capture_output=True, text=True, timeout=60)
            self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
            result = subprocess.run([str(exe)], capture_output=True, text=True, timeout=10,
                                    creationflags=subprocess.BELOW_NORMAL_PRIORITY_CLASS)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("PASS: incomplete GPU copies retain buffers and fence", result.stdout)


if __name__ == "__main__":
    unittest.main()
