#!/usr/bin/env python3
"""Build Tekken 5: Dark Resurrection Online from the player's own PSN package.

    python tools/build_game.py --pkg <game.pkg> --rap <license.rap> [--out DIR] [--steps ...]

Steps (each skipped when its output is already there, unless --force):
  deps     clone ps3recomp at the pinned commit into deps/ps3recomp (a release
           zip already contains it, patched); a developer's checkout whose patch
           series is not this tree's any more (.git/t5dr-prepared.json, else the
           patches tried one by one) is prepared again (tools/prepare_ps3recomp.py)
  keys     write keys/ps3.keys (tools/make_keys.py)
  decrypt  take EBOOT.BIN and PARAM.SFO out of the package, decrypt EBOOT.BIN
           with the .rap and check it is the supported version -- before the
           600 MB unpack, so a wrong package is refused within seconds
  unpack   extract the whole package into game/pkg/
  vfs      lay out game/vfs/ the way the runtime's file system expects
  lift     find functions and translate the PPU code to C++ in build/recomp/
  spu      extract and translate the SPU programs (sound core, skinning jobs) to C in build/spu/
  compile  configure and build build/cmake/t5dr.exe (macOS: build/cmake/t5dr)

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
# The same package (619,430,240 bytes, the same program: ELF_SHA1) also comes from PSN under this content ID,
# with its own .rap (a player's build, 1.1.3). The build checks the program itself, so both are supported.
CONTENT_IDS = (CONTENT_ID, "UP0700-NPUB30009_00-0000000000010000")
# Programs of other versions players had (the content ID in the program's own header -> the version): the build
# says so instead of blaming the .rap (two players' v01.01 packages, GitHub #20/#21).
OTHER_VERSIONS = {"UP0700-NPUB30009_00-0000000000000000": "01.01",
                  # the European "Online" edition (PARAM.SFO VERSION 02.00, APP_VER 01.00): another program again,
                  # closer to the US one; not supported yet (docs/EU.md)
                  "UP0700-NPEA00019_00-TEKKEN5DRO000000": "02.00 (Online)"}
GAME_NAME = "Tekken 5: Dark Resurrection Online (PS3, US PSN, NPUB30009 v01.00)"
ELF_SHA1 = "be80165b84e30b6334baa6d6331b9db4ffd5a6a4"
PKG_SIZE = 619430240
CODE_END = "0x3C7100"   # end of .lib.stub; past it is .rodata

# Function entries of the sound core that its function finder cannot see: the
# DSP effect table in the core's data (LS 0x11AB0-0x11B84, records named
# "DLAY", "DPL2", "HPF ", "IIRF", "LHPF", "MIX ", "MONO", "MUX ", "PTCH", "REVB",
# "TMPL", "VOLP" plus one more process function) holds pointers to 13
# functions that nothing branches to directly. Unlifted, every call landed in
# the runtime's SPU interpreter (~600 entries a second in a fight, each
# interpreting a whole effect over its sample block) instead of native code.
SPU_CORE_EXTRA_FUNCS = ("bnuscore=0xF9B8,0x59A8,0x5D90,0x5FD8,0x68A0,0x6E98,0x7528,"
                        "0x7598,0x7618,0x7690,0x7968,0x8B70,0x8BC0")

# 1.1.9: the programs the build accepts, by the SHA-1 of the decrypted EBOOT.elf (docs/EU.md). The US release is
# the one everything was made for; the European release (NPEA00019 v01.00, Sony's EP9000 package of 2007) is
# another build of the game -- about half of its functions are the US ones byte for byte, the rest and the data
# layout differ -- so what src/ does at US addresses (online play, practice tools, training overlay, late input)
# stays off for it (src/platform/t5_game.h): it builds and plays offline.
#   code_end   end of .lib.stub (the firmware import stubs); past it is .rodata
#   spu_extra  the sound core's effect functions (SPU_CORE_EXTRA_FUNCS above): the EU core is another build of it,
#              its effect table (the same 12 names, 0x60 further on) points 0x88 further; the 13th entry by its code
#   pgo        the shipped PGO profile names the US program's functions: for another program it would only mislead
#   online     the online modules know this program (BuildInfo.has_online reads it from the build stamp)
PROGRAMS = {
    ELF_SHA1: {
        "key": "us", "title_id": TITLE_ID, "version": TITLE_VERSION, "region": "US", "name": GAME_NAME,
        "content_ids": CONTENT_IDS, "pkg_size": PKG_SIZE, "code_end": CODE_END, "spu_extra": SPU_CORE_EXTRA_FUNCS,
        "pgo": True, "online": True,
    },
    "586baa2074e3d259b303879fc7cbea1000041b60": {
        "key": "eu", "title_id": "NPEA00019", "version": "01.00", "region": "EU",
        "name": "Tekken 5: Dark Resurrection (PS3, EU PSN, NPEA00019 v01.00)",
        "content_ids": ("EP9000-NPEA00019_00-0000000000000000",), "pkg_size": 599050576, "code_end": "0x30388C",
        "spu_extra": ("bnuscore=0xFA38,0x5A30,0x5E18,0x6060,0x6930,0x6F28,0x75B8,"
                      "0x7628,0x76A8,0x7720,0x79F8,0x8C00,0x8C50"),
        "pgo": False, "online": False,
    },
}
US_PROGRAM = PROGRAMS[ELF_SHA1]
TITLE_IDS = tuple(dict.fromkeys(p["title_id"] for p in PROGRAMS.values()))      # ("NPUB30009", "NPEA00019")
ALL_CONTENT_IDS = tuple(c for p in PROGRAMS.values() for c in p["content_ids"])
SUPPORTED_TEXT = "; ".join(f"{p['name']}, content ID {p['content_ids'][0]}" for p in PROGRAMS.values())


def program_of(content_id=None, title_id=None):
    """The supported program a package or license is for: by its content ID, else its title ID; None if none."""
    for p in PROGRAMS.values():
        if content_id and content_id in p["content_ids"]:
            return p
    for p in PROGRAMS.values():
        if title_id and title_id == p["title_id"]:
            return p
    return None

STEPS = ["deps", "keys", "decrypt", "unpack", "vfs", "lift", "spu", "compile", "shaders"]
# "shaders" (1.1.5, tools/shader_warmup.py) runs only with --warmup (the launcher passes it) or when named in
# --steps: it starts the built game for a few minutes, which a developer's or CI build does not want.
DEFAULT_STEPS = [s for s in STEPS if s != "shaders"]


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
        self.exe = os.path.join(self.cmake, "t5dr.exe" if os.name == "nt" else "t5dr")
        self.stamp = os.path.join(self.build, "t5dr_build.json")

    def hdd0_usrdir_of(self, title_id):
        """/dev_hdd0/game/<title id>/USRDIR, where a PSN game reads its data: the program's own title ID (1.1.9)."""
        return os.path.join(self.hdd0, "game", title_id, "USRDIR")


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
        return parse_sfo(f.read())


def parse_sfo(d):
    """PARAM.SFO's bytes -> {key: value}; {} for anything else."""
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


def sfo_version(s):
    """The game version a PARAM.SFO names: APP_VER (a v01.01 package has "01.01"), else VERSION (the supported
    package has only VERSION "01.00"); "?" when it names none."""
    return s.get("APP_VER") or s.get("VERSION") or "?"


def self_content_id(data):
    """The content ID in a PS3 program's (SELF's) NPDRM header -- no key needed to read it -- or None. `data`: the
    program's first bytes (64 KB is plenty) or a path. Decrypting it needs the .rap of exactly this content ID."""
    try:
        if isinstance(data, str):
            with open(data, "rb") as f:
                data = f.read(1 << 16)
        if data[:4] != b"SCE\0":
            return None
        sup_off, sup_size = struct.unpack_from(">QQ", data, 0x28 + 8 * 6)
        off, end = sup_off, min(sup_off + sup_size, len(data))
        while off + 0x10 <= end:
            typ, size, nxt = struct.unpack_from(">IIQ", data, off)
            if typ == 3:
                npd = data[off + 0x10: off + 0x90]
                return npd[0x10:0x40].rstrip(b"\0").decode("ascii", "replace") if npd[:4] == b"NPD\0" else None
            if not nxt or size < 0x10:
                break
            off += size
    except (OSError, struct.error):
        pass
    return None


_PKG_TOOL = {}


def peek_key_file(keys=None):
    """The keys/ps3.keys the package peek can use: `keys` (the launcher passes its output folder's), this build's
    (P.keys), <ROOT>/native/keys/ps3.keys; None when none is there yet."""
    for k in ([keys] if keys else []) + [P.keys, os.path.join(ROOT, "native", "keys", "ps3.keys")]:
        if k and os.path.isfile(k):
            return k
    return None


def peek_needs_keys(deps=None, keys=None):
    """True when the package peek waits for keys/ps3.keys: a release's pkg_extract.py (the package keys are not
    shipped: package_release.strip_pkg_keys) and no key file yet -- a fresh release folder before BUILD GAME's keys
    step (1.1.5/1.1.6: the version warning never showed there; GitHub #20/#21)."""
    if os.environ.get("T5DR_KEYS") or peek_key_file(keys):
        return False
    try:
        with open(os.path.join(deps or P.deps, "tools", "pkg_extract.py"), encoding="utf-8", errors="replace") as f:
            return "_t5dr_key(" in f.read()
    except OSError:
        return False


def _pkg_tool(deps, keys=None):
    """ps3recomp's pkg_extract.py as a module (for its keystream: the package key stays in ps3recomp), or None."""
    path = os.path.join(deps, "tools", "pkg_extract.py")
    # A release's pkg_extract.py reads the package key from T5DR_KEYS while it is imported, and without it
    # raises SystemExit: in 1.1.5 that closed the launcher right after its start (the Build tab peeks into the
    # chosen package). So the key file's path for the import, and SystemExit is one more "cannot peek".
    old = os.environ.get("T5DR_KEYS")
    key = old or peek_key_file(keys)
    slot = (path, key)                    # (a key file made later -- the launcher makes one -- is tried again)
    if slot not in _PKG_TOOL:
        mod = None
        if not old and key:
            os.environ["T5DR_KEYS"] = key
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("t5dr_pkg_extract", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if not (getattr(mod, "_HAVE_PYCRYPTO", False) and callable(getattr(mod, "_keystream", None))):
                mod = None
        except (Exception, SystemExit):   # noqa: BLE001 -- no tree, an old one, no keys, no pycryptodome
            mod = None
        finally:
            if old:
                os.environ["T5DR_KEYS"] = old
            else:
                os.environ.pop("T5DR_KEYS", None)
        _PKG_TOOL[slot] = mod
    return _PKG_TOOL[slot]


def pkg_peek(path, want=("PARAM.SFO", "EBOOT.BIN"), limit=1 << 16, deps=None, keys=None):
    """{file name: its first `limit` bytes} for the files named in `want`, read straight from a retail PS3 package:
    its file table and a few KB, nothing unpacked, well under a second. None when that is not possible (not a
    package, a debug package, ps3recomp's pkg_extract.py or pycryptodome missing)."""
    mod = _pkg_tool(deps or P.deps, keys)
    if mod is None:
        return None
    try:
        with open(path, "rb") as f:
            hdr = f.read(0xA0)
            if len(hdr) < 0xA0 or hdr[:4] != b"\x7fPKG" or not struct.unpack_from(">H", hdr, 4)[0] & 0x8000:
                return None
            count = struct.unpack_from(">I", hdr, 0x14)[0]
            data_off = struct.unpack_from(">Q", hdr, 0x20)[0]
            riv, hdr60 = hdr[0x70:0x80], hdr[0x60:0xA0]
            if not 0 < count < 100000:
                return None

            def dec(off, n):
                sb, skip = off // 16, off % 16
                f.seek(data_off + sb * 16)
                raw = f.read(skip + n)
                ks = mod._keystream("finalized", riv, hdr60, sb, (len(raw) + 15) // 16)[:len(raw)]
                return (int.from_bytes(raw, "big") ^ int.from_bytes(ks, "big")).to_bytes(len(raw), "big")[skip:]
            table = dec(0, count * 0x20)
            out = {}
            for i in range(len(table) // 0x20):
                no, ns, fo, fs, flags = struct.unpack_from(">IIQQI", table, i * 0x20)
                if flags & 0x10000000 or not 0 < ns < 4096:      # PSP-keyed entries: not in a PS3 game
                    continue
                name = dec(no, ns).split(b"\0")[0].decode("ascii", "replace").replace("\\", "/").split("/")[-1]
                if name in want and fs > 0 and name not in out:
                    out[name] = dec(fo, min(fs, limit))
            return out
    except (OSError, struct.error, ValueError, OverflowError):
        return None


def package_facts(path, deps=None, keys=None):
    """What a package says about itself before anything is unpacked: {"title", "title_id", "version" (PARAM.SFO),
    "program" (the content ID of its program, whose license it needs)}, or None when it cannot be read that way."""
    files = pkg_peek(path, deps=deps, keys=keys)
    if not files:
        return None
    s = parse_sfo(files.get("PARAM.SFO", b""))
    return {"title": s.get("TITLE", "?"), "title_id": s.get("TITLE_ID", "?"), "version": sfo_version(s),
            "program": self_content_id(files.get("EBOOT.BIN", b""))}


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


PATCH_DIR = os.path.join(ROOT, "patches", "ps3recomp")
PREPARED_STAMP = "t5dr-prepared.json"     # in a git checkout's .git/: the series step_deps / prepare_ps3recomp applied


def patch_digest(d=None):
    h = hashlib.sha1()
    d = d or PATCH_DIR
    for name in sorted(os.listdir(d)):
        if name.endswith(".patch"):
            h.update(name.encode())
            with open(os.path.join(d, name), "rb") as f:
                h.update(f.read().replace(b"\r\n", b"\n"))
    return h.hexdigest()


# Bump when a change to the steps below changes what ends up in t5dr.exe (lifter
# arguments, SPU handling, compile flags); messages and the like do not count.
CODE_VERSION = 7   # 2: sound core lifted with SPU_CORE_EXTRA_FUNCS; 3: sound core with SPU_NEAR_FLOAT;
                   # 4 (1.1.3): lifted code compiled with the PGO profile (tools/gamedll/t5dr_lifted.proftext);
                   # 5 (1.1.4 work): lifted PPU code with register promotion (ps3recomp patch 0066), compiled with
                   # -fno-finite-loops (build_game_dll.py);
                   # 6 (1.1.4): + the guest store's coherence check through a bitmap pointer (0069); the game
                   # computes differently with random-unlock-114 (seeds, unlocks) and skip-114 (START gate);
                   # 7 (1.1.5): online training rooms (endless health) and the health handicap change what the
                   # game simulates online (src/netplay/match_rules.h)

# Guest functions src/ detours: a macOS online build lifts them with hook slots (step_lift).
HOOK_SLOTS = os.path.join(ROOT, "src", "rollback", "hook_slots.txt")

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


def patch_series(d=None):
    d = d or PATCH_DIR
    return sorted(n for n in os.listdir(d) if n.endswith(".patch"))


def _git_out(deps, *args):
    r = subprocess.run(["git", "-c", "core.longpaths=true", "-C", deps, *args], capture_output=True)
    if r.returncode:
        raise OSError(f"git {' '.join(args)} in {deps}: {r.stderr.decode('utf-8', 'replace').strip()}")
    return r.stdout


def tree_digest(deps):
    """The state of a checkout's files against its HEAD: the diff, the untracked files and their content. Equal
    to the stamp's: nothing was changed by hand since the series was applied."""
    h = hashlib.sha1()
    h.update(_git_out(deps, "rev-parse", "HEAD"))
    h.update(_git_out(deps, "diff", "HEAD", "--binary").replace(b"\r\n", b"\n"))
    for rel in sorted(_git_out(deps, "ls-files", "--others", "--exclude-standard", "-z").split(b"\0")):
        if rel:
            h.update(rel)
            try:
                with open(os.path.join(deps, rel.decode("utf-8", "replace")), "rb") as f:
                    h.update(hashlib.sha1(f.read()).digest())
            except OSError:
                pass
    return h.hexdigest()


def write_prepared_stamp(deps, commit=None, patches=None, adopted=False):
    """Note in deps/.git which commit + patch series this checkout has (prepare_ps3recomp.py, step_deps)."""
    stamp = {"commit": commit or PS3RECOMP_COMMIT, "patches": patch_digest(patches), "series": patch_series(patches),
             "tree": tree_digest(deps), "adopted": adopted, "time": time.strftime("%Y-%m-%d %H:%M:%S")}
    with open(os.path.join(deps, ".git", PREPARED_STAMP), "w", encoding="utf-8") as f:
        json.dump(stamp, f, indent=1)
    return stamp


def note_prepared(deps, adopted=False):
    """write_prepared_stamp, where a failure only costs the check next time (the step's work is done)."""
    try:
        write_prepared_stamp(deps, adopted=adopted)
    except OSError as e:
        print(f"  (could not note the patch series in {deps}: {e})", flush=True)


def read_prepared_stamp(deps):
    try:
        with open(os.path.join(deps, ".git", PREPARED_STAMP), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def same_dir(a, b):
    """Whether two paths name the same folder. Not by their text: git answers with the long form of a path that
    Windows may give in its short 8.3 form (a GitHub runner's temp folder is C:/Users/RUNNER~1/..., git says
    C:/Users/runneradmin/...), and the two strings differ."""
    try:
        return os.path.samefile(a, b)
    except OSError:
        return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))


def checkout_state(deps):
    """A developer's git checkout of ps3recomp against this tree's pin and patch series: ('current', None, stamp),
    ('changed', why, stamp), or ('unknown', why, None) for one prepared before this check existed -- then every
    patch is tried (one that still applies is not in the checkout; why is None when all are in). ('foreign', why,
    None): deps/.git is no repository of its own (git would answer for a repository around it) -- not checked."""
    try:
        top = _git_out(deps, "rev-parse", "--show-toplevel").decode("utf-8", "replace").strip()
    except OSError as e:
        return "foreign", f"not a git checkout ({e})", None
    if not same_dir(top, deps):
        return "foreign", f"its .git is not a repository (git sees {top})", None
    stamp = read_prepared_stamp(deps)
    if stamp is not None:
        if stamp.get("commit") == PS3RECOMP_COMMIT and stamp.get("patches") == patch_digest():
            return "current", None, stamp
        have, want = stamp.get("series") or [], patch_series()
        added = [n for n in want if n not in have]
        gone = [n for n in have if n not in want]
        if stamp.get("commit") != PS3RECOMP_COMMIT:
            why = f"the pinned commit changed ({stamp.get('commit')} -> {PS3RECOMP_COMMIT})"
        elif added or gone:
            why = "the patch series changed" + (f": new {', '.join(added)}" if added else "") \
                + (f"; removed {', '.join(gone)}" if gone else "")
        else:
            why = "a patch of the series was edited"
        return "changed", why, stamp
    missing = []
    for name in patch_series():
        r = subprocess.run(["git", "-c", "core.longpaths=true", "-C", deps, "apply", "--check", "--whitespace=nowarn",
                            os.path.join(PATCH_DIR, name)], capture_output=True)
        if r.returncode == 0:                    # it still applies: the checkout does not have it
            missing.append(name)
    return "unknown", (f"patches missing (at least): {', '.join(missing)}" if missing else None), None


def reprepare_checkout(deps, why, stamp):
    """Prepare the pin + this series afresh (tools/prepare_ps3recomp.py, cloned from the checkout itself, else from
    PS3RECOMP_URL) and put it in the place of `deps`. The old tree is deleted when it is exactly what its stamp says
    was prepared, else kept next to it (it may hold changes of the developer's own)."""
    deps = os.path.abspath(deps)
    new = deps + ".new"
    if os.path.isdir(new):
        rmtree(new)
    base = [PY, os.path.join(ROOT, "tools", "prepare_ps3recomp.py"), "--dest", new, "--commit", PS3RECOMP_COMMIT,
            "--branch", PS3RECOMP_BRANCH, "--patches", PATCH_DIR]
    print(f"  {deps} is out of date: {why}. Preparing ps3recomp {PS3RECOMP_COMMIT} + {len(patch_series())} "
          "patches again.", flush=True)
    try:
        run(base + ["--source", deps])
    except subprocess.CalledProcessError:
        if os.path.isdir(new):
            rmtree(new)
        print("  (it cannot be cloned from the checkout; fetching from the pinned repository)", flush=True)
        try:
            run(base + ["--source", PS3RECOMP_URL])
        except subprocess.CalledProcessError:
            if os.path.isdir(new):
                rmtree(new)
            # (a developer's checkout only -- a release has its vendored copy --, so English, not in the catalogs)
            raise BuildError(f"Could not prepare ps3recomp with the current patch series (tools/prepare_ps3recomp.py, see "
                 f"above); {deps} is unchanged.")
    pristine = False
    if stamp and not stamp.get("adopted"):
        try:
            pristine = tree_digest(deps) == stamp.get("tree")
        except OSError:
            pristine = False
    keep = None
    try:
        if pristine:
            rmtree(deps)
        else:
            keep = deps + time.strftime(".old-%Y%m%d-%H%M%S")
            os.replace(deps, keep)
    except OSError as e:
        rmtree(new)
        raise BuildError(f"Could not move {deps} aside ({e.strerror or e}); close the programs that use files in it and run "
             "the step again.")
    os.replace(new, deps)
    if read_prepared_stamp(deps) is None:
        write_prepared_stamp(deps)
    print("  the old checkout had no changes of its own: removed" if keep is None else
          f"  the old checkout is kept as {keep} (it may hold changes of your own; delete it when it does not)",
          flush=True)


def step_deps(a):
    vend = deps_stamp_ok()
    if vend is True:
        # Also with "Redo every step": the copy is part of the release, there is nothing to fetch again (1.0.0
        # deleted it and tried a git clone, which failed on its read-only .git files: "Access is denied").
        print("  ps3recomp included in this package (patched) -- nothing to fetch")
    elif vend is False:
        fail("The ps3recomp copy in this folder does not match this version of the port. "
             "Download the release again and extract it into an empty folder.")
    elif prereqs.release_folder() and os.name == "nt" and not os.path.isdir(os.path.join(P.deps, ".git")):
        # a release folder without its ps3recomp copy: the zip was not fully extracted -- never clone with Git there
        fail("This folder is incomplete ({folders} missing). Extract the release zip again with \"Extract All\" "
             "into a short path such as {example}, then start T5DR Online.exe from there -- not from inside the "
             "zip.".format(folders=", ".join(prereqs.release_missing()) or os.path.join("deps", "ps3recomp"),
                           example=prereqs.INCOMPLETE_EXAMPLE))
    elif os.path.isdir(os.path.join(P.deps, ".git")) and not a.force:
        # A developer's checkout: "already done" only with the pin and this tree's patch series (1.1.6: the main
        # checkout lacked 0071-0081, and every test and build against it used a stale runtime).
        state, why, stamp = checkout_state(P.deps)
        if state == "current":
            print("  already done")
        elif state == "foreign":
            print(f"  already done ({why}: the patch series is not checked)")
        elif state == "unknown" and why is None:
            note_prepared(P.deps, adopted=True)            # every patch is in: from now on the stamp tells
            print("  already done (every patch of the series is in the checkout)")
        else:
            reprepare_checkout(P.deps, why, stamp)
    else:
        if not shutil.which("git"):
            fail("Git is needed to download ps3recomp (the recompiler). Install Git, or use a release "
                 "zip, which already contains it.")
        if os.path.isdir(P.deps):
            rmtree(P.deps)
        # autocrlf=true on every OS: some patches (0033) carry CRLF in their context lines, written
        # against a Windows checkout, and only apply to a tree that has CRLF line endings.
        run(["git", "-c", "core.longpaths=true", "clone", "-c", "core.autocrlf=true",
             "-b", PS3RECOMP_BRANCH, PS3RECOMP_URL, P.deps])
        run(["git", "-C", P.deps, "checkout", "-q", PS3RECOMP_COMMIT])
        # Our fixes on top of the pinned commit (Windows build gaps and the like).
        patches = PATCH_DIR
        for name in sorted(os.listdir(patches)):
            if name.endswith(".patch"):
                run(["git", "-C", P.deps, "apply", "--whitespace=nowarn", os.path.join(patches, name)])
        note_prepared(P.deps)
    if not prereqs.python_crypto():
        if vend:
            fail("This package's Python is missing pycryptodome. Download the release again.")
        try:
            run([PY, "-m", "pip", "install", "-q", "-r", os.path.join(P.deps, "requirements.txt")], capture=True)
        except subprocess.CalledProcessError as e:
            if "externally-managed-environment" in (e.output or ""):
                fail("This Python refuses pip install (PEP 668; Homebrew's does). Use a virtual environment: "
                     "python3 -m venv .venv && .venv/bin/pip install pycryptodome, then run the tools with "
                     ".venv/bin/python.")
            raise


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


_PROGRAM = {}


def built_program(elf=None):
    """The PROGRAMS entry of the decrypted program at `elf` (default: this build's game/EBOOT.elf), or None when it
    is missing or none of the supported ones. Hashed once per file version."""
    elf = elf or P.elf
    try:
        st = os.stat(elf)
    except OSError:
        return None
    key = (os.path.abspath(elf), st.st_size, st.st_mtime_ns)
    if key not in _PROGRAM:
        _PROGRAM[key] = PROGRAMS.get(sha1(elf))
    return _PROGRAM[key]


def need_program():
    """The supported program this build has decrypted (the steps after `decrypt` follow it)."""
    prog = built_program()
    if prog is None:
        fail("The decrypted game program is missing or not a supported version. Tick \"Redo every step\" and press "
             "BUILD GAME again.")
    return prog


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


def fail_version(ver, prog, want=None):
    """`want`: the supported program of the package's title ID (the US one when not given)."""
    want = want or US_PROGRAM
    fail(f"This package is version {ver} of the game (program content ID {prog or '?'}). The port supports only "
         f"version {want['version']}: {want['name']}, content ID {want['content_ids'][0]}, {want['pkg_size']:,} "
         "bytes. This version cannot be used, whatever the license (.rap).")


def other_package(a):
    """True when the chosen package is another game than the one this output folder holds (its content ID names
    another title ID than the PARAM.SFO taken out before): a US build folder given the EU package, or the other way
    round. Then the steps that keep their output start again from that package (1.1.9)."""
    sfo = os.path.join(P.pkg_dir, "PARAM.SFO")
    if not (a.pkg and os.path.exists(a.pkg) and os.path.exists(sfo)):
        return False
    try:
        cid, tid = pkg_content_id(a.pkg), read_sfo(sfo).get("TITLE_ID")
    except OSError:
        return False
    return bool(cid and tid and tid in TITLE_IDS and tid not in cid)


def step_decrypt(a):
    if other_package(a):
        print("  the chosen package is another version of the game than the one unpacked here: starting from it")
        for stale in (P.unpacked_stamp, os.path.join(P.pkg_dir, "USRDIR", "EBOOT.BIN"),
                      os.path.join(P.pkg_dir, "PARAM.SFO"), P.elf):
            if os.path.exists(stale):
                os.remove(stale)
    if built_program() and not a.force:
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
             f"The port needs {SUPPORTED_TEXT}.")
    s = read_sfo(sfo) if os.path.exists(sfo) else {}
    title, tid, ver = s.get("TITLE", "?"), s.get("TITLE_ID", "?"), sfo_version(s)
    print(f"  PARAM.SFO: {title} / {tid} / version {ver}")
    if tid not in TITLE_IDS:
        fail(f"This package is \"{title}\" ({tid}). The port needs {SUPPORTED_TEXT}.")
    want = program_of(title_id=tid)
    kind = program_kind(eboot)
    prog = self_content_id(eboot) if kind == "self" else None
    if prog:
        print(f"  program content ID: {prog} (its license: {prog}.rap)")
    # Two players had v01.01 (APP_VER 01.01, program UP0700-NPUB30009_00-0000000000000000): their .rap could not
    # decrypt it and the build said the .rap was wrong. The version is what is wrong, and no .rap changes that.
    if ver not in ("?", want["version"]):
        fail_version(ver, prog, want)
    if prog in OTHER_VERSIONS:
        fail_version(OTHER_VERSIONS[prog], prog, want)
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
                if prog in OTHER_VERSIONS:
                    fail_version(OTHER_VERSIONS[prog], prog, want)     # no .rap makes another version usable
                fail("The license (.rap) does not belong to this package. Use the .rap whose name matches "
                     f"the package's content ID ({prog or want['content_ids'][0]}).")
            if a.pkg and os.path.exists(a.pkg) and os.path.getsize(a.pkg) != want["pkg_size"]:
                fail(f"The package is {os.path.getsize(a.pkg):,} bytes, the supported one is {want['pkg_size']:,} "
                     "bytes: the download is incomplete or it is a different file. Download it again.")
            fail("Decrypting the game program failed (see the log above). Tick \"Redo every step\" and press "
                 f"BUILD GAME again; if it fails again, check that the package is {want['pkg_size']:,} bytes.")
    got = sha1(P.elf)
    have = PROGRAMS.get(got)
    if have is None:
        os.remove(P.elf)
        cid = next((l.split("content id", 1)[1].split(",")[0].strip()
                    for l in out.splitlines() if "content id" in l), "?")
        fail(f"This copy is a different version of the game: \"{title}\" version {ver}, content ID {cid} "
             f"(program SHA-1 {got[:12]}...). The port supports only {want['name']}, "
             f"content ID {want['content_ids'][0]}.")
    print(f"  program OK: SHA-1 {got} ({have['title_id']} v{have['version']}, {have['region']})")
    if not have["online"]:
        print(f"  note: {have['title_id']} is another build of the game than the US one -- it plays offline; online "
              "play, the practice tools and the training overlay need the US version (NPUB30009) for now")


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
    try:
        # (ps3recomp patch 0074: every file in 16 MB pieces, a line every 64 MB of a big one, and an incomplete
        # package is named instead of leaving short files behind)
        run([PY, os.path.join(P.tools, "pkg_extract.py"), a.pkg, P.pkg_dir], env=keys_env(), capture=True)
    except subprocess.CalledProcessError as e:
        if "cut short" in (e.output or ""):
            size = (program_of(content_id=pkg_content_id(a.pkg)) or US_PROGRAM)["pkg_size"]
            fail(f"The package is {os.path.getsize(a.pkg):,} bytes, the supported one is {size:,} bytes: the "
                 "download is incomplete or it is a different file. Download it again.")
        raise
    with open(P.unpacked_stamp, "w", encoding="utf-8") as f:   # any file name (cp1252 stopped at "Ł")
        f.write(os.path.basename(a.pkg) + "\n")


def step_vfs(a):
    # The runtime boots <vfs>/PS3_GAME/USRDIR/EBOOT.elf and reads PARAM.SFO
    # beside it. The game itself is a PSN title: it looks for its data under
    # /dev_hdd0/game/NPUB30009/USRDIR/, which run_game.py maps to
    # <vfs>/dev_hdd0 through PS3_HDD0_ROOT.
    # (the EU program reads /dev_hdd0/game/NPEA00019/USRDIR/: each program its own title ID)
    hdd0_usrdir = P.hdd0_usrdir_of(need_program()["title_id"])
    os.makedirs(P.usrdir, exist_ok=True)
    os.makedirs(hdd0_usrdir, exist_ok=True)
    link_or_copy(P.elf, os.path.join(P.usrdir, "EBOOT.elf"))
    link_or_copy(os.path.join(P.pkg_dir, "PARAM.SFO"), os.path.join(P.vfs, "PS3_GAME", "PARAM.SFO"))
    link_or_copy(os.path.join(P.pkg_dir, "PARAM.SFO"), os.path.join(hdd0_usrdir, "..", "PARAM.SFO"))
    for name in sorted(os.listdir(os.path.join(P.pkg_dir, "USRDIR"))):
        if name.upper() != "EBOOT.BIN":
            link_or_copy(os.path.join(P.pkg_dir, "USRDIR", name), os.path.join(hdd0_usrdir, name))
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
    prog = need_program()
    lifter_id = (sha1(lifter) if os.path.exists(lifter) else "") + ("" if regpromo else ":regpromo=off")
    if prog is not US_PROGRAM:          # (a lift of one program is never taken for another's: 1.1.9)
        lifter_id += ":program=" + prog["key"]
    # macOS online (--macos-online): every function src/ detours gets a hook slot (rb_detour.cpp; an
    # arm64 Mac may not patch its own code). The stamp records the list, so a change lifts again.
    hooks = []
    if mac_modules(a):
        hooks = ["--hook-slots", HOOK_SLOTS]
        lifter_id += ":hooks=" + sha1(HOOK_SLOTS)
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
         "--code-end", prog["code_end"], "--max-chunk-lines", "80000",
         "-o", P.recomp] + ([] if regpromo else ["--regpromo", "off"]) + hooks)
    with open(stamp, "w") as f:
        f.write(lifter_id + "\n")


def stamp_program(stamp):
    """The program (PROGRAMS key) whose sound core the SPU step lifted, from its stamp: the US one for a stamp
    without the line or without a stamp (every build before 1.1.9)."""
    try:
        with open(stamp) as f:
            lines = f.read().split()
    except OSError:
        return "us"
    return next((l.split("=", 1)[1] for l in lines if l.startswith("program=")), "us")


def spu_stamp_text(extra):
    """The SPU step's stamp: the core's lift arguments, and for another program than the US one its key."""
    prog = need_program()
    return extra + "\n" + ("" if prog is US_PROGRAM else "program=" + prog["key"] + "\n")


def step_spu(a):
    extra = need_program()["spu_extra"]   # the sound core is the program's own build (PROGRAMS)
    core_done = os.path.exists(os.path.join(P.spu, "spu_workloads.c"))
    jobs_done = os.path.exists(os.path.join(P.spu, "lifted", "jcsignal", "spu_recomp.c"))
    # The core is lifted again when its lift arguments changed (a lift without
    # the stamp predates SPU_CORE_EXTRA_FUNCS).
    stamp = os.path.join(P.spu, ".core_lift_args")
    core_args_ok = False
    if os.path.exists(stamp):
        with open(stamp) as f:
            core_args_ok = f.read().split()[:1] == [extra] and stamp_program(stamp) == need_program()["key"]
    if core_done and jobs_done and core_args_ok and not a.force:
        print("  already done")
        return
    if core_done and not core_args_ok and not a.force and stamp_program(stamp) != need_program()["key"]:
        core_done = False                # another program's sound core (1.1.9): extracted and lifted afresh below
    if core_done and not core_args_ok and not a.force:
        print("  the sound core's lift arguments changed: lifting it again")
        run([PY, os.path.join(P.tools, "build_spu_workloads.py"), "--images", os.path.join(P.spu, "images"),
             "--lifted", os.path.join(P.spu, "lifted"), "--out", os.path.join(P.spu, "spu_workloads.c"),
             "--register-fn", "t5dr_spu_register_all", "--constructor", "--title", "t5dr", "--eboot", P.elf,
             "--relift", "--extra-funcs", extra])
        with open(stamp, "w") as f:
            f.write(spu_stamp_text(extra))
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
             "--extra-funcs", extra])
        with open(stamp, "w") as f:
            f.write(spu_stamp_text(extra))
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


def mac_modules(a):
    """macOS (1.1.9): the src/ modules (practice tools, training, unlocks, direct fight, netplay) are built by
    default -- offline; online play still needs --macos-online (the stamp) and the launcher / T5_NET_MODE.
    --macos-offline leaves them out. Never on Windows (the CMake build there has them always)."""
    return sys.platform == "darwin" and not getattr(a, "macos_offline", False)


def write_stamp(compiler, extra=None):
    prog = built_program() or US_PROGRAM
    keys = {"code_id": code_id(), "elf_sha1": next(h for h, p in PROGRAMS.items() if p is prog),
            "title": prog["title_id"], "version": prog["version"], "region": prog["region"],
            "compiler": compiler, "built": datetime.datetime.now().isoformat(timespec="seconds")}
    if not prog["online"]:
        keys["online"] = False          # BuildInfo.has_online: the lobby client starts no match with this game
    with open(P.stamp, "w") as f:
        json.dump(dict(keys, **(extra or {})), f, indent=1)


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
         "--llvm", llvm] + (["--force"] if a.force else [])
        # the shipped profile names the US program's functions; for another program it would only mislead clang
        + ([] if need_program()["pgo"] else ["--profile", "none"]))
    write_stamp("clang-cl (header-free game DLL) from " + llvm)
    print(f"\nbuilt {P.exe} + t5dr_game.dll")


def compile_unix(a):
    """macOS: CMake + Ninja with the system compiler. The runtime is built from source with the
    game (there is no prebuilt host), draws through ps3recomp's Metal backend and plays through SDL2."""
    cmake, ninja = shutil.which("cmake"), shutil.which("ninja")
    if not (cmake and ninja):
        fail("CMake and Ninja were not found. On macOS: brew install cmake ninja sdl2 glslang spirv-cross")
    modules = mac_modules(a)
    online = modules and bool(getattr(a, "macos_online", False))
    configure = [cmake, "-S", ROOT, "-B", P.cmake, "-G", "Ninja", f"-DCMAKE_MAKE_PROGRAM={ninja}",
                 "-DCMAKE_BUILD_TYPE=Release", f"-DPS3RECOMP_DIR={P.deps}", f"-DRECOMP_DIR={P.recomp}",
                 f"-DSPU_DIR={P.spu}", f"-DPython3_EXECUTABLE={PY}", "-DT5DR_REQUIRE_SHADERS=ON",
                 # (always given: a build folder that was configured with it on keeps it in its cache)
                 f"-DT5DR_MACOS_ONLINE={'ON' if modules else 'OFF'}"]
    try:
        run(configure, capture=True)
    except subprocess.CalledProcessError as e:
        if "T5DR_REQUIRE_SHADERS" in (e.output or ""):
            fail("glslang and spirv-cross were not found; the game's shaders need them. "
                 "On macOS: brew install glslang spirv-cross")
        raise
    run([cmake, "--build", P.cmake])
    cc = subprocess.run(["cc", "--version"], capture_output=True, text=True).stdout.splitlines()
    # "online": whether the lobby client may start a match with this game (it refuses one without): only a
    # build made with --macos-online -- the modules alone (practice tools, unlocks, direct fight) do not
    # make a Mac an online player; the European program never is one (docs/EU.md). "modules": the src/ modules are in. A Windows build writes neither key.
    write_stamp((cc[0] if cc else "cc") + " (CMake)", {"online": online and need_program()["online"], "modules": modules})
    print(f"\nbuilt {P.exe}" + (" (online modules: a test build, docs/MACOS_ONLINE_TEST.md)" if online else
                                 " (offline; practice tools, unlocks, direct fight in)" if modules else
                                 " (the game alone: --macos-offline)"))


def step_shaders(a):
    """1.1.5: the shader warm-up (tools/shader_warmup.py). Never fails the build: whatever happens, the first
    fights build the rest of their shaders as before."""
    if not os.path.exists(P.exe):
        print("  no built game -- skipped")
        return
    cmd = [PY, os.path.join(ROOT, "tools", "shader_warmup.py"), "--out", P.out]
    if a.force:
        cmd.append("--force")
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                encoding="utf-8", errors="replace")
        for line in proc.stdout:
            line = line.rstrip()
            # "already done" on its own line: the launcher marks the step as skipped
            print("  already done" if line.endswith("] already done for this build") else line, flush=True)
        proc.wait(timeout=60)
    except Exception as e:  # noqa: BLE001 -- never fail the build over the warm-up
        print(f"  shader warm-up skipped: {e}", flush=True)


def step_compile(a):
    if sys.platform == "darwin":
        return compile_unix(a)
    if sys.platform != "win32":
        fail("Building the game is supported on Windows and macOS only.")
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
    if os.path.exists(PGO_PROFILE) and need_program()["pgo"]:   # (the profile is the US program's)
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
    # First of all: an older Python got through keys/decrypt/unpack and stopped only in the lift (ps3recomp's
    # elf_parser.py: `int | None`, TypeError) -- the owner's Mac, system python3 3.9.
    problem = prereqs.python_problem()
    if problem:
        print(f"ERROR: {problem}", file=sys.stderr, flush=True)
        sys.exit(2)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pkg", help="the PSN package (.pkg)")
    ap.add_argument("--rap", help="the license (.rap)")
    ap.add_argument("--out", default=ROOT, help="output root for game/, build/, keys/ (default: the repository)")
    ap.add_argument("--deps", help="ps3recomp checkout to use (default: deps/ps3recomp)")
    ap.add_argument("--steps", nargs="+", choices=STEPS, default=DEFAULT_STEPS)
    ap.add_argument("--warmup", action="store_true",
                    help="after the build, play a few hidden fights once so the first real ones do not stutter "
                         "(tools/shader_warmup.py; never fails the build)")
    ap.add_argument("--force", action="store_true", help="redo steps whose output exists")
    ap.add_argument("--code-id", action="store_true", help="print the code ID of this version and exit")
    ap.add_argument("--full-compile", action="store_true",
                    help="compile everything with CMake + Visual Studio even when a prebuilt runtime is present")
    ap.add_argument("--macos-offline", action="store_true",
                    help="macOS: leave the src/ modules out (practice tools, training, unlocks, direct fight, "
                         "netplay) -- the game alone, as builds before 1.1.9")
    ap.add_argument("--macos-online", action="store_true",
                    help="macOS: build the online modules too (netplay, rollback, direct fight) -- a test build "
                         "until a Mac-vs-PC match is proven in sync (docs/MACOS_ONLINE_TEST.md)")
    a = ap.parse_args()
    if (a.macos_online or a.macos_offline) and sys.platform != "darwin":
        ap.error("--macos-online / --macos-offline are for macOS (a Windows build always has the modules)")
    if a.macos_online and a.macos_offline:
        ap.error("--macos-online and --macos-offline exclude each other")
    if a.code_id:
        print(code_id())
        return
    if a.warmup and "shaders" not in a.steps:
        a.steps = list(a.steps) + ["shaders"]
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
