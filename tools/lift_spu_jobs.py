#!/usr/bin/env python3
"""Extract, lift and register the game's SPURS job binaries.

    python tools/lift_spu_jobs.py --elf game/EBOOT.elf --spu build/spu \
                                  [--ps3recomp deps/ps3recomp] [--relift]

Tekken 5: Dark Resurrection Online runs three SPURS jobs every frame on one job
chain (JOBLIST of skinning jobs, SYNC, then a job that signals the PPU):

  skin4x    vertex skinning, modes 0x40..0x4F
  skin1x    vertex skinning, modes 0x10..0x13
  jcsignal  throws an SPU user event to the queue the game attached with
            cellSpursAttachLv2EventQueue; the PPU waits for exactly that event

They are NOT SPU ELFs. Each is a raw local-store image (a 16-byte GUID that
decodes as harmless `ila` instructions, then the code) stored in the EBOOT's
read-only 0x10000000 segment, so extract_spu_images.py cannot see them. The job
descriptors point straight at these addresses, and the runtime looks a job up
by the FNV-1a-64 of exactly sizeBinary<<4 bytes at the descriptor's eaBinary
(runtime/spu/spu_workload.c, spu_workload_dispatch_job). So this script cuts
exactly those bytes out of the ELF, checks them against the expected
fingerprints (a different game version fails loudly here instead of
mis-registering), and lifts each one at base 0 -- the runtime loads a job image
at LS 0 (runtime/spu/spurs_job.c), so the lifted addresses equal the link-time
ones.

Output, per job, under --spu (beside the sound core from build_spu_workloads.py):

  images/<job>.bin            the raw image
  images/<job>.funcs.json     function boundaries (find_spu_functions.py --raw)
  lifted/<job>/spu_recomp.c   lifted C, plus an appended registration block
  lifted/<job>/spu_recomp.h

The registration lives in the lifted file itself (a constructor that registers
the image's functions under its own image id and its fingerprint), so the
CMake glob <SPU_DIR>/lifted/*/spu_recomp.c picks each job up with no change to
spu_workloads.c, which build_spu_workloads.py owns and regenerates.

Everything written is game-derived and belongs in git-ignored build/.
"""
import argparse
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# (name, guest EA, fingerprinted size, FNV-1a-64, code end, image id,
#  jump-table targets, description)
#
# size: the job descriptor's sizeBinary<<4 -- what the runtime fingerprints.
#   The signal job's code is 0xA8 bytes, but its descriptor is built with
#   size 0xA8 rounded up to 16 (0x3806d0), so 0xB0 bytes are hashed.
# code end: where the image's code stops and its rodata (the printf format
#   "Skinning Geometry no support types(%d)", float tables, LS buffer offsets)
#   begins. Data that happens to decode as branches would otherwise seed bogus
#   functions.
# jump-table targets: each skinning job dispatches on its mode through a
#   `bi $r4` into a table of handler stubs (skin4x: table at 0xE0, skin1x: at
#   0x120). Indirect targets must be registered function entries; the finder
#   usually seeds them already, passing them is belt and braces.
# image id: distinct from build_spu_workloads.py's sequential ids (1..N, the
#   sound core is 1) so per-image indirect-branch tables never mix.
JOBS = [
    ("skin4x",   0x1003DF80, 0x4480, 0x398E459063BA810A, 0x33B0, 32,
     [0x160, 0x1A0, 0x1E0, 0x220], "vertex skinning, modes 0x40-0x4F"),
    ("skin1x",   0x10042480, 0x4200, 0xA5D68040C9BF35AF, 0x30E0, 33,
     [0x130, 0x170, 0x1B0, 0x1F0], "vertex skinning, modes 0x10-0x13"),
    ("jcsignal", 0x10046700, 0x00B0, 0xE79EA03E65964477, 0x00B0, 34,
     [], "job-chain completion: throws an SPU user event to the attached queue"),
]

REG_MARK = "/* ---- t5dr job registration (appended by tools/lift_spu_jobs.py) ---- */"


def fnv1a64(b):
    h = 1469598103934665603
    for x in b:
        h = ((h ^ x) * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return h


def load_segments(path):
    """PT_LOAD segments of a 64-bit big-endian (PPU) ELF: [(vaddr, bytes)]."""
    b = open(path, "rb").read()
    if b[:4] != b"\x7fELF" or b[4] != 2 or b[5] != 2:
        sys.exit(f"[lift_spu_jobs] {path}: not a 64-bit big-endian ELF (decrypted EBOOT expected)")
    phoff = int.from_bytes(b[0x20:0x28], "big")
    phentsize = int.from_bytes(b[0x36:0x38], "big")
    phnum = int.from_bytes(b[0x38:0x3A], "big")
    segs = []
    for i in range(phnum):
        p = phoff + i * phentsize
        if int.from_bytes(b[p:p + 4], "big") != 1:      # PT_LOAD
            continue
        off = int.from_bytes(b[p + 8:p + 16], "big")
        va = int.from_bytes(b[p + 16:p + 24], "big")
        fs = int.from_bytes(b[p + 32:p + 40], "big")
        segs.append((va, b[off:off + fs]))
    return segs


def read_guest(segs, ea, size):
    for va, data in segs:
        if va <= ea and ea + size <= va + len(data):
            return data[ea - va:ea - va + size]
    return None


_INC_RE = re.compile(r'#include\s+"(?:\.\./)+runtime/spu/([A-Za-z0-9_]+\.h)"')


def debase_includes(path):
    """The lifter includes the runtime headers by a relative path that only
    resolves inside the ps3recomp tree; the CMake target adds runtime/spu to
    the include path instead (same rewrite as build_spu_workloads.py)."""
    txt = open(path, encoding="utf-8", errors="ignore").read()
    new = _INC_RE.sub(r'#include "\1"', txt)
    if new != txt:
        open(path, "w", encoding="utf-8", newline="\n").write(new)


def registration(name, prefix, ea, size, fp, image_id, desc):
    return f"""
{REG_MARK}
/* SPURS job "{name}": {desc}.
 * Raw job image at guest EA 0x{ea:08X}, {size} (0x{size:X}) bytes, FNV-1a-64
 * 0x{fp:016X}. The job-chain walker (libs/spurs/cellSpurs.c) hands the runtime
 * eaBinary/sizeBinary from the job descriptor, the dispatcher fingerprints those
 * bytes and enters the lifted code at LS 0 with the jm2 job ABI. */
#include "spu_workload.h"
extern void spu_begin_image(int image_id);

__attribute__((constructor)) static void {prefix}register_job(void)
{{
    spu_begin_image({image_id}); {prefix}spu_recomp_register();
    spu_workload_register_img(0x{fp:016X}ULL, {prefix}spu_func_00000000, {image_id}, "{name}");
    spu_begin_image(0);
}}
"""


def run(cmd):
    print("  >", " ".join(cmd), flush=True)
    if subprocess.run(cmd).returncode != 0:
        sys.exit(f"[lift_spu_jobs] command failed: {cmd[1] if len(cmd) > 1 else cmd[0]}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--elf", required=True, help="decrypted PPU EBOOT.elf")
    ap.add_argument("--spu", required=True, help="SPU output dir (the CMake SPU_DIR)")
    ap.add_argument("--ps3recomp", default=os.path.join(ROOT, "deps", "ps3recomp"),
                    help="ps3recomp checkout (for tools/spu_lifter.py, find_spu_functions.py)")
    ap.add_argument("--relift", action="store_true", help="lift again even if the output exists")
    a = ap.parse_args()

    tools = os.path.join(a.ps3recomp, "tools")
    finder = os.path.join(tools, "find_spu_functions.py")
    lifter = os.path.join(tools, "spu_lifter.py")
    for t in (finder, lifter):
        if not os.path.exists(t):
            sys.exit(f"[lift_spu_jobs] missing {t}")

    segs = load_segments(a.elf)
    images = os.path.join(a.spu, "images")
    os.makedirs(images, exist_ok=True)

    for name, ea, size, want_fp, code_end, image_id, targets, desc in JOBS:
        img = read_guest(segs, ea, size)
        if img is None:
            sys.exit(f"[lift_spu_jobs] {name}: 0x{ea:08X}+0x{size:X} is not file-backed in {a.elf}")
        fp = fnv1a64(img)
        if fp != want_fp:
            sys.exit(f"[lift_spu_jobs] {name}: fingerprint 0x{fp:016X} != expected 0x{want_fp:016X} "
                     f"(not NPUB30009 v01.00?)")

        prefix = f"t5job_{name}_"
        outdir = os.path.join(a.spu, "lifted", name)
        src = os.path.join(outdir, "spu_recomp.c")
        if os.path.exists(src) and not a.relift and REG_MARK in open(src, encoding="utf-8").read():
            print(f"[lift_spu_jobs] {name}: already lifted ({src})", flush=True)
            continue

        binp = os.path.join(images, f"{name}.bin")
        open(binp, "wb").write(img)

        # Function boundaries: a raw image has no symbols, so every seed comes
        # from branch analysis. Drop anything the finder seeded in the rodata
        # tail, then make sure the jump-table targets are entries.
        funcs_json = os.path.join(images, f"{name}.funcs.json")
        run([sys.executable, finder, binp, "--raw", "--base", "0", "--out", funcs_json])
        funcs = [f for f in json.load(open(funcs_json)) if f["start"] < code_end]
        for f in funcs:
            f["end"] = min(f["end"], code_end)
        json.dump(funcs, open(funcs_json, "w"), indent=1)

        os.makedirs(outdir, exist_ok=True)
        cmd = [sys.executable, lifter, binp, "--base", "0", "--length", hex(code_end),
               "--functions", funcs_json, "--symbol-prefix", prefix, "-o", outdir]
        if targets:
            cmd += ["--extra-funcs", ",".join(hex(t) for t in targets)]
        run(cmd)

        debase_includes(os.path.join(outdir, "spu_recomp.h"))
        debase_includes(src)
        hdr = open(os.path.join(outdir, "spu_recomp.h"), encoding="utf-8").read()
        if f"{prefix}spu_func_00000000(" not in hdr:
            sys.exit(f"[lift_spu_jobs] {name}: no entry function at LS 0 in the lift")
        with open(src, "a", encoding="utf-8", newline="\n") as f:
            f.write(registration(name, prefix, ea, size, fp, image_id, desc))
        print(f"[lift_spu_jobs] {name}: 0x{ea:08X}+0x{size:X} fp=0x{fp:016X} image {image_id} -> {outdir}", flush=True)


if __name__ == "__main__":
    main()
