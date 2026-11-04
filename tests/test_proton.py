"""Linux / Steam Deck through Wine or Proton (1.2.0, docs/LINUX_STEAM_DECK.md): what the launcher does differently
there, and that Windows sees none of it. No Wine needed: stand-in ntdll/kernel32 objects and temporary folders.

* tools/run_game.py names where d3d12.dll and d3dcompiler_47.dll come from (Wine's own builtin or a native DLL:
  vkd3d-proton, Microsoft's compiler) in the [wine] line;
* the launcher finds the Linux Downloads/Desktop/Documents (WINEHOMEDIR, ~/.config/user-dirs.dirs) for the
  package search and saves the problem report on the Linux Desktop, not in Proton's hidden prefix;
* the problem report's system.txt names Wine / Proton;
* the problem check names a graphics failure seen in the game log under Wine (GitHub #26's dark blue window);
* the lobby's port forwarding reads the Linux routing table under Wine.
"""
import ctypes
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for sub in ("tools", "lobby", "launcher"):
    p = os.path.join(ROOT, sub)
    if p not in sys.path:
        sys.path.insert(0, p)

import run_game        # noqa: E402
import core            # noqa: E402
import problem_check   # noqa: E402
import problem_report  # noqa: E402
from t5lobby import portmap  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_wine import FakeNtdll  # noqa: E402


class FakeKernel32:
    """LoadLibraryExW hands out the address of a fake module image: a Wine builtin carries WINE_BUILTIN at 0x40."""

    def __init__(self, images):
        self.images = {k.lower(): ctypes.create_string_buffer(v, 0x100) for k, v in images.items()}
        self.freed = []
        k32 = self

        def load(name, _file, flags):
            assert flags == 0x00000001        # DONT_RESOLVE_DLL_REFERENCES: nothing of the DLL runs
            img = k32.images.get(name.lower())
            return ctypes.addressof(img) if img is not None else None

        def free(h):
            k32.freed.append(h)
            return 1
        self.LoadLibraryExW, self.FreeLibrary = load, free


def image(builtin):
    return b"MZ" + b"\0" * 0x3E + (run_game.WINE_BUILTIN if builtin else b"This program cannot be run in DOS")


class DllOrigin(unittest.TestCase):
    def test_builtin_native_missing(self):
        k = FakeKernel32({"d3d12.dll": image(False), "d3dcompiler_47.dll": image(True)})
        self.assertEqual(run_game.dll_origin("d3d12.dll", k), "native")
        self.assertEqual(run_game.dll_origin("d3dcompiler_47.dll", k), "wine")
        self.assertEqual(run_game.dll_origin("nothing.dll", k), "")
        self.assertEqual(len(k.freed), 2)                      # every mapped DLL freed again

    @unittest.skipUnless(os.name == "nt", "Windows")
    def test_this_windows_has_no_wine_builtins(self):
        self.assertEqual(run_game.dll_origin("kernel32.dll"), "native")
        self.assertEqual(run_game.dll_origin("no-such-dll-t5dr.dll"), "")

    def test_wine_line_names_the_dlls(self):
        k = FakeKernel32({"d3d12.dll": image(False), "d3dcompiler_47.dll": image(True)})
        with mock.patch.dict(os.environ, {"STEAM_COMPAT_TOOL_PATHS": "/x/GE-Proton10-11"}):
            info = run_game.wine_info(FakeNtdll(), k)
        self.assertEqual(info["dlls"], {"d3d12.dll": "native", "d3dcompiler_47.dll": "wine"})
        note = run_game.wine_note(info, {"RSX_VERTEX_THREADS": "0", "PS3_LWM_FAST": "0"})
        self.assertTrue(note.endswith(" -- RSX_VERTEX_THREADS=0, PS3_LWM_FAST=0 -- d3d12: vkd3d-proton (native), "
                                      "d3dcompiler_47: Wine's own"), note)
        m = problem_check.RE_WINE_LOG.match(note)              # the check's "This PC: ..." stays the short part
        self.assertEqual(m.group(1), "Wine 10.0 (wine-10.0 (Staging)) Proton: GE-Proton10-11 on Linux 6.17.1-cachyos")

    def test_stand_in_ntdll_alone_asks_no_dlls(self):
        self.assertNotIn("dlls", run_game.wine_info(FakeNtdll()))


def linux_home(d, user_dirs=None):
    home = os.path.join(d, "home", "deck")
    for sub in ("Desktop", "Downloads", "Documents", "Schreibtisch"):
        os.makedirs(os.path.join(home, sub))
    if user_dirs:
        os.makedirs(os.path.join(home, ".config"))
        with open(os.path.join(home, ".config", "user-dirs.dirs"), "w", encoding="utf-8") as f:
            f.write(user_dirs)
    return home


WINE = {"version": "10.0", "build": "", "host": "Linux 6.17", "proton": "GE-Proton10-11"}


class HostFolders(unittest.TestCase):
    def test_wine_home(self):
        with tempfile.TemporaryDirectory() as d:
            home = linux_home(d)
            self.assertEqual(run_game.wine_home({"WINEHOMEDIR": "\\??\\" + home}), home)
            self.assertIsNone(run_game.wine_home({"WINEHOMEDIR": "\\??\\" + home + "-gone"}))
            self.assertIsNone(run_game.wine_home({}))

    def test_user_dirs_file_and_defaults(self):
        with tempfile.TemporaryDirectory() as d:
            home = linux_home(d, '# written by xdg-user-dirs-update\nXDG_DESKTOP_DIR="$HOME/Schreibtisch"\n'
                                 'XDG_DOWNLOAD_DIR="$HOME/Downloads"\nXDG_MUSIC_DIR="$HOME/Musik"\n')
            dirs = run_game.wine_user_dirs(home)
            self.assertEqual(dirs, {"DESKTOP": os.path.join(home, "Schreibtisch"),
                                    "DOWNLOAD": os.path.join(home, "Downloads"),
                                    "DOCUMENTS": os.path.join(home, "Documents")})
        with tempfile.TemporaryDirectory() as d:
            home = linux_home(d)                               # no user-dirs.dirs: the English defaults
            self.assertEqual(run_game.wine_user_dirs(home)["DESKTOP"], os.path.join(home, "Desktop"))

    def test_under_wine_the_linux_folders(self):
        with tempfile.TemporaryDirectory() as d:
            home = linux_home(d)
            with mock.patch.object(run_game, "under_wine", lambda: WINE), \
                    mock.patch.dict(os.environ, {"WINEHOMEDIR": "\\??\\" + home}):
                self.assertEqual(core.desktop_dir(), os.path.join(home, "Desktop"))
                self.assertEqual(core.wine_host_dirs(), [os.path.join(home, s) for s in
                                                         ("Downloads", "Desktop", "Documents")] + [home])
                roots = [os.path.normcase(r) for r in core.candidate_roots()]
                self.assertIn(os.path.normcase(os.path.join(home, "Downloads")), roots)
            with mock.patch.object(run_game, "under_wine", lambda: WINE), \
                    mock.patch.dict(os.environ, {"WINEHOMEDIR": ""}):
                self.assertEqual(core.wine_host_dirs(), [])    # no Linux home known: the Windows way

    def test_windows_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            home = linux_home(d)
            with mock.patch.object(run_game, "under_wine", lambda: None), \
                    mock.patch.dict(os.environ, {"WINEHOMEDIR": "\\??\\" + home}):   # (even with the variable)
                self.assertEqual(core.wine_host_dirs(), [])
                desk = core.desktop_dir()
                self.assertFalse(desk.startswith(home), desk)
                self.assertFalse(any(r.startswith(home) for r in core.candidate_roots()))
        if os.name == "nt":                                    # this PC: real Windows
            self.assertIsNone(run_game.under_wine())
            self.assertEqual(core.wine_host_dirs(), [])


class Report(unittest.TestCase):
    def test_linux_user_name_is_scrubbed(self):
        text = r"release folder Z:\home\alicewine\Games\T5DR, home \??\Z:\home\alicewine"
        with mock.patch.dict(os.environ, {"WINEHOMEDIR": r"\??\Z:\home\alicewine", "USER": "alicewine"}):
            out = problem_report.scrub_text(text)
        self.assertNotIn("alicewine", out)
        with mock.patch.dict(os.environ, {"WINEHOMEDIR": ""}):            # Windows: as before
            os.environ.pop("WINEHOMEDIR", None)
            self.assertIn("alicewine", problem_report.scrub_text(text))

    def test_windows_has_no_wine_line(self):
        if os.name == "nt":
            self.assertIsNone(problem_report.wine_text())

    def test_wine_line(self):
        info = dict(WINE, dlls={"d3d12.dll": "native", "d3dcompiler_47.dll": "wine"})
        with mock.patch.object(run_game, "under_wine", lambda: info):
            self.assertEqual(problem_report.wine_text(), "Wine 10.0 Proton: GE-Proton10-11 on Linux 6.17 -- d3d12: "
                                                         "vkd3d-proton (native), d3dcompiler_47: Wine's own")
            ctx = problem_report.Context(tempfile.gettempdir())
            text = problem_report.system_text(ctx)
        lines = text.splitlines()
        i = next(n for n, ln in enumerate(lines) if ln.startswith("Windows: "))
        self.assertTrue(lines[i + 1].startswith("Wine / Proton: Wine 10.0 Proton: GE-Proton10-11"), lines[i + 1])


LOG_WINE = ("[wine] Wine 10.0 Proton: GE-Proton10-11 on Linux 6.17 -- RSX_VERTEX_THREADS=0, PS3_LWM_FAST=0 -- "
            "d3d12: vkd3d-proton (native), d3dcompiler_47: Wine's own\n")


class Check(unittest.TestCase):
    def keys(self, log, wine=None):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "logs"))
            with open(os.path.join(d, "logs", "game-20261104-120000.log"), "w", encoding="utf-8") as f:
                f.write(log)
            found = problem_check.check_pc({"cores": 4, "logical": 8, "wine": wine}, d)
        return {f.key: f for f in found}

    def test_graphics_failure_under_wine(self):
        for line in ("[rsx] live-draw init FAILED -- falling back to the D3D12 backend",
                     "[display] present shader compile failed: error X3000",
                     "[pso-fail] pixel compile: xps(12,3): error: unsupported",
                     "[gpu] FATAL (exit code 13): T5DR Online - Direct3D 12 not available"):
            got = self.keys(LOG_WINE + "[rsx] backend init OK\n" + line + "\n")
            self.assertEqual(set(got), {"wine", "wine_graphics"}, line)
            self.assertEqual(got["wine_graphics"].values["line"], line)
            self.assertEqual(got["wine_graphics"].kind, "problem")
        self.assertIn("wine_graphics", self.keys("[pso-fail] vertex compile: x\n", wine="Wine 9.0"))   # launcher's

    def test_no_finding_on_windows_or_without_a_failure(self):
        self.assertEqual(self.keys("[pso-fail] vertex compile: x\n"), {})            # Windows: nothing new
        self.assertEqual(set(self.keys(LOG_WINE + "[rsx] live-draw engine up (D3D12); GDI present suppressed\n")),
                         {"wine"})


ROUTE = ("Iface\tDestination\tGateway \tFlags\tRefCnt\tUse\tMetric\tMask\t\tMTU\tWindow\tIRTT\n"
         "wlan0\t0032A8C0\t00000000\t0001\t0\t0\t600\t00FFFFFF\t0\t0\t0\n"
         "wlan0\t00000000\t0132A8C0\t0003\t0\t0\t600\t00000000\t0\t0\t0\n")


class Gateway(unittest.TestCase):
    def test_proc_route(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "route")
            with open(p, "w") as f:
                f.write(ROUTE)
            self.assertEqual(portmap._proc_route_gateway(p), "192.168.50.1")
            with mock.patch.object(portmap, "_under_wine", lambda: True), \
                    mock.patch.object(portmap, "WINE_PROC_ROUTE", p), \
                    mock.patch.object(portmap.subprocess, "run", side_effect=AssertionError("route.exe asked")):
                if os.name == "nt":
                    self.assertEqual(portmap.default_gateway(), "192.168.50.1")

    @unittest.skipUnless(os.name == "nt", "Windows")
    def test_windows_still_asks_route_exe(self):
        self.assertFalse(portmap._under_wine())
        with mock.patch.object(portmap, "_proc_route_gateway", side_effect=AssertionError("read the Linux table")):
            portmap.default_gateway()                          # route.exe as before (any answer)


if __name__ == "__main__":
    unittest.main()
