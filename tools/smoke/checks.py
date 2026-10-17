"""Turn one test run (Game.result()) into pass/fail checks. Pure: no game,
no Windows -- tests/test_smoke_checks.py feeds it synthetic runs.

Statuses
  pass        the check holds
  fail        it does not -- a regression unless known_issues.json lists it
  known-fail  it does not, and known_issues.json says why (issue id)
  xpass       known_issues.json expects a failure but it passed: the issue
              may be fixed -- confirm and delete the entry
  warn        it failed, but the measurement is unreliable (other games or
              compilers were running) -- fps and audio only, unless --strict
  info        a number worth reporting with no threshold (fight fps)
  skip        nothing to measure (e.g. a phase shorter than one 5-s window)

Phase kinds (set by the scenario with Game.phase(name, kind)) choose what is
checked in that stretch of the run:
  boot     nothing but crashes/hangs (intro movie, first loads)
  title    fps >= fps_min.title; no audio check (the title menu is silent)
  menu     fps >= fps_min.menu, audio silent <= audio_silent.menu
  load     nothing (loading screens, VS splash, intros)
  fight    fps reported (fps_min.fight if > 0), audio silent <= audio_silent.fight,
           frames show the fight HUD and no spikes
  attract  audio silent <= audio_silent.attract
  idle     crashes/hangs/memory only (long stability runs)
"""
import fnmatch
import re
import statistics

import frames as framelib

DEFAULTS = {
    "hang_gap_s": 12.0,          # no [fps] line for this long = hang (the runtime prints one every 5 s)
    "first_frame_s": 60.0,       # first [fps] line must come within this many seconds of start
    "fps_min.title": 58.0,       # median over the phase's full 5-s windows
    "fps_min.menu": 58.0,
    "fps_min.fight": 0.0,        # 0 = report only
    "fps_min.attract": 0.0,
    "audio_silent.menu": 10.0,   # median % of silent mixed blocks per 5-s window
    "audio_silent.fight": 10.0,
    "audio_silent.attract": 10.0,
    "mem_growth_mb": 400.0,      # private bytes, peak after the first title vs at the first title
    "mem_slope_mb_min": 15.0,    # long runs: growth per minute over the second half
    "frozen_eps": 0.3,           # mean abs luma change (0-255) between dumps below this = same picture
    "frozen_min_frames": 6,      # need this many frames in a phase to call it frozen
    "settle_s": 3.0,             # picture checks skip the first seconds of a phase (fades)
    "picture_min_frames": 5,     # ... and need this many frames after that (shorter phases: see the shots)
    "spike_limit": framelib.SPIKE_LIMIT,
    "contention_builds": 4,      # this many compiler processes make fps/audio unreliable
}

FPS_KINDS = {"title": "fps_min.title", "menu": "fps_min.menu", "fight": "fps_min.fight",
             "attract": "fps_min.attract"}
AUDIO_KINDS = {"menu": "audio_silent.menu", "fight": "audio_silent.fight",
               "attract": "audio_silent.attract"}
MOTION_KINDS = {"title", "menu", "fight", "attract"}     # the picture must change
CONTENT_KINDS = {"title", "menu", "fight", "attract", "idle"}

ORDER = ["fail", "warn", "known-fail", "xpass", "pass", "info", "skip"]


def check(cid, status, detail="", evidence=None, value=None, limit=None):
    c = {"id": cid, "status": status, "detail": detail}
    if evidence:
        c["evidence"] = evidence
    if value is not None:
        c["value"] = value
    if limit is not None:
        c["limit"] = limit
    return c


def median(xs):
    return statistics.median(xs) if xs else None


def in_window(t, span, start, end, tol=0.5):
    """Does a 5-s sample that arrived at t lie inside [start, end]?"""
    if t is None:
        return False
    return t - span >= start - tol and t <= end + tol


def phase_samples(samples, phase, span_of=lambda s: s[2]):
    _name, _kind, start, end = phase
    return [s for s in samples if in_window(s[0], span_of(s), start, end)]


def unreliable(contention, th):
    """Why fps/audio numbers cannot be trusted, or None."""
    if not contention:
        return None
    why = []
    if contention.get("games"):
        why.append(f"{contention['games']} other t5dr.exe")
    if contention.get("builds", 0) >= th["contention_builds"]:
        why.append(f"{contention['builds']} compiler processes")
    return ", ".join(why) or None


def evaluate(run, known_nids=(), thresholds=None, strict=False):
    """List of checks for one run (a Game.result() dict)."""
    th = dict(DEFAULTS)
    th.update(thresholds or {})
    out = []
    end_t = run.get("duration") or 0.0
    phases = [list(p) for p in run.get("phases", [])]
    for p in phases:
        if p[3] is None:
            p[3] = end_t
    noisy = None if strict else unreliable(run.get("contention"), th)

    # --- started / crashed / exited early
    if run.get("start_error"):
        return [check("start", "fail", run["start_error"])]
    crashes = run.get("crashes", [])
    if crashes:
        t, line, ph = crashes[0][:3]
        out.append(check("no-crash", "fail", f"{len(crashes)} [CRASH] line(s); first at {t:.0f}s in {ph}: {line[:160]}",
                         evidence="game.log"))
    elif run.get("aborted") and "exited" in run["aborted"]:
        out.append(check("no-crash", "fail", run["aborted"], evidence="game.log"))
    else:
        out.append(check("no-crash", "pass", "no [CRASH], ran until stopped"))

    # --- hang: gaps between [fps] lines
    fps = run.get("fps", [])
    fps_t = [f[0] for f in fps if f[0] is not None]
    if not fps_t:
        out.append(check("no-hang", "fail", "no [fps] line at all: nothing was ever presented",
                         evidence="game.log"))
    else:
        first = fps_t[0]
        pts = fps_t + ([end_t] if not run.get("aborted") or "exited" not in run["aborted"] else [])
        worst = max(((b - a, a) for a, b in zip(pts, pts[1:])), default=(0.0, first))
        if first > th["first_frame_s"]:
            out.append(check("no-hang", "fail", f"first [fps] line only at {first:.0f}s", value=round(first, 1),
                             limit=th["first_frame_s"]))
        elif worst[0] > th["hang_gap_s"]:
            ph = phase_at(phases, worst[1])
            out.append(check("no-hang", "fail", f"no frames for {worst[0]:.0f}s from {worst[1]:.0f}s ({ph})",
                             value=round(worst[0], 1), limit=th["hang_gap_s"], evidence="events.tsv"))
        else:
            out.append(check("no-hang", "pass", f"longest gap between [fps] lines {worst[0]:.1f}s",
                             value=round(worst[0], 1), limit=th["hang_gap_s"]))

    # --- expectations the scenario recorded (reached the title, fight started, ...)
    for e in run.get("expects", []):
        out.append(check(f"reach.{e['name']}", "pass" if e["ok"] else "fail", e.get("detail", ""),
                         evidence=e.get("evidence")))

    # --- per phase: fps, audio, picture
    audio = run.get("audio", [])
    frames = run.get("frames", [])
    for ph in phases:
        name, kind, start, end = ph
        if kind in FPS_KINDS:
            key = FPS_KINDS[kind]
            vals = [f[1] for f in phase_samples(fps, ph)]
            if not vals:
                out.append(check(f"fps.{name}", "skip", f"no full 5-s window in {end - start:.0f}s"))
            else:
                med, lo = median(vals), min(vals)
                desc = f"median {med:.1f}, min {lo:.1f} over {len(vals)} window(s)"
                limit = th[key]
                if limit <= 0:
                    out.append(check(f"fps.{name}", "info", desc, value=round(med, 1)))
                elif med >= limit:
                    out.append(check(f"fps.{name}", "pass", desc, value=round(med, 1), limit=limit))
                else:
                    st = "warn" if noisy else "fail"
                    out.append(check(f"fps.{name}", st, desc + (f" -- unreliable: {noisy}" if noisy else ""),
                                     value=round(med, 1), limit=limit))
        if kind in AUDIO_KINDS:
            key = AUDIO_KINDS[kind]
            vals = [a[1] for a in phase_samples(audio, ph, span_of=lambda a: 5.0)]
            if not vals:
                why = "no [audio-rate] lines (AUDIO_RATE unsupported?)" if not audio else \
                      f"no full 5-s window in {end - start:.0f}s"
                out.append(check(f"audio.{name}", "skip", why))
            else:
                med, hi = median(vals), max(vals)
                desc = f"silent blocks median {med:.1f}%, max {hi:.1f}% over {len(vals)} window(s)"
                limit = th[key]
                if med <= limit:
                    out.append(check(f"audio.{name}", "pass", desc, value=round(med, 1), limit=limit))
                else:
                    st = "warn" if noisy else "fail"
                    out.append(check(f"audio.{name}", st, desc + (f" -- unreliable: {noisy}" if noisy else ""),
                                     value=round(med, 1), limit=limit))
        pf = [f for f in frames if f.get("t") is not None and start <= f["t"] <= end]
        # Fades to and from black happen at most phase changes: judge the
        # picture once the phase has settled.
        settled = [f for f in pf if f["t"] >= start + th["settle_s"]]
        if kind in CONTENT_KINDS and len(settled) >= th["picture_min_frames"]:
            classes = [framelib.classify(f) for f in settled]
            bad = [c for c in classes if c != "content"]
            if len(bad) * 2 > len(classes):
                worst = max(set(bad), key=bad.count)
                ev = next(f["file"] for f, c in zip(settled, classes) if c == worst)
                out.append(check(f"picture.{name}", "fail",
                                 f"{len(bad)}/{len(classes)} frames {worst}", evidence=ev))
            else:
                out.append(check(f"picture.{name}", "pass", f"{len(classes) - len(bad)}/{len(classes)} frames with content"))
        if kind in MOTION_KINDS and len(pf) >= th["frozen_min_frames"]:
            diffs = [f.get("diff_prev") for f in pf[1:]]
            if framelib.frozen(diffs, th["frozen_eps"]):
                out.append(check(f"frozen.{name}", "fail",
                                 f"{len(pf)} frames over {pf[-1]['t'] - pf[0]['t']:.0f}s are the same picture",
                                 evidence=pf[-1]["file"]))
            else:
                mx = max(d for d in diffs if d is not None)
                out.append(check(f"frozen.{name}", "pass", f"largest change between dumps {mx:.1f}"))

    # --- fighters: HUD seen, no spikes
    fight_phases = [p for p in phases if p[1] == "fight"]
    if fight_phases:
        ff = [f for f in frames if f.get("t") is not None and any(p[2] <= f["t"] <= p[3] for p in fight_phases)]
        fights = [f for f in ff if f.get("fight", {}).get("is_fight")]
        if not fights:
            ev = ff[-1]["file"] if ff else None
            out.append(check("fighters", "fail", f"no frame with the fight HUD among {len(ff)} fight-phase frames",
                             evidence=ev))
        else:
            ok, med, mx = framelib.fighters_verdict([f["fight"]["spikes"] for f in fights], th["spike_limit"])
            worst = max(fights, key=lambda f: f["fight"]["spikes"])
            desc = f"{len(fights)} HUD frames, spike score median {med}, max {mx} (limit {th['spike_limit']})"
            out.append(check("fighters", "pass" if ok else "fail", desc, evidence=worst["file"],
                             value=med, limit=th["spike_limit"]))

    # --- screenshots the scenario asked for
    for name, shot in sorted(run.get("shots", {}).items()):
        exp = shot.get("expect", "content")
        if exp == "any":
            continue
        fr = shot.get("frame")
        if not fr:
            out.append(check(f"shot.{name}", "fail", "no frame was presented", evidence=None))
            continue
        cls = framelib.classify(fr)
        if exp == "fight":
            fc = shot.get("fight") or fr.get("fight") or {}
            if cls != "content" or not fc.get("is_fight"):
                out.append(check(f"shot.{name}", "fail", f"{cls}, HUD {fc.get('hud')}: not a fight",
                                 evidence=shot.get("file")))
            else:
                out.append(check(f"shot.{name}", "pass", f"fight HUD {fc.get('hud')}, spikes {fc.get('spikes')}",
                                 evidence=shot.get("file")))
        else:
            out.append(check(f"shot.{name}", "pass" if cls == "content" else "fail", framelib.describe(fr),
                             evidence=shot.get("file")))

    # --- unresolved NIDs
    nids = run.get("nids", {})
    new = sorted(n for n in nids if n not in set(known_nids))
    if new:
        det = "; ".join(f"{n} first in {nids[n].get('first_phase')} (x{nids[n].get('count')})" for n in new)
        out.append(check("nids", "fail", "new unresolved NID(s): " + det, evidence="game.log"))
    else:
        out.append(check("nids", "pass", f"{len(nids)} unresolved NID(s), all known" if nids else "none"))

    # --- guest faults the runtime survived (null calls, unregistered OPDs):
    # none on a healthy run; QA issue 1 shows up as these on some builds.
    faults = [n for n in run.get("notable", []) if n.get("kind") in FAULT_KINDS]
    if faults:
        first = min(faults, key=lambda n: n.get("t") or 0)
        total = sum(n.get("count", 1) for n in faults)
        out.append(check("guest-faults", "fail",
                         f"{total} line(s); first at {first.get('t') or 0:.0f}s in {first.get('phase')}: {first['line'][:150]}",
                         evidence="game.log"))
    else:
        out.append(check("guest-faults", "pass", "no null calls/reads/writes or unregistered OPDs"))

    # --- memory
    out.append(memory_check(run, th))
    return out


FAULT_KINDS = ("null-call", "opd")


def phase_at(phases, t):
    for name, _k, s, e in phases:
        if s <= t <= (e if e is not None else t):
            return name
    return "?"


def memory_check(run, th):
    mem = [m for m in run.get("mem", []) if m[0] is not None]
    if len(mem) < 3:
        return check("memory", "skip", "fewer than 3 samples")
    phases = run.get("phases", [])
    # Baseline: the first sample once the title is up and boot allocations are
    # done (at least 20 s after the first presented frame).
    t_base = next((p[2] for p in phases if p[1] in ("title", "menu", "idle", "attract")), None)
    fps_t = [f[0] for f in run.get("fps", []) if f[0] is not None]
    if fps_t:
        t_base = max(t_base or 0.0, fps_t[0] + 20.0)
    base = next((m for m in mem if t_base is not None and m[0] >= t_base), mem[len(mem) // 3])
    after = [m for m in mem if m[0] >= base[0]]
    peak = max(after, key=lambda m: m[3])
    growth = peak[3] - base[3]
    detail = f"private {base[3]:.0f} MB at {base[0]:.0f}s -> peak {peak[3]:.0f} MB at {peak[0]:.0f}s (+{growth:.0f} MB)"
    status = "pass" if growth <= th["mem_growth_mb"] else "fail"
    # Long runs: the second half should be flat-ish.
    span = mem[-1][0] - mem[0][0]
    if span >= 300:
        half = [m for m in mem if m[0] >= mem[0][0] + span / 2]
        if len(half) >= 2:
            slope = (half[-1][3] - half[0][3]) / max(1e-6, (half[-1][0] - half[0][0]) / 60.0)
            detail += f"; second half {slope:+.1f} MB/min"
            if slope > th["mem_slope_mb_min"]:
                status = "fail"
    return check("memory", status, detail, evidence="mem.tsv", value=round(growth, 1), limit=th["mem_growth_mb"])


# ------------------------------------------------------------ known issues
def _matches(k, test, c):
    return (fnmatch.fnmatch(test, k.get("test", "*")) and fnmatch.fnmatch(c["id"], k.get("check", "*"))
            and (not k.get("detail") or re.search(k["detail"], c.get("detail", ""))))


def apply_known(test, checks, known_failures):
    """Mark failures listed in known_issues.json. Each entry:
    {"issue": "QA-1", "test": "title_twice", "check": "picture.title3*",
     "detail": "<optional regex on the check's detail>", "note": ...,
     "expect": "fail" (default) | "maybe"}
    test/check are fnmatch patterns. A failing check that matches becomes
    known-fail. An issue none of whose entries for this test matched a
    failure gets one extra check known.<issue> = xpass (it did not reproduce),
    unless all its entries say expect "maybe". Returns the list."""
    seen = {}                                   # issue -> reproduced?
    expect_fail = {}
    for k in known_failures:
        if fnmatch.fnmatch(test, k.get("test", "*")):
            seen.setdefault(k["issue"], False)
            expect_fail[k["issue"]] = expect_fail.get(k["issue"], False) or k.get("expect", "fail") == "fail"
    for c in checks:
        if c["status"] != "fail":          # a WARN (unreliable under load) is not evidence either way
            continue
        for k in known_failures:
            if _matches(k, test, c):
                c["issue"] = k["issue"]
                c["status"] = "known-fail"
                seen[k["issue"]] = True
                break
    for issue, reproduced in seen.items():
        if not reproduced and expect_fail.get(issue):
            note = next((k.get("note", "") for k in known_failures if k["issue"] == issue), "")
            checks.append(dict(check(f"known.{issue}", "xpass",
                                     f"{issue} did not reproduce in this test: {note[:160]}"), issue=issue))
    return checks


def test_status(checks):
    """Worst status of a test: fail > warn > known-fail > xpass > pass."""
    sts = {c["status"] for c in checks}
    for s in ORDER:
        if s in sts:
            return s if s in ("fail", "warn", "known-fail", "xpass") else "pass"
    return "pass"


def known_nid_set(known):
    return set(known.get("nids", {}))
