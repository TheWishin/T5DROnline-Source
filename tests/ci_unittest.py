#!/usr/bin/env python3
"""Run a unittest suite as CI does, and say which tests failed in annotations.

    python tests/ci_unittest.py [-v] [-s DIR]          # what `python -m unittest discover -s DIR` does
    python ../../tests/ci_unittest.py -v test_lobby    # what `python -m unittest -v test_lobby` does

Same tests and results as the plain `unittest` command, with a bounded parent
deadline (900 seconds by default, timeout exit code 124). What
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
  Every failure's traceback is also written and flushed to the log immediately,
  including outside GitHub Actions, so a later crash cannot lose its details.

And for a red run whose log nobody can read (the push job was red from the 1.1.5
merge on with no annotation to go by):

* The time per module is printed at the end (slowest first); on a runner the
  slowest ones are also in the summary notice.
* The tests run in a child process. When it ends without finishing (an
  interpreter abort such as "Tcl_AsyncDelete", an access violation, a test
  that ends its own process), this process says so in an annotation: the exit
  code, the test that was running, the modules done so far. faulthandler
  prints the child's Python stacks into the log. --in-process skips the child.
  The parent also bounds discovery, fixtures and interpreter shutdown; a timeout
  dumps all Python thread stacks, reports the phase and terminates descendants.
"""
import argparse
import faulthandler
import importlib.util
import json
import math
import os
import platform
import re
import subprocess
import sys
import tempfile
import time
import unittest

# runpy and module entry points do not put this directory on sys.path. Load the
# sibling by path without changing where the selected test modules resolve.
_process_spec = importlib.util.spec_from_file_location(
    "_t5dr_ci_process", os.path.join(os.path.dirname(os.path.abspath(__file__)), "ci_process.py"))
_process_module = importlib.util.module_from_spec(_process_spec)
_process_spec.loader.exec_module(_process_module)
ProcessTree = _process_module.ProcessTree

MAX_DETAIL = 8          # failures that get an annotation of their own
SLOWEST = 8             # modules named in the summary notice
TB_LINES = 14           # traceback lines kept (the end is what matters)
TB_CHARS = 3500
PROGRESS_ENV = "T5DR_CI_PROGRESS"      # the child keeps the running test and the times in this file
TIMEOUT_ENV = "T5DR_CI_TIMEOUT"
DEADLINE_ENV = "T5DR_CI_DEADLINE"
DEFAULT_TIMEOUT = 900.0
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
    parent), each failure's traceback right away, and annotations on a runner."""

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.module_secs = {}
        self.module_tests = {}
        self.progress = os.environ.get(PROGRESS_ENV)
        self.gha = os.environ.get("GITHUB_ACTIONS") == "true"
        self.annotated = 0
        self._t0 = None

    def write_progress(self, current, done=False, exit_code=None):
        if not self.progress:
            return
        data = {"current": current, "done": done, "run": self.testsRun,
                "modules": self.module_secs, "exit_code": exit_code}
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
        self.write_progress("after " + test.id())

    def _report_problem(self, kind, test, traceback):
        # TextTestRunner normally waits until the suite ends to print these.
        # A child abort or timeout would then lose every earlier failure's
        # details, and GitHub annotations only retain the first MAX_DETAIL.
        # Keep the standard final report too, while making the log durable now.
        self.stream.writeln()
        self.printErrorList(kind, [(test, traceback)])
        self.stream.flush()
        if self.gha and self.annotated < MAX_DETAIL:
            self.annotated += 1
            annotate("error", f"unittest {kind}: {test.id()}", tb_tail(traceback) or kind)

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self._report_problem("FAIL", test, self.failures[-1][1])

    def addError(self, test, err):
        super().addError(test, err)
        self._report_problem("ERROR", test, self.errors[-1][1])

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err is not None:
            failed = issubclass(err[0], test.failureException)
            problems = self.failures if failed else self.errors
            self._report_problem("FAIL" if failed else "ERROR", subtest, problems[-1][1])


class TrackedSuite(unittest.TestSuite):
    """Name fixture work too: unittest calls startTest only after setUpClass."""

    def _handleClassSetUp(self, test, result):
        cls = test.__class__
        if cls != getattr(result, "_previousTestClass", None):
            result.write_progress("setUpClass " + cls.__module__ + "." + cls.__qualname__)
        super()._handleClassSetUp(test, result)

    def _tearDownPreviousClass(self, test, result):
        previous = getattr(result, "_previousTestClass", None)
        if previous is not None and previous != getattr(test, "__class__", None):
            result.write_progress("tearDownClass " + previous.__module__ + "." + previous.__qualname__)
        super()._tearDownPreviousClass(test, result)

    def _handleModuleFixture(self, test, result):
        previous = getattr(result, "_previousTestClass", None)
        self._setting_up_module = (test.__class__.__module__
                                   if getattr(previous, "__module__", None) != test.__class__.__module__
                                   else None)
        try:
            super()._handleModuleFixture(test, result)
        finally:
            self._setting_up_module = None

    def _handleModuleTearDown(self, result):
        previous = getattr(result, "_previousTestClass", None)
        if previous is not None:
            result.write_progress("tearDownModule " + previous.__module__)
        super()._handleModuleTearDown(result)
        # unittest tears down the previous module inside _handleModuleFixture,
        # before calling the new module's setUpModule. Record that transition.
        if getattr(self, "_setting_up_module", None):
            result.write_progress("setUpModule " + self._setting_up_module)


class DiscoveryLoader(unittest.TestLoader):
    """Partition discovery before imports, keeping expensive files in other runs."""

    def __init__(self, excluded=()):
        super().__init__()
        self.excluded = frozenset(excluded)

    def _match_path(self, path, full_path, pattern):
        if os.path.splitext(path)[0] in self.excluded:
            return False
        return super()._match_path(path, full_path, pattern)


def module_basename(value):
    if not value.isidentifier():
        raise argparse.ArgumentTypeError("expected a test-file basename without .py or a directory")
    return value


def positive_seconds(value):
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        raise argparse.ArgumentTypeError("timeout must be a finite positive number of seconds")
    if not math.isfinite(seconds) or seconds <= 0:
        raise argparse.ArgumentTypeError("timeout must be a finite positive number of seconds")
    return seconds


def run_child(argv, gha, timeout):
    """Run the tests in a child (this file with --in-process) and report a child that did not finish."""
    fd, progress = tempfile.mkstemp(prefix="t5dr_ci_progress_", suffix=".json")
    os.close(fd)
    os.remove(progress)
    t0 = time.monotonic()
    timed_out = False
    tree = ProcessTree()
    try:
        proc = subprocess.Popen(
            [sys.executable, os.path.abspath(__file__), "--in-process"] + list(argv),
            env=dict(os.environ, **{PROGRESS_ENV: progress,
                                   DEADLINE_ENV: str(t0 + timeout)}), **tree.popen_kwargs)
        try:
            tree.attach(proc)
        except Exception:
            proc.kill()
            proc.wait(timeout=5)
            raise
        # The child waits here until containment covers descendants as well.
        with open(progress + ".ready", "w", encoding="utf-8"):
            pass
        try:
            rc = proc.wait(timeout=max(0.001, t0 + timeout - time.monotonic()))
        except subprocess.TimeoutExpired:
            timed_out = True
            # Give the child's deadline stack dump time to reach stderr.
            try:
                proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                pass
            tree.terminate()
            rc = proc.wait(timeout=5)
    finally:
        tree.close()
    state = {}
    try:
        with open(progress, encoding="utf-8") as f:
            state = json.load(f)
    except (OSError, ValueError):
        pass
    for p in (progress, progress + ".tmp", progress + ".ready"):
        try:
            os.remove(p)
        except OSError:
            pass
    if timed_out:
        msg = (f"test timeout after {timeout:g} s: {state.get('run', 0)} tests in, "
               f"during {state.get('current') or 'loading modules'}; "
               f"slowest modules so far: {slowest(state.get('modules') or {})}")
        print("\n" + msg, flush=True)
        if gha:
            annotate("error", "unittest timeout", msg)
        return 124
    # A summary precedes interpreter shutdown. A later abort (or an atexit
    # handler overriding failure with exit 0) must not hide behind done=True.
    if state.get("done") and rc == state.get("exit_code"):
        return rc
    code = f"0x{rc & 0xFFFFFFFF:08X}" if rc < 0 or rc > 255 else str(rc)
    msg = (f"the test process ended without finishing: exit code {code} after {time.monotonic() - t0:.0f} s, "
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
    ap.add_argument("--timeout", type=positive_seconds,
                    help="parent deadline in seconds (default: T5DR_CI_TIMEOUT or 900; --in-process is unbounded)")
    ap.add_argument("--exclude-module", action="append", default=[], type=module_basename,
                    help="exclude this test-file basename (without .py) before discovery imports; repeatable")
    ap.add_argument("names", nargs="*", help="test modules/classes/methods instead of discovery")
    argv = sys.argv[1:] if argv is None else argv
    a = ap.parse_args(argv)
    if a.names and a.exclude_module:
        ap.error("--exclude-module requires discovery, without named test selections")
    try:
        timeout = a.timeout if a.timeout is not None else positive_seconds(os.environ.get(TIMEOUT_ENV, DEFAULT_TIMEOUT))
    except argparse.ArgumentTypeError as exc:
        ap.error(str(exc))

    gha = os.environ.get("GITHUB_ACTIONS") == "true"
    if not a.in_process:
        return run_child(argv, gha, timeout)
    faulthandler.enable()               # a hard crash prints every thread's Python stack into the log
    if os.environ.get(DEADLINE_ENV) and os.environ.get(PROGRESS_ENV):
        faulthandler.dump_traceback_later(max(0.001, float(os.environ[DEADLINE_ENV]) - time.monotonic()))
        while not os.path.exists(os.environ[PROGRESS_ENV] + ".ready"):
            time.sleep(0.01)
    sys.stdout = Mute(sys.stdout)
    sys.stderr = Mute(sys.stderr)

    loader = DiscoveryLoader(a.exclude_module)
    loader.suiteClass = TrackedSuite
    # Discovery happens before TextTestRunner constructs its result.
    progress = os.environ.get(PROGRESS_ENV)
    if progress:
        with open(progress, "w", encoding="utf-8") as f:
            json.dump({"current": "loading modules", "done": False}, f)
    if a.names:
        sys.path.insert(0, os.getcwd())          # as `python -m unittest` does
        suite = loader.loadTestsFromNames(a.names)
    else:
        start = os.path.abspath(a.start_directory)
        if a.exclude_module:
            print("== discovery excludes: " + ", ".join(sorted(set(a.exclude_module))), flush=True)
        suite = loader.discover(start)           # also puts `start` on sys.path
    t0 = time.time()
    runner = unittest.TextTestRunner(stream=sys.stdout, verbosity=2 if a.verbose else 1, resultclass=TimedResult)
    result = runner.run(suite)
    secs = time.time() - t0
    exit_code = 0 if result.wasSuccessful() else 1
    result.write_progress("shutdown", done=True, exit_code=exit_code)

    print("\n== time per module (slowest first)")
    for line in timing_lines(result.module_secs, result.module_tests):
        print(line)
    skips = skip_lines(result.skipped)
    if skips:
        print("\n== why tests were skipped (a runner without something a test needs says so here)")
        for line in skips:
            print(line)
    bad = [("FAIL", t, tb) for t, tb in result.failures] + [("ERROR", t, tb) for t, tb in result.errors] \
        + [("UNEXPECTED SUCCESS", t, "") for t in result.unexpectedSuccesses]
    if bad:
        # Keep the failing IDs in a captured log's tail, after the potentially
        # long timing and skip tables, including outside GitHub Actions.
        names = ", ".join(f"{kind} {test.id()}" for kind, test, _ in bad)
        summary = f"{len(bad)} of {result.testsRun} tests did not pass: {names}"
        print("\n== tests that did not pass")
        print(summary)
    sys.stdout.flush()
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
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
