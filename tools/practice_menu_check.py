#!/usr/bin/env python3
"""Check the practice menu in the game (docs/TRAINING.md "Practice menu", 1.3.0).

    python tools/practice_menu_check.py [--exe build/cmake/t5dr.exe] [--root DIR] [--out DIR] [--keep]

Starts the game twice through the smoke harness's menu driver (title -> PRACTICE -> the cursor's fighters -> the
fight) with the practice tools on (T5_PRACTICE=1, T5_PRACTICE_LOG, T5_PRACTICE_DIR in the working directory) and
drives P1's pad file. First game:

    START opens the menu (a picture of it), the dummy dashes in (DASH IN), a recording made from the menu and saved
    for the dummy's character, the dummy blocking after the first hit counter-attacks with slot 1 after a block,
    the input delay of 3 frames (a SQUARE press reaches the game 3 frames later), switched sides, the dummy back
    turned, a remembered position, the game's own pause menu from the menu, the menu closed again.

Second game (a new process, same folder): the menu's settings and the recording are still there (log lines, a
picture of the menu). The pictures are the window's backbuffer (RSX_TEST_BB_SHOT: the overlay included) as PNG in
<out>/shots -- they show the game, so they stay in the working directory and are never committed.

The games run muted, in the background, at below-normal priority. Exit 0 = PASS.
"""
import argparse
import ctypes
import math
import os
import re
import shutil
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools", "smoke"))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from game import FRAMES, Game, find_game_root  # noqa: E402
import scenarios as sc  # noqa: E402

PLACE = re.compile(r"^(\d+) (.+?) P1 (-?[\d.]+) (-?[\d.]+) (-?[\d.]+) dummy (-?[\d.]+) (-?[\d.]+) (-?[\d.]+)$")

# the menu's lines (practice_logic.h Item), in order
ITEMS = ["BEHAVIOUR", "COUNTER-ATTACK", "COUNTER EVERY", "COUNTER WITH", "SLOT", "RECORD", "PLAY ONCE",
         "PLAY IN A LOOP", "PLAYBACK", "DELETE THIS SLOT", "RESTART AT", "SIDES", "DUMMY FACING",
         "REMEMBER THIS POSITION", "RESTART NOW", "INPUT DELAY (YOU)", "TRAINING DISPLAY", "GAME'S PAUSE MENU", "CLOSE"]


def below_normal(pid):
    if os.name != "nt":
        return
    k = ctypes.windll.kernel32
    k.OpenProcess.restype = ctypes.c_void_p
    h = k.OpenProcess(0x0200 | 0x0400, False, pid)     # PROCESS_SET_INFORMATION | QUERY_INFORMATION
    if h:
        k.SetPriorityClass(ctypes.c_void_p(h), 0x4000)  # BELOW_NORMAL_PRIORITY_CLASS
        k.CloseHandle(ctypes.c_void_p(h))


class Driver:
    """The menu on P1's pad file; the cursor is followed here (the menu keeps it between openings)."""

    def __init__(self, g, out):
        self.g, self.out, self.cur, self.n = g, out, 0, 0
        self.shots = []

    def tap(self, *b, ms=100, gap=250):
        self.g.press(*b, ms=ms, gap=gap)

    def open(self):
        self.tap("START", gap=400)

    def close(self):
        self.tap("CIRCLE", gap=400)

    def go(self, item):
        want = ITEMS.index(item)
        n = len(ITEMS)
        down = (want - self.cur) % n
        up = (self.cur - want) % n
        for _ in range(min(down, up)):
            self.tap("DOWN" if down <= up else "UP", gap=150)
        self.cur = want

    def change(self, item, steps):
        self.go(item)
        for _ in range(abs(steps)):
            self.tap("RIGHT" if steps > 0 else "LEFT", gap=150)

    def do(self, item):
        self.go(item)
        self.tap("CROSS", gap=300)

    def sel(self, *dirs, btn="CROSS"):
        g = self.g
        g.hold("SELECT")
        g.wait(0.1)
        if dirs:
            g.hold("SELECT", *dirs)
            g.wait(0.1)
        if btn:
            g.hold("SELECT", *dirs, btn)
            g.wait(0.15)
            g.hold("SELECT", *dirs)
            g.wait(0.1)
        g.hold("SELECT")
        g.wait(0.1)
        g.release()
        g.wait(0.3)

    def shot(self, name, wait=0.4):
        """the window's picture, overlay included (RSX_TEST_BB_SHOT), as <out>/shots/<name>.png"""
        os.makedirs(os.path.join(self.out, "shots"), exist_ok=True)
        ppm = os.path.join(self.out, "shots", name + ".ppm")
        req = os.path.join(self.out, "shot.req")
        self.g.wait(wait)
        with open(req, "w") as f:
            f.write(ppm)
        end = time.time() + 8
        while os.path.exists(req) and time.time() < end:
            time.sleep(0.05)
        for _ in range(40):
            if os.path.exists(ppm) and os.path.getsize(ppm) > 100:
                break
            time.sleep(0.05)
        if not os.path.exists(ppm):
            print(f"  (no picture {name})")
            return
        try:
            from PIL import Image
            Image.open(ppm).save(os.path.join(self.out, "shots", name + ".png"))
            os.remove(ppm)
        except Exception as e:  # noqa: BLE001 -- the PPM stays
            print(f"  (picture {name} kept as PPM: {e})")
        self.shots.append(name)


def first_game(d):
    g = d.g
    g.wait(2)
    d.shot("01-fight")
    d.open()
    d.shot("02-menu")
    d.close()
    # the dummy dashes in: BEHAVIOUR 5 to the right (game, block, crouch, walk, step, dash)
    d.open()
    d.change("BEHAVIOUR", 5)
    d.shot("03-menu-dash")
    d.close()
    g.wait(3)
    d.open()
    d.change("BEHAVIOUR", 1)                 # backdash: the dummy goes away again
    d.close()
    g.wait(3)
    # a recording from the menu: RECORD, then the pad plays the dummy (forward, a jab), SELECT+1 stops
    d.sel()                                  # back to the round start
    g.wait(1)
    d.open()
    d.change("BEHAVIOUR", -5)                # block after the first hit
    d.do("RECORD")                           # the menu closes; recording starts once the pad is let go
    g.wait(0.5)
    g.hold("RIGHT")
    g.wait(0.5)
    g.release()
    g.press("SQUARE", gap=300)
    g.press("SQUARE", gap=300)
    d.sel(btn="SQUARE")
    g.wait(0.5)
    # counter-attack after a block with slot 1
    d.sel()
    g.wait(1)
    d.open()
    d.change("COUNTER-ATTACK", 1)            # after a block
    d.change("COUNTER WITH", 1)              # slot 1
    d.shot("04-menu-counter")
    d.close()
    for _ in range(3):                       # walk in and jab: the first hits, the next are blocked
        g.hold("RIGHT")
        g.wait(0.5)
        g.release()
        for _ in range(3):
            g.press("SQUARE", gap=300)
        g.wait(1.6)
        d.sel()
        g.wait(0.8)
    d.open()
    d.change("COUNTER-ATTACK", -1)           # off again
    # input delay 3: SQUARE presses reach the game 3 frames later
    d.change("INPUT DELAY (YOU)", 3)
    d.close()
    g.wait(0.5)
    for _ in range(4):
        g.press("SQUARE", ms=120, gap=500)
    d.open()
    d.change("INPUT DELAY (YOU)", -3)
    # switched sides
    d.change("SIDES", 1)
    d.do("RESTART NOW")
    g.wait(2.5)
    d.shot("05-switched")
    # back turned (sides as started)
    d.open()
    d.change("SIDES", 1)
    d.change("DUMMY FACING", 1)
    d.do("RESTART NOW")
    g.wait(1.5)
    d.shot("06-back-turned")
    g.wait(1)
    d.open()
    d.change("DUMMY FACING", 1)              # facing you again
    d.close()
    d.sel()
    g.wait(1)
    # a remembered position: walk in, SELECT+START, walk back, SELECT+3 -> there
    g.hold("RIGHT")
    g.wait(1.0)
    g.release()
    g.wait(0.8)
    g.hold("SELECT")
    g.wait(0.1)
    g.hold("SELECT", "START")
    g.wait(0.15)
    g.hold("SELECT")
    g.wait(0.1)
    g.release()
    g.wait(0.6)
    g.hold("LEFT")
    g.wait(1.2)
    g.release()
    g.wait(0.5)
    d.sel()
    g.wait(1.5)
    d.shot("07-remembered")
    # back to the round start for the next game, and the counter on again (it is kept)
    d.open()
    d.change("RESTART AT", -1)               # remembered -> round start
    d.change("COUNTER-ATTACK", 1)
    d.close()
    # the game's own pause menu from the menu
    d.open()
    d.do("GAME'S PAUSE MENU")
    g.wait(1.5)
    d.shot("08-game-pause-menu")
    g.press("START", gap=800)                # the game's menu closes; START there is the game's
    g.wait(1)
    d.shot("09-after-game-menu")


def second_game(d):
    g = d.g
    g.wait(2)
    d.open()
    d.shot("10-second-game-menu")
    d.do("PLAY ONCE")                        # the recording from the first game plays
    g.wait(3)
    d.shot("11-second-game-play")


def places(lines):
    return [m.groups() for m in (PLACE.match(ln) for ln in lines) if m]


def xyz(p):
    return [float(v) for v in p[2:]]


def check_first(lines):
    ok = True

    def good(cond, what):
        nonlocal ok
        ok &= bool(cond)
        print(f"  {'ok  ' if cond else 'FAIL'} {what}")
    pl = places(lines)
    start = next((p for p in pl if p[1] == "round start:"), None)
    good(start, "the fight started in Practice with the tools on")
    s = xyz(start) if start else [0] * 6
    good(sum(" menu opened" in ln for ln in lines) >= 8, f"the menu opened ({sum(' menu opened' in ln for ln in lines)} times)")
    good(any("menu BEHAVIOUR: DASH IN" in ln for ln in lines), "BEHAVIOUR: DASH IN chosen")
    # dash: the dummy came toward P1 while DASH IN was on
    i0 = next((i for i, ln in enumerate(lines) if "menu BEHAVIOUR: DASH IN" in ln), None)
    if i0 is not None:
        after = [xyz(p) for p in places(lines[i0:i0 + 400]) if p[1] == "places:"][:8]
        if after:
            d0 = math.hypot(after[0][0] - after[0][3], after[0][1] - after[0][4])
            dmin = min(math.hypot(a[0] - a[3], a[1] - a[4]) for a in after)
            good(dmin < d0 - 600, f"the dummy dashed in: distance {d0:.0f} -> {dmin:.0f}")
        else:
            good(False, "no places after DASH IN")
    i1 = next((i for i, ln in enumerate(lines) if "menu BEHAVIOUR: BACKDASH" in ln), None)
    if i1 is not None:
        after = [xyz(p) for p in places(lines[i1:i1 + 400]) if p[1] == "places:"][:8]
        if after:
            d0 = math.hypot(after[0][0] - after[0][3], after[0][1] - after[0][4])
            dmax = max(math.hypot(a[0] - a[3], a[1] - a[4]) for a in after)
            good(dmax > d0 + 600, f"the dummy backdashed away: distance {d0:.0f} -> {dmax:.0f}")
        else:
            good(False, "no places after BACKDASH")
    else:
        good(False, "BEHAVIOUR: BACKDASH not chosen")
    good(any(re.search(r" record slot 1$", ln) for ln in lines), "RECORD from the menu: slot 1 records")
    saved = [ln for ln in lines if re.search(r" slots saved for character \d+: [1-8] recorded$", ln)]
    good(saved, "the recording saved for the dummy's character" + (f" ({saved[0].split(' ', 1)[1]})" if saved else ""))
    good(any("menu COUNTER-ATTACK: AFTER A BLOCK" in ln for ln in lines) and any("menu COUNTER WITH: SLOT 1" in ln for ln in lines),
         "counter-attack after a block with slot 1 chosen")
    ca = [ln for ln in lines if " counter-attack after a block: slot 1" in ln]
    good(ca, f"the dummy counter-attacked after a block ({len(ca)} times)")
    pr = [int(ln.split()[0]) for ln in lines if " delay 3: square pressed" in ln]
    rc = [int(ln.split()[0]) for ln in lines if " delay 3: square reaches the game" in ln]
    pairs = list(zip(pr, rc))
    good(len(pairs) >= 3 and all(b - a == 3 for a, b in pairs), f"input delay 3: press -> game {[b - a for a, b in pairs]}")
    sw = next((i for i, ln in enumerate(lines) if "menu SIDES: SWITCHED" in ln), None)
    r = next((p for p in places(lines[sw:]) if p[1] == "reset round start:"), None) if sw is not None else None
    if r:
        a = xyz(r)
        good(abs(a[0] - s[3]) < 60 and abs(a[1] - s[4]) < 60 and abs(a[3] - s[0]) < 60 and abs(a[4] - s[1]) < 60,
             f"switched sides: P1 ({a[0]:.0f}, {a[1]:.0f}) where the dummy started, the dummy ({a[3]:.0f}, {a[4]:.0f})")
    else:
        good(False, "no restart after SIDES: SWITCHED")
    bt = next((i for i, ln in enumerate(lines) if " back turned:" in ln), None)
    if bt is not None:
        later = [xyz(p) for p in places(lines[bt:bt + 60]) if p[1] in ("after the turn, back to:", "places:")]
        if later:
            a = later[0]
            look = math.atan2(a[0] - a[3], a[1] - a[4])           # from the dummy to P1
            off = abs((a[5] - look + math.pi) % (2 * math.pi) - math.pi)
            good(off > 2.0, f"the dummy back turned: it looks {math.degrees(off):.0f} degrees away from P1")
        else:
            good(False, "no places after the back-turned restart")
    else:
        good(False, "no back-turned restart")
    rem = next((p for p in pl if p[1] == "remembered:"), None)
    back = next((p for p in pl if p[1] == "reset remembered:"), None)
    if rem and back:
        a, b = xyz(rem), xyz(back)
        good(abs(a[0] - b[0]) < 5 and abs(a[3] - b[3]) < 5 and abs(a[1] - b[1]) < 5,
             f"remembered position: restarted at P1 ({b[0]:.0f}, {b[1]:.0f}) dummy ({b[3]:.0f}, {b[4]:.0f})")
        good(abs(a[0] - s[0]) > 200 or abs(a[1] - s[1]) > 200, "the remembered place is not the round start")
    else:
        good(False, "remembered position: no 'remembered' / 'reset remembered' lines")
    good(any(" the game's pause menu" in ln for ln in lines), "GAME'S PAUSE MENU: a START tap for the game")
    return ok


def check_second(lines):
    ok = True

    def good(cond, what):
        nonlocal ok
        ok &= bool(cond)
        print(f"  {'ok  ' if cond else 'FAIL'} {what}")
    loaded = [ln for ln in lines if re.search(r" slots for character \d+: [1-8] recorded$", ln)]
    good(loaded, "second game: the recording loaded for the dummy's character" +
         (f" ({loaded[0].split(' ', 1)[1]})" if loaded else ""))
    good(any(re.search(r" play slot 1$", ln) for ln in lines), "second game: PLAY ONCE plays slot 1")
    return ok


def run_game(exe, root, out, name, env, drive):
    gdir = os.path.join(out, name)
    g = Game(gdir, exe=exe, root=root, env=env, cwd=os.path.join(out, "cwd"))
    d = Driver(g, out)
    try:
        g.start()
        below_normal(g.proc.pid)
        if sc.to_title(g):
            g.phase("practice-select", "menu")
            sc.pick_mode(g, sc.PRACTICE, wait=3.0)
            if sc.start_fight(g, skip=False) or not FRAMES:
                drive(d)
    finally:
        g.stop()
    return d.shots


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--exe", default=None, help="t5dr.exe (default: <root>/build/cmake/t5dr.exe)")
    ap.add_argument("--root", default=None, help="the build's output root with game/vfs (build_game.py --out)")
    ap.add_argument("--out", default="", help="working directory (default: a temporary one)")
    ap.add_argument("--keep", action="store_true", help="keep the working directory")
    a = ap.parse_args()
    root = os.path.abspath(a.root) if a.root else find_game_root()
    exe = os.path.abspath(a.exe) if a.exe else os.path.join(root, "build", "cmake",
                                                            "t5dr.exe" if os.name == "nt" else "t5dr")
    out = os.path.abspath(a.out) if a.out else tempfile.mkdtemp(prefix="practice_menu_check_")
    os.makedirs(out, exist_ok=True)
    pdir = os.path.join(out, "practice")
    shutil.rmtree(pdir, ignore_errors=True)
    logs = [os.path.join(out, "practice1.log"), os.path.join(out, "practice2.log")]
    base = {"T5_PRACTICE": "1", "T5_TRAINING": "frames", "PS3_AUDIO_MUTE": "1", "PS3_WINDOW_BACKGROUND": "1",
            "T5_PRACTICE_DIR": pdir, "RSX_TEST_BB_SHOT": os.path.join(out, "shot.req"), "T5_TRAINING_LANG": "en"}
    ok = True
    shots = run_game(exe, root, out, "game1", dict(base, T5_PRACTICE_LOG=logs[0]), first_game)
    print("first game:")
    if os.path.exists(logs[0]):
        with open(logs[0], encoding="utf-8", errors="replace") as f:
            ok = check_first(f.read().splitlines()) and ok
    else:
        print("  FAIL no practice log: the game did not reach the fight, or T5_PRACTICE did not take")
        ok = False
    files = sorted(os.listdir(pdir)) if os.path.isdir(pdir) else []
    print(f"  practice folder: {files}")
    ok = bool([f for f in files if re.match(r"char\d\d\.txt$", f)]) and "settings.txt" in files and ok
    shots += run_game(exe, root, out, "game2", dict(base, T5_PRACTICE_LOG=logs[1]), second_game)
    print("second game:")
    if os.path.exists(logs[1]):
        with open(logs[1], encoding="utf-8", errors="replace") as f:
            ok = check_second(f.read().splitlines()) and ok
    else:
        print("  FAIL no practice log in the second game")
        ok = False
    st = os.path.join(pdir, "settings.txt")
    if os.path.exists(st):
        with open(st, encoding="utf-8") as f:
            text = f.read()
        good = "counter block" in text and "counter_slot 1" in text
        print(f"  {'ok  ' if good else 'FAIL'} settings kept: counter block, slot 1")
        ok = ok and good
    print(f"pictures: {len(shots)} in {os.path.join(out, 'shots')}")
    if not a.keep and not a.out:
        shutil.rmtree(out, ignore_errors=True)
    print("PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
