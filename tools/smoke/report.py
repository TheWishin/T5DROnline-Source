"""Write the suite's report: report.json (everything) and report.md (one
table, failures first). Pure: tests/test_smoke_report.py checks it."""
import json
import os

from checks import ORDER, test_status

MARK = {"pass": "PASS", "fail": "FAIL", "known-fail": "KNOWN", "xpass": "XPASS",
        "warn": "WARN", "info": "info", "skip": "skip"}


def exit_code(tests):
    """0: nothing unexpected failed. 1: a check failed that no known issue
    explains. 2: a test could not run (harness error)."""
    if any(t.get("error") for t in tests):
        return 2
    if any(c["status"] == "fail" for t in tests for c in t["checks"]):
        return 1
    return 0


def counts(tests):
    n = {}
    for t in tests:
        for c in t["checks"]:
            n[c["status"]] = n.get(c["status"], 0) + 1
    return n


def _link(out_dir, test, ev):
    if not ev:
        return ""
    rel = f"{test}/{ev}".replace("\\", "/")
    return f"[{os.path.basename(ev)}]({rel})"


def _cell(s):
    return str(s).replace("|", "\\|").replace("\n", " ")


def markdown(meta, tests, out_dir=""):
    code = exit_code(tests)
    n = counts(tests)
    verdict = {0: "PASS", 1: "FAIL", 2: "ERROR"}[code]
    lines = [f"# Smoke suite: {verdict}", ""]
    lines.append(f"- suite **{meta.get('suite')}**, {len(tests)} test(s), {meta.get('duration', 0):.0f} s, "
                 f"exe `{meta.get('exe')}` ({meta.get('exe_mtime', '?')})")
    lines.append("- checks: " + ", ".join(f"{MARK[s]} {n[s]}" for s in ORDER if n.get(s)))
    if meta.get("contention"):
        lines.append(f"- load on the PC during the run: {meta['contention']} "
                     "(fps/audio failures under load are WARN, not FAIL; --strict to fail them)")
    lines.append(f"- exit code {code}")
    lines.append("")
    lines.append("| test | result | time |")
    lines.append("|---|---|---|")
    for t in tests:
        st = "ERROR" if t.get("error") else MARK[test_status(t["checks"])]
        lines.append(f"| [{t['name']}]({t['name']}/) | {st} | {t.get('duration', 0):.0f} s |")
    lines.append("")
    # Failures and other notable checks first, then everything.
    notable = [(t, c) for t in tests for c in t["checks"] if c["status"] in ("fail", "warn", "known-fail", "xpass")]
    if notable or any(t.get("error") for t in tests):
        lines.append("## Needs attention")
        lines.append("")
        for t in tests:
            if t.get("error"):
                lines.append(f"- **ERROR** `{t['name']}`: {t['error']}")
        for t, c in sorted(notable, key=lambda tc: ORDER.index(tc[1]["status"])):
            issue = f" ({c['issue']})" if c.get("issue") else ""
            hint = " -- known issue no longer reproduces? Confirm, then remove it from known_issues.json" \
                if c["status"] == "xpass" else ""
            ev = _link(out_dir, t["name"], c.get("evidence"))
            lines.append(f"- **{MARK[c['status']]}**{issue} `{t['name']}` `{c['id']}`: {_cell(c['detail'])}"
                         f"{' ' + ev if ev else ''}{hint}")
        lines.append("")
    lines.append("## All checks")
    lines.append("")
    lines.append("| test | check | result | detail | evidence |")
    lines.append("|---|---|---|---|---|")
    for t in tests:
        for c in t["checks"]:
            issue = f" {c['issue']}" if c.get("issue") else ""
            lines.append(f"| {t['name']} | {c['id']} | {MARK[c['status']]}{issue} | {_cell(c['detail'])} | "
                         f"{_link(out_dir, t['name'], c.get('evidence'))} |")
    lines.append("")
    return "\n".join(lines)


def write(out_dir, meta, tests):
    os.makedirs(out_dir, exist_ok=True)
    doc = {"meta": meta, "exit_code": exit_code(tests), "counts": counts(tests),
           "tests": [{k: v for k, v in t.items() if k != "run"} for t in tests]}
    with open(os.path.join(out_dir, "report.json"), "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1, default=str)
    md = markdown(meta, tests, out_dir)
    with open(os.path.join(out_dir, "report.md"), "w", encoding="utf-8") as f:
        f.write(md)
    return md
