"""Characters and stages: lobby keys <-> the game's ids for direct-fight mode.

The lobby, the launcher and the server talk in stable keys ("jin", "s20",
"random"); only T5_FIGHT carries the game's numeric ids (docs/DIRECTFIGHT.md).
The table is data/fighters.json (or the file named by T5_FIGHTERS_FILE).

    T5_FIGHT=<p1 id>,<p2 id>,<stage id>,<rounds to win>
"""
import json
import os
import random

RANDOM = "random"
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

    def fighter_name(self, key):
        x = self._f.get(key)
        return x["name"] if x else ("Random" if key == RANDOM else (key or "?"))

    def stage_name(self, key):
        x = self._s.get(key)
        return x["name"] if x else ("Random" if key == RANDOM else (key or "?"))

    def selectable(self):
        """Fighters a player can pick (bosses and unverified ones are left out)."""
        return [x for x in self.fighters if not x.get("boss") and not x.get("unverified")]

    def valid_fighter(self, key):
        return key == RANDOM or key in {x["key"] for x in self.selectable()}

    def valid_stage(self, key):
        return key == RANDOM or key in self._s

    def resolve(self, p1, p2, stage, seed):
        """Turn 'random' into concrete keys, the same way on every machine (seeded).
        -> (p1 key, p2 key, stage key)."""
        rng = random.Random(int(seed) & 0xFFFFFFFF)
        pool = [x["key"] for x in self.selectable()]
        p1 = p1 if p1 in self._f else rng.choice(pool)
        p2 = p2 if p2 in self._f else rng.choice(pool)
        stage = stage if stage in self._s else rng.choice([x["key"] for x in self.stages])
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
