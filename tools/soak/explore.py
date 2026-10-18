"""Closed-loop explorer for finding menu flows (the soak's scenarios were found
with it): starts one polite game (soakgame.SoakGame) and runs the commands
appended to <dir>/cmd.txt, one per line; each finished command is appended to
<dir>/done.txt with the time.

    python tools/soak/explore.py --exe EXE --dir RUN_DIR [--cpus N] [--keep-gamedata] [NAME=VALUE ...]

    press CROSS [ms] [gap_ms] [pad]   tap
    hold LEFT SQUARE                  hold until the next hold/release
    release
    wait 2.5
    shot NAME [any|content|fight]     next read-back frame -> NAME.png (nothing on the desktop)
    seq DOWN DOWN CROSS               taps, 400 ms apart
    con poke16 10090FBC 1             a debug-console command (PS3_DEBUG)
    quit
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from soakgame import SoakGame  # noqa: E402


def run_cmd(g, line):
    p = line.split()
    if not p:
        return True
    c = p[0].lower()
    if c == "quit":
        return False
    if c == "press":
        b = p[1].upper()
        ms = int(p[2]) if len(p) > 2 else 100
        gap = int(p[3]) if len(p) > 3 else 300
        pad = int(p[4]) if len(p) > 4 else 1
        g.press(*b.split("+"), ms=ms, gap=gap, pad=pad)
    elif c == "hold":
        g.hold(*[x.upper() for x in p[1:]])
    elif c == "hold2":
        g.hold(*[x.upper() for x in p[1:]], pad=2)
    elif c == "release":
        g.release()
        g.release(pad=2)
    elif c == "wait":
        g.wait(float(p[1]))
    elif c == "shot":
        g.shot(p[1], expect=p[2] if len(p) > 2 else "any", settle=0.5, timeout=4)
    elif c == "seq":
        for b in p[1:]:
            g.press(*b.upper().split("+"), gap=400)
    elif c == "con":
        g.event("console", f"{line[4:]}: {g.console(line[4:])}")
    elif c == "phase":
        g.phase(p[1], p[2] if len(p) > 2 else "menu")
    else:
        g.event("cmderr", f"unknown command {line}")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", required=True)
    ap.add_argument("--dir", required=True)
    ap.add_argument("--cpus", type=int)
    ap.add_argument("--cpu-offset", type=int, default=0)
    ap.add_argument("--dump-every", type=int, default=30)
    ap.add_argument("--keep-gamedata", action="store_true")
    ap.add_argument("--seed-gamedata")
    ap.add_argument("env", nargs="*")
    a = ap.parse_args()
    env = dict(kv.split("=", 1) for kv in a.env)
    g = SoakGame(a.dir, cpus=a.cpus, cpu_offset=a.cpu_offset, exe=a.exe, env=env, dump_every=a.dump_every, abort_hang=0,
                 keep_gamedata=a.keep_gamedata, seed_gamedata=a.seed_gamedata, console=True)
    cmd_path = os.path.join(a.dir, "cmd.txt")
    done_path = os.path.join(a.dir, "done.txt")
    os.makedirs(a.dir, exist_ok=True)
    if not os.path.exists(cmd_path):          # commands written before the start are kept
        open(cmd_path, "w").close()
    open(done_path, "w").close()
    g.start()
    n = 0
    try:
        while g.alive():
            with open(cmd_path) as f:
                lines = f.read().splitlines()
            if len(lines) <= n:
                time.sleep(0.1)
                continue
            for line in lines[n:]:
                n += 1
                try:
                    if not run_cmd(g, line):
                        raise SystemExit
                except SystemExit:
                    raise
                except Exception as e:
                    g.event("cmderr", f"{line}: {e}")
                with open(done_path, "a") as f:
                    f.write(f"{g.now():.1f} {line}\n")
    except (SystemExit, KeyboardInterrupt):
        pass
    finally:
        g.stop()


if __name__ == "__main__":
    main()
