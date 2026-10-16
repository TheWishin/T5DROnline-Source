"""Persistent state: accounts (salted scrypt password hashes, ratings) and match history.
SQLite from the standard library; one connection used from the event loop thread."""
import base64
import hashlib
import hmac
import json
import os
import sqlite3
import time

from .. import rating as glicko

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
"""


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


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL" if path != ":memory:" else "PRAGMA journal_mode=MEMORY")
        self.db.executescript(SCHEMA)

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

    def rating(self, aid):
        """Current Rating with inactivity RD growth applied."""
        row = self.account_by_id(aid)
        rt = glicko.Rating(row["rating"], row["rd"], row["vol"])
        if row["last_ranked"]:
            rt = glicko.inflate(rt, (time.time() - row["last_ranked"]) / 86400.0)
        return rt

    def set_rating(self, aid, rt, outcome):
        col = {"win": "wins", "loss": "losses", "draw": "draws"}[outcome]
        self.db.execute(
            f"UPDATE accounts SET rating = ?, rd = ?, vol = ?, last_ranked = ?, games = games + 1, "
            f"{col} = {col} + 1 WHERE id = ?", (rt.r, rt.rd, rt.vol, time.time(), aid))

    def add_unranked_game(self, aid, outcome):
        col = {"win": "wins", "loss": "losses", "draw": "draws"}[outcome]
        self.db.execute(f"UPDATE accounts SET games = games + 1, {col} = {col} + 1 WHERE id = ?", (aid,))

    def leaderboard(self, limit=20):
        return [dict(r) for r in self.db.execute(
            "SELECT name, rating, rd, games, wins, losses, draws FROM accounts WHERE games > 0 "
            "ORDER BY rating - 2 * rd DESC LIMIT ?", (limit,))]

    # ----------------------------------------------------------------- matches
    def save_match(self, m):
        self.db.execute(
            "INSERT OR REPLACE INTO matches (id, created, ended, ranked, p1_name, p2_name, p1_account, "
            "p2_account, build, path, rtt_ms, delay, status, winner, score, reports, rating) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (m["id"], m["created"], m.get("ended"), int(m["ranked"]), m["p1_name"], m["p2_name"],
             m.get("p1_account"), m.get("p2_account"), m.get("build"), m.get("path"), m.get("rtt_ms"),
             m.get("delay"), m["status"], m.get("winner"), json.dumps(m.get("score")),
             json.dumps(m.get("reports")), json.dumps(m.get("rating"))))

    def match_row(self, mid):
        r = self.db.execute("SELECT * FROM matches WHERE id = ?", (mid,)).fetchone()
        return dict(r) if r else None
