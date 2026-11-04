"""Online feel + rollback capacity (docs/NETPLAY.md "Online feel and rollback capacity") and the connection line:
the pure C++ policy, and how the netplay core, the rollback loop, the runtime's overlay patch and the launcher are
wired. No game, socket or server."""
import os
import re
import subprocess
import tempfile
import unittest

from helpers import ROOT


def read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


class Policy(unittest.TestCase):
    def test_native_policy(self):
        from test_always_left import compiler, build
        vcvars, clang = compiler()
        with tempfile.TemporaryDirectory() as directory:
            exe = os.path.join(directory, "rollback_feel_test.exe")
            build(vcvars, clang, os.path.join(ROOT, "tests", "c", "rollback_feel_test.cpp"), exe, "/std:c++17 /EHsc")
            result = subprocess.run([exe], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertRegex(result.stdout, r"PASS \d+ checks")


class Wire(unittest.TestCase):
    """An older game must still connect: no protocol version change, the cost rides behind the HELLO's 12 bytes."""

    def setUp(self):
        self.core = read("src", "netplay", "netplay_core.cpp")

    def test_protocol_version_unchanged(self):
        self.assertIn("constexpr uint8_t  kVersion  = 4;", self.core)

    def test_hello_cost_is_optional_and_after_the_extension(self):
        self.assertIn("constexpr uint32_t kHelloRbCost = 4u;", self.core)
        self.assertIn("struct HelloCost { uint8_t feel; uint8_t cap; uint16_t live_us; uint16_t restore_us; uint16_t resim_us; };",
                      self.core)
        # an older game copies at most sizeof(HelloExt) and ignores the rest (its own receive code, unchanged here)
        self.assertIn("memcpy(&x, h + 1, (size_t)std::min<int>(n - (int)sizeof(Hdr), (int)sizeof x));", self.core)
        # the cost is read only when flagged and long enough
        self.assertIn("(x.flags & kHelloRbCost) && n >= (int)(sizeof(Hdr) + sizeof(HelloExt) + sizeof(HelloCost))",
                      self.core)
        # the lockstep (no rollback offer) sends the old HELLO size
        self.assertIn("s.rb_offer ? (int)sizeof p : (int)(sizeof p.h + sizeof p.x)", self.core)

    def test_only_the_hosts_auto_pick_changes(self):
        # the fixed values (both players set the same number, the lobby's ranked / far-match value) are untouched
        decide = self.core[self.core.index("void decide_rb_delay_locked()"):]
        decide = decide[:decide.index("\nvoid send_reject")]
        both = decide.index("both players set %d")
        feel = decide.index("feel::decide(")
        self.assertLess(both, feel)
        self.assertIn("if (s.mode == Mode::Host) {", decide)
        self.assertIn("if (pick > s.delay) pick = s.delay;", decide)

    def test_feel_setting_parsed(self):
        self.assertIn('s.rb_feel = feel::parse(env("T5_RB_NET_FEEL"));', self.core)


class Measure(unittest.TestCase):
    def test_rollback_loop_measures_fights_only_and_reports(self):
        rb = read("src", "rollback", "rb_net.cpp")
        self.assertIn("np::rb_cost_note(", rb)
        self.assertIn("if (g_cost.prev_ok && fighting_now())", rb)
        self.assertIn("cost_flush(true);", rb)
        self.assertIn("g_cost.wall_ms += ms; g_cost.wall_n++;", rb)      # the live frame as wall time (early_commit)
        self.assertIn("bool line_stats(uint32_t* rollbacks, uint32_t* deepest)", rb)


class Line(unittest.TestCase):
    def test_line_reads_only_and_draws_in_the_status_layer(self):
        src = read("src", "netplay", "net_line.cpp")
        self.assertIn("constexpr unsigned kLayer = 2;", src)
        self.assertIn("VK_F3", src)
        self.assertNotIn("wr32", src)
        self.assertNotIn("vm_base", src)
        hooks = read("src", "netplay", "t5_hooks.cpp")
        self.assertIn("if (!rb::net::bypass() && ctx->thread_id == (g_main_tid != ~0ull ? g_main_tid : 1)) "
                      "t5_net_line_frame();", hooks)

    def test_runtime_patch_composites_layer_two(self):
        patch = read("patches", "ps3recomp", "0115-overlay-status-layer.patch")
        self.assertIn("+#define OVL_LAYERS 3", patch)
        self.assertIn("+    const ovl_list* st = &g_layers[2];", patch)
        self.assertIn("+            if (it.kind == 1) it.text += g_pub.ntext;", patch)

    def test_runtime_patch_headless(self):
        """Apply every patch's overlay part in order and run a small harness: layer 2 is drawn over layer 0 and
        over layer 1, and clearing it leaves the others."""
        import shutil
        compiler = os.environ.get("CC")
        if not compiler and os.name != "nt":
            compiler = shutil.which("cc") or shutil.which("clang") or shutil.which("gcc")
        if not compiler:
            self.skipTest("set CC to a C compiler for the standalone overlay harness")
        git = shutil.which("git")
        if not git:
            self.skipTest("git is needed to apply the patches")
        patches = sorted(p for p in os.listdir(os.path.join(ROOT, "patches", "ps3recomp")) if p.endswith(".patch"))
        with tempfile.TemporaryDirectory() as d:
            subprocess.run([git, "init", "-q", d], check=True)
            for name in patches:
                text = read("patches", "ps3recomp", name)
                if "libs/video/rsx_overlay." not in text and "libs/video/rsx_picture_rect." not in text:
                    continue
                subprocess.run([git, "-C", d, "apply", "--whitespace=nowarn", "--include=libs/video/rsx_overlay.*",
                                "--include=libs/video/rsx_picture_rect.*",
                                os.path.join(ROOT, "patches", "ps3recomp", name)], check=True)
            work = os.path.join(d, "libs", "video")
            with open(os.path.join(work, "t.c"), "w", encoding="utf-8") as f:
                f.write(HARNESS)
            exe = os.path.join(d, "t.exe" if os.name == "nt" else "t")
            cmd = [compiler, "-std=c17", "-DRSX_OVERLAY_NO_D3D", os.path.join(work, "rsx_overlay.c"),
                   os.path.join(work, "t.c"), "-o", exe]
            cmd += ["-lgdi32", "-luser32"] if os.name == "nt" else ["-pthread", "-lm"]
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            subprocess.run([exe], check=True, capture_output=True, text=True)


HARNESS = r'''
#include "rsx_overlay.h"
#include <assert.h>
static rsx_overlay_quad q[16384];
static int layout(void) { return rsx_overlay_layout(1280,720,1280,720,q,16384); }
int main(void) {
    rsx_overlay_begin(); rsx_overlay_rect(1,1,10,10,0x111111FFu); rsx_overlay_end();
    rsx_overlay_begin_layer(2); rsx_overlay_rect(5,5,10,10,0x222222FFu); rsx_overlay_end();
    assert(layout()==2 && q[0].rgba==0x111111FFu && q[1].rgba==0x222222FFu);
    rsx_overlay_begin_layer(1); rsx_overlay_rect(7,7,10,10,0x333333FFu); rsx_overlay_end();
    assert(layout()==2 && q[0].rgba==0x333333FFu && q[1].rgba==0x222222FFu);
    rsx_overlay_clear_layer(2);
    assert(layout()==1 && q[0].rgba==0x333333FFu);
    rsx_overlay_clear_layer(1);
    assert(layout()==1 && q[0].rgba==0x111111FFu);
    rsx_overlay_begin_layer(2); rsx_overlay_rect(5,5,10,10,0x222222FFu); rsx_overlay_end();
    rsx_overlay_clear();
    assert(layout()==1 && q[0].rgba==0x222222FFu);
    rsx_overlay_begin_layer(3); rsx_overlay_rect(1,1,10,10,0x444444FFu); rsx_overlay_end();
    assert(layout()==1 && q[0].rgba==0x222222FFu);
    return 0;
}
'''

if __name__ == "__main__":
    unittest.main()
