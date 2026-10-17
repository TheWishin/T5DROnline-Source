"""Persistent state: accounts (salted scrypt password hashes, ratings, rank tiers), login
sessions ("remember me" tokens, stored hashed), recovery codes (stored hashed) and match
history. SQLite from the standard library; one connection used from the event loop thread.

Older databases are upgraded in place (missing columns and tables are added)."""
import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time

from .. import rating as glicko
from ..ranks import RankState

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE,
    pw TEXT NOT NULL,
    created REAL NOT NULL,
    last_seen REAL,
    rating REAL NOT NULL, rd REAL NOT NULL, vol REAL NOT NULL,
    last_ranked REAL,
    games INTEGER NOT NULL DEFAULT 0, wins INTEGER NOT NULL DEFAULT 0,
    losses INTEGER NOT NULL DEFAULT 0, draws INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS matches (
    id TEXT PRIMARY KEY,
    created REAL NOT NULL, ended REAL,
    ranked INTEGER NOT NULL,
    p1_name TEXT, p2_name TEXT, p1_account INTEGER, p2_account INTEGER,
    build TEXT, path TEXT, rtt_ms REAL, delay INTEGER,
    status TEXT NOT NULL, winner INTEGER, score TEXT, reports TEXT, rating TEXT
);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    account_id INTEGER NOT NULL,
    created REAL NOT NULL,
    last_used REAL NOT NULL,
    expires REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS recovery (
    account_id INTEGER NOT NULL,
    code_hash TEXT NOT NULL,
    created REAL NOT NULL,
    used REAL
);
CREATE TABLE IF NOT EXISTS ip_bans (
    net TEXT PRIMARY KEY,          -- an address or a CIDR network
    until REAL NOT NULL,           -- unix time
    reason TEXT,
    created REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS sessions_account ON sessions (account_id);
CREATE INDEX IF NOT EXISTS recovery_account ON recovery (account_id);
"""

# Columns added after the first release of the schema: (table, column, declaration).
RANKED_COLUMNS = [
    ("accounts", "ranked_games", "INTEGER NOT NULL DEFAULT 0"),
    ("accounts", "tier", "INTEGER NOT NULL DEFAULT 0"),
    ("accounts", "tier_since", "INTEGER NOT NULL DEFAULT 0"),
    ("accounts", "tier_peak", "INTEGER NOT NULL DEFAULT 0"),
    ("accounts", "tier_floor", "INTEGER NOT NULL DEFAULT 0"),
    ("accounts", "pw_changed", "REAL"),
    ("matches", "origin", "TEXT"),
    ("matches", "started", "REAL"),
    ("matches", "duration", "REAL"),
    ("matches", "p1_char", "TEXT"),
    ("matches", "p2_char", "TEXT"),
    ("matches", "stage", "TEXT"),
    ("matches", "reason", "TEXT"),
    ("matches", "blame", "INTEGER"),
]
# Moderation (the admin tool, docs/HOSTING.md): account bans. Address bans live in ip_bans.
MODERATION_COLUMNS = [
    ("accounts", "banned_until", "REAL"),          # unix time; PERMANENT = for ever; NULL = not banned
    ("accounts", "ban_reason", "TEXT"),
]
RANKED_INDEXES = """
CREATE INDEX IF NOT EXISTS matches_p1 ON matches (p1_account, ended);
CREATE INDEX IF NOT EXISTS matches_p2 ON matches (p2_account, ended);
CREATE INDEX IF NOT EXISTS matches_created ON matches (created);
"""
PERMANENT = 32503680000.0     # 3000-01-01: "banned for ever"

SESSION_DAYS = 30.0
RECOVERY_CODES = 8
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"     # no 0/O, 1/I/L: read off a screen, typed back


def hash_password(password, n=1 << 14, r=8, p=1):
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, maxmem=256 << 20, dklen=32)
    b64 = lambda b: base64.b64encode(b).decode("ascii")  # noqa: E731
    return f"scrypt${n}${r}${p}${b64(salt)}${b64(dk)}"


def check_password(password, stored):
    try:
        algo, n, r, p, salt, dk = stored.split("$")
        if algo != "scrypt":
            return False
        want = base64.b64decode(dk)
        got = hashlib.scrypt(password.encode("utf-8"), salt=base64.b64decode(salt), n=int(n), r=int(r),
                             p=int(p), maxmem=256 << 20, dklen=len(want))
        return hmac.compare_digest(got, want)
    except (ValueError, TypeError):
        return False


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_code(code):
    """'abcd-efgh-jkmn' / 'ABCD EFGH JKMN' -> 'ABCDEFGHJKMN'."""
    return "".join(ch for ch in str(code).upper() if ch.isalnum())


def new_recovery_code():
    raw = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(12))      # ~59 bits
    return f"{raw[:4]}-{raw[4:8]}-{raw[8:]}"


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL" if path != ":memory:" else "PRAGMA journal_mode=MEMORY")
        self.db.execute("PRAGMA busy_timeout=5000")    # the admin tool may hold the write lock briefly
        self.db.executescript(SCHEMA)
        self._add_columns()
        self.db.executescript(RANKED_INDEXES)

    def _add_columns(self):
        for table, col, decl in RANKED_COLUMNS + MODERATION_COLUMNS:
            have = {r["name"] for r in self.db.execute(f"PRAGMA table_info({table})")}
            if col not in have:
                self.db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")

    def close(self):
        self.db.close()

    # ----------------------------------------------------------------- accounts
    def account(self, name):
        return self.db.execute("SELECT * FROM accounts WHERE name = ?", (name,)).fetchone()

    def account_by_id(self, aid):
        return self.db.execute("SELECT * FROM accounts WHERE id = ?", (aid,)).fetchone()

    def create_account(self, name, pw_hash):
        """-> row, or None when the name exists (any case)."""
        try:
            self.db.execute(
                "INSERT INTO accounts (name, pw, created, rating, rd, vol) VALUES (?, ?, ?, ?, ?, ?)",
                (name, pw_hash, time.time(), glicko.DEFAULT_R, glicko.DEFAULT_RD, glicko.DEFAULT_VOL))
        except sqlite3.IntegrityError:
            return None
        return self.account(name)

    def touch(self, aid):
        self.db.execute("UPDATE accounts SET last_seen = ? WHERE id = ?", (time.time(), aid))

    def set_password(self, aid, pw_hash):
        self.db.execute("UPDATE accounts SET pw = ?, pw_changed = ? WHERE id = ?", (pw_hash, time.time(), aid))

    def rating(self, aid):
        """Current Rating with inactivity RD growth applied."""
        row = self.account_by_id(aid)
        rt = glicko.Rating(row["rating"], row["rd"], row["vol"])
        if row["last_ranked"]:
            rt = glicko.inflate(rt, (time.time() - row["last_ranked"]) / 86400.0)
        return rt

    def rank_state(self, aid):
        row = self.account_by_id(aid)
        return RankState(row["tier"], row["ranked_games"], row["tier_since"], row["tier_peak"], row["tier_floor"])

    def set_rating(self, aid, rt, outcome, rank=None):
        col = {"win": "wins", "loss": "losses", "draw": "draws"}[outcome]
        self.db.execute(
            f"UPDATE accounts SET rating = ?, rd = ?, vol = ?, last_ranked = ?, games = games + 1, "
            f"ranked_games = ranked_games + 1, {col} = {col} + 1 WHERE id = ?",
            (rt.r, rt.rd, rt.vol, time.time(), aid))
        if rank is not None:
            self.db.execute("UPDATE accounts SET tier = ?, tier_since = ?, tier_peak = ?, tier_floor = ? WHERE id = ?",
                            (rank.tier, rank.since_change, rank.peak, rank.floor, aid))

    def add_unranked_game(self, aid, outcome):
        col = {"win": "wins", "loss": "losses", "draw": "draws"}[outcome]
        self.db.execute(f"UPDATE accounts SET games = games + 1, {col} = {col} + 1 WHERE id = ?", (aid,))

    def leaderboard(self, limit=20, offset=0):
        rows = [dict(r) for r in self.db.execute(
            "SELECT id, name, rating, rd, games, ranked_games, wins, losses, draws, tier, tier_peak FROM accounts "
            "WHERE ranked_games > 0 ORDER BY rating - 2 * rd DESC, rating DESC LIMIT ? OFFSET ?", (limit, offset))]
        for i, r in enumerate(rows):
            r["place"] = offset + i + 1
            r["main"] = self.main_char(r.pop("id"))
        return rows

    # ----------------------------------------------------------------- sessions ("remember me")
    def create_session(self, aid, days=SESSION_DAYS):
        """New login token for `aid`; only its hash is stored. -> the token (hex)."""
        token = secrets.token_hex(32)
        now = time.time()
        self.db.execute("INSERT INTO sessions (token_hash, account_id, created, last_used, expires) "
                        "VALUES (?, ?, ?, ?, ?)", (_sha(token), aid, now, now, now + days * 86400.0))
        return token

    def session_account(self, token, days=SESSION_DAYS):
        """Account row for a valid token (sliding expiry), else None."""
        if not isinstance(token, str) or len(token) != 64:
            return None
        h = _sha(token)
        row = self.db.execute("SELECT * FROM sessions WHERE token_hash = ?", (h,)).fetchone()
        now = time.time()
        if row is None:
            return None
        if row["expires"] < now:
            self.db.execute("DELETE FROM sessions WHERE token_hash = ?", (h,))
            return None
        self.db.execute("UPDATE sessions SET last_used = ?, expires = ? WHERE token_hash = ?",
                        (now, now + days * 86400.0, h))
        return self.account_by_id(row["account_id"])

    def revoke_session(self, token):
        if isinstance(token, str):
            self.db.execute("DELETE FROM sessions WHERE token_hash = ?", (_sha(token),))

    def revoke_sessions(self, aid, keep=None):
        """Log out every remembered login of `aid` (except the token `keep`)."""
        if keep:
            self.db.execute("DELETE FROM sessions WHERE account_id = ? AND token_hash != ?", (aid, _sha(keep)))
        else:
            self.db.execute("DELETE FROM sessions WHERE account_id = ?", (aid,))

    def session_count(self, aid):
        return self.db.execute("SELECT COUNT(*) FROM sessions WHERE account_id = ?", (aid,)).fetchone()[0]

    def prune_sessions(self):
        self.db.execute("DELETE FROM sessions WHERE expires < ?", (time.time(),))

    # ----------------------------------------------------------------- recovery codes
    def issue_recovery_codes(self, aid, n=RECOVERY_CODES):
        """A fresh set of one-time codes (the old set stops working). -> the codes, shown once."""
        codes = [new_recovery_code() for _ in range(n)]
        now = time.time()
        self.db.execute("DELETE FROM recovery WHERE account_id = ?", (aid,))
        self.db.executemany("INSERT INTO recovery (account_id, code_hash, created) VALUES (?, ?, ?)",
                            [(aid, _sha(normalize_code(c)), now) for c in codes])
        return codes

    def use_recovery_code(self, aid, code):
        """Consume one code of `aid`. -> True when it was valid and unused."""
        h = _sha(normalize_code(code))
        cur = self.db.execute("UPDATE recovery SET used = ? WHERE account_id = ? AND code_hash = ? AND used IS NULL",
                              (time.time(), aid, h))
        return cur.rowcount == 1

    def recovery_left(self, aid):
        return self.db.execute("SELECT COUNT(*) FROM recovery WHERE account_id = ? AND used IS NULL",
                               (aid,)).fetchone()[0]

    # ----------------------------------------------------------------- matches
    def save_match(self, m):
        self.db.execute(
            "INSERT OR REPLACE INTO matches (id, created, ended, ranked, p1_name, p2_name, p1_account, "
            "p2_account, build, path, rtt_ms, delay, status, winner, score, reports, rating, origin, started, "
            "duration, p1_char, p2_char, stage, reason, blame) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (m["id"], m["created"], m.get("ended"), int(m["ranked"]), m["p1_name"], m["p2_name"],
             m.get("p1_account"), m.get("p2_account"), m.get("build"), m.get("path"), m.get("rtt_ms"),
             m.get("delay"), m["status"], m.get("winner"), json.dumps(m.get("score")),
             json.dumps(m.get("reports")), json.dumps(m.get("rating")), m.get("origin"), m.get("started"),
             m.get("duration"), m.get("p1_char"), m.get("p2_char"), m.get("stage"), m.get("reason"),
             m.get("blame")))

    def match_row(self, mid):
        r = self.db.execute("SELECT * FROM matches WHERE id = ?", (mid,)).fetchone()
        return dict(r) if r else None

    def history(self, aid, limit=20, offset=0):
        """Finished matches of an account, newest first, from that player's side:
        {match, time, ranked, status, opponent, you_char, opp_char, stage, result: win|loss|draw|-,
         score [you, opp], delta, reason}."""
        out = []
        for r in self.db.execute(
                "SELECT * FROM matches WHERE (p1_account = ? OR p2_account = ?) AND status != 'playing' "
                "ORDER BY COALESCE(ended, created) DESC LIMIT ? OFFSET ?", (aid, aid, limit, offset)):
            r = dict(r)
            side = 0 if r["p1_account"] == aid else 1
            score = json.loads(r["score"]) if r["score"] else None
            rating = json.loads(r["rating"]) if r["rating"] else None
            counted = r["status"] in COUNTED
            if not counted:
                res = "-"
            elif r["winner"] is None:
                res = "draw"
            else:
                res = "win" if r["winner"] == side else "loss"
            out.append({
                "match": r["id"], "time": r["ended"] or r["created"], "ranked": bool(r["ranked"]),
                "status": r["status"], "reason": r["reason"],
                "opponent": r["p2_name"] if side == 0 else r["p1_name"],
                "you_char": r["p1_char"] if side == 0 else r["p2_char"],
                "opp_char": r["p2_char"] if side == 0 else r["p1_char"],
                "stage": r["stage"], "result": res,
                "score": (score if side == 0 else score[::-1]) if score else None,
                "delta": rating[side]["delta"] if rating else None,
                "path": r["path"], "rtt_ms": r["rtt_ms"], "delay": r["delay"]})
        return out

    def char_usage(self, aid, limit=5):
        """[{char, games, wins}] over counted matches, most played first."""
        rows = self.db.execute(
            "SELECT ch, COUNT(*) AS games, SUM(won) AS wins FROM ("
            "  SELECT p1_char AS ch, CASE WHEN winner = 0 THEN 1 ELSE 0 END AS won FROM matches "
            "   WHERE p1_account = ? AND p1_char IS NOT NULL AND status IN ('confirmed','onesided','forfeit','resolved')"
            "  UNION ALL "
            "  SELECT p2_char AS ch, CASE WHEN winner = 1 THEN 1 ELSE 0 END AS won FROM matches "
            "   WHERE p2_account = ? AND p2_char IS NOT NULL AND status IN ('confirmed','onesided','forfeit','resolved')"
            ") GROUP BY ch ORDER BY games DESC, wins DESC LIMIT ?", (aid, aid, limit))
        return [{"char": r["ch"], "games": r["games"], "wins": r["wins"] or 0} for r in rows]

    def main_char(self, aid):
        u = self.char_usage(aid, 1)
        return u[0]["char"] if u else None

    def strikes(self, aid, since):
        """Matches since `since` that ended without a result because of this account
        (crash, quit before the minimum length, no report)."""
        return self.db.execute(
            "SELECT COUNT(*) FROM matches WHERE ended >= ? AND status = 'void' AND "
            "((p1_account = ? AND blame = 0) OR (p2_account = ? AND blame = 1))", (since, aid, aid)).fetchone()[0]

    def disputes(self, aid, since):
        return self.db.execute(
            "SELECT COUNT(*) FROM matches WHERE ended >= ? AND status = 'disputed' AND (p1_account = ? OR p2_account = ?)",
            (since, aid, aid)).fetchone()[0]

    def pair_ranked(self, a, b, since):
        """Counted ranked matches between accounts a and b since `since` (anti win-trading cap)."""
        return self.db.execute(
            "SELECT COUNT(*) FROM matches WHERE ranked = 1 AND ended >= ? AND status IN "
            "('confirmed','onesided','forfeit','resolved') AND "
            "((p1_account = ? AND p2_account = ?) OR (p1_account = ? AND p2_account = ?))",
            (since, a, b, b, a)).fetchone()[0]

    def place(self, aid):
        """Leaderboard place of an account (1 = top), None when it has no ranked match."""
        row = self.account_by_id(aid)
        if row is None or not row["ranked_games"]:
            return None
        key = row["rating"] - 2 * row["rd"]
        return 1 + self.db.execute("SELECT COUNT(*) FROM accounts WHERE ranked_games > 0 AND rating - 2 * rd > ?",
                                   (key,)).fetchone()[0]

    # ----------------------------------------------------------------- moderation (admin tool + server)
    @staticmethod
    def ban_state(row, now=None):
        """(until, reason) when the account row is banned now, else None."""
        until = row["banned_until"] if "banned_until" in row.keys() else None
        if until and until > (now or time.time()):
            return until, row["ban_reason"] or ""
        return None

    def ban_account(self, name, until, reason=""):
        return self.db.execute("UPDATE accounts SET banned_until = ?, ban_reason = ? WHERE name = ?",
                               (until, reason, name)).rowcount > 0

    def unban_account(self, name):
        return self.db.execute("UPDATE accounts SET banned_until = NULL, ban_reason = NULL WHERE name = ?",
                               (name,)).rowcount > 0

    def banned_account_ids(self, now=None):
        return {r[0] for r in self.db.execute("SELECT id FROM accounts WHERE banned_until > ?",
                                               (now or time.time(),))}

    def ban_ip(self, net, until, reason=""):
        self.db.execute("INSERT OR REPLACE INTO ip_bans (net, until, reason, created) VALUES (?, ?, ?, ?)",
                        (net, until, reason, time.time()))

    def unban_ip(self, net):
        return self.db.execute("DELETE FROM ip_bans WHERE net = ?", (net,)).rowcount > 0

    def ip_bans(self, now=None):
        return [dict(r) for r in self.db.execute("SELECT * FROM ip_bans WHERE until > ? ORDER BY created",
                                                  (now or time.time(),))]

    def reset_rating(self, name):
        """Back to 1500 / RD 350 and unranked (placement again); the win/loss record stays."""
        return self.db.execute(
            "UPDATE accounts SET rating = ?, rd = ?, vol = ?, last_ranked = NULL, ranked_games = 0, tier = 0, "
            "tier_since = 0, tier_peak = 0, tier_floor = 0 WHERE name = ?",
            (glicko.DEFAULT_R, glicko.DEFAULT_RD, glicko.DEFAULT_VOL, name)).rowcount > 0

    def delete_account(self, name):
        row = self.account(name)
        if row is None:
            return False
        self.db.execute("DELETE FROM accounts WHERE id = ?", (row["id"],))
        self._drop_orphans()
        return True

    def _drop_orphans(self):
        """Remembered logins and recovery codes of accounts that no longer exist."""
        for table in ("sessions", "recovery"):
            self.db.execute(f"DELETE FROM {table} WHERE account_id NOT IN (SELECT id FROM accounts)")

    def list_accounts(self, pattern=None, limit=50, banned_only=False):
        sql, args = "SELECT * FROM accounts WHERE 1 = 1", []
        if pattern:
            esc = pattern.replace("!", "!!").replace("%", "!%").replace("_", "!_")
            sql += " AND name LIKE ? ESCAPE '!'"
            args.append(f"%{esc}%")
        if banned_only:
            sql += " AND banned_until > ?"
            args.append(time.time())
        sql += " ORDER BY COALESCE(last_seen, created) DESC LIMIT ?"
        args.append(limit)
        return [dict(r) for r in self.db.execute(sql, args)]

    def recent_matches(self, limit=20, name=None):
        sql, args = "SELECT * FROM matches", []
        if name:
            sql += " WHERE p1_name = ? COLLATE NOCASE OR p2_name = ? COLLATE NOCASE"
            args += [name, name]
        sql += " ORDER BY created DESC LIMIT ?"
        args.append(limit)
        return [dict(r) for r in self.db.execute(sql, args)]

    def purge_guest_matches(self, older_than_days):
        """Match records in which no account took part (guests only), older than the given age."""
        cut = time.time() - older_than_days * 86400.0
        return self.db.execute("DELETE FROM matches WHERE p1_account IS NULL AND p2_account IS NULL "
                               "AND created < ?", (cut,)).rowcount

    def purge_inactive_accounts(self, days, include_played=False):
        """Accounts not seen for `days` (by default only those that never finished a game)."""
        cut = time.time() - days * 86400.0
        sql = "DELETE FROM accounts WHERE COALESCE(last_seen, created) < ? AND (banned_until IS NULL OR banned_until < ?)"
        if not include_played:
            sql += " AND games = 0"
        n = self.db.execute(sql, (cut, time.time())).rowcount
        self._drop_orphans()
        return n

    def stats(self, now=None):
        """Numbers for the status page: accounts and the last 24 hours of matches."""
        now = now or time.time()
        day = now - 86400.0
        one = lambda sql, *a: self.db.execute(sql, a).fetchone()[0]   # noqa: E731
        by_status = {r[0]: r[1] for r in self.db.execute(
            "SELECT status, COUNT(*) FROM matches WHERE created >= ? GROUP BY status", (day,))}
        by_path = {r[0] or "none": r[1] for r in self.db.execute(
            "SELECT path, COUNT(*) FROM matches WHERE created >= ? GROUP BY path", (day,))}
        return {
            "accounts": one("SELECT COUNT(*) FROM accounts"),
            "accounts_seen_24h": one("SELECT COUNT(*) FROM accounts WHERE last_seen >= ?", day),
            "accounts_seen_7d": one("SELECT COUNT(*) FROM accounts WHERE last_seen >= ?", now - 7 * 86400.0),
            "accounts_banned": one("SELECT COUNT(*) FROM accounts WHERE banned_until > ?", now),
            "ip_bans": one("SELECT COUNT(*) FROM ip_bans WHERE until > ?", now),
            "matches_24h": sum(by_status.values()),
            "matches_24h_by_status": by_status,
            "matches_24h_by_path": by_path,
            "matches_total": one("SELECT COUNT(*) FROM matches"),
        }


# Statuses whose result counts (record, rating when ranked).
COUNTED = ("confirmed", "onesided", "forfeit", "resolved")
