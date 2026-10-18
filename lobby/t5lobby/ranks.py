"""Rank tiers on top of Glicko-2: the game's own rank names, Tekken style.

The tier list is the game's: Tekken 5 DR keeps one rank badge sprite per rank,
in rank order, in a table in its program (English names `beginner_b`,
`9th_kyu_b` ... `tekken_lord_b`, each followed by a Japanese variant). The
index in that table is RANKS' index here, so a tier can be handed to the game
as-is (T5_HUD_RANKS, see docs/RANKED.md "In-game identity"). Whether the game's
own rank number uses the same order is not verified yet; nothing depends on it
except that hook.

How a player moves through the tiers (all numbers in RankRules):

* Placement: the first `placement` ranked matches of an account are placement
  matches. Meanwhile the tier is Beginner (index 0, what the game shows for a new
  profile). After the last one the tier is set straight from the rating, at most
  `placement_cap` (Beginner is never reached again).
* Promotion: as soon as the rating reaches a higher tier's threshold, the player
  is promoted (several tiers at once if the rating jumped).
* Demotion, with hysteresis: only when the rating falls `hysteresis` points
  below the current tier's threshold, and not during the `shield` matches after
  a promotion. The new tier is the highest one whose threshold is within
  `hysteresis` points of the rating, so it is not lost again right away.
  Kyu ranks are never lost (as in the arcade): a player drops at most to 1st
  Dan once they have reached it, and never below their placement tier while
  they are in the Kyu ranks.
* Provisional: while the rating deviation (RD) is above `provisional_rd` the
  rating is still a rough guess; the UI shows the tier with a "?" (also during
  placement).
"""
from dataclasses import dataclass

from .i18n import t

# (name, rating threshold). Index 0 = Beginner (unplaced), index 1 has no threshold (the floor).
RANKS = [
    ("Beginner", None),
    ("9th Kyu", None), ("8th Kyu", 1150), ("7th Kyu", 1200), ("6th Kyu", 1250), ("5th Kyu", 1300),
    ("4th Kyu", 1350), ("3rd Kyu", 1400), ("2nd Kyu", 1440), ("1st Kyu", 1480),
    ("1st Dan", 1520), ("2nd Dan", 1560), ("3rd Dan", 1600), ("4th Dan", 1640), ("5th Dan", 1680),
    ("6th Dan", 1720), ("7th Dan", 1760),
    ("Shihan", 1800), ("Expert", 1840), ("Warrior", 1880), ("Master", 1920), ("Virtuoso", 1960),
    ("Champion", 2000), ("Lone Wolf", 2040), ("Destroyer", 2080), ("Berserker", 2120), ("Sage", 2160),
    ("Legend", 2200), ("Fujin", 2240), ("Raijin", 2280), ("Deity", 2320), ("Lord of War", 2360),
    ("Dragon Lord", 2400), ("Tekken Lord", 2450), ("Dark Lord", 2500), ("Kouryu", 2550), ("Kirin", 2600),
]
BEGINNER = 0
FIRST_DAN = 10
NAMES = [n for n, _ in RANKS]


def threshold(tier):
    """Rating at which `tier` starts (float('-inf') for the floor tiers)."""
    t = RANKS[tier][1]
    return float("-inf") if t is None else float(t)


def tier_for(rating):
    """Highest tier (>= 1) whose threshold the rating reaches."""
    best = 1
    for i in range(1, len(RANKS)):
        if rating >= threshold(i):
            best = i
    return best


def name(tier):
    return NAMES[max(0, min(len(NAMES) - 1, int(tier)))]


def index(name_or_tier):
    """'2nd Dan' / '2nd dan' / 11 -> 11; None when unknown."""
    if isinstance(name_or_tier, int):
        return name_or_tier if 0 <= name_or_tier < len(RANKS) else None
    low = str(name_or_tier).strip().lower()
    for i, n in enumerate(NAMES):
        if n.lower() == low:
            return i
    return None


@dataclass
class RankRules:
    placement: int = 5          # placement matches before the first real tier
    placement_cap: int = 12     # 3rd Dan: the highest tier placement can give
    hysteresis: float = 30.0    # rating points below a tier's threshold before demotion
    shield: int = 3             # matches after a promotion without demotion
    provisional_rd: float = 110.0


@dataclass
class RankState:
    tier: int = BEGINNER        # current tier (index into RANKS)
    games: int = 0              # ranked matches that counted
    since_change: int = 0       # ranked matches since the last tier change
    peak: int = BEGINNER        # highest tier ever held
    floor: int = BEGINNER       # placement tier (Kyu ranks below it are never given back)

    def as_dict(self):
        return {"tier": self.tier, "games": self.games, "since_change": self.since_change, "peak": self.peak,
                "floor": self.floor}


def after_match(state, rating, rules=None):
    """State after one more counted ranked match that left the rating at `rating`.
    -> (new RankState, event): event is None, 'placed', 'promoted' or 'demoted'."""
    rules = rules or RankRules()
    s = RankState(state.tier, state.games + 1, state.since_change + 1, state.peak, state.floor)
    event = None
    if s.games < rules.placement:
        s.tier = BEGINNER
    elif state.tier == BEGINNER:
        s.tier = max(1, min(rules.placement_cap, tier_for(rating)))
        s.floor = s.tier
        s.since_change = 0
        event = "placed"
    else:
        target = tier_for(rating)
        if target > s.tier:
            s.tier = target
            s.since_change = 0
            event = "promoted"
        elif rating < threshold(s.tier) - rules.hysteresis and s.since_change > rules.shield:
            low = tier_for(rating + rules.hysteresis)
            # Kyu ranks are never lost: not below 1st Dan once reached, not below the placement tier.
            low = max(low, FIRST_DAN if s.peak >= FIRST_DAN else s.floor, 1)
            if low < s.tier:
                s.tier = low
                s.since_change = 0
                event = "demoted"
    s.peak = max(s.peak, s.tier)
    return s, event


def describe(state, rd, rules=None):
    """What the lobby shows: {tier, rank, provisional, placement: [played, needed] or None}."""
    rules = rules or RankRules()
    placing = state.tier == BEGINNER and state.games < rules.placement
    return {"tier": state.tier, "rank": name(state.tier),
            "provisional": bool(placing or rd > rules.provisional_rd),
            "placement": [state.games, rules.placement] if placing else None}


def record_label(rec, draws=False):
    """[wins, losses(, draws)] -> '5W 3L' (and ' 1D' when asked for and not zero)."""
    out = t("{wins}W {losses}L", wins=rec[0], losses=rec[1])
    if draws and len(rec) > 2 and rec[2]:
        out += " " + t("{draws}D", draws=rec[2])
    return out


def label(info):
    """'2nd Dan', '2nd Dan?' (provisional), 'Beginner (placement 2/5)'."""
    if not info:
        return ""
    if info.get("placement"):
        n, k = info["placement"]
        return t("{rank} (placement {done}/{total})", rank=info["rank"], done=n, total=k)
    return info["rank"] + ("?" if info.get("provisional") else "")
