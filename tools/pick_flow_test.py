#!/usr/bin/env python3
"""Two games on this PC, every match picked on the game's own select screen (in-game select).

    python tools/pick_flow_test.py --exe build/cmake/t5dr.exe --out build/cs/runs/p1 \\
        [--flow persistent|rematch] [--rematch-every 3] [--picks "jin:rp/lil:lk,random/timeout,..."]
        [--locked-after 0] [--pick-seconds 30] [--rounds 1] [--mash]

Each match's fight line carries pick=N (docs/DIRECTFIGHT.md "Character select in the
game"): both players pick on their own select screen -- here a script presses the
buttons through each game's PS3_PAD_FILE, closed-loop (T5_DF_TRACE=1 logs the cursor
cell) -- the picks are exchanged over the netplay session, and both games fight what
was picked. --picks gives every match's P1/P2 scenario (cycled when shorter):

    <char>:<button>         move the cursor to that character (code or name prefix) and
                            confirm with lp|rp|lk|rk (Square, Triangle, Cross, Circle)
    random                  press Select (the game picks a random character and costume)
    timeout                 press nothing: after N seconds the line's character
    late<S>:<char>:<button> the same as <char>:<button>, S seconds after the screen is live

--flow persistent (default): both games started once with T5_CTL_DIR, every match a
control command; a new session ("idle", new ports/seed/key) for match 1 and every
--rematch-every K-th match after it, rematches in the running session in between (the
lockstep pauses at the select screen and resumes at the fight). --flow rematch: one
host and one joiner started with T5_FIGHT, the next matches as T5_FIGHT_FILE lines.
--locked-after K: from the (K+1)-th match of a session on, the line carries the
characters the session's first match picked and no pick= (a ranked set's lock).

Checks per match: both games log the same fighters (character, button, model) at FIGHT
START, scripted picks are what was asked for (a timeout is the line's character), no
"PICK MISMATCH", both results the same winner and state hash with 0 mismatching frames.
Exit code 0 = every match OK. Every game is killed at the end; the games run minimized, muted
(PS3_AUDIO_MUTE=1) and at below-normal priority.

Select restarts (docs/DIRECTFIGHT.md "Select restarts"; persistent flow only):

  --aborts N        before match 1, N sessions in a row that end at the select screen
                    without a fight -- an opponent who leaves during the pick, a match
                    the lobby cancels: "fight" (new session, pick=N line), the pickers
                    move the cursor, pick or do nothing, then after 0.4-4 s the session
                    ends: both launchers say "idle", or only one game's (the other one's
                    session ends by the peer's BYE; its launcher's "idle" follows),
                    in turn (--abort-how both|host|join|mix). Each game then restarts
                    its select screen (no fight since the title: no title visit). Checked
                    per abort: both games back at neutral, one more "select screen
                    restarted" in each log, no NULL access / bad guest call / crash /
                    stuck line. Then the matches run as usual (fights, rematches, sync).
  --abort-plan K:N,...  N aborts after match K as well (0 = before match 1, like --aborts)
  --fresh-after-aborts host|join  that game is started again after the aborts: match 1 is
                    a game with N restarts against a fresh one (they must stay in sync)
  --offline         one game, no netplay: the aborts and matches offline (P1 picks with
                    the pad script, P2 keeps the line's character; the result file must
                    name a winner). With --env T5_DF_SELECT_RESTART=inplace the driver
                    restarts the select screen the old way: that broke the game after
                    the 4th-11th restart, and these checks catch it.
"""
import argparse
import json
import os
import random
import re
import subprocess
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fight_flow_test as ff  # noqa: E402  (the pause-menu check, docs/NETPLAY.md "No pause online")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T0 = time.time()

# A game in the state the old select restart left it in (and other faults the aborts must not cause).
BAD = [
    ("bad_guest_call", re.compile(r"guest_call: OPD .* not registered")),
    ("null_call", re.compile(r"\[null-call\]")),
    ("null_write", re.compile(r"\[null-write\]")),
    ("null_read", re.compile(r"\[null-read\]")),
    ("fence_overflow", re.compile(r"fence queue overflow")),
    ("crash", re.compile(r"\[CRASH\]")),
    ("abort", re.compile(r"abort\(\) is called")),
    ("reset_stuck", re.compile(r"reset: waiting in mode")),
    ("stuck_exit", re.compile(r"STUCK:")),
]


def bad_lines(text):
    return [name for name, rx in BAD if rx.search(text)]

CODES = ["pau", "law", "lei", "kin", "yos", "nin", "hwo", "xia", "cha", "jin", "jul", "kum",
         "pan", "bry", "hei", "kaz", "lee", "ste", "mar", "mok", "edd", "jac", "rog", "ann",
         "wan", "gan", "ask", "bru", "bae", "dvj", "rav", "fen", "amk", "lil", "dra", "jnp"]
NAMES = ["Paul", "Law", "Lei", "King", "Yoshimitsu", "Nina", "Hwoarang", "Xiaoyu", "Christie", "Jin", "Julia", "Kuma",
         "Panda", "Bryan", "Heihachi", "Kazuya", "Lee", "Steve", "Marduk", "Mokujin", "Eddy", "Jack-5", "Roger Jr.", "Anna",
         "Wang", "Ganryu", "Asuka", "Bruce", "Baek", "Devil Jin", "Raven", "Feng", "Armor King", "Lili", "Dragunov",
         "Jinpachi"]
# the select grid (src/directfight/df_fight.cpp kGrid): cell -> character id
GRID = [23, 18, 1, 6, 3, 33, 34, 14, 8, 0, 21, 27,
        22, 2, 5, 17, 15, 7, 9, 16, 10, 4, 13, 11,
        -1, 20, 28, 19, 29, 30, 26, 31, 25, 24, 32]
BUTTONS = {"lp": ("SQUARE", "Square (LP)"), "rp": ("TRIANGLE", "Triangle (RP)"),
           "lk": ("CROSS", "Cross (LK)"), "rk": ("CIRCLE", "Circle (RK)")}
DEFAULT_BTN = "Cross (LK)"


def log(msg):
    print(f"[{time.time() - T0:7.1f}s] {msg}", flush=True)


def char_id(s):
    s = s.strip().lower()
    if s.isdigit():
        return int(s)
    if s in CODES:
        return CODES.index(s)
    for i, n in enumerate(NAMES):
        if n.lower().startswith(s):
            return i
    raise ValueError(f"unknown character {s}")


def cell_of(c):
    if c == 12:
        c = 11
    return GRID.index(c) if c in GRID else -1


def row(c):
    return 0 if c >= 24 else 2 if c >= 12 else 1


def col(c):
    return c - 24 if c >= 24 else c - 12 if c >= 12 else c


def step(cell, target):
    """One cursor step towards target (the driver's navigate(), df_fight.cpp)."""
    r, tr, c, tc = row(cell), row(target), col(cell), col(target)
    if r != tr:
        if tr == 0 and c == 0:
            return "RIGHT"
        if tr == 0 and c == 11:
            return "LEFT"
        return "DOWN" if (tr - r + 3) % 3 == 1 else "UP"
    n = 10 if r == 0 else 12
    cc, tcc = (c - 1, tc - 1) if r == 0 else (c, tc)
    fwd, back = (tcc - cc + n) % n, (cc - tcc + n) % n
    return "RIGHT" if fwd <= back else "LEFT"


def mash_script(path, seed, frames=400000, start_every=0):
    """start_every N: about every N-th input is START (pause mashing; fight_flow_test.mash_script)."""
    rnd = random.Random(seed)
    buttons = [0x4000, 0x2000, 0x8000, 0x1000, 0x4000 | 0x2000, 0x8000 | 0x1000, 0x10, 0x20, 0x40, 0x80, 0x20, 0x80]
    out, f = [], 30
    while f < frames:
        if start_every and rnd.randrange(start_every) == 0:
            n = rnd.randint(1, 4)
            out.append(f"{f} {n} {0x0008 | rnd.choice([0, 0, 0x8000, 0x4000]):#x}")
            f += n + rnd.randint(1, 6)
            continue
        n = rnd.randint(1, 4)
        out.append(f"{f} {n} {rnd.choice(buttons):#x}")
        f += n + rnd.randint(1, 6)
    with open(path, "w") as fp:
        fp.write("\n".join(out) + "\n")
    return path


def read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def write_atomic(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


class Game:
    def __init__(self, a, idx, role):
        self.a, self.idx, self.role = a, idx, role
        self.slot = 0 if role == "host" else 1
        self.dir = os.path.abspath(os.path.join(a.out, f"run{idx}"))
        os.makedirs(self.dir, exist_ok=True)
        self.status_path = os.path.join(self.dir, "status.json")
        self.result_path = os.path.join(self.dir, "result.json")
        self.fight_path = os.path.join(self.dir, "fight.txt")
        self.pad_path = os.path.join(self.dir, "pad.txt")
        self.ctl = os.path.join(self.dir, "ctl")
        self.seq = 0
        self.proc = None
        self.starts = 0
        self.log_path = None
        open(self.pad_path, "w").close()

    def base_env(self):
        vfs = os.path.abspath(self.a.vfs)
        env = dict(os.environ)
        env.update({
            "PS3_VFS_ROOT": vfs.replace("\\", "/"), "PS3_HDD0_ROOT": os.path.join(vfs, "dev_hdd0").replace("\\", "/"),
            "PS3_GCM_TICKER_PUMP": "1", "RSX_LIVE_DRAW": "1", "PS3_VERBOSE": "0", "PS3_WINDOW_BACKGROUND": "1",
            "PS3_AUDIO_MUTE": "1",      # silent (the mix is zeroed after AUDIO_WAV): tests run beside people
            "PAD_NO_KEYBOARD": "1", "T5_NET_LOCALPAD": "0", "PS3_PAD_FILE": self.pad_path, "T5_DF_TRACE": "1",
            "T5_DF_STATUS_FILE": self.status_path, "T5_NET_TIMEOUT": "20", "T5_NET_SCRIPT_FIGHT": "1",
        })
        if self.a.mash:
            env["T5_NET_SCRIPT"] = mash_script(os.path.join(self.dir, "mash.txt"), 100 + self.idx,
                                               start_every=self.a.mash_start)
        if self.a.mash_start:
            env["T5_DF_WATCH"] = ff.PAUSE_WORD   # the pause menu, logged when it opens
        for kv in self.a.env + (self.a.env1 if self.role == "host" else self.a.env2):
            k, v = kv.split("=", 1)
            env[k] = v
        return env

    def start(self, env):
        self.starts += 1
        env["T5_NET_LOG"] = os.path.join(self.dir, f"frames{self.starts}.log")
        self.log_path = os.path.join(self.dir, f"game{self.starts}.log")
        lf = open(self.log_path, "w")
        vfs = os.path.abspath(self.a.vfs)
        self.proc = subprocess.Popen([os.path.abspath(self.a.exe), os.path.join(vfs, "PS3_GAME", "USRDIR", "EBOOT.elf")],
                                     cwd=self.dir, env=env, stdout=lf, stderr=subprocess.STDOUT,
                                     creationflags=getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0))
        log(f"game {self.idx} ({self.role}) started, pid {self.proc.pid}, log {self.log_path}")

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.kill()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                pass

    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def status(self):
        return read_json(self.status_path) or {}

    def send(self, cmd, **kw):
        self.seq += 1
        os.makedirs(self.ctl, exist_ok=True)
        write_atomic(os.path.join(self.ctl, "cmd.json"), json.dumps(dict(kw, seq=self.seq, cmd=cmd, time=time.time())))

    def ctl_state(self):
        return read_json(os.path.join(self.ctl, "state.json")) or {}

    def log_size(self):
        try:
            return os.path.getsize(self.log_path)
        except (OSError, TypeError):
            return 0

    def log_since(self, pos):
        try:
            with open(self.log_path, "rb") as f:
                f.seek(pos)
                return f.read().decode("utf-8", "replace")
        except (OSError, TypeError):
            return ""

    def pad(self, text):
        """The runtime re-reads the pad file on every poll and holds it open meanwhile: a rename over
        it fails then, a plain rewrite does not (an empty read in between is one poll of nothing)."""
        for _ in range(100):
            try:
                with open(self.pad_path, "w") as f:
                    f.write(text)
                return
            except PermissionError:
                time.sleep(0.002)

    def press(self, buttons, hold=0.08, gap=0.17):
        self.pad(buttons)
        time.sleep(hold)
        self.pad("")
        time.sleep(gap)


class Picker(threading.Thread):
    """Plays one player's in-game pick through the game's PS3_PAD_FILE, closed-loop on the
    cursor cell the game logs (T5_DF_TRACE=1)."""

    def __init__(self, game, spec, log_pos, deadline):
        super().__init__(daemon=True)
        self.g, self.spec, self.pos, self.deadline = game, spec, log_pos, deadline
        self.note = ""

    def cell(self):
        cells = re.findall(r"in-game select: (?:cursor at cell|the select screen is live, player \d's cursor at cell) (\d+)",
                           self.g.log_since(self.pos))
        return int(cells[-1]) if cells else None

    def run(self):
        try:
            self.play()
        except Exception as e:     # noqa: BLE001 -- reported with the match
            self.note = f"picker failed: {e!r}"

    def play(self):
        while time.time() < self.deadline and self.cell() is None:
            time.sleep(0.1)
        if self.cell() is None:
            self.note = "the select screen never came"
            return
        spec = self.spec
        if spec == "timeout":
            return
        if spec == "random":
            time.sleep(0.6)
            self.g.press("SELECT", 0.1, 0.3)
            return
        m = re.match(r"late([\d.]+):(.*)", spec)
        if m:
            time.sleep(float(m.group(1)))
            spec = m.group(2)
        ch, btn = spec.split(":")
        target = cell_of(char_id(ch))
        time.sleep(0.4)
        for _ in range(60):
            c = self.cell()
            if c == target:
                break
            self.g.press(step(c, target))
            t = time.time()
            while self.cell() == c and time.time() - t < 0.6:
                time.sleep(0.03)
        else:
            self.note = f"cursor never reached cell {target}"
            return
        time.sleep(0.15)
        self.g.press(BUTTONS[btn][0], 0.1, 0.3)


def session_env(a, k, match, game, port0):
    seed = 1000 + 7919 * k
    if getattr(a, "offline", False):      # no netplay: the driver writes the result file itself
        return {"T5_NET_ROUNDS": str(a.rounds), "T5_NET_RESULT_FILE": game.result_path, "T5_DF_STATUS_FILE": game.status_path,
                "T5_HUD_NAMES": "Tester One|Tester Two", "T5_HUD_RANKS": f"{(k * 3) % 37},{(k * 5) % 37}"}
    env = {
        "T5_NET_MODE": game.role, "T5_NET_DELAY": str(a.delay), "T5_NET_TIMEOUT": "20", "T5_NET_MATCH": match,
        "T5_NET_ROUNDS": str(a.rounds), "T5_NET_PATH": "lan", "T5_NET_RTT_MS": "1", "T5_NET_SEED": str(seed),
        "T5_NET_BUILD": "pick-flow-test", "T5_NET_KEY": f"key-{k}-{seed}", "T5_NET_RESULT_FILE": game.result_path,
        "T5_NET_START": "external", "T5_DF_STATUS_FILE": game.status_path,
        "T5_HUD_NAMES": "Tester One|Tester Two", "T5_HUD_RANKS": f"{(k * 3) % 37},{(k * 5) % 37}",
    }
    env["T5_NET_PORT"] = str(port0 if game.role == "host" else port0 + 1)
    env["T5_NET_PEER"] = f"127.0.0.1:{port0 + 1 if game.role == 'host' else port0}"
    return env


RE_PICKS = re.compile(r"fighters: P1 (.+?) with (.+?) \(model 0x([0-9A-F]+)\), P2 (.+?) with (.+?) \(model 0x([0-9A-F]+)\)")


def expected(spec, line_char):
    """(name, button) a scenario must give, or None (random: anything)."""
    if spec == "random":
        return None
    if spec == "timeout":
        c = char_id(line_char)
        return NAMES[c], ("Square (LP)" if c == 11 else "Circle (RK)" if c == 12 else DEFAULT_BTN)
    m = re.match(r"(?:late[\d.]+:)?(.*):(\w+)$", spec)
    c = char_id(m.group(1))
    if c == 11 and m.group(2) in ("lk", "rk"):
        c = 12
    return NAMES[c], BUTTONS[m.group(2)][1]


class AbortPicker(threading.Thread):
    """One player during a session that will be aborted: moves the cursor a few cells (the preview
    models load), maybe confirms, or does nothing -- until `stop` is set."""

    def __init__(self, game, stop, rnd, may_pick):
        super().__init__(daemon=True)
        self.g, self.stop, self.rnd = game, stop, rnd
        self.what = rnd.choice(["none", "move", "move", "pick"] if may_pick else ["none", "move", "move"])
        self.did = "none"

    def run(self):
        try:
            if self.what == "none":
                return
            for _ in range(self.rnd.randint(1, 6)):
                if self.stop.is_set():
                    return
                self.g.press(self.rnd.choice(["LEFT", "RIGHT", "UP", "DOWN"]), 0.08, self.rnd.uniform(0.1, 0.4))
                self.did = "move"
            if self.what == "pick" and not self.stop.is_set():
                self.g.press(self.rnd.choice(["SQUARE", "TRIANGLE", "CROSS", "CIRCLE"]), 0.1, 0.3)
                self.did = "pick"
        except Exception as e:     # noqa: BLE001 -- the abort goes on
            self.did = f"failed: {e!r}"


def abort_plan(aborts, text):
    """{match k: aborted sessions after it} from --aborts N (k = 0) and --abort-plan 'K:N,...'."""
    plan = {}
    for item in filter(None, (text or "").replace(" ", "").split(",")):
        kk, nn = item.split(":")
        if int(kk) < 0 or int(nn) < 0:
            raise ValueError(f"--abort-plan {item}: K and N must not be negative")
        if int(nn):
            plan[int(kk)] = plan.get(int(kk), 0) + int(nn)
    if aborts:
        plan[0] = plan.get(0, 0) + aborts
    return plan


RE_LIVE = re.compile(r"in-game select: the select screen is live")
RE_RESTARTED = re.compile(r"select screen restarted")


def run_aborts(a, games, n, first_i, rnd, report):
    """n sessions that end at the select screen (see --aborts). False on the first failure."""
    hows = {"mix": ["both", "host", "join"], "both": ["both"], "host": ["host"], "join": ["join"]}[a.abort_how]
    if len(games) == 1:
        hows = ["both"]
    chars = a.chars.split(",")
    for i in range(first_i, first_i + n):
        k = 1000 + i
        mid = f"a{i:03d}"
        port = a.port + 2000 + 4 * (i % 400)
        line = f"{chars[(2 * i) % len(chars)]},{chars[(2 * i + 1) % len(chars)]},{20 + i % 10},{a.rounds} pick={a.pick_seconds}"
        how = hows[i % len(hows)]
        pos = {g.idx: g.log_size() for g in games}
        t0 = time.time()
        for g in games:
            g.send("fight", match=mid, env=dict(session_env(a, k, mid, g, port), T5_FIGHT=line))
        ab = {"i": i, "match": mid, "line": line, "how": how}
        # the select screen live on every game (its in-game select waits for this PC's player)
        t_end = time.time() + 60
        while time.time() < t_end and not all(RE_LIVE.search(g.log_since(pos[g.idx])) for g in games):
            if not all(g.running() for g in games) or any(bad_lines(g.log_since(pos[g.idx])) for g in games):
                break
            time.sleep(0.1)
        live = all(RE_LIVE.search(g.log_since(pos[g.idx])) for g in games)
        stop = threading.Event()
        # one side at most confirms its pick (offline none: P2 would follow at once): the fight never starts
        picker_side = rnd.randrange(len(games)) if len(games) > 1 else -1
        pickers = [AbortPicker(g, stop, rnd, j == picker_side) for j, g in enumerate(games)] if live else []
        for pk in pickers:
            pk.start()
        time.sleep(rnd.uniform(0.4, 4.0) if live else 0)
        stop.set()
        for pk in pickers:
            pk.join(5)
        for g in games:
            g.pad("")
        # the session ends: both launchers leave, or one game's -- the other's session ends by its BYE
        if how == "both":
            order = list(games)
            rnd.shuffle(order)
            for g in order:
                g.send("idle")
                time.sleep(rnd.uniform(0.0, 0.5))
        else:
            leaver = games[0] if how == "host" else games[1]
            leaver.send("idle")
            time.sleep(rnd.uniform(1.0, 2.5))
            for g in games:
                if g is not leaver:
                    g.send("idle")
        # back at neutral, each select screen restarted once more, no fault
        t_end = time.time() + 45
        back = False
        while time.time() < t_end:
            if not all(g.running() for g in games):
                break
            texts = {g.idx: g.log_since(pos[g.idx]) for g in games}
            if any(bad_lines(t) for t in texts.values()):
                break
            if all(g.status().get("state") == "neutral" and int(g.ctl_state().get("seq") or 0) >= g.seq for g in games) \
                    and all(RE_RESTARTED.search(t) for t in texts.values()):
                back = True
                break
            time.sleep(0.2)
        texts = {g.idx: g.log_since(pos[g.idx]) for g in games}
        ab["live"] = live
        ab["pickers"] = [pk.did for pk in pickers]
        ab["restarts"] = {g.idx: len(RE_RESTARTED.findall(texts[g.idx])) for g in games}
        ab["bad"] = {g.idx: bad_lines(texts[g.idx]) for g in games if bad_lines(texts[g.idx])}
        ab["seconds"] = round(time.time() - t0, 1)
        ab["ok"] = live and back and not ab["bad"] and all(g.running() for g in games)
        report.setdefault("aborts", []).append(ab)
        log(f"abort {i} ({mid}, {how}): {'OK' if ab['ok'] else 'FAILED'} -- pickers {ab['pickers']}, "
            f"restarts {ab['restarts']}, {ab['seconds']} s"
            + (f", BAD {ab['bad']}" if ab["bad"] else "") + ("" if live else ", the select screen never came")
            + ("" if back else ", not back at neutral")
            + (", a fight started (too late an abort)" if any("state loading" in t or "state leave" in t for t in texts.values())
               else ""))
        if not ab["ok"]:
            return False
        time.sleep(rnd.uniform(0.2, 1.0))      # the next opponent: the lobby's accept and punch
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--exe", default=os.path.join(ROOT, "build", "cmake", "t5dr.exe"))
    ap.add_argument("--vfs", default=os.path.join(ROOT, "game", "vfs"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--flow", choices=["persistent", "rematch"], default="persistent")
    ap.add_argument("--matches", type=int, default=4)
    ap.add_argument("--first", type=int, default=1, help="the first match's number (match k's line, picks, seed and "
                                                         "ports are the same in every run: --first 4 replays from match 4)")
    ap.add_argument("--rematch-every", type=int, default=3, help="persistent: a new session every K matches")
    ap.add_argument("--picks", default="jin:rp/lil:lk,random/kaz:lp,timeout/xia:rk,kum:lk/random")
    ap.add_argument("--chars", default="hei,dra,ask,law", help="the lines' (launcher) characters, cycled")
    ap.add_argument("--stages", default="20,33,25,31")
    ap.add_argument("--pick-seconds", type=int, default=30)
    ap.add_argument("--locked-after", type=int, default=0)
    ap.add_argument("--no-pick", action="store_true", help="the lines' characters, no in-game select (comparison runs)")
    ap.add_argument("--keep-going", action="store_true", help="go on after a match with a desync or other problem")
    ap.add_argument("--buttons", default="", help="--no-pick: buttons=b1|b2 on the lines (costumes, 1-4)")
    ap.add_argument("--rounds", type=int, default=1)
    ap.add_argument("--delay", type=int, default=2)
    ap.add_argument("--mash", action="store_true")
    ap.add_argument("--mash-start", type=int, default=0, metavar="N",
                    help="--mash: about every N-th input is START (pause mashing); the run fails if a pause menu opens")
    ap.add_argument("--rematch-wait", type=float, default=1.0)
    ap.add_argument("--port", type=int, default=7600)
    ap.add_argument("--seconds", type=float, default=3600)
    ap.add_argument("--match-seconds", type=float, default=420)
    ap.add_argument("--env", action="append", default=[])
    ap.add_argument("--env1", action="append", default=[])
    ap.add_argument("--env2", action="append", default=[])
    ap.add_argument("--aborts", type=int, default=0, help="persistent: N sessions ending at the select screen before match 1")
    ap.add_argument("--abort-plan", default="", help="K:N,... -- N aborted sessions after match K (0 = before match 1)")
    ap.add_argument("--abort-how", choices=["mix", "both", "host", "join"], default="mix")
    ap.add_argument("--offline", action="store_true", help="one game without netplay (persistent flow)")
    ap.add_argument("--fresh-after-aborts", choices=["host", "join"], default=None,
                    help="restart that game after the aborts before match 1: a game whose select screen was "
                         "restarted many times meets a freshly started one")
    ap.add_argument("--seed", type=int, default=1, help="the aborts' random choices")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    plan = abort_plan(a.aborts, a.abort_plan)
    if (plan or a.offline) and a.flow != "persistent":
        sys.exit("--aborts / --abort-plan / --offline need --flow persistent")
    rnd = random.Random(a.seed)
    games = [Game(a, 1, "host")] if a.offline else [Game(a, 1, "host"), Game(a, 2, "join")]
    for g in games:
        for p in (g.status_path, g.result_path, g.fight_path, g.fight_path + ".done", os.path.join(g.ctl, "cmd.json"),
                  os.path.join(g.ctl, "state.json")):
            try:
                os.remove(p)
            except OSError:
                pass
    picks = [s.split("/") for s in a.picks.split(",")]
    chars = a.chars.split(",")
    stages = [int(s) for s in a.stages.split(",")]
    report = {"flow": a.flow, "offline": a.offline, "abort_plan": plan, "matches": []}
    ok_all = True
    n_aborts = 0
    try:
        port, sess_k, sess_first = a.port, 1, 1
        locked = None
        fixed_time = str(int(time.time()))
        if plan.get(0):
            for g in games:      # the games come up at the title and wait at a select screen, nothing pending
                e = g.base_env()
                e["T5_CTL_DIR"] = g.ctl
                g.start(e)
            t_end = time.time() + 120
            while time.time() < t_end and not all(g.status().get("state") == "neutral" for g in games):
                time.sleep(0.5)
            if not run_aborts(a, games, plan[0], n_aborts, rnd, report):
                ok_all = False
                raise StopIteration
            n_aborts += plan[0]
            if a.fresh_after_aborts and not a.offline:
                g = games[0] if a.fresh_after_aborts == "host" else games[1]
                log(f"game {g.idx} ({g.role}) stopped: match 1 meets a freshly started game")
                g.stop()
        for k in range(a.first, a.first + a.matches):
            mid = f"p{k:02d}"
            new_session = a.flow == "persistent" and (k == a.first or (k - 1) % a.rematch_every == 0)
            rematch = not new_session and k > 1
            if new_session:
                port, sess_k, sess_first, locked = a.port + 4 * k, k, k, None
            p1c, p2c = chars[(2 * k) % len(chars)], chars[(2 * k + 1) % len(chars)]
            n_in_session = k - sess_first
            lock = a.locked_after and n_in_session >= a.locked_after and locked
            if a.no_pick:
                line = f"{p1c},{p2c},{stages[k % len(stages)]},{a.rounds}" + (f" buttons={a.buttons}" if a.buttons else "")
                spec = None
            elif lock:
                line = f"{locked[0]},{locked[1]},{stages[k % len(stages)]},{a.rounds}"
                spec = None
            else:
                line = f"{p1c},{p2c},{stages[k % len(stages)]},{a.rounds} pick={a.pick_seconds}"
                spec = picks[(k - 1) % len(picks)]
            base, pos, t_cmd = {}, {}, {}
            for g in games:
                try:
                    os.replace(g.result_path, os.path.join(g.dir, f"result-before-{mid}.json"))
                except OSError:
                    pass
                base[g.idx] = int(g.status().get("match") or 0)
                pos[g.idx] = g.log_size()
            for g in games:
                env = session_env(a, sess_k, mid, g, port)
                if a.flow == "rematch":
                    if k == a.first:
                        e = g.base_env()
                        e.update(env)
                        e.update({"T5_FIGHT": line, "T5_FIGHT_FILE": g.fight_path, "PS3_FIXED_TIME": fixed_time})
                        g.start(e)
                        pos[g.idx] = 0
                    else:
                        time.sleep(random.uniform(0.2, 1.5))
                        write_atomic(g.fight_path, f"{line} match={mid}\n")
                else:
                    if not g.running():
                        e = g.base_env()
                        e["T5_CTL_DIR"] = g.ctl
                        g.seq = 0
                        g.send("fight", match=mid, env=dict(env, T5_FIGHT=line))
                        g.start(e)
                        base[g.idx], pos[g.idx] = 0, 0
                    else:
                        if new_session:
                            g.send("idle")
                            time.sleep(random.uniform(0.3, 1.0))
                        g.send("fight", match=mid, env=dict(env, T5_FIGHT=line), rematch=rematch)
                t_cmd[g.idx] = time.time()
            log(f"match {k} ({mid}): {line}{' (rematch)' if rematch else ''}{' LOCKED' if lock else ''}, picks {spec}")
            pickers = []
            if spec and a.offline:
                spec = [spec[0], "timeout"]       # no netplay: P2 keeps the line's character
            if spec:
                for g in games:
                    pk = Picker(g, spec[g.slot], pos[g.idx], time.time() + 240)
                    pk.start()
                    pickers.append(pk)
            m = {"k": k, "match": mid, "line": line, "rematch": rematch, "locked": bool(lock), "spec": spec}
            t_fight, results = {}, {}
            t_end = time.time() + a.match_seconds
            while time.time() < t_end and time.time() - T0 < a.seconds:
                for g in games:
                    st = g.status()
                    if g.idx not in t_fight and st.get("state") == "fight" and int(st.get("match") or 0) > base[g.idx]:
                        t_fight[g.idx] = time.time()
                        log(f"match {k}: game {g.idx} FIGHT after {t_fight[g.idx] - t_cmd[g.idx]:.1f} s")
                    r = read_json(g.result_path)
                    if r and r.get("match") == mid and g.idx not in results:
                        results[g.idx] = r
                        log(f"match {k}: game {g.idx} result {json.dumps(r)}")
                if len(results) == len(games) or not all(g.running() for g in games):
                    break
                time.sleep(0.25)
            got = {}
            for g in games:
                text = g.log_since(pos[g.idx])
                mm = RE_PICKS.search(text)
                got[g.idx] = mm.groups() if mm else None
                if "PICK MISMATCH" in text:
                    m.setdefault("problems", []).append(f"game {g.idx}: PICK MISMATCH")
            m["picks"] = got
            problems = m.setdefault("problems", [])
            for g in games:
                bad = bad_lines(g.log_since(pos[g.idx]))
                if bad:
                    problems.append(f"game {g.idx}: {bad}")
            if a.offline:
                got[2] = got[1]
            if got[1] is None or got[1] != got[2]:
                problems.append(f"picks differ or missing: {got}")
            elif spec:
                for side in (0, 1):
                    want = expected(spec[side], (p1c, p2c)[side])
                    if a.offline and side == 1:     # the driver confirms the line's character with its default button
                        want = (NAMES[char_id(p2c)], "default")
                    have = (got[1][3 * side], got[1][3 * side + 1])
                    if want and tuple(want) != have:
                        problems.append(f"P{side + 1} picked {have}, wanted {want}")
            elif lock and got[1]:
                want = (NAMES[char_id(locked[0])], NAMES[char_id(locked[1])])
                if (got[1][0], got[1][3]) != want:
                    problems.append(f"locked match fought {(got[1][0], got[1][3])}, wanted {want}")
            for pk in pickers:
                if pk.note:
                    problems.append(f"picker game {pk.g.idx}: {pk.note}")
            if got.get(1) and a.locked_after and n_in_session == 0:
                locked = (str(NAMES.index(got[1][0])), str(NAMES.index(got[1][3])))
            r1, r2 = results.get(1), results.get(2)
            if a.offline:
                r2 = r1
            res_ok = (r1 is not None and r2 is not None and r1.get("winner") == r2.get("winner")
                      and r1.get("winner") is not None and r1.get("hash") == r2.get("hash")
                      and not r1.get("desync") and not r2.get("desync"))
            if not res_ok:
                problems.append("results differ, missing, or desync")
            m["to_fight_s"] = {g.idx: round(t_fight[g.idx] - t_cmd[g.idx], 1) if g.idx in t_fight else None for g in games}
            m["results"] = results
            m["ok"] = not problems
            ok_all &= m["ok"]
            report["matches"].append(m)
            log(f"match {k}: {'OK' if m['ok'] else 'FAILED'} -- picks {got.get(1)}, to FIGHT {m['to_fight_s']}, winners "
                f"{[r and r.get('winner') for r in (r1, r2)]}, desync {[r and r.get('desync') for r in (r1, r2)]}"
                + (f"; problems {problems}" if problems else ""))
            if (not res_ok and not a.keep_going) or not all(g.running() for g in games) or len(results) < len(games):
                ok_all = False
                break
            time.sleep(a.rematch_wait)
            if plan.get(k):
                if not run_aborts(a, games, plan[k], n_aborts, rnd, report):
                    ok_all = False
                    break
                n_aborts += plan[k]
        time.sleep(2.0)
    except StopIteration:
        pass
    finally:
        for g in games:
            g.stop()
        for g in games:
            sync = []
            for fn in sorted(f for f in os.listdir(g.dir) if f.startswith("game") and f.endswith(".log")):
                with open(os.path.join(g.dir, fn), encoding="utf-8", errors="replace") as f:
                    for ln in f:
                        mm = re.search(r"sync check through frame (\d+): (\d+) mismatching", ln)
                        if mm:
                            sync.append((fn, int(mm.group(1)), int(mm.group(2))))
            report[f"sync{g.idx}"] = sync[-3:]
            log(f"game {g.idx}: last sync checks {sync[-3:]}")
        if a.mash_start:
            for g in games:
                opens = ff.pause_menu_opens(os.path.join(g.dir, "df_frames.log"))
                tally = [0, 0, 0]
                for fn in sorted(f for f in os.listdir(g.dir) if f.startswith("game") and f.endswith(".log")):
                    tally = [x + y for x, y in zip(tally, ff.start_tally(os.path.join(g.dir, fn)))]
                report[f"pause{g.idx}"] = {"menu_opened": opens, "start_cut_p1": tally[0], "start_cut_p2": tally[1],
                                           "start_kept": tally[2]}
                log(f"game {g.idx}: pause menu opened {opens} time(s); START taken out on {tally[0]} (P1) + "
                    f"{tally[1]} (P2) frames, kept on {tally[2]} (post-match skip)")
                if opens:
                    ok_all = False
        if report.get("aborts"):
            n_ok = sum(1 for ab in report["aborts"] if ab["ok"])
            restarts = {g.idx: sum(ab["restarts"].get(g.idx, 0) for ab in report["aborts"]) for g in games}
            report["restarts"] = restarts
            log(f"aborted sessions: {n_ok}/{len(report['aborts'])} OK, select restarts per game {restarts}")
        report["ok"] = ok_all
        with open(os.path.join(a.out, "report.json"), "w") as f:
            json.dump(report, f, indent=1)
        n_ok = sum(1 for m in report["matches"] if m["ok"])
        log(f"{'ALL OK' if ok_all else 'FAILED'}: {n_ok}/{a.matches} matches; report {os.path.join(a.out, 'report.json')}")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
