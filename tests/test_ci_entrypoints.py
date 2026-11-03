"""Run the CI command through script, module, and runpy entry points.

Each command discovers a real, synthetic unittest suite.  A help-only invocation
would miss failures in the parent/child handoff and test loading.
"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "tests" / "ci_unittest.py"
SCOPE = ROOT / "_ci_scope_temp"


class Entrypoints(unittest.TestCase):
    def setUp(self):
        SCOPE.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="ci_entrypoints_", dir=SCOPE)
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        (self.directory / "test_entry_probe.py").write_text(
            "import unittest\n"
            "class Probe(unittest.TestCase):\n"
            "    def test_actual_suite(self):\n"
            "        print('ENTRYPOINT_PROBE_EXECUTED', flush=True)\n"
            "        self.assertEqual(6 * 7, 42)\n",
            encoding="utf-8",
        )

    def run_entry(self, prefix, *, cwd=ROOT, in_process=False, names=()):
        env = {key: value for key, value in os.environ.items()
               if not key.startswith("T5DR_CI_")
               and key not in ("GITHUB_ACTIONS", "PYTHONPATH")}
        env.update(TMP=str(self.directory), TEMP=str(self.directory),
                   TMPDIR=str(self.directory), PYTHONDONTWRITEBYTECODE="1")
        args = ["--timeout", "15", "-v", "-s", str(self.directory)]
        if in_process:
            args.append("--in-process")
        args.extend(names)
        result = subprocess.run(
            [sys.executable, "-B", *prefix, *args], cwd=cwd, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            timeout=40,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("ENTRYPOINT_PROBE_EXECUTED", result.stdout)
        self.assertIn("Ran 1 test", result.stdout)
        self.assertIn("\nOK\n", result.stdout)
        self.assertIn("test_entry_probe (1 tests)", result.stdout)

    def test_script_from_another_directory(self):
        self.run_entry([str(WRAPPER)], cwd=self.directory)

    def test_named_module_from_another_directory(self):
        self.run_entry([str(WRAPPER)], cwd=self.directory,
                       names=("test_entry_probe",))

    def test_module(self):
        self.run_entry(["-m", "tests.ci_unittest"])

    def test_runpy_path(self):
        self.run_entry(["-c", "import runpy; runpy.run_path('tests/ci_unittest.py', run_name='__main__')"])

    def test_runpy_path_in_process(self):
        self.run_entry(["-c", "import runpy; runpy.run_path('tests/ci_unittest.py', run_name='__main__')"],
                       in_process=True)

    def test_runpy_absolute_path_from_another_directory(self):
        # Pass the path as argv rather than interpolating a machine-specific
        # path into executable Python source.
        self.run_entry(["-c", "import runpy, sys; runpy.run_path(sys.argv.pop(1), run_name='__main__')",
                        str(WRAPPER)], cwd=self.directory)


if __name__ == "__main__":
    unittest.main()
