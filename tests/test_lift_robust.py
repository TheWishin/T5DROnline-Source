"""The translation step never hangs silently (ps3recomp patch 0048, docs/TROUBLESHOOTING.md "The build stops at
Translate code"). No game needed.

* Launcher: the Build tab's hint once the lift step has printed nothing for LIFT_QUIET_S (English and German,
  once per quiet stretch into the log view and build.log), and the lifter's new lines never move the percentage.
* Lifter (a ps3recomp tree with patch 0048: PS3RECOMP_DIR, else deps/ps3recomp): the default worker count from
  processors and free memory, the watchdog's limit, and a synthetic lift (400 two-instruction functions, no game
  data) with a worker that dies and one that hangs -- the output is byte for byte the serial lift's.
"""
import hashlib
import importlib.util
import io
import os
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for sub in ("tools", "lobby", "launcher"):
    p = os.path.join(ROOT, sub)
    if p not in sys.path:
        sys.path.insert(0, p)

import core  # noqa: E402
from t5lobby import i18n  # noqa: E402

GB = 1 << 30
MB = 1 << 20

# Lines the patched lifter prints (taken from real lifts of the game, 2026-10-19).
LIFTER_LINES = [
    "Lifting 22550 functions...",
    "  jobs: 8 -- 32 processors, at most 8 by default, 12.6 GB free memory",
    "  jobs: 3 -- 8 processors, only 1.4 GB free memory: room for 3 worker(s) of ~128 MB next to ~1024 MB for "
    "the lifter itself",
    "  parallel lift: 8 workers, 65 chunks of ~352",
    "  ... lifted 352/22550 functions (1%) elapsed 0.0m eta 1.0m",
    "  ... lifted 21846/22550 functions (96%) elapsed 0.1m eta 0.0m",
    "  ... still lifting: 1 chunks left, elapsed 0.6m",
    "  ... still lifting: 1 chunks left, elapsed 1.1m, none finished for 1.0m (the rest is lifted in this process "
    "after 2.0m)",
    "  parallel lift: worker process 2 stopped (exit code 1) while it lifted chunk 12; an antivirus or too little "
    "free memory can do that. The chunks still missing are lifted in this process instead (same result).",
    "  parallel lift: no chunk finished for 2.0 minutes (1 worker(s) still busy). The chunks still missing are "
    "lifted in this process instead (same result).",
    "  parallel lift: worker process 3 did not exit, stopping it",
    "  ... lifted 22550/22550 functions (100%) elapsed 0.4m eta 0.0m",
    "  parallel lift: 65 chunks in 125.5 s, 1 of them in this process; peak memory per worker 42 MB",
    "  Generated 509 mid-function tail-entry wrappers total",
    "  ... emitting 0/23059 functions",
    "  ... emitting 20000/23059 functions",
    "  23059 functions lifted",
    "  peak memory of the lifter process: 584 MB",
]


def subs(lines, step="lift"):
    """The percentages the Build tab takes from these lines, as (line, fraction or None)."""
    out = []
    for line in lines:
        step, events = core.build_line_events(step, line)
        fr = [v for k, v in events if k == "sub"]
        out.append((line, fr[0] if fr else None))
    return out


class LauncherPercent(unittest.TestCase):
    def test_only_progress_lines_move_the_percentage(self):
        got = dict(subs(LIFTER_LINES))
        for line, fr in got.items():
            progress = ("... lifted " in line or "... emitting " in line)
            self.assertEqual(fr is not None, progress, line)
        self.assertAlmostEqual(got["  ... lifted 21846/22550 functions (96%) elapsed 0.1m eta 0.0m"],
                               0.7 * 21846 / 22550)
        self.assertAlmostEqual(got["  ... emitting 0/23059 functions"], 0.7)
        # in order the percentage never goes back
        seq = [fr for _line, fr in subs(LIFTER_LINES) if fr is not None]
        self.assertEqual(seq, sorted(seq))

    def test_heartbeat_template(self):
        lifter = load_lifter()
        if lifter is None:
            self.skipTest("no ps3recomp tree with patch 0048 (PS3RECOMP_DIR)")
        for left in (1, 7, 65, 1234):
            line = lifter.LIFT_HEARTBEAT.format(left=left, minutes=12.5)
            self.assertIsNone(core.RE_FUNCS.search(line), line)
            self.assertIsNone(core.RE_STEP.match(line), line)

    def test_other_lines_keep_their_meaning(self):
        step, ev = core.build_line_events(None, "[lift]")
        self.assertEqual((step, ev[-1]), ("lift", ("step", "lift")))
        self.assertEqual(core.build_line_events("lift", "  already done")[1][-1], ("skip", "lift"))
        self.assertEqual(core.build_line_events("lift", "ERROR: step 'lift' failed")[1][-1],
                         ("error", "step 'lift' failed"))
        self.assertEqual(core.build_line_events("compile", "[3/12] Building CXX")[1][-1], ("sub", 0.25))
        self.assertEqual(core.build_line_events("spu", "  ... lifted 3/4 functions")[1], [
            ("line", "  ... lifted 3/4 functions")])            # only the lift step reads lifter progress


class QuietHint(unittest.TestCase):
    def tearDown(self):
        i18n.set_language("en")

    def test_threshold_and_step(self):
        self.assertEqual(core.LIFT_QUIET_S, 180)
        self.assertIsNone(core.lift_quiet_hint("lift", 179.9))
        self.assertIsNone(core.lift_quiet_hint("compile", 900))
        self.assertIsNone(core.lift_quiet_hint(None, 900))
        h = core.lift_quiet_hint("lift", 180)
        self.assertIn("printed nothing for 3 minutes", h)
        self.assertIn("translation step", h)
        self.assertIn("10 minutes", core.lift_quiet_hint("lift", 659))

    def test_german(self):
        i18n.set_language("de")
        i18n.clear_missing()
        h = core.lift_quiet_hint("lift", 245)
        self.assertEqual(i18n.missing(), [])
        self.assertIn("seit 4 Minuten nichts ausgegeben", h)
        self.assertIn("Code übersetzen", h)

    def test_build_run_notes_it_once_per_quiet_stretch(self):
        with tempfile.TemporaryDirectory() as d:
            b = core.BuildRun(None, None, d)
            log = io.StringIO()
            b._log = log
            b.step, b.last_output = "lift", 1000.0
            self.assertIsNone(b.quiet_hint(now=1100.0))
            h = b.quiet_hint(now=1185.0)
            self.assertIn("3 minutes", h)
            self.assertIn("4 minutes", b.quiet_hint(now=1245.0))     # the detail line keeps counting ...
            lines = drain(b)
            self.assertEqual(lines, [("line", "[launcher] " + h)])  # ... the log view gets it once
            self.assertEqual(log.getvalue(), "[launcher] " + h + "\n")
            # output again: no hint; a new quiet stretch is noted again
            b.last_output, b._quiet_noted = 1300.0, False
            self.assertIsNone(b.quiet_hint(now=1301.0))
            self.assertIsNotNone(b.quiet_hint(now=1490.0))
            self.assertEqual(len(drain(b)), 1)
            b.step = "compile"
            self.assertIsNone(b.quiet_hint(now=5000.0))

    def test_pump_resets_the_quiet_clock(self):
        with tempfile.TemporaryDirectory() as d:
            b = core.BuildRun(None, None, d)
            b.proc = FakeProc(["[lift]"] + LIFTER_LINES)
            b.last_output = 0.0
            b._quiet_noted = True
            b._pump()
            self.assertEqual(b.step, "lift")
            self.assertGreater(b.last_output, 0.0)
            self.assertFalse(b._quiet_noted)
            ev = drain(b)
            self.assertEqual(ev[-1], ("end", 0))
            fracs = [v for k, v in ev if k == "sub"]
            self.assertEqual(len(fracs), 5)
            self.assertEqual(fracs, sorted(fracs))
            with open(b.log_path, encoding="utf-8") as f:
                text = f.read()
            self.assertIn("still lifting: 1 chunks left", text)
            self.assertTrue(text.rstrip().endswith("# exit code 0"))


class FakeProc:
    pid = 0

    def __init__(self, lines):
        self.stdout = io.BytesIO("".join(ln + "\n" for ln in lines).encode("utf-8"))

    def wait(self, timeout=None):
        return 0

    def poll(self):
        return 0


def drain(b):
    out = []
    while not b.events.empty():
        out.append(b.events.get_nowait())
    return out


# --------------------------------------------------------------------------- the lifter

def find_ps3recomp():
    cands = [os.environ.get("PS3RECOMP_DIR"), os.path.join(ROOT, "deps", "ps3recomp")]
    try:
        r = subprocess.run(["git", "-C", ROOT, "rev-parse", "--git-common-dir"], capture_output=True, text=True,
                           timeout=20)
        if r.returncode == 0:
            common = os.path.normpath(os.path.join(ROOT, r.stdout.strip()))
            cands.append(os.path.join(os.path.dirname(common), "deps", "ps3recomp"))
    except (OSError, subprocess.SubprocessError):
        pass
    for c in cands:
        p = os.path.join(c or "", "tools", "ppu_lifter.py")
        if c and os.path.isfile(p):
            with open(p, encoding="utf-8", errors="replace") as f:
                if "def _auto_jobs(" in f.read():
                    return c
    return None


_LIFTER = []


def load_lifter():
    if not _LIFTER:
        tree = find_ps3recomp()
        mod = None
        if tree:
            spec = importlib.util.spec_from_file_location("ppu_lifter_0048",
                                                          os.path.join(tree, "tools", "ppu_lifter.py"))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            mod.TREE = tree
        _LIFTER.append(mod)
    return _LIFTER[0]


class LifterUnits(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.L = load_lifter()
        if cls.L is None:
            raise unittest.SkipTest("no ps3recomp tree with patch 0048 (PS3RECOMP_DIR)")

    def test_ram_cap(self):
        jobs = self.L._auto_jobs
        # the measured plan: ~128 MB per worker next to ~1 GB for the lifter itself, at most 8 by default
        self.assertEqual((self.L.LIFT_WORKER_MB, self.L.LIFT_MAIN_MB, self.L.LIFT_MAX_AUTO_JOBS), (128, 1024, 8))
        j, why = jobs(32, 13 * GB)
        self.assertEqual(j, 8)
        self.assertIn("32 processors, at most 8 by default", why)
        self.assertEqual(jobs(8, 8 * GB)[0], 8)
        self.assertEqual(jobs(8, 2 * GB)[0], 8)                    # (2048 - 1024) // 128 = 8
        self.assertEqual(jobs(8, 1536 * MB)[0], 4)                 # (1536 - 1024) // 128 = 4
        j, why = jobs(8, 1536 * MB)
        self.assertIn("only 1.5 GB free memory: room for 4 worker(s)", why)
        self.assertEqual(jobs(8, 1151 * MB)[0], 1)                 # room for none: the serial lift
        self.assertEqual(jobs(8, 1024 * MB)[0], 1)
        self.assertEqual(jobs(8, 100 * MB)[0], 1)
        self.assertEqual(jobs(8, 0)[0], 1)
        self.assertEqual(jobs(16, 1024 * MB + 5 * 128 * MB)[0], 5)
        self.assertEqual(jobs(4, 64 * GB)[0], 4)                   # never more than the processors
        self.assertEqual(jobs(1, 64 * GB)[0], 1)
        self.assertEqual(jobs(None, 64 * GB)[0], 1)
        self.assertEqual(jobs(0, 64 * GB)[0], 1)
        j, why = jobs(6, None)                                    # unknown free memory: processors only
        self.assertEqual(j, 6)
        self.assertIn("free memory unknown", why)
        self.assertEqual(jobs(64, 64 * GB, max_jobs=16)[0], 16)
        self.assertEqual(jobs(64, 3 * GB, worker_mb=256, main_mb=2048)[0], 4)
        for cpus in range(1, 70):
            for free_mb in (0, 500, 1024, 1100, 1300, 2000, 4000, 9000, 70000):
                j, _ = jobs(cpus, free_mb * MB)
                self.assertGreaterEqual(j, 1)
                self.assertLessEqual(j, min(cpus, 8))
                if j > 1:     # what it starts fits next to the lifter itself
                    self.assertLessEqual(1024 + j * 128, free_mb)

    def test_memory_probes(self):
        free = self.L._free_memory_bytes()
        if os.name == "nt" or sys.platform.startswith("linux"):
            self.assertIsInstance(free, int)
            self.assertGreater(free, 16 * MB)
        self.assertGreater(self.L._peak_memory_bytes(), 1 * MB)

    def test_stall_limit(self):
        with mock.patch.dict(os.environ, {"T5DR_LIFT_STALL_SECONDS": ""}):
            lim = self.L._stall_limit
            self.assertEqual(lim(None), 600)      # before the first chunk
            self.assertEqual(lim(0.4), 120)       # 10x the slowest chunk, at least 2 minutes ...
            self.assertEqual(lim(30), 300)
            self.assertEqual(lim(200), 600)       # ... at most 10
        with mock.patch.dict(os.environ, {"T5DR_LIFT_STALL_SECONDS": "7"}):
            self.assertEqual(self.L._stall_limit(None), 7)


class SyntheticLift(unittest.TestCase):
    """The real ppu_lifter.py on a raw image of 400 tiny functions (li r3,i; blr): 8 chunks with --jobs 2."""

    @classmethod
    def setUpClass(cls):
        L = load_lifter()
        if L is None:
            raise unittest.SkipTest("no ps3recomp tree with patch 0048 (PS3RECOMP_DIR)")
        cls.lifter = os.path.join(L.TREE, "tools", "ppu_lifter.py")
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        d = cls.tmp.name
        n, base = 400, 0x10000
        with open(os.path.join(d, "image.bin"), "wb") as f:
            f.write(b"".join(struct.pack(">II", 0x38600000 | i, 0x4E800020) for i in range(n)))
        with open(os.path.join(d, "functions.json"), "w") as f:
            f.write("[" + ",".join(f'{{"start": "{base + 8 * i:#x}", "end": "{base + 8 * i + 8:#x}"}}'
                                   for i in range(n)) + "]")
        cls.serial = cls.lift("serial", ["--jobs", "1"])

    @classmethod
    def lift(cls, name, args, **env):
        d = cls.tmp.name
        out = os.path.join(d, name)
        e = dict(os.environ, PYTHONUTF8="1")
        for k in ("T5DR_LIFT_TEST_KILL", "T5DR_LIFT_TEST_HANG", "T5DR_LIFT_TEST_FREE_MB", "T5DR_LIFT_STALL_SECONDS",
                  "T5DR_LIFT_HEARTBEAT_SECONDS"):
            e.pop(k, None)
        e.update(env)
        r = subprocess.run([sys.executable, cls.lifter, os.path.join(d, "image.bin"), "--raw", "--base", "0x10000",
                            "--functions", os.path.join(d, "functions.json"), "-o", out] + args,
                           capture_output=True, text=True, encoding="utf-8", errors="replace", env=e, timeout=300)
        if r.returncode != 0:
            raise AssertionError(f"lift {name} exited {r.returncode}:\n{(r.stdout + r.stderr)[-3000:]}")
        files = {}
        for fn in sorted(os.listdir(out)):
            with open(os.path.join(out, fn), "rb") as f:
                files[fn] = hashlib.sha256(f.read()).hexdigest()
        return files, r.stdout

    def check(self, got, log_must=()):
        files, log = got
        self.assertEqual(files, self.serial[0])
        self.assertGreaterEqual(len(files), 2)
        for s in log_must:
            self.assertIn(s, log)
        # the Build tab's percentage only ever goes up, and only on progress lines
        fr = [v for _ln, v in subs(log.splitlines()) if v is not None]
        self.assertEqual(fr, sorted(fr))
        self.assertAlmostEqual(max(fr), 0.7)       # every function lifted (the emitting lines start at 70 %)
        return log

    def test_pool(self):
        self.check(self.lift("pool", ["--jobs", "2"]), ["parallel lift: 2 workers, 8 chunks of ~50",
                                                        "parallel lift: 8 chunks in"])

    def test_auto_jobs_line(self):
        log = self.check(self.lift("auto", []))
        self.assertRegex(log, r"(?m)^  jobs: \d+( \(serial lift\))? -- \d+ processors?")

    def test_low_memory_means_serial(self):
        log = self.check(self.lift("lowmem", [], T5DR_LIFT_TEST_FREE_MB="1100"))
        self.assertRegex(log, r"(?m)^  jobs: 1 [(]serial lift[)] -- [0-9]+ processors?, (at most 8 by default, )?"
                              r"only 1[.]1 GB free memory: room for 0 worker[(]s[)] of ~128 MB next to ~1024 MB")
        self.assertNotIn("parallel lift", log)

    def test_dead_worker(self):
        log = self.check(self.lift("kill", ["--jobs", "2"], T5DR_LIFT_TEST_KILL="3"),
                         ["stopped (exit code 1) while it lifted chunk 3",
                          "The chunks still missing are lifted in this process instead (same result)."])
        self.assertEqual(log.count("The chunks still missing"), 1)                  # one line

    def test_every_worker_dies(self):
        self.check(self.lift("killall", ["--jobs", "3"], T5DR_LIFT_TEST_KILL="0,1,2,3,4,5,6,7"),
                   ["lifted in this process instead"])

    def test_hung_worker(self):
        log = self.check(self.lift("hang", ["--jobs", "2"], T5DR_LIFT_TEST_HANG="5", T5DR_LIFT_STALL_SECONDS="4",
                                   T5DR_LIFT_HEARTBEAT_SECONDS="1"), ["1 of them in this process"])
        self.assertRegex(log, r"(?m)^  [.][.][.] still lifting: [0-9]+ chunks left, elapsed [0-9.]+m$")
        self.assertRegex(log, r"no chunk finished for [0-9]+ seconds [(]1 worker[(]s[)] still busy[)]")
        self.assertNotIn("did not exit", log)


if __name__ == "__main__":
    unittest.main()
