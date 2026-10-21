#!/usr/bin/env python3
"""Several e2e runs in one table: runs, PASS, FAIL, SKIP per scenario, and every failed check.

    python tools/e2e/summarize.py build/e2e/runs/gate_rb1 build/e2e/runs/gate_ls1 ... [--out summary.md]

Each argument is a run folder (with report.json) or a glob of them. The table counts every attempt of every run;
the failures list names the run and the checks that failed.

A FAIL whose failed checks all belong to mirror matches (both players on the same fighter) is counted as
"FAIL (mirror)": the in-game select's mirror costume bug (1.1.0 gate, cs_mirror), kept apart from other failures
until it is fixed. A FAIL whose first failed check is about a real match that went out of sync (the game's own
desync count, voided by the lobby) is "FAIL (desync)": the checks after it are what the desync did to the planned
flow (a replayed game, a set that ends later). Every desynced real match is listed with its stage and fighters,
and a table counts real games and desyncs per stage."""
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


def _real_rows(r):
    """(row, fought, desynced) for every real-game match row of a result (stub rows have no fighters)."""
    out = []
    for row in r.get("matches", []):
        sides = [v for v in row.values() if isinstance(v, dict) and "result_file" in v]
        fought = next((tuple(v.get("fought")) for v in sides if v.get("fought")), None)
        if not sides or fought is None:
            continue
        des = row.get("reason") == "desync" or any((v.get("result_file") or {}).get("desync") for v in sides)
        out.append((row, fought, des))
    return out


def desync_first(r):
    """The desynced match row when the first failed check of this result is about it, else None."""
    bad = [c for c in r.get("checks", []) if not c["ok"] and c["level"] == "fail"]
    if not bad:
        return None
    for row, _fought, des in _real_rows(r):
        lab = row.get("label") or row.get("match")
        if des and lab and bad[0]["name"].startswith(f"{lab}:"):
            return row
    return None


def table(runs):
    order, rows, fails = [], {}, []
    keys = ("PASS", "FAIL", "FAIL (mirror)", "FAIL (desync)", "SKIP")
    stages, desyncs = {}, []
    for name, rep in runs:
        for r in rep.get("results", []):
            n = r["name"]
            if n not in rows:
                order.append(n)
                rows[n] = dict({k: 0 for k in keys}, group=r["group"], runs=[])
            st = r["status"]
            if st == "FAIL" and mirror_only(r):
                st = "FAIL (mirror)"
            elif st == "FAIL" and desync_first(r) is not None:
                st = "FAIL (desync)"
            for row, fought, des in _real_rows(r):
                stg = (row.get("fight") or {}).get("stage") or "?"
                k = stages.setdefault(stg, [0, 0])
                k[0] += 1
                k[1] += bool(des)
                if des:
                    desyncs.append((name, n, row.get("label"), stg, " vs ".join(fought)))
            rows[n][st] += 1
            rows[n]["runs"].append(f"{name}:{st}")
            if r["status"] == "FAIL":
                bad = [f"{c['name']} ({c['detail'][:160]})" for c in r["checks"] if not c["ok"] and c["level"] == "fail"]
                fails.append((n, name, st, r.get("error"), bad))
    L = ["| scenario | group | runs | PASS | FAIL | FAIL (mirror) | FAIL (desync) | SKIP |",
         "|---|---|---|---|---|---|---|---|"]
    for n in order:
        x = rows[n]
        tot = sum(x[k] for k in keys)
        L.append(f"| {n} | {x['group']} | {tot} | {x['PASS']} | {x['FAIL']} | {x['FAIL (mirror)']} | "
                 f"{x['FAIL (desync)']} | {x['SKIP']} |")
    tot = {k: sum(r[k] for r in rows.values()) for k in keys}
    L += ["", f"Total: {tot['PASS']} PASS, {tot['FAIL']} FAIL, {tot['FAIL (mirror)']} FAIL (mirror), "
              f"{tot['FAIL (desync)']} FAIL (desync), {tot['SKIP']} SKIP in {len(runs)} run(s).", ""]
    if fails:
        L += ["## Failures", ""]
        for n, run, st, err, bad in fails:
            L.append(f"- **{n}** in {run}" + (f" ({st[6:-1]})" if st != "FAIL" else "") + ": "
                     + (f"{err}; " if err else "") + "; ".join(bad)[:1200])
        L.append("")
    if stages:
        n_games, n_des = sum(v[0] for v in stages.values()), sum(v[1] for v in stages.values())
        L += ["## Desyncs", "", f"{n_des} of {n_games} real games out of sync.", ""]
        for run, n, label, stg, fought in desyncs:
            L.append(f"- {run} {n} '{label}': stage {stg}, {fought}")
        L += ["", "| stage | real games | desynced |", "|---|---|---|"]
        for stg in sorted(stages):
            L.append(f"| {stg} | {stages[stg][0]} | {stages[stg][1]} |")
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
