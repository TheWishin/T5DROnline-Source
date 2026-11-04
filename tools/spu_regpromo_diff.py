#!/usr/bin/env python3
"""Proof for the SPU lifter's register promotion (ps3recomp patch 0113, tools/spu_regpromo.py there):
every lifted SPU function of an image, as lifted without and with --regpromo, run side by side on the
same random inputs, must leave the same SPU context, local store and trace of every call.

    python tools/spu_regpromo_diff.py --old OFF/spu_recomp.c --new ON/spu_recomp.c --ps3recomp TREE
        [--define SPU_NEAR_FLOAT] [--cases 200] [--only 0xB1E8,...] [--keep DIR]

OFF and ON are the same image lifted with `spu_lifter.py --regpromo off` and with the default.
The tool writes one C harness (both versions of every function, renamed OLD_/NEW_), compiles it
with clang-cl at the flags of the game build (/O2, -msse4.1, -ffp-contract=off, SPU_LS_NO_HOOKS and
--define) and runs it:

  * each case starts from one random context -- registers mixing floats (normal, tiny, huge,
    denormal, +-0, exponent 255), small integers and local-store addresses -- and a random 256 KB
    local store; the old function runs, then the new one from the same bytes;
  * every other lifted function they call or branch to, and every runtime routine they use
    (spu_drain_call, spu_img_restore, spu_stop, channels, halts, indirect branches ...), is a stub
    that hashes the whole register file, pc and status at the call into the trace and then changes
    a few registers by that hash -- so a call that saw other registers, or a caller that did not
    reload what the callee changed, shows up;
  * every label counts a step; a case past 20,000 steps (a loop the random counter made endless)
    is stopped the same way in both versions and counted, not compared;
  * compared: the register file, pc, the pending trampoline, status, stop code, host depth, image
    id, a hash of the local store and the call trace. Exit 1 on any difference.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

FUNC = re.compile(r"^void ([A-Za-z_0-9]+)\(spu_context\* ctx\) \{\n(.*?)^\}\n", re.M | re.S)
LABEL = re.compile(r"^[ \t]*(loc_[0-9A-F]+:)[ \t]*$", re.M)

HARNESS_HEAD = r"""
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <setjmp.h>
#include "spu_context.h"
#include "spu_helpers.h"
static jmp_buf rp_jb;
static uint64_t rp_trace, rp_steps;
static int rp_stopped;
#define RP_MAX_STEPS 20000
#define RP_TICK() do { if (++rp_steps > RP_MAX_STEPS) { rp_stopped = 1; longjmp(rp_jb, 1); } } while (0)
#ifdef RP_FINITE
/* SPU_FAST_FLOAT images: host IEEE ops, whose NaN payload depends on the operand order the compiler picks
 * (fadd/fmul are commutative to it) -- in the old lift as much as in the new; every NaN counts as one */
static uint32_t rp_canon(uint32_t w) { return ((w & 0x7F800000u) == 0x7F800000u && (w & 0x7FFFFFu)) ? 0x7FC00000u : w; }
#else
static uint32_t rp_canon(uint32_t w) { return w; }
#endif
static uint64_t rp_mix(uint64_t h, uint64_t v) { h ^= v + 0x9E3779B97F4A7C15ull + (h << 6) + (h >> 2); return h * 0x100000001B3ull; }
static void rp_seen(spu_context* ctx, uint64_t tag) {
    uint64_t h = rp_mix(rp_trace, tag);
    for (int r = 0; r < 128; r++)
        for (int i = 0; i < 4; i++) h = rp_mix(h, rp_canon(ctx->gpr[r]._u32[i]));
    h = rp_mix(h, (uint64_t)ctx->pc); h = rp_mix(h, (uint64_t)ctx->host_depth);
    h = rp_mix(h, (uint64_t)(uint32_t)ctx->image_id); h = rp_mix(h, (uint64_t)ctx->status);
    rp_trace = h;
    /* a callee changes registers: a few, chosen and filled by the hash */
    for (int k = 0; k < 6; k++) {
        const int r = (int)((h >> (k * 7)) & 127);
        ctx->gpr[r]._u32[k & 3] ^= (uint32_t)(h >> 32) | 1u;
    }
}
"""

# runtime routines the lifted code may call; the stub's tag names it
RUNTIME_STUBS = r"""
void spu_drain_call(spu_context* ctx, uint32_t return_pc) { rp_seen(ctx, 0x1000000ull + return_pc); }
void spu_img_restore(spu_context* ctx, int32_t saved_img) { rp_seen(ctx, 0x2000000ull + (uint32_t)saved_img); }
void spu_indirect_branch(spu_context* ctx) { rp_seen(ctx, 0x3000000ull); }
void spu_halt(spu_context* ctx) { rp_seen(ctx, 0x4000000ull); longjmp(rp_jb, 2); }
void spu_stop(spu_context* ctx) { rp_seen(ctx, 0x5000000ull + ctx->stop_code); }
void spu_wrch(spu_context* ctx, uint32_t ch, u128 v) {
    rp_trace = rp_mix(rp_mix(rp_mix(rp_trace, 0x6000000ull + ch), v._u32[0]), v._u32[1]);
    rp_seen(ctx, 0x6100000ull + ch);
}
u128 spu_rdch(spu_context* ctx, uint32_t ch) {
    rp_seen(ctx, 0x7000000ull + ch);
    u128 r; for (int i = 0; i < 4; i++) r._u32[i] = (uint32_t)(rp_trace >> (8 * i)); return r;
}
u128 spu_rchcnt(spu_context* ctx, uint32_t ch) {
    rp_seen(ctx, 0x8000000ull + ch);
    u128 r; memset(&r, 0, sizeof r); r._u32[0] = (uint32_t)(rp_trace & 1); return r;
}
"""

MAIN = r"""
typedef void (*fn_t)(spu_context*);
typedef struct { const char* name; fn_t old_fn, new_fn; } pair_t;
extern const pair_t rp_pairs[];
static uint64_t xs = 0x2545F4914F6CDD1Dull;
static uint32_t xr(void) { xs ^= xs << 13; xs ^= xs >> 7; xs ^= xs << 17; return (uint32_t)xs; }
static int bias;   /* after a case stopped at the step limit: more small integers (loop counters) */
static uint32_t rnd_word_any(void) {
    static const uint32_t sp[] = {0, 0x80000000u, 1, 0x00400000u, 0x807FFFFFu, 0x00800000u, 0x7F7FFFFFu, 0xFF7FFFFFu,
        0x7F800000u, 0xFF800000u, 0x7FC00000u, 0xFFFFFFFFu, 0x3F800000u, 0xBF800000u, 0x3F000000u, 0x47000000u};
    const uint32_t r = xr();
    if (bias && (r >> 29) < (uint32_t)bias) return (r >> 3) & 63;
    switch (r & 7) {
    case 0: return sp[(r >> 3) & 15];
    case 1: return (r >> 3) & 63;                                   /* small integers: counters, indices */
    case 2: return ((r >> 3) & 0x3FFF0u);                            /* local-store addresses */
    case 3: return (r & 0x807FFFFFu) | ((100u + (xr() % 56u)) << 23); /* ordinary floats */
    case 4: return (r & 0x807FFFFFu) | (((r >> 8) & 3u) << 23);       /* tiny / denormal */
    default: return xr();
    }
}
static uint32_t rnd_word(void) {
#ifdef RP_FINITE   /* no exponent-255 words: host IEEE ops (SPU_FAST_FLOAT) leave NaN payloads to the compiler */
    for (;;) { const uint32_t w = rnd_word_any(); if ((w & 0x7F800000u) != 0x7F800000u) return w; }
#else
    return rnd_word_any();
#endif
}
static uint64_t ls_hash(const uint8_t* ls) {
    uint64_t h = 1469598103934665603ull;
    const uint32_t* w = (const uint32_t*)ls;
    for (int i = 0; i < 0x40000 / 4; i++) h = rp_mix(h, rp_canon(_byteswap_ulong(w[i])));
    return h;
}
typedef struct { spu_context c; uint64_t ls, trace; int how; } result_t;
static void run(fn_t f, spu_context* c, result_t* out) {
    rp_trace = 0; rp_steps = 0; rp_stopped = 0;
    volatile int how = setjmp(rp_jb);
    if (how == 0) f(c);
    out->how = how;
    out->c = *c; out->ls = ls_hash(c->ls); out->trace = rp_trace;
}
static int same(const result_t* a, const result_t* b) {
    if (a->how != b->how || a->ls != b->ls || a->trace != b->trace) return 0;
    for (int r = 0; r < 128; r++) for (int i = 0; i < 4; i++)
        if (rp_canon(a->c.gpr[r]._u32[i]) != rp_canon(b->c.gpr[r]._u32[i])) return 0;
    return a->c.pc == b->c.pc && a->c.tramp_fn == b->c.tramp_fn && a->c.status == b->c.status &&
           a->c.stop_code == b->c.stop_code && a->c.host_depth == b->c.host_depth && a->c.image_id == b->c.image_id;
}
int main(int argc, char** argv) {
    const int cases = argc > 1 ? atoi(argv[1]) : 200;
    static spu_context init, c;
    uint8_t* ls0 = (uint8_t*)malloc(0x40000);
    uint8_t* ls = (uint8_t*)malloc(0x40000);
    long long compared = 0, stopped = 0, differ = 0, funcs = 0;
    for (const pair_t* p = rp_pairs; p->name; p++, funcs++) {
        int bad = 0, done = 0;
        bias = 0;
        for (int k = 0; done < cases && k < cases * 40; k++) {
            memset(&init, 0, sizeof init);
            for (int r = 0; r < 128; r++) for (int i = 0; i < 4; i++) init.gpr[r]._u32[i] = rnd_word();
            init.pc = 0x100; init.host_depth = (int)(xr() & 3); init.image_id = 1;
            { const int b = bias; bias = 0; for (int i = 0; i < 0x40000; i += 4) { uint32_t w = rnd_word(); memcpy(ls0 + i, &w, 4); } bias = b; }
            result_t A, B;
            c = init; memcpy(ls, ls0, 0x40000); c.ls = ls; run(p->old_fn, &c, &A);
            if (A.how == 1) { stopped++; if (bias < 7) bias++; continue; }
            done++;
            c = init; memcpy(ls, ls0, 0x40000); c.ls = ls; run(p->new_fn, &c, &B);
            compared++;
            if (!same(&A, &B)) { differ++; if (bad++ < 2) printf("DIFFER %s case %d (how %d/%d)\n", p->name, k, A.how, B.how); }
        }
    }
    printf("%lld function(s), %lld case(s) compared, %lld stopped at the step limit, %lld differ\n",
           funcs, compared, stopped, differ);
    return differ != 0;
}
"""


def functions(path):
    text = open(path, encoding="utf-8").read().replace("\r\n", "\n")
    return {m.group(1): m.group(2) for m in FUNC.finditer(text)}, text


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--old", required=True)
    ap.add_argument("--new", required=True)
    ap.add_argument("--ps3recomp", required=True)
    ap.add_argument("--define", action="append", default=[])
    ap.add_argument("--cases", type=int, default=200)
    ap.add_argument("--only", default="", help="comma list of function start addresses")
    ap.add_argument("--finite", action="store_true",
                    help="for images built with SPU_FAST_FLOAT: no exponent-255 (Inf/NaN) input words, and every NaN "
                         "compares as one -- host IEEE operations give NaN payloads the compiler may pick (operand order)")
    ap.add_argument("--keep", default="", help="write the harness and the exe here")
    ap.add_argument("--clang", default=shutil.which("clang-cl") or r"C:\Program Files\LLVM\bin\clang-cl.exe")
    a = ap.parse_args()

    old, _ = functions(a.old)
    new, _ = functions(a.new)
    if set(old) != set(new):
        sys.exit("the two lifts have different functions")
    only = {int(x, 0) for x in a.only.split(",") if x.strip()}
    names = sorted(n for n in old if old[n] != new[n]
                   and (not only or int(n.rsplit("_", 1)[1], 16) in only))
    print(f"{len(old)} function(s), {len(names)} promoted (different in the two lifts)")
    if not names:
        return 0
    out = [HARNESS_HEAD]
    allf = sorted(old)
    for n in allf:          # every lifted function by its own name is a stub for the others
        out.append(f"void {n}(spu_context* ctx);")
    out.append(RUNTIME_STUBS)
    for n in allf:
        addr = int(n.rsplit("_", 1)[1], 16)
        out.append(f"void {n}(spu_context* ctx) {{ rp_seen(ctx, 0x9000000ull + 0x{addr:X}u); }}")
    for n in names:
        for tag, body in (("OLD_", old[n]), ("NEW_", new[n])):
            body = LABEL.sub(r"\1 RP_TICK();", body)
            out.append(f"static void {tag}{n}(spu_context* ctx) {{\n{body}}}")
    out.append(MAIN)
    out.append("const pair_t rp_pairs[] = {")
    out += [f'    {{"{n}", OLD_{n}, NEW_{n}}},' for n in names]
    out.append("    {0, 0, 0}};")
    src = "\n".join(out)
    work = a.keep or tempfile.mkdtemp(prefix="spu_rp_")
    os.makedirs(work, exist_ok=True)
    c = os.path.join(work, "spu_rp_diff.c")
    with open(c, "w", encoding="utf-8", newline="\n") as f:
        f.write(src)
    exe = os.path.join(work, "spu_rp_diff.exe")
    spu = os.path.join(a.ps3recomp, "runtime", "spu")
    cmd = [a.clang, "/nologo", "/O2", "/Ob2", "/W0", "/std:c17", "-msse4.1", "/clang:-ffp-contract=off",
           "/clang:-fno-finite-loops", "/DSPU_LS_NO_HOOKS", "/I", spu, "/I", os.path.join(a.ps3recomp, "runtime"),
           "/I", os.path.join(a.ps3recomp, "include"), c, "/Fe:" + exe, "/Fo:" + os.path.join(work, "spu_rp_diff.obj")]
    cmd += ["/D" + d for d in a.define] + (["/DRP_FINITE"] if a.finite else [])
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=work)
    if r.returncode != 0 or not os.path.isfile(exe):
        sys.stdout.write((r.stdout + r.stderr)[-6000:])
        sys.exit("the harness did not build")
    r = subprocess.run([exe, str(a.cases)], capture_output=True, text=True)
    sys.stdout.write(r.stdout[-6000:])
    if not a.keep:
        shutil.rmtree(work, ignore_errors=True)
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
