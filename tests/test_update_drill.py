"""tools/update_drill.py (docs/RELEASING.md "Update drill"): its arguments, how it reads the swap step's result
and its verdict. The drill itself runs real releases with a real package (the owner's PC); these parts need
neither."""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr

from helpers import ROOT

sys.path.insert(0, os.path.join(ROOT, "tools"))
import update_drill  # noqa: E402


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(data if isinstance(data, str) else json.dumps(data))


class Clock:
    """time.time / time.sleep stand-ins: sleeping moves the clock, and may change the files (step)."""

    def __init__(self, step=None):
        self.now = 1000.0
        self.slept = 0
        self.step = step

    def time(self):
        return self.now

    def sleep(self, s):
        self.now += s
        self.slept += 1
        if self.step:
            self.step(self.slept)


class Args(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="t5dr_drill_test_")
        self.old = os.path.join(self.d, "T5DR-Online-1.1.6.zip")
        self.new = os.path.join(self.d, "T5DR-Online-1.1.7.zip")
        self.pkg = os.path.join(self.d, "game.pkg")
        for path, version in ((self.old, "1.1.6"), (self.new, "1.1.7")):
            with zipfile.ZipFile(path, "w") as z:
                z.writestr(f"T5DR-Online-{version}/release.json", json.dumps({"version": version}))
                z.writestr(f"T5DR-Online-{version}/launcher/t5dr_launcher.pyw", "# launcher\n")
        write(self.pkg, "PKG stand-in")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def parse(self, *extra):
        return update_drill.parse_args(["--old-zip", self.old, "--pkg", self.pkg, "--work",
                                        os.path.join(self.d, "w")] + list(extra))

    def refused(self, *extra):
        err = io.StringIO()
        with redirect_stderr(err), self.assertRaises(SystemExit) as cm:
            self.parse(*extra)
        self.assertEqual(cm.exception.code, 2)
        return err.getvalue()

    def test_tag_and_its_version(self):
        a = self.parse("--tag", "v1.1.7")
        self.assertEqual((a.tag, a.new_zip, a.want, a.expect, a.alive, a.close_after), ("v1.1.7", None, "1.1.7",
                                                                                       "update", 30.0, None))
        self.assertEqual(self.parse("--tag", "1.1.7-rc1").want, "1.1.7-rc1")

    def test_new_zip_reads_its_version(self):
        a = self.parse("--new-zip", self.new, "--expect", "rollback", "--alive", "20")
        self.assertEqual((a.tag, a.want, a.expect, a.alive), (None, "1.1.7", "rollback", 20.0))
        self.assertEqual(self.parse("--new-zip", self.new, "--close-after", "3").close_after, 3.0)

    def test_one_new_release_exactly(self):
        self.assertIn("one of the arguments --tag --new-zip is required", self.refused())
        self.assertIn("not allowed with", self.refused("--tag", "v1.1.7", "--new-zip", self.new))

    def test_missing_files_are_named(self):
        self.assertIn("--new-zip", self.refused("--new-zip", os.path.join(self.d, "nope.zip")))
        os.remove(self.pkg)
        self.assertIn("--pkg", self.refused("--tag", "v1.1.7"))

    def test_a_zip_without_release_json(self):
        bad = os.path.join(self.d, "bad.zip")
        with zipfile.ZipFile(bad, "w") as z:
            z.writestr("T5DR-Online-1.1.7/README.txt", "x")
        self.assertIn("release.json", self.refused("--new-zip", bad))

    def test_close_after_is_for_a_working_release(self):
        self.assertIn("--close-after", self.refused("--new-zip", self.new, "--expect", "rollback",
                                                    "--close-after", "3"))
        self.refused("--tag", "v1.1.7", "--expect", "maybe")


class ReadResult(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="t5dr_drill_test_")
        self.install = os.path.join(self.d, "T5DR-Online-1.1.6")
        self.sroot = self.install + ".update"
        write(os.path.join(self.install, "release.json"), {"version": "1.1.6"})
        write(os.path.join(self.sroot, "swap.log"), "update 1.1.6 -> 1.1.7\n")

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def result(self, **r):
        write(os.path.join(self.sroot, "result.json"), dict({"ok": True, "phase": "swapped"}, **r))

    def read(self, step=None, timeout=300.0):
        c = Clock(step)
        r, log = update_drill.read_result(self.sroot, self.install, "1.1.7", timeout=timeout, sleep=c.sleep,
                                          clock=c.time)
        return r, log, c

    def test_waits_through_swapped_until_done(self):
        self.result()                                      # the new launcher has not confirmed yet

        def step(n):
            if n == 30:                                    # it confirmed (15 s)
                self.result(phase="done")
        r, log, c = self.read(step)
        self.assertEqual((r["ok"], r["phase"]), (True, "done"))
        self.assertEqual(c.slept, 30)
        self.assertIn("1.1.6 -> 1.1.7", log)

    def test_rolled_back(self):
        self.result()
        self.result(ok=False, phase="undone", rolled_back=True, error="the new launcher 1.1.7 did not start")
        r, _, c = self.read()
        self.assertEqual((r["ok"], r["phase"], r["rolled_back"]), (False, "undone", True))
        self.assertEqual(c.slept, 0)

    def test_failed_before_the_swap(self):
        self.result(ok=False, phase=None, changed=False, error="programs from the folder were still running")
        r, _, _ = self.read()
        self.assertFalse(r["ok"])
        self.assertIn("still running", r["error"])

    def test_staging_folder_cleaned_up_by_the_new_launcher(self):
        self.result()

        def step(n):
            if n == 3:                                     # the new launcher read the result and removed it
                write(os.path.join(self.install, "release.json"), {"version": "1.1.7"})
                shutil.rmtree(self.sroot)
        r, log, _ = self.read(step)
        self.assertEqual((r["ok"], r["phase"], r["error"]), (True, "done", None))
        self.assertIn("1.1.6 -> 1.1.7", log)               # the log as last seen

    def test_staging_folder_gone_but_the_old_version(self):
        self.result()
        shutil.rmtree(self.sroot)
        r, _, _ = self.read()
        self.assertFalse(r["ok"])
        self.assertEqual(r["error"], "the folder has version 1.1.6")

    def test_no_verdict_before_the_timeout(self):
        self.result()
        r, _, c = self.read(timeout=10)
        self.assertEqual(r["phase"], "swapped")
        self.assertEqual(c.slept, 20)

    def test_a_half_written_result_is_skipped(self):
        write(os.path.join(self.sroot, "result.json"), '{"ok": tr')

        def step(n):
            if n == 2:
                self.result(phase="done")
        r, _, _ = self.read(step)
        self.assertEqual(r["phase"], "done")


class Verdict(unittest.TestCase):
    def test_update(self):
        v = update_drill.verdict
        done = {"ok": True, "phase": "done"}
        self.assertTrue(v("update", done, "1.1.7", "1.1.6", "1.1.7", [[1, "pythonw.exe"]])[0])
        self.assertIn("does not run", v("update", done, "1.1.7", "1.1.6", "1.1.7", [])[1])
        self.assertIn("version 1.1.6", v("update", done, "1.1.6", "1.1.6", "1.1.7", [[1, "x"]])[1])
        undone = {"ok": False, "phase": "undone", "rolled_back": True, "error": "did not start"}
        ok, why = v("update", undone, "1.1.6", "1.1.6", "1.1.7", [[1, "x"]])
        self.assertFalse(ok)
        self.assertIn("did not start", why)

    def test_rollback(self):
        v = update_drill.verdict
        undone = {"ok": False, "phase": "undone", "rolled_back": True}
        self.assertTrue(v("rollback", undone, "1.1.6", "1.1.6", "1.1.7", [[1, "x"]])[0])
        self.assertIn("not running", v("rollback", undone, "1.1.6", "1.1.6", "1.1.7", [])[1])
        # 1.1.5 seen from 1.1.4: the broken launcher confirmed, the swap step kept it
        self.assertIn("not rolled back", v("rollback", {"ok": True, "phase": "done"}, "1.1.7", "1.1.6", "1.1.7",
                                           [])[1])
        half = dict(undone, rolled_back=False)
        self.assertFalse(v("rollback", half, "1.1.6", "1.1.6", "1.1.7", [[1, "x"]])[0])


if __name__ == "__main__":
    unittest.main()
