#!/usr/bin/env python3
"""Build Tekken 5: Dark Resurrection Online from the player's own PSN package.

    python tools/build_game.py --pkg <game.pkg> --rap <license.rap> [--out DIR] [--steps ...]

Steps (each skipped when its output is already there, unless --force):
  deps     clone ps3recomp at the pinned commit into deps/ps3recomp (a release
           zip already contains it, patched)
  keys     write keys/ps3.keys (tools/make_keys.py)
  decrypt  take EBOOT.BIN and PARAM.SFO out of the package, decrypt EBOOT.BIN
           with the .rap and check it is the supported version -- before the
           600 MB unpack, so a wrong package is refused within seconds
  unpack   extract the whole package into game/pkg/
  vfs      lay out game/vfs/ the way the runtime's file system expects
  lift     find functions and translate the PPU code to C++ in build/recomp/
  spu      extract and translate the SPU programs (sound core, skinning jobs) to C in build/spu/
  compile  configure and build build/cmake/t5dr.exe

--out DIR puts game/, build/ and keys/ under DIR instead of the repository
(the launcher uses <package>/native). Everything written there is
game-derived and must never be shared or committed.

Output for the launcher: each step starts with a line "[step]"; a step that
has nothing to do prints "  already done"; a failure ends with one line
"ERROR: <plain explanation>" on stderr and exit code 2.
"""
import argparse
import datetime
import hashlib
import json
import os
import shutil
import stat
import struct
import subprocess
import sys
import time
import urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import prereqs  # noqa: E402

PY = sys.executable

PS3RECOMP_URL = "https://github.com/NoahBPeterson/ps3recomp.git"
PS3RECOMP_BRANCH = "infamous/upstream-sync"
PS3RECOMP_COMMIT = "f17bcd3"

# NPUB30009 v01.00 -- the only version the port supports.
TITLE_ID = "NPUB30009"
TITLE_VERSION = "01.00"
CONTENT_ID = "UP0700-NPUB30009_00-UPDATE0000010000"
GAME_NAME = "Tekken 5: Dark Resurrection Online (PS3, US PSN, NPUB30009 v01.00)"
ELF_SHA1 = "be80165b84e30b6334baa6d6331b9db4ffd5a6a4"
PKG_SIZE = 619430240
CODE_END = "0x3C7100"   # end of .lib.stub; past it is .rodata

STEPS = ["deps", "keys", "decrypt", "unpack", "vfs", "lift", "spu", "compile"]


class Paths:
    """Every location the build writes, below one output root."""

    def __init__(self, out, deps=None):
        self.out = os.path.abspath(out)
        self.deps = os.path.abspath(deps) if deps else os.path.join(ROOT, "deps", "ps3recomp")
        self.tools = os.path.join(self.deps, "tools")
        self.keys = os.path.join(self.out, "keys", "ps3.keys")
        self.game = os.path.join(self.out, "game")
        self.pkg_dir = os.path.join(self.game, "pkg")
        self.unpacked_stamp = os.path.join(self.pkg_dir, ".unpacked")
        self.elf = os.path.join(self.game, "EBOOT.elf")
        self.vfs = os.path.join(self.game, "vfs")
        self.usrdir = os.path.join(self.vfs, "PS3_GAME", "USRDIR")
        self.hdd0 = os.path.join(self.vfs, "dev_hdd0")
        self.hdd0_usrdir = os.path.join(self.hdd0, "game", TITLE_ID, "USRDIR")
        self.build = os.path.join(self.out, "build")
        self.analysis = os.path.join(self.build, "out")
        self.recomp = os.path.join(self.build, "recomp")
        self.cmake = os.path.join(self.build, "cmake")
        self.spu = os.path.join(self.build, "spu")
        self.exe = os.path.join(self.cmake, "t5dr.exe")
        self.stamp = os.path.join(self.build, "t5dr_build.json")


P = Paths(ROOT)


class BuildError(Exception):
    pass


def fail(msg):
    raise BuildError(msg)


def run(cmd, capture=False, env=None, **kw):
    print("  >", " ".join(f'"{c}"' if " " in str(c) else str(c) for c in cmd), flush=True)
    if not capture:
        return subprocess.run(cmd, check=True, env=env, **kw)
    # Echo the output and keep it, so a failure can be explained.
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                         encoding="utf-8", errors="replace", env=env, **kw)
    lines = []
    for line in p.stdout:
        print(line, end="", flush=True)
        lines.append(line)
    p.wait()
    out = "".join(lines)
    if p.returncode:
        raise subprocess.CalledProcessError(p.returncode, cmd, output=out)
    return out


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


def pkg_content_id(path):
    """Content ID from a .pkg header, or None when the file is not a PS3 package."""
    with open(path, "rb") as f:
        hdr = f.read(0x60)
    if len(hdr) < 0x60 or hdr[:4] != b"\x7fPKG":
        return None
    return hdr[0x30:0x54].split(b"\0")[0].decode("ascii", "replace")


def read_sfo(path):
    """PARAM.SFO -> {key: value}."""
    with open(path, "rb") as f:
        d = f.read()
    if d[:4] != b"\0PSF":
        return {}
    key_tab, data_tab, n = struct.unpack_from("<III", d, 8)
    out = {}
    for i in range(n):
        ko, fmt, ln, _mx, do = struct.unpack_from("<HHIII", d, 0x14 + i * 16)
        key = d[key_tab + ko: d.index(b"\0", key_tab + ko)].decode("ascii", "replace")
        raw = d[data_tab + do: data_tab + do + ln]
        out[key] = (struct.unpack_from("<I", raw)[0] if fmt == 0x0404
                    else raw.split(b"\0")[0].decode("utf-8", "replace"))
    return out


def keys_env():
    env = dict(os.environ)
    env["T5DR_KEYS"] = P.keys        # the release's pkg_extract.py reads the package key from here
    env.setdefault("PYTHONUNBUFFERED", "1")
    return env


def deps_stamp_ok():
    """A release zip carries ps3recomp already patched; check it matches our patches."""
    stamp = os.path.join(P.deps, ".t5dr-vendored.json")
    if not os.path.exists(stamp):
        return None
    with open(stamp) as f:
        s = json.load(f)
    want = patch_digest()
    return s.get("commit") == PS3RECOMP_COMMIT and s.get("patches") == want


def patch_digest():
    h = hashlib.sha1()
    d = os.path.join(ROOT, "patches", "ps3recomp")
    for name in sorted(os.listdir(d)):
        if name.endswith(".patch"):
            h.update(name.encode())
            with open(os.path.join(d, name), "rb") as f:
                h.update(f.read().replace(b"\r\n", b"\n"))
    return h.hexdigest()


# Bump when a change to the steps below changes what ends up in t5dr.exe (lifter
# arguments, SPU handling, compile flags); messages and the like do not count.
CODE_VERSION = 4   # 2: sound core lifted with SPU_CORE_EXTRA_FUNCS; 3: sound core with SPU_NEAR_FLOAT;
                   # 4: lifted code compiled with the PGO profile (tools/gamedll/t5dr_lifted.proftext);
                   # 4: lifted PPU code with register promotion (ps3recomp patch 0066)

# The lifted code's profile for profile-guided optimisation (docs/BUILD_PERF.md): text, split into
# four parts and turned into clang's format at compile time (build_game_dll.prepare_profiles).
PGO_PROFILE = os.path.join(ROOT, "tools", "gamedll", "t5dr_lifted.proftext")


def code_id():
    """Identifies everything besides the player's game that goes into t5dr.exe. When a
    new release changes it, the launcher asks for a rebuild."""
    h = hashlib.sha1()
    h.update(f"{CODE_VERSION}:{PS3RECOMP_COMMIT}:{CODE_END}".encode())
    h.update(patch_digest().encode())
    with open(os.path.join(ROOT, "CMakeLists.txt"), "rb") as f:
        h.update(f.read().replace(b"\r\n", b"\n"))
    if os.path.exists(PGO_PROFILE):                  # a new profile changes the compiled code
        with open(PGO_PROFILE, "rb") as f:
            h.update(b"pgo:" + f.read().replace(b"\r\n", b"\n"))
    if prebuilt_host():
        h.update(sha1(os.path.join(HOST_DIR, "t5dr.exe")).encode())
        gd = os.path.join(ROOT, "tools", "gamedll")
        for dp, _, fns in sorted(os.walk(gd)):
            for n in sorted(fns):
                with open(os.path.join(dp, n), "rb") as f:
                    h.update(n.encode() + f.read().replace(b"\r\n", b"\n"))
    return h.hexdigest()[:16]


# A release made with package_release.py --prebuilt-host carries the runtime
# already compiled (t5dr.exe, CMake -DT5DR_GAME_DLL=ON) and its import library.
# The compile step then builds only the lifted code into t5dr_game.dll, with
# clang-cl + lld-link and no Visual Studio (tools/build_game_dll.py).
HOST_DIR = os.path.join(ROOT, "runtime")


def prebuilt_host():
    return all(os.path.exists(os.path.join(HOST_DIR, n)) for n in ("t5dr.exe", "t5dr.lib"))


# --------------------------------------------------------------------------- steps

def rmtree(path):
    """shutil.rmtree that also removes read-only files (git's object packs are read-only on Windows)."""
    def onerror(func, p, _exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)
    shutil.rmtree(path, onerror=onerror)


def step_deps(a):
    vend = deps_stamp_ok()
    if vend is True:
        # Also with "Redo every step": the copy is part of the release, there is nothing to fetch again (1.0.0
        # deleted it and tried a git clone, which failed on its read-only .git files: "Access is denied").
        print("  ps3recomp included in this package (patched) -- nothing to fetch")
    elif vend is False:
        fail("The ps3recomp copy in this folder does not match this version of the port. "
             "Download the release again and extract it into an empty folder.")
    elif os.path.isdir(os.path.join(P.deps, ".git")) and not a.force:
        print("  already done")
    else:
        if not shutil.which("git"):
            fail("Git is needed to download ps3recomp (the recompiler). Install Git, or use a release "
                 "zip, which already contains it.")
        if os.path.isdir(P.deps):
            rmtree(P.deps)
        run(["git", "-c", "core.longpaths=true", "clone", "-b", PS3RECOMP_BRANCH, PS3RECOMP_URL, P.deps])
        run(["git", "-C", P.deps, "checkout", "-q", PS3RECOMP_COMMIT])
        # Our fixes on top of the pinned commit (Windows build gaps and the like).
        patches = os.path.join(ROOT, "patches", "ps3recomp")
        for name in sorted(os.listdir(patches)):
            if name.endswith(".patch"):
                run(["git", "-C", P.deps, "apply", "--whitespace=nowarn", os.path.join(patches, name)])
    if not prereqs.python_crypto():
        if vend:
            fail("This package's Python is missing pycryptodome. Download the release again.")
        run([PY, "-m", "pip", "install", "-q", "-r", os.path.join(P.deps, "requirements.txt")])


def step_keys(a):
    if os.path.exists(P.keys) and not a.force:
        print("  already done")
        return
    try:
        run([PY, os.path.join(ROOT, "tools", "make_keys.py"), "--out", P.keys], capture=True)
    except subprocess.CalledProcessError as e:
        if "urlopen" in (e.output or "") or "URLError" in (e.output or "") or "getaddrinfo" in (e.output or ""):
            fail("Could not download the public PS3 key data from github.com (needed once, a few KB). "
                 "Check the internet connection and press BUILD GAME again.")
        raise


def need_pkg(a):
    if not a.pkg:
        fail("Choose your game package (.pkg) first.")
    if not os.path.exists(a.pkg):
        fail(f"The package file does not exist: {a.pkg}")
    cid = pkg_content_id(a.pkg)
    if cid is None:
        fail(f"{os.path.basename(a.pkg)} is not a PS3 package (.pkg).")
    return cid


def program_kind(path):
    """"self" for a PS3 program as the package carries it, "elf" for one already decrypted, None for anything
    else (an empty or cut-short file left by a stopped run)."""
    try:
        with open(path, "rb") as f:
            head = f.read(4)
        size = os.path.getsize(path)
    except OSError:
        return None
    if size < 0x1000:
        return None
    return {b"SCE\0": "self", b"\x7fELF": "elf"}.get(head)


def step_decrypt(a):
    if os.path.exists(P.elf) and sha1(P.elf) == ELF_SHA1 and not a.force:
        print("  already done")
        return
    if not a.rap:
        fail("Choose your license file (.rap) first.")
    if not os.path.exists(a.rap) or os.path.getsize(a.rap) != 16:
        fail(f"{a.rap} is not a PS3 license: a .rap file is exactly 16 bytes.")
    eboot = os.path.join(P.pkg_dir, "USRDIR", "EBOOT.BIN")
    sfo = os.path.join(P.pkg_dir, "PARAM.SFO")

    def take_out():
        cid = need_pkg(a)
        print(f"  package content ID: {cid}")
        # Only the program and its PARAM.SFO first: a few MB, seconds.
        for name in ("PARAM.SFO", "EBOOT.BIN"):
            run([PY, os.path.join(P.tools, "pkg_extract.py"), a.pkg, P.pkg_dir, "--only", name], env=keys_env())

    if not (os.path.exists(eboot) and os.path.exists(sfo)) or a.force:
        take_out()
    elif program_kind(eboot) is None and a.pkg:
        # Left by an earlier run that was stopped while taking it out (empty or cut short).
        print("  the program taken out by an earlier run is damaged: taking it out of the package again")
        os.remove(eboot)
        take_out()
    if not os.path.exists(eboot):
        fail("This package has no USRDIR/EBOOT.BIN -- it is not a game package (an add-on or theme?). "
             f"The port needs {GAME_NAME}.")
    s = read_sfo(sfo) if os.path.exists(sfo) else {}
    title, tid, ver = s.get("TITLE", "?"), s.get("TITLE_ID", "?"), s.get("APP_VER", s.get("VERSION", "?"))
    print(f"  PARAM.SFO: {title} / {tid} / version {ver}")
    if tid != TITLE_ID:
        fail(f"This package is \"{title}\" ({tid}). The port needs {GAME_NAME}.")
    kind = program_kind(eboot)
    if kind == "elf":
        # A re-packed package that carries the program already decrypted: usable when it is the same program
        # (the SHA-1 pin below decides).
        print("  the package carries the program already decrypted")
        os.makedirs(os.path.dirname(P.elf), exist_ok=True)
        shutil.copyfile(eboot, P.elf)
        out = ""
    else:
        try:
            out = run([PY, os.path.join(ROOT, "tools", "unself.py"), eboot, a.rap, P.elf, "--keys", P.keys],
                      capture=True)
        except subprocess.CalledProcessError as e:
            if "wrong .rap" in (e.output or ""):
                fail("The license (.rap) does not belong to this package. Use the .rap whose name matches "
                     f"the package's content ID ({CONTENT_ID}).")
            if a.pkg and os.path.exists(a.pkg) and os.path.getsize(a.pkg) != PKG_SIZE:
                fail(f"The package is {os.path.getsize(a.pkg):,} bytes, the supported one is {PKG_SIZE:,} bytes: "
                     "the download is incomplete or it is a different file. Download it again.")
            fail("Decrypting the game program failed (see the log above). Tick \"Redo every step\" and press "
                 f"BUILD GAME again; if it fails again, check that the package is {PKG_SIZE:,} bytes.")
    got = sha1(P.elf)
    if got != ELF_SHA1:
        os.remove(P.elf)
        cid = next((l.split("content id", 1)[1].split(",")[0].strip()
                    for l in out.splitlines() if "content id" in l), "?")
        fail(f"This copy is a different version of the game: \"{title}\" version {ver}, content ID {cid} "
             f"(program SHA-1 {got[:12]}...). The port supports only {GAME_NAME}, "
             f"content ID {CONTENT_ID}.")
    print(f"  program OK: SHA-1 {got} ({TITLE_ID} v{TITLE_VERSION})")


def step_unpack(a):
    if os.path.exists(P.unpacked_stamp) and not a.force:
        print("  already done")
        return
    usr = os.path.join(P.pkg_dir, "USRDIR")
    if not a.pkg and not a.force and os.path.isdir(usr) and len(os.listdir(usr)) > 1:
        print("  already done (unpacked by an earlier version of this script)")
        open(P.unpacked_stamp, "w").close()
        return
    need_pkg(a)
    run([PY, os.path.join(P.tools, "pkg_extract.py"), a.pkg, P.pkg_dir], env=keys_env())
    with open(P.unpacked_stamp, "w", encoding="utf-8") as f:   # any file name (cp1252 stopped at "Ł")
        f.write(os.path.basename(a.pkg) + "\n")


def step_vfs(a):
    # The runtime boots <vfs>/PS3_GAME/USRDIR/EBOOT.elf and reads PARAM.SFO
    # beside it. The game itself is a PSN title: it looks for its data under
    # /dev_hdd0/game/NPUB30009/USRDIR/, which run_game.py maps to
    # <vfs>/dev_hdd0 through PS3_HDD0_ROOT.
    os.makedirs(P.usrdir, exist_ok=True)
    os.makedirs(P.hdd0_usrdir, exist_ok=True)
    link_or_copy(P.elf, os.path.join(P.usrdir, "EBOOT.elf"))
    link_or_copy(os.path.join(P.pkg_dir, "PARAM.SFO"), os.path.join(P.vfs, "PS3_GAME", "PARAM.SFO"))
    link_or_copy(os.path.join(P.pkg_dir, "PARAM.SFO"), os.path.join(P.hdd0_usrdir, "..", "PARAM.SFO"))
    for name in sorted(os.listdir(os.path.join(P.pkg_dir, "USRDIR"))):
        if name.upper() != "EBOOT.BIN":
            link_or_copy(os.path.join(P.pkg_dir, "USRDIR", name), os.path.join(P.hdd0_usrdir, name))
            stale = os.path.join(P.usrdir, name)
            if os.path.exists(stale):
                os.remove(stale)


def step_lift(a):
    # The lift is redone when the lifter changed (the patches change what it
    # emits -- e.g. 0013's inline guest stores); a stamp next to the output
    # records which ppu_lifter.py made it. A lift without a stamp predates it
    # and is redone once (~1 minute).
    lifter = os.path.join(P.tools, "ppu_lifter.py")
    stamp = os.path.join(P.recomp, ".lifter.sha1")
    # Register promotion (ps3recomp patch 0066, the lifter's default): the guest registers a function
    # uses live in C locals between calls. T5DR_LIFT_REGPROMO=0 lifts without it -- the same results,
    # only slower; for comparisons. The stamp records it, so switching lifts again.
    regpromo = os.environ.get("T5DR_LIFT_REGPROMO", "1") != "0"
    lifter_id = (sha1(lifter) if os.path.exists(lifter) else "") + ("" if regpromo else ":regpromo=off")
    if os.path.exists(os.path.join(P.recomp, "ppu_recomp.h")) and not a.force:
        made_by = open(stamp).read().strip() if os.path.exists(stamp) else None
        if made_by == lifter_id:
            print("  already done")
            return
        print("  the lifter changed since the last lift: lifting again")
    os.makedirs(P.analysis, exist_ok=True)
    run([PY, os.path.join(P.tools, "ppu_loader.py"), P.elf, "-o", P.analysis])
    run([PY, os.path.join(P.tools, "find_functions.py"), P.elf,
         "--seed-json", os.path.join(P.analysis, "EBOOT.functions.json"),
         "-o", os.path.join(P.analysis, "functions.json")])
    if os.path.isdir(P.recomp):
        rmtree(P.recomp)
    os.makedirs(P.recomp)
    run([PY, os.path.join(P.tools, "ppu_lifter.py"), P.elf,
         "--functions", os.path.join(P.analysis, "functions.json"),
         "--hle-stubs", os.path.join(P.analysis, "EBOOT.imports.json"),
         "--code-end", CODE_END, "--max-chunk-lines", "80000",
         "-o", P.recomp] + ([] if regpromo else ["--regpromo", "off"]))
    with open(stamp, "w") as f:
        f.write(lifter_id + "\n")


# Function entries of the sound core that its function finder cannot see: the
# DSP effect table in the core's data (LS 0x11AB0-0x11B84, records named
# "DLAY", "DPL2", "HPF ", "IIRF", "LHPF", "MIX ", "MONO", "MUX ", "PTCH", "REVB",
# "TMPL", "VOLP" plus one more process function) holds pointers to 13
# functions that nothing branches to directly. Unlifted, every call landed in
# the runtime's SPU interpreter (~600 entries a second in a fight, each
# interpreting a whole effect over its sample block) instead of native code.
SPU_CORE_EXTRA_FUNCS = ("bnuscore=0xF9B8,0x59A8,0x5D90,0x5FD8,0x68A0,0x6E98,0x7528,"
                        "0x7598,0x7618,0x7690,0x7968,0x8B70,0x8BC0")


def step_spu(a):
    core_done = os.path.exists(os.path.join(P.spu, "spu_workloads.c"))
    jobs_done = os.path.exists(os.path.join(P.spu, "lifted", "jcsignal", "spu_recomp.c"))
    # The core is lifted again when its lift arguments changed (a lift without
    # the stamp predates SPU_CORE_EXTRA_FUNCS).
    stamp = os.path.join(P.spu, ".core_lift_args")
    core_args_ok = os.path.exists(stamp) and open(stamp).read().strip() == SPU_CORE_EXTRA_FUNCS
    if core_done and jobs_done and core_args_ok and not a.force:
        print("  already done")
        return
    if core_done and not core_args_ok and not a.force:
        print("  the sound core's lift arguments changed: lifting it again")
        run([PY, os.path.join(P.tools, "build_spu_workloads.py"), "--images", os.path.join(P.spu, "images"),
             "--lifted", os.path.join(P.spu, "lifted"), "--out", os.path.join(P.spu, "spu_workloads.c"),
             "--register-fn", "t5dr_spu_register_all", "--constructor", "--title", "t5dr", "--eboot", P.elf,
             "--relift", "--extra-funcs", SPU_CORE_EXTRA_FUNCS])
        with open(stamp, "w") as f:
            f.write(SPU_CORE_EXTRA_FUNCS + "\n")
    if a.force or not core_done:
        if os.path.isdir(P.spu):
            rmtree(P.spu)
        images = os.path.join(P.spu, "images")
        os.makedirs(images)
        run([PY, os.path.join(P.tools, "extract_spu_images.py"), P.elf, "--output", images])
        # One embedded image: Namco's sound core ("bnusCoreSpu.elf").
        found = [n for n in os.listdir(images) if n.endswith(".elf")]
        if len(found) != 1:
            fail(f"expected 1 SPU image, found {len(found)}")
        os.rename(os.path.join(images, found[0]), os.path.join(images, "bnuscore.elf"))
        run([PY, os.path.join(P.tools, "build_spu_workloads.py"), "--images", images,
             "--lifted", os.path.join(P.spu, "lifted"), "--out", os.path.join(P.spu, "spu_workloads.c"),
             "--register-fn", "t5dr_spu_register_all", "--constructor", "--title", "t5dr", "--eboot", P.elf,
             "--extra-funcs", SPU_CORE_EXTRA_FUNCS])
        with open(stamp, "w") as f:
            f.write(SPU_CORE_EXTRA_FUNCS + "\n")
    # The SPURS jobs (vertex skinning + the chain's signal job) are raw images
    # in the ELF's data segment, not SPU ELFs; they need their own extractor.
    run([PY, os.path.join(ROOT, "tools", "lift_spu_jobs.py"), "--elf", P.elf, "--spu", P.spu, "--ps3recomp", P.deps]
        + (["--relift"] if a.force else []))


def find_vcvars():
    bat = prereqs.vcvars()
    if not bat:
        fail("The C++ build tools (Visual Studio 2022 Build Tools, x64 C++ toolset) are not installed. "
             "Open the launcher's Build tab and click Install next to them.")
    return bat


def write_stamp(compiler):
    with open(P.stamp, "w") as f:
        json.dump({"code_id": code_id(), "elf_sha1": ELF_SHA1, "title": TITLE_ID, "version": TITLE_VERSION,
                   "compiler": compiler, "built": datetime.datetime.now().isoformat(timespec="seconds")},
                  f, indent=1)


def compile_game_dll(a):
    llvm = prereqs.portable_llvm()
    if not llvm:
        fail("clang-cl.exe and lld-link.exe were not found in toolchain\\llvm\\bin. Download the release again.")
    os.makedirs(P.cmake, exist_ok=True)
    for n in os.listdir(HOST_DIR):                  # t5dr.exe (+ anything shipped beside it)
        if n.lower().endswith((".exe", ".dll")):
            src, dst = os.path.join(HOST_DIR, n), os.path.join(P.cmake, n)
            if not os.path.exists(dst) or sha1(src) != sha1(dst):
                shutil.copy2(src, dst)
    run([PY, os.path.join(ROOT, "tools", "build_game_dll.py"), "--recomp", P.recomp, "--spu", P.spu,
         "--deps", P.deps, "--host-lib", os.path.join(HOST_DIR, "t5dr.lib"),
         "--out", os.path.join(P.cmake, "t5dr_game.dll"), "--obj", os.path.join(P.build, "gamedll_obj"),
         "--llvm", llvm] + (["--force"] if a.force else []))
    write_stamp("clang-cl (header-free game DLL) from " + llvm)
    print(f"\nbuilt {P.exe} + t5dr_game.dll")


def step_compile(a):
    if prebuilt_host() and not a.full_compile:
        return compile_game_dll(a)
    vcvars = find_vcvars()
    if not prereqs.windows_sdk():
        fail("The Windows SDK is missing (needed for Direct3D 12). Install it with the C++ build tools.")
    clang = prereqs.clang_cl()
    if not clang:
        fail("clang-cl (LLVM 16 or newer) was not found. Install LLVM or the Visual Studio component "
             "'C++ Clang tools for Windows'.")
    cmake, ninja = prereqs.cmake_ninja()
    if not (cmake and ninja):
        fail("CMake and Ninja were not found. Install the Visual Studio component 'C++ CMake tools for Windows'.")
    compiler = [f'-DCMAKE_C_COMPILER="{clang[0]}"', f'-DCMAKE_CXX_COMPILER="{clang[0]}"']
    # the PGO profile, split into its parts (build_game_dll.prepare_profiles); without llvm-profdata.exe
    # next to clang-cl the build goes on without it (same game, a little slower)
    pgo = []
    if os.path.exists(PGO_PROFILE):
        import build_game_dll
        os.makedirs(P.cmake, exist_ok=True)
        prof = build_game_dll.prepare_profiles(PGO_PROFILE, P.cmake, os.path.dirname(clang[0]))
        for part, var in (("ppu", "T5DR_PGO"), ("snd", "T5DR_PGO_SND"), ("skin", "T5DR_PGO_SKIN"),
                          ("spu", "T5DR_PGO_SPU")):
            pgo.append(f'-D{var}="{prof.get(part, "")}"')
    configure = " ".join([f'"{cmake}"', "-S", f'"{ROOT}"', "-B", f'"{P.cmake}"', "-G", "Ninja",
                          f'-DCMAKE_MAKE_PROGRAM="{ninja}"',
                          "-DCMAKE_BUILD_TYPE=Release", f'-DPS3RECOMP_DIR="{P.deps}"',
                          f'-DRECOMP_DIR="{P.recomp}"', f'-DSPU_DIR="{P.spu}"', f'-DPython3_EXECUTABLE="{PY}"']
                         + compiler + pgo)
    build = f'"{cmake}" --build "{P.cmake}"'
    cmd = f'call "{vcvars}" >nul && {configure} && {build}'
    print("  >", cmd, flush=True)
    subprocess.run(cmd, shell=True, check=True)
    write_stamp("clang-cl %d.%d + MSVC/Windows SDK (CMake)" % clang[1])
    print(f"\nbuilt {P.exe}")


def main():
    global P
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pkg", help="the PSN package (.pkg)")
    ap.add_argument("--rap", help="the license (.rap)")
    ap.add_argument("--out", default=ROOT, help="output root for game/, build/, keys/ (default: the repository)")
    ap.add_argument("--deps", help="ps3recomp checkout to use (default: deps/ps3recomp)")
    ap.add_argument("--steps", nargs="+", choices=STEPS, default=STEPS)
    ap.add_argument("--force", action="store_true", help="redo steps whose output exists")
    ap.add_argument("--code-id", action="store_true", help="print the code ID of this version and exit")
    ap.add_argument("--full-compile", action="store_true",
                    help="compile everything with CMake + Visual Studio even when a prebuilt runtime is present")
    a = ap.parse_args()
    if a.code_id:
        print(code_id())
        return
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    os.environ.setdefault("PYTHONUNBUFFERED", "1")
    # The Python tools this starts print paths; into a pipe they would use the ANSI code page and
    # stop with UnicodeEncodeError on a folder or user name outside it ("Tekken Ł東京").
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    # And the files they write (the lifted C++, JSON) in UTF-8, whatever Windows' code page is: on a
    # Korean Windows (cp949) the lifter stopped with UnicodeEncodeError on a "--" dash in a comment.
    os.environ["PYTHONUTF8"] = "1"
    P = Paths(a.out, a.deps)
    os.makedirs(P.out, exist_ok=True)
    os.chdir(P.out)
    step = None
    times = []
    try:
        for step in STEPS:
            if step in a.steps:
                print(f"[{step}]", flush=True)
                t0 = time.time()
                globals()["step_" + step](a)
                times.append((step, time.time() - t0))
                print(f"  ({step}: {times[-1][1]:.1f} s)", flush=True)
    except BuildError as e:
        print(f"ERROR: {e}", file=sys.stderr, flush=True)
        sys.exit(2)
    except subprocess.CalledProcessError as e:
        print(f"ERROR: step '{step}' failed: a tool exited with code {e.returncode} -- the lines above say why.",
              file=sys.stderr, flush=True)
        sys.exit(2)
    except KeyboardInterrupt:
        print("ERROR: cancelled", file=sys.stderr, flush=True)
        sys.exit(3)
    except OSError as e:
        # disk full, a file locked by antivirus/OneDrive, a path too long for Windows: one sentence for
        # the launcher, the details (traceback) in build.log
        import traceback
        traceback.print_exc(file=sys.stdout)
        too_long = (getattr(e, "winerror", None) in (3, 206) or "[WinError 206]" in str(e)
                    or len(str(e.filename or "")) > 240)
        hint = (" The folder path is too long for Windows: move the folder to a short path such as "
                r"C:\Games\T5DR." if too_long
                else " Is the disk full, or does another program (antivirus, OneDrive) hold the file?")
        print(f"ERROR: step '{step}' could not read or write a file: {e.strerror or e}"
              f" ({e.filename}).{hint}", file=sys.stderr, flush=True)
        sys.exit(2)
    print("[done] " + ", ".join(f"{n} {t:.0f}s" for n, t in times) + f" -- total {sum(t for _, t in times):.0f} s",
          flush=True)


if __name__ == "__main__":
    main()
