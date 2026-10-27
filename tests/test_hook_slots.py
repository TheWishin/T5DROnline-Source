"""The lifter's hook slots (ps3recomp patch 0078, ppu_lifter.py --hook-slots): how a macOS build intercepts
guest functions without patching code (src/rollback/rb_detour.cpp, src/rollback/hook_slots.txt).

Three tiny guest functions are lifted from raw PowerPC code -- 0x10000 `li r3,5; blr`, 0x10008
`li r3,7; blr`, 0x10010 `b 0x10000` -- two of them with a slot, then compiled with a driver and run:
an empty slot runs the body, a hook in the slot takes every call (direct, the tail call, the function
table), the table's `orig` runs the body from a hook, and a lift without --hook-slots has none of it
(the Windows build's lifted code stays as it was).

Needs a ps3recomp checkout with patch 0078 (PS3RECOMP_DIR or deps/ps3recomp) and a compiler (clang-cl in
the MSVC environment on Windows, clang++ elsewhere). Skipped without them.
"""
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

from helpers import PY
from test_fp_vectors import find_ps3recomp, find_vcvars

DRIVER = r"""
#include "ppu_recomp.h"
#include <stdio.h>
#include <string.h>

extern "C" PPU_THREAD_LOCAL void (*g_trampoline_fn)(void*) = 0;
static void drain(ppu_context* ctx) { while (g_trampoline_fn) { void (*f)(void*) = g_trampoline_fn; g_trampoline_fn = 0; f(ctx); } }
static void (*g_orig)(ppu_context*) = 0;
static int g_hits = 0;
static void hook42(ppu_context* ctx) { g_hits++; ctx->gpr[3] = 42; }
static void hook_plus(ppu_context* ctx) { g_hits++; g_orig(ctx); ctx->gpr[3] += 100; }

int main()
{
    static ppu_context ctx;
    int bad = 0;
#define CHECK(c) do { if (!(c)) { printf("FAIL line %d: %s\n", __LINE__, #c); bad++; } } while (0)
    CHECK(ppu_hook_count == 2);
    CHECK(ppu_hook_table[0].addr == 0x10000 && ppu_hook_table[0].slot == 0);
    CHECK(ppu_hook_table[1].addr == 0x10010 && ppu_hook_table[1].slot == 1);
    func_00010000(&ctx); drain(&ctx); CHECK(ctx.gpr[3] == 5);
    func_00010010(&ctx); drain(&ctx); CHECK(ctx.gpr[3] == 5);
    __atomic_store_n(&ppu_hook_slots[0], hook42, __ATOMIC_RELEASE);
    func_00010000(&ctx); drain(&ctx); CHECK(ctx.gpr[3] == 42);
    func_00010010(&ctx); drain(&ctx); CHECK(ctx.gpr[3] == 42);
    for (uint64_t i = 0; i < function_table_count; i++)
        if (function_table[i].addr == 0x10000) { ctx.gpr[3] = 0; function_table[i].func(&ctx); drain(&ctx); CHECK(ctx.gpr[3] == 42); }
    g_orig = ppu_hook_table[0].orig;
    __atomic_store_n(&ppu_hook_slots[0], hook_plus, __ATOMIC_RELEASE);
    func_00010000(&ctx); drain(&ctx); CHECK(ctx.gpr[3] == 105);
    __atomic_store_n(&ppu_hook_slots[0], (void (*)(ppu_context*))0, __ATOMIC_RELEASE);
    func_00010000(&ctx); drain(&ctx); CHECK(ctx.gpr[3] == 5);
    func_00010008(&ctx); drain(&ctx); CHECK(ctx.gpr[3] == 7);
    CHECK(g_hits == 4);
    printf("%s (%d hook calls)\n", bad ? "FAILED" : "hook slots OK", g_hits);
    return bad ? 1 : 0;
}
"""


class HookSlots(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = find_ps3recomp()
        if not cls.tree:
            raise unittest.SkipTest("no ps3recomp checkout (set PS3RECOMP_DIR)")
        cls.lifter = os.path.join(cls.tree, "tools", "ppu_lifter.py")
        with open(cls.lifter, encoding="utf-8") as f:
            if "--hook-slots" not in f.read():
                raise unittest.SkipTest("this ps3recomp checkout predates patch 0078 (rebuild deps)")
        cls.vcvars = None
        if os.name == "nt":
            if not os.path.isfile(r"C:\Program Files\LLVM\bin\clang-cl.exe") and not shutil.which("clang-cl"):
                raise unittest.SkipTest("no clang-cl")
            if not os.environ.get("INCLUDE"):
                cls.vcvars = find_vcvars()
                if not cls.vcvars:
                    raise unittest.SkipTest("no MSVC environment (vcvars64.bat)")
        elif not (shutil.which("clang++") or shutil.which("c++")):
            raise unittest.SkipTest("no C++ compiler")
        cls.work = tempfile.mkdtemp(prefix="hookslots_")
        words = [0x38600005, 0x4E800020, 0x38600007, 0x4E800020, 0x4BFFFFF0, 0x60000000]
        with open(os.path.join(cls.work, "blob.bin"), "wb") as f:
            f.write(b"".join(struct.pack(">I", w) for w in words))
        with open(os.path.join(cls.work, "funcs.json"), "w") as f:
            f.write('[{"start": "0x10000", "end": "0x10008"}, {"start": "0x10008", "end": "0x10010"}, '
                    '{"start": "0x10010", "end": "0x10014"}]')
        with open(os.path.join(cls.work, "slots.txt"), "w") as f:
            f.write("# test\n10000\n00010010  # the tail call into 10000\n99999  # no function there\n")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(getattr(cls, "work", ""), ignore_errors=True)

    def lift(self, out, slots):
        cmd = [PY, self.lifter, os.path.join(self.work, "blob.bin"), "--raw", "--base", "0x10000",
               "--functions", os.path.join(self.work, "funcs.json"), "-o", os.path.join(self.work, out)]
        if slots:
            cmd += ["--hook-slots", os.path.join(self.work, "slots.txt")]
        r = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=300)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return r.stdout, os.path.join(self.work, out)

    def test_without_slots_nothing_changes(self):
        _, d = self.lift("plain", False)
        for n in os.listdir(d):
            with open(os.path.join(d, n), encoding="utf-8", errors="replace") as f:
                text = f.read()
            self.assertNotIn("ppu_hook", text, n)
            self.assertNotIn("__orig", text, n)

    def test_slots_take_every_call(self):
        log, d = self.lift("slots", True)
        self.assertIn("no lifted function starts there", log)       # 0x99999: reported, no slot
        with open(os.path.join(d, "driver.cpp"), "w") as f:
            f.write(DRIVER)
        ppu = os.path.join(self.tree, "runtime", "ppu")
        exe = os.path.join(d, "hs" + (".exe" if os.name == "nt" else ""))
        srcs = [os.path.join(d, "ppu_recomp_000.cpp"), os.path.join(d, "driver.cpp")]
        if os.name == "nt":
            cl = shutil.which("clang-cl") or r"C:\Program Files\LLVM\bin\clang-cl.exe"
            argv = [cl, "/nologo", "/O2", "/TP", "/std:c++20", "/EHsc", "/w", f"/I{d}", f"/I{ppu}", *srcs,
                    f"/Fe{exe}", f"/Fo{d}\\"]
            if self.vcvars:
                cmd = '"%s" >nul 2>&1 && %s' % (self.vcvars, subprocess.list2cmdline(argv))
                r = subprocess.run(f'cmd /s /c "{cmd}"', capture_output=True, text=True, errors="replace", timeout=600)
            else:
                r = subprocess.run(argv, capture_output=True, text=True, errors="replace", timeout=600)
        else:
            cc = shutil.which("clang++") or shutil.which("c++")
            r = subprocess.run([cc, "-O2", "-std=c++20", "-w", "-I", d, "-I", ppu, *srcs, "-o", exe],
                               capture_output=True, text=True, errors="replace", timeout=600)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = subprocess.run([exe], capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("hook slots OK (4 hook calls)", r.stdout)


if __name__ == "__main__":
    unittest.main()
