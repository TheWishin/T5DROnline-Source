#!/usr/bin/env python3
"""Check out ps3recomp at the commit tools/build_game.py pins and apply
patches/ps3recomp/*.patch in name order -- the tree build_game.py's `deps`
step builds against, in a directory of your choice.

    python tools/prepare_ps3recomp.py --dest DIR [--source URL_OR_PATH] [--replace]

CI uses it (.github/workflows/ci.yml); use it yourself to check that the whole
series still applies on a fresh tree before committing a new patch:

    python tools/prepare_ps3recomp.py --dest build/<you>/patchcheck --source deps/ps3recomp --replace

It stops at the first patch that does not apply, names it, and shows git's
reason. The pin (URL, branch, commit) is read from tools/build_game.py, so
there is one place to change it.
"""
import argparse
import importlib.util
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def build_game():
    """tools/build_game.py as a module, without running it (the pin, the series stamp)."""
    spec = importlib.util.spec_from_file_location("build_game", os.path.join(ROOT, "tools", "build_game.py"))
    bg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bg)
    return bg


def pin():
    """(url, branch, commit) from tools/build_game.py."""
    bg = build_game()
    return bg.PS3RECOMP_URL, bg.PS3RECOMP_BRANCH, bg.PS3RECOMP_COMMIT


def git(*args, check=True, capture=False):
    cmd = ["git", "-c", "core.longpaths=true", *args]
    if capture:
        return subprocess.run(cmd, capture_output=True, text=True)
    print("  > " + " ".join(cmd), flush=True)
    return subprocess.run(cmd, check=check)


def fail(msg, patch=None):
    # One line GitHub turns into an annotation on the patch, plus plain text.
    if os.environ.get("GITHUB_ACTIONS") == "true":
        try:
            rel = os.path.relpath(patch, ROOT).replace(os.sep, "/") if patch else ""
        except ValueError:      # another drive
            rel = ""
        where = f" file={rel}" if rel and not rel.startswith("..") else ""
        print(f"::error{where}::{msg.splitlines()[0]}", flush=True)
    sys.exit(f"[prepare_ps3recomp] {msg}")


def is_url(s):
    return "://" in s or s.startswith("git@")


def main():
    url, branch, commit = pin()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dest", required=True, help="directory to check ps3recomp out into (must not exist)")
    ap.add_argument("--source", default=url, help=f"clone from here instead of {url} (a URL or a local clone)")
    ap.add_argument("--branch", default=branch, help=f"branch the pinned commit lives on (default {branch})")
    ap.add_argument("--commit", default=commit, help=f"commit to check out (default: the pin, {commit})")
    ap.add_argument("--patches", default=os.path.join(ROOT, "patches", "ps3recomp"), help="patch directory")
    ap.add_argument("--replace", action="store_true", help="delete --dest first if it exists")
    a = ap.parse_args()

    dest = os.path.abspath(a.dest)
    if os.path.exists(dest):
        if not a.replace:
            fail(f"{dest} exists; pass --replace to start over")
        shutil.rmtree(dest)

    # autocrlf=true on every OS: some patches (0033) carry CRLF in their context lines and only
    # apply to a tree with CRLF line endings, as a Windows checkout has.
    clone = ["clone", "-q", "--no-checkout", "-c", "core.autocrlf=true"]
    if is_url(a.source):
        # Full history of the branch, blobs on demand: a few MB instead of the
        # whole object store, and the pinned commit is reachable either way.
        clone += ["--filter=blob:none", "-b", a.branch]
    git(*clone, a.source, dest)
    if git("-C", dest, "checkout", "-q", "--detach", a.commit, check=False).returncode != 0:
        fail(f"pinned commit {a.commit} is not in {a.source} (branch {a.branch}) -- was it force-pushed away?")
    head = git("-C", dest, "rev-parse", "HEAD", capture=True).stdout.strip()
    print(f"ps3recomp {head} ({a.branch} @ {a.commit})", flush=True)

    patches = sorted(n for n in os.listdir(a.patches) if n.endswith(".patch"))
    if not patches:
        fail(f"no patches in {a.patches}")
    done = []
    for name in patches:
        path = os.path.join(a.patches, name)
        chk = git("-C", dest, "apply", "--check", "--verbose", "--whitespace=nowarn", path, capture=True)
        if chk.returncode != 0:
            base = f"{a.commit}" + (" + " + ", ".join(done) if done else "")
            fail(f"patch {name} does not apply on {base}\n\n{chk.stdout}{chk.stderr}", patch=path)
        git("-C", dest, "apply", "--whitespace=nowarn", path)
        print(f"applied {name}", flush=True)
        done.append(name)

    changed = git("-C", dest, "status", "--short", capture=True).stdout
    # What this tree is (.git/t5dr-prepared.json): build_game.py's deps step re-prepares a checkout whose series
    # is not the repository's any more.
    build_game().write_prepared_stamp(dest, commit=a.commit, patches=a.patches)
    print(f"\n{len(done)} patch(es) applied, {len(changed.splitlines())} file(s) changed in {dest}")


if __name__ == "__main__":
    main()
