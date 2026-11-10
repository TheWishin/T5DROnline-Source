"""Lobby release discovery, entirely offline: no server, sockets or GitHub connection."""
import asyncio
import json
from types import SimpleNamespace
import unittest
import urllib.error
from unittest import mock

import util  # noqa: F401 (sets sys.path without starting its server helper)
from t5lobby import proto
from t5lobby.compatibility import BuildGroups, CrossplayPolicy
from t5lobby.server import Config, LobbyServer
from t5lobby.server import releases


def metadata(version="1.2.3"):
    base = f"https://github.com/TheWishin/T5DROnline/releases/download/v{version}/"
    return {"tag_name": f"v{version}", "draft": False, "prerelease": False,
            "name": "Release", "body": "Notes", "published_at": "2026-10-30T00:00:00Z",
            "html_url": f"https://github.com/TheWishin/T5DROnline/releases/tag/v{version}",
            "assets": [{"name": name, "state": "uploaded", "size": 123,
                        "browser_download_url": base + name, "digest": "sha256:" + "a" * 64}
                       for name in (f"T5DR-Online-{version}.zip", "SHA256SUMS", "SHA256SUMS.sig")]}


class WelcomeReleaseTest(unittest.IsolatedAsyncioTestCase):
    async def welcome(self, version, data):
        cache = releases.ReleaseCache()
        cache.version, cache.data, cache.expires = version, data, float("inf")
        server = SimpleNamespace(cfg=Config(), latest_release=version, release_cache=cache,
                                 udp=SimpleNamespace(port=7781, port2=7782), _casual_welcome=lambda conn: {},
                                 _rematch_enabled=lambda: False,
                                 reports_on=lambda: False, reports_welcome=lambda conn: {},   # (1.2.1 reports.py)
                                 pics_on=lambda: False, pics_welcome=lambda conn: {})         # (profile_pics.py)
        # Match the constructor's policy while keeping this handler test socket-free.
        server.build_groups = BuildGroups(server.cfg.compat_groups)
        server.crossplay = CrossplayPolicy(server.cfg.crossplay, server.cfg.crossplay_groups)
        conn = SimpleNamespace(player=None, ip="192.0.2.1", writer=mock.Mock())
        conn.writer.get_extra_info.return_value = None
        # No capabilities or build are needed: an old launcher still gets its normal welcome.
        return await LobbyServer.h_hello(server, conn, {"t": "hello", "proto": proto.PROTO_VERSION})

    async def test_welcome_has_release_metadata_without_login_or_protocol_change(self):
        data = metadata()
        welcome = await self.welcome("1.2.3", data)
        self.assertEqual(welcome["latest_release"], data)  # KeyError on the old server
        self.assertEqual(welcome["proto"], 1)
        self.assertEqual(welcome["t"], "welcome")
        self.assertEqual(welcome["udp_port"], 7781)
        self.assertEqual(welcome["caps"], [])
        self.assertEqual(welcome["compat_group"], "")

    async def test_no_admin_release_or_metadata_means_fallback(self):
        for version in ("", "1.2.3"):
            self.assertIsNone((await self.welcome(version, None))["latest_release"])

    async def test_rejected_build_still_refused_with_optional_release_metadata(self):
        for data in (metadata(), None):
            with self.subTest(metadata=data is not None):
                cache = releases.ReleaseCache()
                cache.version, cache.data, cache.expires = "1.2.3", data, float("inf")
                server = SimpleNamespace(cfg=Config(builds=["accepted-build"]), latest_release="1.2.3",
                                         release_cache=cache)
                conn = SimpleNamespace(player=None, helloed=False)
                with self.assertRaises(proto.LobbyError) as raised:
                    await LobbyServer.h_hello(server, conn, {"t": "hello", "proto": proto.PROTO_VERSION,
                                                            "build": {"release": "1.0.0"}})
                self.assertEqual(raised.exception.code, proto.E_VERSION)
                self.assertEqual(raised.exception.extra["latest_release"], data)  # absent on old code
                self.assertFalse(conn.helloed)
                self.assertIsNone(conn.player)


class ReleaseCacheTest(unittest.IsolatedAsyncioTestCase):
    async def test_shared_lookup_cached_and_refreshed_without_per_client_requests(self):
        cache = releases.ReleaseCache()
        with mock.patch.object(releases.time, "monotonic", return_value=100) as clock, \
                mock.patch.object(releases.asyncio, "to_thread", new_callable=mock.AsyncMock,
                                  return_value=metadata()) as fetch:
            await cache.refresh("1.2.3")
            for _ in range(20):
                self.assertEqual(cache.public("1.2.3")["tag_name"], "v1.2.3")
                await cache.refresh("1.2.3")
            fetch.assert_awaited_once_with(releases.fetch_release)
            clock.return_value = 401
            self.assertIsNone(cache.public("1.2.3"))
            await cache.refresh("1.2.3")
            self.assertEqual(fetch.await_count, 2)

    async def test_admin_version_change_and_clear_do_not_serve_previous_metadata(self):
        cache = releases.ReleaseCache()
        with mock.patch.object(releases.time, "monotonic", return_value=100) as clock, \
                mock.patch.object(releases.asyncio, "to_thread", new_callable=mock.AsyncMock,
                                  return_value=metadata()) as fetch:
            await cache.refresh("1.2.3")
            self.assertIsNone(cache.public("1.2.4"))
            await cache.refresh("1.2.4")
            self.assertIsNone(cache.public("1.2.4"))
            self.assertEqual(fetch.await_count, 1)  # admin changes cannot exhaust the API limit
            clock.return_value = 161
            fetch.return_value = metadata("1.2.4")
            await cache.refresh("1.2.4")
            self.assertIsNotNone(cache.public("1.2.4"))
            await cache.refresh("")
            self.assertIsNone(cache.public(""))
            self.assertEqual(fetch.await_count, 2)

    async def test_failed_refresh_clears_cached_release_and_throttles_retry(self):
        cache = releases.ReleaseCache()
        with mock.patch.object(releases.time, "monotonic", return_value=100) as clock, \
                mock.patch.object(releases.asyncio, "to_thread", new_callable=mock.AsyncMock,
                                  return_value=metadata()) as fetch:
            await cache.refresh("1.2.3")
            clock.return_value = 401
            fetch.side_effect = OSError("offline")
            await cache.refresh("1.2.3")
            self.assertIsNone(cache.public("1.2.3"))
            clock.return_value = 500
            await cache.refresh("1.2.3")
            self.assertEqual(fetch.await_count, 2)

    async def test_rate_limit_reset_respected_even_if_admin_changes_version(self):
        cache = releases.ReleaseCache()
        error = urllib.error.HTTPError(releases.API_LATEST, 403, "limited",
                                       {"X-RateLimit-Reset": "2000"}, None)
        with mock.patch.object(releases.time, "monotonic", return_value=100) as clock, \
                mock.patch.object(releases.time, "time", return_value=1000), \
                mock.patch.object(releases.asyncio, "to_thread", new_callable=mock.AsyncMock,
                                  side_effect=error) as fetch:
            await cache.refresh("1.2.3")
            clock.return_value = 500
            await cache.refresh("1.2.4")
            fetch.assert_awaited_once()
            self.assertIsNone(cache.public("1.2.4"))

    async def test_cancellation_propagates_for_server_shutdown(self):
        cache = releases.ReleaseCache()
        with mock.patch.object(releases.asyncio, "to_thread", new_callable=mock.AsyncMock,
                               side_effect=asyncio.CancelledError):
            with self.assertRaises(asyncio.CancelledError):
                await cache.refresh("1.2.3")


class ReleaseMetadataTest(unittest.TestCase):
    def test_preserves_all_updater_fields_including_signature_and_digest(self):
        original = metadata()
        self.assertEqual(releases.release_metadata(original, "1.2.3"), original)
        self.assertEqual(releases.release_metadata(original, "v1.2.3"), original)

    def test_refuses_draft_prerelease_withdrawn_and_unannounced_release(self):
        for changed in ({"draft": True}, {"prerelease": True}, {"tag_name": "v1.2.4"},
                        {"tag_name": "v1.2.3-rc1"}):
            self.assertIsNone(releases.release_metadata(dict(metadata(), **changed), "1.2.3"))
        self.assertIsNone(releases.release_metadata(None, "1.2.3"))
        self.assertIsNone(releases.release_metadata(metadata(), ""))

    def test_payload_bounded_and_unneeded_assets_and_fields_omitted(self):
        data = metadata()
        data["author"] = {"login": "unused"}
        data["assets"].append({"name": "unused.bin", "size": 42})
        slim = releases.release_metadata(data, "1.2.3")
        self.assertNotIn("author", slim)
        self.assertEqual(len(slim["assets"]), 3)
        data["body"] = "x" * releases.MAX_METADATA
        self.assertIsNone(releases.release_metadata(data, "1.2.3"))

    def test_fetch_uses_fixed_endpoint_and_bounded_read(self):
        raw = json.dumps(metadata()).encode()
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = raw
        opener = mock.Mock()
        opener.open.return_value = response
        with mock.patch.object(releases.urllib.request, "build_opener", return_value=opener):
            self.assertEqual(releases.fetch_release(), metadata())
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, releases.API_LATEST)
        response.read.assert_called_once_with(releases.MAX_RESPONSE + 1)
        response.read.return_value = b"x" * (releases.MAX_RESPONSE + 1)
        with mock.patch.object(releases.urllib.request, "build_opener", return_value=opener):
            with self.assertRaises(ValueError):
                releases.fetch_release()
        self.assertIsNone(releases._NoRedirects().redirect_request(None, None, 302, "", {}, "https://evil.invalid"))


if __name__ == "__main__":
    unittest.main()
