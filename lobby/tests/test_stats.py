"""The Online tab's stats page (1.1.5): the server's read-only `stats` request -- totals and every fighter's matches
and wins, ranked and casual apart -- its cache, and the page in the launcher (tk_stats.py)."""
import os
import tempfile
import time
import unittest

import util
from util import ServerThread, client
from t5lobby.server import lobby as lobby_mod
from t5lobby.server.store import Store

NOW = 1_800_000_000.0


def match(n, p1, p2, c1, c2, winner, ranked=False, status="confirmed", ago=3600.0):
    return {"id": f"m{n:012d}", "created": NOW - ago - 60, "ended": NOW - ago, "ranked": ranked, "p1_name": p1,
            "p2_name": p2, "status": status, "winner": winner, "p1_char": c1, "p2_char": c2}


def fill(st):
    st.create_account("Alice", "x")
    st.create_account("Bob", "x")
    st.create_account("Idle", "x")
    for m in (match(1, "Alice", "Bob", "jin", "law", 0, ranked=True),
              match(2, "Alice", "Bob", "jin", "law", 1, ranked=True, ago=2 * 86400),
              match(3, "alice", "Guest7", "jin", "jin", 0),                      # a mirror: one win, one loss
              match(4, "Bob", "Guest7", "law", "nina", None),                    # a draw
              match(5, "Bob", "Carol", "law", "nina", 0, status="void"),          # not counted
              match(6, "Bob", "Dave", "law", "nina", None, status="playing")):   # not counted
        st.save_match(m)


class StoreTest(unittest.TestCase):
    def test_totals_and_fighters(self):
        st = Store(":memory:")
        fill(st)
        s = st.community_stats(NOW)
        self.assertEqual((s["accounts"], s["players"], s["matches"], s["ranked"]), (3, 3, 4, 2))
        self.assertEqual((s["matches_24h"], s["players_24h"]), (3, 3))
        f = {r["char"]: r for r in s["fighters"]}
        self.assertEqual(f["jin"], {"char": "jin", "ranked": [2, 1, 0], "casual": [2, 1, 0]})
        self.assertEqual(f["law"], {"char": "law", "ranked": [2, 1, 0], "casual": [1, 0, 1]})
        self.assertEqual(f["nina"], {"char": "nina", "ranked": [0, 0, 0], "casual": [1, 0, 1]})
        self.assertEqual([r["char"] for r in s["fighters"]], ["jin", "law", "nina"])       # most played first
        self.assertEqual(s["made"], NOW)

    def test_empty(self):
        s = Store(":memory:").community_stats(NOW)
        self.assertEqual((s["accounts"], s["players"], s["matches"], s["ranked"], s["fighters"]), (0, 0, 0, 0, []))


class ServerTest(unittest.TestCase):
    def setUp(self):
        self.s = ServerThread().start()
        self.clients = []

    def tearDown(self):
        for c in self.clients:
            c.close()
        self.s.stop()

    def test_request_is_cached_and_read_only(self):
        self.s.call(lambda: fill(self.s.srv.store))
        c = client(self.s, "Viewer")
        self.clients.append(c)
        self.assertTrue(c.has_stats)
        r = c.stats()
        self.assertEqual((r["t"], r["matches"], r["ranked"]), ("stats", 4, 2))
        self.assertEqual(len(r["fighters"]), 3)
        self.s.call(lambda: self.s.srv.store.save_match(match(9, "Eve", "Bob", "lili", "law", 0)))
        self.assertEqual(c.stats()["matches"], 4)                                # from the cache
        self.s.call(lambda: setattr(self.s.srv, "_stats_cache", (time.monotonic() - lobby_mod.STATS_SECONDS - 1,
                                                                 self.s.srv._stats_cache[1])))
        self.assertEqual(c.stats()["matches"], 5)                                # computed again after it

    def test_old_server_has_no_stats(self):
        orig = lobby_mod.FEATURES
        lobby_mod.FEATURES = [f for f in orig if f != "stats"]
        try:
            c = client(self.s, "Viewer")
            self.clients.append(c)
            self.assertFalse(c.has_stats)
        finally:
            lobby_mod.FEATURES = orig


class RowsTest(unittest.TestCase):
    def test_modes_and_sorting(self):
        from t5lobby import tk_stats
        f = [{"char": "jin", "ranked": [10, 9, 0], "casual": [40, 10, 2]},
             {"char": "law", "ranked": [40, 30, 0], "casual": [0, 0, 0]},
             {"char": "nina", "ranked": [0, 0, 0], "casual": [5, 5, 0]},
             {"char": "bad", "ranked": "x"}]                                   # (a damaged row is left out)
        self.assertEqual(tk_stats.rows_for(f, "all"), [("jin", 50, 19, 2), ("law", 40, 30, 0), ("nina", 5, 5, 0)])
        self.assertEqual(tk_stats.rows_for(f, "ranked"), [("law", 40, 30, 0), ("jin", 10, 9, 0)])
        self.assertEqual(tk_stats.rows_for(f, "casual"), [("jin", 40, 10, 2), ("nina", 5, 5, 0)])
        # best win rate first; under 30 matches after the others (5 of 5 is not much to go on)
        self.assertEqual([r[0] for r in tk_stats.rows_for(f, "all", "winrate")], ["law", "jin", "nina"])
        self.assertIsNone(tk_stats.rate(0, 0))
        self.assertEqual(tk_stats.rate(1, 3), 33)


try:
    import tkinter as tk
    from test_tk_tab import TkBase
except ImportError:      # pragma: no cover
    tk = None
    TkBase = unittest.TestCase


@unittest.skipIf(tk is None, "no tkinter")
class PageTest(TkBase):
    def test_page_shows_the_numbers(self):
        tab = self.tab
        self.s.call(lambda: fill(self.s.srv.store))
        tab.server_var.set(self.s.addr)
        tab.name_var.set("Viewer")
        tab.do_login("guest")
        self.pump(lambda: tab.client is not None and tab.client.me is not None)
        tab.nb.select(tab.stats_page)
        self.pump(lambda: len(tab.stats.tv.get_children()) == 3)
        st = tab.stats
        self.assertEqual(st.tile_vars["matches"].get(), "4")
        self.assertEqual(st.tile_vars["ranked"].get(), "2")
        self.assertEqual(st.tile_vars["accounts"].get(), "3")
        first = st.tv.item(st.tv.get_children()[0], "values")
        self.assertEqual([str(v) for v in first[1:4]], ["4", "2", "50 %"])         # jin: 4 matches, 2 wins
        self.assertIn("few", st.tv.item(st.tv.get_children()[0], "tags"))          # (under 30 matches: grey)
        st.mode_var.set("ranked")
        st.fill()
        self.assertEqual(len(st.tv.get_children()), 2)                            # nina never played ranked
        st.sort_by("fighter")
        names = [st.tv.item(i, "values")[0] for i in st.tv.get_children()]
        self.assertEqual(names, sorted(names, key=str.lower))
        asked = st.asked
        st.shown()                                                                # fresh: not asked again
        self.assertEqual(st.asked, asked)

    def test_older_server_says_so(self):
        tab = self.tab
        orig = lobby_mod.FEATURES
        lobby_mod.FEATURES = [f for f in orig if f != "stats"]
        try:
            tab.server_var.set(self.s.addr)
            tab.name_var.set("Viewer")
            tab.do_login("guest")
            self.pump(lambda: tab.client is not None and tab.client.me is not None)
        finally:
            lobby_mod.FEATURES = orig
        tab.nb.select(tab.stats_page)
        self.pump(lambda: "1.1.5" in tab.stats.made_var.get())
        self.assertEqual(tab.stats.tv.get_children(), ())


if __name__ == "__main__":
    unittest.main()
