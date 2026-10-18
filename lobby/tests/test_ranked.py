"""Ranked play, accounts and match integrity (docs/RANKED.md).

Units: rank tiers (placement, promotion, demotion with hysteresis and shield, Kyu floor),
the fighters table, sessions / recovery codes in the store, the database upgrade, the
client's no-password-in-clear policy.

End to end (real server, clients on localhost): remembered logins, logout, password change,
recovery codes, reserved names, characters in match_start, rank progress in match_result,
profile / history / leaderboard; integrity: desync -> void, disputes decided by the state
hash, minimum match length, quitting, crashes and strikes, losing the lobby mid-match
(grace period, forfeit, automatic reconnect), lone reports, the per-pair ranked cap;
rematches (inside the running games and with a new connection); the match driver with the
stub game (process and persistent mode)."""
import json
import os
import sqlite3
import sys
import tempfile
import time
import unittest

import util
from util import ServerThread, client, expect
from t5lobby import fighters, proto, ranks
from t5lobby.client import LobbyClient, is_local_address
from t5lobby.proto import LobbyError
from t5lobby.server.store import Store

HERE = os.path.dirname(os.path.abspath(__file__))
STUB = os.path.join(os.path.dirname(HERE), "tools", "stub_game.py")


# ============================================================================== units
class RankTest(unittest.TestCase):
    def test_table_matches_the_game(self):
        self.assertEqual(len(ranks.RANKS), 37)                  # the game's badge table: Beginner .. Kirin
        self.assertEqual(ranks.name(0), "Beginner")
        self.assertEqual(ranks.name(10), "1st Dan")
        self.assertEqual(ranks.name(33), "Tekken Lord")
        self.assertEqual(ranks.index("2nd dan"), 11)
        thresholds = [t for _, t in ranks.RANKS[2:]]
        self.assertEqual(thresholds, sorted(thresholds))

    def test_tier_for(self):
        self.assertEqual(ranks.tier_for(900), 1)                 # 9th Kyu is the floor
        self.assertEqual(ranks.tier_for(1500), 9)                # 1st Kyu
        self.assertEqual(ranks.tier_for(1520), 10)               # 1st Dan
        self.assertEqual(ranks.tier_for(5000), 36)

    def play(self, state, ratings, rules=None):
        events = []
        for r in ratings:
            state, ev = ranks.after_match(state, r, rules)
            events.append(ev)
        return state, events

    def test_placement(self):
        rules = ranks.RankRules(placement=3, placement_cap=12)
        s, ev = self.play(ranks.RankState(), [1600, 1650])
        self.assertEqual(s.tier, ranks.BEGINNER)
        info = ranks.describe(s, 200, rules)
        self.assertTrue(info["provisional"])
        s, ev = self.play(ranks.RankState(), [1600, 1700, 1900], rules)
        self.assertEqual(ev[-1], "placed")
        self.assertEqual(s.tier, 12)                             # capped at 3rd Dan
        s, ev = self.play(ranks.RankState(), [1300, 1250, 1240], rules)
        self.assertEqual(s.tier, ranks.tier_for(1240))
        self.assertEqual(ranks.label(ranks.describe(ranks.RankState(games=1), 300, rules)), "Beginner (placement 1/3)")

    def test_promotion_demotion_hysteresis_shield(self):
        rules = ranks.RankRules(placement=1, hysteresis=30, shield=2)
        s, _ = self.play(ranks.RankState(), [1600], rules)        # placed at 3rd Dan (1600)
        self.assertEqual(s.tier, 12)
        s, ev = self.play(s, [1690], rules)                     # straight to 5th Dan
        self.assertEqual((s.tier, ev[-1]), (14, "promoted"))
        s, ev = self.play(s, [1600, 1600], rules)               # far below, but shielded for 2 matches
        self.assertEqual(s.tier, 14)
        s, ev = self.play(s, [1660], rules)                     # 20 below 1680: within the hysteresis
        self.assertEqual((s.tier, ev[-1]), (14, None))
        s, ev = self.play(s, [1600], rules)                     # 80 below: demoted, to where 1600 + 30 lands
        self.assertEqual((s.tier, ev[-1]), (ranks.tier_for(1630), "demoted"))
        s, ev = self.play(s, [1000] * 6, rules)                 # never back below 1st Dan once reached
        self.assertEqual(s.tier, ranks.FIRST_DAN)
        self.assertEqual(s.peak, 14)

    def test_kyu_floor_is_the_placement_tier(self):
        rules = ranks.RankRules(placement=1, shield=0)
        s, _ = self.play(ranks.RankState(), [1300], rules)        # placed at 5th Kyu
        s, _ = self.play(s, [1100] * 5, rules)
        self.assertEqual(s.tier, ranks.tier_for(1300))


class FightersTest(unittest.TestCase):
    def test_table_and_resolution(self):
        t = fighters.table()
        self.assertTrue(t.valid_fighter("jin") and t.valid_fighter("random") and not t.valid_fighter("goku"))
        a = t.resolve("random", "jin", "random", 1234)
        self.assertEqual(a, t.resolve("random", "jin", "random", 1234))    # same on every PC
        self.assertEqual(a[1], "jin")
        self.assertNotIn(a[0], ("jinpachi", "panda"))                      # no bosses, nothing unverified
        self.assertEqual(t.fight_env("paul", "law", "s20", 3), "0,1,20,3")
        self.assertEqual((t.fighter("lili")["id"], t.fighter("dragunov")["id"]), (33, 34))   # DIRECTFIGHT.md
        self.assertEqual([s["id"] for s in t.stages], list(range(17, 35)))
        self.assertFalse(t.valid_fighter("jinpachi"))


class StoreTest(unittest.TestCase):
    def test_sessions_and_recovery_codes(self):
        st = Store(":memory:")
        acc = st.create_account("Nina", "x")
        tok = st.create_session(acc["id"])
        self.assertEqual(len(tok), 64)
        self.assertNotIn(tok, json.dumps([dict(r) for r in st.db.execute("SELECT * FROM sessions")]))   # hashed
        self.assertEqual(st.session_account(tok)["name"], "Nina")
        self.assertIsNone(st.session_account("0" * 64))
        tok2 = st.create_session(acc["id"])
        st.revoke_sessions(acc["id"], keep=tok2)
        self.assertIsNone(st.session_account(tok))
        self.assertIsNotNone(st.session_account(tok2))
        st.db.execute("UPDATE sessions SET expires = 0")
        self.assertIsNone(st.session_account(tok2))              # expired
        codes = st.issue_recovery_codes(acc["id"], 4)
        self.assertEqual(len(set(codes)), 4)
        self.assertTrue(st.use_recovery_code(acc["id"], codes[0].lower().replace("-", " ")))
        self.assertFalse(st.use_recovery_code(acc["id"], codes[0]))          # once only
        self.assertEqual(st.recovery_left(acc["id"]), 3)
        st.issue_recovery_codes(acc["id"], 4)
        self.assertFalse(st.use_recovery_code(acc["id"], codes[1]))          # old set gone
        st.close()

    def test_old_database_is_upgraded(self):
        d = tempfile.mkdtemp()
        path = os.path.join(d, "old.db")
        db = sqlite3.connect(path)
        db.executescript("""
            CREATE TABLE accounts (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                pw TEXT NOT NULL, created REAL NOT NULL, last_seen REAL, rating REAL NOT NULL, rd REAL NOT NULL,
                vol REAL NOT NULL, last_ranked REAL, games INTEGER NOT NULL DEFAULT 0,
                wins INTEGER NOT NULL DEFAULT 0, losses INTEGER NOT NULL DEFAULT 0, draws INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE matches (id TEXT PRIMARY KEY, created REAL NOT NULL, ended REAL, ranked INTEGER NOT NULL,
                p1_name TEXT, p2_name TEXT, p1_account INTEGER, p2_account INTEGER, build TEXT, path TEXT,
                rtt_ms REAL, delay INTEGER, status TEXT NOT NULL, winner INTEGER, score TEXT, reports TEXT,
                rating TEXT);
            INSERT INTO accounts (name, pw, created, rating, rd, vol, games, wins)
                VALUES ('Old', 'x', 0, 1600, 80, 0.06, 3, 3);""")
        db.commit()
        db.close()
        st = Store(path)
        row = st.account("Old")
        self.assertEqual((row["rating"], row["tier"], row["ranked_games"]), (1600, 0, 0))
        st.close()


class PolicyTest(unittest.TestCase):
    def test_local_addresses(self):
        for ip in ("127.0.0.1", "192.168.1.20", "10.0.0.5", "172.16.3.4", "localhost"):
            self.assertTrue(is_local_address(ip), ip)
        for ip in ("8.8.8.8", "93.184.216.34"):
            self.assertFalse(is_local_address(ip), ip)

    def test_no_password_in_clear_to_a_public_server(self):
        c = LobbyClient("93.184.216.34:7781", util.BUILD)
        c.server_ip = "93.184.216.34"
        for call in (lambda: c.login("Nina", "secret1"), lambda: c.register("Nina", "secret1"),
                     lambda: c.login_session("ab" * 32), lambda: c.change_password("a" * 6, "b" * 6),
                     lambda: c.recover("Nina", "AAAA-BBBB-CCCC", "b" * 6)):
            with self.assertRaises(LobbyError) as e:
                call()
            self.assertEqual(e.exception.code, proto.E_INSECURE)
        self.assertTrue(LobbyClient("93.184.216.34", util.BUILD, tls_fingerprint="ab").password_ok())
        self.assertTrue(LobbyClient("93.184.216.34", util.BUILD, plain_passwords=True).password_ok())


# ============================================================================== end to end
class Base(unittest.TestCase):
    server_cfg = {}

    def setUp(self):
        self.s = ServerThread(**self.server_cfg).start()
        self.clients = []

    def tearDown(self):
        for c in self.clients:
            c.close()
        self.s.stop()

    def c(self, name=None, **kw):
        c = client(self.s, name, **kw)
        self.clients.append(c)
        return c

    def acc(self, name, **kw):
        return self.c(name, password="pw-" + name, register=True, auto_ready=True, **kw)

    def ranked(self, a, b, ca=None, cb=None):
        a.ranked_match(ca)
        b.ranked_match(cb)
        # 20 s: after a placement game the two ratings are ~330 apart, and the queue's rating
        # window (100 + 25/s) needs ~9.5 s to reach that -- too close to 10 s on a slow box.
        return expect(a, "match_start", 20.0), expect(b, "match_start", 20.0)

    def account(self, name):
        return self.s.call(lambda: dict(self.s.srv.store.account(name)))

    def player(self, name):
        return self.s.call(lambda: self.s.srv.by_name.get(name.lower()))


class AccountTest(Base):
    def test_register_remember_session_logout(self):
        a = self.c()
        me = a.register("Julia", "jaguar-1", remember=True)
        self.assertFalse(me["guest"])
        self.assertEqual(len(a.recovery_codes), 8)
        tok = a.session
        self.assertEqual(len(tok), 64)
        a.close()
        b = self.c()
        self.assertEqual(b.login_session(tok)["name"], "Julia")
        self.assertEqual(b.session, tok)
        b.logout(forget=True)                                   # ends the remembered login on the server
        x = self.c()
        with self.assertRaises(LobbyError) as e:
            x.login_session(tok)
        self.assertEqual(e.exception.code, proto.E_AUTH)
        self.assertEqual(x.login("Julia", "jaguar-1")["name"], "Julia")

    def test_password_change_and_recovery(self):
        a = self.c()
        a.register("Bryan", "fury-123", remember=True)
        codes = a.recovery_codes
        old_session = a.session
        with self.assertRaises(LobbyError):
            a.change_password("wrong-pw", "new-pass-1")
        a.change_password("fury-123", "new-pass-1", remember=True)
        self.assertNotEqual(a.session, old_session)
        a.close()
        x = self.c()
        with self.assertRaises(LobbyError):
            x.login_session(old_session)                        # every other remembered login ended
        with self.assertRaises(LobbyError):
            x.login("Bryan", "fury-123")
        y = self.c()
        r = y.recover("Bryan", codes[2], "after-recovery")
        self.assertEqual(r["codes_left"], 7)
        with self.assertRaises(LobbyError):
            y.recover("Bryan", codes[2], "again-recovery")      # each code once
        self.assertEqual(y.login("Bryan", "after-recovery")["name"], "Bryan")
        new = y.new_recovery_codes("after-recovery")
        self.assertEqual(len(new), 8)
        with self.assertRaises(LobbyError):
            y.new_recovery_codes("wrong-pw")
        prof = y.profile()
        self.assertEqual(prof["recovery_codes_left"], 8)

    def test_name_rules(self):
        x = self.c()
        for bad in ("Admin", "a.d.m.i.n", "Moderator7", "Unknown", "GUEST"):
            with self.assertRaises(LobbyError) as e:
                x.login_guest(bad)
            self.assertEqual(e.exception.code, proto.E_BAD_NAME, bad)
        with self.assertRaises(LobbyError):
            x.register("Server", "whatever-1")
        self.c("Marduk")                                        # a guest called Marduk is online
        with self.assertRaises(LobbyError) as e:
            x.register("marduk", "whatever-1")
        self.assertEqual(e.exception.code, proto.E_NAME_TAKEN)
        self.assertIsNone(self.s.call(lambda: self.s.srv.store.account("Marduk")))   # nothing half-created

    def test_guest_is_casual_only(self):
        g = self.c("Roger")
        self.assertEqual(g.me["rank"], "Guest")
        with self.assertRaises(LobbyError):
            g.ranked_match()
        with self.assertRaises(LobbyError):
            g.create_room("r", ranked=True)
        g.quick_match()

    def test_relogin_takes_over_a_running_match(self):
        a = self.acc("Anna")
        b = self.acc("Nina")
        ea, eb = self.ranked(a, b)
        a2 = self.c()
        a2.login("Anna", "pw-Anna")                             # same account from another place
        ev = expect(a2, "match_start")
        self.assertEqual(ev["match"], ea["match"])
        self.assertEqual(self.player("Anna").status, "playing")

    def test_a_replaced_login_says_why_in_plain_words(self):
        # e2e finding: the first PC's tab said "Lost the lobby connection: 0 bytes read on a total of
        # undefined expected bytes" after the account logged in elsewhere
        a = self.acc("Kuma")
        a2 = self.c()
        a2.login("Kuma", "pw-Kuma")
        ev = expect(a, "disconnected", timeout=10)
        self.assertEqual(ev["reason"], "removed from the lobby: logged in from another place")
        self.assertNotIn("bytes read", ev["reason"])


class RankedFlowTest(Base):
    def test_characters_ranks_profile_history_leaderboard(self):
        a = self.acc("Jin")
        b = self.acc("Hwoarang")
        with self.assertRaises(LobbyError):
            a.set_char("goku")
        ea, eb = self.ranked(a, b, "jin", "random")
        self.assertEqual(ea["fight"], eb["fight"])
        f = ea["fight"]
        mine = f["p1"] if ea["slot"] == 0 else f["p2"]
        self.assertEqual(mine, "jin")
        self.assertTrue(fighters.table().fighter(f["p2"] if ea["slot"] == 0 else f["p1"]))
        self.assertEqual([p["name"] for p in ea["players"]], [ea["players"][0]["name"], ea["players"][1]["name"]])
        w = ea["slot"]
        score = [3, 1] if w == 0 else [1, 3]
        a.report_result(w, score, source="game", desync=0)
        b.report_result(w, score, source="game", desync=0)
        ra = expect(a, "match_result")
        self.assertEqual(ra["status"], "confirmed")
        self.assertEqual(ra["rating"]["rank_after"]["placement"], [1, 5])
        self.assertEqual(ra["rating"]["rank_after"]["rank"], "Beginner")
        prof = a.profile()
        self.assertEqual(prof["main"], "jin")
        self.assertEqual(prof["history"][0]["result"], "win")
        self.assertEqual(prof["history"][0]["you_char"], "jin")
        self.assertEqual(prof["history"][0]["score"], [3, 1])
        self.assertGreater(prof["history"][0]["delta"], 0)
        hist = b.history("Jin")
        self.assertEqual(hist[0]["opponent"], "Hwoarang")
        board = a.leaderboard()
        self.assertEqual([r["name"] for r in board], ["Jin", "Hwoarang"])
        self.assertEqual(board[0]["rank"], "Beginner")
        self.assertTrue(board[0]["provisional"])
        self.assertEqual(board[0]["main"], "jin")

    def test_placement_then_rank(self):
        self.s.call(lambda: setattr(self.s.srv.rules, "placement", 2))
        a = self.acc("Lee")
        b = self.acc("Steve")
        for _ in range(2):
            ea, eb = self.ranked(a, b)
            w = ea["slot"]
            a.report_result(w, None)
            b.report_result(w, None)
            ra = expect(a, "match_result")
            expect(b, "match_result")
        self.assertEqual(ra["rating"]["event"], "placed")
        self.assertNotEqual(ra["rating"]["rank_after"]["rank"], "Beginner")
        self.assertGreater(self.account("Lee")["tier"], 0)
        self.assertEqual(self.account("Lee")["ranked_games"], 2)


class IntegrityTest(Base):
    def setup_match(self):
        a = self.acc("Alice")
        b = self.acc("Bob")
        ea, eb = self.ranked(a, b)
        return a, b, ea, eb

    def test_desync_voids_immediately(self):
        a, b, ea, eb = self.setup_match()
        a.report_result(ea["slot"], [3, 0] if ea["slot"] == 0 else [0, 3], source="game", desync=12)
        ev = expect(b, "match_result")
        self.assertEqual((ev["status"], ev["reason"]), ("void", "desync"))
        self.assertEqual(self.account("Alice")["rating"], 1500)

    def test_dispute_decided_by_equal_hash(self):
        a, b, ea, eb = self.setup_match()
        a.report_result(ea["slot"], None, source="manual", hash="abc123")     # Alice claims the win by hand
        b.report_result(eb["slot"], [1, 3] if eb["slot"] == 1 else [3, 1], source="game", hash="abc123")
        ev = expect(a, "match_result")
        self.assertEqual(ev["status"], "resolved")
        self.assertEqual(ev["winner"], eb["slot"])                           # the game's own result stands

    def test_dispute_with_different_hash_is_a_desync(self):
        a, b, ea, eb = self.setup_match()
        a.report_result(ea["slot"], None, source="game", hash="aaaa")
        b.report_result(eb["slot"], None, source="game", hash="bbbb")
        ev = expect(a, "match_result")
        self.assertEqual((ev["status"], ev["reason"]), ("void", "desync"))

    def test_fight_without_a_winner_is_void_but_a_draw_counts(self):
        a, b, ea, eb = self.setup_match()
        a.report_result(None, [0, 0], source="game")
        b.report_result(None, [0, 0], source="game")
        self.assertEqual(expect(a, "match_result")["reason"], "no_result")
        ea, eb = self.ranked(a, b)
        a.report_result(None, [2, 2], source="game")        # a real draw
        b.report_result(None, [2, 2], source="game")
        ev = expect(a, "match_result")
        self.assertEqual((ev["status"], ev["winner"]), ("confirmed", None))

    def test_dispute_without_evidence(self):
        a, b, ea, eb = self.setup_match()
        a.report_result(ea["slot"], None, source="game")
        b.report_result(eb["slot"], None, source="game")
        self.assertEqual(expect(a, "match_result")["status"], "disputed")

    def test_crash_strikes_turn_into_losses(self):
        self.s.call(lambda: setattr(self.s.srv.cfg, "strike_limit", 1))
        a = self.acc("Alice")
        b = self.acc("Bob")
        for i, expected in enumerate(("void", "forfeit")):
            ea, eb = self.ranked(a, b)
            a.report_result(None, None, source="crash")
            b.report_result(None, None, source="disconnect")
            ev = expect(a, "match_result")
            expect(b, "match_result")
            self.assertEqual(ev["status"], expected)
            self.assertEqual(ev["blame"], "you")
        self.assertEqual(self.account("Alice")["losses"], 1)
        self.assertEqual(a.profile()["voids_24h"], 1)

    def closed_game(self, quitter_first):
        # Alt+F4 mid-match (rematch-fix): the quitter's game exits with 7, its launcher reports "quit";
        # the opponent's game got BYE and reports a disconnect with peer_quit. A loss for the quitter,
        # not a void (the 0.1.9 test: a closed game used to run on and void the match as a desync).
        a, b, ea, eb = self.setup_match()
        if quitter_first:
            a.report_result(None, None, source="quit", reason="quit")
            b.report_result(None, None, source="disconnect", reason="peer_quit")
        else:
            b.report_result(None, None, source="disconnect", reason="peer_quit")
            a.report_result(None, None, source="quit", reason="quit")
        ev = expect(b, "match_result")
        self.assertEqual((ev["status"], ev["reason"], ev["winner"]), ("forfeit", "quit", eb["slot"]))
        ev = expect(a, "match_result")
        self.assertEqual(ev["blame"], "you")

    def test_closed_game_is_a_forfeit(self):
        self.closed_game(True)

    def test_closed_game_is_a_forfeit_whoever_reports_first(self):
        self.closed_game(False)

    def test_both_disconnect_is_void_without_blame(self):
        a, b, ea, eb = self.setup_match()
        a.report_result(None, None, source="disconnect")
        b.report_result(None, None, source="disconnect")
        ev = expect(a, "match_result")
        self.assertEqual((ev["status"], ev["reason"], ev["blame"]), ("void", "connection", None))

    def test_lone_report_against_own_interest_counts(self):
        a, b, ea, eb = self.setup_match()
        a.report_result(eb["slot"], None, source="game")      # "my opponent won", Bob never reports
        ev = expect(a, "match_result", timeout=10)
        self.assertEqual(ev["status"], "onesided")
        self.assertEqual(ev["winner"], eb["slot"])

    def test_lone_claim_against_an_online_opponent_is_void(self):
        a, b, ea, eb = self.setup_match()
        a.report_result(ea["slot"], None, source="game")      # "I won", Bob is online but silent
        ev = expect(a, "match_result", timeout=10)
        self.assertEqual((ev["status"], ev["reason"], ev["blame"]), ("void", "no_report", "opponent"))

    def test_lobby_drop_grace_then_forfeit(self):
        a, b, ea, eb = self.setup_match()
        b.reconnect_window = 0
        b._loop.call_soon_threadsafe(b._writer.transport.abort)     # Bob's launcher loses the lobby for good
        n = expect(a, "notice")
        self.assertEqual(n["code"], "opponent_dropped")
        ev = expect(a, "match_result", timeout=10)                 # grace (2 s in tests) runs out
        self.assertEqual((ev["status"], ev["reason"], ev["winner"]), ("forfeit", "disconnect", ea["slot"]))
        self.assertGreater(ev["rating"]["delta"], 0)

    def test_automatic_reconnect_keeps_the_match(self):
        a, b, ea, eb = self.setup_match()
        a._loop.call_soon_threadsafe(a._writer.transport.abort)     # Alice's connection breaks
        expect(a, "reconnecting")
        expect(a, "reconnected", timeout=15)
        self.assertEqual(self.player("Alice").status, "playing")
        w = ea["slot"]
        a.report_result(w, None, match_id=ea["match"])
        b.report_result(w, None)
        self.assertEqual(expect(a, "match_result")["status"], "confirmed")


class IntegrityMinLengthTest(Base):
    server_cfg = {"min_match_seconds": 30.0}

    def test_short_match_and_early_quit(self):
        a = self.acc("Alice")
        b = self.acc("Bob")
        ea, eb = self.ranked(a, b)
        a.report_result(ea["slot"], None, source="game")
        b.report_result(ea["slot"], None, source="game")
        ev = expect(a, "match_result")
        self.assertEqual((ev["status"], ev["reason"]), ("void", "too_short"))
        ea, eb = self.ranked(a, b)
        a.leave_match()                                          # quits right away
        ev = expect(b, "match_result")
        self.assertEqual((ev["status"], ev["reason"], ev["blame"]), ("void", "early_quit", "opponent"))


class PairCapTest(Base):
    server_cfg = {"pair_cap": 1}

    def test_second_ranked_match_of_a_pair_is_unranked(self):
        a = self.acc("Alice")
        b = self.acc("Bob")
        ea, eb = self.ranked(a, b)
        a.report_result(0, None)
        b.report_result(0, None)
        expect(a, "match_result")
        a.ranked_match()
        b.ranked_match()
        mf = expect(a, "match_found")
        self.assertFalse(mf["ranked"])
        self.assertEqual(expect(a, "notice")["code"], "pair_cap")


class RematchTest(Base):
    def finish(self, a, b, ea):
        a.report_result(ea["slot"], None)
        b.report_result(ea["slot"], None)
        return expect(a, "match_result"), expect(b, "match_result")

    def test_rematch_inside_the_running_games(self):
        a = self.acc("Alice")
        b = self.acc("Bob")
        ea, eb = self.ranked(a, b)
        ra, _ = self.finish(a, b, ea)
        self.assertGreater(ra["rematch_window"], 0)
        self.assertEqual(a.rematch(ra["match"], True, keep=True)["state"], "waiting")
        self.assertEqual(expect(b, "rematch")["state"], "offered")
        r = b.rematch(ra["match"], True, keep=True)
        self.assertEqual(r["state"], "accepted")
        s = expect(a, "match_start")
        self.assertTrue(s["continue"])
        self.assertIsNone(s.get("ticket"))
        self.assertEqual(s["rematch_of"], ra["match"])
        self.assertTrue(s["ranked"])
        self.assertEqual(self.player("Bob").status, "playing")

    def test_rematch_with_a_new_connection_and_decline(self):
        a = self.acc("Alice")
        b = self.acc("Bob")
        ea, eb = self.ranked(a, b)
        ra, _ = self.finish(a, b, ea)
        a.rematch(ra["match"], True, keep=False)
        b.rematch(ra["match"], True, keep=True)                  # one game is gone: connect again
        s = expect(a, "match_start")
        self.assertFalse(s["continue"])
        self.assertIsNotNone(s["ticket"])
        rb = self.finish(a, b, s)[0]
        b.rematch(rb["match"], False)
        self.assertEqual(expect(a, "rematch")["state"], "declined")


class RelayRematchTest(Base):
    server_cfg = {"force_relay": True, "rematch_window": 1.0}

    def test_continued_rematch_keeps_the_relay(self):
        a = self.acc("Alice")
        b = self.acc("Bob")
        ea, eb = self.ranked(a, b)
        self.assertEqual(ea["path"], "relay")
        a.report_result(0, None)
        b.report_result(0, None)
        ra = expect(a, "match_result")
        self.assertEqual(self.s.call(lambda: len(self.s.srv.udp.relays)), 1)    # still open after the match
        a.rematch(ra["match"], True, keep=True)
        b.rematch(ra["match"], True, keep=True)
        s = expect(a, "match_start")
        self.assertTrue(s["continue"])
        self.assertEqual(s["path"], "relay")
        time.sleep(6.5)                                                         # past window + 5 s
        self.assertEqual(self.s.call(lambda: len(self.s.srv.udp.relays)), 1)    # adopted by the rematch
        a.report_result(1, None)
        b.report_result(1, None)
        expect(a, "match_result")
        self.assertTrue(self.s.wait_for(lambda: len(self.s.srv.udp.relays) == 0, timeout=10))


class DriverTest(Base):
    """The launcher's glue with the stub game: launch, result file, report, rematch in the same game."""

    def launch_stub(self, d, extra):
        import subprocess

        class G:
            def __init__(self, env):
                self.log_path = os.path.join(d, f"game-{time.monotonic_ns()}.log")
                full = dict(os.environ, **extra)
                full.update(env)
                with open(self.log_path, "w") as lf:
                    self.proc = subprocess.Popen([sys.executable, STUB], env=full, stdout=lf, stderr=lf)

            def running(self):
                return self.proc.poll() is None

            def stop(self):
                if self.running():
                    self.proc.kill()
                    self.proc.wait(5)
        return G

    def run_pair(self, mode, extra1, extra2, matches=1):
        from t5lobby.match_driver import MatchDriver
        a = self.acc("Alice")
        b = self.acc("Bob")
        drivers = []
        for c, extra, n in ((a, extra1, "a"), (b, extra2, "b")):
            d = tempfile.mkdtemp(prefix=f"drv{n}")
            drivers.append(MatchDriver(c, self.launch_stub(d, extra), d, mode=mode, ask_manual=False,
                                       auto_rematch=matches - 1))
        a.ranked_match("lili")
        b.ranked_match("asuka")
        results = {0: [], 1: []}
        t_end = time.monotonic() + 40
        try:
            while time.monotonic() < t_end and min(len(results[0]), len(results[1])) < matches:
                for i, (c, drv) in enumerate(zip((a, b), drivers)):
                    while True:
                        ev = c.next_event(0)
                        if ev is None:
                            break
                        drv.on_event(ev)
                        if ev["t"] == "match_result":
                            results[i].append(ev)
                    drv.poll()
                time.sleep(0.05)
        finally:
            for drv in drivers:
                drv.close()
        return results, drivers

    def test_process_mode_with_rematch_in_the_same_game(self):
        stub = {"T5_STUB_SECONDS": "1", "T5_STUB_MATCHES": "2", "T5_STUB_GAP": "2", "T5_STUB_LINGER": "10"}
        results, drivers = self.run_pair("process", stub, stub, matches=2)
        self.assertEqual([r["status"] for r in results[0]], ["confirmed", "confirmed"])
        self.assertEqual(len(drivers[0].history), 2)
        self.assertEqual(drivers[0].history[0][1]["source"], "game")
        self.assertTrue(results[0][0]["fight"]["p1"] in ("lili", "asuka"))
        # the second fight went to the running game through T5_FIGHT_FILE (direct-fight's channel)
        with open(drivers[0].fight_path + ".done") as f:
            line = f.read().split(",")
        self.assertEqual(len(line), 4)
        self.assertEqual(set(line[:2]), {"33", "26"})              # Lili, Asuka

    def test_persistent_mode(self):
        stub = {"T5_STUB_SECONDS": "1"}
        results, drivers = self.run_pair("persistent", stub, stub, matches=2)
        self.assertEqual([r["status"] for r in results[0]], ["confirmed", "confirmed"])
        self.assertEqual(drivers[0].mode, "persistent")

    def test_no_result_file_falls_back_to_the_status(self):
        stub = {"T5_STUB_SECONDS": "1", "T5_STUB_NORESULT": "1", "T5_STUB_LINGER": "15"}
        results, drivers = self.run_pair("process", stub, stub)
        self.assertEqual((results[0][0]["status"], results[0][0]["reason"]), ("void", "no_result"))
        self.assertEqual(drivers[0].history[0][1]["reason"], "no_result")

    def test_lost_opponent_ends_the_match_as_a_disconnect(self):
        stub = {"T5_STUB_SECONDS": "2"}
        results, drivers = self.run_pair("process", dict(stub, T5_STUB_FAIL="lost"), stub)
        # void either way: "connection" when the other game also reports in time, "no_report" when
        # the test server's 2-s result window closes first (the other stub notices after 5 s)
        self.assertEqual(results[0][0]["status"], "void")
        self.assertEqual(drivers[0].history[0][1]["source"], "disconnect")
        self.assertEqual(drivers[0].history[0][1]["reason"], "peer_timeout")

    def test_desync_is_reported(self):
        stub = {"T5_STUB_SECONDS": "1"}
        results, _ = self.run_pair("process", dict(stub, T5_STUB_DESYNC="1"), stub)
        self.assertEqual((results[0][0]["status"], results[0][0]["reason"]), ("void", "desync"))


class SpeedAndKeyTest(Base):
    """Slow PCs (lockstep plays at the slower PC's speed) and the per-match netplay key."""

    def test_slow_pc_is_kept_out_of_ranked_and_warned(self):
        a = self.acc("Alice")
        b = self.acc("Bob")
        a.report_perf(31.2)
        self.assertTrue(self.s.wait_for(lambda: self.s.srv.by_name["alice"].fps == 31.2))
        with self.assertRaises(LobbyError) as cm:
            a.ranked_match()
        self.assertEqual(cm.exception.code, proto.E_NOT_ALLOWED)
        self.assertIn("31 fps", cm.exception.msg)
        # casual still works, and both players hear about the slow PC before the match
        a.quick_match()
        b.quick_match()
        na = expect(a, "notice")
        nb = expect(b, "notice")
        self.assertEqual(na["code"], "slow_pc")
        self.assertIn("your PC", na["msg"])
        self.assertIn("Alice's PC", nb["msg"])
        ea, eb = expect(a, "match_start"), expect(b, "match_start")
        self.assertEqual(eb["opponent"]["fps"], 31.2)

    def test_fast_enough_pc_plays_ranked(self):
        a = self.acc("Alice")
        a.report_perf(58.0)
        self.assertTrue(self.s.wait_for(lambda: self.s.srv.by_name["alice"].fps == 58.0))
        self.assertEqual(a.ranked_match()["mode"], "ranked")

    def test_match_key_reaches_the_game_environment(self):
        a = self.acc("Alice")
        b = self.acc("Bob")
        ea, eb = self.ranked(a, b)
        self.assertEqual(len(ea["key"]), 32)
        self.assertEqual(ea["key"], eb["key"])
        env = ea["ticket"].game_env()
        self.assertEqual(env["T5_NET_KEY"], ea["key"])


class DriverResultFileTest(unittest.TestCase):
    """The match driver against result files the game left behind (no server needed)."""

    class FakeClient:
        def __init__(self):
            self.reports, self.perf = [], []

        def report_result(self, winner, score=None, match_id=None, **kw):
            self.reports.append(dict(kw, match=match_id, winner=winner, score=score))

        def report_perf(self, fps):
            self.perf.append(fps)

        def game_started(self, mid):
            pass

        def leave_match(self, mid):
            pass

    class FakeGame:
        def __init__(self):
            self.alive = True
            self.log_path = None
            self.proc = None

        def running(self):
            return self.alive

        def stop(self):
            self.alive = False

    class Ticket:
        def __init__(self, mid):
            self.match_id, self.slot, self.role, self.delay = mid, 0, "host", 3
            self.opponent, self.path, self.rtt_ms = {"name": "Bob"}, "lan", 1.0

        def game_env(self, result_file=None):
            return {"T5_NET_RESULT_FILE": result_file}

        def summary(self):
            return "Bob"

    def setUp(self):
        from t5lobby.match_driver import MatchDriver
        self.dir = tempfile.mkdtemp(prefix="drvres")
        self.client = self.FakeClient()
        self.game = self.FakeGame()
        self.drv = MatchDriver(self.client, lambda env: self.game, self.dir, mode="process", ask_manual=False)
        fight = {"p1": "lili", "p2": "asuka", "stage": "s20", "rounds": 3}
        self.drv.on_event({"t": "match_start", "match": "m1", "ticket": self.Ticket("m1"), "fight": fight,
                           "opponent": {"name": "Bob"}, "slot": 0})

    def write(self, d):
        with open(self.drv.result_path, "w") as f:
            json.dump(d, f)

    def test_result_of_another_match_is_not_reported(self):
        self.write({"match": "m0", "winner": 0, "score": [3, 1]})
        self.drv.poll()
        self.assertEqual(self.client.reports, [])
        self.assertFalse(os.path.exists(self.drv.result_path))           # moved aside
        self.write({"match": "m1", "winner": 1, "score": [2, 3], "desync": 0, "hash": "ab", "frames": 9000,
                    "fps": 57.5})
        self.drv.poll()
        self.assertEqual(len(self.client.reports), 1)
        r = self.client.reports[0]
        self.assertEqual((r["match"], r["winner"], r["source"], r["hash"]), ("m1", 1, "game", "ab"))
        self.assertEqual(self.client.perf, [57.5])

    def test_voided_match_leaves_no_result_for_the_rematch(self):
        # the lobby voids m1 on the opponent's report; our game writes m1's result afterwards
        self.drv.on_event({"t": "match_result", "match": "m1", "status": "void", "reason": "desync"})
        self.write({"match": "m1", "winner": 0, "score": [3, 0]})
        fight = {"p1": "lili", "p2": "asuka", "stage": "s20", "rounds": 3}
        self.drv.on_event({"t": "match_start", "match": "m2", "continue": True, "fight": fight,
                           "opponent": {"name": "Bob"}, "slot": 0})
        self.drv.poll()
        self.assertEqual(self.client.reports, [])
        with open(self.drv.fight_path) as f:
            self.assertTrue(f.read().strip().endswith("match=m2"))
        self.write({"match": "m1", "winner": 0, "score": [3, 0]})        # late again: still refused
        self.drv.poll()
        self.assertEqual(self.client.reports, [])
        self.write({"match": "m2", "winner": 0, "score": [3, 2]})
        self.drv.poll()
        self.assertEqual([(r["match"], r["winner"]) for r in self.client.reports], [("m2", 0)])

    def test_reason_means_disconnect(self):
        self.write({"match": "m1", "winner": None, "score": [1, 0], "reason": "peer_timeout"})
        self.drv.poll()
        r = self.client.reports[0]
        self.assertEqual((r["source"], r["reason"], r["winner"]), ("disconnect", "peer_timeout", None))

    def test_exit_code_of_a_lost_session_is_not_a_crash(self):
        class Proc:
            returncode = 3
        self.game.proc = Proc()
        self.game.alive = False
        self.drv.poll()
        r = self.client.reports[0]
        self.assertEqual((r["source"], r["reason"]), ("disconnect", "peer_lost"))

    def test_a_game_that_gave_up_its_reset_is_not_a_crash(self):
        # exit code 6: the persistent game's reset for this match was stuck for 60 s and it ended itself
        # (e2e: the match was voided as this player's crash -- a strike -- before the fight even started)
        class Proc:
            returncode = 6
        self.game.proc = Proc()
        self.game.alive = False
        self.drv.poll()
        r = self.client.reports[0]
        self.assertEqual((r["source"], r["reason"]), ("disconnect", "game_stuck"))

    def test_closed_window_is_a_quit(self):
        # Alt+F4 / the X button / Esc mid-match: the game writes "quit", tells the peer and exits with 7
        self.write({"match": "m1", "winner": None, "score": [1, 0], "reason": "quit"})
        class Proc:
            returncode = 7
        self.game.proc = Proc()
        self.game.alive = False
        self.drv.poll()
        self.assertEqual(len(self.client.reports), 1)
        r = self.client.reports[0]
        self.assertEqual((r["source"], r["reason"]), ("quit", "quit"))

    def test_closed_window_without_result_file_is_a_quit(self):
        class Proc:
            returncode = 7
        self.game.proc = Proc()
        self.game.alive = False
        self.drv.poll()
        r = self.client.reports[0]
        self.assertEqual((r["source"], r["reason"]), ("quit", "quit"))

    def test_closed_window_after_the_ko_keeps_the_result(self):
        # closed after the match was decided: the game's result stands (no quit)
        self.write({"match": "m1", "winner": 0, "score": [3, 1], "desync": 0, "hash": "cd", "frames": 7000})
        class Proc:
            returncode = 7
        self.game.proc = Proc()
        self.game.alive = False
        self.drv.poll()
        r = self.client.reports[0]
        self.assertEqual((r["source"], r["winner"]), ("game", 0))



if __name__ == "__main__":
    unittest.main()
