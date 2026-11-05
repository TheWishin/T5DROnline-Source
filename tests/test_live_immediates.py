"""Exact opt-in instruction immediates retain runtime behavior after lifting."""
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from helpers import ROOT
from test_ps_hid import find_vcvars


class LiveImmediates(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        deps = Path(os.environ.get("PS3RECOMP_DIR", str(Path(ROOT) / "deps/ps3recomp")))
        cls.script = deps / "tools/ppu_lifter.py"
        if not cls.script.is_file() or "def load_live_immediates(" not in cls.script.read_text(encoding="utf-8"):
            raise unittest.SkipTest("requires prepared ps3recomp with patch 0120")
        spec = importlib.util.spec_from_file_location("test_live_lifter", cls.script)
        cls.lifter = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.lifter
        spec.loader.exec_module(cls.lifter)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)

    def manifest(self, sites):
        path = self.folder / "live.json"
        path.write_text(json.dumps(dict(schema=1, sites=sites)))
        return path

    def program(self, words=(0x38600064, 0x2F830063, 0x38800007, 0x4E800020)):
        path = self.folder / "toy.bin"
        path.write_bytes(struct.pack(">%dI" % len(words), *words))
        return path

    def test_manifest_rejects_duplicate_and_unaligned_sites(self):
        for sites in ([dict(address="0x10001", expected_word="0x38600064")],
                      [dict(address="0x10000", expected_word="0x38600064")] * 2):
            with self.assertRaises(ValueError):
                self.lifter.load_live_immediates(self.manifest(sites))

    def test_cli_rejects_missing_changed_and_unsupported_instruction(self):
        program = self.program()
        for address, word in [(0x20000, 0x38600064), (0x10000, 0x38600063), (0x1000C, 0x4E800020)]:
            manifest = self.manifest([dict(address=hex(address), expected_word=hex(word))])
            r = subprocess.run([sys.executable, str(self.script), str(program), "--raw", "--base", "0x10000",
                                "--live-immediates", str(manifest), "-o", str(self.folder / "out")],
                               capture_output=True, text=True, timeout=30)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("missing, unsupported or changed instruction", r.stderr)

    def test_parallel_and_serial_lifts_emit_identical_dynamic_bodies(self):
        words = [0x38600064, 0x2F830063, 0x38800007, 0x4E800020] * 120
        program = self.program(words)
        functions = self.folder / "functions.json"
        functions.write_text(json.dumps([dict(start=hex(0x10000 + 16*i), end=hex(0x10010 + 16*i)) for i in range(120)]))
        manifest = self.manifest([dict(address="0x10000", expected_word="0x38600064"),
                                  dict(address="0x10004", expected_word="0x2F830063")])
        outputs = []
        for jobs in (1, 2):
            out = self.folder / str(jobs)
            r = subprocess.run([sys.executable, str(self.script), str(program), "--raw", "--base", "0x10000",
                                "--functions", str(functions), "--live-immediates", str(manifest), "--jobs", str(jobs),
                                "--single-file", "-o", str(out)], capture_output=True, text=True, timeout=90)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            outputs.append((out / "ppu_recomp.c").read_text())
            header = (out / "ppu_live_immediates.h").read_text()
            self.assertIn("T5DR_LIVE_IMMEDIATE_ABI 1", header)
            self.assertIn("T5DR_LIVE_IMMEDIATE_COUNT 2", header)
        self.assertEqual(outputs[0], outputs[1])
        self.assertIn("vm_read32(0x00010000u)", outputs[0])

    def test_no_manifest_keeps_constant_codegen_and_reports_abi_zero(self):
        out = self.folder / "plain"
        functions = self.folder / "plain-functions.json"
        functions.write_text(json.dumps([dict(start="0x10000", end="0x10010")]))
        r = subprocess.run([sys.executable, str(self.script), str(self.program()), "--raw", "--base", "0x10000",
                            "--functions", str(functions), "--jobs", "1", "--single-file", "-o", str(out)],
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("T5DR_LIVE_IMMEDIATE_ABI 0", (out / "ppu_live_immediates.h").read_text())
        self.assertNotIn("vm_read32(0x00010000u)", (out / "ppu_recomp.c").read_text())

    def test_native_runtime_mutation_with_and_without_register_promotion(self):
        clang = shutil.which("clang-cl") or r"C:\Program Files\LLVM\bin\clang-cl.exe"
        vcvars = find_vcvars() if os.name == "nt" else None
        if not vcvars or not Path(clang).is_file():
            self.skipTest("requires clang-cl and Visual Studio build tools")
        functions = []
        for promoted in (False, True):
            lifter = self.lifter.PPULifter()
            lifter.regpromo = promoted
            lifter.live_immediates = {0x10000: 0x38600064, 0x10004: 0x2F830063}
            lifter.lift_function(self.lifter.disassemble_bytes(self.program().read_bytes(), 0x10000, True), 0x10000, 0x10010)
            emitted = lifter.emit_source()
            match = re.search(r"void func_00010000\(ppu_context\* ctx\) \{(.*?)\n\}", emitted, re.S)
            self.assertIsNotNone(match, emitted[-2000:])
            functions.append("void run_%d(ppu_context* ctx) {%s\n}" % (promoted, match.group(1)))
        source = self.folder / "native.cpp"
        source.write_text("""#include <stdint.h>
#include <stdio.h>
struct ppu_context { uint64_t gpr[32] = {}; uint32_t cr = 0, xer = 0; };
static uint32_t words[3];
uint32_t vm_read32(uint32_t address) { return words[(address - 0x10000) / 4]; }
""" + "\n".join(functions) + """
int main() {
  for (auto run : {run_0, run_1}) {
    ppu_context ctx;
    words[0] = 0x38600064; words[1] = 0x2F830063; words[2] = 0x38800009;
    run(&ctx);
    if (ctx.gpr[3] != 100 || (ctx.cr & 15) != 4 || ctx.gpr[4] != 7) return 1;
    words[1] = 0x2F830077;
    run(&ctx);
    if (ctx.gpr[3] != 100 || (ctx.cr & 15) != 8 || ctx.gpr[4] != 7) return 2;
    words[0] = 0x38600078;
    run(&ctx);
    if (ctx.gpr[3] != 120 || (ctx.cr & 15) != 4 || ctx.gpr[4] != 7) return 3;
    words[0] = 0x3860FFFF;
    run(&ctx);
    if (ctx.gpr[3] != UINT64_MAX || (ctx.cr & 15) != 8) return 4;
  }
  puts("PASS runtime immediates, sign extension, unselected constants, regpromo on/off");
}
""".replace("for (auto run : {run_0, run_1})", "void (*runs[])(ppu_context*) = {run_0, run_1}; for (auto run : runs)"))
        exe = self.folder / "native.exe"
        command = (f'"{vcvars}" >nul 2>&1 && "{clang}" /nologo /std:c++17 /EHsc /O2 '
                   f'"{source}" /Fe:"{exe}" /Fo:"{self.folder / "native.obj"}"')
        r = subprocess.run(f'cmd /s /c "{command}"', capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = subprocess.run([str(exe)], capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("PASS runtime immediates", r.stdout)


class BuildLiveImmediates(unittest.TestCase):
    def test_eu_manifest_changes_invalidate_lift_cache_and_code_identity(self):
        sys.path.insert(0, str(Path(ROOT) / "tools"))
        import build_game as build
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recomp, tools = root / "recomp", root / "tools"
            recomp.mkdir(); tools.mkdir()
            (tools / "ppu_lifter.py").write_text("# test lifter\n")
            manifest = root / "manifest.json"
            manifest.write_text('{"schema":1,"sites":[{"address":"0x10000","expected_word":"0x38600064"}]}')
            paths = SimpleNamespace(tools=str(tools), recomp=str(recomp), analysis=str(root / "analysis"), elf=str(root / "toy.elf"))
            calls = []
            def run(command):
                calls.append(command)
                if str(command[1]).endswith("ppu_lifter.py"):
                    (recomp / "ppu_recomp.h").write_text("# test header\n")
                    count, digest = build.live_immediate_identity(str(manifest))
                    (recomp / "ppu_live_immediates.h").write_text(
                        '#define T5DR_LIVE_IMMEDIATE_ABI 1\n'
                        f'#define T5DR_LIVE_IMMEDIATE_COUNT {count}\n'
                        f'#define T5DR_LIVE_IMMEDIATE_MANIFEST_SHA256 "{digest}"\n')
            patches = [mock.patch.object(build, "P", paths), mock.patch.object(build, "EU_LIVE_IMMEDIATES", str(manifest)),
                       mock.patch.object(build, "mac_modules", return_value=False), mock.patch.object(build, "run", side_effect=run),
                       mock.patch.object(build, "need_program", return_value={"key":"eu_online", "code_end":"0x20000"})]
            import contextlib
            with contextlib.ExitStack() as stack:
                for patch in patches: stack.enter_context(patch)
                build.step_lift(SimpleNamespace(force=False))
                self.assertIn("--live-immediates", calls[-1])
                self.assertEqual(calls[-1][-1], str(manifest))
                before = len(calls)
                build.step_lift(SimpleNamespace(force=False))
                self.assertEqual(len(calls), before)
                (recomp / "ppu_live_immediates.h").unlink()
                build.step_lift(SimpleNamespace(force=False))
                self.assertEqual(len(calls), before + 3)
                (recomp / "ppu_live_immediates.h").write_text("")
                build.step_lift(SimpleNamespace(force=False))
                self.assertEqual(len(calls), before + 6)
                manifest.write_text('{"schema":1,"sites":[{"address":"0x10000","expected_word":"0x38600065"}]}')
                build.step_lift(SimpleNamespace(force=False))
                self.assertEqual(len(calls), before + 9)
            with mock.patch.object(build, "EU_LIVE_IMMEDIATES", str(manifest)), mock.patch.object(build, "prebuilt_host", return_value=False):
                first = build.code_id()
                manifest.write_text("changed again")
                self.assertNotEqual(first, build.code_id())


if __name__ == "__main__":
    unittest.main()
