"""Release signatures: Ed25519 (RFC 8032) over a release's SHA256SUMS, standard library only.

Why: SHA256SUMS and the zip come from the same GitHub release, so the checksum only proves that the
download is what that release holds -- not who made the release. A stolen PUBLIC_RELEASE_TOKEN (it may
write the public repository's releases), a hijacked GitHub login or a tampered release workflow could
publish a zip and a matching SHA256SUMS, and every launcher would offer it. The private key of the
release signature never reaches the build job or the public repository: it is a secret of the Dev
repository's `release` environment (docs/RELEASING.md "Release signature"). The public key ships in
launcher/updater.py (RELEASE_PUBLIC_KEYS); a launcher that has one refuses an update without a valid
signature by it.

What is signed (the "statement", UTF-8, one item per line):

    T5DR-Online-release-signature-v1
    version=<the release version, e.g. 1.1.2>
    sums-sha256=<SHA-256 of the SHA256SUMS file, lower-case hex>

SHA256SUMS names T5DR-Online-<version>.zip with its SHA-256, so the signature covers the zip, and the
version line binds it to that version: an old, genuinely signed release cannot be passed off as a
newer one. The signature file (release asset `SHA256SUMS.sig`) is JSON:

    {"format": "t5dr-release-sig/1", "version": "1.1.2", "key": "<key id>", "signature": "<128 hex>"}

key id = the first 16 hex digits of SHA-256(public key). Ed25519 here is the pure-Python reference
arithmetic of RFC 8032 (section 6) in extended coordinates: a verification takes a few milliseconds.
Signing (tools/release_sign.py, the release workflow) uses the same code; it is not constant-time,
which does not matter on a one-off CI runner, but do not use it as a general-purpose signer.
"""
import hashlib
import json
import re

FORMAT = "t5dr-release-sig/1"
STATEMENT_HEAD = "T5DR-Online-release-signature-v1"
SIG_ASSET = "SHA256SUMS.sig"
MAX_SIG_FILE = 4096

# ---------------------------------------------------------------------------- Ed25519 (RFC 8032)

_P = 2 ** 255 - 19
_L = 2 ** 252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _P - 2, _P) % _P
_SQRT_M1 = pow(2, (_P - 1) // 4, _P)


def _sha512_int(*parts):
    h = hashlib.sha512()
    for p in parts:
        h.update(p)
    return int.from_bytes(h.digest(), "little")


def _add(P, Q):
    x1, y1, z1, t1 = P
    x2, y2, z2, t2 = Q
    a = (y1 - x1) * (y2 - x2) % _P
    b = (y1 + x1) * (y2 + x2) % _P
    c = 2 * t1 * t2 * _D % _P
    d = 2 * z1 * z2 % _P
    e, f, g, h = b - a, d - c, d + c, b + a
    return (e * f % _P, g * h % _P, f * g % _P, e * h % _P)


def _mul(s, P):
    Q = (0, 1, 1, 0)                      # the neutral element
    while s > 0:
        if s & 1:
            Q = _add(Q, P)
        P = _add(P, P)
        s >>= 1
    return Q


def _equal(P, Q):
    x1, y1, z1, _ = P
    x2, y2, z2, _ = Q
    return (x1 * z2 - x2 * z1) % _P == 0 and (y1 * z2 - y2 * z1) % _P == 0


def _recover_x(y, sign):
    if y >= _P:
        return None
    x2 = (y * y - 1) * pow(_D * y * y + 1, _P - 2, _P) % _P
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P != 0:
        x = x * _SQRT_M1 % _P
    if (x * x - x2) % _P != 0:
        return None
    if (x & 1) != sign:
        x = _P - x
    return x


_GY = 4 * pow(5, _P - 2, _P) % _P
_GX = _recover_x(_GY, 0)
_G = (_GX, _GY, 1, _GX * _GY % _P)


def _compress(P):
    x, y, z, _ = P
    zinv = pow(z, _P - 2, _P)
    x, y = x * zinv % _P, y * zinv % _P
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def _decompress(s):
    if len(s) != 32:
        return None
    y = int.from_bytes(s, "little")
    sign = y >> 255
    y &= (1 << 255) - 1
    x = _recover_x(y, sign)
    if x is None:
        return None
    return (x, y, 1, x * y % _P)


def _secret_expand(seed):
    if len(seed) != 32:
        raise ValueError("an Ed25519 private key (seed) is 32 bytes")
    h = hashlib.sha512(seed).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def public_key(seed):
    """32-byte public key of a 32-byte private key (seed)."""
    a, _ = _secret_expand(seed)
    return _compress(_mul(a, _G))


def sign(seed, msg):
    """64-byte Ed25519 signature of msg (bytes)."""
    a, prefix = _secret_expand(seed)
    A = _compress(_mul(a, _G))
    r = _sha512_int(prefix, msg) % _L
    R = _compress(_mul(r, _G))
    k = _sha512_int(R, A, msg) % _L
    s = (r + k * a) % _L
    return R + int.to_bytes(s, 32, "little")


def verify(public, msg, signature):
    """True when signature (64 bytes) is a valid Ed25519 signature of msg by public (32 bytes).
    Refuses a non-canonical S (S >= L) and public keys / R that are not points."""
    if len(public) != 32 or len(signature) != 64:
        return False
    A = _decompress(public)
    if A is None:
        return False
    Rs = signature[:32]
    R = _decompress(Rs)
    if R is None:
        return False
    s = int.from_bytes(signature[32:], "little")
    if s >= _L:
        return False
    k = _sha512_int(Rs, public, msg) % _L
    return _equal(_mul(s, _G), _add(R, _mul(k, A)))


# ---------------------------------------------------------------------------- release statements

RE_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def key_id(public):
    return hashlib.sha256(public).hexdigest()[:16]


def parse_public_key(text):
    """64 hex digits -> 32 bytes. Raises ValueError (also for a key that is not a curve point)."""
    t = str(text).strip().lower()
    if not RE_HEX64.match(t):
        raise ValueError("a release public key is 64 hex digits")
    raw = bytes.fromhex(t)
    if _decompress(raw) is None:
        raise ValueError("not an Ed25519 public key")
    return raw


def statement(version, sums_bytes):
    """The bytes a release signature signs."""
    return (f"{STATEMENT_HEAD}\nversion={version}\n"
            f"sums-sha256={hashlib.sha256(sums_bytes).hexdigest()}\n").encode("utf-8")


def make_sig_file(seed, version, sums_bytes):
    """The text of SHA256SUMS.sig for this release."""
    pub = public_key(seed)
    sig = sign(seed, statement(version, sums_bytes))
    return json.dumps({"format": FORMAT, "version": version, "key": key_id(pub), "signature": sig.hex()},
                      indent=1) + "\n"


class SignatureError(ValueError):
    """The signature file is missing, malformed, by an unknown key, for another version, or wrong."""


def check_sig_file(sig_bytes, version, sums_bytes, public_keys):
    """Verify SHA256SUMS.sig against SHA256SUMS for `version` with one of public_keys (hex strings or
    32-byte keys). Returns the key id that signed. Raises SignatureError with a plain sentence."""
    keys = {}
    for k in public_keys:
        raw = k if isinstance(k, bytes) else parse_public_key(k)
        keys[key_id(raw)] = raw
    if not keys:
        raise SignatureError("no release public key to check the signature with")
    if not sig_bytes or len(sig_bytes) > MAX_SIG_FILE:
        raise SignatureError("the release has no usable signature file")
    try:
        doc = json.loads(sig_bytes.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise SignatureError("the signature file is not readable") from None
    if not isinstance(doc, dict) or doc.get("format") != FORMAT:
        raise SignatureError("the signature file has an unknown format")
    if doc.get("version") != version:
        raise SignatureError(f"the signature is for version {doc.get('version')!r}, not {version}")
    kid = doc.get("key")
    if kid not in keys:
        raise SignatureError("the release is signed by a key this launcher does not know")
    sig = str(doc.get("signature") or "")
    if not re.fullmatch(r"[0-9a-f]{128}", sig):
        raise SignatureError("the signature file holds no signature")
    if not verify(keys[kid], statement(version, sums_bytes), bytes.fromhex(sig)):
        raise SignatureError("the signature does not match this release's SHA256SUMS")
    return kid
