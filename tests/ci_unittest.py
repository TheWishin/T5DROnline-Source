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
"""
import argparse
import os
import platform
import re
import sys
import time
import unittest

MAX_DETAIL = 8          # failures that get an annotation of their own
TB_LINES = 14           # traceback lines kept (the end is what matters)
TB_CHARS = 3500
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


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-v", "--verbose", action="store_true", help="one line per test, like unittest -v")
    ap.add_argument("-s", "--start-directory", default=os.path.dirname(os.path.abspath(__file__)),
                    help="discover test*.py here (default: this file's directory)")
    ap.add_argument("names", nargs="*", help="test modules/classes/methods instead of discovery")
    a = ap.parse_args()

    gha = os.environ.get("GITHUB_ACTIONS") == "true"
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
    result = unittest.TextTestRunner(stream=sys.stdout, verbosity=2 if a.verbose else 1).run(suite)
    secs = time.time() - t0

    bad = [("FAIL", t, tb) for t, tb in result.failures] + [("ERROR", t, tb) for t, tb in result.errors] \
        + [("UNEXPECTED SUCCESS", t, "") for t in result.unexpectedSuccesses]
    if gha:
        what = " ".join(a.names) or "discover " + os.path.basename(os.path.abspath(a.start_directory))
        annotate("notice", f"unittest {what}",
                 f"ran {result.testsRun} tests in {secs:.1f} s: {len(result.failures)} failures, "
                 f"{len(result.errors)} errors, {len(result.skipped)} skipped; "
                 f"python {platform.python_version()} on {platform.platform()}, {os.cpu_count()} cpus")
        for kind, test, tb in bad[:MAX_DETAIL]:
            annotate("error", f"unittest {kind}: {test.id()}", tb_tail(tb) or kind)
        if bad:
            names = ", ".join(f"{kind.split()[0]} {test.id()}" for kind, test, _ in bad)
            annotate("error", "unittest summary", f"{len(bad)} of {result.testsRun} tests did not pass: {names}")
    sys.exit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    main()
