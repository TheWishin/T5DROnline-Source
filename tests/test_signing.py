"""Code signing support of the release tooling (tools/code_signing.py, package_release.py
--sign-stage / --stub-compiler). No signing service, no certificate and no toolchain needed: the
programs are small fake PE files and Windows' verdict is replaced by a stand-in."""
import os
import tempfile
import unittest
from unittest import mock

from helpers import load_tool, put

signing = load_tool("code_signing")
package = load_tool("package_release")


def make_pe(body=b"program"):
    """A minimal PE32+ file: DOS header, PE header, optional header, 16 data directories."""
    data = bytearray(0x400)
    data[0:2] = b"MZ"
    pe = 0x80
    data[0x3C:0x40] = pe.to_bytes(4, "little")
    data[pe:pe + 4] = b"PE\0\0"
    data[pe + 20:pe + 22] = (240).to_bytes(2, "little")      # SizeOfOptionalHeader
    data[pe + 24:pe + 26] = (0x20B).to_bytes(2, "little")    # PE32+
    data[0x200:0x200 + len(body)] = body
    return bytes(data)


def sign_like_a_service(data, cert=b"CERTIFICATE" * 8):
    """What Authenticode signing changes: pad to 8, append the certificate table, point the security
    directory at it, set a new checksum."""
    b = bytearray(data) + bytes((-len(data)) % 8)
    pos = len(b)
    cert = cert + bytes((-len(cert)) % 8)
    b += cert
    opt = 0x80 + 24
    b[opt + 64:opt + 68] = (0xCAFE).to_bytes(4, "little")                       # CheckSum
    sec = opt + 112 + 4 * 8
    b[sec:sec + 8] = pos.to_bytes(4, "little") + len(cert).to_bytes(4, "little")
    return bytes(b)


class Helpers(unittest.TestCase):
    def test_signed_copy_is_the_same_program(self):
        built = make_pe()
        signed = sign_like_a_service(built)
        self.assertEqual(signing.certificate_table(built), (0, 0))
        pos, size = signing.certificate_table(signed)
        self.assertEqual(pos + size, len(signed))
        self.assertTrue(signing.same_program(built, signed))

    def test_a_changed_program_is_not(self):
        built = make_pe()
        self.assertFalse(signing.same_program(built, sign_like_a_service(make_pe(b"other program"))))
        tampered = bytearray(sign_like_a_service(built))
        tampered[0x200] ^= 1
        self.assertFalse(signing.same_program(built, bytes(tampered)))

    def test_not_a_pe_file(self):
        with self.assertRaises(ValueError):
            signing.certificate_table(b"this is not a program" * 20)

    def test_certificate_table_outside_the_file(self):
        signed = bytearray(sign_like_a_service(make_pe()))
        sec = 0x80 + 24 + 112 + 32
        signed[sec + 4:sec + 8] = (10 ** 6).to_bytes(4, "little")
        with self.assertRaises(ValueError):
            signing.strip_signature(bytes(signed))

    def test_what_we_sign(self):
        with tempfile.TemporaryDirectory() as d:
            for rel in ("T5DR Online.exe", "runtime/t5dr.exe", "runtime/t5dr.lib", "runtime/extra.dll",
                        "python/python.exe", "python/DLLs/_ssl.pyd", "python/vcruntime140.dll",
                        "toolchain/llvm/bin/clang-cl.exe", "launcher/t5dr_launcher.pyw", "tools/x.exe"):
                os.makedirs(os.path.dirname(os.path.join(d, rel)), exist_ok=True)
                put(os.path.join(d, rel), b"x")
            self.assertEqual(signing.signable_files(d),
                             ["T5DR Online.exe", "runtime/extra.dll", "runtime/t5dr.exe", "tools/x.exe"])


class SignStages(unittest.TestCase):
    """package_release.export_to_sign / install_signed around a fake signing service."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.stage = os.path.join(self.tmp.name, "stage")
        self.signed = os.path.join(self.tmp.name, "signed")
        for rel, body in (("T5DR Online.exe", b"starter"), ("runtime/t5dr.exe", b"runtime")):
            os.makedirs(os.path.dirname(os.path.join(self.stage, rel)), exist_ok=True)
            put(os.path.join(self.stage, rel), make_pe(body))
        self.quiet = mock.patch.object(package, "log", lambda *a, **k: None)
        self.quiet.start()
        self.addCleanup(self.quiet.stop)

    def sign_all(self, status=("Valid", "CN=Test Publisher")):
        for rel in signing.signable_files(self.stage):
            src = os.path.join(self.stage, *rel.split("/"))
            dst = os.path.join(self.signed, *rel.split("/"))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(src, "rb") as f:
                put(dst, sign_like_a_service(f.read()))
        return mock.patch.object(package.code_signing, "authenticode_status", lambda p: status)

    def test_export_keeps_relative_paths(self):
        dest = os.path.join(self.tmp.name, "to-sign")
        self.assertEqual(package.export_to_sign(self.stage, dest), ["T5DR Online.exe", "runtime/t5dr.exe"])
        self.assertTrue(os.path.isfile(os.path.join(dest, "runtime", "t5dr.exe")))

    def test_install_replaces_the_built_files(self):
        with self.sign_all():
            self.assertEqual(package.install_signed(self.stage, self.signed),
                             ["T5DR Online.exe", "runtime/t5dr.exe"])
        for rel in ("T5DR Online.exe", "runtime/t5dr.exe"):
            with open(os.path.join(self.stage, *rel.split("/")), "rb") as f:
                self.assertGreater(signing.certificate_table(f.read())[1], 0)

    def test_missing_signed_copy_stops(self):
        with self.sign_all():
            os.remove(os.path.join(self.signed, "runtime", "t5dr.exe"))
            with self.assertRaises(SystemExit) as e:
                package.install_signed(self.stage, self.signed)
        self.assertIn("runtime/t5dr.exe", str(e.exception))

    def test_unsigned_file_returned_stops(self):
        with self.sign_all():
            with open(os.path.join(self.stage, "T5DR Online.exe"), "rb") as f:
                put(os.path.join(self.signed, "T5DR Online.exe"), f.read())
            with self.assertRaises(SystemExit) as e:
                package.install_signed(self.stage, self.signed)
        self.assertIn("no signature", str(e.exception))

    def test_different_program_returned_stops(self):
        with self.sign_all():
            put(os.path.join(self.signed, "T5DR Online.exe"), sign_like_a_service(make_pe(b"somebody else")))
            with self.assertRaises(SystemExit) as e:
                package.install_signed(self.stage, self.signed)
        self.assertIn("not the file built", str(e.exception))

    def test_signature_windows_does_not_trust_stops(self):
        with self.sign_all(status=("UnknownError", "CN=Self")):
            with self.assertRaises(SystemExit) as e:
                package.install_signed(self.stage, self.signed)
            self.assertIn("UnknownError", str(e.exception))
            # ... unless this is a test with a self-signed certificate
            self.assertEqual(len(package.install_signed(self.stage, self.signed, accept_untrusted=True)), 2)

    def test_hash_mismatch_is_never_accepted(self):
        with self.sign_all(status=("HashMismatch", "CN=Self")):
            with self.assertRaises(SystemExit):
                package.install_signed(self.stage, self.signed, accept_untrusted=True)


class StubCompiler(unittest.TestCase):
    def test_default_is_msvc(self):
        with mock.patch.dict(os.environ, {"T5DR_STUB_COMPILER": ""}):
            self.assertEqual(package.default_stub_compiler(), "msvc")

    def test_environment_picks_the_compiler(self):
        for value, want in (("clang", "clang"), (" CLANG ", "clang"), ("msvc", "msvc"), ("gcc", "msvc")):
            with mock.patch.dict(os.environ, {"T5DR_STUB_COMPILER": value}):
                self.assertEqual(package.default_stub_compiler(), want, value)


if __name__ == "__main__":
    unittest.main()
