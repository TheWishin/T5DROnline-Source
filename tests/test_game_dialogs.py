"""The game's own message boxes reach the player (1.1.5). The runtime answers cellMsgDialog by itself and only prints
the text; a player's "The installed game data is corrupted. Ending game." was a silent black screen. The launcher
reads the dialogs from the game log (core.DialogScan, GameRun) and shows each with what to do; one after which the
game stops also explains the game's end (explain_exit). No game needed: the log lines are the runtime's own
(libs/system/cellMsgDialog.c), as they appear in real game logs."""
import os
import sys
import tempfile
import threading
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for sub in ("tools", "lobby", "launcher"):
    p = os.path.join(ROOT, sub)
    if p not in sys.path:
        sys.path.insert(0, p)

import core  # noqa: E402

CORRUPTED = [
    "[live-draw] frame 15264 packets[seen=11282511 queued=11282511 movie=0 qfull=0]",
    "[cellMsgDialog] Open2(type=0x00000080, msg='The installed game data is corrupted. Ending game.",
    "Please delete the corrupted game data and reinstall the game.')",
    "========================================",
    "[DIALOG] The installed game data is corrupted. Ending game.",
    "Please delete the corrupted game data and reinstall the game.",
    "========================================",
    "[cellMsgDialog] Auto-responding: NONE (no buttons)",
    "[fps] 60.0 (frames 15166..15466 over 5.0s)",
]
SAVE = [
    "[cellMsgDialog] Open2(type=0x00000111, msg='Unable to save Play Data.",
    "Cancel Play Data save?')",
    "========================================",
    "[DIALOG] Unable to save Play Data.",
    "Cancel Play Data save?",
    "========================================",
    "[cellMsgDialog] Auto-responding: YES",
]


def scan(lines):
    s, out = core.DialogScan(), []
    for l in lines:
        d = s.feed(l)
        if d:
            out.append(d)
    d = s.finish()
    if d:
        out.append(d)
    return out


class Scan(unittest.TestCase):
    def test_real_log_lines(self):
        self.assertEqual(scan(CORRUPTED + SAVE), [
            "The installed game data is corrupted. Ending game.\nPlease delete the corrupted game data and reinstall "
            "the game.",
            "Unable to save Play Data.\nCancel Play Data save?"])

    def test_no_end_line(self):
        # another thread's line instead of the "=" line, a dialog cut off by the game's end, a runaway one
        self.assertEqual(scan(["[DIALOG] One", "[cellMsgDialog] Auto-responding: OK"]), ["One"])
        self.assertEqual(scan(["[DIALOG] Two", "line"]), ["Two\nline"])
        self.assertEqual(scan(["[DIALOG] A", "[DIALOG] B", "====="]), ["A", "B"])
        many = scan(["[DIALOG] x"] + ["y"] * 20)
        self.assertEqual(len(many[0].splitlines()), core.DIALOG_MAX_LINES)
        self.assertEqual(scan(["[DIALOG] ", "====="]), [])
        self.assertEqual(scan(["no dialog here", "====="]), [])

    def test_advice(self):
        fatal, text = core.dialog_info(scan(CORRUPTED)[0])
        self.assertTrue(fatal)
        self.assertIn("Redo every step", text)
        self.assertIn("619,430,240 bytes", text)
        fatal, text = core.dialog_info(scan(SAVE)[0])
        self.assertFalse(fatal)
        self.assertIn("could not write its save", text)
        self.assertFalse(core.dialog_info("Unable to load Play Data.")[0])
        self.assertIn("could not read its save", core.dialog_info("Unable to load Play Data.")[1])
        self.assertEqual(core.dialog_info("Something new.")[0], False)
        self.assertIn("Report a problem", core.dialog_info("Something new.")[1])
        msg = core.dialog_message("Unable to save Play Data.\nCancel Play Data save?")
        self.assertTrue(msg.startswith('The game shows: "Unable to save Play Data. Cancel Play Data save?" The game'),
                        msg)

    def test_explain_exit(self):
        dialogs = scan(CORRUPTED)
        why = core.explain_exit(0, CORRUPTED, dialogs)
        self.assertIn("installed game data is corrupted", why)
        self.assertIn("Redo every step", why)
        # a dialog the game goes on after does not explain a normal end
        self.assertIsNone(core.explain_exit(0, SAVE, scan(SAVE)))
        # a device loss stays the device loss
        self.assertIn("graphics card stopped", core.explain_exit(12, [], dialogs))
        self.assertIsNone(core.explain_exit(0, ["[fps] 60.0"]))          # (callers without dialogs)

    def test_translated(self):
        from t5lobby import i18n
        try:
            i18n.set_language("de")
            fatal, text = core.dialog_info(scan(CORRUPTED)[0])
            self.assertIn("Alle Schritte neu machen", text)
            self.assertIn("Das Spiel zeigt", core.dialog_message("Unable to load Play Data."))
        finally:
            i18n.set_language("en")


class FakeProc:
    def __init__(self):
        self.done = False
        self.returncode = None

    def poll(self):
        return 0 if self.done else None


class Tail(unittest.TestCase):
    def test_game_run_collects_dialogs(self):
        with tempfile.TemporaryDirectory() as d:
            g = core.GameRun(d, None)
            g.log_path = os.path.join(d, "game.log")
            g.proc = FakeProc()
            with open(g.log_path, "w", encoding="utf-8") as f:
                f.write("\n".join(CORRUPTED[:5]) + "\n")
                f.flush()
                th = threading.Thread(target=g._tail, daemon=True)
                th.start()
                time.sleep(0.6)
                self.assertEqual(g.dialog_count, 0)                  # the dialog has not ended yet
                f.write("\n".join(CORRUPTED[5:] + SAVE) + "\n")
                f.flush()
                end = time.monotonic() + 5
                while g.dialog_count < 2 and time.monotonic() < end:
                    time.sleep(0.05)
                g.proc.done = True
                th.join(5)
            self.assertEqual(g.dialog_count, 2)
            self.assertIn("corrupted", g.dialogs[0])
            self.assertEqual(g.fps, 60.0)


if __name__ == "__main__":
    unittest.main()
