""""Always left" (1.1.9, casual matches only; docs/NETPLAY.md "Always left"): the player the game made P2 sees the
fight with themselves on the left. No game needed.

* tests/c/always_left_test.cpp (src/netplay/always_left.h): when this PC shows a fight mirrored (online P2,
  offline Versus; never the attract demo, a replay or outside a fight) and the input mapping (left <-> right,
  stick X mirrored, nothing else).
* tests/c/always_left_render_test.c (ps3recomp patch 0086, libs/video/rsx_always_left.h, taken from the patch
  itself): the vertex program run on the CPU, and the HUD laid out mirrored with strings kept readable.
  With a patched ps3recomp tree (PS3RECOMP_DIR) the test program is also checked against the runtime's
  decompiler.
* The wiring: the swap is in the exchanged local sample (both PCs simulate the same input), the frame hook
  never runs in a re-simulated frame, the renderer patch writes no guest memory, the launcher setting
  (off by default) gives T5_ALWAYS_LEFT=1.
* Casual only (1.1.9): the lobby's match kind -> T5_NET_CASUAL (a challenge / invite / unranked room: 1; ranked,
  Quick, a tournament set: 0), the setting in every match's environment, the game reads both per session.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

from helpers import ROOT
from test_ps_hid import find_vcvars
from test_stage_blur import find_ps3recomp

sys.path.insert(0, os.path.join(ROOT, "launcher"))
import core  # noqa: E402
import problem_report as report  # noqa: E402

PATCH = os.path.join(ROOT, "patches", "ps3recomp", "0086-always-left.patch")
LLVM_CL = r"C:\Program Files\LLVM\bin\clang-cl.exe"


def text(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def new_file_from_patch(patch_text, path):
    """The content of a file the patch adds (all '+' lines of its one hunk)."""
    out, inside = [], False
    for line in patch_text.splitlines():
        if line.startswith("diff --git "):
            inside = line.endswith(" b/" + path)
            continue
        if not inside or line.startswith(("+++", "---", "@@", "new file", "index ")):
            continue
        if line.startswith("+"):
            out.append(line[1:])
    return "\n".join(out) + "\n"


def compiler():
    if os.name != "nt":
        raise unittest.SkipTest("built with the Windows C compiler")
    vcvars = find_vcvars()
    clang = shutil.which("clang-cl") or (LLVM_CL if os.path.isfile(LLVM_CL) else None)
    if not vcvars or not clang:
        raise unittest.SkipTest("no clang-cl / Visual Studio build tools")
    return vcvars, clang


def build(vcvars, clang, src, exe, flags=""):
    obj = os.path.splitext(exe)[0] + ".obj"
    cmd = f'"{vcvars}" >nul 2>&1 && "{clang}" /nologo /O1 /W3 /D_CRT_SECURE_NO_WARNINGS {flags} "{src}" /Fe:"{exe}" /Fo:"{obj}"'
    r = subprocess.run(f'cmd /s /c "{cmd}"', capture_output=True, text=True, timeout=600)
    if not os.path.isfile(exe):
        raise AssertionError(f"could not build {src}: " + (r.stdout + r.stderr)[-2000:])


class GameLayer(unittest.TestCase):
    def test_c_unit_test_passes(self):
        vcvars, clang = compiler()
        with tempfile.TemporaryDirectory() as d:
            exe = os.path.join(d, "always_left_test.exe")
            build(vcvars, clang, os.path.join(ROOT, "tests", "c", "always_left_test.cpp"), exe, "/std:c++17 /EHsc")
            r = subprocess.run([exe], capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout[-3000:])
        self.assertRegex(r.stdout, r"(?m)^PASS \d+ checks$")


class Renderer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(PATCH, encoding="utf-8") as f:
            cls.patch = f.read()

    def test_c_unit_test_passes(self):
        vcvars, clang = compiler()
        with tempfile.TemporaryDirectory() as d:
            hdr = new_file_from_patch(self.patch, "libs/video/rsx_always_left.h")
            self.assertIn("al_vp_eval", hdr)
            with open(os.path.join(d, "rsx_always_left.h"), "w", encoding="utf-8") as f:
                f.write(hdr)
            flags = f'/I "{d}"'
            tree = find_ps3recomp()
            if tree:      # the runtime's own decompiler reads the test's program the same way
                flags += " /DAL_WITH_DECOMPILER " + " ".join(
                    f'/I "{os.path.join(tree, *p)}"' for p in (("libs", "video"), ("libs",), ("runtime",), ("include",)))
            exe = os.path.join(d, "always_left_render_test.exe")
            build(vcvars, clang, os.path.join(ROOT, "tests", "c", "always_left_render_test.c"), exe, flags)
            r = subprocess.run([exe], capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout[-3000:])
        self.assertRegex(r.stdout, r"(?m)^PASS \d+ checks$")

    def test_patch_is_presentation_only(self):
        added = [l[1:] for l in self.patch.splitlines() if l.startswith("+") and not l.startswith("+++")]
        body = "\n".join(added)
        for guest_write in ("vm_write", "wr32(", "wr16(", "vm_base", "guest_write"):
            self.assertNotIn(guest_write, body)
        files = re.findall(r"^diff --git a/(\S+)", self.patch, re.M)
        self.assertEqual(sorted(files), ["libs/video/rsx_always_left.h", "libs/video/rsx_live_draw.c",
                                         "libs/video/rsx_live_draw.h"])
        self.assertIn("void rsx_live_draw_set_always_left(int on)", body)
        # off unless the game asks: every change sits behind g_al.active or its request
        self.assertIn("if (g_al.active || g_al_req) ld_al_draw(", body)
        self.assertIn("(al_mirror || al_dx_px != 0.0f)", body)

    def test_series_order(self):
        names = sorted(n for n in os.listdir(os.path.join(ROOT, "patches", "ps3recomp")) if n.endswith(".patch"))
        # in the series, its number taken once (the Mac patches 0100-0102 come later)
        self.assertIn("0086-always-left.patch", names)
        nums = [n[:4] for n in names]
        self.assertEqual(len(nums), len(set(nums)), "a patch number used twice")


class Wiring(unittest.TestCase):
    def test_swap_in_the_exchanged_sample(self):
        core_src = text("src", "netplay", "netplay_core.cpp")
        m = re.search(r"PadInput sample_local\(uint32_t f\)\n\{(.*?)\n\}", core_src.replace("\r\n", "\n"), re.S)
        self.assertTrue(m)
        self.assertIn("return always_left_input(in);", m.group(1))
        # the menu inject (direct fight driving the select screen) is never swapped
        self.assertLess(m.group(1).index("g_local_inject_on"), m.group(1).index("always_left_input"))

    def test_frame_hook_not_in_resimulation(self):
        hooks = text("src", "netplay", "t5_hooks.cpp")
        self.assertIn("if (!rb::net::bypass()) t5_always_left_frame();", hooks)
        self.assertIn("if (t5_always_left_enabled() && !t5_always_left_df_pads())", hooks)
        self.assertIn('"cellPadGetData(always left)", t5_always_left_pad_read', hooks)

    def test_game_side_writes_only_the_pad_data_the_game_reads(self):
        src = text("src", "netplay", "always_left.cpp").replace("\r\n", "\n")
        # writes: only port 2's pad data the game asked for (inside t5_always_left_pad_fix)
        start = src.index('extern "C" void t5_always_left_pad_fix')
        fn = src[start:src.index("\n}\n", start)]
        self.assertEqual(src.count("wr16("), fn.count("wr16(") + 1)   # + its definition
        self.assertIn("port != 1", fn)
        self.assertNotIn("wr32(", src)
        # both offline pad hooks mirror port 2 through it; the direct fight's menu inject does not
        df = text("src", "directfight", "df_hooks.cpp").replace("\r\n", "\n")
        m = re.search(r"void h_cellPadGetData\(ppu_context\* ctx\)\n\{(.*?)\n\}", df, re.S)
        self.assertEqual(m.group(1).count("t5_always_left_pad_fix(port, ea)"), 2)
        self.assertLess(m.group(1).index("g_inject_on"), m.group(1).index("t5_always_left_pad_fix"))


class Setting(unittest.TestCase):
    def path(self, saved=None):
        import json
        d = tempfile.mkdtemp(prefix="t5dr-al")
        self.addCleanup(shutil.rmtree, d, True)
        p = os.path.join(d, "launcher.json")
        if saved is not None:
            with open(p, "w", encoding="utf-8") as f:
                json.dump(saved, f)
        return p

    def test_off_by_default_on_gives_env(self):
        s = core.Settings(self.path())
        self.assertFalse(s["always_left"])
        self.assertNotIn("T5_ALWAYS_LEFT", s.env_overrides())
        s["always_left"] = True
        self.assertEqual(s.env_overrides()["T5_ALWAYS_LEFT"], "1")

    def test_saved_and_loaded(self):
        p = self.path()
        s = core.Settings(p)
        s["always_left"] = True
        s.save()
        self.assertTrue(core.Settings(p)["always_left"])
        self.assertEqual(core.Settings(p).env_overrides()["T5_ALWAYS_LEFT"], "1")

    def test_problem_report(self):
        self.assertIn("always_left", report.SETTING_KEYS)
        lines = report.settings_lines({"always_left": True})
        self.assertIn("Always see me on the left (casual matches): yes", lines)

    def test_launcher_has_the_checkbox(self):
        ui = text("launcher", "t5dr_launcher.pyw")
        self.assertIn('t("Always see me on the left")', ui)
        self.assertIn('self.settings["always_left"] = bool(self.always_left_var.get())', ui)
        self.assertIn("t(core.ALWAYS_LEFT_HELP)", ui)
        self.assertIn("Casual matches only", core.ALWAYS_LEFT_HELP)


LOBBY = os.path.join(ROOT, "lobby")
if LOBBY not in sys.path:
    sys.path.insert(0, LOBBY)


class CasualOnly(unittest.TestCase):
    """1.1.9: the owner's rule -- ranked keeps the server's sides by coin and the game's own picture; casual matches
    get the choice."""

    def test_match_kind(self):
        from t5lobby.handover import match_casual
        self.assertTrue(match_casual({"ranked": False, "casual": {"swap": True}}))          # challenge, invite, room
        self.assertFalse(match_casual({"ranked": False}))                                   # the Quick queue
        self.assertFalse(match_casual({"ranked": True}))
        self.assertFalse(match_casual({"ranked": True, "casual": {"swap": True}}))          # (never, whatever it says)
        self.assertFalse(match_casual({"casual": {"swap": True}, "set": {"tournament": "t1"}}))
        self.assertFalse(match_casual(None))

    def test_ticket_env(self):
        from t5lobby.handover import MatchTicket
        kw = dict(match_id="m", role="join", slot=1, local_port=1, peer=("127.0.0.1", 2), path="lan", rtt_ms=1.0,
                  jitter_ms=0.0, delay=2)
        self.assertEqual(MatchTicket(**kw).game_env()["T5_NET_CASUAL"], "0")
        self.assertEqual(MatchTicket(casual=True, **kw).game_env()["T5_NET_CASUAL"], "1")

    def test_client_ticket_from_match_start(self):
        src = text("lobby", "t5lobby", "client.py")
        self.assertIn("casual=match_casual(msg)", src)

    def test_every_match_gets_the_setting(self):
        from t5lobby.handover import MatchTicket
        from t5lobby.match_driver import MatchDriver
        d = tempfile.mkdtemp(prefix="t5dr-al")
        self.addCleanup(shutil.rmtree, d, True)
        on = [True]
        drv = MatchDriver(client=None, launch=lambda env: None, workdir=d, mode="process", always_left=lambda: on[0])
        tk = MatchTicket(match_id="m", role="join", slot=1, local_port=1, peer=("127.0.0.1", 2), path="lan",
                         rtt_ms=1.0, jitter_ms=0.0, delay=2, casual=True)
        env = drv.match_env({}, tk)
        self.assertEqual((env["T5_ALWAYS_LEFT"], env["T5_NET_CASUAL"]), ("1", "1"))
        on[0] = False                       # changed in the launcher: the next match has it
        self.assertEqual(drv.match_env({}, tk)["T5_ALWAYS_LEFT"], "0")
        plain = MatchDriver(client=None, launch=lambda env: None, workdir=d, mode="process")
        self.assertNotIn("T5_ALWAYS_LEFT", plain.match_env({}, tk))      # (no launcher setting: the process's)

    def test_game_reads_the_session_values(self):
        src = text("src", "netplay", "always_left.cpp")
        self.assertIn('t5_env("T5_ALWAYS_LEFT")', src)
        self.assertIn('t5_env("T5_NET_CASUAL")', src)
        hdr = text("src", "netplay", "always_left.h")
        self.assertIn("return f.local_slot == 1 && f.casual;", hdr)


if __name__ == "__main__":
    unittest.main()
