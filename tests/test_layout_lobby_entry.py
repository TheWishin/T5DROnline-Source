"""Real Tk lobby layout through Walk.run, without game assets or a server.

The original launcher and online walk run with the optional artwork branch
disabled, before the report fixtures. Each configuration has a fresh interpreter.
"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PROBE_TIMEOUT = 45
PROBE_STACK_DELAY = 40
# Keep the focused entry points useful on their own, but run their normal-font
# configurations only once during discovery. The matrix covers the remainder.
NAMED_LAYOUTS = {
    "portuguese_100": ("pt-BR", 100),
    "korean_133": ("ko", 133),
    "german_100": ("de", 100),
    "german_150": ("de", 150),
    "japanese_100": ("ja", 100),
    "japanese_150": ("ja", 150),
    "english_100": ("en", 100),
    "english_150": ("en", 150),
}
PROBE = r'''
import faulthandler
import os
from pathlib import Path
import sys
import threading
from unittest import mock

faulthandler.enable(all_threads=True)
# Keep this armed through interpreter shutdown; the parent bounds that too.
faulthandler.dump_traceback_later(float(os.environ["T5_LAYOUT_STACK_DELAY"]))

root, language, scale = Path(sys.argv[1]), sys.argv[2], int(sys.argv[3])
hidden = tuple(sys.argv[4:])
sys.path.insert(0, str(root / "tests"))
try:
    import tkinter as tk
except ImportError:
    print("TK_UNAVAILABLE")
    raise SystemExit(77)

import i18n_layout as layout
import core
import updater
from t5lobby import fighter_art, rank_art

errors = []
boundaries = []
threading.excepthook = lambda event: errors.append(
    (event.exc_type.__name__, str(event.exc_value)))

def denied(name):
    def refuse(*args, **kwargs):
        boundaries.append(name)
        raise AssertionError(name + " is outside this offline lobby test")
    return refuse

load_launcher = layout.load_launcher
def load():
    module = load_launcher()
    module.App.report_callback_exception = lambda self, typ, value, tb: errors.append(
        (typ.__name__, str(value)))
    return module

screen = layout.Walk.screen
def observe(walk, name, top=None):
    screen(walk, name, top)
    if name == "online lobby":
        tab = walk.app.online
        assert tab.strict_check.winfo_manager() == "grid"
        assert tab.view.casual_row.winfo_manager() == "grid"
        assert tab.tv_players.get_children(), "the real lobby has no player rows"
        assert tab.tv_rooms.get_children(), "the real lobby has no room rows"
        if os.environ.get("T5_LAYOUT_VERIFY_GEOMETRY") == "1":
            app, view = walk.app, tab.view
            players, rooms, chat_card = tab.tv_players.master.master, tab.tv_rooms.master.master, tab.chat_log.master
            page = players.master
            app.attributes("-alpha", 0.0)
            height = min(walk.px(840), 1000)
            if scale == 150:
                # The existing compact-display control frees list rows on a
                # short high-DPI screen; exercise that actual production action.
                view.toggle_top(True)
            # Tk keeps a window within the screen (wm maxsize defaults to it). GitHub's
            # Windows runners have a 1024x768 screen, so 1400x840 came out 1024x749
            # there and the lists lost their rows: the sizes below are the ones under
            # test, so let them exceed the runner's screen (offscreen anyway).
            app.wm_maxsize(max(app.wm_maxsize()[0], walk.px(1400)), max(app.wm_maxsize()[1], height))
            for width in (1400, 1080, 1180, 1080):
                app.geometry("%dx%d+20000+20000" % (walk.px(width), height))
                app.deiconify()
                app.update()
                # (the launcher's own minimum height may make it a little taller than asked: px(680) at 150 %)
                assert abs(app.winfo_width() - walk.px(width)) <= 2 and app.winfo_height() >= height - 2, (
                    "window size", width, walk.px(width), height, app.winfo_width(), app.winfo_height(),
                    app.winfo_screenwidth(), app.winfo_screenheight())
                view._apply_wraps()
                app.update()
                assert int(players.grid_info()["columnspan"]) == 1, players.grid_info()
                for card in (players, rooms, chat_card):
                    assert card.winfo_ismapped(), (width, card)
                    assert card.winfo_y() + card.winfo_height() <= page.winfo_height() + 2, (
                        width, str(card), card.winfo_y(), card.winfo_height(), page.winfo_height())
                input_row = chat_card.grid_slaves(row=2, column=0)[0]
                assert input_row.winfo_y() + input_row.winfo_height() <= chat_card.winfo_height(), (
                    width, input_row.winfo_y(), input_row.winfo_height(), chat_card.winfo_height())
                tab.tv_players.see(tab.tv_players.get_children()[0])
                tab.tv_rooms.see(tab.tv_rooms.get_children()[0])
                app.update_idletasks()
                first = tab.tv_players.bbox(tab.tv_players.get_children()[0])
                assert first and first[1] + first[3] <= tab.tv_players.winfo_height(), (
                    width, first, tab.tv_players.winfo_height())
                first_room = tab.tv_rooms.bbox(tab.tv_rooms.get_children()[0])
                assert first_room and first_room[1] + first_room[3] <= tab.tv_rooms.winfo_height(), (
                    width, first_room, tab.tv_rooms.winfo_height())
                from tkinter import font as tkfont
                line_height = tkfont.Font(root=tab.chat_log, font=tab.chat_log.cget("font")).metrics("linespace")
                assert tab.chat_log.winfo_height() >= 2 * line_height + 4, tab.chat_log.winfo_height()
                assert chat_card.winfo_width() >= walk.px(100), chat_card.winfo_width()
                entry = input_row.grid_slaves(row=0, column=0)[0]
                entry_font = tkfont.Font(root=entry, font=entry.cget("font"))
                assert entry.winfo_width() >= entry_font.measure("0000"), entry.winfo_width()
                tab.tv_players.see("p2")
                app.update_idletasks()
                mute_box = tab.tv_players.bbox("p2", "mute")
                assert mute_box and mute_box[0] + mute_box[2] <= tab.tv_players.winfo_width(), (
                    width, mute_box, tab.tv_players.winfo_width())
            clicked = []
            with mock.patch.object(tab, "toggle_mute", side_effect=clicked.append):
                tab.tv_players.event_generate("<Button-1>", x=mute_box[0] + mute_box[2] // 2,
                                             y=mute_box[1] + mute_box[3] // 2)
                app.update()
            assert clicked == ["Rival_Long_Name"], clicked
            app.withdraw()
            app.update()

    if name == "online lobby, sorted by ping":
        # Skip the optional fixture that writes stand-in fighter PNGs; continue
        # every remaining state through the original no-art Online walk.
        walk.app.online.charsel = None

walk = layout.Walk(language, scale, hidden)
with mock.patch.object(layout, "load_launcher", side_effect=load), \
        mock.patch.object(layout.Walk, "screen", observe), \
        mock.patch.object(layout.Walk, "_windows", lambda self, folder: None), \
        mock.patch.object(core, "find_candidates", return_value=([], [])), \
        mock.patch.object(core, "peek_needs_keys", return_value=False), \
        mock.patch.object(updater, "pending_results", return_value=[]), \
        mock.patch.object(tk.Misc, "clipboard_clear", return_value=None), \
        mock.patch.object(tk.Misc, "clipboard_append", return_value=None), \
        mock.patch.object(fighter_art.FACES, "prepare", return_value=None), \
        mock.patch.object(rank_art.ART, "prepare", return_value=None), \
        mock.patch("socket.socket", side_effect=denied("socket creation")), \
        mock.patch("subprocess.Popen", side_effect=denied("process creation")):
    try:
        result = walk.run()
    except tk.TclError as error:
        if not walk.screens and ("no display" in str(error).lower()
                                 or "couldn't connect to display" in str(error).lower()):
            print("TK_NO_DISPLAY: " + str(error))
            raise SystemExit(77)
        raise

assert result is walk
assert "tab settings (bottom)" in walk.screens, walk.screens
assert "online lobby" in walk.screens, walk.screens
assert "online stats (casual)" in walk.screens, walk.screens
assert not any("pictures" in name for name in walk.screens), walk.screens
cuts = layout.compare(walk)
assert not cuts, cuts
assert not walk.missing, walk.missing
assert not errors, errors
assert not boundaries, boundaries
assert not walk.shown, walk.shown
print("real Tk Walk.run lobby layout passed: %s %s" % (language, scale))
'''


class LobbyLayoutEntry(unittest.TestCase):
    def run_layout(self, language, scale, hidden=(), geometry=False):
        scope = ROOT / "_ci_scope_temp"
        scope.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="lobby_layout_", dir=scope) as folder:
            env = dict(os.environ, TEMP=folder, TMP=folder,
                       T5_PAD_NAV="0", T5_FW_CHECK="0", T5_NOTIFY="0",
                       T5DR_NO_UPDATE_CHECK="1", T5_UI_CACHE="0", PYTHONIOENCODING="utf-8",
                       T5_LAYOUT_STACK_DELAY=str(PROBE_STACK_DELAY),
                       T5_LAYOUT_VERIFY_GEOMETRY="1" if geometry else "0")
            for name in ("T5_FIGHTER_ART", "T5_RANK_ART", "T5_UI_SHOTS"):
                env.pop(name, None)
            try:
                result = subprocess.run(
                    [sys.executable, "-B", "-c", PROBE, str(ROOT), language, str(scale), *hidden],
                    cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8",
                    timeout=PROBE_TIMEOUT,
                )
            except subprocess.TimeoutExpired as error:
                # TimeoutExpired retains bytes even with text=True. Keep the
                # child's all-thread dump instead of printing its huge -c argv.
                output = "".join(
                    part.decode("utf-8", errors="replace") if isinstance(part, bytes) else part
                    for part in (error.stdout, error.stderr) if part
                )
                raise self.failureException(
                    f"layout probe timed out after {PROBE_TIMEOUT:g} s: "
                    f"language={language}, scale={scale}, hidden={hidden}, geometry={geometry}\n{output}"
                ) from None
        output = result.stdout + result.stderr
        if result.returncode == 77 and ("TK_UNAVAILABLE" in output or "TK_NO_DISPLAY:" in output):
            self.skipTest(output.strip())
        self.assertEqual(result.returncode, 0, output)
        self.assertIn(f"real Tk Walk.run lobby layout passed: {language} {scale}", result.stdout)

    def test_lobby_resizes_without_losing_chat_or_player_rows(self):
        for scale in (100, 150):
            with self.subTest(scale=scale):
                self.run_layout("de", scale, geometry=True)

    def test_all_languages_and_scales(self):
        for language in ("en", "de", "es", "fr", "pt-BR", "ja", "ko"):
            for scale in (100, 133, 150):
                if (language, scale) in NAMED_LAYOUTS.values():
                    continue
                with self.subTest(language=language, scale=scale):
                    self.run_layout(language, scale)

    def test_font_fallback_every_language(self):
        for hidden in (("Bahnschrift",), ("Bahnschrift", "Segoe UI")):
            for language in ("en", "de", "es", "fr", "pt-BR", "ja", "ko"):
                for scale in (100, 150):
                    with self.subTest(hidden=hidden, language=language, scale=scale):
                        self.run_layout(language, scale, hidden)

    def test_portuguese_100(self):
        self.run_layout(*NAMED_LAYOUTS["portuguese_100"])

    def test_korean_133(self):
        self.run_layout(*NAMED_LAYOUTS["korean_133"])

    def test_german_100(self):
        self.run_layout(*NAMED_LAYOUTS["german_100"])

    def test_german_150(self):
        self.run_layout(*NAMED_LAYOUTS["german_150"])

    def test_japanese_100(self):
        self.run_layout(*NAMED_LAYOUTS["japanese_100"])

    def test_japanese_150(self):
        self.run_layout(*NAMED_LAYOUTS["japanese_150"])

    def test_english_100(self):
        self.run_layout(*NAMED_LAYOUTS["english_100"])

    def test_english_150(self):
        self.run_layout(*NAMED_LAYOUTS["english_150"])


if __name__ == "__main__":
    unittest.main()
