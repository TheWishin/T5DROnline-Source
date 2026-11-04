"""Send a problem report zip to the lobby server (server/reports.py). Standard library only, blocking: the launcher
calls it on a worker thread. The same file is copied into the OpenRecomp launcher (openrecomp/report_upload.py); keep
the two the same.

    upload(host, port, zip_path, meta, tls="pin", fingerprint=FP, build={...}, progress=None) -> {"id", "webhook"}

Raises ReportError(code, msg, retry=None): code "unsupported" when the server takes no reports (an older server):
the launcher then offers Save only.

Only what the player confirmed is sent: the zip (made by problem_report.build, already cleaned of user names,
addresses, passwords and player names) and `meta` (game, version, build id, OS, the note, a contact and the lobby name
if the player gave them).
"""
import hashlib
import json
import os
import socket
import ssl

PROTO_VERSION = 1
FEATURE = "problem_reports"
UNSUPPORTED = "unsupported"     # ReportError.code: the server takes no reports (an older one): offer Save only
CLIENT = "report-upload/1"
META_KEYS = ("game", "version", "build_id", "os", "description", "contact", "name", "name_kind", "launcher", "language")
MAX_LINE = 1 << 20


class ReportError(Exception):
    def __init__(self, code, msg="", retry=None):
        super().__init__(f"{code}: {msg}" if msg else code)
        self.code, self.msg, self.retry = code, msg, retry


def _line(obj):
    return (json.dumps(obj, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8", "replace")


class _Conn:
    def __init__(self, host, port, tls, fingerprint, timeout):
        try:
            raw = socket.create_connection((host, port), timeout=timeout)
        except OSError as e:
            raise ReportError("connect_failed", f"cannot reach the server ({type(e).__name__})") from None
        self.sock = raw
        try:
            if tls in ("pin", "ca"):
                ctx = ssl.create_default_context()
                if tls == "pin":
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                self.sock = ctx.wrap_socket(raw, server_hostname=host if tls == "ca" else None)
                if tls == "pin":
                    der = self.sock.getpeercert(binary_form=True)
                    want = (fingerprint or "").replace(":", "").strip().lower()
                    if not want or hashlib.sha256(der).hexdigest() != want:
                        raise ReportError("tls_mismatch", "the server's certificate does not match the pinned one")
        except ReportError:
            self.close()
            raise
        except (OSError, ssl.SSLError) as e:
            self.close()
            raise ReportError("connect_failed", f"secure connection failed ({type(e).__name__})") from None
        self.f = self.sock.makefile("rb")
        self.rid = 0

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass

    def send(self, obj):
        self.sock.sendall(_line(obj))

    def request(self, obj, timeout):
        self.rid += 1
        rid = self.rid
        self.send(dict(obj, rid=rid))
        return self.reply(rid, timeout)

    def reply(self, rid, timeout):
        self.sock.settimeout(timeout)
        while True:
            try:
                line = self.f.readline(MAX_LINE)
            except socket.timeout:
                raise ReportError("timeout", "the server did not answer") from None
            except OSError as e:
                raise ReportError("disconnected", f"the connection broke ({type(e).__name__})") from None
            if not line:
                raise ReportError("disconnected", "the server closed the connection")
            try:
                msg = json.loads(line.decode("utf-8"))
            except ValueError:
                continue
            if not isinstance(msg, dict):
                continue
            if msg.get("re") == rid or (msg.get("t") == "error" and msg.get("re") is None and _fatal(msg)):
                if msg.get("t") == "error":
                    raise ReportError(str(msg.get("code") or "error"), str(msg.get("msg") or ""), msg.get("retry"))
                return msg


def _fatal(msg):
    """An error without "re" that ends the connection (flooding, server full, a timeout) -- the waiting request's
    answer. (The server's "login timeout" after report_done comes once the reply is read: never seen here.)"""
    return msg.get("code") in ("rate_limited", "server_full", "not_allowed", "bad_request")


def clean_meta(meta):
    out = {}
    for k in META_KEYS:
        v = (meta or {}).get(k)
        if isinstance(v, str) and v.strip():
            out[k] = v.strip()[:1000]
    return out


def server_takes_reports(host, port, tls="pin", fingerprint="", timeout=8.0):
    """-> max bytes the server takes, or 0 when it takes none (an older server, or reports switched off)."""
    c = _Conn(host, port, tls, fingerprint, timeout)
    try:
        w = c.request({"t": "hello", "proto": PROTO_VERSION, "client": CLIENT, "purpose": "report",
                       "caps": [FEATURE], "build": {}}, timeout)
        return _max_bytes(w)
    finally:
        c.close()


def _max_bytes(welcome):
    rep = welcome.get("reports")
    if FEATURE not in (welcome.get("features") or []) or not isinstance(rep, dict):
        return 0
    try:
        return max(0, int(rep.get("max_bytes", 0)))
    except (TypeError, ValueError):
        return 0


def upload(host, port, zip_path, meta, tls="pin", fingerprint="", build=None, progress=None, timeout=20.0):
    """Send the zip. progress(sent, total) is called while the bytes go out. -> {"id": "K7QF2M", "webhook": bool}."""
    with open(zip_path, "rb") as f:
        data = f.read()
    c = _Conn(host, port, tls, fingerprint, timeout)
    try:
        w = c.request({"t": "hello", "proto": PROTO_VERSION, "client": CLIENT, "purpose": "report",
                       "caps": [FEATURE], "build": build or {}}, timeout)
        limit = _max_bytes(w)
        if not limit:
            raise ReportError(UNSUPPORTED, "this server does not take problem reports")
        if len(data) > limit:
            raise ReportError("report_size", f"the report is {len(data)} bytes, the server takes {limit}")
        go = c.request({"t": "report_begin", "size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                        "meta": clean_meta(meta)}, timeout)
        if go.get("t") != "report_go" or not isinstance(go.get("id"), str):
            raise ReportError("bad_reply", "the server did not start the report")
        c.rid += 1
        rid = c.rid
        c.sock.settimeout(max(timeout, 60.0))
        try:
            c.send({"t": "report_data", "id": go["id"], "rid": rid})
            step = 64 * 1024
            for off in range(0, len(data), step):
                c.sock.sendall(data[off:off + step])
                if progress is not None:
                    progress(min(off + step, len(data)), len(data))
        except OSError as e:
            raise ReportError("disconnected", f"the connection broke while sending ({type(e).__name__})") from None
        done = c.reply(rid, max(timeout, 120.0))
        if done.get("t") != "report_done":
            raise ReportError("bad_reply", "the server did not confirm the report")
        return {"id": str(done.get("id") or go["id"]), "webhook": bool(done.get("webhook"))}
    finally:
        c.close()


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="send a problem report zip to a lobby server (testing)")
    ap.add_argument("server", help="host:port")
    ap.add_argument("zip")
    ap.add_argument("--tls", default="off", choices=("off", "pin", "ca"))
    ap.add_argument("--fingerprint", default="")
    ap.add_argument("--note", default="")
    a = ap.parse_args(argv)
    host, _, port = a.server.rpartition(":")
    r = upload(host, int(port), a.zip, {"description": a.note, "game": "test", "os": os.name}, a.tls, a.fingerprint)
    print(f"sent: report #{r['id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
