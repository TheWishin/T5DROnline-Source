"""Graphics settings for weak graphics cards (ps3recomp patch 0079, docs/RENDER_PERF.md "Graphics settings for weak
graphics cards"). No game needed.

* Launcher Settings -> Graphics: each effect On (the default: nothing set) or Off (its variable = 0 for the game),
  saved, in the problem report, in every catalog; the "Lowest" preset (Internal resolution Lowest, stage blur /
  glow off, every effect off) and "Default" (puts them back).
* The runtime's switches are in patch 0079, which reads only the environment and changes only host pixels (no guest
  memory, no command stream: the two players of a match may choose differently).
* tests/c/graphics_test.c, built against the patched runtime source: with shadows off a shadow sampler returns an
  empty map's result without reading the map (the program compiles with D3DCompile). Skipped without a patched
  ps3recomp tree (PS3RECOMP_DIR) or a C compiler.
"""
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

from helpers import ROOT

sys.path.insert(0, os.path.join(ROOT, "launcher"))     # (not lobby/: its run.py would hide tools/smoke/run.py)
import core  # noqa: E402
import problem_report as report  # noqa: E402

PATCH = os.path.join(ROOT, "patches", "ps3recomp", "0079-graphics-settings.patch")


def text(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def labels():
    return {"display": dict(core.DISPLAY_MODES), "internal_res": core.INTERNAL_RES_LABELS,
            "vsync": core.VSYNC_MODES, "stage_blur": core.STAGE_BLUR_MODES, "input_delay": core.INPUT_DELAYS,
            **{key: spec[2] for key, spec in core.GRAPHICS.items()}}


class Settings(unittest.TestCase):
    def path(self, saved=None):
        d = tempfile.mkdtemp(prefix="t5dr-gfx")
        self.addCleanup(shutil.rmtree, d, True)
        p = os.path.join(d, "launcher.json")
        if saved is not None:
            with open(p, "w", encoding="utf-8") as f:
                json.dump(saved, f)
        return p

    def test_the_settings(self):
        self.assertEqual(list(core.GRAPHICS), ["shadows", "effects"])
        self.assertEqual(core.GRAPHICS["shadows"][1], "PS3_SHADOWS")
        self.assertEqual(core.GRAPHICS["effects"][1], "PS3_EFFECTS")
        for key, (name, var, modes, default) in core.GRAPHICS.items():
            self.assertEqual(list(modes), ["on", "off"], key)
            self.assertEqual(default, "on", key)              # the game's own look unless the player picks Off
            self.assertEqual(core.DEFAULTS[key], "on", key)
            self.assertTrue(var.startswith("PS3_"), key)
            self.assertIn(key, core.GRAPHICS_HINTS)
            self.assertEqual(core.SETTING_ENV[key], var)          # Extra settings override it (Settings says so)
        # Effects off also hides hit effects (GitHub #12: the EWGF lightning): the hint says so; it is never on by
        # default, and only the Lowest preset the player clicks turns it off
        self.assertIn("EWGF", core.GRAPHICS_HINTS["effects"])
        self.assertEqual(core.DEFAULT_PRESET["effects"], "on")

    def test_on_by_default_sends_nothing(self):
        for saved in (None, {}, {"display": "window1080", "internal_res": "4k", "stage_blur": "on"}):
            s = core.Settings(self.path(saved))
            env = s.env_overrides()
            for key, (_n, var, _m, _d) in core.GRAPHICS.items():
                self.assertEqual(s[key], "on", (saved, key))
                self.assertNotIn(var, env, (saved, key))

    def test_off_goes_to_the_game(self):
        for key, (_n, var, _m, _d) in core.GRAPHICS.items():
            p = self.path()
            s = core.Settings(p)
            s[key] = "off"
            s.save()
            with open(p, encoding="utf-8") as f:
                self.assertEqual(json.load(f)[key], "off")
            env = core.Settings(p).env_overrides()
            self.assertEqual(env[var], "0", key)
            # the game gets it through GameRun.start: Play offline and every online match alike
            _cmd, game_env, _cwd = core.run_game.game_command(tempfile.mkdtemp(), env)
            self.assertEqual(game_env[var], "0", key)

    def test_unknown_value_is_the_default(self):
        for bad in ("maybe", "", None, True, 0, "OFF", [], {"off": 1}):
            s = core.Settings(self.path({"shadows": bad}))
            self.assertEqual(s["shadows"], "on", bad)
            self.assertNotIn("PS3_SHADOWS", s.env_overrides())

    def test_extra_settings_still_win(self):
        s = core.Settings(self.path({"shadows": "off", "extra_env": "PS3_SHADOWS=1"}))
        self.assertEqual(s.env_overrides()["PS3_SHADOWS"], "1")
        self.assertEqual(core.extra_env_override(s, "shadows"), "PS3_SHADOWS=1")

    def test_lowest_preset(self):
        s = core.Settings(self.path({"internal_res": "4k", "internal_res_set": True, "stage_blur": "on",
                                     "settings_version": 1, "vsync": "off", "display": "borderless"}))
        changed = core.apply_preset(s, core.LOWEST_PRESET)
        self.assertIn("internal_res", changed)
        self.assertEqual(core.preset_in_use(s), "lowest")
        env = s.env_overrides()
        self.assertEqual(env["PS3_INTERNAL_RES"], "lowest")
        self.assertEqual(env["PS3_STAGE_BLUR"], "0")
        self.assertEqual(env["PS3_SHADOWS"], "0")
        # effects stay on (owner, 1.1.5): the hit effects show what happens in a fight -- and Lowest switches them
        # back on when they were off
        self.assertNotIn("PS3_EFFECTS", env)
        self.assertEqual((s["shadows"], s["effects"]), ("off", "on"))
        s["effects"] = "off"
        core.apply_preset(s, core.LOWEST_PRESET)
        self.assertEqual(s["effects"], "on")
        # the other settings stay as they were
        self.assertEqual((s["vsync"], s["display"]), ("off", "borderless"))
        s.save()
        self.assertEqual(core.preset_in_use(core.Settings(s.path)), "lowest")

    def test_default_preset_puts_it_back(self):
        s = core.Settings(self.path({"settings_version": 1}))
        self.assertEqual(core.preset_in_use(s), "default")
        core.apply_preset(s, core.LOWEST_PRESET)
        core.apply_preset(s, core.DEFAULT_PRESET)
        self.assertEqual(core.preset_in_use(s), "default")
        self.assertFalse(s["internal_res_set"])        # Auto on integrated graphics again, Native elsewhere
        self.assertEqual(s.internal_res_choice(False), "native")
        self.assertEqual(s.internal_res_choice(True), "auto")
        env = s.env_overrides()
        for key, (_n, var, _m, _d) in core.GRAPHICS.items():
            self.assertNotIn(var, env, key)
        self.assertEqual(env.get("PS3_STAGE_BLUR"), "0")    # stage blur / glow: Off is its default (1.1.4)
        # a mix is neither
        s["shadows"] = "off"
        self.assertIsNone(core.preset_in_use(s))

    def test_launcher_shows_it(self):
        src = text("launcher", "t5dr_launcher.pyw")
        self.assertIn('t("Graphics (weak graphics cards)")', src)
        self.assertIn("core.LOWEST_PRESET", src)
        self.assertIn("core.DEFAULT_PRESET", src)
        self.assertIn("self.settings[key] = var.get()", src)                 # saved with the others
        self.assertIn("**{key: spec[2] for key, spec in core.GRAPHICS.items()}", src)   # problem report labels

    def test_every_catalog_has_the_texts(self):
        texts = [spec[0] for spec in core.GRAPHICS.values()] + list(core.GRAPHICS_HINTS.values()) + \
            list(core.ON_OFF_MODES.values()) + ["Graphics (weak graphics cards)", "Lowest (old graphics cards)",
                                                "Default"]
        for lang in ("de", "es", "ko", "ja", "pt_br", "fr"):
            spec = importlib.util.spec_from_file_location(f"i18n_{lang}_gfx",
                                                          os.path.join(ROOT, "lobby", "t5lobby", f"i18n_{lang}.py"))
            cat = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cat)
            for t in texts:
                self.assertTrue(cat.MESSAGES.get(t), (lang, t))

    def test_problem_report_lists_it(self):
        self.assertIn("shadows", report.SETTING_KEYS)
        on = report.settings_lines(dict(core.DEFAULTS), labels(), {}, None)
        self.assertIn("Shadows: On (default) [on]", on)
        self.assertIn("Effects: On (default) [on]", on)
        self.assertEqual(on.index("Shadows: On (default) [on]"),
                         [i for i, ln in enumerate(on) if ln.startswith("Stage blur / glow:")][0] + 1)
        off = report.settings_lines(dict(core.DEFAULTS, shadows="off"), labels(), {"PS3_SHADOWS": "0"}, None)
        self.assertIn("Shadows: Off [off]", off)
        self.assertIn("PS3_SHADOWS=0", off[-1])
        self.assertTrue(report.GAME_LOG_FACTS.match("[display] shadows: off (PS3_SHADOWS): ..."))
        self.assertTrue(report.GAME_LOG_FACTS.match("[display] effects: off (PS3_EFFECTS): ..."))
        both = report.settings_lines(dict(core.DEFAULTS, shadows="off", effects="off"), labels(),
                                     {"PS3_SHADOWS": "0", "PS3_EFFECTS": "0"}, None)
        self.assertIn("Effects: Off [off]", both)


class Patch(unittest.TestCase):
    def setUp(self):
        if not os.path.isfile(PATCH):
            self.skipTest("no patch 0079 in this checkout")
        self.patch = text("patches", "ps3recomp", "0079-graphics-settings.patch")

    def added(self):
        return "\n".join(ln[1:] for ln in self.patch.splitlines() if ln.startswith("+") and not ln.startswith("+++"))

    def test_runtime_reads_the_switches(self):
        add = self.added()
        self.assertIn('getenv("PS3_SHADOWS")', add)
        self.assertIn('getenv("PS3_EFFECTS")', add)
        self.assertRegex(add, r"g_ld_effects = !\(e && \(e\[0\] == '0'")
        self.assertIn("static int g_ld_effects = 1;", add)
        self.assertIn("[display] effects: off", add)
        # 0 / off / false / no turn it off; unset or anything else keeps it on (the launcher sends "0")
        self.assertRegex(add, r"g_ld_shadows = !\(e && \(e\[0\] == '0'")
        self.assertIn("static int g_ld_shadows = 1;", add)
        self.assertIn("[display] shadows: off", add)

    def test_only_the_renderer_and_the_decompiler(self):
        files = re.findall(r"^diff --git a/(\S+) ", self.patch, re.M)
        self.assertEqual(sorted(set(files)), ["libs/video/rsx_fp_decompiler.c", "libs/video/rsx_live_draw.c"])

    def test_host_pixels_only(self):
        # nothing the patch adds writes guest memory or touches the command stream: a match's two PCs may differ
        add = self.added()
        for word in ("vm_base", "guest_write", "write_be", "cellGcm", "rsx_dsp_set", "g.rsx.regs[", "wr32(",
                     "g.rsx.constants["):
            self.assertNotIn(word, add, word)

    def test_skipped_before_the_vertices(self):
        # both switches drop a draw at the top of sink_end_impl, before its vertices are fetched (no translation)
        add = self.added()
        self.assertIn("if (!g_ld_shadows && ld_shadow_caster()) {", add)
        self.assertIn("if (!g_ld_effects && ld_effect_draw()) {", add)
        self.assertLess(self.patch.index("ld_effect_draw()) {"), self.patch.index("ld_current_vertex_layout(&used_layout);"))

    def test_shadows_off_is_pso_identity(self):
        add = self.added()
        # the off bit rides in shadow_func, which the PSO key already hashes (patch 0043's key code)
        self.assertIn("(g_ld_shadows ? 0u : 16u)", add)
        self.assertIn("zfunc[u] & 31u", add)

    def test_series_order(self):
        names = sorted(n for n in os.listdir(os.path.join(ROOT, "patches", "ps3recomp")) if n.endswith(".patch"))
        self.assertGreater(names.index("0079-graphics-settings.patch"), names.index("0043-stage-blur.patch"))


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
        p = os.path.join(c or "", "libs", "video", "rsx_fp_decompiler.c")
        if c and os.path.isfile(p):
            with open(p, encoding="utf-8", errors="replace") as f:
                if "if (f & 16) return (float4)rsx_zcmp(1.0, r, f & 7);" in f.read():
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


class RuntimeShaders(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.name != "nt":
            raise unittest.SkipTest("built with the Windows C compiler")
        cls.tree = find_ps3recomp()
        if not cls.tree:
            raise unittest.SkipTest("no ps3recomp tree with patch 0079 (PS3RECOMP_DIR)")
        vcvars = find_vcvars()
        clang = shutil.which("clang-cl") or (r"C:\Program Files\LLVM\bin\clang-cl.exe"
                                             if os.path.isfile(r"C:\Program Files\LLVM\bin\clang-cl.exe") else None)
        if not vcvars or not (clang or shutil.which("cl")):
            raise unittest.SkipTest("no Windows C compiler")
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        exe = os.path.join(cls.tmp.name, "graphics_test.exe")
        inc = [os.path.join(cls.tree, *p) for p in (("libs", "video"), ("libs",), ("runtime",), ("include",))]
        src = os.path.join(ROOT, "tests", "c", "graphics_test.c")
        cc = f'"{clang}"' if clang else "cl"
        flags = " ".join(f'/I "{d}"' for d in inc)
        cmd = (f'"{vcvars}" >nul 2>&1 && {cc} /nologo /O1 /W0 {flags} "{src}" /Fe:"{exe}" '
               f'/Fo:"{os.path.join(cls.tmp.name, "graphics_test.obj")}"')
        r = subprocess.run(f'cmd /s /c "{cmd}"', capture_output=True, text=True, timeout=600)
        if not os.path.isfile(exe):
            raise AssertionError("could not build tests/c/graphics_test.c: " + (r.stdout + r.stderr)[-1500:])
        cls.exe = exe

    def test_c_unit_test_passes(self):
        r = subprocess.run([self.exe], capture_output=True, text=True, timeout=120, cwd=self.tmp.name)
        tail = r.stdout[-3000:]
        self.assertEqual(r.returncode, 0, tail)
        self.assertRegex(r.stdout, r"(?m)^PASS \d+ checks$", tail)


if __name__ == "__main__":
    unittest.main()
