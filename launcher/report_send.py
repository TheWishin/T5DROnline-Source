"""'Send to the developer' for the report window (problem_report_ui.py): which server takes the report, what goes
along with the zip, and the upload itself (lobby/t5lobby/report_upload.py).

The report always goes to the project's own lobby server (the default entry of the release's lobby/servers.json),
never to a server the player added: a friend's server is not the developer. Sent with the zip: the game, its
version and build id, Windows' version, what the player wrote, a contact if they gave one, and the lobby name the
launcher knows (guest or account) -- the window says so before anything is sent.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LOBBY = os.path.join(os.path.dirname(HERE), "lobby")
if LOBBY not in sys.path:
    sys.path.append(LOBBY)

GAME = "T5DR Online"


class Sender:
    def __init__(self, entry, meta, build_info=None):
        self.entry = entry          # servers.ServerEntry
        self.meta = dict(meta)      # game, version, os, name, name_kind, launcher, language
        self.build_info = build_info    # dict, or a function making it (problem_report.build_info_for: it hashes the game)

    def _args(self):
        return self.entry.host, self.entry.port, self.entry.tls, self.entry.fingerprint

    def probe(self, timeout=8.0):
        """-> the largest zip the server takes, 0 when it takes none (an older server). Raises on no connection."""
        from t5lobby import report_upload as up
        host, port, tls, fp = self._args()
        return up.server_takes_reports(host, port, tls, fp, timeout)

    def send(self, zip_path, note="", contact="", progress=None):
        """-> {"id": ..., "webhook": bool}; raises report_upload.ReportError."""
        from t5lobby import report_upload as up
        host, port, tls, fp = self._args()
        try:
            info = (self.build_info() if callable(self.build_info) else self.build_info) or {}
        except Exception:      # noqa: BLE001 -- not built: the report goes without a build id
            info = {}
        meta = dict(self.meta, description=note.strip(), contact=contact.strip(),
                    build_id=str(info.get("build_id") or ""))
        build = {"id": meta["build_id"], "release": meta.get("version", "")}
        return up.upload(host, port, zip_path, meta, tls, fp, build=build, progress=progress)


def official_entry():
    """The project's lobby server (the release's servers.json default), or None. T5_REPORT_SERVER=host:port (plain
    TCP, tests and a local lobby only) sends elsewhere."""
    try:
        from t5lobby import servers
        test = os.environ.get("T5_REPORT_SERVER", "").strip()
        if test:
            return servers.parse_address(test, "test")
        entries, _problems = servers.load(None)
        return servers.default_entry(entries)
    except Exception:      # noqa: BLE001 -- no lobby files in this copy: Save only
        return None


def os_line():
    try:
        import problem_report as report
        return report.windows_version()
    except Exception:      # noqa: BLE001
        import platform
        return platform.platform()


def make_sender(release=None, build_info=None, name="", name_kind="", language=""):
    """A Sender for this copy, or None when it has no server to send to. build_info: problem_report.build_info_for."""
    entry = official_entry()
    if entry is None or not entry.host:
        return None
    release = release or {}
    meta = {"game": GAME, "version": str(release.get("version") or "dev"), "os": os_line(), "name": name or "",
            "name_kind": name_kind or "", "launcher": "T5DR launcher", "language": language or ""}
    return Sender(entry, meta, build_info)
