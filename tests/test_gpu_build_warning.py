"""Offline pre-build GPU warning regressions; no adapter probing or build."""
import os
import sys
import unittest
from unittest import mock

from helpers import ROOT

sys.path.insert(0, os.path.join(ROOT, "launcher"))
import gpu_support  # noqa: E402


def gpu(name):
    return (name, "driver", "date", None)


class GraphicsWarningTest(unittest.TestCase):
    def test_warns_before_first_game_log_exists(self):
        with mock.patch("problem_report.gpu_info", return_value=[gpu("Intel(R) HD Graphics 4400")]):
            warning = gpu_support.build_warning()
        self.assertEqual(warning["values"], {"gpus": "Intel(R) HD Graphics 4400"})
        self.assertIn("Continue building?", warning["message"])
        self.assertIn("may not run", warning["message"])

    def test_haswell_classes_and_older_names(self):
        for name in ("Intel HD Graphics", "Intel(R) HD Graphics 2000", "Intel HD Graphics 3000",
                     "Intel HD Graphics 4000", "Intel HD Graphics 4200", "Intel HD Graphics 4600",
                     "Intel HD Graphics 5000", "Intel Iris Graphics 5100", "Intel Iris Pro Graphics 5200"):
            with self.subTest(name=name):
                self.assertIsNotNone(gpu_support.build_warning([gpu(name)]))

    def test_unknown_is_not_declared_supported_or_warned_by_broad_intel_match(self):
        for name in ("Intel UHD Graphics 620", "Intel HD Graphics 44000", "Intel HD Graphics 460",
                     "Intel HD Graphics 530", "Intel HD Graphics 5500", "Intel Iris Xe Graphics",
                     "NVIDIA GeForce RTX 3090", "AMD Radeon Graphics", "Unknown adapter"):
            with self.subTest(name=name):
                self.assertIsNone(gpu_support.build_warning([gpu(name)]))

    def test_hybrid_system_still_explains_adapter_choice(self):
        warning = gpu_support.build_warning([gpu("Intel HD Graphics 4400"), gpu("NVIDIA GeForce GTX 960M")])
        self.assertEqual(warning["values"]["gpus"], "Intel HD Graphics 4400")
        self.assertIn("another graphics card", warning["message"])

    def test_missing_and_malformed_adapter_data(self):
        self.assertIsNone(gpu_support.build_warning([]))
        self.assertIsNone(gpu_support.build_warning([None, (), 123, (None,), "Intel HD Graphics 4400"]))
        with mock.patch("problem_report.gpu_info", side_effect=OSError("unavailable")):
            self.assertIsNone(gpu_support.build_warning())

    def test_duplicate_adapters_only_appear_once(self):
        warning = gpu_support.build_warning([gpu("Intel HD Graphics 4400"), gpu("Intel HD Graphics 4400")])
        self.assertEqual(warning["values"]["gpus"], "Intel HD Graphics 4400")


if __name__ == "__main__":
    unittest.main()
