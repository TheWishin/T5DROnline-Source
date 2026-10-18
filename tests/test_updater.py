"""The launcher's self-update (launcher/updater.py, README "Updating"): version order, the URL
allow-list, the release check and its cache, download + SHA-256 check + unpack, the swap with
rollback, the detached swap step, and that the player's native folder is never touched.
No network: GitHub is a fake opener here."""
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
import zipfile
from unittest import mock

from helpers import ROOT

sys.path.insert(0, os.path.join(ROOT, "launcher"))
import updater  # noqa: E402

SCRIPT_EXT = (".bat", ".cmd", ".ps1", ".vbs", ".vbe", ".js", ".jse", ".wsf", ".hta")


def tree(d):
    """{relative path: bytes} of every file below d."""
    out = {}
    for dp, _, fns in os.walk(d):
        for f in fns:
            p = os.path.join(dp, f)
            with open(p, "rb") as fh:
                out[os.path.relpath(p, d).replace("\\", "/")] = fh.read()
    return out


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb" if isinstance(data, bytes) else "w") as f:
        f.write(data)


def make_install(d, version="1.0.0"):
    """A fake release folder plus the player's files."""
    for rel, data in {
        "release.json": json.dumps({"version": version}),
        "T5DR Online.exe": b"MZ old stub",
        "launcher/t5dr_launcher.pyw": "# old launcher\n",
        "launcher/updater.py": "# old updater\n",
        "python/pythonw.exe": b"MZ old python",
        "python/Lib/os.py": "# old\n",
        "tools/build_game.py": "# old\n",
        "tools/old_only.py": "# removed in the new release\n",
        "runtime/t5dr.exe": b"MZ old runtime",
        "docs/TROUBLESHOOTING.md": "old\n",
        "README.txt": "old\n",
        # the player's files
        "native/gamedata/dev_hdd0/home/00000001/savedata/SAVE/DATA.BIN": b"my save",
        "native/build/t5dr_build.json": json.dumps({"code_id": "aaaaaaaaaaaaaaaa"}),
        "native/logs/game-20261018-120000.log": "log\n",
        "launcher.json": json.dumps({"nickname": "Wishin"}),
        "launcher.log": "log\n",
        "my game.pkg": b"\x7fPKG not really",
    }.items():
        write(os.path.join(d, rel), data)


NEW_FILES = {
    "release.json": None,                      # filled with the version
    "T5DR Online.exe": b"MZ new stub",
    "launcher/t5dr_launcher.pyw": "# new launcher\n",
    "launcher/updater.py": "# new updater\n",
    "python/pythonw.exe": b"MZ new python",
    "python/Lib/os.py": "# new\n",
    "tools/build_game.py": "# new\n",
    "runtime/t5dr.exe": b"MZ new runtime",
    "docs/TROUBLESHOOTING.md": "new\n",
    "README.txt": "new\n",
    "lobby/t5lobby/client.py": "# new folder\n",
}


def make_new(d, version="1.0.1"):
    for rel, data in NEW_FILES.items():
        write(os.path.join(d, rel), json.dumps({"version": version}) if data is None else data)


def make_zip(version="1.0.1", extra=None, top=None, inner_version=None):
    top = top or f"T5DR-Online-{version}"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel, data in NEW_FILES.items():
            zf.writestr(f"{top}/{rel}", json.dumps({"version": inner_version or version}) if data is None else data)
        for name, data in (extra or {}).items():
            zf.writestr(name, data)
    return buf.getvalue()


def release(version="1.0.1", zip_bytes=b"", sums=None, api_digest="auto", code_id=None):
    zname = f"T5DR-Online-{version}.zip"
    digest = hashlib.sha256(zip_bytes).hexdigest()
    sums = f"{digest}  {zname}\n" if sums is None else sums
    base = f"https://github.com/TheWishin/T5DROnline/releases/download/v{version}/"
    data = {
        "tag_name": f"v{version}", "name": f"T5DR Online {version}", "draft": False, "prerelease": False,
        "html_url": f"https://github.com/TheWishin/T5DROnline/releases/tag/v{version}",
        "published_at": "2026-10-20T10:00:00Z",
        "body": ("**New.**\n\n### Game\n- [fixed](https://example.invalid) `rematch`\n\n---\n\n### Download\n\n"
                 "| | |\n|---|---|\n" + (f"| Code ID | `{code_id}` |\n" if code_id else "")),
        "assets": [
            {"name": "SHA256SUMS", "size": len(sums), "state": "uploaded", "browser_download_url": base + "SHA256SUMS"},
            {"name": zname, "size": len(zip_bytes), "state": "uploaded", "browser_download_url": base + zname,
             "digest": None if api_digest is None else "sha256:" + (digest if api_digest == "auto" else api_digest)},
        ],
    }
    return data, {base + "SHA256SUMS": sums.encode(), base + zname: zip_bytes}


class FakeResponse(io.BytesIO):
    def __init__(self, body, headers=None):
        super().__init__(body)
        self.headers = headers or {}

    def geturl(self):
        return ""


class FakeGitHub:
    """Stands in for updater.open_url: serves bytes per URL, and insists on the allow-list."""

    def __init__(self, files=None, api=None, api_status=200, api_headers=None):
        self.files = dict(files or {})
        self.api = api
        self.api_status = api_status
        self.api_headers = api_headers or {"ETag": 'W/"1"'}
        self.calls = []

    def __call__(self, url, headers=None, kind="download", timeout=None):
        assert updater.url_allowed(url, kind), (url, kind)
        self.calls.append((url, dict(headers or {})))
        if kind == "api":
            if isinstance(self.api_status, Exception):
                raise self.api_status
            if self.api_status != 200:
                raise urllib.error.HTTPError(url, self.api_status, "x", self.api_headers, io.BytesIO(b""))
            return FakeResponse(json.dumps(self.api).encode(), self.api_headers)
        if url not in self.files:
            raise urllib.error.HTTPError(url, 404, "not found", {}, io.BytesIO(b""))
        body = self.files[url]
        return FakeResponse(body, {"Content-Length": str(len(body))})


# --------------------------------------------------------------------------- versions

class Versions(unittest.TestCase):
    def test_order(self):
        order = ["0.1.0-preview", "0.1.8-preview", "0.1.9-preview", "1.0.0-preview", "1.0.0-preview.2",
                 "1.0.0-rc1", "1.0.0-rc2", "1.0.0-rc10", "1.0.0", "1.0.1-preview", "1.0.1", "1.1.0", "2.0.0"]
        keys = [updater.version_key(v) for v in order]
        self.assertNotIn(None, keys)
        self.assertEqual(keys, sorted(keys))
        for a, b in zip(order, order[1:]):
            self.assertTrue(updater.is_newer(b, a), (b, a))
            self.assertFalse(updater.is_newer(a, b), (a, b))

    def test_equal_v_prefix_and_build_metadata(self):
        self.assertFalse(updater.is_newer("v1.0.0", "1.0.0"))
        self.assertFalse(updater.is_newer("1.0.0+abc", "1.0.0"))
        self.assertTrue(updater.is_newer("v1.0.1", "1.0.0"))
        self.assertTrue(updater.is_newer("1.0.0", "1.0.0-preview"))   # a release beats its preview
        self.assertTrue(updater.is_newer("0.1.10-preview", "0.1.9-preview"))

    def test_dev_and_garbage_never_update(self):
        for local in ("dev", "", None, "1.0", "latest"):
            self.assertFalse(updater.is_newer("9.9.9", local), local)
        for remote in ("", "v", "1.0", "nightly", "1.0.0-", "1.0.0-a..b"):
            self.assertFalse(updater.is_newer(remote, "0.0.1"), remote)

    def test_local_version_from_release_json(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(updater.local_version(d), "dev")
            write(os.path.join(d, "release.json"), json.dumps({"version": "1.0.0"}))
            self.assertEqual(updater.local_version(d), "1.0.0")
            self.assertFalse(updater.is_release_install(d))          # no bundled Python
            write(os.path.join(d, "python", "pythonw.exe"), b"x")
            self.assertTrue(updater.is_release_install(d))


# --------------------------------------------------------------------------- URLs

class AllowList(unittest.TestCase):
    GOOD = [
        ("https://github.com/TheWishin/T5DROnline/releases/download/v1.0.0/T5DR-Online-1.0.0.zip", "download"),
        ("https://github.com/thewishin/t5dronline/releases/download/v1.0.0/SHA256SUMS", "download"),
        ("https://objects.githubusercontent.com/github-production-release-asset-2e65be/1423117739/654012155"
         "?X-Amz-Algorithm=AWS4-HMAC-SHA256", "download"),
        ("https://release-assets.githubusercontent.com/github-production-release-asset/1423117739/"
         "5aab6979-b9fd-41ef-9425-589f4cbb3ed1?sp=r&sv=2018-11-09&rscd=attachment", "download"),
        ("https://api.github.com/repos/TheWishin/T5DROnline/releases/latest", "api"),
        ("https://github.com/TheWishin/T5DROnline/releases/tag/v1.0.0", "page"),
    ]
    BAD = [
        ("http://github.com/TheWishin/T5DROnline/releases/download/v1/x.zip", "download"),       # not https
        ("https://github.com/TheWishin/T5DROnline-Dev/releases/download/v1/x.zip", "download"),  # private repo
        ("https://github.com/Someone/T5DROnline/releases/download/v1/x.zip", "download"),
        ("https://github.com/TheWishin/T5DROnline/archive/refs/tags/v1.zip", "download"),        # not a release file
        ("https://github.com/TheWishin/T5DROnline/releases/download/../../../evil/x.zip", "download"),
        ("https://github.com/TheWishin/T5DROnline/releases/download/v1/%2e%2e/x", "download"),
        ("https://github.com.evil.example/TheWishin/T5DROnline/releases/download/v1/x.zip", "download"),
        ("https://github.com@evil.example/TheWishin/T5DROnline/releases/download/v1/x.zip", "download"),
        ("https://user:pw@github.com/TheWishin/T5DROnline/releases/download/v1/x.zip", "download"),
        ("https://github.com:8443/TheWishin/T5DROnline/releases/download/v1/x.zip", "download"),
        ("https://objects.githubusercontent.com/github-production-release-asset-2e65be/999/1", "download"),
        ("https://release-assets.githubusercontent.com/github-production-release-asset/999/uuid", "download"),
        ("https://objects.githubusercontent.com.evil.example/github-production-release-asset-2e65be/"
         "1423117739/1", "download"),
        ("https://raw.githubusercontent.com/TheWishin/T5DROnline/main/x.zip", "download"),
        ("https://evil.example/TheWishin/T5DROnline/releases/download/v1/x.zip", "download"),
        ("https://api.github.com/repos/TheWishin/T5DROnline/releases/latest", "download"),        # API is not a file
        ("https://api.github.com/repos/Other/T5DROnline/releases/latest", "api"),
        ("https://github.com/TheWishin/T5DROnline/releases/download/v1/x.zip", "api"),
        ("https://evil.example/", "page"),
        ("file:///C:/x.zip", "download"),
        ("", "download"),
        ("https://[::1/x", "download"),
    ]

    def test_allowed(self):
        for url, kind in self.GOOD:
            self.assertTrue(updater.url_allowed(url, kind), url)

    def test_refused(self):
        for url, kind in self.BAD:
            self.assertFalse(updater.url_allowed(url, kind), url)

    def test_redirect_to_another_host_is_refused(self):
        h = updater._CheckedRedirects("download")
        req = urllib.request.Request("https://github.com/TheWishin/T5DROnline/releases/download/v1/x.zip")
        with self.assertRaises(updater.UpdateError):
            h.redirect_request(req, None, 302, "Found", {}, "https://evil.example/x.zip")
        with self.assertRaises(updater.UpdateError):
            h.redirect_request(req, None, 302, "Found", {}, "http://objects.githubusercontent.com/"
                                                           "github-production-release-asset-2e65be/1423117739/1")
        ok = h.redirect_request(req, None, 302, "Found", {}, self.GOOD[3][0])
        self.assertTrue(ok.full_url.startswith("https://release-assets.githubusercontent.com/"))

    def test_open_url_refuses_before_connecting(self):
        with mock.patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("connected")):
            with self.assertRaises(updater.UpdateError):
                updater.open_url("https://evil.example/x.zip")



# --------------------------------------------------------------------------- the release and the check

class Release(unittest.TestCase):
    def test_parse(self):
        data, _ = release("1.0.1", b"zipbytes", code_id="0123456789abcdef")
        rel = updater.parse_release(data)
        self.assertEqual(rel["version"], "1.0.1")
        self.assertEqual(rel["zip"]["name"], "T5DR-Online-1.0.1.zip")
        self.assertEqual(rel["zip"]["sha256"], hashlib.sha256(b"zipbytes").hexdigest())
        self.assertEqual(rel["code_id"], "0123456789abcdef")
        self.assertIn("• fixed rematch", rel["notes"])
        self.assertNotIn("Download", rel["notes"])                 # the facts after '---' are cut
        self.assertNotIn("https://example.invalid", rel["notes"])

    def test_refused_releases(self):
        data, _ = release("1.0.1", b"z")
        for change in (lambda d: d.update(draft=True),                       # a draft is never offered
                       lambda d: d.update(tag_name="nightly"),
                       lambda d: d.update(assets=[a for a in d["assets"] if a["name"] != "SHA256SUMS"]),
                       lambda d: d.update(assets=[a for a in d["assets"] if a["name"] == "SHA256SUMS"]),
                       lambda d: d["assets"][1].update(browser_download_url="https://evil.example/x.zip"),
                       lambda d: d["assets"][0].update(state="starter")):
            d = json.loads(json.dumps(data))
            change(d)
            with self.assertRaises(updater.UpdateError):
                updater.parse_release(d)

    def test_notes_are_cut(self):
        text = updater.notes_summary("\n".join(f"- line {i}" for i in range(200)))
        self.assertTrue(text.endswith("…"))
        self.assertLessEqual(text.count("\n"), updater.CHECK_INTERVAL)

    def test_sums(self):
        h = "ab" * 32
        self.assertEqual(updater.parse_sums(f"{h}  T5DR-Online-1.0.1.zip\n", "T5DR-Online-1.0.1.zip"), h)
        self.assertEqual(updater.parse_sums(f"{h.upper()} *T5DR-Online-1.0.1.zip", "T5DR-Online-1.0.1.zip"), h)
        self.assertIsNone(updater.parse_sums(f"{h}  other.zip\n", "T5DR-Online-1.0.1.zip"))
        self.assertIsNone(updater.parse_sums("garbage", "T5DR-Online-1.0.1.zip"))


class Check(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = os.path.join(self.tmp.name, updater.CACHE_FILE)
        self.data, _ = release("1.0.1", b"z")

    def tearDown(self):
        self.tmp.cleanup()

    def test_cached_for_an_hour_then_conditional(self):
        gh = FakeGitHub(api=self.data)
        rel, problem = updater.check_latest(self.cache, opener=gh, now=1000)
        self.assertEqual((rel["version"], problem), ("1.0.1", None))
        rel, _ = updater.check_latest(self.cache, opener=gh, now=1000 + 3500)
        self.assertEqual(len(gh.calls), 1)                         # from the cache
        gh.api_status = 304
        rel, problem = updater.check_latest(self.cache, opener=gh, now=1000 + 3700)
        self.assertEqual((rel["version"], problem), ("1.0.1", None))
        self.assertEqual(len(gh.calls), 2)
        self.assertEqual(gh.calls[1][1].get("If-None-Match"), 'W/"1"')   # 304s do not use up the limit
        self.assertEqual(gh.calls[1][0], updater.API_LATEST)

    def test_button_forces_a_new_check(self):
        gh = FakeGitHub(api=self.data)
        updater.check_latest(self.cache, opener=gh, now=1000)
        updater.check_latest(self.cache, opener=gh, now=1001, force=True)
        self.assertEqual(len(gh.calls), 2)

    def test_quiet_failures(self):
        for err in (urllib.error.URLError("no network"), OSError("down"), TimeoutError(), 500):
            gh = FakeGitHub(api=self.data, api_status=err)
            rel, problem = updater.check_latest(self.cache, opener=gh, now=1000, force=True)
            self.assertIsNone(rel)
            self.assertTrue(problem)
        gh = FakeGitHub(api={"not": "a release"})
        self.assertEqual(updater.check_latest(self.cache, opener=gh, now=1000, force=True)[0], None)

    def test_no_release_yet(self):
        gh = FakeGitHub(api_status=404)
        self.assertEqual(updater.check_latest(self.cache, opener=gh, now=1000), (None, None))

    def test_rate_limit_is_remembered(self):
        gh = FakeGitHub(api=self.data, api_status=403, api_headers={"X-RateLimit-Remaining": "0",
                                                                     "X-RateLimit-Reset": "5000"})
        rel, problem = updater.check_latest(self.cache, opener=gh, now=1000)
        self.assertIsNone(rel)
        self.assertTrue(problem)
        gh.api_status = 200
        rel, problem = updater.check_latest(self.cache, opener=gh, now=2000)   # at start: quiet
        self.assertEqual((rel, problem), (None, None))
        rel, problem = updater.check_latest(self.cache, opener=gh, now=2000, force=True)
        self.assertIn("wait", problem)
        self.assertEqual(len(gh.calls), 1)
        rel, problem = updater.check_latest(self.cache, opener=gh, now=5001)
        self.assertEqual(rel["version"], "1.0.1")


# --------------------------------------------------------------------------- download, check, unpack

class Prepare(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.install = os.path.join(self.tmp.name, "T5DR-Online-1.0.0")
        make_install(self.install)
        self.before = tree(self.install)

    def tearDown(self):
        self.tmp.cleanup()

    def prepare(self, data, files):
        rel = updater.parse_release(data)
        return updater.prepare_update(rel, self.install, opener=FakeGitHub(files))

    def assert_nothing_changed(self):
        self.assertEqual(tree(self.install), self.before)
        for d in updater.stage_roots(self.install):
            self.assertFalse(os.path.exists(d), d)

    def test_good_update_is_staged_next_to_the_install(self):
        z = make_zip("1.0.1")
        staged = self.prepare(*release("1.0.1", z))
        self.assertEqual(staged["sroot"], self.install + ".update")
        self.assertEqual(tree(staged["new"])["launcher/t5dr_launcher.pyw"], b"# new launcher\n")
        self.assertTrue(os.path.exists(os.path.join(staged["sroot"], "runner", "python", "pythonw.exe")))
        self.assertTrue(os.path.exists(os.path.join(staged["sroot"], "runner", "t5dr_update.py")))
        self.assertFalse(os.path.exists(os.path.join(staged["sroot"], "download", "T5DR-Online-1.0.1.zip")))
        self.assertEqual(tree(self.install), self.before)

    def test_checksum_mismatch_is_refused(self):
        z = make_zip("1.0.1")
        data, files = release("1.0.1", z, api_digest=None)
        url = data["assets"][1]["browser_download_url"]
        files[url] = z[:-1] + bytes([z[-1] ^ 1])                  # one bit flipped on the way
        with self.assertRaisesRegex(updater.UpdateError, "SHA-256"):
            self.prepare(data, files)
        self.assert_nothing_changed()

    def test_sums_disagree_with_github(self):
        z = make_zip("1.0.1")
        with self.assertRaisesRegex(updater.UpdateError, "disagree"):
            self.prepare(*release("1.0.1", z, api_digest="00" * 32))
        self.assert_nothing_changed()

    def test_sums_without_the_zip(self):
        z = make_zip("1.0.1")
        with self.assertRaisesRegex(updater.UpdateError, "no line"):
            self.prepare(*release("1.0.1", z, sums=("ab" * 32) + "  T5DR-Online-1.0.0.zip\n"))
        self.assert_nothing_changed()

    def test_short_download(self):
        z = make_zip("1.0.1")
        data, files = release("1.0.1", z)
        files[data["assets"][1]["browser_download_url"]] = z[:1000]
        with self.assertRaises(updater.UpdateError):
            self.prepare(data, files)
        self.assert_nothing_changed()

    def test_bad_archives(self):
        cases = {
            "zip slip": make_zip("1.0.1", {"T5DR-Online-1.0.1/../../evil.py": "x"}),
            "absolute": make_zip("1.0.1", {"/evil.py": "x"}),
            "backslash": make_zip("1.0.1", {"T5DR-Online-1.0.1/..\\..\\evil.py": "x"}),
            "drive": make_zip("1.0.1", {"C:/evil.py": "x"}),
            "second top folder": make_zip("1.0.1", {"Other/evil.py": "x"}),
            "player's native folder": make_zip("1.0.1", {"T5DR-Online-1.0.1/native/gamedata/x": "x"}),
            "player's settings": make_zip("1.0.1", {"T5DR-Online-1.0.1/launcher.json": "{}"}),
            "wrong version inside": make_zip("1.0.1", inner_version="1.0.9"),
            "wrong top folder": make_zip("1.0.1", top="T5DR-Online-1.0.2"),
        }
        for why, z in cases.items():
            with self.subTest(why):
                with self.assertRaises(updater.UpdateError):
                    self.prepare(*release("1.0.1", z))
                self.assert_nothing_changed()
                self.assertFalse(os.path.exists(os.path.join(self.tmp.name, "evil.py")))


# --------------------------------------------------------------------------- the swap

class Swap(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.install = os.path.join(self.tmp.name, "T5DR Online Ł東京")      # any folder name
        self.new = os.path.join(self.tmp.name, "stage", "new", "T5DR-Online-1.0.1")
        self.backup = os.path.join(self.tmp.name, "stage", "backup")
        make_install(self.install)
        make_new(self.new)
        self.before = tree(self.install)
        self.new_before = tree(self.new)

    def tearDown(self):
        self.tmp.cleanup()

    def player_files(self, t):
        return {k: v for k, v in t.items() if k.startswith("native/") or k in (
            "launcher.json", "launcher.log", "my game.pkg")}

    def test_swap_keeps_native_and_settings(self):
        mtime = os.path.getmtime(os.path.join(self.install, "native", "logs", "game-20261018-120000.log"))
        journal = updater.swap(self.install, self.new, self.backup, "1.0.1")
        after = tree(self.install)
        self.assertEqual(self.player_files(after), self.player_files(self.before))
        self.assertEqual(os.path.getmtime(os.path.join(self.install, "native", "logs",
                                                       "game-20261018-120000.log")), mtime)
        for rel, data in self.new_before.items():
            self.assertEqual(after[rel], data, rel)
        self.assertNotIn("tools/old_only.py", after)                 # a file the new release dropped
        self.assertEqual(tree(self.backup)["tools/old_only.py"], self.before["tools/old_only.py"])
        self.assertIn("lobby", journal["new"])
        self.assertNotIn("native", journal["old"] + journal["new"])
        self.assertEqual(updater.local_version(self.install), "1.0.1")

    def test_failed_move_rolls_back(self):
        calls = {"n": 0}

        def flaky(src, dst):
            if os.path.dirname(src) == self.new:
                calls["n"] += 1
                if calls["n"] == 4:
                    raise PermissionError(13, "in use (antivirus)", src)
            os.rename(src, dst)
        with self.assertRaises(updater.SwapFailed) as cm:
            updater.swap(self.install, self.new, self.backup, "1.0.1", move=flaky)
        self.assertEqual(cm.exception.problems, [])
        self.assertEqual(tree(self.install), self.before)            # exactly as before
        self.assertEqual(tree(self.new), self.new_before)            # the staged release is intact again

    def test_bad_new_release_rolls_back(self):
        write(os.path.join(self.new, "release.json"), json.dumps({"version": "1.0.9"}))
        with self.assertRaisesRegex(updater.SwapFailed, "release.json"):
            updater.swap(self.install, self.new, self.backup, "1.0.1")
        self.assertEqual(tree(self.install), self.before)

    def test_missing_python_rolls_back(self):
        os.remove(os.path.join(self.new, "python", "pythonw.exe"))
        with self.assertRaisesRegex(updater.SwapFailed, "pythonw"):
            updater.swap(self.install, self.new, self.backup, "1.0.1")
        self.assertEqual(tree(self.install), self.before)

    def test_release_with_players_files_is_refused(self):
        write(os.path.join(self.new, "native", "x"), "x")
        with self.assertRaises(updater.SwapFailed):
            updater.swap(self.install, self.new, self.backup, "1.0.1")
        self.assertEqual(tree(self.install), self.before)

    def test_undo_after_the_swap(self):
        journal = updater.swap(self.install, self.new, self.backup, "1.0.1")
        self.assertEqual(updater.undo(self.install, self.new, self.backup, journal["new"], journal["old"]), [])
        self.assertEqual(tree(self.install), self.before)

    def test_move_retries_while_a_file_is_held(self):
        src, dst = os.path.join(self.tmp.name, "a"), os.path.join(self.tmp.name, "b")
        write(src, "x")
        real = os.rename
        n = {"i": 0}

        def held(s, d):
            n["i"] += 1
            if n["i"] < 3:
                e = PermissionError(13, "held")
                e.winerror = 32
                raise e
            real(s, d)
        with mock.patch.object(updater.os, "rename", held):
            updater.move_with_retry(src, dst, timeout=5)
        self.assertTrue(os.path.exists(dst))
        write(src, "y")
        with self.assertRaises(FileExistsError):                     # never over an existing file
            updater.move_with_retry(src, dst)


class SwapStep(unittest.TestCase):
    """The detached step: a real Python process runs updater.py --apply, as after the launcher closed."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="t5dr_update_test_")
        self.install = os.path.join(self.tmp, "T5DR-Online-1.0.0")
        make_install(self.install)
        self.sroot = self.install + ".update"
        self.new = os.path.join(self.sroot, "new", "T5DR-Online-1.0.1")
        make_new(self.new)
        self.before = tree(self.install)

    def tearDown(self):
        # the stand-in launcher the step started (cwd = the install) may still be ending
        for _ in range(100):
            shutil.rmtree(self.tmp, ignore_errors=True)
            if not os.path.exists(self.tmp):
                break
            time.sleep(0.1)

    def run_step(self, launcher_code):
        """The 'launcher' the step starts is a tiny Python program (no window on this PC)."""
        staged = {"sroot": self.sroot, "new": self.new}
        launch = [sys.executable, "-c", launcher_code]
        proc = updater.start_swap(staged, "1.0.0", "1.0.1", out_dir=os.path.join(self.install, "native"),
                                  root=self.install, wait_pid=0, python=sys.executable, launch=launch)
        proc.wait(90)
        return proc.returncode, json.load(open(os.path.join(self.sroot, "result.json")))

    def no_scripts(self):
        for d in (self.install, self.sroot):
            for dp, _, fns in os.walk(d):
                self.assertFalse([f for f in fns if f.lower().endswith(SCRIPT_EXT)], dp)

    def test_update_and_confirm(self):
        code = "import os; open(os.environ['T5DR_UPDATE_CONFIRM'], 'w').write('ok')"
        rc, res = self.run_step(code)
        self.assertEqual(rc, 0, open(os.path.join(self.sroot, "swap.log")).read())
        self.assertTrue(res["ok"])
        self.assertEqual(res["phase"], "done")
        self.assertEqual(updater.local_version(self.install), "1.0.1")
        self.assertFalse(os.path.exists(os.path.join(self.sroot, "backup")))     # removed once confirmed
        self.assertEqual(tree(os.path.join(self.install, "native")),
                         {k[len("native/"):]: v for k, v in self.before.items() if k.startswith("native/")})
        self.no_scripts()
        # the new launcher reports it and cleans up
        ((sroot, r),) = updater.pending_results(self.install)
        self.assertTrue(updater.cleanup(sroot, r, logs_dir=os.path.join(self.install, "native", "logs")))
        self.assertFalse(os.path.exists(self.sroot))
        logs = os.listdir(os.path.join(self.install, "native", "logs"))
        self.assertTrue(any(f.startswith("update-") for f in logs), logs)

    def test_new_launcher_that_does_not_start_is_rolled_back(self):
        rc, res = self.run_step("import sys; sys.exit(1)")
        self.assertEqual(rc, 6, open(os.path.join(self.sroot, "swap.log")).read())
        self.assertFalse(res["ok"])
        self.assertTrue(res["rolled_back"])
        self.assertEqual(tree(self.install), self.before)
        self.no_scripts()

    def test_program_still_running_from_the_folder(self):
        plan = {"install": self.install, "new": self.new, "backup": os.path.join(self.sroot, "backup"),
                "from": "1.0.0", "to": "1.0.1", "wait_pid": 0, "launch": [sys.executable, "-c", "pass"]}
        path = os.path.join(self.sroot, "plan.json")
        write(path, json.dumps(plan))
        game = (4242, os.path.join(self.install, "native", "build", "cmake", "t5dr.exe"))
        with mock.patch.object(updater.time, "time", side_effect=[0, 0] + [100] * 50), \
                mock.patch.object(updater.time, "sleep"):
            rc = updater.apply_plan(path, list_processes=lambda dirs, exclude=(): [game])
        self.assertEqual(rc, 4)
        res = json.load(open(os.path.join(self.sroot, "result.json")))
        self.assertFalse(res["ok"])
        self.assertFalse(res["changed"])
        self.assertIn("t5dr.exe", res["error"])
        self.assertEqual(tree(self.install), self.before)


# --------------------------------------------------------------------------- never while playing

class Busy(unittest.TestCase):
    def app(self, **kw):
        game = mock.Mock()
        game.running.return_value = kw.pop("game_running", False)
        online = mock.Mock(spec=["host_proc", "match", "driver", "client"])
        online.host_proc = kw.pop("host_proc", None)
        online.match = kw.pop("match", None)
        online.driver = mock.Mock(ticket=kw.pop("ticket", None))
        online.client = mock.Mock(me={"status": kw.pop("status", "idle")})
        return mock.Mock(build=kw.pop("build", None), game=game, online=online,
                         settings=mock.Mock(out_dir="C:/x/native"))

    def test_reasons(self):
        none = lambda dirs, exclude=(): []      # noqa: E731
        self.assertIsNone(updater.busy_reason(self.app(), list_processes=none))
        self.assertIsNone(updater.busy_reason(self.app(status="room"), list_processes=none))
        for kw, word in ((dict(build=object()), "build"), (dict(game_running=True), "game"),
                         (dict(status="queue"), "online"), (dict(status="playing"), "online"),
                         (dict(status="match"), "online"), (dict(match={"id": 1}), "match"),
                         (dict(ticket="t1"), "match"), (dict(host_proc=object()), "Host")):
            self.assertIn(word, updater.busy_reason(self.app(**kw), list_processes=none), kw)
        other = lambda dirs, exclude=(): [(9, r"C:\x\native\build\cmake\t5dr.exe")]   # noqa: E731
        self.assertIn("t5dr.exe", updater.busy_reason(self.app(), list_processes=other))

    @unittest.skipUnless(os.name == "nt", "Windows process list")
    def test_process_list_sees_this_python(self):
        here = os.path.dirname(sys.executable)
        pids = [p for p, _ in updater.processes_under([here])]
        self.assertIn(os.getpid(), pids)
        self.assertNotIn(os.getpid(), [p for p, _ in updater.processes_under([here], exclude={os.getpid()})])


# --------------------------------------------------------------------------- around it

class Around(unittest.TestCase):
    def test_stage_folder_is_next_to_the_install(self):
        self.assertEqual(updater.stage_roots(r"C:\Games\T5DR")[0], r"C:\Games\T5DR.update")
        self.assertEqual(updater.stage_roots("C:\\")[-1], "C:\\.update")
        self.assertEqual(len(updater.stage_roots("C:\\")), 1)

    def test_cleanup_keeps_a_backup_that_was_not_restored(self):
        with tempfile.TemporaryDirectory() as d:
            s = os.path.join(d, "x.update")
            write(os.path.join(s, "backup", "launcher", "a.py"), "x")
            self.assertFalse(updater.cleanup(s, {"ok": False, "changed": True, "rolled_back": False}))
            self.assertTrue(os.path.exists(os.path.join(s, "backup", "launcher", "a.py")))
            self.assertTrue(updater.cleanup(s, {"ok": False, "changed": False}))

    def test_release_ships_the_updater(self):
        with open(os.path.join(ROOT, "tools", "package_release.py"), encoding="utf-8") as f:
            self.assertIn('"launcher/updater.py"', f.read())

    def test_play_tab_asks_for_one_build_after_a_code_change(self):
        import core
        with tempfile.TemporaryDirectory() as out:
            write(os.path.join(out, "build", "cmake", "t5dr.exe"), b"MZ")
            write(os.path.join(out, "game", "EBOOT.elf"), b"x")
            write(os.path.join(out, "build", "t5dr_build.json"), json.dumps({"code_id": "old"}))
            with mock.patch.object(core.build_game, "sha1", return_value=core.build_game.ELF_SHA1), \
                    mock.patch.object(core.build_game, "code_id", return_value="new"):
                st = core.game_state(out)
        self.assertTrue(st["needs_rebuild"])
        self.assertIn("Build the game once (about 2 minutes)", st["text"])

    def test_rebuild_hint_from_the_release_notes(self):
        with tempfile.TemporaryDirectory() as out:
            rel = {"code_id": "0123456789abcdef"}
            self.assertIsNone(updater.rebuild_needed(rel, out))                    # never built
            write(os.path.join(out, "build", "t5dr_build.json"), json.dumps({"code_id": "0123456789abcdef"}))
            self.assertFalse(updater.rebuild_needed(rel, out))
            self.assertTrue(updater.rebuild_needed({"code_id": "fedcba9876543210"}, out))
            self.assertIsNone(updater.rebuild_needed({"code_id": None}, out))


if __name__ == "__main__":
    unittest.main()
