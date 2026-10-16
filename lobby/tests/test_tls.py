"""Control channel over TLS with a self-signed certificate pinned by its SHA-256 fingerprint
(how a friend group runs it without a CA). Needs the openssl command (Git for Windows has one);
skipped without it."""
import hashlib
import os
import shutil
import ssl
import subprocess
import tempfile
import unittest

import util  # noqa: F401
from util import ServerThread, client, expect
from t5lobby.proto import LobbyError


def find_openssl():
    exe = shutil.which("openssl")
    if exe:
        return exe
    for p in (r"C:\Program Files\Git\usr\bin\openssl.exe", r"C:\Program Files\Git\mingw64\bin\openssl.exe"):
        if os.path.exists(p):
            return p
    return None


@unittest.skipIf(find_openssl() is None, "openssl not found")
class TlsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp()
        cls.cert = os.path.join(cls.dir, "cert.pem")
        cls.key = os.path.join(cls.dir, "key.pem")
        subprocess.run([find_openssl(), "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2",
                        "-subj", "/CN=t5lobby-test", "-keyout", cls.key, "-out", cls.cert],
                       check=True, capture_output=True)
        with open(cls.cert) as f:
            der = ssl.PEM_cert_to_DER_cert(f.read())
        cls.fp = hashlib.sha256(der).hexdigest()

    def setUp(self):
        self.s = ServerThread(tls_cert=self.cert, tls_key=self.key).start()
        self.clients = []

    def tearDown(self):
        for c in self.clients:
            c.close()
        self.s.stop()

    def test_pinned_certificate(self):
        fp = ":".join(self.fp[i:i + 2] for i in range(0, 64, 2)).upper()   # the format openssl prints
        a = client(self.s, "Alice", tls_fingerprint=fp, auto_ready=True)
        b = client(self.s, "Bob", tls_fingerprint=self.fp, auto_ready=True)
        self.clients += [a, b]
        a.quick_match()
        b.quick_match()
        self.assertEqual(expect(a, "match_start")["ticket"].opponent["name"], "Bob")

    def test_wrong_fingerprint_refused(self):
        with self.assertRaises(LobbyError) as e:
            self.clients.append(client(self.s, "Eve", tls_fingerprint="00" * 32))
        self.assertEqual(e.exception.code, "tls_mismatch")

    def test_plain_client_cannot_talk_to_tls_server(self):
        with self.assertRaises(LobbyError):
            c = util.LobbyClient(self.s.addr, util.BUILD, request_timeout=2)
            self.clients.append(c)
            c.connect(timeout=3)


if __name__ == "__main__":
    unittest.main()
