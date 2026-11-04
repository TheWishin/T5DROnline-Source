"""The launcher side of search options and Remove my data, without windows: what is sent, what is listed, what goes
(tk_search.py, tk_forget.py, netinfo.py, client.py)."""
import os
import tempfile
import unittest

import util  # noqa: F401 -- sys.path
from t5lobby import netinfo, tk_forget, tk_search
from t5lobby.client import LobbyClient
from util import BUILD


class SearchTest(unittest.TestCase):
    def test_options_and_summary(self):
        self.assertEqual(tk_search.options({}), {"max_ping": None, "no_wifi": False, "steady": False})
        cfg = {"max_ping": 100, "no_wifi": True, "steady": True}
        self.assertEqual(tk_search.options(cfg), cfg)
        self.assertEqual(tk_search.options({"max_ping": 55})["max_ping"], None)
        self.assertEqual(tk_search.summary(cfg), "ping up to 100 ms, no Wi-Fi, steady 60 fps")
        self.assertEqual(tk_search.summary({}), "")

    def test_netinfo_message(self):
        m = tk_search.netinfo_msg({"area": "eu", "lang": "ko"}, wifi=True)
        self.assertEqual(m, {"wifi": True, "area": "eu", "lang": "ko"})
        m = tk_search.netinfo_msg({"area": "moon", "lang": "xx"}, wifi="?")
        self.assertEqual((m["wifi"], m["area"]), (None, "auto"))
        self.assertIn(m["lang"], dict(netinfo.LANGS))

    def test_where_text(self):
        self.assertEqual(tk_search.where_text({"area": "na", "lang": "pt-BR"}), "NA pt-BR")
        self.assertEqual(tk_search.where_text({}), "")

    def test_client_sends_options_only_to_a_server_that_has_them(self):
        c = LobbyClient("127.0.0.1:1", BUILD)
        c.welcome = {"features": []}
        self.assertEqual(c._search_options({"t": "queue"}, {"max_ping": 60, "no_wifi": True}), {"t": "queue"})
        c.welcome = {"features": ["mm_filters"]}
        self.assertEqual(c._search_options({"t": "queue"}, {"max_ping": 60, "no_wifi": True, "steady": False}),
                         {"t": "queue", "max_ping": 60, "no_wifi": True})
        self.assertIsNone(LobbyClient("127.0.0.1:1", BUILD).send_netinfo(True))     # (no welcome: nothing sent)

    def test_wifi_detection(self):
        self.assertTrue(netinfo.on_wifi(lambda: 7, lambda: {7: netinfo.IF_TYPE_IEEE80211, 3: 6}))
        self.assertFalse(netinfo.on_wifi(lambda: 3, lambda: {7: 71, 3: 6}))
        self.assertIsNone(netinfo.on_wifi(lambda: None, lambda: {}))
        self.assertIsNone(netinfo.on_wifi(lambda: 9, lambda: {7: 71}))
        self.assertIn(netinfo.on_wifi(), (True, False, None))       # the real one never raises


class ForgetLocalTest(unittest.TestCase):
    def test_lists_only_online_data_and_removes_it(self):
        with tempfile.TemporaryDirectory() as d:
            out, rep, cfg_dir = (os.path.join(d, x) for x in ("native", "myreplays", "cfg"))
            for p in (os.path.join(out, "logs"), os.path.join(out, "gamedata-online", "SAVE"), os.path.join(out, "gamedata"),
                      rep, cfg_dir):
                os.makedirs(p)
            files = {os.path.join(cfg_dir, "online.json"): "{}", os.path.join(rep, "a.t5replay"): "x",
                     os.path.join(rep, "keep.txt"): "mine", os.path.join(out, "logs", "game-1.log"): "log",
                     os.path.join(out, "logs", "warmup.skip"): "", os.path.join(out, "rb_cost.txt"): "1,2,3,1",
                     os.path.join(out, "gamedata-online", "SAVE", "x.bin"): "s",
                     os.path.join(out, "gamedata", "offline.bin"): "o"}
            for p, text in files.items():
                with open(p, "w") as f:
                    f.write(text)
            items = tk_forget.local_items(os.path.join(cfg_dir, "online.json"), out, rep)
            self.assertEqual([k for k, *_ in items], ["online", "replays", "logs", "save", "cost"])
            paths = [p for _k, _l, ps, _s in items for p in ps]
            removed, failed = tk_forget.remove_paths(paths)
            self.assertEqual((removed, failed), (len(paths), []))
            self.assertTrue(os.path.exists(os.path.join(rep, "keep.txt")))              # not a replay: stays
            self.assertTrue(os.path.exists(os.path.join(out, "logs", "warmup.skip")))   # not a log: stays
            self.assertTrue(os.path.exists(os.path.join(out, "gamedata", "offline.bin")))  # the offline save stays
            self.assertFalse(os.path.exists(os.path.join(out, "gamedata-online")))
            self.assertEqual(tk_forget.local_items(os.path.join(cfg_dir, "online.json"), out, rep), [])

    def test_human(self):
        self.assertEqual(tk_forget.human(10), "10 bytes")
        self.assertEqual(tk_forget.human(2048), "2.0 KB")


if __name__ == "__main__":
    unittest.main()
