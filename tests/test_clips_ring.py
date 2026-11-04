"""Compile the exact bounded ring shipped by patch 0119; no game or network."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "patches/ps3recomp/0119-clips.patch"


def ring_header():
    if PATCH.is_file():
        patch = PATCH.read_text(encoding="utf-8")
        marker = "diff --git a/libs/video/rsx_clips_ring.h b/libs/video/rsx_clips_ring.h\n"
        section = patch.split(marker, 1)[1].split("\ndiff --git ", 1)[0]
        return "\n".join(line[1:] for line in section.splitlines()
                         if line.startswith("+") and not line.startswith("+++")) + "\n"
    tree = os.environ.get("PS3RECOMP_DIR")
    if tree:
        header = Path(tree) / "libs/video/rsx_clips_ring.h"
        if header.is_file():
            return header.read_text(encoding="utf-8-sig")
    raise FileNotFoundError("patch 0119 or PS3RECOMP_DIR containing rsx_clips_ring.h required")


def find_vcvars():
    pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    vswhere = Path(pf86) / "Microsoft Visual Studio/Installer/vswhere.exe"
    if vswhere.is_file():
        found = subprocess.run([str(vswhere), "-latest", "-products", "*", "-property", "installationPath"],
                               capture_output=True, text=True, timeout=30)
        for line in found.stdout.splitlines():
            path = Path(line.strip()) / "VC/Auxiliary/Build/vcvars64.bat"
            if path.is_file():
                return path
    return None


class ClipsRing(unittest.TestCase):
    def test_native_ring(self):
        # All compiler output and executable artifacts stay in this worktree.
        scratch = ROOT / "build/clips/ring-tests"
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as temporary:
            tmp = Path(temporary)
            (tmp / "rsx_clips_ring.h").write_text(ring_header(), encoding="utf-8")
            source = ROOT / "tests/c/clips_ring_test.cpp"
            exe = tmp / ("ring.exe" if os.name == "nt" else "ring")
            if os.name == "nt":
                clang = shutil.which("clang-cl")
                fallback = Path(r"C:\Program Files\LLVM\bin\clang-cl.exe")
                clang = clang or (str(fallback) if fallback.is_file() else None)
                vcvars = find_vcvars()
                if not clang or not vcvars:
                    self.skipTest("Windows clang-cl and Visual Studio C++ toolchain required")
                command = (f'"{vcvars}" >nul 2>&1 && "{clang}" /nologo /std:c++17 /EHsc /O2 /W4 '
                           f'/I"{tmp}" "{source}" /Fe:"{exe}" /Fo:"{tmp / "ring.obj"}"')
                built = subprocess.run(f'cmd /s /c "{command}"', capture_output=True, text=True,
                                       timeout=60, cwd=tmp)
            else:
                compiler = shutil.which("c++") or shutil.which("clang++") or shutil.which("g++")
                if not compiler:
                    self.skipTest("C++17 compiler required")
                built = subprocess.run([compiler, "-std=c++17", "-O2", "-Wall", "-Wextra", "-I", str(tmp),
                                        str(source), "-o", str(exe)], capture_output=True, text=True,
                                       timeout=60, cwd=tmp)
            self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
            ran = subprocess.run([str(exe)], capture_output=True, text=True, timeout=30, cwd=tmp)
            self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)
            self.assertRegex(ran.stdout, r"PASS: [1-9][0-9]* clips ring checks")


if __name__ == "__main__":
    unittest.main()
