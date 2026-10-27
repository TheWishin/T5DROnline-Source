"""The macOS port (docs/MACOS.md, docs/MACOS_ONLINE_TEST.md) as far as it can be checked on Windows.

- src/ reaches the host only through src/platform (t5_win.h, t5_plat.h,
  t5_sock.h): no file outside it includes <windows.h>, Winsock or the MSVC
  intrinsics header, and every Win32-style call it makes outside a Windows-only
  block is something the runtime's POSIX shim or t5_plat.h provides.
- The POSIX half (src/platform/t5_plat_posix.c, t5_sock.h) passes
  clang -fsyntax-only for arm64 and x86-64 macOS and x86-64 Linux, against the
  declaration-only headers in tests/posix_sysroot (the real system headers when
  this runs on macOS or Linux).
- Every src/ file passes clang -fsyntax-only for arm64 macOS (the macOS online
  build, CMake T5DR_MACOS_ONLINE) against the runtime's POSIX shim, those
  headers and a declaration-only C++ standard library (posix_sysroot/include/c++/v1):
  LP64 type widths, the macOS libc, BSD sockets -- what a Windows compile cannot see.
- Every guest function src/ detours has a hook slot (src/rollback/hook_slots.txt):
  an arm64 Mac intercepts through the lifter's slots, not by patching code.
- The lifted code is compiled with -ffp-contract=off by both compiler drivers
  (clang-cl on Windows, clang elsewhere): Apple clang fuses a*b+c by default.
"""
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor

from helpers import ROOT

SRC = os.path.join(ROOT, "src")
PLATFORM = os.path.join(SRC, "platform")
SYSROOT = os.path.join(ROOT, "tests", "posix_sysroot", "include")

# Built into t5dr.exe on Windows only (CMakeLists.txt, if(WIN32)).
WINDOWS_ONLY = {os.path.join("platform", "cpu_check.cpp"), os.path.join("platform", "gpu_preference.c")}
HOST_HEADERS = ("windows.h", "winsock2.h", "ws2tcpip.h", "intrin.h", "xmmintrin.h", "emmintrin.h", "immintrin.h")


def src_files(exts=(".cpp", ".c", ".h")):
    for root, _, files in os.walk(SRC):
        for f in files:
            if f.endswith(exts):
                p = os.path.join(root, f)
                yield os.path.relpath(p, SRC), p


def read(p):
    with open(p, encoding="utf-8", errors="replace") as f:
        return f.read()


def strip_comments(text):
    text = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), text, flags=re.S)
    text = re.sub(r"//[^\n]*", "", text)
    return re.sub(r'"(?:\\.|[^"\\\n])*"', '""', text)


def outside_windows_blocks(text):
    """The lines a non-Windows build compiles: drops `#if defined(_WIN32)` / `#ifdef _WIN32`
    bodies (keeping their #else part) and `#if !defined(_WIN32)` else-parts."""
    out, stack = [], []        # stack of (kind, skipping)
    for line in text.splitlines():
        s = line.strip()
        m = re.match(r"#\s*(if|ifdef|ifndef|elif|else|endif)\b\s*(.*?)\s*$", s)
        if m:
            d, cond = m.group(1), m.group(2)
            if d in ("if", "ifdef", "ifndef"):
                win = (d == "ifdef" and cond == "_WIN32") or (d == "if" and re.fullmatch(r"defined\s*\(\s*_WIN32\s*\)", cond))
                notwin = (d == "ifndef" and cond == "_WIN32") or \
                    (d == "if" and re.fullmatch(r"!\s*defined\s*\(\s*_WIN32\s*\)", cond))
                stack.append(("win" if win else "notwin" if notwin else "other", bool(win)))
            elif d in ("else", "elif") and stack:
                kind, skip = stack[-1]
                if kind == "win":
                    stack[-1] = (kind, False)
                elif kind == "notwin":
                    stack[-1] = (kind, True)
            elif d == "endif" and stack:
                stack.pop()
            continue
        if not any(skip for _, skip in stack):
            out.append(line)
    return "\n".join(out)


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
        if c and os.path.isfile(os.path.join(c, "runtime", "platform", "win32_compat.h")):
            return c
    return None


def find_clang():
    for c in (os.environ.get("CLANG"), shutil.which("clang"), r"C:\Program Files\LLVM\bin\clang.exe"):
        if c and (os.path.isfile(c) or shutil.which(c)):
            return c
    return None


class SourceLayout(unittest.TestCase):
    def test_host_headers_only_in_platform(self):
        bad = []
        for rel, p in src_files():
            if rel.startswith("platform" + os.sep) or rel in WINDOWS_ONLY:
                continue
            for line in read(p).splitlines():
                m = re.match(r'\s*#\s*include\s*[<"]([^>"]+)[>"]', line)
                if m and os.path.basename(m.group(1)).lower() in HOST_HEADERS:
                    bad.append(f"{rel}: {line.strip()}")
        self.assertEqual(bad, [], "src/ must include host headers through src/platform/t5_win.h / t5_sock.h")

    def test_platform_header_used(self):
        users = [rel for rel, p in src_files() if '"../platform/t5_win.h"' in read(p)]
        self.assertGreaterEqual(len(users), 20, users)

    def test_win32_calls_are_provided_off_windows(self):
        tree = find_ps3recomp()
        if not tree:
            self.skipTest("no ps3recomp checkout (set PS3RECOMP_DIR)")
        provided = set()
        for h in ("win32_compat.h", "msvc_compat.h", "win32_backtrace.h"):
            provided |= set(re.findall(r"\b([A-Z_a-z][A-Za-z0-9_]*)\b", read(os.path.join(tree, "runtime", "platform", h))))
        plat = read(os.path.join(PLATFORM, "t5_plat.h"))
        posix_decls = plat.split("#if !defined(_WIN32)")[1].split("#else")[0]
        provided |= set(re.findall(r"\b(t5p_\w+)\s*\(", posix_decls))
        ours = set()
        texts = {}
        for rel, p in src_files((".cpp", ".h")):
            if rel in WINDOWS_ONLY:
                continue
            t = strip_comments(read(p))
            texts[rel] = outside_windows_blocks(t)
            ours |= set(re.findall(r"\b(?:struct|class|enum|union|namespace|typedef\s+[\w\s\*]+?)\s+([A-Za-z_]\w*)", t))
            ours |= set(re.findall(r"^[\w:<>\*&\s]+?\b([A-Za-z_]\w*)\s*\([^;{}]*\)\s*(?:const\s*)?\{", t, re.M))
            ours |= set(re.findall(r"#\s*define\s+([A-Za-z_]\w*)", t))
        missing = {}
        for rel, t in texts.items():
            for name in set(re.findall(r"\b([A-Z][a-z0-9]+[A-Z][A-Za-z0-9]*)\s*\(", t)):   # CamelCase calls: Win32 style
                if name not in provided and name not in ours:
                    missing.setdefault(name, []).append(rel)
            for name in set(re.findall(r"\b(_[a-z][a-z0-9_]+|__[a-z][a-z0-9_]+)\s*\(", t)):  # _stricmp, __rdtsc ...
                if name.startswith(("__builtin", "__atomic", "__llvm_")) or name in provided or name in ours:
                    continue
                missing.setdefault(name, []).append(rel)
        self.assertEqual(missing, {}, "Win32/MSVC calls a macOS/Linux build would not find "
                                      "(add them to src/platform/t5_plat.h or guard them with #if defined(_WIN32))")

    def test_lifted_code_never_contracted(self):
        cm = read(os.path.join(ROOT, "CMakeLists.txt"))
        self.assertIn('set(_lifted_opts "${_clang_flag_prefix}-ffp-contract=off"', cm)
        self.assertRegex(cm, r'if\(MSVC\)\s*\n\s*set\(_clang_flag_prefix "/clang:"\)')
        # and on a Mac everything else in t5dr too (boot harness, loader, HLE table, src/)
        self.assertRegex(cm, r'if\(APPLE\)\s*\n\s*target_compile_options\(t5dr PRIVATE -ffp-contract=off\)')

    def test_macos_online_is_off_by_default(self):
        """A Mac build has the online modules only when asked (docs/MACOS_ONLINE_TEST.md): CMake's option is
        OFF, tools/build_game.py passes it from --macos-online only, and the stamp tells the lobby client."""
        cm = read(os.path.join(ROOT, "CMakeLists.txt"))
        self.assertRegex(cm, r'option\(T5DR_MACOS_ONLINE "[^"]*" OFF\)')
        self.assertIn("if(WIN32 OR T5DR_MACOS_ONLINE)", cm)
        bg = read(os.path.join(ROOT, "tools", "build_game.py"))
        self.assertIn('f"-DT5DR_MACOS_ONLINE={\'ON\' if online else \'OFF\'}"', bg)
        self.assertIn('write_stamp((cc[0] if cc else "cc") + " (CMake)", {"online": online})', bg)
        self.assertIn('ap.add_argument("--macos-online", action="store_true"', bg)
        # and a Mac that has them still offers no rollback unless asked (lockstep first)
        self.assertIn('getenv("T5_MACOS_ROLLBACK")', read(os.path.join(SRC, "rollback", "rb_net.cpp")))

    def test_every_detour_has_a_hook_slot(self):
        listed = set()
        for line in read(os.path.join(SRC, "rollback", "hook_slots.txt")).splitlines():
            tok = line.split("#", 1)[0].strip()
            if tok:
                listed.add(int(tok, 16))
        missing = {f"{a:08X}": sorted(f) for a, f in detour_targets().items() if a not in listed}
        self.assertEqual(missing, {}, "guest functions src/ detours without a hook slot: add them to "
                                      "src/rollback/hook_slots.txt (a Mac could not intercept them)")
        self.assertGreaterEqual(len(listed), 40)


def detour_targets():
    """{guest address: {files}} of every rb::detour(...) in src/: the first argument resolved through the
    file's k* constants and k*[] arrays (rb_icall.cpp's list variable is its kDetourCut)."""
    out = {}
    for rel, p in src_files((".cpp",)):
        if os.path.basename(p) == "rb_detour.cpp":
            continue
        t = strip_comments(read(p))
        consts = {m.group(1): int(m.group(2), 16) for m in re.finditer(r"\b(k\w+)\s*=\s*0x([0-9A-Fa-f]+)", t)}
        arrays = {m.group(1): [int(h, 16) for h in re.findall(r"0x([0-9A-Fa-f]+)", m.group(2))]
                  for m in re.finditer(r"\b(k\w+)\s*\[\s*\]\s*=\s*\{(.*?)\};", t, flags=re.S)}
        for m in re.finditer(r"\bdetour\(\s*([^,]+?)\s*,", t):
            arg = m.group(1)
            if re.fullmatch(r"0x[0-9A-Fa-f]+u?", arg):
                vals = [int(arg.rstrip("u"), 16)]
            elif arg in consts:
                vals = [consts[arg]]
            elif re.match(r"k\w+\s*\[", arg) and re.match(r"k\w+", arg).group(0) in arrays:
                vals = arrays[re.match(r"k\w+", arg).group(0)]
            elif arg == "a" and "kDetourCut" in arrays:
                vals = arrays["kDetourCut"]
            else:
                raise AssertionError(f"{rel}: cannot resolve detour({arg}, ...) -- teach tests/test_macos_port.py")
            for v in vals:
                if 0x10000 <= v < 0x1000000:
                    out.setdefault(v, set()).add(rel)
    return out


class PosixSyntax(unittest.TestCase):
    TARGETS = ("arm64-apple-macos12", "x86_64-apple-macos12", "x86_64-linux-gnu")

    @classmethod
    def setUpClass(cls):
        cls.clang = find_clang()
        if not cls.clang:
            raise unittest.SkipTest("no clang")

    def check(self, target, path, std="-std=c17"):
        cmd = [self.clang, f"--target={target}", "-fsyntax-only", std, "-Wall", "-Wextra", "-Werror",
               "-Wno-unused-parameter", "-Wno-unused-function", "-I", PLATFORM]
        if sys.platform == "win32" or not target.startswith(("x86_64-linux" if sys.platform.startswith("linux")
                                                             else "never", "arm64-apple" if sys.platform == "darwin"
                                                             else "never")):
            cmd += ["-nostdlibinc", "-isystem", SYSROOT]
        r = subprocess.run(cmd + [path], capture_output=True, text=True, errors="replace")
        self.assertEqual(r.returncode, 0, f"{target}: {' '.join(cmd)} {path}\n{r.stdout}{r.stderr}")

    def test_t5_plat_posix(self):
        for t in self.TARGETS:
            with self.subTest(target=t):
                self.check(t, os.path.join(PLATFORM, "t5_plat_posix.c"))

    def test_t5_sock(self):
        probe = (
            '#include "t5_sock.h"\n#include "t5_plat.h"\n'
            "int probe(void) {\n"
            "    if (!t5s_startup()) return 0;\n"
            "    t5s_socket s = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);\n"
            "    if (s == T5S_INVALID) return 0;\n"
            "    t5s_set_recv_timeout(s, 200); t5s_no_connreset(s);\n"
            "    struct sockaddr_in a; t5s_socklen l = sizeof a; char b[16];\n"
            "    long n = (long)recvfrom(s, b, sizeof b, 0, (struct sockaddr*)&a, &l);\n"
            "    int t = n == T5S_ERROR && t5s_error_is_transient(t5s_last_error());\n"
            "    t5s_close(s);\n"
            "    char sep = T5P_SEP[0]; uint64_t st = 0;\n"
            "    return t + (sep == '/') + t5p_file_stamp(\"x\", &st) + (int)t5p_fp_control();\n"
            "}\n")
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "sock_probe.c")
            with open(p, "w") as f:
                f.write(probe)
            for t in self.TARGETS:
                with self.subTest(target=t):
                    self.check(t, p)

    def test_sysroot_catches_platform_differences(self):
        """The stand-in headers keep the differences that matter: st_mtim is glibc's, not Apple's."""
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "neg.c")
            with open(p, "w") as f:
                f.write("#include <sys/stat.h>\nlong f(const char* p) { struct stat st; stat(p, &st); "
                        "return st.st_mtim.tv_nsec; }\n")
            r = subprocess.run([self.clang, "--target=arm64-apple-macos12", "-fsyntax-only", "-nostdlibinc",
                                "-isystem", SYSROOT, p], capture_output=True, text=True)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("st_mtim", r.stderr)

    def test_contraction_is_the_arm64_default(self):
        """Why -ffp-contract=off matters on a Mac: without it clang fuses a*b+c into one fmadd."""
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "c.c")
            with open(p, "w") as f:
                f.write("double f(double a, double b, double c) { return a * b + c; }\n")
            asm = {}
            for flag in ("", "-ffp-contract=off"):
                r = subprocess.run([self.clang, "--target=arm64-apple-macos12", "-O2", "-S", "-o", "-", p]
                                   + ([flag] if flag else []), capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, r.stderr)
                asm[flag] = r.stdout
            self.assertIn("fmadd", asm[""])
            self.assertNotIn("fmadd", asm["-ffp-contract=off"])



class MacSourceSyntax(unittest.TestCase):
    """clang -fsyntax-only of src/ for arm64 macOS, as CMake builds it with T5DR_MACOS_ONLINE: the runtime's
    POSIX shim (runtime/platform), the declaration-only C and C++ headers of tests/posix_sysroot, and the
    generic lifted header ppu_lifter.HEADER_PREAMBLE. It finds what a Windows compile cannot: a Win32 name
    outside a Windows-only block, a size_t/uint64_t mix std::min rejects on LP64, a macOS libc difference."""
    TARGET = "arm64-apple-macos13"
    WINDOWS_ONLY = {"cpu_check.cpp", "gpu_preference.c"}

    @classmethod
    def setUpClass(cls):
        cls.clang = find_clang()
        cls.tree = find_ps3recomp()
        if not cls.clang:
            raise unittest.SkipTest("no clang")
        if not cls.tree:
            raise unittest.SkipTest("no ps3recomp checkout (set PS3RECOMP_DIR)")
        cls.tmp = tempfile.mkdtemp(prefix="t5mac_")
        sys.path.insert(0, os.path.join(cls.tree, "tools"))
        try:
            import ppu_lifter   # noqa: E402  (the runtime's own tool)
            with open(os.path.join(cls.tmp, "ppu_recomp.h"), "w", encoding="utf-8", newline="\n") as f:
                f.write(ppu_lifter.HEADER_PREAMBLE)
        finally:
            sys.path.pop(0)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(getattr(cls, "tmp", ""), ignore_errors=True)

    def cmd(self, path, target=None):
        t = self.tree
        d = os.path.basename(os.path.dirname(path))
        cpp = path.endswith(".cpp")
        cmd = [self.clang, f"--target={target or self.TARGET}", "-fsyntax-only", "-std=c++20" if cpp else "-std=c17",
               "-ffp-contract=off", "-fno-caret-diagnostics", "-Wno-unknown-pragmas", "-D_CRT_SECURE_NO_WARNINGS",
               "-nostdlibinc"]
        if cpp:
            cmd += ["-isystem", os.path.join(SYSROOT, "c++", "v1")]
        cmd += ["-isystem", SYSROOT]
        if d == "netplay":
            cmd.append('-DT5DR_LIFTED_ARCH_NAME="none"')
        if d == "rollback":
            cmd.append("-DT5DR_HOOK_SLOTS")
        inc = {"rollback": ["runtime/syscalls"], "directfight": ["runtime/syscalls"], "perf": ["runtime/syscalls"],
               "training": ["libs/video"]}.get(d, [])
        inc += ["runtime/platform", "runtime/ppu", "runtime/spu", "runtime/prx", "include"]
        for i in [os.path.join(t, x) for x in inc] + [self.tmp] + sorted(
                p for p in glob.glob(os.path.join(t, "libs", "*")) if os.path.isdir(p)):
            cmd += ["-I", i]
        return cmd + [path]

    def test_src_compiles_for_arm64_macos(self):
        files = [p for rel, p in src_files((".cpp", ".c")) if os.path.basename(p) not in self.WINDOWS_ONLY]
        self.assertGreaterEqual(len(files), 25)

        def one(p):
            r = subprocess.run(self.cmd(p), capture_output=True, text=True, errors="replace")
            return p, r.returncode, r.stderr

        with ThreadPoolExecutor(max(2, min(8, (os.cpu_count() or 4) // 2))) as ex:
            results = list(ex.map(one, files))
        for p, rc, err in results:
            with self.subTest(file=os.path.relpath(p, SRC)):
                self.assertEqual(rc, 0, "\n".join(l for l in err.splitlines() if "error" in l)[:4000])

    def test_stdlib_stand_in_keeps_lp64_width_errors(self):
        """The one strict part of the C++ stand-in: std::min/max deduce one type, so a size_t (unsigned long on
        macOS) against a uint64_t (unsigned long long) fails as it does with the real libc++."""
        p = os.path.join(self.tmp, "lp64.cpp")
        with open(p, "w") as f:
            f.write("#include <algorithm>\n#include <stdint.h>\n#include <stddef.h>\n"
                    "uint64_t f(size_t a, uint64_t b) { return std::min(a, b); }\n")
        r = subprocess.run(self.cmd(p), capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("min", r.stderr)


class MacDeterminism(unittest.TestCase):
    """ps3recomp patch 0078: on arm64 the square root of a negative number gives the PC's NaN (sign set), and
    the optimizer may not fold that choice back into a plain fsqrt (it did at -O2 before the opaque asm)."""

    def test_sqrt_nan_sign_survives_the_optimizer(self):
        clang, tree = find_clang(), find_ps3recomp()
        if not clang or not tree:
            self.skipTest("no clang / ps3recomp checkout")
        hdr = os.path.join(tree, "runtime", "ppu", "ppu_fp_det.h")
        if "PPU_FP_OPAQUE" not in read(hdr):
            self.skipTest("this ps3recomp checkout predates patch 0078 (rebuild deps)")
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "s.c")
            with open(p, "w") as f:
                f.write('#include "ppu_fp_det.h"\ndouble f(double x) { return ppu_sqrt_det(x); }\n'
                        "float g(float x) { return ppu_sqrtf_det(x); }\n")
            r = subprocess.run([clang, "--target=arm64-apple-macos13", "-O2", "-ffp-contract=off", "-S", "-o", "-",
                                "-nostdlibinc", "-isystem", SYSROOT, "-I", os.path.dirname(hdr), p],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            asm = r.stdout.lower()
            self.assertIn("fsqrt", asm)
            self.assertIn("0xfff8000000000000", asm)       # the PC's default NaN for a negative double
            self.assertIn("0xffc00000", asm)               # and for a float
            self.assertIn("fcsel", asm)                    # chosen at run time, not folded away


if __name__ == "__main__":
    unittest.main()
