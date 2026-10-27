"""The profile's match history with a replay button (tk_history.py, 1.1.5): your own matches that have a replay on
this PC are marked, Watch replay plays one through the launcher's Replays tab; someone else's profile and an Online
tab without the launcher show no button."""
import time
import unittest

from util import client

try:
    import tkinter as tk
    from test_tk_tab import TkBase
    from t5lobby import tk_history
except ImportError:      # pragma: no cover
    tk = None
    TkBase = unittest.TestCase


class FakeEntry:
    fighters = "Jin vs Marshall Law"


class FakeReplays:
    """The launcher's Replays tab as far as the profile uses it."""
    def __init__(self):
        self.asked, self.watched = [], []

    def for_history(self, h, ids):
        self.asked.append((h["match"], ids.get(h["you_char"]), ids.get(h["opp_char"])))
        return FakeEntry() if h["opponent"] == "Rival" else None

    def watch_entry(self, e):
        self.watched.append(e)


@unittest.skipIf(tk is None, "no tkinter")
class HistoryReplayTest(TkBase):
    def match(self, n, opp, ago, aid, winner=0):
        st = self.s.srv.store
        st.save_match({"id": f"m{n:012d}", "created": time.time() - ago - 90, "ended": time.time() - ago,
                       "ranked": False, "p1_name": "Champ", "p2_name": opp, "p1_account": aid, "status": "confirmed",
                       "winner": winner, "score": [3, 1] if winner == 0 else [1, 3], "p1_char": "jin",
                       "p2_char": "law"})

    def login(self):
        c = client(self.s, "Champ", password="champ-pw1", register=True)
        c.close()
        aid = self.s.call(lambda: self.s.srv.store.account("Champ")["id"])
        self.s.call(lambda: (self.match(1, "Rival", 600, aid), self.match(2, "Other", 60, aid, winner=1)))
        tab = self.tab
        tab.server_var.set(self.s.addr)
        tab.name_var.set("Champ")
        tab.pw_var.set("champ-pw1")
        tab.do_login("account")
        self.pump(lambda: tab.client is not None and tab.client.me is not None)
        return tab

    def test_own_matches_with_a_replay_can_be_watched(self):
        self.app.replays = rp = FakeReplays()
        tab = self.login()
        tab.show_profile(None)
        self.pump(lambda: len(tab.tv_hist.get_children()) == 2 and tab.history.rows)
        tv, ui = tab.tv_hist, tab.history
        rows = tv.get_children()
        self.assertEqual({a[1:] for a in rp.asked}, {(9, 1)})                 # Jin 9, Law 1 (the replay's ids)
        by_opp = {tv.item(i, "values")[2]: i for i in rows}
        self.assertTrue(str(tv.item(by_opp["Rival"], "values")[0]).startswith(tk_history.MARK))
        self.assertFalse(str(tv.item(by_opp["Other"], "values")[0]).startswith(tk_history.MARK))
        self.assertEqual(tv.item(by_opp["Rival"], "tags"), ("won",))            # the server says win / loss
        self.assertEqual(tv.item(by_opp["Other"], "tags"), ("lost",))
        self.assertEqual(ui.bar.winfo_manager(), "grid")
        self.assertIn("1 of these matches", ui.hint.get())
        self.assertEqual(str(ui.btn.cget("state")), "disabled")
        tv.selection_set(by_opp["Other"])
        self.root.update()
        self.assertEqual(str(ui.btn.cget("state")), "disabled")
        self.assertIn("No replay", ui.hint.get())
        tv.selection_set(by_opp["Rival"])
        self.root.update()
        self.assertEqual(str(ui.btn.cget("state")), "normal")
        ui.btn.invoke()
        self.assertEqual(len(rp.watched), 1)

    def test_no_button_without_the_launcher_or_on_another_profile(self):
        tab = self.login()                                       # (FakeApp: no Replays tab)
        tab.show_profile(None)
        self.pump(lambda: len(tab.tv_hist.get_children()) == 2 and tab.history.rows)
        self.assertEqual(tab.history.bar.winfo_manager(), "")
        self.app.replays = rp = FakeReplays()
        other = client(self.s, "Viewer", password="viewer-pw1", register=True)
        other.close()
        tab.show_profile("Viewer")
        self.pump(lambda: "Viewer" in tab.prof_title.get())
        self.root.update()
        self.assertEqual(tab.history.bar.winfo_manager(), "")
        self.assertEqual(rp.asked, [])


if __name__ == "__main__":
    unittest.main()
