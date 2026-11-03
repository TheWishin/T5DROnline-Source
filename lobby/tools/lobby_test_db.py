"""Synthetic lobby databases for deploy rehearsals, and a code-free fingerprint of a database's data.

    python lobby/tools/lobby_test_db.py make --lobby <T5DR checkout of the OLD release>/lobby --out t5.db \\
        [--accounts 1300] [--logins logins.json] [--release 1.1.9]
    python lobby/tools/lobby_test_db.py digest t5.db > before.json
    python lobby/tools/lobby_test_db.py compare before.json t5.db        (exit 1 = data lost or changed)

`make` builds the database with THAT checkout's own Store and LobbyServer (so a schema-1 database is made by 1.1.9
code, as on the central server), filled with made-up players only -- never real player data: accounts with known
passwords, ratings and ranks, remembered logins, recovery codes, friends, friend requests, blocks, ranked and casual
matches, ranked sets, bans, an address ban, a deleted account (the id rule's kv row), notices, the release flag.
`--logins` writes the names, passwords, remembered-login tokens and recovery codes of a few of them (for login
checks after an upgrade).

`digest` reads with sqlite3 only (no lobby code): per table the columns, the row count and a SHA-256 over every row.
`compare` recomputes the digest of a later database over the columns the earlier one had: a migration may ADD
tables and columns, but every earlier row must still be there unchanged (`--grow` also allows more rows, for a
database that kept running). The kv flags a server start or the admin tool rewrite (drain, release) are left out.
"""
import argparse
import hashlib
import json
import os
import random
import sqlite3
import sys
import time

VOLATILE_KV = {"drain", "release"}


def make(a):
    sys.path.insert(0, os.path.abspath(a.lobby))
    from t5lobby import rating as glicko
    from t5lobby.server import Config, LobbyServer
    from t5lobby.server.store import Store, hash_password
    if os.path.exists(a.out):
        sys.exit(f"{a.out} exists: give a new file")
    rnd = random.Random(a.seed)
    st = Store(a.out)
    st.defer_commits(lambda flush: None)       # one transaction for everything (flush at the end)
    now = time.time()
    ids, names = [], []
    pw_hash = {}
    for i in range(1, a.accounts + 1):
        name = f"Reh{i:04d}" if i % 7 else f"reh_{i:04d}.x"
        pw = f"reh-pass-{i}"
        row = st.create_account(name, hash_password(pw, n=1 << 10))
        ids.append(row["id"])
        names.append(name)
        pw_hash[name] = pw
    for aid in rnd.sample(ids, min(300, len(ids))):
        for _ in range(rnd.randint(1, 4)):
            rt = glicko.Rating(1500 + rnd.uniform(-300, 400), rnd.uniform(60, 250), 0.06)
            st.set_rating(aid, rt, rnd.choice(["win", "loss", "draw"]))
        st.add_unranked_game(aid, rnd.choice(["win", "loss"]))
    logins = []
    for k in range(min(20, len(ids))):
        tok = st.create_session(ids[k])
        codes = st.issue_recovery_codes(ids[k]) if k < 5 else []
        logins.append({"name": names[k], "password": pw_hash[names[k]], "token": tok, "recovery": codes[:2]})
    pairs = set()
    while len(pairs) < min(200, len(ids) // 2):
        x, y = rnd.sample(ids, 2)
        pairs.add((min(x, y), max(x, y)))
    for x, y in sorted(pairs):
        st.add_friendship(x, y, time.time())
    for _ in range(50):
        x, y = rnd.sample(ids, 2)
        st.add_friend_request(x, y, time.time())
    for _ in range(30):
        x, y = rnd.sample(range(len(ids)), 2)
        st.add_block(ids[x], ids[y], names[y])
    chars = ["Jin", "Kazuya", "Steve", "Xiaoyu", "Bryan", "Asuka", "Law", "Hwoarang", "Lili", "Kuma"]
    statuses = ["confirmed"] * 8 + ["void", "onesided", "forfeit", "disputed"]
    for m in range(a.matches):
        i, j = rnd.sample(range(len(ids)), 2)
        t0 = now - rnd.uniform(0, 60 * 86400)
        winner = rnd.choice([0, 1, None]) if rnd.random() < 0.97 else None
        st.save_match({"id": f"m{m:06x}reh", "created": t0, "ended": t0 + 180, "ranked": rnd.random() < 0.5,
                       "p1_name": names[i], "p2_name": names[j], "p1_account": ids[i], "p2_account": ids[j],
                       "build": "rehbuild", "path": rnd.choice(["direct", "relay"]), "rtt_ms": rnd.uniform(10, 200),
                       "delay": 2, "status": rnd.choice(statuses), "winner": winner, "score": [2, 1],
                       "reports": None, "rating": None, "origin": rnd.choice(["queue", "challenge", "room"]),
                       "started": t0 + 5, "duration": 170.0, "p1_char": rnd.choice(chars),
                       "p2_char": rnd.choice(chars), "stage": "t5s02", "reason": None, "blame": None})
    for n in range(a.sets):
        i, j = rnd.sample(range(len(ids)), 2)
        t0 = now - rnd.uniform(0, 30 * 86400)
        games = []
        for g in range(1, 4):
            mid = f"s{n:05x}g{g}reh"
            st.save_match({"id": mid, "created": t0 + g * 200, "ended": t0 + g * 200 + 180, "ranked": True,
                           "p1_name": names[i], "p2_name": names[j], "p1_account": ids[i], "p2_account": ids[j],
                           "status": "confirmed", "winner": g % 2, "score": [2, 0], "set_id": f"set{n:05x}",
                           "set_game": g, "p1_char": rnd.choice(chars), "p2_char": rnd.choice(chars)})
            games.append({"match": mid, "number": g, "status": "confirmed", "winner": g % 2, "score": [2, 0]})
        st.save_set({"id": f"set{n:05x}", "created": t0, "ended": t0 + 800, "ranked": True, "p1_name": names[i],
                     "p2_name": names[j], "p1_account": ids[i], "p2_account": ids[j], "wins_needed": 2,
                     "status": "confirmed", "winner": 1, "score": [1, 2], "games": games,
                     "rating": [{"delta": -12.5}, {"delta": 12.5}]})
    st.ban_account(names[-1], now + 7 * 86400, "rehearsal ban")
    st.ban_account(names[-2], 32503680000.0, "rehearsal ban for good")
    st.ban_ip("203.0.113.0/24", now + 86400, "rehearsal")
    st.add_notice("rehearsal notice (ended)", now - 60, now - 3600)
    st.delete_account(names[-3])               # the highest-id rule (kv accounts.max_id) gets a row
    if a.release:
        st.set_flag("release", a.release)
    st.flush()
    st.close()
    # the server's own start-up on the file (its other tables: tournaments, ...), as a first start would do
    LobbyServer(Config(db=a.out, status_port=0)).store.close()
    db = sqlite3.connect(a.out)
    ver = db.execute("PRAGMA user_version").fetchone()[0]
    mode = db.execute("PRAGMA journal_mode").fetchone()[0]
    n = db.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
    db.close()
    if a.logins:
        with open(a.logins, "w", encoding="utf-8") as f:
            json.dump({"database": os.path.abspath(a.out), "schema": ver, "logins": logins}, f, indent=1)
    print(f"{a.out}: schema {ver}, {mode}, {n} accounts (made-up players), {a.matches + 3 * a.sets} matches, "
          f"{a.sets} sets")
    return 0


def _tables(db):
    return [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type = 'table' "
                                     "AND name NOT LIKE 'sqlite_%' ORDER BY name")]


def digest_db(path, columns=None):
    db = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        out = {"schema": db.execute("PRAGMA user_version").fetchone()[0], "tables": {}}
        for t in _tables(db):
            have = [r[1] for r in db.execute(f"PRAGMA table_info({t})")]
            cols = have if columns is None or t not in columns else columns[t]
            missing = [c for c in cols if c not in have]
            if missing:
                out["tables"][t] = {"columns": cols, "missing": missing}
                continue
            sel = ", ".join(f'"{c}"' for c in cols)
            where = (" WHERE key NOT IN (%s)" % ", ".join("'%s'" % k for k in sorted(VOLATILE_KV))) if t == "kv" else ""
            rows = sorted(json.dumps(list(r), default=repr) for r in db.execute(f'SELECT {sel} FROM "{t}"{where}'))
            h = hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()
            out["tables"][t] = {"columns": cols, "rows": len(rows), "sha256": h, "all_columns": have,
                                "_rows": rows if columns is not None else None}
        return out
    finally:
        db.close()


def cmd_digest(a):
    d = digest_db(a.db)
    for t in d["tables"].values():
        t.pop("_rows", None)
        t.pop("all_columns", None)
    json.dump(d, sys.stdout, indent=1)
    print()
    return 0


def cmd_compare(a):
    with open(a.before, encoding="utf-8") as f:
        before = json.load(f)
    after = digest_db(a.db, {t: v["columns"] for t, v in before["tables"].items()})
    bad = []
    for t, b in before["tables"].items():
        x = after["tables"].get(t)
        if x is None:
            bad.append(f"table {t} is gone")
        elif x.get("missing"):
            bad.append(f"{t}: columns gone: {', '.join(x['missing'])}")
        elif x["sha256"] != b["sha256"]:
            if a.grow and x["rows"] >= b["rows"]:
                continue
            bad.append(f"{t}: rows changed ({b['rows']} -> {x['rows']})")
    added_t = sorted(set(after["tables"]) - set(before["tables"]))
    added_c = {t: [c for c in after["tables"][t]["all_columns"] if c not in b["columns"]]
               for t, b in before["tables"].items() if t in after["tables"] and "all_columns" in after["tables"][t]}
    added_c = {t: c for t, c in added_c.items() if c}
    rows = sum(b.get("rows", 0) for b in before["tables"].values())
    print(f"schema {before['schema']} -> {after['schema']}; {len(before['tables'])} tables, {rows} rows compared")
    if added_t:
        print("tables added:", ", ".join(added_t))
    for t, c in sorted(added_c.items()):
        print(f"columns added to {t}: {', '.join(c)}")
    for line in bad:
        print("DIFFERENT:", line)
    print("data unchanged" + (" (rows may have grown)" if a.grow else "") if not bad else "DATA CHANGED")
    return 1 if bad else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("make", help="a synthetic database made by a given lobby checkout's code")
    p.add_argument("--lobby", required=True, help="the T5DR checkout's lobby folder whose code makes the file")
    p.add_argument("--out", required=True)
    p.add_argument("--accounts", type=int, default=1300)
    p.add_argument("--matches", type=int, default=3000)
    p.add_argument("--sets", type=int, default=150)
    p.add_argument("--seed", type=int, default=120)
    p.add_argument("--logins", help="write a few accounts' passwords, tokens and recovery codes here (JSON)")
    p.add_argument("--release", default="", help="the release flag (admin release), e.g. 1.1.9 as on central")
    p.set_defaults(fn=make)
    p = sub.add_parser("digest", help="row counts and hashes per table (JSON on stdout)")
    p.add_argument("db")
    p.set_defaults(fn=cmd_digest)
    p = sub.add_parser("compare", help="every earlier row still there, unchanged (exit 1 if not)")
    p.add_argument("before", help="a digest JSON")
    p.add_argument("db")
    p.add_argument("--grow", action="store_true", help="more rows are fine (a database that kept running)")
    p.set_defaults(fn=cmd_compare)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
