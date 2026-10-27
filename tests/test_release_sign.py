"""tools/release_sign.py: the release signature's keys, signing in the release workflow, checking.
Every key here is made by the test and thrown away; no real key is ever read."""
import contextlib
import hashlib
import io
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

from helpers import ROOT

sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "launcher"))
import release_sign  # noqa: E402
import release_sig  # noqa: E402


def sums_for(version, payload=b"zip"):
    return f"{hashlib.sha256(payload).hexdigest()}  T5DR-Online-{version}.zip\n".encode()


class ReleaseSign(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name
        self.seed = os.urandom(32)
        self.pub = release_sig.public_key(self.seed).hex()
        self.dist = os.path.join(self.d, "dist")
        os.makedirs(self.dist)
        with open(os.path.join(self.dist, "SHA256SUMS"), "wb") as f:
            f.write(sums_for("1.1.2"))

    def tearDown(self):
        self.tmp.cleanup()

    def run_main(self, *argv, env=None):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, env or {}, clear=False), contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err):
            code = release_sign.main(list(argv))
        return code, out.getvalue() + err.getvalue()

    def test_keygen_writes_outside_the_repository_only(self):
        inside = os.path.join(ROOT, "build", "never-a-key.txt")
        code, text = self.run_main("keygen", "--out", inside)
        self.assertEqual(code, 1)
        self.assertIn("inside the repository", text)
        self.assertFalse(os.path.exists(inside))
        out = os.path.join(self.d, "key.txt")
        code, text = self.run_main("keygen", "--out", out)
        self.assertEqual(code, 0, text)
        with open(out) as f:
            seed = bytes.fromhex(f.read().strip())
        self.assertIn(release_sig.public_key(seed).hex(), text)
        self.assertNotIn(seed.hex(), text)                        # the private key is never printed
        code, text = self.run_main("keygen", "--out", out)       # never overwrites a key
        self.assertEqual(code, 1)
        with open(out) as f:
            self.assertEqual(f.read().strip(), seed.hex())

    def test_public_key_never_shows_the_private_one(self):
        code, text = self.run_main("public-key", env={release_sign.KEY_ENV: self.seed.hex()})
        self.assertEqual(code, 0, text)
        self.assertIn(self.pub, text)
        self.assertNotIn(self.seed.hex(), text)

    def test_add_public_key(self):
        path = os.path.join(self.d, "updater.py")
        shutil.copy(release_sign.UPDATER, path)
        self.assertEqual(release_sign.updater_keys(path), release_sign.updater_keys())
        self.assertTrue(release_sign.add_public_key(self.pub, path))
        self.assertFalse(release_sign.add_public_key(self.pub.upper(), path))     # once
        other = release_sig.public_key(os.urandom(32)).hex()
        self.assertTrue(release_sign.add_public_key(other, path))
        self.assertEqual(release_sign.updater_keys(path)[-2:], (self.pub, other))
        with open(path, encoding="utf-8") as f:
            compile(f.read(), path, "exec")
        with self.assertRaises(ValueError):
            release_sign.add_public_key("ab" * 31, path)                          # not 64 hex digits

    def test_sign_and_verify(self):
        sums, sig = os.path.join(self.dist, "SHA256SUMS"), os.path.join(self.dist, "SHA256SUMS.sig")
        kid = release_sign.sign("1.1.2", sums, sig, self.seed, keys=(self.pub,))
        self.assertEqual(release_sign.verify("1.1.2", sums, sig, [self.pub]), kid)
        with self.assertRaises(release_sig.SignatureError):
            release_sign.verify("1.1.3", sums, sig, [self.pub])
        with self.assertRaises(release_sign.Fail):                 # SHA256SUMS of another version
            release_sign.sign("1.1.3", sums, sig, self.seed, keys=(self.pub,))
        code, text = self.run_main("verify", "--version", "1.1.2", "--sums", sums, "--sig", sig,
                                   "--public-key", self.pub)
        self.assertEqual(code, 0, text)

    def test_sign_refuses_a_key_the_launcher_does_not_have(self):
        sums, sig = os.path.join(self.dist, "SHA256SUMS"), os.path.join(self.dist, "SHA256SUMS.sig")
        other = release_sig.public_key(os.urandom(32)).hex()
        with self.assertRaisesRegex(release_sign.Fail, "RELEASE_PUBLIC_KEYS"):
            release_sign.sign("1.1.2", sums, sig, self.seed, keys=(other,))
        self.assertFalse(os.path.exists(sig))

    def test_ci_step(self):
        sig = os.path.join(self.dist, "SHA256SUMS.sig")
        env = {release_sign.KEY_ENV: ""}
        with mock.patch.dict(os.environ, env), mock.patch.object(release_sign, "updater_keys", return_value=()):
            self.assertEqual(release_sign.ci("1.1.2", self.dist)[0], 0)          # nothing set up: unsigned
        self.assertFalse(os.path.exists(sig))
        with mock.patch.dict(os.environ, env), mock.patch.object(release_sign, "updater_keys",
                                                                 return_value=(self.pub,)):
            code, msg = release_sign.ci("1.1.2", self.dist)                       # key shipped, secret missing
            self.assertEqual(code, 1)
            self.assertIn("missing", msg)
        env = {release_sign.KEY_ENV: self.seed.hex()}
        with mock.patch.dict(os.environ, env), mock.patch.object(release_sign, "updater_keys",
                                                                 return_value=(self.pub,)):
            code, msg = release_sign.ci("1.1.2", self.dist)
            self.assertEqual(code, 0, msg)
            self.assertNotIn(self.seed.hex(), msg)
        with open(sig, "rb") as f, open(os.path.join(self.dist, "SHA256SUMS"), "rb") as g:
            release_sig.check_sig_file(f.read(), "1.1.2", g.read(), [self.pub])
        with mock.patch.dict(os.environ, env), mock.patch.object(release_sign, "updater_keys", return_value=()):
            with self.assertRaises(release_sign.Fail):                           # secret, but no key shipped
                release_sign.ci("1.1.2", self.dist)

    def test_ci_with_the_shipped_key(self):
        """launcher/updater.py ships the owner's public key: a release run without the secret, or with a
        secret that is not that key, stops before anything is published."""
        self.assertTrue(release_sign.updater_keys())
        with mock.patch.dict(os.environ, {release_sign.KEY_ENV: ""}):
            code, msg = release_sign.ci("1.1.2", self.dist)
        self.assertEqual(code, 1)
        self.assertIn(release_sign.KEY_ENV, msg)
        with mock.patch.dict(os.environ, {release_sign.KEY_ENV: self.seed.hex()}):
            with self.assertRaisesRegex(release_sign.Fail, "not in RELEASE_PUBLIC_KEYS"):
                release_sign.ci("1.1.2", self.dist)
        self.assertFalse(os.path.exists(os.path.join(self.dist, "SHA256SUMS.sig")))

    def test_bad_private_keys(self):
        for bad in ("", "xyz", "ab" * 31, "ab" * 33):
            with self.assertRaises(release_sign.Fail):
                release_sign.parse_seed(bad)
        self.assertEqual(release_sign.parse_seed(" " + "AB" * 32 + "\n"), bytes([0xAB]) * 32)

    def test_workflow_signs_in_the_release_environment_only(self):
        with open(os.path.join(ROOT, ".github", "workflows", "release.yml"), encoding="utf-8") as f:
            wf = f.read()
        build, publish = wf.split("\n  publish:", 1)
        self.assertNotIn("T5DR_RELEASE_SIGNING_KEY", build)                        # the build job never has it
        self.assertIn("secrets.T5DR_RELEASE_SIGNING_KEY", publish)
        self.assertIn("release_sign.py ci", publish)
        self.assertIn("name: release", publish)
        self.assertLess(publish.index("release_sign.py ci"), publish.index("gh release create"))


if __name__ == "__main__":
    unittest.main()
