"""Online training rooms and the health handicap (1.1.5; docs/ONLINE.md "Training rooms and the health handicap").

Both change what the two games simulate, so the games must agree on them: they travel in match_start's `fight`
(`training`, `life`), which both launchers turn into the same fight line (`train=1`, `life=P1|P2`) and the games
latch at FIGHT START (src/netplay/match_rules.h). The server decides them once per match, at create_match, from the
room (training) and the players' own settings (life), so match_found, match_start and every rematch of it agree.

* Training room: a room whose matches are fought with endless health and no round timer (Tekken 8's practice
  lobby). Nothing is rated, recorded or blamed: whatever ends the fight (a player holding SELECT to give up, a
  100 % combo, a player leaving, a lost connection) finishes the match as `training` (no winner, no history, no
  strike). One round: the fight ends at its first KO, and the players' launchers go back to the select screen with
  a rematch. Only launchers that announce the `training` cap (their game can run it) may create or join one, or be
  invited into one.
* Health handicap: each player picks their own health in percent (`set_life`, 30-100 in steps of 10) for casual
  matches -- quick matches, challenges, invites, rooms. Ranked and tournament matches are always 100 %. Both
  players see both values before and during the match (match_found, match_start, the lobby list's `life`).
  Applied only when both launchers have the `handicap` cap (both games must write it).

Methods of LobbyServer (lobby.py) that keep this feature apart from the rest of the server code (the second wave's
agents B and E change the same files).
"""
from .. import proto
from ..proto import LobbyError

LIFE_CHOICES = tuple(range(30, 101, 10))     # what a player may pick (percent)
TRAINING_ROUNDS = 1                          # a training fight ends at its first KO (a give-up)


def clean_life(v):
    """A player's health handicap from a message: one of LIFE_CHOICES, else None."""
    if isinstance(v, bool) or not isinstance(v, int) or v not in LIFE_CHOICES:
        return None
    return v


class MatchRulesMixin:
    """Methods of LobbyServer: self.cfg, self.dirty, ..."""

    # ------------------------------------------------------------------ the health handicap
    async def h_set_life(self, conn, msg):
        """The health this player fights with in casual matches (percent; 100 = no handicap)."""
        if "handicap" not in conn.caps:
            raise LobbyError(proto.E_NOT_ALLOWED, "the health handicap needs a newer launcher; update it")
        life = clean_life(msg.get("life"))
        if life is None:
            raise LobbyError(proto.E_BAD_REQUEST, "life is 30 to 100 in steps of 10")
        p = conn.player
        if p.life != life:
            p.life = life
            self.dirty = True
        return {"t": "life", "life": life}

    @staticmethod
    def _rules_apply_life(host, join, ranked, origin):
        """The two players' health for a new match ([P1, P2] percent) -- None when it is 100/100 or cannot apply:
        ranked and tournament matches, or a launcher (game) that cannot play it."""
        if ranked or origin == "tournament":
            return None
        if not all("handicap" in getattr(q.conn, "caps", ()) for q in (host, join)):
            return None
        life = [getattr(host, "life", 100), getattr(join, "life", 100)]
        return life if life != [100, 100] else None

    def _rules_new_match(self, m, host, join, ranked, origin, rematch_of=None):
        """create_match: the match's rules, decided once (a rematch keeps its first match's training flag; the
        handicap is taken anew -- a player may have changed it between two fights)."""
        if rematch_of is not None and getattr(rematch_of, "training", False):
            m.training = True
        m.life = self._rules_apply_life(host, join, ranked, origin)

    @staticmethod
    def _rules_found(m, side):
        """match_found's part: what the player is about to accept (their own side's view)."""
        d = {}
        if m.training:
            d["training"] = True
        if m.life:
            d["life"] = {"you": m.life[side], "opponent": m.life[1 - side]}
        return d

    @staticmethod
    def _rules_fight(m):
        """match_start's `fight` part: what both games simulate (the launchers' fight line)."""
        d = {}
        if m.training:
            d.update(training=True, rounds=TRAINING_ROUNDS)
        if m.life:
            d["life"] = list(m.life)
        return d

    # a training fight that ended in the game (a give-up, a KO): reason None -- the launchers go back to the select
    # screen together; any other reason (a player left or quit, the connection, a crash): they end the session
    FOUGHT = (None, "too_short", "no_result", "score_mismatch")

    @classmethod
    def _rules_finish(cls, m, status, winner, score, reason, blame):
        """_finish: a training match has no result -- whatever ended it."""
        if not m.training:
            return status, winner, score, reason, blame
        if status in ("confirmed", "onesided", "resolved", "void") and reason in cls.FOUGHT:
            reason = None
        return "training", None, None, reason, None

    def _training_leave(self, p):
        """Leave room during a training room's match ("leave any time"): the match ends without a result (reason
        "left"), the room leave goes on. False when p's match is not a training match (finish it first)."""
        m = p.match
        if m is None or not m.training:
            return False
        if m.state == "playing":
            self._finish(m, "training", None, None, reason="left")
        else:
            self.cancel_match(m, "opponent_left", by=p)
        return p.match is None

    # ------------------------------------------------------------------ training rooms
    @staticmethod
    def _can_train(p_or_conn):
        caps = getattr(p_or_conn, "caps", None)
        if caps is None:
            conn = getattr(p_or_conn, "conn", None)
            caps = getattr(conn, "caps", ()) if conn is not None else ()
        return "training" in caps

    def _room_training_opt(self, conn, msg, ranked):
        """room_create's `training`: True only from a launcher that can play it; never ranked."""
        if not msg.get("training"):
            return False
        if not self._can_train(conn):
            raise LobbyError(proto.E_NOT_ALLOWED, "training rooms need a newer launcher; update it")
        if ranked:
            raise LobbyError(proto.E_NOT_ALLOWED, "training rooms are casual (unranked)")
        return True

    def _room_training_check(self, r, p):
        """Joining or being invited into a training room: only a launcher (game) that can play it."""
        if getattr(r, "training", False) and not self._can_train(p):
            raise LobbyError(proto.E_NOT_ALLOWED, "training rooms need a newer launcher; update it")
