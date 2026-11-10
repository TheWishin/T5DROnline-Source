#!/usr/bin/env python3
"""Check the input display in offline Versus and the players' own button names in the game
(docs/TRAINING.md "Offline Versus" and "Your own button names").

    python tools/vs_overlay_check.py [--exe build/cmake/t5dr.exe] [--vfs DIR] [--out DIR] [--affinity MASK]

Four games, one after the other, each muted, in the background, at below-normal priority:

  names   Versus on this PC (T5_NET_MODE=local: both players here, input scripted frame by frame), Jin vs
          Jin, with T5_VS_OVERLAY=1, the training overlay itself Off, and a controls.ini whose [names] /
          [names1] / [names2] sections name the buttons. The overlay's log must show the display coming up
          for both players in Versus (game type 4) and every scripted press listed under its player's own
          name: P1's SQUARE as LP, SQUARE+TRIANGLE as LP+RP, L1 as TAG; P2's SQUARE as PUNCH (its own
          section wins), CIRCLE as RK (from [names]); P2's L1 not at all (only P1 named it). A picture of
          what the window shows is read back (RSX_TEST_BB_SHOT) and must have the panels' pixels.
  plain   the same game and script with every overlay setting off and no names: nothing is shown.
          Its per-frame state hashes (T5_NET_LOG) must equal the names game's, frame for frame: the
          display changes nothing the game computes.
  default the same with T5_VS_OVERLAY=1 and a controls.ini without names: the display lists 1 2 3 4.
  offline Versus with no netplay code path at all (no T5_NET_MODE; the pads are PS3_PAD_FILE scripts in
          real time): the display comes up with T5_VS_OVERLAY=1 and lists a press under its name.

Exit 0 = PASS. Nothing of the game is kept unless --keep / --out.
"""
import argparse
import ctypes
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

os.environ.setdefault("T5_NET_BIND", "127.0.0.1")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from run_game import game_command  # noqa: E402

# T5_NET_SCRIPT masks
SQ, TRI, CROSS, CIRCLE, L1, RIGHT, LEFT = 0x8000, 0x1000, 0x4000, 0x2000, 0x0400, 0x20, 0x80
ROUND_FRAME = 762      # lockstep frame the round starts at (Jin vs Jin, stage 20, deterministic)
SHOT_FRAME = ROUND_FRAME + 330
LAST_FRAME = ROUND_FRAME + 420

NAMES_INI = """; test file (tools/vs_overlay_check.py)
[names]
1 = LP          ; both players
2 = RP
3 = LK
circle = RK
[names1]
L1 = Tag
[names2]
square = Punch
"""


def scripts():
    b = ROUND_FRAME + 60
    p1 = [f"{b}:6:{SQ:#x}", f"{b + 60}:6:{SQ | TRI:#x}", f"{b + 120}:8:{L1:#x}", f"{b + 180}:6:{CROSS | RIGHT:#x}",
          f"{b + 240}:6:{SQ:#x}"]
    p2 = [f"{b + 20}:6:{SQ:#x}", f"{b + 80}:6:{CIRCLE:#x}", f"{b + 140}:8:{L1:#x}", f"{b + 250}:6:{CIRCLE | LEFT:#x}"]
    return ",".join(p1), ",".join(p2)


def start(a, out, env):
    os.makedirs(out, exist_ok=True)
    base = {"PS3_VFS_ROOT": a.vfs.replace("\\", "/"), "PS3_HDD0_ROOT": os.path.join(a.vfs, "dev_hdd0").replace("\\", "/"),
            "PS3_WINDOW_BACKGROUND": "1", "PS3_AUDIO_MUTE": "1", "T5_PRACTICE": "0",
            "T5_TRAINING_LOG": os.path.join(out, "training.log"),
            "RSX_TEST_CLIENT_SIZE": "1280x720", "RSX_TEST_BB_SHOT": os.path.join(out, "shot.req")}
    base.update(env)
    argv, full_env, _ = game_command(ROOT, base)
    for k in ("T5_TRAINING", "T5_TRAINING_ALL", "T5_TRAINING_ONLINE", "T5_VS_OVERLAY", "PS3_CONTROLS"):
        if k not in base:
            full_env.pop(k, None)
    argv[0] = os.path.abspath(a.exe)
    argv[1] = os.path.join(a.vfs, "PS3_GAME", "USRDIR", "EBOOT.elf")
    flags = subprocess.BELOW_NORMAL_PRIORITY_CLASS if os.name == "nt" else 0
    gl = open(os.path.join(out, "game.log"), "w")
    p = subprocess.Popen(argv, env=full_env, cwd=out, stdout=gl, stderr=subprocess.STDOUT, creationflags=flags)
    if a.affinity and os.name == "nt":
        ctypes.windll.kernel32.SetProcessAffinityMask(ctypes.c_void_p(int(p._handle)), ctypes.c_size_t(a.affinity))
    return p, gl


def stop(p, gl):
    if p.poll() is None:
        p.kill()
        p.wait(timeout=20)
    gl.close()


def last_frame(out):
    frames = os.path.join(out, "frames.log")
    try:
        with open(frames, "rb") as f:
            f.seek(max(0, os.path.getsize(frames) - 400))
            tail = [ln for ln in f.read().decode(errors="replace").splitlines() if ln[:1].isdigit()]
        return int(tail[-1].split()[0]) if tail else -1
    except (OSError, ValueError):
        return -1


def take_shot(out, name, timeout=15):
    """ask the game for what its window shows; the PPM's path or None"""
    path = os.path.join(out, name)
    req = os.path.join(out, "shot.req")
    with open(req, "w") as f:
        f.write(path)
    t0 = time.time()
    while time.time() - t0 < timeout:
        if not os.path.exists(req) and os.path.exists(path) and os.path.getsize(path) > 1000:
            time.sleep(0.3)
            return path
        time.sleep(0.2)
    return None


def run_local(a, out, env):
    """a scripted local-lockstep Versus to LAST_FRAME; a picture at SHOT_FRAME"""
    s1, s2 = scripts()
    e = {"T5_NET_MODE": "local", "T5_NET_START": "external", "T5_NET_LOCALPAD": "0", "T5_RB_MODE": "off",
         "T5_NET_SEED": "0x5EED0018",     # the same match in every run: the hashes are compared
         "T5_FIGHT": "jin,jin,20,3", "T5_NET_SCRIPT": "@" + s1, "T5_NET_SCRIPT2": "@" + s2,
         "T5_NET_LOG": os.path.join(out, "frames.log")}
    e.update(env)
    p, gl = start(a, out, e)
    shot = None
    t0 = time.time()
    try:
        while p.poll() is None and time.time() - t0 < a.timeout:
            time.sleep(0.25)
            f = last_frame(out)
            if shot is None and f >= SHOT_FRAME:
                shot = take_shot(out, "shot.ppm") or ""
            if f >= LAST_FRAME:
                break
    finally:
        stop(p, gl)
    return shot


def read_log(out):
    rows = {"show": [], "hide": [], "names": [], "input": [], "drawn": []}
    try:
        for line in open(os.path.join(out, "training.log"), encoding="utf-8", errors="replace"):
            m = re.match(r"(\d+) (show|hide|names|input|drawn) (.*)", line.rstrip("\n"))
            if m:
                rows[m.group(2)].append((int(m.group(1)), m.group(3)))
    except OSError:
        pass
    return rows


def hashes(out):
    """{lockstep frame: its hash and input lines} from T5_NET_LOG"""
    h = {}
    try:
        for line in open(os.path.join(out, "frames.log"), errors="replace"):
            parts = line.split()
            # "<frame> X H <area hashes>" and "<frame> I <P1 input> <P2 input> <state hash>"
            if len(parts) > 3 and parts[0].isdigit() and (parts[1] == "I" or parts[1:3] == ["X", "H"]):
                h.setdefault(int(parts[0]), []).append(" ".join(parts[1:]))
    except OSError:
        pass
    return h


def load_ppm(path):
    with open(path, "rb") as f:
        data = f.read()
    m = re.match(rb"P6\s+(\d+)\s+(\d+)\s+(\d+)\s", data)
    if not m:
        return 0, 0, b""
    return int(m.group(1)), int(m.group(2)), data[m.end():]


def panel_pixels(path):
    """(dark panel share at P1's list, light text pixels there, the same for P2's)"""
    w, h, px = load_ppm(path)
    if not w or len(px) < w * h * 3:
        return None

    def box(x0, x1, y0, y1):
        text = 0
        for y in range(y0, y1):
            row = px[(y * w + x0) * 3:(y * w + x1) * 3]
            for i in range(0, len(row), 3):
                if row[i] > 200 and row[i + 1] > 180:
                    text += 1
        return text
    sx, sy = w / 1280.0, h / 720.0
    y0, y1 = int(190 * sy), int((190 + 18 * 6) * sy)
    return box(int(20 * sx), int(170 * sx), y0, y1), box(int(1110 * sx), int(1262 * sx), y0, y1)


def ppm_to_png(path):
    try:
        from PIL import Image
    except ImportError:
        return path
    png = os.path.splitext(path)[0] + ".png"
    Image.open(path).save(png)
    return png


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--exe", default=os.path.join(ROOT, "build", "cmake", "t5dr.exe"))
    ap.add_argument("--vfs", default=os.environ.get("PS3_VFS_ROOT", os.path.join(ROOT, "game", "vfs")))
    ap.add_argument("--out", default="", help="working directory (default: a temporary one)")
    ap.add_argument("--timeout", type=float, default=600)
    ap.add_argument("--affinity", type=lambda s: int(s, 0), default=0, help="processor mask for the games (0xFFFF0000)")
    ap.add_argument("--only", default="", help="names,plain,default,offline (default: all)")
    ap.add_argument("--keep", action="store_true", help="keep the working directory")
    a = ap.parse_args()
    out = os.path.abspath(a.out) if a.out else tempfile.mkdtemp(prefix="vs_overlay_check_")
    os.makedirs(out, exist_ok=True)
    only = [s for s in a.only.split(",") if s] or ["names", "plain", "default", "offline"]
    ini = os.path.join(out, "controls_names.ini")
    with open(ini, "w") as f:
        f.write(NAMES_INI)
    plain_ini = os.path.join(out, "controls_plain.ini")
    with open(plain_ini, "w") as f:
        f.write("[general]\nlog = 0\n")
    ok = True

    def check(good, text):
        nonlocal ok
        ok &= bool(good)
        print(f"  {'ok  ' if good else 'FAIL'} {text}")

    if "names" in only:
        d = os.path.join(out, "names")
        shot = run_local(a, d, {"T5_TRAINING": "off", "T5_VS_OVERLAY": "1", "PS3_CONTROLS": ini})
        r = read_log(d)
        print(f"names: {len(r['input'])} input rows, {len(r['drawn'])} drawn under names ({d})")
        check(any("game type 4 P1 P2" in t and "frames" not in t for _, t in r["show"]),
              "shown in Versus (game type 4) for both players, inputs only")
        nm = dict((t.split(" ", 1)[0], t.split(" ", 1)[1]) for _, t in r["names"])
        check(nm.get("P1") == "1=LP 2=RP 3=LK 4=RK L1=Tag" and nm.get("P2") == "1=Punch 2=RP 3=LK 4=RK",
              f"names read from controls.ini: {nm}")
        d1 = [t.split(" ", 1)[1] for _, t in r["drawn"] if t.startswith("P1 ")]
        d2 = [t.split(" ", 1)[1] for _, t in r["drawn"] if t.startswith("P2 ")]
        check(d1 == ["5 LP", "5 LP+RP", "5 Tag", "6 LK", "5 LP"], f"P1's presses as drawn: {d1}")
        check(d2 == ["5 Punch", "5 RK", "6 RK"], f"P2's presses as drawn (its L1 has no name: not listed): {d2}")
        if shot:
            px = panel_pixels(shot)
            check(px and px[0] > 150 and px[1] > 150, f"picture of the window: text pixels in P1's / P2's list {px}")
            print("    picture: " + ppm_to_png(shot))
        else:
            check(False, "picture of the window (RSX_TEST_BB_SHOT)")
    if "plain" in only:
        d = os.path.join(out, "plain")
        shot = run_local(a, d, {"T5_TRAINING": "off", "PS3_CONTROLS": plain_ini})
        r = read_log(d)
        check(not r["show"] and not r["drawn"], f"every setting off: nothing shown ({len(r['show'])} show lines)")
        if shot:
            px = panel_pixels(shot)
            check(px is not None and px[0] < 60 and px[1] < 60, f"picture without the display: text pixels {px}")
            ppm_to_png(shot)
        if "names" in only:
            ha, hb = hashes(os.path.join(out, "names")), hashes(d)
            common = sorted(f for f in ha if f in hb and f <= LAST_FRAME)
            diff = [f for f in common if ha[f] != hb[f]]
            check(len(common) >= LAST_FRAME - 5 and not diff,
                  f"state hashes with the display on vs off: {len(common)} frames compared, {len(diff)} different"
                  + (f" (first {diff[0]})" if diff else ""))
    if "default" in only:
        d = os.path.join(out, "default")
        run_local(a, d, {"T5_TRAINING": "off", "T5_VS_OVERLAY": "1", "PS3_CONTROLS": plain_ini})
        r = read_log(d)
        i1 = [t.split(" ", 1)[1] for _, t in r["input"] if t.startswith("P1 ") and "+" in t]
        check(r["show"] and not r["names"] and not r["drawn"] and i1 == ["5+1", "5+1+2", "6+3", "5+1"],
              f"no names in controls.ini: shown with 1 2 3 4 ({i1})")
    if "offline" in only:
        d = os.path.join(out, "offline")
        os.makedirs(d, exist_ok=True)
        pad = os.path.join(d, "pad1.txt")
        for n in ("pad1.txt", "pad2.txt"):
            open(os.path.join(d, n), "w").close()
        p, gl = start(a, d, {"T5_FIGHT": "jin,jin,20,3", "T5_TRAINING": "off", "T5_VS_OVERLAY": "1", "PS3_CONTROLS": ini,
                             "PS3_PAD_FILE": pad.replace("\\", "/"),
                             "PS3_PAD_FILE2": os.path.join(d, "pad2.txt").replace("\\", "/")})
        shown = pressed = False
        t0 = time.time()
        try:
            while p.poll() is None and time.time() - t0 < a.timeout:
                time.sleep(0.5)
                r = read_log(d)
                if not shown and r["show"]:
                    shown = True
                    t_show = time.time()
                if shown and time.time() - t_show > 12:           # the round runs: hold SQUARE, then L1
                    for held, secs in (("SQUARE", 0.5), ("", 0.7), ("L1", 0.5), ("", 0.8)):
                        with open(pad, "w") as f:
                            f.write(held)
                        time.sleep(secs)
                    pressed = True
                    got = [t for _, t in read_log(d)["drawn"]]
                    if ("P1 5 LP" in got and "P1 5 Tag" in got) or time.time() - t_show > 30:
                        break
            shot = take_shot(d, "shot.ppm") if pressed else None
        finally:
            stop(p, gl)
        r = read_log(d)
        d1 = [t.split(" ", 1)[1] for _, t in r["drawn"] if t.startswith("P1 ")]
        check(any("game type 4 P1 P2" in t for _, t in r["show"]), "offline Versus, no netplay: shown for both players")
        check("5 LP" in d1 and "5 Tag" in d1, f"offline Versus: a pad's SQUARE and L1 as drawn: {d1}")
        if shot:
            print("    picture: " + ppm_to_png(shot))
    if not a.keep and not a.out:
        shutil.rmtree(out, ignore_errors=True)
    print("PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
