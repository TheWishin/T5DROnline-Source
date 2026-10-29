#!/usr/bin/env python3
"""Shader warm-up after BUILD GAME (1.1.5; docs/RENDER_PERF.md "2-core mode and slow graphics cards", part
"Shader warm-up").

    python tools/shader_warmup.py [--out DIR] [--fights N] [--fight-seconds S] [--minutes M] [--force]

A fresh build meets every pipeline once: the renderer decompiles the game's RSX programs into HLSL, compiles
them (D3DCompile) and the driver builds the pipeline -- on the render translation's thread, during the first
fights on every stage (a player's i5-2500 log: 300+ frames slowed by the translation in its first 30 s). The
caches survive the game: <out>/scratch/rsx_shader_cache_v2 holds the compiled shaders, the driver's pipeline
library and the list of pipelines the next start re-creates on a background thread (patch 0023).

This plays those first fights for the player, right after BUILD GAME: the built game, minimised, muted, at
below-normal priority, as one persistent game (T5_CTL_DIR, docs/DIRECTFIGHT.md "Persistent game"): a "fight"
on a stage with two fighters (offline, nobody presses a button), FIGHT START + --fight-seconds, "idle" (back to
a fresh select screen), the next fight, ... "quit". It runs where the launcher starts the game
(run_game.game_command: <out> is the working directory), so the caches are the ones the player's games use.
The fights cover every stage of the stage select (ids 17-34) with the 35 fighters of the select screen (two a
fight; Jinpachi needs an unlock offline), then the Tekken 5 stages (ids 0-13, 15) as far as --fights allows.

Never fails a build: a game that does not start, stops or gets stuck ends the warm-up with a note and exit
code 0; the first fights then build their pipelines as before. warmup.json in the cache folder (the game's
size and time stamp) makes it run once per build; --force runs it again.

Lines it prints: "[warmup] fight 3 of 18: stage 19, lei vs king" (the launcher's Build tab shows them).

Skip (the Build tab's "Skip warm-up" while this step runs): the launcher creates <out>/logs/warmup.skip
(SKIP_FILE). Within a quarter of a second the warm-up ends as after its last fight -- the game is asked to quit
(killed only if it does not within 20 s), warmup.json says "skipped" so the next BUILD GAME of the same game
does not start it again ("Redo every step" does), and exit code 0: the build ends as built, the game works, and
the first fights build the shaders that were not warmed.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "lobby"))
import run_game  # noqa: E402

# Stage select ids first (what ranked and quick matches draw), then the Tekken 5 stages (lobby fighters.json).
STAGES = list(range(17, 35)) + list(range(0, 14)) + [15]
FIGHTERS = 35   # ids 0-34: Jinpachi (35) is not selectable offline without his unlock -- his fight never started
# P1 presses during each fight (as tools/fight_bench.py): the fighters move, hit and block, so the hit sparks and
# effects of a real fight are drawn too -- with idle fighters a warmed stage still met ~10 new pipelines.
PAD = ["RIGHT", "SQUARE", "", "TRIANGLE", "", "CROSS", "", "RIGHT", "CIRCLE", "", "LEFT", "", "SQUARE", "",
       "SQUARE TRIANGLE", ""]
CACHE = os.path.join("scratch", "rsx_shader_cache_v2")
MARKER = "warmup.json"
SKIP_FILE = os.path.join("logs", "warmup.skip")     # (launcher/core.py BuildRun.skip_warmup writes the same path)
STALE_SKIP = 60.0                                   # an older skip file is left over from another run


class Skipped(Exception):
    """The player pressed Skip warm-up."""


def skip_requested(path):
    return bool(path) and os.path.exists(path)


def fight_lines(n):
    """n fight lines "p1,p2,stage,1": stage after stage, the fighters two by two (all 35 in the first 18)."""
    out = []
    for i in range(min(n, len(STAGES))):
        p1, p2 = (2 * i) % FIGHTERS, (2 * i + 1) % FIGHTERS
        out.append((STAGES[i], p1, p2, f"{p1},{p2},{STAGES[i]},1"))
    return out


def exe_stamp(exe):
    st = os.stat(exe)
    return {"size": st.st_size, "mtime": int(st.st_mtime)}


def read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def note(msg):
    print(f"[warmup] {msg}", flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=ROOT, help="the build's output root (build_game.py --out)")
    ap.add_argument("--fights", type=int, default=18, help="how many fights (18 = every stage of the stage select)")
    ap.add_argument("--fight-seconds", type=float, default=6.0, help="seconds of each fight after FIGHT START")
    ap.add_argument("--minutes", type=float, default=12.0, help="give up after this long")
    ap.add_argument("--force", action="store_true", help="run again although warmup.json says it ran for this build")
    ap.add_argument("env", nargs="*", help="extra NAME=VALUE for the game (tests)")
    a = ap.parse_args()
    out = os.path.abspath(a.out)
    try:
        return warmup(a, out)
    except Exception as e:  # noqa: BLE001 -- never fail the build over the warm-up
        note(f"stopped: {type(e).__name__}: {e} -- the first fights build their shaders instead")
        return 0


def warmup(a, out):
    extra = dict(kv.split("=", 1) for kv in a.env)
    cmd, env, cwd = run_game.game_command(out, extra)
    if not os.path.isfile(cmd[0]) or not os.path.isfile(cmd[1]):
        note("no built game here -- nothing to warm up")
        return 0
    cache = os.path.join(cwd, CACHE)
    marker = os.path.join(cache, MARKER)
    stamp = exe_stamp(cmd[0])
    if not a.force and read_json(marker).get("exe") == stamp:
        note("already done for this build")
        return 0
    if sys.platform != "win32":
        note("only on Windows (the D3D12 renderer's caches)")
        return 0
    if read_json(os.path.join(out, "build", "t5dr_build.json")).get("online", True) is False:
        # 1.1.9: the European program -- the fights are played through the direct fight (src/directfight), which
        # knows only the US program (src/platform/t5_game.h); without it the game would sit at its title
        note("not for this version of the game (the European one) -- the first fights build their shaders instead")
        return 0
    lines = fight_lines(a.fights)
    skip = os.path.join(out, SKIP_FILE)
    try:
        if time.time() - os.path.getmtime(skip) > STALE_SKIP:
            os.remove(skip)                          # (left over: not this build's)
    except OSError:
        pass
    if skip_requested(skip):
        note("skipped -- the first fights build their shaders instead")
        return 0
    work = tempfile.mkdtemp(prefix="t5dr-warmup-")
    ctl_dir = os.path.join(work, "ctl")
    status = os.path.join(work, "status.json")
    pad = os.path.join(work, "pad.txt")
    open(pad, "w").close()
    from t5lobby.match_driver import Control
    ctl = Control(ctl_dir)
    env.update({
        "T5_CTL_DIR": ctl_dir, "T5_DF_STATUS_FILE": status,
        "PS3_WINDOW_BACKGROUND": "1", "PS3_AUDIO_MUTE": "1", "PAD_NO_KEYBOARD": "1", "PS3_PAD_FILE": pad,
        "T5_UNLOCK_STAGES": "1",                    # the Tekken 5 stages offline (docs/DIRECTFIGHT.md "Unlocks")
    })
    for k, v in extra.items():
        env[k] = v
    log_path = os.path.join(out, "logs", "warmup.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    note(f"{len(lines)} short fights in a hidden game, so the first real fights do not stutter "
         f"(about {max(1, round((20 + len(lines) * (8 + a.fight_seconds)) / 60))} minutes)")
    t_end = time.time() + 60 * a.minutes
    done = 0
    skipped = False
    with open(log_path, "w", encoding="utf-8", errors="replace") as log:
        p = subprocess.Popen(cmd, env=env, cwd=cwd, stdout=log, stderr=subprocess.STDOUT,
                             creationflags=subprocess.BELOW_NORMAL_PRIORITY_CLASS)
        try:
            try:
                done = play(ctl, status, p, lines, a.fight_seconds, t_end, pad, skip)
            except Skipped as e:
                done, skipped = e.args[0], True
            if p.poll() is None:
                ctl.send("quit")
                try:
                    p.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    pass
        finally:
            if p.poll() is None:
                p.kill()
                p.wait()
    if done or skipped:
        os.makedirs(cache, exist_ok=True)
        with open(marker, "w", encoding="utf-8") as f:
            json.dump({"exe": stamp, "fights": done, "of": len(lines), "time": int(time.time()),
                       **({"skipped": True} if skipped else {})}, f)
    try:
        os.remove(skip)
    except OSError:
        pass
    if skipped:
        note(f"skipped after {done} of {len(lines)} fights -- the first fights build the rest of their shaders")
        return 0
    note(f"done: {done} of {len(lines)} fights" + ("" if done == len(lines) else
                                                   " -- the rest build their shaders in the first fights"))
    return 0


def set_pad(path, buttons):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write(buttons)
    for _ in range(50):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.005)


def play(ctl, status, p, lines, fight_seconds, t_end, pad, skip=None):
    """Drive the persistent game through `lines`; returns how many fights reached FIGHT START. Raises
    Skipped(done) as soon as the skip file is there (checked every quarter of a second)."""
    done = 0
    last_match = 0

    def nap(seconds):
        if skip_requested(skip):
            raise Skipped(done)
        time.sleep(seconds)
    for i, (stage, p1, p2, line) in enumerate(lines):
        if time.time() > t_end:
            note("out of time")
            break
        note(f"fight {i + 1} of {len(lines)}: stage {stage}, fighters {p1} and {p2}")
        ctl.send("fight", match=f"warmup{i + 1}", rematch=False, env={"T5_FIGHT": line, "T5_DF_STATUS_FILE": status})
        t0 = time.time()
        fought = False
        while time.time() - t0 < 120 and time.time() < t_end:
            if p.poll() is not None:
                note(f"the game stopped (exit code {p.returncode})")
                return done
            st = read_json(status)
            if st.get("state") in ("fight", "over") and int(st.get("match") or 0) > last_match:
                last_match = int(st.get("match") or 0)
                fought = True
                break
            nap(0.25)
        if not fought:
            note("this fight did not start -- stopping")
            return done
        done += 1
        t0 = time.time()
        k = 0
        while time.time() - t0 < fight_seconds:
            set_pad(pad, PAD[k % len(PAD)])
            k += 1
            nap(0.25)
        set_pad(pad, "")
        ctl.send("idle")
        t0 = time.time()
        while time.time() - t0 < 90:
            if p.poll() is not None:
                note(f"the game stopped (exit code {p.returncode})")
                return done
            cs = ctl.state() or {}
            if read_json(status).get("state") == "neutral" and cs.get("state") in ("idle", "error"):
                break
            nap(0.25)
        else:
            note("the game did not come back to the select screen -- stopping")
            return done
    return done


if __name__ == "__main__":
    sys.exit(main())
