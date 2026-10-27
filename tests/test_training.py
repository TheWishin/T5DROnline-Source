"""The training overlay (docs/TRAINING.md): input display and frame data over the picture.

* tests/c/training_test.cpp, built against src/training/training_logic.h and the patched runtime's
  libs/video/rsx_overlay.c (ps3recomp patch 0045, without Direct3D), must print PASS: Tekken notation, the input
  history, the frame-data tracker on frame sequences shaped like the traced fights, the font and the layout.
* src/training only reads guest memory: no store into it, no call into the game -- the game state, and so
  online play, is the same with the overlay on or off.
* Patch 0045 touches the present path of rsx_live_draw.c with one call and its declaration, nothing else.
* The launcher's "Training overlay" setting reaches the game as T5_TRAINING / _ALL / _ONLINE / _LANG.

The C part needs a ps3recomp tree with patch 0045 (PS3RECOMP_DIR, deps/ps3recomp) and a Windows C compiler; it is
skipped without them.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

from helpers import ROOT

# appended, not in front: lobby/run.py must not hide tools/smoke/run.py from test_smoke.py
for _sub in ("launcher", "lobby"):
    if os.path.join(ROOT, _sub) not in sys.path:
        sys.path.append(os.path.join(ROOT, _sub))

PATCH = os.path.join(ROOT, "patches", "ps3recomp", "0045-training-overlay.patch")
TRAINING = os.path.join(ROOT, "src", "training")


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
        if c and os.path.isfile(os.path.join(c, "libs", "video", "rsx_overlay.c")):
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


class LogicAndLayoutTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.name != "nt":
            raise unittest.SkipTest("built with the Windows compiler")
        cls.tree = find_ps3recomp()
        if not cls.tree:
            raise unittest.SkipTest("no ps3recomp tree with patch 0045 (PS3RECOMP_DIR)")
        vcvars = find_vcvars()
        clang = shutil.which("clang-cl") or (r"C:\Program Files\LLVM\bin\clang-cl.exe"
                                             if os.path.isfile(r"C:\Program Files\LLVM\bin\clang-cl.exe") else None)
        if not vcvars or not (clang or shutil.which("cl")):
            raise unittest.SkipTest("no Windows C compiler")
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        exe = os.path.join(cls.tmp.name, "training_test.exe")
        inc = [os.path.join(cls.tree, "libs", "video"), TRAINING]
        srcs = [os.path.join(ROOT, "tests", "c", "training_test.cpp"),
                os.path.join(cls.tree, "libs", "video", "rsx_overlay.c")]
        cc = f'"{clang}"' if clang else "cl"
        flags = " ".join(f'/I "{d}"' for d in inc)
        cmd = (f'"{vcvars}" >nul 2>&1 && {cc} /nologo /O1 /W0 /EHsc /std:c++17 /DRSX_OVERLAY_NO_D3D {flags} '
               + " ".join(f'"{s}"' for s in srcs) + f' /Fe:"{exe}" /Fo:"{cls.tmp.name}\\\\"')
        r = subprocess.run(f'cmd /s /c "{cmd}"', capture_output=True, text=True, timeout=600, cwd=cls.tmp.name)
        if not os.path.isfile(exe):
            raise AssertionError("could not build tests/c/training_test.cpp: " + (r.stdout + r.stderr)[-2000:])
        cls.exe = exe

    def test_c_unit_test_passes(self):
        r = subprocess.run([self.exe], capture_output=True, text=True, timeout=120, cwd=self.tmp.name)
        tail = r.stdout[-3000:]
        self.assertEqual(r.returncode, 0, tail)
        self.assertRegex(r.stdout, r"(?m)^PASS \d+ checks$", tail)


def code_only(text):
    """C/C++ source without comments and string literals."""
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    text = re.sub(r"//[^\n]*", " ", text)
    return re.sub(r'"(\\.|[^"\\])*"', '""', text)


# the practice tools (practice.cpp) change the game -- offline Practice only, checked by PracticeGateTest
CHANGES_THE_GAME = ("practice.cpp",)


class ReadOnlyTest(unittest.TestCase):
    """The overlay must never change the game: it reads guest memory and nothing else."""

    def sources(self):
        out = {}
        for name in sorted(os.listdir(TRAINING)):
            if name.endswith((".cpp", ".h")) and name not in CHANGES_THE_GAME:
                with open(os.path.join(TRAINING, name), encoding="utf-8") as f:
                    out[name] = code_only(f.read())
        return out

    def test_sources_exist(self):
        self.assertIn("training.cpp", self.sources())
        self.assertIn("training_logic.h", self.sources())

    def test_no_store_into_guest_memory(self):
        bad = [
            (r"\bwr(8|16|32|64)\s*\(", "a guest store helper"),
            (r"vm_base\s*\[[^\]]*\]\s*(=[^=]|\+=|-=|\|=|&=|\^=|\+\+|--)", "an assignment through vm_base[]"),
            (r"\b(memcpy|memmove|memset|strcpy|strncpy|fread|_byteswap_\w+\s*\(\s*\*)\s*\(\s*\(?\s*(uint8_t\s*\*)?\s*\)?\s*vm_base",
             "a write into vm_base"),
            (r"\*\s*\(\s*\w+\s*\*\s*\)\s*\(\s*vm_base[^;]*\)\s*=[^=]", "a store through a cast of vm_base"),
            (r"ppu_guest_call|gcall\s*\(|g_lv2_syscalls|ps3_hle_register", "a call into the game or a hook"),
            (r"\bVM_BASE\b|vm_base_k", "the lifted code's base pointer"),
        ]
        for name, src in self.sources().items():
            for pat, what in bad:
                m = re.search(pat, src)
                self.assertIsNone(m, f"src/training/{name}: {what}: {m.group(0) if m else ''}")

    def test_every_guest_access_is_a_read_helper(self):
        """Every statement that names vm_base is one of the three read helpers or the research trace."""
        allowed = (r"^memcpy\(\s*&v\s*,\s*vm_base\s*\+\s*a\s*,\s*[24]\s*\)$",
                   r"^return\s+vm_base\[a\]$",
                   r"^fwrite\(\s*vm_base\s*\+\s*0x[0-9A-Fa-f]+u?\s*,\s*1\s*,\s*(0x[0-9A-Fa-f]+|\d+)\s*,\s*g_cfg\.trace\s*\)$",
                   # T5_TRAINING_TRACE_RANGES: page by page, uncommitted pages as zeros (trace_range)
                   r"^const\s+bool\s+ok\s*=\s*VirtualQuery\(\s*vm_base\s*\+\s*a\s*,\s*&mi\s*,\s*sizeof\s+mi\s*\)",
                   r"^fwrite\(\s*ok\s*\?\s*\(const void\*\)\(vm_base\s*\+\s*a\)\s*:\s*\(const void\*\)zero\s*,\s*1\s*,"
                   r"\s*n\s*,\s*g_cfg\.trace\s*\)$")
        stmts = [x.strip() for x in re.split(r"[;{}]", self.sources()["training.cpp"]) if "vm_base" in x]
        self.assertGreaterEqual(len(stmts), 3)
        for st in stmts:
            self.assertTrue(any(re.match(a, st) for a in allowed), f"unexpected use of guest memory: {st}")

    def test_called_only_for_live_frames(self):
        with open(os.path.join(ROOT, "src", "netplay", "t5_hooks.cpp"), encoding="utf-8") as f:
            hooks = f.read()
        calls = re.findall(r"[^\n]*t5_training_frame\(ctx\);[^\n]*", hooks)
        self.assertEqual(len(calls), 1, calls)
        self.assertIn("!rb::net::bypass()", calls[0])


class PracticeGateTest(unittest.TestCase):
    """The practice tools change the game, so they run only offline, in Practice, in the fight."""

    def setUp(self):
        with open(os.path.join(TRAINING, "practice.cpp"), encoding="utf-8") as f:
            self.src = code_only(f.read())
        with open(os.path.join(ROOT, "src", "netplay", "t5_hooks.cpp"), encoding="utf-8") as f:
            self.hooks = f.read()

    def test_called_only_offline(self):
        calls = [ln.strip() for ln in self.hooks.splitlines() if "t5_practice_pads(" in ln and "extern" not in ln]
        self.assertEqual(calls, ["t5_practice_pads(&m0, &m1);"])
        body = self.hooks.split("void keyread_tick()")[1].split("\n}\n")[0]
        self.assertRegex(body, r"if \(g_offline\) \{[^}]*t5_practice_pads\(&m0, &m1\);")
        # online the ring is written in the same order as before
        self.assertRegex(body, r"gcall\(kFnPortMask, 0\);\s*if \(!g_offline\) wr16\(kRing \+ slot, m0\);")

    def test_gate(self):
        gate = re.search(r"bool allowed\(\)\s*\{(.*?)\n\}", self.src, re.S)
        self.assertIsNotNone(gate)
        for need in ("g_cfg.on", "g_cfg.offline", "t5_netplay_enabled() == 0", "rd32(kGameType) == kGtPractice",
                     "rd32(kPhase) == 17"):
            self.assertIn(need, gate.group(1))
        body = self.src.split("void t5_practice_pads(")[1]
        first = body.split("if (!allowed())")[0]
        self.assertNotRegex(first, r"\*p[12]\s*=|\bput\w*\(", "nothing changes before the gate")
        for env in ("T5_NET_MODE", "T5_CTL_DIR", "T5_REPLAY_FILE"):
            with open(os.path.join(TRAINING, "practice.cpp"), encoding="utf-8") as f:
                self.assertIn(env, f.read())

    def test_no_calls_into_the_game(self):
        self.assertNotRegex(self.src, r"ppu_guest_call|gcall\s*\(|g_lv2_syscalls|ps3_hle_register")

    def test_guest_writes_only_in_the_put_helpers(self):
        """Every statement that names vm_base is a read helper or one of the gated put helpers."""
        stmts = [x.strip() for x in re.split(r"[;{}]", self.src) if "vm_base" in x]
        allowed = (r"^memcpy\(\s*&v\s*,\s*vm_base\s*\+\s*a\s*,\s*[24]\s*\)$",
                   r"^return\s+vm_base\[a\]$",
                   r"^memcpy\(\s*vm_base\s*\+\s*a\s*,\s*&v\s*,\s*4\s*\)$")
        for st in stmts:
            self.assertTrue(any(re.match(a, st) for a in allowed), f"unexpected use of guest memory: {st}")


class PatchTest(unittest.TestCase):
    def test_present_hook_is_two_lines(self):
        with open(PATCH, encoding="utf-8", newline="") as f:
            text = f.read()
        self.assertNotIn("\r", text)
        files = re.findall(r"(?m)^diff --git a/(\S+) b/", text)
        self.assertEqual(sorted(files), ["libs/video/rsx_live_draw.c", "libs/video/rsx_overlay.c",
                                         "libs/video/rsx_overlay.h"])
        live = text.split("diff --git a/libs/video/rsx_live_draw.c")[1].split("\ndiff --git")[0]
        added = [ln for ln in live.splitlines() if ln.startswith("+") and not ln.startswith("+++")]
        removed = [ln for ln in live.splitlines() if ln.startswith("-") and not ln.startswith("---")]
        self.assertEqual(len(added), 2, added)
        self.assertEqual(removed, [])
        self.assertTrue(any("rsx_overlay_present(g.dev, g.list, bb," in ln for ln in added), added)
        self.assertEqual(len(re.findall(r"(?m)^@@", live)), 1)

    def test_overlay_is_our_own(self):
        with open(PATCH, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("Our own 5 x 7 glyphs", text)
        self.assertNotRegex(text.lower(), r"\b(font8x8|ibm|copyright \(c\))")


class LauncherSettingTest(unittest.TestCase):
    def setUp(self):
        saved = list(sys.path)
        self.addCleanup(lambda: sys.path.__setitem__(slice(None), saved))
        import core
        self.core = core
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def settings(self, **kw):
        path = os.path.join(self.tmp.name, "launcher.json")
        s = self.core.Settings(path)
        s.update(kw)
        return s

    def test_default_is_practice_inputs_and_frame_data(self):
        s = self.settings()
        self.assertEqual(s["training"], "frames")
        env = s.env_overrides()
        self.assertEqual(env["T5_TRAINING"], "frames")
        self.assertNotIn("T5_TRAINING_ALL", env)
        self.assertNotIn("T5_TRAINING_ONLINE", env)

    def test_off_inputs_frames_and_options(self):
        for key in ("off", "inputs", "frames"):
            self.assertEqual(self.settings(training=key).env_overrides()["T5_TRAINING"], key)
        env = self.settings(training="inputs", training_all=True, training_online=True).env_overrides()
        self.assertEqual((env["T5_TRAINING_ALL"], env["T5_TRAINING_ONLINE"]), ("1", "1"))
        self.assertIn(env["T5_TRAINING_LANG"], ("de", "en"))

    def test_unknown_saved_value_falls_back(self):
        path = os.path.join(self.tmp.name, "launcher.json")
        with open(path, "w") as f:
            f.write('{"training": "everything"}')
        self.assertEqual(self.core.Settings(path)["training"], "frames")

    def test_choices_are_translated(self):
        from t5lobby import i18n_de
        for _key, label in self.core.TRAINING_MODES.items():
            self.assertIn(label, i18n_de.MESSAGES)
        for _key, label in self.core.PRACTICE_DUMMY.items():
            self.assertIn(label, i18n_de.MESSAGES)
        self.assertIn(self.core.PRACTICE_HELP, i18n_de.MESSAGES)

    def test_practice_tools(self):
        env = self.settings().env_overrides()
        self.assertEqual((env["T5_PRACTICE"], env["T5_PRACTICE_DUMMY"]), ("1", "game"))
        for key in self.core.PRACTICE_DUMMY:
            self.assertEqual(self.settings(practice_dummy=key).env_overrides()["T5_PRACTICE_DUMMY"], key)
        env = self.settings(practice=False, practice_dummy="crouch").env_overrides()
        self.assertEqual(env["T5_PRACTICE"], "0")
        self.assertNotIn("T5_PRACTICE_DUMMY", env)
        # the in-game texts follow the launcher's language even with the overlay off
        self.assertIn("T5_TRAINING_LANG", self.settings(training="off").env_overrides())
        path = os.path.join(self.tmp.name, "launcher.json")
        with open(path, "w") as f:
            f.write('{"practice": "yes", "practice_dummy": "dance"}')
        s = self.core.Settings(path)
        self.assertEqual((s["practice"], s["practice_dummy"]), (True, "game"))


class DocsTest(unittest.TestCase):
    def test_training_doc(self):
        with open(os.path.join(ROOT, "docs", "TRAINING.md"), encoding="utf-8") as f:
            doc = f.read()
        for word in ("T5_TRAINING", "T5_TRAINING_ALL", "T5_TRAINING_ONLINE", "F2", "0x21C", "+3", "rsx_overlay",
                     "mismatching"):
            self.assertIn(word, doc)

    def test_readmes_mention_it(self):
        for path in ("README.md", os.path.join("docs", "README.de.md")):
            with open(os.path.join(ROOT, path), encoding="utf-8") as f:
                self.assertTrue("TRAINING.md" in f.read(), f"{path} does not link docs/TRAINING.md")


if __name__ == "__main__":
    unittest.main()
