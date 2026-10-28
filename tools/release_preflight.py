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
  5. the zip's smoke test with a bare PATH, the launcher started with a package chosen (smoke_release.py)
  6. the repo's unit tests (python -m unittest discover -s tests), PS3RECOMP_DIR = step 3's tree
  7. ready for players: the changelog section has a release date in its heading and no HTML comments
     (placeholders, notes for the release; the launcher's update offer shows the notes as plain text,
     comments included, and the zip ships CHANGELOG.md), and the release line of README.md and
     docs/README.de.md names this version. Listed after step 1 already, failed only here, so a dry run
     with placeholders still runs every other step.

Needs the MSVC environment for step 4 (it re-runs itself inside vcvars64.bat when cl/link are
not on PATH). Exit code 0 = safe to tag. Work files go to build/preflight/ (removed unless --keep).
"""
import argparse
import os
import re
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


def changelog_leftovers(ver, text):
    """What in the CHANGELOG section of `ver` must not reach players: a heading without the release date
    (YYYY-MM-DD) and every HTML comment. [] when the section is ready (or missing: step 1 reports that)."""
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    from release_notes import find_section
    head = re.search(r"^##\s+\[?[vV]?" + re.escape(ver) + r"(?![0-9A-Za-z.\-]).*$", text, re.M)
    body = find_section(text, ver)
    if head is None or body is None:
        return []
    out = []
    if not re.search(r"\b\d{4}-\d{2}-\d{2}\b", head.group(0)):
        out.append(f"heading without a release date: {head.group(0).strip()}")
    for c in re.findall(r"<!--(.*?)(?:-->|\Z)", body, re.S):
        c = " ".join(c.split())
        out.append("comment: <!-- " + (c[:100] + " ..." if len(c) > 100 else c) + " -->")
    return out


def readme_leftovers(ver, root=ROOT):
    """The READMEs (README.md, docs/README.de.md) whose release line ("**Release X (date).**" and the zip name
    T5DR-Online-X.zip) does not name `ver` yet (docs/RELEASING.md "Cutting a release", step 2)."""
    out = []
    for rel in ("README.md", "docs/README.de.md"):
        try:
            with open(os.path.join(root, *rel.split("/")), encoding="utf-8") as f:
                text = f.read()
        except OSError:
            continue
        named = (re.findall(r"^\*\*Release ([0-9][\w.\-]*) ", text, re.M)
                 + re.findall(r"T5DR-Online-([0-9][\w.\-]*)\.zip", text))
        wrong = sorted({v for v in named if v != ver})
        if wrong or not named:
            out.append(f"{rel}: the release line names {', '.join(wrong) or 'no version'}, not {ver}")
    return out


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

    # The tag builds what is committed: an uncommitted or untracked file passes the index checks
    # here and fails on the runner (1.0.0's first run: a new icon the guard had not seen).
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout
    dirty = [l for l in dirty.splitlines() if l.strip() and not l[3:].startswith("runs/")]
    if dirty:
        print("PREFLIGHT FAILED: commit everything first; uncommitted or untracked:\n  " + "\n  ".join(dirty[:20]))
        sys.exit(1)
    step("1. changelog section", [py, "tools/release_notes.py", "--version", ver, "--check"])
    with open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8") as f:
        leftovers = changelog_leftovers(ver, f.read()) + readme_leftovers(ver)
    if leftovers:
        print("   not ready for players yet (step 7 fails on it):\n     " + "\n     ".join(leftovers), flush=True)
    step("2a. guard: index", [py, "tools/check_no_game_data.py"])
    # The last release tag (v...), not any tag: a helper tag on an integration branch (pre-gthread, ...) made this
    # check only the commits since that helper (1.1.3 prep: 71 files instead of everything since v1.1.2).
    last = subprocess.run(["git", "describe", "--tags", "--abbrev=0", "--match", "v[0-9]*"], cwd=ROOT,
                          capture_output=True, text=True).stdout.strip()
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
                                           "--work", os.path.join(work, "smoke")])     # with the GUI checks (1.1.5)
    # against the tree of step 3 (the zip's), not deps/ps3recomp of this checkout, which may hold an older series
    step("6. unit tests", [py, "-m", "unittest", "discover", "-s", "tests"], env=dict(os.environ, PS3RECOMP_DIR=ps3))
    print("\n== 7. ready for players (changelog: release date, no HTML comments; README release lines)", flush=True)
    if leftovers:
        print("   " + "\n   ".join(leftovers))
        print("\nPREFLIGHT FAILED at: 7. ready for players (date the heading, fill in or remove every comment, "
              "put the version into both README release lines)", flush=True)
        sys.exit(1)
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import release_sign                 # the publish job signs SHA256SUMS (RELEASING.md "Release signature")
    keys = release_sign.updater_keys()
    if keys:
        ids = ", ".join(release_sign.release_sig.key_id(bytes.fromhex(k)) for k in keys)
        print(f"\n   release signature: this launcher trusts key {ids}; the publish job needs the secret "
              f"{release_sign.KEY_ENV} in the 'release' environment (or it stops before publishing)", flush=True)
    print(f"\nPREFLIGHT OK for {ver}: safe to tag v{ver}", flush=True)
    if not a.keep:
        rmtree(work)


if __name__ == "__main__":
    main()
