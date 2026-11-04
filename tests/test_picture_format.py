"""Picture format and own window size (ps3recomp patch 0107, launcher Settings -> Display / Picture format,
docs/PICTURE_FORMAT.md). No game needed.

* tests/c/picture_rect_test.c, built against the patched runtime source (libs/video/rsx_picture_rect.h), checks
  the rectangles of every format on 26 window shapes; "fit" must be the present before 0107 to the pixel. It
  must print PASS. Skipped without a patched ps3recomp tree (PS3RECOMP_DIR) or a Windows C compiler.
* The launcher: window_size() takes whole numbers in range only, fit_client() keeps the shape inside the work
  area, the settings refuse junk, PS3_PICTURE reaches the game only for a non-default format, an Extra
  settings line overrides it, the problem report names both.
* The patch: the files it touches, the switches the docs name, and that nothing the game sees changes.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

from helpers import ROOT

sys.path.insert(0, os.path.join(ROOT, "launcher"))
import core  # noqa: E402
import problem_report as report  # noqa: E402

PATCH = os.path.join(ROOT, "patches", "ps3recomp", "0107-picture-format.patch")


def text(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def find_ps3recomp():
    cands = [os.environ.get("PS3RECOMP_DIR"), os.path.join(ROOT, "deps", "ps3recomp")]
    try:
        r = subprocess.run(["git", "-C", ROOT, "rev-parse", "--git-common-dir"], capture_output=True, text=True,
                           timeout=20)
        if r.returncode == 0:
            common = os.path.normpath(os.path.join(ROOT, r.stdout.strip()))
            cands.append(os.path.join(os.path.dirname(common), "deps", "ps3recomp"))
    except (OSError, subprocess.SubprocessError):
        pass
    for c in cands:
        p = os.path.join(c or "", "libs", "video", "rsx_picture_rect.h")
        if c and os.path.isfile(p):
            return c
    return None


def find_vcvars():
    pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    vswhere = os.path.join(pf86, "Microsoft Visual Studio", "Installer", "vswhere.exe")
    if os.path.isfile(vswhere):
        r = subprocess.run([vswhere, "-latest", "-products", "*", "-property", "installationPath"],
                           capture_output=True, text=True, timeout=60)
        for line in r.stdout.splitlines():
            p = os.path.join(line.strip(), "VC", "Auxiliary", "Build", "vcvars64.bat")
            if os.path.isfile(p):
                return p
    return None


class Rectangles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.name != "nt":
            raise unittest.SkipTest("built with the Windows toolchain")
        cls.tree = find_ps3recomp()
        if not cls.tree:
            raise unittest.SkipTest("no ps3recomp tree with patch 0107 (PS3RECOMP_DIR)")
        vcvars = find_vcvars()
        clang = shutil.which("clang-cl") or (r"C:\Program Files\LLVM\bin\clang-cl.exe"
                                             if os.path.isfile(r"C:\Program Files\LLVM\bin\clang-cl.exe") else None)
        if not vcvars or not (clang or shutil.which("cl")):
            raise unittest.SkipTest("no Windows C compiler")
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        exe = os.path.join(cls.tmp.name, "picture_rect_test.exe")
        src = os.path.join(ROOT, "tests", "c", "picture_rect_test.c")
        cc = f'"{clang}"' if clang else "cl"
        cmd = (f'"{vcvars}" >nul 2>&1 && {cc} /nologo /O1 /W3 /I "{os.path.join(cls.tree, "libs", "video")}" '
               f'"{src}" /Fe:"{exe}" /Fo:"{os.path.join(cls.tmp.name, "picture_rect_test.obj")}"')
        r = subprocess.run(f'cmd /s /c "{cmd}"', capture_output=True, text=True, timeout=600)
        if not os.path.isfile(exe):
            raise AssertionError("could not build tests/c/picture_rect_test.c: " + (r.stdout + r.stderr)[-1500:])
        cls.exe = exe

    def test_c_unit_test_passes(self):
        r = subprocess.run([self.exe], capture_output=True, text=True, timeout=120, cwd=self.tmp.name)
        tail = r.stdout[-3000:]
        self.assertEqual(r.returncode, 0, tail)
        self.assertRegex(r.stdout, r"(?m)^PASS \d+ checks$", tail)


class WindowSize(unittest.TestCase):
    def test_whole_numbers_in_range(self):
        self.assertEqual(core.window_size(1920, 1200), (1920, 1200))
        self.assertEqual(core.window_size("2160", " 1440 "), (2160, 1440))
        self.assertEqual(core.window_size(*core.WINDOW_SIZE_MIN), core.WINDOW_SIZE_MIN)
        self.assertEqual(core.window_size(*core.WINDOW_SIZE_MAX), core.WINDOW_SIZE_MAX)

    def test_refused(self):
        for w, h in ((0, 720), (1280, 0), (-1280, 720), (1280.5, 720), ("1280.5", "720"), ("", "720"),
                     ("abc", "720"), (True, 720), (None, None), (319, 720), (1280, 239), (7681, 720),
                     (1280, 4321), ("99999999999", "720"), ("+1280", "720"), ("1e3", "720"), ([1280], 720),
                     ("1\u00b280", "720"), ("1280", "7\u00b20"), ("\u0661\u0662\u0668\u0660", "720")):
            self.assertIsNone(core.window_size(w, h), (w, h))

    def test_fit_client_keeps_the_shape(self):
        self.assertEqual(core.fit_client(1920, 1200, 2560, 1400), (1920, 1200))     # fits: unchanged
        w, h = core.fit_client(2560, 1600, 1920, 1040)                              # too big: scaled down
        self.assertLessEqual(w, 1920 - 16)
        self.assertLessEqual(h, 1040 - 40)
        self.assertAlmostEqual(w / h, 1.6, delta=0.01)
        w, h = core.fit_client(2160, 1440, 1280, 760)
        self.assertAlmostEqual(w / h, 1.5, delta=0.01)
        self.assertEqual(core.fit_client(1280, 720, 1280, 760), (1264, 711))         # the old 16:9 rule

    def test_custom_display_is_offered(self):
        self.assertIn("custom", dict(core.DISPLAY_MODES))


class SettingsAndEnv(unittest.TestCase):
    def settings(self, saved):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        p = os.path.join(d, "launcher.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(saved, f)
        return core.Settings(p)

    def test_defaults_change_nothing(self):
        s = self.settings({})
        self.assertEqual(s["picture"], "fit")
        self.assertEqual(s["display"], "window")
        self.assertNotIn("PS3_PICTURE", s.env_overrides())

    def test_each_format_reaches_the_game(self):
        for key in ("fill", "stretch", "4:3"):
            s = self.settings({"picture": key})
            self.assertEqual(s.env_overrides().get("PS3_PICTURE"), key)

    def test_true_43_offline_tells_the_game(self):
        s = self.settings({"picture": core.TRUE_43})
        env = s.env_overrides()
        self.assertEqual(env.get("PS3_VIDEO_ASPECT"), "4:3")
        self.assertNotIn("PS3_PICTURE", env)       # the present follows the game's 4:3 by itself

    def test_true_43_never_online(self):
        # a game started for online play (or a replay) never gets the game's own 4:3, but the middle-of-the-
        # picture 4:3, which is picture only
        env = self.settings({"picture": core.TRUE_43}).env_overrides()
        env.update({"T5_CTL_DIR": "x"})
        self.assertTrue(core.is_online_env(env))
        core.online_picture_env(env)
        self.assertIsNone(env["PS3_VIDEO_ASPECT"])
        self.assertIsNone(env["PS3_VIDEO_RESOLUTION"])
        self.assertEqual(env["PS3_PICTURE"], core.TRUE_43_ONLINE)
        # an Extra settings line from the player is taken out too; another format is left alone
        env = {"T5_NET_MODE": "replay", "PS3_VIDEO_RESOLUTION": "480", "PS3_PICTURE": "fill"}
        core.online_picture_env(env)
        self.assertEqual((env["PS3_VIDEO_RESOLUTION"], env["PS3_PICTURE"]), (None, "fill"))
        env = {"T5_NET_MODE": "net"}
        core.online_picture_env(env)
        self.assertNotIn("PS3_PICTURE", env)

    def child_env(self, saved, extra_env, inherited=None):
        """The environment GameRun.start really hands the game (Popen mocked; nothing starts)."""
        from unittest import mock
        out = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, out, True)
        os.makedirs(os.path.join(out, "build", "cmake"))
        exe = os.path.join(out, "build", "cmake", "t5dr.exe" if os.name == "nt" else "t5dr")
        open(exe, "wb").close()
        seen = {}

        class Proc:
            pid = 1

            def poll(self):
                return 0

        def popen(cmd, env=None, **kw):
            seen.update(env)
            return Proc()
        with mock.patch.object(core.process_owner, "popen", popen),                 mock.patch.object(core.warmup, "pause_all", return_value=None),                 mock.patch.object(core.warmup, "resume_all"),                 mock.patch.dict(os.environ, inherited or {}):
            core.GameRun(out, self.settings(saved)).start(extra_env=extra_env)
        return seen

    @unittest.skipUnless(os.name == "nt", "Windows' environment ignores the case of names")
    def test_online_filter_takes_every_spelling(self):
        # review picture-120 P1: an Extra settings line "ps3_video_aspect=4:3" reached an online game as
        # PS3_VIDEO_ASPECT=4:3 (getenv on Windows ignores case) -> a 4:3 camera on one PC only = desync
        online = {"T5_CTL_DIR": "ctl"}
        for line in ("ps3_video_aspect=4:3", "Ps3_Video_Aspect=4:3\nps3_video_resolution=480",
                     "PS3_VIDEO_ASPECT=4:3"):
            for picture in ("fit", core.TRUE_43):
                with self.subTest(line=line, picture=picture):
                    env = self.child_env({"picture": picture, "extra_env": line}, online)
                    bad = sorted(k for k in env if k.upper() in ("PS3_VIDEO_ASPECT", "PS3_VIDEO_RESOLUTION"))
                    self.assertEqual(bad, [], env)
                    self.assertEqual(env.get("PS3_PICTURE"), core.TRUE_43_ONLINE)
        # inherited from Windows' own environment: taken out as well
        env = self.child_env({}, online, inherited={"PS3_VIDEO_ASPECT": "4:3"})
        self.assertFalse([k for k in env if k.upper() == "PS3_VIDEO_ASPECT"], env)
        # the same lines offline still reach the game (one spelling)
        env = self.child_env({"extra_env": "ps3_video_aspect=4:3"}, None)
        self.assertEqual([(k, v) for k, v in env.items() if k.upper() == "PS3_VIDEO_ASPECT"],
                         [("PS3_VIDEO_ASPECT", "4:3")])
        # the other online-only filters see every spelling too
        env = self.child_env({"extra_env": "t5_unlock_stages=1\nt5_auto_skip_offline=1"}, online)
        self.assertFalse([k for k in env if k.upper() in ("T5_UNLOCK_STAGES", "T5_AUTO_SKIP_OFFLINE")], env)

    def test_extra_line_later_spelling_wins(self):
        s = self.settings({"picture": "fill", "extra_env": "PS3_PICTURE=stretch\nps3_picture=4:3"})
        env = s.env_overrides()
        if os.name == "nt":
            self.assertEqual([(k, v) for k, v in env.items() if k.upper() == "PS3_PICTURE"], [("PS3_PICTURE", "4:3")])
            self.assertEqual(core.extra_env_override(s, "picture"), "PS3_PICTURE=stretch")
        env = {"ps3_video_aspect": "a", "PS3_VIDEO_ASPECT": "b", "x_y": "c"}
        core.canon_env(env)
        if os.name == "nt":
            self.assertEqual(env, {"PS3_VIDEO_ASPECT": "b", "X_Y": "c"})
        else:
            self.assertEqual(len(env), 3)

    def test_gamerun_applies_it_online(self):
        src = text("launcher", "core.py")
        i = src.index("if is_online_env(env_over):")
        self.assertIn("online_picture_env(env_over)", src[i:i + 800])

    def test_junk_is_refused(self):
        s = self.settings({"picture": "21:9", "display": "huge", "window_w": "big", "window_h": -3})
        self.assertEqual(s["picture"], "fit")
        self.assertEqual(s["display"], "window")
        self.assertEqual((s["window_w"], s["window_h"]), (core.DEFAULTS["window_w"], core.DEFAULTS["window_h"]))
        s = self.settings({"picture": ["fill"], "window_w": 2160, "window_h": 1440, "display": "custom"})
        self.assertEqual(s["picture"], "fit")
        self.assertEqual((s["window_w"], s["window_h"], s["display"]), (2160, 1440, "custom"))

    def test_saved_unicode_digits_fall_back(self):
        # review picture-120 P3: a saved "1\u00b280" made Settings() raise ValueError instead of the default size
        s = self.settings({"display": "custom", "window_w": "1\u00b280", "window_h": "720"})
        self.assertEqual((s["window_w"], s["window_h"]), (core.DEFAULTS["window_w"], core.DEFAULTS["window_h"]))

    def test_extra_settings_line_is_named(self):
        s = self.settings({"picture": "fill", "extra_env": "PS3_PICTURE=stretch"})
        self.assertEqual(core.extra_env_override(s, "picture"), "PS3_PICTURE=stretch")

    def test_problem_report_names_them(self):
        st = dict(core.DEFAULTS, display="custom", window_w=2160, window_h=1440, picture="fill")
        lines = report.settings_lines(st, {"display": dict(core.DISPLAY_MODES), "picture": core.PICTURE_FORMATS})
        self.assertTrue(any(ln.startswith("Window and resolution: ") and ln.endswith("[custom] 2160 x 1440")
                            for ln in lines), lines)
        self.assertTrue(any(ln.startswith("Picture format: ") and "[fill]" in ln for ln in lines), lines)
        lines = report.settings_lines({"display": "window"})
        self.assertIn("Picture format: fit", lines)


class TranslatedEverywhere(unittest.TestCase):
    TEXTS = ("Picture format", "pixels", "Window, my own size:",
             "Width {wmin}-{wmax} and height {hmin}-{hmax}, whole numbers. Until then the game uses {w} x {h}.",
             "For screens that are not 16:9, such as 16:10 and 3:2 laptops. The game draws 16:9, so Fill cuts a "
             "little off the sides and Stretch widens everything. Only your picture changes: online, both players "
             "can choose differently.")

    def test_new_texts_in_every_catalog(self):
        sys.path.insert(0, os.path.join(ROOT, "lobby"))
        import importlib
        src = text("launcher", "t5dr_launcher.pyw")
        for w in self.TEXTS[:2]:
            self.assertIn(f't("{w}")', src)
        for lang in ("de", "es", "fr", "ja", "ko", "pt_br"):
            cat = importlib.import_module(f"t5lobby.i18n_{lang}").MESSAGES
            for w in list(core.PICTURE_FORMATS.values()) + list(self.TEXTS):
                self.assertIn(w, cat, (lang, w))
                for ph in re.findall(r"\{\w+\}", w):
                    self.assertIn(ph, cat[w], (lang, w))


class Patch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.path.isfile(PATCH):
            raise unittest.SkipTest("patch 0107 not in this tree")
        cls.patch = text("patches", "ps3recomp", "0107-picture-format.patch")

    def test_files_it_touches(self):
        files = re.findall(r"(?m)^diff --git a/(\S+)", self.patch)
        self.assertEqual(sorted(files), ["libs/video/cellVideoOut.c", "libs/video/rsx_live_draw.c",
                                         "libs/video/rsx_overlay.c", "libs/video/rsx_picture_rect.h"])

    def test_host_pixels_only(self):
        # the present and the overlay; the guest's own display mode stays 16:9 unless the test hook asks
        self.assertIn("PS3_PICTURE", self.patch)
        self.assertIn("rsx_picture_rect(", self.patch)
        self.assertIn("PS3_VIDEO_ASPECT", self.patch)
        self.assertIn("s_report_aspect = CELL_VIDEO_OUT_ASPECT_16_9", self.patch)

    def test_true_43_is_an_sd_tv(self):
        # the game's 4:3 HUD is laid out for 480 lines; the present shows the picture as 4:3 and Internal
        # resolution counts from 720 lines
        self.assertIn('r = "480";', self.patch)
        self.assertIn("cellVideoOut_report_4_3()) pic_w = (pic_h * 4u + 1u) / 3u;", self.patch)
        self.assertIn("s *= cellVideoOut_res_boost();", self.patch)
        self.assertIn("rsx_overlay_present(g.dev, g.list, bb, pic_w, pic_h);", self.patch)

    def test_documented(self):
        doc = text("docs", "PICTURE_FORMAT.md")
        for want in ("PS3_PICTURE", "fill", "stretch", "4:3", "PS3_VIDEO_ASPECT", "patch 0107"):
            self.assertIn(want, doc)


if __name__ == "__main__":
    unittest.main()
