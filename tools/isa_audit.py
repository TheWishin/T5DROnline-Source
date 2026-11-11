#!/usr/bin/env python3
"""Which x86 instruction-set extensions a built program really contains.

    python tools/isa_audit.py FILE.exe|FILE.dll [--map FILE.map | --pdb FILE.pdb] [--objdump llvm-objdump.exe]
                              [--top N] [--json OUT] [--fail-on LEVEL,...]

Disassembles the code sections with llvm-objdump and counts every instruction that is not in the x86-64 baseline
(SSE2): SSE3, SSSE3, SSE4.1, SSE4.2, POPCNT, LZCNT, BMI1/2, MOVBE, AVX/AVX2/FMA (any VEX-coded instruction), AES,
PCLMUL. With a linker map (/MAP) each one is attributed to its function and object file, so the list says whether the
hits are the Microsoft C library's own CPUID-dispatched routines (memcpy, strlen, __std_* vector algorithms: never
run on a processor without the feature) or code of ours that an old processor would reach.

A compile flag only says what the compiler may use; this says what it did use. It is how the SSE2 baseline build
(CMake T5DR_X86_BASELINE, docs/SSE2_BASELINE.md) is checked on a PC whose processor has everything.
Jump tables and other data inside code sections decode as random instructions: a hit in a function that has no
other such instruction and sits in a table is that; the per-function counts make them easy to see.

Exit status 0. --fail-on LEVEL[,LEVEL] exits 1 when an instruction of that level is attributed to a function that
is not on the dispatch list (DISPATCHED below).
"""
import argparse
import bisect
import collections
import json
import os
import re
import shutil
import subprocess
import sys

SSE3 = {"addsubpd", "addsubps", "haddpd", "haddps", "hsubpd", "hsubps", "movddup", "movshdup", "movsldup", "lddqu",
        "fisttpl", "fisttps", "fisttpll", "fisttp"}
SSSE3 = {"pshufb", "palignr", "pabsb", "pabsw", "pabsd", "phaddw", "phaddd", "phaddsw", "phsubw", "phsubd", "phsubsw",
         "pmaddubsw", "pmulhrsw", "psignb", "psignw", "psignd"}
SSE41 = {"blendpd", "blendps", "blendvpd", "blendvps", "pblendvb", "pblendw", "dppd", "dpps", "extractps", "insertps",
         "pinsrb", "pinsrd", "pinsrq", "pextrb", "pextrd", "pextrq", "pmovsxbw", "pmovsxbd", "pmovsxbq", "pmovsxwd",
         "pmovsxwq", "pmovsxdq", "pmovzxbw", "pmovzxbd", "pmovzxbq", "pmovzxwd", "pmovzxwq", "pmovzxdq", "pmulld",
         "pmuldq", "pminsb", "pminsd", "pminuw", "pminud", "pmaxsb", "pmaxsd", "pmaxuw", "pmaxud", "ptest", "roundpd",
         "roundps", "roundsd", "roundss", "packusdw", "pcmpeqq", "phminposuw", "mpsadbw", "movntdqa"}
SSE42 = {"pcmpgtq", "crc32b", "crc32w", "crc32l", "crc32q", "crc32", "pcmpestri", "pcmpestrm", "pcmpistri", "pcmpistrm"}
POPCNT = {"popcntl", "popcntq", "popcntw", "popcnt"}
LZCNT = {"lzcntl", "lzcntq", "lzcntw", "lzcnt"}
BMI = {"andnl", "andnq", "bextrl", "bextrq", "blsil", "blsiq", "blsrl", "blsrq", "blsmskl", "blsmskq", "pdepl", "pdepq",
       "pextl", "pextq", "bzhil", "bzhiq", "mulxl", "mulxq", "rorxl", "rorxq", "sarxl", "sarxq", "shlxl", "shlxq",
       "shrxl", "shrxq"}
# tzcnt is "rep bsf": a processor without BMI1 runs it as bsf (the same result for a nonzero operand, which is where
# compilers use this encoding in baseline code). Counted on its own line, not as a requirement.
TZCNT = {"tzcntl", "tzcntq", "tzcntw", "tzcnt"}
MOVBE = {"movbel", "movbeq", "movbew", "movbe"}
AES = {"aesenc", "aesenclast", "aesdec", "aesdeclast", "aesimc", "aeskeygenassist", "pclmulqdq"}
NOT_VEX = {"verr", "verw", "vmcall", "vmlaunch", "vmresume", "vmxoff", "vmxon", "vmclear", "vmptrld", "vmptrst",
           "vmread", "vmwrite", "vmfunc", "vmrun", "vmload", "vmsave", "vmmcall"}
LEVELS = ["sse3", "ssse3", "sse4.1", "sse4.2", "popcnt", "lzcnt", "bmi", "movbe", "avx", "aes", "tzcnt"]
# Ours, and checked by CPUID before every use: the hardware fma of ppu_fp_det.h (ppu_fp_cpu_fma picks it or the
# software fma, patch 0032).
GUARDED = {"ppu_fma_hw"}
CLIB = re.compile(r"^(msvcprt|libcpmt|libcmt|msvcrt|libucrt|ucrt|libvcruntime|vcruntime|libconcrt)\w*:", re.I)

# The Microsoft C/C++ library picks these by CPUID at run time (__isa_available, __favor): their SSE4/AVX bodies
# never run on a processor without the feature. So do the STL's vector algorithms (__std_* in msvcprt/libcpmt).
DISPATCHED = re.compile(
    r"^(mem(cpy|move|set|chr|cmp|ccpy)|str(len|chr|rchr|nlen|cmp|ncmp|str|spn|cspn|pbrk|cat|cpy|ncpy|ncat)|wcs\w+|wmem\w+|"
    r"__std_\w+|_?_?(l?l?round|ceil|floor|trunc|rint|nearbyint|fma|sqrt|log\w*|exp\w*|pow|sin|cos|tan|a(sin|cos|tan)\w*|"
    r"fmod|remainder|hypot|cbrt|erf\w*|[lt]gamma)[fl]?|__libm_\w+|_?_?(sse2|avx|fma3|sse4)\w*|__crt_\w+|"
    r"__memcpy_\w+|__memset_\w+|__isa_\w+|_guard_\w+|__acrt_\w+|_log\w*|_exp\w*|_pow\w*|_sin\w*|_cos\w*|_tan\w*|"
    r".*_(fma3?|avx2?|sse4|sse41|sse42)(_\w+)?|__remainder\w*|__vdecl_\w+|__svml_\w+|__memchr\w*|__strncnt|__wcsncnt)$")


def level_of(mn):
    if mn in SSE41:
        return "sse4.1"
    if mn in SSSE3:
        return "ssse3"
    if mn in SSE3:
        return "sse3"
    if mn in SSE42:
        return "sse4.2"
    if mn in POPCNT:
        return "popcnt"
    if mn in LZCNT:
        return "lzcnt"
    if mn in BMI:
        return "bmi"
    if mn in TZCNT:
        return "tzcnt"
    if mn in MOVBE:
        return "movbe"
    if mn in AES:
        return "aes"
    if mn.startswith("v") and mn not in NOT_VEX and len(mn) > 3:
        return "avx"
    return None


def read_map(path):
    """[(address, name, object)] sorted, from an MSVC/lld /MAP file."""
    syms = []
    rx = re.compile(r"^\s*[0-9a-fA-F]{4}:[0-9a-fA-F]{8}\s+(\S+)\s+([0-9a-fA-F]{16})\s+(?:f\s+)?(?:i\s+)?(\S+)?")
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            m = rx.match(line)
            if m:
                syms.append((int(m.group(2), 16), m.group(1), m.group(3) or ""))
    syms.sort()
    return syms


def read_pdb(pdb, image, objdump):
    """[(address, name, "")] from a PDB's public symbols (llvm-pdbutil next to llvm-objdump) -- for a program linked
    without /MAP. Section starts come from the image's section table."""
    base = []
    out = subprocess.run([objdump, "-h", image], capture_output=True, text=True, errors="replace").stdout
    for line in out.splitlines():
        m = re.match(r"^\s*\d+\s+\S+\s+[0-9a-f]+\s+([0-9a-f]+)\s", line)
        if m:
            base.append(int(m.group(1), 16))
    util = os.path.join(os.path.dirname(objdump), "llvm-pdbutil" + (".exe" if os.name == "nt" else ""))
    p = subprocess.Popen([util, "dump", "--publics", pdb], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                         errors="replace")
    syms, name = [], None
    for line in p.stdout:
        m = re.search(r"S_PUB32 \[size = \d+\] `(.*)`", line)
        if m:
            name = m.group(1)
            continue
        m = re.search(r"addr = (\d+):(\d+)", line)
        if m and name is not None:
            sec = int(m.group(1))
            if 1 <= sec <= len(base):
                syms.append((base[sec - 1] + int(m.group(2)), name, ""))
            name = None
    p.wait()
    syms.sort()
    return syms


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file")
    ap.add_argument("--map", default="")
    ap.add_argument("--pdb", default="", help="instead of --map: the program's PDB (public symbols)")
    ap.add_argument("--objdump", default=shutil.which("llvm-objdump") or r"C:\Program Files\LLVM\bin\llvm-objdump.exe")
    ap.add_argument("--top", type=int, default=12)
    ap.add_argument("--json", default="")
    ap.add_argument("--fail-on", default="")
    ap.add_argument("--list", default="", help="LEVEL[,LEVEL]: print every function with such an instruction")
    a = ap.parse_args()
    syms = read_map(a.map) if a.map else read_pdb(a.pdb, a.file, a.objdump) if a.pdb else []
    addrs = [s[0] for s in syms]
    counts = collections.Counter()
    mnem = collections.defaultdict(collections.Counter)
    funcs = collections.defaultdict(collections.Counter)     # level -> (function, object) -> n
    total = 0
    p = subprocess.Popen([a.objdump, "-d", "--no-show-raw-insn", "--no-print-imm-hex", a.file], stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, text=True, errors="replace", bufsize=1 << 20)
    rx = re.compile(r"^\s*([0-9a-f]+):\s+(?:(?:lock|rep|repe|repne|data16|notrack)\s+)*([a-z][a-z0-9]*)")
    for line in p.stdout:
        m = rx.match(line)
        if not m:
            continue
        total += 1
        lv = level_of(m.group(2))
        if not lv:
            continue
        counts[lv] += 1
        mnem[lv][m.group(2)] += 1
        if syms:
            i = bisect.bisect_right(addrs, int(m.group(1), 16)) - 1
            funcs[lv][(syms[i][1], syms[i][2]) if i >= 0 else ("?", "")] += 1
    p.wait()
    print(f"{os.path.basename(a.file)}: {total:,} instructions decoded")
    out = dict(file=a.file, instructions=total, levels={})
    bad = 0
    want = {x for x in a.fail_on.split(",") if x}
    for lv in LEVELS:
        if not counts[lv]:
            print(f"  {lv:7s} 0")
            out["levels"][lv] = dict(count=0)
            continue
        ours = [(k, n) for k, n in funcs[lv].items() if k[0] not in GUARDED and
                not DISPATCHED.match(k[0].lstrip("_?").split("@")[0]) and
                not DISPATCHED.match(k[0]) and not ((CLIB.match(k[1]) or not k[1]) and "__std_" in k[0]) and
                # a program linked with the static C runtime (/MT, the release's prebuilt runtime) carries the C
                # library's own objects, whose local labels (YmmLoop, Lcos_piby4_compute, ...) are not on the
                # dispatch list: anything from a C library object is the library's own CPUID dispatch, as
                # tools/check_binaries.py isa_findings counts it for the normal runtime
                not (k[1] and CLIB.match(k[1]) and not os.environ.get("ISA_AUDIT_STRICT_CLIB"))]
        n_ours = sum(n for _, n in ours)
        note = f" in {len(funcs[lv])} functions; {n_ours:,} of them in {len(ours)} functions outside the C library's dispatch" if syms else ""
        print(f"  {lv:7s} {counts[lv]:,}{note}")
        print("          " + ", ".join(f"{k} {n}" for k, n in mnem[lv].most_common(8)))
        for (fn, obj), n in sorted(ours, key=lambda x: -x[1])[:a.top]:
            print(f"          {n:6d}  {fn[:70]}  [{obj}]")
        out["levels"][lv] = dict(count=counts[lv], mnemonics=dict(mnem[lv]), functions=len(funcs[lv]), outside_dispatch=n_ours,
                                 top=[dict(function=k[0], object=k[1], n=n) for k, n in sorted(ours, key=lambda x: -x[1])[:50]])
        if lv in a.list.split(","):
            for (fn, obj), n in sorted(funcs[lv].items(), key=lambda x: -x[1]):
                print(f"          all: {n:6d}  {fn[:90]}  [{obj}]")
        if lv in want and lv != "tzcnt" and (n_ours or not syms):
            bad += 1
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=1)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
