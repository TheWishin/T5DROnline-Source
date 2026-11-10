"""Win records in the match (1.2.3; docs/ONLINE.md "Win records in the match"; player wish: "show w/r percentage in
matches -- just like in the arcades").

The game has the arcade's record bar itself: the select screen and the VS screen show each side's "PLAYER DATA
<wins> W <losses> L <rate> %" from that side's VS custom data (wins u32 at +0x108, losses u32 at +0x10C; the game
works out the rate). Online it always read "0 W 0 L 0.00 %". Now the server hands both launchers each player's
record with match_start and the game writes it there at FIGHT START (T5_HUD_RECORDS, src/directfight/df_fight.cpp).

Which record: a ranked match shows the players' ranked record (what the ranking is about; casual games among friends
cannot pad it), every other match the record over all their counted matches, ranked and casual (casual-only numbers
are small for players who mostly play ranked; an arcade card counts every fight too). Counted matches as the
profile's stats (store.match_stats); draws are left out (the game's bar has wins and losses only). Guests have no
record: their side shows 0 W 0 L as before.

Both games write the same numbers (the server's one list, P1 first), so the two PCs' memory stays the same. The
bytes are display data -- outside the netplay state hash, and nothing in a fight reads them -- but they are sent only
when both clients have the cap (an older launcher or game would write nothing on its PC) and both players allow it
(`record_prefs {show}`, the launcher's "Show win records in matches", on by default, sent after every login and on
change, like spec_prefs): a player who turns it off hides the records of both players of their matches.
"""
import logging

from .. import proto
from ..proto import LobbyError

log = logging.getLogger("t5lobby.server")

CAP = "hud_records"
FEATURE = "hud_records"
KIND_RANKED = "ranked"
KIND_ALL = "all"


def record_of(stats, kind):
    """[wins, losses] from store.match_stats' {ranked: {...}, casual: {...}} for `kind` (ranked / all)."""
    parts = ("ranked",) if kind == KIND_RANKED else ("ranked", "casual")
    wins = sum(int((stats.get(k) or {}).get("wins") or 0) for k in parts)
    losses = sum(int((stats.get(k) or {}).get("losses") or 0) for k in parts)
    return [max(0, wins), max(0, losses)]


class RecordsMixin:
    async def h_record_prefs(self, conn, msg):
        """The player's "Show win records in matches" (default on: a client with the cap that never sent it)."""
        if CAP not in getattr(conn, "caps", ()):
            raise LobbyError(proto.E_BAD_REQUEST, "bad request")
        show = msg.get("show")
        if not isinstance(show, bool):
            raise LobbyError(proto.E_BAD_REQUEST, "show must be boolean")
        conn.player.record_show = show
        return None

    def _records_wanted(self, m):
        """Both clients can show records and both players allow it."""
        return all(CAP in getattr(p.conn, "caps", ()) and getattr(p, "record_show", True) for p in m.players)

    def _records(self, m):
        """{"kind", "sides": [[wins, losses] or None, ...]} for match m (P1 first), or None. Read once per match start
        (a rematch reads them again: the match before it counts by then)."""
        if not self._records_wanted(m):
            return None
        kind = KIND_RANKED if m.ranked else KIND_ALL
        accounts = [None if p.guest else getattr(p, "account_id", None) for p in m.players]
        try:
            stats = self.store.match_stats_of([a for a in accounts if a is not None])
        except Exception:                       # (a database problem never stops a match)
            log.exception("win records for match %s", m.id)
            return None
        return {"kind": kind, "sides": [None if a is None else record_of(stats.get(a) or {}, kind) for a in accounts]}

    def _records_start_info(self, m, p):
        """For match_start to player p: {"records": ...} when the match has them (only to a client with the cap)."""
        if CAP not in getattr(p.conn, "caps", ()):
            return {}
        if getattr(m, "_records_at", None) != m.started:
            m._records_at, m._records_info = m.started, self._records(m)
        return {"records": m._records_info} if m._records_info is not None else {}
