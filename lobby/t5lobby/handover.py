"""Where the lobby ends and the game begins.

When both players are connected the client library emits a MatchTicket. Its
game_env() is the environment for t5dr.exe; the netplay layer (src/netplay,
branch `netplay`) reads it. Read by netplay today:

    T5_NET_MODE     host | join         host = P1 (slot 0), join = P2 (slot 1)
    T5_NET_PORT     local UDP port      the port the lobby punched through; bind exactly this one
                                        (relay bridge: a free local port, the punched one stays in the launcher)
    T5_NET_PEER     ip:port             the opponent (direct), the lobby server's relay port, or
                                        127.0.0.1:<port> of the launcher's relay bridge (nat.RelayBridge)
    T5_NET_DELAY    frames              suggested input delay from the measured RTT (host's value wins)
    T5_RB_NET_DELAY auto | 0 | 1 | 2    rollback input delay: a ranked match's fixed value (the server's
                                        T5L_RANKED_INPUT_DELAY); otherwise the player's setting (launcher)
    T5_NET_TIMEOUT  seconds             give up when the peer is silent this long

Passed for the game side to pick up (not read yet; see docs/ONLINE.md):

    T5_NET_MATCH        match id (log it; it ties game logs to the lobby's match record)
    T5_NET_ROUNDS       rounds to win (3)
    T5_NET_PATH         direct | lan | relay
    T5_NET_RTT_MS       measured round trip
    T5_NET_SEED         32-bit value both sides share (the netplay may use it as match seed)
    T5_NET_BUILD        build id both players share (could go into the netplay HELLO to refuse a
                        mismatched peer on direct-IP connections that bypass the lobby)
    T5_NET_KEY          the match's secret (from the server, never sent over UDP): netplay
                        authenticates every packet with it, so only the opponent's game can
                        take part (and follow it to a new address after NAT rebinding)
    T5_NET_RESULT_FILE  where the game writes {"winner": 0|1|null, "score": [p1, p2]} at the end
    T5_NET_SOCKET_FILE  (handover="share" only) file that receives the duplicated socket, see below

Socket handover (optional): instead of closing its socket and letting the game
bind the same port, the launcher can give the game the socket itself
(WSADuplicateSocket via Python's socket.share). That closes the gap in which a
NAT could drop the mapping and the race for the port. The game must then read
T5_NET_SOCKET_FILE: it waits for the file, reads the hex WSAPROTOCOL_INFOW blob
and calls WSASocketW(FROM_PROTOCOL_INFO, ..., &info, 0, 0).
"""
import json
import os
from dataclasses import dataclass, field

from .i18n import N_, t


@dataclass
class MatchTicket:
    match_id: str
    role: str                 # host | join
    slot: int                 # 0 = P1, 1 = P2
    local_port: int
    peer: tuple               # (ip, port) the game sends to
    path: str                 # direct | lan | relay
    rtt_ms: float
    jitter_ms: float
    delay: int
    rounds: int = 3
    ranked: bool = False
    opponent: dict = field(default_factory=dict)
    build: str = ""
    seed: int = 0
    result_file: str = ""
    timeout: int = 20
    key: str = field(default="", repr=False)
    input_delay: object = None   # ranked: the server's fixed rollback input delay (frames); None = the player's setting
    _dup_socket: object = field(default=None, repr=False)

    def game_env(self, result_file=None):
        env = {
            "T5_NET_MODE": "host" if self.role == "host" else "join",
            "T5_NET_PORT": str(self.local_port),
            "T5_NET_PEER": f"{self.peer[0]}:{self.peer[1]}",
            "T5_NET_DELAY": str(self.delay),
            "T5_NET_TIMEOUT": str(self.timeout),
            "T5_NET_MATCH": self.match_id,
            "T5_NET_ROUNDS": str(self.rounds),
            "T5_NET_PATH": self.path,
            "T5_NET_RTT_MS": f"{self.rtt_ms:.1f}",
            "T5_NET_SEED": str(self.seed),
            "T5_NET_BUILD": self.build,
        }
        if self.key:
            env["T5_NET_KEY"] = self.key
        if self.input_delay is not None:
            env["T5_RB_NET_DELAY"] = str(int(self.input_delay))
        rf = result_file or self.result_file
        if rf:
            env["T5_NET_RESULT_FILE"] = rf
        if self._dup_socket is not None:
            env["T5_NET_SOCKET_FILE"] = self.socket_file_path()
        return env

    # ---------------------------------------------------------------- socket handover (optional)
    def socket_file_path(self):
        import tempfile
        return os.path.join(tempfile.gettempdir(), f"t5net-{self.match_id}.sock")

    def share_socket(self, pid, path=None):
        """Duplicate the punched socket into process `pid` (Windows) and write the blob for the
        game to `path` (default socket_file_path()). Closes this process's copy."""
        s = self._dup_socket
        if s is None:
            raise RuntimeError("this ticket was made with handover='port'")
        path = path or self.socket_file_path()
        blob = s.share(pid)
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            f.write(blob.hex())
        os.replace(tmp, path)
        s.close()
        self._dup_socket = None
        return path

    def release_socket(self):
        if self._dup_socket is not None:
            self._dup_socket.close()
            self._dup_socket = None

    def summary(self):
        how = {"direct": N_("direct connection"), "lan": N_("local network"), "relay": N_("through the lobby server")}
        return t("{name} -- {how}, ping {ms} ms, input delay {delay}", name=self.opponent.get("name", "?"),
                 how=t(how[self.path]) if self.path in how else self.path, ms=f"{self.rtt_ms:.0f}", delay=self.delay)


def read_result_file(path):
    """The game's result file -> (winner, score) or None if it is not there / not valid."""
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return None
    w = d.get("winner")
    sc = d.get("score")
    if w not in (0, 1, None):
        return None
    if sc is not None and not (isinstance(sc, list) and len(sc) == 2 and all(isinstance(x, int) for x in sc)):
        sc = None
    return w, sc
