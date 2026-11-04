"""Game editions must not look like a player's country, in Tk or the CLI."""
import io
import unittest
from unittest import mock

import util
from t5lobby import cli
from t5lobby.buildid import BuildInfo
from t5lobby.editions import edition_note
from test_tk_tab import TkBase, tk

EU = BuildInfo("586baa2074e3d259b303879fc7cbea1000041b60", "0123456789abcdef", "test")


class EditionNotes(unittest.TestCase):
    def test_only_known_differing_editions_are_labeled(self):
        for own in ("US", "EU", "?", None):
            for other in ("US", "EU", "?", None, "AT"):
                expected = other + " edition" if own in ("US", "EU") and other in ("US", "EU") and own != other else ""
                self.assertEqual(edition_note({"region": other}, {"region": own}), expected)
        self.assertEqual(edition_note({}, None), "")

    def test_cli_list_uses_status_notes_and_preserves_server_field(self):
        server = util.ServerThread().start()
        self.addCleanup(server.stop)
        eu = util.client(server, "Austrian", build=EU)
        self.addCleanup(eu.close)
        us = util.client(server, "SameEdition")
        self.addCleanup(us.close)
        output = io.StringIO()
        with mock.patch("sys.stdout", output):
            self.assertEqual(cli.main(["--server", server.addr, "--name", "Viewer", "--list"]), 0)
        text = output.getvalue()
        self.assertNotIn("[US]", text)
        self.assertNotIn("[EU]", text)
        self.assertIn("EU edition", next(line for line in text.splitlines() if "Austrian" in line))
        self.assertNotIn("edition", next(line for line in text.splitlines() if "SameEdition" in line))
        self.assertEqual(eu.me["region"], "EU")
        self.assertEqual(us.me["region"], "US")


@unittest.skipIf(tk is None, "no tkinter")
class EditionUI(TkBase):
    def test_names_status_and_registered_profile(self):
        tab = self.tab
        tab.server_var.set(self.s.addr)
        tab.do_login("guest")
        self.pump(lambda: tab.client and tab.client.me)
        self.other = util.client(self.s, "Austrian", build=EU, password="edition-test-pw", register=True)
        self.pump(lambda: tab.tv_players.exists(self.other.me["id"]))
        row = tab.tv_players.item(self.other.me["id"], "values")
        self.assertNotIn("[EU]", row[0])
        self.assertIn("EU edition", row[5])
        tab.view.refresh()
        self.assertGreaterEqual(int(tab.tv_players.column("status", "minwidth")),
                                tab.view._player_record_font.measure(row[5]) + tab.view.px(8))
        own = tab.tv_players.item(tab.client.me["id"], "values")
        self.assertNotIn("[US]", own[0])
        self.assertNotIn("edition", own[5])
        # Registered profiles omit region on existing servers; use the live lobby metadata.
        tab.show_profile("Austrian")
        self.pump(lambda: "EU edition" in tab.prof_text.get())
        self.other.close()
        self.other = util.client(self.s, "SameEdition", password="edition-test-pw", register=True)
        self.pump(lambda: any(p["name"] == "SameEdition" for p in tab.client.players))
        tab.show_profile("SameEdition")
        self.pump(lambda: "SameEdition" in tab.prof_title.get())
        self.assertNotIn("edition", tab.prof_text.get())
