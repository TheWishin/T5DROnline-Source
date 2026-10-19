"""Tournament brackets: single and double elimination (docs/TOURNAMENTS.md "Brackets"). Pure logic, no I/O.

    b = Bracket.build("double", ["a1", "a7", "a3", ...])   # entrants in seed order: seed 1 first
    for s in b.open_sets(): ...                           # sets whose two players are known: play them
    b.report("W1-2", winner=0, score=[2, 1])               # side 0 / 1 of that set won
    b.finished(), b.champion(), b.standings()

An entrant is any hashable key (the lobby uses account ids). Every set has two sides; a side is filled from
its source when that source is decided:

    ("seed", n)      the n-th seed (no such seed: a bye)
    ("win", id)      the winner of set `id`
    ("lose", id)     the loser of set `id` (double elimination: the drop into the losers bracket)
    ("p0"/"p1", id)  side 0 / 1 of set `id` (the grand final reset: the same two players again)

A side can be EMPTY (None): a bye, or a player who was disqualified before the set was reached. A set with
one EMPTY side is a walkover for the other (reason "bye"), with two it is decided for nobody (reason "empty"),
and either way it is never played. EMPTY moves on like a player: the loser of a walkover is EMPTY, so the next
set in the losers bracket is a walkover too. That is all that byes and disqualifications need.

Layout for 2^k slots (the entrants rounded up; top seeds get the byes, seeds 1 and 2 can only meet in the final):

    winners   W1 .. Wk; Wr has 2^(k-r) sets; the winner of Wr-i goes to W(r+1)-ceil(i/2)
    losers    (double, k >= 2) L1 .. L(2k-2): L1 pairs the losers of W1; L(2j) is the winner of L(2j-1) against the
              loser of W(j+1) dropping down (the drops in alternating order, so the same two meet again late);
              L(2j+1) pairs the winners of L(2j). k = 1 (two players): the loser of W1-1 is the losers' finalist.
    grand final  GF1: the winners' champion (side 0) against the losers' champion (side 1). When side 1 wins it
              in a real set, GF2 (the reset) is played between the same two: both have lost once. Otherwise
              GF2 is skipped and GF1's winner is the champion.

Set states: pending (a source is not decided yet), open (both players known: to be played), done.
"""
import math

EMPTY = None
SINGLE, DOUBLE = "single", "double"
FORMATS = (SINGLE, DOUBLE)
# reasons a set was decided without being played (no game): a bye, nobody at all, the grand final reset not needed
NOT_PLAYED = ("bye", "empty", "skipped")


def seed_positions(size):
    """Seeds in bracket order for `size` slots (a power of two): 1 v size, then the halves so that the top seeds
    meet as late as possible. 8 -> [1, 8, 4, 5, 2, 7, 3, 6]."""
    order = [1]
    while len(order) < size:
        n = len(order) * 2
        order = [x for s in order for x in (s, n + 1 - s)]
    return order


def rounds_for(n):
    """Winners rounds for n entrants (at least 1: two players)."""
    return max(1, math.ceil(math.log2(max(2, n))))


class BSet:
    __slots__ = ("id", "bracket", "round", "index", "src", "p", "known", "state", "winner", "score", "reason",
                 "data")

    def __init__(self, sid, bracket, rnd, index, src):
        self.id = sid
        self.bracket = bracket          # "W", "L" or "GF"
        self.round = rnd
        self.index = index              # 1-based within its round
        self.src = [tuple(src[0]), tuple(src[1])]
        self.p = [EMPTY, EMPTY]
        self.known = [False, False]
        self.state = "pending"
        self.winner = None              # 0 / 1 (side), None while not decided or decided for nobody
        self.score = None               # [games side 0, games side 1] when reported
        self.reason = None              # how it was decided: None (played), bye, empty, skipped, no_show, dq, ...
        self.data = {}                  # whatever the tournament keeps with the set (live state, games, carry ...)

    @property
    def played(self):
        """Decided by playing (or by a forfeit): not a bye, an empty set or a skipped reset."""
        return self.state == "done" and self.reason not in NOT_PLAYED

    def winner_entrant(self):
        return self.p[self.winner] if self.state == "done" and self.winner is not None else EMPTY

    def loser_entrant(self):
        if self.state != "done" or self.winner is None:
            return EMPTY
        return self.p[1 - self.winner]

    def to_dict(self):
        return {"id": self.id, "bracket": self.bracket, "round": self.round, "index": self.index,
                "src": [list(s) for s in self.src], "p": list(self.p), "known": list(self.known),
                "state": self.state, "winner": self.winner, "score": self.score, "reason": self.reason,
                "data": self.data}

    @classmethod
    def from_dict(cls, d):
        s = cls(d["id"], d["bracket"], int(d["round"]), int(d["index"]), d["src"])
        s.p = list(d.get("p") or [EMPTY, EMPTY])
        s.known = [bool(x) for x in (d.get("known") or [False, False])]
        s.state = d.get("state") or "pending"
        s.winner = d.get("winner")
        s.score = d.get("score")
        s.reason = d.get("reason")
        s.data = dict(d.get("data") or {})
        return s


class BracketError(ValueError):
    pass


class Bracket:
    def __init__(self, fmt, entrants):
        if fmt not in FORMATS:
            raise BracketError(f"format is {' or '.join(FORMATS)}")
        if len(entrants) < 2 or len(set(entrants)) != len(entrants) or EMPTY in entrants:
            raise BracketError("a bracket needs two or more different entrants")
        self.format = fmt
        self.entrants = list(entrants)              # seed order
        self.k = rounds_for(len(entrants))
        self.size = 1 << self.k
        self.sets = {}                              # id -> BSet, in creation (= dependency) order
        self.dq = set()                             # disqualified entrants: placed as EMPTY from now on
        self.dirty = set()                          # ids changed since the caller last looked (persistence)

    # ------------------------------------------------------------------ building
    @classmethod
    def build(cls, fmt, entrants):
        b = cls(fmt, entrants)
        k, size = b.k, b.size
        pos = seed_positions(size)
        for i in range(size // 2):
            b._add("W", 1, i + 1, ("seed", pos[2 * i]), ("seed", pos[2 * i + 1]))
        for r in range(2, k + 1):
            for i in range(size >> r):
                b._add("W", r, i + 1, ("win", f"W{r - 1}-{2 * i + 1}"), ("win", f"W{r - 1}-{2 * i + 2}"))
        if fmt == DOUBLE:
            if k >= 2:
                for i in range(size // 4):
                    b._add("L", 1, i + 1, ("lose", f"W1-{2 * i + 1}"), ("lose", f"W1-{2 * i + 2}"))
                for j in range(1, k):
                    n = size >> (j + 1)                 # sets in L(2j) = the sets of W(j+1)
                    for i in range(n):
                        x = n - i if j % 2 == 1 else i + 1          # the drops in alternating order
                        b._add("L", 2 * j, i + 1, ("win", f"L{2 * j - 1}-{i + 1}"), ("lose", f"W{j + 1}-{x}"))
                    if j < k - 1:
                        for i in range(n // 2):
                            b._add("L", 2 * j + 1, i + 1, ("win", f"L{2 * j}-{2 * i + 1}"),
                                   ("win", f"L{2 * j}-{2 * i + 2}"))
                losers_champ = ("win", f"L{2 * k - 2}-1")
            else:
                losers_champ = ("lose", "W1-1")
            b._add("GF", 1, 1, ("win", f"W{k}-1"), losers_champ)
            b._add("GF", 2, 1, ("p0", "GF1"), ("p1", "GF1"))
        b.resolve()
        return b

    def _add(self, bracket, rnd, index, s0, s1):
        sid = f"GF{rnd}" if bracket == "GF" else f"{bracket}{rnd}-{index}"
        self.sets[sid] = BSet(sid, bracket, rnd, index, (s0, s1))

    @property
    def losers_rounds(self):
        return 2 * self.k - 2 if self.format == DOUBLE else 0

    def final_id(self):
        return f"W{self.k}-1" if self.format == SINGLE else "GF1"

    # ------------------------------------------------------------------ deciding sets
    def _source(self, src):
        """(known, entrant) for one side's source."""
        kind, ref = src
        if kind == "seed":
            n = int(ref)
            return True, self.entrants[n - 1] if n <= len(self.entrants) else EMPTY
        s = self.sets[ref]
        if kind in ("p0", "p1"):
            # the grand final reset: only when the losers' side won GF1 in a real set and the winners' side is
            # still in the tournament; otherwise it is skipped (both sides EMPTY)
            if s.state != "done":
                return False, EMPTY
            reset = s.winner == 1 and s.played and s.p[0] is not EMPTY and s.p[0] not in self.dq
            return True, (s.p[0 if kind == "p0" else 1] if reset else EMPTY)
        if s.state != "done":
            return False, EMPTY
        return True, s.winner_entrant() if kind == "win" else s.loser_entrant()

    def resolve(self):
        """Fill in every side whose source is decided; decide byes and empty sets. -> ids of sets that opened."""
        opened = []
        for s in self.sets.values():            # (creation order is dependency order: one pass is enough)
            if s.state == "done":
                continue
            for side in (0, 1):
                if not s.known[side]:
                    ok, e = self._source(s.src[side])
                    if ok:
                        s.known[side] = True
                        s.p[side] = EMPTY if e in self.dq else e
                        self.dirty.add(s.id)
            if not all(s.known):
                continue
            if s.p[0] is EMPTY and s.p[1] is EMPTY:
                self._decide(s, None, None, "skipped" if s.bracket == "GF" and s.round == 2 else "empty")
            elif s.p[0] is EMPTY or s.p[1] is EMPTY:
                self._decide(s, 1 if s.p[0] is EMPTY else 0, None, "bye")
            elif s.state == "pending":
                s.state = "open"
                self.dirty.add(s.id)
                opened.append(s.id)
        return opened

    def _decide(self, s, winner, score, reason):
        s.state = "done"
        s.winner = winner
        s.score = list(score) if score is not None else None
        s.reason = reason
        self.dirty.add(s.id)

    def report(self, sid, winner, score=None, reason=None):
        """Set `sid` (open) was won by side `winner` (0 / 1). -> ids of sets that opened."""
        s = self.sets.get(sid)
        if s is None:
            raise BracketError("no such set")
        if s.state != "open":
            raise BracketError("that set is not open")
        if winner not in (0, 1):
            raise BracketError("the winner is side 0 or 1")
        self._decide(s, winner, score, reason)
        return self.resolve()

    def forfeit(self, sid, loser_side, reason="dq"):
        """`loser_side` of an open set does not play it (disqualified, no-show): the other side wins."""
        return self.report(sid, 1 - loser_side, None, reason)

    def double_forfeit(self, sid, reason="no_show"):
        """Neither side plays an open set: decided for nobody (the next opponents get walkovers)."""
        s = self.sets.get(sid)
        if s is None or s.state != "open":
            raise BracketError("that set is not open")
        self._decide(s, None, None, reason)
        return self.resolve()

    # ------------------------------------------------------------------ disqualification
    def disqualify(self, entrant):
        """From now on `entrant` is placed as EMPTY (a set waiting for its other player gets a walkover). -> the id
        of the open set it is in now, which the caller must forfeit for it (forfeit()), or None. Sets it already
        played stay as they are."""
        if entrant not in self.entrants:
            raise BracketError("not in this bracket")
        self.dq.add(entrant)
        hit = None
        for s in self.sets.values():
            if s.state == "open" and entrant in s.p:
                hit = s.id
            elif s.state == "pending":
                for side in (0, 1):
                    if s.known[side] and s.p[side] == entrant:
                        s.p[side] = EMPTY
                        self.dirty.add(s.id)
        if hit is None:
            self.resolve()
        return hit

    # ------------------------------------------------------------------ undoing
    def dependents(self, sid):
        """Sets that take a side from `sid` directly."""
        return [s for s in self.sets.values() if any(ref == sid for _k, ref in s.src)]

    def reset_blocker(self, sid, busy=lambda s: False):
        """Why `sid` cannot be put back to unplayed: the id of a later set that was already played from its result
        (or that `busy(set)` says is being played), else None."""
        todo = list(self.dependents(sid))
        seen = set()
        while todo:
            d = todo.pop()
            if d.id in seen:
                continue
            seen.add(d.id)
            if d.played or busy(d):
                return d.id
            if d.state == "done":               # a bye / empty set decided from it: undone too, and so on
                todo.extend(self.dependents(d.id))
        return None

    def reset(self, sid):
        """Put `sid` back to unplayed (open when both players are still known) and clear what later sets took
        from it. The caller checked reset_blocker() first. -> ids of the sets that changed."""
        s = self.sets.get(sid)
        if s is None:
            raise BracketError("no such set")
        changed = [sid]
        s.state, s.winner, s.score, s.reason = "pending", None, None, None
        self.dirty.add(sid)
        todo = [sid]
        while todo:
            ref = todo.pop()
            for d in self.dependents(ref):
                hit = False
                for side, (_kind, r) in enumerate(d.src):
                    if r == ref and d.known[side]:
                        d.known[side] = False
                        d.p[side] = EMPTY
                        hit = True
                if not hit:
                    continue
                if d.state == "done":
                    todo.append(d.id)           # (a walkover decided from it: what came after it goes too)
                d.state, d.winner, d.score, d.reason = "pending", None, None, None
                self.dirty.add(d.id)
                changed.append(d.id)
        self.resolve()
        return changed

    # ------------------------------------------------------------------ the end
    def finished(self):
        if self.format == SINGLE:
            return self.sets[self.final_id()].state == "done"
        return self.sets["GF2"].state == "done"

    def champion(self):
        if not self.finished():
            return None
        if self.format == SINGLE:
            return self.sets[self.final_id()].winner_entrant()
        gf2 = self.sets["GF2"]
        return gf2.winner_entrant() if gf2.played else self.sets["GF1"].winner_entrant()

    def _stage(self, s):
        """How far into the bracket a loss in `s` eliminates (higher = later = better place)."""
        if s.bracket == "W":
            return s.round
        if s.bracket == "L":
            return s.round
        return 2 * self.k - 2 + s.round      # GF1 / GF2 after the last losers round

    def eliminated(self):
        """{entrant: stage} of the entrants knocked out so far (single: one lost set, double: two), with the stage
        of the set that knocked them out (higher = later)."""
        need = 1 if self.format == SINGLE else 2
        losses, out_at = {}, {}
        for s in self.sets.values():             # (losers' sets come after the winners' ones: the 2nd loss is later)
            if not s.played or s.winner is None:
                continue
            lo = s.p[1 - s.winner]
            if lo is EMPTY:
                continue
            losses[lo] = losses.get(lo, 0) + 1
            if losses[lo] >= need:
                out_at[lo] = self._stage(s)
        return out_at

    def place_for(self, stage):
        """The place of an entrant knocked out at `stage`, the usual way: everyone knocked out in the same round
        shares it. Single: the final's loser 2nd, the semi-finals' 3rd, the quarter-finals' 5th, ... Double: the
        grand final's loser 2nd, the losers' final 3rd, then 4th, 5th, 7th, 9th, 13th ... (one place per player
        knocked out in a later round)."""
        if self.format == SINGLE:
            return 1 + (1 << (self.k - stage))
        if stage > self.losers_rounds:
            return 2
        later = sum(1 for s in self.sets.values() if s.bracket == "L" and s.round > stage)
        return 3 + later

    def standings(self):
        """[(entrant, place)] best first: the champion 1st, everyone knocked out with the place of the round that
        knocked them out (place_for). Entrants still in and the disqualified are not listed."""
        rows = []
        champ = self.champion()
        if champ is not None and champ not in self.dq:
            rows.append((champ, 1))
        for e, st in self.eliminated().items():
            if e not in self.dq and e != champ:
                rows.append((e, self.place_for(st)))
        rows.sort(key=lambda r: (r[1], self.entrants.index(r[0])))
        return rows

    def open_sets(self):
        return [s for s in self.sets.values() if s.state == "open"]

    def set_of(self, entrant):
        """The open set `entrant` plays next, or None."""
        for s in self.sets.values():
            if s.state == "open" and entrant in s.p:
                return s
        return None

    def to_dict(self):
        return {"format": self.format, "entrants": list(self.entrants), "dq": sorted(self.dq, key=str),
                "sets": [s.to_dict() for s in self.sets.values()]}

    @classmethod
    def from_dict(cls, d):
        b = cls(d["format"], list(d["entrants"]))
        b.dq = set(d.get("dq") or ())
        for sd in d["sets"]:
            s = BSet.from_dict(sd)
            b.sets[s.id] = s
        return b
