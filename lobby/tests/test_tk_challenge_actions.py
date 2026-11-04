"""Player activation and outgoing feedback, with focused fakes and real Tk/server flows."""
from types import SimpleNamespace
import unittest
from unittest import mock

import util  # noqa: F401  (lobby import path only)
from t5lobby import tk_challenges
from t5lobby.tk_tab import OnlineTab
from test_tk_tab import TkBase, tk
from util import client, expect


class Var:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class PlayerTree:
    """The selection and hit-testing parts of a Treeview."""
    def __init__(self):
        self.selected = ("rival",)
        self.row = "rival"
        self.region = "cell"
        self.column = "#1"
        self.tags = {}
        self.columns = ("player", "rank", "rating", "record", "main", "status", "ping", "mute")

    def __getitem__(self, key):
        return self.columns

    def selection(self):
        return self.selected

    def selection_set(self, row):
        self.selected = (row,)

    def focus(self, row=None):
        return self.selected[0] if row is None else None

    def identify_region(self, x, y):
        return self.region

    def identify_row(self, y):
        return self.row

    def identify_column(self, x):
        return self.column

    def item(self, row, option=None):
        return self.tags.get(row, ()) if option == "tags" else {"tags": self.tags.get(row, ())}

    def exists(self, row):
        return row in ("me", "rival", "other", tk_challenges.AWAY)


class PlayerActivation(unittest.TestCase):
    def tab(self):
        tab = OnlineTab.__new__(OnlineTab)
        tab.tv_players = PlayerTree()
        tab.actions = {"challenge": mock.Mock()}
        tab.actions["challenge"].cget.return_value = "normal"
        players = [{"id": pid, "name": pid, "build": "build", "status": "idle", "rtt": 40}
                   for pid in ("me", "rival", "other")]
        tab.client = SimpleNamespace(me=players[0], players=players,
                                     build=SimpleNamespace(build_id="build"), compatible=lambda p: True)
        tab._last_lobby = {"players": players}
        tab.chal = SimpleNamespace(playable=tk_challenges.ChallengesUI.playable,
                                   selection_changed=mock.Mock(), send=mock.Mock())
        return tab

    def test_enter_challenges_selected_player(self):
        tab = self.tab()
        tab.on_player_activate(SimpleNamespace(keysym="Return", x=0, y=0))
        tab.chal.send.assert_called_once_with()

    def test_double_click_uses_hit_player_instead_of_old_selection(self):
        tab = self.tab()
        tab.tv_players.selected = ("other",)
        tab.on_player_activate(SimpleNamespace(keysym="??", x=20, y=40))
        self.assertEqual(tab.tv_players.selection(), ("rival",))
        tab.chal.send.assert_called_once_with()

    def test_headers_blank_rows_separator_self_and_mute_cell_do_not_challenge(self):
        for region, row, column in (("heading", "rival", "#1"), ("nothing", "", "#1"),
                                    ("cell", "", "#1"), ("cell", tk_challenges.AWAY, "#1"),
                                    ("cell", "me", "#1"), ("cell", "rival", "#8")):
            with self.subTest(region=region, row=row, column=column):
                tab = self.tab()
                tab.tv_players.region, tab.tv_players.row, tab.tv_players.column = region, row, column
                tab.on_player_activate(SimpleNamespace(keysym="??", x=20, y=40))
                tab.chal.send.assert_not_called()

    def test_disabled_action_and_unavailable_row_do_not_challenge(self):
        tab = self.tab()
        tab.actions["challenge"].cget.return_value = "disabled"
        tab.on_player_activate(SimpleNamespace(keysym="Return", x=0, y=0))
        tab.chal.send.assert_not_called()
        tab.actions["challenge"].cget.return_value = "normal"
        tab.client.players[1]["status"] = "playing"
        tab.on_player_activate(SimpleNamespace(keysym="Return", x=0, y=0))
        tab.chal.send.assert_not_called()


class ChallengeFeedback(unittest.TestCase):
    def ui(self, delay="6"):
        client = SimpleNamespace(me={"id": "me"}, send_challenge=mock.Mock(), cancel_challenge=mock.Mock(),
                                 multi_challenge_ok=lambda: True, challenge_delay_max=lambda pid=None: 8)
        tab = SimpleNamespace(cfg={"challenge_delay": delay}, client=client, tv_players=PlayerTree(),
                              _last_lobby={"players": [{"id": "rival", "name": "Rival"}]},
                              casual=SimpleNamespace(first_to=3), call=mock.Mock(), status=mock.Mock(),
                              chat_line=mock.Mock(), relist=mock.Mock(), _save_cfg=mock.Mock())
        with mock.patch.object(tk_challenges.tk, "StringVar", Var):
            ui = tk_challenges.ChallengesUI(tab)
        return ui

    def test_challenge_uses_current_delay_and_blocks_repeated_activation_before_reply(self):
        ui = self.ui()
        ui.send()
        self.assertEqual(ui.tab.call.call_args.args, (ui.client.send_challenge, "rival", 6, 3))
        ui.send()
        self.assertEqual(ui.tab.call.call_count, 1)
        ui.tab.call.call_args.kwargs["then"]({"challenge": "c1", "delay": {"frames": 6}})
        self.assertEqual(ui.challenged_ids(), {"rival"})
        ui.send()
        self.assertEqual(ui.tab.call.call_count, 1)

    def test_failed_send_can_be_retried(self):
        ui = self.ui()
        ui.send()
        ui.tab.call.call_args.kwargs["fail"]()
        ui.send()
        self.assertEqual(ui.tab.call.call_count, 2)

    def test_end_before_send_reply_never_restores_pending_row(self):
        for state in ("accepted", "declined", "expired", "cancelled", "withdrawn"):
            with self.subTest(state=state):
                ui = self.ui()
                ui.on_event({"t": "challenge_update", "challenge": "c1", "state": state})
                ui._sent({"challenge": "c1"}, "rival", "Rival")
                self.assertEqual(ui.challenged_ids(), set())
                self.assertEqual(ui.out, {})

    def test_pending_ends_only_on_server_event_and_reset_clears_everything(self):
        for state in ("accepted", "declined", "expired", "cancelled", "withdrawn"):
            with self.subTest(state=state):
                ui = self.ui()
                ui._sent({"challenge": "c1"}, "rival", "Rival")
                ui.on_event({"t": "challenge_update", "challenge": "c1", "state": state})
                self.assertEqual(ui.challenged_ids(), set())
                ui.tab.relist.assert_called()
        ui = self.ui()
        ui.send()
        ui._sent({"challenge": "c1"}, "rival", "Rival")
        ui.reset()
        self.assertFalse(ui.out)
        self.assertFalse(ui.incoming)
        self.assertFalse(ui.ended)
        self.assertFalse(ui.sending)

    def test_countdown_changes_once_per_second_and_waits_at_zero_for_server(self):
        ui = self.ui()
        with mock.patch.object(tk_challenges.time, "monotonic", return_value=100):
            ui._sent({"challenge": "c1"}, "rival", "Rival")
        with mock.patch.object(tk_challenges.time, "monotonic", return_value=103.1):
            self.assertEqual(ui.pending_text("rival"), "Challenge sent -")
            self.assertEqual(ui.pending_clock("rival"), "0:27 -")
            ui.tick()
            ui.tab.relist.reset_mock()
            ui.tick()
            ui.tab.relist.assert_not_called()
        with mock.patch.object(tk_challenges.time, "monotonic", return_value=104.1):
            ui.tick()
            ui.tab.relist.assert_called_once_with()
        with mock.patch.object(tk_challenges.time, "monotonic", return_value=200):
            ui.tick()
            self.assertEqual(ui.pending_clock("rival"), "0:00 -")
            self.assertEqual(ui.challenged_ids(), {"rival"})
        ui.on_event({"t": "challenge_update", "challenge": "c1", "state": "expired"})
        self.assertEqual(ui.pending_text("rival"), "")

    def test_reset_and_replaced_client_ignore_late_send_callbacks(self):
        for changed_client in (False, True):
            with self.subTest(changed_client=changed_client):
                ui = self.ui()
                ui.send()
                callback = ui.tab.call.call_args.kwargs["then"]
                if changed_client:
                    ui.tab.client = SimpleNamespace(me={"id": "new"})
                else:
                    ui.reset()
                callback({"challenge": "old"})
                self.assertFalse(ui.out)
                ui.tab.chat_line.assert_not_called()

    def test_cancel_waits_for_server_to_end_highlight(self):
        ui = self.ui()
        ui._sent({"challenge": "c1"}, "rival", "Rival")
        ui.cancel("c1")
        self.assertEqual(ui.tab.call.call_args.args, (ui.client.cancel_challenge, "c1"))
        self.assertEqual(ui.challenged_ids(), {"rival"})
        ui.on_event({"t": "challenge_update", "challenge": "c1", "state": "cancelled"})
        self.assertEqual(ui.challenged_ids(), set())


@unittest.skipIf(tk is None, "no tkinter")
class ChallengeRowWidgets(TkBase):
    def test_multiple_pending_keep_one_keyboard_cancel_detail(self):
        tab = self.tab
        for i in range(5):
            tab.tv_players.insert("", "end", iid=f"p{i}", values=(f"Rival {i}",))
            tab.chal.out[f"c{i}"] = {"pid": f"p{i}", "name": f"Rival {i}", "delay": {"frames": 2},
                                     "deadline": 0}
        tab.chal._show_open()
        first_widgets = tab.chal.rows.winfo_children()
        self.assertEqual(len(first_widgets), 2)     # one detail and one real button, even with five pending
        tab.chal._show_open()
        self.assertEqual(tab.chal.rows.winfo_children(), first_widgets)
        with mock.patch.object(tab.chal, "cancel") as cancel:
            next(w for w in first_widgets if w.cget("text") == "Cancel").invoke()
            cancel.assert_called_once_with("c0")
            cancel.reset_mock()
            tab.tv_players.selection_set("p3")
            tab.chal.selection_changed()
            widgets = tab.chal.rows.winfo_children()
            self.assertEqual(len(widgets), 2)
            self.assertIn("Rival 3", widgets[0].cget("text"))
            next(w for w in widgets if w.cget("text") == "Cancel").invoke()
            cancel.assert_called_once_with("c3")

    def test_double_click_binding_challenges_clicked_player_with_current_delay(self):
        tab = self.tab
        tab.server_var.set(self.s.addr)
        tab.do_login("guest")
        self.pump(lambda: tab.client is not None and tab.client.me is not None)
        self.other = client(self.s, "Rival")
        pid = self.other.me["id"]
        self.pump(lambda: tab.tv_players.exists(pid))
        # The first lobby broadcast can precede the rival's UDP registration.
        self.pump(lambda: "away" not in tab.tv_players.item(pid, "tags"))
        self.pump(lambda: str(tab.actions["challenge"].cget("state")) == "normal")
        # Mouse bindings need mapped widgets. Keep this test window transparent and offscreen.
        self.root.attributes("-alpha", 0.0)
        self.root.geometry("1400x900+20000+20000")
        self.root.deiconify()
        self.root.update()
        tv = tab.tv_players
        tv.see(pid)
        self.root.update_idletasks()
        box = tv.bbox(pid, "player")
        self.assertTrue(box)
        x, y = box[0] + box[2] // 2, box[1] + box[3] // 2
        self.assertEqual(tv.identify_row(y), pid)
        tab.chal.delay = "1"
        tv.selection_set(tab.client.me["id"])
        for when in (1000, 1100):
            tv.event_generate("<ButtonPress-1>", x=x, y=y, time=when)
            tv.event_generate("<ButtonRelease-1>", x=x, y=y, time=when + 20)
        self.root.update()
        self.pump(lambda: bool(tab.chal.out))
        challenge = expect(self.other, "challenged")
        self.assertEqual(challenge["delay"], {"frames": 1, "auto": False})
        self.assertEqual(tv.selection(), (pid,))

    def test_enter_sends_current_delay_and_inline_cancel_restores_row(self):
        tab = self.tab
        tab.server_var.set(self.s.addr)
        tab.name_var.set("Tester")
        tab.do_login("guest")
        self.pump(lambda: tab.client is not None and tab.client.me is not None)
        self.other = client(self.s, "Rival")
        pid = self.other.me["id"]
        self.pump(lambda: tab.tv_players.exists(pid))
        self.pump(lambda: "away" not in tab.tv_players.item(pid, "tags"))
        self.pump(lambda: str(tab.actions["challenge"].cget("state")) == "normal")
        self.assertEqual(tab.actions["challenge"].cget("style"), "Card.Accent.TButton")
        tv = tab.tv_players
        self.assertIn("on_player_activate", tv.bind("<Double-1>"))
        self.assertIn("on_player_activate", tv.bind("<Return>"))
        tv.selection_set(pid)
        original_status = tv.set(pid, "status")
        original_ping = tv.set(pid, "ping")
        tab.chal.delay = "2"
        tab.on_player_activate(SimpleNamespace(keysym="Return", x=0, y=0))
        self.pump(lambda: bool(tab.chal.out))
        challenge = expect(self.other, "challenged")
        self.assertEqual(challenge["delay"]["frames"], 2)
        self.assertEqual(challenge["delay"]["auto"], False)
        self.assertIn("challenged", tv.item(pid, "tags"))
        self.assertEqual(tv.set(pid, "status"), "Challenge sent -")
        self.assertEqual(tv.set(pid, "mute"), "Cancel")
        self.assertRegex(tv.set(pid, "ping"), r"^0:[0-3][0-9] -$")
        self.assertTrue(tab.chal.rows.winfo_children())
        # The real Treeview's inline action dispatches Cancel for this pending row.
        with mock.patch.object(tv, "identify_region", return_value="cell"), \
                mock.patch.object(tv, "identify_column", return_value="#8"), \
                mock.patch.object(tv, "identify_row", return_value=pid), \
                mock.patch.object(tab, "toggle_mute") as mute:
            self.assertEqual(tab.on_player_mute_click(SimpleNamespace(x=100, y=50)), "break")
            mute.assert_not_called()
        self.pump(lambda: not tab.chal.out)
        self.assertNotIn("challenged", tv.item(pid, "tags"))
        self.assertEqual(tv.set(pid, "status"), original_status)
        self.assertEqual(tv.set(pid, "ping"), original_ping)
        self.assertEqual(tv.set(pid, "mute"), "Mute")
        self.assertEqual(tab.chal.box.winfo_manager(), "")


if __name__ == "__main__":
    unittest.main()
