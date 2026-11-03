"""The rematch question in the game (1.2.0, docs/REMATCH_1.2.0.md). The server owns deadlines and all match
transitions.

After a casual match (quick, challenge, invite, classic room; never ranked sets, tournaments or community rooms)
whose two players both have it (cap ingame_rematch_v1), the result carries `rematch_ui`: the launchers show the
question in the game with a countdown of T5L_INGAME_REMATCH_SECONDS (10), and the rematch window is that long (plus
VOTE_GRACE for a yes pressed in the last moment). Each client still sends its own vote through h_rematch's
participation, status, block and room checks. Old launchers (no cap) keep the launcher's question and the 20 s
window (T5L_REMATCH_WINDOW).
"""
import math
import time

from .. import proto
from ..proto import LobbyError

CAP = "ingame_rematch_v1"
SKIP_CAP = "auto_skip_after_round_v1"
INTRO_CAP = "auto_skip_intro_v1"    # 1.2.0: this launcher's game skips the intros by the fight line's rule
POLICIES = ("both_confirm", "auto_unless_declined")
VOTE_GRACE = 1.5        # seconds past the countdown a vote still counts (pressed at 9.9 s, still on its way)


def policy(value):
    if value not in POLICIES:
        raise LobbyError(proto.E_BAD_REQUEST, "invalid rematch policy")
    return value


def duration(value):
    """Only bounded finite server durations enter the optional protocol."""
    value = float(value)
    return min(120.0, max(1.0, value)) if math.isfinite(value) else 20.0


class RematchMixin:
    def _rematch_enabled(self):
        return bool(getattr(self.cfg, "ingame_rematch", False))

    def _skip_enabled(self):
        """The after-round skip rule changes what the games simulate: its own switch (T5L_AUTO_SKIP, on), and each
        match only with both players' consent. Independent of the in-game rematch question (T5L_INGAME_REMATCH)."""
        return bool(getattr(self.cfg, "auto_skip", False))

    def _rematch_capable(self, p):
        return CAP in getattr(getattr(p, "conn", None), "caps", ())

    def _rematch_ui_eligible(self, m):
        if (not self._rematch_enabled() or m.ranked or getattr(m, "requested_ranked", False)
                or getattr(m, "training", False)        # (a training room goes back to the select by itself)
                or getattr(m, "origin", None) == "tournament" or getattr(m, "tournament_origin", False)):
            return False
        gs = getattr(m, "set", None)
        if getattr(gs, "tour", None) is not None or (gs is not None and
                (gs.rated or getattr(gs, "automatic", False)) and gs.state == "active"):
            return False
        room = getattr(m, "room", None)
        if room is not None and (room.community or room.ranked or self.rooms.get(room.id) is not room):
            return False
        return all(self._rematch_capable(p) and p.online and p.room is room for p in m.players)

    def _rematch_ui_open(self, m):
        """Latch the policy once at the authoritative result, before sending it."""
        if not self._rematch_ui_eligible(m):
            return
        room = m.room
        chosen = getattr(room, "rematch_policy", "both_confirm") if room is not None else getattr(
            self.cfg, "casual_rematch_policy", "both_confirm")
        # Invalid operator configuration fails closed to the explicit-vote rule.
        m.ui_policy = chosen if chosen in POLICIES else "both_confirm"
        window = duration(getattr(self.cfg, "ingame_rematch_seconds", 10.0))
        m.ui_window = window
        m.ui_deadline = time.monotonic() + window + VOTE_GRACE
        m.ui_auto_after = min(5.0, window / 2.0)

    def _rematch_window(self, m):
        """Seconds the players have to agree on a rematch of `m` (the in-game question's, else the launcher's)."""
        if hasattr(m, "ui_deadline"):
            return m.ui_window
        return self.cfg.rematch_window

    def _rematch_ui_result(self, m, viewer=None):
        gs = getattr(m, "set", None)
        if gs is not None and getattr(gs, "automatic", False) and gs.state == "active":
            return {}                          # the set countdown owns the next game
        if not hasattr(m, "ui_deadline") or not self._rematch_ui_eligible(m):
            return {}
        return {"rematch_ui": {"v": 1, "kind": "rematch", "policy": m.ui_policy,
                               "timeout": round(max(0.0, m.ui_deadline - VOTE_GRACE - time.monotonic()), 2),
                               "auto_after": m.ui_auto_after,
                               "room_mode": "classic" if m.room is not None else "casual",
                               "actions": ["accept", "decline"]}}

    def _rematch_ui_validate(self, m):
        if hasattr(m, "ui_deadline") and (time.monotonic() >= m.ui_deadline
                                         or not self._rematch_ui_eligible(m)):
            self._expire_recent(m)
            raise LobbyError(proto.E_NOT_FOUND, "that match is over; find a new opponent")

    def _rematch_room_options(self, conn, msg, ranked=False, size=2, mode="line"):
        chosen = msg.get("rematch_policy", "both_confirm")
        skip = msg.get("auto_skip_after_round", False)
        if not isinstance(skip, bool):
            raise LobbyError(proto.E_BAD_REQUEST, "auto_skip_after_round must be boolean")
        chosen = policy(chosen)
        if chosen != "both_confirm" or skip:
            # (each rule needs only its own switch and cap: the round skip does not need the in-game question)
            if ((chosen != "both_confirm" and (not self._rematch_enabled() or CAP not in conn.caps))
                    or (skip and (SKIP_CAP not in conn.caps or not self._skip_enabled()))):
                raise LobbyError(proto.E_NOT_ALLOWED, "rematch rules require an updated launcher")
            if ranked or size > 2 or mode != "line":
                raise LobbyError(proto.E_NOT_ALLOWED, "rematch rules require a classic casual room")
        return chosen, skip

    async def h_room_rules(self, conn, msg):
        """Owner-only rules for future matches; a running result keeps its snapshot."""
        if not ((self._rematch_enabled() and CAP in conn.caps) or (self._skip_enabled() and SKIP_CAP in conn.caps)):
            raise LobbyError(proto.E_NOT_ALLOWED, "rematch rules require an updated launcher")
        room = self._room_owner(conn.player)
        if room.ranked or room.community:
            raise LobbyError(proto.E_NOT_ALLOWED, "rematch rules require a classic casual room")
        if room.match is not None or (getattr(room, "set", None) is not None
                and getattr(room.set, "casual", False) and room.set.state == "active"):
            raise LobbyError(proto.E_BUSY, "finish the match first")
        chosen, skip = self._rematch_room_options(conn, {
            "rematch_policy": msg.get("rematch_policy", room.rematch_policy),
            "auto_skip_after_round": msg.get("auto_skip_after_round", room.auto_skip_after_round)},
            room.ranked, room.size, getattr(room, "mode", "line"))
        room.rematch_policy, room.auto_skip_after_round = chosen, skip
        self.dirty = True
        return {"t": "room", "room": self._room_view(room, conn.player)}

    def _rematch_skip_rule(self, m, host, join, ranked, origin):
        """One immutable match flag, only after both players opted in."""
        room = m.room
        if (not self._skip_enabled() or ranked or getattr(m, "requested_ranked", False) or origin == "tournament"
                or getattr(m, "tournament_origin", False)
                or (room is not None and (room.ranked or room.community
                                          or not getattr(room, "auto_skip_after_round", False)))):
            return False
        return all(SKIP_CAP in getattr(getattr(p, "conn", None), "caps", ())
                   and getattr(p, "auto_skip_after_round", False) for p in (host, join))

    def _intro_skip_rule(self, host, join):
        """1.2.0 (owner: "skip the intro at the start of the game online"): the fighters' intros before round 1 are
        skipped in every match -- casual, ranked, tournaments, training rooms -- when both launchers' games have the
        rule (INTRO_CAP); no setting. The games apply it from the fight line (auto_skip_intro=1) as both players'
        START in the intros only (src/netplay/no_pause.h): READY/FIGHT and everything after it stay as they are.
        A launcher without the cap (1.1.9 and older) gets nothing new: both players press START as before.
        T5L_AUTO_SKIP_INTRO=0 switches it off."""
        return bool(getattr(self.cfg, "auto_skip_intro", True)) and all(
            INTRO_CAP in getattr(getattr(q, "conn", None), "caps", ()) for q in (host, join))
