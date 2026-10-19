#!/usr/bin/env python3
"""Assemble the player release (folder + zip) and prove it holds nothing of the game.

    python tools/package_release.py --release --version 0.1.0-preview --llvm DIR
                                    [--ps3recomp SRC] [--out DIR] [--jobs N]
                                    [--keys FILE] [--game-dir DIR ...]
    python tools/package_release.py [--version V] [--bundle-python] [--llvm DIR] [--prebuilt-host] [--zip] ...
    python tools/package_release.py --scan-only PATH      (a folder or a zip)
    python tools/package_release.py --release ... --stub-compiler msvc|clang
    python tools/package_release.py --release ... --sign-stage prepare       (code signing, 1st half)
    python tools/package_release.py --release ... --sign-stage finish --signed-dir DIR   (2nd half)

--release is the published layout (= --bundle-python --prebuilt-host --zip, and
--llvm is required). The same command runs on a developer PC and in
.github/workflows/release.yml; see docs/RELEASING.md. Nothing here depends on
where things are installed: Visual Studio is found with vswhere (or the MSVC
environment of the calling shell is used when it has one), LLVM comes from
--llvm, Python is the interpreter running this script.

Output: <out>/T5DR-Online-<version>/ and, with --zip, <out>/T5DR-Online-<version>.zip
plus <out>/SHA256SUMS. <out> defaults to dist/ in the repository.

--version (MAJOR.MINOR.PATCH with an optional -suffix, e.g. 0.1.0-preview) is
stamped into README.txt, into release.json (the launcher shows it in its title
bar and header) and into the folder/zip name.

What goes in:
  T5DR Online.exe          small native starter (launcher/stub), built here with MSVC cl.exe + link.exe
                           (--stub-compiler msvc, the default) or with clang-cl (--stub-compiler clang)
  launcher/                the launcher (Python/tkinter)
  lobby/                   the lobby client, and the server for "Host for friends" (run.py, deploy/windows)
  tools/                   build_game.py, run_game.py, make_keys.py, unself.py, prereqs.py, ...
  patches/, CMakeLists.txt the port's own sources
  docs/, CHANGELOG.md      player docs (troubleshooting, German README, controls.ini, online)
  deps/ps3recomp/          ps3recomp (MIT) at the pinned commit with our patches applied
                           (tools/prepare_ps3recomp.py), only what the build uses -- no
                           fw_spu/ (Sony firmware), no tests, and pkg_extract.py with its
                           package keys taken out (it reads them from keys/ps3.keys, which
                           make_keys.py writes on the player's PC)
  python/                  (--bundle-python) a private copy of this CPython with tkinter and
                           pycryptodome, isolated by a ._pth file, self-tested after copying
  toolchain/llvm/          (--llvm) clang-cl + lld-link + clang's headers: the player's PC
                           compiles the game DLL with these (tools/build_game_dll.py)
  runtime/                 (--prebuilt-host) t5dr.exe + t5dr.lib, the runtime without game code
  LICENSES/, README.txt, release.json

Code signing (docs/RELEASING.md "Code signing"): the release workflow signs T5DR Online.exe and
runtime/t5dr.exe with a signing service when its secrets exist. A service works on files, so the run
is split in two: `--sign-stage prepare` builds and stages everything and copies the files to sign to
<out>/to-sign/ (same relative paths); after the service has signed them into a folder,
`--sign-stage finish --signed-dir DIR` puts the signed copies in, checks that each is the built file
plus a valid signature, recomputes the code ID (it hashes runtime/t5dr.exe) and writes the zip. Without
--sign-stage nothing changes: one run, unsigned.

What must never go in -- checked on the folder and again on the zip, the run
fails if any check fails:
  * game files by name (.pkg .rap .rif .edat .sdat .self .sprx .prx .elf EBOOT PARAM.SFO
    T55DATA, lifted ppu_recomp*/spu_recomp*, keys/, game/, native/, build/, logs, launcher.json)
  * game files by content (PPC64/SPU ELF, SELF "SCE\\0", PKG, PARAM.SFO magic)
  * any decryption key from --keys (raw bytes, hex in either case, C array form)
  * with --game-dir: any file byte-identical to a file in those folders
"""
import argparse
import datetime
import fnmatch
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import build_game  # noqa: E402
import check_binaries  # noqa: E402
import code_signing  # noqa: E402
import prereqs     # noqa: E402

OUR_FILES = [
    "CMakeLists.txt",
    "tools/build_game.py", "tools/run_game.py", "tools/make_keys.py", "tools/unself.py", "tools/prereqs.py",
    "tools/build_game_dll.py", "tools/lift_spu_jobs.py", "tools/gamedll/t5dr_game_dll.c", "tools/gamedll/t5dr_host.def",
    "tools/gamedll/ucrt_min.def",
    "launcher/t5dr_launcher.pyw", "launcher/core.py", "launcher/online.py", "launcher/updater.py",
    "launcher/release_sig.py",
    "launcher/problem_report.py", "launcher/problem_report_ui.py",
    "launcher/controls_ui.py", "launcher/controls_edit.py", "launcher/stub/t5dr_stub.c",
    "docs/RELEASE.md",
    # online: "Host for friends" entry point (works with the bundled, isolated Python) and the server list
    "lobby/run.py", "lobby/servers.json",
]
# Shipped when present (player docs; the players' README section links them).
OUR_OPTIONAL_FILES = ["CHANGELOG.md", "docs/TROUBLESHOOTING.md", "docs/README.de.md", "docs/ONLINE.md",
                      "docs/RANKED.md", "docs/controls.ini", "docs/HOSTING.md"]
# lobby/t5lobby/*.py is the client side (Online tab, match driver). lobby/t5lobby/server/ ships too:
# the Online tab's "Host for friends" runs a lobby server from the zip (lobby/run.py host); the
# Windows deploy scripts stay in the repository: script files in a game download get flagged
# (docs/HOSTING.md). The Linux/Docker packaging stays in the repository.
# src/ is the runtime's own code (netplay, direct fight, rollback, perf): CMakeLists.txt globs it,
# so a staged tree without it builds a runtime with no online play at all (the host build does not fail).
OUR_GLOBS = ["patches/ps3recomp/*.patch", "tools/gamedll/include/*.h", "lobby/t5lobby/*.py",
             "lobby/t5lobby/data/*.json", "lobby/t5lobby/server/*.py",
             "src/*/*.cpp", "src/*/*.h", "src/*/*.c", "src/*/*.manifest", "src/*/*.rc.in", "src/*/*/*.c"]

# ps3recomp: only what tools/build_game.py and CMakeLists.txt use.
PS3_KEEP_DIRS = ["include", "libs", "runtime", "third_party"]
PS3_KEEP_FILES = ["CMakeLists.txt", "LICENSE", "CONTRIBUTORS.md", "requirements.txt"]
PS3_TOOLS_GLOBS = ["tools/*.py", "tools/*.json"]
PS3_SKIP = ["*/__pycache__/*", "*.pyc", "*.prx", "*.sprx", "*.elf", "*.self", "*/spu_recomp.c", "*/spu_recomp.h",
            "*.m", "*.mm"]

FORBIDDEN_NAMES = ["*.pkg", "*.rap", "*.rif", "*.edat", "*.sdat", "*.self", "*.sprx", "*.prx", "*.elf",
                   "eboot.bin", "eboot.elf", "param.sfo", "t55data*", "*.keys", "ppu_recomp*", "spu_recomp*",
                   "spu_workloads.c", "launcher.json", "*.log", "t5dr.map", "*.dmp", "t5dr_game.dll", "t5dr_game.lib"]
# A player's own t5dr.exe holds the lifted code (~40 MB, a function table full of
# func_XXXXXXXX names) and is caught by the content checks; the prebuilt runtime
# t5dr.exe (--prebuilt-host, ~1.5 MB) holds none and may ship. Big binaries are
# only expected in toolchain/llvm.
BIG_BINARY = 20_000_000
RE_LIFTED = re.compile(rb"func_[0-9A-Fa-f]{8}")   # lifted code: ~1.5 per KB; ps3recomp's own files: < 40 in total
FORBIDDEN_DIRS = ["keys", "game", "native", "build", "gamedata", "scratch", "logs", "fw_spu"]

# MAJOR.MINOR.PATCH with an optional SemVer pre-release suffix: 0.1.0, 0.1.0-preview, 0.2.0-rc.1
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z]+(?:\.[0-9A-Za-z]+)*)?$")

# The LLVM license, for toolchain/llvm when the LLVM folder has none (the official
# Windows installer installs no license file). Text of llvm/LICENSE.TXT at llvmorg-23.1.3.
LLVM_LICENSE_COPY = os.path.join(ROOT, "tools", "licenses", "LLVM-LICENSE.TXT")

# Modules the bundled Python must have: the launcher (tkinter, ctypes), the build
# (pycryptodome, zlib, hashlib, multiprocessing for the lifter) and the lobby client
# (asyncio, ssl; sqlite3 for "Host for friends").
PY_SELFTEST = (
    "import sys, json, ssl, sqlite3, ctypes, zlib, hashlib, asyncio, multiprocessing, tkinter\n"
    "from Crypto.Cipher import AES\n"
    "assert AES.new(bytes(16), AES.MODE_ECB).encrypt(bytes(16)).hex() == '66e94bd4ef8a2c3b884cfa59ca342b2e'\n"
    "print(json.dumps({'version': sys.version.split()[0], 'tcl': tkinter.Tcl().eval('info patchlevel'),\n"
    "                  'prefix': sys.prefix, 'path': sys.path}))\n")


# --------------------------------------------------------------------------- helpers

def log(msg):
    print(msg, flush=True)


def warn(msg):
    log(f"WARNING: {msg}")
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::warning::{msg.splitlines()[0]}", flush=True)


def fail(msg):
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::error::{msg.splitlines()[0]}", flush=True)
    sys.exit(msg)


def copy(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)


def git(*args, cwd=None, check=True):
    return subprocess.run(["git", *args], cwd=cwd, check=check, capture_output=True, text=True)


def dir_size(d):
    return sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(d) for f in fs)


def mb(n):
    return f"{n / 1e6:,.1f} MB"


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def parse_version(s):
    """'0.1.0-preview' (a leading 'v' as in the tag is dropped); exits on anything else."""
    v = s[1:] if s[:1] in ("v", "V") and s[1:2].isdigit() else s
    if not VERSION_RE.match(v):
        fail(f"--version {s!r}: expected MAJOR.MINOR.PATCH with an optional -suffix "
             "(0.1.0, 0.1.0-preview, 0.2.0-rc.1)")
    return v


def msvc_prefix():
    """What a cmd.exe command needs in front to have the MSVC x64 environment: '' when this
    process already has it (CI's ilammy/msvc-dev-cmd, a Developer Command Prompt), else a
    call of vcvars64.bat found with vswhere, None when there is neither. (Calling vcvars a
    second time in an already set-up shell can overflow cmd's 8191-character line.)"""
    if (os.environ.get("VCINSTALLDIR") and os.environ.get("INCLUDE") and os.environ.get("LIB")
            and os.environ.get("VSCMD_ARG_TGT_ARCH", "x64").lower() == "x64"):
        return ""
    bat = prereqs.vcvars()
    return f'call "{bat}" >nul && ' if bat else None


def find_clang(llvm):
    """(clang-cl.exe, 'X.Y.Z') -- from --llvm when given, so the runtime, the stub and the
    player's game DLL are all compiled by the clang the zip ships; else prereqs' choice."""
    if llvm:
        exe = os.path.join(llvm, "bin", "clang-cl.exe")
        if not os.path.exists(exe):
            fail(f"--llvm {llvm}: no bin\\clang-cl.exe there")
    else:
        found = prereqs.clang_cl()
        if not found:
            return None, None
        exe = found[0]
    r = subprocess.run([exe, "--version"], capture_output=True, text=True)
    m = re.search(r"clang version (\d+\.\d+\.\d+)", r.stdout)
    return exe, (m.group(1) if m else "unknown")


def source_commit():
    """Commit of this checkout (with '-dirty' when tracked files differ from it)."""
    try:
        sha = git("rev-parse", "HEAD", cwd=ROOT).stdout.strip()
        dirty = git("status", "--porcelain", "--untracked-files=no", cwd=ROOT).stdout.strip()
        return sha + ("-dirty" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return os.environ.get("GITHUB_SHA", "unknown")


def build_time():
    """UTC build time; SOURCE_DATE_EPOCH (reproducible-builds convention) wins when set."""
    sde = os.environ.get("SOURCE_DATE_EPOCH")
    t = (datetime.datetime.fromtimestamp(int(sde), datetime.timezone.utc) if sde
         else datetime.datetime.now(datetime.timezone.utc))
    return t.isoformat(timespec="seconds")


def windows_only_env():
    """Environment with PATH reduced to Windows' own folders and no PYTHON* variables:
    what a player's PC without Python/LLVM/Visual Studio looks like to a child process."""
    env = {k: v for k, v in os.environ.items() if not k.upper().startswith("PYTHON")}
    sysroot = os.environ.get("SystemRoot", r"C:\Windows")
    env["PATH"] = os.pathsep.join([os.path.join(sysroot, "System32"), sysroot,
                                   os.path.join(sysroot, "System32", "Wbem")])
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


# --------------------------------------------------------------------------- parts

def add_our_files(stage):
    for rel in OUR_FILES:
        src = os.path.join(ROOT, rel)
        if not os.path.exists(src):
            fail(f"missing {rel}")
        copy(src, os.path.join(stage, rel))
    for rel in OUR_OPTIONAL_FILES:
        src = os.path.join(ROOT, rel)
        if os.path.exists(src):
            copy(src, os.path.join(stage, rel))
        else:
            log(f"  (no {rel} in this checkout, not shipped)")
    for g in OUR_GLOBS:
        for src in sorted(glob.glob(os.path.join(ROOT, g))):
            copy(src, os.path.join(stage, os.path.relpath(src, ROOT)))


def strip_pkg_keys(path):
    """ps3recomp's pkg_extract.py carries the PS3/PSP package keys as literals. The release
    may not contain keys, so swap them for a lookup in the player's keys file."""
    s = open(path, encoding="utf-8").read()
    helper = (
        "def _t5dr_key(name):\n"
        "    # T5DR release: the package keys are not shipped. tools/make_keys.py writes them to\n"
        "    # keys/ps3.keys on the player's PC; build_game.py passes its path in T5DR_KEYS.\n"
        "    path = os.environ.get(\"T5DR_KEYS\", \"\")\n"
        "    try:\n"
        "        for line in open(path):\n"
        "            if line.split(\"=\", 1)[0].strip() == name:\n"
        "                return bytes.fromhex(line.split(\"=\", 1)[1].strip())\n"
        "    except OSError:\n"
        "        pass\n"
        "    raise SystemExit(f\"package key {name} not found in T5DR_KEYS={path!r} -- run tools/make_keys.py\")\n\n")
    n_total = 0
    for var, name in (("PS3_GPKG_KEY", "PKG_AES_KEY"), ("PSP_PKG_KEY", "PKG_AES_KEY2")):
        s, n = re.subn(r'^(%s\s*=\s*)bytes\.fromhex\("[0-9a-fA-F]{32}"\)' % var,
                       lambda m, name=name: m.group(1) + f'_t5dr_key("{name}")', s, flags=re.M)
        n_total += n
    if n_total != 2:
        fail("pkg_extract.py changed upstream: could not take its keys out -- update strip_pkg_keys()")
    i = s.index("PS3_GPKG_KEY =")
    s = s[:i] + helper + s[i:]
    open(path, "w", encoding="utf-8", newline="\n").write(s)


def add_ps3recomp(stage, src):
    """ps3recomp at the pin with patches/ps3recomp/*.patch applied in name order -- by
    tools/prepare_ps3recomp.py, the same code CI and build_game.py's users rely on."""
    tmp = tempfile.mkdtemp(prefix="t5dr_ps3recomp_")
    try:
        tree = os.path.join(tmp, "ps3recomp")
        if os.path.exists(src):
            src = os.path.abspath(src)
        log(f"  ps3recomp {build_game.PS3RECOMP_COMMIT} + patches, from {src}")
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "prepare_ps3recomp.py"),
                            "--dest", tree, "--source", src], capture_output=True, text=True)
        if r.returncode:
            fail("ps3recomp could not be prepared:\n" + (r.stdout + r.stderr)[-4000:])
        for line in r.stdout.splitlines():
            if line.startswith("applied "):
                log(f"  {line}")
        dst = os.path.join(stage, "deps", "ps3recomp")
        picked = []
        for d in PS3_KEEP_DIRS:
            for dp, dns, fns in os.walk(os.path.join(tree, d)):
                dns[:] = sorted(x for x in dns if x != "__pycache__")
                picked += [os.path.join(dp, f) for f in sorted(fns)]
        picked += [os.path.join(tree, f) for f in PS3_KEEP_FILES if os.path.exists(os.path.join(tree, f))]
        for g in PS3_TOOLS_GLOBS:
            picked += sorted(glob.glob(os.path.join(tree, g)))
        n = 0
        for f in picked:
            rel = os.path.relpath(f, tree).replace("\\", "/")
            if any(fnmatch.fnmatch("/" + rel, pat) or fnmatch.fnmatch(rel, pat) for pat in PS3_SKIP):
                continue
            copy(f, os.path.join(dst, rel))
            n += 1
        strip_pkg_keys(os.path.join(dst, "tools", "pkg_extract.py"))
        patches = sorted(p for p in os.listdir(os.path.join(ROOT, "patches", "ps3recomp")) if p.endswith(".patch"))
        with open(os.path.join(dst, ".t5dr-vendored.json"), "w") as f:
            json.dump({"commit": build_game.PS3RECOMP_COMMIT, "patches": build_game.patch_digest(),
                       "patch_files": patches,
                       "source": f"{build_game.PS3RECOMP_URL} (branch {build_game.PS3RECOMP_BRANCH})"},
                      f, indent=1)
        log(f"  ps3recomp: {n} files, {mb(dir_size(dst))}")
        return patches
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def add_python(stage):
    """A private copy of the running CPython: interpreter, stdlib without tests/IDLE,
    tkinter with Tcl/Tk, pycryptodome. python3XY._pth keeps it away from any other Python.
    (python.org's "embeddable" zip has no tkinter, so it cannot run the launcher.)"""
    base = sys.base_prefix
    dst = os.path.join(stage, "python")
    ver = f"{sys.version_info.major}{sys.version_info.minor}"
    if not os.path.exists(os.path.join(base, "DLLs", "_tkinter.pyd")) or not os.path.isdir(os.path.join(base, "tcl")):
        fail(f"--bundle-python: the Python at {base} has no tkinter/Tcl -- use a python.org CPython with Tcl/Tk")
    for f in sorted(os.listdir(base)):
        p = os.path.join(base, f)
        if os.path.isfile(p) and (f.lower().endswith((".exe", ".dll")) or f.upper().startswith("LICENSE")):
            if f.lower() in ("python.exe", "pythonw.exe") or f.lower().endswith(".dll") or f.upper().startswith("LICENSE"):
                copy(p, os.path.join(dst, f))
    skip_lib = {"test", "idlelib", "ensurepip", "lib2to3", "turtledemo", "pydoc_data", "site-packages", "venv",
                "__pycache__", "tkinter/test", "unittest/test", "distutils/tests"}
    # macOS-only helper scripts. fetch_macholib.bat is one line ("svn export http://...") that
    # virus scanners flag as a downloader (Generic.BAT.Downloader, 8/65 on VirusTotal for
    # 0.1.8-preview); nothing ever runs it, so it stays out of the zip.
    skip_files = {"ctypes/macholib/fetch_macholib", "ctypes/macholib/fetch_macholib.bat"}
    for dp, dns, fns in os.walk(os.path.join(base, "Lib")):
        rel = os.path.relpath(dp, os.path.join(base, "Lib")).replace("\\", "/")
        dns[:] = sorted(d for d in dns if (d if rel == "." else f"{rel}/{d}") not in skip_lib and d != "__pycache__"
                        and not d.startswith("test"))
        for f in fns:
            if not f.endswith((".pyc",)) and (f if rel == "." else f"{rel}/{f}") not in skip_files:
                copy(os.path.join(dp, f), os.path.join(dst, "Lib", "" if rel == "." else rel, f))
    for dp, dns, fns in os.walk(dst):     # no batch files in the bundled Python at all
        bats = [f for f in fns if f.lower().endswith((".bat", ".cmd"))]
        if bats:
            fail(f"batch file(s) in the bundled Python (virus scanners flag them): {dp}: {bats}")
    for dp, dns, fns in os.walk(os.path.join(base, "DLLs")):
        for f in fns:
            if not f.startswith(("_test", "_ctypes_test", "_testcapi")):
                copy(os.path.join(dp, f), os.path.join(dst, "DLLs", os.path.relpath(os.path.join(dp, f),
                                                                                     os.path.join(base, "DLLs"))))
    for dp, dns, fns in os.walk(os.path.join(base, "tcl")):
        # tix8.4.3 (tkinter.tix, nothing here uses it) holds tix84.dll, the only unsigned DLL of python.org's Tcl/Tk
        dns[:] = [d for d in dns if (d not in ("demos", "tzdata", "msgs", "encoding") or "tk" in dp.lower())
                  and d != "nmake" and not d.lower().startswith("tix")]
        for f in fns:
            rel = os.path.relpath(os.path.join(dp, f), base)
            copy(os.path.join(dp, f), os.path.join(dst, rel))
    # Tcl needs its encoding tables; keep the ones a Western/CJK Windows uses.
    for d in os.listdir(os.path.join(base, "tcl")):
        if d.startswith("tcl8") and os.path.isdir(os.path.join(base, "tcl", d, "encoding")):
            enc_src = os.path.join(base, "tcl", d, "encoding")
            for f in os.listdir(enc_src):
                if f.startswith(("ascii", "cp125", "cp437", "cp850", "iso8859-1", "utf", "unicode", "cp932",
                                 "cp936", "cp949", "cp950", "identity")):
                    copy(os.path.join(enc_src, f), os.path.join(dst, "tcl", d, "encoding", f))
    # pycryptodome only (no pip, no other packages)
    try:
        import Crypto
    except ImportError:
        fail("--bundle-python needs pycryptodome in this Python (pip install -r tools/release-requirements.txt)")
    cdir = os.path.dirname(Crypto.__file__)
    for dp, dns, fns in os.walk(cdir):
        dns[:] = [d for d in dns if d not in ("__pycache__", "SelfTest")]
        for f in fns:
            if not f.endswith(".pyc"):
                copy(os.path.join(dp, f), os.path.join(dst, "Lib", "site-packages", "Crypto",
                                                       os.path.relpath(os.path.join(dp, f), cdir)))
    # No "import site": with it, site.py adds the player's own user site-packages
    # (%APPDATA%\Python\Python3XY\site-packages) to sys.path. Lib\site-packages is listed
    # here directly, which is all site would add for us (python.org's embeddable zip
    # ships its ._pth the same way).
    with open(os.path.join(dst, f"python{ver}._pth"), "w") as f:
        f.write("Lib\nDLLs\nLib\\site-packages\n.\n")
    add_pycryptodome_license(stage)
    info = check_python(stage)
    log(f"  python: {mb(dir_size(dst))}, CPython {info['version']}, Tcl/Tk {info['tcl']}, pycryptodome "
        f"{getattr(Crypto, '__version__', '?')} (self-test passed)")
    return info["version"]


def add_pycryptodome_license(stage):
    try:
        from importlib import metadata
        dist = metadata.distribution("pycryptodome")
        for f in dist.files or []:
            if os.path.basename(str(f)).upper().startswith(("LICENSE", "COPYING")):
                copy(str(dist.locate_file(f)), os.path.join(stage, "LICENSES", "pycryptodome-" + os.path.basename(str(f))))
                return
    except Exception as e:      # metadata missing: say so, the release still needs the file
        log(f"  pycryptodome license lookup failed: {e}")
    fail("no license file found for pycryptodome (its dist-info has none?)")


def check_python(stage):
    """Run the bundled interpreter with a Windows-only PATH and no PYTHON* variables: it
    must import what the launcher, the build and the lobby need, and see only its own
    folder on sys.path."""
    pydir = os.path.join(stage, "python")
    r = subprocess.run([os.path.join(pydir, "python.exe"), "-B", "-c", PY_SELFTEST], capture_output=True,
                       text=True, env=windows_only_env(), cwd=stage)
    if r.returncode:
        fail("the bundled Python failed its self-test:\n" + r.stdout + r.stderr)
    info = json.loads(r.stdout.strip().splitlines()[-1])
    pyabs = os.path.normcase(os.path.abspath(pydir))
    outside = [p for p in info["path"] if p and not os.path.normcase(os.path.abspath(p)).startswith(pyabs)]
    if outside:
        fail(f"the bundled Python is not isolated; sys.path has {outside}")
    return info


def add_llvm(stage, llvm):
    dst = os.path.join(stage, "toolchain", "llvm")
    for exe in ("clang-cl.exe", "lld-link.exe"):
        src = os.path.join(llvm, "bin", exe)
        if not os.path.exists(src):
            fail(f"--llvm {llvm}: no bin\\{exe}")
        copy(src, os.path.join(dst, "bin", exe))
    inc_root = os.path.join(llvm, "lib", "clang")
    ver = sorted(os.listdir(inc_root), key=lambda v: [int(x) if x.isdigit() else x for x in re.split(r"[.]", v)])[-1]
    shutil.copytree(os.path.join(inc_root, ver, "include"), os.path.join(dst, "lib", "clang", ver, "include"))
    lic = [c for c in (os.path.join(llvm, "LICENSE.TXT"), os.path.join(llvm, "share", "doc", "LLVM", "LICENSE.TXT"),
                       LLVM_LICENSE_COPY) if os.path.exists(c)]
    if not lic:
        fail("no LLVM license text to ship with toolchain/llvm")
    copy(lic[0], os.path.join(stage, "LICENSES", "LLVM-LICENSE.TXT"))
    log(f"  llvm: {mb(dir_size(dst))} (clang resource headers {ver})")


def add_prebuilt_host(stage, clang, jobs, version="0.0.0-dev"):
    """runtime/t5dr.exe + t5dr.lib: ps3recomp's runtime without any game code (CMake
    -DT5DR_GAME_DLL=ON), built from exactly the sources staged above, static C runtime
    (no Visual C++ redistributable needed). The player's PC then compiles only the
    lifted code, into t5dr_game.dll (tools/build_game_dll.py)."""
    pre = msvc_prefix()
    cm, nj = prereqs.cmake_ninja()
    if pre is None or not (clang[0] and cm and nj):
        fail("--prebuilt-host needs Visual Studio Build Tools (or an MSVC environment), clang-cl, CMake and Ninja")
    tmp = tempfile.mkdtemp(prefix="t5dr_host_")
    try:
        args = [f'"{cm}"', "-S", f'"{stage}"', "-B", f'"{tmp}"', "-G", "Ninja", f'-DCMAKE_MAKE_PROGRAM="{nj}"',
                "-DCMAKE_BUILD_TYPE=Release", "-DT5DR_GAME_DLL=ON", "-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded",
                f'-DT5DR_VERSION="{version}"',
                f'-DPS3RECOMP_DIR="{os.path.join(stage, "deps", "ps3recomp")}"', f'-DSPU_DIR="{tmp}"',
                f'-DPython3_EXECUTABLE="{sys.executable}"',
                f'-DCMAKE_C_COMPILER="{clang[0]}"', f'-DCMAKE_CXX_COMPILER="{clang[0]}"']
        build = f'"{cm}" --build "{tmp}"' + (f" -j {jobs}" if jobs else "")
        cmd = f'{pre}{" ".join(args)} && {build}'
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")   # no __pycache__ in the staged tools
        log(f"  building the runtime host (clang-cl {clang[1]}{', -j %d' % jobs if jobs else ''}) ...")
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, env=env)
        if r.returncode:
            fail("host build failed:\n" + (r.stdout + r.stderr)[-4000:])
        dst = os.path.join(stage, "runtime")
        for n in ("t5dr.exe", "t5dr.lib"):
            copy(os.path.join(tmp, n), os.path.join(dst, n))
        log(f"  runtime/t5dr.exe: {os.path.getsize(os.path.join(dst, 't5dr.exe')):,} bytes")
        # It must run on any x64 CPU with SSE4.1: AVX & co. only inside the C library's CPUID dispatch.
        objdump = os.path.join(os.path.dirname(clang[0]), "llvm-objdump.exe")
        mapf = os.path.join(tmp, "t5dr.map")
        if os.path.exists(objdump) and os.path.exists(mapf):
            dis = subprocess.run([objdump, "-d", "--no-show-raw-insn", os.path.join(dst, "t5dr.exe")],
                                 capture_output=True, text=True, errors="replace").stdout
            bad = check_binaries.isa_findings(dis, check_binaries.read_map(mapf))
            if bad:
                fail("runtime/t5dr.exe uses instructions beyond SSE4.1 outside the C library (it would crash on "
                     "older CPUs):\n" + "\n".join(f"  {dict(c)} in {w}" for w, c in sorted(bad.items())[:20]))
            log("  runtime/t5dr.exe: nothing beyond SSE4.1 outside the C library's CPUID dispatch")
        else:
            log("  (no llvm-objdump next to clang-cl or no linker map: instruction-set check skipped)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def staged_code_id(stage):
    """The code ID that builds made from this folder will carry (t5dr_build.json, and what the
    launcher compares to ask for a rebuild). build_game.code_id() also hashes runtime/t5dr.exe and
    tools/gamedll next to the script that runs it, so it has to run from the staged copy -- from this
    checkout it hashes something else (and the zip's release.json named an ID no build ever had)."""
    code = ("import sys; sys.dont_write_bytecode = True; sys.path.insert(0, sys.argv[1]); "
            "import build_game; print(build_game.code_id())")
    r = subprocess.run([sys.executable, "-B", "-c", code, os.path.join(stage, "tools")],
                       capture_output=True, text=True, env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    if r.returncode or not r.stdout.strip():
        fail("could not compute the code ID of the staged folder:\n" + (r.stdout + r.stderr)[-1500:])
    return r.stdout.strip().splitlines()[-1]


STUB_RC = """#include <windows.h>
1 ICON "{ico}"
1 24 "{manifest}"
1 VERSIONINFO
 FILEVERSION {v1},{v2},{v3},0
 PRODUCTVERSION {v1},{v2},{v3},0
 FILEFLAGSMASK 0x3fL
 FILEFLAGS 0x0L
 FILEOS 0x40004L
 FILETYPE 0x1L
 FILESUBTYPE 0x0L
BEGIN
  BLOCK "StringFileInfo"
  BEGIN
    BLOCK "040904b0"
    BEGIN
      VALUE "CompanyName", "T5DR Online"
      VALUE "FileDescription", "T5DR Online launcher"
      VALUE "FileVersion", "{version}"
      VALUE "InternalName", "T5DR Online"
      VALUE "LegalCopyright", "MIT License - T5DR Online contributors"
      VALUE "OriginalFilename", "T5DR Online.exe"
      VALUE "ProductName", "T5DR Online"
      VALUE "ProductVersion", "{version}"
    END
  END
  BLOCK "VarFileInfo"
  BEGIN
    VALUE "Translation", 0x409, 1200
  END
END
"""


STUB_COMPILERS = ("msvc", "clang")


def default_stub_compiler():
    """--stub-compiler's default: the T5DR_STUB_COMPILER environment variable (the release workflow
    sets it from the repository variable of that name), else msvc."""
    v = os.environ.get("T5DR_STUB_COMPILER", "").strip().lower()
    return v if v in STUB_COMPILERS else "msvc"


# Launcher stub variants for the antivirus experiments (docs/RELEASING.md "The launcher stub"). The default,
# 'current', is the build that was sent to VirusTotal; the others change one thing at a time:
#   plain      current + no PATH fallback + a CodeView debug entry (PDB name only, like ordinary programs)
#              + an icon whose small sizes are bitmaps (the resource section stops looking packed)
#   dynamic    plain + the dynamic C runtime (imports like pythonw.exe; vcruntime140.dll ships beside the exe)
#   inprocess  plain + no child process: python312.dll is loaded into the stub and Py_Main is called, as
#              pythonw.exe does itself (needs the import library of the CPython that is bundled)
STUB_VARIANTS = {
    "current": {"icon": "t5dr.ico", "defines": [], "crt": "/MT", "debug": False, "python": False,
                "vcruntime": False},
    "plain": {"icon": "t5dr_bmp.ico", "defines": ["T5DR_STUB_NO_PATH_FALLBACK"], "crt": "/MT", "debug": True,
              "python": False, "vcruntime": False},
    "dynamic": {"icon": "t5dr_bmp.ico", "defines": ["T5DR_STUB_NO_PATH_FALLBACK"], "crt": "/MD", "debug": True,
                "python": False, "vcruntime": True},
    "inprocess": {"icon": "t5dr_bmp.ico", "defines": ["T5DR_STUB_INPROCESS"], "crt": "/MT", "debug": True,
                  "python": True, "vcruntime": False},
}


def default_stub_variant():
    """--stub-variant's default: the environment variable T5DR_STUB_VARIANT, else current."""
    v = os.environ.get("T5DR_STUB_VARIANT", "").strip().lower()
    return v if v in STUB_VARIANTS else "current"



def find_msvc_tools(pre):
    """(cl.exe, link.exe, rc.exe, toolset version) of the MSVC environment `pre` sets up (see
    msvc_prefix), or None when it has no cl.exe/link.exe/rc.exe. Paths come from VCToolsInstallDir and
    the Windows SDK's folder, not from a PATH search: Git for Windows has its own link.exe (coreutils)."""
    # `set VCTools` lists VCToolsInstallDir=... and VCToolsVersion=... (an `echo %VAR%` on the same line
    # as the vcvars call would be expanded before vcvars ran).
    r = subprocess.run(f"{pre}set VCTools&& where rc.exe", shell=True, capture_output=True, text=True,
                       errors="replace")
    env = dict(l.strip().split("=", 1) for l in r.stdout.splitlines() if l.startswith("VCTools") and "=" in l)
    rcs = [l.strip() for l in r.stdout.splitlines() if l.strip().lower().endswith("rc.exe")]
    tools_dir, ver = env.get("VCToolsInstallDir", ""), env.get("VCToolsVersion", "?")
    if r.returncode or not tools_dir or not rcs:
        return None
    rc = rcs[0]
    cl = os.path.join(tools_dir, "bin", "Hostx64", "x64", "cl.exe")
    link = os.path.join(tools_dir, "bin", "Hostx64", "x64", "link.exe")
    if not (os.path.exists(cl) and os.path.exists(link) and os.path.exists(rc)):
        return None
    return cl, link, rc, ver


def build_stub(stage, clang, version="0.0.0", compiler=None, variant=None):
    """T5DR Online.exe from launcher/stub/t5dr_stub.c: an ordinary Windows application (static
    C runtime, version information, icon, manifest).

    compiler 'msvc' (the default): cl.exe + link.exe + rc.exe of the MSVC environment, with
    /O2 /MT /GS /guard:cf and /DYNAMICBASE /NXCOMPAT /GUARD:CF /RELEASE -- what Microsoft's own tools
    emit, which some machine-learning scanners like better. Falls back to clang-cl (with a warning)
    when this PC has no cl.exe/link.exe. 'clang': clang-cl, as before 1.0.1.
    variant (msvc only; STUB_VARIANTS): 'current' is the default build; the others are the antivirus
    experiments described at STUB_VARIANTS.
    Without either compiler, a .cmd starter stands in (developer zips only; --release fails).
    Returns a text naming the compiler that was used ('MSVC 14.44.35207 ...'), or None for the .cmd."""
    compiler = compiler or default_stub_compiler()
    variant = variant or default_stub_variant()
    spec = STUB_VARIANTS[variant]
    src = os.path.join(ROOT, "launcher", "stub", "t5dr_stub.c")
    out = os.path.join(stage, "T5DR Online.exe")
    pre = msvc_prefix()
    used = None
    if pre is not None:
        tools = find_msvc_tools(pre) if compiler == "msvc" else None
        if compiler == "msvc" and not tools:
            if clang[0]:
                warn("T5DR Online.exe: no cl.exe/link.exe/rc.exe in the MSVC environment, building it with clang-cl "
                     "instead (--stub-compiler clang)")
            else:
                warn("T5DR Online.exe: no cl.exe/link.exe/rc.exe in the MSVC environment and no clang-cl")
        if variant != "current" and not tools:
            fail(f"--stub-variant {variant} needs the MSVC tools (cl.exe, link.exe)")
        if tools or clang[0]:
            tmp = tempfile.mkdtemp(prefix="t5dr_stub_")
            try:
                nums = (re.findall(r"\d+", str(version).split("-")[0]) + ["0", "0", "0"])[:3]
                rc = os.path.join(tmp, "stub.rc")
                stub_dir = os.path.join(ROOT, "launcher", "stub")
                # The manifest with LF line endings whatever git's autocrlf did to the checkout: the same
                # sources give the same T5DR Online.exe on every PC.
                manifest = os.path.join(tmp, "t5dr_stub.manifest")
                with open(os.path.join(stub_dir, "t5dr_stub.manifest"), "rb") as f:
                    xml = f.read().replace(b"\r\n", b"\n")
                with open(manifest, "wb") as f:
                    f.write(xml)
                with open(rc, "w", encoding="utf-8") as f:
                    f.write(STUB_RC.format(ico=os.path.join(stub_dir, spec["icon"]).replace("\\", "/"),
                                           manifest=manifest.replace("\\", "/"),
                                           v1=nums[0], v2=nums[1], v3=nums[2], version=version))
                res = os.path.join(tmp, "stub.res")
                obj = os.path.join(tmp, "stub.obj")
                built = os.path.join(tmp, "stub.exe")     # linked in the short temp path, copied to `out` after
                if tools:
                    cl, link, rcexe, ver = tools
                    defs = "".join(f" /D{d}" for d in spec["defines"])
                    libs = ""
                    if spec["python"]:
                        if sys.version_info[:2] != (3, 12):
                            fail("--stub-variant inprocess is written for python312.dll (the pinned CPython 3.12)")
                        pylib = os.path.join(sys.base_prefix, "libs", "python312.lib")
                        if not os.path.exists(pylib):
                            fail(f"--stub-variant inprocess needs {pylib} (the import library of this Python)")
                        libs = f' /DELAYLOAD:python312.dll delayimp.lib "{pylib}"'
                    dbg = " /DEBUG /PDBALTPATH:t5dr_stub.pdb /OPT:REF /OPT:ICF" if spec["debug"] else ""
                    cmd = (f'{pre}"{rcexe}" /nologo /fo "{res}" "{rc}" && '
                           f'"{cl}" /nologo /c /O2 {spec["crt"]} /GS /guard:cf /W3{defs} "{src}" /Fo"{obj}" && '
                           f'"{link}" /nologo /OUT:"{built}" /SUBSYSTEM:WINDOWS /MANIFEST:NO /INCREMENTAL:NO '
                           f'/DYNAMICBASE /NXCOMPAT /GUARD:CF /RELEASE{dbg} "{obj}" "{res}" kernel32.lib user32.lib{libs}')
                    used = f"MSVC {ver} (cl.exe + link.exe)" + ("" if variant == "current" else f", variant {variant}")
                else:
                    llvm_rc = os.path.join(os.path.dirname(clang[0]), "llvm-rc.exe")
                    rcexe = f'"{llvm_rc}"' if os.path.exists(llvm_rc) else "rc.exe"
                    cmd = (f'{pre}{rcexe} /nologo /fo "{res}" "{rc}" && '
                           f'"{clang[0]}" /nologo /O2 /MT "{src}" /Fo"{obj}" /Fe"{built}" '
                           f'/link /SUBSYSTEM:WINDOWS /MANIFEST:NO "{res}" kernel32.lib user32.lib')
                    used = f"clang-cl {clang[1]}"
                r = subprocess.run(cmd, shell=True, capture_output=True, text=True, errors="replace")
                if r.returncode == 0 and os.path.exists(built):
                    shutil.copy2(built, out)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)
            if r.returncode == 0 and os.path.exists(out):
                if spec["vcruntime"]:     # the dynamic C runtime: Microsoft's own DLL beside the exe
                    for cand in (os.path.join(stage, "python", "vcruntime140.dll"),
                                 os.path.join(sys.base_prefix, "vcruntime140.dll")):
                        if os.path.exists(cand):
                            copy(cand, os.path.join(os.path.dirname(out), "vcruntime140.dll"))
                            break
                    else:
                        fail("--stub-variant dynamic needs vcruntime140.dll (from the bundled or the running Python)")
                log(f"  T5DR Online.exe: {os.path.getsize(out):,} bytes, built with {used}")
                return used
            fail("launcher stub build failed:\n" + r.stdout + r.stderr)
    log("  no MSVC/clang-cl here: using a .cmd starter instead of T5DR Online.exe")
    with open(os.path.join(stage, "T5DR Online.cmd"), "w") as f:
        f.write('@echo off\r\ncd /d "%~dp0"\r\nif exist python\\pythonw.exe (start "" python\\pythonw.exe '
                'launcher\\t5dr_launcher.pyw) else (start "" pythonw launcher\\t5dr_launcher.pyw)\r\n')
    return None


def add_docs(stage, version):
    readme = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
    m = re.search(r"<!-- players:start -->(.*?)<!-- players:end -->", readme, re.S)
    body = m.group(1).strip() if m else readme
    with open(os.path.join(stage, "README.txt"), "w", encoding="utf-8", newline="\r\n") as f:
        f.write(f"Tekken 5: Dark Resurrection Online -- native Windows build, release {version}\n\n{body}\n")
    lic = os.path.join(stage, "LICENSES")
    os.makedirs(lic, exist_ok=True)
    copy(os.path.join(ROOT, "LICENSE"), os.path.join(lic, "T5DR-Online-MIT.txt"))
    copy(os.path.join(stage, "deps", "ps3recomp", "LICENSE"), os.path.join(lic, "ps3recomp-MIT.txt"))
    at3 = os.path.join(stage, "deps", "ps3recomp", "third_party", "at3_standalone", "COPYING.LGPLv2.1")
    if os.path.exists(at3):
        copy(at3, os.path.join(lic, "at3_standalone-LGPL-2.1.txt"))
    py_lic = os.path.join(stage, "python", "LICENSE.txt")
    if os.path.exists(py_lic):
        copy(py_lic, os.path.join(lic, "Python-PSF.txt"))


def sweep_pycache(stage):
    for dp, dns, _ in os.walk(stage):
        for d in [d for d in dns if d == "__pycache__"]:
            shutil.rmtree(os.path.join(dp, d), ignore_errors=True)
        dns[:] = [d for d in dns if d != "__pycache__"]


def write_zip(stage, zpath, name):
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for dp, dns, fns in os.walk(stage):
            dns.sort()
            for f in sorted(fns):
                p = os.path.join(dp, f)
                zf.write(p, os.path.join(name, os.path.relpath(p, stage)))


# --------------------------------------------------------------------------- the scan

def load_key_patterns(keys_file):
    pats = []
    if not keys_file or not os.path.exists(keys_file):
        return pats
    for line in open(keys_file):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, val = line.split("=", 1)
        try:
            b = bytes.fromhex(val.strip())
        except ValueError:
            continue
        if len(b) < 8:
            continue
        h = b.hex()
        forms = [b, h.encode(), h.upper().encode(),
                 ", ".join("0x%02x" % x for x in b[:8]).encode(), ", ".join("0x%02X" % x for x in b[:8]).encode(),
                 ",".join("0x%02x" % x for x in b[:8]).encode(), ",".join("0x%02X" % x for x in b[:8]).encode()]
        pats.append((name.strip(), forms))
    return pats


def classify(name, data):
    """Reasons this file looks game-derived (empty list: fine)."""
    why = []
    base = os.path.basename(name).lower()
    parts = [p.lower() for p in re.split(r"[\\/]", name)[:-1]]
    for pat in FORBIDDEN_NAMES:
        if fnmatch.fnmatch(base, pat):
            why.append(f"name matches {pat}")
    for d in FORBIDDEN_DIRS:
        if d in parts:
            why.append(f"inside a '{d}' folder")
    if data[:4] == b"\x7fELF" and len(data) > 0x14:
        mach = int.from_bytes(data[0x12:0x14], "big" if data[5] == 2 else "little")
        if mach in (0x15, 0x17):
            why.append("PS3 PPU/SPU ELF")
    if len(data) > BIG_BINARY and base.endswith((".exe", ".dll")) and "toolchain/llvm/" not in name.replace("\\", "/"):
        why.append(f"unexpectedly big binary ({len(data) / 1e6:.0f} MB) outside toolchain/llvm")
    if data[:4] == b"SCE\0":
        why.append("SELF/SCE container")
    if data[:4] == b"\x7fPKG":
        why.append("PS3 package")
    if data[:4] == b"\0PSF":
        why.append("PARAM.SFO")
    # lifted code under any name or cut into pieces: it names guest functions func_XXXXXXXX
    # everywhere (a 100 KB piece has ~150); the most any ps3recomp source has is 38.
    n = len(RE_LIFTED.findall(data))
    if n >= 100:
        why.append(f"looks like lifted game code ({n} func_XXXXXXXX names)")
    return why


def scan_files(items, key_pats, game_index):
    """items: iterable of (relative name, bytes). Returns list of (name, reason)."""
    bad = []
    count = size = 0
    for name, data in items:
        count += 1
        size += len(data)
        for r in classify(name, data):
            bad.append((name, r))
        for kname, forms in key_pats:
            if any(f in data for f in forms):
                bad.append((name, f"contains key {kname}"))
        if game_index and len(data) in game_index:
            h = hashlib.sha1(data).hexdigest()
            if h in game_index[len(data)]:
                bad.append((name, f"identical to game-derived file {game_index[len(data)][h]}"))
    return bad, count, size


def iter_dir(d):
    for dp, _, fns in os.walk(d):
        for f in fns:
            p = os.path.join(dp, f)
            with open(p, "rb") as fh:
                yield os.path.relpath(p, d).replace("\\", "/"), fh.read()


def iter_zip(z):
    with zipfile.ZipFile(z) as zf:
        for info in zf.infolist():
            if not info.is_dir():
                yield info.filename, zf.read(info)


def index_game(dirs):
    idx = {}
    for d in dirs or []:
        for dp, _, fns in os.walk(d):
            for f in fns:
                p = os.path.join(dp, f)
                try:
                    n = os.path.getsize(p)
                    if n < 64:
                        continue
                    h = hashlib.sha1()
                    with open(p, "rb") as fh:
                        for b in iter(lambda: fh.read(1 << 20), b""):
                            h.update(b)
                    idx.setdefault(n, {})[h.hexdigest()] = p
                except OSError:
                    pass
    return idx


def report(label, bad, count, size):
    if bad:
        log(f"\nSCAN FAILED ({label}): {len(bad)} problem(s)")
        if os.environ.get("GITHUB_ACTIONS") == "true":
            print(f"::error::game-data scan failed on {label}: {len(bad)} problem(s), first: {bad[0][0]}: {bad[0][1]}")
        for n, r in bad[:50]:
            log(f"  {n}: {r}")
        return False
    log(f"scan OK ({label}): {count} files, {mb(size)} -- no game files, no lifted code, no keys")
    return True


# --------------------------------------------------------------------------- code signing

def export_to_sign(stage, dest):
    """Copy the files we sign (tools/code_signing.py signable_files) to `dest`, keeping their relative
    paths: what the signing service gets. Nothing else leaves the folder."""
    files = code_signing.signable_files(stage)
    if not files:
        fail("--sign-stage prepare: no program to sign in the staged folder")
    if os.path.exists(dest):
        shutil.rmtree(dest)
    for rel in files:
        target = os.path.join(dest, *rel.split("/"))
        copy(os.path.join(stage, *rel.split("/")), target)
        log(f"  to sign: {rel} ({os.path.getsize(target):,} bytes, sha256 {sha256_file(target)[:16]}...)")
    return files


def install_signed(stage, signed_dir, accept_untrusted=False):
    """Put the signed copies from `signed_dir` over the built files. Each one must exist, carry a
    signature that Windows reports as Valid, and be the built file plus that signature -- a signing
    service may add a certificate to our program and change nothing else. Returns the list."""
    files = code_signing.signable_files(stage)
    if not files:
        fail("--sign-stage finish: no program to sign in the staged folder")
    done = []
    for rel in files:
        built = os.path.join(stage, *rel.split("/"))
        signed = os.path.join(signed_dir, *rel.split("/"))
        if not os.path.isfile(signed):
            fail(f"{rel}: the signing service returned no signed copy (expected {signed})")
        with open(built, "rb") as f:
            built_bytes = f.read()
        with open(signed, "rb") as f:
            signed_bytes = f.read()
        try:
            has_sig = code_signing.certificate_table(signed_bytes)[1] > 0
            same = code_signing.same_program(built_bytes, signed_bytes)
        except ValueError as e:
            fail(f"{rel}: {e}")
        if not has_sig:
            fail(f"{rel}: the returned file has no signature")
        if not same:
            fail(f"{rel}: the signed file is not the file built in this run (more than a signature differs)")
        status, subject = code_signing.authenticode_status(signed)
        if status != "Valid" and not (accept_untrusted and status in ("UnknownError", "NotTrusted")):
            fail(f"{rel}: Windows reports the signature as {status} (signer: {subject or 'none'})")
        shutil.copy2(signed, built)
        log(f"  signed: {rel} -- {status}, {subject}")
        done.append(rel)
    return done


def check_stage(stage, clang, release, key_pats, game_index):
    """The checks on the staged folder before it becomes a zip (or before it is sent to be signed)."""
    sweep_pycache(stage)
    llvm_bin = os.path.dirname(clang[0]) if clang[0] else None
    if llvm_bin and os.path.exists(os.path.join(llvm_bin, "llvm-readobj.exe")):
        log("checking the binaries for a clean Windows 10/11 (tools/check_binaries.py)")
        problems, _ = check_binaries.check_release(stage, llvm_bin, log=log)
        if problems:
            fail("binaries that would not run on every Windows 10/11 PC:\n  " + "\n  ".join(problems))
    else:
        log("  (no llvm-readobj next to clang-cl: import check skipped)")

    # Script files in a game download are what virus scanners flag first: 0.1.8/0.1.9-preview got
    # "Generic.BAT.Downloader" from 8 of 62-65 scanners. The zip carries none.
    scripts = [os.path.relpath(os.path.join(dp, f), stage) for dp, _, fns in os.walk(stage) for f in fns
               if f.lower().endswith((".bat", ".cmd", ".ps1", ".vbs", ".vbe", ".js", ".jse", ".wsf", ".hta"))]
    if scripts and release:
        fail("script files in the release (virus scanners flag them): " + ", ".join(sorted(scripts)[:20]))
    ok = report("folder", *scan_files(iter_dir(stage), key_pats, game_index))
    if not ok:
        fail("refusing to package: see the scan above")
    log(f"folder: {mb(dir_size(stage))}")


# --------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", default="0.0.0-dev",
                    help="release version, MAJOR.MINOR.PATCH[-suffix]; a leading v is dropped (default 0.0.0-dev)")
    ap.add_argument("--release", action="store_true",
                    help="the published layout: --bundle-python --prebuilt-host --zip (needs --llvm)")
    ap.add_argument("--out", default=os.path.join(ROOT, "dist"))
    ap.add_argument("--ps3recomp", default=build_game.PS3RECOMP_URL,
                    help="git URL or local clone to take ps3recomp from (default: the pinned upstream)")
    ap.add_argument("--bundle-python", action="store_true", help="ship a private copy of this Python")
    ap.add_argument("--llvm", help="LLVM folder (bin/clang-cl.exe, bin/lld-link.exe, lib/clang/N/include) to ship "
                                   "in toolchain/llvm and to compile the runtime and the stub with "
                                   "(tools/fetch_llvm.py gets the pinned one)")
    ap.add_argument("--prebuilt-host", action="store_true",
                    help="ship the runtime precompiled (runtime/t5dr.exe); players then need no Visual Studio "
                         "(use together with --llvm)")
    ap.add_argument("--jobs", type=int, help="parallel compile jobs for the runtime host (default: all cores)")
    ap.add_argument("--keys", default=os.path.join(ROOT, "keys", "ps3.keys"),
                    help="key file whose keys must not appear anywhere (default keys/ps3.keys)")
    ap.add_argument("--game-dir", action="append", help="folder of game-derived files to cross-check (repeatable)")
    ap.add_argument("--zip", action="store_true", help="also write the zip and SHA256SUMS")
    ap.add_argument("--scan-only", metavar="PATH", help="only scan this folder or zip")
    ap.add_argument("--stub-compiler", choices=STUB_COMPILERS, default=default_stub_compiler(),
                    help="what builds T5DR Online.exe: msvc = cl.exe + link.exe (default; falls back to clang-cl "
                         "with a warning when this PC has no MSVC tools), clang = clang-cl. Default: the "
                         "environment variable T5DR_STUB_COMPILER, else msvc")
    ap.add_argument("--stub-variant", choices=sorted(STUB_VARIANTS), default=default_stub_variant(),
                    help="antivirus experiments with T5DR Online.exe (see STUB_VARIANTS in this file and "
                         "docs/RELEASING.md): current (default), plain, dynamic, inprocess. Default: the "
                         "environment variable T5DR_STUB_VARIANT, else current")
    ap.add_argument("--sign-stage", choices=("prepare", "finish"),
                    help="code signing in two halves: 'prepare' builds and stages, runs the checks and copies the "
                         "files to sign to <out>/to-sign/ (no zip); 'finish' (needs --signed-dir) installs the "
                         "signed copies and writes the zip. Without it: one run, nothing signed")
    ap.add_argument("--signed-dir", metavar="DIR",
                    help="with --sign-stage finish: the folder the signing service filled, same relative paths "
                         "as <out>/to-sign/")
    ap.add_argument("--accept-untrusted-signature", action="store_true",
                    help="testing only: accept a signature Windows does not trust (a self-signed test certificate)")
    a = ap.parse_args()

    key_pats = load_key_patterns(a.keys)
    if not key_pats:
        log(f"note: no key file at {a.keys}; the key-bytes scan is skipped (pass --keys on a PC that has one)")
    game_index = index_game(a.game_dir)

    if a.scan_only:
        it = iter_zip(a.scan_only) if a.scan_only.lower().endswith(".zip") else iter_dir(a.scan_only)
        sys.exit(0 if report(a.scan_only, *scan_files(it, key_pats, game_index)) else 1)

    version = parse_version(a.version)
    if a.release:
        if not a.llvm:
            fail("--release needs --llvm (python tools/fetch_llvm.py --dest DIR gets the pinned LLVM)")
        a.bundle_python = a.prebuilt_host = a.zip = True
    if a.sign_stage == "finish" and not a.signed_dir:
        fail("--sign-stage finish needs --signed-dir (the folder with the signed copies)")
    if a.signed_dir and a.sign_stage != "finish":
        fail("--signed-dir belongs to --sign-stage finish")
    clang = find_clang(a.llvm)

    out = os.path.abspath(a.out)
    name = f"T5DR-Online-{version}"
    stage = os.path.join(out, name)
    release_json = os.path.join(stage, "release.json")

    if a.sign_stage == "finish":
        if not os.path.isfile(release_json):
            fail(f"--sign-stage finish: no staged folder at {stage} (run --sign-stage prepare first)")
        with open(release_json) as f:
            info = json.load(f)
        info["signed"] = install_signed(stage, os.path.abspath(a.signed_dir), a.accept_untrusted_signature)
        info["code_id"] = staged_code_id(stage)      # hashes runtime/t5dr.exe, which now carries a signature
        with open(release_json, "w") as f:
            json.dump(info, f, indent=1)
    else:
        if os.path.exists(stage):
            shutil.rmtree(stage)
        os.makedirs(stage)
        log(f"staging {stage}")
        add_our_files(stage)
        patches = add_ps3recomp(stage, a.ps3recomp)
        py_ver = add_python(stage) if a.bundle_python else None
        if a.llvm:
            add_llvm(stage, a.llvm)
        if a.prebuilt_host:
            add_prebuilt_host(stage, clang, a.jobs, version)
        stub = build_stub(stage, clang, version, a.stub_compiler, a.stub_variant)
        if not stub and a.release:
            fail("--release needs the native starter T5DR Online.exe (MSVC or clang-cl)")
        add_docs(stage, version)
        info = {"name": "T5DR Online", "version": version, "code_id": staged_code_id(stage),
                "ps3recomp": build_game.PS3RECOMP_COMMIT, "patches": patches, "game": build_game.GAME_NAME,
                "commit": source_commit(), "built": build_time(),
                "llvm": clang[1] if a.llvm else None, "python": py_ver, "prebuilt_host": bool(a.prebuilt_host),
                "stub_compiler": stub, "stub_variant": a.stub_variant, "signed": []}
        with open(release_json, "w") as f:
            json.dump(info, f, indent=1)

    check_stage(stage, clang, a.release, key_pats, game_index)
    if a.sign_stage == "prepare":
        export_to_sign(stage, os.path.join(out, "to-sign"))
        log("prepare done: sign the files in to-sign/, then run again with --sign-stage finish --signed-dir DIR")
        return
    if a.zip:
        zpath = os.path.join(out, name + ".zip")
        write_zip(stage, zpath, name)
        if not report("zip", *scan_files(iter_zip(zpath), key_pats, game_index)):
            os.remove(zpath)
            fail("zip removed: see the scan above")
        digest = sha256_file(zpath)
        with open(os.path.join(out, "SHA256SUMS"), "w", newline="\n") as f:
            f.write(f"{digest}  {name}.zip\n")
        log(f"zip: {zpath} ({mb(os.path.getsize(zpath))})")
        log(f"sha256: {digest}")


if __name__ == "__main__":
    main()
