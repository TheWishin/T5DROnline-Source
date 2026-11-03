"""Catalog coverage for the combined 1.2.0 drafts; no launcher, server or game imports."""
import ast
from pathlib import Path
import string
import unittest


LOBBY = Path(__file__).resolve().parents[1] / "lobby" / "t5lobby"
LANGUAGES = ("de", "es", "fr", "ja", "ko", "pt_br")
FEATURE_TEXTS = (
    "input delays above 2 frames need a newer launcher and server",
    "DEV",
    "Mention a player with @name; press Tab to complete.",
    "Sound and taskbar flash for lobby notifications",
    "Ranked by character",
    "No ranked games played.",
    "Replay folder",
    "Moved {moved} replay file(s). {retained} file(s) remain in {source}; existing files were not replaced.",
    "Several matches at once",
    "Table {table}: {players}",
    "Casual set vs {name}",
    "The casual set ended {mine}-{theirs}. Completed games keep their results; no rating change.",
    "Rematch starts in {seconds} s unless you decline.",
    "Auto-skip replays and round endings (both players agree)",
    "this server has no in-game rematch",
    "As dealt",
    "Always left",
    "Always right",
    "Casual matches only: show your fighter on the chosen side and swap left/right controls when mirrored. "
    "Ranked and Quick matches keep the dealt side. Offline: Versus previews the chosen side.",
    "Graphics compatibility warning",
    "Could not stop the shader warm-up",
    "This PC lists older Intel graphics ({gpus}). Intel HD 4400-class graphics may lack a working Direct3D 12 "
    "driver and may not run the game. Building the game does not add graphics support. If this PC has another "
    "graphics card, select it in Windows Graphics settings. Continue building?",
    "Launcher button bindings and macros take priority over the game's Controller Setup. "
    "Set them in Settings > Set up controllers… in the launcher.",
    "Intel HD Graphics 4400: graphics device lost",
    "Game log: Intel HD Graphics 4400 was selected and the graphics device was lost.",
    "Intel HD Graphics 4400 lost the graphics device (exit code 12). Try the latest graphics driver offered "
    "by your PC maker, close GPU-heavy programs and overlays, and choose Lowest (0.5x) Internal resolution. "
    "If this PC has another GPU, select it for t5dr.exe in Windows Graphics settings. These steps may not fix it. "
    "If it still fails, click Report a problem and send the report to the maintainer.",
    "Private messages",
    "Private messages ({count})",
    "Message player",
    "Private messages are relayed, not saved by the server. Only lines you select are sent with a report.",
    "Message {name}",
    "Mute",
    "Unmute",
    "Report selected lines",
    "Select up to {count} lines to report.",
    "Send selected lines to moderators?",
    "Report sent to moderators.",
    "Private chat is unavailable on this server.",
    "Private messages are kept only until you log out or close the launcher.",
    "Block {name}? This also leaves any running match against them.",
)
KNOWN_MESSAGES = (
    "input delays above 2 frames need a newer launcher and server",
    "table is 1 to {count}",
    "this server has no simultaneous room tables",
    "the casual set goes on by itself",
    "first_to: 1, 2, 3, 5 or 10",
    "this server has no in-game rematch",
    "invalid rematch policy",
    "auto_skip_after_round must be boolean",
    "rematch rules require an updated launcher",
    "rematch rules require a classic casual room",
    "round skips require an updated launcher",
    "private messages are unavailable",
    "private messages: slow down",
    "write a private message first",
    "muted is a boolean",
    "the private mute list is full",
    "private reports: slow down",
    "choose between 1 and 5 private message lines",
    "these private message lines cannot be verified; reconnect and try new lines",
)


def assignments(path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {target.id: node.value for node in tree.body if isinstance(node, ast.Assign)
            for target in node.targets if isinstance(target, ast.Name)}


def fields(text):
    return sorted(name for _, name, _, _ in string.Formatter().parse(text) if name is not None)


class IntegratedCatalogTest(unittest.TestCase):
    def test_every_language_keeps_all_integrated_features(self):
        for language in LANGUAGES:
            with self.subTest(language=language):
                node = assignments(LOBBY / f"i18n_{language}.py")["MESSAGES"]
                messages = ast.literal_eval(node)
                for text in FEATURE_TEXTS + KNOWN_MESSAGES:
                    self.assertIn(text, messages)
                self.assertNotIn(
                    "Sound and taskbar flash when a match is found, I am challenged or invited, "
                    "or someone joins my room", messages)
                self.assertNotIn("Always see me on the left", messages)
                self.assertNotIn("Mute private messages", messages)
                self.assertNotIn("Unmute private messages", messages)

    def test_catalogs_have_equal_keys_without_duplicates_and_keep_placeholders(self):
        expected = None
        for language in LANGUAGES:
            node = assignments(LOBBY / f"i18n_{language}.py")["MESSAGES"]
            keys = [ast.literal_eval(key) for key in node.keys]
            messages = ast.literal_eval(node)
            with self.subTest(language=language):
                self.assertEqual(len(keys), len(set(keys)), "duplicate catalog keys hide translations")
                if expected is None:
                    expected = set(keys)
                self.assertEqual(set(keys), expected)
            for text, translation in messages.items():
                with self.subTest(language=language, text=text):
                    self.assertEqual(fields(text), fields(translation))
                    self.assertTrue(translation.strip())

    def test_combined_server_messages_are_in_active_known_groups(self):
        nodes = assignments(LOBBY / "i18n_known.py")
        active_groups = [group.id for group in nodes["GROUPS"].elts]
        known = set()
        for group in active_groups:
            for node in ast.walk(nodes[group]):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "N_":
                    known.add(ast.literal_eval(node.args[0]))
        for text in KNOWN_MESSAGES:
            with self.subTest(text=text):
                self.assertIn(text, known)


if __name__ == "__main__":
    unittest.main()
