#!/usr/bin/env python3
"""Assemble the player release (folder + zip) and prove it holds nothing of the game.

    python tools/package_release.py --release --version 0.1.0-preview --llvm DIR
                                    [--ps3recomp SRC] [--out DIR] [--jobs N]
                                    [--keys FILE] [--game-dir DIR ...]
    python tools/package_release.py [--version V] [--bundle-python] [--llvm DIR] [--prebuilt-host] [--zip] ...
    python tools/package_release.py --scan-only PATH      (a folder or a zip)

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
  T5DR Online.exe          small native starter (launcher/stub), built here with clang-cl
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
import prereqs     # noqa: E402

OUR_FILES = [
    "CMakeLists.txt",
    "tools/build_game.py", "tools/run_game.py", "tools/make_keys.py", "tools/unself.py", "tools/prereqs.py",
    "tools/build_game_dll.py", "tools/lift_spu_jobs.py", "tools/gamedll/t5dr_game_dll.c", "tools/gamedll/t5dr_host.def",
    "tools/gamedll/ucrt_min.def",
    "launcher/t5dr_launcher.pyw", "launcher/core.py", "launcher/online.py", "launcher/stub/t5dr_stub.c",
    "docs/RELEASE.md",
    # online: "Host for friends" entry point (works with the bundled, isolated Python) and the server list
    "lobby/run.py", "lobby/servers.json",
]
# Shipped when present (player docs; the players' README section links them).
OUR_OPTIONAL_FILES = ["CHANGELOG.md", "docs/TROUBLESHOOTING.md", "docs/README.de.md", "docs/ONLINE.md",
                      "docs/RANKED.md", "docs/controls.ini", "docs/HOSTING.md"]
# lobby/t5lobby/*.py is the client side (Online tab, match driver). lobby/t5lobby/server/ ships too:
# the Online tab's "Host for friends" and lobby/deploy/windows/ run a lobby server from the zip
# (docs/HOSTING.md). The Linux/Docker packaging stays in the repository.
OUR_GLOBS = ["patches/ps3recomp/*.patch", "tools/gamedll/include/*.h", "lobby/t5lobby/*.py",
             "lobby/t5lobby/data/*.json", "lobby/t5lobby/server/*.py", "lobby/deploy/windows/*"]

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
    for dp, dns, fns in os.walk(os.path.join(base, "Lib")):
        rel = os.path.relpath(dp, os.path.join(base, "Lib")).replace("\\", "/")
        dns[:] = sorted(d for d in dns if (d if rel == "." else f"{rel}/{d}") not in skip_lib and d != "__pycache__"
                        and not d.startswith("test"))
        for f in fns:
            if not f.endswith((".pyc",)):
                copy(os.path.join(dp, f), os.path.join(dst, "Lib", "" if rel == "." else rel, f))
    for dp, dns, fns in os.walk(os.path.join(base, "DLLs")):
        for f in fns:
            if not f.startswith(("_test", "_ctypes_test", "_testcapi")):
                copy(os.path.join(dp, f), os.path.join(dst, "DLLs", os.path.relpath(os.path.join(dp, f),
                                                                                     os.path.join(base, "DLLs"))))
    for dp, dns, fns in os.walk(os.path.join(base, "tcl")):
        dns[:] = [d for d in dns if d not in ("demos", "tzdata", "msgs", "encoding") or "tk" in dp.lower()]
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


def add_prebuilt_host(stage, clang, jobs):
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
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def build_stub(stage, clang):
    """T5DR Online.exe from launcher/stub/t5dr_stub.c (kernel32/user32 only). Without
    clang-cl or MSVC, a .cmd starter stands in (developer zips only; --release fails)."""
    src = os.path.join(ROOT, "launcher", "stub", "t5dr_stub.c")
    out = os.path.join(stage, "T5DR Online.exe")
    pre = msvc_prefix()
    if clang[0] and pre is not None:
        tmp = tempfile.mkdtemp(prefix="t5dr_stub_")
        cmd = (f'{pre}"{clang[0]}" /nologo /O2 /GS- "{src}" /Fo"{tmp}\\stub.obj" /Fe"{out}" '
               f'/link /SUBSYSTEM:WINDOWS /ENTRY:start /NODEFAULTLIB kernel32.lib user32.lib')
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        shutil.rmtree(tmp, ignore_errors=True)
        if r.returncode == 0 and os.path.exists(out):
            log(f"  T5DR Online.exe: {os.path.getsize(out):,} bytes")
            return True
        fail("launcher stub build failed:\n" + r.stdout + r.stderr)
    log("  no clang-cl/MSVC here: using a .cmd starter instead of T5DR Online.exe")
    with open(os.path.join(stage, "T5DR Online.cmd"), "w") as f:
        f.write('@echo off\r\ncd /d "%~dp0"\r\nif exist python\\pythonw.exe (start "" python\\pythonw.exe '
                'launcher\\t5dr_launcher.pyw) else (start "" pythonw launcher\\t5dr_launcher.pyw)\r\n')
    return False


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
    clang = find_clang(a.llvm)

    out = os.path.abspath(a.out)
    name = f"T5DR-Online-{version}"
    stage = os.path.join(out, name)
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
        add_prebuilt_host(stage, clang, a.jobs)
    if not build_stub(stage, clang) and a.release:
        fail("--release needs the native starter T5DR Online.exe (clang-cl + MSVC)")
    add_docs(stage, version)
    info = {"name": "T5DR Online", "version": version, "code_id": build_game.code_id(),
            "ps3recomp": build_game.PS3RECOMP_COMMIT, "patches": patches, "game": build_game.GAME_NAME,
            "commit": source_commit(), "built": build_time(),
            "llvm": clang[1] if a.llvm else None, "python": py_ver, "prebuilt_host": bool(a.prebuilt_host)}
    with open(os.path.join(stage, "release.json"), "w") as f:
        json.dump(info, f, indent=1)
    sweep_pycache(stage)

    ok = report("folder", *scan_files(iter_dir(stage), key_pats, game_index))
    if not ok:
        fail("refusing to package: see the scan above")
    log(f"folder: {mb(dir_size(stage))}")
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
