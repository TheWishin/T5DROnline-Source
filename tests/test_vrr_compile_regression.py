"""Source-only guard for the patch 0103/upstream present-sample collision.

The maintainer's Windows build reports an existing ld_present_sample typedef
in rsx_live_draw.c. Keep that legacy measurement type and the pacing sample in
separate namespaces. No compiler, dependency checkout or game is needed.
"""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "patches/ps3recomp/0103-vrr-pacing.patch"


class PresentSampleType(unittest.TestCase):
    def test_pacing_sample_does_not_redeclare_upstream_measurement_type(self):
        patch = PATCH.read_text(encoding="utf-8")
        section = patch.split(
            "diff --git a/libs/video/rsx_live_draw.c b/libs/video/rsx_live_draw.c\n", 1
        )[1].split("\ndiff --git ", 1)[0]
        added = "\n".join(line[1:] for line in section.splitlines()
                          if line.startswith("+") and not line.startswith("+++"))
        # The legacy type already exists upstream. Merely adding members to a
        # second declaration still conflicts; the pacing type needs its own tag
        # and typedef, including both pointer declarations which access it.
        self.assertNotRegex(added, r"\bld_present_sample\b")
        match = re.search(r"typedef struct (\w+) \{(.*?)\}\s*(\w+);", added, re.S)
        self.assertIsNotNone(match)
        tag, fields, alias = match.groups()
        self.assertEqual(tag, "ld_pace_present_sample")
        self.assertEqual(alias, tag)
        self.assertIn("hp_target target;", fields)
        self.assertIn("LONGLONG ready, entry, returned, wait_ticks, wake_error;", fields)
        self.assertIn("static ld_pace_present_sample g_present_sample;", added)
        self.assertIn("const ld_pace_present_sample* ps = &g_present_sample;", added)
        self.assertIn("ld_pace_present_sample* ps = &g_present_sample;", added)
        # The existing upstream present-measurement feature remains called.
        self.assertIn("ld_present_measure_record(g_ld_frames + 1u);", section)


if __name__ == "__main__":
    unittest.main()
