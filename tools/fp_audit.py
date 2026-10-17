#!/usr/bin/env python3
"""Static check of t5dr_game.dll (or any PE) for code whose floating-point result
can differ between two x64 PCs (docs/NETPLAY.md, "Same game state on every CPU").

    python tools/fp_audit.py build/cmake/t5dr_game.dll [more.dll ...] [--llvm DIR] [--strict]

Reports, per file:
  - estimate instructions: rcpps/rcpss/rsqrtps/rsqrtss (Intel and AMD return different
    bits) and the AVX-512 rcp14/rsqrt14/rcp28/rsqrt28 forms, plus the dot products
    dpps/dppd (internal rounding is the CPU's business) -- must be 0;
  - x87 instructions (80-bit intermediates, control word per thread) -- must be 0;
  - MXCSR writes (ldmxcsr) in the game code -- must be 0 (the runtime owns MXCSR);
  - the C runtime math functions it imports from ucrtbase.dll. ucrtbase picks its
    code path by CPU (fma/fmaf: vfmadd or a software routine; sin/exp/pow...: an
    FMA3 or an SSE2 implementation, which disagree in the last bit) and its version
    comes with Windows, so game code must not depend on them. Allowed: none of the
    math functions (the lifted code uses runtime/ppu/ppu_fp_det.h instead).
--strict exits 1 when anything above is found (the regression tool uses it).
"""
import argparse
import collections
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

ESTIMATE = re.compile(r"^v?(rcp|rsqrt)(ps|ss|14ps|14ss|14pd|14sd|28ps|28ss|28pd|28sd)\b|^v?dpp[sd]$")
X87 = re.compile(r"^f(ld|st|ist|ild|add|sub|mul|div|xch|chs|abs|sqrt|sin|cos|sincos|ptan|patan|2xm1|yl2x|yl2xp1|scale|"
                 r"rndint|nstcw|ldcw|comi|ucomi|com|ucom|bld|bstp|init|ninit|nsave|rstor|xam|tst|prem|prem1|xtract|"
                 r"cmov|free|incstp|decstp|nop|wait|nstenv|ldenv|nstsw)\w*$")
MXCSR = re.compile(r"^v?ldmxcsr$")
# ucrtbase functions whose result is a floating-point value computed by the CRT
CRT_MATH = {"sqrt", "sqrtf", "floor", "floorf", "ceil", "ceilf", "trunc", "truncf", "round", "roundf", "rint", "rintf",
            "nearbyint", "nearbyintf", "fma", "fmaf", "fmod", "fmodf", "fmin", "fminf", "fmax", "fmaxf", "copysign",
            "copysignf", "ldexp", "ldexpf", "frexp", "frexpf", "modf", "modff", "lrint", "lrintf", "llrint", "llrintf",
            "lround", "lroundf", "exp", "expf", "exp2", "exp2f", "log", "logf", "log2", "log2f", "log10", "log10f",
            "pow", "powf", "sin", "sinf", "cos", "cosf", "tan", "tanf", "asin", "asinf", "acos", "acosf", "atan",
            "atanf", "atan2", "atan2f", "sinh", "sinhf", "cosh", "coshf", "tanh", "tanhf", "cbrt", "cbrtf",
            "remainder", "remainderf", "hypot", "hypotf", "_set_FMA3_enable"}


def find_tool(llvm, name):
    for d in ([llvm] if llvm else []) + [os.path.join(ROOT, "toolchain", "llvm", "bin"),
                                         os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "LLVM", "bin")]:
        p = os.path.join(d, name + ".exe")
        if os.path.exists(p):
            return p
    sys.exit(f"{name}.exe not found (--llvm DIR)")


def imports(readobj, path):
    out = subprocess.run([readobj, "--coff-imports", path], capture_output=True, text=True).stdout
    res, lib = collections.defaultdict(list), None
    for line in out.splitlines():
        m = re.search(r"Name: (\S+)", line)
        if m and line.strip().startswith("Name:"):
            lib = m.group(1).lower()
        m = re.search(r"Symbol: (\S+)", line)
        if m and lib:
            res[lib].append(m.group(1))
    return res


def scan(objdump, path):
    """Mnemonic counts of the interesting instructions in the executable sections."""
    p = subprocess.Popen([objdump, "-d", "--no-show-raw-insn", "--no-leading-addr", path],
                         stdout=subprocess.PIPE, text=True, errors="replace", bufsize=1 << 20)
    hits = collections.Counter()
    total = 0
    for line in p.stdout:
        if not line.startswith("\t") and not line.startswith(" "):
            continue
        parts = line.split()
        if not parts:
            continue
        mn = parts[0]
        if mn in ("rep", "lock", "notrack", "data16") and len(parts) > 1:
            mn = parts[1]
        total += 1
        if ESTIMATE.match(mn) or X87.match(mn) or MXCSR.match(mn):
            hits[mn] += 1
    p.wait()
    return total, hits


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+")
    ap.add_argument("--llvm", help="folder with llvm-objdump.exe / llvm-readobj.exe")
    ap.add_argument("--strict", action="store_true", help="exit 1 on any finding")
    a = ap.parse_args()
    objdump, readobj = find_tool(a.llvm, "llvm-objdump"), find_tool(a.llvm, "llvm-readobj")
    bad = 0
    for f in a.files:
        imp = imports(readobj, f)
        math = sorted(set(s for lib, syms in imp.items() if lib == "ucrtbase.dll" or lib.startswith("api-ms-win-crt-math")
                          for s in syms if s in CRT_MATH))
        total, hits = scan(objdump, f)
        est = {k: v for k, v in hits.items() if ESTIMATE.match(k)}
        x87 = {k: v for k, v in hits.items() if X87.match(k)}
        mx = {k: v for k, v in hits.items() if MXCSR.match(k)}
        print(f"{f}: {total} instructions")
        print(f"  estimate instructions (rcp/rsqrt/dpps): {sum(est.values())} {dict(est) if est else ''}")
        print(f"  x87 instructions: {sum(x87.values())} {dict(x87) if x87 else ''}")
        print(f"  MXCSR writes: {sum(mx.values())}")
        print(f"  C runtime math imported (ucrtbase.dll / api-ms-win-crt-math): {', '.join(math) if math else 'none'}")
        bad += bool(est) + bool(x87) + bool(mx) + bool(math)
    if a.strict and bad:
        print("FAIL: floating-point code that can differ between PCs (see above)")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
