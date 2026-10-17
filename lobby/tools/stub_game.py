#!/usr/bin/env python3
"""Stand-in for t5dr.exe: reads the same environment the lobby hands the game, does the
netplay layer's handshake on it, "plays" a match and writes what the real game writes.

    T5_NET_MODE=host|join  T5_NET_PORT=<local port>  T5_NET_PEER=<ip:port>  T5_NET_DELAY=<frames>
    T5_NET_RESULT_FILE     {"winner": 0|1|null, "score": [p1, p2]} at the end of each match
    T5_NET_SEED            shared by both sides: picks the winner the same way on both

Like src/netplay: both bind T5_NET_PORT; the joiner sends HELLO to T5_NET_PEER every
100 ms (the host also calls T5_NET_PEER when given one); the host answers whoever said
hello; the joiner adopts the host's delay. Then both exchange input packets at 60 Hz and
log netplay-style lines ("[netplay] connected", "sync check through frame N: M
mismatching frame(s)", "DESYNC at frame", "frame N: match K over, P1 a - P2 b", "no
input from the peer ... peer lost").

Knobs for tests (all optional):

    T5_STUB_SECONDS   length of one match (default 1)
    T5_STUB_MATCHES   matches in this process (default 1; the real game goes back to
                      character select after a match and can play the next one)
    T5_STUB_GAP       seconds between matches (default 2)
    T5_STUB_WINNER    0 | 1 | draw (default: from T5_NET_SEED)
    T5_STUB_DESYNC    1: this side's state hash differs from frame 30 on (both sides log it)
    T5_STUB_NORESULT  1: the match ends without a result file (status says 0-0, no winner)
    T5_STUB_FAIL      crash | quit | vanish   (crash: exit 3 with a [CRASH] line mid-match;
                      quit: exit 0 mid-match, like closing the window; vanish: stop sending
                      mid-match without exiting, the opponent's game loses the peer)
    T5_STUB_LINGER    seconds to stay open after the last match (default 0)
    T5_FIGHT_FILE     like direct-fight: before the 2nd, 3rd ... match wait for this file
                      (the next fight), then rename it to .done
    T5_DF_STATUS_FILE like direct-fight: {"state": fight|over|neutral, "match": n}
    T5_CTL_DIR        persistent mode (docs/RANKED.md, "Game control channel"): boot to
                      idle, then run every "fight" command from <dir>/cmd.json with its env;
                      "idle" ends the session, "quit" exits

Exit code 0 = every match connected and finished.
"""
import json
import os
import socket
import struct
import sys
import time
import zlib

MAGIC = b"T5NP"
HELLO, INPUT = 1, 2
LOBBY = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def log(msg):
    print(f"[netplay] {msg}", flush=True)


class Session:
    """One netplay session (one opponent) from an environment dict."""

    def __init__(self, env):
        self.env = env
        self.mode = env.get("T5_NET_MODE", "")
        self.port = int(env.get("T5_NET_PORT", "0") or 0)
        self.delay = int(env.get("T5_NET_DELAY", "3") or 3)
        self.timeout = float(env.get("T5_NET_TIMEOUT", "20") or 20)
        self.seed = int(env.get("T5_NET_SEED", "0") or 0)
        self.peer = None
        peer = env.get("T5_NET_PEER", "")
        if peer:
            h, p = peer.rsplit(":", 1)
            self.peer = (h, int(p))
        self.sock = None
        self.frame = 0
        self.mismatches = 0
        self.desync = env.get("T5_STUB_DESYNC") == "1"
        self.vanished = False

    def open(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.bind(("0.0.0.0", self.port))
        if os.name == "nt":
            sys.path.insert(0, LOBBY)
            from t5lobby.proto import disable_udp_connreset
            disable_udp_connreset(s)
        s.settimeout(0.05)
        self.sock = s
        log(f"mode {self.mode}, delay {self.delay}" + (f", lobby match {self.env['T5_NET_MATCH']}"
                                                         if self.env.get("T5_NET_MATCH") else ""))
        if self.env.get("T5_FIGHT"):
            log(f"direct fight requested: T5_FIGHT={self.env['T5_FIGHT']} (stub: logged only)")
        if self.env.get("T5_HUD_NAMES"):
            log(f"HUD: {self.env['T5_HUD_NAMES']} ranks {self.env.get('T5_HUD_RANKS', '')}")

    def close(self):
        if self.sock is not None:
            self.sock.close()
            self.sock = None

    def connect(self):
        t_end = time.time() + self.timeout
        last = 0.0
        target = self.peer
        while time.time() < t_end:
            if target is not None and time.time() - last >= 0.1:
                self.sock.sendto(MAGIC + bytes([HELLO, 1, self.delay, 1 if self.mode == "join" else 0]) + b"\0" * 4,
                                 target)
                last = time.time()
            try:
                data, src = self.sock.recvfrom(2048)
            except (socket.timeout, ConnectionResetError):
                continue
            if data[:4] != MAGIC or data[4] != HELLO:
                continue
            if self.mode == "host":
                self.peer = src
                self.sock.sendto(MAGIC + bytes([HELLO, 1, self.delay, 0]) + b"\0" * 4, src)
                break
            else:
                self.delay = data[6]
                self.peer = src
                # make sure the host has heard us too (our earlier hellos may have hit a closed port)
                self.sock.sendto(MAGIC + bytes([HELLO, 1, self.delay, 1]) + b"\0" * 4, src)
                break
        else:
            log(f"no peer within {self.timeout:.0f}s")
            return False
        log(f"connected ({self.mode}, P{1 if self.mode == 'host' else 2}), delay {self.delay}")
        log(f"lockstep starts: frame 0, delay {self.delay}")
        return True

    def hash(self, f):
        h = zlib.crc32(struct.pack("!II", self.seed, f))
        return h ^ (0xDEAD if self.desync and f >= 30 else 0)

    def exchange(self, frames, fail=None, fail_at=None):
        """`frames` frames of input exchange with per-frame hashes. -> 'ok' | 'lost' | fail."""
        last_heard = time.time()
        for _ in range(frames):
            f = self.frame
            if fail_at is not None and f >= fail_at:
                if fail == "vanish":
                    self.vanished = True
                    log("stub: stopped sending (vanish)")
                    time.sleep(self.timeout + 1)
                    return "vanish"
                return fail
            self.sock.sendto(MAGIC + bytes([INPUT, 1, self.delay, 0]) + struct.pack("!II", f, self.hash(f)), self.peer)
            t_frame = time.perf_counter() + 1 / 60
            while time.perf_counter() < t_frame:
                try:
                    data, _ = self.sock.recvfrom(2048)
                except (socket.timeout, ConnectionResetError):
                    break
                if data[:4] == MAGIC and data[4] == INPUT and len(data) >= 16:
                    last_heard = time.time()
                    rf, rh = struct.unpack_from("!II", data, 8)
                    if rh != self.hash(rf):
                        self.mismatches += 1
                        if self.mismatches <= 10:
                            log(f"DESYNC at frame {rf}: local state hash {self.hash(rf):016x}, peer {rh:016x}")
                elif data[:4] == MAGIC and data[4] == HELLO and self.mode == "host":
                    self.sock.sendto(MAGIC + bytes([HELLO, 1, self.delay, 0]) + b"\0" * 4, self.peer)
            if time.time() - last_heard > min(self.timeout, 5.0):
                log(f"no input from the peer for {min(self.timeout, 5.0):.0f}s -- peer lost, continuing with "
                    f"P{2 if self.mode == 'host' else 1} idle")
                return "lost"
            self.frame += 1
            if self.frame % 60 == 0:
                log(f"sync check through frame {self.frame - 1}: {self.mismatches} mismatching frame(s)"
                    + ("" if self.mismatches else " -- in sync"))
        return "ok"

    def play(self, n, env):
        """One match: exchange for T5_STUB_SECONDS, then the result. -> 'ok' or a failure."""
        seconds = float(env.get("T5_STUB_SECONDS", "1") or 1)
        frames = max(30, int(seconds * 60))
        fail = env.get("T5_STUB_FAIL")
        r = self.exchange(frames, fail, frames // 2 if fail else None)
        if r != "ok":
            return r
        w = env.get("T5_STUB_WINNER")
        if w in ("0", "1"):
            winner = int(w)
        elif w == "draw":
            winner = None
        else:
            winner = (self.seed >> n) & 1
        score = [3, 3] if winner is None else ([3, (self.seed >> 3) % 3] if winner == 0 else [(self.seed >> 3) % 3, 3])
        log(f"frame {self.frame}: match {n} over, P1 {score[0]} - P2 {score[1]}, winner "
            f"{'none (draw)' if winner is None else 'P%d' % (winner + 1)}")
        path = env.get("T5_NET_RESULT_FILE")
        if env.get("T5_STUB_NORESULT") == "1":
            path = None                   # like a fight left without a winner: no result file
            winner, score = None, [0, 0]
        self.last = (winner, score)
        if path:
            tmp = path + ".tmp"
            with open(tmp, "w") as f:
                json.dump({"winner": winner, "score": score}, f)
            os.replace(tmp, path)
        # drain: let the opponent see our last frames
        self.exchange(20)
        return "ok"


def status(env, state, match, last=None):
    """T5_DF_STATUS_FILE, as the direct-fight code writes it."""
    path = env.get("T5_DF_STATUS_FILE")
    if path:
        with open(path + ".tmp", "w") as f:
            d = {"state": state, "match": match}
            if last is not None:
                d["last_winner"], d["last_score"] = last
            json.dump(d, f)
        os.replace(path + ".tmp", path)


def run_env(env):
    s = Session(env)
    if s.mode not in ("host", "join"):
        log("T5_NET_MODE must be host or join")
        return 2
    s.open()
    try:
        if not s.connect():
            return 1
        fight_file = env.get("T5_FIGHT_FILE")
        for n in range(1, int(env.get("T5_STUB_MATCHES", "1") or 1) + 1):
            if n > 1:
                r = s.exchange(int(float(env.get("T5_STUB_GAP", "2")) * 60))
                if r != "ok":
                    return 1
                if fight_file:
                    # Like direct-fight: wait at character select for the next fight from the file.
                    status(env, "neutral", n - 1)
                    t_end = time.time() + 120
                    while not os.path.exists(fight_file):
                        if time.time() > t_end or s.exchange(15) != "ok":
                            return 1
                    with open(fight_file) as f:
                        log(f"next fight from T5_FIGHT_FILE: {f.read().strip()}")
                    os.replace(fight_file, fight_file + ".done")
            status(env, "fight", n)
            r = s.play(n, env)
            status(env, "over", n, getattr(s, "last", None))
            if r == "crash":
                print("[CRASH] stub: simulated crash", flush=True)
                return 3
            if r in ("quit",):
                return 0
            if r != "ok":
                return 1
        linger = float(env.get("T5_STUB_LINGER", "0") or 0)
        if linger:
            s.exchange(int(linger * 60))
        return 0
    finally:
        s.close()


def persistent(ctl_dir):
    """Control channel: state.json says where the game is, cmd.json says what to do next."""
    def state(st, seq, **kw):
        path = os.path.join(ctl_dir, "state.json")
        with open(path + ".tmp", "w") as f:
            json.dump(dict(kw, state=st, seq=seq, ctl=1), f)
        os.replace(path + ".tmp", path)

    seen = 0
    state("idle", 0)
    log(f"control channel {ctl_dir}: idle")
    t_idle = time.time()
    while True:
        try:
            with open(os.path.join(ctl_dir, "cmd.json")) as f:
                cmd = json.load(f)
        except (OSError, ValueError):
            cmd = None
        if cmd is None or cmd.get("seq", 0) <= seen:
            if time.time() - t_idle > float(os.environ.get("T5_STUB_IDLE_EXIT", "600")):
                return 0
            time.sleep(0.05)
            continue
        seen = cmd["seq"]
        if cmd["cmd"] == "quit":
            state("quit", seen)
            return 0
        if cmd["cmd"] == "idle":
            state("idle", seen)
            t_idle = time.time()
            continue
        if cmd["cmd"] == "fight":
            env = dict(os.environ)
            env.update(cmd.get("env") or {})
            state("connecting", seen, match=cmd.get("match"))
            s = Session(env)
            s.open()
            try:
                if not s.connect():
                    state("error", seen, match=cmd.get("match"), error="no peer")
                    continue
                state("fight", seen, match=cmd.get("match"))
                r = s.play(1, env)
                if r == "crash":
                    print("[CRASH] stub: simulated crash", flush=True)
                    return 3
                state("result" if r == "ok" else "error", seen, match=cmd.get("match"))
            finally:
                s.close()
            t_idle = time.time()


def main():
    ctl = os.environ.get("T5_CTL_DIR")
    if ctl:
        return persistent(ctl)
    return run_env(dict(os.environ))


if __name__ == "__main__":
    sys.exit(main())
