"""Jinpachi and the random cell online by match kind, Mokujin and Random different every match, offline random at every
start (docs/DIRECTFIGHT.md "Unlocks", docs/NETPLAY.md "Desync hunt": the select pin). No game: the launcher's and the
lobby's halves run, the game's are checked in its source, and the seeds are computed the way t5_hooks.cpp does.

- T5_NET_UNLOCKS comes from the lobby's match_start event (handover.match_unlocks), the same on both PCs: "open" for
  casual quick matches, rooms and invites, "closed" for ranked matches and tournament sets; an old/absent value is
  closed in the game.
- The select screen's generator is pinned to (session seed ^ 0x7E1EC7ED) + k * 0x9E3779B9, k = the fights the
  session has started (both PCs count them at FIGHT START); k = 0 is 1.1.3's seed, so format-3 replays play back
  with k forced to 0.
- Offline: one OS-random seed at boot; T5_OFFLINE_SEED=<n> fixed (pinned at the select screens), =0 off."""
import os
import re
import sys
import unittest

from helpers import ROOT

sys.path.insert(0, os.path.join(ROOT, "lobby"))
from t5lobby import handover  # noqa: E402
from t5lobby.handover import MatchTicket, match_unlocks  # noqa: E402


def text(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


def select_seed(session_seed, k):
    """t5_hooks.cpp select_seed(): the seed the select screen's TLS generator is pinned to."""
    return ((session_seed ^ 0x7E1EC7ED) + k * 0x9E3779B9) & 0xFFFFFFFF


class MatchKind(unittest.TestCase):
    def test_casual_rooms_invites_open(self):
        for ev in ({"ranked": False, "set": None}, {"ranked": False, "set": {"id": "s1", "game": 1, "ranked": False}},
                   {"ranked": False, "origin": "invite"}, {"ranked": False, "room": {"id": "r1"}}):
            self.assertEqual(match_unlocks(ev), "open", ev)

    def test_ranked_and_tournaments_closed(self):
        for ev in ({"ranked": True}, {"ranked": True, "set": {"locked": True}},
                   {"ranked": False, "set": {"tournament": {"id": "t1", "name": "Cup"}}},
                   {"ranked": True, "set": {"tournament": {"id": "t1"}}}, None, "x"):
            self.assertEqual(match_unlocks(ev), "closed", ev)

    def test_ticket_env_both_sides_the_same(self):
        def ticket(role, slot, unlocks):
            return MatchTicket("m1", role, slot, 50000 + slot, ("203.0.113.9", 50000), "direct", 30.0, 1.0, 2,
                               unlocks=unlocks)
        for kind in ("open", "closed"):
            envs = [ticket("host", 0, kind).game_env(), ticket("join", 1, kind).game_env()]
            self.assertEqual({e["T5_NET_UNLOCKS"] for e in envs}, {kind})
        # anything but "open" goes to the game as closed; a ticket made without it (an old caller) is closed
        self.assertEqual(ticket("host", 0, "weird").game_env()["T5_NET_UNLOCKS"], "closed")
        self.assertEqual(MatchTicket("m1", "host", 0, 1, ("h", 1), "lan", 1.0, 0.0, 2).game_env()["T5_NET_UNLOCKS"],
                         "closed")

    def test_client_takes_it_from_the_event_not_a_setting(self):
        src = text("lobby", "t5lobby", "client.py")
        self.assertIn("unlocks=match_unlocks(msg)", src)
        self.assertNotIn("unlock_jinpachi", src)
        self.assertIn('"boss_chars"', src)

    def test_documented(self):
        self.assertIn("T5_NET_UNLOCKS", handover.__doc__)
        self.assertIn("T5_NET_UNLOCKS", text("docs", "DIRECTFIGHT.md"))
        self.assertIn("tournament", text("docs", "DIRECTFIGHT.md").split("## Unlocks", 1)[1].split("\n## ", 1)[0])


class GameSide(unittest.TestCase):
    def test_unlock_answer(self):
        src = text("src", "directfight", "df_unlock.cpp")
        self.assertIn('getenv("T5_NET_UNLOCKS")', src)
        self.assertIn('!_stricmp(u, "open")', src)                   # anything else (absent, old) = closed
        self.assertIn('env_on("T5_UNLOCK_JINPACHI")', src)
        self.assertIn("t5_replay_unlocks_open()", src)               # a playback: the file's answer
        # the stages stay as a fresh save online, whatever the kind
        self.assertRegex(src, r"Mode::Fixed\) r = \(mask & kFlagJinpachi\) && online_open\(\)")

    def test_persistent_session_sets_it_before_the_grid(self):
        src = text("src", "directfight", "df_fight.cpp")
        self.assertIn('"T5_NET_UNLOCKS"', src)
        self.assertIn("regrid = t5_unlock_set_open(", src)
        self.assertIn("!g_fresh || regrid) go_reset(f);", src)
        # the open grid: the random cell 24, Jinpachi 35, the top row 12 cells
        self.assertIn("kRandomCell = 24, kJinpachiCell = 35", src)
        self.assertIn("const int n = top10 ? 10 : 12", src)

    def test_select_pin_mixes_the_match_number(self):
        src = text("src", "netplay", "t5_hooks.cpp")
        self.assertIn("(np::session_seed() ^ 0x7E1EC7EDu) + k * 0x9E3779B9u", src)
        self.assertIn("if (np::replaying() && !rp::play_select_mix()) k = 0;", src)
        self.assertIn("t5_df_session_matches()", src)
        self.assertIn("g_session_matches++;", text("src", "directfight", "df_fight.cpp"))

    def test_seeds_differ_every_match_and_session(self):
        seen = set()
        for sess in (1000 + 7919 * k for k in range(1, 6)):        # pick_flow_test's session seeds
            for k in range(12):
                seen.add(select_seed(sess, k))
        self.assertEqual(len(seen), 60)
        # the first match of a session keeps 1.1.3's seed (format-3 replays: every match)
        self.assertEqual(select_seed(8919, 0), 8919 ^ 0x7E1EC7ED)

    def test_offline_seed(self):
        src = text("src", "netplay", "t5_hooks.cpp")
        m = re.search(r"void offline_seed\(\)\n\{(.*?)\n\}", src, re.S)
        self.assertTrue(m)
        body = m.group(1)
        for k in ("T5_FIGHT", "T5_FIGHT_FILE", "T5_REPLAY_FILE", "T5_OFFLINE_SEED"):
            self.assertIn(f'"{k}"', body)
        self.assertIn("BCryptGenRandom", body)
        self.assertIn("rb::tls_rand_reseed(g_main_tls, seed, true)", body)
        # only where the game runs offline (no T5_NET_MODE / T5_CTL_DIR), once
        self.assertIn("if (!g_offline_seeded && g_main_tls) offline_seed();", src)

    def test_replay_format_4(self):
        src = text("src", "netplay", "replay.cpp")
        self.assertIn("constexpr uint32_t kVersion = 4;", src)
        self.assertIn("d.select_mix = ver >= 4 && (hf & kFlagSelectMix);", src)
        self.assertIn("d.unlocks_open = ver >= 4 && (hf & kFlagUnlocksOpen);", src)


class Lobby(unittest.TestCase):
    def test_server_takes_jinpachi_in_casual_only(self):
        src = text("lobby", "t5lobby", "server", "lobby.py")
        self.assertIn('"boss_chars"', src)
        self.assertIn('boss_ok = not m.ranked and not (m.set is not None and "tournament" in m.set.info())', src)

    def test_launcher_reports_jinpachi_only_where_offered(self):
        import types
        from t5lobby import fighters
        from t5lobby.match_driver import MatchDriver
        table = fighters.Table()

        def drv(ev, caps):
            ns = types.SimpleNamespace(table=table, match_ev=ev,
                                       client=types.SimpleNamespace(welcome={"caps": caps}))
            ns._boss_ok = lambda: MatchDriver._boss_ok(ns)
            return lambda fid: MatchDriver._key(ns, fid)
        casual, ranked = {"ranked": False}, {"ranked": True}
        tour = {"ranked": False, "set": {"tournament": {"id": "t"}}}
        self.assertEqual(drv(casual, ["boss_chars"])(35), "jinpachi")
        self.assertIsNone(drv(casual, [])(35))                      # a 1.1.3 server would refuse the whole result
        self.assertIsNone(drv(ranked, ["boss_chars"])(35))
        self.assertIsNone(drv(tour, ["boss_chars"])(35))
        self.assertEqual(drv(ranked, [])(9), "jin")

    def test_fighter_table(self):
        from t5lobby import fighters
        t = fighters.Table()
        j = t.fighter_by_id(35)
        self.assertEqual((j["key"], j["code"], j.get("boss")), ("jinpachi", "jnp", True))
        self.assertFalse(t.valid_fighter("jinpachi"))                # never a launcher/ranked pick or a random one


if __name__ == "__main__":
    unittest.main()
