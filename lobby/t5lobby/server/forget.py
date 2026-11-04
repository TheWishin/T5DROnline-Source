"""Remove my data (docs/ONLINE.md "Remove my data"): an account removes itself from the server.

    forget_me {password, dry_run}   -> forget_me {dry_run: true, counts}            (what would go; nothing changes)
                                    -> forgotten {counts} and the connection ends     (done)

Accounts only (a guest keeps nothing on the server but match records under the name it played with, which every
other guest may use too); the password is asked again even with a remembered login, with the same failed-attempt
limits as a password change. Not while the player is in a match, a queue, a room, a running set or a tournament that
is not over (signed up, checked in, playing or organizing): those need the account until they end. What goes and what
stays without a name: store.Store.forget_account. The server's own log keeps what it logged before (it rotates).
Feature "forget_me" in the welcome; an older server answers "unknown message" and the launcher says the server
cannot do it.
"""
import logging
import time

from .. import proto
from ..proto import LobbyError
from .store import check_password

log = logging.getLogger("t5lobby")

ACTIVE_TOURNAMENT = ("signup", "checkin", "running")


class ForgetMixin:
    """Methods of LobbyServer (lobby.py)."""

    def _forget_blocker(self, p):
        """Why the account cannot go right now (a sentence for the player), or None."""
        if p.status != "idle" or p.match is not None:
            return f"you are {p.status}: finish or leave it first"
        if p.set is not None and getattr(p.set, "state", None) == "active":
            return "you are in a set: finish or leave it first"
        tours = getattr(getattr(self, "tours", None), "tours", {}) or {}
        for t in tours.values():
            if getattr(t, "state", None) in ACTIVE_TOURNAMENT and (
                    p.account_id in getattr(t, "entrants", {}) or p.account_id == getattr(t, "organizer_id", None)):
                return "you take part in a tournament that is not over: leave it (or let it end) first"
        return None

    def _forget_counts(self, aid):
        """What forget_account would touch (for the launcher's confirmation)."""
        db = self.store
        c = {}
        c["matches"] = db._x("SELECT COUNT(*) FROM matches WHERE p1_account = ? OR p2_account = ?",
                             (aid, aid)).fetchone()[0]
        c["sets"] = db._x("SELECT COUNT(*) FROM sets WHERE p1_account = ? OR p2_account = ?", (aid, aid)).fetchone()[0]
        c["friends"] = db._x("SELECT COUNT(*) FROM friends WHERE account_id = ?", (aid,)).fetchone()[0]
        c["sessions"] = db._x("SELECT COUNT(*) FROM sessions WHERE account_id = ?", (aid,)).fetchone()[0]
        c["blocks"] = db._x("SELECT COUNT(*) FROM blocks WHERE account_id = ?", (aid,)).fetchone()[0]
        return c

    async def h_forget_me(self, conn, msg):
        p = conn.player
        if p.account_id is None:
            raise LobbyError(proto.E_NOT_ALLOWED, "guests have no account on the server: there is nothing to remove")
        why = self._forget_blocker(p)
        if why:
            raise LobbyError(proto.E_BUSY, why)
        key = "name:" + p.name.lower()
        if not self.login_fail.peek_ok(key):
            raise LobbyError(proto.E_RATE, "too many failed attempts; wait a few minutes")
        if not self.pw_ops.take(f"a:{p.account_id}"):
            raise LobbyError(proto.E_RATE, "too many requests; wait a minute")
        row = self.store.account_by_id(p.account_id)
        if row is None:
            raise LobbyError(proto.E_NOT_FOUND, "this account no longer exists")
        if not await self._pw(check_password, str(msg.get("password", "")), row["pw"]):
            self.login_fail.take(key)
            raise LobbyError(proto.E_AUTH, "wrong password")
        if conn.closed or conn.player is not p:
            return None
        why = self._forget_blocker(p)             # (it may have changed while the password was checked)
        if why:
            raise LobbyError(proto.E_BUSY, why)
        aid, name = p.account_id, p.name
        if msg.get("dry_run"):
            return {"t": "forget_me", "dry_run": True, "counts": self._forget_counts(aid)}
        friends = set(p.friends)
        for inv in [i for i in self.invites.values() if p in (i.src, i.dst)]:
            self._end_invite(inv, "cancelled")
        counts = self.store.forget_account(aid) or {}
        self._count("accounts_forgotten")
        log.info("account %s removed itself (Remove my data): %s", aid,
                 ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
        # the friends who are online: this account leaves their lists now
        for fid in friends:
            q = self.by_account.get(fid)
            if q is not None:
                q.friends.discard(aid)
        self._send_friends_soon(*friends)
        # the player leaves the lobby: every session of the account ends, the connection closes after the answer
        for q in [q for q in self.players.values() if q.account_id == aid]:
            q.session = None
            if q.conn is not None and q.conn is not conn:
                q.conn.send({"t": "notice", "code": "account_removed", "msg": "this account was removed"})
                q.conn.drop("account removed")
            self.player_dropped(q, final=True, logout=True)     # (final: out of every list, its session token gone)
        conn.player = None
        conn.send({"t": "forgotten", "counts": counts, "name": name, "time": time.time(), "re": msg.get("rid")})
        self.dirty = True
        return False
