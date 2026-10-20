"""The Online tab and a server restart (an update, docs/HOSTING.md "Updates and restarts"):

1. after the restart the tab logs in again by itself with the saved login (the server forgot the session, so the
   client could not resume it): account players are not left at the login screen
2. a server that cannot be reached (restarting, an outage) does not delete the saved login -- only the server's
   "no" does
3. no automatic login after being removed (another login of the same account, a ban)
"""
import json
import os
import socket
import tempfile
import time
import unittest

import util  # noqa: F401
from util import BUILD, ServerThread, client
from test_tk_tab import TkBase, tk

try:
    from t5lobby.tk_tab import OnlineTab
except ImportError:      # pragma: no cover
    OnlineTab = None


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@unittest.skipIf(tk is None, "no tkinter")
class ReloginTest(TkBase):
    def setUp(self):
        self.db = os.path.join(tempfile.mkdtemp(), "t5lobby.db")
        self.server_cfg = {"db": self.db, "port": free_port()}
        super().setUp()
        self.tab.RELOGIN_FIRST, self.tab.RELOGIN_EVERY = 0.3, 1.0

    def register(self, name="Riko"):
        tab = self.tab
        tab.server_var.set(self.s.addr)
        tab.name_var.set(name)
        tab.pw_var.set("secret-pw1")
        tab.ask_string = lambda *a, **k: "secret-pw1"
        tab.do_login("register")
        self.pump(lambda: tab.client is not None and tab.client.me is not None)
        self.pump(lambda: tab.codes_window is not None)
        tab.codes_window.destroy()
        return tab.client

    def saved_token(self):
        with open(os.path.join(os.environ["T5_ONLINE_DIR"], "online.json")) as f:
            return json.dumps(json.load(f).get("sessions") or {})

    def restart_server(self, down=0.0):
        self.s.stop()
        time.sleep(down)
        self.s = ServerThread(**dict(self.server_cfg)).start()

    def test_logs_in_again_by_itself_after_a_server_restart(self):
        tab = self.tab
        first = self.register()
        self.restart_server()
        self.pump(lambda: tab.client is not None and tab.client is not first and tab.client.me is not None, 30)
        self.assertEqual(tab.client.me["name"], "Riko")
        self.assertIn("saved login", tab.status_var.get())
        self.assertTrue(self.s.call(lambda: "riko" in self.s.srv.by_name))
        self.assertIsNone(tab._relogin_at)

    def test_keeps_trying_while_the_server_is_away_and_keeps_the_saved_login(self):
        tab = self.tab
        first = self.register()
        token = self.saved_token()
        self.s.stop()
        self.pump(lambda: tab.client is None and tab._relogin_n >= 2, 90)      # tried, could not reach it
        self.assertEqual(self.saved_token(), token)                         # the saved login is still there
        self.s = ServerThread(**dict(self.server_cfg)).start()
        self.pump(lambda: tab.client is not None and tab.client is not first and tab.client.me is not None, 30)
        self.assertEqual(tab.client.me["name"], "Riko")

    def test_a_launcher_started_while_the_server_is_down_keeps_the_saved_login(self):
        self.register()
        token = self.saved_token()
        self.tab.on_close()
        self.s.stop()
        tab2 = OnlineTab(self.root, self.app)
        tab2._build_info = lambda: (BUILD, None)
        self.tab = tab2
        tab2.on_show()                                                      # tries the saved login: no server
        self.pump(lambda: not tab2._login_busy and tab2._auto_tried, 30)
        self.assertIsNone(tab2.client)
        self.assertEqual(self.saved_token(), token)
        self.assertNotIn("expired", tab2.status_var.get())
        self.s = ServerThread(**dict(self.server_cfg)).start()

    def test_an_expired_saved_login_is_forgotten(self):
        self.register()
        self.s.call(lambda: self.s.srv.store.db.execute("DELETE FROM sessions"))   # (the server forgot it)
        self.s.call(lambda: self.s.srv.store.flush())
        self.tab.on_close()
        tab2 = OnlineTab(self.root, self.app)
        tab2._build_info = lambda: (BUILD, None)
        self.tab = tab2
        tab2.on_show()
        self.pump(lambda: "expired" in tab2.status_var.get(), 30)
        self.assertEqual(self.saved_token(), "{}")

    def test_no_automatic_login_after_being_removed(self):
        tab = self.tab
        self.register()
        other = client(self.s, "Riko", password="secret-pw1")              # the same account logs in elsewhere
        self.other = other
        self.pump(lambda: tab.client is None, 20)
        t_end = time.monotonic() + 3.0
        while time.monotonic() < t_end:
            self.root.update()
            time.sleep(0.02)
        self.assertIsNone(tab.client)
        self.assertIsNone(tab._relogin_at)
        self.assertEqual(self.s.call(lambda: self.s.srv.by_name["riko"].conn is not None), True)


if __name__ == "__main__":
    unittest.main()
