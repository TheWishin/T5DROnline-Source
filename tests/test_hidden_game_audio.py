"""Compile the actual hidden-window mute block with fake window/audio state."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class HiddenAudioTest(unittest.TestCase):
    def test_hidden_boot_park_restore_and_permanent_mute(self):
        patch = (ROOT / "patches/ps3recomp/0118-hidden-game-audio.patch").read_text(encoding="utf-8")
        block = "\n".join(line[1:] for line in patch.splitlines() if
                          line.startswith((" ", "+")) and not line.startswith("+++"))
        source = r'''
#include <cstring>
#include <cassert>
#define _WIN32 1
typedef void* HWND;
static bool visible, iconic, exists, permanent, enabled;
static float s_mix_buffer[4];
static const char* fake_env(const char* key) {
    if (!strcmp(key,"PS3_AUDIO_MUTE")) return permanent?"1":nullptr;
    if (!strcmp(key,"PS3_AUDIO_MUTE_HIDDEN")) return enabled?"1":nullptr;
    return nullptr;
}
#define getenv fake_env
void* rsx_null_backend_get_hwnd(void) { return exists?(void*)1:nullptr; }
int IsWindowVisible(HWND) { return visible; }
int IsIconic(HWND) { return iconic; }
static void submit() {
''' + block + r'''
}
static void check(bool silence) {
    for (float& v:s_mix_buffer) v=0.25f;
    submit();
    for (float v:s_mix_buffer) assert(v==(silence?0.0f:0.25f));
}
int main(int argc,char** argv) {
    permanent=argv[1][0]=='1'; enabled=argv[2][0]=='1';
    exists=false; visible=false; iconic=false; check(permanent||enabled); // hidden boot
    exists=true; visible=true; check(permanent); // game shown
    iconic=true; check(permanent||enabled); // minimized practice tool
    iconic=false; visible=false; check(permanent||enabled); // parked persistent game
    visible=true; check(permanent); // same process restored for next match
}
'''
        compiler = shutil.which("clang++") or shutil.which("g++")
        vcvars = None
        if os.name == "nt":
            from test_ps_hid import find_vcvars
            vcvars = find_vcvars()
            compiler = shutil.which("clang-cl") or r"C:\Program Files\LLVM\bin\clang-cl.exe"
            if not vcvars or not os.path.isfile(compiler):
                self.skipTest("requires clang-cl and Visual Studio build tools")
        elif not compiler:
            self.skipTest("requires a C++17 compiler")
        with tempfile.TemporaryDirectory(dir=ROOT / "tests") as directory:
            work = Path(directory)
            src = work / "audio.cpp"
            src.write_text(source, encoding="utf-8")
            exe = work / ("audio.exe" if os.name == "nt" else "audio")
            command = [compiler, "-std=c++17", str(src), "-o", str(exe)]
            if vcvars:
                command = (f'"{vcvars}" >nul 2>&1 && "{compiler}" /nologo /std:c++17 /EHsc '
                           f'"{src}" /Fe:"{exe}" /Fo:"{work / "audio.obj"}"')
                command = f'cmd /s /c "{command}"'
            build = subprocess.run(command, capture_output=True, text=True, timeout=120)
            self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
            for permanent in ("0", "1"):
                for enabled in ("0", "1"):
                    result = subprocess.run([str(exe), permanent, enabled], capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
