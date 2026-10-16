#!/usr/bin/env python3
"""Download the pinned LLVM release for Windows, check its SHA-256, and unpack the parts
the release needs into a folder laid out like an LLVM install.

    python tools/fetch_llvm.py --dest DIR [--archive FILE] [--keep-archive]

DIR then has bin/ (clang-cl, lld-link, llvm-lib, llvm-mt, ... -- what CMake uses to
build the runtime host) and lib/clang/<N>/include (clang's own headers) and can be
passed to `package_release.py --llvm DIR`, which ships clang-cl.exe, lld-link.exe and
the headers in toolchain/llvm. Nothing is installed: no registry, no PATH change.

The pin (version, URL, SHA-256) is below and nowhere else. It matches the LLVM the
release was developed and verified with (23.1.3). To move it: take the new
"clang+llvm-<ver>-x86_64-pc-windows-msvc.tar.xz" asset of
https://github.com/llvm/llvm-project/releases, put its version, URL and SHA-256 (the
"digest" GitHub lists for the asset) here, and build a test zip (docs/RELEASING.md).

--archive FILE uses an archive already on disk (it is still checked against the pin).
Running again with the same DIR is a no-op once DIR holds the pinned version.
"""
import argparse
import hashlib
import json
import os
import posixpath
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request

LLVM_VERSION = "23.1.3"
LLVM_ASSET = f"clang+llvm-{LLVM_VERSION}-x86_64-pc-windows-msvc.tar.xz"
LLVM_URL = f"https://github.com/llvm/llvm-project/releases/download/llvmorg-{LLVM_VERSION}/{LLVM_ASSET}"
LLVM_SHA256 = "9ee6a2192fbb30c776415af529927f76ca6b5d1d55699bb1315f9878e610b5b8"
LLVM_SIZE = 901_331_280

MARKER = ".t5dr-llvm.json"


def log(msg):
    print(msg, flush=True)


def fail(msg):
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::error::{msg.splitlines()[0]}", flush=True)
    sys.exit(f"[fetch_llvm] {msg}")


def wanted(rel):
    """Parts of the archive (paths below its top folder) that are unpacked."""
    return (rel.startswith("bin/") or rel.startswith("lib/clang/")
            or ("/" not in rel and rel.upper().startswith(("LICENSE", "README"))))


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def download(url, path, size):
    tmp = path + ".part"
    for attempt in range(1, 4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "T5DROnline-release/1"})
            h = hashlib.sha256()
            got, last, t0 = 0, 0, time.time()
            with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
                for b in iter(lambda: r.read(1 << 20), b""):
                    f.write(b)
                    h.update(b)
                    got += len(b)
                    if got - last >= 100 << 20:
                        last = got
                        log(f"  {got >> 20} / {size >> 20} MiB")
            log(f"  downloaded {got:,} bytes in {time.time() - t0:.0f} s")
            os.replace(tmp, path)
            return h.hexdigest()
        except OSError as e:
            log(f"  download attempt {attempt} failed: {e}")
            time.sleep(5 * attempt)
    fail(f"could not download {url}")


def safe_rel(name):
    """Path below the archive's top folder, '/'-separated; None for the top folder itself.
    Refuses absolute paths and '..' (a malformed or hostile archive)."""
    name = name.replace("\\", "/")
    while name.startswith("./"):
        name = name[2:]
    parts = name.split("/", 1)
    if len(parts) < 2 or not parts[1].strip("/"):
        return None
    rel = posixpath.normpath(parts[1])
    if rel.startswith(("/", "../")) or rel == ".." or ":" in rel:
        fail(f"unsafe path in archive: {name}")
    return rel


def extract(archive, dest):
    """One streaming pass over the .tar.xz. Hard links and symlinks to a file already
    written are copied; links whose target lies outside the wanted parts are filled by a
    second pass."""
    written, pending = {}, {}
    n = 0
    with tarfile.open(archive, "r|xz") as tf:
        for m in tf:
            rel = safe_rel(m.name)
            if rel is None or not wanted(rel):
                continue
            out = os.path.join(dest, *rel.split("/"))
            if m.isdir():
                os.makedirs(out, exist_ok=True)
            elif m.isfile():
                os.makedirs(os.path.dirname(out), exist_ok=True)
                with tf.extractfile(m) as src, open(out, "wb") as f:
                    shutil.copyfileobj(src, f, 1 << 20)
                written[rel] = out
                n += 1
            elif m.islnk() or m.issym():
                target = safe_rel(m.linkname) if m.islnk() else posixpath.normpath(
                    posixpath.join(posixpath.dirname(rel), m.linkname))
                if target in written:
                    os.makedirs(os.path.dirname(out), exist_ok=True)
                    shutil.copyfile(written[target], out)
                    n += 1
                else:
                    pending.setdefault(target, []).append(out)
    if pending:
        log(f"  second pass for {len(pending)} link target(s) outside the unpacked parts")
        with tarfile.open(archive, "r|xz") as tf:
            for m in tf:
                rel = safe_rel(m.name)
                if rel in pending and m.isfile():
                    for out in pending.pop(rel):
                        os.makedirs(os.path.dirname(out), exist_ok=True)
                        with tf.extractfile(m) as src, open(out, "wb") as f:
                            shutil.copyfileobj(src, f, 1 << 20)
                        n += 1
        if pending:
            fail(f"links to files that are not in the archive: {sorted(pending)[:5]}")
    return n


def installed(dest):
    try:
        with open(os.path.join(dest, MARKER)) as f:
            m = json.load(f)
        return m.get("sha256") == LLVM_SHA256 and os.path.exists(os.path.join(dest, "bin", "clang-cl.exe"))
    except (OSError, ValueError):
        return False


def clang_version(dest):
    r = subprocess.run([os.path.join(dest, "bin", "clang-cl.exe"), "--version"], capture_output=True, text=True)
    return r.stdout.splitlines()[0] if r.returncode == 0 and r.stdout else ""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dest", required=True, help="folder to unpack into")
    ap.add_argument("--archive", help=f"use this {LLVM_ASSET} instead of downloading it")
    ap.add_argument("--keep-archive", action="store_true", help="keep the downloaded archive next to DIR")
    a = ap.parse_args()

    dest = os.path.abspath(a.dest)
    if installed(dest):
        log(f"LLVM {LLVM_VERSION} already in {dest}: {clang_version(dest)}")
        return
    if os.path.exists(dest):
        shutil.rmtree(dest)
    os.makedirs(dest)

    if a.archive:
        archive = os.path.abspath(a.archive)
        digest = sha256_file(archive)
    else:
        archive = os.path.join(os.path.dirname(dest), LLVM_ASSET)
        log(f"downloading {LLVM_URL} ({LLVM_SIZE / 1e6:,.0f} MB)")
        digest = download(LLVM_URL, archive, LLVM_SIZE)
    if digest != LLVM_SHA256:
        fail(f"SHA-256 mismatch for {archive}: got {digest}, pinned {LLVM_SHA256}")
    log(f"SHA-256 OK ({digest})")

    t0 = time.time()
    n = extract(archive, dest)
    log(f"unpacked {n} files in {time.time() - t0:.0f} s")
    if not a.archive and not a.keep_archive:
        os.remove(archive)

    for need in ("bin/clang-cl.exe", "bin/lld-link.exe"):
        if not os.path.exists(os.path.join(dest, *need.split("/"))):
            fail(f"{need} is not in {LLVM_ASSET}")
    inc = os.path.join(dest, "lib", "clang")
    if not os.path.isdir(inc) or not any(os.path.isdir(os.path.join(inc, v, "include")) for v in os.listdir(inc)):
        fail(f"lib/clang/<N>/include is not in {LLVM_ASSET}")
    ver = clang_version(dest)
    if f"clang version {LLVM_VERSION}" not in ver:
        fail(f"unpacked clang-cl reports {ver!r}, expected {LLVM_VERSION}")
    with open(os.path.join(dest, MARKER), "w") as f:
        json.dump({"version": LLVM_VERSION, "asset": LLVM_ASSET, "url": LLVM_URL, "sha256": LLVM_SHA256}, f, indent=1)
    log(f"LLVM {LLVM_VERSION} in {dest}: {ver}")


if __name__ == "__main__":
    main()
