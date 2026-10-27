"""The update a player makes, for real, before a release reaches players (docs/RELEASING.md "Update drill").

Unpacks the previous release's zip, chooses a real game package in its launcher.json (as a player's launcher has
it), then lets that release's own updater download the new release from GitHub, check it, swap it in and start the
new launcher -- the path 1.1.5 broke: its launcher closed two seconds after the update, with a package chosen.
PASS only when the swap step reports "updated" and the new launcher still runs after --alive seconds.

    python tools/update_drill.py --old-zip T5DR-Online-1.1.4.zip --tag v1.1.6 --pkg D:/game/xxx.pkg --work D:/drill

The new release may be a pre-release (publish it as one, run the drill, then mark it latest): the drill reads it by
its tag. Nothing here touches the player's own install or the package (it is only read).
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile

API = "https://api.github.com/repos/TheWishin/T5DROnline/releases/tags/"

# Runs inside the old release's own Python, with its own updater, and ends right after starting the swap step
# (as the launcher closes): the swap step waits until no program runs from the folder.
HELPER = r'''
import json, os, sys, time
install, data_path, out = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, os.path.join(install, "launcher"))
import updater
data = json.load(open(data_path, encoding="utf-8"))
data["prerelease"] = False                       # the drill may run on a pre-release
rel = updater.parse_release(data)
old = updater.local_version(install)
staged = updater.prepare_update(rel, root=install)
updater.start_swap(staged, old, rel["version"], root=install, wait_pid=0)
json.dump({"from": old, "to": rel["version"], "sroot": staged["sroot"]}, open(out, "w"))
'''


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--old-zip", required=True, help="the previous release's zip (what players have)")
    ap.add_argument("--tag", required=True, help="the new release's tag on GitHub, e.g. v1.1.6")
    ap.add_argument("--pkg", required=True, help="a real game package (.pkg); only read")
    ap.add_argument("--rap", default="", help="its .rap (optional)")
    ap.add_argument("--work", required=True, help="an empty folder for the drill")
    ap.add_argument("--alive", type=float, default=30.0, help="seconds the new launcher must keep running")
    a = ap.parse_args(argv)
    if os.path.exists(a.work) and os.listdir(a.work):
        sys.exit(f"--work {a.work} is not empty")
    os.makedirs(a.work, exist_ok=True)
    with zipfile.ZipFile(a.old_zip) as z:
        top = z.namelist()[0].split("/")[0]
        z.extractall(a.work)
    install = os.path.join(a.work, top)
    with open(os.path.join(install, "launcher.json"), "w", encoding="utf-8") as f:
        json.dump({"pkg": os.path.abspath(a.pkg), "rap": os.path.abspath(a.rap) if a.rap else ""}, f)
    data_path = os.path.join(a.work, "release.json")
    req = urllib.request.Request(API + a.tag, headers={"Accept": "application/vnd.github+json",
                                                      "User-Agent": "t5dr-update-drill"})
    with urllib.request.urlopen(req, timeout=30) as r, open(data_path, "wb") as f:
        f.write(r.read())
    helper = os.path.join(a.work, "drill_helper.py")
    with open(helper, "w", encoding="utf-8") as f:
        f.write(HELPER)
    out = os.path.join(a.work, "drill.json")
    py = os.path.join(install, "python", "python.exe")
    print(f"update drill: {top} -> {a.tag}, package {a.pkg}", flush=True)
    subprocess.run([py, helper, install, data_path, out], timeout=600, check=False)
    started = json.load(open(out, encoding="utf-8")) if os.path.exists(out) else {}
    sroot = started.get("sroot")
    if not sroot:
        print("UPDATE DRILL FAIL: the old updater did not start the update")
        return 1
    res = os.path.join(sroot, "result.json")
    r = {}
    end = time.time() + 300
    want = a.tag[1:] if a.tag[:1] in ("v", "V") else a.tag
    log, log_text = os.path.join(sroot, "swap.log"), ""
    while time.time() < end:
        try:
            r = json.load(open(res, encoding="utf-8"))
        except (OSError, ValueError):
            pass                                  # keep the last one seen
        try:
            log_text = open(log, encoding="utf-8", errors="replace").read()
        except OSError:
            pass
        if r.get("phase") in ("done", "undone") or (r and not r.get("ok")):
            break
        if not os.path.exists(sroot):
            # The new launcher read the result and removed the staging folder: it started on the new files.
            try:
                installed = json.load(open(os.path.join(install, "release.json"), encoding="utf-8")).get("version")
            except (OSError, ValueError):
                installed = None
            r = {"ok": installed == want, "phase": "done" if installed == want else None,
                 "error": None if installed == want else f"the folder has version {installed}"}
            break
        time.sleep(0.5)
    alive = []
    if r.get("ok"):
        time.sleep(a.alive)
        # The new release's own process list (its Python excludes itself).
        probe = ("import json, os, sys; sys.path.insert(0, os.path.join(sys.argv[1], 'launcher')); import updater; "
                 "print(json.dumps([list(p) for p in updater.processes_under([sys.argv[1]], exclude={os.getpid()}) "
                 "if os.path.basename(p[1]).lower() in ('pythonw.exe', 'python.exe')]))")
        q = subprocess.run([py, "-c", probe, install], capture_output=True, text=True, timeout=60)
        try:
            alive = json.loads(q.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            alive = []
    print(log_text.rstrip())
    ok = bool(r.get("ok")) and r.get("phase") == "done" and bool(alive)
    print(f"swap: {'updated' if r.get('ok') else 'NOT updated'} ({r.get('phase')}, {r.get('error') or 'no error'}); "
          f"new launcher running after {a.alive:.0f} s: {'yes' if alive else 'NO'}")
    for pid, _path in alive:                      # the drill's own launchers
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    print("UPDATE DRILL " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
