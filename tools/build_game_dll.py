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

Robustness (1.1.3; a player's build lost two chunks after ~5 s with 12 compilers running and the log
showed only the first 3,000 characters of warnings):
  * the default number of compilers fits the free memory: one per processor, but only as many as
    (free memory - COMPILE_RESERVE_MB) / COMPILE_JOB_MB allows (auto_jobs; the line "jobs: N -- ..."
    says which limit applied);
  * a file that fails is compiled once more after all others are done, with nothing else running;
    only a second failure fails the step;
  * a failure prints the compiler's real errors first (error / fatal / out of memory / LLVM ERROR /
    Access is denied / Permission denied lines with context), then its last lines, and the whole
    output goes to <obj>/<file>.log (the launcher's problem report takes the newest of these);
  * the lifted PPU code compiles with -Wno-unused-value -Wno-parentheses-equality: the lifter's
    _mul128 helper and its `if ((--ctx->ctr == 0))` loops filled every log with warnings. Warning
    options change no generated code (checked: same .obj bytes with and without them).
Test hooks (environment): T5DR_COMPILE_TEST_FREE_MB = the free memory auto_jobs sees,
T5DR_COMPILE_TEST_FAIL_ONCE = source file names whose first compile gets a real compiler error,
T5DR_COMPILE_TIMEOUT_S = the per-file time limit, T5DR_COMPILE_TEST_TOOL = a Python script that plays
clang-cl and lld-link (tests/test_compile_robust.py).
"""
import argparse
import glob
import os
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GDIR = os.path.join(ROOT, "tools", "gamedll")
NO_WINDOW = 0x08000000 if os.name == "nt" else 0

# Memory of one clang-cl, measured 2026-10-20 on the 15 lifted chunks of NPUB30009 v01.00 (LLVM 23.1.3,
# these flags, -march=x86-64-v3, one compiler at a time in a job object, Windows 11): peak working set
# 0.33-0.58 GB per chunk, commit 0.31-0.56 GB. It grows through the whole compile (~0.35 GB after the first
# 3 s of parsing, the peak in the last seconds of code generation), so compilers started together do not
# peak together and starting them staggered saves nothing: N compilers need at most ~N x 0.58 GB. The plan
# keeps a wide margin over that, and leaves room for Windows and the programs next to the build.
COMPILE_JOB_MB = 1024
COMPILE_RESERVE_MB = 1024
COMPILE_TIMEOUT_S = 1800        # one file; the slowest chunk takes ~1-2 minutes on a slow PC
# The lifted PPU code only: the lifter's 128-bit multiply helper (`_mul128(a, b, &hi);`, the return value
# unused) and its counter loops (`if ((--ctx->ctr == 0))`) warn in every chunk.
PPU_QUIET = ["-Wno-unused-value", "-Wno-parentheses-equality"]
TAIL_LINES = 40                 # of a failed compile's output, after its error lines


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
        r = subprocess.run((list(cl) if isinstance(cl, (list, tuple)) else [cl])
                           + ["/nologo", "/X", f"/clang:-march={cpu}", "/clang:-dM", "/E", "-TC", src],
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


# --------------------------------------------------------------------------- memory and the number of compilers

def free_memory_bytes():
    """Memory the compilers could still use without paging, or None when unknown: the smaller of the free
    physical memory and what the commit limit (RAM + page file) still allows. T5DR_COMPILE_TEST_FREE_MB
    replaces it (tests)."""
    env = os.environ.get("T5DR_COMPILE_TEST_FREE_MB")
    if env:
        try:
            return int(float(env) * (1 << 20))
        except ValueError:
            pass
    if os.name != "nt":
        try:
            return os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
        except (ValueError, OSError, AttributeError):
            return None
    try:
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

        st = MEMORYSTATUSEX()
        st.dwLength = ctypes.sizeof(st)
        if not ctypes.WinDLL("kernel32").GlobalMemoryStatusEx(ctypes.byref(st)):
            return None
        return min(st.ullAvailPhys, st.ullAvailPageFile)
    except (OSError, AttributeError, ValueError):
        return None


def process_peak_bytes(proc):
    """Peak working set of a finished subprocess.Popen (its handle is still open), 0 when unknown."""
    if os.name != "nt":
        return 0
    try:
        import ctypes
        from ctypes import wintypes

        class PMC(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]

        get = ctypes.WinDLL("psapi").GetProcessMemoryInfo
        get.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
        pmc = PMC()
        pmc.cb = ctypes.sizeof(pmc)
        if get(wintypes.HANDLE(int(proc._handle)), ctypes.byref(pmc), pmc.cb):
            return int(pmc.PeakWorkingSetSize)
    except (OSError, AttributeError, ValueError, TypeError):
        pass
    return 0


def gb(n):
    return f"{n / (1 << 30):.1f} GB" if n >= 1 << 30 else f"{n / (1 << 20):.0f} MB"


def auto_jobs(cpus, free_bytes, job_mb=COMPILE_JOB_MB, reserve_mb=COMPILE_RESERVE_MB):
    """The default number of compilers and why, as (jobs, reason): one per processor, and only as many as
    fit in the free memory at ~job_mb each next to reserve_mb for Windows and the other programs."""
    cpus = max(1, int(cpus or 1))
    why = [f"{cpus} processor" + ("s" if cpus != 1 else "")]
    if free_bytes is None:
        why.append("free memory unknown")
        return cpus, ", ".join(why)
    free_mb = max(0, int(free_bytes)) >> 20
    fit = max(0, (free_mb - reserve_mb) // job_mb)
    if fit < cpus:
        why.append(f"only {free_mb / 1024:.1f} GB free memory: room for {fit} compiler(s) of "
                   f"~{job_mb / 1024:.1f} GB next to ~{reserve_mb / 1024:.1f} GB for Windows and other programs")
        return max(1, fit), ", ".join(why)
    why.append(f"{free_mb / 1024:.1f} GB free memory")
    return cpus, ", ".join(why)


# --------------------------------------------------------------------------- a failed compile, explained

# Windows exit codes (NTSTATUS) a compiler that did not end by itself gets.
EXIT_CODES = {
    0xC0000005: "access violation: the compiler crashed",
    0xC0000017: "out of memory",
    0xC000012D: "out of memory: the page file is full (commit limit)",
    0xC00000FD: "stack overflow",
    0xC0000409: "the compiler stopped itself (fail-fast)",
    0xC000001D: "illegal instruction",
    0xC0000135: "a DLL it needs is missing",
    0xC0000142: "it could not start (DLL initialisation failed)",
    0xC000013A: "stopped with Ctrl+C",
    0x40010004: "killed by another program",
}

ERROR_LINE = re.compile(r"\berrors?\b|\bfatal\b|out of memory|LLVM ERROR|Access is denied|Permission denied|"
                        r"PLEASE submit a bug report|Exception Code|failed due to signal|bad_alloc|Allocation failed",
                        re.I)


def exit_text(rc, timed_out=False):
    if timed_out:
        return "stopped after the time limit"
    if rc is None:
        return "could not be started"
    u = rc & 0xFFFFFFFF
    if u >= 0x40000000 or rc < 0:
        return f"exit code 0x{u:08X}" + (f" ({EXIT_CODES[u]})" if u in EXIT_CODES else "")
    return f"exit code {rc}"


def error_excerpt(text, before=2, after=3, tail=TAIL_LINES, max_lines=120):
    """What to print of a failed compile's output: (error_lines, tail_lines). error_lines = every line that
    names an error (ERROR_LINE) with `before`/`after` lines around it, gaps marked "...", at most max_lines;
    tail_lines = the last `tail` lines. Output short enough to show whole comes back as ([], all of it)."""
    lines = text.splitlines()
    if len(lines) <= tail:
        return [], lines
    hits = [i for i, ln in enumerate(lines) if ERROR_LINE.search(ln)]
    out, last = [], -1
    for i in hits:
        lo, hi = max(i - before, last + 1), min(i + after, len(lines) - 1)
        if lo > hi:
            continue
        if out and lo > last + 1:
            out.append("...")
        out.extend(lines[lo:hi + 1])
        last = hi
        if len(out) >= max_lines:
            more = sum(1 for j in hits if j > last)
            out = out[:max_lines]
            if more:
                out.append(f"... ({more} more error lines in the log file)")
            break
    return out, lines[-tail:]


def print_failure(name, res, log_path, attempt=1):
    """The failure of one compile for the build log (and the launcher's log view). Every line is indented:
    the launcher reads "[step]", "[k/n]" and "ERROR:" at the start of a line."""
    errs, tail = error_excerpt(res.output)
    print(f"  {name}" + (" (second try)" if attempt > 1 else "") + f": {exit_text(res.rc, res.timed_out)}, "
          f"after {res.seconds:.1f} s" + (f", peak memory {gb(res.peak)}" if res.peak else "")
          + (f", free memory now {gb(res.free_after)}" if res.free_after is not None else ""), flush=True)
    if errs:
        print("  error lines:", flush=True)
        for ln in errs:
            print("    | " + ln, flush=True)
    if tail:
        print(f"  the last {len(tail)} lines of the output:" if errs or len(tail) >= TAIL_LINES
              else "  the output:", flush=True)
        for ln in tail:
            print("    | " + ln, flush=True)
    elif not errs:
        print("  (no output)", flush=True)
    if log_path:
        print(f"  full output: {log_path}", flush=True)


def write_log(log_path, name, attempt, cmd, res):
    """The full output of a failed compile, one section per attempt (the first attempt starts a new file)."""
    try:
        with open(log_path, "w" if attempt == 1 else "a", encoding="utf-8", errors="replace") as f:
            f.write(f"# {name}, attempt {attempt}" + (" (alone, nothing else compiling)" if attempt > 1 else "")
                    + f", {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"# {exit_text(res.rc, res.timed_out)} after {res.seconds:.1f} s"
                    + (f", peak memory {gb(res.peak)}" if res.peak else "")
                    + (f", free memory after {gb(res.free_after)}" if res.free_after is not None else "") + "\n")
            f.write("# " + subprocess.list2cmdline(cmd) + "\n")
            f.write(res.output if res.output.endswith("\n") or not res.output else res.output + "\n")
        return log_path
    except OSError as e:
        print(f"  (could not write {log_path}: {e})", flush=True)
        return None


# --------------------------------------------------------------------------- running the compilers

class CompileResult:
    def __init__(self, rc, output="", seconds=0.0, peak=0, timed_out=False, free_after=None, skipped=False):
        self.rc, self.output, self.seconds, self.peak = rc, output, seconds, peak
        self.timed_out, self.free_after, self.skipped = timed_out, free_after, skipped

    @property
    def ok(self):
        return self.rc == 0 and not self.timed_out


def compile_timeout():
    try:
        return max(1.0, float(os.environ.get("T5DR_COMPILE_TIMEOUT_S") or COMPILE_TIMEOUT_S))
    except ValueError:
        return COMPILE_TIMEOUT_S


def run_compiler(cmd, env=None, timeout=None):
    """Run one compile and wait for it at most `timeout` seconds (then it is stopped and counts as failed).
    The compiler's stdout and stderr in one stream, in the order it wrote them."""
    timeout = timeout or compile_timeout()
    t = time.time()
    try:
        p = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             stdin=subprocess.DEVNULL, creationflags=NO_WINDOW)
    except OSError as e:      # an antivirus that blocks clang-cl.exe, a deleted toolchain
        return CompileResult(None, f"could not start {cmd[0]}: {e}\n", time.time() - t,
                             free_after=free_memory_bytes())
    timed_out = False
    try:
        raw, _ = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        p.kill()
        try:
            raw, _ = p.communicate(timeout=60)
        except subprocess.TimeoutExpired:
            raw = b""
        raw = (raw or b"") + f"\n[build_game_dll] stopped after {timeout:.0f} s without finishing\n".encode()
    seconds = time.time() - t
    peak = process_peak_bytes(p)
    out = (raw or b"").decode("utf-8", "replace").replace("\r\n", "\n")
    free = free_memory_bytes() if p.returncode or timed_out else None
    return CompileResult(p.returncode, out, seconds, peak, timed_out, free)


def compile_all(todo, jobs, compile_one, name_of=os.path.basename):
    """Compile `todo` on `jobs` threads; compile_one(src, attempt) -> CompileResult. A file that fails is
    compiled once more after all the others have finished, alone. Returns (ok, {src: CompileResult}): ok is
    False as soon as one second attempt fails too (the files after it are not tried again)."""
    def safe(src, attempt):
        try:
            return compile_one(src, attempt)
        except Exception as e:                       # noqa: BLE001 -- one file's problem, not the pool's
            print(f"  {name_of(src)}: {type(e).__name__}: {e}", flush=True)
            return CompileResult(None, f"{type(e).__name__}: {e}\n")
    with ThreadPoolExecutor(max(1, jobs)) as ex:
        first = list(ex.map(lambda s: safe(s, 1), todo))
    results = dict(zip(todo, first))
    failed = [s for s in todo if not results[s].ok]
    if not failed:
        return True, results
    print(("1 file" if len(failed) == 1 else f"{len(failed)} files") + " failed: compiling "
          + ("it" if len(failed) == 1 else "them") + " once more, one at a time with nothing else compiling"
          " (a failure that goes away was a passing problem: too little free memory, an antivirus scan, a file "
          "held by another program)", flush=True)
    for k, src in enumerate(failed, 1):
        print(f"  second try {k}/{len(failed)}: {name_of(src)}", flush=True)
        r = safe(src, 2)
        results[src] = r
        if not r.ok:
            left = len(failed) - k
            print(f"  {name_of(src)} failed again" + (f" ({left} more not tried again)" if left else ""), flush=True)
            return False, results
        print(f"  {name_of(src)}: {r.seconds:.1f} s, compiled on the second try", flush=True)
    return True, results


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--recomp", required=True)
    ap.add_argument("--spu", required=True)
    ap.add_argument("--deps", required=True, help="ps3recomp source (headers, spu_dispatch_mt.c)")
    ap.add_argument("--host-lib", required=True, help="t5dr.lib, the import library of the runtime host")
    ap.add_argument("--out", required=True, help="the DLL to write (next to t5dr.exe)")
    ap.add_argument("--obj", help="object directory (default: <out dir>/gamedll_obj)")
    ap.add_argument("--llvm", help="folder with clang-cl.exe and lld-link.exe")
    ap.add_argument("--jobs", type=int, default=None,
                    help="compilers at once (default: one per processor, as many as fit in the free memory)")
    ap.add_argument("--force", action="store_true", help="recompile objects that look current")
    ap.add_argument("--march", default="auto",
                    help="target CPU of the lifted PPU code: auto (x86-64-v3 when this PC's CPU and Windows "
                         "support it, else none), x86-64-v3, native, none")
    a = ap.parse_args()

    test_tool = os.environ.get("T5DR_COMPILE_TEST_TOOL")    # tests: a Python script plays clang-cl and lld-link
    if test_tool:
        cl = test_tool
        cl_cmd, lld_cmd = [sys.executable, test_tool, "clang-cl"], [sys.executable, test_tool, "lld-link"]
    else:
        llvm = find_llvm(a.llvm)
        cl = os.path.join(llvm, "clang-cl.exe")
        cl_cmd, lld_cmd = [cl], [os.path.join(llvm, "lld-link.exe")]
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
        march, missing = host_cpu_level(cl_cmd, obj)
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

    def obj_name(src):
        return (os.path.basename(os.path.dirname(src)) + "_" + os.path.basename(src) if "lifted" in src
                else os.path.basename(src))

    def command(src, o, attempt):
        cmd = cl_cmd + common
        if src.endswith(".c"):
            cmd += ["/std:c17", "-TC", "/DSPU_USE_DISPATCH_MT", "-msse4.1"]   # as ps3recomp_runtime's INTERFACE option
            cmd += ppu_opts     # same target CPU as the PPU code: the sound core ~7% cheaper with x86-64-v3 (CMakeLists.txt)
            if os.path.basename(os.path.dirname(src)).startswith("skin"):
                cmd += ["/DSPU_FAST_FLOAT"]     # render-only skinning jobs: IEEE float ops (CMakeLists.txt)
            elif os.path.basename(os.path.dirname(src)) == "bnuscore":
                cmd += ["/DSPU_NEAR_FLOAT"]     # the sound core: near-exact IEEE float ops (CMakeLists.txt)
            if "lifted" in src:
                cmd += ["/DSPU_LS_NO_HOOKS"]    # no local-store debug hooks in lifted images (CMakeLists.txt)
        else:
            cmd += ["-std:c++20", "-TP", "/EHs-c-", "/Zc:tlsGuards-"] + ppu_opts + PPU_QUIET
        if os.path.basename(src) == "t5dr_game_dll.c":
            cmd += [f'/DT5DR_GAME_MARCH="{march}"']   # t5dr_game_march: checked by the runtime at load
        if attempt == 1 and os.path.basename(src) in fail_once:     # test hook: a real compiler error, once
            cmd += (["/clang:-Werror=unused-value"] if src.endswith(".cpp")
                    else ["/FI" + os.path.join(obj, "t5dr_test_fail_once_missing.h")])
        return cmd + ["-c", src, "/Fo" + o]

    def current(src, o):
        return (not a.force and stamp_ok and os.path.exists(o)
                and os.path.getmtime(o) > max(os.path.getmtime(src), newest_dep))

    def compile_one(src, attempt):
        name = obj_name(src)
        o = os.path.join(obj, name + ".obj")
        if attempt == 1 and current(src, o):
            return CompileResult(0, skipped=True)
        cmd = command(src, o, attempt)
        res = run_compiler(cmd, env)
        with lock:
            if attempt == 1:
                done[0] += 1
                # "[k/n]" like ninja, so the launcher shows the compile progress
                print(f"[{done[0]}/{len(todo)}] {name}: {res.seconds:.1f} s"
                      + (f", {gb(res.peak)}" if res.peak else "")
                      + ("" if res.ok else f" FAILED ({exit_text(res.rc, res.timed_out)})"), flush=True)
            if not res.ok:
                log = write_log(os.path.join(obj, name + ".log"), name, attempt, cmd, res)
                print_failure(name, res, log, attempt)
        return res

    todo = srcs + c_srcs
    # Every <name>.log in the object folder belongs to this run: the full output of a compile (or the link)
    # that failed.
    link_log = os.path.join(obj, "t5dr_game_link.log")
    for p in [os.path.join(obj, obj_name(s) + ".log") for s in todo] + [link_log]:
        try:
            os.remove(p)
        except OSError:
            pass
    fail_once = {s.strip() for s in os.environ.get("T5DR_COMPILE_TEST_FAIL_ONCE", "").split(",") if s.strip()}

    cpus = os.cpu_count() or 4
    if a.jobs:
        jobs, jobs_why = max(1, a.jobs), f"--jobs {a.jobs}, {cpus} processors"
    else:
        jobs, jobs_why = auto_jobs(cpus, free_memory_bytes())
    t0 = time.time()
    print(f"jobs: {jobs} -- {jobs_why}", flush=True)
    print(f"compiling {len(todo)} files with {cl} ({jobs} jobs)", flush=True)
    if not stamp_ok and os.path.exists(stamp_path):
        os.remove(stamp_path)                  # written again only when every object is built
    # biggest first: the longest chunk bounds the wall time
    todo.sort(key=lambda p: -os.path.getsize(p))
    done, lock = [0], threading.Lock()
    ok, results = compile_all(todo, jobs, compile_one, obj_name)
    if not ok:
        logs = [os.path.join(obj, obj_name(s) + ".log") for s in todo if not results[s].ok]
        print("compile failed. The compiler's full output: " + ", ".join(p for p in logs if os.path.exists(p))
              + " (the launcher's Report a problem button includes these files)", flush=True)
        sys.exit("compile failed")
    with open(stamp_path, "w") as f:
        f.write(march + "\n")
    t1 = time.time()
    ran = [(r.peak, s) for s, r in results.items() if not r.skipped and r.peak]
    if ran:
        peak, src = max(ran)
        print(f"peak memory of one compiler: {gb(peak)} ({obj_name(src)})", flush=True)
    objs = [os.path.join(obj, obj_name(s) + ".obj") for s in todo]

    ucrt = os.path.join(obj, "ucrt_min.lib")
    subprocess.run(lld_cmd + ["/lib", "/nologo", "/machine:x64", "/def:" + os.path.join(GDIR, "ucrt_min.def"),
                    "/out:" + ucrt], check=True, env=env, creationflags=NO_WINDOW)
    link = lld_cmd + ["/nologo", "/DLL", "/NOENTRY", "/NODEFAULTLIB", "/MACHINE:X64", "/OPT:REF", "/OPT:ICF",
            "/OUT:" + a.out, "/IMPLIB:" + os.path.join(obj, "t5dr_game.lib"),
            "/EXPORT:function_table,DATA", "/EXPORT:function_table_count,DATA"]
    link += objs + [os.path.abspath(a.host_lib), ucrt]
    r = run_compiler(link, env)
    if not r.ok:
        log = write_log(link_log, "link", 1, link, r)
        print_failure("t5dr_game.dll (link)", r, log, 1)
        sys.exit("link failed")
    print(f"wrote {a.out} ({os.path.getsize(a.out) / 1e6:.1f} MB): compile {t1 - t0:.1f} s, "
          f"link {time.time() - t1:.1f} s", flush=True)


if __name__ == "__main__":
    main()
