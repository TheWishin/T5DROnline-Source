"""Local replay library preferences and the viewer's file command channel.

Preferences never modify replay files. Keys use the file name and match number,
so moving the entire replay folder preserves favourites.
"""
import json
import os
import tempfile

import replays


def atomic_text(path, text):
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".replay-", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


class Library:
    def __init__(self, folder):
        self.path = os.path.join(folder, ".replay-library.json")
        self.favourites = set()
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.loads(f.read(1 << 20))
            self.favourites = {v for v in data.get("favourites", []) if isinstance(v, str)}
        except (OSError, ValueError, TypeError, AttributeError):
            pass

    @staticmethod
    def key(entry):
        return os.path.normcase(os.path.basename(entry.path)) + ":" + str(entry.index)

    def favourite(self, entry):
        return self.key(entry) in self.favourites

    def toggle(self, entry):
        favourites = self.favourites ^ {self.key(entry)}
        atomic_text(self.path, json.dumps({"version": 1, "favourites": sorted(favourites)}) + "\n")
        self.favourites = favourites

    def filter(self, entries, fighter="", opponent="", mode="", favourites=False):
        fighter, opponent = fighter.strip().casefold(), opponent.strip().casefold()
        return [e for e in entries
                if (not fighter or any(fighter in replays.fighter_name(p).casefold() for p in (e.p1, e.p2)))
                and (not opponent or opponent in e.opponent.casefold())
                and (not mode or mode == e.mode)
                and (not favourites or self.favourite(e))]


class ViewerChannel:
    """Only publish the next command after the game consumes the previous one."""
    def __init__(self, command, status):
        self.command, self.status = command, status
        self.pending = []
        for path in (command, status):
            try:
                os.remove(path)
            except FileNotFoundError:
                pass

    def send(self, command):
        self.pending.append(command)
        self.flush()

    def flush(self):
        if self.pending and not os.path.exists(self.command):
            atomic_text(self.command, self.pending[0] + "\n")
            self.pending.pop(0)

    def read(self):
        self.flush()
        try:
            with open(self.status, encoding="utf-8") as f:
                data = json.loads(f.read(65536))
            if not isinstance(data, dict):
                return None
            start, end, frame = (int(data.get(k, 0)) for k in ("start", "end", "frame"))
            if not 0 <= start <= end <= 0xFFFFFFFF or not 0 <= frame <= 0xFFFFFFFF:
                return None
            data.update(start=start, end=end, frame=frame)
            rounds = data.get("rounds", [])
            data["rounds"] = [v for v in rounds if type(v) is int and start <= v <= end] if isinstance(rounds, list) else []
            return data
        except (OSError, ValueError, TypeError, OverflowError):
            return None
