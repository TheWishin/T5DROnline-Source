#!/usr/bin/env python3
"""Decrypt a PS3 NPDRM SELF (EBOOT.BIN) to a plain ELF with the player's own .rap.

    python tools/unself.py <EBOOT.BIN> <license.rap> <out.elf> [--keys keys/ps3.keys]

Contains no keys. They are read from a local keys file (git-ignored) holding
NAME=HEX lines: NP_KLIC_KEY, RAP_KEY, RAP_PBOX, RAP_E1, RAP_E2 and
NPDRM_<rev>_ERK / NPDRM_<rev>_RIV per key revision.

Written from the public SELF format description; RPCS3's unself.cpp was used
as a reference for the layout only.
"""
import argparse
import hashlib
import struct
import sys
import zlib

from Crypto.Cipher import AES
from Crypto.Util import Counter


def load_keys(path):
    keys = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                name, val = line.split("=", 1)
                keys[name.strip()] = bytes.fromhex(val.strip())
    return keys


def rap_to_rif_key(rap, k):
    key = bytearray(AES.new(k["RAP_KEY"], AES.MODE_CBC, bytes(16)).decrypt(rap))
    pbox, e1, e2 = k["RAP_PBOX"], k["RAP_E1"], k["RAP_E2"]
    for _ in range(5):
        for i in range(16):
            p = pbox[i]
            key[p] ^= e1[p]
        for i in range(15, 0, -1):
            key[pbox[i]] ^= key[pbox[i - 1]]
        o = 0
        for i in range(16):
            p = pbox[i]
            kc = (key[p] - o) & 0xFF
            ec2 = e2[p]
            if o != 1 or kc != 0xFF:
                o = 1 if kc < ec2 else 0
                key[p] = (kc - ec2) & 0xFF
            else:
                key[p] = (kc - ec2) & 0xFF
    return bytes(key)


def ctr(key, iv, data):
    c = Counter.new(128, initial_value=int.from_bytes(iv, "big"))
    return AES.new(key, AES.MODE_CTR, counter=c).decrypt(data)


def u64(b, o):
    return struct.unpack_from(">Q", b, o)[0]


def u32(b, o):
    return struct.unpack_from(">I", b, o)[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("self_path")
    ap.add_argument("rap_path")
    ap.add_argument("out_path")
    ap.add_argument("--keys", default="keys/ps3.keys")
    a = ap.parse_args()

    k = load_keys(a.keys)
    s = open(a.self_path, "rb").read()
    rap = open(a.rap_path, "rb").read()
    if s[:4] != b"SCE\0":
        sys.exit("not a SELF")

    # SCE header
    se_flags = struct.unpack_from(">H", s, 8)[0]       # key revision
    se_meta = u32(s, 0x0C)
    se_hsize = u64(s, 0x10)
    # Extended header
    prog_id_off, ehdr_off, phdr_off, shdr_off, seg_off, ver_off, sup_off, sup_size = (
        u64(s, 0x28 + 8 * i) for i in range(8))
    prog_type = u32(s, prog_id_off + 0x0C)
    print(f"key revision 0x{se_flags:04X}, program type {prog_type}, header 0x{se_hsize:X}")
    if prog_type != 8:
        sys.exit(f"program type {prog_type} is not NPDRM (8)")

    # Supplemental headers -> NPD header
    npd = None
    off, end = sup_off, sup_off + sup_size
    while off < end:
        typ, size, nxt = struct.unpack_from(">IIQ", s, off)
        if typ == 3:
            npd = s[off + 0x10: off + 0x10 + 0x80]
        off += size
        if not nxt:
            break
    if npd is None or npd[:4] != b"NPD\0":
        sys.exit("no NPDRM header")
    license_type = u32(npd, 8)
    content_id = npd[0x10:0x40].rstrip(b"\0").decode()
    print(f"content id {content_id}, license type {license_type}")

    # Metadata info: NPDRM layer (AES-128-CBC, key from the .rap), then AES-256-CBC
    klic = rap_to_rif_key(rap, k)
    npdrm_key = AES.new(k["NP_KLIC_KEY"], AES.MODE_ECB).decrypt(klic)
    mi_off = se_meta + 0x20
    mi = s[mi_off: mi_off + 0x40]
    if not se_flags & 0x8000:
        mi = AES.new(npdrm_key, AES.MODE_CBC, bytes(16)).decrypt(mi)
        rev = f"NPDRM_{se_flags:04X}"
        mi = AES.new(k[rev + "_ERK"], AES.MODE_CBC, k[rev + "_RIV"]).decrypt(mi)
    if any(mi[0x10:0x20]) or any(mi[0x30:0x40]):
        sys.exit("metadata did not decrypt (wrong .rap for this package?)")
    meta_key, meta_iv = mi[0:0x10], mi[0x20:0x30]

    # Metadata header + section headers + data keys (AES-128-CTR)
    mh = ctr(meta_key, meta_iv, s[mi_off + 0x40: se_hsize])
    section_count, key_count = u32(mh, 0x0C), u32(mh, 0x10)
    secs = [struct.unpack_from(">QQIIIIIIII", mh, 0x20 + i * 0x30) for i in range(section_count)]
    dk_off = 0x20 + section_count * 0x30
    data_keys = [mh[dk_off + i * 0x10: dk_off + (i + 1) * 0x10] for i in range(key_count)]

    # ELF header + program headers (plaintext in the SELF)
    ehdr = s[ehdr_off: ehdr_off + 0x40]
    if ehdr[:4] != b"\x7fELF" or ehdr[4] != 2:
        sys.exit("expected a 64-bit ELF inside")
    e_phnum, e_shoff = struct.unpack_from(">H", ehdr, 0x38)[0], u64(ehdr, 0x28)
    e_shentsize, e_shnum = struct.unpack_from(">HH", ehdr, 0x3A)
    phdrs = [s[phdr_off + i * 0x38: phdr_off + (i + 1) * 0x38] for i in range(e_phnum)]

    size = max([0x40 + e_phnum * 0x38] +
               [u64(p, 8) + u64(p, 0x20) for p in phdrs] +
               [e_shoff + e_shentsize * e_shnum if shdr_off else 0])
    out = bytearray(size)
    out[0:0x40] = ehdr
    for i, p in enumerate(phdrs):
        out[0x40 + i * 0x38: 0x40 + (i + 1) * 0x38] = p

    for (data_off, data_size, typ, prog_idx, _hashed, _sha, enc, key_idx, iv_idx, comp) in secs:
        if typ != 2:
            continue
        data = s[data_off: data_off + data_size]
        if enc == 3:
            data = ctr(data_keys[key_idx], data_keys[iv_idx], data)
        p = phdrs[prog_idx]
        p_offset, p_filesz = u64(p, 8), u64(p, 0x20)
        if comp == 2:
            data = zlib.decompress(data)
            if len(data) != p_filesz:
                print(f"  warning: segment {prog_idx} inflated to {len(data)}, expected {p_filesz}")
        out[p_offset: p_offset + len(data)] = data

    if shdr_off:
        out[e_shoff: e_shoff + e_shentsize * e_shnum] = s[shdr_off: shdr_off + e_shentsize * e_shnum]

    open(a.out_path, "wb").write(out)
    print(f"wrote {a.out_path}: {len(out)} bytes, sha1 {hashlib.sha1(out).hexdigest()}")


if __name__ == "__main__":
    main()
