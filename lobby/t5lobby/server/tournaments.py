"""Community tournaments in the lobby (docs/TOURNAMENTS.md).

An organizer (an account; T5L_TOUR_ORGANIZERS can narrow that) creates a tournament: name, single or double
elimination, sets of first to 2 or 3 games, a start time, a player limit (8/16/32/64) and an optional check-in
window. Players (accounts, with a launcher that announced the "tournaments" cap) sign up and, when there is a
check-in window, check in. At the start time the server seeds them (randomly or by rating), builds the bracket
(bracket.py) and calls every set whose two players are known: both get `tour_call` ("Your tournament set is
ready") and accept it within T5L_TOUR_NOSHOW seconds. Whoever has not accepted by then is a no-show: the set is
lost and that player is disqualified.

A set runs as a TourSet: the lobby's best-of set machinery (lobby.py "ranked sets": the next game starts by
itself after a countdown, results come from the games with every integrity rule -- quits, disconnects, desync
replays, voids) with three differences: it is not rated (unless T5L_TOUR_RATED), the players pick their fighters
in the game before every game (no character lock), and leaving it or quitting it is losing it even at 0-0. When
it ends, its result goes into the bracket and the next sets are called. A set that ends without a result
(crash, broken connection, too many replays) is called again with its score so far, at most T5L_TOUR_RETRIES
times; then -- and at once for a dispute -- it waits for the organizer.

The organizer (or an account in T5L_TOUR_ADMINS) can start early, cancel, report a set's result, override a
decided one, reset a set (play it again from 0-0), and disqualify a player.

Everything is kept in the database (own tables, own schema version: MIGRATIONS below). A restart resumes the
tournaments: a set that was being played is called again with the score it had (from the `sets` row of its
TourSet), a called set gets a fresh no-show time.

Messages (clients with the "tournaments" cap; older clients never get any of them):

    tour_list                                -> tour_list {rows, can_create}
    tour_get {tournament}                    -> tour {tournament}           (with the bracket)
    tour_create {name, format, set_wins, start, max_players, checkin_minutes, seeding}   -> tour {tournament}
    tour_join / tour_leave / tour_checkin {tournament}                      -> tour {tournament}
    tour_accept {tournament, set}            -> tour_call {...}             (accept a called set)
    tour_admin {tournament, op: start|cancel|report|override|reset|dq, set, winner, score, player} -> tour {...}
    pushed: tour_call, tour_call_end {tournament, set, reason}, tour_changed {id, rev, state},
            tour_notice {code, tournament, ...}

The status port serves the brackets read-only for streamers: GET /tournaments and /tournaments/<id> (JSON).
"""
import json
import logging
import math
import random
import time

from .. import proto
from ..proto import LobbyError
from .bracket import EMPTY, FORMATS, NOT_PLAYED, Bracket, BSet
from .lobby import GameSet
from .ratelimit import TokenBucket

log = logging.getLogger("t5lobby.tour")

DAY = 86400.0
OPEN_STATES = ("signup", "checkin", "running")
MAX_PLAYERS = (8, 16, 32, 64)
SET_WINS = (2, 3)
CHECKIN_MINUTES = (0, 5, 10, 15, 30, 60)
SEEDING = ("random", "rating")
ADMIN_OPS = ("start", "cancel", "report", "override", "reset", "dq")
# rate-limit buckets of the lobby (lobby.py dispatch): reading the list, and changes (a bracket, tour_get, is built
# once per change and second and costs a lookup after that: TourManager.full)
HEAVY = frozenset(("tour_list",))
STATE = frozenset(("tour_create", "tour_join", "tour_leave", "tour_checkin", "tour_accept", "tour_admin"))
CAP = "tournaments"

# The tournament tables have their own schema version (kv key below), so that they never collide with other
# numbered migrations: each step runs once, in order, in one transaction with its version number.
SCHEMA_KEY = "schema.tournaments"
MIGRATIONS = [
    (1, "tournaments, entrants, bracket sets", """
CREATE TABLE IF NOT EXISTS tournaments (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    organizer_id INTEGER, organizer_name TEXT,
    build TEXT,                         -- the game build it is played with (the organizer's)
    format TEXT NOT NULL,               -- single | double
    set_wins INTEGER NOT NULL,          -- games to win a set (2: best of 3, 3: best of 5)
    max_players INTEGER NOT NULL,
    start_time REAL NOT NULL,           -- unix time
    checkin_minutes INTEGER NOT NULL DEFAULT 0,
    seeding TEXT NOT NULL,              -- random | rating
    rated INTEGER NOT NULL DEFAULT 0,
    state TEXT NOT NULL,                -- signup | checkin | running | finished | cancelled
    created REAL NOT NULL, started REAL, ended REAL,
    seed INTEGER NOT NULL,              -- the random seeding's (and tie breaks') seed
    champion TEXT, reason TEXT,
    bracket TEXT,                       -- JSON {format, entrants (account ids, seed order), dq}
    rev INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS tournaments_state ON tournaments (state, start_time);
CREATE TABLE IF NOT EXISTS tour_entrants (
    tournament_id TEXT NOT NULL,
    account_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    signed_up REAL NOT NULL,
    checked_in REAL,
    seed INTEGER,                       -- NULL: not in the bracket
    rating REAL,                        -- at the start (seeding by rating)
    dq TEXT,                            -- why disqualified: no_show | organizer | withdrew
    place INTEGER,
    PRIMARY KEY (tournament_id, account_id)
);
CREATE TABLE IF NOT EXISTS tour_sets (
    tournament_id TEXT NOT NULL,
    set_id TEXT NOT NULL,               -- W1-1, L2-3, GF1, GF2
    ord INTEGER NOT NULL,               -- creation order = the order sets depend on each other
    bracket TEXT NOT NULL, round INTEGER NOT NULL, idx INTEGER NOT NULL,
    src TEXT NOT NULL, p TEXT NOT NULL, known TEXT NOT NULL,      -- JSON
    state TEXT NOT NULL,                -- pending | open | done
    winner INTEGER, score TEXT, reason TEXT,
    data TEXT,                          -- JSON: live (called | playing | attention), games, carry, ...
    updated REAL,
    PRIMARY KEY (tournament_id, set_id)
);
"""),
]


def migrate(db):
    """Run the MIGRATIONS this database has not had yet (sqlite3 connection, not in a transaction). -> versions
    applied."""
    db.execute("CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT, updated REAL)")
    r = db.execute("SELECT value FROM kv WHERE key = ?", (SCHEMA_KEY,)).fetchone()
    have = int(r[0]) if r and str(r[0]).isdigit() else 0
    done = []
    newest = MIGRATIONS[-1][0]
    if have > newest:
        log.warning("tournament schema %d is newer than this server's (%d): using it as it is", have, newest)
        return done
    for version, what, sql in MIGRATIONS:
        if version <= have:
            continue
        try:
            db.executescript(f"BEGIN IMMEDIATE;\n{sql}\nINSERT OR REPLACE INTO kv (key, value, updated) VALUES "
                             f"('{SCHEMA_KEY}', '{int(version)}', {time.time()!r});\nCOMMIT;")
        except Exception:
            if db.in_transaction:
                db.execute("ROLLBACK")
            log.error("tournament schema step %d (%s) failed", version, what)
            raise
        log.info("database: tournament schema %d (%s)", version, what)
        done.append(version)
    return done


def _rid():
    import os
    return "t" + os.urandom(5).hex()


class Entrant:
    __slots__ = ("aid", "name", "signed_up", "checked_in", "seed", "rating", "dq", "place")

    def __init__(self, aid, name, signed_up, checked_in=None, seed=None, rating=None, dq=None, place=None):
        self.aid, self.name, self.signed_up, self.checked_in = aid, name, signed_up, checked_in
        self.seed, self.rating, self.dq, self.place = seed, rating, dq, place


class Tournament:
    def __init__(self, **kw):
        self.id = kw["id"]
        self.name = kw["name"]
        self.organizer_id = kw.get("organizer_id")
        self.organizer_name = kw.get("organizer_name") or ""
        self.build = kw.get("build")
        self.format = kw["format"]
        self.set_wins = int(kw["set_wins"])
        self.max_players = int(kw["max_players"])
        self.start_time = float(kw["start_time"])
        self.checkin_minutes = int(kw.get("checkin_minutes") or 0)
        self.seeding = kw.get("seeding") or "random"
        self.rated = bool(kw.get("rated"))
        self.state = kw.get("state") or "signup"
        self.created = float(kw.get("created") or time.time())
        self.started = kw.get("started")
        self.ended = kw.get("ended")
        self.seed = int(kw.get("seed") or random.getrandbits(31))
        self.champion = kw.get("champion")
        self.reason = kw.get("reason")
        self.rev = int(kw.get("rev") or 0)
        self.entrants = {}              # account id -> Entrant, in sign-up order
        self.bracket = None             # Bracket (account ids) once running

    @property
    def best_of(self):
        return 2 * self.set_wins - 1

    def checkin_opens(self):
        return self.start_time - self.checkin_minutes * 60.0 if self.checkin_minutes else None

    def name_of(self, aid):
        e = self.entrants.get(aid)
        return e.name if e is not None else None


class TourSet(GameSet):
    """A tournament set (see the module doc): the lobby's best-of set with the tournament's rules."""

    def __init__(self, a, b, ranked, wins_needed, tour, bset, carry=(0, 0)):
        super().__init__(a, b, True, wins_needed)       # (the best-of machinery: lobby.GameSet "rated")
        self.ranked = bool(ranked)                      # T5L_TOUR_RATED: the rating changes once, at the end
        self.locked = False                             # the fighters are picked in the game before every game
        self.forfeit_at_zero = True                     # leaving / quitting loses the set even at 0-0
        self.tour = tour
        self.bset_id = bset.id
        self.detached = False                           # the organizer decided the set: its end changes nothing
        self.wins = {a.id: int(carry[0]), b.id: int(carry[1])}
        self.number = int(carry[0]) + int(carry[1]) + 1
        self.label = {"id": tour.id, "name": tour.name, "set": bset.id, "bracket": bset.bracket, "round": bset.round,
                      "format": tour.format, "rounds": tour.bracket.k if tour.bracket else 1,
                      "losers_rounds": tour.bracket.losers_rounds if tour.bracket else 0}

    def info(self):
        d = super().info()
        d["tournament"] = dict(self.label)
        return d

    def view(self, p):
        d = super().view(p)
        d["tournament"] = dict(self.label)
        return d


class TourManager:
    def __init__(self, srv):
        self.srv = srv
        self.cfg = srv.cfg
        self.store = srv.store
        self.migrated = migrate(self.store.db)
        self.tours = {}                 # id -> Tournament (open ones, and finished ones still listed)
        self.live = {}                  # TourSet id -> TourSet (sets being played)
        self.dirty = set()              # tournament ids whose change is not announced yet (tour_changed)
        self.http_cache = {}
        self.view_cache = {}            # tournament id -> (rev, time, the part of full() every viewer gets)
        self.created_from = {}          # tournament id -> address key it was created from (memory only: the limit per
                                        # internet address; never written to the database)
        self.drain_since = None         # `admin drain` on since (time.time()): the no-show clocks stand still
        self._task = None
        self.handlers = {"tour_list": self.h_list, "tour_get": self.h_get, "tour_create": self.h_create,
                         "tour_join": self.h_join, "tour_leave": self.h_leave, "tour_checkin": self.h_checkin,
                         "tour_accept": self.h_accept, "tour_admin": self.h_admin}

    # ================================================================== lifecycle
    async def start(self):
        import asyncio
        self.load()
        self._task = asyncio.ensure_future(self._tick_loop())

    async def stop(self):
        import asyncio
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None

    def handler(self, t):
        return self.handlers.get(t)

    def welcome(self):
        return {"noshow": self.cfg.tour_noshow, "organizers": self._organizer_rule()[0]}

    def _now(self):
        return time.time()

    # ================================================================== persistence
    def load(self):
        """Tournaments from the database (at start): the open ones resume, recent finished ones are listed."""
        now = self._now()
        cut = now - self.cfg.tour_keep_days * DAY
        rows = self.store._x("SELECT * FROM tournaments WHERE state IN ('signup', 'checkin', 'running') OR "
                             "COALESCE(ended, created) >= ? ORDER BY created", (cut,)).fetchall()
        for r in rows:
            t = Tournament(**dict(r))
            for e in self.store._x("SELECT * FROM tour_entrants WHERE tournament_id = ? ORDER BY signed_up",
                                   (t.id,)):
                t.entrants[e["account_id"]] = Entrant(e["account_id"], e["name"], e["signed_up"], e["checked_in"],
                                                      e["seed"], e["rating"], e["dq"], e["place"])
            meta = json.loads(r["bracket"]) if r["bracket"] else None
            if meta:
                b = Bracket(meta["format"], list(meta["entrants"]))
                b.dq = set(meta.get("dq") or ())
                for sr in self.store._x("SELECT * FROM tour_sets WHERE tournament_id = ? ORDER BY ord", (t.id,)):
                    s = BSet.from_dict({"id": sr["set_id"], "bracket": sr["bracket"], "round": sr["round"],
                                        "index": sr["idx"], "src": json.loads(sr["src"]), "p": json.loads(sr["p"]),
                                        "known": json.loads(sr["known"]), "state": sr["state"], "winner": sr["winner"],
                                        "score": json.loads(sr["score"]) if sr["score"] else None,
                                        "reason": sr["reason"], "data": json.loads(sr["data"]) if sr["data"] else {}})
                    b.sets[s.id] = s
                t.bracket = b
            self.tours[t.id] = t
            if t.state == "running" and t.bracket is not None:
                self._resume(t, now)
        if rows:
            log.info("tournaments: %d loaded (%d running)", len(rows),
                     sum(1 for t in self.tours.values() if t.state == "running"))

    def _resume(self, t, now):
        """After a restart: a set that was being played (its TourSet lived in the last server process) is called
        again with the score it had; a called set gets a fresh no-show time."""
        for s in t.bracket.sets.values():
            d = s.data
            live = d.get("live")
            if s.state != "open" or live == "attention":
                continue                        # (an open set nobody called yet -- a drain -- is called now too)
            if live == "playing":
                row = self.store.set_row(d["lobby_set"]) if d.get("lobby_set") else None
                if row and isinstance(row.get("score"), list) and len(row["score"]) == 2:
                    d["carry"] = [int(x) for x in row["score"]]
                d["games"] = list(d.get("games") or []) + [g for g in (row or {}).get("games") or []
                                                            if g.get("match") not in
                                                            {x.get("match") for x in d.get("games") or []}]
                d["restarts"] = int(d.get("restarts") or 0) + 1
                d.pop("lobby_set", None)
            self._call(t, s, now, quiet=True)
        self._save(t)

    def _save(self, t, entrants=None):
        """The tournament row, the given entrants (all when None) and the bracket sets that changed: one
        transaction with whatever else the lobby writes in this callback (store.defer_commits)."""
        t.rev += 1
        meta = None
        if t.bracket is not None:
            meta = json.dumps({"format": t.bracket.format, "entrants": t.bracket.entrants,
                               "dq": sorted(t.bracket.dq, key=str)})
        x = self.store._x
        x("INSERT OR REPLACE INTO tournaments (id, name, organizer_id, organizer_name, build, format, set_wins, "
          "max_players, start_time, checkin_minutes, seeding, rated, state, created, started, ended, seed, champion, "
          "reason, bracket, rev) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
          (t.id, t.name, t.organizer_id, t.organizer_name, t.build, t.format, t.set_wins, t.max_players, t.start_time,
           t.checkin_minutes, t.seeding, int(t.rated), t.state, t.created, t.started, t.ended, t.seed, t.champion,
           t.reason, meta, t.rev))
        for e in (t.entrants.values() if entrants is None else entrants):
            x("INSERT OR REPLACE INTO tour_entrants (tournament_id, account_id, name, signed_up, checked_in, seed, "
              "rating, dq, place) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
              (t.id, e.aid, e.name, e.signed_up, e.checked_in, e.seed, e.rating, e.dq, e.place))
        if t.bracket is not None and t.bracket.dirty:
            order = {sid: i for i, sid in enumerate(t.bracket.sets)}
            for sid in sorted(t.bracket.dirty, key=lambda k: order.get(k, 0)):
                s = t.bracket.sets[sid]
                x("INSERT OR REPLACE INTO tour_sets (tournament_id, set_id, ord, bracket, round, idx, src, p, known, "
                  "state, winner, score, reason, data, updated) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                  (t.id, s.id, order[sid], s.bracket, s.round, s.index, json.dumps(s.src), json.dumps(s.p),
                   json.dumps(s.known), s.state, s.winner, json.dumps(s.score) if s.score is not None else None,
                   s.reason, json.dumps(s.data), self._now()))
            t.bracket.dirty.clear()
        self.dirty.add(t.id)
        self.http_cache.pop(t.id, None)
        self.http_cache.pop(None, None)

    def _drop_entrant_row(self, t, aid):
        self.store._x("DELETE FROM tour_entrants WHERE tournament_id = ? AND account_id = ?", (t.id, aid))

    # ================================================================== who may do what
    def _organizer_rule(self):
        """-> ("any" | "none" | "list", {lower names})."""
        raw = str(self.cfg.tour_organizers or "any").strip().lower()
        if raw in ("", "any", "all", "1", "yes"):
            return "any", set()
        if raw in ("none", "0", "no", "off"):
            return "none", set()
        return "list", {x.strip() for x in raw.split(",") if x.strip()}

    def _is_admin(self, p):
        return p.account_id is not None and p.name.lower() in {str(x).lower() for x in self.cfg.tour_admins}

    def may_organize(self, p):
        if p.account_id is None:
            return False
        if self._is_admin(p):
            return True
        rule, names = self._organizer_rule()
        return rule == "any" or (rule == "list" and p.name.lower() in names)

    def _manages(self, p, t):
        return p.account_id is not None and (p.account_id == t.organizer_id or self._is_admin(p))

    @staticmethod
    def _need_account(p):
        if p.account_id is None:
            raise LobbyError(proto.E_NOT_ALLOWED, "tournaments need an account")

    def _get(self, msg):
        t = self.tours.get(str(msg.get("tournament") or ""))
        if t is None:
            raise LobbyError(proto.E_NOT_FOUND, "no such tournament")
        return t

    def _player(self, aid, name):
        """The lobby's Player of an entrant (online, or dropped and resumable), or None."""
        p = self.srv.by_name.get(str(name).lower())
        return p if p is not None and p.account_id == aid else None

    def _send(self, aid, name, msg):
        p = self._player(aid, name)
        if p is not None and p.conn is not None and CAP in p.conn.caps:
            p.send(msg)

    def _notice(self, t, aid, code, **kw):
        self._send(aid, t.name_of(aid) or "", dict(kw, t="tour_notice", code=code, tournament={"id": t.id,
                                                                                               "name": t.name}))

    def _notice_organizer(self, t, code, **kw):
        if t.organizer_id is not None:
            self._send(t.organizer_id, t.organizer_name, dict(kw, t="tour_notice", code=code,
                                                              tournament={"id": t.id, "name": t.name}))

    # ================================================================== views
    def summary(self, t, viewer=None):
        d = {"id": t.id, "name": t.name, "organizer": t.organizer_name, "format": t.format, "set_wins": t.set_wins,
             "best_of": t.best_of, "start": t.start_time, "checkin_minutes": t.checkin_minutes,
             "checkin_opens": t.checkin_opens(), "max_players": t.max_players, "seeding": t.seeding,
             "rated": t.rated, "state": t.state, "players": len(t.entrants),
             "checked_in": sum(1 for e in t.entrants.values() if e.checked_in),
             "created": t.created, "started": t.started, "ended": t.ended, "champion": t.champion,
             "reason": t.reason, "rev": t.rev, "starts_in": max(0.0, round(t.start_time - self._now(), 1))}
        if viewer is not None:
            e = t.entrants.get(viewer.account_id) if viewer.account_id is not None else None
            you = {"entrant": e is not None, "build_ok": viewer.build_id == t.build}
            if e is not None:
                you.update(checked_in=bool(e.checked_in), seed=e.seed, dq=e.dq, place=e.place)
                s = t.bracket.set_of(e.aid) if t.bracket is not None and not e.dq else None
                you["set"] = s.id if s is not None else None
            d["you"] = you
            d["can_manage"] = self._manages(viewer, t)
        return d

    def full(self, t, viewer=None):
        """The tournament with its entrants, bracket and standings (tour_get, the status port). The bracket part is
        the same for every viewer: built once per change (and at most once a second while sets run), then reused."""
        now = self._now()
        hit = self.view_cache.get(t.id)
        if hit is None or hit[0] != t.rev or now - hit[1] >= 1.0:
            hit = self.view_cache[t.id] = (t.rev, now, self._shared_view(t, now))
        d = dict(hit[2])
        d.update(self.summary(t, viewer))
        return d

    def _shared_view(self, t, now):
        d = {}
        ents = sorted(t.entrants.values(), key=lambda e: (e.seed is None, e.seed or 0, e.signed_up))
        d["entrants"] = [{"name": e.name, "seed": e.seed, "checked_in": bool(e.checked_in), "dq": e.dq,
                          "place": e.place} for e in ents]
        b = t.bracket
        if b is not None:
            sets = []
            for s in b.sets.values():
                dd = s.data
                row = {"id": s.id, "bracket": s.bracket, "round": s.round, "index": s.index,
                       "p": [t.name_of(x) if x is not EMPTY else None for x in s.p], "known": list(s.known),
                       "seeds": [t.entrants[x].seed if x is not EMPTY and x in t.entrants else None for x in s.p],
                       "state": s.state, "live": dd.get("live"), "winner": s.winner, "score": s.score,
                       "reason": s.reason, "carry": dd.get("carry"),
                       "games": [{"winner": g.get("winner"), "score": g.get("score"), "status": g.get("status")}
                                 for g in dd.get("games") or []]}
                if dd.get("live") == "called":
                    row["accepted"] = list(dd.get("accepted") or [False, False])
                    row["deadline_in"] = max(0.0, round(float(dd.get("deadline") or now) - now, 1))
                if dd.get("live") == "attention":
                    row["why"] = dd.get("why")
                lg = self.live.get(dd.get("lobby_set")) if dd.get("live") == "playing" else None
                if lg is not None:
                    row["wins"] = lg.score()
                    row["game"] = lg.number
                    # spectating (docs/SPECTATE.md "Tournaments"): its game can be watched right now -- being played,
                    # both players allow spectators, room for one more (who may: may_watch; the server checks again)
                    watchable = getattr(self.srv, "_spec_watchable", None)
                    row["watch"] = bool(watchable is not None and lg.current is not None and watchable(lg.current))
                sets.append(row)
            d["bracket"] = {"format": b.format, "size": b.size, "rounds": b.k, "losers_rounds": b.losers_rounds,
                            "sets": sets}
            d["standings"] = [{"name": t.name_of(aid), "place": place} for aid, place in b.standings()]
        return d

    def status(self):
        by = {}
        for t in self.tours.values():
            by[t.state] = by.get(t.state, 0) + 1
        return {"by_state": by, "sets_playing": len(self.live)}

    # ---------------------------------------------------------------- the status port (streamers)
    def http(self, path):
        """GET /tournaments (the list) and /tournaments/<id> (one bracket): -> (code, JSON text). Names only: no
        account ids, no addresses."""
        parts = [p for p in path.split("/") if p]
        if len(parts) == 1:
            key = None
        elif len(parts) == 2:
            key = parts[1]
        else:
            return 404, json.dumps({"error": "not found"}) + "\n"
        hit = self.http_cache.get(key)
        now = self._now()
        if hit is not None and now - hit[0] < 1.0:
            return 200, hit[1]
        if key is None:
            body = {"tournaments": [self.summary(t) for t in self._listed()], "time": round(now)}
        else:
            t = self.tours.get(key)
            if t is None:
                return 404, json.dumps({"error": "no such tournament"}) + "\n"
            body = dict(self.full(t), time=round(now))
        text = json.dumps(body, indent=1) + "\n"
        self.http_cache[key] = (now, text)
        return 200, text

    def _listed(self):
        order = {"running": 0, "checkin": 1, "signup": 2, "finished": 3, "cancelled": 4}
        return sorted(self.tours.values(), key=lambda t: (order.get(t.state, 9),
                                                          t.start_time if t.state in OPEN_STATES else -(t.ended or 0)))

    # ================================================================== requests
    async def h_list(self, conn, msg):
        p = conn.player
        return {"t": "tour_list", "rows": [self.summary(t, p) for t in self._listed()][:60],
                "can_create": self.may_organize(p), "rated": self.cfg.tour_rated}

    async def h_get(self, conn, msg):
        # (security review 2) a whole bracket is ~60 KB of JSON at 64 players: without a limit of its own one connection
        # could ask for it 20 times a second (the launcher asks at most once a second)
        b = getattr(conn, "tour_reads", None)
        if b is None:
            b = conn.tour_reads = TokenBucket(self.cfg.tour_get_rate, self.cfg.tour_get_burst)
        if not b.take():
            raise LobbyError(proto.E_RATE, "slow down")
        return {"t": "tour", "tournament": self.full(self._get(msg), conn.player)}

    async def h_create(self, conn, msg):
        p = conn.player
        self._need_account(p)
        if not self.may_organize(p):
            raise LobbyError(proto.E_NOT_ALLOWED, "only the server's organizers can create tournaments here")
        name = proto.clean_text(msg.get("name") or "", 40).strip()
        if len(name) < 3:
            raise LobbyError(proto.E_BAD_REQUEST, "a tournament name is 3-40 characters")
        admin = self._is_admin(p)
        if not admin and (proto.reserved_name(name) or self.srv.name_blocked(name)):
            # (security review 2) "Official ...", "Admin cup", the server's blocklist: only T5L_TOUR_ADMINS
            raise LobbyError(proto.E_BAD_NAME, "that tournament name is not allowed here")
        fmt = msg.get("format")
        if fmt not in FORMATS:
            raise LobbyError(proto.E_BAD_REQUEST, "the format is single or double elimination")
        try:
            set_wins = int(msg.get("set_wins", 2))
            max_players = int(msg.get("max_players", 16))
            checkin = int(msg.get("checkin_minutes", 0) or 0)
            start = float(msg["start"])
        except (KeyError, TypeError, ValueError):
            raise LobbyError(proto.E_BAD_REQUEST, "set length, player limit, check-in and start time are numbers")
        if not math.isfinite(start):
            # (security review 2) NaN passed both checks below; SQLite stores it as NULL, so the row could never be
            # saved: a tournament that never started, could not be cancelled for good and held a slot until a restart
            raise LobbyError(proto.E_BAD_REQUEST, "set length, player limit, check-in and start time are numbers")
        if set_wins not in SET_WINS:
            raise LobbyError(proto.E_BAD_REQUEST, "a set is first to 2 or first to 3 games")
        if max_players not in MAX_PLAYERS:
            raise LobbyError(proto.E_BAD_REQUEST, "the player limit is 8, 16, 32 or 64")
        if checkin not in CHECKIN_MINUTES:
            raise LobbyError(proto.E_BAD_REQUEST, "the check-in window is 0, 5, 10, 15, 30 or 60 minutes")
        seeding = msg.get("seeding", "random")
        if seeding not in SEEDING:
            raise LobbyError(proto.E_BAD_REQUEST, "seeding is random or by rating")
        now = self._now()
        if start < now - 120:
            raise LobbyError(proto.E_BAD_REQUEST, "that start time has passed")
        if start > now + self.cfg.tour_max_days * DAY:
            raise LobbyError(proto.E_BAD_REQUEST, f"a tournament starts within {self.cfg.tour_max_days:g} days")
        start = max(start, now)
        open_ = [t for t in self.tours.values() if t.state in OPEN_STATES]
        # (security review 2) T5L_TOUR_ADMINS are not held back by the server-wide limit: a few throw-away accounts
        # (T5L_TOUR_ORGANIZERS=any) could fill it with tournaments 14 days ahead and block every real organizer
        if len(open_) >= self.cfg.tour_max_open and not admin:
            raise LobbyError(proto.E_BUSY, "this server has as many tournaments as it takes; try again later")
        mine = sum(1 for t in open_ if t.organizer_id == p.account_id)
        if mine >= self.cfg.tour_per_organizer and not admin:
            raise LobbyError(proto.E_BUSY, f"you already run {mine} tournaments; finish or cancel one first")
        akey = getattr(conn, "akey", None)
        if akey is not None and not admin and \
                sum(1 for t in open_ if self.created_from.get(t.id) == akey) >= self.cfg.tour_per_organizer:
            # ... and T5L_TOUR_PER_ORGANIZER counts per internet address too, all its accounts together
            raise LobbyError(proto.E_BUSY, "this internet address runs as many tournaments as one organizer may; "
                                           "finish or cancel one first")
        t = Tournament(id=_rid(), name=name, organizer_id=p.account_id, organizer_name=p.name, build=p.build_id,
                       format=fmt, set_wins=set_wins, max_players=max_players, start_time=start,
                       checkin_minutes=checkin, seeding=seeding, rated=self.cfg.tour_rated, state="signup",
                       created=now)
        if checkin and now >= t.checkin_opens():
            t.state = "checkin"
        self.tours[t.id] = t
        if akey is not None:
            self.created_from[t.id] = akey
        self._save(t)
        log.info("tournament %s %r created by %s: %s, first to %d, %d players, start %s", t.id, name, p.name, fmt,
                 set_wins, max_players, time.strftime("%Y-%m-%d %H:%M", time.gmtime(start)))
        self.srv._count("tournaments_created")
        return {"t": "tour", "tournament": self.full(t, p)}

    async def h_join(self, conn, msg):
        p = conn.player
        self._need_account(p)
        t = self._get(msg)
        if CAP not in conn.caps:
            raise LobbyError(proto.E_NOT_ALLOWED, "update the launcher to play in tournaments")
        if t.state not in ("signup", "checkin"):
            raise LobbyError(proto.E_STATE, "sign-up for that tournament is closed")
        if p.build_id != t.build:
            raise LobbyError(proto.E_VERSION, "that tournament is played with another build of the game")
        if p.account_id in t.entrants:
            return {"t": "tour", "tournament": self.full(t, p)}
        if len(t.entrants) >= t.max_players:
            raise LobbyError(proto.E_FULL, "that tournament is full")
        e = Entrant(p.account_id, p.name, self._now())
        if t.state == "checkin":
            e.checked_in = e.signed_up          # signing up during the check-in window is checking in
        t.entrants[p.account_id] = e
        self._save(t, [e])
        return {"t": "tour", "tournament": self.full(t, p)}

    async def h_leave(self, conn, msg):
        p = conn.player
        self._need_account(p)
        t = self._get(msg)
        e = t.entrants.get(p.account_id)
        if e is None:
            raise LobbyError(proto.E_STATE, "you are not in that tournament")
        if t.state in ("signup", "checkin"):
            if e.dq:
                # (security review 2) leaving and signing up again used to clear the organizer's disqualification
                raise LobbyError(proto.E_NOT_ALLOWED, "the organizer took you off this tournament")
            del t.entrants[p.account_id]
            self._drop_entrant_row(t, p.account_id)
            self._save(t, [])
        elif t.state == "running":
            # (knocked out already: nothing to withdraw from, and the place stays)
            if not e.dq and e.seed is not None and e.aid not in t.bracket.eliminated():
                self._disqualify(t, e, "withdrew")
        else:
            raise LobbyError(proto.E_STATE, "that tournament is over")
        return {"t": "tour", "tournament": self.full(t, p)}

    async def h_checkin(self, conn, msg):
        p = conn.player
        self._need_account(p)
        t = self._get(msg)
        e = t.entrants.get(p.account_id)
        if e is None:
            raise LobbyError(proto.E_STATE, "you are not in that tournament")
        if t.state != "checkin":
            raise LobbyError(proto.E_STATE, "check-in is not open")
        if not e.checked_in:
            e.checked_in = self._now()
            self._save(t, [e])
        return {"t": "tour", "tournament": self.full(t, p)}

    async def h_accept(self, conn, msg):
        p = conn.player
        self._need_account(p)
        t = self._get(msg)
        if t.state != "running" or t.bracket is None:
            raise LobbyError(proto.E_STATE, "that tournament is not running")
        s = t.bracket.sets.get(str(msg.get("set") or ""))
        if s is None or s.state != "open" or p.account_id not in s.p:
            raise LobbyError(proto.E_NOT_FOUND, "that set is not yours to play")
        if s.data.get("live") != "called":
            raise LobbyError(proto.E_STATE, "that set is not waiting for you")
        if p.build_id != t.build:
            raise LobbyError(proto.E_VERSION, "that tournament is played with another build of the game")
        self._make_free(p)
        side = s.p.index(p.account_id)
        acc = s.data.setdefault("accepted", [False, False])
        if not acc[side]:
            acc[side] = True
            self._save(t, [])
        self._send_calls(t, s)
        self._maybe_start(t, s)
        return None

    async def h_admin(self, conn, msg):
        p = conn.player
        self._need_account(p)
        t = self._get(msg)
        if not self._manages(p, t):
            raise LobbyError(proto.E_NOT_ALLOWED, "only the organizer can do that")
        op = msg.get("op")
        if op not in ADMIN_OPS:
            raise LobbyError(proto.E_BAD_REQUEST, "op is start, cancel, report, override, reset or dq")
        log.info("tournament %s: %s by %s (%s)", t.id, op, p.name,
                 {k: msg.get(k) for k in ("set", "winner", "score", "player") if msg.get(k) is not None})
        if op == "start":
            if t.state not in ("signup", "checkin"):
                raise LobbyError(proto.E_STATE, "that tournament has started already")
            if self._eligible_count(t) < 2:
                raise LobbyError(proto.E_STATE, "a tournament needs at least 2 players")
            self._start(t)
        elif op == "cancel":
            if t.state not in OPEN_STATES:
                raise LobbyError(proto.E_STATE, "that tournament is over")
            self._cancel(t, "organizer")
        elif op == "dq":
            e = next((x for x in t.entrants.values() if x.name.lower() == str(msg.get("player") or "").lower()), None)
            if e is None:
                raise LobbyError(proto.E_NOT_FOUND, "no such player in that tournament")
            if t.state == "running" and e.aid != p.account_id and not self._is_admin(p):
                s = t.bracket.set_of(e.aid) if t.bracket is not None else None
                if s is not None and p.account_id in s.p:
                    raise LobbyError(proto.E_NOT_ALLOWED, "you play in that set yourself: a server tournament admin "
                                                          "decides it (or cancel the tournament)")
            if t.state in ("signup", "checkin"):
                e.dq = "organizer"
                self._save(t, [e])
            elif t.state == "running":
                if e.dq or e.seed is None:
                    raise LobbyError(proto.E_STATE, "that player is out already")
                self._disqualify(t, e, "organizer")
            else:
                raise LobbyError(proto.E_STATE, "that tournament is over")
        else:
            self._set_op(t, op, msg, p)
        return {"t": "tour", "tournament": self.full(t, p)}

    # (security review 2) With T5L_TOUR_ORGANIZERS=any every account may organize -- and sign up for its own
    # tournament. An organizer does not decide a set they play themselves (report, override, reset), nor disqualify
    # the opponent of their open set: a T5L_TOUR_ADMINS account does, or the organizer cancels the tournament.

    def _set_op(self, t, op, msg, p=None):
        if t.state != "running" or t.bracket is None:
            raise LobbyError(proto.E_STATE, "that tournament is not running")
        s = t.bracket.sets.get(str(msg.get("set") or ""))
        if s is None:
            raise LobbyError(proto.E_NOT_FOUND, "no such set")
        if p is not None and p.account_id in s.p and not self._is_admin(p):
            raise LobbyError(proto.E_NOT_ALLOWED, "you play in that set yourself: a server tournament admin decides it "
                                                  "(or cancel the tournament)")
        winner, score = None, None
        if op in ("report", "override"):
            winner = msg.get("winner")
            if winner not in (0, 1):
                raise LobbyError(proto.E_BAD_REQUEST, "the winner is side 0 or 1")
            score = msg.get("score")
            if score is not None and not (isinstance(score, list) and len(score) == 2 and all(
                    isinstance(x, int) and not isinstance(x, bool) and 0 <= x <= t.set_wins for x in score)):
                raise LobbyError(proto.E_BAD_REQUEST, "the score is [games side 0, games side 1]")
        if op == "report":
            if s.state != "open":
                raise LobbyError(proto.E_STATE, "that set is decided; override it instead")
            self._detach(t, s)
            self._tell_set_players(t, s, "decided")
            self._decide(t, s, winner, score, "organizer")
            return
        # override / reset: undo what the bracket did with this set (and the walkovers decided from it)
        if op == "override" and (s.state != "done" or s.reason in NOT_PLAYED):
            raise LobbyError(proto.E_STATE, "only a played set can be overridden")
        if op == "override" and any(e is not EMPTY and e in t.bracket.dq for e in s.p):
            # (review-113) put back, the set is the other player's walkover (bracket.resolve): no winner to choose,
            # nothing to play -- a reset gives the walkover (the launcher knows this text in every language)
            raise LobbyError(proto.E_STATE, "only a played set can be overridden")
        if op == "reset" and s.state == "pending":
            raise LobbyError(proto.E_STATE, "that set has not been played")
        if s.state == "done" and s.reason in NOT_PLAYED:
            raise LobbyError(proto.E_STATE, "that set was a walkover")
        if s.state == "done":
            blocker = t.bracket.reset_blocker(s.id, busy=lambda d: d.data.get("live") == "playing")
            if blocker is not None:
                raise LobbyError(proto.E_STATE, f"set {blocker} was already played from this result; reset it first")
        self._detach(t, s)
        changed = t.bracket.reset(s.id) if s.state == "done" else [s.id]
        for sid in changed:
            d = t.bracket.sets[sid]
            if d.data.get("live") == "called":
                self._tell_set_players(t, d, "reset")
            d.data = {}
            t.bracket.dirty.add(sid)
        if op == "override":
            self._tell_set_players(t, s, "decided")
            self._decide(t, s, winner, score, "organizer")
        else:
            self._tell_set_players(t, s, "reset")
            self._save(t, [])
            self._call_open(t)

    # ================================================================== the tournament's course
    def _eligible(self, t):
        need = bool(t.checkin_minutes)
        return [e for e in t.entrants.values() if not e.dq and (e.checked_in or not need)]

    def _eligible_count(self, t):
        return len(self._eligible(t))

    def _start(self, t):
        now = self._now()
        ents = self._eligible(t)
        if len(ents) < 2:
            self._cancel(t, "not_enough")
            return
        rnd = random.Random(t.seed)
        rnd.shuffle(ents)                               # (random seeding; with rating: the tie break)
        if t.seeding == "rating":
            for e in ents:
                try:
                    e.rating = round(self.store.rating(e.aid).r, 1)
                except Exception:      # noqa: BLE001 -- a deleted account: rated as new
                    e.rating = 1500.0
            ents.sort(key=lambda e: -(e.rating or 0))
        for i, e in enumerate(ents):
            e.seed = i + 1
        for e in t.entrants.values():
            if e not in ents and not e.dq:
                self._notice(t, e.aid, "no_checkin")
        t.bracket = Bracket.build(t.format, [e.aid for e in ents])
        t.state = "running"
        t.started = now
        log.info("tournament %s %r starts: %d players, %s elimination", t.id, t.name, len(ents), t.format)
        self._save(t)
        for e in ents:
            self._notice(t, e.aid, "started", seed=e.seed, players=len(ents))
        self._call_open(t)

    def _cancel(self, t, reason):
        if t.bracket is not None:
            for s in t.bracket.sets.values():
                if s.data.get("live"):
                    if s.data.get("live") == "called":
                        self._tell_set_players(t, s, "cancelled")
                    self._detach(t, s)
                    t.bracket.dirty.add(s.id)
        t.state = "cancelled"
        t.reason = reason
        t.ended = self._now()
        log.info("tournament %s cancelled (%s)", t.id, reason)
        self._save(t)
        for e in t.entrants.values():
            self._notice(t, e.aid, "cancelled", reason=reason)

    def _finish(self, t):
        b = t.bracket
        champ = b.champion()
        t.champion = t.name_of(champ) if champ is not EMPTY else None
        for aid, place in b.standings():
            if aid in t.entrants:
                t.entrants[aid].place = place
        t.state = "finished"
        t.ended = self._now()
        log.info("tournament %s %r finished: champion %s", t.id, t.name, t.champion)
        self._save(t)
        self.srv._count("tournaments_finished")
        for e in t.entrants.values():
            if e.seed is not None:
                self._notice(t, e.aid, "finished", champion=t.champion, place=e.place)

    def _after(self, t, eliminated_before=None):
        """Something was decided: places of the newly knocked out, the end, or the next calls."""
        b = t.bracket
        out = b.eliminated()
        for aid, _st in out.items():
            if eliminated_before is not None and aid not in eliminated_before and aid not in b.dq:
                place = dict(b.standings()).get(aid)
                self._notice(t, aid, "eliminated", place=place)
        if b.finished():
            self._finish(t)
            return
        self._save(t, [])
        self._call_open(t)

    def _decide(self, t, s, winner, score, reason):
        before = set(t.bracket.eliminated())
        s.data["live"] = None
        s.data.pop("accepted", None)
        s.data.pop("deadline", None)
        t.bracket.report(s.id, winner, score, reason)
        self._after(t, before)

    def _disqualify(self, t, e, why):
        before = set(t.bracket.eliminated())
        e.dq = why
        sid = t.bracket.disqualify(e.aid)
        self._notice(t, e.aid, "dq", reason=why)
        if sid is not None:
            s = t.bracket.sets[sid]
            side = s.p.index(e.aid)
            if s.data.get("live"):
                self._detach(t, s)
            self._send(s.p[1 - side], t.name_of(s.p[1 - side]),
                       {"t": "tour_call_end", "tournament": t.id, "set": s.id, "reason": "opponent_out"})
            s.data = {"live": None, "games": s.data.get("games") or []}
            t.bracket.forfeit(sid, side, "dq" if why != "no_show" else "no_show")
        self._save(t, [e])
        self._after(t, before)

    # ---------------------------------------------------------------- calling sets
    def _draining(self):
        return bool(getattr(self.srv, "draining", False))

    def _call_open(self, t):
        if t.state != "running":
            return
        now = self._now()
        if not self._draining():                # (admin drain: the next sets are called when it ends or after the
            for s in t.bracket.open_sets():     # restart: _resume)
                if not s.data.get("live"):
                    self._call(t, s, now)
        self._save(t, [])

    def _call(self, t, s, now, quiet=False):
        d = s.data
        d["live"] = "called"
        d["deadline"] = now + self.cfg.tour_noshow
        d["accepted"] = [False, False]
        d.setdefault("carry", [0, 0])
        d.setdefault("games", [])
        d.setdefault("voids", 0)
        t.bracket.dirty.add(s.id)
        for aid in s.p:                     # (out of the queue: a match found now would keep them from accepting)
            p = self._player(aid, t.name_of(aid))
            if p is not None and p.status == "queue":
                self.srv._leave_queue(p)
        self._send_calls(t, s)
        if not quiet:
            log.info("tournament %s: set %s called (%s vs %s)", t.id, s.id, t.name_of(s.p[0]), t.name_of(s.p[1]))

    def _call_msg(self, t, s, side):
        d = s.data
        opp = s.p[1 - side]
        oq = self._player(opp, t.name_of(opp))
        b = t.bracket
        carry = d.get("carry") or [0, 0]
        return {"t": "tour_call", "tournament": {"id": t.id, "name": t.name},
                "set": {"id": s.id, "bracket": s.bracket, "round": s.round, "index": s.index, "format": t.format,
                        "rounds": b.k, "losers_rounds": b.losers_rounds},
                "best_of": t.best_of, "wins_needed": t.set_wins, "side": side,
                "score": [carry[side], carry[1 - side]], "replay": int(d.get("voids") or 0) > 0 or
                bool(d.get("restarts")),
                "opponent": oq.brief() if oq is not None else {"name": t.name_of(opp), "guest": False},
                "opponent_online": bool(oq is not None and oq.online),
                "deadline": max(0.0, round(float(d.get("deadline") or 0) - self._now(), 1)),
                "noshow": self.cfg.tour_noshow,
                "accepted": [bool((d.get("accepted") or [False, False])[side]),
                             bool((d.get("accepted") or [False, False])[1 - side])]}

    def _send_calls(self, t, s):
        for side in (0, 1):
            aid = s.p[side]
            if aid is not EMPTY:
                self._send(aid, t.name_of(aid), self._call_msg(t, s, side))

    def _tell_set_players(self, t, s, reason):
        for aid in s.p:
            if aid is not EMPTY:
                self._send(aid, t.name_of(aid), {"t": "tour_call_end", "tournament": t.id, "set": s.id,
                                                 "reason": reason})

    def _make_free(self, p):
        """`p` accepts a called set: out of the queue and a room; refused while it plays something else."""
        if p.match is not None or p.status in ("match", "playing"):
            raise LobbyError(proto.E_BUSY, "finish your match first, then accept the tournament set")
        gs = p.set
        if gs is not None and gs.state == "active":
            if gs.rated:
                raise LobbyError(proto.E_BUSY, "finish your set first, then accept the tournament set")
            self.srv._decline_recent(gs, p)
            self.srv._end_set(gs, "left", by=p)
        self.srv._leave_queue(p)
        if p.room is not None:
            self.srv._leave_room(p)

    def _free(self, p):
        return (p is not None and p.online and p.match is None and p.status not in ("match", "playing")
                and not (p.set is not None and p.set.state == "active" and p.set.rated))

    def _maybe_start(self, t, s):
        d = s.data
        if d.get("live") != "called" or d.get("accepted") != [True, True] or self._draining():
            return                                      # (admin drain: no new match before the restart)
        ps = [self._player(aid, t.name_of(aid)) for aid in s.p]
        if not all(self._free(p) for p in ps):
            return                                      # (the tick tries again; the no-show time still runs)
        a, b = ps
        rated = t.rated
        cfg = self.cfg
        if rated and not cfg.ranked_same_ip and self.srv._same_address(a, b):
            rated = False
        if rated and cfg.pair_cap > 0 and self.store.pair_ranked(a.account_id, b.account_id,
                                                                 self._now() - DAY) >= cfg.pair_cap:
            rated = False
        for p in ps:
            self.srv._leave_queue(p)
            if p.room is not None:
                self.srv._leave_room(p)
        ts = TourSet(a, b, rated, t.set_wins, t, s, d.get("carry") or (0, 0))
        d["live"] = "playing"
        d["lobby_set"] = ts.id
        d.pop("deadline", None)
        d.pop("accepted", None)
        d["attempts"] = int(d.get("attempts") or 0) + 1
        self.live[ts.id] = ts
        t.bracket.dirty.add(s.id)
        self._tell_set_players(t, s, "started")
        self._save(t, [])
        log.info("tournament %s: set %s starts (%s vs %s, attempt %d)", t.id, s.id, a.name, b.name, d["attempts"])
        self.srv.create_match(a, b, ranked=rated, origin="tournament", game_set=ts)

    def _detach(self, t, s):
        """The organizer (or a disqualification, a cancel) decides a set that is being played: its TourSet ends
        and its result no longer counts."""
        d = s.data
        ts = self.live.pop(d.get("lobby_set"), None) if d.get("lobby_set") else None
        if ts is not None and ts.state == "active":
            ts.detached = True
            m = ts.current
            if m is not None and m.state not in ("playing", "done", "cancelled"):
                self.srv.cancel_match(m, "organizer")
            else:
                if m is not None:
                    m.ranked = False            # (a game still being played counts on its own, unrated)
                if ts.state == "active":
                    self.srv._end_set(ts, "cancelled")
        d["live"] = None
        d.pop("lobby_set", None)
        d.pop("accepted", None)
        d.pop("deadline", None)
        t.bracket.dirty.add(s.id)

    # ---------------------------------------------------------------- a set's end (lobby.py _set_conclude)
    def set_concluded(self, gs):
        """Called by the lobby when a TourSet ends (after its own bookkeeping, before its messages): the bracket
        moves on right after those messages."""
        import asyncio
        if not isinstance(gs, TourSet) or gs.detached:
            return
        asyncio.get_running_loop().call_soon(self._set_concluded, gs)

    def _set_concluded(self, gs):
        if self.live.get(gs.id) is not gs:
            return
        del self.live[gs.id]
        t = gs.tour
        s = t.bracket.sets.get(gs.bset_id) if t.bracket is not None else None
        if t.state != "running" or s is None or s.state != "open" or s.data.get("lobby_set") != gs.id:
            return
        d = s.data
        d.pop("lobby_set", None)
        o = gs.outcome or {}
        games = list(d.get("games") or [])
        for g in gs.log:
            games.append({"match": g.get("match"), "number": g.get("number"), "winner": g.get("winner"),
                          "score": g.get("score"), "status": g.get("status"), "reason": g.get("reason")})
        d["games"] = games[-20:]
        d["carry"] = gs.score()
        winner = o.get("winner")
        if o.get("status") in ("confirmed", "forfeit") and winner is not None:
            side = gs.side(winner)
            self._decide(t, s, side, gs.score(), None if o["status"] == "confirmed" else "forfeit")
            return
        reason = o.get("reason") or o.get("status") or "void"
        blame = o.get("blame")
        if blame is not None and getattr(blame, "account_id", None) in s.p:
            # (security review 2) a game voided by one player's own doing (a crash: the game killed while losing) was
            # simply called again with the score so far -- a free do-over of a lost game, T5L_TOUR_RETRIES times a set.
            # T5L_TOUR_BLAMED_VOIDS of them a set are forgiven (real crashes happen); the next one loses the set.
            side = s.p.index(blame.account_id)
            blamed = d.setdefault("blamed", [0, 0])
            blamed[side] += 1
            if blamed[side] > self.cfg.tour_blamed_voids:
                log.info("tournament %s: set %s: %s ended %d games without a result (%s): the set goes to %s", t.id,
                         s.id, t.name_of(s.p[side]), blamed[side], reason, t.name_of(s.p[1 - side]))
                self._decide(t, s, 1 - side, gs.score(), "forfeit")
                return
        d["voids"] = int(d.get("voids") or 0) + 1
        if reason in ("disputed", "hash_mismatch") or d["voids"] > self.cfg.tour_retries:
            self._attention(t, s, reason)
            return
        log.info("tournament %s: set %s without a result (%s): called again at %d-%d", t.id, s.id, reason,
                 *d["carry"])
        self._call(t, s, self._now())
        self._save(t, [])

    def _attention(self, t, s, why):
        s.data["live"] = "attention"
        s.data["why"] = why
        t.bracket.dirty.add(s.id)
        log.info("tournament %s: set %s waits for the organizer (%s)", t.id, s.id, why)
        self._save(t, [])
        self._tell_set_players(t, s, "attention")
        self._notice_organizer(t, "attention", set=s.id, why=why)

    # ---------------------------------------------------------------- spectating (server/spectating.py)
    def may_watch(self, viewer, m):
        """SpectateMixin._spec_tournament_may_watch: a tournament's sets are public (the bracket is on the status port
        for anybody), so anybody whose launcher shows tournaments may watch one being played -- if both players allow
        spectators (their own setting; the rest of spectating's rules apply: blocks, the limit, not a player of it)."""
        gs = getattr(m, "set", None)
        if not isinstance(gs, TourSet) or gs.detached or gs.state != "active" or gs.tour.state != "running":
            return False
        c = getattr(viewer, "conn", None)
        return c is not None and CAP in getattr(c, "caps", ())

    def set_match(self, tid, sid):
        """watch {tournament, set}: the match of that set being played (None between its games)."""
        t = self.tours.get(str(tid or ""))
        if t is None:
            raise LobbyError(proto.E_NOT_FOUND, "no such tournament")
        s = t.bracket.sets.get(str(sid or "")) if t.bracket is not None else None
        if s is None:
            raise LobbyError(proto.E_NOT_FOUND, "no such set")
        ts = self.live.get(s.data.get("lobby_set")) if s.data.get("live") == "playing" else None
        return ts.current if ts is not None else None

    def match_live(self, m):
        """lobby.py: a game of a tournament set started playing or ended -- the bracket's live part (can it be
        watched, the set's score) changed, so the launchers showing it fetch it again (tour_changed). Nothing is
        written: only the announcement's revision moves."""
        gs = getattr(m, "set", None)
        if not isinstance(gs, TourSet) or gs.detached or gs.tour.state != "running":
            return
        t = gs.tour
        t.rev += 1
        self.dirty.add(t.id)
        self.http_cache.pop(t.id, None)
        self.http_cache.pop(None, None)

    # ---------------------------------------------------------------- lobby hooks
    def check_free(self, p, requester=None):
        """lobby.py _abandon_set: queueing, a room, a challenge -- not while a tournament set is called for `p` or
        being played."""
        gs = p.set
        if isinstance(gs, TourSet) and gs.state == "active":
            raise LobbyError(proto.E_BUSY, "you are in a tournament set; finish it first" if requester is None
                             else "that player is playing a tournament set")
        if p.account_id is None:
            return
        for t in self.tours.values():
            if t.state != "running" or p.account_id not in t.entrants:
                continue
            s = t.bracket.set_of(p.account_id)
            if s is not None and s.data.get("live") == "called":
                raise LobbyError(proto.E_BUSY, "your tournament set is ready; accept it first" if requester is None
                                 else "that player has a tournament set to play")

    def player_online(self, p):
        """Logged in (or back): the sets called for this player, again."""
        if p.account_id is None or p.conn is None or CAP not in p.conn.caps:
            return
        for t in self.tours.values():
            if t.state != "running" or p.account_id not in t.entrants:
                continue
            s = t.bracket.set_of(p.account_id)
            if s is not None and s.data.get("live") == "called":
                self._send_calls(t, s)
                self._maybe_start(t, s)

    # ================================================================== the tick: start times, no-shows, news
    async def _tick_loop(self):
        import asyncio
        while True:
            await asyncio.sleep(max(0.05, self.cfg.tour_tick))
            try:
                self.tick()
            except Exception:
                log.exception("tournaments")

    # `admin drain` (before a restart: no new matches, the running ones finish): a tournament starts no new set --
    # no start, no new calls, no set of a call starts -- and the no-show clocks of the called sets stand still. The
    # sets being played go on to their end (like ranked sets). Drain off: the clocks go on where they stood and the
    # open sets are called; a restart instead calls every open set again with a fresh no-show time (_resume).
    def _drain_tick(self, now):
        draining = self._draining()
        if draining and self.drain_since is None:
            self.drain_since = now
            log.info("tournaments: drain on, no new set starts")
        elif not draining and self.drain_since is not None:
            paused, self.drain_since = now - self.drain_since, None
            for t in self.tours.values():
                if t.state != "running" or t.bracket is None:
                    continue
                for s in t.bracket.open_sets():
                    d = s.data
                    if d.get("live") == "called":
                        d["deadline"] = float(d.get("deadline") or now) + paused
                        t.bracket.dirty.add(s.id)
                        self._send_calls(t, s)
                self._call_open(t)
        return draining

    def tick(self, now=None):
        now = self._now() if now is None else now
        draining = self._drain_tick(now)
        for t in list(self.tours.values()):
            if t.state == "signup" and t.checkin_minutes and now >= t.checkin_opens():
                t.state = "checkin"
                self._save(t, [])
                for e in t.entrants.values():
                    self._notice(t, e.aid, "checkin_open", minutes=t.checkin_minutes)
            if t.state in ("signup", "checkin") and now >= t.start_time and not draining:
                self._start(t)
            if t.state == "running" and not draining:
                for s in list(t.bracket.open_sets()):
                    d = s.data
                    if d.get("live") != "called" or t.state != "running":
                        continue
                    if now >= float(d.get("deadline") or 0):
                        self._no_show(t, s, now)
                    else:
                        self._maybe_start(t, s)
            if t.state in ("finished", "cancelled") and (t.ended or 0) < now - self.cfg.tour_keep_days * DAY:
                del self.tours[t.id]
                self.created_from.pop(t.id, None)
                self.view_cache.pop(t.id, None)
        self._announce()

    def _no_show(self, t, s, now):
        """The no-show time of a called set is over: whoever has not accepted (or is not there) loses it and is
        disqualified; nobody there: both are out, and their next opponents get walkovers. Both accepted and online
        but one still busy (a game the organizer took out of the tournament, ...): another no-show time for that,
        then the busy one is the no-show."""
        acc = s.data.get("accepted") or [False, False]
        ps = [self._player(aid, t.name_of(aid)) for aid in s.p]
        there = [bool(acc[i]) and ps[i] is not None and ps[i].online for i in (0, 1)]
        if all(there):
            self._maybe_start(t, s)                     # (both there and accepted: it starts as soon as it can)
            if s.data.get("live") != "called" or now < float(s.data.get("deadline") or 0) + self.cfg.tour_noshow:
                return
            there = [self._free(p) for p in ps]
        before = set(t.bracket.eliminated())
        gone = [i for i in (0, 1) if not there[i]]
        log.info("tournament %s: set %s no-show: %s", t.id, s.id, ", ".join(t.name_of(s.p[i]) for i in gone))
        s.data["live"] = None
        s.data.pop("accepted", None)
        s.data.pop("deadline", None)
        for i in gone:
            e = t.entrants[s.p[i]]
            e.dq = "no_show"
            t.bracket.dq.add(e.aid)
            self._notice(t, e.aid, "dq", reason="no_show")
        if len(gone) == 2:
            t.bracket.double_forfeit(s.id, "no_show")
        else:
            w = 1 - gone[0]
            self._send(s.p[w], t.name_of(s.p[w]), {"t": "tour_call_end", "tournament": t.id, "set": s.id,
                                                   "reason": "no_show"})
            t.bracket.report(s.id, w, None, "no_show")
        # (a disqualified player waiting in a later set: that set is a walkover now)
        for i in gone:
            t.bracket.disqualify(s.p[i])
        self._save(t, [t.entrants[s.p[i]] for i in gone])
        self._after(t, before)

    def _announce(self):
        """tour_changed for the tournaments that changed (clients with the cap fetch what they show)."""
        if not self.dirty:
            return
        ids, self.dirty = self.dirty, set()
        msgs = [proto.encode({"t": "tour_changed", "id": tid, "rev": self.tours[tid].rev,
                              "state": self.tours[tid].state}) for tid in ids if tid in self.tours]
        if not msgs:
            return
        for p in self.srv.players.values():
            c = p.conn
            if c is not None and not c.closed and CAP in c.caps:
                for m in msgs:
                    c.send_raw(m)
