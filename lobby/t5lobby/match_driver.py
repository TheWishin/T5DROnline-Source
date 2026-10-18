"""MatchDriver: the glue between the lobby and the game.

From "match found" to "result reported" without the player doing anything:

    match_found   a game left over from the last opponent is closed (process mode) or sent
                  back to idle (persistent mode); a rematch inside the running games keeps it
    match_start   the game gets the match: T5_NET_* (netplay), T5_FIGHT (direct-fight mode:
                  characters, stage, rounds; with T5_NET_START=external and the same
                  PS3_FIXED_TIME on both PCs, docs/DIRECTFIGHT.md), T5_HUD_* (the lobby names
                  and rank tiers the game writes into its fight HUD)
    during play   the game's log is followed: the netplay desync detector, a lost opponent,
                  "match over" lines, crashes
    lag check     when the lobby settled the match, the game log's own numbers (frames played,
                  time spent waiting for the opponent, this PC's speed) go to the lobby, which
                  tells both players "ping X should mean about Y frames behind, it was Z"
    result        the game's result file (T5_NET_RESULT_FILE) is read and reported with the
                  evidence (desync count, state hash when the game writes one); the file is
                  archived so the next match in the same game process starts clean. A file
                  naming another match ("match": id) is never reported for this one; a
                  file with a "reason" (the game lost its opponent, could not connect, ...)
                  is reported as a disconnect
    after         the game stays open at character select; a rematch with the same opponent
                  continues inside the running games: the next fight goes to T5_FIGHT_FILE
                  (no restart, no new connection)
    ranked set    between two games of a ranked set (best of 3, docs/RANKED.md "Ranked sets") the
                  next game starts by itself: the driver tells the lobby whether this game still
                  runs connected (set_next keep), and the next game continues in it like a rematch

Two ways to run the game:

* process mode (works today): one t5dr.exe per opponent. The netplay session is set up
  from the environment at boot (T5_NET_*), direct-fight boots straight into the fight
  (T5_FIGHT); rematches against the same opponent continue in that process through
  T5_FIGHT_FILE. The game's state (T5_DF_STATUS_FILE) is shown to the player.
* persistent mode (T5_CTL_DIR, for direct-fight builds): the game is started once and
  stays open between opponents; each match is a command written to <dir>/cmd.json, the
  game answers in <dir>/state.json. Protocol: docs/RANKED.md, "Game control channel";
  the game side: docs/DIRECTFIGHT.md, "Persistent game". A new opponent is a new netplay
  session in the running game (a few seconds from the command to the fight instead of
  ~20 s for a new process); a rematch is a "fight" with "rematch": true in the running
  session. Used when the game build understands it (mode="auto" looks for the T5_CTL_DIR
  string in the game binaries) or when forced (mode="persistent"). Fallback: a game that
  does not take a command in time (CTL_ACK_SECONDS) or dies twice in persistent mode is
  restarted in process mode, which then stays for the rest of the session.

The driver has no UI. A front end feeds it every LobbyClient event (on_event), calls
poll() a few times a second and shows the notes it gets back:

    {"t": "driver", "kind": "status", "text": ...}
    {"t": "driver", "kind": "ask_result", "match": id, "opponent": name}   no result: ask the player
    {"t": "driver", "kind": "rematch_offer", "match": id, "opponent": name, "timeout": s}
    {"t": "driver", "kind": "set_next", "match": id, "set": {...}}         a ranked set goes on by itself
    {"t": "driver", "kind": "game_closed"}
"""
import functools
import json
import os
import queue
import re
import threading
import time
import urllib.parse

from . import fighters, proto, ranks
from .handover import MatchTicket, read_result_file

CTL_MARKER = b"T5_CTL_DIR"

RE_SYNC = re.compile(r"\[netplay\] sync check through frame (\d+): (\d+) mismatching")
RE_DESYNC = re.compile(r"\[netplay\] DESYNC at frame (\d+)")
RE_OVER = re.compile(r"\[netplay\] frame (\d+): match (\d+) over, P1 (\d+) - P2 (\d+)")
RE_LOST = re.compile(r"\[netplay\] (no input from the peer .*peer lost|peer lost \((\w+)\))")
RE_FAIL = re.compile(r"\[netplay\] cannot connect \((\w+)\)")
RE_CONNECTED = re.compile(r"\[netplay\] connected \(")
RE_BUILD = re.compile(r"\[netplay\] (the peer runs a different build|cannot connect \(build_mismatch\))")
RE_SPEED = re.compile(r"\[netplay\] speed: [\d.]+ fps, this PC ([\d.]+) fps")
# netplay logs one such line per 600 lockstep frames: overall speed, this PC's own speed without the
# waits for the peer, and how long it waited (src/netplay/netplay_core.cpp account_frame)
RE_WAIT = re.compile(r"\[netplay\] speed: ([\d.]+) fps, this PC ([\d.]+) fps without the waits for the peer "
                     r"\(waited ([\d.]+) s of ([\d.]+) s\)")
RE_FPS = re.compile(r"^\[fps\] ([\d.]+) ")
# a persistent game starts a netplay session per opponent (src/netplay/t5_hooks.cpp)
RE_SESSION = re.compile(r"\[netplay\] session (\d+) set up")
# how long a game may take to take a control command (persistent mode): a running one, a booting one
CTL_ACK_SECONDS = 10.0
CTL_ACK_BOOT_SECONDS = 90.0

# Why a game could not finish its match (result file "reason", netplay log), for the player.
REASON_TEXT = {
    "peer_quit": "Your opponent closed the game.",
    "peer_timeout": "The connection to your opponent's game was lost.",
    "peer_stalled": "Your opponent's game stopped responding.",
    "start_timeout": "Your opponent's game did not get to the fight.",
    "peer_restarted": "Your opponent's game was restarted; the match cannot go on.",
    "peer_lost": "The connection to your opponent's game was lost.",
    "no_peer": "Your opponent's game could not be reached (firewall or router?).",
    "build_mismatch": "Your opponent's game is a different build.",
    "rejected": "Your opponent's game is in another match.",
    "bind_failed": "The game could not open its network port (another program uses it?).",
    "quit": "You closed the game during the match: it counts as a loss.",
}
# Exit codes of a game whose netplay session could not go on (src/netplay/t5_hooks.cpp).
EXIT_REASON = {3: "peer_lost", 4: "no_peer", 5: "build_mismatch"}
# The player closed the game window (Alt+F4, the X button, Esc) while a netplay session was set up:
# the game told the opponent and ended itself; for the lobby that is this player's quit (a loss).
EXIT_QUIT = 7


class GameLog:
    """Follows the game's log file and keeps what the lobby needs from the netplay lines."""

    def __init__(self, path):
        self.path = path
        self.pos = 0
        self.partial = ""
        self.mismatches = 0          # netplay's cumulative mismatch count (sync check lines)
        self.desync_lines = 0        # DESYNC lines (the first 10 mismatches are logged one by one)
        self.last_frame = 0
        self.overs = []              # (frame, n, p1 rounds, p2 rounds)
        self.peer_lost = 0
        self.session_lost = 0        # peer_lost in the current netplay session (persistent game: one per opponent)
        self.sessions = 0
        self.lost_reason = None      # "peer lost (<reason>)"
        self.fail_reason = None      # "cannot connect (<reason>)"
        self.connected = False
        self.crashed = False
        self.build_mismatch = False
        self.local_fps = None        # this PC's own speed in lockstep (netplay's speed line)
        self.speeds = []             # (fps, this PC's fps, waited s, window s) per netplay speed line
        self.fps = []                # the runtime's [fps] lines (sustained speed offline / before lockstep)

    def poll(self):
        if not self.path:
            return
        try:
            with open(self.path, "rb") as f:
                f.seek(self.pos)
                data = f.read()
                self.pos = f.tell()
        except OSError:
            return
        if not data:
            return
        text = self.partial + data.decode("utf-8", "replace")
        lines = text.split("\n")
        self.partial = lines.pop()
        for ln in lines:
            self.line(ln.rstrip("\r"))

    def line(self, ln):
        if "[CRASH]" in ln:
            self.crashed = True
        m = RE_FPS.search(ln)
        if m:
            self.fps = (self.fps + [float(m.group(1))])[-24:]
            return
        if "[netplay]" not in ln:
            return
        m = RE_SYNC.search(ln)
        if m:
            self.last_frame = max(self.last_frame, int(m.group(1)))
            self.mismatches = max(self.mismatches, int(m.group(2)))
            return
        m = RE_DESYNC.search(ln)
        if m:
            self.desync_lines += 1
            self.mismatches = max(self.mismatches, self.desync_lines)
            return
        m = RE_OVER.search(ln)
        if m:
            self.overs.append(tuple(int(x) for x in m.groups()))
            self.last_frame = max(self.last_frame, int(m.group(1)))
            return
        m = RE_SESSION.search(ln)
        if m:
            # a new opponent in a persistent game: what the last session saw no longer applies
            self.sessions = int(m.group(1))
            self.connected = False
            self.session_lost = 0
            self.build_mismatch = False
            self.fail_reason = None
            return
        m = RE_LOST.search(ln)
        if m:
            self.peer_lost += 1
            self.session_lost += 1
            self.lost_reason = m.group(2) or "peer_lost"
            return
        m = RE_WAIT.search(ln)
        if m:
            self.local_fps = float(m.group(2))
            self.speeds.append(tuple(float(x) for x in m.groups()))
            return
        m = RE_SPEED.search(ln)
        if m:
            self.local_fps = float(m.group(1))
            return
        if RE_CONNECTED.search(ln):
            self.connected = True
        if RE_BUILD.search(ln):
            self.build_mismatch = True
        m = RE_FAIL.search(ln)
        if m:
            self.fail_reason = m.group(1)

    def sustained_fps(self):
        """This PC's speed from the log: netplay's own measure in lockstep (time waiting for the
        peer left out), else the median of the runtime's [fps] lines."""
        if self.local_fps:
            return self.local_fps
        if len(self.fps) >= 3:
            return sorted(self.fps)[len(self.fps) // 2]
        return None

    def mark(self):
        """Counters at the start of a match: (mismatches, overs, peer_lost, speed lines)."""
        self.poll()
        return (self.mismatches, len(self.overs), self.peer_lost, len(self.speeds))

    def lag_stats(self, since=0):
        """The numbers behind the post-game lag check, from the speed lines after `since`:
        {frames, waited_ms, pc_fps, fps} -- or None when there are too few (a match shorter than
        one 600-frame line says nothing)."""
        rows = self.speeds[since:]
        frames = sum(round(fps * window) for fps, _pc, _w, window in rows)
        if not rows or frames < 300:
            return None
        pcs = sorted(pc for _f, pc, _w, _t in rows)
        return {"frames": frames, "waited_ms": sum(w for _f, _p, w, _t in rows) * 1000.0,
                "pc_fps": round(pcs[len(pcs) // 2], 1),
                "fps": round(frames / sum(t for _f, _p, _w, t in rows), 1)}


def replace_retry(src, dst, tries=50, wait=0.01):
    """os.replace that retries for a moment: on Windows the replace fails while another process has
    the target open without delete sharing (an older game reading cmd.json at that moment -- the
    command would be lost, and with it a rematch). The game opens it with delete sharing since
    rematch-fix; older builds and other readers still get this."""
    for i in range(tries):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if i == tries - 1:
                raise
            time.sleep(wait)


class Control:
    """The game control channel (persistent mode): cmd.json written here, state.json read."""

    def __init__(self, directory):
        self.dir = directory
        os.makedirs(directory, exist_ok=True)
        self.seq = 0
        for name in ("cmd.json", "state.json"):
            try:
                os.remove(os.path.join(directory, name))
            except OSError:
                pass

    def send(self, cmd, **fields):
        self.seq += 1
        d = dict(fields, seq=self.seq, cmd=cmd, time=time.time())
        path = os.path.join(self.dir, "cmd.json")
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f)
        replace_retry(tmp, path)
        return self.seq

    def state(self):
        try:
            with open(os.path.join(self.dir, "state.json"), encoding="utf-8") as f:
                d = json.load(f)
            return d if isinstance(d, dict) else None
        except (OSError, ValueError):
            return None


_ctl_cache = {}


def game_supports_control(paths):
    """Does this game build understand T5_CTL_DIR? (looks for the variable's name in the binaries)"""
    key = []
    for p in paths:
        try:
            st = os.stat(p)
            key.append((p, st.st_mtime, st.st_size))
        except OSError:
            pass
    key = tuple(key)
    if key not in _ctl_cache:
        _ctl_cache[key] = _scan_for_control(paths)
    return _ctl_cache[key]


def _scan_for_control(paths):
    for p in paths:
        try:
            with open(p, "rb") as f:
                while True:
                    chunk = f.read(1 << 22)
                    if not chunk:
                        break
                    if CTL_MARKER in chunk:
                        return True
                    f.seek(-len(CTL_MARKER), os.SEEK_CUR)
                    if len(chunk) < (1 << 22):
                        break
        except OSError:
            continue
    return False


class MatchDriver:
    def __init__(self, client, launch, workdir, table=None, mode="auto", game_files=(), extra_env=None,
                 ask_manual=True, auto_rematch=0, fight_env=True, async_calls=False, input_delay=None):
        """client: LobbyClient. launch(env) -> game handle (.running(), .stop(), .proc, .log_path) or
        None. workdir: where result files and the control channel live. mode: auto | process |
        persistent. game_files: binaries to check for the control channel (mode auto).
        ask_manual: when the game closes without a result, ask the player (else report a quit).
        auto_rematch: accept this many rematches by itself (scripted runs). async_calls: lobby
        requests on a worker thread (a UI must not wait for the network). input_delay: this
        player's rollback input delay setting ("auto", "0", "1", "2"; a ranked match's fixed value
        wins), passed to every match as T5_RB_NET_DELAY."""
        self.client = client
        self.launch = launch
        self.workdir = os.path.abspath(workdir)
        os.makedirs(self.workdir, exist_ok=True)
        self.table = table or fighters.table()
        if mode == "auto":
            mode = "persistent" if game_supports_control(game_files) else "process"
        self.mode = mode
        self.extra_env = dict(extra_env or {})
        self.input_delay = str(input_delay) if input_delay not in (None, "") else None
        self.ask_manual = ask_manual
        self.auto_rematch = auto_rematch
        self.fight_env = fight_env
        self.async_calls = async_calls
        self.notes = queue.Queue()

        self.game = None             # game handle
        self.glog = None             # GameLog of that game
        self.ctl = None              # Control (persistent mode)
        self.session = None          # id of the first match this game process played
        self.result_path = None
        self.fight_path = None       # T5_FIGHT_FILE of the running game (next fight in the same process)
        self.status_path = None      # T5_DF_STATUS_FILE of the running game
        self.game_state = None       # last "state" from it
        self.df_status = None        # the whole last status
        self.saw_fight = False       # this match's fight was seen in the status file
        self.t_over = None           # when the status said the fight is over (no result file yet)
        self.df_base = 0             # the status' match number before this match (its fight has a higher one)
        self.ticket = None           # MatchTicket of the match being played
        self.session_ticket = None   # MatchTicket that set up the current game connection
        self.match_ev = None         # its match_start event
        self.mark = None             # GameLog.mark() at its start
        self.reported = False
        self.t_reported = 0.0
        self.last = None             # last finished match (match_result event)
        self.history = []            # (match id, what was reported) -- for tools and tests
        self.rematch_sent = set()    # finished matches this side already answered a rematch for
        self.last_fps = None         # this PC's sustained speed in its last match (reported to the lobby)
        self.ctl_wait = None         # (seq, sent at, booting) of a control command the game has not taken yet
        self.ctl_failures = 0        # persistent games that died or did not answer
        self.need_session = None     # persistent game, a new session: its netplay session number (lines before it
                                     # in the log -- the last session's "peer lost" -- are not this match's)

    # ------------------------------------------------------------------ helpers
    def note(self, kind, **kw):
        self.notes.put(dict(kw, t="driver", kind=kind))

    def status(self, text):
        self.note("status", text=proto.scrub_addresses(str(text)))      # never an IP address in what the player reads

    def game_running(self):
        return self.game is not None and self.game.running()

    def connected_game(self):
        """The game runs and its netplay session is alive (a rematch can continue in it)."""
        if not self.game_running() or self.glog is None:
            return False
        self.glog.poll()
        return self.glog.connected and self.glog.session_lost == 0 and not self.glog.build_mismatch

    def stop_game(self):
        if self.game is not None:
            try:
                if self.ctl is not None and self.game.running():
                    self.ctl.send("quit")
                    t_end = time.monotonic() + 3.0
                    while self.game.running() and time.monotonic() < t_end:
                        time.sleep(0.1)
                if self.game.running():
                    self.game.stop()
            finally:
                self.game = None
                self.glog = None
                self.ctl = None
                self.session = None

    # ------------------------------------------------------------------ environment
    def match_env(self, ev, ticket):
        env = ticket.game_env(result_file=self.result_path)
        line = self.fight_line(ev)
        if line:
            # Direct fight: both PCs boot into the same fight; lockstep starts there (netplay is told
            # by the direct-fight code), with the same frozen clock on both (docs/DIRECTFIGHT.md).
            env["T5_FIGHT"] = line
            env["T5_NET_START"] = "external"
            if ev.get("start_time"):
                env["PS3_FIXED_TIME"] = str(int(ev["start_time"]))
        if self.fight_path:
            env["T5_FIGHT_FILE"] = self.fight_path
            env["T5_DF_STATUS_FILE"] = self.status_path
        hud = hud_values(ev)
        if hud:
            # In-game identity (docs/DIRECTFIGHT.md): the lobby's names and rank tiers in the fight HUD.
            env["T5_HUD_NAMES"] = "|".join(hud[0])
            env["T5_HUD_RANKS"] = ",".join(str(t) for t in hud[1])
        env.update(self.extra_env)
        # Rollback input delay (docs/NETPLAY.md "Input delay"): a ranked match's fixed value wins
        # over everything; otherwise this player's setting, in every session's environment (a
        # persistent game reads a key a session once set as unset when a later one leaves it out).
        if getattr(ticket, "input_delay", None) is not None:
            env["T5_RB_NET_DELAY"] = str(int(ticket.input_delay))
        elif self.input_delay:
            env["T5_RB_NET_DELAY"] = str(self.input_delay)
        return env

    def fight_line(self, ev):
        """T5_FIGHT value for a match_start event, or None (no direct fight)."""
        fight = ev.get("fight") or {}
        if not (self.fight_env and self.table.fighter(fight.get("p1")) and self.table.fighter(fight.get("p2"))
                and self.table.stage(fight.get("stage"))):
            return None
        return self.table.fight_env(fight["p1"], fight["p2"], fight["stage"], fight.get("rounds", 3))

    def _write_fight_file(self, line, mid=None, ev=None):
        # match=<id>: the game puts it into this match's result file (older builds ignore it);
        # names= / ranks=: the HUD identity again (a rank may have moved after a ranked match)
        hud = hud_values(ev)
        if hud:
            line += " names=" + "|".join(urllib.parse.quote(n, safe="") for n in hud[0])
            line += " ranks=" + "|".join(str(t) for t in hud[1])
        tmp = self.fight_path + ".tmp"
        with open(tmp, "w", encoding="ascii") as f:
            f.write(line + (f" match={mid}" if mid else "") + "\n")
        replace_retry(tmp, self.fight_path)

    def _discard_result(self, why):
        """A result file that must not be reported (left from a voided match, or naming another
        match): moved aside to results/<why>-<time>.json."""
        if not self.result_path or not os.path.exists(self.result_path):
            return
        d = os.path.join(self.workdir, "results")
        os.makedirs(d, exist_ok=True)
        try:
            os.replace(self.result_path, os.path.join(d, f"{why}-{time.time_ns()}.json"))
        except OSError:
            try:
                os.remove(self.result_path)
            except OSError:
                pass

    # ------------------------------------------------------------------ lobby events
    def on_event(self, ev):
        t = ev.get("t")
        if t == "match_found":
            if not ev.get("keep"):
                self._release_game()
        elif t == "match_start":
            if ev.get("ticket") is not None or ev.get("continue"):
                self._start(ev)
        elif t == "match_result":
            self._finished(ev)
        elif t == "rematch":
            if ev.get("state") == "offered":
                self.note("rematch_offer", match=ev["match"], opponent=ev.get("from", {}).get("name", "?"),
                          timeout=ev.get("timeout", 20))
                if self.auto_rematch > 0:
                    self.rematch(ev["match"], True)
            elif ev.get("state") == "declined":
                self.status("Your opponent does not want a rematch.")
        elif t == "disconnected":
            self.ticket = None

    def _release_game(self):
        """A new opponent: the old game session cannot be reused in process mode."""
        if self.game is None:
            return
        if self.mode == "persistent" and self.game_running():
            self.ctl.send("idle")
            return
        self.stop_game()

    def _start(self, ev):
        t = ev.get("ticket")
        mid = ev["match"]
        if ev.get("continue"):
            # Rematch inside the running games: same process, same connection.
            if not self.game_running():
                self.status("The game is not running any more; leaving the rematch.")
                self._call(self.client.leave_match, mid)
                return
            self.ticket = _Continued(mid, ev, self.session_ticket)
            self.need_session = None
            self.match_ev = ev
            self._discard_result("stale")    # nothing the game wrote before this match belongs to it
            self.mark = self.glog.mark()
            self.reported = False
            self.saw_fight = False
            self.t_over = None
            self.df_base = int((self.df_status or {}).get("match") or 0)
            if self.mode == "persistent" and self.ctl is not None:
                self._send_fight(mid, self.match_env(ev, self.ticket), rematch=True)
            else:
                line = self.fight_line(ev)
                if line and self.fight_path:
                    self._write_fight_file(line, mid, ev)   # the game picks it up at character select
            self.status(f"Rematch against {ev['opponent']['name']}: same connection, the game stays open.")
            self._call(self.client.game_started, mid)
            return
        self.ticket = t
        self.session_ticket = t
        self.match_ev = ev
        self.reported = False
        self.saw_fight = False
        self.t_over = None
        self.df_base = int((self.df_status or {}).get("match") or 0) if self.game_running() else 0
        self.need_session = None
        if self.mode == "persistent" and self.game_running() and self.ctl is not None:
            # a new opponent in the running game: a new netplay session (docs/DIRECTFIGHT.md). The last session may
            # still log its end ("peer lost (peer_quit)" when the other game went idle first): that is not this match.
            if self.glog is not None:
                self.glog.poll()
                self.need_session = self.glog.sessions + 1
            self._send_fight(mid, self.match_env(ev, t))
        else:
            self.stop_game()
            self.session = mid
            self.df_status, self.df_base = None, 0           # a new game counts its fights from 1
            self.result_path = os.path.join(self.workdir, f"result-{mid}.json")
            self.fight_path = os.path.join(self.workdir, f"fight-{mid}.txt")
            self.status_path = os.path.join(self.workdir, f"status-{mid}.json")
            self.game_state = None
            for p in (self.result_path, self.result_path + ".tmp", self.fight_path, self.fight_path + ".done",
                      self.status_path):
                try:
                    os.remove(p)
                except OSError:
                    pass
            env = self.match_env(ev, t)
            if self.mode == "persistent":
                self.ctl = Control(os.path.join(self.workdir, "ctl"))
                launch_env = {"T5_CTL_DIR": self.ctl.dir}
                launch_env.update({k: v for k, v in env.items() if k.startswith("T5_HUD")})
                launch_env.update(self.extra_env)
                self._send_fight(mid, env, booting=True)
                env = launch_env
            game = self.launch(env)
            if game is None:
                self.status("The game could not start; leaving the match.")
                self._call(self.client.leave_match, mid)
                self.ticket = None
                return
            if getattr(t, "_dup_socket", None) is not None and getattr(game, "proc", None) is not None:
                t.share_socket(game.proc.pid)
            self.game = game
            self.glog = GameLog(getattr(game, "log_path", None))
        self.mark = self.glog.mark() if self.glog else (0, 0, 0, 0)
        self.status(f"Playing against {t.summary()}")
        self._call(self.client.game_started, mid)

    def _send_fight(self, mid, env, rematch=False, booting=False):
        seq = self.ctl.send("fight", match=mid, env=env, rematch=rematch)
        self.ctl_wait = (seq, time.monotonic(), booting)

    def _watch_ctl(self):
        """Persistent mode: the game must take each command. One that does not (or a game that died
        twice) sends this player back to one game process per opponent, starting with this match."""
        if self.mode != "persistent":
            return
        w = self.ctl_wait
        if w is not None and self.ctl is not None and self.game_running():
            st = self.ctl.state() or {}
            try:
                taken = int(st.get("seq") or 0) >= w[0]
            except (TypeError, ValueError):
                taken = False
            if taken:
                self.ctl_wait = None
                return
            if time.monotonic() - w[1] < (CTL_ACK_BOOT_SECONDS if w[2] else CTL_ACK_SECONDS):
                return
            self.ctl_wait = None
            self.ctl_failures = 2
        elif w is not None and self.game is not None and not self.game_running():
            self.ctl_wait = None
            if getattr(getattr(self.game, "proc", None), "returncode", None) == EXIT_QUIT:
                return       # the player closed it: not a control channel failure, and nothing is restarted
            self.ctl_failures += 1
        if self.ctl_failures < 2:
            return
        self.mode = "process"
        self.status("The game did not answer its control channel; it is restarted for every opponent from now on.")
        ev, t = self.match_ev, self.ticket
        self.stop_game()
        if ev is not None and isinstance(t, MatchTicket) and not self.reported:
            self._start(dict(ev, ticket=t))

    def _send_lag(self, mid):
        """Report this match's lag numbers (the lobby shows both players the comparison)."""
        fn = getattr(self.client, "report_lag", None)
        if fn is None or self.glog is None or self.mark is None:
            return
        self.glog.poll()
        st = self.glog.lag_stats(self.mark[3] if len(self.mark) > 3 else 0)
        if st:
            self._call(fn, mid, st["frames"], st["waited_ms"], st["pc_fps"], st["fps"])

    def _finished(self, ev):
        self.last = ev
        if self.ticket is not None and getattr(self.ticket, "match_id", None) == ev["match"]:
            self._send_lag(ev["match"])
            if not self.reported:
                # The lobby settled the match without our report (e.g. void on the opponent's
                # desync report): whatever our game writes for it now must not count for the next.
                self._discard_result("unreported")
            self.ticket = None
        s = ev.get("set") or {}
        if s.get("rated") and s.get("next"):
            # A ranked set goes on by itself (no vote): say whether this game can play the next one as it runs.
            fn = getattr(self.client, "set_next", None)
            if fn is not None:
                self._call(fn, ev["match"], self.connected_game())
            self.note("set_next", match=ev["match"], set=s)
        elif ev.get("rematch_window") and self.auto_rematch > 0:
            self.rematch(ev["match"], True)

    def rematch(self, match_id=None, accept=True):
        """Offer / accept (or decline) a rematch against the last opponent."""
        mid = match_id or (self.last or {}).get("match")
        if not mid or mid in self.rematch_sent:
            return
        self.rematch_sent.add(mid)
        keep = accept and self.connected_game()
        if accept and self.auto_rematch > 0:
            self.auto_rematch -= 1
        self._call(self.client.rematch, mid, accept, keep)
        if not accept and self.mode == "process":
            self.stop_game()

    def _call(self, fn, *args):
        if self.async_calls:
            # The thread gets the queue and the call, not the driver: a UI's objects must never be
            # released from a worker thread (Tk aborts the process when that happens).
            threading.Thread(target=_call_now, args=(self.notes, fn) + args, daemon=True).start()
            return None
        return _call_now(self.notes, fn, *args)

    # ------------------------------------------------------------------ polling
    def poll(self):
        """Call a few times a second. Returns the notes for the UI (list of dicts)."""
        self._watch_ctl()
        self._watch_state()
        t = self.ticket
        if t is not None and not self.reported:
            self._check(t)
        out = []
        try:
            while True:
                out.append(self.notes.get_nowait())
        except queue.Empty:
            pass
        return out

    STATE_TEXT = {"title": "The game is starting...", "select": "Character select...",
                  "stage": "Stage select...", "loading": "Loading the fight...", "fight": "Fight!",
                  "over": "Match over.", "neutral": "At character select, waiting for the next match."}

    def _watch_state(self):
        """The direct-fight status file: where the game is (shown to the player)."""
        if not self.status_path or not self.game_running():
            return
        try:
            with open(self.status_path, encoding="utf-8") as f:
                st = json.load(f)
        except (OSError, ValueError):
            return
        state = st.get("state") if isinstance(st, dict) else None
        self.df_status = st
        try:
            k = int(st.get("match") or 0)
        except (TypeError, ValueError):
            k = 0
        # Only this match's fight counts (the status may still show the previous one for a moment).
        if state == "fight" and self.ticket is not None and k > self.df_base and not self.saw_fight:
            self.saw_fight = True
            # FIGHT START is a netplay sync point (frame counters, input ring, random seeds): only
            # mismatches from here on belong to this match, not menu ones from before it.
            if self.glog is not None:
                self.mark = self.glog.mark()
        if state in ("over", "neutral") and self.saw_fight and k > self.df_base and self.t_over is None:
            self.t_over = time.monotonic()
        if state and state != self.game_state:
            self.game_state = state
            self.note("game_state", state=state, match=st.get("match"))
            if state in self.STATE_TEXT and self.ticket is not None:
                self.status(self.STATE_TEXT[state])

    def _evidence(self):
        """Desync count since the match started, from the game log."""
        if self.glog is None or self.mark is None:
            return None
        self.glog.poll()
        return max(0, self.glog.mismatches - self.mark[0])

    def _check(self, t):
        mid = t.match_id
        if self.glog is not None:
            self.glog.poll()
        res = read_result_file(self.result_path) if self.result_path else None
        if res is not None:
            extra = _result_extra(self.result_path)
            if extra.get("match") and str(extra["match"]) != str(mid):
                # Left over from another match (a voided one, or an old game): never this one's.
                self._discard_result("stale")
                self.status("Ignored a result the game wrote for an earlier match.")
                return
            self._archive(mid)
            self._perf(extra.get("fps"))
            desync = self._evidence() or 0
            desync = max(desync, int(extra.get("desync") or 0))
            reason = extra.get("reason")
            if reason == "quit":
                # This player closed the game window mid-match (exit code 7): a quit, i.e. a loss.
                self._report(mid, None, res[1], "quit", desync=desync, reason="quit")
                self.status(REASON_TEXT["quit"])
                return
            if reason:
                # The game could not play the match to its end (lost its opponent, no connection).
                self._report(mid, None, res[1], "disconnect", desync=desync, reason=str(reason)[:32])
                self.status(REASON_TEXT.get(reason, f"The match could not be finished ({reason})."))
                return
            self._report(mid, res[0], res[1], "game", desync=desync, hash=extra.get("hash"),
                         frames=extra.get("frames"))
            return
        if self.t_over is not None and time.monotonic() - self.t_over > 5.0 and self.df_status:
            # The direct-fight code saw the fight end but no result file came (netplay writes none
            # for a 0-0 end, e.g. a fight left without a winner): report what the status says.
            st = self.df_status
            score = st.get("last_score") if isinstance(st.get("last_score"), list) else None
            winner = st.get("last_winner") if st.get("last_winner") in (0, 1) else None
            self._report(mid, winner, score, "game", desync=self._evidence() or 0,
                         reason=None if winner is not None else "no_result")
            return
        running = self.game_running()
        g = self.glog
        if g is not None and self.mark is not None:
            overs = g.overs[self.mark[1]:]
            if overs and not running:
                # No result file, but the log saw the match end (older netplay builds).
                _f, _n, w1, w2 = overs[-1]
                winner = 0 if w1 > w2 else 1 if w2 > w1 else None
                self._report(mid, winner, [w1, w2], "game", desync=self._evidence() or 0)
                return
            lost = g.peer_lost > self.mark[2] and (self.need_session is None or (
                g.sessions >= self.need_session and g.session_lost > 0))
            if lost and (not running or self._grace("lost")):
                # (a game that ends the match itself writes a result file with the reason first;
                # give it a moment before reporting from the log)
                reason = g.lost_reason or "peer_lost"
                self._report(mid, None, None, "disconnect", desync=self._evidence() or 0, reason=reason)
                self.status(REASON_TEXT.get(reason, REASON_TEXT["peer_lost"]))
                return
        if running:
            return
        code = getattr(getattr(self.game, "proc", None), "returncode", None)
        if code == EXIT_QUIT:
            # The player closed the game (no result file: the window closed before the game had a
            # match id, or the file could not be written): the same quit.
            self.note("game_closed", code=code, crashed=False)
            self._report(mid, None, None, "quit", desync=self._evidence() or 0, reason="quit")
            self.status(REASON_TEXT["quit"])
            return
        if code in EXIT_REASON:
            # The netplay session could not go on and the game closed itself (no result file?).
            reason = (g.fail_reason or g.lost_reason) if g is not None else None
            reason = reason or EXIT_REASON[code]
            self.note("game_closed", code=code, crashed=False)
            self._report(mid, None, None, "disconnect", desync=self._evidence() or 0, reason=reason)
            self.status(REASON_TEXT.get(reason, f"The match could not be played ({reason})."))
            return
        crashed = (g is not None and g.crashed) or (code not in (0, None))
        self.note("game_closed", code=code, crashed=crashed)
        if crashed:
            self._report(mid, None, None, "crash", reason=f"exit {code}")
            self.status("The game stopped unexpectedly; the match does not count (repeated crashes do).")
        elif self.ask_manual:
            self.reported = True     # wait for the player's answer (answer())
            self.note("ask_result", match=mid, opponent=t.opponent.get("name", "?"), slot=t.slot)
        else:
            self.answer("quit")

    def answer(self, what):
        """The player's answer when the game closed without a result: won | lost | draw | quit."""
        t = self.ticket
        if t is None:
            return
        mid = t.match_id
        if what == "quit":
            self.reported = True
            self.history.append((mid, {"source": "quit"}))
            self._call(self.client.leave_match, mid)
            return
        winner = {"won": t.slot, "lost": 1 - t.slot, "draw": None}[what]
        self._report(mid, winner, None, "manual")

    def _grace(self, key, seconds=3.0):
        """True once `seconds` have passed since this was first asked for `key` in this match."""
        t = getattr(self, "_grace_t", None)
        if t is None or t[0] != (self.ticket and self.ticket.match_id, key):
            self._grace_t = ((self.ticket and self.ticket.match_id, key), time.monotonic())
            return False
        return time.monotonic() - t[1] >= seconds

    def _perf(self, fps=None):
        """This PC's sustained speed after a match: from the result file, else from the log. The
        lobby uses it to warn about (or keep out of ranked) a PC too slow for lockstep."""
        try:
            fps = float(fps) if fps is not None else None
        except (TypeError, ValueError):
            fps = None
        if fps is None and self.glog is not None:
            fps = self.glog.sustained_fps()
        if not fps or fps <= 0:
            return
        self.last_fps = round(fps, 1)
        fn = getattr(self.client, "report_perf", None)
        if fn is not None:
            self._call(fn, self.last_fps)

    def _report(self, mid, winner, score, source, **ev):
        self.reported = True
        self.t_reported = time.monotonic()
        ev = {k: v for k, v in ev.items() if v is not None}
        self.history.append((mid, dict(ev, winner=winner, score=score, source=source)))
        self._call(functools.partial(self.client.report_result, winner, score, mid, source=source, **ev))
        if source == "game":
            self.status("Result sent" + (f" (the games went out of sync on {ev['desync']} frames)"
                                         if ev.get("desync") else "") + "; waiting for the lobby...")

    def _archive(self, mid):
        d = os.path.join(self.workdir, "results")
        os.makedirs(d, exist_ok=True)
        try:
            os.replace(self.result_path, os.path.join(d, f"{mid}.json"))
        except OSError:
            pass

    def close(self):
        self.stop_game()


def _call_now(notes, fn, *args):
    try:
        return fn(*args)
    except Exception as e:   # noqa: BLE001 -- reported, never raised into the UI loop
        notes.put({"t": "driver", "kind": "status",
                   "text": proto.scrub_addresses(f"Lobby: {getattr(e, 'msg', '') or e}")})
        return None


class _Continued:
    """Ticket stand-in for a rematch inside the running games (the connection is the old one)."""

    def __init__(self, mid, ev, prev):
        self.match_id = mid
        self.slot = ev.get("slot", getattr(prev, "slot", 0))
        self.role = ev.get("role", getattr(prev, "role", "host"))
        self.opponent = ev.get("opponent", {})
        self.ranked = ev.get("ranked", False)
        self.delay = ev.get("delay", getattr(prev, "delay", 3))
        self.rtt_ms = ev.get("rtt_ms", 0.0)
        self.path = ev.get("path", getattr(prev, "path", ""))
        self._prev = prev

    def game_env(self, result_file=None):
        env = self._prev.game_env(result_file) if self._prev is not None else {}
        env["T5_NET_MATCH"] = self.match_id
        return env

    def summary(self):
        return f"{self.opponent.get('name', '?')} -- rematch, input delay {self.delay}"


def fps_from_logs(log_dir):
    """This PC's sustained speed from the newest game log in `log_dir` (the launcher's
    logs/game-*.log): the median of the runtime's [fps] lines, the first two (boot) left out.
    None when there is no usable log. Used before the first online match."""
    import glob
    for path in sorted(glob.glob(os.path.join(log_dir, "game-*.log")), reverse=True)[:3]:
        vals = []
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                for ln in f:
                    m = RE_FPS.search(ln)
                    if m:
                        vals.append(float(m.group(1)))
        except OSError:
            continue
        vals = vals[2:]
        if len(vals) >= 4:
            return round(sorted(vals)[len(vals) // 2], 1)
    return None


def hud_values(ev):
    """([P1 name, P2 name], [P1 tier, P2 tier]) for the fight HUD from match_start's players (P1
    first, the same list on both PCs), or None. Guests and unplaced players get the Beginner badge.
    In a ranked set from its second game on, each name ends with that player's games won ("Alice [1]";
    match_start's `set.wins`, the same on both PCs)."""
    players = (ev or {}).get("players") or []
    if len(players) != 2:
        return None
    names = [str(p.get("name", ""))[:16] for p in players]
    s = (ev or {}).get("set") or {}
    wins = s.get("wins")
    if s.get("rated") and int(s.get("number") or 1) > 1 and isinstance(wins, list) and len(wins) == 2:
        # a ranked set from game 2 on: the games won so far after each name ("Alice [1]"), 16 characters at most
        names = [f"{n[:12]} [{int(w)}]" for n, w in zip(names, wins)]
    tiers = []
    for p in players:
        t = p.get("tier")
        tiers.append(t if isinstance(t, int) and 0 <= t < len(ranks.RANKS) else ranks.BEGINNER)
    return names, tiers


def _result_extra(path):
    """Optional fields of the result file beyond winner/score (match, desync, hash, frames, fps,
    reason)."""
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return {k: d[k] for k in ("match", "desync", "hash", "frames", "fps", "reason")
                if k in d and d[k] is not None}
    except (OSError, ValueError, TypeError):
        return {}
