"""Local host-menu protocol tests: fake files/clock, no game and no sockets."""
import json
import os
import queue
import tempfile
import unittest

import util  # noqa: F401
from t5lobby.ingame_ui import CAP, HEALTH_SECONDS, MAX_BYTES, IngameUI, _read


class IngameUITest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.now = 100.0
        self.ui = IngameUI(self.directory.name, "session1", clock=lambda: self.now, worker=False)
        self.ui.offer("m1", "rematch", ["accept", "decline"], 20, {"title": "Rematch?"})
        self.ready()

    def ready(self, sequence=1, **extra):
        value = dict(self.ui._base(), cap=CAP, ready=True, seq=sequence, rev=self.ui.document["rev"])
        value.update(extra)
        self.write("ui_ready.json", value)
        self.ui.pump()

    def write(self, filename, value):
        with open(os.path.join(self.directory.name, filename), "w", encoding="utf-8") as stream:
            json.dump(value, stream)

    def action(self, sequence=1, **extra):
        value = dict(self.ui._base(), seq=sequence, prompt=self.ui.document["prompt"], match="m1", action="accept")
        value.update(extra)
        return value

    def test_one_action_reserved_until_asynchronous_completion(self):
        first = self.action()
        self.ui.receive(first)
        self.ui.receive(first)
        self.ui.receive(self.action(2, action="decline"))
        self.assertEqual(self.ui.events.get_nowait(), ("action", first))
        with self.assertRaises(queue.Empty):
            self.ui.events.get_nowait()
        self.assertEqual(self.ui.pending, first)
        self.ui.complete(1, True)
        self.ui.receive(first)
        self.assertIsNone(self.ui.pending)
        self.assertEqual(self.ui.document["ack_seq"], 1)
        self.assertEqual(self.ui.document["ack_status"], "ok")

    def test_ack_survives_replacement_of_prompt_and_match(self):
        self.ui.receive(self.action())
        self.ui.offer("m2", "ready", ["ready", "decline"], 15)
        self.ui.complete(1, False)
        self.assertEqual(self.ui.document["match"], "m2")
        self.assertEqual((self.ui.document["ack_seq"], self.ui.document["ack_status"]), (1, "rejected"))
        self.ui.offer("m3", "rematch", ["accept"], 20)
        self.assertEqual(self.ui.document["ack_seq"], 1)

    def test_stale_action_read_after_prompt_replacement_gets_rejected_ack(self):
        old = self.action()
        self.ui.offer("m2", "ready", ["ready"], 15)
        previous = self.ui.document["rev"]
        self.ui.receive(old)
        self.assertEqual((self.ui.document["ack_seq"], self.ui.document["ack_status"]), (1, "rejected"))
        self.assertGreater(self.ui.document["rev"], previous)
        self.assertIsNone(self.ui.pending)

    def test_foreign_identity_and_malformed_sequence_never_dispatch(self):
        for extra in ({"v": 2}, {"v": True}, {"generation": "old"}, {"session": "other"},
                      {"seq": True}, {"seq": 0}, {"seq": -1}, {"seq": "1"}, {"seq": 2 ** 40}):
            self.ui.receive(self.action(**extra))
        self.assertEqual(self.ui.seen, 0)
        self.assertTrue(self.ui.events.empty())

    def test_disallowed_action_gets_visible_rejection_revision(self):
        previous = self.ui.document["rev"]
        self.ui.receive(self.action(action="next"))
        self.assertEqual(self.ui.document["ack_status"], "rejected")
        self.assertGreater(self.ui.document["rev"], previous)
        self.assertTrue(self.ui.events.empty())

    def test_expiry_rejects_late_pad_and_hides_prompt(self):
        self.now += 20
        self.ui.receive(self.action())
        self.assertEqual(self.ui.document["ack_status"], "rejected")
        self.ui.pump()
        self.assertEqual(self.ui.document["kind"], "hidden")
        self.assertEqual(self.ui.events.get_nowait(), ("expired", None))

    def test_frozen_ready_file_does_not_keep_crashed_game_healthy(self):
        self.now += HEALTH_SECONDS
        self.ui.pump()
        self.assertFalse(self.ui.healthy)
        self.ready(sequence=2)
        self.assertTrue(self.ui.healthy)

    def test_new_prompt_needs_actual_rendered_revision(self):
        self.assertTrue(self.ui.active)
        self.ui.offer("m2", "ready", ["ready"], 15)
        self.assertFalse(self.ui.active)
        self.ready(sequence=2)
        self.assertTrue(self.ui.active)

    def test_labels_publish_revision_and_unsupported_glyphs_fall_back(self):
        previous = self.ui.document["rev"]
        self.ui.labels({"title": "再戦"})
        self.assertGreater(self.ui.document["rev"], previous)
        self.assertFalse(self.ui.active)
        self.ready(sequence=2, ready=False)
        self.assertFalse(self.ui.healthy)

    def test_atomic_worker_document_and_sequence_separation(self):
        self.ui.pump()
        doc = _read(os.path.join(self.directory.name, "ui.json"))
        self.assertEqual(doc["generation"], self.ui.generation)
        self.assertNotIn("cmd", doc)
        self.assertFalse(os.path.exists(os.path.join(self.directory.name, "cmd.json")))
        self.write("ui_action.json", self.action())
        self.ui.pump()
        self.assertEqual(self.ui.events.get_nowait()[1]["seq"], 1)

    def test_restarting_launcher_rejects_previous_launch_files(self):
        self.write("ui_action.json", self.action())
        fresh = IngameUI(self.directory.name, "session1", clock=lambda: self.now, worker=False)
        fresh.offer("m1", "rematch", ["accept"], 20)
        fresh.pump()
        self.assertNotEqual(fresh.generation, self.ui.generation)
        self.assertFalse(fresh.healthy)
        self.assertTrue(fresh.events.empty())

    def test_bounded_messages_and_malformed_json(self):
        path = os.path.join(self.directory.name, "ui_action.json")
        for raw in (b"[1]", b"{", b"\xff", b'{"seq":1,"seq":2}', b'{"seq":NaN}',
                    b" " * (MAX_BYTES + 1)):
            with open(path, "wb") as stream:
                stream.write(raw)
            self.assertIsNone(_read(path))

    def test_automatic_countdown_does_not_shorten_authoritative_window(self):
        self.ui.countdown(5)
        self.now += 4
        self.ui.pump()
        self.assertEqual(_read(os.path.join(self.directory.name, "ui.json"))["remaining_ms"], 1000)
        self.ui.waiting()
        self.ui.pump()
        self.assertEqual(_read(os.path.join(self.directory.name, "ui.json"))["remaining_ms"], 16000)


if __name__ == "__main__":
    unittest.main()
