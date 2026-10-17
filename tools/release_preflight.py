#!/usr/bin/env python3
"""Run what the release workflow runs, on this PC, before pushing a release tag.

    python tools/release_preflight.py --version 0.1.7-preview [--llvm DIR] [--keep]

The release job (.github/workflows/release.yml) fails after ~5 minutes on the runner if the
changelog section, the binary checks or the zip smoke test fail; this finds the same problems
here first (0.1.5-preview's first run stopped at the binary check). Steps, in order:

  1. CHANGELOG.md has a section for the version (tools/release_notes.py --check)
  2. nothing game-derived in the index or the commits since the last tag (check_no_game_data.py)
  3. ps3recomp at the pin + the patch series, into a fresh folder (prepare_ps3recomp.py)
  4. the player zip, exactly as the workflow builds it (package_release.py --release), which also
     runs tools/check_binaries.py and the zip scan
  5. the zip's smoke test with a bare PATH (smoke_release.py --no-gui)
  6. the repo's unit tests (python -m unittest discover -s tests)

Needs the MSVC environment for step 4 (it re-runs itself inside vcvars64.bat when cl/link are
not on PATH). Exit code 0 = safe to tag. Work files go to build/preflight/ (removed unless --keep).
"""
import argparse
import os
import shutil
import stat
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VCVARS = r"C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"


def rmtree(path):
    """shutil.rmtree that also removes read-only files (git objects in the ps3recomp clone)."""
    def onerror(func, p, _exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)
    if os.path.exists(path):
        shutil.rmtree(path, onerror=onerror)


def step(title, cmd, **kw):
    print(f"\n== {title}\n   > {' '.join(cmd) if isinstance(cmd, list) else cmd}", flush=True)
    r = subprocess.run(cmd, cwd=ROOT, **kw)
    if r.returncode != 0:
        print(f"\nPREFLIGHT FAILED at: {title} (exit {r.returncode})", flush=True)
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--version", required=True, help="e.g. 0.1.7-preview (no leading v)")
    ap.add_argument("--llvm", default=os.path.join(ROOT, "build", "rd", "llvm"),
                    help="unpacked LLVM (tools/fetch_llvm.py --dest DIR); default build/rd/llvm")
    ap.add_argument("--keep", action="store_true", help="keep build/preflight/")
    a = ap.parse_args()
    ver = a.version[1:] if a.version.startswith("v") else a.version
    py = sys.executable
    base = os.path.join(ROOT, "build", "preflight")
    for old in (os.listdir(base) if os.path.isdir(base) else []):   # earlier runs
        rmtree(os.path.join(base, old))
    work = os.path.join(base, f"{ver}-{time.strftime('%H%M%S')}")
    llvm = os.path.abspath(a.llvm)
    if not os.path.isfile(os.path.join(llvm, "bin", "clang-cl.exe")):
        sys.exit(f"no LLVM at {llvm}: run python tools/fetch_llvm.py --dest {llvm}")
    os.makedirs(work)

    step("1. changelog section", [py, "tools/release_notes.py", "--version", ver, "--check"])
    step("2a. guard: index", [py, "tools/check_no_game_data.py"])
    last = subprocess.run(["git", "describe", "--tags", "--abbrev=0"], cwd=ROOT, capture_output=True,
                          text=True).stdout.strip()
    step("2b. guard: commits since " + (last or "the start"),
         [py, "tools/check_no_game_data.py", "--history", f"{last}..HEAD" if last else "HEAD"])
    ps3 = os.path.join(work, "ps3recomp")
    step("3. ps3recomp + patch series", [py, "tools/prepare_ps3recomp.py", "--dest", ps3])
    dist = os.path.join(work, "dist")
    pkg = [py, "tools/package_release.py", "--release", "--version", ver, "--llvm", llvm, "--ps3recomp", ps3,
           "--out", dist]
    if shutil.which("link") and shutil.which("cl"):
        step("4. player zip (package_release --release)", pkg)
    else:
        step("4. player zip (package_release --release, inside vcvars64)",
             f'cmd /c ""{VCVARS}" >nul 2>&1 && {subprocess.list2cmdline(pkg)}"', shell=True)
    zipf = os.path.join(dist, f"T5DR-Online-{ver}.zip")
    step("5. zip smoke test (bare PATH)", [py, "tools/smoke_release.py", zipf, "--version", ver,
                                           "--work", os.path.join(work, "smoke"), "--no-gui"])
    step("6. unit tests", [py, "-m", "unittest", "discover", "-s", "tests"])
    print(f"\nPREFLIGHT OK for {ver}: safe to tag v{ver}", flush=True)
    if not a.keep:
        rmtree(work)


if __name__ == "__main__":
    main()
