#!/usr/bin/env python3
"""Assemble the player release (folder + zip) and prove it holds nothing of the game.

    python tools/package_release.py [--version 0.1.0] [--ps3recomp SRC] [--bundle-python]
                                    [--llvm DIR] [--keys FILE] [--game-dir DIR ...] [--zip]

Output: dist/T5DR-Online-<version>/ and, with --zip, dist/T5DR-Online-<version>.zip.

What goes in:
  T5DR Online.exe          small native starter (launcher/stub), built here with clang-cl
  launcher/                the launcher (Python/tkinter)
  tools/                   build_game.py, run_game.py, make_keys.py, unself.py, prereqs.py
  patches/, CMakeLists.txt the port's own sources
  deps/ps3recomp/          ps3recomp (MIT) at the pinned commit with our patches applied,
                           only what the build uses -- no fw_spu/ (Sony firmware), no tests,
                           and pkg_extract.py with its package keys taken out (it reads them
                           from keys/ps3.keys, which make_keys.py writes on the player's PC)
  python/                  (--bundle-python) a private copy of this CPython with tkinter and
                           pycryptodome, isolated by a ._pth file
  toolchain/llvm/          (--llvm) clang-cl + lld-link + clang's headers, for the planned
                           header-free compile (docs/RELEASE.md); not used by the build yet
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
import hashlib
import io
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
    "tools/build_game_dll.py", "tools/gamedll/t5dr_game_dll.c", "tools/gamedll/t5dr_host.def",
    "tools/gamedll/ucrt_min.def",
    "launcher/t5dr_launcher.pyw", "launcher/core.py", "launcher/online.py", "launcher/stub/t5dr_stub.c",
    "docs/RELEASE.md",
]
OUR_GLOBS = ["patches/ps3recomp/*.patch", "tools/gamedll/include/*.h"]

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


# --------------------------------------------------------------------------- helpers

def log(msg):
    print(msg, flush=True)


def copy(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(src, dst)


def git(*args, cwd=None, check=True):
    return subprocess.run(["git", *args], cwd=cwd, check=check, capture_output=True, text=True)


def dir_size(d):
    return sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(d) for f in fs)


def mb(n):
    return f"{n / 1e6:,.1f} MB"


# --------------------------------------------------------------------------- parts

def add_our_files(stage):
    for rel in OUR_FILES:
        src = os.path.join(ROOT, rel)
        if not os.path.exists(src):
            sys.exit(f"missing {rel}")
        copy(src, os.path.join(stage, rel))
    import glob
    for g in OUR_GLOBS:
        for src in glob.glob(os.path.join(ROOT, g)):
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
        sys.exit("pkg_extract.py changed upstream: could not take its keys out -- update strip_pkg_keys()")
    i = s.index("PS3_GPKG_KEY =")
    s = s[:i] + helper + s[i:]
    open(path, "w", encoding="utf-8", newline="\n").write(s)


def add_ps3recomp(stage, src):
    tmp = tempfile.mkdtemp(prefix="t5dr_ps3recomp_")
    try:
        log(f"  cloning ps3recomp from {src}")
        git("-c", "core.longpaths=true", "clone", "-q", "--no-checkout", src, tmp)
        git("checkout", "-q", build_game.PS3RECOMP_COMMIT, cwd=tmp)
        patches = sorted(os.path.join(ROOT, "patches", "ps3recomp", n)
                         for n in os.listdir(os.path.join(ROOT, "patches", "ps3recomp")) if n.endswith(".patch"))
        for p in patches:
            r = git("apply", "--whitespace=nowarn", p, cwd=tmp, check=False)
            if r.returncode:
                sys.exit(f"patch {os.path.basename(p)} does not apply on {build_game.PS3RECOMP_COMMIT}:\n{r.stderr}")
            log(f"  applied {os.path.basename(p)}")
        dst = os.path.join(stage, "deps", "ps3recomp")
        import glob
        picked = []
        for d in PS3_KEEP_DIRS:
            for dp, dns, fns in os.walk(os.path.join(tmp, d)):
                dns[:] = [x for x in dns if x != "__pycache__"]
                picked += [os.path.join(dp, f) for f in fns]
        picked += [os.path.join(tmp, f) for f in PS3_KEEP_FILES if os.path.exists(os.path.join(tmp, f))]
        for g in PS3_TOOLS_GLOBS:
            picked += glob.glob(os.path.join(tmp, g))
        n = 0
        for f in picked:
            rel = os.path.relpath(f, tmp).replace("\\", "/")
            if any(fnmatch.fnmatch("/" + rel, pat) or fnmatch.fnmatch(rel, pat) for pat in PS3_SKIP):
                continue
            copy(f, os.path.join(dst, rel))
            n += 1
        strip_pkg_keys(os.path.join(dst, "tools", "pkg_extract.py"))
        with open(os.path.join(dst, ".t5dr-vendored.json"), "w") as f:
            json.dump({"commit": build_game.PS3RECOMP_COMMIT, "patches": build_game.patch_digest(),
                       "source": "https://github.com/NoahBPeterson/ps3recomp (branch infamous/upstream-sync)"},
                      f, indent=1)
        log(f"  ps3recomp: {n} files, {mb(dir_size(dst))}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def add_python(stage):
    """A private copy of the running CPython: interpreter, stdlib without tests/IDLE,
    tkinter with Tcl/Tk, pycryptodome. python312._pth keeps it away from any other Python."""
    base = sys.base_prefix
    dst = os.path.join(stage, "python")
    ver = f"{sys.version_info.major}{sys.version_info.minor}"
    for f in os.listdir(base):
        p = os.path.join(base, f)
        if os.path.isfile(p) and (f.lower().endswith((".exe", ".dll")) or f.upper().startswith("LICENSE")):
            if f.lower() in ("python.exe", "pythonw.exe") or f.lower().endswith(".dll") or f.upper().startswith("LICENSE"):
                copy(p, os.path.join(dst, f))
    skip_lib = {"test", "idlelib", "ensurepip", "lib2to3", "turtledemo", "pydoc_data", "site-packages", "venv",
                "__pycache__", "tkinter/test", "unittest/test", "distutils/tests"}
    for dp, dns, fns in os.walk(os.path.join(base, "Lib")):
        rel = os.path.relpath(dp, os.path.join(base, "Lib")).replace("\\", "/")
        dns[:] = [d for d in dns if (d if rel == "." else f"{rel}/{d}") not in skip_lib and d != "__pycache__"
                  and not d.startswith("test")]
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
    enc_src = None
    for d in os.listdir(os.path.join(base, "tcl")):
        if d.startswith("tcl8") and os.path.isdir(os.path.join(base, "tcl", d, "encoding")):
            enc_src = os.path.join(base, "tcl", d, "encoding")
            for f in os.listdir(enc_src):
                if f.startswith(("ascii", "cp125", "cp437", "cp850", "iso8859-1", "utf", "unicode", "cp932",
                                 "cp936", "cp949", "cp950", "identity")):
                    copy(os.path.join(enc_src, f), os.path.join(dst, "tcl", d, "encoding", f))
    # pycryptodome only (no pip, no other packages)
    import Crypto
    cdir = os.path.dirname(Crypto.__file__)
    for dp, dns, fns in os.walk(cdir):
        dns[:] = [d for d in dns if d not in ("__pycache__", "SelfTest")]
        for f in fns:
            if not f.endswith(".pyc"):
                copy(os.path.join(dp, f), os.path.join(dst, "Lib", "site-packages", "Crypto",
                                                       os.path.relpath(os.path.join(dp, f), cdir)))
    with open(os.path.join(dst, f"python{ver}._pth"), "w") as f:
        f.write("Lib\nDLLs\nLib\\site-packages\n.\nimport site\n")
    log(f"  python: {mb(dir_size(dst))}")


def add_llvm(stage, llvm):
    dst = os.path.join(stage, "toolchain", "llvm")
    for exe in ("clang-cl.exe", "lld-link.exe"):
        copy(os.path.join(llvm, "bin", exe), os.path.join(dst, "bin", exe))
    inc_root = os.path.join(llvm, "lib", "clang")
    ver = sorted(os.listdir(inc_root))[-1]
    shutil.copytree(os.path.join(inc_root, ver, "include"), os.path.join(dst, "lib", "clang", ver, "include"))
    for lic in ("LICENSE.TXT",):
        for cand in (os.path.join(llvm, lic), os.path.join(llvm, "share", "doc", "LLVM", lic)):
            if os.path.exists(cand):
                copy(cand, os.path.join(stage, "LICENSES", "LLVM-LICENSE.TXT"))
    log(f"  llvm: {mb(dir_size(dst))}")


def add_prebuilt_host(stage):
    """runtime/t5dr.exe + t5dr.lib: ps3recomp's runtime without any game code (CMake
    -DT5DR_GAME_DLL=ON), built from exactly the sources staged above, static C runtime
    (no Visual C++ redistributable needed). The player's PC then compiles only the
    lifted code, into t5dr_game.dll (tools/build_game_dll.py)."""
    bat, clang = prereqs.vcvars(), prereqs.clang_cl()
    cm, nj = prereqs.cmake_ninja()
    if not (bat and clang and cm and nj):
        sys.exit("--prebuilt-host needs Visual Studio Build Tools, clang-cl, CMake and Ninja on this PC")
    tmp = tempfile.mkdtemp(prefix="t5dr_host_")
    try:
        args = [f'"{cm}"', "-S", f'"{stage}"', "-B", f'"{tmp}"', "-G", "Ninja", f'-DCMAKE_MAKE_PROGRAM="{nj}"',
                "-DCMAKE_BUILD_TYPE=Release", "-DT5DR_GAME_DLL=ON", "-DCMAKE_MSVC_RUNTIME_LIBRARY=MultiThreaded",
                f'-DPS3RECOMP_DIR="{os.path.join(stage, "deps", "ps3recomp")}"', f'-DSPU_DIR="{tmp}"',
                f'-DPython3_EXECUTABLE="{sys.executable}"',
                f'-DCMAKE_C_COMPILER="{clang[0]}"', f'-DCMAKE_CXX_COMPILER="{clang[0]}"']
        cmd = f'call "{bat}" >nul && {" ".join(args)} && "{cm}" --build "{tmp}"'
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")   # no __pycache__ in the staged tools
        log(f"  building the runtime host (clang-cl {clang[1][0]}.{clang[1][1]}) ...")
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, env=env)
        if r.returncode:
            sys.exit("host build failed:\n" + (r.stdout + r.stderr)[-4000:])
        dst = os.path.join(stage, "runtime")
        for n in ("t5dr.exe", "t5dr.lib"):
            copy(os.path.join(tmp, n), os.path.join(dst, n))
        log(f"  runtime/t5dr.exe: {os.path.getsize(os.path.join(dst, 't5dr.exe')):,} bytes")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def build_stub(stage):
    """T5DR Online.exe from launcher/stub/t5dr_stub.c (kernel32/user32 only)."""
    src = os.path.join(ROOT, "launcher", "stub", "t5dr_stub.c")
    out = os.path.join(stage, "T5DR Online.exe")
    clang, bat = prereqs.clang_cl(), prereqs.vcvars()
    if clang and bat:
        tmp = tempfile.mkdtemp(prefix="t5dr_stub_")
        cmd = (f'call "{bat}" >nul && "{clang[0]}" /nologo /O2 /GS- "{src}" /Fo"{tmp}\\stub.obj" /Fe"{out}" '
               f'/link /SUBSYSTEM:WINDOWS /ENTRY:start /NODEFAULTLIB kernel32.lib user32.lib')
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        shutil.rmtree(tmp, ignore_errors=True)
        if r.returncode == 0 and os.path.exists(out):
            log(f"  T5DR Online.exe: {os.path.getsize(out):,} bytes")
            return
        log("  stub build failed, using a .cmd starter instead:\n" + r.stdout + r.stderr)
    with open(os.path.join(stage, "T5DR Online.cmd"), "w") as f:
        f.write('@echo off\r\ncd /d "%~dp0"\r\nif exist python\\pythonw.exe (start "" python\\pythonw.exe '
                'launcher\\t5dr_launcher.pyw) else (start "" pythonw launcher\\t5dr_launcher.pyw)\r\n')


def add_docs(stage, version):
    readme = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
    m = re.search(r"<!-- players:start -->(.*?)<!-- players:end -->", readme, re.S)
    body = m.group(1).strip() if m else readme
    with open(os.path.join(stage, "README.txt"), "w", encoding="utf-8", newline="\r\n") as f:
        f.write(f"Tekken 5: Dark Resurrection Online -- native Windows build, release {version}\n\n{body}\n")
    lic = os.path.join(stage, "LICENSES")
    os.makedirs(lic, exist_ok=True)
    copy(os.path.join(stage, "deps", "ps3recomp", "LICENSE"), os.path.join(lic, "ps3recomp-MIT.txt"))
    at3 = os.path.join(stage, "deps", "ps3recomp", "third_party", "at3_standalone", "COPYING.LGPLv2.1")
    if os.path.exists(at3):
        copy(at3, os.path.join(lic, "at3_standalone-LGPL-2.1.txt"))
    py_lic = os.path.join(stage, "python", "LICENSE.txt")
    if os.path.exists(py_lic):
        copy(py_lic, os.path.join(lic, "Python-PSF.txt"))


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
        for n, r in bad[:50]:
            log(f"  {n}: {r}")
        return False
    log(f"scan OK ({label}): {count} files, {mb(size)} -- no game files, no lifted code, no keys")
    return True


# --------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", default="0.1.0")
    ap.add_argument("--out", default=os.path.join(ROOT, "dist"))
    ap.add_argument("--ps3recomp", default=build_game.PS3RECOMP_URL, help="git URL or local clone to take ps3recomp from")
    ap.add_argument("--bundle-python", action="store_true", help="ship a private copy of this Python")
    ap.add_argument("--llvm", help="LLVM install to take clang-cl/lld-link from (toolchain/llvm)")
    ap.add_argument("--prebuilt-host", action="store_true",
                    help="ship the runtime precompiled (runtime/t5dr.exe); players then need no Visual Studio "
                         "(use together with --llvm)")
    ap.add_argument("--keys", default=os.path.join(ROOT, "keys", "ps3.keys"),
                    help="key file whose keys must not appear anywhere (default keys/ps3.keys)")
    ap.add_argument("--game-dir", action="append", help="folder of game-derived files to cross-check (repeatable)")
    ap.add_argument("--zip", action="store_true")
    ap.add_argument("--scan-only", metavar="PATH", help="only scan this folder or zip")
    a = ap.parse_args()

    key_pats = load_key_patterns(a.keys)
    if not key_pats:
        log(f"warning: no key file at {a.keys}; the key scan is skipped (pass --keys)")
    game_index = index_game(a.game_dir)

    if a.scan_only:
        it = iter_zip(a.scan_only) if a.scan_only.lower().endswith(".zip") else iter_dir(a.scan_only)
        sys.exit(0 if report(a.scan_only, *scan_files(it, key_pats, game_index)) else 1)

    name = f"T5DR-Online-{a.version}"
    stage = os.path.join(a.out, name)
    if os.path.exists(stage):
        shutil.rmtree(stage)
    os.makedirs(stage)
    log(f"staging {stage}")
    add_our_files(stage)
    add_ps3recomp(stage, a.ps3recomp)
    if a.bundle_python:
        add_python(stage)
    if a.llvm:
        add_llvm(stage, a.llvm)
    if a.prebuilt_host:
        add_prebuilt_host(stage)
    build_stub(stage)
    add_docs(stage, a.version)
    info = {"name": "T5DR Online", "version": a.version, "code_id": build_game.code_id(),
            "ps3recomp": build_game.PS3RECOMP_COMMIT, "game": build_game.GAME_NAME,
            "built": datetime.datetime.now().isoformat(timespec="seconds")}
    with open(os.path.join(stage, "release.json"), "w") as f:
        json.dump(info, f, indent=1)

    ok = report("folder", *scan_files(iter_dir(stage), key_pats, game_index))
    if not ok:
        sys.exit("refusing to package: see the scan above")
    log(f"folder: {mb(dir_size(stage))}")
    if a.zip:
        zpath = os.path.join(a.out, name + ".zip")
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            for dp, _, fns in os.walk(stage):
                for f in sorted(fns):
                    p = os.path.join(dp, f)
                    zf.write(p, os.path.join(name, os.path.relpath(p, stage)))
        if not report("zip", *scan_files(iter_zip(zpath), key_pats, game_index)):
            os.remove(zpath)
            sys.exit("zip removed: see the scan above")
        log(f"zip: {zpath} ({mb(os.path.getsize(zpath))})")


if __name__ == "__main__":
    main()
