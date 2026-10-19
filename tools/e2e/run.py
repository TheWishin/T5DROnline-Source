#!/usr/bin/env python3
"""End-to-end scenario runner: a LOCAL lobby server, two players driven through the launcher's own
Online tab (launcher/online.py -> t5lobby.tk_tab, LobbyClient, MatchDriver), real games (t5dr.exe,
persistent mode) or the stub game, a network shaper between the two games. Writes report.md
(PASS / FAIL / SKIP per scenario with the evidence) and report.json.

    python tools/e2e/run.py --list
    python tools/e2e/run.py --suite quick                 # lobby + stub scenarios, ~4 min, no game needed
    python tools/e2e/run.py --suite game                  # the real-game scenarios, ~75 min
    python tools/e2e/run.py                               # everything (suite full)
    python tools/e2e/run.py --only ranked_set,net_rollback --repeat 2
    python tools/e2e/run.py --exe C:/T5DROnline/build/cmake/t5dr.exe --out build/e2e/runs/r1

Options: --exe (default: build/cmake/t5dr.exe of this tree or of the main tree above build/),
--rounds N (rounds to win in real matches, default 1), --short (fewer netcode cases), --keep-going
(the runner never stops at a failed scenario anyway; this also keeps going after a Ctrl+C'd one),
--skip a,b. Exit code 0 = no FAIL, 1 = a FAIL, 2 = the runner itself broke.

Rules it keeps (build/AGENT_BRIEF.md): local server only (127.0.0.1; a guard refuses anything else),
games minimized + muted + below-normal priority, nothing on the desktop takes the focus, the
clipboard is never touched, only processes started here are stopped. The run folder holds logs with
player names and local addresses: never commit it (build/ is ignored).
"""
import argparse
import datetime
import fnmatch
import json
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.append(HERE)      # (appended: never in front of tools/smoke, whose run.py and scenarios.py the tests import)

import e2e_harness as harness  # noqa: E402
from e2e_harness import Abort, Ctx, Run, Skip, log  # noqa: E402
import e2e_scenarios as scenarios  # noqa: E402


def default_exe():
    for root in (harness.ROOT, harness.find_game_root()):
        if root:
            p = os.path.join(root, "build", "cmake", "t5dr.exe")
            if os.path.isfile(p):
                return p
    return None


def select(a):
    sel = []
    only = [x.strip() for x in a.only.split(",") if x.strip()] if a.only else []
    skip = [x.strip() for x in a.skip.split(",") if x.strip()] if a.skip else []
    for s in scenarios.SCENARIOS:
        if only:
            if not any(fnmatch.fnmatch(s.name, pat) or s.group.split(" ", 1)[-1].startswith(pat) for pat in only):
                continue
        elif a.suite not in s.suites:
            continue
        if any(fnmatch.fnmatch(s.name, pat) for pat in skip):
            continue
        sel.append(s)
    return sel


def run_one(run, sc, k, total, attempt):
    name = sc.name + (f"#{attempt}" if attempt > 1 else "")
    d = os.path.join(run.out, name)
    log(f"=== [{k}/{total}] {name} ({sc.group}): {sc.desc}")
    ctx = Ctx(run, sc.name, d, game=sc.game)
    t0 = time.time()
    status, error = None, None
    try:
        if sc.game and not run.exe:
            raise Skip("no game build: pass --exe")
        sc.fn(ctx)
    except Skip as e:
        status, error = "SKIP", str(e)
    except Abort as e:
        error = f"aborted at: {e}"
    except KeyboardInterrupt:
        error = "interrupted"
        raise
    except Exception as e:      # noqa: BLE001 -- a broken scenario is a FAIL with its traceback
        error = f"{type(e).__name__}: {e}"
        with open(os.path.join(d, "traceback.txt"), "w", encoding="utf-8") as f:
            f.write(traceback.format_exc())
        log(traceback.format_exc())
    finally:
        try:
            ctx.close()
        except Exception as e:  # noqa: BLE001
            log(f"close: {e}")
    if status is None:
        status = "FAIL" if (ctx.failed() or error) else "PASS"
    res = {"name": sc.name, "attempt": attempt, "group": sc.group, "game": sc.game, "desc": sc.desc, "status": status,
           "error": error, "seconds": round(time.time() - t0, 1), "dir": os.path.relpath(d, run.out),
           "checks": [{"name": n, "ok": ok, "detail": det, "level": lvl} for n, ok, det, lvl in ctx.checks],
           "evidence": ctx.evidence, "matches": ctx.matches, "contention": run.contention()}
    with open(os.path.join(d, "result.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1, default=str)
    nf = sum(1 for c in ctx.checks if not c[1] and c[3] == "fail")
    nw = sum(1 for c in ctx.checks if not c[1] and c[3] == "warn")
    log(f"=== {name}: {status} in {res['seconds']:.0f} s ({len(ctx.checks)} checks, {nf} failed, {nw} warnings)"
        + (f" -- {error}" if error else ""))
    return res


def md_escape(s):
    return str(s).replace("|", "\\|").replace("\n", " ")


def write_report(run, results, a, t0):
    by = {}
    for r in results:
        by.setdefault(r["name"], []).append(r)
    order = [s.name for s in scenarios.SCENARIOS if s.name in by]
    L = [f"# End-to-end report ({datetime.datetime.now():%Y-%m-%d %H:%M})", "",
         f"- tree: `{harness.ROOT}` ({_git_head()}), game: `{run.exe or 'none'}`, rounds per match {run.rounds}, "
         f"netcode {getattr(run, 'netcode', 'rollback')}"
         + (f", every real match on stage {run.stage} (--stage)" if getattr(run, "stage", None) else ""),
         f"- suite `{a.suite}`" + (f", only `{a.only}`" if a.only else "") + f", repeat {a.repeat}, "
         f"{(time.time() - t0) / 60:.0f} min",
         f"- other load while running: {results[-1]['contention'] if results else '-'} (fps checks only warn then)", "",
         "| scenario | group | runs | PASS | FAIL | SKIP | what |", "|---|---|---|---|---|---|---|"]
    tot = {"PASS": 0, "FAIL": 0, "SKIP": 0}
    for n in order:
        rs = by[n]
        c = {k: sum(1 for r in rs if r["status"] == k) for k in tot}
        for k in tot:
            tot[k] += c[k]
        mark = "**FAIL**" if c["FAIL"] else ("SKIP" if c["SKIP"] == len(rs) else "PASS")
        L.append(f"| {n} | {rs[0]['group']} | {len(rs)} | {c['PASS']} | {c['FAIL']} | {c['SKIP']} | {mark}: "
                 f"{md_escape(rs[0]['desc'])} |")
    L += ["", f"Total: {tot['PASS']} PASS, {tot['FAIL']} FAIL, {tot['SKIP']} SKIP.", ""]
    fails = [r for r in results if r["status"] == "FAIL"]
    if fails:
        L += ["## Failures first", ""]
        for r in fails:
            L.append(f"- **{r['name']}** (run {r['attempt']}): " + (f"{md_escape(r['error'])}; " if r["error"] else "")
                     + "; ".join(md_escape(f"{c['name']}: {c['detail']}") for c in r["checks"]
                                 if not c["ok"] and c["level"] == "fail")[:1500])
        L.append("")
    L += ["## Scenarios", ""]
    for n in order:
        for r in by[n]:
            L.append(f"### {n}" + (f" (run {r['attempt']})" if len(by[n]) > 1 else "") + f": {r['status']}")
            L.append("")
            L.append(f"{r['desc']}. {r['seconds']:.0f} s, folder `{r['dir']}`." + (f" {r['error']}" if r["error"] else ""))
            L.append("")
            for c in r["checks"]:
                tag = "ok" if c["ok"] else ("WARN" if c["level"] == "warn" else "FAIL")
                L.append(f"- {tag}: {md_escape(c['name'])}" + (f" -- {md_escape(c['detail'])}" if c["detail"] else ""))
            for e in r["evidence"]:
                L.append(f"- evidence: {md_escape(e)}")
            L.append("")
    with open(os.path.join(run.out, "report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    with open(os.path.join(run.out, "report.json"), "w", encoding="utf-8") as f:
        json.dump({"results": results, "totals": tot}, f, indent=1, default=str)
    return tot


def _git_head():
    try:
        import subprocess
        return subprocess.run(["git", "-C", harness.ROOT, "log", "-1", "--format=%h %s"], capture_output=True,
                              text=True, timeout=10).stdout.strip()[:80]
    except Exception:           # noqa: BLE001
        return "?"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--suite", default="full", choices=["quick", "lobby", "game", "net", "full"])
    ap.add_argument("--only", default="", help="comma list of scenario names / fnmatch patterns")
    ap.add_argument("--skip", default="")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--exe", default=None, help="t5dr.exe to play (only read; copied into the run folder)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--rounds", type=int, default=1)
    ap.add_argument("--short", action="store_true", help="fewer netcode cases")
    ap.add_argument("--netcode", choices=["rollback", "lockstep"], default="rollback",
                    help="lockstep: every real game runs with T5_RB_MODE=off (the scenarios that pick their own netcode "
                         "skip or keep theirs)")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--stage", default=None,
                    help="stage key (e.g. s27): every real match is fought there -- both launchers hand it to their "
                         "game instead of the lobby's pick")
    a = ap.parse_args()
    if a.list:
        for s in scenarios.SCENARIOS:
            print(f"{s.name:24} {s.group:24} {'game' if s.game else 'lobby':6} {','.join(s.suites):24} {s.desc}")
        return 0
    sel = select(a)
    if not sel:
        print("no scenario selected", file=sys.stderr)
        return 2
    exe = a.exe or default_exe()
    if any(s.game for s in sel) and not exe:
        log("no t5dr.exe found: real-game scenarios will be SKIP (pass --exe)")
    out = a.out or os.path.join(harness.ROOT, "build", "e2e", "runs", datetime.datetime.now().strftime("%Y%m%d-%H%M%S"))
    harness.below_normal_priority()
    run = Run(out, exe if any(s.game for s in sel) or exe else None, harness.find_game_root(), seed=a.seed,
              rounds=a.rounds, short=a.short, netcode=a.netcode, stage=a.stage)
    run.stage_bin()
    run.tk_root()
    log(f"e2e run {out}: {len(sel)} scenario(s) x {a.repeat}, exe {run.exe}, game root {run.game_root}")
    results = []
    t0 = time.time()
    total = len(sel) * a.repeat
    k = 0
    try:
        for attempt in range(1, a.repeat + 1):
            for sc in sel:
                k += 1
                results.append(run_one(run, sc, k, total, attempt))
                write_report(run, results, a, t0)
    except KeyboardInterrupt:
        log("interrupted")
    finally:
        run.close()
    tot = write_report(run, results, a, t0)
    log(f"report: {os.path.join(out, 'report.md')} -- {tot}")
    return 1 if tot["FAIL"] else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException:     # noqa: BLE001
        traceback.print_exc()
        sys.exit(2)
