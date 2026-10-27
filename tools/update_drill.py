"""The update a player makes, for real, before a release reaches players (docs/RELEASING.md "Update drill").

Unpacks the previous release's zip, chooses a real game package in its launcher.json (as a player's launcher has
it), then lets that release's own updater fetch the new release, check it, swap it in and start the new launcher --
the path 1.1.5 broke: its launcher closed two seconds after the update, with a package chosen.
PASS only when the swap step reports "updated" and the new launcher still runs after --alive seconds.

    python tools/update_drill.py --old-zip T5DR-Online-1.1.4.zip --tag v1.1.6 --pkg D:/game/xxx.pkg --work D:/drill

--tag reads the release from GitHub by its tag, so it works on a pre-release (publish it as one, run the drill
from the last two releases, then mark it latest). --new-zip takes a local zip instead (a candidate before the
tag, or a deliberately broken one): the old updater unpacks it and swaps it in exactly as after a download, only
the download and its checksum/signature check are skipped.

    --close-after 3          the player closes the new launcher after 3 s (its window gets WM_CLOSE); the update
                             must stay
    --expect rollback        the new release is broken on purpose: PASS when the swap step put the old files back
                             and the old launcher runs again

Nothing here touches the player's own install or the package (it is only read).
"""
import argparse
import json
import os
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
updater.start_swap(staged, old, rel["version"], out_dir=os.path.join(install, "native"), root=install, wait_pid=0)
json.dump({"from": old, "to": rel["version"], "sroot": staged["sroot"]}, open(out, "w"))
'''

# --new-zip: what prepare_update does once the download passed its checks -- unpack with the old updater's own
# checks, copy the old Python as the swap step's runner -- then the same start_swap.
LOCAL_HELPER = r'''
import json, os, shutil, sys
install, zip_path, version, out = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
sys.path.insert(0, os.path.join(install, "launcher"))
import updater
old = updater.local_version(install)
sroot = updater._new_stage_root(install)
new = updater.unpack(zip_path, os.path.join(sroot, "new"), version)
runner = os.path.join(sroot, "runner")
shutil.copytree(os.path.join(install, "python"), os.path.join(runner, "python"),
                ignore=shutil.ignore_patterns("__pycache__"))
shutil.copy2(os.path.abspath(updater.__file__), os.path.join(runner, "t5dr_update.py"))
updater.start_swap({"sroot": sroot, "new": new}, old, version, out_dir=os.path.join(install, "native"),
                   root=install, wait_pid=0)
json.dump({"from": old, "to": version, "sroot": sroot}, open(out, "w"))
'''

# The launchers running from the folder (pythonw/python under it), listed by the folder's own updater.
PROBE = ("import json, os, sys; sys.path.insert(0, os.path.join(sys.argv[1], 'launcher')); import updater; "
         "print(json.dumps([list(p) for p in updater.processes_under([sys.argv[1]], exclude={os.getpid()}) "
         "if os.path.basename(p[1]).lower() in ('pythonw.exe', 'python.exe')]))")


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--old-zip", required=True, help="the previous release's zip (what players have)")
    new = ap.add_mutually_exclusive_group(required=True)
    new.add_argument("--tag", help="the new release's tag on GitHub, e.g. v1.1.6 (a pre-release too)")
    new.add_argument("--new-zip", help="the new release as a local zip (no download, no checksum/signature check)")
    ap.add_argument("--pkg", required=True, help="a real game package (.pkg); only read")
    ap.add_argument("--rap", default="", help="its .rap (optional)")
    ap.add_argument("--work", required=True, help="an empty folder for the drill")
    ap.add_argument("--alive", type=float, default=30.0, help="seconds the new launcher must keep running")
    ap.add_argument("--close-after", type=float, default=None, metavar="SECONDS",
                    help="close the new launcher by hand (WM_CLOSE) this long after the swap; the update must stay")
    ap.add_argument("--expect", choices=("update", "rollback"), default="update",
                    help="rollback: the new release is broken on purpose; PASS = old files back, old launcher runs")
    ap.add_argument("--timeout", type=float, default=300.0, help="seconds to wait for the swap step's result")
    a = ap.parse_args(argv)
    if not os.path.isfile(a.old_zip):
        ap.error(f"--old-zip {a.old_zip} does not exist")
    if a.new_zip and not os.path.isfile(a.new_zip):
        ap.error(f"--new-zip {a.new_zip} does not exist")
    if not os.path.isfile(a.pkg):
        ap.error(f"--pkg {a.pkg} does not exist")
    if a.close_after is not None and a.expect == "rollback":
        ap.error("--close-after is for a working release (--expect update)")
    if a.tag:
        a.want = a.tag[1:] if a.tag[:1] in ("v", "V") else a.tag
    else:
        a.want = zip_version(a.new_zip)
        if not a.want:
            ap.error(f"--new-zip {a.new_zip} has no <top folder>/release.json with a version")
    return a


def zip_version(path):
    """The version in a release zip's <top>/release.json (None if it has none)."""
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        top = names[0].split("/")[0] if names else ""
        try:
            return json.loads(z.read(f"{top}/release.json")).get("version")
        except (KeyError, ValueError):
            return None


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def read_result(sroot, install, want, timeout=300.0, poll=0.5, sleep=time.sleep, clock=time.time):
    """Wait for the swap step's verdict. Returns (result, swap.log text). The result is result.json once it says
    'done' or 'undone' or failed; when the staging folder is gone (the new launcher read the result and cleaned
    up), it is made from the folder's release.json. A result still 'swapped' at the timeout is returned as is."""
    res, log = os.path.join(sroot, "result.json"), os.path.join(sroot, "swap.log")
    r, log_text = {}, ""
    end = clock() + timeout
    while clock() < end:
        r = _read_json(res) or r                       # keep the last one seen
        try:
            with open(log, encoding="utf-8", errors="replace") as f:
                log_text = f.read()
        except OSError:
            pass
        if r.get("phase") in ("done", "undone") or (r and not r.get("ok")):
            break
        if not os.path.exists(sroot):
            installed = (_read_json(os.path.join(install, "release.json")) or {}).get("version")
            ok = installed == want
            r = dict(r, ok=ok, phase="done" if ok else r.get("phase"),
                     error=None if ok else f"the folder has version {installed}")
            break
        sleep(poll)
    return r, log_text


def verdict(expect, r, installed, old_version, want, running):
    """(PASS?, why). running = launchers still running from the folder after --alive seconds."""
    if expect == "rollback":
        if r.get("ok") or r.get("phase") != "undone" or not r.get("rolled_back"):
            return False, f"the broken release was not rolled back (phase {r.get('phase')}, ok {r.get('ok')})"
        if installed != old_version:
            return False, f"the folder has version {installed}, not the old {old_version}"
        if not running:
            return False, "the old launcher is not running after the rollback"
        return True, f"rolled back to {old_version}; its launcher runs"
    if not r.get("ok") or r.get("phase") != "done":
        return False, f"not updated ({r.get('phase')}, {r.get('error') or 'no error'})"
    if installed != want:
        return False, f"the folder has version {installed}, not {want}"
    if not running:
        return False, "the new launcher does not run"
    return True, f"updated to {want}; the new launcher runs"


def launchers(py, install):
    q = subprocess.run([py, "-c", PROBE, install], capture_output=True, text=True, timeout=60)
    try:
        return json.loads(q.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return []


def close_windows_of(pids):
    """WM_CLOSE to the visible top-level windows of these processes (the player clicks the X). Returns how many."""
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    found = []
    proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def each(hwnd, _):
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in pids and user32.IsWindowVisible(hwnd):
            found.append(hwnd)
        return True

    user32.EnumWindows(proc(each), 0)
    for hwnd in found:
        user32.PostMessageW(hwnd, 0x0010, 0, 0)          # WM_CLOSE
    return len(found)


def main(argv=None):
    a = parse_args(argv)
    if os.path.exists(a.work) and os.listdir(a.work):
        sys.exit(f"--work {a.work} is not empty")
    os.makedirs(a.work, exist_ok=True)
    with zipfile.ZipFile(a.old_zip) as z:
        top = z.namelist()[0].split("/")[0]
        z.extractall(a.work)
    install = os.path.join(a.work, top)
    old_version = (_read_json(os.path.join(install, "release.json")) or {}).get("version")
    with open(os.path.join(install, "launcher.json"), "w", encoding="utf-8") as f:
        json.dump({"pkg": os.path.abspath(a.pkg), "rap": os.path.abspath(a.rap) if a.rap else ""}, f)
    out = os.path.join(a.work, "drill.json")
    py = os.path.join(install, "python", "python.exe")
    if a.tag:
        data_path = os.path.join(a.work, "release.json")
        req = urllib.request.Request(API + a.tag, headers={"Accept": "application/vnd.github+json",
                                                          "User-Agent": "t5dr-update-drill"})
        with urllib.request.urlopen(req, timeout=30) as r, open(data_path, "wb") as f:
            f.write(r.read())
        helper, args = HELPER, [data_path, out]
    else:
        helper, args = LOCAL_HELPER, [os.path.abspath(a.new_zip), a.want, out]
    helper_path = os.path.join(a.work, "drill_helper.py")
    with open(helper_path, "w", encoding="utf-8") as f:
        f.write(helper)
    print(f"update drill: {top} -> {a.tag or a.new_zip} ({a.want}), package {a.pkg}, expect {a.expect}", flush=True)
    subprocess.run([py, helper_path, install] + args, timeout=600, check=False)
    started = _read_json(out) or {}
    sroot = started.get("sroot")
    if not sroot:
        print("UPDATE DRILL FAIL: the old updater did not start the update")
        return 1
    closed = None
    if a.close_after is not None:
        # the player closes the new launcher by hand, close_after seconds after the swap step started it
        end = time.time() + a.timeout
        while time.time() < end:
            r0 = _read_json(os.path.join(sroot, "result.json")) or {}
            if r0.get("phase") in ("swapped", "done", "undone") or (r0 and not r0.get("ok")):
                break
            time.sleep(0.2)
        time.sleep(a.close_after)
        npy = os.path.join(install, "python", "python.exe")
        pids = {p for p, _ in launchers(npy, install)}
        closed = close_windows_of(pids) if pids else 0
        print(f"closed the new launcher by hand {a.close_after:.0f} s after its start ({closed} window(s), "
              f"pid(s) {sorted(pids)})", flush=True)
    r, log_text = read_result(sroot, install, a.want, timeout=a.timeout)
    if a.close_after is None:
        time.sleep(a.alive)
    else:
        time.sleep(3)                                 # it ends; nothing may start it again
    # The folder's own Python (the new one after an update, the old one after a rollback) lists what runs.
    running = launchers(os.path.join(install, "python", "python.exe"), install)
    installed = (_read_json(os.path.join(install, "release.json")) or {}).get("version")
    print(log_text.rstrip())
    if a.close_after is not None:
        # closed by hand: the update must stay, and nothing runs (no launcher came back)
        ok, why = verdict("update", r, installed, old_version, a.want, running=[1])
        if ok and closed == 0:
            ok, why = False, "no window of the new launcher to close"
        if ok and running:
            ok, why = False, f"a launcher runs again after the close: {running}"
        elif ok:
            why = f"updated to {a.want}; closed by hand after {a.close_after:.0f} s, the update stayed"
    else:
        ok, why = verdict(a.expect, r, installed, old_version, a.want, running)
    print(f"swap: {'updated' if r.get('ok') else 'NOT updated'} ({r.get('phase')}, {r.get('error') or 'no error'}); "
          f"folder now {installed}; launchers running: {len(running)}")
    for pid, _path in running:                     # the drill's own launchers
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    print(f"UPDATE DRILL {'PASS' if ok else 'FAIL'}: {why}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
