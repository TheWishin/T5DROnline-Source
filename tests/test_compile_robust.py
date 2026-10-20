"""The compile step survives a passing failure and says why a file failed (tools/build_game_dll.py, 1.1.3).

Player report (1.1.2, 12 processors, 9.7 GB free): two lifted chunks FAILED ~5 s after 12 compilers started,
every other file compiled, and build.log showed only the first 3,000 characters of the compiler's output --
warnings, cut off before the error. No game and no compiler needed here:

* jobs: one compiler per processor, only as many as fit in the free memory (auto_jobs, with the per-compiler
  peak measured on the real chunks);
* errors: the error lines first (with a few lines around them), then the last lines; exit codes named;
* retry: a file that fails is compiled again after all others, alone; only a second failure fails the step
  (compile_all with a fake compile function, then build_game_dll.py end to end with a fake compiler script --
  T5DR_COMPILE_TEST_TOOL -- that runs "out of memory" when another compile runs beside it, one that always
  fails and one that hangs);
* what build_game_dll.py prints never looks like a step, an ERROR or progress to the launcher, except "[k/n]".
"""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest

from helpers import PY, ROOT, TOOLS, load_tool

sys.path.insert(0, os.path.join(ROOT, "launcher"))
sys.path.insert(0, os.path.join(ROOT, "lobby"))
import core  # noqa: E402

bd = load_tool("build_game_dll")

GB = 1 << 30
MB = 1 << 20
# The biggest peak working set of one clang-cl on a lifted chunk (ppu_recomp_012.cpp, 2026-10-20: 0.58-0.59 GB;
# the 15 chunks 0.33-0.59 GB, the SPU C files 0.05-0.24 GB).
MEASURED_PEAK_MB = 590


def capture(fn, *a, **kw):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        r = fn(*a, **kw)
    return r, buf.getvalue()


class Jobs(unittest.TestCase):
    def test_the_players_pc(self):
        # 12 processors, 9.7 GB free: 12 compilers at ~0.6 GB fit, but not with the margin -> 8
        jobs, why = bd.auto_jobs(12, int(9.7 * GB))
        self.assertEqual(jobs, 8)
        self.assertEqual(why, "12 processors, only 9.7 GB free memory: room for 8 compiler(s) of ~1.0 GB next to "
                              "~1.0 GB for Windows and other programs")

    def test_enough_memory_one_per_processor(self):
        self.assertEqual(bd.auto_jobs(12, 32 * GB), (12, "12 processors, 32.0 GB free memory"))
        self.assertEqual(bd.auto_jobs(1, 32 * GB), (1, "1 processor, 32.0 GB free memory"))

    def test_little_memory_still_one(self):
        for free in (0, 512 * MB, int(1.5 * GB), 2 * GB - 1):
            jobs, why = bd.auto_jobs(8, free)
            self.assertEqual(jobs, 1, free)
            self.assertIn("room for 0 compiler(s)", why)

    def test_unknown_memory_or_processors(self):
        self.assertEqual(bd.auto_jobs(6, None), (6, "6 processors, free memory unknown"))
        self.assertEqual(bd.auto_jobs(None, None)[0], 1)
        self.assertEqual(bd.auto_jobs(0, 8 * GB)[0], 1)

    def test_never_more_than_fits_or_than_processors(self):
        for cpus in (1, 2, 4, 6, 8, 12, 16, 24, 32, 64):
            for free_mb in range(0, 64 * 1024, 256):
                jobs, _ = bd.auto_jobs(cpus, free_mb * MB)
                self.assertTrue(1 <= jobs <= cpus, (cpus, free_mb, jobs))
                if jobs > 1:
                    self.assertLessEqual(jobs * bd.COMPILE_JOB_MB + bd.COMPILE_RESERVE_MB, free_mb, (cpus, free_mb))

    def test_budget_has_a_margin_over_the_measured_peak(self):
        self.assertGreaterEqual(bd.COMPILE_JOB_MB, 1.5 * MEASURED_PEAK_MB)
        self.assertGreaterEqual(bd.COMPILE_RESERVE_MB, 512)

    def test_free_memory(self):
        os.environ["T5DR_COMPILE_TEST_FREE_MB"] = "3000"
        try:
            self.assertEqual(bd.free_memory_bytes(), 3000 * MB)
        finally:
            del os.environ["T5DR_COMPILE_TEST_FREE_MB"]
        real = bd.free_memory_bytes()
        if os.name == "nt":
            self.assertIsNotNone(real)
            self.assertGreater(real, 64 * MB)

    def test_peak_memory_of_a_finished_process(self):
        p = subprocess.Popen([PY, "-c", "x = bytearray(64 << 20)"], stdout=subprocess.DEVNULL)
        p.wait(timeout=60)
        peak = bd.process_peak_bytes(p)
        if os.name == "nt":
            self.assertGreaterEqual(peak, 64 * MB)
        else:
            self.assertEqual(peak, 0)


def warning_flood(src="ppu_recomp_007.cpp", loops=300):
    """What clang-cl printed for a lifted chunk before 1.1.3 (the player's log)."""
    out = [f"{src}(192,5): warning: ignoring return value of function declared with const attribute "
           "[-Wunused-value]", "  192 |     _mul128(a, b, &hi);", "      |     ^~~~~~~~~~~~~~~~~~"]
    for i in range(loops):
        ln = 16460 + i * 37
        out += [f"{src}({ln},25): warning: equality comparison with extraneous parentheses [-Wparentheses-equality]",
                f" {ln} |         if ((--ctx->ctr == 0)) goto loc_001F{i:04X};",
                "       |              ~~~~~~~~~~~^~~~",
                f"{src}({ln},25): note: remove extraneous parentheses around the comparison to silence this warning",
                f" {ln} |         if ((--ctx->ctr == 0)) goto loc_001F{i:04X};",
                "       |             ~           ^   ~",
                f"{src}({ln},25): note: use '=' to turn this equality comparison into an assignment",
                f" {ln} |         if ((--ctx->ctr == 0)) goto loc_001F{i:04X};",
                "       |                         ^~",
                "       |                         ="]
    return out


CRASH = ["LLVM ERROR: out of memory", "Allocation failed",
         "PLEASE submit a bug report to https://github.com/llvm/llvm-project/issues/ and include the crash backtrace.",
         "Stack dump:", "0.\tProgram arguments: clang-cl.exe -c ppu_recomp_007.cpp",
         "1.\t<eof> parser at end of file", "Exception Code: 0xE0000046",
         "clang-cl: error: clang frontend command failed due to signal (use -v to see invocation)"]


class Errors(unittest.TestCase):
    def test_the_error_after_3000_characters_of_warnings_comes_first(self):
        text = "\n".join(warning_flood() + CRASH) + "\n"
        self.assertGreater(text.index("LLVM ERROR"), 3000 * 30)
        errs, tail = bd.error_excerpt(text)
        self.assertIn("LLVM ERROR: out of memory", errs)
        self.assertIn("Exception Code: 0xE0000046", errs)
        self.assertNotIn("warning", "\n".join(errs[:2]))     # context only: the two lines before the first error
        self.assertEqual(tail, text.splitlines()[-bd.TAIL_LINES:])
        self.assertEqual(len(tail), 40)

    def test_each_kind_of_error_line(self):
        for line in ("ppu_recomp_002.cpp(9,1): error: unknown type name 'x'",
                     "fatal error: 'ppu_recomp.h' file not found",
                     "LLVM ERROR: out of memory",
                     "clang-cl: error: unable to open output file 'a.obj': 'Access is denied'",
                     "error: unable to rename temporary 'a.obj-1f2e.tmp' to output file 'a.obj': 'Permission denied'",
                     "Access is denied.",
                     "could not allocate: out of memory",
                     "2 errors generated."):
            lines = warning_flood(loops=10)
            text = "\n".join(lines[:50] + [line] + lines[50:])
            errs, _ = bd.error_excerpt(text)
            self.assertIn(line, errs, line)

    def test_warnings_alone_are_no_error_lines(self):
        text = "\n".join(warning_flood(loops=20))
        errs, tail = bd.error_excerpt(text)
        self.assertEqual(errs, [])
        self.assertEqual(len(tail), 40)

    def test_context_and_gaps(self):
        lines = [f"line {i}" for i in range(200)]
        lines[50] = "a.cpp(50,1): error: one"
        lines[120] = "a.cpp(120,1): error: two"
        errs, _ = bd.error_excerpt("\n".join(lines))
        self.assertEqual(errs, lines[48:54] + ["..."] + lines[118:124])

    def test_neighbouring_errors_do_not_repeat_lines(self):
        lines = [f"line {i}" for i in range(100)]
        lines[50] = lines[51] = lines[53] = "error: x"
        errs, _ = bd.error_excerpt("\n".join(lines))
        self.assertEqual(errs, lines[48:57])

    def test_many_errors_are_capped(self):
        text = "\n".join(f"a.cpp({i},1): error: e{i}" for i in range(1000))
        errs, tail = bd.error_excerpt(text, max_lines=60)
        self.assertEqual(len(errs), 61)
        self.assertRegex(errs[-1], r"^\.\.\. \(\d+ more error lines in the log file\)$")
        self.assertEqual(tail[-1], "a.cpp(999,1): error: e999")

    def test_short_output_is_shown_whole(self):
        text = "a.cpp(1,1): error: x\n1 error generated.\n"
        self.assertEqual(bd.error_excerpt(text), ([], ["a.cpp(1,1): error: x", "1 error generated."]))
        self.assertEqual(bd.error_excerpt(""), ([], []))

    def test_exit_codes(self):
        self.assertEqual(bd.exit_text(1), "exit code 1")
        self.assertEqual(bd.exit_text(0xC0000005), "exit code 0xC0000005 (access violation: the compiler crashed)")
        self.assertIn("out of memory", bd.exit_text(0xC0000017))
        self.assertIn("page file", bd.exit_text(0xC000012D))
        self.assertEqual(bd.exit_text(-1073741819), "exit code 0xC0000005 (access violation: the compiler crashed)")
        self.assertEqual(bd.exit_text(0xC0001234), "exit code 0xC0001234")
        self.assertEqual(bd.exit_text(1, timed_out=True), "stopped after the time limit")
        self.assertEqual(bd.exit_text(None), "could not be started")

    def test_printed_failure_is_safe_for_the_launcher(self):
        res = bd.CompileResult(1, "\n".join(warning_flood() + CRASH + ["[compile]", "ERROR: x", "[3/9] y"]) + "\n",
                               4.8, 300 * MB, free_after=2 * GB)
        _, out = capture(bd.print_failure, "ppu_recomp_007.cpp", res, r"D:\T5DR\native\build\gamedll_obj\x.log")
        lines = out.splitlines()
        self.assertTrue(lines[0].startswith("  ppu_recomp_007.cpp: exit code 1, after 4.8 s, peak memory 300 MB, "
                                            "free memory now 2.0 GB"), lines[0])
        self.assertLess(out.index("LLVM ERROR: out of memory"), out.index("the last 40 lines"))
        self.assertIn(r"  full output: D:\T5DR\native\build\gamedll_obj\x.log", lines)
        step = "compile"
        for ln in lines:
            self.assertTrue(ln.startswith("  "), ln)
            step, events = core.build_line_events(step, ln)
            self.assertEqual([e[0] for e in events], ["line"], ln)

    def test_log_file_keeps_both_attempts(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "a.cpp.log")
            first = bd.CompileResult(1, "x\nLLVM ERROR: out of memory\n", 5.0, 400 * MB, free_after=GB)
            second = bd.CompileResult(1, "a.cpp(1,1): error: y", 20.0, 500 * MB)
            self.assertEqual(bd.write_log(p, "a.cpp", 1, ["clang-cl.exe", "-c", "a b.cpp"], first), p)
            bd.write_log(p, "a.cpp", 2, ["clang-cl.exe", "-c", "a b.cpp"], second)
            with open(p, encoding="utf-8") as f:
                text = f.read()
            self.assertIn("# a.cpp, attempt 1,", text)
            self.assertIn("# a.cpp, attempt 2 (alone, nothing else compiling),", text)
            self.assertIn("# exit code 1 after 5.0 s, peak memory 400 MB, free memory after 1.0 GB", text)
            self.assertIn('# clang-cl.exe -c "a b.cpp"', text)
            self.assertLess(text.index("LLVM ERROR"), text.index("error: y"))
            self.assertTrue(text.endswith("error: y\n"))
            bd.write_log(p, "a.cpp", 1, ["c"], first)                   # a new run starts the file again
            with open(p, encoding="utf-8") as f:
                self.assertNotIn("attempt 2", f.read())

    def test_ppu_warnings_off(self):
        self.assertEqual(bd.PPU_QUIET, ["-Wno-unused-value", "-Wno-parentheses-equality"])


class Retry(unittest.TestCase):
    """compile_all with a fake compile function that knows how many compiles run beside it."""

    def run_all(self, todo, jobs, fails, hold=0.15):
        lock = threading.Lock()
        running = [0]
        calls = []

        def one(src, attempt):
            with lock:
                running[0] += 1
                crowd = running[0] - 1
                t0 = time.monotonic()
            time.sleep(hold)
            with lock:
                crowd = max(crowd, running[0] - 1)
                running[0] -= 1
                calls.append(dict(src=src, attempt=attempt, crowd=crowd, start=t0, end=time.monotonic()))
            f = fails(src, attempt, crowd)
            if isinstance(f, Exception):
                raise f
            return bd.CompileResult(1 if f else 0, "out", hold)
        (ok, res), out = capture(bd.compile_all, todo, jobs, one)
        return ok, res, calls, out

    def test_a_passing_failure_is_compiled_again_alone(self):
        todo = ["a", "b", "c", "d", "e", "f"]
        ok, res, calls, out = self.run_all(todo, 4, lambda s, att, crowd: s in ("a", "b") and crowd > 0)
        self.assertTrue(ok, out)
        self.assertTrue(all(r.ok for r in res.values()))
        first_end = max(c["end"] for c in calls if c["attempt"] == 1)
        again = [c for c in calls if c["attempt"] == 2]
        self.assertEqual([c["src"] for c in again], ["a", "b"])
        for c in again:
            self.assertEqual(c["crowd"], 0)                       # nothing else compiling
            self.assertGreaterEqual(c["start"], first_end)        # after every first attempt
        self.assertEqual(sorted(c["src"] for c in calls if c["attempt"] == 1), todo)
        self.assertIn("2 files failed: compiling them once more, one at a time with nothing else compiling", out)
        self.assertIn("  second try 1/2: a", out)
        self.assertRegex(out, r"(?m)^  b: [\d.]+ s, compiled on the second try$")

    def test_a_second_failure_fails_and_stops(self):
        ok, res, calls, out = self.run_all(["a", "b", "c"], 3, lambda s, att, crowd: s in ("a", "b"))
        self.assertFalse(ok)
        self.assertEqual([(c["src"], c["attempt"]) for c in calls if c["attempt"] == 2], [("a", 2)])
        self.assertFalse(res["a"].ok)
        self.assertFalse(res["b"].ok)
        self.assertTrue(res["c"].ok)
        self.assertIn("  a failed again (1 more not tried again)", out)

    def test_an_exception_counts_as_a_failure(self):
        ok, res, calls, out = self.run_all(["a", "b"], 2,
                                           lambda s, att, crowd: OSError("Access is denied") if s == "a" and att == 1
                                           else False)
        self.assertTrue(ok)
        self.assertIn("  a: OSError: Access is denied", out)
        self.assertIn("1 file failed: compiling it once more", out)

    def test_nothing_failed_nothing_said(self):
        ok, res, calls, out = self.run_all(["a", "b", "c"], 2, lambda *_: False, hold=0.01)
        self.assertTrue(ok)
        self.assertEqual(out, "")
        self.assertEqual(len(calls), 3)


# A stand-in for clang-cl and lld-link: build_game_dll.py runs it through T5DR_COMPILE_TEST_TOOL.
FAKE_TOOL = r'''
import json, os, sys, time
role, args = sys.argv[1], sys.argv[2:]
d = os.environ["FAKE_CC_DIR"]
def names(var):
    return {s for s in os.environ.get(var, "").split(",") if s}
def note(**kw):
    # one file per record: several of these run at once, and appends from several processes to one file can land
    # on the same bytes on Windows (review-113: a JSONDecodeError in calls(), now and then)
    calls = os.path.join(d, "calls")
    os.makedirs(calls, exist_ok=True)
    tmp = os.path.join(calls, "%d-%d.tmp" % (time.time_ns(), os.getpid()))
    with open(tmp, "w") as f:
        f.write(json.dumps(kw))
    os.replace(tmp, tmp[:-4] + ".json")
if role == "lld-link":
    for a in args:
        if a.lower().startswith("/out:"):
            with open(a[5:], "wb") as f:
                f.write(b"MZ fake")
    note(role=role, args=args)
    sys.exit(0)
src = args[args.index("-c") + 1]
out = next(a[3:] for a in args if a.startswith("/Fo"))
name = os.path.basename(src)
run_dir = os.path.join(d, "running")
os.makedirs(run_dir, exist_ok=True)
me = os.path.join(run_dir, str(os.getpid()))
open(me, "w").close()
t0 = time.time()
crowd, rc = 0, 0
try:
    end = t0 + float(os.environ.get("FAKE_CC_SECONDS", "0.8"))
    while time.time() < end:                       # how many compiles run beside this one
        crowd = max(crowd, len(os.listdir(run_dir)) - 1)
        time.sleep(0.02)
    if name in names("FAKE_CC_HANG_ONCE") and not os.path.exists(os.path.join(d, "hung-" + name)):
        open(os.path.join(d, "hung-" + name), "w").close()
        note(role=role, name=name, hang=True, start=t0)
        time.sleep(600)
    if "-Wno-unused-value" not in args:
        print(f"{src}(192,5): warning: ignoring return value of function declared with const attribute [-Wunused-value]")
    if name in names("FAKE_CC_CROWD_FAIL") and crowd:
        for i in range(200):
            print(f"{src}({1000 + i},25): warning: equality comparison with extraneous parentheses [-Wparentheses-equality]")
        sys.stdout.flush()
        sys.stderr.write("LLVM ERROR: out of memory\nAllocation failed\n")
        rc = 1
    elif "/clang:-Werror=unused-value" in args:        # build_game_dll's T5DR_COMPILE_TEST_FAIL_ONCE
        print(f"{src}(192,5): error: ignoring return value of function declared with const attribute [-Werror,-Wunused-value]")
        print("1 error generated.")
        rc = 1
    elif name in names("FAKE_CC_ALWAYS_FAIL"):
        print(f"{src}(7,1): error: unknown type name 'broken'")
        print("1 error generated.")
        rc = 1
    else:
        with open(out, "wb") as f:
            f.write(b"fake object of " + name.encode())
finally:
    os.remove(me)
note(role=role, name=name, crowd=crowd, rc=rc, start=t0, end=time.time(), args=args)
sys.exit(rc)
'''


class EndToEnd(unittest.TestCase):
    """build_game_dll.py itself, with the fake compiler: no clang, no lifted code."""

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, self.d, True)
        d = self.d
        self.tool = os.path.join(d, "fake_cc.py")
        with open(self.tool, "w") as f:
            f.write(FAKE_TOOL)
        self.recomp = os.path.join(d, "recomp")
        os.makedirs(self.recomp)
        for i in range(4):          # biggest first: 000 starts first
            with open(os.path.join(self.recomp, f"ppu_recomp_{i:03d}.cpp"), "w") as f:
                f.write("// fake\n" * (400 - 50 * i))
        open(os.path.join(self.recomp, "ppu_recomp.h"), "w").close()
        self.spu = os.path.join(d, "spu")
        os.makedirs(os.path.join(self.spu, "lifted", "bnuscore"))
        open(os.path.join(self.spu, "lifted", "bnuscore", "spu_recomp.c"), "w").close()
        open(os.path.join(self.spu, "spu_workloads.c"), "w").close()
        self.deps = os.path.join(d, "deps")
        for sub in ("runtime/ppu", "runtime/spu", "include"):
            os.makedirs(os.path.join(self.deps, sub))
        open(os.path.join(self.deps, "runtime", "spu", "spu_dispatch_mt.c"), "w").close()
        self.host = os.path.join(d, "t5dr.lib")
        open(self.host, "w").close()
        self.obj = os.path.join(d, "obj")
        self.out = os.path.join(d, "out", "t5dr_game.dll")
        os.makedirs(os.path.dirname(self.out))

    def run_tool(self, extra=(), **env):
        e = dict(os.environ, T5DR_COMPILE_TEST_TOOL=self.tool, FAKE_CC_DIR=self.d, PYTHONIOENCODING="utf-8")
        e.pop("T5DR_COMPILE_TEST_FREE_MB", None)
        e.update({k: str(v) for k, v in env.items()})
        r = subprocess.run([PY, os.path.join(TOOLS, "build_game_dll.py"), "--recomp", self.recomp, "--spu", self.spu,
                            "--deps", self.deps, "--host-lib", self.host, "--out", self.out, "--obj", self.obj,
                            "--march", "none"] + list(extra),
                           capture_output=True, text=True, encoding="utf-8", errors="replace", env=e, timeout=300)
        return r.returncode, r.stdout, r.stderr

    def calls(self):
        """The fake tools' records in the order they were written (one file each, named by the time)."""
        p = os.path.join(self.d, "calls")
        if not os.path.isdir(p):
            return []
        out = []
        for n in sorted((n for n in os.listdir(p) if n.endswith(".json")),
                        key=lambda n: tuple(int(x) for x in n[:-5].split("-"))):
            with open(os.path.join(p, n)) as f:
                out.append(json.loads(f.read()))
        return out

    def assert_launcher_safe(self, out):
        """The launcher reads "[step]", "[k/n]", "ERROR:" and "already done" at the start of build lines."""
        step, fracs = "compile", []
        for ln in out.splitlines():
            step, events = core.build_line_events(step, ln)
            kinds = [e[0] for e in events]
            self.assertIn(kinds, (["line"], ["line", "sub"]), ln)
            fracs += [e[1] for e in events if e[0] == "sub"]
        self.assertEqual(fracs, sorted(fracs))
        self.assertTrue(fracs and fracs[-1] == 1.0, fracs)

    def test_a_chunk_that_runs_out_of_memory_beside_others_compiles_alone(self):
        rc, out, err = self.run_tool(["--jobs", "4"], FAKE_CC_CROWD_FAIL="ppu_recomp_000.cpp")
        self.assertEqual(rc, 0, out + err)
        self.assertIn("jobs: 4 -- --jobs 4, ", out)
        self.assertIn("compiling 8 files with", out)
        self.assertRegex(out, r"(?m)^\[\d/8\] ppu_recomp_000\.cpp: [\d.]+ s(, \d+ MB)? FAILED \(exit code 1\)$")
        self.assertLess(out.index("  error lines:"), out.index("    | LLVM ERROR: out of memory"))
        self.assertIn("1 file failed: compiling it once more, one at a time with nothing else compiling", out)
        self.assertRegex(out, r"(?m)^  ppu_recomp_000\.cpp: [\d.]+ s, compiled on the second try$")
        self.assertRegex(out, r"(?m)^wrote .*t5dr_game\.dll")
        self.assert_launcher_safe(out)
        log = os.path.join(self.obj, "ppu_recomp_000.cpp.log")
        self.assertIn("  full output: " + log, out)
        with open(log, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("# ppu_recomp_000.cpp, attempt 1,", text)
        self.assertIn("LLVM ERROR: out of memory", text)
        self.assertEqual(text.count("[-Wparentheses-equality]"), 200)         # the whole output, not 3,000 chars
        calls = [c for c in self.calls() if c.get("role") == "clang-cl"]
        mine = [c for c in calls if c["name"] == "ppu_recomp_000.cpp"]
        self.assertEqual([c["rc"] for c in mine], [1, 0])
        self.assertGreater(mine[0]["crowd"], 0)
        self.assertEqual(mine[1]["crowd"], 0)
        self.assertGreaterEqual(mine[1]["start"], max(c["end"] for c in calls if c is not mine[1]) - 0.05)
        for c in calls:          # the lifted PPU code without its two warnings, the C files as before
            quiet = "-Wno-unused-value" in c["args"] and "-Wno-parentheses-equality" in c["args"]
            self.assertEqual(quiet, c["name"].endswith(".cpp"), c["name"])
        self.assertTrue(os.path.exists(os.path.join(self.obj, "march.txt")))

        # the next build: everything current, the old log removed
        rc, out, err = self.run_tool(["--jobs", "4"])
        self.assertEqual(rc, 0, out + err)
        self.assertFalse(os.path.exists(log))
        self.assertNotRegex(out, r"(?m)^\[\d+/8\]")

    def test_a_file_that_fails_twice_fails_the_step(self):
        rc, out, err = self.run_tool(["--jobs", "3"], FAKE_CC_ALWAYS_FAIL="ppu_recomp_001.cpp,ppu_recomp_002.cpp")
        self.assertNotEqual(rc, 0)
        self.assertIn("compile failed", err)
        self.assertIn("2 files failed: compiling them once more", out)
        self.assertIn("  ppu_recomp_001.cpp failed again (1 more not tried again)", out)
        self.assertIn("  ppu_recomp_001.cpp (second try): exit code 1", out)
        log1 = os.path.join(self.obj, "ppu_recomp_001.cpp.log")
        log2 = os.path.join(self.obj, "ppu_recomp_002.cpp.log")
        self.assertIn(f"compile failed. The compiler's full output: {log1}, {log2}", out)
        with open(log1, encoding="utf-8") as f:
            text = f.read()
        self.assertEqual(text.count("error: unknown type name 'broken'"), 2)
        self.assertIn("attempt 2 (alone, nothing else compiling)", text)
        self.assertFalse(os.path.exists(self.out))
        self.assertFalse(os.path.exists(os.path.join(self.obj, "march.txt")))
        self.assert_launcher_safe(out)

    def test_a_compile_that_hangs_is_stopped_and_compiled_again(self):
        rc, out, err = self.run_tool(["--jobs", "2"], FAKE_CC_HANG_ONCE="ppu_recomp_003.cpp",
                                     T5DR_COMPILE_TIMEOUT_S=4)
        self.assertEqual(rc, 0, out + err)
        self.assertIn("ppu_recomp_003.cpp: stopped after the time limit", out)
        self.assertIn("stopped after 4 s without finishing", out)
        self.assertRegex(out, r"(?m)^  ppu_recomp_003\.cpp: [\d.]+ s, compiled on the second try$")

    def test_default_jobs_fit_the_free_memory(self):
        rc, out, err = self.run_tool(T5DR_COMPILE_TEST_FREE_MB=2600)
        self.assertEqual(rc, 0, out + err)
        cpus = os.cpu_count() or 4
        self.assertRegex(out, r"(?m)^jobs: 1 -- \d+ processors?, " +
                         ("only 2.5 GB free memory: room for 1 compiler\\(s\\) of ~1.0 GB next to ~1.0 GB for "
                          "Windows and other programs$" if cpus > 1 else "2.5 GB free memory$"))
        self.assertIn("compiling 8 files with", out)
        self.assertNotIn("FAILED", out)
        rc, out, err = self.run_tool(["--force"], T5DR_COMPILE_TEST_FREE_MB=64 * 1024)
        self.assertRegex(out, rf"(?m)^jobs: {cpus} -- {cpus} processors?, 64.0 GB free memory$")

    def test_fail_once_hook_gives_a_real_compiler_error_once(self):
        # the hook main() uses for a demonstration with the real compiler: the first compile of a named file
        # gets -Werror=unused-value (C++) / a missing forced include (C)
        rc, out, err = self.run_tool(["--jobs", "2"], T5DR_COMPILE_TEST_FAIL_ONCE="ppu_recomp_002.cpp")
        self.assertEqual(rc, 0, out + err)
        calls = [c for c in self.calls() if c.get("name") == "ppu_recomp_002.cpp"]
        self.assertEqual(["/clang:-Werror=unused-value" in c["args"] for c in calls], [True, False])


if __name__ == "__main__":
    unittest.main()
