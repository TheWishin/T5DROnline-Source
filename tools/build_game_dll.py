#!/usr/bin/env python3
"""Compile the lifted game code into t5dr_game.dll with clang-cl + lld-link only.

    python tools/build_game_dll.py --recomp build/recomp --spu build/spu --deps deps/ps3recomp
                                   --host-lib <dir of t5dr.exe>/t5dr.lib --out <dir of t5dr.exe>/t5dr_game.dll
                                   [--llvm DIR] [--jobs N]

This is the player-side half of the "no Visual Studio needed" build (docs/RELEASE.md):
t5dr.exe -- ps3recomp's runtime -- is compiled once by us (CMake -DT5DR_GAME_DLL=ON)
and shipped; the player's PC compiles only what came out of their own game. That
code needs no C runtime or Windows SDK headers: clang's own headers (stdint.h,
intrin.h) plus the few declarations in tools/gamedll/include are enough, and it
links against two import libraries made from our own .def files (t5dr.exe's
exports, ucrtbase.dll's C functions). clang-cl, lld-link and clang's headers are
redistributable (Apache-2.0 WITH LLVM-exception).
"""
import argparse
import glob
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GDIR = os.path.join(ROOT, "tools", "gamedll")
NO_WINDOW = 0x08000000 if os.name == "nt" else 0


# x86-64-v3 (what -march=x86-64-v3 may use): clang's macros for each feature.
V3_FEATURES = ("__AVX__", "__AVX2__", "__BMI__", "__BMI2__", "__F16C__", "__FMA__", "__LZCNT__", "__MOVBE__")


def host_cpu_level(cl, scratch):
    """'x86-64-v3' when this PC's CPU *and* Windows support AVX2/FMA/BMI2/MOVBE/F16C/LZCNT, else 'none'
    (plain x86-64 for the lifted PPU code), plus the missing features. clang's -march=native reads
    CPUID and XGETBV itself -- unlike IsProcessorFeaturePresent(PF_AVX2_INSTRUCTIONS_AVAILABLE), which
    Windows 10 versions before 2004 do not know (they answer "no" on an AVX2 CPU)."""
    src = os.path.join(scratch, "cpu_probe.c")
    with open(src, "w") as f:
        f.write("int x;\n")
    try:
        cpu = os.environ.get("T5DR_TEST_CPU_MODEL", "native")    # tests: e.g. "sandybridge" (AVX, no AVX2)
        r = subprocess.run([cl, "/nologo", "/X", f"/clang:-march={cpu}", "/clang:-dM", "/E", "-TC", src],
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           creationflags=NO_WINDOW, timeout=60)
        macros = set(l.split()[1] for l in r.stdout.splitlines() if l.startswith("#define "))
        if r.returncode == 0 and "__x86_64__" in macros:
            missing = [m.strip("_").lower() for m in V3_FEATURES if m not in macros]
            return ("none" if missing else "x86-64-v3"), missing
    except (OSError, subprocess.SubprocessError):
        pass
    if os.name == "nt":                     # fallback: Windows' own answer
        import ctypes
        if ctypes.windll.kernel32.IsProcessorFeaturePresent(40):   # PF_AVX2_INSTRUCTIONS_AVAILABLE
            return "x86-64-v3", []
    return "none", ["avx2 (not detected)"]


def find_llvm(arg):
    for d in ([arg] if arg else []) + [os.path.join(ROOT, "toolchain", "llvm", "bin"),
                                       os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "LLVM", "bin")]:
        if d and os.path.exists(os.path.join(d, "clang-cl.exe")) and os.path.exists(os.path.join(d, "lld-link.exe")):
            return d
    sys.exit("clang-cl.exe + lld-link.exe not found (--llvm DIR)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--recomp", required=True)
    ap.add_argument("--spu", required=True)
    ap.add_argument("--deps", required=True, help="ps3recomp source (headers, spu_dispatch_mt.c)")
    ap.add_argument("--host-lib", required=True, help="t5dr.lib, the import library of the runtime host")
    ap.add_argument("--out", required=True, help="the DLL to write (next to t5dr.exe)")
    ap.add_argument("--obj", help="object directory (default: <out dir>/gamedll_obj)")
    ap.add_argument("--llvm", help="folder with clang-cl.exe and lld-link.exe")
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 4)
    ap.add_argument("--force", action="store_true", help="recompile objects that look current")
    ap.add_argument("--march", default="auto",
                    help="target CPU of the lifted PPU code: auto (x86-64-v3 when this PC's CPU and Windows "
                         "support it, else none), x86-64-v3, native, none")
    a = ap.parse_args()

    llvm = find_llvm(a.llvm)
    cl, lld = os.path.join(llvm, "clang-cl.exe"), os.path.join(llvm, "lld-link.exe")
    obj = a.obj or os.path.join(os.path.dirname(os.path.abspath(a.out)), "gamedll_obj")
    os.makedirs(obj, exist_ok=True)
    ps3 = os.path.abspath(a.deps)

    # Nothing from an installed Visual Studio or Windows SDK may leak in.
    env = {k: v for k, v in os.environ.items()
           if k.upper() not in ("INCLUDE", "LIB", "LIBPATH", "EXTERNAL_INCLUDE", "VCINSTALLDIR", "VCTOOLSINSTALLDIR",
                                "WINDOWSSDKDIR", "UCRTVERSION", "UNIVERSALCRTSDKDIR")}
    common = ["/nologo", "/X",                      # /X: no system include paths, only clang's own headers
              "-fms-compatibility-version=19.44", "/O2", "/Ob2", "/DNDEBUG", "/DWIN32", "/D_WINDOWS",
              "/GS-", "/Zl",                        # no stack cookies, no default-library directives
              "/FI" + os.path.join(GDIR, "include", "t5dr_dll_prefix.h"),
              "-I" + os.path.join(GDIR, "include"), "-I" + os.path.abspath(a.recomp),
              "-I" + os.path.join(ps3, "runtime", "ppu"), "-I" + os.path.join(ps3, "runtime", "spu"),
              "-I" + os.path.join(ps3, "include")]
    # The lifted PPU code is built for this PC: x86-64-v3 (AVX2/FMA/BMI2/MOVBE) when
    # it has AVX2 -- byte-swapped guest accesses become movbe, the fused ops single
    # vfmadd instructions -- else the x86-64 baseline. -ffp-contract=off either way:
    # no fusing of a*b+c that the PPU code wrote as two operations. Both targets
    # compute the same bits, so players with either can play each other: the
    # lifter's FP helpers (ps3recomp runtime/ppu/ppu_fp_det.h, patch 0032) never
    # call the C runtime's math, and a fused op without FMA instructions is an
    # exact software fma (docs/NETPLAY.md, "Same game state on every CPU";
    # tools/cross_build_test.py checks it).
    march = a.march
    why = ""
    if march == "auto":
        march, missing = host_cpu_level(cl, obj)
        why = (" (this processor has AVX2, FMA, BMI2 and MOVBE)" if march != "none" else
               " (baseline x86-64: this processor or Windows lacks " + ", ".join(missing) + ")")
    ppu_opts = ["/clang:-ffp-contract=off"] + ([] if march == "none" else [f"/clang:-march={march}"])
    print(f"lifted PPU code: -march={march}{why}", flush=True)
    srcs = sorted(glob.glob(os.path.join(a.recomp, "*.cpp")))
    spu_c = sorted(glob.glob(os.path.join(a.spu, "lifted", "*", "spu_recomp.c")))
    spu_w = os.path.join(a.spu, "spu_workloads.c")
    c_srcs = spu_c + ([spu_w] if os.path.exists(spu_w) else [])
    if c_srcs:
        c_srcs.append(os.path.join(ps3, "runtime", "spu", "spu_dispatch_mt.c"))
    c_srcs.append(os.path.join(GDIR, "t5dr_game_dll.c"))
    if not srcs:
        sys.exit(f"no lifted sources in {a.recomp}")

    # an object is current when it is newer than its source and than everything it was compiled with
    # objects remember the target CPU they were compiled for (a native folder moved to another PC,
    # or a forced --march): any change recompiles everything
    stamp_path = os.path.join(obj, "march.txt")
    try:
        stamp_ok = open(stamp_path).read().strip() == march
    except OSError:
        stamp_ok = False
    newest_dep = max(os.path.getmtime(p) for p in
                     glob.glob(os.path.join(GDIR, "include", "*.h")) + [os.path.abspath(__file__)] +
                     glob.glob(os.path.join(a.recomp, "*.h")) + glob.glob(os.path.join(ps3, "runtime", "spu", "*.h")) +
                     glob.glob(os.path.join(ps3, "runtime", "ppu", "*.h")))

    def job(src):
        is_c = src.endswith(".c")
        name = os.path.basename(os.path.dirname(src)) + "_" + os.path.basename(src) if "lifted" in src else os.path.basename(src)
        o = os.path.join(obj, name + ".obj")
        if (not a.force and os.path.exists(o) and os.path.getmtime(o) > max(os.path.getmtime(src), newest_dep)
                and stamp_ok):
            return 0, o
        cmd = [cl] + common
        if is_c:
            cmd += ["/std:c17", "-TC", "/DSPU_USE_DISPATCH_MT", "-msse4.1"]   # as ps3recomp_runtime's INTERFACE option
            cmd += ppu_opts     # same target CPU as the PPU code: the sound core ~7% cheaper with x86-64-v3 (CMakeLists.txt)
            if os.path.basename(os.path.dirname(src)).startswith("skin"):
                cmd += ["/DSPU_FAST_FLOAT"]     # render-only skinning jobs: IEEE float ops (CMakeLists.txt)
            elif os.path.basename(os.path.dirname(src)) == "bnuscore":
                cmd += ["/DSPU_NEAR_FLOAT"]     # the sound core: near-exact IEEE float ops (CMakeLists.txt)
            if "lifted" in src:
                cmd += ["/DSPU_LS_NO_HOOKS"]    # no local-store debug hooks in lifted images (CMakeLists.txt)
        else:
            cmd += ["-std:c++20", "-TP", "/EHs-c-", "/Zc:tlsGuards-"] + ppu_opts
        if os.path.basename(src) == "t5dr_game_dll.c":
            cmd += [f'/DT5DR_GAME_MARCH="{march}"']   # t5dr_game_march: checked by the runtime at load
        cmd += ["-c", src, "/Fo" + o]
        t = time.time()
        r = subprocess.run(cmd, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           creationflags=NO_WINDOW)
        with lock:
            done[0] += 1
            # "[k/n]" like ninja, so the launcher shows the compile progress
            print(f"[{done[0]}/{len(todo)}] {os.path.basename(src)}: {time.time() - t:.1f} s"
                  + ("" if r.returncode == 0 else " FAILED"), flush=True)
        if r.returncode:
            print((r.stdout + r.stderr)[:3000], flush=True)
        return r.returncode, o

    t0 = time.time()
    print(f"compiling {len(srcs) + len(c_srcs)} files with {cl} ({a.jobs} jobs)", flush=True)
    if not stamp_ok and os.path.exists(stamp_path):
        os.remove(stamp_path)                  # written again only when every object is built
    # biggest first: the longest chunk bounds the wall time
    todo = sorted(srcs + c_srcs, key=lambda p: -os.path.getsize(p))
    done, lock = [0], threading.Lock()
    with ThreadPoolExecutor(a.jobs) as ex:
        res = list(ex.map(job, todo))
    if any(rc for rc, _ in res):
        sys.exit("compile failed")
    with open(stamp_path, "w") as f:
        f.write(march + "\n")
    t1 = time.time()

    ucrt = os.path.join(obj, "ucrt_min.lib")
    subprocess.run([lld, "/lib", "/nologo", "/machine:x64", "/def:" + os.path.join(GDIR, "ucrt_min.def"),
                    "/out:" + ucrt], check=True, env=env, creationflags=NO_WINDOW)
    link = [lld, "/nologo", "/DLL", "/NOENTRY", "/NODEFAULTLIB", "/MACHINE:X64", "/OPT:REF", "/OPT:ICF",
            "/OUT:" + a.out, "/IMPLIB:" + os.path.join(obj, "t5dr_game.lib"),
            "/EXPORT:function_table,DATA", "/EXPORT:function_table_count,DATA"]
    link += [o for _, o in res] + [os.path.abspath(a.host_lib), ucrt]
    r = subprocess.run(link, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       creationflags=NO_WINDOW)
    if r.returncode:
        print(r.stdout + r.stderr)
        sys.exit("link failed")
    print(f"wrote {a.out} ({os.path.getsize(a.out) / 1e6:.1f} MB): compile {t1 - t0:.1f} s, "
          f"link {time.time() - t1:.1f} s", flush=True)


if __name__ == "__main__":
    main()
