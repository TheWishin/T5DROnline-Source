"""Native synthetic modules prove capability checks reject stale and partial translations."""
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from helpers import ROOT
from test_ps_hid import find_vcvars

class LiveImmediateCapability(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.name != "nt": raise unittest.SkipTest("Windows native module fixture")
        cls.vcvars = find_vcvars()
        cls.clang = shutil.which("clang-cl") or r"C:\Program Files\LLVM\bin\clang-cl.exe"
        if not cls.vcvars or not os.path.isfile(cls.clang): raise unittest.SkipTest("no native compiler")
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.directory = Path(cls.temp.name)
        cls.exe = cls.directory / "live_immediates_test.exe"
        src = Path(ROOT) / "tests/c/live_immediates_test.cpp"
        cls.compile(f'/DPS3_GAME_DLL=1 /EHsc /std:c++17 "{src}" /Fe:"{cls.exe}" /Fo:"{cls.directory / "host.obj"}"')

    @classmethod
    def compile(cls, flags):
        cmd = f'"{cls.vcvars}" >nul 2>&1 && "{cls.clang}" /nologo /O1 {flags}'
        result = subprocess.run(f'cmd /s /c "{cmd}"', cwd=cls.directory, capture_output=True, text=True, timeout=120)
        if result.returncode: raise AssertionError(result.stdout + result.stderr)

    def test_loaded_module_capability_and_unload(self):
        variants = [("missing", None, ""), ("old", 0, "a" * 64), ("future", 2, "a" * 64),
                    ("partial", 1, "b" * 64), ("short", 1, "a" * 63), ("good", 1, "a" * 64)]
        source = Path(ROOT) / "tests/c/live_immediates_fake_dll.c"
        for name, abi, manifest in variants:
            with self.subTest(name=name):
                directory = self.directory / name
                directory.mkdir()
                config = directory / "config.h"
                config.write_text("#define OMIT_CAPABILITY\n" if abi is None else f'#define TEST_ABI {abi}u\n#define TEST_SHA "{manifest}"\n')
                module = directory / "t5dr_game.dll"
                self.compile(f'/TC /Zl /FI"{config}" /c "{source}" /Fo:"{directory / "fake.obj"}"')
                linker = shutil.which("lld-link") or str(Path(self.clang).with_name("lld-link.exe"))
                result = subprocess.run([linker, "/dll", "/noentry", "/nodefaultlib", str(directory / "fake.obj"),
                                         f"/out:{module}"], cwd=directory, capture_output=True, text=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                result = subprocess.run([str(self.exe), str(module), str(int(name == "good"))], cwd=directory,
                                        capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("PASS live-immediate ABI", result.stdout)

    def test_monolithic_generated_header_and_absent_header(self):
        source = Path(ROOT) / "tests/c/live_immediates_test.cpp"
        for supported in (False, True):
            with self.subTest(supported=supported):
                directory = self.directory / ("mono-good" if supported else "mono-old")
                directory.mkdir()
                if supported:
                    (directory / "ppu_live_immediates.h").write_text('#define T5DR_LIVE_IMMEDIATE_ABI 1u\n#define T5DR_LIVE_IMMEDIATE_MANIFEST_SHA256 "' + "a" * 64 + '"\n')
                exe = directory / "mono.exe"
                self.compile(f'/DTEST_MONOLITHIC=1 /DTEST_EXPECT_MONOLITHIC={int(supported)} /I"{directory}" /EHsc /std:c++17 '
                             f'"{source}" /Fe:"{exe}" /Fo:"{directory / "mono.obj"}"')
                result = subprocess.run([str(exe)], cwd=directory, capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
