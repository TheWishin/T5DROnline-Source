#!/usr/bin/env python3
"""Build Tekken 5: Dark Resurrection Online from the player's own PSN package.

    python tools/build_game.py --pkg <game.pkg> --rap <license.rap> [--steps ...]

Steps (each skipped when its output is already there, unless --force):
  deps     clone ps3recomp at the pinned commit into deps/ps3recomp
  keys     write keys/ps3.keys (tools/make_keys.py)
  unpack   extract the package into game/pkg/
  decrypt  decrypt EBOOT.BIN with the .rap and check it is the supported version
  vfs      lay out game/vfs/ the way the runtime's file system expects
  lift     find functions and translate the PPU code to C++ in build/recomp/
  spu      extract and translate the SPU programs (sound core) to C in build/spu/
  compile  configure and build build/cmake/t5dr.exe

Everything it writes is game-derived and stays in game/, build/, deps/, keys/
-- all git-ignored.
"""
import argparse
import hashlib
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable

PS3RECOMP_URL = "https://github.com/NoahBPeterson/ps3recomp.git"
PS3RECOMP_BRANCH = "infamous/upstream-sync"
PS3RECOMP_COMMIT = "f17bcd3"

# NPUB30009 v01.00 -- the only version the port supports.
TITLE_ID = "NPUB30009"
ELF_SHA1 = "be80165b84e30b6334baa6d6331b9db4ffd5a6a4"
CODE_END = "0x3C7100"   # end of .lib.stub; past it is .rodata

DEPS = os.path.join(ROOT, "deps", "ps3recomp")
TOOLS = os.path.join(DEPS, "tools")
GAME = os.path.join(ROOT, "game")
PKG_DIR = os.path.join(GAME, "pkg")
ELF = os.path.join(GAME, "EBOOT.elf")
VFS = os.path.join(GAME, "vfs")
USRDIR = os.path.join(VFS, "PS3_GAME", "USRDIR")
HDD0 = os.path.join(VFS, "dev_hdd0")
HDD0_USRDIR = os.path.join(HDD0, "game", TITLE_ID, "USRDIR")
OUT = os.path.join(ROOT, "build", "out")
RECOMP = os.path.join(ROOT, "build", "recomp")
CMAKE_BUILD = os.path.join(ROOT, "build", "cmake")
SPU = os.path.join(ROOT, "build", "spu")

STEPS = ["deps", "keys", "unpack", "decrypt", "vfs", "lift", "spu", "compile"]


def run(cmd, **kw):
    print("  >", " ".join(str(c) for c in cmd))
    subprocess.run(cmd, check=True, **kw)


def sha1(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def link_or_copy(src, dst):
    if os.path.exists(dst):
        os.remove(dst)
    try:
        os.link(src, dst)       # same drive: no 600 MB copy
    except OSError:
        shutil.copy2(src, dst)


def step_deps(a):
    if os.path.isdir(os.path.join(DEPS, ".git")) and not a.force:
        return
    if os.path.isdir(DEPS):
        shutil.rmtree(DEPS)
    run(["git", "-c", "core.longpaths=true", "clone", "-b", PS3RECOMP_BRANCH, PS3RECOMP_URL, DEPS])
    run(["git", "-C", DEPS, "checkout", "-q", PS3RECOMP_COMMIT])
    # Our fixes on top of the pinned commit (Windows build gaps and the like).
    patches = os.path.join(ROOT, "patches", "ps3recomp")
    for name in sorted(os.listdir(patches)):
        if name.endswith(".patch"):
            run(["git", "-C", DEPS, "apply", "--whitespace=nowarn", os.path.join(patches, name)])
    run([PY, "-m", "pip", "install", "-q", "-r", os.path.join(DEPS, "requirements.txt")])


def step_keys(a):
    if os.path.exists(os.path.join(ROOT, "keys", "ps3.keys")) and not a.force:
        return
    run([PY, os.path.join(ROOT, "tools", "make_keys.py"), "--out", os.path.join(ROOT, "keys", "ps3.keys")])


def step_unpack(a):
    if os.path.exists(os.path.join(PKG_DIR, "USRDIR", "EBOOT.BIN")) and not a.force:
        return
    if not a.pkg:
        sys.exit("unpack needs --pkg")
    run([PY, os.path.join(TOOLS, "pkg_extract.py"), a.pkg, PKG_DIR])


def step_decrypt(a):
    if os.path.exists(ELF) and sha1(ELF) == ELF_SHA1 and not a.force:
        return
    if not a.rap:
        sys.exit("decrypt needs --rap")
    run([PY, os.path.join(ROOT, "tools", "unself.py"), os.path.join(PKG_DIR, "USRDIR", "EBOOT.BIN"),
         a.rap, ELF, "--keys", os.path.join(ROOT, "keys", "ps3.keys")])
    got = sha1(ELF)
    if got != ELF_SHA1:
        sys.exit(f"decrypted program has SHA-1 {got}; this port supports only {TITLE_ID} v01.00 ({ELF_SHA1})")


def step_vfs(a):
    # The runtime boots <vfs>/PS3_GAME/USRDIR/EBOOT.elf and reads PARAM.SFO
    # beside it. The game itself is a PSN title: it looks for its data under
    # /dev_hdd0/game/NPUB30009/USRDIR/, which run_game.py maps to
    # <vfs>/dev_hdd0 through PS3_HDD0_ROOT.
    os.makedirs(USRDIR, exist_ok=True)
    os.makedirs(HDD0_USRDIR, exist_ok=True)
    link_or_copy(ELF, os.path.join(USRDIR, "EBOOT.elf"))
    link_or_copy(os.path.join(PKG_DIR, "PARAM.SFO"), os.path.join(VFS, "PS3_GAME", "PARAM.SFO"))
    link_or_copy(os.path.join(PKG_DIR, "PARAM.SFO"), os.path.join(HDD0_USRDIR, "..", "PARAM.SFO"))
    for name in sorted(os.listdir(os.path.join(PKG_DIR, "USRDIR"))):
        if name.upper() != "EBOOT.BIN":
            link_or_copy(os.path.join(PKG_DIR, "USRDIR", name), os.path.join(HDD0_USRDIR, name))
            stale = os.path.join(USRDIR, name)
            if os.path.exists(stale):
                os.remove(stale)


def step_lift(a):
    if os.path.exists(os.path.join(RECOMP, "ppu_recomp.h")) and not a.force:
        return
    os.makedirs(OUT, exist_ok=True)
    run([PY, os.path.join(TOOLS, "ppu_loader.py"), ELF, "-o", OUT])
    run([PY, os.path.join(TOOLS, "find_functions.py"), ELF,
         "--seed-json", os.path.join(OUT, "EBOOT.functions.json"),
         "-o", os.path.join(OUT, "functions.json")])
    if os.path.isdir(RECOMP):
        shutil.rmtree(RECOMP)
    os.makedirs(RECOMP)
    run([PY, os.path.join(TOOLS, "ppu_lifter.py"), ELF,
         "--functions", os.path.join(OUT, "functions.json"),
         "--hle-stubs", os.path.join(OUT, "EBOOT.imports.json"),
         "--code-end", CODE_END, "--max-chunk-lines", "80000",
         "-o", RECOMP])


def step_spu(a):
    if os.path.exists(os.path.join(SPU, "spu_workloads.c")) and not a.force:
        return
    if os.path.isdir(SPU):
        shutil.rmtree(SPU)
    images = os.path.join(SPU, "images")
    os.makedirs(images)
    run([PY, os.path.join(TOOLS, "extract_spu_images.py"), ELF, "--output", images])
    # One embedded image: Namco's sound core ("bnusCoreSpu.elf").
    found = [n for n in os.listdir(images) if n.endswith(".elf")]
    if len(found) != 1:
        sys.exit(f"expected 1 SPU image, found {len(found)}")
    os.rename(os.path.join(images, found[0]), os.path.join(images, "bnuscore.elf"))
    run([PY, os.path.join(TOOLS, "build_spu_workloads.py"), "--images", images,
         "--lifted", os.path.join(SPU, "lifted"), "--out", os.path.join(SPU, "spu_workloads.c"),
         "--register-fn", "t5dr_spu_register_all", "--constructor", "--title", "t5dr", "--eboot", ELF])


def find_vcvars():
    vswhere = os.path.join(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                           "Microsoft Visual Studio", "Installer", "vswhere.exe")
    if not os.path.exists(vswhere):
        sys.exit("Visual Studio 2022 Build Tools not found (C++ workload needed)")
    path = subprocess.run([vswhere, "-latest", "-products", "*", "-requires",
                           "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
                           "-property", "installationPath"],
                          capture_output=True, text=True).stdout.strip()
    bat = os.path.join(path, "VC", "Auxiliary", "Build", "vcvars64.bat")
    if not path or not os.path.exists(bat):
        sys.exit("vcvars64.bat not found -- install the VS 2022 C++ build tools")
    return bat


def step_compile(a):
    vcvars = find_vcvars()
    compiler = []
    clang = shutil.which("clang-cl") or (r"C:\Program Files\LLVM\bin\clang-cl.exe"
                                         if os.path.exists(r"C:\Program Files\LLVM\bin\clang-cl.exe") else None)
    if clang:
        compiler = [f'-DCMAKE_C_COMPILER="{clang}"', f'-DCMAKE_CXX_COMPILER="{clang}"']
    configure = " ".join(["cmake", "-S", f'"{ROOT}"', "-B", f'"{CMAKE_BUILD}"', "-G", "Ninja",
                          "-DCMAKE_BUILD_TYPE=Release", f'-DPS3RECOMP_DIR="{DEPS}"',
                          f'-DRECOMP_DIR="{RECOMP}"', f'-DSPU_DIR="{SPU}"', f'-DPython3_EXECUTABLE="{PY}"'] + compiler)
    build = f'cmake --build "{CMAKE_BUILD}"'
    cmd = f'call "{vcvars}" >nul && {configure} && {build}'
    print("  >", cmd)
    subprocess.run(cmd, shell=True, check=True)
    print(f"\nbuilt {os.path.join(CMAKE_BUILD, 't5dr.exe')}")
    print("run:  python tools/run_game.py")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pkg", help="the PSN package (.pkg)")
    ap.add_argument("--rap", help="the license (.rap)")
    ap.add_argument("--steps", nargs="+", choices=STEPS, default=STEPS)
    ap.add_argument("--force", action="store_true", help="redo steps whose output exists")
    a = ap.parse_args()
    os.chdir(ROOT)
    for s in STEPS:
        if s in a.steps:
            print(f"[{s}]")
            globals()["step_" + s](a)


if __name__ == "__main__":
    main()
