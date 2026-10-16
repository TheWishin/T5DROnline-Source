"""tools/unself.py without any game data: the .rap -> RIF key derivation
against a reference implementation and a fixed vector, and a full decrypt of a
synthetic NPDRM SELF built here with fake keys."""
import os
import struct
import subprocess
import tempfile
import unittest
import zlib

from helpers import PY, TOOLS, fake_bytes, fake_keys, get, load_tool, put, write_keys

try:
    from Crypto.Cipher import AES
    from Crypto.Util import Counter
except ImportError:                     # pragma: no cover
    if os.environ.get("CI"):
        raise                           # CI installs pycryptodome; a skip there would hide a break
    AES = None


def ref_rap_to_rif(rap, k):
    """Straight transliteration of the C reference (rap2rifkey with unsigned
    char arithmetic), written independently of tools/unself.py. The first
    step is one AES-128 block with a zero IV, i.e. plain ECB."""
    key = list(AES.new(k["RAP_KEY"], AES.MODE_ECB).decrypt(rap))
    pbox, e1, e2 = k["RAP_PBOX"], k["RAP_E1"], k["RAP_E2"]
    for _round in range(5):
        for i in range(16):
            key[pbox[i]] ^= e1[pbox[i]]
        for i in range(15, 0, -1):
            key[pbox[i]] ^= key[pbox[i - 1]]
        o = 0
        for i in range(16):
            p = pbox[i]
            kc = (key[p] - o) % 256
            ec2 = e2[p]
            if o != 1 or kc != 0xFF:
                o = 1 if kc < ec2 else 0
            key[p] = (kc - ec2) % 256
    return bytes(key)


# rap_to_rif_key(fake_bytes("rap input"), fake_keys()) as computed when this
# test was written; any change to the derivation changes it.
GOLDEN_RIF = "5a27a699dc97f15ae6c7bc95de306616"


@unittest.skipIf(AES is None, "pycryptodome not installed (pip install pycryptodome)")
class RapToRif(unittest.TestCase):
    def setUp(self):
        self.unself = load_tool("unself")
        self.k = fake_keys()

    def test_matches_reference(self):
        for i in range(64):
            rap = fake_bytes(f"rap {i}")
            self.assertEqual(self.unself.rap_to_rif_key(rap, self.k), ref_rap_to_rif(rap, self.k), f"rap #{i}")

    def test_borrow_edge(self):
        # Inputs that make the subtraction chain borrow through 0xFF bytes:
        # all-zero and all-0xFF raps, plus E2 = 0xFF everywhere.
        k = dict(self.k, RAP_E2=bytes([0xFF] * 16))
        for rap in (bytes(16), bytes([0xFF] * 16)):
            for keys in (self.k, k):
                self.assertEqual(self.unself.rap_to_rif_key(rap, keys), ref_rap_to_rif(rap, keys))

    def test_golden_vector(self):
        got = self.unself.rap_to_rif_key(fake_bytes("rap input"), self.k).hex()
        self.assertEqual(got, GOLDEN_RIF)

    def test_load_keys_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "ps3.keys")
            write_keys(path, self.k)
            self.assertEqual(self.unself.load_keys(path), self.k)


def ctr(key, iv, data):
    return AES.new(key, AES.MODE_CTR, counter=Counter.new(128, initial_value=int.from_bytes(iv, "big"))).encrypt(data)


def make_elf():
    """A small big-endian ELF64 the way unself writes one back: header at 0,
    program headers at 0x40, two PT_LOAD segments, section headers at the end."""
    seg0 = (b"compressible segment " * 64)[:0x500]
    seg1 = fake_bytes("segment 1", 0x123)
    off0, off1 = 0x100, 0x700
    shoff, shentsize, shnum = 0x900, 0x40, 2
    size = shoff + shentsize * shnum
    elf = bytearray(size)
    ehdr = bytearray(0x40)
    ehdr[0:6] = b"\x7fELF\x02\x02"
    struct.pack_into(">Q", ehdr, 0x20, 0x40)            # e_phoff
    struct.pack_into(">Q", ehdr, 0x28, shoff)           # e_shoff
    struct.pack_into(">HHHHH", ehdr, 0x36, 0x38, 2, shentsize, shnum, 0)
    elf[0:0x40] = ehdr
    phdrs = []
    for i, (off, data, va) in enumerate([(off0, seg0, 0x10000), (off1, seg1, 0x20000)]):
        p = struct.pack(">IIQQQQQQ", 1, 5, off, va, va, len(data), len(data), 0x10)
        elf[0x40 + i * 0x38: 0x40 + (i + 1) * 0x38] = p
        elf[off:off + len(data)] = data
        phdrs.append(p)
    shdrs = fake_bytes("section headers", shentsize * shnum)
    elf[shoff:] = shdrs
    return bytes(elf), bytes(ehdr), phdrs, [seg0, seg1], shdrs


def make_self(elf_parts, k, rif_key, revision=1):
    """Wrap the ELF into an NPDRM SELF, encrypting with the fake keys exactly
    the way unself.py decrypts: metadata info under the klicensee layer and
    the revision's ERK/RIV, metadata header + data keys under AES-CTR, segment
    0 zlib-compressed, both segments AES-CTR encrypted."""
    _elf, ehdr, phdrs, segs, shdrs = elf_parts
    meta_key, meta_iv = fake_bytes("meta key"), fake_bytes("meta iv")
    data_keys = [fake_bytes(f"data key {i}") for i in range(4)]
    payloads = [zlib.compress(segs[0]), segs[1]]
    comps = [2, 1]

    # Fixed layout
    prog_id_off, ehdr_off, phdr_off = 0x70, 0x90, 0xD0
    sup_off = phdr_off + 0x38 * len(phdrs)
    sup = struct.pack(">IIQ", 3, 0x90, 0) + b"NPD\0" + struct.pack(">II", 3, 2) + bytes(4) \
        + b"UP0000-TEST00000_00-0000000000000000".ljust(0x30, b"\0") + bytes(0x80 - 0x40)
    se_meta = sup_off + len(sup) + 0x10                   # metadata info at se_meta + 0x20
    mi_off = se_meta + 0x20
    nsec = len(payloads)
    mh_len = 0x20 + nsec * 0x30 + len(data_keys) * 0x10
    se_hsize = mi_off + 0x40 + mh_len
    shdr_off = se_hsize
    data_off = shdr_off + len(shdrs)

    secs, blobs, off = b"", b"", data_off
    for i, data in enumerate(payloads):
        enc = ctr(data_keys[2 * i], data_keys[2 * i + 1], data)
        secs += struct.pack(">QQIIIIIIII", off, len(enc), 2, i, 2, 0, 3, 2 * i, 2 * i + 1, comps[i])
        blobs += enc
        off += len(enc)
    mh = bytearray(0x20)
    struct.pack_into(">II", mh, 0x0C, nsec, len(data_keys))
    mh = bytes(mh) + secs + b"".join(data_keys)

    mi = meta_key + bytes(16) + meta_iv + bytes(16)
    rev = f"NPDRM_{revision:04X}"
    mi = AES.new(k[rev + "_ERK"], AES.MODE_CBC, k[rev + "_RIV"]).encrypt(mi)
    npdrm_key = AES.new(k["NP_KLIC_KEY"], AES.MODE_ECB).decrypt(rif_key)
    mi = AES.new(npdrm_key, AES.MODE_CBC, bytes(16)).encrypt(mi)

    s = bytearray(data_off)
    s[0:4] = b"SCE\0"
    struct.pack_into(">IHHIQQ", s, 4, 2, revision, 1, se_meta, se_hsize, 0)
    struct.pack_into(">8Q", s, 0x28, prog_id_off, ehdr_off, phdr_off, shdr_off, 0, 0, sup_off, len(sup))
    # program identification: auth id, vendor id, self type (8 = NPDRM application), version
    struct.pack_into(">QIIQ", s, prog_id_off, 0x1010000001000003, 0x01000002, 8, 0x0001000000000000)
    s[ehdr_off:ehdr_off + 0x40] = ehdr
    for i, p in enumerate(phdrs):
        s[phdr_off + i * 0x38: phdr_off + (i + 1) * 0x38] = p
    s[sup_off:sup_off + len(sup)] = sup
    s[mi_off:mi_off + 0x40] = mi
    s[mi_off + 0x40:se_hsize] = ctr(meta_key, meta_iv, mh)
    s[shdr_off:shdr_off + len(shdrs)] = shdrs
    return bytes(s) + blobs


@unittest.skipIf(AES is None, "pycryptodome not installed (pip install pycryptodome)")
class DecryptSyntheticSelf(unittest.TestCase):
    def test_roundtrip(self):
        unself = load_tool("unself")
        k = fake_keys()
        rap = fake_bytes("license")
        parts = make_elf()
        blob = make_self(parts, k, unself.rap_to_rif_key(rap, k))
        with tempfile.TemporaryDirectory() as d:
            paths = {n: os.path.join(d, n) for n in ("EBOOT.BIN", "test.rap", "out.elf", "ps3.keys")}
            put(paths["EBOOT.BIN"], blob)
            put(paths["test.rap"], rap)
            write_keys(paths["ps3.keys"], k)
            r = subprocess.run([PY, os.path.join(TOOLS, "unself.py"), paths["EBOOT.BIN"], paths["test.rap"],
                                paths["out.elf"], "--keys", paths["ps3.keys"]], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertIn("UP0000-TEST00000_00-0000000000000000", r.stdout)
            self.assertEqual(get(paths["out.elf"]), parts[0])

            # The wrong license must be refused, not turned into garbage.
            put(paths["test.rap"], fake_bytes("someone else's license"))
            r = subprocess.run([PY, os.path.join(TOOLS, "unself.py"), paths["EBOOT.BIN"], paths["test.rap"],
                                paths["out.elf"] + "2", "--keys", paths["ps3.keys"]], capture_output=True, text=True)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("did not decrypt", r.stderr)

    def test_rejects_non_self(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x.bin")
            put(p, b"\x7fELF" + bytes(60))
            kp = os.path.join(d, "ps3.keys")
            write_keys(kp, fake_keys())
            r = subprocess.run([PY, os.path.join(TOOLS, "unself.py"), p, p, p + ".out", "--keys", kp],
                               capture_output=True, text=True)
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("not a SELF", r.stderr)


if __name__ == "__main__":
    unittest.main()
