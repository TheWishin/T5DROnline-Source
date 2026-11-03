"""Inspect a native test's compiler command using fakes; never run a compiler."""
import ast
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


class OverlayHarnessLinkLibraries(unittest.TestCase):
    def test_training_layout_keeps_bitmap_and_unprepared_native_cases_separate(self):
        source = (ROOT / "tests/c/training_test.cpp").read_text(encoding="utf-8")
        self.assertIn(r'\xC3\x9F?\x01\x09', source)
        self.assertNotIn(r'\xC3\x9F\xE2\x82\xAC\x01\x09', source)
        self.assertIn(r'const char* unprepared = "a\xE2\x82\xAC";', source)
        self.assertIn('CHECK(!rsx_overlay_text_supported(unprepared));', source)
        self.assertIn('CHECK_EQ(rsx_overlay_text_width(unprepared, 1), 0);', source)

    def test_training_harness_links_windows_font_dependencies(self):
        source = ROOT / "tests" / "test_training.py"
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        harness = next(node for node in tree.body if isinstance(node, ast.ClassDef)
                       and node.name == "LogicAndLayoutTest")
        setup = next(node for node in harness.body if isinstance(node, ast.FunctionDef)
                     and node.name == "setUpClass")
        setup.decorator_list = []
        run = mock.Mock(return_value=SimpleNamespace(stdout="", stderr="", returncode=0))
        namespace = {
            "os": SimpleNamespace(name="nt", path=SimpleNamespace(
                join=os.path.join, isfile=lambda _: True)),
            "find_ps3recomp": lambda: "fake-runtime",
            "find_vcvars": lambda: "fake-vcvars.bat",
            "shutil": SimpleNamespace(which=lambda _: "fake-clang-cl"),
            "tempfile": SimpleNamespace(TemporaryDirectory=lambda: SimpleNamespace(
                name="fake-temporary-directory", cleanup=lambda: None)),
            "subprocess": SimpleNamespace(run=run),
            "unittest": unittest,
            "ROOT": str(ROOT),
            "TRAINING": str(ROOT / "src" / "training"),
        }
        exec(compile(ast.Module(body=[setup], type_ignores=[]), str(source), "exec"), namespace)
        namespace["setUpClass"](SimpleNamespace(addClassCleanup=lambda _: None))
        run.assert_called_once()
        command = run.call_args.args[0].lower()
        self.assertIn("gdi32.lib", command)
        self.assertIn("user32.lib", command)


if __name__ == "__main__":
    unittest.main()
