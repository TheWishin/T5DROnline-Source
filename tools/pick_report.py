#!/usr/bin/env python3
"""Per-match table of a lobby run with the real game (lobby/tools/ranked_session.py --exe ... --out DIR).

    python tools/pick_report.py DIR [DIR ...]

For every match the lobby started: did FIGHT START come on both PCs, the fighters each game logged at
FIGHT START (character, costume button, model id) and whether both agree, whether the pick was made in
the game (pick=N) or locked (a ranked set's later game, buttons=), the sync evidence (the drivers'
reports: mismatching frames, state hash of both sides) and the lobby's verdict (confirmed / void ...).
A locked game must fight the models of its set's picked game. Exit code 0 = every match OK.
"""
import json
import os
import re
import sys

RE_FIGHTERS = re.compile(r"\[df\] frame \d+: fighters: P1 (.+?) with (.+?) \(model (0x[0-9A-Fa-f]+)\), "
                         r"P2 (.+?) with (.+?) \(model (0x[0-9A-Fa-f]+)\)")
RE_START = re.compile(r"\[df\] frame \d+: FIGHT START match \d+ id (\S+):")
RE_MISMATCH = re.compile(r"PICK MISMATCH")


def game_starts(paths):
    """match id -> (P1 char, P1 button, P1 model, P2 char, P2 button, P2 model) from FIGHT START."""
    out = {}
    for p in paths:
        last = None
        try:
            with open(p, encoding="utf-8", errors="replace") as f:
                for line in f:
                    m = RE_FIGHTERS.search(line)
                    if m:
                        last = m.groups()
                        continue
                    m = RE_START.search(line)
                    if m:
                        out[m.group(1)] = last
                        last = None
                    if RE_MISMATCH.search(line):
                        out.setdefault("_pick_mismatch", []).append(line.strip())
        except OSError:
            pass
    return out


def report(run):
    with open(os.path.join(run, "events.json")) as f:
        ev = json.load(f)
    players = sorted(ev.values(), key=lambda p: p["idx"])
    starts = [game_starts(p["games"]) for p in players]
    reported = [{mid: r for mid, r in p["reported"]} for p in players]
    rows, ok_all = [], True
    order, info = [], {}
    for e in players[0]["events"]:
        if e["t"] == "match_start":
            order.append(e["match"])
            info[e["match"]] = {"start": e}
        elif e["t"] == "match_result" and e["match"] in info:
            info[e["match"]]["result"] = e
    picked_models = {}          # set id -> the models its picked game fought with
    for mid in order:
        st = info[mid]["start"]
        res = info[mid].get("result") or {}
        fight = st.get("fight") or {}
        s = st.get("set") or {}
        how = "pick" if fight.get("pick") else ("locked" + (" b=" + "|".join(map(str, fight["buttons"]))
                                                          if fight.get("buttons") else "")
                                               if s.get("locked") and (s.get("game") or 1) > 1 else "launcher")
        f1, f2 = starts[0].get(mid), starts[1].get(mid)
        both = f1 is not None and f2 is not None
        same = both and f1 == f2
        fighters = (f"{f1[0]} ({f1[1].split(' ')[0]}) vs {f1[3]} ({f1[4].split(' ')[0]})" if f1 else "-")
        if not same and f2:
            fighters += f" / P2 PC: {f2[0]} ({f2[1].split(' ')[0]}) vs {f2[3]} ({f2[4].split(' ')[0]})"
        lock_ok = True
        if both and s.get("id"):
            models = (f1[2], f1[5])
            if how == "pick":
                picked_models[s["id"]] = models
            elif how.startswith("locked") and s["id"] in picked_models:
                lock_ok = picked_models[s["id"]] == models
        r1, r2 = reported[0].get(mid) or {}, reported[1].get(mid) or {}
        desync = [r1.get("desync"), r2.get("desync")]
        hash_ok = r1.get("hash") is not None and r1.get("hash") == r2.get("hash")
        sync = "0 / same hash" if desync == [0, 0] and hash_ok else f"desync {desync}, hash {'same' if hash_ok else 'differs'}"
        verdict = res.get("status", "-") + (f" ({res['reason']})" if res.get("reason") else "")
        ok = both and same and lock_ok and desync == [0, 0] and hash_ok and res.get("status") == "confirmed"
        ok_all &= ok
        set_txt = f"set g{s.get('number')}" if s.get("rated") else ("ranked" if st.get("ranked") else "casual")
        rows.append((mid, set_txt, how, "yes" if both else f"P1 {'yes' if f1 else 'no'}, P2 {'yes' if f2 else 'no'}",
                     fighters + ("" if lock_ok else " (NOT the set's picks)"), sync, verdict, "OK" if ok else "FAIL"))
    print(f"== {run}")
    print("| match | kind | fighters from | started both | fighters (costume) | sync | lobby | |")
    print("|---|---|---|---|---|---|---|---|")
    for r in rows:
        print("| " + " | ".join(r) + " |")
    for i, s in enumerate(starts):
        for line in s.get("_pick_mismatch", []):
            print(f"P{i + 1}: {line}")
            ok_all = False
    return ok_all


def main():
    ok = True
    for run in sys.argv[1:]:
        ok &= report(run)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
