"""Characters and stages: lobby keys <-> the game's ids for direct-fight mode.

The lobby, the launcher and the server talk in stable keys ("jin", "s20",
"random"); only T5_FIGHT carries the game's numeric ids (docs/DIRECTFIGHT.md).
The table is data/fighters.json (or the file named by T5_FIGHTERS_FILE).

    T5_FIGHT=<p1 id>,<p2 id>,<stage id>,<rounds to win>
"""
import json
import os
import random

from .i18n import N_, t

RANDOM = "random"
# The stages' names (docs/DIRECTFIGHT.md "Stage ids": each id seen in a fight of its own, named as the Tekken wikis
# list the game's stages; the game itself shows only pictures). Players know them by these English names in every
# language, so the catalogs keep them. Ids 17-30 are Dark Resurrection's new versions of the Tekken 5 stages 0-13.
STAGE_NAMES = {
    "s17": N_("Western Gate"), "s18": N_("Autumn Temple"), "s19": N_("Meteor Shower"), "s20": N_("Ghetto Pit"),
    "s21": N_("City Lights"), "s22": N_("Great Plains"), "s23": N_("Galleon"), "s24": N_("All Hollow's Eve"),
    "s25": N_("Winter Palace"), "s26": N_("Festival"), "s27": N_("Aurora Australis"), "s28": N_("Heaven's Gate"),
    "s29": N_("Space Colony"), "s30": N_("Pool Party"), "s31": N_("Playroom"), "s32": N_("Wolves' Den"),
    "s33": N_("Industrial Complex"), "s34": N_("Ominous Mist"),
    "t5s01": N_("Dragon's Nest"), "t5s02": N_("Burning Temple"), "t5s03": N_("Waterfall"),
    "t5s04": N_("Urban Jungle"), "t5s05": N_("City at Sunset"), "t5s06": N_("Moonlit Wilderness"),
    "t5s07": N_("Pirate's Cove"), "t5s08": N_("Secret Garden"), "t5s09": N_("Cathedral"), "t5s10": N_("Acid Rain"),
    "t5s11": N_("Polar Paradise"), "t5s12": N_("Hell's Gate"), "t5s13": N_("Final Frontier"),
    "t5s14": N_("Poolside"), "t5s15": N_("Final Stage"),
}
_DEFAULT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "fighters.json")


class Table:
    def __init__(self, path=None):
        path = path or os.environ.get("T5_FIGHTERS_FILE") or _DEFAULT
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        self.path = path
        self.status = d.get("status", "")
        self.fighters = [dict(x) for x in d["fighters"]]
        self.stages = [dict(x) for x in d["stages"]]
        self._f = {x["key"]: x for x in self.fighters}
        self._s = {x["key"]: x for x in self.stages}

    @property
    def placeholder(self):
        return self.status == "placeholder"

    def fighter(self, key):
        return self._f.get(key)

    def stage(self, key):
        return self._s.get(key)

    def fighter_by_id(self, fid):
        """The fighter with the game's character id (the in-game select reports ids), or None."""
        for x in self.fighters:
            if x["id"] == fid:
                return x
        return None

    def fighter_name(self, key):
        x = self._f.get(key)
        return x["name"] if x else (t("Random") if key == RANDOM else (key or "?"))

    def stage_name(self, key):
        """The stage's name: "Ghetto Pit"; a stage without one by its number ("Stage 35", "Tekken 5 stage 6")."""
        x = self._s.get(key)
        if x is None:
            return t("Random") if key == RANDOM else (key or "?")
        if key in STAGE_NAMES:
            return t(STAGE_NAMES[key])
        if x.get("t5"):
            return t("Tekken 5 stage {number}", number=int(key[3:]) if key[3:].isdigit() else x["id"] + 1)
        return t("Stage {number}", number=x["id"])

    def selectable(self):
        """Fighters a player can pick (bosses and unverified ones are left out)."""
        return [x for x in self.fighters if not x.get("boss") and not x.get("unverified")]

    def valid_fighter(self, key):
        return key == RANDOM or key in {x["key"] for x in self.selectable()}

    def valid_stage(self, key):
        return key == RANDOM or key in self._s

    def stage_pool(self, old_stages=False):
        """Stages drawn at random: the ones the stage select offers, plus the Tekken 5 stages ("t5": ids 0-13
        and 15) when the server enables them for a match (docs/RANKED.md "Characters and stages")."""
        return [x["key"] for x in self.stages if old_stages or not x.get("t5")]

    def resolve(self, p1, p2, stage, seed, old_stages=False):
        """Turn 'random' into concrete keys, the same way on every machine (seeded).
        -> (p1 key, p2 key, stage key)."""
        rng = random.Random(int(seed) & 0xFFFFFFFF)
        pool = [x["key"] for x in self.selectable()]
        p1 = p1 if p1 in self._f else rng.choice(pool)
        p2 = p2 if p2 in self._f else rng.choice(pool)
        stage = stage if stage in self._s else rng.choice(self.stage_pool(old_stages))
        return p1, p2, stage

    def fight_env(self, p1, p2, stage, rounds=3):
        """T5_FIGHT value for concrete keys."""
        return f"{self._f[p1]['id']},{self._f[p2]['id']},{self._s[stage]['id']},{int(rounds)}"


_table = None


def table():
    global _table
    if _table is None:
        _table = Table()
    return _table
