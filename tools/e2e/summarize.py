#!/usr/bin/env python3
"""Several e2e runs in one table: runs, PASS, FAIL, SKIP per scenario, and every failed check.

    python tools/e2e/summarize.py build/e2e/runs/gate_rb1 build/e2e/runs/gate_ls1 ... [--out summary.md]

Each argument is a run folder (with report.json) or a glob of them. The table counts every attempt of every run;
the failures list names the run and the checks that failed.

A FAIL whose failed checks all belong to mirror matches (both players on the same fighter) is counted as
"FAIL (mirror)": the in-game select's mirror costume bug (1.1.0 gate, cs_mirror), kept apart from other failures
until it is fixed."""
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


def mirror_only(r):
    """True when every failed check of this result is about a mirror match (same fighter on both sides)."""
    bad = [c for c in r.get("checks", []) if not c["ok"] and c["level"] == "fail"]
    if not bad or r.get("error"):
        return False
    mirror = set()
    for row in r.get("matches", []):
        f = row.get("fight") or {}
        if f.get("p1") and f.get("p1") == f.get("p2"):
            mirror.add(row.get("label") or row.get("match"))
            mirror.add(row.get("match"))
    if r["name"] == "cs_mirror":
        mirror.update(row.get("label") for row in r.get("matches", []) if "same button" in str(row.get("label")))
    return bool(mirror) and all(any(c["name"].startswith(f"{m}:") for m in mirror if m) for c in bad)


def table(runs):
    order, rows, fails = [], {}, []
    keys = ("PASS", "FAIL", "FAIL (mirror)", "SKIP")
    for name, rep in runs:
        for r in rep.get("results", []):
            n = r["name"]
            if n not in rows:
                order.append(n)
                rows[n] = dict({k: 0 for k in keys}, group=r["group"], runs=[])
            st = r["status"]
            if st == "FAIL" and mirror_only(r):
                st = "FAIL (mirror)"
            rows[n][st] += 1
            rows[n]["runs"].append(f"{name}:{st}")
            if r["status"] == "FAIL":
                bad = [f"{c['name']} ({c['detail'][:160]})" for c in r["checks"] if not c["ok"] and c["level"] == "fail"]
                fails.append((n, name, st, r.get("error"), bad))
    L = ["| scenario | group | runs | PASS | FAIL | FAIL (mirror) | SKIP |", "|---|---|---|---|---|---|---|"]
    for n in order:
        x = rows[n]
        tot = sum(x[k] for k in keys)
        L.append(f"| {n} | {x['group']} | {tot} | {x['PASS']} | {x['FAIL']} | {x['FAIL (mirror)']} | {x['SKIP']} |")
    tot = {k: sum(r[k] for r in rows.values()) for k in keys}
    L += ["", f"Total: {tot['PASS']} PASS, {tot['FAIL']} FAIL, {tot['FAIL (mirror)']} FAIL (mirror), {tot['SKIP']} SKIP "
              f"in {len(runs)} run(s).", ""]
    if fails:
        L += ["## Failures", ""]
        for n, run, st, err, bad in fails:
            L.append(f"- **{n}** in {run}" + (" (mirror)" if st != "FAIL" else "") + ": "
                     + (f"{err}; " if err else "") + "; ".join(bad)[:1200])
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
