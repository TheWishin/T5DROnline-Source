#!/usr/bin/env python3
"""Run a unittest suite as CI does, and say which tests failed in annotations.

    python tests/ci_unittest.py [-v] [-s DIR]          # what `python -m unittest discover -s DIR` does
    python ../../tests/ci_unittest.py -v test_lobby    # what `python -m unittest -v test_lobby` does

Same tests, same output, same exit code as the plain `unittest` command. What
it adds, on GitHub Actions (GITHUB_ACTIONS=true), is what the job log cannot
give anyone without a login: every failed or errored test as one
`::error title=...::` annotation (test id + the end of its traceback), and one
summary annotation naming all of them. The REST API serves annotations without
authentication and the job logs only with it, so this is how a red run is read
from outside.

Two details matter on a runner:

* GitHub shows at most 10 error annotations per step. Several tools under test
  print `::error::` on purpose when a test drives them into an error path
  (a rejected --version, an unsafe archive path, ...). Those lines would use up
  the cap and push the real failures out, so lines of that kind written by this
  process are muted: they are still in the log, behind "[muted]", but they are
  not workflow commands. (Output of subprocesses a test captures never reached
  the log anyway.)
* Only a handful of failures get their own annotation; the summary lists all.
  Each one is written the moment the test fails, so a later crash cannot lose it.

And for a red run whose log nobody can read (the push job was red from the 1.1.5
merge on with no annotation to go by):

* The time per module is printed at the end (slowest first); on a runner the
  slowest ones are also in the summary notice.
* The tests run in a child process. When it ends without finishing (an
  interpreter abort such as "Tcl_AsyncDelete", an access violation, a test
  that ends its own process), this process says so in an annotation: the exit
  code, the test that was running, the modules done so far. faulthandler
  prints the child's Python stacks into the log. --in-process skips the child.
"""
import argparse
import faulthandler
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
import time
import unittest

MAX_DETAIL = 8          # failures that get an annotation of their own
SLOWEST = 8             # modules named in the summary notice
TB_LINES = 14           # traceback lines kept (the end is what matters)
TB_CHARS = 3500
PROGRESS_ENV = "T5DR_CI_PROGRESS"      # the child keeps the running test and the times in this file
COMMAND = re.compile(r"^::(error|warning|notice|debug|group|endgroup|add-mask|stop-commands)", re.M)


class Mute:
    """A text stream that defuses workflow commands (see the module docstring)."""

    def __init__(self, inner):
        self._inner = inner

    def write(self, s):
        return self._inner.write(COMMAND.sub(r"[muted] ::\1", s))

    def flush(self):
        self._inner.flush()

    def __getattr__(self, name):
        return getattr(self._inner, name)


def esc_data(s):
    return s.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def esc_prop(s):
    return esc_data(s).replace(":", "%3A").replace(",", "%2C")


def annotate(level, title, message):
    # The real stdout: sys.stdout is the muting wrapper while the tests run.
    print(f"::{level} title={esc_prop(title)}::{esc_data(message)}", file=sys.__stdout__, flush=True)


def tb_tail(tb):
    lines = tb.rstrip().splitlines()[-TB_LINES:]
    text = "\n".join(lines)
    return text[-TB_CHARS:]


def module_of(test):
    """The module a test belongs to ('test_updater'); a module that failed to import keeps its name."""
    tid = test.id()
    if tid.startswith("unittest.loader."):
        return tid.rsplit(".", 1)[-1]
    mod = type(test).__module__
    return mod if mod not in ("unittest.case", "unittest.suite") else tid.split(".")[0]


def timing_lines(secs, counts=None):
    """'   12.3 s  40.1 %  test_x (12 tests)' per module, slowest first."""
    total = sum(secs.values()) or 1.0
    out = []
    for mod, s in sorted(secs.items(), key=lambda kv: (-kv[1], kv[0])):
        n = (counts or {}).get(mod)
        out.append(f"{s:8.1f} s {100 * s / total:5.1f} %  {mod}" + (f" ({n} tests)" if n else ""))
    return out


def skip_lines(skipped, n=12):
    """'  3 x <reason> (test_x, test_y)' per distinct reason, most frequent first."""
    by = {}
    for test, reason in skipped:
        by.setdefault(str(reason).strip(), []).append(module_of(test))
    out = []
    for reason, mods in sorted(by.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:n]:
        names = sorted(set(mods))
        out.append(f"{len(mods):3d} x {reason[:200]} ({', '.join(names[:4])}{', ...' if len(names) > 4 else ''})")
    return out


def slowest(secs, n=SLOWEST):
    return ", ".join(f"{m} {s:.0f}s" for m, s in sorted(secs.items(), key=lambda kv: (-kv[1], kv[0]))[:n]) or "-"


class TimedResult(unittest.TextTestResult):
    """The usual result, plus: the time per module, the running test in the progress file (for the
    parent), and on a runner each failure's annotation right away."""

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.module_secs = {}
        self.module_tests = {}
        self.progress = os.environ.get(PROGRESS_ENV)
        self.gha = os.environ.get("GITHUB_ACTIONS") == "true"
        self.annotated = 0
        self._t0 = None

    def write_progress(self, current, done=False):
        if not self.progress:
            return
        data = {"current": current, "done": done, "run": self.testsRun, "modules": self.module_secs}
        try:
            with open(self.progress + ".tmp", "w", encoding="utf-8") as f:
                json.dump(data, f)
            os.replace(self.progress + ".tmp", self.progress)
        except OSError:
            pass

    def startTest(self, test):
        self.write_progress(test.id())
        self._t0 = time.perf_counter()
        super().startTest(test)

    def stopTest(self, test):
        super().stopTest(test)
        mod = module_of(test)
        if self._t0 is not None:
            self.module_secs[mod] = self.module_secs.get(mod, 0.0) + time.perf_counter() - self._t0
        self.module_tests[mod] = self.module_tests.get(mod, 0) + 1
        self._t0 = None

    def _annotate(self, kind, test, err):
        if self.gha and self.annotated < MAX_DETAIL:
            self.annotated += 1
            annotate("error", f"unittest {kind}: {test.id()}", tb_tail(self._exc_info_to_string(err, test)) or kind)

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self._annotate("FAIL", test, err)

    def addError(self, test, err):
        super().addError(test, err)
        self._annotate("ERROR", test, err)

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err is not None:
            self._annotate("FAIL" if issubclass(err[0], test.failureException) else "ERROR", subtest, err)


def run_child(argv, gha):
    """Run the tests in a child (this file with --in-process) and report a child that did not finish."""
    fd, progress = tempfile.mkstemp(prefix="t5dr_ci_progress_", suffix=".json")
    os.close(fd)
    os.remove(progress)
    t0 = time.time()
    rc = subprocess.call([sys.executable, os.path.abspath(__file__), "--in-process"] + list(argv),
                         env=dict(os.environ, **{PROGRESS_ENV: progress}))
    state = {}
    try:
        with open(progress, encoding="utf-8") as f:
            state = json.load(f)
    except (OSError, ValueError):
        pass
    for p in (progress, progress + ".tmp"):
        try:
            os.remove(p)
        except OSError:
            pass
    if state.get("done"):
        return rc
    code = f"0x{rc & 0xFFFFFFFF:08X}" if rc < 0 or rc > 255 else str(rc)
    msg = (f"the test process ended without finishing: exit code {code} after {time.time() - t0:.0f} s, "
           f"{state.get('run', 0)} tests in, during {state.get('current') or '(no test started: loading the modules)'}; "
           f"slowest modules so far: {slowest(state.get('modules') or {})}")
    print("\n" + msg, flush=True)
    if gha:
        annotate("error", "unittest process died", msg)
    return rc or 1


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-v", "--verbose", action="store_true", help="one line per test, like unittest -v")
    ap.add_argument("-s", "--start-directory", default=os.path.dirname(os.path.abspath(__file__)),
                    help="discover test*.py here (default: this file's directory)")
    ap.add_argument("--in-process", action="store_true",
                    help="run the tests in this process (default: in a child process, so a crash is reported)")
    ap.add_argument("names", nargs="*", help="test modules/classes/methods instead of discovery")
    argv = sys.argv[1:] if argv is None else argv
    a = ap.parse_args(argv)

    gha = os.environ.get("GITHUB_ACTIONS") == "true"
    if not a.in_process:
        return run_child(argv, gha)
    faulthandler.enable()               # a hard crash prints every thread's Python stack into the log
    sys.stdout = Mute(sys.stdout)
    sys.stderr = Mute(sys.stderr)

    loader = unittest.TestLoader()
    if a.names:
        sys.path.insert(0, os.getcwd())          # as `python -m unittest` does
        suite = loader.loadTestsFromNames(a.names)
    else:
        start = os.path.abspath(a.start_directory)
        suite = loader.discover(start)           # also puts `start` on sys.path
    t0 = time.time()
    runner = unittest.TextTestRunner(stream=sys.stdout, verbosity=2 if a.verbose else 1, resultclass=TimedResult)
    result = runner.run(suite)
    secs = time.time() - t0
    result.write_progress(None, done=True)

    print("\n== time per module (slowest first)")
    for line in timing_lines(result.module_secs, result.module_tests):
        print(line)
    skips = skip_lines(result.skipped)
    if skips:
        print("\n== why tests were skipped (a runner without something a test needs says so here)")
        for line in skips:
            print(line)
    sys.stdout.flush()

    bad = [("FAIL", t, tb) for t, tb in result.failures] + [("ERROR", t, tb) for t, tb in result.errors] \
        + [("UNEXPECTED SUCCESS", t, "") for t in result.unexpectedSuccesses]
    if gha:
        what = " ".join(a.names) or "discover " + os.path.basename(os.path.abspath(a.start_directory))
        annotate("notice", f"unittest {what}",
                 f"ran {result.testsRun} tests in {secs:.1f} s: {len(result.failures)} failures, "
                 f"{len(result.errors)} errors, {len(result.skipped)} skipped; "
                 f"python {platform.python_version()} on {platform.platform()}, {os.cpu_count()} cpus; "
                 f"slowest: {slowest(result.module_secs)}")
        if skips:
            annotate("warning", f"unittest {what}: skipped", "; ".join(skips)[:TB_CHARS])
        if bad:
            names = ", ".join(f"{kind.split()[0]} {test.id()}" for kind, test, _ in bad)
            annotate("error", "unittest summary", f"{len(bad)} of {result.testsRun} tests did not pass: {names}")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
