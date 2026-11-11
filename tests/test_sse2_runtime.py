"""The release's second runtime for processors without SSE4.1 (branch t5-oldhw-019, docs/SSE2_BASELINE.md "Shipping
it"): which runtime BUILD GAME picks (CPUID facts mocked), what it hands build_game_dll.py, what the build stamp and
the launcher make of it, and that the package scan lets runtime/sse2 through but still catches game data in it.

    python tests/test_sse2_runtime.py

No game, no compiler run (the clang check runs only when clang-cl is installed, and only with a stand-in CPU model).
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for sub in ("tools", "launcher", "lobby"):
    sys.path.insert(0, os.path.join(ROOT, sub))
os.environ.setdefault("T5_PAD_NAV", "0")

import build_game as bg        # noqa: E402
import package_release as pr   # noqa: E402


class ChooseRuntime(unittest.TestCase):
    """build_game.choose_runtime: every combination of what Windows and CPUID say."""

    def test_no_sse2_runtime_shipped_is_always_normal(self):
        for facts in ({}, {"pf_sse41": False, "clang_sse41": False, "pf_sse3": False}, {"forced": "sse2"}):
            self.assertEqual(bg.choose_runtime(False, **facts)[0], "sse41", facts)

    def test_windows_says_sse41(self):
        self.assertEqual(bg.choose_runtime(True, pf_sse41=True), ("sse41", "this processor has SSE4.1"))
        # Windows' yes is certain: a clang "no" (cannot happen) does not overrule it
        self.assertEqual(bg.choose_runtime(True, pf_sse41=True, clang_sse41=False)[0], "sse41")

    def test_old_windows_says_no_cpuid_says_yes(self):
        # Windows 10 before 2004 answers "no" for feature 37 on every processor: CPUID decides
        self.assertEqual(bg.choose_runtime(True, pf_sse41=False, clang_sse41=True, pf_sse3=True)[0], "sse41")

    def test_cpuid_says_no(self):
        simd, why = bg.choose_runtime(True, pf_sse41=False, clang_sse41=False, pf_sse3=True)
        self.assertEqual(simd, "sse2")
        self.assertIn("no SSE4.1", why)

    def test_no_clang_answer(self):
        # no SSE3 at all: certainly no SSE4.1
        self.assertEqual(bg.choose_runtime(True, pf_sse41=False, clang_sse41=None, pf_sse3=False)[0], "sse2")
        # SSE3 there, SSE4.1 unknown: the normal runtime (it says so clearly if it cannot run)
        self.assertEqual(bg.choose_runtime(True, pf_sse41=False, clang_sse41=None, pf_sse3=True)[0], "sse41")
        self.assertEqual(bg.choose_runtime(True)[0], "sse41")

    def test_forced(self):
        self.assertEqual(bg.choose_runtime(True, forced="sse2", pf_sse41=True), ("sse2", "T5DR_RUNTIME=sse2"))
        self.assertEqual(bg.choose_runtime(True, forced="sse41", pf_sse41=False, clang_sse41=False)[0], "sse41")
        self.assertEqual(bg.choose_runtime(True, forced="bogus", pf_sse41=True)[0], "sse41")


class RuntimeForThisPc(unittest.TestCase):
    """build_game.runtime_for_this_pc gathers the facts: mocked Windows and CPUID answers."""

    def run_with(self, shipped=True, pf=None, clang=None, env=None):
        pf = pf or {}
        calls = []

        def fake_clang(_llvm):
            calls.append("clang")
            return clang
        env = dict(env or {})
        clean = {k: v for k, v in os.environ.items() if k not in ("T5DR_RUNTIME", "T5DR_TEST_CPU_MODEL")}
        clean.update(env)
        with mock.patch.dict(os.environ, clean, clear=True), \
                mock.patch.object(bg, "prebuilt_host_sse2", return_value=shipped), \
                mock.patch.object(bg, "_pf", side_effect=lambda f: pf.get(f)), \
                mock.patch.object(bg, "clang_has_sse41", side_effect=fake_clang):
            return bg.runtime_for_this_pc("llvm")[0], calls

    def test_modern_pc_never_starts_clang(self):
        self.assertEqual(self.run_with(pf={bg.PF_SSE4_1: True, bg.PF_SSE3: True}), ("sse41", []))

    def test_old_cpu(self):
        self.assertEqual(self.run_with(pf={bg.PF_SSE4_1: False, bg.PF_SSE3: True}, clang=False), ("sse2", ["clang"]))

    def test_old_windows_new_cpu(self):
        self.assertEqual(self.run_with(pf={bg.PF_SSE4_1: False, bg.PF_SSE3: True}, clang=True), ("sse41", ["clang"]))

    def test_release_without_sse2_runtime(self):
        self.assertEqual(self.run_with(shipped=False, pf={bg.PF_SSE4_1: False}, clang=False), ("sse41", []))

    def test_forced_by_environment(self):
        self.assertEqual(self.run_with(pf={bg.PF_SSE4_1: True}, env={"T5DR_RUNTIME": "sse2"}), ("sse2", []))

    def test_test_cpu_model_ignores_windows(self):
        # T5DR_TEST_CPU_MODEL stands in for the processor: Windows' answer about this PC's own one is not asked
        got = self.run_with(pf={bg.PF_SSE4_1: True, bg.PF_SSE3: True}, clang=False,
                            env={"T5DR_TEST_CPU_MODEL": "core2"})
        self.assertEqual(got, ("sse2", ["clang"]))


def find_clang_bin():
    for d in (os.path.join(ROOT, "toolchain", "llvm", "bin"), r"C:\Program Files\LLVM\bin"):
        if os.path.isfile(os.path.join(d, "clang-cl.exe")):
            return d
    return None


@unittest.skipUnless(os.name == "nt" and find_clang_bin(), "needs clang-cl on Windows")
class ClangCpuid(unittest.TestCase):
    """The real clang probe with stand-in processors (LLVM's own CPU tables)."""

    def model(self, name):
        with mock.patch.dict(os.environ, {"T5DR_TEST_CPU_MODEL": name}):
            return bg.clang_has_sse41(find_clang_bin())

    def test_models(self):
        self.assertIs(self.model("core2"), False)        # Core 2 "Merom" (2006): SSSE3, no SSE4.1
        self.assertIs(self.model("amdfam10"), False)     # Phenom II / Athlon II
        self.assertIs(self.model("k8-sse3"), False)      # Athlon 64 X2 (late)
        self.assertIs(self.model("penryn"), True)        # Core 2 "Penryn" (2008)
        self.assertIs(self.model("sandybridge"), True)

    def test_no_clang(self):
        self.assertIsNone(bg.clang_has_sse41(os.path.join(ROOT, "no-such-dir")))


class CompileStep(unittest.TestCase):
    """compile_game_dll copies the chosen runtime to build/cmake/t5dr.exe, links against its t5dr.lib and asks
    build_game_dll.py for --simd sse2; the stamp says which."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="t5dr_sse2rt_")
        self.host = os.path.join(self.tmp, "runtime")
        os.makedirs(os.path.join(self.host, "sse2"))
        for d, tag in ((self.host, b"normal"), (os.path.join(self.host, "sse2"), b"sse2")):
            for n in ("t5dr.exe", "t5dr.lib"):
                with open(os.path.join(d, n), "wb") as f:
                    f.write(tag + b" " + n.encode())
        self.out = os.path.join(self.tmp, "native")
        self.P = mock.MagicMock()
        self.P.cmake = os.path.join(self.out, "build", "cmake")
        self.P.build = os.path.join(self.out, "build")
        self.P.exe = os.path.join(self.P.cmake, "t5dr.exe")
        self.P.stamp = os.path.join(self.P.build, "t5dr_build.json")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def compile(self, simd):
        runs, stamps = [], []
        a = mock.MagicMock(force=False)
        with mock.patch.object(bg, "HOST_DIR", self.host), \
                mock.patch.object(bg, "HOST_SSE2_DIR", os.path.join(self.host, "sse2")), \
                mock.patch.object(bg, "P", self.P), \
                mock.patch.object(bg.prereqs, "portable_llvm", return_value="llvm"), \
                mock.patch.object(bg, "runtime_for_this_pc", return_value=(simd, "test")), \
                mock.patch.object(bg, "need_program", return_value={"pgo": True}), \
                mock.patch.object(bg, "run", side_effect=lambda cmd, **k: runs.append(cmd)), \
                mock.patch.object(bg, "write_stamp", side_effect=lambda c, extra=None: stamps.append(extra)), \
                mock.patch("builtins.print"):
            bg.compile_game_dll(a)
        with open(self.P.exe, "rb") as f:
            exe = f.read()
        return runs[0], stamps[0], exe

    def test_sse2(self):
        cmd, stamp, exe = self.compile("sse2")
        self.assertEqual(exe, b"sse2 t5dr.exe")
        self.assertEqual(cmd[cmd.index("--host-lib") + 1], os.path.join(self.host, "sse2", "t5dr.lib"))
        self.assertEqual(cmd[cmd.index("--simd") + 1], "sse2")
        self.assertEqual(stamp, {"runtime": "sse2"})

    def test_normal_is_unchanged(self):
        cmd, stamp, exe = self.compile("sse41")
        self.assertEqual(exe, b"normal t5dr.exe")
        self.assertEqual(cmd[cmd.index("--host-lib") + 1], os.path.join(self.host, "t5dr.lib"))
        self.assertNotIn("--simd", cmd)                  # build_game_dll.py runs exactly as before
        self.assertEqual(stamp, {"runtime": "sse41"})

    def test_switching_back_and_forth_replaces_the_exe(self):
        self.assertEqual(self.compile("sse2")[2], b"sse2 t5dr.exe")
        self.assertEqual(self.compile("sse41")[2], b"normal t5dr.exe")
        # the sse2 folder itself is never copied into build/cmake
        self.assertFalse(os.path.exists(os.path.join(self.P.cmake, "sse2")))


class BuildDllOptions(unittest.TestCase):
    def test_simd_sse2_drops_msse41_and_targets_the_baseline(self):
        with open(os.path.join(ROOT, "tools", "build_game_dll.py"), encoding="utf-8") as f:
            src = f.read()
        self.assertIn('if a.simd == "sse2" and march == "auto":', src)
        self.assertIn('march, why = "none"', src)
        self.assertRegex(src, r'if a\.simd == "sse41":\s+cmd \+= \["-msse4\.1"\]')


class CodeId(unittest.TestCase):
    def test_sse2_runtime_is_part_of_the_release_identity(self):
        tmp = tempfile.mkdtemp(prefix="t5dr_sse2id_")
        try:
            host = os.path.join(tmp, "runtime")
            os.makedirs(os.path.join(host, "sse2"))
            for n in ("t5dr.exe", "t5dr.lib"):
                for d in (host, os.path.join(host, "sse2")):
                    with open(os.path.join(d, n), "wb") as f:
                        f.write(b"x" + d.encode())
            with mock.patch.object(bg, "HOST_DIR", host), \
                    mock.patch.object(bg, "HOST_SSE2_DIR", os.path.join(host, "sse2")):
                with_sse2 = (bg.code_id(), bg.crossplay_group())
                with open(os.path.join(host, "sse2", "t5dr.exe"), "wb") as f:
                    f.write(b"other")
                other = (bg.code_id(), bg.crossplay_group())
                os.remove(os.path.join(host, "sse2", "t5dr.exe"))
                without = (bg.code_id(), bg.crossplay_group())
            self.assertNotEqual(with_sse2, other)
            self.assertNotEqual(with_sse2, without)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class Launcher(unittest.TestCase):
    def setUp(self):
        import core
        self.core = core
        self.tmp = tempfile.mkdtemp(prefix="t5dr_sse2la_")
        os.makedirs(os.path.join(self.tmp, "build"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def stamp(self, **keys):
        with open(os.path.join(self.tmp, "build", "t5dr_build.json"), "w") as f:
            json.dump(keys, f)

    def test_build_runtime_and_log_line(self):
        self.assertIsNone(self.core.build_runtime(self.tmp))
        self.stamp(runtime="sse2")
        self.assertEqual(self.core.build_runtime(self.tmp), "sse2")
        self.assertIn("SSE2", self.core.RUNTIME_LOG["sse2"])
        self.assertTrue(all(v.startswith("[launcher] runtime: ") for v in self.core.RUNTIME_LOG.values()))

    def test_fatal_message_asks_for_a_rebuild_when_the_sse2_runtime_ships(self):
        lines = ["[cpu] FATAL (exit code 14): this processor lacks SSE4.1, which T5DR Online needs"]
        with mock.patch.object(self.core.build_game, "prebuilt_host_sse2", return_value=True):
            self.assertIn("BUILD GAME again", self.core.explain_exit(14, lines))
        with mock.patch.object(self.core.build_game, "prebuilt_host_sse2", return_value=False):
            self.assertIn("too old", self.core.explain_exit(14, lines))

    def test_game_state_asks_for_the_other_runtime(self):
        core = self.core
        with mock.patch.object(core.build_game, "prebuilt_host_sse2", return_value=True),                 mock.patch.object(core, "this_pc_runtime", return_value="sse2"),                 mock.patch.object(core, "game_exe", return_value=__file__),                 mock.patch.object(core.build_game, "sha1", return_value="abc"),                 mock.patch.dict(core.build_game.PROGRAMS, {"abc": {"title_id": "NPUB30009", "version": "01.00"}}),                 mock.patch.object(core.build_game, "code_id", return_value="cid"):
            os.makedirs(os.path.join(self.tmp, "game"))
            open(os.path.join(self.tmp, "game", "EBOOT.elf"), "wb").close()
            self.stamp(code_id="cid", runtime="sse41")
            st = core.game_state(self.tmp)
            self.assertTrue(st["needs_rebuild"])
            self.assertIn("no SSE4.1", st["text"])
            self.stamp(code_id="cid")                       # an older stamp without the key = the normal runtime
            self.assertTrue(core.game_state(self.tmp)["needs_rebuild"])
            self.stamp(code_id="cid", runtime="sse2")
            self.assertTrue(core.game_state(self.tmp)["ok"])
            with mock.patch.object(core, "this_pc_runtime", return_value="sse41"):
                st = core.game_state(self.tmp)
                self.assertTrue(st["needs_rebuild"])
                self.assertIn("faster version", st["text"])
                self.stamp(code_id="cid", runtime="sse41")
                self.assertTrue(core.game_state(self.tmp)["ok"])
        # a release without runtime/sse2 never asks
        with mock.patch.object(core.build_game, "prebuilt_host_sse2", return_value=False),                 mock.patch.object(core, "this_pc_runtime", side_effect=AssertionError("not asked")),                 mock.patch.object(core, "game_exe", return_value=__file__),                 mock.patch.object(core.build_game, "sha1", return_value="abc"),                 mock.patch.dict(core.build_game.PROGRAMS, {"abc": {"title_id": "NPUB30009", "version": "01.00"}}),                 mock.patch.object(core.build_game, "code_id", return_value="cid"):
            self.stamp(code_id="cid", runtime="sse41")
            self.assertTrue(core.game_state(self.tmp)["ok"])

    def test_problem_report_keeps_the_runtime_lines(self):
        import problem_report
        for line in list(self.core.RUNTIME_LOG.values()) + [
                "[cpu] runtime: SSE2 build for processors without SSE4.1 (runtime\\sse2, about 1.3x the processor "
                "time of the normal build)"]:
            self.assertTrue(problem_report.GAME_LOG_FACTS.match(line), line)
        self.assertFalse(problem_report.GAME_LOG_FACTS.match("[launcher] Wine 9.0"))

    def test_sse2_runtime_names_itself_in_the_log(self):
        with open(os.path.join(ROOT, "src", "platform", "cpu_check.cpp"), encoding="utf-8") as f:
            src = f.read()
        base = src[src.index("#ifdef T5DR_X86_BASELINE"):src.index("#endif")]
        self.assertIn('"[cpu] runtime: SSE2 build', base)
        self.assertNotIn("getenv", base)                 # always, not only with PS3_DEBUG

    def test_this_pc_runtime_is_asked_once(self):
        self.core._THIS_PC_RUNTIME.clear()
        try:
            with mock.patch.object(self.core.build_game, "runtime_for_this_pc", return_value=("sse2", "x")) as m:
                self.assertEqual(self.core.this_pc_runtime(), "sse2")
                self.assertEqual(self.core.this_pc_runtime(), "sse2")
            self.assertEqual(m.call_count, 1)
        finally:
            self.core._THIS_PC_RUNTIME.clear()


def find_tree():
    """A ps3recomp tree with patch 0126 applied (PS3RECOMP_DIR or deps/ps3recomp)."""
    for d in (os.environ.get("PS3RECOMP_DIR"), os.path.join(ROOT, "deps", "ps3recomp")):
        h = os.path.join(d or "", "runtime", "spu", "spu_helpers.h")
        if d and os.path.isfile(h):
            with open(h, encoding="utf-8", errors="replace") as f:
                if "SPU_X86_SSE2_ISA" in f.read():
                    return d
    return None


@unittest.skipUnless(os.name == "nt" and find_clang_bin() and find_tree() and shutil.which("git"),
                     "needs clang-cl, git and a ps3recomp tree with patch 0126 (PS3RECOMP_DIR)")
class NormalBuildUnchanged(unittest.TestCase):
    """Patch 0126 must not change what the normal (SSE4.1) build compiles: spu_helpers.h with and without it,
    preprocessed with the flags the lifted SPU code gets (-msse4.1, x86-64-v3 or not, the three float modes),
    gives the same tokens. The PPU headers are not touched by 0126 at all."""

    def test_spu_helpers_tokens(self):
        import subprocess
        tree = find_tree()
        cl = os.path.join(find_clang_bin(), "clang-cl.exe")
        patch = os.path.join(ROOT, "patches", "ps3recomp", "0126-sse2-baseline.patch")
        with open(patch, encoding="utf-8") as f:
            touched = sorted(set(l.split()[2][2:] for l in f if l.startswith("diff --git ")))
        self.assertFalse([p for p in touched if p.startswith(("runtime/ppu/", "libs/", "include/"))], touched)
        tmp = tempfile.mkdtemp(prefix="t5dr_sse2pp_")
        try:
            for side in ("old", "new"):
                shutil.copytree(os.path.join(tree, "runtime", "spu"), os.path.join(tmp, side, "runtime", "spu"),
                                ignore=shutil.ignore_patterns("tests", "*.c", "*.cpp"))
            r = subprocess.run(["git", "apply", "-R", "--include=runtime/spu/spu_helpers.h", patch],
                               cwd=os.path.join(tmp, "old"), capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            src = os.path.join(tmp, "t.c")
            with open(src, "w") as f:
                f.write('#include "spu_helpers.h"\n')

            def tokens(side, flags):
                r = subprocess.run([cl, "/nologo", "-TC", "/std:c17", "/DSPU_USE_DISPATCH_MT", *flags,
                                    "/I" + os.path.join(tmp, side, "runtime", "spu"),
                                    "/I" + os.path.join(tree, "include"), "/I" + os.path.join(tree, "runtime", "ppu"),
                                    "/I" + os.path.join(tree, "runtime"), "/EP", src],
                                   capture_output=True, text=True, errors="replace")
                self.assertEqual(r.returncode, 0, r.stderr[-1500:])
                return r.stdout.split()
            for isa in (["-msse4.1"], ["-msse4.1", "-march=x86-64-v3"], ["-msse4.1", "-mavx"]):
                for mode in ([], ["/DSPU_NEAR_FLOAT"], ["/DSPU_FAST_FLOAT"]):
                    self.assertEqual(tokens("old", isa + mode), tokens("new", isa + mode), isa + mode)
            self.assertNotEqual(tokens("old", []), tokens("new", []))     # the baseline side does change
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class PackageScan(unittest.TestCase):
    """package_release's game-data scan: the SSE2 runtime passes like the normal one, and the same rules still catch
    lifted code or a game file put next to it."""

    def scan(self, files):
        tmp = tempfile.mkdtemp(prefix="t5dr_sse2scan_")
        try:
            for rel, data in files.items():
                p = os.path.join(tmp, *rel.split("/"))
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, "wb") as f:
                    f.write(data)
            bad, count, _ = pr.scan_files(pr.iter_dir(tmp), [], {})
            return bad, count
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def runtime_like(self):
        return b"MZ" + b"\0" * 62 + b"PE\0\0" + os.urandom(4096)

    def test_runtime_sse2_passes(self):
        bad, count = self.scan({"runtime/t5dr.exe": self.runtime_like(), "runtime/t5dr.lib": b"!<arch>\n" + b"x" * 64,
                                "runtime/sse2/t5dr.exe": self.runtime_like(),
                                "runtime/sse2/t5dr.lib": b"!<arch>\n" + b"y" * 64})
        self.assertEqual((bad, count), ([], 4))

    def test_lifted_code_or_game_files_in_runtime_sse2_are_caught(self):
        lifted = self.runtime_like() + b"".join(b"func_%08X " % (0x10000 + i * 4) for i in range(4000))
        bad, _ = self.scan({"runtime/sse2/t5dr.exe": lifted, "runtime/sse2/EBOOT.BIN": b"\0" * 128,
                            "runtime/sse2/t5dr_game.dll": b"x" * 128})
        names = sorted({n.replace(os.sep, "/") for n, _ in bad})
        self.assertEqual(names, ["runtime/sse2/EBOOT.BIN", "runtime/sse2/t5dr.exe", "runtime/sse2/t5dr_game.dll"],
                         bad)

    def test_staged_folder_of_a_real_release_has_both_runtimes(self):
        # tools/smoke_release.py expects both in every release zip
        with open(os.path.join(ROOT, "tools", "smoke_release.py"), encoding="utf-8") as f:
            src = f.read()
        self.assertIn('"runtime/sse2/t5dr.exe", "runtime/sse2/t5dr.lib"', src)
        with open(os.path.join(ROOT, "tools", "package_release.py"), encoding="utf-8") as f:
            src = f.read()
        self.assertIn('args.append("-DT5DR_X86_BASELINE=ON")', src)
        self.assertIn('"--fail-on", "sse3,ssse3,sse4.1,sse4.2,popcnt,lzcnt,bmi,movbe,avx,aes"', src)


if __name__ == "__main__":
    unittest.main()
