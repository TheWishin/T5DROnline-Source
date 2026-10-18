#!/usr/bin/env python3
"""Unpack a release zip into a fresh folder and check that it works as a player gets it.

    python tools/smoke_release.py dist/T5DR-Online-0.1.0-preview.zip --version 0.1.0-preview
                                  [--work DIR] [--no-gui]

Checks (each one is printed; exit 1 if any fails):
  layout     the zip has one top folder T5DR-Online-<version> with the starter, launcher,
             tools, the vendored ps3recomp, python/, toolchain/llvm/, runtime/, LICENSES/
  stamp      release.json and README.txt carry --version (the launcher shows release.json's)
  python     the bundled Python runs with a PATH of Windows folders only and no PYTHON*
             variables, imports tkinter/ssl/pycryptodome, and sees only its own folder
  prereqs    tools/prereqs.py, run by the bundled Python, finds everything the build needs
             inside the folder (precompiled runtime, clang-cl + lld-link)
  toolchain  toolchain/llvm's clang-cl is the version release.json names
  imports    runtime/t5dr.exe and T5DR Online.exe import only DLLs that are part of Windows
             (static C runtime: no Visual C++ redistributable needed)
  signature  (when release.json lists signed files) Windows reports every signature as Valid
  launcher   (GUI) the launcher renders every tab offscreen and exits (--screenshots mode)
  starter    (GUI) T5DR Online.exe starts the launcher from the bundled Python; it is still
             running after a few seconds, and is then closed
Nothing here needs the game. --no-gui skips the two GUI checks.
"""
import argparse
import json
import os
import shutil
import struct
import subprocess
import sys
import time
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import code_signing  # noqa: E402
from package_release import PY_SELFTEST, windows_only_env  # noqa: E402

REQUIRED = [
    "T5DR Online.exe", "README.txt", "release.json", "CMakeLists.txt",
    "launcher/t5dr_launcher.pyw", "launcher/core.py", "launcher/problem_report.py", "launcher/problem_report_ui.py",
    "launcher/updater.py", "lobby/t5lobby/client.py",
    "tools/build_game.py", "tools/build_game_dll.py", "tools/prereqs.py", "tools/make_keys.py",
    "deps/ps3recomp/.t5dr-vendored.json", "deps/ps3recomp/tools/ppu_lifter.py",
    "python/python.exe", "python/pythonw.exe",
    "toolchain/llvm/bin/clang-cl.exe", "toolchain/llvm/bin/lld-link.exe",
    "runtime/t5dr.exe", "runtime/t5dr.lib",
    "LICENSES/ps3recomp-MIT.txt", "LICENSES/Python-PSF.txt", "LICENSES/LLVM-LICENSE.TXT",
]
REDIST = ("vcruntime", "msvcp", "concrt", "vcomp", "ucrtbased", "msvcr", "libomp", "python3")

results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok)))
    print(f"[{'ok' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""), flush=True)
    if not ok and os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::error::release smoke test '{name}' failed: {detail.splitlines()[0] if detail else ''}", flush=True)
    return ok


def pe_imports(path):
    """Lower-case names of the DLLs a PE file imports (normal and delay-load)."""
    with open(path, "rb") as f:
        data = f.read()
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        raise ValueError("not a PE file")
    nsec, = struct.unpack_from("<H", data, pe + 6)
    optsz, = struct.unpack_from("<H", data, pe + 20)
    opt = pe + 24
    magic, = struct.unpack_from("<H", data, opt)
    ddir = opt + (112 if magic == 0x20B else 96)
    secs = opt + optsz

    def off(rva):
        for i in range(nsec):
            vsize, vaddr, rawsize, rawptr = struct.unpack_from("<IIII", data, secs + 40 * i + 8)
            if vaddr <= rva < vaddr + max(vsize, rawsize):
                return rva - vaddr + rawptr
        raise ValueError(f"RVA {rva:#x} in no section")

    def cstr(rva):
        o = off(rva)
        return data[o:data.index(b"\0", o)].decode("ascii", "replace").lower()

    names = []
    imp_rva, _ = struct.unpack_from("<II", data, ddir + 8 * 1)
    if imp_rva:
        o = off(imp_rva)
        while True:
            name_rva = struct.unpack_from("<5I", data, o)[3]
            if not name_rva:
                break
            names.append(cstr(name_rva))
            o += 20
    dly_rva, _ = struct.unpack_from("<II", data, ddir + 8 * 13)
    if dly_rva:
        o = off(dly_rva)
        while True:
            name_rva = struct.unpack_from("<8I", data, o)[1]
            if not name_rva:
                break
            names.append(cstr(name_rva))
            o += 32
    return names


def windows_dll(name):
    sysdir = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32")
    if name.startswith(REDIST):
        return False
    return name.startswith(("api-ms-win-", "ext-ms-win-")) or os.path.exists(os.path.join(sysdir, name))


def run(cmd, timeout=120, **kw):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, **kw)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except subprocess.TimeoutExpired as e:
        return -1, f"timed out after {timeout} s\n{e.stdout or ''}{e.stderr or ''}"


def launcher_processes(folder):
    """PIDs of pythonw.exe processes started from this folder's python/."""
    exe = os.path.join(folder, "python", "pythonw.exe").replace("'", "''")
    ps = (f"Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe'\" | "
          f"Where-Object {{ $_.ExecutablePath -eq '{exe}' }} | ForEach-Object {{ $_.ProcessId }}")
    rc, out = run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], timeout=60)
    return [int(x) for x in out.split() if x.strip().isdigit()]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("zip")
    ap.add_argument("--version", required=True)
    ap.add_argument("--work", help="folder to unpack into (emptied first; default: next to the zip)")
    ap.add_argument("--no-gui", action="store_true", help="skip the launcher and starter checks")
    ap.add_argument("--starter-seconds", type=int, default=6)
    a = ap.parse_args()
    version = a.version[1:] if a.version[:1] in ("v", "V") else a.version
    name = f"T5DR-Online-{version}"
    work = os.path.abspath(a.work or os.path.join(os.path.dirname(os.path.abspath(a.zip)), "smoke"))
    if os.path.exists(work):
        shutil.rmtree(work)
    os.makedirs(work)

    with zipfile.ZipFile(a.zip) as zf:
        tops = {n.split("/", 1)[0] for n in zf.namelist()}
        check("layout: one top folder", tops == {name}, f"{sorted(tops)}")
        zf.extractall(work)
    root = os.path.join(work, name)
    missing = [p for p in REQUIRED if not os.path.exists(os.path.join(root, *p.split("/")))]
    check("layout: required files", not missing, f"missing {missing}" if missing else f"{len(REQUIRED)} present")

    info = {}
    try:
        with open(os.path.join(root, "release.json")) as f:
            info = json.load(f)
    except (OSError, ValueError) as e:
        check("stamp: release.json", False, str(e))
    check("stamp: release.json version", info.get("version") == version, f"{info.get('version')!r}")
    try:
        with open(os.path.join(root, "README.txt"), encoding="utf-8") as f:
            first = f.readline().strip()
    except OSError:
        first = ""
    check("stamp: README.txt", first.endswith(f"release {version}"), first)

    env = windows_only_env()
    py, pyw = os.path.join(root, "python", "python.exe"), os.path.join(root, "python", "pythonw.exe")
    rc, out = run([py, "-B", "-c", PY_SELFTEST], env=env, cwd=root)
    if check("python: imports with a bare PATH", rc == 0, out.strip()[-300:] if rc else ""):
        pinfo = json.loads(out.strip().splitlines()[-1])
        pdir = os.path.normcase(os.path.join(root, "python"))
        outside = [p for p in pinfo["path"] if p and not os.path.normcase(os.path.abspath(p)).startswith(pdir)]
        check("python: isolated sys.path", not outside, f"{outside}" if outside else
              f"CPython {pinfo['version']}, Tcl/Tk {pinfo['tcl']}")

    rc, out = run([py, "-B", os.path.join(root, "tools", "prereqs.py"), "--json"], env=env, cwd=root)
    try:
        items = json.loads(out[out.index("["):])
        bad = [f"{i['name']}: {i['detail']}" for i in items if not i["ok"]]
        ids = {i["id"] for i in items}
        check("prereqs: all found inside the folder", rc == 0 and not bad and {"runtime", "llvm"} <= ids,
              "; ".join(bad) if bad else ", ".join(f"{i['id']}={i['detail']}" for i in items if i["id"] in
                                                   ("runtime", "llvm", "ps3recomp")))
    except (ValueError, KeyError) as e:
        check("prereqs: all found inside the folder", False, f"{e}\n{out[-500:]}")

    rc, out = run([os.path.join(root, "toolchain", "llvm", "bin", "clang-cl.exe"), "--version"], env=env)
    want = info.get("llvm") or "?"
    check("toolchain: clang-cl version", rc == 0 and f"clang version {want}" in out,
          out.splitlines()[0] if out else f"exit {rc}")

    for rel in ("runtime/t5dr.exe", "T5DR Online.exe"):
        try:
            dlls = pe_imports(os.path.join(root, *rel.split("/")))
            bad = [d for d in dlls if not windows_dll(d)]
            check(f"imports: {rel}", dlls and not bad, f"not part of Windows: {bad}" if bad else ", ".join(dlls))
        except (OSError, ValueError, struct.error) as e:
            check(f"imports: {rel}", False, str(e))

    # A code-signed release (docs/RELEASING.md "Code signing"): Windows must accept every signature.
    signed = info.get("signed") or []
    for rel in signed:
        status, subject = code_signing.authenticode_status(os.path.join(root, *rel.split("/")))
        check(f"signature: {rel}", status == "Valid", f"{status}, {subject}")
    if not signed:
        print("[--] signature: this zip is not code-signed (no signing service set up)", flush=True)

    # The host build globs src/ (netplay, direct fight, rollback); a zip staged without it still
    # builds, just a runtime with no online play. The strings are the env variables the lobby sets.
    try:
        with open(os.path.join(root, "runtime", "t5dr.exe"), "rb") as f:
            blob = f.read()
        want = (b"T5_NET_MODE", b"T5_FIGHT", b"T5_FIGHT_FILE", b"T5_NET_RESULT_FILE")
        miss = [w.decode() for w in want if w not in blob]
        check("runtime: netplay and direct fight compiled in", not miss,
              f"missing in runtime/t5dr.exe: {miss} (is src/ staged?)" if miss else ", ".join(w.decode() for w in want))
    except OSError as e:
        check("runtime: netplay and direct fight compiled in", False, str(e))

    if not a.no_gui:
        shots = os.path.join(work, "shots")
        t0 = time.time()
        rc, out = run([pyw, "-B", os.path.join(root, "launcher", "t5dr_launcher.pyw"), "--screenshots", shots],
                      env=env, cwd=root, timeout=180)
        pngs = sorted(f for f in os.listdir(shots) if f.endswith(".png")) if os.path.isdir(shots) else []
        check("launcher: renders offscreen and exits", rc == 0,
              f"exit {rc} after {time.time() - t0:.0f} s, {len(pngs)} tab image(s) in {shots}"
              + (f"\n{out.strip()[-500:]}" if rc else ""))

        before = set(launcher_processes(root))
        p = subprocess.Popen([os.path.join(root, "T5DR Online.exe")], cwd=root, env=env)
        try:
            rc = p.wait(30)
        except subprocess.TimeoutExpired:
            p.kill()
            rc = "hung"
        time.sleep(a.starter_seconds)
        pids = [x for x in launcher_processes(root) if x not in before]
        check("starter: launcher running", rc == 0 and pids,
              f"starter exit {rc}, launcher pid(s) {pids} alive after {a.starter_seconds} s")
        for pid in pids:
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
        time.sleep(1)
        left = [x for x in launcher_processes(root) if x not in before]
        check("starter: launcher closed", not left, f"still running: {left}" if left else "")

    failed = [n for n, ok in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed" + (f"; FAILED: {failed}" if failed else ""))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
