"""Private chat: relay only; only lines explicitly submitted in a report are stored.

Receipts authenticate a client's chosen report lines without keeping a transcript. The
random signing key lives for one server process; receipts expire after 24 hours.
"""
import hashlib
import hmac
import json
import os
import time

from .. import proto
from ..proto import LobbyError
from .ratelimit import KeyedBuckets, TokenBucket

CAP = "private_chat"
TEXT_LIMIT = 200
REPORT_LINES = 5
RECEIPT_SECONDS = 86400


class PrivateChatMixin:
    def _private_init(self):
        self._private_key = os.urandom(32)
        self._private_send = KeyedBuckets(rate=1.0, burst=5)
        self._private_address = KeyedBuckets(rate=2.0, burst=10)
        self._private_receive = KeyedBuckets(rate=5.0, burst=10)
        self._private_total = TokenBucket(rate=20.0, burst=40)
        self._private_reports = KeyedBuckets(rate=1 / 60.0, burst=2)
        self._private_report_address = KeyedBuckets(rate=1 / 30.0, burst=4)

    @staticmethod
    def _private_actor(p):
        return {"id": p.id, "name": p.name, "guest": p.guest}

    def _private_require(self, conn):
        if not self.cfg.private_chat or CAP not in conn.caps:
            raise LobbyError("private_unavailable", "private messages are unavailable")

    def _private_target(self, msg):
        p = self.players.get(msg.get("player")) if isinstance(msg.get("player"), str) else None
        if p is None and isinstance(msg.get("name"), str):
            p = self.by_name.get(msg["name"].strip().lower())
        return p

    def _private_stamp(self, line):
        # A fixed subset prevents a client adding fields to a report that moderators
        # might mistake for server-verified information.
        clean = {k: line[k] for k in ("id", "from", "to", "text", "time")}
        payload = json.dumps(clean, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
        return hmac.new(self._private_key, payload, hashlib.sha256).hexdigest()

    async def h_private_message(self, conn, msg):
        self._private_require(conn)
        p = conn.player
        key = self._block_key(p)
        # Charge failed attempts too, including unavailable or blocked recipients.
        if (not self._private_send.take(key) or not self._private_address.take(conn.akey)
                or not self._private_total.take()):
            raise LobbyError(proto.E_RATE, "private messages: slow down")
        # The same server policy covers public and private chat. Charge attempts
        # before checking it, so a muted/filtered sender cannot evade rate limits.
        check_mute = getattr(self, "_check_chat_mute", None)
        if check_mute is not None:
            check_mute(p)
        q = self._private_target(msg)
        is_muted = getattr(self, "_is_muted", None)
        if (q is None or q is p or not self._can(q, CAP) or self._is_blocked(p, q)
                or (is_muted(q, p) if is_muted is not None
                    else key in getattr(q, "private_mutes", set()))):
            # The same refusal for offline, blocked and muted: do not disclose preferences.
            raise LobbyError("private_unavailable", "private messages are unavailable")
        if not self._private_receive.take(self._block_key(q)):
            raise LobbyError(proto.E_RATE, "private messages: slow down")
        text = msg.get("text")
        if not isinstance(text, str):
            raise LobbyError("private_empty", "write a private message first")
        check_text = getattr(self, "_check_filtered_text", None)
        if check_text is not None:
            check_text(text, "chat", p)
        text = proto.clean_text(text.strip(), TEXT_LIMIT)
        if not text:
            raise LobbyError("private_empty", "write a private message first")
        if check_text is not None:
            # Cleaning controls and truncating can expose a new word boundary.
            check_text(text, "chat", p)
        line = {"id": "pm" + os.urandom(8).hex(), "from": self._private_actor(p),
                "to": self._private_actor(q), "text": text, "time": time.time()}
        line["receipt"] = self._private_stamp(line)
        # Do not add this to events, log it, or write it to Store.
        q.send(dict(line, t="private_message"))
        return {"t": "private_sent", "message": line}

    async def h_private_mute(self, conn, msg):
        # Keep the older private-chat request working while using the persistent,
        # all-chat mute list on the full lobby server.
        mute = getattr(self, "h_mute", None)
        if mute is not None:
            return await mute(conn, msg, legacy=True)
        self._private_require(conn)
        p, q = conn.player, self._private_target(msg)
        muted = msg.get("muted", True)
        if not isinstance(muted, bool):
            raise LobbyError(proto.E_BAD_REQUEST, "muted is a boolean")
        mutes = p.__dict__.setdefault("private_mutes", {})
        name = msg.get("name")
        if q is not None and q is not p:
            key, shown = self._block_key(q), q.name
        elif q is None and not muted and isinstance(name, str):
            key = next((k for k, v in mutes.items() if v.lower() == name.strip().lower()), None)
            if key is None:
                raise LobbyError("private_unavailable", "private messages are unavailable")
            shown = mutes[key]
        else:
            raise LobbyError("private_unavailable", "private messages are unavailable")
        if muted:
            if key not in mutes and len(mutes) >= self.cfg.max_blocks:
                raise LobbyError("private_limit", "the private mute list is full")
            mutes[key] = shown
        else:
            mutes.pop(key, None)
        return {"t": "private_muted", "name": shown, "muted": muted}

    def _private_report_line(self, p, line):
        try:
            if not isinstance(line, dict) or not isinstance(line.get("receipt"), str):
                return None
            clean = {k: line[k] for k in ("id", "from", "to", "text", "time")}
            if not hmac.compare_digest(self._private_stamp(clean), line["receipt"]):
                return None
            if p.id not in (clean["from"]["id"], clean["to"]["id"]):
                return None
            age = time.time() - clean["time"]
            return clean if 0 <= age <= RECEIPT_SECONDS else None
        except (KeyError, TypeError, ValueError, OverflowError):
            return None

    async def h_private_report(self, conn, msg):
        self._private_require(conn)
        p = conn.player
        if (not self._private_reports.take(self._block_key(p))
                or not self._private_report_address.take(conn.akey)):
            raise LobbyError(proto.E_RATE, "private reports: slow down")
        lines = msg.get("lines")
        if not isinstance(lines, list) or not 1 <= len(lines) <= REPORT_LINES:
            raise LobbyError("private_report_limit", "choose between 1 and 5 private message lines")
        chosen = [self._private_report_line(p, line) for line in lines]
        if any(line is None for line in chosen):
            raise LobbyError("private_receipt", "these private message lines cannot be verified; reconnect and try new lines")
        peer = chosen[0]["to"] if chosen[0]["from"]["id"] == p.id else chosen[0]["from"]
        pair = {p.id, peer["id"]}
        if (any({line["from"]["id"], line["to"]["id"]} != pair for line in chosen)
                or len({line["id"] for line in chosen}) != len(chosen)):
            raise LobbyError("private_receipt", "these private message lines cannot be verified; reconnect and try new lines")
        reason = proto.clean_text(msg.get("reason", ""), TEXT_LIMIT)
        report_id = self.store.add_private_report(p.name, p.account_id, peer["name"], chosen, reason,
                                                  self.cfg.private_report_days, self.cfg.max_private_reports)
        return {"t": "private_reported", "id": report_id, "lines": len(chosen)}
