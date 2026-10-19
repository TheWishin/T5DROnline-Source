#!/usr/bin/env python3
"""Two games on this PC, many matches in a row, the way the launcher drives them.

    python tools/fight_flow_test.py --exe build/cmake/t5dr.exe --out build/ff/runs/r1 \
        [--flow rematch|persistent] [--matches 4] [--mash] [--rounds 1] [--fresh-at N] [--seconds 1500]

--flow rematch (process mode): one host + one joiner started with T5_FIGHT (direct
fight, T5_NET_START=external); every next match is a line in each game's
T5_FIGHT_FILE, written at slightly different times on the two sides (two launchers).

--flow persistent (T5_CTL_DIR): both games are started once without netplay and get
every match as a control command (docs/DIRECTFIGHT.md "Persistent game"): "idle",
then "fight" with a NEW session each time (new UDP ports, seed, key, match id), as
for a new opponent. --rematch-every K makes every K-th match a rematch in the
running session instead. --fresh-at N restarts the joiner's game (--fresh-role host: the host's) before match N (a
new opponent whose game has just started meets a game that has played already).

--exe2 runs the joiner's game from another build (tools/cross_build_test.py).

--mash: both players press face buttons and directions at random the whole time
(T5_NET_SCRIPT: fights, KOs, win poses, select screens). --rematch-wait 20 gives
the next command only 20 s after the results (people clicking Rematch late): the
games wait at a live select screen meanwhile, which is where mashing used to start
the game's own next VS battle.

How real players differ from the scripted flow (rematch-fix, 2026-10-18):

  --pattern NNR     persistent: the kind of every match in turn, N = a new session
                    (a new opponent, or a room's "Ready" again: "idle", then "fight"
                    with new ports/seed/key), R = a rematch in the running session.
                    "NNR" = room match, Ready again, then Rematch (the 1.0.0 report).
                    Match 1 is always N. Overrides --rematch-every.
  --same-chars      a rematch keeps the last match's characters (the lobby does; the
                    cursor then sits on the right cell and confirms at once)
  --skew S          one launcher hands its game the command S seconds after the
                    other (+-20 %); --skew-first host|join|alt|random says whose is
                    first (default host: P1 first, the order that hung 1.0.0)
  --stutter MS      the joiner's game is suspended for MS every 0.2-0.6 s during the
                    matches (a choppy PC: rollbacks all the time, the select included)
  --close K:ROLE:S  in match K, S seconds after that game's FIGHT START, the window of
                    ROLE's game (host|join) gets WM_CLOSE (what Alt+F4 and the X button
                    send). Expected: that game ends at once with "quit" in its result
                    file and exit code 7, the other side's result says peer_quit; the
                    closed game is started again (fresh, like the launcher) for the
                    next match, which must be a new session (never the old one)
  --hz2 HZ          the joiner's display runs at HZ (RSX_TEST_DISPLAY_HZ: 240 = no
                    display lock, the game on the 59.94 Hz clock, like the friend's PC)

Two different PCs (desync hunt, 2026-10-18; docs/NETPLAY.md "Desync hunt"):

  --cpus1/--cpus2 N|0xMASK   that game runs on N logical processors (0..N-1) or the mask,
                    and PS3_CPUS says so (its thread pools size from it): a 4-, 6-, 8-
                    or 16-core PC. The game starts suspended, gets the mask, resumes.
  --hitch2 MS[:MIN:MAX]      the joiner's main thread stalls MS at a frame boundary every
                    MIN..MAX frames (T5_TEST_HITCH) while its other threads run on (a
                    shader compile or a busy PC; --stutter stops the whole process)
  --gamedata1/--gamedata2 DIR   copy DIR (a gamedata tree: dev_hdd0/home/.../savedata)
                    into that game's folder before it starts: a player's own save with
                    its options and custom characters (a fresh folder has the defaults)
  --clock2 SECONDS  the joiner's clock runs SECONDS away from the host's
                    (PS3_FIXED_TIME=<now+S>+, a running clock; persistent games use the
                    real clock, so two PCs never read the same time)

Checks, per match: both games reach FIGHT START of that match, both write its
result file (same winner and state hash, 0 mismatching frames). Prints the time
from the command (fight file / control command) to FIGHT START on both sides.
Every game log is scanned for FIFO stalls ("queued flip never reached by the FIFO
walker", "drain stalled") and walker resyncs; a stall fails the run.
Windows open minimized, host devices are ignored, every game is killed at the end.
Exit code 0 = every match fought and confirmed on both sides.
"""
import argparse
import ctypes
import json
import os
import random
import re
import subprocess
import sys
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T0 = time.time()


def log(msg):
    print(f"[{time.time() - T0:7.1f}s] {msg}", flush=True)


# Pad bits (PadInput.buttons: DIGITAL1 | DIGITAL2 << 8) and the Tekken buttons 1/2/3/4 = LP/RP/LK/RK.
U, R, D, L = 0x10, 0x20, 0x40, 0x80
B1, B2, B3, B4 = 0x8000, 0x1000, 0x4000, 0x2000


def motion_moves(fwd, back):
    """What players do and a random mash almost never does: frame-exact motion inputs (electrics,
    hellsweeps, dragon-punch and half-circle motions, dashes, sidesteps), throws and the all-buttons
    ki charge -- each a list of (mask, frames). fwd/back: the direction bits for one facing."""
    df, db = D | fwd, D | back
    return [
        [(fwd, 1), (0, 1), (D, 1), (df | B2, 2)],                 # electric wind god fist (f,n,d,df+2)
        [(fwd, 1), (0, 1), (D, 1), (df | B1, 2)],                 # wind god fist family, df+1
        [(fwd, 1), (0, 1), (D, 1), (df | B4, 2)],                 # hellsweep (f,n,d,df+4)
        [(fwd, 2), (0, 2), (D, 2), (df, 1), (df | B2, 3)],        # slower wgf
        [(D, 1), (df, 1), (fwd | B1, 2)],                         # qcf+1
        [(D, 1), (db, 1), (back | B2, 2)],                        # qcb+2
        [(fwd, 1), (df, 1), (D, 1), (db, 1), (back | B1, 2)],     # hcb+1
        [(back, 1), (db, 1), (D, 1), (df, 1), (fwd | B3, 2)],     # hcf+3
        [(fwd, 2), (0, 2), (fwd, 6)],                             # dash
        [(back, 2), (0, 2), (back, 2), (0, 2), (back, 2)],        # backdash
        [(U, 1), (0, 3)], [(D, 1), (0, 3)],                       # sidesteps
        [(B1 | B3, 2)], [(B2 | B4, 2)],                           # throws
        [(df | B1 | B2, 2)], [(back | B1 | B2, 3)], [(fwd | B3 | B4, 2)], [(U | fwd | B3 | B4, 2)],
        [(B1 | B2 | B3 | B4, 40)],                                # ki charge (Mishimas)
        [(D, 6), (df | B2, 2)], [(D, 6), (D | B4, 2)],            # crouch moves
        [(fwd | B2, 2), (0, 4), (B1, 2)], [(B1, 2), (0, 3), (B2, 2), (0, 3), (B1, 2)],   # strings
        [(back, 20), (back | B2, 2)],                             # charged back moves
    ]


START = 0x0008


def mash_script(path, seed, frames=400000, gap=6, moves=False, start_every=0):
    """Face buttons and directions, 1-4 frames each, 1..gap frames apart (no START: that paused a fight
    before 1.1.2). gap 6 (default) is button mashing; ~20 is closer to a person (fewer inputs the peer
    mispredicts). moves: half of the inputs are motion inputs (motion_moves) in either facing.
    start_every N: about every N-th input is START (alone or with an attack) -- a player mashing pause;
    online it must never pause (docs/NETPLAY.md "No pause online"). The script is not filtered on the
    sending side, so START reaches the wire like from a modified client."""
    rnd = random.Random(seed)
    buttons = [0x4000, 0x2000, 0x8000, 0x1000, 0x4000 | 0x2000, 0x8000 | 0x1000, 0x10, 0x20, 0x40, 0x80, 0x20, 0x80]
    seqs = motion_moves(R, L) + motion_moves(L, R)
    out, f = [], 30
    while f < frames:
        if start_every and rnd.randrange(start_every) == 0:
            n = rnd.randint(1, 4)
            out.append(f"{f} {n} {START | rnd.choice([0, 0, 0x8000, 0x4000]):#x}")
            f += n + rnd.randint(1, gap)
            continue
        if moves and rnd.random() < 0.5:
            for mask, n in rnd.choice(seqs):
                if mask:
                    out.append(f"{f} {n} {mask:#x}")
                f += n
            f += rnd.randint(1, gap)
            continue
        n = rnd.randint(1, 4)
        out.append(f"{f} {n} {rnd.choice(buttons):#x}")
        f += n + rnd.randint(1, gap)
    with open(path, "w") as fp:
        fp.write("\n".join(out) + "\n")
    return path


def read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


# ---- Windows helpers: a choppy PC (suspend/resume), a closed window (WM_CLOSE) ---------------
_ntdll = ctypes.WinDLL("ntdll") if os.name == "nt" else None
_k32 = ctypes.WinDLL("kernel32", use_last_error=True) if os.name == "nt" else None
_u32 = ctypes.WinDLL("user32", use_last_error=True) if os.name == "nt" else None


def cpu_mask(spec):
    """--cpus1/--cpus2: N = logical processors 0..N-1, or 0xMASK; 0 = no change."""
    if not spec:
        return 0
    return int(spec, 16) if spec.lower().startswith("0x") else (1 << int(spec)) - 1


def suspend_process(pid, on):
    h = _k32.OpenProcess(0x0800, False, pid)          # PROCESS_SUSPEND_RESUME
    if not h:
        return False
    try:
        return (_ntdll.NtSuspendProcess(h) if on else _ntdll.NtResumeProcess(h)) == 0
    finally:
        _k32.CloseHandle(h)


def close_windows(pid):
    """WM_CLOSE to every top-level window of the process (Alt+F4 / the X button). Returns how many."""
    import ctypes.wintypes as wt
    found = []
    proto_ = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

    def cb(h, _lp):
        p = wt.DWORD()
        _u32.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value == pid and _u32.IsWindowVisible(h):
            found.append(h)
        return True
    _u32.EnumWindows(proto_(cb), 0)
    for h in found:
        _u32.PostMessageW(h, 0x0010, 0, 0)
    return len(found)


# The game's pause menu (VS fight): this word goes 0 -> 2 when it opens and back to 0 when it closes
# (with 0x1008F0B4/B8 1 -> 0 and 0x100996B4 1 -> 3; build/nopause probes p1/p4, docs/NETPLAY.md
# "No pause online"). With T5_DF_WATCH the direct-fight log has every change.
PAUSE_WORD = "10092EA0"
RE_PAUSE_OPEN = re.compile(r"\[0x10092EA0\] 0x00000000 -> 0x0*[1-9A-F]")
RE_NO_PAUSE = re.compile(r"no pause online, (the match|after the last match): START taken out on (\d+) frame\(s\) of P1's "
                         r"input and (\d+) of P2's, kept on (\d+)")


def pause_menu_opens(path):
    """How often the pause menu opened in a direct-fight log (T5_DF_WATCH with PAUSE_WORD)."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return sum(1 for ln in f if RE_PAUSE_OPEN.search(ln))
    except OSError:
        return 0


def start_tally(path):
    """START frames the no-pause rule took out of P1's / P2's input, and kept (the post-match skip)."""
    t = [0, 0, 0]
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for ln in f:
                m = RE_NO_PAUSE.search(ln)
                if m:
                    for i in range(3):
                        t[i] += int(m.group(2 + i))
    except OSError:
        pass
    return t


FIFO_BAD = (("fifo_stall", re.compile(r"queued flip never reached by the FIFO walker")),
            ("drain_stalled", re.compile(r"fifo recycle: drain stalled")),
            ("fifo_resync", re.compile(r"\[cellGcmSys\] FIFO (resync|walker circling)")))


def scan_fifo(path):
    out = {}
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for ln in f:
                for name, rx in FIFO_BAD:
                    if rx.search(ln):
                        out[name] = out.get(name, 0) + 1
    except OSError:
        pass
    return out


def write_atomic(path, text):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    for i in range(50):          # a game reading the old file this moment (older builds: no delete sharing)
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if i == 49:
                raise
            time.sleep(0.01)


class Game:
    def __init__(self, a, idx, role):
        self.a, self.idx, self.role = a, idx, role
        self.dir = os.path.abspath(os.path.join(a.out, f"run{idx}"))
        os.makedirs(self.dir, exist_ok=True)
        self.status_path = os.path.join(self.dir, "status.json")
        self.result_path = os.path.join(self.dir, "result.json")
        self.fight_path = os.path.join(self.dir, "fight.txt")
        self.ctl = os.path.join(self.dir, "ctl")
        self.seq = 0
        self.proc = None
        self.starts = 0

    def base_env(self):
        vfs = os.path.abspath(self.a.vfs)
        env = dict(os.environ)
        env.update({
            "PS3_VFS_ROOT": vfs.replace("\\", "/"), "PS3_HDD0_ROOT": os.path.join(vfs, "dev_hdd0").replace("\\", "/"),
            "PS3_GCM_TICKER_PUMP": "1", "RSX_LIVE_DRAW": "1", "PS3_VERBOSE": "0", "PS3_WINDOW_BACKGROUND": "1",
            "PAD_NO_KEYBOARD": "1", "T5_NET_LOCALPAD": "0", "T5_NET_LOG": os.path.join(self.dir, f"frames{self.starts}.log"),
            "T5_DF_STATUS_FILE": self.status_path, "T5_NET_TIMEOUT": "20",
        })
        if self.a.mash:
            env["T5_NET_SCRIPT"] = mash_script(os.path.join(self.dir, "mash.txt"), 100 + self.idx,
                                               gap=getattr(self.a, "mash_gap", 6), moves=getattr(self.a, "moves", False),
                                               start_every=getattr(self.a, "mash_start", 0))
        if getattr(self.a, "mash_start", 0):
            env["T5_DF_WATCH"] = PAUSE_WORD   # the pause menu, logged when it opens (pause_menu_opens)
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
        exe = self.a.exe2 if self.role == "join" and self.a.exe2 else self.a.exe
        flags = 0x00004000 if getattr(self.a, "below_normal", False) and os.name == "nt" else 0   # BELOW_NORMAL_PRIORITY_CLASS
        gd = self.a.gamedata1 if self.role == "host" else self.a.gamedata2
        if gd and self.starts == 1:      # a player's own save: copied once, the game keeps writing it
            import shutil
            dst = os.path.join(self.dir, "gamedata")
            shutil.rmtree(dst, ignore_errors=True)
            shutil.copytree(gd, dst)
            log(f"game {self.idx}: save data from {gd}")
        mask = cpu_mask(self.a.cpus1 if self.role == "host" else self.a.cpus2)
        if mask:
            env["PS3_CPUS"] = str(bin(mask).count("1"))
            flags |= 0x00000004          # CREATE_SUSPENDED: the mask is in before the game sizes its pools
        self.proc = subprocess.Popen([os.path.abspath(exe), os.path.join(vfs, "PS3_GAME", "USRDIR", "EBOOT.elf")],
                                     cwd=self.dir, env=env, stdout=lf, stderr=subprocess.STDOUT, creationflags=flags)
        if mask:
            ok = _k32.SetProcessAffinityMask(ctypes.c_void_p(int(self.proc._handle)), ctypes.c_size_t(mask))
            suspend_process(self.proc.pid, False)
            log(f"game {self.idx}: affinity {mask:#x} ({bin(mask).count('1')} logical processors){'' if ok else ' FAILED'}")
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
        d = dict(kw, seq=self.seq, cmd=cmd, time=time.time())
        write_atomic(os.path.join(self.ctl, "cmd.json"), json.dumps(d))

    def ctl_state(self):
        return read_json(os.path.join(self.ctl, "state.json")) or {}


def session_env(a, k, match, game, port0):
    """T5_NET_* for a match of session k as the lobby would hand it out (new ports/seed/key per session)."""
    seed = 1000 + 7919 * k
    env = {
        "T5_NET_MODE": game.role, "T5_NET_DELAY": str(a.delay), "T5_NET_TIMEOUT": "20", "T5_NET_MATCH": match,
        "T5_NET_ROUNDS": str(a.rounds), "T5_NET_PATH": "lan", "T5_NET_RTT_MS": "1", "T5_NET_SEED": str(seed),
        "T5_NET_BUILD": "fight-flow-test", "T5_NET_KEY": f"key-{k}-{seed}", "T5_NET_RESULT_FILE": game.result_path,
        "T5_NET_START": "external", "T5_DF_STATUS_FILE": game.status_path,
        "T5_HUD_NAMES": "Tester One|Tester Two", "T5_HUD_RANKS": f"{(k * 3) % 37},{(k * 5) % 37}",
    }
    if game.role == "host":
        env["T5_NET_PORT"] = str(port0)
        env["T5_NET_PEER"] = f"127.0.0.1:{port0 + 1}"
    else:
        env["T5_NET_PORT"] = str(port0 + 1)
        env["T5_NET_PEER"] = f"127.0.0.1:{port0}"
    return env


def fight_line(a, k, prev=None):
    """The k-th match's T5_FIGHT line; a rematch with --same-chars keeps prev's characters (the lobby
    keeps the players' picks, the stage is drawn again)."""
    chars = a.chars.split(",")
    p1, p2 = chars[(2 * k) % len(chars)], chars[(2 * k + 1) % len(chars)]
    colors = (a.colors or "").split(",") if getattr(a, "colors", "") else []
    c1 = colors[(2 * k) % len(colors)] if colors else ""
    c2 = colors[(2 * k + 1) % len(colors)] if colors else ""
    if prev:
        p1, p2 = prev.split(",")[:2]
        if colors:
            c1, c2 = prev.split(",")[4:6]
    stages = [int(s) for s in a.stages.split(",")]
    return f"{p1},{p2},{stages[k % len(stages)]},{a.rounds}" + (f",{c1},{c2}" if colors else "")


def match_kind(a, k):
    """'N' (a new session) or 'R' (a rematch in the running session) for match k."""
    if k == 1:
        return "N"
    if a.flow == "rematch":
        return "R"
    if a.pattern:
        return a.pattern[(k - 1) % len(a.pattern)].upper()
    return "R" if a.rematch_every and (k - 1) % a.rematch_every == 0 else "N"


def stutter_loop(games, ms, on, stop):
    """--stutter: the joiner's game is suspended for `ms` every 0.2-0.6 s while `on` is set."""
    while not stop.is_set():
        time.sleep(random.uniform(0.2, 0.6))
        if not on.is_set():
            continue
        g = games[1]
        if not g.running():
            continue
        suspend_process(g.proc.pid, True)
        time.sleep(ms / 1000.0)
        suspend_process(g.proc.pid, False)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--exe", default=os.path.join(ROOT, "build", "cmake", "t5dr.exe"))
    ap.add_argument("--vfs", default=os.path.join(ROOT, "game", "vfs"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--flow", choices=["rematch", "persistent"], default="rematch")
    ap.add_argument("--matches", type=int, default=3)
    ap.add_argument("--rounds", type=int, default=1)
    ap.add_argument("--delay", type=int, default=2)
    ap.add_argument("--chars", default="kaz,hei,lil,dra")
    ap.add_argument("--stages", default="20,33,25,31")
    ap.add_argument("--mash", action="store_true")
    ap.add_argument("--mash-gap", type=int, default=6, help="--mash: at most this many frames between presses (20 ~ a person)")
    ap.add_argument("--mash-start", type=int, default=0, metavar="N",
                    help="--mash: about every N-th input is START (pause mashing); the run fails if a pause menu opens")
    ap.add_argument("--moves", action="store_true", help="--mash with motion inputs (electrics, hellsweeps, qcf/hcb, "
                                                        "dashes, throws, ki charge): what players do")
    ap.add_argument("--rematch-every", type=int, default=0, help="persistent: every K-th match is a rematch in the session")
    ap.add_argument("--pattern", default="", help="persistent: N (new session) / R (rematch) per match in turn, e.g. NNR")
    ap.add_argument("--same-chars", action="store_true", help="a rematch keeps the last match's characters (the lobby's way)")
    ap.add_argument("--skew", type=float, default=0.0, help="the second launcher's command comes this many seconds later")
    ap.add_argument("--skew-first", choices=["host", "join", "alt", "random"], default="host")
    ap.add_argument("--stutter", type=int, default=0, help="suspend the joiner's game for MS every 0.2-0.6 s in matches")
    ap.add_argument("--close", action="append", default=[], help="K:ROLE:S -- WM_CLOSE to ROLE's window S s into match K")
    ap.add_argument("--hz2", type=float, default=0.0, help="the joiner's display rate (RSX_TEST_DISPLAY_HZ)")
    ap.add_argument("--polite", action="store_true",
                    help="someone is using this PC: games muted (PS3_AUDIO_MUTE=1) at below-normal priority")
    ap.add_argument("--fresh-at", type=int, default=0, help="persistent: restart the joiner's game before this match")
    ap.add_argument("--fresh-role", choices=["host", "join", "alt"], default="join",
                    help="--fresh-at/--fresh-every restart this side's game (alt: host and joiner in turn)")
    ap.add_argument("--fresh-every", type=int, default=0,
                    help="persistent: every K-th match after the first is an opponent switch against a fresh game")
    ap.add_argument("--colors", default="", help="costumes 1|2 per character slot, cycled like --chars (T5_FIGHT p1color,p2color)")
    ap.add_argument("--rematch-wait", type=float, default=1.0,
                    help="seconds between a match's results and the next command (players clicking Rematch late: 20)")
    ap.add_argument("--port", type=int, default=7400)
    ap.add_argument("--seconds", type=float, default=1800)
    ap.add_argument("--match-seconds", type=float, default=420, help="give up on a match after this long")
    ap.add_argument("--env", action="append", default=[], help="NAME=VALUE for both games")
    ap.add_argument("--env1", action="append", default=[], help="NAME=VALUE for the host's game only")
    ap.add_argument("--env2", action="append", default=[], help="NAME=VALUE for the joiner's game only")
    ap.add_argument("--exe2", help="the joiner's t5dr.exe (another build, t5dr_game.dll beside it; "
                                   "tools/cross_build_test.py --flow persistent)")
    ap.add_argument("--cpus1", default="", help="host's CPUs: N logical processors or 0xMASK (+ PS3_CPUS)")
    ap.add_argument("--cpus2", default="", help="joiner's CPUs: N logical processors or 0xMASK (+ PS3_CPUS)")
    ap.add_argument("--hitch2", default="", help="MS[:MIN:MAX] -- the joiner's main thread stalls (T5_TEST_HITCH)")
    ap.add_argument("--gamedata1", default="", help="copy this gamedata tree (a player's save) for the host's game")
    ap.add_argument("--gamedata2", default="", help="copy this gamedata tree (a player's save) for the joiner's game")
    ap.add_argument("--clock2", type=float, default=0.0, help="the joiner's clock this many seconds off the host's")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    a.below_normal = a.polite
    if a.polite:
        a.env = a.env + ["PS3_AUDIO_MUTE=1"]
    if a.hz2:
        a.env2 = a.env2 + [f"RSX_TEST_DISPLAY_HZ={a.hz2:g}"]
    if a.hitch2:
        a.env2 = a.env2 + [f"T5_TEST_HITCH={a.hitch2}"]
    if a.clock2:
        a.env2 = a.env2 + [f"PS3_FIXED_TIME={int(time.time() + a.clock2)}+"]
    for g, gd in (("1", a.gamedata1), ("2", a.gamedata2)):
        if gd and not os.path.isdir(os.path.join(gd, "dev_hdd0")):
            sys.exit(f"--gamedata{g}: {gd} has no dev_hdd0 folder")
    closes = {}
    for c in a.close:
        k, role, sec = c.split(":")
        closes[int(k)] = (role, float(sec))
    if closes and a.flow != "persistent":
        sys.exit("--close needs --flow persistent (the closed game comes back as a fresh persistent game)")

    games = [Game(a, 1, "host"), Game(a, 2, "join")]
    for g in games:
        for p in (g.status_path, g.result_path, g.fight_path, g.fight_path + ".done", os.path.join(g.ctl, "cmd.json"),
                  os.path.join(g.ctl, "state.json")):
            try:
                os.remove(p)
            except OSError:
                pass
    report = {"flow": a.flow, "mash": a.mash, "mash_start": a.mash_start, "pattern": a.pattern, "skew": a.skew, "stutter": a.stutter,
              "hz2": a.hz2, "env": a.env, "env1": a.env1, "env2": a.env2, "cpus": [a.cpus1, a.cpus2],
              "gamedata": [a.gamedata1, a.gamedata2], "matches": []}
    ok_all = True
    stop = threading.Event()
    st_on = threading.Event()
    if a.stutter:
        threading.Thread(target=stutter_loop, args=(games, a.stutter, st_on, stop), daemon=True).start()
    try:
        port = a.port
        sess_k = 1
        fixed_time = str(int(time.time()))
        prev_line = None
        session_alive = False
        for k in range(1, a.matches + 1):
            mid = f"t{k:02d}"
            kind = match_kind(a, k)
            if kind == "R" and a.flow == "persistent" and not session_alive:
                kind = "N"                     # the session ended (a closed game): a new one
            rematch = kind == "R"
            line = fight_line(a, k, prev_line if (rematch and a.same_chars) else None)
            if a.flow == "persistent" and not rematch:
                port = a.port + 4 * k
                sess_k = k
            base = {}
            for g in games:
                try:
                    os.replace(g.result_path, os.path.join(g.dir, f"result-before-{mid}.json"))
                except OSError:
                    pass
            # who gets the command first, and how much later the other one (two launchers)
            first = {"host": 0, "join": 1, "alt": (k + 1) % 2, "random": random.randint(0, 1)}[a.skew_first]
            order = [games[first], games[1 - first]]
            delays = [0.0, a.skew * random.uniform(0.8, 1.2) if a.skew else 0.0]
            t_cmd = {}
            t_prev = time.time()
            for (g, dly) in zip(order, delays):
                env = session_env(a, sess_k, mid, g, port)
                st = g.status()
                base[g.idx] = int(st.get("match") or 0)
                wait = dly - (time.time() - t_prev)
                if wait > 0:
                    time.sleep(wait)
                if a.flow == "rematch":
                    if k == 1:
                        e = g.base_env()
                        e.update(env)
                        e.update({"T5_FIGHT": line, "T5_FIGHT_FILE": g.fight_path, "PS3_FIXED_TIME": fixed_time})
                        g.start(e)
                    else:
                        if not a.skew:
                            time.sleep(random.uniform(0.2, 1.5))   # two launchers never write at the same moment
                        write_atomic(g.fight_path, f"{line} match={mid}\n")
                else:
                    fresh_now = a.fresh_at == k and g.role == a.fresh_role
                    if a.fresh_every and k > 1 and (k - 1) % a.fresh_every == 0:
                        # an opponent switch: a new session against a freshly started game; the side
                        # restarted alternates (--fresh-role alt), so each persistent game meets fresh ones
                        role = a.fresh_role if a.fresh_role != "alt" else ("join" if ((k - 1) // a.fresh_every) % 2 else "host")
                        fresh_now = g.role == role
                    if fresh_now and g.running():
                        log(f"match {k}: restarting game {g.idx} (a new opponent's fresh game)")
                        g.stop()
                    if not g.running():
                        e = g.base_env()
                        e["T5_CTL_DIR"] = g.ctl
                        g.seq = 0
                        for p in (os.path.join(g.ctl, "cmd.json"), os.path.join(g.ctl, "state.json"), g.status_path):
                            try:
                                os.remove(p)
                            except OSError:
                                pass
                        base[g.idx] = 0
                        env2 = dict(env, T5_FIGHT=line)
                        g.send("fight", match=mid, env=env2)
                        g.start(e)
                    else:
                        if not rematch:
                            g.send("idle")
                            time.sleep(random.uniform(0.3, 1.0))   # the lobby's ready check and NAT punch
                        g.send("fight", match=mid, env=dict(env, T5_FIGHT=line), rematch=bool(rematch))
                t_cmd[g.idx] = time.time()
            prev_line = line
            session_alive = True
            log(f"match {k} ({mid}): {line}{' (rematch)' if rematch else ' (new session)'}, ports {port}/{port + 1}, "
                f"first {order[0].role}"
                + (f", the other {t_cmd[order[1].idx] - t_cmd[order[0].idx]:.2f} s later" if a.skew else ""))
            m = {"k": k, "match": mid, "line": line, "rematch": bool(rematch), "first": order[0].role}
            t_fight, results = {}, {}
            t_end = time.time() + a.match_seconds
            close = closes.get(k)
            closed = None                    # the Game whose window was closed
            t_closed = None
            st_on.set()
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
                if close and closed is None:
                    role, sec = close
                    g = games[0] if role == "host" else games[1]
                    if g.idx in t_fight and time.time() - t_fight[g.idx] >= sec:
                        st_on.clear()
                        n = close_windows(g.proc.pid)
                        closed, t_closed = g, time.time()
                        log(f"match {k}: WM_CLOSE to game {g.idx}'s window(s): {n}")
                if closed is not None:
                    other = games[1] if closed is games[0] else games[0]
                    if (not closed.running() and other.idx in results) or time.time() - t_closed > 40:
                        break
                    time.sleep(0.25)
                    continue
                if len(results) == 2 or not all(g.running() for g in games):
                    break
                time.sleep(0.25)
            st_on.clear()
            m["to_fight_s"] = {g.idx: round(t_fight[g.idx] - t_cmd[g.idx], 1) if g.idx in t_fight else None for g in games}
            m["results"] = results
            r1, r2 = results.get(1), results.get(2)
            if closed is not None:
                other = games[1] if closed is games[0] else games[0]
                rc, ro = results.get(closed.idx), results.get(other.idx)
                code = closed.proc.poll()
                m["closed"] = {"game": closed.idx, "exit_code": code,
                               "own_reason": rc and rc.get("reason"), "peer_reason": ro and ro.get("reason")}
                ok = (code == 7 and rc is not None and rc.get("reason") == "quit" and ro is not None
                      and ro.get("reason") == "peer_quit")
                log(f"match {k}: closed game {closed.idx}: exit code {code}, its result {rc}, the other's {ro}")
                if closed.running():
                    log(f"match {k}: game {closed.idx} still runs without its window -- killed")
                    closed.stop()
                session_alive = False
            else:
                ok = (r1 is not None and r2 is not None and r1.get("winner") == r2.get("winner")
                      and r1.get("winner") is not None
                      and r1.get("hash") == r2.get("hash") and not r1.get("desync") and not r2.get("desync"))
            m["ok"] = ok
            ok_all &= ok
            report["matches"].append(m)
            log(f"match {k}: {'OK' if ok else 'FAILED'} -- to FIGHT {m['to_fight_s']}, winners "
                f"{[r and r.get('winner') for r in (r1, r2)]}, desync {[r and r.get('desync') for r in (r1, r2)]}")
            if not ok or (closed is None and not all(g.running() for g in games)):
                ok_all = False
                break
            # the launcher waits for the lobby's verdict and the players' rematch clicks
            time.sleep(a.rematch_wait)
        time.sleep(2.0)
    finally:
        stop.set()
        for g in games:
            g.stop()
        fifo_total = {}
        for g in games:
            sync = []
            for fn in sorted(f for f in os.listdir(g.dir) if f.startswith("game") and f.endswith(".log")):
                with open(os.path.join(g.dir, fn), encoding="utf-8", errors="replace") as f:
                    for ln in f:
                        mm = re.search(r"sync check through frame (\d+): (\d+) mismatching", ln)
                        if mm:
                            sync.append((fn, int(mm.group(1)), int(mm.group(2))))
                fifo = scan_fifo(os.path.join(g.dir, fn))
                if fifo:
                    report.setdefault("fifo", {})[f"{g.idx}/{fn}"] = fifo
                    for kk, v in fifo.items():
                        fifo_total[kk] = fifo_total.get(kk, 0) + v
            report[f"sync{g.idx}"] = sync[-3:]
            log(f"game {g.idx}: last sync checks {sync[-3:]}")
        if fifo_total.get("fifo_stall") or fifo_total.get("drain_stalled"):
            ok_all = False
        if a.mash_start:
            for g in games:
                opens = pause_menu_opens(os.path.join(g.dir, "df_frames.log"))
                tally = [0, 0, 0]
                for fn in sorted(f for f in os.listdir(g.dir) if f.startswith("game") and f.endswith(".log")):
                    tally = [x + y for x, y in zip(tally, start_tally(os.path.join(g.dir, fn)))]
                report[f"pause{g.idx}"] = {"menu_opened": opens, "start_cut_p1": tally[0], "start_cut_p2": tally[1],
                                           "start_kept": tally[2]}
                log(f"game {g.idx}: pause menu opened {opens} time(s); START taken out on {tally[0]} (P1) + "
                    f"{tally[1]} (P2) frames, kept on {tally[2]} (post-match skip)")
                if opens:
                    ok_all = False
        log(f"FIFO: {fifo_total or 'no stall, no resync'}")
        report["ok"] = ok_all
        with open(os.path.join(a.out, "report.json"), "w") as f:
            json.dump(report, f, indent=1)
        log(f"{'ALL OK' if ok_all else 'FAILED'}: {sum(1 for m in report['matches'] if m['ok'])}/{a.matches} matches; "
            f"report {os.path.join(a.out, 'report.json')}")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
