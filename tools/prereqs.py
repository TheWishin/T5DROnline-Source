#!/usr/bin/env python3
"""Find the tools the build needs on this PC, and say how to get the missing ones.

    python tools/prereqs.py [--json]

Used by tools/build_game.py (compile step) and by the launcher's Build tab.
Nothing here installs anything; `install_command()` only returns the winget
command line the launcher runs after the player agreed to it.
"""
import glob
import json
import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PF = os.environ.get("ProgramFiles", r"C:\Program Files")
PF86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
VSWHERE = os.path.join(PF86, "Microsoft Visual Studio", "Installer", "vswhere.exe")
NO_WINDOW = 0x08000000 if os.name == "nt" else 0     # CREATE_NO_WINDOW

# Smallest Visual Studio Build Tools selection the compile step needs: the
# MSVC x64 toolset (C/C++ runtime headers and libraries), the Windows SDK
# (Windows/Direct3D 12 headers and import libraries), CMake + Ninja, and
# Microsoft's own build of clang-cl. No IDE, no "recommended" extras.
VS_COMPONENTS = [
    "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
    "Microsoft.VisualStudio.Component.Windows11SDK.26100",
    "Microsoft.VisualStudio.Component.VC.CMake.Project",
    "Microsoft.VisualStudio.Component.VC.Llvm.Clang",
]


def _run(cmd, timeout=20):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, creationflags=NO_WINDOW)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except (OSError, subprocess.SubprocessError) as e:
        return -1, str(e)


def vs_install():
    """Path of the newest Visual Studio / Build Tools with the x64 C++ toolset, or None."""
    if not os.path.exists(VSWHERE):
        return None
    rc, out = _run([VSWHERE, "-latest", "-products", "*", "-requires",
                    "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-property", "installationPath"])
    path = out.strip().splitlines()[0].strip() if rc == 0 and out.strip() else ""
    return path if path and os.path.isdir(path) else None


def vcvars():
    vs = vs_install()
    bat = os.path.join(vs, "VC", "Auxiliary", "Build", "vcvars64.bat") if vs else None
    return bat if bat and os.path.exists(bat) else None


def windows_sdk():
    """Newest Windows 10/11 SDK that has the Direct3D 12 headers, as (version, dir) or None."""
    base = os.path.join(PF86, "Windows Kits", "10", "Include")
    found = []
    for d in glob.glob(os.path.join(base, "10.*")):
        if os.path.exists(os.path.join(d, "um", "d3d12.h")) and os.path.exists(os.path.join(d, "ucrt", "stdio.h")):
            found.append((tuple(int(x) for x in os.path.basename(d).split(".")), d))
    if not found:
        return None
    ver, d = max(found)
    return ".".join(map(str, ver)), d


def _clang_version(exe):
    rc, out = _run([exe, "--version"])
    m = re.search(r"clang version (\d+)\.(\d+)", out)
    return (int(m.group(1)), int(m.group(2))) if rc == 0 and m else None


def clang_cl():
    """(path, (major, minor)) of the clang-cl to use, or None. Prefers a full LLVM install."""
    cands = [os.path.join(ROOT, "toolchain", "llvm", "bin", "clang-cl.exe"),
             shutil.which("clang-cl"),
             os.path.join(PF, "LLVM", "bin", "clang-cl.exe")]
    vs = vs_install()
    if vs:
        cands.append(os.path.join(vs, "VC", "Tools", "Llvm", "x64", "bin", "clang-cl.exe"))
    for c in cands:
        if c and os.path.exists(c):
            v = _clang_version(c)
            if v and v[0] >= 16:
                return c, v
    return None


def prebuilt_host():
    """True for a release whose runtime is precompiled (runtime/t5dr.exe + t5dr.lib): the
    player's PC then compiles only the game DLL, with clang-cl + lld-link alone."""
    return all(os.path.exists(os.path.join(ROOT, "runtime", n)) for n in ("t5dr.exe", "t5dr.lib"))


def portable_llvm():
    """Folder holding clang-cl.exe + lld-link.exe for the game DLL: the release's own copy first."""
    for d in (os.path.join(ROOT, "toolchain", "llvm", "bin"), os.path.join(PF, "LLVM", "bin")):
        if all(os.path.exists(os.path.join(d, n)) for n in ("clang-cl.exe", "lld-link.exe")):
            return d
    return None


def cmake_ninja():
    """(cmake, ninja) paths: on PATH, else the copies Visual Studio ships with its CMake component."""
    cm, nj = shutil.which("cmake"), shutil.which("ninja")
    vs = vs_install()
    if vs:
        ext = os.path.join(vs, "Common7", "IDE", "CommonExtensions", "Microsoft", "CMake")
        cm = cm or (os.path.join(ext, "CMake", "bin", "cmake.exe")
                    if os.path.exists(os.path.join(ext, "CMake", "bin", "cmake.exe")) else None)
        nj = nj or (os.path.join(ext, "Ninja", "ninja.exe")
                    if os.path.exists(os.path.join(ext, "Ninja", "ninja.exe")) else None)
    return cm, nj


MIN_PYTHON = (3, 10)      # ps3recomp's tools use 3.10 syntax (`int | None`): 3.9 fails only in the lift step


def python_problem(version_info=None, executable=None):
    """None when this Python is new enough, else the sentence that says what to do (build_game.py stops with it
    before any step; the Python line below shows it)."""
    v = tuple(version_info or sys.version_info)
    if v[:2] >= MIN_PYTHON:
        return None
    return (f"T5DR needs Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} or newer; this is {v[0]}.{v[1]} at "
            f"{executable or sys.executable}. On macOS: brew install python@3.12 and make the venv with python3.12 "
            "(python3.12 -m venv .venv).")


def python_crypto():
    try:
        import Crypto.Cipher.AES  # noqa: F401  (pycryptodome)
        return True
    except ImportError:
        return False


def ps3recomp_source():
    """'vendored' (release zip), 'git' (developer checkout), or None (needs Git to fetch)."""
    d = os.path.join(ROOT, "deps", "ps3recomp")
    if os.path.exists(os.path.join(d, ".t5dr-vendored.json")):
        return "vendored"
    if os.path.isdir(os.path.join(d, ".git")):
        return "git"
    return None


INCOMPLETE_EXAMPLE = r"C:\T5DR"       # a short path to extract the release zip into again


def release_folder(root=None):
    """This folder came from a release zip (its release.json), not from a developer's checkout."""
    return os.path.isfile(os.path.join(root or ROOT, "release.json"))


def release_missing(root=None):
    """The parts a release zip ships that this folder lacks -- an "Extract All" cut short, or files taken out of the
    zip one by one or run from inside it: e.g. ["deps\\ps3recomp", "toolchain\\llvm", "runtime", "python"]; [] for a
    complete release and for a developer's checkout. Git, Visual Studio and the like cannot replace them."""
    root = root or ROOT
    if not release_folder(root) or os.name != "nt":
        return []
    out = []
    if not os.path.exists(os.path.join(root, "deps", "ps3recomp", ".t5dr-vendored.json")):
        out.append(os.path.join("deps", "ps3recomp"))
    llvm = os.path.join(root, "toolchain", "llvm", "bin")
    if not all(os.path.exists(os.path.join(llvm, n)) for n in ("clang-cl.exe", "lld-link.exe")):
        out.append(os.path.join("toolchain", "llvm"))
    if not all(os.path.exists(os.path.join(root, "runtime", n)) for n in ("t5dr.exe", "t5dr.lib")):
        out.append("runtime")
    if not os.path.exists(os.path.join(root, "python", "python.exe")):
        out.append("python")
    return out


def check():
    """List of dicts: id, name, ok, detail, needed_for, install (winget id or None)."""
    items = []

    def add(id_, name, ok, detail, needed_for, install=None):
        items.append(dict(id=id_, name=name, ok=bool(ok), detail=detail, needed_for=needed_for, install=install))

    add("python", "Python 3.10+", python_problem() is None,                  # (MIN_PYTHON)
        python_problem() or f"{sys.version.split()[0]} at {sys.executable}", "all steps")
    add("pycryptodome", "pycryptodome (Python AES)", python_crypto(),
        "installed" if python_crypto() else "missing -- pip install pycryptodome", "unpack, decrypt")
    src = ps3recomp_source()
    release = release_folder() and os.name == "nt"
    if release:
        # A release ships ps3recomp, the compiler and the runtime: a missing one means the zip was not fully
        # extracted. Never offer Git there (1.1.6: a player pressed "Install missing..." for it; nothing changed).
        vendored = src == "vendored"
        add("ps3recomp", "ps3recomp source", vendored,
            "included in this package" if vendored else
            "missing from this folder -- extract the release zip again", "lift, compile")
    else:
        git = shutil.which("git")
        add("ps3recomp", "ps3recomp source", src or git,
            {"vendored": "included in this package", "git": "git checkout in deps/"}.get(
                src, "not present -- will be downloaded with Git" if git else "not present and Git is missing"),
            "lift, compile", None if src or git else "Git.Git")
    if prebuilt_host() or release:
        # (a release folder: never Visual Studio either -- its runtime and compiler are in the zip)
        llvm = portable_llvm()
        add("runtime", "Game runtime (t5dr.exe)", prebuilt_host(),
            "precompiled, included in this package" if prebuilt_host() else
            "missing from this folder -- extract the release zip again", "compile")
        add("llvm", "clang-cl + lld-link", llvm,
            ("included in this package" if llvm and llvm.startswith(ROOT) else llvm) if llvm
            else "missing from toolchain\\llvm -- extract the release zip again", "compile")
        return items
    vs = vs_install()
    add("msvc", "C++ build tools (MSVC x64)", vs, vs or "not found", "compile",
        None if vs else "Microsoft.VisualStudio.2022.BuildTools")
    sdk = windows_sdk()
    add("sdk", "Windows SDK (Direct3D 12)", sdk, f"{sdk[0]}" if sdk else "not found", "compile",
        None if sdk else "Microsoft.VisualStudio.2022.BuildTools")
    cl = clang_cl()
    add("clang", "clang-cl 16+ (LLVM)", cl, f"{cl[1][0]}.{cl[1][1]} at {cl[0]}" if cl else "not found", "compile",
        None if cl else "Microsoft.VisualStudio.2022.BuildTools")
    cm, nj = cmake_ninja()
    add("cmake", "CMake + Ninja", cm and nj,
        f"{cm} / {nj}" if cm and nj else "missing " + " and ".join(n for n, p in (("CMake", cm), ("Ninja", nj)) if not p),
        "compile", None if cm and nj else "Microsoft.VisualStudio.2022.BuildTools")
    return items


def install_command(winget_id):
    """The winget command line for one missing prerequisite (run only after the player agreed)."""
    base = ["winget", "install", "--exact", "--id", winget_id, "--source", "winget",
            "--accept-package-agreements", "--accept-source-agreements"]
    if winget_id == "Microsoft.VisualStudio.2022.BuildTools":
        vs = vs_install()
        if vs:   # already there, only components missing: modify the existing install
            setup = os.path.join(PF86, "Microsoft Visual Studio", "Installer", "setup.exe")
            return [setup, "modify", "--installPath", vs, "--passive", "--norestart"] + \
                   sum((["--add", c] for c in VS_COMPONENTS), [])
        return base + ["--override", "--passive --wait --norestart " +
                       " ".join("--add " + c for c in VS_COMPONENTS)]
    return base


def main():
    items = check()
    if "--json" in sys.argv:
        print(json.dumps(items, indent=1))
        return
    for it in items:
        print(f"{'ok ' if it['ok'] else 'MISSING'}  {it['name']:<30} {it['detail']}")
    if not all(it["ok"] for it in items):
        sys.exit(1)


if __name__ == "__main__":
    main()
