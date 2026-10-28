"""Casual matches by choice: P1 / P2 and the stage (1.1.5; docs/ONLINE.md "Sides and stages by choice").

A player's wishes -- the side (P1, P2 or any) and the stage (one of the server's stages or Random) -- are a
setting of their launcher: `casual_prefs {side, stage}`, sent after every login and whenever the player changes
them, like spec_prefs. They count in the casual matches the two players chose each other for: an accepted
challenge, a friend's casual invite, a room's match (not a ranked room's), and the rematches of those. Ranked and
Quick get the server's sides and a random stage.

The server's sides (1.1.7; owner: "never the one with the lower ping is P1"): a fair coin (`_side_coin`, secrets)
orders the two players of every queue match (ranked and quick), of a ranked room's new set, and of a ranked rematch
(a new set; with launchers without sets a new rated game). The games of a rated set keep the sides of its first
game (they continue inside the running games; a game keeps its slot for its whole netplay session), a quick
rematch keeps them too, and a tournament set has its bracket's order. Before 1.1.7 the queue made the player with
the lower server round trip P1 ("more likely the better-connected PC"): that round trip is to the lobby server, not
between the two PCs, and the host role carries nothing that makes a better connection (docs/ONLINE.md "The side is
the netplay role"). The role is in match_found / match_reveal / match_start as always, so this needs no launcher
change: every launcher plays the side the server names.

Sides. The side is the netplay role: the game makes the host P1 (slot 0) and the joiner P2 (netplay_core.cpp,
`slot = join ? 1 : 0`); setting up the connection is the same for both (both launchers punch, both games get
the other's address, the relay keeps one session per side; the host only answers the first valid hello and
announces the session). So a side wish only orders the two players of the match -- no game change, the same
build. A wish is granted when the other player wants the other side or does not care; both want the same side:
a coin flip; nobody cares: the order as before (the challenger, the inviter, the room's first player is P1).

Stages. The same wish on both sides: that one (Random: drawn from the pool as before, with the match's seed).
Different wishes: one of the two, by the match's seed (Random against a stage: half the time that stage, else a
random one). A Tekken 5 stage counts only when the server draws those too (T5L_OLD_STAGES) and both launchers know
them (cap old_stages); else it is Random. welcome.casual.stages lists what a launcher can offer.

Swap sides on a rematch: either player asks for it with the rematch (`rematch {swap: true}`; the offer the other
player gets says so). The rematch then has P1 and P2 the other way round, over a new netplay session: a game keeps
its slot for its whole session, so a rematch inside the running games cannot swap. Casual matches by choice only.

Older launchers never send casual_prefs (any side, Random): their matches are as before. Against a new launcher
they get their side and the stage in match_found / match_start as always; asked for a swap they see an ordinary
rematch offer.
"""
import logging
import random
import secrets

from .. import fighters, proto
from ..proto import LobbyError

log = logging.getLogger("t5lobby.server")

CASUAL_ORIGINS = ("challenge", "invite", "room")   # the matches whose players chose each other
SIDES = (None, 0, 1)                                # any, P1, P2


def _coin():
    """A fair coin for two players who want the same side (tests replace it)."""
    return secrets.randbelow(2)


def _side_coin():
    """The fair coin for the server's sides: 0 keeps the order it is given, 1 swaps it (tests replace it)."""
    return secrets.randbelow(2)


class CasualMixin:
    """The server's side of casual choices (a mixin of LobbyServer)."""

    # ---------------------------------------------------------------- wishes
    @staticmethod
    def _casual_wish(p):
        """{"side": None | 0 | 1, "stage": key | "random"}: what `p` asked for (an older launcher: nothing)."""
        return {"side": getattr(p, "casual_side", None), "stage": getattr(p, "casual_stage", fighters.RANDOM)}

    def _casual_stages(self, caps):
        """The stages a launcher with `caps` may choose: the stage select's, and the Tekken 5 ones when this server
        draws those too and the launcher knows them."""
        return self.table.stage_pool(old_stages=bool(self.cfg.old_stages) and "old_stages" in caps)

    def _casual_welcome(self, conn):
        return {"casual": {"stages": self._casual_stages(getattr(conn, "caps", ()))}}

    async def h_casual_prefs(self, conn, msg):
        """The player's wishes for casual matches: side 0 (P1), 1 (P2) or null (any); stage a stage key or
        "random"."""
        if not conn.state.take():
            raise LobbyError(proto.E_RATE, "slow down")
        side = msg.get("side")
        if side not in SIDES or isinstance(side, bool):
            raise LobbyError(proto.E_BAD_REQUEST, "side: 0 (P1), 1 (P2) or null (any)")
        stage = str(msg.get("stage") or fighters.RANDOM)
        if stage != fighters.RANDOM and stage not in self._casual_stages(getattr(conn, "caps", ())):
            raise LobbyError(proto.E_BAD_REQUEST, f"unknown stage {stage!r}")
        p = conn.player
        p.casual_side, p.casual_stage = (None if side is None else int(side)), stage

    # ---------------------------------------------------------------- which matches
    def _casual_match(self, m):
        """Do the players' wishes count in match `m`? Casual matches they chose each other for (the first match of
        its set came from a challenge, an invite or a room), not ranked ones (also not a ranked room's match that
        the server made unranked), not the queue's."""
        if m.ranked or (m.room is not None and m.room.ranked and not m.room.community):
            return False
        first = m.set.matches[0] if m.set is not None and m.set.matches else m
        return first.origin in CASUAL_ORIGINS

    # ---------------------------------------------------------------- sides
    def _casual_sides(self, a, b, ranked=False):
        """(P1, P2) for a casual match between `a` (the challenger, the inviter, the room's first player) and `b`,
        by their side wishes. ranked: the server's order (a, b) stays."""
        if ranked:
            return a, b
        wa, wb = self._casual_wish(a)["side"], self._casual_wish(b)["side"]
        if wa is None and wb is None:
            return a, b
        if wa is not None and wa == wb:
            first = (a, b) if _coin() == 0 else (b, a)
            how = "coin flip"
        elif wa == 0 or wb == 1:
            first, how = (a, b), "wish"
        else:
            first, how = (b, a), "wish"
        log.info("casual sides: %s P1, %s P2 (%s)", first[0].name, first[1].name, how)
        return first

    @staticmethod
    def _drawn_sides(a, b, why):
        """(P1, P2) of a match whose sides the server decides (a queue match, a ranked room's new set): a fair
        coin, never the server round trip, the queue order or the room's order."""
        first = (a, b) if _side_coin() == 0 else (b, a)
        log.info("sides: %s P1, %s P2 (drawn, %s)", first[0].name, first[1].name, why)
        return first

    @staticmethod
    def _ranked_rematch_swap(prev):
        """A ranked rematch starts a new set (a launcher without sets: a new rated game), so its sides are drawn
        again: True = P1 and P2 the other way round (a new netplay session, like Swap sides). The next game of a
        running rated set is not a rematch (_set_next keeps the set's sides)."""
        gs = prev.set
        if not prev.ranked or (gs is not None and gs.rated and gs.state == "active"):
            return False
        swap = _side_coin() == 1
        log.info("ranked rematch of %s: sides drawn again (%s)", prev.id, "swapped" if swap else "as before")
        return swap

    def _rematch_swap(self, prev, msg):
        """Does this rematch answer ask for P1 and P2 the other way round? Only in a casual match by choice."""
        return bool(msg.get("swap")) and self._casual_match(prev)

    @staticmethod
    def _rematch_swapped(prev):
        """Both said yes to the rematch of `prev`: did either of them ask for the sides swapped?"""
        return any((r or {}).get("swap") for r in getattr(prev, "rematch", ()) or ())

    def _casual_start_info(self, m):
        """For match_start: the wishes counted in this match (the launcher offers Swap sides on its rematch)."""
        return {"casual": {"swap": True}} if self._casual_match(m) else {}

    # ---------------------------------------------------------------- stages
    def _casual_stage_for(self, m, p):
        """`p`'s stage wish if this match can have it, else Random."""
        key = self._casual_wish(p)["stage"]
        st = self.table.stage(key)
        if st is None or (st.get("t5") and not self._old_stages(m)):
            return fighters.RANDOM
        return key

    def _casual_stage(self, m, seed):
        """The stage key to put into table.resolve() for match `m`: Random (drawn there, as before) unless the
        players' wishes count; then by their wishes (the coin from the match's seed: the same on a relay retry)."""
        if not self._casual_match(m):
            return fighters.RANDOM
        wa, wb = (self._casual_stage_for(m, q) for q in m.players)
        if wa == wb:
            return wa
        return (wa, wb)[random.Random((int(seed) ^ 0x5EED57A6) & 0xFFFFFFFF).randrange(2)]
