"""Updates: the launcher offers new releases and installs them itself, like Tekken 6 Native Online
("The launcher offers the update; the game is then updated by itself in a few seconds").

    python launcher/updater.py --check            the public repository's latest release (diagnostics)
    pythonw <runner>/t5dr_update.py --apply PLAN  the swap step; the launcher starts it (5. below)

1. Check. At start (at most once an hour; the answer is cached in update-check.json next to
   launcher.json) and from the "Check for updates" button, the latest *published* release of the
   public repository is read with GitHub's REST API, unauthenticated (60 requests an hour per
   address; a conditional request with the ETag does not count when nothing changed). That API
   never returns drafts, so a release the owner has not published yet (VirusTotal first) is never
   offered. No network, a rate limit or any other failure: nothing at start, a sentence on the button.
2. Offer: the version, a summary of the release notes, the download size, and whether the game has
   to be built once afterwards (the notes' "Code ID" against the build stamp).
3. Download and check: the zip and SHA256SUMS from the release's assets, https only, from
   github.com/TheWishin/T5DROnline/releases/download/... and GitHub's release-file storage for this
   repository's ID (objects.githubusercontent.com, and release-assets.githubusercontent.com where
   GitHub has sent release downloads since 2025); every redirect is checked. The zip's SHA-256 must
   match SHA256SUMS and the digest GitHub's API reports. Anything else is refused; nothing changes.
4. Stage: unpacked next to the install (<folder>.update\new -- the same drive, so the swap is a
   rename), every path in the archive checked (one top folder, no absolute or ".." paths, nothing
   named like the player's files); its release.json must name the offered version.
5. Swap: the running launcher cannot replace the Python it runs on. A copy of the bundled Python
   (<folder>.update\runner) runs this file with --apply, detached, once the launcher has closed: it
   waits for the launcher to exit and for nothing else to run from the folder, then moves the old
   program files (launcher, python, runtime, tools, lobby, docs, ...) to <folder>.update\backup and
   the new ones in. The player's files are never moved: native\ (unpacked game, build, saves, logs),
   launcher.json, launcher.log and anything else that is not a program file. No script file is
   involved (virus scanners flag .bat/.cmd/.ps1 in game downloads; the zip carries none).
6. Restart: the new launcher starts and confirms (T5DR_UPDATE_CONFIRM). If anything fails -- a move,
   the check of the new files, or the new launcher ends without confirming -- the old files go back
   and the old launcher starts and says why.
7. Rebuild: when the new version changes the game code (build_game.code_id()), the Play tab says
   "Build the game once (about 2 minutes)" and its button becomes BUILD GAME (core.game_state).

Never while a build, the game, an online match or search, "Host for friends" or any other program
from this folder runs (busy_reason(); the swap step looks at the processes again).

Everything above the Tk part uses only the standard library: the swap step runs this file on its own.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IS_WIN = os.name == "nt"

OWNER, REPO_NAME = "TheWishin", "T5DROnline"
REPO = f"{OWNER}/{REPO_NAME}"
# GitHub's numeric ID of that repository (api.github.com/repos/TheWishin/T5DROnline -> "id"). Release
# files are stored under it (.../github-production-release-asset/<id>/...); it never changes.
REPO_ID = "1423117739"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"
ASSET_HOSTS = ("objects.githubusercontent.com", "release-assets.githubusercontent.com")
RE_ASSET_PATH = re.compile(r"^/github-production-release-asset(?:-[0-9a-z]+)?/(\d+)/[^/]+$")

CHECK_INTERVAL = 3600            # seconds between two checks at start
CACHE_FILE = "update-check.json"
TIMEOUT = 15
MAX_SUMS = 64 * 1024
MAX_ZIP = 1_000_000_000          # the zip is ~90 MB
MAX_UNPACKED = 3_000_000_000     # ~250 MB unpacked
CONFIRM_ENV = "T5DR_UPDATE_CONFIRM"
CONFIRM_WAIT = 120               # seconds the swap step waits for the new launcher
NO_CHECK_ENV = "T5DR_NO_UPDATE_CHECK"

# Top-level names of the release folder that are program files (package_release.py's layout, plus
# the .cmd starter of developer zips). These are swapped; everything else in the folder is kept.
PROGRAM_ITEMS = ("T5DR Online.exe", "T5DR Online.cmd", "launcher", "lobby", "tools", "patches", "src",
                 "CMakeLists.txt", "docs", "CHANGELOG.md", "deps", "python", "toolchain", "runtime",
                 "LICENSES", "README.txt", "release.json")
# The player's files: never in a release, never moved. A zip that has one at its top is refused.
PROTECTED = ("native", "launcher.json", "launcher.log", "launcher.log.1", CACHE_FILE, ".update",
             "keys", "game", "build", "gamedata", "logs", "scratch")
_PROGRAM = {n.lower() for n in PROGRAM_ITEMS}
_PROTECTED = {n.lower() for n in PROTECTED}
RE_BAD_CHARS = re.compile(r'[<>:"|?*\x00-\x1f\\]')

DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_BREAKAWAY_FROM_JOB = 0x01000000


class UpdateError(Exception):
    """A plain sentence for the player; nothing was changed."""


class Cancelled(UpdateError):
    pass


class SwapFailed(Exception):
    def __init__(self, msg, problems=()):
        super().__init__(msg)
        self.problems = list(problems)


# --------------------------------------------------------------------------- versions

RE_VERSION = re.compile(r"^[vV]?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z]+(?:\.[0-9A-Za-z]+)*))?(?:\+[0-9A-Za-z.-]+)?$")


def _natural(s):
    return tuple((0, int(p), "") if p.isdigit() else (1, 0, p.lower()) for p in re.findall(r"\d+|\D+", s))


def version_key(v):
    """Sort key of a version (SemVer order; 1.0.0-preview < 1.0.0-rc2 < 1.0.0-rc10 < 1.0.0), or None."""
    m = RE_VERSION.match(str(v or "").strip())
    if not m:
        return None
    core = tuple(int(x) for x in m.group(1, 2, 3))
    if m.group(4) is None:
        return core, (1,)                     # a release sorts after all its pre-releases
    ids = tuple((0, int(p), ()) if p.isdigit() else (1, 0, _natural(p)) for p in m.group(4).split("."))
    return core, (0, ids)


def is_newer(remote, local):
    """True when `remote` is a later version than `local`. A development checkout ("dev") or an
    unreadable version is never offered anything."""
    r, l_ = version_key(remote), version_key(local)
    return bool(r and l_ and r > l_)


def local_version(root=ROOT):
    try:
        with open(os.path.join(root, "release.json"), encoding="utf-8") as f:
            return str(json.load(f).get("version") or "dev")
    except (OSError, ValueError, AttributeError):
        return "dev"


def is_release_install(root=ROOT):
    return (version_key(local_version(root)) is not None
            and os.path.exists(os.path.join(root, "python", "pythonw.exe")))


# --------------------------------------------------------------------------- URLs

def url_allowed(url, kind="download"):
    """kind 'api': GitHub's REST API for this repository. 'download': this repository's release
    files on github.com and GitHub's file storage for this repository's ID. 'page': this
    repository's pages on github.com (opened in the browser). https only, no user name, no port."""
    try:
        u = urllib.parse.urlsplit(str(url))
        port = u.port
    except ValueError:
        return False
    if u.scheme != "https" or u.username is not None or u.password is not None or port not in (None, 443):
        return False
    host = (u.hostname or "").lower().rstrip(".")
    path = urllib.parse.unquote(u.path)
    if "\\" in path or any(p in (".", "..") for p in path.split("/")):
        return False
    repo = f"/{OWNER}/{REPO_NAME}/".lower()
    if kind == "api":
        return host == "api.github.com" and path.lower().startswith("/repos" + repo)
    if kind == "page":
        return host == "github.com" and (path.lower() + "/").startswith(repo)
    if kind == "download":
        if host == "github.com":
            return path.lower().startswith(repo + "releases/download/")
        if host in ASSET_HOSTS:
            m = RE_ASSET_PATH.match(path)
            return bool(m and m.group(1) == REPO_ID)
    return False


def _host(url):
    try:
        return urllib.parse.urlsplit(url).hostname or url
    except ValueError:
        return url


class _CheckedRedirects(urllib.request.HTTPRedirectHandler):
    """Follow a redirect only to an allowed URL (https, this repository's files)."""
    max_redirections = 5

    def __init__(self, kind):
        super().__init__()
        self.kind = kind

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        newurl = urllib.parse.urljoin(req.full_url, newurl)
        if not url_allowed(newurl, self.kind):
            raise UpdateError(f"The download was sent to {_host(newurl)}, which is not GitHub's storage for "
                              "this project. Nothing was changed.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def user_agent():
    return f"T5DR-Online-launcher/{local_version()}"


def open_url(url, headers=None, kind="download", timeout=TIMEOUT):
    """urlopen for allowed URLs only, redirects checked. Raises UpdateError, urllib errors, OSError."""
    if not url_allowed(url, kind):
        raise UpdateError(f"Refused to download from {_host(url)}: not this project's GitHub releases.")
    req = urllib.request.Request(url, headers={"User-Agent": user_agent(), **(headers or {})})
    r = urllib.request.build_opener(_CheckedRedirects(kind)).open(req, timeout=timeout)
    if not url_allowed(r.geturl(), kind):         # belt and braces: where the bytes really came from
        r.close()
        raise UpdateError(f"The download came from {_host(r.geturl())}. Nothing was changed.")
    return r


# --------------------------------------------------------------------------- the release

def notes_summary(body, max_lines=40, max_chars=3000):
    """The release notes as plain text, without the download facts after the '---' line."""
    text = str(body or "").replace("\r\n", "\n")
    text = re.split(r"\n\s*-{3,}\s*\n", "\n" + text, maxsplit=1)[0]
    out = []
    for line in text.split("\n"):
        s = line.rstrip()
        s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s)          # [text](link) -> text
        s = re.sub(r"(\*\*|__)(.+?)\1", r"\2", s)
        s = s.replace("`", "")
        h = re.match(r"^\s*#{1,6}\s+(.*)$", s)
        if h:
            s = h.group(1).strip()
            if out and out[-1]:
                out.append("")
        s = re.sub(r"^(\s*)[-*+]\s+", lambda m: m.group(1) + "• ", s)
        if s or (out and out[-1]):
            out.append(s)
    while out and not out[-1]:
        out.pop()
    cut = len(out) > max_lines
    out = out[:max_lines]
    text = "\n".join(out)
    if len(text) > max_chars:
        text, cut = text[:max_chars].rsplit("\n", 1)[0], True
    return text + ("\n…" if cut else "")


def notes_code_id(body):
    """The 'Code ID' of the download facts (release_notes.py), or None."""
    m = re.search(r"Code ID\s*\|\s*`?([0-9a-f]{16})`?", str(body or ""))
    return m.group(1) if m else None


def parse_release(data):
    """The fields the launcher needs from GET /releases/latest. Raises UpdateError."""
    if not isinstance(data, dict) or data.get("draft"):
        raise UpdateError("GitHub did not return a published release.")
    tag = str(data.get("tag_name") or "")
    version = tag[1:] if tag[:1] in ("v", "V") else tag
    if version_key(version) is None:
        raise UpdateError(f"The latest release has an unexpected version ({tag!r}).")
    zip_name = f"T5DR-Online-{version}.zip"
    assets = {a.get("name"): a for a in (data.get("assets") or []) if isinstance(a, dict)}
    z, s = assets.get(zip_name), assets.get("SHA256SUMS")
    if not z or not s:
        raise UpdateError(f"Release {version} has no {zip_name} with SHA256SUMS yet.")
    for a in (z, s):
        if not url_allowed(a.get("browser_download_url"), "download"):
            raise UpdateError(f"Release {version}: {a.get('name')} is not on this project's GitHub releases.")
        if a.get("state", "uploaded") != "uploaded":
            raise UpdateError(f"Release {version}: {a.get('name')} is still being uploaded.")
    m = re.fullmatch(r"sha256:([0-9a-fA-F]{64})", str(z.get("digest") or ""))
    page = data.get("html_url")
    body = data.get("body") or ""
    return {
        "version": version, "tag": tag, "name": str(data.get("name") or f"T5DR Online {version}"),
        "published": str(data.get("published_at") or "")[:10], "prerelease": bool(data.get("prerelease")),
        "page": page if url_allowed(page, "page") else RELEASES_PAGE,
        "notes": notes_summary(body), "code_id": notes_code_id(body),
        "zip": {"name": zip_name, "url": z["browser_download_url"], "size": int(z.get("size") or 0),
                "sha256": m.group(1).lower() if m else None},
        "sums": {"url": s["browser_download_url"], "size": int(s.get("size") or 0)},
    }


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def _write_json(path, data):
    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1)
        os.replace(tmp, path)
    except OSError:
        pass


def check_latest(cache_path, force=False, opener=None, now=None):
    """(release or None, problem or None) -- never raises. Without force, an answer younger than an
    hour is reused. A rate limit is remembered until GitHub's reset time (also for force)."""
    now = time.time() if now is None else now
    opener = opener or open_url
    cache = _read_json(cache_path) or {}
    if cache.get("rate_reset", 0) > now:
        when = time.strftime("%H:%M", time.localtime(cache["rate_reset"]))
        return cache.get("release"), (f"GitHub asks to wait with update checks until {when}." if force else None)
    if not force and "release" in cache and 0 <= now - cache.get("checked", 0) < CHECK_INTERVAL:
        return cache.get("release"), None
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if cache.get("etag") and cache.get("release"):
        headers["If-None-Match"] = cache["etag"]
    try:
        with opener(API_LATEST, headers, "api") as r:
            data = json.loads(r.read(4_000_000).decode("utf-8"))
            etag = r.headers.get("ETag")
        rel = parse_release(data)
        cache = {"checked": now, "etag": etag, "release": rel}
    except urllib.error.HTTPError as e:
        hdr = e.headers or {}
        if e.code == 304:
            cache["checked"] = now
            rel = cache.get("release")
        elif e.code == 404:                      # no published release (yet)
            cache, rel = {"checked": now, "release": None}, None
        elif e.code in (403, 429):
            try:
                reset = float(hdr.get("X-RateLimit-Reset") or 0) or now + float(hdr.get("Retry-After") or 3600)
            except ValueError:
                reset = now + 3600
            cache["rate_reset"] = min(reset, now + 3 * 3600)
            _write_json(cache_path, cache)
            return None, "GitHub limits update checks right now. Try again later."
        else:
            return None, f"GitHub answered with error {e.code}. Try again later."
    except UpdateError as e:
        return None, str(e)
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return None, "No connection to GitHub. Check the internet connection and try again."
    _write_json(cache_path, cache)
    return rel, None


# --------------------------------------------------------------------------- download and stage

def download(url, dest, opener=None, max_bytes=MAX_ZIP, expect_size=None, progress=None, cancel=None):
    """Stream url to dest; returns its SHA-256 (hex)."""
    opener = opener or open_url
    h = hashlib.sha256()
    n = 0
    tmp = dest + ".part"
    try:
        with opener(url, {"Accept": "application/octet-stream"}, "download", timeout=60) as r, open(tmp, "wb") as f:
            total = expect_size or int(r.headers.get("Content-Length") or 0)
            if total > max_bytes:
                raise UpdateError("The download is far bigger than a release should be. Nothing was changed.")
            while True:
                if cancel is not None and cancel.is_set():
                    raise Cancelled("Cancelled.")
                b = r.read(1 << 18)
                if not b:
                    break
                n += len(b)
                if n > max_bytes:
                    raise UpdateError("The download is far bigger than a release should be. Nothing was changed.")
                h.update(b)
                f.write(b)
                if progress:
                    progress(n, total)
        if expect_size and n != expect_size:
            raise UpdateError(f"The download stopped early ({n:,} of {expect_size:,} bytes). Try again.")
        os.replace(tmp, dest)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    return h.hexdigest()


def parse_sums(text, name):
    """SHA-256 for `name` from a SHA256SUMS text ('<hex>  <name>' or '<hex> *<name>'), or None."""
    for line in str(text).splitlines():
        m = re.match(r"^([0-9a-fA-F]{64})\s+\*?(.+?)\s*$", line)
        if m and m.group(2) == name:
            return m.group(1).lower()
    return None


def _member_problem(name, top):
    if not name or "\\" in name or name.startswith("/") or RE_BAD_CHARS.search(name.replace("/", "")):
        return "not a plain relative path"
    parts = name.rstrip("/").split("/")
    if any(p in ("", ".", "..") for p in parts):
        return "'.', '..' or an empty part"
    if parts[0] != top:
        return f"outside the folder {top}"
    if len(parts) > 1 and len(parts) == 2 and parts[1].lower() in _PROTECTED:
        return "named like the player's own files"
    if len(parts) > 2 and parts[1].lower() in _PROTECTED:
        return "inside a folder named like the player's own files"
    return None


def unpack(zip_path, dest, version, progress=None, cancel=None):
    """Unpack the release zip into dest after checking every path; returns dest/T5DR-Online-<version>."""
    top = f"T5DR-Online-{version}"
    dest = os.path.abspath(dest)
    try:
        zf = zipfile.ZipFile(zip_path)
    except (OSError, zipfile.BadZipFile) as e:
        raise UpdateError(f"The download is not a readable zip ({e}). Nothing was changed.")
    with zf:
        infos = zf.infolist()
        total = 0
        for i in infos:
            why = _member_problem(i.filename, top)
            if why is None and (i.external_attr >> 16) & 0o170000 == 0o120000:
                why = "a symbolic link"
            if why:
                raise UpdateError(f"The download contains an unexpected path ({i.filename!r}: {why}). "
                                  "Nothing was changed.")
            total += i.file_size
        if total > MAX_UNPACKED:
            raise UpdateError("The download unpacks to far more than a release should. Nothing was changed.")
        done = 0
        for i in infos:
            if cancel is not None and cancel.is_set():
                raise Cancelled("Cancelled.")
            target = os.path.abspath(os.path.join(dest, *i.filename.rstrip("/").split("/")))
            if not target.startswith(dest + os.sep):
                raise UpdateError(f"The download contains an unexpected path ({i.filename!r}). Nothing was changed.")
            if i.is_dir():
                os.makedirs(target, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            try:
                with zf.open(i) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst, 1 << 20)
            except zipfile.BadZipFile as e:
                raise UpdateError(f"The download is damaged ({e}). Nothing was changed.")
            done += i.file_size
            if progress:
                progress(done, total)
    new = os.path.join(dest, top)
    info = _read_json(os.path.join(new, "release.json"))
    if not info or info.get("version") != version:
        raise UpdateError(f"The downloaded release does not say it is version {version}. Nothing was changed.")
    if not os.path.exists(os.path.join(new, "launcher", "t5dr_launcher.pyw")):
        raise UpdateError("The downloaded release has no launcher. Nothing was changed.")
    return new


def stage_roots(root=ROOT):
    """Where an update is staged: <folder>.update next to the install (same drive), else inside it."""
    root = os.path.abspath(root)
    parent, name = os.path.split(root.rstrip("\\/"))
    out = []
    if name and parent and os.path.normcase(parent) != os.path.normcase(root):
        out.append(os.path.join(parent, name + ".update"))
    out.append(os.path.join(root, ".update"))
    return out


def _new_stage_root(root):
    for d in stage_roots(root):
        try:
            if os.path.exists(d):
                shutil.rmtree(d)
            os.makedirs(d)
            with open(os.path.join(d, ".probe"), "w") as f:
                f.write("ok")
            os.remove(os.path.join(d, ".probe"))
            return d
        except OSError:
            continue
    raise UpdateError("The launcher cannot write next to its folder or into it, so it cannot update itself. "
                      "Download the zip from the releases page instead.")


def prepare_update(release, root=ROOT, opener=None, progress=None, cancel=None, need_python=True):
    """Download, check and unpack `release`, and prepare the swap step's Python. Returns
    dict(sroot, new). Raises UpdateError (or Cancelled); the staging folder is removed then.
    progress(stage, done, total): stage is 'download', 'verify', 'unpack', 'runner'."""
    progress = progress or (lambda *_: None)
    py_src = os.path.join(root, "python")
    if need_python and not os.path.exists(os.path.join(py_src, "pythonw.exe")):
        raise UpdateError("This folder has no python\\pythonw.exe, so the launcher cannot update itself "
                          "(a development checkout?). Download the zip from the releases page instead.")
    z = release["zip"]
    sroot = _new_stage_root(root)
    try:
        need = (z.get("size") or 100_000_000) * 4 + 200_000_000
        try:
            free = shutil.disk_usage(sroot).free
        except OSError:
            free = need
        if free < need:
            raise UpdateError(f"Not enough free disk space: the update needs about {need // 1_000_000} MB "
                              f"next to the folder, {free // 1_000_000} MB are free.")
        dl = os.path.join(sroot, "download")
        os.makedirs(dl)
        sums_path = os.path.join(dl, "SHA256SUMS")
        download(release["sums"]["url"], sums_path, opener, max_bytes=MAX_SUMS, cancel=cancel)
        with open(sums_path, encoding="utf-8", errors="replace") as f:
            want = parse_sums(f.read(), z["name"])
        if not want:
            raise UpdateError(f"SHA256SUMS of release {release['version']} has no line for {z['name']}. "
                              "Nothing was changed.")
        if z.get("sha256") and z["sha256"] != want:
            raise UpdateError("SHA256SUMS and GitHub disagree about the download's checksum. Nothing was changed.")
        zpath = os.path.join(dl, z["name"])
        got = download(z["url"], zpath, opener, expect_size=z.get("size") or None, cancel=cancel,
                       progress=lambda n, t: progress("download", n, t))
        progress("verify", 0, 0)
        if got != want:
            raise UpdateError(f"The download is damaged or not the published file: its SHA-256 is {got[:16]}..., "
                              f"SHA256SUMS says {want[:16]}.... Nothing was changed.")
        new = unpack(zpath, os.path.join(sroot, "new"), release["version"], cancel=cancel,
                     progress=lambda n, t: progress("unpack", n, t))
        os.remove(zpath)
        if need_python and not os.path.exists(os.path.join(new, "python", "pythonw.exe")):
            raise UpdateError("The downloaded release has no python\\pythonw.exe. Nothing was changed.")
        if need_python:
            progress("runner", 0, 0)
            runner = os.path.join(sroot, "runner")
            shutil.copytree(py_src, os.path.join(runner, "python"), ignore=shutil.ignore_patterns("__pycache__"))
            shutil.copy2(os.path.abspath(__file__), os.path.join(runner, "t5dr_update.py"))
        return {"sroot": sroot, "new": new}
    except BaseException as e:
        shutil.rmtree(sroot, ignore_errors=True)
        if isinstance(e, OSError) and not isinstance(e, UpdateError):
            raise UpdateError(f"Could not download or unpack the update ({e.strerror or e}). Nothing was "
                              "changed.") from e
        raise


def start_swap(staged, version_from, version_to, out_dir=None, root=ROOT, wait_pid=None, python=None, launch=None):
    """Write the plan and start the swap step detached (the bundled Python's copy in the staging
    folder runs this file). The launcher must close right after. Returns the process."""
    sroot = staged["sroot"]
    plan = {"install": os.path.abspath(root), "new": staged["new"], "backup": os.path.join(sroot, "backup"),
            "from": version_from, "to": version_to, "out_dir": out_dir,
            "wait_pid": os.getpid() if wait_pid is None else wait_pid,
            "expect_python": os.path.exists(os.path.join(root, "python", "pythonw.exe")),
            "created": time.strftime("%Y-%m-%d %H:%M:%S")}
    if launch:
        plan["launch"] = launch              # tests: the command that stands in for the new launcher
    plan_path = os.path.join(sroot, "plan.json")
    with open(plan_path, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=1)
    script = os.path.join(sroot, "runner", "t5dr_update.py")
    exe = python or os.path.join(sroot, "runner", "python", "pythonw.exe")
    if not os.path.exists(script):
        script = os.path.abspath(__file__)
    return _spawn([exe, "-B", script, "--apply", plan_path], cwd=sroot)


def _spawn(cmd, cwd, env=None):
    kw = dict(cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
              close_fds=True)
    if not IS_WIN:
        return subprocess.Popen(cmd, start_new_session=True, **kw)
    flags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    try:
        return subprocess.Popen(cmd, creationflags=flags | CREATE_BREAKAWAY_FROM_JOB, **kw)
    except OSError:                    # a job that does not allow breaking away
        return subprocess.Popen(cmd, creationflags=flags, **kw)


# --------------------------------------------------------------------------- processes (Windows)

def processes_under(dirs, exclude=()):
    """[(pid, exe path)] of the processes whose program lies in one of dirs (Windows; else [])."""
    if not IS_WIN:
        return []
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class PE(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("pid", wintypes.DWORD),
                    ("heap", ctypes.c_size_t), ("module", wintypes.DWORD), ("threads", wintypes.DWORD),
                    ("ppid", wintypes.DWORD), ("prio", ctypes.c_long), ("flags", wintypes.DWORD),
                    ("exe", ctypes.c_wchar * 260)]
    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    k32.Process32FirstW.argtypes = k32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PE)]
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                               ctypes.POINTER(wintypes.DWORD)]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    prefixes = [os.path.normcase(os.path.abspath(d)).rstrip("\\/") + os.sep for d in dirs if d]
    snap = k32.CreateToolhelp32Snapshot(2, 0)              # TH32CS_SNAPPROCESS
    if not snap or snap == ctypes.c_void_p(-1).value:
        return []
    found = []
    try:
        pe = PE()
        pe.dwSize = ctypes.sizeof(PE)
        ok = k32.Process32FirstW(snap, ctypes.byref(pe))
        while ok:
            pid = pe.pid
            if pid and pid not in exclude:
                h = k32.OpenProcess(0x1000, False, pid)    # PROCESS_QUERY_LIMITED_INFORMATION
                if h:
                    buf = ctypes.create_unicode_buffer(32768)
                    n = wintypes.DWORD(32768)
                    if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
                        p = os.path.normcase(buf.value)
                        if any(p.startswith(x) for x in prefixes):
                            found.append((pid, buf.value))
                    k32.CloseHandle(h)
            ok = k32.Process32NextW(snap, ctypes.byref(pe))
    finally:
        k32.CloseHandle(snap)
    return found


def wait_for_exit(pid, timeout):
    """True once process pid has ended (or cannot be seen), False after timeout seconds."""
    if not pid:
        return True
    if IS_WIN:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.OpenProcess.restype = wintypes.HANDLE
        k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        k32.CloseHandle.argtypes = [wintypes.HANDLE]
        h = k32.OpenProcess(0x00100000, False, int(pid))        # SYNCHRONIZE
        if not h:
            return True
        try:
            return k32.WaitForSingleObject(h, int(timeout * 1000)) == 0
        finally:
            k32.CloseHandle(h)
    end = time.time() + timeout
    while time.time() < end:
        try:
            os.kill(int(pid), 0)
        except OSError:
            return True
        time.sleep(0.2)
    return False


def busy_reason(app, out_dir=None, list_processes=None):
    """Why the launcher must not update now (one sentence), or None."""
    if getattr(app, "build", None):
        return "A build is running. Update when it is finished."
    game = getattr(app, "game", None)
    try:
        if game is not None and game.running():
            return "The game is running. Close it first, then update."
    except Exception:          # noqa: BLE001 -- a half-started game counts as running
        return "The game is running. Close it first, then update."
    o = getattr(app, "online", None)
    if o is not None:
        if getattr(o, "host_proc", None) is not None:
            return "'Host for friends' is running. Stop hosting first, then update."
        if getattr(o, "match", None) is not None:
            return "An online match was found. Update after the match."
        drv = getattr(o, "driver", None)
        if drv is not None and getattr(drv, "ticket", None) is not None:
            return "An online match is running. Update after the match."
        client = getattr(o, "client", None)
        me = getattr(client, "me", None) if client is not None else None
        if isinstance(me, dict) and me.get("status") in ("queue", "match", "playing"):
            return "You are searching for or playing an online match. Update afterwards."
    settings = getattr(app, "settings", None)
    out_dir = out_dir or getattr(settings, "out_dir", None)
    procs = (list_processes or processes_under)([ROOT, out_dir], exclude={os.getpid()})
    if procs:
        names = sorted({os.path.basename(p) for _, p in procs})
        return ("Other programs from this folder are still running (" + ", ".join(names) + "): another "
                "launcher window, the game or a lobby server. Close them, then update.")
    return None


# --------------------------------------------------------------------------- the swap (runs detached)

def move_with_retry(src, dst, timeout=20.0):
    """os.rename (never over an existing file), retried while antivirus or the indexer holds a file."""
    end = time.time() + timeout
    delay = 0.1
    while True:
        try:
            os.rename(src, dst)
            return
        except (FileExistsError, FileNotFoundError):
            raise
        except OSError as e:
            if time.time() >= end or getattr(e, "winerror", 5) not in (5, 32, 33, 145):
                raise
        time.sleep(delay)
        delay = min(delay * 2, 1.0)


def swap_plan(install, new_dir):
    """(old names to back up, new names to move in). Raises SwapFailed for a release that carries a
    name of the player's files."""
    news = sorted(os.listdir(new_dir))
    bad = [n for n in news if n.lower() in _PROTECTED]
    if bad:
        raise SwapFailed(f"the new release contains {', '.join(bad)} (the player's files)")
    new_lower = {n.lower() for n in news}
    olds = sorted(n for n in os.listdir(install) if n.lower() in _PROGRAM or n.lower() in new_lower)
    return olds, news


def verify_install(install, version, expect_python=True):
    info = _read_json(os.path.join(install, "release.json"))
    if not info or info.get("version") != version:
        raise SwapFailed(f"release.json does not say {version} after the swap")
    if not os.path.exists(os.path.join(install, "launcher", "t5dr_launcher.pyw")):
        raise SwapFailed("launcher\\t5dr_launcher.pyw is missing after the swap")
    if expect_python and not os.path.exists(os.path.join(install, "python", "pythonw.exe")):
        raise SwapFailed("python\\pythonw.exe is missing after the swap")


def undo(install, new_dir, backup, new_items, old_items, log=None, move=None):
    """Put the old program files back. Returns the problems (empty: fully undone)."""
    log = log or (lambda m: None)
    move = move or move_with_retry
    problems = []
    for n in reversed(list(new_items)):
        src = os.path.join(install, n)
        if os.path.lexists(src):
            try:
                move(src, os.path.join(new_dir, n))
                log(f"undo: {n} back to the staging folder")
            except OSError as e:
                problems.append(f"{n}: {e}")
                log(f"undo: could not move {n} out: {e}")
    for n in reversed(list(old_items)):
        try:
            move(os.path.join(backup, n), os.path.join(install, n))
            log(f"undo: {n} restored")
        except OSError as e:
            problems.append(f"{n}: {e}")
            log(f"undo: could not restore {n}: {e}")
    return problems


def swap(install, new_dir, backup, version, expect_python=True, log=None, move=None):
    """Move the old program files to backup and the new ones in; on any failure everything is put
    back (SwapFailed). Returns {'old': [...], 'new': [...]} (what moved, for undo())."""
    log = log or (lambda m: None)
    move = move or move_with_retry
    olds, news = swap_plan(install, new_dir)
    moved_old, moved_new = [], []
    try:
        os.makedirs(backup, exist_ok=True)
        for n in olds:
            move(os.path.join(install, n), os.path.join(backup, n))
            moved_old.append(n)
        log(f"moved to the backup: {', '.join(moved_old) or '-'}")
        for n in news:
            move(os.path.join(new_dir, n), os.path.join(install, n))
            moved_new.append(n)
        log(f"moved in: {', '.join(moved_new)}")
        verify_install(install, version, expect_python)
    except BaseException as e:
        log(f"swap failed: {e!r}; undoing")
        problems = undo(install, new_dir, backup, moved_new, moved_old, log, move)
        raise SwapFailed(_plain(e), problems) from e
    return {"old": moved_old, "new": moved_new}


def _plain(e):
    if isinstance(e, OSError):
        return f"{e.strerror or e} ({e.filename})" if e.filename else str(e.strerror or e)
    return str(e)


def launcher_command(install):
    py = os.path.join(install, "python", "pythonw.exe")
    if os.path.exists(py):
        return [py, os.path.join(install, "launcher", "t5dr_launcher.pyw")], True
    stub = os.path.join(install, "T5DR Online.exe")
    return ([stub], False) if os.path.exists(stub) else (None, False)


def wait_confirm(proc, marker, timeout, watch_exit=True):
    """True: the launcher confirmed. False: it ended without confirming. None: still starting."""
    end = time.time() + timeout
    while time.time() < end:
        if os.path.exists(marker):
            return True
        if watch_exit and proc is not None and proc.poll() is not None:
            time.sleep(0.5)
            return os.path.exists(marker)
        time.sleep(0.25)
    return None


def apply_plan(plan_path, confirm_wait=CONFIRM_WAIT, list_processes=None):
    """The swap step (run detached by start_swap, after the launcher closed). Exit code 0 = updated."""
    sroot = os.path.dirname(os.path.abspath(plan_path))
    logf = open(os.path.join(sroot, "swap.log"), "a", encoding="utf-8", errors="replace")

    def log(msg):
        logf.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
        logf.flush()

    plan = _read_json(plan_path) or {}
    install, new_dir, backup = plan.get("install"), plan.get("new"), plan.get("backup")
    result = {"ok": False, "from": plan.get("from"), "to": plan.get("to"), "pid": os.getpid(),
              "changed": False, "rolled_back": False, "problems": []}
    res_path = os.path.join(sroot, "result.json")
    list_processes = list_processes or processes_under
    launch = plan.get("launch")

    def finish(ok, error=None, start=True, env=None):
        result.update(ok=ok, error=error, time=time.strftime("%Y-%m-%d %H:%M:%S"))
        _write_json(res_path, result)
        log(f"result: {'updated' if ok else 'not updated'}{': ' + error if error else ''}")
        proc = None
        if start and install:
            others = [p for p in list_processes([install], exclude={os.getpid()})
                      if os.path.basename(p[1]).lower() in ("pythonw.exe", "python.exe")]
            if others:
                log("another launcher is running from the folder: not starting one")
            else:
                cmd, _ = (launch, True) if launch else launcher_command(install)
                if cmd:
                    try:
                        proc = _spawn(cmd, cwd=install, env=dict(os.environ, **(env or {})))
                        log(f"started {cmd[0]}")
                    except OSError as e:
                        log(f"could not start the launcher: {e}")
        return proc

    try:
        log(f"update {plan.get('from')} -> {plan.get('to')} in {install}")
        if not (install and new_dir and backup and plan.get("to")):
            finish(False, "the update plan is incomplete", start=bool(install))
            return 2
        if not wait_for_exit(plan.get("wait_pid"), 60):
            finish(False, "the launcher did not close", start=False)
            return 3
        dirs = [install] + ([plan["out_dir"]] if plan.get("out_dir") else [])
        end = time.time() + 30
        while True:
            busy = list_processes(dirs, exclude={os.getpid()})
            if not busy or time.time() >= end:
                break
            time.sleep(1)
        if busy:
            names = ", ".join(sorted({os.path.basename(p) for _, p in busy}))
            finish(False, f"programs from the folder were still running ({names}); close them and try again")
            return 4
        try:
            journal = swap(install, new_dir, backup, plan["to"], plan.get("expect_python", True), log)
        except SwapFailed as e:
            result.update(changed=bool(e.problems), rolled_back=not e.problems, problems=e.problems)
            finish(False, f"could not replace the program files: {e}")
            return 5
        result.update(changed=True, journal=journal, phase="swapped")
        marker = os.path.join(sroot, "confirm")
        proc = finish(True, env={CONFIRM_ENV: marker})
        watch = bool(launch) or launcher_command(install)[1]
        confirmed = wait_confirm(proc, marker, confirm_wait, watch_exit=watch) if proc else None
        if confirmed is False:
            log("the new launcher ended without starting up; putting the old files back")
            problems = undo(install, new_dir, backup, journal["new"], journal["old"], log)
            result.update(rolled_back=not problems, problems=problems, phase="undone")
            finish(False, f"the new launcher {plan['to']} did not start")
            return 6
        result["phase"] = "done"
        _write_json(res_path, result)
        shutil.rmtree(backup, ignore_errors=True)
        log("done" + (" (the launcher confirmed)" if confirmed else " (no confirmation yet)"))
        return 0
    except BaseException as e:       # noqa: BLE001 -- the old launcher must come back whatever happened
        log(f"unexpected error: {e!r}")
        if not result.get("changed"):
            finish(False, f"unexpected error: {e}")
        return 7
    finally:
        logf.close()


def confirm_started():
    """Called by a launcher started by the swap step: tells it the new launcher is up."""
    marker = os.environ.pop(CONFIRM_ENV, None)   # not inherited by the game
    if marker and os.path.basename(marker) == "confirm":
        try:
            with open(marker, "w") as f:
                f.write(str(os.getpid()))
        except OSError:
            pass


def pending_results(root=ROOT):
    """[(stage folder, result)] of finished swap steps (the launcher reports and cleans them up)."""
    out = []
    for d in stage_roots(root):
        res = _read_json(os.path.join(d, "result.json"))
        if res is not None:
            out.append((d, res))
    return out


def cleanup(sroot, result=None, logs_dir=None, wait=60.0):
    """After the swap step ended: keep its log in native\\logs, remove the staging folder."""
    if result and result.get("pid"):
        wait_for_exit(result["pid"], wait)
    src = os.path.join(sroot, "swap.log")
    if logs_dir and os.path.exists(src):
        try:
            os.makedirs(logs_dir, exist_ok=True)
            shutil.copy2(src, os.path.join(logs_dir, time.strftime("update-%Y%m%d-%H%M%S.log")))
        except OSError:
            pass
    if result and result.get("ok") is False and result.get("changed") and not result.get("rolled_back"):
        return False                     # the old files are still in backup\: keep them for the player
    shutil.rmtree(sroot, ignore_errors=True)
    return not os.path.exists(sroot)


def stale_stage_folders(root=ROOT, age=6 * 3600, now=None):
    """Staging folders without a result (a download the launcher was closed during), older than age."""
    now = time.time() if now is None else now
    out = []
    for d in stage_roots(root):
        if os.path.isdir(d) and not os.path.exists(os.path.join(d, "result.json")):
            try:
                if now - os.path.getmtime(d) > age:
                    out.append(d)
            except OSError:
                pass
    return out


# --------------------------------------------------------------------------- the launcher's side (Tk)

def _mb(n):
    return f"{n / 1e6:,.1f} MB"


def rebuild_needed(release, out_dir):
    """True/False when the release's code ID is known and a build stamp exists, else None."""
    stamp = _read_json(os.path.join(out_dir or "", "build", "t5dr_build.json")) if out_dir else None
    if not release.get("code_id") or not stamp or not stamp.get("code_id"):
        return None
    return release["code_id"] != stamp["code_id"]


class Updater:
    """The header button, the check at start, the offer window and the update itself.
    t5dr_launcher.App creates one: Updater(app, header_frame)."""

    def __init__(self, app, header=None, root=ROOT):
        self.app = app
        self.root = root
        self.local = local_version(root)
        self.cache_path = os.path.join(root, CACHE_FILE)
        self.release = None
        self.win = None
        self.worker = None
        self.cancel = threading.Event()
        self.readonly = bool(getattr(app, "readonly", False))
        confirm_started()
        self.button = None
        if header is not None:
            from tkinter import ttk
            self.button = ttk.Button(header, text="Check for updates", command=self.on_button)
            self.button.pack(side="right")
        if not self.readonly:
            app.after(700, self.report_last_update)
            if is_release_install(root) and not os.environ.get(NO_CHECK_ENV):
                app.after(4000, lambda: self.check(manual=False))

    # -------------------------------------------------------------- results of an earlier update
    def report_last_update(self):
        out_dir = getattr(getattr(self.app, "settings", None), "out_dir", None)
        logs = os.path.join(out_dir, "logs") if out_dir else None
        for sroot, res in pending_results(self.root):
            if res.get("ok") and res.get("to") == self.local:
                self._status(f"Updated from {res.get('from')} to {res.get('to')}.")
                try:
                    st = self.app.game_state() if hasattr(self.app, "game_state") else {}
                    if not st or "needs_rebuild" not in st:
                        import core
                        st = core.game_state(out_dir)
                    if st.get("needs_rebuild"):
                        self.app.nb.select(self.app.tabs["play"])
                except Exception:       # noqa: BLE001 -- only a convenience
                    pass
            elif not res.get("ok"):
                self._show_failure(sroot, res)
            threading.Thread(target=cleanup, args=(sroot, res, logs), daemon=True).start()
        for d in stale_stage_folders(self.root):
            threading.Thread(target=shutil.rmtree, args=(d, True), daemon=True).start()

    def _show_failure(self, sroot, res):
        from tkinter import messagebox
        to = res.get("to") or "the new version"
        if res.get("changed") and not res.get("rolled_back"):
            text = (f"The update to {to} failed and could not be undone completely: {res.get('error')}.\n\n"
                    f"The old program files are in\n{os.path.join(sroot, 'backup')}\n"
                    "Your game, saves and settings (the native folder) were not touched. Download the zip "
                    "from the releases page and extract it over this folder.")
        else:
            text = (f"The update to {to} did not work: {res.get('error')}.\n\nNothing was changed; this is "
                    f"still version {self.local}. Try again later, or download the zip from the releases page.")
        self.app.after(300, lambda: messagebox.showwarning("Update", text, parent=self.app))

    # -------------------------------------------------------------- check
    def on_button(self):
        if self.readonly:
            return
        if self.release and is_newer(self.release["version"], self.local):
            self.offer()
        else:
            self.check(manual=True)

    def check(self, manual):
        from tkinter import messagebox
        if not is_release_install(self.root):
            if manual:
                messagebox.showinfo("Updates", "This is a development checkout (no release.json and bundled "
                                    "Python), so it does not update itself. Use git, or a release zip from\n"
                                    + RELEASES_PAGE, parent=self.app)
            return
        if self.button is not None and manual:
            self.button.configure(text="Checking…", state="disabled")

        def work():
            rel, problem = check_latest(self.cache_path, force=manual)
            self.app.after(0, lambda: self._checked(rel, problem, manual))
        threading.Thread(target=work, daemon=True).start()

    def _checked(self, rel, problem, manual):
        from tkinter import messagebox
        if self.button is not None:
            self.button.configure(state="normal", text="Check for updates")
        if problem:
            if manual:
                messagebox.showinfo("Updates", f"Could not check for updates.\n\n{problem}", parent=self.app)
            return
        if rel and is_newer(rel["version"], self.local):
            self.release = rel
            if self.button is not None:
                self.button.configure(text=f"Update to {rel['version']}…")
            why = busy_reason(self.app)
            if manual or not why:
                self.offer()
            else:
                self._status(f"Version {rel['version']} is available. Click 'Update to {rel['version']}' at the "
                             "top when you are done.")
        elif manual:
            messagebox.showinfo("Updates", f"You have the newest version ({self.local}).", parent=self.app)

    def _status(self, text):
        try:
            if hasattr(self.app, "set_status"):
                self.app.set_status(text)
            else:
                self.app.status.set(text)
        except Exception:     # noqa: BLE001
            pass

    # -------------------------------------------------------------- offer
    def offer(self):
        import tkinter as tk
        from tkinter import ttk
        if self.win is not None and self.win.winfo_exists():
            self.win.lift()
            return
        rel = self.release
        w = self.win = tk.Toplevel(self.app)
        w.title("Update available")
        w.transient(self.app)
        w.resizable(True, True)
        w.minsize(560, 440)
        w.protocol("WM_DELETE_WINDOW", self.close_window)
        box = ttk.Frame(w, padding=(18, 14))
        box.pack(fill="both", expand=True)
        ttk.Label(box, text=f"T5DR Online {rel['version']} is available", style="H2.TLabel").pack(anchor="w")
        when = f", published {rel['published']}" if rel.get("published") else ""
        ttk.Label(box, wraplength=560, justify="left", text=(
            f"You have {self.local}. Download: {_mb(rel['zip']['size'])}{when}. The launcher downloads it, checks "
            "it, replaces its program files and starts again. Your game, saves and settings (the native folder) "
            "stay as they are.")).pack(anchor="w", pady=(4, 0))
        out_dir = getattr(getattr(self.app, "settings", None), "out_dir", None)
        rb = rebuild_needed(rel, out_dir)
        if rb is True:
            text, style = ("After this update the game is built once more (about 2 minutes): the Play tab offers "
                           "BUILD GAME. Only the code is rebuilt; the unpacked game and saves are kept."), "warn.TLabel"
        elif rb is False:
            text, style = "The game itself does not need to be built again.", "Muted.TLabel"
        else:
            text, style = ("If this update changes the game code, the Play tab asks you to build the game once "
                           "(about 2 minutes)."), "Muted.TLabel"
        ttk.Label(box, wraplength=560, justify="left", text=text, style=style).pack(anchor="w", pady=(4, 6))
        notes = tk.Text(box, height=12, wrap="word", relief="flat", font=("Segoe UI", 9), padx=8, pady=6)
        notes.insert("1.0", rel.get("notes") or "(no release notes)")
        notes.configure(state="disabled")
        notes.pack(fill="both", expand=True)
        self.progress = ttk.Progressbar(box, maximum=1000)
        self.msg = tk.StringVar(value="")
        self.err = tk.StringVar(value="")
        ttk.Label(box, textvariable=self.msg, style="Muted.TLabel").pack(anchor="w", pady=(6, 0))
        tk.Label(box, textvariable=self.err, fg="#cf222e", wraplength=560, justify="left",
                 font=("Segoe UI", 9, "bold")).pack(anchor="w")
        row = ttk.Frame(box)
        row.pack(fill="x", pady=(8, 0))
        self.b_update = ttk.Button(row, text="Update now", command=self.start_update)
        self.b_update.pack(side="left")
        self.b_later = ttk.Button(row, text="Later", command=self.close_window)
        self.b_later.pack(side="left", padx=8)
        ttk.Button(row, text="Release page", command=lambda: self._open_page(rel["page"])).pack(side="right")
        self.progress_row = row
        why = busy_reason(self.app)
        if why:
            self.err.set(why)
        w.after(50, lambda: (w.lift(), self.b_update.focus_set()))

    def _open_page(self, url):
        if url_allowed(url, "page"):
            import webbrowser
            webbrowser.open(url)

    def close_window(self):
        if self.worker is not None and self.worker.is_alive():
            self.cancel.set()
            self.msg.set("Cancelling…")
            return
        if self.win is not None:
            self.win.destroy()
            self.win = None

    # -------------------------------------------------------------- update
    def start_update(self):
        if self.readonly or (self.worker is not None and self.worker.is_alive()):
            return
        why = busy_reason(self.app)
        if why:
            self.err.set(why)
            return
        self.err.set("")
        self.cancel.clear()
        self.b_update.configure(state="disabled")
        self.b_later.configure(text="Cancel")
        self.progress.pack(fill="x", pady=(6, 0), before=self.progress_row)
        self.progress["value"] = 0
        rel = self.release
        self.msg.set("Downloading…")

        def progress(stage, n, total):
            self.app.after(0, lambda: self._progress(stage, n, total))

        def work():
            try:
                staged = prepare_update(rel, self.root, progress=progress, cancel=self.cancel)
            except UpdateError as e:
                self.app.after(0, lambda e=e: self._failed(str(e), isinstance(e, Cancelled)))
                return
            except Exception as e:           # noqa: BLE001 -- a bug must not leave the window stuck
                self.app.after(0, lambda e=e: self._failed(f"Unexpected error: {e}"))
                return
            self.app.after(0, lambda: self._ready(staged))
        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def _progress(self, stage, n, total):
        if self.win is None:
            return
        if stage == "download":
            self.progress["value"] = int(700 * n / total) if total else 0
            self.msg.set(f"Downloading… {_mb(n)}" + (f" of {_mb(total)}" if total else ""))
        elif stage == "verify":
            self.progress["value"] = 700
            self.msg.set("Checking the download (SHA-256)…")
        elif stage == "unpack":
            self.progress["value"] = 700 + (int(250 * n / total) if total else 0)
            self.msg.set(f"Unpacking… {int(100 * n / total) if total else 0}%")
        elif stage == "runner":
            self.progress["value"] = 960
            self.msg.set("Preparing the restart…")

    def _failed(self, text, cancelled=False):
        self.worker = None
        if self.win is None:
            return
        self.progress.pack_forget()
        self.msg.set("")
        self.err.set("" if cancelled else text)
        self.b_update.configure(state="normal", text="Try again" if not cancelled else "Update now")
        self.b_later.configure(text="Later")
        if cancelled:
            self.close_window()

    def _ready(self, staged):
        self.worker = None
        why = busy_reason(self.app)
        if why:
            shutil.rmtree(staged["sroot"], ignore_errors=True)
            self._failed(why)
            return
        out_dir = getattr(getattr(self.app, "settings", None), "out_dir", None)
        try:
            start_swap(staged, self.local, self.release["version"], out_dir=out_dir, root=self.root)
        except (OSError, UpdateError) as e:
            shutil.rmtree(staged["sroot"], ignore_errors=True)
            self._failed(f"Could not start the update step: {e}")
            return
        self.progress["value"] = 1000
        self.msg.set(f"Installing {self.release['version']}: the launcher restarts in a few seconds…")
        self._status(f"Updating to {self.release['version']}…")
        self.app.after(400, self._close_app)

    def _close_app(self):
        try:
            if self.win is not None:
                self.win.destroy()
                self.win = None
        finally:
            if hasattr(self.app, "on_close"):
                self.app.on_close()
            else:
                self.app.destroy()


def attach(app, header=None):
    """The launcher's hook (t5dr_launcher.App._layout)."""
    return Updater(app, header)


# --------------------------------------------------------------------------- command line

def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="print the latest published release (no cache)")
    ap.add_argument("--apply", metavar="PLAN", help="(the launcher starts this) swap in a staged release")
    a = ap.parse_args(argv)
    if a.apply:
        return apply_plan(a.apply)
    if a.check:
        rel, problem = check_latest(os.path.join(ROOT, CACHE_FILE), force=True)
        print(json.dumps({"local": local_version(), "latest": rel, "problem": problem,
                          "newer": bool(rel and is_newer(rel["version"], local_version()))}, indent=1))
        return 0 if not problem else 1
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
