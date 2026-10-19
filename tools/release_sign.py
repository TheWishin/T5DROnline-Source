#!/usr/bin/env python3
r"""The release signature (Ed25519 over SHA256SUMS): keys, signing, checking. Standard library only.

Why and how it fits together: launcher/release_sig.py, docs/RELEASING.md "Release signature".

    python tools/release_sign.py keygen --out FILE
        A new private key (64 hex digits) into FILE, which must be OUTSIDE this repository and must not
        exist yet. Prints the public key. Put the private key into the GitHub secret (RELEASING.md),
        keep one offline copy (password manager), then delete FILE.
    python tools/release_sign.py add-public-key HEX
        Adds a public key to RELEASE_PUBLIC_KEYS in launcher/updater.py (commit that).
    python tools/release_sign.py public-key [--key-env VAR | --key-file FILE]
        The public key of a private key (default: the environment variable T5DR_RELEASE_SIGNING_KEY).
    python tools/release_sign.py sign --version X --sums dist/SHA256SUMS --out dist/SHA256SUMS.sig
        Signs with the private key from T5DR_RELEASE_SIGNING_KEY (or --key-file). Refuses when its public
        key is not in launcher/updater.py: the launcher of this release must be able to check the next one.
    python tools/release_sign.py verify --version X --sums SHA256SUMS --sig SHA256SUMS.sig [--public-key HEX]
        Checks a downloaded release (default keys: launcher/updater.py's). Exit 0 = good.
    python tools/release_sign.py ci --version X --dist DIR
        The release workflow's step (publish job): with the secret, sign DIR/SHA256SUMS into
        DIR/SHA256SUMS.sig; without it, fail when launcher/updater.py has a key (those launchers would
        refuse the release), else say that the release goes out unsigned (as up to 1.1.1).

The private key is never printed, never written inside the repository, and never logged.
"""
import argparse
import ast
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "launcher"))
import release_sig  # noqa: E402

UPDATER = os.path.join(ROOT, "launcher", "updater.py")
KEY_ENV = "T5DR_RELEASE_SIGNING_KEY"
RE_KEYS = re.compile(r"^RELEASE_PUBLIC_KEYS = \((?P<body>[^)]*)\)", re.M)


class Fail(Exception):
    pass


def updater_keys(path=UPDATER):
    """RELEASE_PUBLIC_KEYS of launcher/updater.py, read without importing it."""
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read(), path)
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "RELEASE_PUBLIC_KEYS" for t in node.targets):
            keys = ast.literal_eval(node.value)
            if not isinstance(keys, tuple) or not all(isinstance(k, str) for k in keys):
                raise Fail("RELEASE_PUBLIC_KEYS in launcher/updater.py must be a tuple of strings")
            for k in keys:
                try:
                    release_sig.parse_public_key(k)
                except ValueError as e:
                    raise Fail(f"RELEASE_PUBLIC_KEYS: {k[:12]}...: {e}") from None
            return keys
    raise Fail("launcher/updater.py has no RELEASE_PUBLIC_KEYS")


def parse_seed(text):
    t = re.sub(r"\s+", "", str(text or "")).lower()
    if not re.fullmatch(r"[0-9a-f]{64}", t):
        raise Fail("the private key must be 64 hex digits (tools/release_sign.py keygen makes one)")
    return bytes.fromhex(t)


def load_seed(key_env=KEY_ENV, key_file=None):
    if key_file:
        with open(key_file, encoding="utf-8") as f:
            return parse_seed(f.read())
    v = os.environ.get(key_env, "")
    if not v.strip():
        raise Fail(f"no private key: set {key_env} or use --key-file")
    return parse_seed(v)


def _inside_repo(path):
    p = os.path.normcase(os.path.realpath(os.path.abspath(path)))
    r = os.path.normcase(os.path.realpath(ROOT))
    return p == r or p.startswith(r.rstrip("\\/") + os.sep)


def keygen(out):
    if _inside_repo(out):
        raise Fail(f"{out} is inside the repository: keep the private key out of it (and out of git)")
    seed = os.urandom(32)
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)     # never overwrites a key
    with os.fdopen(fd, "w", encoding="ascii") as f:
        f.write(seed.hex() + "\n")
    pub = release_sig.public_key(seed)
    return pub.hex(), release_sig.key_id(pub)


def add_public_key(hexkey, path=UPDATER):
    raw = release_sig.parse_public_key(hexkey)
    keys = list(updater_keys(path))
    if raw.hex() in keys:
        return False
    keys.append(raw.hex())
    with open(path, encoding="utf-8", newline="") as f:
        text = f.read()
    nl = "\r\n" if "\r\n" in text else "\n"
    body = "".join(f'    "{k}",{nl}' for k in keys)
    new, n = RE_KEYS.subn(lambda m: f"RELEASE_PUBLIC_KEYS = ({nl}{body})", text, count=1)
    if n != 1:
        raise Fail("could not find RELEASE_PUBLIC_KEYS = (...) in launcher/updater.py")
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(new)
    if raw.hex() not in updater_keys(path):
        raise Fail("launcher/updater.py did not take the key")
    return True


def sign(version, sums_path, out, seed, keys=None, check=True):
    with open(sums_path, "rb") as f:
        sums = f.read()
    zip_line = f"T5DR-Online-{version}.zip"
    if not re.search(r"(?m)^[0-9a-fA-F]{64} [ *]" + re.escape(zip_line) + r"\s*$", sums.decode("utf-8", "replace")):
        raise Fail(f"{sums_path} has no line for {zip_line}")
    pub = release_sig.public_key(seed).hex()
    if check:
        keys = updater_keys() if keys is None else keys
        if pub not in keys:
            raise Fail(f"the signing key ({release_sig.key_id(bytes.fromhex(pub))}) is not in RELEASE_PUBLIC_KEYS of "
                       "launcher/updater.py: this release's launcher could not check the next update. Add it "
                       "(tools/release_sign.py add-public-key), or fix the secret")
    text = release_sig.make_sig_file(seed, version, sums)
    release_sig.check_sig_file(text.encode(), version, sums, [pub])           # never ship a bad one
    with open(out, "w", encoding="ascii", newline="\n") as f:
        f.write(text)
    return release_sig.key_id(bytes.fromhex(pub))


def verify(version, sums_path, sig_path, keys):
    with open(sums_path, "rb") as f:
        sums = f.read()
    with open(sig_path, "rb") as f:
        sig = f.read()
    return release_sig.check_sig_file(sig, version, sums, keys)


def ci(version, dist, key_env=KEY_ENV):
    """-> (exit code, message). The release workflow's signing step."""
    keys = updater_keys()
    sums, out = os.path.join(dist, "SHA256SUMS"), os.path.join(dist, release_sig.SIG_ASSET)
    if os.environ.get(key_env, "").strip():
        kid = sign(version, sums, out, load_seed(key_env), keys)
        return 0, f"signed SHA256SUMS of {version} with release key {kid} -> {out}"
    if keys:
        return 1, (f"launcher/updater.py has a release key, but the secret {key_env} is missing in this job: those "
                   "launchers would refuse an unsigned release. Add the secret to the 'release' environment "
                   "(docs/RELEASING.md, Release signature)")
    return 0, "no release signing key set up: this release is not signed (docs/RELEASING.md, Release signature)"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("keygen")
    g.add_argument("--out", required=True)
    a = sub.add_parser("add-public-key")
    a.add_argument("key")
    p = sub.add_parser("public-key")
    for q in (p,):
        q.add_argument("--key-env", default=KEY_ENV)
        q.add_argument("--key-file")
    s = sub.add_parser("sign")
    s.add_argument("--version", required=True)
    s.add_argument("--sums", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--key-env", default=KEY_ENV)
    s.add_argument("--key-file")
    s.add_argument("--no-key-check", action="store_true", help="tests only: sign with a key the launcher does not have")
    v = sub.add_parser("verify")
    v.add_argument("--version", required=True)
    v.add_argument("--sums", required=True)
    v.add_argument("--sig", required=True)
    v.add_argument("--public-key", action="append", help="default: RELEASE_PUBLIC_KEYS of launcher/updater.py")
    c = sub.add_parser("ci")
    c.add_argument("--version", required=True)
    c.add_argument("--dist", required=True)
    args = ap.parse_args(argv)
    try:
        if args.cmd == "keygen":
            pub, kid = keygen(args.out)
            print(f"private key written to {args.out} (64 hex digits; never commit it, never paste it anywhere "
                  "but the GitHub secret and your password manager)")
            print(f"public key: {pub}")
            print(f"key id:     {kid}")
            print(f"next: python tools/release_sign.py add-public-key {pub}")
        elif args.cmd == "add-public-key":
            changed = add_public_key(args.key)
            print("added to launcher/updater.py" if changed else "already in launcher/updater.py")
        elif args.cmd == "public-key":
            pub = release_sig.public_key(load_seed(args.key_env, args.key_file))
            print(f"{pub.hex()}  (key id {release_sig.key_id(pub)})")
        elif args.cmd == "sign":
            kid = sign(args.version, args.sums, args.out, load_seed(args.key_env, args.key_file),
                       check=not args.no_key_check)
            print(f"signed with key {kid}: {args.out}")
        elif args.cmd == "verify":
            kid = verify(args.version, args.sums, args.sig, args.public_key or updater_keys())
            print(f"good signature by key {kid}")
        elif args.cmd == "ci":
            code, msg = ci(args.version, args.dist)
            print(("::error::" if code else "") + msg)
            return code
    except (Fail, release_sig.SignatureError, ValueError, OSError) as e:
        print(f"::error::{e}" if os.environ.get("GITHUB_ACTIONS") else f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
