"""Online fullscreen policy, using fake launches and fake runtime environment only."""
import ctypes
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from helpers import ROOT

sys.path.insert(0, os.path.join(ROOT, "launcher"))
import core

PATCH = Path(ROOT, "patches", "ps3recomp", "0117-online-borderless.patch")


class LauncherFullscreen(unittest.TestCase):
    def launch(self, resolved_env, extra_env=None):
        with tempfile.TemporaryDirectory() as out:
            exe = Path(out, "t5dr.exe")
            exe.touch()
            settings = core.Settings(os.path.join(out, "settings.json"))
            game = core.GameRun(out, settings)
            with mock.patch.object(core.run_game, "game_command", return_value=([str(exe)], dict(resolved_env), out)), \
                    mock.patch.object(core.run_game, "under_wine", return_value=False), \
                    mock.patch.object(core, "costume_env"), \
                    mock.patch.object(core.warmup, "pause_all"), \
                    mock.patch.object(core.threading, "Thread"), \
                    mock.patch.object(core.subprocess, "Popen") as popen:
                popen.return_value.pid = 123
                self.assertEqual(game.start(extra_env), 123)
                # The game still has no console window; all handles and launches are fake.
                if core.IS_WIN:
                    self.assertEqual(popen.call_args.kwargs["creationflags"], core.CREATE_NO_WINDOW)
                return popen.call_args.kwargs["env"]

    def test_online_exclusive_uses_borderless_after_effective_environment_is_merged(self):
        for online in ({"T5_CTL_DIR": "control"}, {"T5_NET_MODE": "host"}, {"T5_NET_MODE": "join"},
                       {"T5_NET_MODE": "HOST"}):
            for fullscreen in ("exclusive", "EXCLUSIVE", "2"):
                with self.subTest(online=online, fullscreen=fullscreen):
                    env = {**online, "PS3_FULLSCREEN": fullscreen}
                    self.assertEqual(self.launch(env)["PS3_FULLSCREEN"], "1")

    def test_online_windowed_and_offline_exclusive_are_preserved(self):
        for env in ({"PS3_FULLSCREEN": "exclusive"}, {"T5_CTL_DIR": "", "PS3_FULLSCREEN": "2"},
                    {"T5_NET_MODE": "replay", "PS3_FULLSCREEN": "exclusive"},
                    {"T5_NET_MODE": "host"}, {"T5_NET_MODE": "join", "PS3_FULLSCREEN": "0"},
                    {"T5_CTL_DIR": "control", "PS3_FULLSCREEN": "1"}):
            with self.subTest(env=env):
                self.assertEqual(self.launch(env), env)


class RuntimeFullscreen(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.name != "nt":
            raise unittest.SkipTest("runtime fake DLL uses clang-cl on Windows")
        clang = shutil.which("clang-cl") or r"C:\Program Files\LLVM\bin\clang-cl.exe"
        if not os.path.isfile(clang):
            raise unittest.SkipTest("no clang-cl")
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        patch = PATCH.read_text(encoding="utf-8")
        # Compile the actual function added to the runtime, without loading the game,
        # DXGI or user32. No Windows SDK, CRT or real environment/window is needed.
        added = "\n".join(line[1:] for line in patch.splitlines() if line.startswith("+") and not line.startswith("+++"))
        start = added.index("static int ld_exclusive_requested(")
        policy = added[start:added.index("\n}", start) + 2]
        source = r'''
static const char *fake_mode, *fake_ctl;
static int fake_strcmp(const char *a, const char *b) {
    while (*a && *a == *b) { ++a; ++b; }
    return (unsigned char)*a - (unsigned char)*b;
}
static int lower(int c) { return c >= 'A' && c <= 'Z' ? c + 32 : c; }
static int fake_stricmp(const char *a, const char *b) {
    while (*a && lower(*a) == lower(*b)) { ++a; ++b; }
    return lower((unsigned char)*a) - lower((unsigned char)*b);
}
static const char *fake_getenv(const char *name) {
    return fake_strcmp(name, "T5_CTL_DIR") == 0 ? fake_ctl : fake_mode;
}
#define getenv fake_getenv
#define strcmp fake_strcmp
#define _stricmp fake_stricmp
''' + policy + r'''
__declspec(dllexport) int exclusive(const char *fullscreen, const char *mode, const char *ctl) {
    fake_mode = mode; fake_ctl = ctl;
    return ld_exclusive_requested(fullscreen);
}
'''
        src = Path(cls.tmp.name, "online_fullscreen.c")
        src.write_text(source, encoding="utf-8")
        dll = Path(cls.tmp.name, "online_fullscreen.dll")
        cmd = [clang, "/nologo", "/LD", "/Zl", "/GS-", "-fuse-ld=lld", str(src),
               "/Fo:" + str(Path(cls.tmp.name, "online_fullscreen.obj")), "/link", "/noentry", "/nodefaultlib",
               "/out:" + str(dll), "/implib:" + str(Path(cls.tmp.name, "online_fullscreen.lib"))]
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=cls.tmp.name, timeout=60,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)
        cls.dll = ctypes.CDLL(str(dll))
        cls.policy = cls.dll.exclusive
        cls.policy.argtypes = [ctypes.c_char_p] * 3
        cls.policy.restype = ctypes.c_int
        # Release before TemporaryDirectory cleanup (Windows locks loaded DLLs).
        cls.addClassCleanup(lambda: ctypes.windll.kernel32.FreeLibrary(ctypes.c_void_p(cls.dll._handle)))

    def test_online_cannot_enter_dxgi_exclusive(self):
        for fullscreen in (b"exclusive", b"EXCLUSIVE", b"2"):
            for mode, ctl in ((b"host", None), (b"join", None), (b"HOST", None),
                              (None, b"control"), (b"replay", b"control")):
                with self.subTest(fullscreen=fullscreen, mode=mode, ctl=ctl):
                    self.assertEqual(self.policy(fullscreen, mode, ctl), 0)

    def test_offline_exclusive_and_windowed_modes(self):
        for fullscreen in (b"exclusive", b"EXCLUSIVE", b"2"):
            self.assertEqual(self.policy(fullscreen, None, None), 1)
            self.assertEqual(self.policy(fullscreen, b"replay", b""), 1)
        for fullscreen in (None, b"", b"0", b"1", b"borderless"):
            self.assertEqual(self.policy(fullscreen, None, None), 0)


class RuntimeWiring(unittest.TestCase):
    def test_display_configuration_uses_the_online_policy(self):
        patch = PATCH.read_text(encoding="utf-8")
        self.assertIn('+    g_ldp.exclusive_cfg = ld_exclusive_requested(e);', patch)
        self.assertIn('if (g_ldp.exclusive_cfg && !getenv("PS3_WINDOW_BACKGROUND"))', patch)


if __name__ == "__main__":
    unittest.main()
