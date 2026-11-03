"""Bounded, session-only private conversations. No transcript is written to disk."""
from collections import OrderedDict


MAX_CONVERSATIONS = 32
MAX_LINES = 100
MAX_REPORT_LINES = 5


class Conversations:
    def __init__(self):
        self.rows = OrderedDict()
        self.muted = set()       # independent of transcript eviction; discarded with the session
        self.active = None

    def open(self, name):
        key = name.lower()
        if key not in self.rows:
            if len(self.rows) >= MAX_CONVERSATIONS:
                # Keep the conversation a player is currently reading/reporting stable.
                oldest = next(k for k in self.rows if k != self.active)
                del self.rows[oldest]
            self.rows[key] = {"name": name, "lines": [], "unread": 0, "muted": key in self.muted}
        self.rows.move_to_end(key)
        return self.rows[key]

    def receive(self, message, mine, visible=False):
        """Only accepted server envelopes are retained (including their report receipt)."""
        if not isinstance(message, dict):
            return False
        sender, recipient = message.get("from"), message.get("to")
        if not isinstance(sender, dict) or not isinstance(recipient, dict):
            return False
        outgoing = str(sender.get("name", "")).lower() == mine.lower()
        name = (recipient if outgoing else sender).get("name")
        if not isinstance(name, str) or not name or not isinstance(message.get("text"), str):
            return False
        row = self.open(name)
        if row["muted"] and not outgoing:
            return False
        if any(line.get("id") == message.get("id") for line in row["lines"]):
            return False
        row["lines"].append(dict(message))
        del row["lines"][:-MAX_LINES]
        if not outgoing and not (visible and self.active == name.lower()):
            row["unread"] = min(MAX_LINES, row["unread"] + 1)
        return True

    def select(self, name):
        row = self.open(name)
        self.active = name.lower()
        row["unread"] = 0
        return row

    def set_muted(self, name, muted):
        key = name.lower()
        if muted:
            self.muted.add(key)
        else:
            self.muted.discard(key)
        if key in self.rows:
            self.rows[key]["muted"] = bool(muted)
            if muted:
                self.rows[key]["unread"] = 0

    def report_lines(self, name, indices):
        """Selection is explicit; never silently attach the remainder of a conversation."""
        row = self.rows.get(name.lower())
        if row is None or not indices or len(indices) > MAX_REPORT_LINES:
            return []
        try:
            return [dict(row["lines"][i]) for i in sorted(set(indices)) if i >= 0]
        except (IndexError, TypeError):
            return []

    @property
    def unread(self):
        return sum(row["unread"] for row in self.rows.values())
