"""Ranked fighter profiles: fake widgets and mocked transport, with no server or game."""
import asyncio
from types import SimpleNamespace
import unittest
from unittest import mock

from util import BUILD
from t5lobby import i18n, tk_ranked_chars, tk_views
from t5lobby.client import LobbyClient


class Frame:
    def __init__(self):
        self.visible = False

    def grid(self, **kwargs):
        self.visible = True

    def grid_remove(self):
        self.visible = False

    def columnconfigure(self, *args, **kwargs):
        pass

    rowconfigure = columnconfigure


class Tree:
    def __init__(self):
        self.rows = {}
        self.columns = {column: {"width": width, "minwidth": min(width, 50), "anchor": "w"}
                        for column, width in zip(tk_ranked_chars.COLUMNS, tk_ranked_chars.WIDTHS)}
        self.headings = {column: {"text": i18n.t(tk_views.HEADINGS[column]).upper(), "anchor": "w"}
                         for column in tk_ranked_chars.COLUMNS}
        self.tk = SimpleNamespace(splitlist=lambda value: str(value).split())

    def column(self, column, option=None, **kwargs):
        self.columns[column].update(kwargs)
        return self.columns[column][option] if option else dict(self.columns[column])

    def heading(self, column, option=None, **kwargs):
        self.headings[column].update(kwargs)
        return self.headings[column][option] if option else dict(self.headings[column])

    def cget(self, option):
        return {"style": "Lobby.Treeview"}[option]

    def winfo_pixels(self, value):
        return int(value)

    def get_children(self):
        return tuple(self.rows)

    def delete(self, *ids):
        for iid in ids:
            del self.rows[iid]

    def insert(self, parent, index, iid, **values):
        self.rows[iid] = values

    def item(self, iid, **values):
        self.rows[iid] = values

    def move(self, iid, parent, index):
        items = list(self.rows.items())
        row = next(row for row in items if row[0] == iid)
        items.remove(row)
        items.insert(index, row)
        self.rows = dict(items)


class RankedCharacterViewTest(unittest.TestCase):
    def setUp(self):
        self.lang = i18n.language()
        i18n.set_language("en")
        self.tv = Tree()
        self.view = SimpleNamespace(tab=SimpleNamespace(table=SimpleNamespace(fighter_name=lambda key: key.title())),
                                    px=lambda value: value, body=lambda parent: Frame(),
                                    tree=mock.Mock(return_value=(Frame(), self.tv)), show_empty=mock.Mock())
        # Keep the view tests independent of a display, while supplying the
        # style and numeric font metrics used to size the real headings.
        style = SimpleNamespace(lookup=lambda name, option: {"font": "TkHeadingFont", "padding": "0"}[option])
        font = SimpleNamespace(measure=lambda text: len(str(text)) * 8)
        with mock.patch.object(tk_ranked_chars.ttk, "Label"), \
                mock.patch.object(tk_ranked_chars.ttk, "Style", return_value=style), \
                mock.patch.object(tk_ranked_chars.tkfont, "Font", return_value=font):
            self.ui = tk_ranked_chars.RankedCharacters(self.view, Frame())

    def tearDown(self):
        i18n.set_language(self.lang)

    def test_all_server_rows_and_six_columns_without_local_aggregation(self):
        rows = [{"char": f"fighter{i}", "games": 3, "wins": 1, "losses": 1, "draws": 1, "win_rate": 33.33}
                for i in range(8)]
        self.ui.shown({"ranked_chars": rows, "history": [], "chars": []})
        self.assertTrue(self.ui.frame.visible)
        self.assertEqual(len(self.tv.rows), 8)
        self.assertEqual(self.tv.rows["ranked:fighter7"]["values"],
                         ("Fighter7", "3", "1", "1", "1", "33.33 %"))
        self.view.show_empty.assert_called_with(self.tv, False)
        # The shared tree builder provides its vertical scrollbar, independent of the number of fighters.
        self.assertEqual(self.view.tree.call_args.args[1], tk_ranked_chars.COLUMNS)
        self.assertEqual(self.view.tree.call_args.kwargs["height"], 4)

    def test_empty_ranked_record_and_old_server_clear_previous_profile(self):
        self.ui.shown({"ranked_chars": [{"char": "jin", "games": 1, "wins": 1, "losses": 0,
                                         "draws": 0, "win_rate": 100.0}]})
        self.ui.shown({"ranked_chars": []})
        self.assertTrue(self.ui.frame.visible)
        self.assertEqual(self.tv.rows, {})
        self.view.show_empty.assert_called_with(self.tv, True)
        self.ui.shown({"chars": [{"char": "jin", "games": 99, "wins": 50}]})
        self.assertFalse(self.ui.frame.visible)
        self.assertEqual(self.tv.rows, {})

    def test_profile_callback_updates_thin_view(self):
        # Keep the real view's helpers without creating Tk widgets. A namespace
        # cannot stand in for the view now that profiles also refresh mute state.
        view = tk_views.OnlineView.__new__(tk_views.OnlineView)
        view.prof_badge, view.ranked_chars = mock.Mock(), mock.Mock()
        profile = {"account": False, "ranked_chars": []}
        view.profile_shown(profile)
        view.prof_badge.set.assert_called_once_with(None, None)
        view.ranked_chars.shown.assert_called_once_with(profile)

    def test_profile_callback_refreshes_mute_control_with_ranked_view(self):
        view = tk_views.OnlineView.__new__(tk_views.OnlineView)
        view.prof_badge, view.ranked_chars, view.profile_mute = mock.Mock(), mock.Mock(), mock.Mock()
        view.tab = SimpleNamespace(client=SimpleNamespace(me={"name": "Tester"}),
                                   profile_name="Rival", _is_muted=mock.Mock(return_value=True))
        profile = {"account": False, "ranked_chars": []}
        view.profile_shown(profile)
        view.ranked_chars.shown.assert_called_once_with(profile)
        view.tab._is_muted.assert_called_once_with("Rival")
        view.profile_mute.configure.assert_called_once_with(state="normal", text="Unmute")

    def test_rate_comes_from_server_and_uses_language_decimal_separator(self):
        i18n.set_language("de")
        rows = tk_ranked_chars.rows_for({"ranked_chars": [
            {"char": "jin", "games": 3, "wins": 1, "losses": 1, "draws": 1, "win_rate": 42.42}]}, str.title)
        self.assertEqual(rows[0][1][-1], "42,42 %")

    def test_new_texts_in_every_catalog(self):
        for language in i18n.CATALOGS:
            with self.subTest(language=language):
                catalog = i18n.catalog(language)
                for text in ("Ranked by character", "No ranked games played.", "Games", "Losses", "Draws"):
                    self.assertIn(text, catalog)


class ProfileCapabilityTest(unittest.TestCase):
    def test_hello_announces_ranked_chars_without_moving_legacy_caps(self):
        async def check():
            client = LobbyClient("127.0.0.1:1", BUILD, blind_ready=True, ingame_pick=True, sets=True,
                                 tournaments=True, spectate=True, match_rules=True, life150=True)
            writer = mock.Mock()
            writer.get_extra_info.side_effect = lambda key: ("127.0.0.1", 1) if key == "peername" else None
            # No socket is opened: a server predating the cap accepts the hello and omits it in its reply.
            welcome = {"t": "welcome", "caps": []}
            with mock.patch("t5lobby.client.asyncio.open_connection", new=mock.AsyncMock(return_value=(None, writer))), \
                    mock.patch.object(client, "_read_loop", new=mock.AsyncMock()), \
                    mock.patch.object(client, "_request", new=mock.AsyncMock(return_value=welcome)) as request:
                self.assertEqual(await client._connect(1), welcome)
                caps = request.call_args.args[0]["caps"]
                self.assertEqual(caps.count("ranked_chars"), 1)
                self.assertEqual(caps[:16], ["delta", "notices", "blind_ready", "old_stages", "ingame_pick", "sets",
                                              "nat2", "relays", "friends", "tournaments", "spectate", "private_rooms",
                                              "game_fallback", "boss_chars", "lag_wait", "match_rules"])
                self.assertLess(caps.index("ranked_chars"), 32)
                await asyncio.gather(*client._tasks)

        asyncio.run(check())


if __name__ == "__main__":
    unittest.main()
