#!/usr/bin/env python3
"""Release notes for a version: its section of CHANGELOG.md plus the facts of the build.

    python tools/release_notes.py --version 0.1.0-preview --check
    python tools/release_notes.py --version 0.1.0-preview --release-json dist/T5DR-Online-0.1.0-preview/release.json
                                  --sums dist/SHA256SUMS --out dist/RELEASE_NOTES.md [--allow-missing]

The section is the level-2 heading that starts with the version (a leading "v" and
square brackets are fine) and everything up to the next level-2 heading:

    ## v0.1.0-preview (2026-10-20)
    ## [0.1.0] - 2026-11-02
    ## 0.2.0-rc.1

"0.1.0" does not match a "0.1.0-preview" heading. --check only says whether the
section exists and is not empty (exit 1 if not); the release workflow runs it before
the long build so a tag without notes fails in seconds. --allow-missing (dry runs)
writes a placeholder instead of failing.
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def find_section(text, version):
    """Body of the CHANGELOG section for version (str), or None when there is no heading."""
    v = version[1:] if version[:1] in ("v", "V") else version
    head = re.compile(r"^##\s+\[?[vV]?" + re.escape(v) + r"(?![0-9A-Za-z.\-])")
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if head.match(line):
            body = []
            for line2 in lines[i + 1:]:
                if re.match(r"^#{1,2}\s", line2):
                    break
                body.append(line2)
            return "\n".join(body).strip("\n").rstrip()
    return None


def footer(version, info, sums, repo, run_url):
    name = f"T5DR-Online-{version}.zip"
    out = ["", "---", "", "### Download", "",
           f"**`{name}`** below. Unpack it into a folder of its own, start **`T5DR Online.exe`**, pick "
           "your own `.pkg` and `.rap` (Tekken 5: Dark Resurrection Online, PS3 PSN, NPUB30009 "
           "v01.00) and click **BUILD GAME**. Nothing else needs to be installed.",
           "",
           "The zip contains **no part of the game** -- no game files, no translated game code, no "
           "keys. It was scanned for all three before it was published.",
           ""]
    if "-" in version:
        out += ["This is a **pre-release**: expect bugs, and please report them.", ""]
    rows = []
    if sums:
        for line in sums.splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1].lstrip("*") == name:
                rows.append(("SHA-256", f"`{parts[0]}`"))
    if info:
        if info.get("llvm"):
            rows.append(("Compiler in the zip", f"LLVM {info['llvm']} (clang-cl, lld-link), "
                                                "used on your PC to build the game code"))
        if info.get("python"):
            rows.append(("Python in the zip", f"CPython {info['python']} (private copy, with tkinter and pycryptodome)"))
        if info.get("ps3recomp"):
            n = len(info.get("patches") or [])
            rows.append(("ps3recomp", f"`{info['ps3recomp']}`" + (f" + {n} patches from `patches/ps3recomp`" if n else "")))
        if info.get("signed"):
            files = ", ".join(f"`{f}`" for f in info["signed"])
            rows.append(("Code signing", f"{files} carry a digital signature (right-click the file, "
                                         "Properties, Digital Signatures)"))
        if info.get("code_id"):
            rows.append(("Code ID", f"`{info['code_id']}` (the launcher asks for a rebuild when this changes)"))
        commit = (info.get("commit") or "").replace("-dirty", " (with local changes)")
        if commit:
            link = f"[`{commit[:12]}`](https://github.com/{repo}/commit/{commit[:40]})" if repo and "(" not in commit \
                else f"`{commit}`"
            rows.append(("Source", link))
    if run_url:
        rows.append(("Built by", f"[GitHub Actions run]({run_url})"))
    if rows:
        out += ["| | |", "|---|---|"] + [f"| {k} | {v} |" for k, v in rows] + [""]
    out += ["Check the download: `certutil -hashfile " + name + " SHA256` (Windows) or "
            "`sha256sum -c SHA256SUMS`.", ""]
    return "\n".join(out)


def display_path(path):
    """`path` relative to the repository for messages and annotations. On Windows a
    file on another drive has no relative path (os.path.relpath raises ValueError:
    a CI runner has the checkout on D: and the temp folder on C:), so it is shown whole."""
    try:
        return os.path.relpath(path, ROOT).replace(os.sep, "/")
    except ValueError:
        return path.replace(os.sep, "/")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", required=True)
    ap.add_argument("--changelog", default=os.path.join(ROOT, "CHANGELOG.md"))
    ap.add_argument("--check", action="store_true", help="only check that the section exists and is not empty")
    ap.add_argument("--allow-missing", action="store_true", help="placeholder instead of an error (dry runs)")
    ap.add_argument("--release-json", help="release.json of the packaged folder")
    ap.add_argument("--sums", help="SHA256SUMS written by package_release.py")
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""), help="owner/name for commit links")
    ap.add_argument("--out", help="write the notes here (default: stdout)")
    a = ap.parse_args()
    version = a.version[1:] if a.version[:1] in ("v", "V") else a.version

    with open(a.changelog, encoding="utf-8") as f:
        body = find_section(f.read(), version)
    rel = display_path(a.changelog)
    if not body:
        why = "is empty" if body == "" else "is missing"
        msg = (f"{rel}: the section for {version} {why} -- add a heading '## v{version} (YYYY-MM-DD)' "
               "with the changes above the older entries (docs/RELEASING.md)")
        if not a.allow_missing:
            if os.environ.get("GITHUB_ACTIONS") == "true":
                print(f"::error file={rel}::{msg}", flush=True)
            sys.exit(msg)
        print(f"warning: {msg}", file=sys.stderr)
        if os.environ.get("GITHUB_ACTIONS") == "true":
            print(f"::warning file={rel}::{msg}", flush=True)
        if a.check:
            return
        body = f"_Dry run: {rel} has no section for {version} yet._"
    if a.check:
        print(f"{rel}: section for {version} found ({len(body.splitlines())} lines)")
        return

    info = None
    if a.release_json:
        with open(a.release_json, encoding="utf-8") as f:
            info = json.load(f)
    sums = None
    if a.sums:
        with open(a.sums, encoding="utf-8") as f:
            sums = f.read()
    run_url = ""
    if os.environ.get("GITHUB_RUN_ID") and a.repo:
        run_url = f"{os.environ.get('GITHUB_SERVER_URL', 'https://github.com')}/{a.repo}/actions/runs/{os.environ['GITHUB_RUN_ID']}"
    notes = body + "\n" + footer(version, info, sums, a.repo, run_url)
    if a.out:
        with open(a.out, "w", encoding="utf-8", newline="\n") as f:
            f.write(notes)
        print(f"wrote {a.out} ({len(notes.splitlines())} lines)")
    else:
        sys.stdout.write(notes)


if __name__ == "__main__":
    main()
