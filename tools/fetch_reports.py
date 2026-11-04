"""Fetch the problem reports players sent (lobby server reports.py) from the lobby server into build/reports/.

    python tools/fetch_reports.py                 # T5DR and T4: every report not fetched yet
    python tools/fetch_reports.py --game t5 --list
    python tools/fetch_reports.py --id K7QF2M     # one report (again)
    python tools/fetch_reports.py --dry-run       # print the ssh/scp commands only

For the coordinator's PC: ssh/scp with keys/vps_t5lobby and keys/vps_known_hosts (the deploy key; never in git), as
tools/deploy_lobby.sh. On the server it runs the admin tools (`t5lobby-admin reports ...`, `t4lobby-admin reports ...`):
`reports list --json` for what is there, `reports get ID --out DIR` into a folder of its own under /tmp, scp, then
removes that copy (the report itself stays on the server; `reports delete ID` there removes it).

Saved as build/reports/<game>/<YYYY-MM-DD>_<id>.zip + .json. The zips were checked by the server (names, sizes, no
bombs); still, open them like any download.
"""
import argparse
import json
import os
import shlex
import subprocess
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOST = "46.224.146.6"
ADMIN = {"t5": "t5lobby-admin", "t4": "t4lobby-admin"}
REMOTE_TMP = "/tmp/report-fetch"


def ssh_base(a):
    return ["ssh", "-i", a.key, "-o", f"UserKnownHostsFile={a.known_hosts}", "-o", "StrictHostKeyChecking=yes",
            "-o", "BatchMode=yes", f"{a.user}@{a.host}"]


def scp_base(a):
    return ["scp", "-q", "-i", a.key, "-o", f"UserKnownHostsFile={a.known_hosts}", "-o", "StrictHostKeyChecking=yes",
            "-o", "BatchMode=yes"]


def run(cmd, a, capture=True):
    if a.dry_run:
        print("$ " + " ".join(shlex.quote(c) for c in cmd))
        return ""
    r = subprocess.run(cmd, capture_output=capture, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f"{cmd[0]} failed ({r.returncode}): {(r.stderr or '').strip()[:300]}")
    return r.stdout


def remote_list(a, game):
    out = run(ssh_base(a) + [f"{ADMIN[game]} reports list --json --limit {a.limit}"], a)
    if a.dry_run:
        return []
    try:
        rows = json.loads(out)
    except ValueError:
        if "no report folder" in out:
            return []
        raise RuntimeError(f"{ADMIN[game]}: unexpected answer: {out[:200]}")
    return [r for r in rows if isinstance(r, dict) and isinstance(r.get("id"), str) and r["id"].isalnum()]


def local_name(meta):
    day = time.strftime("%Y-%m-%d", time.gmtime(float(meta.get("time", 0))))
    return f"{day}_{meta['id']}"


def fetch_one(a, game, meta, dest):
    rid = meta["id"]
    tmp = f"{REMOTE_TMP}-{game}-{rid}"
    run(ssh_base(a) + [f"{ADMIN[game]} reports get {shlex.quote(rid)} --out {shlex.quote(tmp)}"], a)
    base = os.path.join(dest, local_name(meta))
    try:
        run(scp_base(a) + [f"{a.user}@{a.host}:{tmp}/report-{rid}.zip", base + ".zip"], a)
        run(scp_base(a) + [f"{a.user}@{a.host}:{tmp}/report-{rid}.json", base + ".json"], a)
    finally:
        run(ssh_base(a) + [f"rm -rf {shlex.quote(tmp)}"], a)
    return base + ".zip"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--game", choices=("t5", "t4", "both"), default="both")
    ap.add_argument("--id", help="fetch this report (again)")
    ap.add_argument("--list", action="store_true", help="only list what the server has")
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--host", default=HOST)
    ap.add_argument("--user", default="root")
    ap.add_argument("--key", default=os.path.join(REPO, "keys", "vps_t5lobby"))
    ap.add_argument("--known-hosts", default=os.path.join(REPO, "keys", "vps_known_hosts"))
    ap.add_argument("--out", default=os.path.join(REPO, "build", "reports"))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    if not a.dry_run and not (os.path.isfile(a.key) and os.path.isfile(a.known_hosts)):
        sys.exit(f"need {a.key} and {a.known_hosts} (the deploy key, kept out of git)")
    games = ("t5", "t4") if a.game == "both" else (a.game,)
    got = 0
    for game in games:
        dest = os.path.join(a.out, game)
        os.makedirs(dest, exist_ok=True)
        rows = remote_list(a, game)
        if a.dry_run and a.id:
            rows = [{"id": a.id, "time": time.time()}]
        if a.id:
            rows = [r for r in rows if r["id"].upper() == a.id.strip("#").upper()]
        for r in rows:
            have = os.path.isfile(os.path.join(dest, local_name(r) + ".zip"))
            line = (f"{game} #{r['id']}  {time.strftime('%Y-%m-%d %H:%M', time.gmtime(float(r.get('time', 0))))}Z  "
                    f"{r.get('version', '?'):<8} {r.get('name') or '-':<16} {(r.get('description') or '')[:50]}")
            if a.list:
                print(line + ("   (fetched)" if have else ""))
                continue
            if have and not a.id:
                continue
            path = fetch_one(a, game, r, dest)
            print(f"{line}\n    -> {path}")
            got += 1
    if not a.list:
        print(f"{got} report(s) fetched into {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
