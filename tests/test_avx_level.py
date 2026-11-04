"""AVX1 software FMA and the DLL's pre-execution CPU guard (patch 0116). No game data."""
import os
import re
import shutil
import subprocess
import tempfile
import unittest

from helpers import ROOT


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


class AvxGuard(unittest.TestCase):
    def test_compiler_cleans_ymm_before_runtime_call_and_return(self):
        """Sandy/Ivy must not enter the SSE runtime with dirty upper YMM state."""
        clang = shutil.which("clang-cl") or (r"C:\Program Files\LLVM\bin\clang-cl.exe"
                                              if os.path.isfile(r"C:\Program Files\LLVM\bin\clang-cl.exe") else None)
        tree = next((p for p in (os.environ.get("PS3RECOMP_DIR"), os.path.join(ROOT, "deps", "ps3recomp"))
                     if p and os.path.isfile(os.path.join(p, "runtime", "ppu", "ppu_vmx.h"))), None)
        if os.name != "nt" or not clang or not tree:
            self.skipTest("Windows clang-cl and prepared ps3recomp tree needed")
        source = r'''
#include "ppu_vmx.h"
#if !defined(__AVX__) || defined(__AVX2__) || defined(__FMA__)
#error invalid AVX1 target
#endif
extern void external_runtime(const void*);
__declspec(noinline) void avx_leaf(void* d, const void* a, const void* b, const void* c) {
    vmx_vmaddfp(d, a, b, c, VMX_NJ);
}
__declspec(noinline) void avx_call(void* d, const void* a, const void* b, const void* c) {
    vmx_vmaddfp(d, a, b, c, VMX_NJ);
    external_runtime(d);
}
'''

        def has_cleanup(assembly, function, boundary):
            body = re.search(r"(?ms)^" + function + r":.*?^\s*\.seh_endproc", assembly).group()
            ymm = list(re.finditer(r"\bymm\d+\b", body))
            clear = list(re.finditer(r"\bvzeroupper\b", body))
            exit_op = re.search(boundary, body)
            return bool(ymm and clear and exit_op and ymm[-1].end() < clear[-1].start() < exit_op.start())

        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "probe.c")
            with open(src, "w", encoding="utf-8") as f:
                f.write(source)
            for negative_control in (False, True):
                opts = ["/clang:-mno-vzeroupper"] if negative_control else []
                r = subprocess.run([clang, "/nologo", "/O2", "/Ob2", "/W0", "/clang:-ffp-contract=off",
                                    "/clang:-mavx", "/clang:-S", "/I", os.path.join(tree, "runtime", "ppu"), src] + opts,
                                   capture_output=True, text=True, timeout=60, cwd=tmp)
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                with open(os.path.join(tmp, "probe.asm"), encoding="utf-8") as f:
                    assembly = f.read()
                self.assertEqual(has_cleanup(assembly, "avx_leaf", r"\bretq?\b"), not negative_control)
                self.assertEqual(has_cleanup(assembly, "avx_call", r"\b(?:jmp|call)\s+external_runtime\b"),
                                 not negative_control)

    def test_dll_initialization_waits_for_the_guard(self):
        builder = read("tools", "build_game_dll.py")
        self.assertIn('"/NOENTRY"', builder)
        dll = read("tools", "gamedll", "t5dr_game_dll.c")
        self.assertIn('__declspec(dllexport) void ppu_game_init(void)', dll)
        # No Windows loader callbacks execute the deferred game constructors.
        self.assertRegex(dll, r't5_tls_callback __xl_a = 0;')
        self.assertRegex(dll, r't5_tls_callback __xl_z = 0;')
        self.assertNotIn("DllMain", dll)
        patch = read("patches", "ps3recomp", "0116-avx-software-fma.patch")
        self.assertIn('strcmp(march, "avx") == 0', patch)
        self.assertIn('strcmp(t, "noavx") == 0', patch)

    def test_cpuid_and_os_state_with_mocked_hardware(self):
        clang = shutil.which("clang-cl") or (r"C:\Program Files\LLVM\bin\clang-cl.exe"
                                              if os.path.isfile(r"C:\Program Files\LLVM\bin\clang-cl.exe") else None)
        if os.name != "nt" or not clang:
            self.skipTest("Windows clang-cl CPU guard harness")
        patch = read("patches", "ps3recomp", "0116-avx-software-fma.patch")
        added = "\n".join(l[1:] for l in patch.splitlines() if l.startswith("+") and not l.startswith("+++"))
        helper = re.search(r'__attribute__\(\(target\("xsave"\)\)\) static int ppu_host_has_avx\(void\)\n\{.*?\n\}',
                           added, re.S).group()
        source = r'''
#include <stdio.h>
static unsigned g_maxleaf = 1, g_ecx;
static unsigned long long g_xcr0 = 6;
static int g_xget_reads;
static void fake_cpuid(int* r, int leaf) {
    r[0] = leaf == 0 ? (int)g_maxleaf : 0;
    r[1] = r[3] = 0; r[2] = leaf == 1 ? (int)g_ecx : 0;
}
static unsigned long long fake_xgetbv(unsigned n) { (void)n; g_xget_reads++; return g_xcr0; }
#define __cpuid(r, leaf) fake_cpuid((r), (leaf))
#define _xgetbv(n) fake_xgetbv(n)
''' + helper + r'''
int main(void) {
    const unsigned need = (1u<<0)|(1u<<9)|(1u<<19)|(1u<<20)|(1u<<23)|(1u<<26)|(1u<<27)|(1u<<28);
    g_ecx = need;
    if (!ppu_host_has_avx() || g_xget_reads != 1) return 1;
    for (int b=0; b<32; b++) if (need & (1u<<b)) {
        g_ecx = need & ~(1u<<b); g_xget_reads=0;
        if (ppu_host_has_avx() || g_xget_reads) return 2;
    }
    g_ecx=need;
    for (int state=0; state<8; state++) {
        g_xcr0=state;
        if (ppu_host_has_avx() != ((state & 6) == 6)) return 3;
    }
    g_maxleaf=0; g_xget_reads=0;
    if (ppu_host_has_avx() || g_xget_reads) return 4;
    puts("AVX guard: feature omissions, XGETBV gating and all XMM/YMM OS states PASS");
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            src, exe = os.path.join(tmp, "guard.c"), os.path.join(tmp, "guard.exe")
            with open(src, "w", encoding="utf-8") as f:
                f.write(source)
            r = subprocess.run([clang, "/nologo", "/O2", src, "/Fe:" + exe, "/Fo:" + os.path.join(tmp, "guard.obj")],
                               capture_output=True, text=True, timeout=60, cwd=tmp)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            r = subprocess.run([exe], capture_output=True, text=True, timeout=10)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
