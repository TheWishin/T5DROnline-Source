"""Source-only runtime patch regressions; no compiler, game, output files or sockets.

The dependency source is intentionally absent. These checks verify the patch's
per-call sample invalidation and hunk integrity, not a real Present lifecycle.
"""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
PATCH_DIR = ROOT / "patches/ps3recomp"


def added_source(patch):
    return "\n".join(line[1:] for line in patch.splitlines()
                     if line.startswith("+") and not line.startswith("+++"))


class PatchAudit(unittest.TestCase):
    def test_present_sample_invalidated_before_any_frame_work(self):
        patch = (PATCH_DIR / "0103-vrr-pacing.patch").read_text(encoding="utf-8")
        # Keep context: ld_begin_recording is an unchanged line in the hunk.
        current = "\n".join(line[1:] for line in patch.splitlines()
                            if line.startswith(("+", " ")) and not line.startswith("+++"))
        start = current.index("static void ld_present_body(u32 buffer_id, int display_synced, const hp_target* pace)\n{")
        prefix = current[start:current.index("ld_begin_recording();", start)]
        for reset in (
            "memset(&g_present_sample.target, 0, sizeof g_present_sample.target);",
            "if (pace) g_present_sample.target = *pace;",
            "g_present_sample.ready = g_present_sample.entry = g_present_sample.returned = 0;",
            "g_present_sample.wait_ticks = g_present_sample.wake_error = 0;",
            "g_present_sample.hr = S_FALSE;",
            "g_present_sample.valid = g_present_sample.fallback = 0;",
            'g_present_sample.status = "no_present";',
        ):
            self.assertIn(reset, prefix)
        # Previous actual-Present history must survive until interval validation.
        self.assertNotRegex(prefix, r"g_present_sample\.previous_\w+\s*=")
        self.assertNotIn("memset(&g_present_sample,", prefix)
        added = added_source(patch)
        self.assertIn('strcmp(g_present_sample.status, "ok") == 0 ? g_present_sample.entry : 0', added)
        self.assertIn('ps->status = present_hr == DXGI_STATUS_OCCLUDED', added)
        self.assertIn("ps->valid = strcmp(ps->status, \"ok\") == 0 && ps->previous_entry > 0", added)

    def test_changed_runtime_patches_have_exact_hunk_counts(self):
        names = (
            "0088-online-boot-overlay.patch", "0089-ingame-rematch-overlay.patch",
            "0103-vrr-pacing.patch", "0104-low-end.patch", "0105-warmup-hidden.patch",
            "0106-kernel-edge.patch", "0107-picture-format.patch", "0109-picture-copy-scissor.patch",
            "0110-always-left-split-hud.patch",
        )
        header = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
        for name in names:
            lines = (PATCH_DIR / name).read_text(encoding="utf-8").splitlines()
            for index, line in enumerate(lines):
                match = header.match(line)
                if not match:
                    continue
                old = new = 0
                for item in lines[index + 1:]:
                    if item.startswith(("@@ ", "diff --git ")):
                        break
                    if item.startswith(" "):
                        old += 1
                        new += 1
                    elif item.startswith("-"):
                        old += 1
                    elif item.startswith("+"):
                        new += 1
                    elif not item.startswith("\\"):
                        break
                with self.subTest(patch=name, line=index + 1):
                    self.assertEqual(old, int(match.group(2) or 1))
                    self.assertEqual(new, int(match.group(4) or 1))


if __name__ == "__main__":
    unittest.main()
