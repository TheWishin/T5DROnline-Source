#!/usr/bin/env python3
"""Offline soak (docs/SOAK.md): drive every offline mode with scripted pads, run
long sessions, track the process, and scan the log for problems.

    python tools/soak/soak.py PLAN --exe EXE --out DIR [--minutes N] [--cpus N] [--mute]
                              [--keep-gamedata] [--seed-gamedata DIR] [--chars N]
    python tools/soak/soak.py report DIR            # summary.md of a finished run again

Plans
  modes    boot with the intro movie played to its end, the title movie, the
           attract demo and ranking loop, then every main-menu entry: ARCADE (a
           stage, a loss, the continue screen), GHOST, VS (two pads, a full match),
           ONLINE (terms, CANCEL), SURVIVAL (fights until a loss), PRACTICE (pause
           menu, back to the title), GALLERY (offline), OPTIONS (every page, a
           setting changed -> saved), then a second boot that loads the save
  arcade   OPTIONS: EASY, 1 round; then ARCADE to the end with --chars characters
           (the CPU's health is held at 1 through T5_DF_POKE, so a mashing script wins):
           every stage, the boss, GAME OVER, the unlock message; the save keeps it
  idle     --minutes on the title / main menu with no input (title, attract demo,
           rankings and the Namco logo cycle by themselves) -- no probe, as a player
  mixed    --minutes of everything in turn: arcade stages, VS matches, survival,
           practice, ghost, options, idle at the title

Every game: muted only with --mute, minimized (PS3_WINDOW_BACKGROUND=1), below-normal
priority, scripted pads, frames read back by the runtime (LD_FRAME_DUMP) -- nothing on
the desktop changes, the clipboard is never touched. --cpus N: affinity to the first N
logical processors and PS3_CPUS=N. Navigation reads the game's mode manager through the
direct-fight probe (T5_DF_PROBE=1, T5_DF_WATCH=1008EBAC: read-only notes in the log);
the idle plan runs without it.

Out: <out>/<run>/game.log, events.tsv, resources.tsv (every 10 s: handles, threads,
private MB, working set, GDI/USER, CPU s, fps, system load, other games/compilers),
frames/ (small JPEGs), *.png (named shots), problems.json, summary.md; <out>/summary.md.
Frames and shots are game content: keep them out of git.
"""
import argparse
import json
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import problems  # noqa: E402
from soakgame import Abort, SoakGame, find_game_root  # noqa: E402

# Main menu (cursor starts on ARCADE; it wraps and stays where it was left)
ARCADE, GHOST, VS, ONLINE, SURVIVAL, PRACTICE, GALLERY, OPTIONS = range(8)
MENU = ["ARCADE", "GHOST", "VS", "ONLINE", "SURVIVAL", "PRACTICE", "GALLERY", "OPTIONS"]
# Mode manager ids (tcb_*mode_t classes, from the probe)
M_INIT, M_TITLE, M_GAME, M_LOGO, M_SELECT, M_END, M_RANKING, M_RESULT, M_ONLINE = 0, 1, 4, 5, 6, 8, 10, 11, 13
P2_HEALTH = 0x10090FBC          # i16, CPU's current health in arcade (build/au/GAPS.md "Endings")


class Driver:
    """Scenario helpers over one SoakGame with the probe on."""

    def __init__(self, g):
        self.g = g
        self.cursor = ARCADE

    # ---------------------------------------------------------------- waiting
    def wait_mode(self, modes, timeout=60.0, taps=None, every=1.0):
        """Wait until the mode manager is in one of `modes`; tap `taps` every `every` s meanwhile."""
        if isinstance(modes, int):
            modes = (modes,)
        end = time.perf_counter() + timeout
        while time.perf_counter() < end:
            if self.g.mode in modes:
                return True
            if taps:
                for b in taps:
                    self.g.press(*b.split("+"), gap=60)
                self.g.wait(max(0.0, every - 0.16 * len(taps)))
            else:
                self.g.wait(0.2)
        return self.g.mode in modes

    def wait_mode_change(self, timeout=60.0, taps=None, every=1.0, start=None):
        start = len(self.g.mode_log) if start is None else start
        end = time.perf_counter() + timeout
        while time.perf_counter() < end:
            if len(self.g.mode_log) > start:
                return self.g.mode
            if taps:
                for b in taps:
                    self.g.press(*b.split("+"), gap=60)
                self.g.wait(max(0.0, every - 0.16 * len(taps)))
            else:
                self.g.wait(0.2)
        return None

    # ---------------------------------------------------------------- title / menu
    def boot_to_title(self, watch_intro=False):
        """Boot; with watch_intro the intro movie plays to its end (no START)."""
        g = self.g
        g.phase("boot", "boot")
        ok = self.wait_mode(M_TITLE, timeout=90)
        g.expect("boot", ok, f"title mode after {g.now():.0f}s" if ok else "no title mode in 90 s")
        if watch_intro:
            g.phase("intro-movie", "attract")
            done = g.wait_log(r"\[cellVdec\] Close\(", timeout=150)
            g.expect("intro-played", done, "intro movie decoded to its end" if done else "intro did not end in 150 s",
                     evidence="game.log")
        return ok

    def menu_state(self, since, need=2):
        """'menu' / 'press_start' / None from the last `need` read-back frames after `since`."""
        fr = [f["fight"]["title"] for f in self.g.frames_since(since)
              if isinstance(f.get("fight", {}).get("title"), dict)]
        if len(fr) < need:
            return None
        # lightning flashes wash single frames out: one clear menu frame and no PRESS START is enough
        if any(x.get("menu") for x in fr) and not any(x.get("press_start") for x in fr[-need:]):
            return "menu"
        if any(x.get("press_start") for x in fr[-need:]):
            return "press_start"
        return None

    def open_menu(self, timeout=90.0):
        """From anywhere (the intro or title movie, PRESS START, the attract demo, the
        rankings): to the title's main menu. START skips movies, the demo and the rankings
        and opens the menu from PRESS START; the menu itself is recognised by frame
        (title_menu_check), so START is never pressed on it (it would pick the item)."""
        g = self.g
        end = time.perf_counter() + timeout
        while time.perf_counter() < end:
            t = g.now()
            g.wait(2.2)                   # two read-back frames (dump every 60 flips)
            st = self.menu_state(t)
            if st == "menu" and g.mode == M_TITLE:
                g.phase("menu", "title")
                g.wait(1.0)               # the menu ignores input while it slides in
                return True
            g.press("START", gap=300)
        g.expect("menu", False, f"main menu not recognised in {timeout:.0f}s (mode {g.mode} {g.mode_name})")
        return False

    def pick(self, idx, wait=3.0):
        """Main menu entry idx (the cursor position is tracked; it stays where it was left)."""
        g = self.g
        n = (idx - self.cursor) % len(MENU)
        for _ in range(n):
            g.press("DOWN", gap=450)
        gt0, n0 = g.game_type, len(g.mode_log)
        g.press("CROSS", gap=300)
        self.cursor = idx
        m = self.wait_mode_change(timeout=8, start=n0)
        g.event("menu", f"picked {MENU[idx]} ({n} down): mode {m} {g.mode_name}, game type {gt0} -> {g.game_type}")
        g.wait(wait)
        return m

    def back_to_title(self, taps=("CIRCLE",), timeout=60.0):
        ok = self.wait_mode(M_TITLE, timeout=timeout, taps=taps, every=1.5)
        self.g.expect(f"title-again-{len(self.g.expects)}", ok,
                      "back in the title mode" if ok else f"not back at the title in {timeout:.0f}s")
        return ok

    # ---------------------------------------------------------------- fights
    def until_fight(self, taps=(("CROSS", 1), ("START", 1)), timeout=60.0):
        g = self.g
        t = g.until_fight(timeout=timeout, taps=taps, need=2)
        return t is not None

    def fight(self, seconds, two_pads=False, p2_attacks=False, name="fight"):
        """P1 walks in and attacks; with two_pads P2 does the same (p2_attacks: only P2)."""
        g = self.g
        t_end = g.now() + seconds
        i = 0
        while g.now() < t_end:
            if not p2_attacks:
                g.hold("RIGHT")
            if two_pads or p2_attacks:
                g.hold("LEFT", pad=2)
            g.wait(0.4)
            g.release()
            g.release(pad=2)
            for b in ("SQUARE", "TRIANGLE", "CROSS") if i % 2 == 0 else ("CIRCLE", "SQUARE"):
                if not p2_attacks:
                    g.press(b, gap=150)
                if two_pads or p2_attacks:
                    g.press2(b, gap=150)
            g.wait(0.6)
            i += 1

    def mash_until_mode_change(self, timeout, pad=1):
        """Attack (pad 1) until the mode manager changes mode."""
        g = self.g
        start = len(g.mode_log)
        end = time.perf_counter() + timeout
        i = 0
        while time.perf_counter() < end and len(g.mode_log) == start:
            g.hold("RIGHT", pad=pad)
            g.wait(0.3)
            g.release(pad=pad)
            for b in ("SQUARE", "TRIANGLE", "CROSS", "CIRCLE")[i % 2:][:3]:
                g.press(b, gap=120, pad=pad)
            g.press("DOWN+CIRCLE", gap=200, pad=pad)
            i += 1
        return len(g.mode_log) > start


# -------------------------------------------------------------------- scenarios
def sc_arcade_loss(d):
    """ARCADE: a character, a stage where P1 stands still and loses, the continue
    countdown runs out -> the rankings -> Namco logo -> the title."""
    g = d.g
    g.phase("arcade-select", "menu")
    d.pick(ARCADE)
    g.shot("arcade-select", expect="content")
    ok = d.until_fight(taps=(("CROSS", 1),))       # CROSS confirms; arcade intros are not skipped
    g.expect("arcade-fight", ok, "arcade fight HUD" if ok else "no arcade fight")
    if not ok:
        return
    g.phase("arcade-fight", "fight")
    g.shot("arcade-fight", expect="fight")
    g.phase("arcade-lose", "fight")
    # P1 does nothing: the CPU wins the stage, the continue screen times out, GAME OVER.
    ok = d.wait_mode((M_RANKING, M_TITLE, M_LOGO), timeout=180)
    g.expect("arcade-over", ok, f"after the loss: mode {g.mode} {g.mode_name}")
    g.shot("arcade-after", expect="any")
    if g.mode == M_RANKING:
        g.phase("rankings", "attract")
    d.wait_mode(M_TITLE, timeout=150)


def sc_ghost(d):
    g = d.g
    g.phase("ghost-select", "menu")
    d.pick(GHOST)
    g.shot("ghost-select", expect="content")
    ok = d.until_fight()
    g.expect("ghost-fight", ok, "ghost fight HUD" if ok else "no ghost fight")
    if not ok:
        return
    g.phase("ghost-fight", "fight")
    g.shot("ghost-fight", expect="fight")
    won = d.mash_until_mode_change(120)
    g.phase("ghost-after", "menu")
    g.shot("ghost-after", expect="any")
    g.event("ghost", f"fight ended: {won}, mode {g.mode} {g.mode_name}")


def sc_vs(d, seconds=None):
    """VS with both pads: P1 picks the cursor's fighter, P2 the one to the right; a full
    match (P1 attacks, P2 stands); the game goes back to the select screen."""
    g = d.g
    g.phase("vs-select", "menu")
    d.pick(VS)
    g.shot("vs-select", expect="content")
    g.press("CROSS", gap=1200)
    g.press2("RIGHT", gap=400)
    g.press2("CROSS", gap=600)
    g.wait(3)
    ok = d.until_fight(taps=(("CROSS", 1), ("CROSS", 2), ("START", 1)))
    g.expect("vs-fight", ok, "VS fight HUD" if ok else "no VS fight")
    if not ok:
        return
    g.phase("vs-fight", "fight")
    g.shot("vs-fight", expect="fight")
    ended = d.mash_until_mode_change(seconds or 240)
    g.phase("vs-after", "menu")
    g.shot("vs-after", expect="any")
    g.event("vs", f"match ended: {ended}, mode {g.mode} {g.mode_name}")


def sc_online(d):
    g = d.g
    g.phase("online", "menu")
    d.pick(ONLINE)
    ok = d.wait_mode(M_ONLINE, timeout=10)
    g.shot("online-terms", expect="content")
    g.expect("online", ok, "the online mode's terms of use" if ok else f"mode {g.mode}")


def sc_survival(d, seconds=90):
    g = d.g
    g.phase("survival-select", "menu")
    d.pick(SURVIVAL)
    g.shot("survival-select", expect="content")
    ok = d.until_fight()
    g.expect("survival-fight", ok, "survival fight HUD" if ok else "no survival fight")
    if not ok:
        return
    g.phase("survival", "fight")
    g.shot("survival-fight", expect="fight")
    d.mash_until_mode_change(seconds)
    g.phase("survival-end", "fight")
    g.shot("survival-end", expect="any")


def sc_practice(d, seconds=30):
    g = d.g
    g.phase("practice-select", "menu")
    d.pick(PRACTICE)
    g.shot("practice-select", expect="content")
    ok = d.until_fight(taps=(("CROSS", 1),))
    g.expect("practice-fight", ok, "practice HUD" if ok else "no practice fight")
    if not ok:
        return
    g.phase("practice", "fight")
    g.shot("practice-fight", expect="fight")
    d.fight(seconds)
    g.phase("practice-menu", "menu")
    g.press("START", gap=1500)
    g.shot("practice-menu", expect="content")


def sc_gallery(d):
    g = d.g
    g.phase("gallery", "menu")
    d.pick(GALLERY)
    g.wait(3)
    g.shot("gallery-retry", expect="content")       # "Unable to update content list. Retry update?"
    g.press("RIGHT", gap=500)                        # NO
    g.press("CROSS", gap=2500)
    g.shot("gallery-return", expect="content")      # "... Return to Title Screen?"
    g.press("CROSS")                                 # YES


def sc_options(d, change=True):
    """OPTIONS: GAME OPTIONS, SOUND OPTIONS (BGM +1), CONTROLLER SETUP, EXIT (from tools/smoke)."""
    g = d.g
    g.phase("options", "menu")
    d.pick(OPTIONS, wait=2.5)
    g.shot("options", expect="content")
    g.press("CROSS", gap=1500)
    g.shot("options-game", expect="content")
    g.wait(1.0)
    g.press("CIRCLE", gap=1500)
    g.press("DOWN", gap=400)
    g.press("CROSS", gap=1500)
    g.press("DOWN", gap=400)
    if change:
        g.press("RIGHT", gap=600)
    g.shot("options-sound", expect="content")
    g.press("CIRCLE", gap=1500)
    g.press("DOWN", gap=400)
    g.press("CROSS", gap=1500)
    g.shot("options-controller", expect="content")
    g.wait(1.0)
    g.press("DOWN", gap=400)
    g.press("DOWN", gap=400)
    g.press("CROSS", gap=1500)
    for _ in range(3):
        g.press("DOWN", gap=400)
    g.press("CROSS")


PLANS = {}


def plan(name):
    def deco(fn):
        PLANS[name] = fn
        return fn
    return deco


def run_one(opts, name, body, probe=True, env=None, keep_gamedata=False, seed=None):
    d_run = os.path.join(opts.out, name)
    e = {"RSX_SHADER_CACHE_DIR": opts.shader_cache}
    if probe:
        e.update({"T5_DF_PROBE": "1", "T5_DF_WATCH": "1008EBAC"})
    e.update(env or {})
    g = SoakGame(d_run, cpus=opts.cpus, exe=opts.exe, env=e, dump_every=opts.dump_every, mute=opts.mute,
                 abort_hang=60, boot_timeout=90, keep_gamedata=keep_gamedata or opts.keep_gamedata,
                 seed_gamedata=seed or opts.seed_gamedata, cwd=os.path.join(opts.out, "cwd"))
    err = None
    print(f"== {name}: {d_run}", flush=True)
    try:
        g.start()
        body(Driver(g))
    except Abort as e:
        err = f"aborted: {e}"
    except Exception as e:  # a scenario bug must not lose the run's data
        import traceback
        traceback.print_exc()
        err = f"error: {e!r}"
    res = g.stop()
    finalize(d_run, g, res, err)
    return res


def finalize(d_run, g, res, err=None):
    with open(os.path.join(d_run, "game.log"), encoding="utf-8", errors="replace") as f:
        pr = problems.scan(f.read())
    pr["run"] = {"duration_s": res.get("duration"), "exit_code": res.get("exit_code"), "aborted": res.get("aborted"),
                 "error": err, "expects": res.get("expects"), "modes": getattr(g, "mode_log", []),
                 "resources": [(t, ph, r, fps) for t, ph, r, fps in getattr(g, "res", [])],
                 "phases": res.get("phases"), "contention": res.get("contention")}
    with open(os.path.join(d_run, "problems.json"), "w", encoding="utf-8") as f:
        json.dump(pr, f, indent=1, default=str)
    write_summary(d_run, pr)


def trend(rows, key):
    """(first, last, min, max, slope per hour over the second half) of one resource column."""
    pts = [(t, r[key]) for t, _, r, _ in rows if r.get(key) is not None]
    if len(pts) < 2:
        return None
    vals = [v for _, v in pts]
    half = pts[len(pts) // 2:]
    n = len(half)
    mt = sum(t for t, _ in half) / n
    mv = sum(v for _, v in half) / n
    var = sum((t - mt) ** 2 for t, _ in half)
    slope = sum((t - mt) * (v - mv) for t, v in half) / var * 3600 if var else 0.0
    return {"first": pts[0][1], "last": pts[-1][1], "min": min(vals), "max": max(vals), "per_hour_2nd_half": round(slope, 1)}


def write_summary(d_run, pr):
    run = pr["run"]
    rows = run["resources"]
    lines = [f"# {os.path.basename(d_run)}", "",
             f"duration {run['duration_s']} s, exit {run['exit_code']}, aborted {run['aborted']}, error {run['error']}", ""]
    lines.append("## Resources (every 10 s; slope over the second half)")
    lines.append("")
    lines.append("| | first | last | min | max | per hour (2nd half) |")
    lines.append("|---|---|---|---|---|---|")
    for k in ("handles", "threads", "private_mb", "ws_mb", "gdi", "user"):
        tr = trend(rows, k)
        if tr:
            lines.append(f"| {k} | {tr['first']} | {tr['last']} | {tr['min']} | {tr['max']} | {tr['per_hour_2nd_half']} |")
    busy = [r.get("sys_busy") for _, _, r, _ in rows if r.get("sys_busy") is not None]
    games = [r.get("games", 0) for _, _, r, _ in rows]
    if busy:
        lines.append("")
        lines.append(f"system load during the run: median {sorted(busy)[len(busy) // 2]} %, max {max(busy)} %; "
                     f"other t5dr.exe up to {max(games) if games else 0}")
    lines += ["", "## Log", "", "```", problems.summary(pr), "```", ""]
    lines.append("## Milestones")
    lines.append("")
    for e in run.get("expects") or []:
        lines.append(f"- {'ok' if e['ok'] else 'FAILED'} {e['name']} ({e['t']} s): {e['detail']}")
    lines.append("")
    lines.append("## Modes")
    lines.append("")
    for t, f, cur, nxt, name in run.get("modes") or []:
        lines.append(f"- {t:.1f} s frame {f}: {cur} {name}")
    with open(os.path.join(d_run, "summary.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# -------------------------------------------------------------------- plans
@plan("modes")
def plan_modes(opts):
    def body(d):
        g = d.g
        d.boot_to_title(watch_intro=True)
        # the title movie, then the title idles into the attract demo / rankings and back
        g.phase("title-idle", "attract")
        g.wait(60)
        g.shot("title-idle", expect="any")
        seq = [("arcade", sc_arcade_loss), ("ghost", sc_ghost), ("vs", sc_vs), ("online", sc_online),
               ("survival", sc_survival), ("practice", sc_practice), ("gallery", sc_gallery), ("options", sc_options)]
        for name, fn in seq:
            if not d.open_menu():
                g.expect(f"{name}-menu", False, f"main menu not reached (mode {g.mode} {g.mode_name})")
                continue
            fn(d)
            d.back_to_title(taps=("CIRCLE",) if name not in ("practice",) else ("CIRCLE", "START"))
        g.wait_log(r"\[cellSaveData\] SAVE complete", timeout=10)
        g.wait(3)
    run_one(opts, "modes", body)

    def body2(d):
        g = d.g
        d.boot_to_title()
        import re
        log = g.log_bytes()
        loads = len(re.findall(rb"\[cellSaveData\] LOAD dir='[^']+' \(new=0\)", log))
        g.expect("save-loaded", loads > 0, f"{loads} existing save(s) loaded at the second boot")
        g.wait(5)
    run_one(opts, "modes-reload", body2, keep_gamedata=True)


def poke_env(start=600, end=400000, every=60, budget=30000):
    """T5_DF_POKE entries that hold the CPU's health (P2, i16 0x10090FBC) at 1: one write every
    `every` frames. The variable is capped at ~30 KB (Windows allows 32 K characters), so a long
    run thins the writes out instead of stopping early."""
    n = (end - start) // every
    while n * 20 > budget:
        every *= 2
        n = (end - start) // every
    return ",".join(f"{f}:{P2_HEALTH:08X}:2:1" for f in range(start, end, every))


def set_easy_one_round(d):
    """OPTIONS > GAME OPTIONS: difficulty EASY (LEFT from MEDIUM), rounds 1; EXIT saves."""
    g = d.g
    g.phase("options-easy", "menu")
    d.pick(OPTIONS, wait=2.5)
    g.press("CROSS", gap=1500)                  # GAME OPTIONS
    g.wait(1.0)
    g.press("LEFT", gap=400)                    # MEDIUM -> EASY
    g.press("DOWN", gap=400)
    g.press("LEFT", gap=400)                    # rounds 2 -> 1
    g.shot("options-easy", expect="content")
    g.press("CIRCLE", gap=1500)
    for _ in range(5):
        g.press("DOWN", gap=400)                # EXIT
    g.press("CROSS", gap=2500)
    d.back_to_title()


def sc_arcade_to_end(d, char_moves=(), name="arcade", timeout=1500):
    """ARCADE with the CPU at 1 HP (T5_DF_POKE): every stage to GAME OVER and the title.
    char_moves: cursor moves on the select screen before CROSS."""
    g = d.g
    g.phase(f"{name}-select", "menu")
    d.pick(ARCADE)
    g.wait(1.0)
    for mv in char_moves:
        g.press(mv, gap=350)
    g.shot(f"{name}-select", expect="content")
    g.press("CROSS", gap=1500)
    g.phase(f"{name}-run", "fight")
    end = time.perf_counter() + timeout
    k = fights = 0
    in_fight = False
    stages = set()
    while time.perf_counter() < end:
        if g.mode in (M_RANKING, M_LOGO, M_END) or (g.mode == M_TITLE and k > 10):
            break
        f = g.latest_frame() or {}
        if f.get("fight", {}).get("is_fight"):
            if not in_fight:
                fights += 1
                g.event("arcade", f"fight {fights}")
                if fights % 2 == 1:
                    g.shot(f"{name}-fight{fights:02d}", expect="fight", settle=2, timeout=4)
            in_fight = True
            g.hold("RIGHT")
            g.wait(0.3)
            g.release()
            g.press("SQUARE", gap=150)
            g.press("TRIANGLE", gap=150)
            g.press("DOWN+CIRCLE", gap=200)
        else:
            in_fight = False
            g.press("CROSS", gap=400)               # intros, win poses, "next battle"
            g.press("START", gap=400)
        k += 1
        if k % 40 == 0:
            g.shot(f"{name}-{int(g.now()):04d}", expect="any", settle=0.3, timeout=2)
    g.expect(f"{name}-end", g.mode in (M_RANKING, M_LOGO, M_END, M_TITLE),
             f"{fights} fights, then mode {g.mode} {g.mode_name}")
    g.shot(f"{name}-end", expect="any", settle=0.5, timeout=3)
    d.wait_mode(M_TITLE, timeout=200, taps=("START",), every=3.0)


@plan("arcade")
def plan_arcade(opts):
    chars = [(), ("RIGHT", "RIGHT", "RIGHT"), ("DOWN", "LEFT", "LEFT"), ("UP", "RIGHT"), ("DOWN", "DOWN", "RIGHT")]

    def body(d):
        g = d.g
        d.boot_to_title()
        d.open_menu()
        set_easy_one_round(d)
        for i in range(opts.chars):
            if not d.open_menu():
                break
            sc_arcade_to_end(d, chars[i % len(chars)], name=f"arcade{i + 1}")
        g.wait(5)
        g.shot("title-after", expect="any")
    run_one(opts, "arcade", body, env={"T5_DF_POKE": poke_env(end=3000 + opts.chars * 30000)})


@plan("idle")
def plan_idle(opts):
    def body(d):
        g = d.g
        g.phase("idle", "idle")
        g.wait(25)
        # START twice: skip the intro, open the main menu; then nothing for --minutes.
        g.press("START", gap=1500)
        g.press("START", gap=1500)
        end = g.now() + opts.minutes * 60
        k = 0
        while g.now() < end:
            g.wait(min(30, end - g.now()))
            k += 1
            if k % 4 == 0:
                g.shot(f"idle-{int(g.now()):05d}s", expect="any", settle=0.5, timeout=3)
    run_one(opts, "idle", body, probe=False)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plan", choices=sorted(PLANS) + ["report"])
    ap.add_argument("dir", nargs="?", help="report: the run directory")
    ap.add_argument("--exe")
    ap.add_argument("--out")
    ap.add_argument("--minutes", type=float, default=30)
    ap.add_argument("--cpus", type=int)
    ap.add_argument("--chars", type=int, default=3)
    ap.add_argument("--mute", action="store_true", help="PS3_AUDIO_MUTE=1 (the mix is still measured)")
    ap.add_argument("--dump-every", type=int, default=30, help="frame read-back every N flips (navigation needs ~2/s)")
    ap.add_argument("--keep-gamedata", action="store_true")
    ap.add_argument("--seed-gamedata")
    ap.add_argument("--shader-cache")
    ap.add_argument("--seed", type=int, default=1)
    opts = ap.parse_args()
    random.seed(opts.seed)
    if opts.plan == "report":
        pj = os.path.join(opts.dir, "problems.json")
        with open(pj, encoding="utf-8") as f:
            write_summary(opts.dir, json.load(f))
        print(open(os.path.join(opts.dir, "summary.md"), encoding="utf-8").read())
        return 0
    root = find_game_root()
    opts.exe = os.path.abspath(opts.exe or os.path.join(root, "build", "cmake", "t5dr.exe"))
    opts.out = os.path.abspath(opts.out or os.path.join(root, "build", "soak", time.strftime("%Y%m%d-%H%M%S")))
    opts.shader_cache = opts.shader_cache or os.path.join(opts.out, "shader_cache")
    os.makedirs(opts.shader_cache, exist_ok=True)
    os.makedirs(opts.out, exist_ok=True)
    PLANS[opts.plan](opts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
