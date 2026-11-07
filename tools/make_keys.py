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
import time
import urllib.error
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
    return fetch(RAW + name)


TRIES = 3          # 1.2.2: a flaky connection or a firewall that lets the second try through
WAIT_S = 2.0


def fetch(url, tries=None, wait=None, opener=None):
    """The text at `url`: up to `tries` attempts (default 3) with a short wait between them; the last error is raised
    (build_game recognises urlopen/URLError and says what to check)."""
    tries = TRIES if tries is None else tries
    wait = WAIT_S if wait is None else wait
    opener = opener or urllib.request.urlopen
    for n in range(1, tries + 1):
        try:
            with opener(url, timeout=60) as r:
                return r.read().decode("utf-8")
        except (urllib.error.URLError, OSError) as e:       # (URLError, timeouts, resets)
            if n == tries:
                raise
            print(f"  could not fetch {url.rsplit('/', 1)[-1]} ({e}); trying again in {wait:g} s ({n}/{tries})",
                  file=sys.stderr)
            time.sleep(wait)


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
