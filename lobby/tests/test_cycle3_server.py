"""Release advice must not claim compatible peers cannot play; no sockets or game."""
import json
from types import SimpleNamespace
import unittest

import util  # noqa: F401 -- import path only
from t5lobby.buildid import BuildInfo
from t5lobby.compatibility import BuildGroups, CAP, compatible
from t5lobby.server.lobby import LobbyServer


class CompatibleReleaseNoticeTest(unittest.TestCase):
    def test_cross_release_peers_get_update_advice_without_incompatibility_claim(self):
        old = BuildInfo("offline-elf", "old-code", release="1.1.9")
        new = BuildInfo("offline-elf", "new-code", release="1.2.0")
        groups = BuildGroups(json.dumps({
            "offline-approved": {"net": old.net, "builds": [old.build_id, new.build_id]}}))
        server = object.__new__(LobbyServer)
        for exact_build in (False, True):
            for caps in (frozenset(), frozenset(("notices",))):
                with self.subTest(exact_build=exact_build, caps=caps):
                    player = SimpleNamespace(
                        release=old.release, build_id=old.build_id,
                        compat_group="" if exact_build else groups.group(old.build_id, old.net, {CAP}),
                        conn=SimpleNamespace(caps=caps))
                    peer = SimpleNamespace(
                        release=new.release, build_id=old.build_id if exact_build else new.build_id,
                        compat_group="" if exact_build else groups.group(new.build_id, new.net, {CAP}))
                    self.assertTrue(compatible(player, peer))
                    self.assertTrue(server._outdated(player, new.release))
                    notice = server._update_msg(player, new.release)
                    text = notice["text"] if "notices" in caps else notice["msg"]
                    self.assertEqual(
                        text, 'T5DR Online 1.2.0 is out. Update the launcher (it offers the update '
                        'when it starts, or press "Check for updates").')
                    self.assertEqual(notice["t"], "server_notice" if "notices" in caps else "notice")


if __name__ == "__main__":
    unittest.main()
