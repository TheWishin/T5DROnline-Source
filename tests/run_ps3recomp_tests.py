#!/usr/bin/env python3
"""Build and run ps3recomp's self-contained native tests on the patched tree.

    python tests/run_ps3recomp_tests.py --ps3recomp DIR [--out DIR] [--only NAME ...]

Needs clang-cl and the MSVC environment (vcvars64 / ilammy/msvc-dev-cmd), like
the runtime build. CI runs it after building ps3recomp_runtime
(.github/workflows/ci.yml); locally:

    cmd /c "vcvars64.bat && python tests/run_ps3recomp_tests.py --ps3recomp build/<you>/ps3recomp"

Each test is one executable compiled straight from its sources (the way
ps3recomp's own CI builds them), run with a timeout. The list favours tests
that compile the files our patches change (spu_helpers.h, spu_workload.c,
spurs_job.c) and the cheap Windows suites upstream already runs. A test that
prints one of its "nothing to compare" lines counts as a failure: a green tick
for a test that compared nothing is worse than a red one.
"""
import argparse
import collections
import os
import platform
import shutil
import subprocess
import sys
import time

# Sources the SPU MFC / lock-line tests link: the SPU runtime without the rest
# of the library (lists from ps3recomp's linux.yml; on Windows the POSIX shim
# runtime/platform/win32_compat.c is not needed, tests/shim/pthread.h is).
SPU_CORE = [
    "runtime/spu/spu_drain.c", "runtime/spu/spu_lockstep.c", "runtime/spu/spu_coherency.c",
    "runtime/spu/spu_workload.c", "runtime/spu/spurs_policy.c", "runtime/spu/spurs_job.c",
    "runtime/spu/spu_tsp_weak.c", "runtime/spu/spu_vm_pagemap.c", "runtime/spu/spurs_policy_blob_weak.c",
    "runtime/spu/spu_interp.c",
    "runtime/platform/fp_env.c",   # patch 0032: ppu_fp_env_fix (MXCSR pinning) used by spu_interp.c
]

HERE = os.path.dirname(os.path.abspath(__file__))
SHIM = os.path.join(HERE, "shim")   # pthread.h for Win32

TESTS = [
    # name, sources, include dirs (ps3recomp-relative, or SHIM), extra flags, timeout (s), why
    ("spu_float", ["runtime/spu/tests/test_spu_float_neon.c"], ["runtime/spu"], ["-msse4.1"], 300,
     "SSE4.1 spu_fa/fs/fm/fma/fms/fnms bit-exact vs. scalar (patch 0003)"),
    ("spu_shufb", ["runtime/spu/tests/test_spu_shufb.c"], ["runtime/spu"], ["-msse4.1"], 120,
     "SIMD shufb vs. scalar"),
    ("spu_helpers", ["runtime/spu/tests/test_spu_helpers.c"], ["runtime/spu"], ["-msse4.1"], 120,
     "SPU instruction helpers (spu_helpers.h, patch 0003)"),
    ("spu_numeric", ["runtime/spu/tests/test_spu_numeric_semantics.c"], ["runtime/spu"], ["-msse4.1"], 120,
     "SPU numeric semantics"),
    ("spu_fast_float", ["runtime/spu/tests/test_spu_fast_float.c"], ["runtime/spu"], ["-msse4.1", "/DSPU_FAST_FLOAT"],
     120, "SPU_FAST_FLOAT within 2-3 ulp of the exact path (patch 0027, render-only skinning jobs)"),
    ("spu_near_float", ["runtime/spu/tests/test_spu_near_float.c"], ["runtime/spu"], ["-msse4.1", "/DSPU_NEAR_FLOAT"],
     120, "SPU_NEAR_FLOAT: SPU zero/extended-range rules exact, 1-2 ulp otherwise (patch 0041, the sound core)"),
    ("spu_coherency", ["runtime/spu/tests/test_spu_coherency.c"], ["runtime/spu", SHIM], [], 120,
     "PPU/SPU lock-line coherence"),
    # Not here: test_spu_lifted_start.c (POSIX-only; with shims it links on
    # Windows but crashes the same way on the unpatched pin), and
    # libs/video/tests/test_gcm_user_command.c / libs/audio/tests/
    # test_audio_ring.c (POSIX-only, and not run by upstream CI either).
    # spu_mfc_slots is ps3recomp's test_spu_mfc_slots.c with the thread count
    # scaled to the machine (tests/c/test_spu_mfc_slots_ci.c, header says
    # what changed). The original starts one spinning worker per slot -- 128 at
    # the pin -- behind a barrier with a 10 s deadline, which a 4-vCPU GitHub
    # runner never meets: the job spent 367 s in it and failed on every run.
    # A leading "@" below means a file of this repository, relative to tests/.
    ("spu_mfc_slots", ["@c/test_spu_mfc_slots_ci.c"] + SPU_CORE,
     ["runtime/spu", "runtime/platform", SHIM], [], 300,
     "MFC engine slots; links spu_workload.c + spurs_job.c (patch 0002)"),
    ("spu_lockline_peer", ["runtime/spu/tests/test_spu_lockline_peer.c"] + SPU_CORE,
     ["runtime/spu", "runtime/platform", SHIM], [], 300,
     "SPU-to-SPU lock-line coherence; links spu_workload.c + spurs_job.c (patch 0002)"),
    ("texture_layout", ["libs/video/tests/test_texture_layout.c", "libs/video/rsx_texture_layout.c"],
     ["libs/video"], [], 120, "RSX texture layout"),
    ("rsx_primitives", ["libs/video/tests/test_rsx_primitives.c"], ["libs/video"], [], 120,
     "RSX primitive assembly"),
]

VACUOUS = ("nothing to compare",)

# Words that make a line of a test's output worth quoting in an annotation.
INTERESTING = ("fail", "assert", "error", "timeout", "timed out", "abort", "overflow", "[spu]", "crash")


def esc_data(s):
    return s.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def esc_prop(s):
    return esc_data(s).replace(":", "%3A").replace(",", "%2C")


def annotate(level, title, message):
    """A GitHub annotation. The job log needs a login, annotations do not (REST API
    /check-runs/<job id>/annotations), so a red run can be read from outside."""
    print(f"::{level} title={esc_prop(title)}::{esc_data(message)}", flush=True)


def as_text(x):
    if x is None:
        return ""
    return x.decode("utf-8", "replace") if isinstance(x, bytes) else x


def key_lines(text, tail=12, limit=3500):
    """What to read first when a test fails: its FAIL/assert/error lines (repeats
    folded into "xN"), then the last lines of its output."""
    lines = [l.rstrip() for l in text.splitlines() if l.strip()]
    seen = collections.Counter(l for l in lines if any(w in l.lower() for w in INTERESTING))
    out = [f"{l.strip()}" + (f"  (x{n})" if n > 1 else "") for l, n in list(seen.items())[:12]]
    if len(seen) > 12:
        out.append(f"... and {len(seen) - 12} more distinct lines of that kind")
    out.append("-- last lines --")
    out += lines[-tail:]
    return "\n".join(out)[-limit:]


def memory_mb():
    """(total, available) physical memory in MB on Windows, else None."""
    if os.name != "nt":
        return None
    import ctypes

    class MS(ctypes.Structure):
        _fields_ = [("len", ctypes.c_ulong), ("load", ctypes.c_ulong)]
        _fields_ += [(n, ctypes.c_ulonglong) for n in ("tot", "avail", "ptot", "pavail", "vtot", "vavail", "ext")]
    m = MS()
    m.len = ctypes.sizeof(m)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
        return None
    return m.tot >> 20, m.avail >> 20


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ps3recomp", required=True, help="patched ps3recomp tree")
    ap.add_argument("--out", default=None, help="where executables go (default: <ps3recomp>/../native-tests)")
    ap.add_argument("--cc", default=os.environ.get("CC_CLANG_CL") or shutil.which("clang-cl")
                    or r"C:\Program Files\LLVM\bin\clang-cl.exe")
    ap.add_argument("--only", nargs="*", help="run only these tests")
    a = ap.parse_args()

    src = os.path.abspath(a.ps3recomp)
    out = os.path.abspath(a.out or os.path.join(src, "..", "native-tests"))
    os.makedirs(out, exist_ok=True)
    gha = os.environ.get("GITHUB_ACTIONS") == "true"

    if gha:
        mem = memory_mb()
        annotate("notice", "ps3recomp native tests: runner",
                 f"{os.cpu_count()} cpus, " + (f"{mem[1]} of {mem[0]} MB memory free, " if mem else "")
                 + f"{platform.platform()}, python {platform.python_version()}, cc {a.cc}")

    results = []
    for name, sources, incs, flags, timeout, why in TESTS:
        if a.only and name not in a.only:
            continue
        objdir = os.path.join(out, name) + os.sep
        os.makedirs(objdir, exist_ok=True)
        exe = os.path.join(out, name + ".exe")
        # No NDEBUG: several tests check with assert().
        cmd = [a.cc, "/nologo", "/O2", "/W0", "/std:c17", "/D_CRT_SECURE_NO_WARNINGS",
               "/I" + os.path.join(src, "include")] + ["/I" + os.path.join(src, i) for i in incs] + flags \
            + [f"/Fo{objdir}", f"/Fe{exe}"] + [os.path.join(HERE, s[1:]) if s.startswith("@") else os.path.join(src, s)
                                          for s in sources]
        if gha:
            print(f"::group::{name}: {why}", flush=True)
        else:
            print(f"--- {name}: {why}", flush=True)
        t0 = time.time()
        text = ""                  # what the test (or the compiler) printed, for the annotation
        b = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
        if b.returncode != 0:
            text = b.stdout + b.stderr
            print(" ".join(cmd))
            print(text[-6000:])
            results.append((name, "BUILD FAILED", time.time() - t0))
        else:
            t1 = time.time()
            try:
                r = subprocess.run([exe], capture_output=True, text=True, errors="replace", timeout=timeout,
                                   cwd=objdir)
                text = r.stdout + r.stderr
                tail = "\n".join(text.splitlines()[-25:])
                print(tail)
                if r.returncode != 0:
                    status = f"FAILED (exit {r.returncode})"
                elif any(v in text for v in VACUOUS):
                    status = "FAILED (compared nothing)"
                else:
                    status = "ok"
            except subprocess.TimeoutExpired as e:
                text = as_text(e.stdout) + as_text(e.stderr)
                status = f"FAILED (timeout {timeout}s)"
            results.append((name, status, time.time() - t0))
            print(f"[{name}] compiled in {t1 - t0:.1f} s, ran {time.time() - t1:.1f} s", flush=True)
        if gha:
            print("::endgroup::", flush=True)
            if results[-1][1] != "ok":
                annotate("error", f"ps3recomp test {name}",
                         f"{results[-1][1]} after {results[-1][2]:.0f} s -- {why}\n" + key_lines(text))

    print("\nps3recomp native tests:")
    for name, status, secs in results:
        print(f"  {name:20s} {status:28s} {secs:6.1f}s")
    if gha:
        annotate("notice", "ps3recomp native tests: timings",
                 "; ".join(f"{n} {st} {sec:.0f}s" for n, st, sec in results))
    bad = [r for r in results if r[1] != "ok"]
    if bad or not results:
        sys.exit(f"{len(bad)} of {len(results)} failed")


if __name__ == "__main__":
    main()
