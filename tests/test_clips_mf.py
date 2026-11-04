"""Opt-in Windows MF integration: synthetic pixels/tone, no game or network.

PS3_CLIPS_MF_TEST=1 python -m unittest discover -s tests -p test_clips_mf.py -v
Requires one heavy slot. Outputs remain under build/clips/mf-tests.
"""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import time
import unittest

from test_clips_ring import ROOT, PATCH, find_vcvars


def patched_file(name):
    patch = PATCH.read_text(encoding="utf-8")
    marker = f"diff --git a/{name} b/{name}\n"
    section = patch.split(marker, 1)[1].split("\ndiff --git ", 1)[0]
    return "\n".join(line[1:] for line in section.splitlines()
                     if line.startswith("+") and not line.startswith("+++")) + "\n"


def config_hash():
    real = Path(os.environ.get("USERPROFILE", "")) / "AppData/Local/OpenRecomp/config.json"
    return hashlib.sha256(real.read_bytes()).hexdigest() if real.is_file() else "absent"


@unittest.skipUnless(os.name == "nt" and os.environ.get("PS3_CLIPS_MF_TEST") == "1",
                     "opt in with PS3_CLIPS_MF_TEST=1 on Windows (one heavy slot)")
class ClipsMediaFoundation(unittest.TestCase):
    def test_synthetic_encode_remux_decode(self):
        before = config_hash()
        scratch = ROOT / "build/clips/mf-tests"
        scratch.mkdir(parents=True, exist_ok=True)
        def guard():
            after = config_hash()
            (scratch / "config-guard.log").write_text(f"before={before}\nafter={after}\n", encoding="utf-8")
            self.assertEqual(before, after)
        self.addCleanup(guard)
        clang = shutil.which("clang-cl") or r"C:\Program Files\LLVM\bin\clang-cl.exe"
        vcvars = find_vcvars()
        self.assertIsNotNone(vcvars, "Visual Studio toolchain required")
        runtime = scratch / "runtime"
        for name in ("rsx_clips.cpp", "rsx_clips.h", "rsx_clips_ring.h"):
            dst = runtime / "libs/video" / name
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(patched_file("libs/video/" + name), encoding="utf-8")
        stub = runtime / "runtime/platform/host_sched.h"
        stub.parent.mkdir(parents=True, exist_ok=True)
        stub.write_text('extern "C" int host_sched_laptop(void);\n', encoding="utf-8")
        exe = scratch / "clips_mf_test.exe"
        obj = scratch / "clips_mf_test.obj"
        command = (f'call "{vcvars}" >nul 2>&1\n'
                   f'"{clang}" /nologo /std:c++20 /EHsc /O2 /D_CRT_SECURE_NO_WARNINGS '
                   f'/I"{runtime / "libs/video"}" "{ROOT / "tests/c/clips_mf_test.cpp"}" '
                   f'/Fo"{obj}" /Fe"{exe}" /link oleaut32.lib propsys.lib\n')
        build = scratch / "build.cmd"
        build.write_text("@echo off\n" + command, encoding="ascii")
        built = subprocess.run(["cmd", "/c", str(build)], capture_output=True, text=True,
                               timeout=60, cwd=scratch)
        (scratch / "compile.log").write_text(built.stdout + built.stderr, encoding="utf-8")
        self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
        for mode in ("disabled", "power-saving", "missing-mf", "software", "hardware"):
            lock = None
            # No test can silently bypass occupied heavy slots.
            deadline = time.monotonic() + max(0, int(os.environ.get("PS3_CLIPS_WAIT_SLOT", "0")))
            while True:
                for name in ("HEAVY3.lock", "HEAVY2.lock", "HEAVY.lock"):
                    path = Path(r"C:\T5DROnline\build\int115") / name
                    try:
                        with path.open("x", encoding="ascii") as f:
                            f.write(f"clips {time.strftime('%Y-%m-%d %H:%M:%S')} synthetic MF {mode}\n")
                        lock = path
                        break
                    except FileExistsError:
                        pass
                if lock or time.monotonic() >= deadline:
                    break
                time.sleep(2)
            self.assertIsNotNone(lock, "All heavy slots occupied; rerun this opt-in integration test later")
            try:
                env = dict(os.environ, PS3_AUDIO_MUTE="1", PS3_WINDOW_BACKGROUND="1")
                for key, sub in (("OPENRECOMP_HOME", "openrecomp"), ("APPDATA", "roaming"),
                                 ("LOCALAPPDATA", "local")):
                    directory = scratch / "isolated" / sub
                    directory.mkdir(parents=True, exist_ok=True)
                    env[key] = str(directory)
                result = subprocess.run([str(exe), str(scratch / f"synthetic {mode}.mp4"), mode],
                                        capture_output=True, text=True, timeout=90, cwd=scratch, env=env,
                                        creationflags=subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS)
                (scratch / f"{mode}.log").write_text(result.stdout + result.stderr +
                                                   f"\nexit={result.returncode}\n", encoding="utf-8")
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("PASS: remux decoded 120 video frames" if mode in ("software", "hardware")
                              else "PASS: disabled capture policy", result.stdout)
            finally:
                lock.unlink()


if __name__ == "__main__":
    unittest.main()
