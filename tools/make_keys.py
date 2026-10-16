#!/usr/bin/env python3
"""Write keys/ps3.keys (git-ignored) for tools/unself.py.

    python tools/make_keys.py [--source DIR]

The keys are not in this repository. This reads them out of RPCS3's public
crypto source (rpcs3/Crypto/key_vault.h and key_vault.cpp) -- fetched from
GitHub, or from a local copy with --source. Nothing of RPCS3 is run or
installed; only these two text files are read.
"""
import argparse
import os
import re
import sys
import urllib.request

RAW = "https://raw.githubusercontent.com/RPCS3/rpcs3/master/rpcs3/Crypto/"
# PKG_AES_KEY / PKG_AES_KEY2: the package (outer layer) keys. A release zip
# carries a copy of ps3recomp's pkg_extract.py with them taken out; it reads
# them from this file instead (T5DR_KEYS, set by build_game.py).
NAMED = ["NP_KLIC_KEY", "RAP_KEY", "RAP_PBOX", "RAP_E1", "RAP_E2", "PKG_AES_KEY", "PKG_AES_KEY2"]


def read(source, name):
    if source:
        with open(os.path.join(source, name), encoding="utf-8") as f:
            return f.read()
    with urllib.request.urlopen(RAW + name, timeout=60) as r:
        return r.read().decode("utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", help="folder holding key_vault.h and key_vault.cpp")
    ap.add_argument("--out", default="keys/ps3.keys")
    a = ap.parse_args()

    h = read(a.source, "key_vault.h")
    c = read(a.source, "key_vault.cpp")

    lines = []
    for n in NAMED:
        m = re.search(r"constexpr u8 %s\[0x10\] = \{([^}]*)\}" % n, h)
        if not m:
            sys.exit(f"{n} not found in key_vault.h")
        lines.append("%s=%s" % (n, "".join(re.findall(r"0x([0-9A-Fa-f]{2})", m.group(1))).upper()))

    body = c[c.index("void KeyVault::LoadSelfNPDRMKeys"):]
    body = body[:body.index("\n}\n")]
    for rev, erk, riv in re.findall(
            r'0x[0-9A-F]+, 0x[0-9A-F]+, (0x[0-9A-F]+), KEY_NPDRM,\s*"([0-9A-F]+)",\s*"([0-9A-F]+)"', body):
        lines.append("NPDRM_%04X_ERK=%s" % (int(rev, 16), erk))
        lines.append("NPDRM_%04X_RIV=%s" % (int(rev, 16), riv))

    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.out, "w") as f:
        f.write("# Local only. Never commit.\n" + "\n".join(lines) + "\n")
    print(f"wrote {a.out} ({len(lines)} entries)")


if __name__ == "__main__":
    main()
