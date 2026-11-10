"""The profile picture (docs/ONLINE.md "Profile picture"): a picture of the player's own customized fighter.

How it is taken: the launcher starts a short OFFLINE game of its own -- hidden, muted, no netplay, on a throw-away
save folder -- with the switches the game already has: direct fight (T5_FIGHT) with the player's fighter as P1,
the offline test hook that puts the customization of a save on P1 (T5_COSTUME_SAVE, a copy of the player's
SYS-DATA: the game only reads it), and the backbuffer read-back (RSX_TEST_BB_SHOT). P1's intro is the game's own
close-up of the fighter alone, without HUD: the launcher asks for a few pictures of it, keeps the best one, cuts the
middle out and shrinks it. Nothing in the game changes for it (no new code, no new state, the same build), no online
session exists while it runs, and the player's saves are never written.

The picture is taken again only when that fighter's customization in the save changed (the cache key is a hash of
the fighter's 0x108-byte block, never the save's path or anything else of it).

No Tk here: launcher/t5dr_launcher.pyw and lobby/t5lobby/tk_tab.py call refresh() from a worker thread.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (os.path.join(ROOT, "tools"), os.path.join(ROOT, "lobby")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from t5lobby import picfmt, process_owner  # noqa: E402

VERSION = 1                     # of the way pictures are taken: a new one takes every picture again
FOLDER = "profile-pics"         # under the build output folder: index.json, <fighter>-<costume>.png, work/
SAVE_OFFSET = 0x820             # SYS-DATA: the customization blocks (docs/DIRECTFIGHT.md "Custom costumes online")
BLOCK = 0x108                   # one item character
COSTUME = 0x58                  # one costume in it: 32 u16 bought, 4 u16 worn, 3 u32 colours bought, 3 u8 worn
ITEM_CHARS = 36
BUTTONS = (1, 3, 2, 4)          # the confirm buttons tried, in this order (LP, LK, RP, RK: usually costume 1, 2, 1, 2)
MAX_RUNS = 4                    # games started for one fighter at most (every button once)
BOOT_TIMEOUT = 150.0            # seconds from the start to the intro (a cold shader cache on a slow PC)
SHOT_TIMES = (2.0, 2.5, 3.0, 3.5)   # seconds into P1's intro (it fades in during the first second) ...
PREFER = (1, 2, 0, 3)               # ... and the order they are liked in: the camera has usually reached the fighter
                                    # by 2.5 s (seen with the intros of Kazuya and Lili; an intro is 3.5 s or longer)
SHOT_WAIT = 2.0                 # for one picture to arrive
STAGE = 0                       # a bright, open stage every save has
CLIENT = (1280, 720)
CREATE_NO_WINDOW = 0x08000000
BELOW_NORMAL = 0x00004000

_RE_WORN = re.compile(r"costumes worn: P1 (?:costume (\d+)[^;]*?: ([^;]*)|default)")
_RE_ITEM = re.compile(r"costumes written: P1 item char (-?\d+) \([^)]*\): ([^,;]*)")
_RE_INTRO = re.compile(r"costumes: (?:blocks hash [0-9A-Fa-f]+ after the loading|the VS custom data changed)")
_lock = threading.Lock()        # one capture at a time in this launcher


def folder(out):
    return os.path.join(out, FOLDER)


# ----------------------------------------------------------------------------- the save
def block(sysdata, item_char):
    """The 0x108 bytes of one item character, or None (short file, bad index)."""
    if not 0 <= item_char < ITEM_CHARS:
        return None
    b = sysdata[SAVE_OFFSET + item_char * BLOCK:SAVE_OFFSET + (item_char + 1) * BLOCK]
    return b if len(b) == BLOCK else None


def customized(blk):
    """The costumes (1-3) of a block that wear an item or a colour of the shop."""
    out = []
    for k in range(3):
        c = blk[k * COSTUME:(k + 1) * COSTUME]
        # (0xFFFF and 0 both mean "nothing worn here", as in the game's own log: df_costume.cpp worn_text)
        worn_parts = any(c[64 + 2 * i:66 + 2 * i] not in (b"\xff\xff", b"\0\0") for i in range(4))
        worn_colours = any(v != 0xFF for v in c[84:87])
        if worn_parts or worn_colours:
            out.append(k + 1)
    return out


def block_key(blk, costume):
    """The cache key of one costume's picture: a hash of what that costume wears and of nothing else."""
    c = blk[(costume - 1) * COSTUME:costume * COSTUME]
    return hashlib.sha256(b"t5dr-profile-pic %d\0" % VERSION + c[64:72] + c[84:87]).hexdigest()[:32]


def read_save(path):
    try:
        with open(path, "rb") as f:
            return f.read(4 << 20)
    except OSError:
        return b""


# ----------------------------------------------------------------------------- the cache
def load_index(out):
    try:
        with open(os.path.join(folder(out), "index.json"), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) and d.get("version") == VERSION else {"version": VERSION, "fighters": {}}
    except (OSError, ValueError):
        return {"version": VERSION, "fighters": {}}


def save_index(out, index):
    os.makedirs(folder(out), exist_ok=True)
    tmp = os.path.join(folder(out), "index.json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=1, sort_keys=True)
    os.replace(tmp, os.path.join(folder(out), "index.json"))


def pic_path(out, fighter, costume):
    return os.path.join(folder(out), f"{fighter}-{int(costume)}.png")


def cached(out, fighter, sysdata, index=None):
    """What the cache says about this fighter with this save -> ("unknown", None) (never looked at: a game must run),
    ("none", []) (nothing customized: no picture), ("stale", [costumes]) (customized, pictures missing or old),
    ("ok", [(costume, png bytes), ...])."""
    index = index or load_index(out)
    ent = (index.get("fighters") or {}).get(fighter)
    if not isinstance(ent, dict) or not isinstance(ent.get("item_char"), int):
        return "unknown", None
    blk = block(sysdata, ent["item_char"])
    if blk is None:
        return "none", []
    want = customized(blk)
    if not want:
        return "none", []
    got, missing = [], []
    for k in want:
        rec = (ent.get("pics") or {}).get(str(k))
        data = None
        if isinstance(rec, dict) and rec.get("key") == block_key(blk, k):
            try:
                with open(pic_path(out, fighter, k), "rb") as f:
                    data = picfmt.clean(f.read())
            except (OSError, picfmt.PicError):
                data = None
        if data is None:
            # a costume no button reaches (ent["unreachable"]) has no picture and needs no new game
            if rec != {"key": block_key(blk, k), "unreachable": True}:
                missing.append(k)
        else:
            got.append((k, data))
    return ("stale", missing) if missing else ("ok", got)


# ----------------------------------------------------------------------------- one hidden game
def game_env(fight, save_copy, work_rel):
    """The switches of the capture game (all of them exist in the released game; see the module text)."""
    return {
        "T5_FIGHT": fight,
        "T5_COSTUME_SAVE": save_copy,
        "PS3_SAVEDATA_DIR": "./" + work_rel + "/save",      # a throw-away save folder: the player's is never touched
        "RSX_TEST_BB_SHOT": work_rel + "/shot.req",
        "RSX_TEST_CLIENT_SIZE": "%dx%d" % CLIENT,
        "PS3_WINDOW_BACKGROUND": "1", "PS3_WINDOW_HIDDEN": "1", "PS3_NO_DIALOGS": "1",
        "PS3_AUDIO_MUTE": "1", "PS3_AUDIO_MUTE_HIDDEN": "1",
        "PS3_INTERNAL_RES": "720", "PS3_FULLSCREEN": None, "PS3_PICTURE": None,
        "PS3_VIDEO_ASPECT": None, "PS3_VIDEO_RESOLUTION": None,
        # never anything of an online game, a replay, the unlocks, the overlays or the practice tools
        "T5_NET_MODE": None, "T5_CTL_DIR": None, "T5_FIGHT_FILE": None, "T5_REPLAY_DIR": None,
        "T5_REPLAY_LIVE": None, "T5_UNLOCK_STAGES": None, "T5_UNLOCK_ITEMS": None, "T5_UNLOCK_JINPACHI": None,
        "T5_TRAINING": None, "T5_HUD_NAMES": None, "T5_HUD_RANKS": None, "T5_NET_RESULT_FILE": None,
        "T5_DF_STATUS_FILE": None, "T5_COSTUME_SAVE2": None, "LD_SURF_DUMP": None, "LD_SURF_DUMP_GATE": None,
    }


def _kill(proc):
    """End the capture game and whatever it started. It lives in a kill-on-close job (process_owner): a launcher
    that is closed or crashes while a picture is taken leaves no hidden game behind either."""
    try:
        process_owner.release(proc)
    except OSError:
        pass
    if proc.poll() is None:
        try:
            proc.kill()
        except OSError:
            pass
    try:
        proc.wait(10)
    except subprocess.TimeoutExpired:
        pass


def run_game_once(out, fighter_id, opponent_id, button, save_path, stop=None, command=None, extra_env=None,
                  boot_timeout=BOOT_TIMEOUT, shot_times=SHOT_TIMES, cwd=None, log=None):
    """One hidden offline game with `fighter_id` as P1, confirmed with `button`. -> {"item_char", "why" (the
    game's word for P1's block: custom / nothing customized / ...), "costume" (1-3, the one this button gives),
    "worn" (True: the game says it wears the customization), "frames": [(w, h, rgb), ...]} or {"error": text}.
    `command(out, env)` -> (argv, env, cwd): run_game.game_command (tests pass a stand-in game).
    `stop`: threading.Event that ends it early."""
    if command is None:
        import run_game
        command = run_game.game_command
    cwd_out = cwd or out
    work_rel = FOLDER + "/work"
    work = os.path.join(cwd_out, FOLDER, "work")
    shutil.rmtree(work, ignore_errors=True)        # whatever a killed run left behind
    os.makedirs(os.path.join(work, "save"), exist_ok=True)
    save_copy = os.path.join(work, "SYS-DATA")
    try:
        shutil.copyfile(save_path, save_copy)
    except OSError as e:
        return {"error": f"the save cannot be read ({e.__class__.__name__})"}
    fight = f"{int(fighter_id)},{int(opponent_id)},{STAGE},1 buttons={int(button)}|1"
    env_over = game_env(fight, work_rel + "/SYS-DATA", work_rel)
    env_over.update(extra_env or {})
    argv, env, run_cwd = command(out, env_over)
    if cwd:
        run_cwd = cwd
    if not os.path.exists(argv[0]):
        return {"error": "the game is not built"}
    res = {"item_char": None, "why": "", "costume": None, "worn": False, "frames": []}
    log_path = os.path.join(work, "game.log")
    flags = (CREATE_NO_WINDOW | BELOW_NORMAL) if os.name == "nt" else 0
    try:
        logf = open(log_path, "wb")
        proc = process_owner.popen(argv, env=env, cwd=run_cwd, stdout=logf, stderr=subprocess.STDOUT,
                                   stdin=subprocess.DEVNULL, creationflags=flags)
    except OSError as e:
        return {"error": f"the game did not start ({e.__class__.__name__})"}
    try:
        pos, tail, intro = 0, b"", None
        deadline = time.monotonic() + boot_timeout
        while intro is None:
            if stop is not None and stop.is_set():
                return {"error": "stopped"}
            if time.monotonic() > deadline:
                return {"error": "the game did not reach the fight in time"}
            ended = proc.poll() is not None
            with open(log_path, "rb") as f:
                f.seek(pos)
                chunk = f.read()
            pos += len(chunk)
            lines = (tail + chunk).split(b"\n")
            tail = lines.pop()
            for raw in lines:
                line = raw.decode("utf-8", "replace")
                if "[df]" not in line:
                    continue
                m = _RE_ITEM.search(line)
                if m:
                    res["item_char"], res["why"] = int(m.group(1)), m.group(2).strip()
                m = _RE_WORN.search(line)
                if m and m.group(1):
                    res["costume"] = int(m.group(1))
                    res["worn"] = m.group(2).strip().startswith("parts")
                if _RE_INTRO.search(line):
                    intro = time.monotonic()
            if intro is None:
                if ended:
                    return {"error": f"the game ended early (exit {proc.returncode})"}
                time.sleep(0.05)
        if log:
            log(f"profile picture: intro reached, item char {res['item_char']} ({res['why']}), "
                f"costume {res['costume']}, worn {res['worn']}")
        req = os.path.join(work, "shot.req")
        for i, at in enumerate(shot_times):
            if stop is not None and stop.is_set():
                return {"error": "stopped"}
            time.sleep(max(0.0, intro + at - time.monotonic()))
            name = f"f{i}.ppm"
            with open(req, "w", encoding="ascii") as f:
                f.write(work_rel + "/" + name)
            t_end = time.monotonic() + SHOT_WAIT
            while os.path.exists(req) and time.monotonic() < t_end and proc.poll() is None:
                time.sleep(0.02)
            res["frames"].append(None)             # (stays None when this picture did not arrive)
            if os.path.exists(req):
                try:
                    os.remove(req)
                except OSError:
                    pass
                continue
            path = os.path.join(work, name)
            t_end = time.monotonic() + SHOT_WAIT
            while time.monotonic() < t_end:        # the game writes the file after it took the request
                try:
                    with open(path, "rb") as f:
                        res["frames"][-1] = picfmt.read_ppm(f.read())
                    break
                except (OSError, picfmt.PicError):
                    time.sleep(0.05)
        return res
    finally:
        _kill(proc)
        logf.close()


def choose_frame(frames, prefer=PREFER):
    """The picture of the intro to keep -> (w, h, rgb) of the portrait, or None. The frames in the order they are
    liked (PREFER); one that shows next to nothing (still fading in, a cut, a flash: under 60 % of the best frame's
    detail) is passed over. `frames`: one entry per SHOT_TIMES, None where no picture came."""
    scored = {}
    for i, fr in enumerate(frames):
        if fr is not None:
            scored[i] = picfmt.detail(*picfmt.portrait(*fr, out_w=60, out_h=80, rough=True))
    if not scored:
        return None
    top = max(scored.values())
    if top < 3.0:
        return None
    order = [i for i in prefer if i in scored] + [i for i in sorted(scored) if i not in prefer]
    for i in order:
        if scored[i] >= 0.6 * top:
            return picfmt.portrait(*frames[i])
    return None


def make_png(frames):
    p = choose_frame(frames)
    return picfmt.fit(*p) if p else None


# ----------------------------------------------------------------------------- the whole job for one fighter
def refresh(out, fighter, fighter_id, opponent_id, save_path, first_button=None, stop=None, log=None, **run_kw):
    """Bring this fighter's pictures up to date with the save. -> {"state": "ok" | "none" | "failed",
    "pics": [(costume, png bytes), ...], "ran": games started, "error": text}. "none": the fighter is not customized
    (the profile then shows no picture of it). Starts a game only when the cache cannot answer."""
    with _lock:
        sysdata = read_save(save_path)
        index = load_index(out)
        state, info = cached(out, fighter, sysdata, index)
        if state == "ok":
            return {"state": "ok", "pics": info, "ran": 0}
        if state == "none":
            return {"state": "none", "pics": [], "ran": 0}
        fighters = index.setdefault("fighters", {})
        ent = fighters.setdefault(fighter, {})
        ent.setdefault("pics", {})
        ent.setdefault("buttons", {})              # button -> the costume it gives (learned from the game's log)
        for k in info or ():                       # known, but its file is gone or damaged: taken again
            ent["pics"].pop(str(k), None)
        order = [b for b in ([first_button] if first_button in BUTTONS else []) + list(BUTTONS)]
        order = sorted(set(order), key=order.index)
        ran, error = 0, ""
        while True:
            blk = block(sysdata, ent["item_char"]) if isinstance(ent.get("item_char"), int) else None
            want = [k for k in (customized(blk) if blk else [])
                    if (ent["pics"].get(str(k)) or {}).get("key") != block_key(blk, k)]
            if blk is not None and not want:
                break
            # a button known to give a wanted costume first; then the buttons not tried yet
            known = [b for b in order if ent["buttons"].get(str(b)) in want]
            fresh = [b for b in order if str(b) not in ent["buttons"]]
            if not known and not fresh:
                for k in want:                     # no button gives this costume: remember, never try again
                    ent["pics"][str(k)] = {"key": block_key(blk, k), "unreachable": True}
                break
            if ran >= MAX_RUNS:
                break
            button = (known or fresh)[0]
            ran += 1
            r = run_game_once(out, fighter_id, opponent_id, button, save_path, stop=stop, log=log, **run_kw)
            if r.get("error"):
                error = r["error"]
                break
            if not isinstance(r.get("item_char"), int) or r["item_char"] < 0:
                error = "the game did not say which fighter it showed"
                break
            ent["item_char"] = r["item_char"]
            blk = block(sysdata, r["item_char"])
            if blk is None or not customized(blk):
                break                              # nothing customized for this fighter: no picture
            if not r.get("costume"):
                error = "the game did not take the customization (" + (r.get("why") or "no reason given") + ")"
                break
            ent["buttons"][str(button)] = r["costume"]
            if blk is None or r["costume"] not in customized(blk):
                continue                           # this button's costume is not customized: the next one
            if not r["worn"]:
                # the save customizes it, the game refused it (an item the costume does not have, ...): no picture
                ent["pics"][str(r["costume"])] = {"key": block_key(blk, r["costume"]), "unreachable": True}
                continue
            png = make_png(r["frames"])
            if png is None:
                error = "no usable picture"
                break
            os.makedirs(folder(out), exist_ok=True)
            with open(pic_path(out, fighter, r["costume"]), "wb") as f:
                f.write(png)
            ent["pics"][str(r["costume"])] = {"key": block_key(blk, r["costume"]),
                                              "sha": hashlib.sha256(png).hexdigest()}
        save_index(out, index)
        shutil.rmtree(os.path.join(run_kw.get("cwd") or out, FOLDER, "work"), ignore_errors=True)
        state, info = cached(out, fighter, sysdata, index)
        if state == "ok":
            return {"state": "ok", "pics": info, "ran": ran}
        if state == "none":
            return {"state": "none", "pics": [], "ran": ran}
        return {"state": "failed", "pics": [], "ran": ran, "error": error or "no picture"}
