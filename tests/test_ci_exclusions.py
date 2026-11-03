"""CI discovery partitions skip excluded files before importing their code."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "tests" / "ci_unittest.py"


class DiscoveryExclusions(unittest.TestCase):
    def setUp(self):
        scope = ROOT / "_ci_scope_temp"
        scope.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="ci_exclusions_", dir=scope)
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.write("test_keep", '''
import unittest
class Keep(unittest.TestCase):
    def test_once(self):
        print("KEPT_BODY", flush=True)
''')

    def write(self, name, source):
        (self.folder / (name + ".py")).write_text(source, encoding="utf-8")

    def run_command(self, *args, timeout="3"):
        env = {key: value for key, value in os.environ.items()
               if key not in ("GITHUB_ACTIONS", "T5DR_CI_PROGRESS", "T5DR_CI_DEADLINE", "T5DR_CI_TIMEOUT")}
        env.update(TEMP=str(self.folder), TMP=str(self.folder), TMPDIR=str(self.folder),
                   PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
        result = subprocess.run(
            [sys.executable, "-B", str(WRAPPER), "--timeout", timeout,
             "-s", str(self.folder), *args], cwd=self.folder, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", timeout=10)
        return result.returncode, result.stdout

    def test_excluded_error_is_not_imported_and_remaining_test_runs_once(self):
        self.write("test_bad", 'print("BAD_IMPORT", flush=True)\nraise RuntimeError("excluded import")\n')
        rc, output = self.run_command("--exclude-module", "test_bad")
        self.assertEqual(rc, 0, output)
        self.assertNotIn("BAD_IMPORT", output)
        self.assertEqual(output.count("KEPT_BODY"), 1, output)
        self.assertIn("Ran 1 test", output)

    def test_excluded_hang_is_not_imported(self):
        self.write("test_hang", 'import time\nprint("HANG_IMPORT", flush=True)\ntime.sleep(120)\n')
        rc, output = self.run_command("--exclude-module", "test_hang", timeout="1")
        self.assertEqual(rc, 0, output)
        self.assertNotIn("HANG_IMPORT", output)
        self.assertIn("Ran 1 test", output)

    def test_repeatable_exclusions_preserve_other_files(self):
        for name in ("test_bad", "test_other"):
            self.write(name, 'raise RuntimeError("must not import")\n')
        rc, output = self.run_command("--exclude-module", "test_bad", "--exclude-module", "test_other")
        self.assertEqual(rc, 0, output)
        self.assertEqual(output.count("KEPT_BODY"), 1, output)
        self.assertIn("Ran 1 test", output)

    def test_without_exclusions_import_error_still_fails(self):
        self.write("test_bad", 'raise RuntimeError("ordinary import error")\n')
        rc, output = self.run_command()
        self.assertEqual(rc, 1, output)
        self.assertIn("ordinary import error", output)
        self.assertIn("Ran 2 tests", output)

    def test_without_exclusions_import_hang_still_times_out(self):
        self.write("test_hang", 'import time\nprint("HANG_IMPORT", flush=True)\ntime.sleep(120)\n')
        rc, output = self.run_command(timeout="1")
        self.assertEqual(rc, 124, output)
        self.assertIn("HANG_IMPORT", output)
        self.assertIn("during loading modules", output)
        self.assertIn("Timeout (", output)

    def test_named_selection_without_exclusions_is_unchanged(self):
        self.write("test_bad", 'raise RuntimeError("not selected")\n')
        rc, output = self.run_command("test_keep")
        self.assertEqual(rc, 0, output)
        self.assertIn("Ran 1 test", output)
        self.assertEqual(output.count("KEPT_BODY"), 1, output)

    def test_named_selection_rejects_discovery_exclusions(self):
        rc, output = self.run_command("--exclude-module", "test_bad", "test_keep")
        self.assertEqual(rc, 2, output)
        self.assertIn("--exclude-module requires discovery", output)

    def test_exclusions_require_file_basename_without_extension(self):
        for value in ("", "test_bad.py", "tests.test_bad", "../test_bad", "test-bad"):
            with self.subTest(value=value):
                rc, output = self.run_command("--exclude-module", value)
                self.assertEqual(rc, 2, output)
                self.assertIn("test-file basename without .py", output)


if __name__ == "__main__":
    unittest.main()
