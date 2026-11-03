"""Run the workflow's actual PowerShell test routing with program-only suites."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
WRAPPER = ROOT / "tests" / "ci_unittest.py"
LAYOUT_MODULES = ("test_i18n", "test_font_fallback", "test_layout_lobby_entry")


def routing_block():
    """Read the executed YAML block, omitting only dependency installation."""
    source = WORKFLOW.read_text(encoding="utf-8")
    step = source.split("      - name: Python unit tests\n", 1)[1]
    block = step.split("        run: |\n", 1)[1].split("\n\n", 1)[0]
    lines = [line[10:] for line in block.splitlines()]
    # pip setup is unrelated to routing and must not install anything in a test.
    start = next(i for i, line in enumerate(lines) if line.strip() ==
                 "if ($LASTEXITCODE) { exit 1 }") + 1
    return "\n".join(lines[start:])


def quote_ps(value):
    return "'" + str(value).replace("'", "''") + "'"


@unittest.skipUnless(shutil.which("pwsh") or shutil.which("powershell"),
                     "PowerShell is required to execute the Windows workflow")
class WorkflowBatches(unittest.TestCase):
    def run_workflow(self, *, delay=0, failing=None):
        scope = ROOT / "_ci_scope_temp"
        scope.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="workflow_batches_", dir=scope) as folder:
            directory = Path(folder)
            for module in ("test_regular", *LAYOUT_MODULES):
                source = (
                    "import os, time, unittest\n"
                    "class ProgramOnly(unittest.TestCase):\n"
                    "    def test_runs(self):\n"
                    f"        time.sleep({delay!r})\n"
                    f"        print('BATCH_EXECUTED:{module} PID:' + str(os.getpid()), flush=True)\n"
                    f"        self.assertFalse({module == failing!r}, 'batch failure')\n"
                )
                (directory / (module + ".py")).write_text(source, encoding="utf-8")
            command = ("& " + quote_ps(sys.executable) + " -B " + quote_ps(WRAPPER)
                       + " -s .")
            script = routing_block().replace("python tests/ci_unittest.py", command)
            script_path = directory / "route.ps1"
            script_path.write_text(script, encoding="utf-8")
            env = {key: value for key, value in os.environ.items()
                   if key not in ("GITHUB_ACTIONS", "T5DR_CI_PROGRESS", "T5DR_CI_DEADLINE")}
            env.update(TEMP=folder, TMP=folder, TMPDIR=folder,
                       T5DR_CI_TIMEOUT="2", PYTHONDONTWRITEBYTECODE="1",
                       PYTHONIOENCODING="utf-8")
            result = subprocess.run(
                [shutil.which("pwsh") or shutil.which("powershell"), "-NoProfile",
                 "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script_path)],
                cwd=folder, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", timeout=25,
            )
        return result.returncode, result.stdout

    def assert_all_once(self, output):
        for module in ("test_regular", *LAYOUT_MODULES):
            self.assertEqual(output.count("BATCH_EXECUTED:" + module), 1, output)
        self.assertEqual(len(set(re.findall(r"BATCH_EXECUTED:\w+ PID:(\d+)", output))),
                         4, "each batch needs its own test process:\n" + output)

    def test_each_batch_keeps_its_own_deadline(self):
        # Four valid 0.8s suites exceed one 2s deadline, but each fits its own.
        code, output = self.run_workflow(delay=0.8)
        self.assertEqual(code, 0, output)
        self.assert_all_once(output)
        self.assertNotIn("test timeout after", output)

    def test_discovery_failure_still_runs_all_layout_batches(self):
        code, output = self.run_workflow(failing="test_regular")
        self.assertNotEqual(code, 0, output)
        self.assert_all_once(output)

    def test_layout_failure_survives_later_success(self):
        code, output = self.run_workflow(failing="test_font_fallback")
        self.assertNotEqual(code, 0, output)
        self.assert_all_once(output)


if __name__ == "__main__":
    unittest.main()
