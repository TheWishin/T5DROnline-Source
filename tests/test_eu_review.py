"""Synthetic owner-local EU review checks; never need a real package or program."""
import csv
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from helpers import ROOT, load_tool


class ReviewSafety(unittest.TestCase):
    def setUp(self):
        self.addr = load_tool("addr_map")

    def test_repository_inputs_and_outputs_refused(self):
        for relative in ("private-report.csv", "docs/EBOOT.elf", "build/new-review"):
            with self.subTest(relative=relative), self.assertRaises(ValueError):
                self.addr.outside_repository(Path(ROOT) / relative)

    def test_private_tables_keep_unresolved_and_owner_review(self):
        us = SimpleNamespace(toc=0x10000, info={0x10000: (4, None, []), 0x10100: (4, None, [])},
                             containing=lambda x: None)
        eu = SimpleNamespace(toc=0x20000)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "review"
            self.addr.write_review(output, us, eu, {0x10000: 0x20000}, {0x30000: (0x40000, 2)},
                                   [0x30000, 0x30004])
            with (output / "required.csv").open(newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(rows[0]["other_candidate"], "00040000")
            self.assertEqual(rows[1]["other_candidate"], "")
            self.assertEqual(rows[1]["status"], "unresolved")
            self.assertTrue(all(not r["owner_decision"] for r in rows))
            with (output / "functions.csv").open(newline="", encoding="utf-8") as f:
                self.assertEqual(list(csv.DictReader(f))[1]["status"], "unresolved")
            self.assertFalse(json.loads((output / "summary.json").read_text())["approved_for_runtime"])
            with self.assertRaises(FileExistsError):
                self.addr.write_review(output, us, eu, {}, {}, [])

    def test_wrong_program_stops_before_analysis(self):
        with mock.patch.dict(sys.modules, {"addr_map": self.addr}):
            tool = load_tool("eu_review")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fake.txt"
            path.write_text("synthetic input, not a game program", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "SHA-1"):
                tool.checked_program(path, "eu")

    def test_extract_refuses_other_package_before_subprocess(self):
        with mock.patch.dict(sys.modules, {"addr_map": self.addr}):
            tool = load_tool("eu_review")
        with tempfile.TemporaryDirectory() as directory:
            a = SimpleNamespace(package=str(Path(directory) / "fake.pkg"), deps=directory,
                                scratch=str(Path(directory) / "new"), keys=None)
            with mock.patch.object(tool, "package_id", return_value="OTHER"), \
                    mock.patch.object(tool, "run_tool") as run, self.assertRaises(ValueError):
                tool.extract(a)
            run.assert_not_called()
            self.assertFalse(Path(a.scratch).exists())

    def test_extract_only_stages_sfo_and_eboot_never_decrypts(self):
        with mock.patch.dict(sys.modules, {"addr_map": self.addr}):
            tool = load_tool("eu_review")
        with tempfile.TemporaryDirectory() as directory:
            a = SimpleNamespace(package=str(Path(directory) / "fake.pkg"), deps=directory,
                                scratch=str(Path(directory) / "new"), keys=None)
            with mock.patch.object(tool, "package_id", return_value=tool.EU_CONTENT_ID), \
                    mock.patch.object(tool, "run_tool") as run, mock.patch("builtins.print"):
                tool.extract(a)
            self.assertEqual([call.args[1] for call in run.call_args_list], ["pkg_extract", "pkg_extract"])
            self.assertEqual([call.args[2][-2:] for call in run.call_args_list],
                             [["--only", "PARAM.SFO"], ["--only", "EBOOT.BIN"]])

    def test_compare_checks_pins_then_analyses_without_lifting(self):
        with mock.patch.dict(sys.modules, {"addr_map": self.addr}):
            tool = load_tool("eu_review")
        us = SimpleNamespace(toc=0x10000, info={}, containing=lambda x: None)
        eu = SimpleNamespace(toc=0x20000, info={}, containing=lambda x: None)
        with tempfile.TemporaryDirectory() as directory:
            a = SimpleNamespace(us="us", eu="eu", deps=directory,
                                scratch=str(Path(directory) / "compare"), required=[])
            with mock.patch.object(tool, "checked_program", side_effect=[Path(directory) / "us", Path(directory) / "eu"]) as pin, \
                    mock.patch.object(tool, "run_tool") as run, \
                    mock.patch.object(tool.addr_map, "Program", side_effect=[us, eu]), \
                    mock.patch.object(tool, "source_inventory"), mock.patch("builtins.print"):
                tool.compare(a)
            self.assertEqual(pin.call_args_list, [mock.call("us", "us"), mock.call("eu", "eu")])
            self.assertEqual([call.args[1] for call in run.call_args_list],
                             ["ppu_loader", "find_functions", "ppu_loader", "find_functions"])
            summary = json.loads((Path(a.scratch) / "review" / "programs.json").read_text())
            self.assertFalse(summary["crossplay_proven"])

    def test_inventory_includes_c_suffixes_without_truncating_long_literals(self):
        with mock.patch.dict(sys.modules, {"addr_map": self.addr}):
            tool = load_tool("eu_review")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src").mkdir()
            (root / "review").mkdir()
            (root / "src" / "fake.cpp").write_text(
                "auto a = 0x12345u; auto b = 0x23456ULL; auto c = 0X34567UL;\n"
                "auto d = 0x123456789ULL; auto e = 0x123;\n", encoding="utf-8")
            tool.source_inventory(root / "review", source_root=root)
            with (root / "review" / "source_literals.csv").open(newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual([r["literal"] for r in rows], ["0x12345", "0x23456", "0X34567"])
            self.assertTrue(all(r["classification"] == "unclassified" for r in rows))


if __name__ == "__main__":
    unittest.main()
