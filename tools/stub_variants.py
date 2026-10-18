#!/usr/bin/env python3
"""Build the launcher-stub variants for the antivirus experiments and test that each one starts the launcher.

    python tools/stub_variants.py --out DIR --release-folder T5DR-Online-X [--version 1.0.2]
                                  [--variants current plain dynamic inprocess] [--no-test]

Writes DIR/<n>-<variant>.exe (the files to upload to VirusTotal) and DIR/variants.md (a table: size,
SHA-256, what differs, the PE features of tools/pe_features.py, the test result). Needs the MSVC tools
(it calls vcvars itself, like package_release.py) and, for the tests, an unpacked or freshly built
release folder: its python/, launcher/, tools/, lobby/ and docs/ are copied into a scratch folder per
variant; the stub is put there and started. Nothing is uploaded or sent anywhere.

Two tests per variant:
  marker    a stand-in launcher script records sys.executable, sys.prefix, sys.path, a Tk import, and runs
            a child process and a multiprocessing child with sys.executable, to prove that Python behaves
            the same under the stub as under pythonw.exe;
  launcher  the real launcher (t5dr_launcher.pyw --screenshots) is started by the stub through a shim
            script, renders every tab invisibly and exits 0.
See docs/RELEASING.md "The launcher stub" for what the variants are.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import package_release as P  # noqa: E402
import pe_features  # noqa: E402

DIFFERS = {
    "current": "the default build: static C runtime, PNG icon, no debug entry, falls back to a pythonw.exe on PATH, "
               "starts python\\pythonw.exe as a child process",
    "plain": "current + never uses a PATH python + CodeView debug entry (name only) + bitmap icon frames",
    "dynamic": "plain + dynamic C runtime (imports vcruntime140.dll and the Windows UCRT like pythonw.exe; "
               "vcruntime140.dll must sit beside the exe)",
    "inprocess": "plain + no child process: loads python\\python312.dll and calls Py_Main (imports like pythonw.exe)",
}

MARKER = r'''import json, os, subprocess, sys
here = os.path.dirname(os.path.abspath(__file__))
out = {"executable": sys.executable, "prefix": sys.prefix, "argv": sys.argv, "cwd": os.getcwd(),
       "path": sys.path, "version": sys.version.split()[0], "stdout_is_none": sys.stdout is None}
try:
    import tkinter
    out["tk"] = tkinter.Tcl().eval("info patchlevel")
except Exception as e:
    out["tk"] = f"FAILED {e!r}"
try:
    r = subprocess.run([sys.executable.replace("pythonw.exe", "python.exe"), "-c", "print(40+2)"],
                       capture_output=True, text=True, timeout=30)
    out["child"] = r.stdout.strip()
except Exception as e:
    out["child"] = f"FAILED {e!r}"
try:
    import multiprocessing.spawn as mps
    out["mp"] = "ok" if mps.get_executable() == sys.executable else "other: " + str(mps.get_executable())
except Exception as e:
    out["mp"] = f"FAILED {e!r}"
with open(os.path.join(here, "..", "marker.json"), "w") as f:
    json.dump(out, f)
'''

SHIM = r'''import os, runpy, sys
here = os.path.dirname(os.path.abspath(__file__))
sys.argv = [os.path.join(here, "_real_launcher.pyw"), "--screenshots", os.path.join(here, "..", "shots")]
try:
    runpy.run_path(os.path.join(here, "_real_launcher.pyw"), run_name="__main__")
    code = 0
except SystemExit as e:
    code = e.code or 0
with open(os.path.join(here, "..", "launcher_exit.txt"), "w") as f:
    f.write(str(code))
'''


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def prepare_test_folder(base, release, variant_dir, shim_real):
    """A scratch copy of the release folder without the big parts, with the variant stub in it."""
    if os.path.exists(base):
        shutil.rmtree(base)
    os.makedirs(base)
    for name in ("launcher", "tools", "lobby", "docs", "python", "release.json", "CMakeLists.txt", "README.txt"):
        src = os.path.join(release, name)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(base, name))
        elif os.path.exists(src):
            shutil.copy2(src, os.path.join(base, name))
    for f in os.listdir(variant_dir):                  # T5DR Online.exe (+ vcruntime140.dll)
        shutil.copy2(os.path.join(variant_dir, f), os.path.join(base, f))
    script = os.path.join(base, "launcher", "t5dr_launcher.pyw")
    if shim_real:
        os.replace(script, os.path.join(base, "launcher", "_real_launcher.pyw"))
        open(script, "w").write(SHIM)
    else:
        open(script, "w").write(MARKER)


def stop_leftovers(base):
    """End programs that run from the scratch folder `base` (only ever ones this test started)."""
    ps = ("Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -and "
          "$_.ExecutablePath.ToLower().StartsWith($env:T5DR_SCRATCH.ToLower()) } | "
          "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }")
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps], capture_output=True,
                   env=dict(os.environ, T5DR_SCRATCH=os.path.abspath(base) + os.sep))


def run_stub(base, wait_for, timeout):
    t0 = time.time()
    # CreateProcess takes no working directory longer than MAX_PATH, so a very long folder is started from here.
    p = subprocess.Popen([os.path.join(base, "T5DR Online.exe")], cwd=base if len(base) < 240 else None)
    try:
        rc = p.wait(30)
    except subprocess.TimeoutExpired:
        rc = "hung"
    while time.time() - t0 < timeout and not os.path.exists(os.path.join(base, wait_for)):
        time.sleep(0.5)
    time.sleep(0.5)
    return rc


UNICODE_DIR = "Tekken Früh Ł東京"       # ue is in cp1252; the Polish L and Kanji are not
LONG_DIR = os.path.join("long-" + "d" * 110, "path-" + "e" * 110)    # the install path goes over 260 characters


def marker_test(base, release, variant_dir, extra_prefix=""):
    """Run the stand-in launcher through the stub in `base`; returns 'ok' or what differs."""
    prepare_test_folder(base, release, variant_dir, shim_real=False)
    rc = run_stub(base, "marker.json", 60)
    marker = os.path.join(base, "marker.json")
    if not os.path.exists(marker):
        stop_leftovers(base)
        shutil.rmtree(base, ignore_errors=True)
        return extra_prefix + f"FAILED: stub exit {rc}, no marker file", None
    info = json.load(open(marker))
    py = os.path.join(base, "python", "pythonw.exe").lower()
    problems = []
    if info["executable"].lower() != py:
        problems.append("sys.executable " + info["executable"])
    if info["child"] != "42":
        problems.append("child process: " + str(info["child"]))
    if info["mp"] != "ok":
        problems.append("multiprocessing: " + str(info["mp"]))
    if str(info["tk"]).startswith("FAILED"):
        problems.append("tkinter: " + str(info["tk"]))
    if not info["prefix"].lower().startswith(os.path.join(base, "python").lower()):
        problems.append("sys.prefix " + info["prefix"])
    for q in info["path"]:
        if q and not q.lower().startswith(os.path.join(base, "python").lower()) and q.lower() != base.lower():
            problems.append("sys.path has " + q)
    stop_leftovers(base)
    shutil.rmtree(base, ignore_errors=True)
    return ("ok" if not problems else "DIFFERENT: " + "; ".join(problems)), info


def test_variant(work, release, variant, variant_dir):
    res = {}
    res["marker"], res["marker_info"] = marker_test(os.path.join(work, variant + "-marker"), release, variant_dir)
    res["unicode"], _ = marker_test(os.path.join(work, variant + "-u", UNICODE_DIR), release, variant_dir)
    res["longpath"], _ = marker_test(os.path.join(work, variant + "-l", LONG_DIR), release, variant_dir)
    shutil.rmtree(os.path.join(work, variant + "-u"), ignore_errors=True)
    shutil.rmtree(os.path.join(work, variant + "-l"), ignore_errors=True)
    base = os.path.join(work, variant + "-launcher")
    return _launcher_test(res, work, release, variant, variant_dir, base)


def _launcher_test(res, work, release, variant, variant_dir, base):
    prepare_test_folder(base, release, variant_dir, shim_real=True)
    rc = run_stub(base, "launcher_exit.txt", 240)
    exit_file = os.path.join(base, "launcher_exit.txt")
    shots = os.path.join(base, "shots")
    pngs = [f for f in os.listdir(shots) if f.endswith(".png")] if os.path.isdir(shots) else []
    code = open(exit_file).read().strip() if os.path.exists(exit_file) else None
    res["launcher"] = "ok" if code == "0" and pngs else f"FAILED: stub exit {rc}, launcher exit {code}, {len(pngs)} images"
    res["images"] = len(pngs)
    stop_leftovers(base)
    shutil.rmtree(base, ignore_errors=True)
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--release-folder", help="an unpacked or freshly built T5DR-Online-<version> folder (for the tests)")
    ap.add_argument("--version", default="1.0.2")
    ap.add_argument("--llvm", default=os.path.join(ROOT, "build", "rd", "llvm"))
    ap.add_argument("--variants", nargs="+", default=list(P.STUB_VARIANTS), choices=sorted(P.STUB_VARIANTS))
    ap.add_argument("--no-test", action="store_true")
    ap.add_argument("--test-only", action="store_true",
                    help="do not build: test the v<n>-<variant>.exe files that are already in --out")
    a = ap.parse_args()
    out = os.path.abspath(a.out)
    os.makedirs(out, exist_ok=True)
    clang = P.find_clang(a.llvm) if os.path.exists(os.path.join(a.llvm, "bin", "clang-cl.exe")) else (None, None)
    rows = []
    work = os.path.join(out, "_test")
    used = "MSVC (existing files)"
    for n, variant in enumerate(a.variants):
        vdir = os.path.join(out, "_build", variant)
        final = os.path.join(out, f"v{n}-{variant}.exe")
        if a.test_only:
            shutil.rmtree(vdir, ignore_errors=True)
            os.makedirs(vdir)
            shutil.copy2(final, os.path.join(vdir, "T5DR Online.exe"))
            if variant == "dynamic":
                shutil.copy2(os.path.join(a.release_folder, "python", "vcruntime140.dll"), vdir)
        else:
            shutil.rmtree(vdir, ignore_errors=True)
            os.makedirs(vdir)
            if variant == "dynamic" and a.release_folder:       # build_stub takes vcruntime140.dll from stage/python
                os.makedirs(os.path.join(vdir, "python"))
                shutil.copy2(os.path.join(a.release_folder, "python", "vcruntime140.dll"), os.path.join(vdir, "python"))
            used = P.build_stub(vdir, clang, a.version, "msvc", variant)
            if not used:
                sys.exit("no MSVC tools: cannot build the variants")
            shutil.rmtree(os.path.join(vdir, "python"), ignore_errors=True)
            shutil.copy2(os.path.join(vdir, "T5DR Online.exe"), final)
        feat = pe_features.parse(final)
        row = {"variant": variant, "file": os.path.basename(final), "size": os.path.getsize(final),
               "sha256": sha256(final), "differs": DIFFERS[variant], "features": pe_features.table_row(feat),
               "imports": {k: len(v) for k, v in feat["imports"].items()}, "delay": feat["delay_imports"],
               "debug": [d["type"] for d in feat["debug_directory"]],
               "rsrc_entropy": next((s["entropy"] for s in feat["sections"] if s["name"] == ".rsrc"), None),
               "extra_files": [f for f in os.listdir(vdir) if f != "T5DR Online.exe"]}
        if not a.no_test and a.release_folder:
            row.update(test_variant(work, a.release_folder, variant, vdir))
        else:
            row["marker"] = row["launcher"] = row["unicode"] = row["longpath"] = "not tested"
        rows.append(row)
        print(f"{row['file']}: {row['size']:,} bytes, sha256 {row['sha256'][:16]}..., marker {row['marker'][:60]}, "
              f"unicode {row['unicode'][:30]}, long path {row['longpath'][:30]}, launcher {row['launcher'][:60]}", flush=True)
    shutil.rmtree(work, ignore_errors=True)
    with open(os.path.join(out, "variants.md"), "w", encoding="utf-8") as f:
        f.write(f"Launcher stub variants, version {a.version}, built {time.strftime('%Y-%m-%d %H:%M')} with "
                f"{used}.\n\n| file | size | SHA-256 | what differs | starts the launcher |\n|---|---|---|---|---|\n")
        for r in rows:
            extra = f" (needs {', '.join(r['extra_files'])} beside it)" if r["extra_files"] else ""
            f.write(f"| `{r['file']}` | {r['size']:,} | `{r['sha256']}` | {r['differs']}{extra} | "
                    f"marker: {r['marker'][:40]}; real launcher: {r['launcher'][:40]} |\n")
        f.write("\n```\n" + "\n".join(r["features"] for r in rows) + "\n```\n")
    json.dump(rows, open(os.path.join(out, "variants.json"), "w"), indent=1)
    print(f"table: {os.path.join(out, 'variants.md')}")


if __name__ == "__main__":
    main()
