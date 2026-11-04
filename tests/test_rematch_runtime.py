"""Rematch runtime regressions; fake host input and a headless overlay, no game/server.

Source checks always run. Optional C harnesses exercise overlay composition
and the prepared runtime's actual pad sampler with a fake clock.
"""
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "patches/ps3recomp/0089-ingame-rematch-overlay.patch"
BASE = ROOT / "patches/ps3recomp/0045-training-overlay.patch"
TAP_PATCH = ROOT / "patches/ps3recomp/0116-ui-pad-tap-latch.patch"


def added_files(patch):
    """Read new-file source from the checked-in runtime patch, no dependency checkout."""
    files = {}
    name = None
    for line in patch.splitlines():
        if line.startswith("diff --git "):
            name = None
        elif line.startswith("+++ b/"):
            name = line[6:]
            files[name] = []
        elif name and line.startswith("+") and not line.startswith("+++"):
            files[name].append(line[1:])
    return {name: "\n".join(lines) + "\n" for name, lines in files.items()}


def overlay_after_patch():
    files = added_files(BASE.read_text(encoding="utf-8"))
    patch = PATCH.read_text(encoding="utf-8")
    name = None
    lines = patch.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("+++ b/"):
            name = line[6:]
        elif line.startswith("@@ ") and name in files:
            old, new = [], []
            i += 1
            while i < len(lines) and not lines[i].startswith(("@@ ", "diff --git ")):
                item = lines[i]
                if item.startswith((" ", "-")):
                    old.append(item[1:])
                if item.startswith((" ", "+")):
                    new.append(item[1:])
                i += 1
            old, new = "\n".join(old) + "\n", "\n".join(new) + "\n"
            if files[name].count(old) != 1:
                raise AssertionError(f"ambiguous/missing patch context in {name}: {old[:80]!r}")
            files[name] = files[name].replace(old, new, 1)
            continue
        i += 1
    return files


HARNESS = r'''
#include "rsx_overlay.h"
#include <assert.h>
#include <string.h>

static rsx_overlay_quad quads[16384];
static int layout(void) {
    return rsx_overlay_layout(1280,720,1280,720,quads,16384);
}
int main(void) {
    /* Old overlay has no per-layer clear and loses the menu/training list. */
    rsx_overlay_begin();
    rsx_overlay_rect(10,20,30,40,0x123456FFu);
    rsx_overlay_end();
    assert(layout()==1 && quads[0].rgba==0x123456FFu);
    rsx_overlay_begin_layer(1);
    rsx_overlay_rect(50,60,70,80,0xABCDEF88u);
    rsx_overlay_end();
    assert(layout()==1 && quads[0].rgba==0xABCDEF88u);
    rsx_overlay_clear();
    assert(layout()==1 && quads[0].rgba==0xABCDEF88u);
    rsx_overlay_begin();
    rsx_overlay_rect(1,2,3,4,0x333333FFu);
    rsx_overlay_end();
    assert(layout()==1 && quads[0].rgba==0xABCDEF88u);
    rsx_overlay_clear_layer(1);
    assert(layout()==1 && quads[0].rgba==0x333333FFu);
    rsx_overlay_clear_layer(999);
    assert(layout()==1 && quads[0].rgba==0x333333FFu);
    rsx_overlay_begin_layer(999);
    rsx_overlay_rect(1,1,10,10,0xFFFFFFFFu);
    rsx_overlay_end();
    assert(layout()==1 && quads[0].rgba==0x333333FFu);
    rsx_overlay_clear();
    assert(layout()==0);
    /* A headless renderer never claims ready and steals the launcher. */
    assert(rsx_overlay_ready()==0);
    assert(rsx_overlay_text_supported("Rematch?"));
    assert(rsx_overlay_text_supported("\xC3\x84\xC3\xB6\xC3\x9F"));
    assert(!rsx_overlay_text_supported("\xC0\xAF"));
    assert(!rsx_overlay_text_supported("\xE3\x81"));
    assert(!rsx_overlay_text_supported("\xED\xA0\x80"));
    assert(!rsx_overlay_text_supported(NULL));
    const char* native[] = { "\xE5\x86\x8D\xE6\x88\xA6", "\xEC\x9E\xAC\xEB\x8C\x80\xEA\xB2\xB0" };
    for (unsigned i=0;i<2;i++) {
        assert(!rsx_overlay_text_supported(native[i]));
        const int prepared=rsx_overlay_text_prepare(native[i]);
        const int supported=rsx_overlay_text_supported(native[i]);
        assert(prepared==supported);
#ifdef _WIN32
        /* Font installs vary: when coverage is claimed, real pixel quads
         * and measured advance are mandatory; no '?' substitution. */
        if (supported) {
            assert(rsx_overlay_text_width(native[i],4)>0);
            rsx_overlay_begin_layer(1);
            rsx_overlay_text(100,100,4,0xFFFFFFFFu,0,native[i]);
            rsx_overlay_end();
            assert(layout()>1);
            for (int q=0,n=layout();q<n;q++) assert(quads[q].glyph==-1);
        }
#else
        assert(!supported);
#endif
    }
    return 0;
}
'''


class RematchRuntimePatch(unittest.TestCase):
    def test_patch_context_and_required_api(self):
        files = overlay_after_patch()
        source = files["libs/video/rsx_overlay.c"]
        for api in ("rsx_overlay_begin_layer", "rsx_overlay_clear_layer", "rsx_overlay_ready",
                    "rsx_overlay_text_supported", "rsx_overlay_text_prepare"):
            self.assertIn(api, source)
            self.assertIn(api, files["libs/video/rsx_overlay.h"])
        self.assertIn("GetGlyphIndicesW", source)
        self.assertIn("L\"Yu Gothic UI\"", source)
        self.assertIn("L\"Malgun Gothic\"", source)
        self.assertIn("g_native_cache[512]", source)

    def test_ui_pad_has_a_reader_independent_of_gameplay(self):
        patch = PATCH.read_text(encoding="utf-8")
        source = added_files(patch)["libs/input/cellPad.c"]
        # The header also declares this API. Inspect the implementation's body,
        # excluding prototypes and other functions that happen to sample pads.
        functions = re.findall(
            r"(?ms)^s32 cellPad_peek_local\([^;{}]*\)\s*\{(.*?)^\}", source)
        self.assertEqual(len(functions), 1, "expected one cellPad_peek_local definition")
        function = functions[0]
        # Apply the follow-up's call-site hunk to the original API. The old
        # current-only peek loses a complete press during a long live frame.
        patch = TAP_PATCH.read_text(encoding="utf-8")
        removed = "padh_sample(port_no, &st, padh_min_interval_us());"
        added = "padh_read(port_no, PADH_READER_UI, &st, padh_min_interval_us());"
        self.assertIn("-    " + removed, patch)
        self.assertIn("+    " + added, patch)
        self.assertIn(removed, function)
        function = function.replace(removed, added)
        self.assertIn(added, function)
        self.assertNotIn("PADH_READER_GAME", function)
        self.assertNotIn("PADH_READER_LOCAL", function)
        self.assertNotIn("cellPad_sample_local(", function)
        self.assertNotIn("pad_poll_backend(", function)
        self.assertIn("PADH_READER_UI    = 2", patch)
        self.assertIn("PADH_READERS      = 3", patch)

    def test_hunk_counts(self):
        for path in (PATCH, TAP_PATCH):
            with self.subTest(patch=path.name):
                lines = path.read_text(encoding="utf-8").splitlines()
                for i, line in enumerate(lines):
                    match = re.match(r"@@ -\d+,(\d+) \+\d+,(\d+) @@", line)
                    if not match:
                        continue
                    hunk = []
                    for item in lines[i + 1:]:
                        if item.startswith(("diff --git ", "@@ ")):
                            break
                        hunk.append(item)
                    self.assertEqual(int(match[1]), sum(s.startswith((" ", "-")) for s in hunk))
                    self.assertEqual(int(match[2]), sum(s.startswith((" ", "+")) for s in hunk))

    def test_headless_layer_behavior(self):
        compiler = os.environ.get("CC")
        if not compiler and os.name != "nt":
            compiler = shutil.which("cc") or shutil.which("clang") or shutil.which("gcc")
        if not compiler:
            self.skipTest("set CC to a C compiler for the standalone overlay harness")
        files = overlay_after_patch()
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            for name in ("rsx_overlay.c", "rsx_overlay.h"):
                (work / name).write_text(files[f"libs/video/{name}"], encoding="utf-8")
            (work / "test.c").write_text(HARNESS, encoding="utf-8")
            exe = work / ("overlay_test.exe" if os.name == "nt" else "overlay_test")
            command = [compiler, "-std=c17", "-DRSX_OVERLAY_NO_D3D", str(work / "rsx_overlay.c"),
                       str(work / "test.c"), "-o", str(exe)]
            command += ["-lgdi32", "-luser32"] if os.name == "nt" else ["-pthread", "-lm"]
            subprocess.run(command, check=True, capture_output=True, text=True)
            subprocess.run([str(exe)], check=True, capture_output=True, text=True)


class RematchTapRuntime(unittest.TestCase):
    """Compile the real runtime's sampler/delivery with explicit fake-clock samples."""

    def test_press_during_a_long_frame_and_reader_independence(self):
        if os.name != "nt":
            self.skipTest("the runtime's pad layer is Windows only")
        from test_ps_hid import find_ps3recomp, find_vcvars
        tree = find_ps3recomp()
        vcvars = find_vcvars()
        compiler = shutil.which("clang-cl") or r"C:\Program Files\LLVM\bin\clang-cl.exe"
        if not tree or not vcvars or not os.path.isfile(compiler):
            self.skipTest("requires the patched runtime, clang-cl and Visual Studio build tools")
        header = Path(tree, "libs/input/pad_host.h").read_text(encoding="utf-8")
        self.assertIn("PADH_READER_UI", header, "prepare the runtime through patch 0116")
        with tempfile.TemporaryDirectory() as directory:
            executable = os.path.join(directory, "rematch_ui_tap_test.exe")
            source = ROOT / "tests/c/rematch_ui_tap_test.c"
            includes = " ".join(f'/I "{Path(tree, *p)}"' for p in
                                (("libs", "input"), ("libs",), ("runtime",), ("include",)))
            command = (f'"{vcvars}" >nul 2>&1 && "{compiler}" /nologo /O1 /W0 {includes} '
                       f'"{source}" /Fe:"{executable}" /Fo:"{directory}/rematch_ui_tap_test.obj"')
            build = subprocess.run(f'cmd /s /c "{command}"', capture_output=True, text=True, timeout=120)
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            result = subprocess.run([executable, os.path.join(directory, "pad.txt")],
                                    capture_output=True, text=True, timeout=15, cwd=directory)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertRegex(result.stdout, r"PASS \d+ checks")


if __name__ == "__main__":
    unittest.main()
