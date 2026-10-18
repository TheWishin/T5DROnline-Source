#!/usr/bin/env python3
"""List every program (PE file) in a release folder or zip and scan each with the local Windows Defender.

    python tools/av_local_scan.py FOLDER_OR_ZIP [--no-scan] [--md FILE] [--also FILE ...]

Nothing is uploaded and no Defender setting is changed: it runs
`MpCmdRun.exe -Scan -ScanType 3 -File <path> -DisableRemediation` (a custom scan that only reports) on
each file. Defender itself may still ask Microsoft's cloud about a file, if the PC's cloud protection
is on (Windows Security -> Virus & threat protection -> Manage settings); this tool leaves that alone.

Groups in the table: ours (T5DR Online.exe, runtime/t5dr.exe), python (the bundled CPython, signed by the
Python Software Foundation), pycryptodome (unsigned wheels), llvm (clang-cl, lld-link: unsigned),
other. A zip is unpacked into a scratch folder first (removed after).
"""
import argparse
import glob
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import pe_features  # noqa: E402


def mpcmdrun():
    cands = sorted(glob.glob(r"C:\ProgramData\Microsoft\Windows Defender\Platform\*\MpCmdRun.exe"))
    cands.append(r"C:\Program Files\Windows Defender\MpCmdRun.exe")
    for c in reversed(cands):
        if os.path.exists(c):
            return c
    return None


def is_pe(path):
    try:
        with open(path, "rb") as f:
            head = f.read(0x40)
            if head[:2] != b"MZ" or len(head) < 0x40:
                return False
            f.seek(int.from_bytes(head[0x3C:0x40], "little"))
            return f.read(4) == b"PE\0\0"
    except OSError:
        return False


def group(rel):
    r = rel.replace("\\", "/").lower()
    if r in ("t5dr online.exe", "runtime/t5dr.exe"):
        return "ours"
    if r.startswith("python/lib/site-packages/crypto/"):
        return "pycryptodome"
    if r.startswith("python/"):
        return "python"
    if r.startswith("toolchain/llvm/"):
        return "llvm"
    return "other"


def scan(mp, path):
    t0 = time.time()
    r = subprocess.run([mp, "-Scan", "-ScanType", "3", "-File", path, "-DisableRemediation"],
                       capture_output=True, text=True, errors="replace", timeout=900)
    out = (r.stdout or "") + (r.stderr or "")
    threats = [l.strip() for l in out.splitlines() if l.strip().lower().startswith(("threat", "found "))]
    name = next((l.split(":", 1)[1].strip() for l in out.splitlines() if l.strip().lower().startswith("threat")
                 and ":" in l), "")
    if r.returncode == 0 and "found no threats" in out.lower():
        verdict = "clean"
    elif r.returncode == 2 or threats:
        verdict = "DETECTED " + name
    else:
        verdict = f"unclear (exit {r.returncode}): {out.strip()[-120:]!r}"
    return verdict, time.time() - t0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("target")
    ap.add_argument("--no-scan", action="store_true", help="only the inventory")
    ap.add_argument("--md", help="also write the table as markdown to this file")
    ap.add_argument("--also", nargs="*", default=[], help="more files to scan (their group is 'extra')")
    ap.add_argument("--zip-scan", action="store_true", help="also scan the zip file itself")
    a = ap.parse_args()
    tmp = None
    root = a.target
    if a.target.lower().endswith(".zip"):
        tmp = tempfile.mkdtemp(prefix="t5dr_av_")
        with zipfile.ZipFile(a.target) as zf:
            zf.extractall(tmp)
        tops = os.listdir(tmp)
        root = os.path.join(tmp, tops[0]) if len(tops) == 1 else tmp
    mp = None if a.no_scan else mpcmdrun()
    if not a.no_scan and not mp:
        sys.exit("MpCmdRun.exe not found (is Windows Defender installed?)")
    items = []
    for dp, _, fns in os.walk(root):
        for f in fns:
            p = os.path.join(dp, f)
            if is_pe(p):
                items.append((group(os.path.relpath(p, root)), os.path.relpath(p, root).replace("\\", "/"), p))
    for p in a.also:
        items.append(("extra", os.path.basename(p), p))
    items.sort(key=lambda x: ({"ours": 0, "extra": 1}.get(x[0], 2), x[0], x[1]))
    rows = []
    totals = {}
    for g, rel, p in items:
        feat = pe_features.parse(p)
        verdict, secs = ("not scanned", 0.0) if a.no_scan else scan(mp, p)
        rows.append((g, rel, feat.get("size", 0), "signed" if feat.get("signed") else "unsigned", verdict, secs))
        t = totals.setdefault(g, [0, 0, 0])
        t[0] += 1
        t[1] += verdict.startswith("clean")
        t[2] += verdict.startswith("DETECTED")
        if g in ("ours", "extra") or verdict.startswith(("DETECTED", "unclear")):
            print(f"{g:<12} {rel:<40} {feat.get('size', 0):>11,}  {rows[-1][3]:<9} {verdict}  ({secs:.0f} s)", flush=True)
    if a.zip_scan and a.target.lower().endswith(".zip") and mp:
        verdict, secs = scan(mp, os.path.abspath(a.target))
        print(f"{'zip':<12} {os.path.basename(a.target):<40} {os.path.getsize(a.target):>11,}  {'-':<9} {verdict}  ({secs:.0f} s)")
        rows.append(("zip", os.path.basename(a.target), os.path.getsize(a.target), "-", verdict, secs))
    print("\nsummary (files, clean, detected):")
    for g, (n, c, d) in sorted(totals.items()):
        print(f"  {g:<13} {n:>4} {c:>4} {d:>4}")
    if a.md:
        with open(a.md, "w", encoding="utf-8") as f:
            f.write("| group | file | size | signed | Defender |\n|---|---|---|---|---|\n")
            for g, rel, size, sig, verdict, _ in rows:
                f.write(f"| {g} | `{rel}` | {size:,} | {sig} | {verdict} |\n")
    if tmp:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
