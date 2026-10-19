#!/usr/bin/env python3
"""Several e2e runs in one table: runs, PASS, FAIL, SKIP per scenario, and every failed check.

    python tools/e2e/summarize.py build/e2e/runs/gate_rb1 build/e2e/runs/gate_ls1 ... [--out summary.md]

Each argument is a run folder (with report.json) or a glob of them. The table counts every attempt of every run;
the failures list names the run and the checks that failed."""
import argparse
import glob
import json
import os
import sys


def load(paths):
    runs = []
    for pat in paths:
        for d in sorted(glob.glob(pat)) or [pat]:
            p = os.path.join(d, "report.json")
            try:
                with open(p, encoding="utf-8") as f:
                    runs.append((os.path.basename(os.path.normpath(d)), json.load(f)))
            except (OSError, ValueError):
                print(f"skipped {d}: no report.json", file=sys.stderr)
    return runs


def table(runs):
    order, rows, fails = [], {}, []
    for name, rep in runs:
        for r in rep.get("results", []):
            n = r["name"]
            if n not in rows:
                order.append(n)
                rows[n] = {"group": r["group"], "PASS": 0, "FAIL": 0, "SKIP": 0, "runs": []}
            rows[n][r["status"]] += 1
            rows[n]["runs"].append(f"{name}:{r['status']}")
            if r["status"] == "FAIL":
                bad = [f"{c['name']} ({c['detail'][:160]})" for c in r["checks"] if not c["ok"] and c["level"] == "fail"]
                fails.append((n, name, r.get("error"), bad))
    L = ["| scenario | group | runs | PASS | FAIL | SKIP |", "|---|---|---|---|---|---|"]
    for n in order:
        x = rows[n]
        tot = x["PASS"] + x["FAIL"] + x["SKIP"]
        L.append(f"| {n} | {x['group']} | {tot} | {x['PASS']} | {x['FAIL']} | {x['SKIP']} |")
    tot = {k: sum(r[k] for r in rows.values()) for k in ("PASS", "FAIL", "SKIP")}
    L += ["", f"Total: {tot['PASS']} PASS, {tot['FAIL']} FAIL, {tot['SKIP']} SKIP in {len(runs)} run(s).", ""]
    if fails:
        L += ["## Failures", ""]
        for n, run, err, bad in fails:
            L.append(f"- **{n}** in {run}: " + (f"{err}; " if err else "") + "; ".join(bad)[:1200])
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--out")
    a = ap.parse_args()
    text = table(load(a.runs))
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
