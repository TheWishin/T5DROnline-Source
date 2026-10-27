#!/usr/bin/env python3
"""Same floating-point bits on every host: the lifted code's FP instructions
run over fixed test vectors, one digest per instruction.

    python tools/fp_vectors.py [--ps3recomp DIR] [--compare FILE] [--write FILE]
                               [--cc COMPILER] [--march TARGET] [--n N]
                               [--dump MNEMONIC --count K]

The C it runs is not written by hand: for each PPU scalar FP and VMX float
instruction it asks ppu_lifter.py to lift one real instruction word (the
statement a game's lifted code contains, helpers from the lifter's
SOURCE_PREAMBLE, runtime/ppu/ppu_fp_det.h and ppu_vmx.h included), wraps it
in a function, and runs it over ~100,000 operand sets per instruction: special
values (zeros, infinities, NaNs with payloads, signalling NaNs, denormals, the
int32/int64 conversion edges, the float range edges), random bit patterns and
ordinary numbers. The outputs (result register, CR, FPSCR, VSCR) are hashed
(FNV-1a 64) per instruction.

Two hosts that print the same digests compute the same guest FP state
(docs/MACOS.md, "Determinism across operating systems and CPUs";
docs/NETPLAY.md, "Same game state on every CPU"). The reference file
tests/data/fp_vectors_x64.txt comes from x86-64 Windows, where the baseline
and the x86-64-v3 builds agree (tests/test_fp_vectors.py). On a Mac:

    python3 tools/fp_vectors.py --ps3recomp deps/ps3recomp --compare tests/data/fp_vectors_x64.txt

exit 0 = every instruction matches x86-64; 1 = a list of those that do not,
each worth a `--dump <mnemonic> --count 20` on both machines and a diff.

Windows: run it inside the MSVC environment (vcvars64), it compiles with
clang-cl. Elsewhere: clang (Apple's or LLVM's).
"""
import argparse
import hashlib
import os
import platform
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
N_DEFAULT = 100000
SEED = 0x7E5D_2026_0C19_0001

# mnemonic, form, instruction word. Registers: result f1/v1, sources f2 f3 f4 / v2 v3 v4.
def _a(op, xo, t=1, a=2, b=3, c=4, rc=0):
    return (op << 26) | (t << 21) | (a << 16) | (b << 11) | (c << 6) | (xo << 1) | rc


def _x(op, xo, t=1, a=0, b=3, rc=0):
    return (op << 26) | (t << 21) | (a << 16) | (b << 11) | (xo << 1) | rc


def _va(xo):
    return (4 << 26) | (1 << 21) | (2 << 16) | (3 << 11) | (4 << 6) | xo


def _vx(xo, a=2):
    return (4 << 26) | (1 << 21) | (a << 16) | (3 << 11) | xo


def _vc(xo, rc=0):
    return (4 << 26) | (1 << 21) | (2 << 16) | (3 << 11) | (rc << 10) | xo


INSNS = [
    # scalar, double
    ("fadd", "f", _a(63, 21, c=0)), ("fsub", "f", _a(63, 20, c=0)), ("fmul", "f", _a(63, 25, b=0)),
    ("fdiv", "f", _a(63, 18, c=0)), ("fsqrt", "f", _a(63, 22, a=0, c=0)), ("fsel", "f", _a(63, 23)),
    ("fre", "f", _a(63, 24, a=0, c=0)), ("frsqrte", "f", _a(63, 26, a=0, c=0)),
    ("fmadd", "f", _a(63, 29)), ("fmsub", "f", _a(63, 28)), ("fnmadd", "f", _a(63, 31)), ("fnmsub", "f", _a(63, 30)),
    # scalar, single
    ("fadds", "f", _a(59, 21, c=0)), ("fsubs", "f", _a(59, 20, c=0)), ("fmuls", "f", _a(59, 25, b=0)),
    ("fdivs", "f", _a(59, 18, c=0)), ("fsqrts", "f", _a(59, 22, a=0, c=0)), ("fres", "f", _a(59, 24, a=0, c=0)),
    ("fmadds", "f", _a(59, 29)), ("fmsubs", "f", _a(59, 28)), ("fnmadds", "f", _a(59, 31)), ("fnmsubs", "f", _a(59, 30)),
    # conversions, moves, compare
    ("frsp", "f", _x(63, 12)), ("fctiw", "f", _x(63, 14)), ("fctiwz", "f", _x(63, 15)),
    ("fctid", "f", _x(63, 814)), ("fctidz", "f", _x(63, 815)), ("fcfid", "f", _x(63, 846)),
    ("fneg", "f", _x(63, 40)), ("fabs", "f", _x(63, 264)), ("fnabs", "f", _x(63, 136)), ("fmr", "f", _x(63, 72)),
    ("fcmpu", "f", (63 << 26) | (1 << 23) | (2 << 16) | (3 << 11)),
    # VMX float
    ("vaddfp", "v", _vx(10)), ("vsubfp", "v", _vx(74)), ("vmaddfp", "v", _va(46)), ("vnmsubfp", "v", _va(47)),
    ("vmaxfp", "v", _vx(1034)), ("vminfp", "v", _vx(1098)),
    ("vrefp", "v", _vx(266, 0)), ("vrsqrtefp", "v", _vx(330, 0)), ("vexptefp", "v", _vx(394, 0)),
    ("vlogefp", "v", _vx(458, 0)),
    ("vrfin", "v", _vx(522, 0)), ("vrfiz", "v", _vx(586, 0)), ("vrfip", "v", _vx(650, 0)), ("vrfim", "v", _vx(714, 0)),
    ("vcfux", "v", _vx(778, 3)), ("vcfsx", "v", _vx(842, 3)), ("vctuxs", "v", _vx(906, 3)), ("vctsxs", "v", _vx(970, 3)),
    ("vcmpeqfp.", "v", _vc(198, 1)), ("vcmpgefp.", "v", _vc(454, 1)), ("vcmpgtfp.", "v", _vc(710, 1)),
    ("vcmpbfp.", "v", _vc(966, 1)),
]

DRIVER = r"""
/* ---- test driver (tools/fp_vectors.py) ---- */
#include <stdio.h>
#include <stdlib.h>

uint8_t* vm_base;   /* the preamble's memory helpers are never called here */

static uint64_t s_rng;
static uint64_t rnd(void) { s_rng ^= s_rng << 13; s_rng ^= s_rng >> 7; s_rng ^= s_rng << 17; return s_rng; }

static const uint64_t kSpecD[] = {
    0x0000000000000000ull, 0x8000000000000000ull, 0x3FF0000000000000ull, 0xBFF0000000000000ull,
    0x7FF0000000000000ull, 0xFFF0000000000000ull, 0x7FF8000000000000ull, 0xFFF8000000000000ull,
    0x7FF8000000000123ull, 0xFFFC00000000BEEFull, 0x7FF0000000000001ull, 0xFFF4000000000000ull,
    0x0000000000000001ull, 0x000FFFFFFFFFFFFFull, 0x8000000000000001ull, 0x0010000000000000ull,
    0x7FEFFFFFFFFFFFFFull, 0xFFEFFFFFFFFFFFFFull, 0x41DFFFFFFFC00000ull, 0x41DFFFFFFFE00000ull,
    0x41E0000000000000ull, 0xC1E0000000000000ull, 0xC1E0000000200000ull, 0x43E0000000000000ull,
    0xC3E0000000000000ull, 0x43DFFFFFFFFFFFFFull, 0x3FE0000000000000ull, 0x3FF8000000000000ull,
    0x4004000000000000ull, 0xBFE0000000000000ull, 0xC004000000000000ull, 0x47EFFFFFE0000000ull,
    0x47EFFFFFF0000000ull, 0x3810000000000000ull, 0x36A0000000000000ull, 0x3690000000000000ull,
    0x380FFFFFC0000000ull, 0x3FEFFFFFFFFFFFFFull, 0x4330000000000000ull, 0x4330000000000001ull,
};
static const uint32_t kSpecF[] = {
    0x00000000u, 0x80000000u, 0x3F800000u, 0xBF800000u, 0x7F800000u, 0xFF800000u, 0x7FC00000u,
    0xFFC00000u, 0x7FC00123u, 0x7F800001u, 0xFFA00000u, 0x00000001u, 0x007FFFFFu, 0x80000001u,
    0x00800000u, 0x7F7FFFFFu, 0xFF7FFFFFu, 0x4EFFFFFFu, 0x4F000000u, 0xCF000000u, 0x4F800000u,
    0x3F000000u, 0x3FC00000u, 0x40200000u, 0xBF000000u, 0x4B000000u, 0x4B7FFFFFu, 0xCB000001u,
};
#define NSPEC_D (sizeof kSpecD / sizeof kSpecD[0])
#define NSPEC_F (sizeof kSpecF / sizeof kSpecF[0])

static double operand_d(void)
{
    const uint64_t r = rnd(), k = r & 7;
    uint64_t u;
    if (k < 2) u = kSpecD[(r >> 8) % NSPEC_D];
    else if (k < 4) u = rnd();                                         /* any bits */
    else if (k < 5) u = rnd() & 0xFFFFFFFFE0000000ull;                 /* single-exact mantissa */
    else {                                                             /* ordinary magnitudes */
        const uint64_t e = 1023 + ((r >> 8) % 81) - 40;
        u = ((r >> 3) & 1ull) << 63 | e << 52 | (rnd() & 0x000FFFFFFFFFFFFFull);
    }
    double d; memcpy(&d, &u, 8); return d;
}
static uint32_t operand_f(void)
{
    const uint64_t r = rnd(), k = r & 7;
    if (k < 2) return kSpecF[(r >> 8) % NSPEC_F];
    if (k < 4) return (uint32_t)rnd();
    const uint32_t e = 127 + (uint32_t)((r >> 8) % 61) - 30;
    return (uint32_t)((r >> 3) & 1u) << 31 | e << 23 | ((uint32_t)rnd() & 0x007FFFFFu);
}

static uint64_t s_h;
static void mix(uint64_t v) { for (int i = 0; i < 8; i++) { s_h ^= (v >> (8 * i)) & 0xFF; s_h *= 0x100000001B3ull; } }

typedef void (*op_fn)(ppu_context*);
typedef struct { const char* name; char kind; op_fn fn; } op_t;
/*@OPS@*/

static void run_op(const op_t* op, long n, long dump)
{
    static ppu_context ctx;
    s_rng = SEED_VALUE ^ (uint64_t)(op->name[0] * 131 + op->name[1] * 7 + op->name[2]);
    for (const char* p = op->name; *p; p++) s_rng = (s_rng ^ (uint8_t)*p) * 0x100000001B3ull | 1;
    s_h = 0xCBF29CE484222325ull;
    for (long i = 0; i < n; i++) {
        memset(&ctx, 0, sizeof ctx);
        if (op->kind == 'f') {
            ctx.fpr[1] = operand_d(); ctx.fpr[2] = operand_d(); ctx.fpr[3] = operand_d(); ctx.fpr[4] = operand_d();
            const double in2 = ctx.fpr[2], in3 = ctx.fpr[3], in4 = ctx.fpr[4];
            op->fn(&ctx);
            uint64_t r; memcpy(&r, &ctx.fpr[1], 8);
            mix(r); mix(ctx.cr); mix(ctx.fpscr);
            if (i < dump) {
                uint64_t a, b, c; memcpy(&a, &in2, 8); memcpy(&b, &in3, 8); memcpy(&c, &in4, 8);
                printf("%s %ld f2=%016llX f3=%016llX f4=%016llX -> f1=%016llX cr=%08X fpscr=%08X\n", op->name, i,
                       (unsigned long long)a, (unsigned long long)b, (unsigned long long)c, (unsigned long long)r,
                       (unsigned)ctx.cr, (unsigned)ctx.fpscr);
            }
        } else {
            for (int v = 1; v <= 4; v++) for (int l = 0; l < 4; l++) ctx.vr[v].w[l] = operand_f();
            ctx.vscr = (rnd() & 1) ? 0x00010000u : 0;                   /* NJ (the PS3 default) or IEEE */
            const ppu_vr a = ctx.vr[2], b = ctx.vr[3], c = ctx.vr[4];
            const uint32_t vscr_in = ctx.vscr;
            op->fn(&ctx);
            for (int l = 0; l < 4; l++) mix(ctx.vr[1].w[l]);
            mix(ctx.cr); mix(ctx.vscr);
            if (i < dump) {
                printf("%s %ld vscr=%08X", op->name, i, (unsigned)vscr_in);
                for (int l = 0; l < 4; l++) printf(" [%08X %08X %08X]", (unsigned)a.w[l], (unsigned)b.w[l], (unsigned)c.w[l]);
                printf(" -> v1=%08X %08X %08X %08X cr=%08X vscr=%08X\n", (unsigned)ctx.vr[1].w[0], (unsigned)ctx.vr[1].w[1],
                       (unsigned)ctx.vr[1].w[2], (unsigned)ctx.vr[1].w[3], (unsigned)ctx.cr, (unsigned)ctx.vscr);
            }
        }
    }
    if (dump <= 0) printf("%-10s %016llX\n", op->name, (unsigned long long)s_h);
}

int main(int argc, char** argv)
{
    long n = argc > 1 ? atol(argv[1]) : 0;
    const char* only = argc > 2 ? argv[2] : "";
    long dump = argc > 3 ? atol(argv[3]) : 0;
    if (n <= 0) n = 1;
    for (size_t i = 0; i < sizeof kOps / sizeof kOps[0]; i++) {
        if (*only && strcmp(only, kOps[i].name)) continue;
        run_op(&kOps[i], n, dump);
    }
    return 0;
}
"""


def find_ps3recomp(arg):
    for c in ([arg] if arg else []) + [os.path.join(ROOT, "deps", "ps3recomp")]:
        if c and os.path.exists(os.path.join(c, "tools", "ppu_lifter.py")) and \
                os.path.exists(os.path.join(c, "runtime", "ppu", "ppu_fp_det.h")):
            return os.path.abspath(c)
    return None


def generate(ps3recomp, out_dir):
    """Write ppu_recomp.h and fp_vectors.cpp into out_dir; return the .cpp path."""
    sys.path.insert(0, os.path.join(ps3recomp, "tools"))
    import ppu_disasm   # noqa: E402  (ps3recomp's own tools)
    import ppu_lifter   # noqa: E402
    lifter = ppu_lifter.PPULifter()
    func = ppu_lifter.LiftedFunction(name="fpv", start_addr=0x10000, end_addr=0x10004)
    bodies = []
    for mnem, kind, word in INSNS:
        insn = ppu_disasm.decode(word, 0x10000)
        if insn.mnemonic != mnem:
            raise SystemExit(f"fp_vectors: {word:08X} decodes as {insn.mnemonic}, expected {mnem}")
        stmt = lifter._translate(insn, func)   # the statement a lifted game contains
        if not stmt or stmt.startswith("/*"):
            raise SystemExit(f"fp_vectors: the lifter has no translation for {mnem}: {stmt!r}")
        bodies.append((mnem, kind, stmt))
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "ppu_recomp.h"), "w", encoding="utf-8", newline="\n") as f:
        f.write(ppu_lifter.HEADER_PREAMBLE)
    src = [ppu_lifter.SOURCE_PREAMBLE, f"#define SEED_VALUE 0x{SEED:016X}ull\n"]
    for i, (mnem, kind, stmt) in enumerate(bodies):
        src.append(f"static void op_{i}(ppu_context* ctx) {{ /* {mnem} */\n    {stmt}\n}}\n")
    rows = "".join(f'    {{ "{m}", \'{k}\', op_{i} }},\n' for i, (m, k, _) in enumerate(bodies))
    src.append(DRIVER.replace("/*@OPS@*/", "static const op_t kOps[] = {\n" + rows + "};\n"))
    path = os.path.join(out_dir, "fp_vectors.cpp")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(src))
    return path


def default_cc():
    if os.name == "nt":
        return shutil.which("clang-cl") or r"C:\Program Files\LLVM\bin\clang-cl.exe"
    return shutil.which("clang++") or shutil.which("c++") or "clang++"


def build(cc, src, out_dir, ps3recomp, march, tag):
    exe = os.path.join(out_dir, f"fp_vectors_{tag}" + (".exe" if os.name == "nt" else ""))
    inc = [out_dir, os.path.join(ps3recomp, "runtime", "ppu")]
    if os.path.basename(cc).lower().startswith("clang-cl"):
        cmd = [cc, "/nologo", "/O2", "/TP", "/std:c++20", "/EHsc", "/w", "/clang:-ffp-contract=off"]
        if march:
            cmd.append(f"/clang:-march={march}")
        cmd += [f"/I{d}" for d in inc] + [src, f"/Fe{exe}", f"/Fo{os.path.join(out_dir, tag + '.obj')}"]
    else:
        cmd = [cc, "-O2", "-std=c++20", "-w", "-ffp-contract=off"]
        if march:
            cmd.append(f"-march={march}")
        cmd += [f"-I{d}" for d in inc] + [src, "-o", exe]
    r = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    if r.returncode != 0:
        raise SystemExit(f"fp_vectors: compile failed ({' '.join(cmd)}):\n{r.stdout}{r.stderr}")
    return exe


def run(exe, n, only="", dump=0, soft_fma=False):
    env = dict(os.environ)
    if soft_fma:
        env["PS3_FP_SOFT_FMA"] = "1"   # ppu_fp_det.h: the software fma a CPU without FMA3 runs
    r = subprocess.run([exe, str(n), only, str(dump)], capture_output=True, text=True, timeout=600, env=env)
    if r.returncode != 0:
        raise SystemExit(f"fp_vectors: {exe} failed ({r.returncode}): {r.stderr}")
    return r.stdout


def parse(text):
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        k, v = line.split()
        out[k] = v
    return out


def host_name():
    m = platform.machine().lower()
    arch = "arm64" if m in ("arm64", "aarch64") else "x64" if m in ("amd64", "x86_64") else m
    return f"{platform.system().lower()}-{arch}"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ps3recomp", help="ps3recomp checkout (default: deps/ps3recomp)")
    ap.add_argument("--cc", default=default_cc(), help="clang-cl on Windows, clang++ elsewhere")
    ap.add_argument("--march", default="", help="target CPU for the build (e.g. x86-64-v3); default: the compiler's")
    ap.add_argument("--n", type=int, default=N_DEFAULT, help=f"operand sets per instruction (default {N_DEFAULT})")
    ap.add_argument("--out", default=os.path.join(ROOT, "build", "fp_vectors"), help="work directory")
    ap.add_argument("--compare", help="reference digests (tests/data/fp_vectors_x64.txt)")
    ap.add_argument("--write", help="write the digests to this file")
    ap.add_argument("--soft-fma", action="store_true",
                    help="x86-64 build without -march: run the software fma (PS3_FP_SOFT_FMA=1), as a CPU without FMA3")
    ap.add_argument("--dump", help="print the first --count operand sets of this instruction instead")
    ap.add_argument("--count", type=int, default=20)
    a = ap.parse_args(argv)
    ps3 = find_ps3recomp(a.ps3recomp)
    if not ps3:
        print("fp_vectors: no ps3recomp checkout (--ps3recomp DIR)", file=sys.stderr)
        return 2
    src = generate(ps3, a.out)
    tag = (a.march or "default").replace("-", "_")
    exe = build(a.cc, src, a.out, ps3, a.march, tag)
    if a.dump:
        sys.stdout.write(run(exe, a.count, a.dump, a.count, a.soft_fma))
        return 0
    text = run(exe, a.n, soft_fma=a.soft_fma)
    digests = parse(text)
    header = (f"# fp_vectors digests: n={a.n} seed=0x{SEED:016X} host={host_name()} "
              f"march={a.march or 'default'}{' soft-fma' if a.soft_fma else ''} insns={len(digests)} "
              f"lifter-sha1={hashlib.sha1(open(os.path.join(ps3, 'tools', 'ppu_lifter.py'), 'rb').read()).hexdigest()[:12]}\n")
    if a.write:
        with open(a.write, "w", encoding="utf-8", newline="\n") as f:
            f.write(header + text)
    if not a.compare:
        sys.stdout.write(header + text)
        return 0
    ref = parse(open(a.compare, encoding="utf-8").read())
    bad = [k for k in ref if digests.get(k) != ref[k]]
    missing = [k for k in digests if k not in ref]
    print(f"fp_vectors: {len(ref) - len(bad)} of {len(ref)} instructions match {os.path.basename(a.compare)} "
          f"({host_name()}, march={a.march or 'default'}, n={a.n})")
    for k in bad:
        print(f"  DIFFERS: {k}  (here {digests.get(k, 'missing')}, reference {ref[k]})")
    for k in missing:
        print(f"  not in the reference: {k}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
