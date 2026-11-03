"""Source-only regressions for the online boot screen; no game/runtime needed.

The driver policy has its own tests. These checks guard the presentation
integration that otherwise could silently expose the title with training off.
"""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


def function_body(source, signature):
    start = source.index("{", source.index(signature))
    depth = 1
    for end in range(start + 1, len(source)):
        depth += (source[end] == "{") - (source[end] == "}")
        if depth == 0:
            return source[start + 1:end]
    raise AssertionError("unfinished function: " + signature)


class OnlineBootOverlayTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "src/training/training.cpp").read_text(encoding="utf-8")

    def test_plain_opaque_screen_and_clear_text(self):
        body = function_body(self.source, 'extern "C" void t5_boot_cover_publish(void)')
        self.assertRegex(body, r"rsx_overlay_rect\(0\.0f, 0\.0f, RSX_OVERLAY_CANVAS_W,"
                               r"\s*RSX_OVERLAY_CANVAS_H,\s*RSX_OVL_RGBA\(0, 0, 0, 255\)\)")
        self.assertIn('RSX_OVL_CENTER, "Connecting..."', body)
        self.assertLess(body.index("rsx_overlay_rect("), body.index("rsx_overlay_text("))
        self.assertLess(body.index("rsx_overlay_text("), body.index("rsx_overlay_end();"))

    def test_cover_runs_with_training_off(self):
        body = function_body(self.source, 'extern "C" void t5_training_frame(ppu_context* ctx)')
        publish = body.index("t5_boot_cover_publish();")
        stop = body.index("if (g_boot_cover_shown) return;")
        self.assertLess(publish, stop)
        self.assertLess(stop, body.index("if (!g_init) init();"))
        self.assertLess(stop, body.index("g_cfg.mode == kOff"))

    def test_retained_cover_is_only_published_on_transition(self):
        body = function_body(self.source, 'extern "C" void t5_boot_cover_publish(void)')
        self.assertRegex(body, r"if \(t5_df_boot_cover\(\)\)\s*\{\s*if \(!g_boot_cover_shown\)")
        release = body.split("else if (g_boot_cover_shown)", 1)[1]
        self.assertLess(release.index("rsx_live_draw_sync();"), release.index("rsx_overlay_clear();"))
        self.assertIn("g_shown = false;", body)

    def test_covered_select_resets_previous_training_history(self):
        body = function_body(self.source, 'extern "C" void t5_boot_cover_publish(void)')
        acquire = body.split("else if (g_boot_cover_shown)", 1)[0]
        reset_body = function_body(acquire, "if (g_in_fight)")
        for reset in ("g_track.reset();", "g_hist[0].clear();", "g_hist[1].clear();",
                      "g_nresults = 0;", "g_in_fight = false;"):
            self.assertIn(reset, reset_body)

    def test_host_movie_path_gets_the_same_overlay_before_present(self):
        patch = (ROOT / "patches/ps3recomp/0088-online-boot-overlay.patch").read_text(encoding="utf-8")
        self.assertIn("void rsx_live_draw_present_rgba(", patch)
        copy = patch.index("CopyTextureRegion(LDL,")
        overlay = patch.index("rsx_overlay_present(g.dev, LDL, bb, w, h);")
        present = patch.index("b.Transition.StateAfter = D3D12_RESOURCE_STATE_PRESENT;")
        self.assertLess(copy, overlay)
        self.assertLess(overlay, present)
        self.assertIn("ld_bound_invalidate();", patch)

    def test_publisher_never_reads_guest_or_drives_game(self):
        body = function_body(self.source, 'extern "C" void t5_boot_cover_publish(void)')
        body = re.sub(r"/\*.*?\*/|//[^\n]*", " ", body, flags=re.S)
        self.assertNotRegex(body, r"vm_base|\brd(?:8|16|32|64)\(|\bwr(?:8|16|32|64)\("
                                 r"|\bgcall\(|ppu_guest_call|\binject\(|\binit\("
                                 r"|GetTickCount|QueryPerformanceCounter")


if __name__ == "__main__":
    unittest.main()
