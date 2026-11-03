"""Optional 1.2 host UI rules. The server owns deadlines and all match transitions.

Each client sends its own vote when its cancellable countdown ends. Those votes
still go through h_rematch's participation, status, block and room checks.
The feature defaults off; old launchers retain the existing rematch protocol.
"""
import math
import time

from .. import proto
from ..proto import LobbyError

CAP = "ingame_rematch_v1"
SKIP_CAP = "auto_skip_after_round_v1"
POLICIES = ("both_confirm", "auto_unless_declined")


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

    def _rematch_capable(self, p):
        return CAP in getattr(getattr(p, "conn", None), "caps", ())

    def _rematch_ui_eligible(self, m):
        if (not self._rematch_enabled() or m.ranked or getattr(m, "requested_ranked", False)
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
        window = duration(self.cfg.rematch_window)
        m.ui_deadline = time.monotonic() + window
        m.ui_auto_after = min(5.0, window / 2.0)

    def _rematch_ui_result(self, m, viewer=None):
        room = getattr(m, "room", None)
        gs = getattr(m, "set", None)
        if gs is not None and getattr(gs, "automatic", False) and gs.state == "active":
            return {}                          # the set countdown owns the next game, before room rotation
        if (self._rematch_enabled() and room is not None and room.community and not room.ranked
                and getattr(room, "mode", "line") == "line"
                and self.rooms.get(room.id) is room and viewer in room.members
                and all(self._rematch_capable(p) and p.online for p in m.players)):
            # Rotation itself remains _room_match_over's job. These are only
            # membership actions, never match-ID rematch votes or public queues.
            return {"rematch_ui": {"v": 1, "kind": "community", "policy": "both_confirm",
                                   "room_mode": "community", "room": room.id, "rotation": room.rotation,
                                   "timeout": duration(self.cfg.room_next_seconds + self.cfg.ready_timeout),
                                   "auto_after": 0,
                                   "actions": ["sit_out" if viewer in room.line else "back_to_line"]}}
        if not hasattr(m, "ui_deadline") or not self._rematch_ui_eligible(m):
            return {}
        return {"rematch_ui": {"v": 1, "kind": "rematch", "policy": m.ui_policy,
                               "timeout": max(0.0, m.ui_deadline - time.monotonic()),
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
            if not self._rematch_enabled() or CAP not in conn.caps or (skip and SKIP_CAP not in conn.caps):
                raise LobbyError(proto.E_NOT_ALLOWED, "rematch rules require an updated launcher")
            if ranked or size > 2 or mode != "line":
                raise LobbyError(proto.E_NOT_ALLOWED, "rematch rules require a classic casual room")
        return chosen, skip

    async def h_room_rules(self, conn, msg):
        """Owner-only rules for future matches; a running result keeps its snapshot."""
        if not self._rematch_enabled() or CAP not in conn.caps:
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
        if (not self._rematch_enabled() or ranked or getattr(m, "requested_ranked", False) or origin == "tournament"
                or getattr(m, "tournament_origin", False)
                or (room is not None and (room.ranked or room.community
                                          or not getattr(room, "auto_skip_after_round", False)))):
            return False
        return all(self._rematch_capable(p)
                   and SKIP_CAP in getattr(p.conn, "caps", ())
                   and getattr(p, "auto_skip_after_round", False) for p in (host, join))
