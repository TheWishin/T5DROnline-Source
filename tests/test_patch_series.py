"""Source-only checks for the integrated runtime patch sequence; no dependency tree."""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
PATCH_DIR = ROOT / "patches" / "ps3recomp"


class PatchSeries(unittest.TestCase):
    def test_filename_order_has_unique_increasing_numbers(self):
        names = sorted(path.name for path in PATCH_DIR.glob("*.patch"))
        numbers = []
        for name in names:
            match = re.fullmatch(r"(\d{4})-.+\.patch", name)
            self.assertIsNotNone(match, name)
            numbers.append(int(match.group(1)))
        self.assertEqual(len(numbers), len(set(numbers)), "duplicate patch numbers")
        self.assertEqual(numbers, sorted(numbers))

    def test_draft_overlays_precede_existing_platform_patches_and_pacing(self):
        names = sorted(path.name for path in PATCH_DIR.glob("*.patch"))
        expected = [
            "0088-online-boot-overlay.patch",
            "0089-ingame-rematch-overlay.patch",
            "0100-macos-metal-slot-wait-warning.patch",
            "0101-macos-fps-slow-frames.patch",
            "0102-macos-pad-file2.patch",
            "0103-vrr-pacing.patch",
            "0104-low-end.patch",
            "0105-warmup-hidden.patch",
            "0106-kernel-edge.patch",
            "0107-picture-format.patch",
            "0109-picture-copy-scissor.patch",
            "0110-always-left-split-hud.patch",
            "0111-always-left-kernel-copy.patch",
            "0112-always-left-copy-any-unit.patch",
            "0113-spu-regpromo.patch",
            "0114-vmx-four-lanes.patch",
            "0115-overlay-status-layer.patch",
        ]
        self.assertEqual([name for name in names if name >= "0088-"], expected)


if __name__ == "__main__":
    unittest.main()
