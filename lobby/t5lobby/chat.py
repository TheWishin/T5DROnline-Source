"""Presentation helpers for server-authenticated lobby badges and mentions (1.2.0).

Names come only from the server's current player rows. Text never grants a badge or decides who is pinged.
"""
import re

from . import proto
from .i18n import t


def dev_badge(player):
    return isinstance(player, dict) and player.get("badge") == "dev"


def display_name(player):
    """The marker is outside the ASCII account-name alphabet, so a name cannot impersonate it."""
    return player.get("name", "") + ("  \u25c6 " + t("DEV") if dev_badge(player) else "")


def mentions_me(event, me):
    """Only the server's resolved player IDs count, never an @ in the message text; ignore own echoes."""
    mine = (me or {}).get("id")
    sender = event.get("from") or {}
    mentions = event.get("mentions")
    return bool(mine is not None and sender.get("id") != mine and isinstance(mentions, list)
                and mine in mentions)


class Completion:
    """Tab cycles an @prefix through the current authoritative roster, without a request or a local user list."""

    def __init__(self):
        self.last = None
        self.roster = ()
        self.matches = ()
        self.index = -1

    def complete(self, text, cursor, players):
        names = tuple(sorted({p.get("name") for p in players if isinstance(p, dict)
                              and proto.valid_name(p.get("name"))}, key=lambda name: (name.casefold(), name)))
        cursor = max(0, min(len(text), int(cursor)))
        if self.last != (text, cursor) or names != self.roster:
            self.last = None
            at = text.rfind("@", 0, cursor)
            if at < 0 or (at and re.match(r"[\w@]", text[at - 1])):
                return None
            prefix = text[at + 1:cursor].casefold()
            matches = tuple(name for name in names if name.casefold().startswith(prefix))
            if not matches:
                return None
            self.before, self.after = text[:at + 1], text[cursor:]
            self.matches, self.index, self.roster = matches, -1, names
        self.index = (self.index + 1) % len(self.matches)
        completed = self.before + self.matches[self.index]
        # A separator lets typing continue naturally and makes punctuation in names unambiguous.
        if not self.after or not self.after[0].isspace():
            completed += " "
        result = (completed + self.after, len(completed))
        self.last = result
        return result
