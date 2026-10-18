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
M_INIT, M_TITLE, M_OPTION, M_GAME, M_LOGO, M_SELECT, M_END, M_RANKING, M_RESULT, M_ONLINE = 0, 1, 3, 4, 5, 6, 8, 10, 11, 13
P2_HEALTH = 0x10090FBC          # i16, CPU's current health in arcade (build/au/GAPS.md "Endings")
# What each main-menu entry leads to: the select mode with this game type (0x1008EBAC), or a mode
GAME_TYPE_OF = {0: 0, 1: 1, 2: 4, 5: 10}                  # ARCADE, GHOST, VS, PRACTICE
MODE_OF = {7: 3, 3: 13}                                    # OPTIONS, ONLINE


def entered_entry(mode, game_type):
    """The main-menu entry a mode change (and game type) shows, or None when unknown."""
    if mode == M_SELECT and game_type is not None:
        for e, t in GAME_TYPE_OF.items():
            if t == game_type:
                return e
        return None
    for e, md in MODE_OF.items():
        if md == mode:
            return e
    return None


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
                    btn, _, pad = b.partition("@")             # "CIRCLE@2": player 2
                    self.g.press(*btn.split("+"), gap=60, pad=int(pad or 1))
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
                    btn, _, pad = b.partition("@")             # "CIRCLE@2": player 2
                    self.g.press(*btn.split("+"), gap=60, pad=int(pad or 1))
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
            if g.mode in (M_SELECT, M_OPTION, M_ONLINE):  # a mode's own menus: back out
                g.press("CIRCLE", gap=150)
                g.press2("CIRCLE", gap=150)
            else:
                g.press("START", gap=300)
        g.expect("menu", False, f"main menu not recognised in {timeout:.0f}s (mode {g.mode} {g.mode_name})")
        return False

    def pick(self, idx, wait=3.0):
        """Main menu entry idx (the cursor position is tracked; it stays where it was left).
        What was entered is checked against the mode / game type the entry leads to; on a
        mismatch (a press lost on a slow PC) the cursor is re-synced from what was entered,
        the driver backs out to the title and tries once more."""
        g = self.g
        for attempt in range(2):
            n = (idx - self.cursor) % len(MENU)
            for _ in range(n):
                g.press("DOWN", gap=450)
            gt0, n0 = g.game_type, len(g.mode_log)
            g.press("CROSS", gap=300)
            m = self.wait_mode_change(timeout=15, start=n0)       # slow under load
            got = entered_entry(m, g.game_type if g.game_type != gt0 or m == M_SELECT else None)
            g.event("menu", f"picked {MENU[idx]} ({n} down): mode {m} {g.mode_name}, game type {gt0} -> {g.game_type}"
                            f" = {MENU[got] if got is not None else '?'}")
            if m in (M_GAME, M_RANKING, M_LOGO) and g.game_type == 2:
                # the title ran into its attract demo instead: the press was lost
                g.expect(f"pick-{MENU[idx].lower()}-{attempt}", False, "the attract demo started instead; retrying")
                if not self.open_menu():
                    return m
                continue
            if got is None or got == idx:
                self.cursor = idx
                g.wait(wait)
                return m
            self.cursor = got
            g.expect(f"pick-{MENU[idx].lower()}-{attempt}", False, f"entered {MENU[got]} instead of {MENU[idx]}; retrying")
            if not (self.back_to_title(taps=("CIRCLE", "CIRCLE@2"), timeout=60) and self.open_menu()):
                return m
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
            g.press("DOWN", "CIRCLE", gap=200, pad=pad)
            i += 1
        return len(g.mode_log) > start


# -------------------------------------------------------------------- scenarios
# Exits found with tools/soak/explore.py (docs/SOAK.md "Menu flows"):
#   ARCADE / GHOST: no pause menu; a lost match -> continue countdown -> rankings
#     (mode 10) -> Namco logo -> the title. The attract demo is the game mode with
#     game type 2. Game types: 0 arcade, 1 ghost, 2 demo, 4 VS, 10 practice.
#   PRACTICE: START -> the practice menu; RETURN TO TITLE SCREEN is the 10th item,
#     then RIGHT (YES) and CROSS.
#   ONLINE: the terms of use; CIRCLE cancels back to the title.
P1_HEALTH = 0x100906EC


def hold_health(d, addr, value=1, every=1.0, until=None, timeout=300.0, attack=True, pad=1, idle_taps=("CROSS", "START")):
    """While the fight HUD is up: write the fighter's health (debug console poke16) about
    every `every` s and attack with `pad`; between fights tap CROSS/START (intros, win
    poses, results). Stops when until() is true or after `timeout`. Returns fights seen."""
    g = d.g
    end = time.perf_counter() + timeout
    fights, in_fight, last_poke = 0, False, 0.0
    while time.perf_counter() < end and not (until and until()):
        f = g.latest_frame() or {}
        if f.get("fight", {}).get("is_fight"):
            if not in_fight:
                fights += 1
                g.event("fight", f"#{fights} (mode {g.mode}, game type {g.game_type})")
            in_fight = True
            if time.perf_counter() - last_poke >= every:
                g.console(f"poke16 {addr:08X} {value:X}")
                last_poke = time.perf_counter()
            if attack:
                g.hold("RIGHT", pad=pad)
                g.wait(0.25)
                g.release(pad=pad)
                g.press("SQUARE", gap=120, pad=pad)
                g.press("DOWN", "CIRCLE", gap=150, pad=pad)
            else:
                g.wait(0.5)
        else:
            in_fight = False
            if not idle_taps:
                g.wait(0.5)
            for b in idle_taps:
                g.press(b, gap=350)
    return fights


def sc_arcade(d, char_moves=(), name="arcade", to_end=True, timeout=1500):
    """ARCADE. to_end: the CPU's health is held at 1, every stage is won up to GAME OVER
    and the title. Otherwise P1 is held at 1 and stands still: the CPU wins (or the
    round times out), the continue countdown runs out, the rankings, the title."""
    g = d.g
    g.phase(f"{name}-select", "menu")
    d.pick(ARCADE)
    g.wait(1.0)
    for mv in char_moves:
        g.press(mv, gap=350)
    g.shot(f"{name}-select", expect="content")
    g.press("CROSS", gap=1500)
    g.phase(f"{name}-run", "fight")
    # after the fighter: ITEM SHOP & EQUIP / GAME START / NAME ENTRY -- CROSS takes GAME START
    if not d.wait_mode(M_GAME, timeout=40, taps=("CROSS",), every=2.0):
        g.expect(f"{name}-start", False, f"ARCADE did not start (mode {g.mode} {g.mode_name})")
        return
    done = lambda: g.mode in (M_RANKING, M_LOGO, M_END, M_TITLE)  # noqa: E731
    if to_end:
        n = hold_health(d, P2_HEALTH, until=done, timeout=timeout)
    else:
        n = hold_health(d, P1_HEALTH, until=done, timeout=timeout, attack=False, idle_taps=())
    g.expect(f"{name}-end", done(), f"{n} fight(s), then mode {g.mode} {g.mode_name}")
    g.shot(f"{name}-end", expect="any", settle=0.5, timeout=3)
    d.wait_mode(M_TITLE, timeout=200, taps=("START",), every=3.0)


def sc_ghost(d, wins=2, timeout=600):
    """GHOST BATTLE: `wins` ghosts beaten (their health held at 1), then P1 at 1 HP
    standing still loses -> rankings -> the title."""
    g = d.g
    g.phase("ghost-select", "menu")
    d.pick(GHOST)
    g.shot("ghost-select", expect="content")
    g.phase("ghost-win", "fight")
    state = {"n": 0}

    def enough():
        return g.mode in (M_RANKING, M_LOGO, M_TITLE) or state["n"] >= wins
    end = time.perf_counter() + timeout
    while not enough() and time.perf_counter() < end:
        n = hold_health(d, P2_HEALTH, timeout=40, until=lambda: g.mode in (M_RANKING, M_LOGO, M_TITLE))
        state["n"] += n
    g.shot("ghost-wins", expect="any", settle=0.5, timeout=3)
    g.phase("ghost-lose", "fight")
    hold_health(d, P1_HEALTH, attack=False, timeout=400, until=lambda: g.mode in (M_RANKING, M_LOGO, M_TITLE),
                idle_taps=())
    g.expect("ghost-end", g.mode in (M_RANKING, M_LOGO, M_TITLE), f"mode {g.mode} {g.mode_name}")
    d.wait_mode(M_TITLE, timeout=200, taps=("START",), every=3.0)


def sc_vs(d, matches=1, timeout=400):
    """VS with both pads: P1 the cursor's fighter, P2 one to the right; P2's health held at 1
    so P1 wins each round fast; after `matches` matches CIRCLE back out to the title."""
    g = d.g
    g.phase("vs-select", "menu")
    d.pick(VS)
    g.shot("vs-select", expect="content")
    g.press("CROSS", gap=1200)
    g.press2("RIGHT", gap=400)
    g.press2("CROSS", gap=600)
    g.wait(2)
    g.phase("vs-fight", "fight")
    sel = {"n": 0}
    end = time.perf_counter() + timeout
    while time.perf_counter() < end and sel["n"] < matches:
        ok = d.until_fight(taps=(("CROSS", 1), ("CROSS", 2), ("START", 1)), timeout=90)
        if not ok:
            break
        g.shot(f"vs-fight{sel['n'] + 1}", expect="fight", settle=1, timeout=3)
        n0 = len(g.mode_log)
        hold_health(d, P2_HEALTH, timeout=240, until=lambda: len(g.mode_log) > n0)
        sel["n"] += 1
        g.event("vs", f"match {sel['n']} over: mode {g.mode} {g.mode_name}")
    g.expect("vs-matches", sel["n"] >= matches, f"{sel['n']} match(es)")
    g.phase("vs-exit", "menu")
    d.back_to_title(taps=("CIRCLE", "CIRCLE@2"), timeout=60)


def sc_online(d):
    g = d.g
    g.phase("online", "menu")
    d.pick(ONLINE)
    ok = d.wait_mode(M_ONLINE, timeout=10)
    g.wait(2)
    g.shot("online-terms", expect="content")
    g.expect("online", ok, "the online mode's terms of use" if ok else f"mode {g.mode}")
    d.back_to_title(taps=("CIRCLE",), timeout=30)


def sc_survival(d, wins=4, timeout=600):
    """SURVIVAL: `wins` opponents beaten (health held at 1), then P1 at 1 HP loses."""
    g = d.g
    g.phase("survival-select", "menu")
    d.pick(SURVIVAL)
    g.shot("survival-select", expect="content")
    g.phase("survival", "fight")
    state = {"n": 0}
    end = time.perf_counter() + timeout
    while state["n"] < wins and time.perf_counter() < end and g.mode not in (M_RANKING, M_LOGO, M_TITLE):
        state["n"] += hold_health(d, P2_HEALTH, timeout=30, until=lambda: g.mode in (M_RANKING, M_LOGO, M_TITLE))
    g.shot("survival-wins", expect="any", settle=0.5, timeout=3)
    g.phase("survival-lose", "fight")
    hold_health(d, P1_HEALTH, attack=False, timeout=400,
                until=lambda: g.mode in (M_RANKING, M_LOGO, M_TITLE, M_RESULT), idle_taps=())
    g.expect("survival-end", g.mode in (M_RANKING, M_LOGO, M_TITLE, M_RESULT), f"mode {g.mode} {g.mode_name}")
    g.shot("survival-end", expect="any", settle=0.5, timeout=3)
    d.wait_mode(M_TITLE, timeout=200, taps=("CROSS", "START"), every=2.0)


def sc_practice(d, seconds=30):
    """PRACTICE: both fighters, `seconds` of attacks, the practice menu, RETURN TO TITLE."""
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
    for _ in range(9):
        g.press("DOWN", gap=350)                    # RETURN TO TITLE SCREEN
    g.press("CROSS", gap=800)
    g.press("RIGHT", gap=600)                       # [No] -> [Yes]
    g.press("CROSS", gap=1500)
    ok = d.wait_mode(M_TITLE, timeout=30)
    g.expect("practice-exit", ok, "practice menu -> RETURN TO TITLE SCREEN" if ok else f"mode {g.mode}")


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
    ok = d.wait_mode(M_TITLE, timeout=30)
    g.expect("gallery-exit", ok, "back at the title" if ok else f"mode {g.mode}")


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
    d.back_to_title(taps=("CIRCLE",), timeout=30)


PLANS = {}


def plan(name):
    def deco(fn):
        PLANS[name] = fn
        return fn
    return deco


def run_one(opts, name, body, probe=True, env=None, keep_gamedata=False, seed=None, console=True, cwd=None):
    d_run = os.path.join(opts.out, name)
    e = {"RSX_SHADER_CACHE_DIR": opts.shader_cache}
    if opts.tag:
        name = f"{name}-{opts.tag}"
        d_run = os.path.join(opts.out, name)
    if probe:
        e.update({"T5_DF_PROBE": "1", "T5_DF_WATCH": "1008EBAC"})
    e.update(env or {})
    g = SoakGame(d_run, cpus=opts.cpus, cpu_offset=opts.cpu_offset, exe=opts.exe, env=e, dump_every=opts.dump_every, mute=opts.mute,
                 abort_hang=60, boot_timeout=90, keep_gamedata=keep_gamedata or opts.keep_gamedata,
                 seed_gamedata=seed or opts.seed_gamedata, cwd=cwd or os.path.join(d_run, "cwd"),
                 console=console and probe)
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
    cwd = os.path.join(opts.out, "modes-cwd")

    def body(d):
        g = d.g
        d.boot_to_title(watch_intro=True)
        # after the intro the title runs the attract demo (a fight) and the rankings by itself
        g.phase("attract", "attract")
        ok = d.wait_mode(M_GAME, timeout=60)
        g.expect("attract-demo", ok and g.game_type == 2, f"attract demo: mode {g.mode}, game type {g.game_type}")
        g.wait(10)
        g.shot("attract-demo", expect="any")
        seq = [("arcade", lambda d: sc_arcade(d, to_end=False)), ("ghost", sc_ghost), ("vs", sc_vs),
               ("online", sc_online), ("survival", sc_survival), ("practice", sc_practice),
               ("gallery", sc_gallery), ("options", sc_options)]
        if opts.scenarios:
            seq = [s for s in seq if s[0] in opts.scenarios.split(",")]
        for name, fn in seq:
            if not d.open_menu():
                continue
            fn(d)
            if g.mode != M_TITLE:
                d.back_to_title(taps=("CIRCLE", "CIRCLE@2", "START"), timeout=90)
        g.wait_log(r"\[cellSaveData\] SAVE complete", timeout=10)
        g.wait(3)
    run_one(opts, "modes", body, cwd=cwd)

    def body2(d):
        import re
        g = d.g
        d.boot_to_title()
        log = g.log_bytes()
        loads = len(re.findall(rb"\[cellSaveData\] LOAD dir='[^']+' \(new=0\)", log))
        g.expect("save-loaded", loads > 0, f"{loads} existing save(s) loaded at the second boot")
        g.wait(5)
    run_one(opts, "modes-reload", body2, keep_gamedata=True, cwd=cwd)


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
    d.back_to_title(taps=("CIRCLE",), timeout=30)


CHAR_MOVES = [(), ("RIGHT", "RIGHT", "RIGHT"), ("DOWN", "LEFT", "LEFT"), ("UP", "RIGHT"), ("DOWN", "DOWN", "RIGHT"),
              ("UP", "LEFT", "LEFT", "LEFT"), ("DOWN", "RIGHT", "RIGHT", "RIGHT", "RIGHT")]


@plan("arcade")
def plan_arcade(opts):
    """EASY, 1 round; ARCADE to the end (boss, GAME OVER, the unlock) with --chars characters."""
    def body(d):
        g = d.g
        d.boot_to_title()
        if d.open_menu():
            set_easy_one_round(d)
        for i in range(opts.chars):
            if not d.open_menu():
                break
            sc_arcade(d, CHAR_MOVES[i % len(CHAR_MOVES)], name=f"arcade{i + 1}", to_end=True)
        g.wait(5)
        g.shot("title-after", expect="any")
    run_one(opts, "arcade", body)


@plan("mixed")
def plan_mixed(opts):
    """--minutes of everything in turn, one process: arcade to the end (a different character
    each time), VS matches, survival, practice, ghost, options, gallery, online terms, idle
    on the title with the attract demo."""
    def body(d):
        g = d.g
        d.boot_to_title()
        k = 0
        end = g.now() + opts.minutes * 60
        while g.now() < end:
            seg = k % 8
            if not d.open_menu():
                d.back_to_title(taps=("CIRCLE", "CIRCLE@2", "START"), timeout=60)
                k += 1
                continue
            g.event("segment", f"#{k} kind {seg}")
            if seg == 0:
                sc_arcade(d, CHAR_MOVES[(k // 8) % len(CHAR_MOVES)], name=f"arcade{k}", to_end=True)
            elif seg == 1:
                sc_vs(d, matches=2)
            elif seg == 2:
                sc_survival(d, wins=3)
            elif seg == 3:
                sc_practice(d, seconds=25)
            elif seg == 4:
                sc_ghost(d, wins=2)
            elif seg == 5:
                sc_options(d, change=(k // 8) % 2 == 0)
            elif seg == 6:
                sc_gallery(d) if (k // 8) % 2 == 0 else sc_online(d)
            else:
                g.phase(f"idle{k}", "attract")       # the title idles into the attract demo and back
                g.wait(90)
            if g.mode != M_TITLE:
                d.back_to_title(taps=("CIRCLE", "CIRCLE@2", "START"), timeout=90)
            k += 1
        g.expect("segments", k >= 8, f"{k} segments in {opts.minutes:.0f} min")
    run_one(opts, "mixed", body)


def sc_online_accept(d):
    """ONLINE BATTLE: the terms (4 pages), YES -> the profile is saved and the game's online
    check runs (sceNp init, the "net ranking" thread, Score/Matching/Signaling contexts,
    cellHttp, manager status OFFLINE) -> "A network error occurred" -> the title."""
    g = d.g
    g.phase("online", "menu")
    d.pick(ONLINE, wait=4.0)
    n0 = g.log_bytes().count(b"net ranking")
    ok = False
    for attempt in range(3):                    # pages ignore presses while they slide (slow under load)
        for i in range(3):
            g.press("RIGHT", gap=1500)
        if attempt == 0:
            g.shot("online-terms", expect="any", settle=0.5, timeout=2)
        g.press("CROSS", gap=3000)              # YES on the last page
        ok = g.wait_log(r"net ranking", timeout=15, count=n0 + 1)
        if ok or g.mode != M_ONLINE:
            break
    g.expect("online-check", ok, "the online check ran (net ranking thread)" if ok else "no online check in 30 s")
    g.wait(8)
    g.shot("online-after", expect="any", settle=0.5, timeout=2)
    for _ in range(6):
        if g.mode == M_TITLE:
            break
        g.press("CROSS", gap=3000)


@plan("ringcheck")
def plan_ringcheck(opts):
    """The second 1.0.0 player's offline path (coordinator, 2026-10-19): boot, the intro to its
    end, the attract demo (the first fight-scene load: the 212-job skinning list), the rankings,
    the title; the main menu, ONLINE (terms, YES: the online check), back at the title, then
    --minutes in the menus. Counted: ring recycles, flips the FIFO walker never reached."""
    def body(d):
        g = d.g
        d.boot_to_title(watch_intro=True)
        g.phase("attract", "attract")
        ok = d.wait_mode(M_GAME, timeout=60)
        g.expect("demo-fight", ok, f"attract demo (first fight load), game type {g.game_type}")
        d.wait_mode(M_TITLE, timeout=150)
        for k in range(max(1, opts.online_repeats)):
            if g.log_bytes().count(b"queued flip never reached"):
                break
            if d.open_menu():
                sc_online_accept(d)
                d.wait_mode(M_TITLE, timeout=60, taps=("CROSS",), every=3.0)
        g.phase("menus", "title")
        end = g.now() + opts.minutes * 60
        while g.now() < end:
            if d.open_menu(timeout=30):
                g.wait(min(20, max(0.0, end - g.now())))
            g.shot(f"menus-{int(g.now()):04d}", expect="any", settle=0.3, timeout=2)
        log = g.log_bytes()
        rec = log.count(b"recycled the title's own ring")
        stall = log.count(b"queued flip never reached")
        g.expect("no-ring-recycle", rec == 0, f"{rec} 'recycled the title's own ring' line(s)")
        g.expect("no-flip-stall", stall == 0, f"{stall} 'queued flip never reached' line(s)")
    run_one(opts, f"ringcheck-{opts.cpus or 'all'}cpu", body, console=False)


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
    ap.add_argument("--cpu-offset", type=int, default=0, help="with --cpus: the first logical processor of the mask")
    ap.add_argument("--chars", type=int, default=3)
    ap.add_argument("--online-repeats", type=int, default=1, help="ringcheck: how often the online check runs")
    ap.add_argument("--scenarios", help="modes: comma-separated subset (arcade,ghost,vs,online,survival,practice,gallery,options)")
    ap.add_argument("--mute", action="store_true", help="PS3_AUDIO_MUTE=1 (the mix is still measured)")
    ap.add_argument("--dump-every", type=int, default=30, help="frame read-back every N flips (navigation needs ~2/s)")
    ap.add_argument("--keep-gamedata", action="store_true")
    ap.add_argument("--seed-gamedata")
    ap.add_argument("--shader-cache")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--tag", help="suffix for the run directory (e.g. the build)")
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
