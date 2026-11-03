"""One shared, short-lived release lookup for the launcher's pre-login welcome.

`admin release` remains the authority for what the lobby announces. GitHub supplies the same
published-release metadata the updater used to fetch itself; clients still validate it and verify
the downloaded release signature. A missing, stale or failed lookup means GitHub fallback.
"""
import asyncio
import json
import logging
import re
import time
import urllib.error
import urllib.request

log = logging.getLogger("t5lobby.releases")
API_LATEST = "https://api.github.com/repos/TheWishin/T5DROnline/releases/latest"
REFRESH_SECONDS = 300
MIN_REQUEST_SECONDS = 60
MAX_RESPONSE = 4_000_000
MAX_METADATA = 256 * 1024


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch_release():
    """Fetch metadata only, from the fixed project endpoint; never follow a redirect."""
    req = urllib.request.Request(API_LATEST, headers={
        "User-Agent": "T5DR-Online-lobby", "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"})
    with urllib.request.build_opener(_NoRedirects()).open(req, timeout=15) as response:
        data = response.read(MAX_RESPONSE + 1)
    if len(data) > MAX_RESPONSE:
        raise ValueError("release metadata too large")
    return json.loads(data.decode("utf-8"))


def release_metadata(data, version):
    """Only the announced, published stable version, with the updater's original fields."""
    version = str(version or "").lstrip("vV")
    if not re.fullmatch(r"\d+\.\d+\.\d+", version) or not isinstance(data, dict):
        return None
    if data.get("draft") or data.get("prerelease") or str(data.get("tag_name") or "").lstrip("vV") != version:
        return None
    fields = ("tag_name", "name", "draft", "prerelease", "html_url", "published_at", "body")
    metadata = {key: data[key] for key in fields if key in data}
    wanted = {f"T5DR-Online-{version}.zip", "SHA256SUMS", "SHA256SUMS.sig"}
    assets = data.get("assets")
    if not isinstance(assets, list):
        return None
    metadata["assets"] = [
        {key: asset[key] for key in ("name", "size", "state", "browser_download_url", "digest") if key in asset}
        for asset in assets if isinstance(asset, dict) and asset.get("name") in wanted]
    # Keep ample space for the rest of welcome within MAX_LINE_FROM_SERVER (1 MiB).
    if len(json.dumps(metadata, ensure_ascii=True).encode("utf-8")) > MAX_METADATA:
        return None
    return metadata


class ReleaseCache:
    def __init__(self):
        self.version = ""
        self.data = None
        self.expires = 0
        self.next_check = 0
        self.not_before = 0

    def public(self, version):
        if version == self.version and time.monotonic() < self.expires:
            return self.data
        return None

    async def refresh(self, version):
        now = time.monotonic()
        if version != self.version:
            self.version, self.data, self.expires = version, None, 0
            self.next_check = 0
        if not version or now < max(self.next_check, self.not_before):
            return
        self.next_check = now + REFRESH_SECONDS
        self.not_before = now + MIN_REQUEST_SECONDS
        try:
            data = await asyncio.to_thread(fetch_release)
            self.data = release_metadata(data, version)
            self.expires = now + REFRESH_SECONDS if self.data else 0
        except (OSError, ValueError, TypeError, AttributeError, RecursionError) as error:
            self.data, self.expires = None, 0
            if isinstance(error, urllib.error.HTTPError) and error.code in (403, 429):
                headers = error.headers or {}
                try:
                    delay = (max(float(headers.get("Retry-After") or 0),
                                 float(headers.get("X-RateLimit-Reset") or 0) - time.time())
                             if headers.get("Retry-After") or headers.get("X-RateLimit-Reset") else 3600)
                    self.not_before = now + max(REFRESH_SECONDS, min(delay, 3 * 3600))
                except (ValueError, TypeError, OverflowError):
                    self.not_before = now + 3600
            log.warning("release metadata unavailable (%s)", type(error).__name__)

    async def run(self, version):
        while True:
            await self.refresh(version())
            await asyncio.sleep(5)
