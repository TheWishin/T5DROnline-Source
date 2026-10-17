"""A self-signed TLS certificate with nothing but the standard library.

Python can serve TLS (ssl) but cannot make a key or a certificate, and a player hosting from a
Windows PC has no openssl. So this module does the minimum by hand: an RSA-2048 key (random
primes from the `secrets` CSPRNG, Miller-Rabin), an X.509 v3 certificate in DER (the same fields
`openssl req -x509` writes: basicConstraints CA:TRUE, subjectKeyIdentifier, subjectAltName),
signed sha256WithRSAEncryption (PKCS#1 v1.5), and the PEM files ssl.load_cert_chain() reads
(the key as unencrypted PKCS#8, written readable by the owner only).

Clients do not check a CA for it: they pin the certificate's SHA-256 fingerprint
(`LobbyClient(tls_fingerprint=...)`, the "fingerprint" of a servers.json entry). The test suite
cross-checks the result with openssl (x509 -text, verify, rsa -check) when openssl exists.

    python -m t5lobby.server.admin gen-cert --dir DIR [--name lobby.example.org]
"""
import base64
import datetime
import hashlib
import math
import os
import secrets
import ssl

# --------------------------------------------------------------------------- RSA

_SMALL_PRIMES = []


def _small_primes(limit=2000):
    if not _SMALL_PRIMES:
        sieve = bytearray([1]) * limit
        sieve[0:2] = b"\x00\x00"
        for i in range(2, int(limit ** 0.5) + 1):
            if sieve[i]:
                sieve[i * i::i] = bytearray(len(sieve[i * i::i]))
        _SMALL_PRIMES.extend(i for i in range(limit) if sieve[i])
    return _SMALL_PRIMES


def is_probable_prime(n, rounds=40):
    if n < 2:
        return False
    for p in _small_primes():
        if n % p == 0:
            return n == p
    d, r = n - 1, 0
    while d % 2 == 0:
        d //= 2
        r += 1
    for _ in range(rounds):
        a = 2 + secrets.randbelow(n - 3)
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(r - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


def _random_prime(bits, e):
    prod = math.prod(_small_primes())
    while True:
        c = secrets.randbits(bits) | (3 << (bits - 2)) | 1    # top two bits set: p*q has exactly 2*bits bits
        if math.gcd(c, prod) != 1 or (c - 1) % e == 0:
            continue
        if is_probable_prime(c):
            return c


def generate_rsa(bits=2048, e=65537):
    """-> dict n, e, d, p, q, dp, dq, qinv."""
    while True:
        p = _random_prime(bits // 2, e)
        q = _random_prime(bits // 2, e)
        if p == q or abs(p - q).bit_length() < bits // 2 - 100:
            continue
        n = p * q
        if n.bit_length() != bits:
            continue
        lam = (p - 1) * (q - 1) // math.gcd(p - 1, q - 1)
        if math.gcd(e, lam) != 1:
            continue
        d = pow(e, -1, lam)
        if p < q:
            p, q = q, p
        return {"n": n, "e": e, "d": d, "p": p, "q": q, "dp": d % (p - 1), "dq": d % (q - 1),
                "qinv": pow(q, -1, p)}


# --------------------------------------------------------------------------- DER

def _len(n):
    if n < 0x80:
        return bytes([n])
    b = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(b)]) + b


def _tlv(tag, content):
    return bytes([tag]) + _len(len(content)) + content


def _int(v):
    return _tlv(0x02, v.to_bytes(v.bit_length() // 8 + 1, "big"))     # leading 0 byte keeps it positive


def _seq(*items):
    return _tlv(0x30, b"".join(items))


def _set(*items):
    return _tlv(0x31, b"".join(items))


def _oid(dotted):
    parts = [int(x) for x in dotted.split(".")]
    out = bytearray([40 * parts[0] + parts[1]])
    for v in parts[2:]:
        chunk = [v & 0x7F]
        v >>= 7
        while v:
            chunk.append(0x80 | (v & 0x7F))
            v >>= 7
        out += bytes(reversed(chunk))
    return _tlv(0x06, bytes(out))


def _utf8(s):
    return _tlv(0x0C, s.encode("utf-8"))


def _time(dt):
    if 1950 <= dt.year < 2050:
        return _tlv(0x17, dt.strftime("%y%m%d%H%M%SZ").encode())      # UTCTime
    return _tlv(0x18, dt.strftime("%Y%m%d%H%M%SZ").encode())          # GeneralizedTime


NULL = b"\x05\x00"
OID_RSA = "1.2.840.113549.1.1.1"
OID_SHA256_RSA = "1.2.840.113549.1.1.11"
DIGESTINFO_SHA256 = bytes.fromhex("3031300d060960864801650304020105000420")


def _sign(key, data):
    k = (key["n"].bit_length() + 7) // 8
    t = DIGESTINFO_SHA256 + hashlib.sha256(data).digest()
    em = b"\x00\x01" + b"\xff" * (k - len(t) - 3) + b"\x00" + t
    m = int.from_bytes(em, "big")
    # CRT, then check the result with the public exponent (guards against a faulty computation
    # leaking the key, and against any bug in the above)
    s1 = pow(m, key["dp"], key["p"])
    s2 = pow(m, key["dq"], key["q"])
    h = (key["qinv"] * (s1 - s2)) % key["p"]
    s = s2 + h * key["q"]
    if pow(s, key["e"], key["n"]) != m:
        raise ArithmeticError("RSA signature self-check failed")
    return s.to_bytes(k, "big")


def _san(name):
    """subjectAltName: an IP address or a DNS name."""
    import ipaddress
    try:
        ip = ipaddress.ip_address(name)
        return _tlv(0x87, ip.packed)            # [7] iPAddress
    except ValueError:
        return _tlv(0x82, name.encode("ascii", "ignore"))   # [2] dNSName


def make_certificate(common_name="t5lobby", days=3650, bits=2048, key=None):
    """-> (cert_pem, key_pem, key dict)."""
    key = key or generate_rsa(bits)
    spk = _seq(_int(key["n"]), _int(key["e"]))                       # RSAPublicKey
    spki = _seq(_seq(_oid(OID_RSA), NULL), _tlv(0x03, b"\x00" + spk))
    name = _seq(_set(_seq(_oid("2.5.4.3"), _utf8(common_name[:64]))))
    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    not_before = now - datetime.timedelta(hours=1)
    not_after = now + datetime.timedelta(days=days)
    alg = _seq(_oid(OID_SHA256_RSA), NULL)
    ski = hashlib.sha1(spk).digest()
    exts = _seq(
        _seq(_oid("2.5.29.14"), _tlv(0x04, _tlv(0x04, ski))),                                 # subjectKeyIdentifier
        _seq(_oid("2.5.29.35"), _tlv(0x04, _seq(_tlv(0x80, ski)))),                           # authorityKeyIdentifier
        _seq(_oid("2.5.29.19"), b"\x01\x01\xff", _tlv(0x04, _seq(b"\x01\x01\xff"))),          # basicConstraints CA:TRUE, critical
        _seq(_oid("2.5.29.17"), _tlv(0x04, _seq(_san(common_name)))),                         # subjectAltName
    )
    serial = int.from_bytes(secrets.token_bytes(16), "big") >> 1 | 1
    tbs = _seq(_tlv(0xA0, _int(2)), _int(serial), alg, name, _seq(_time(not_before), _time(not_after)),
               name, spki, _tlv(0xA3, exts))
    cert = _seq(tbs, alg, _tlv(0x03, b"\x00" + _sign(key, tbs)))
    rsa_priv = _seq(_int(0), *(_int(key[k]) for k in ("n", "e", "d", "p", "q", "dp", "dq", "qinv")))
    pkcs8 = _seq(_int(0), _seq(_oid(OID_RSA), NULL), _tlv(0x04, rsa_priv))
    return _pem("CERTIFICATE", cert), _pem("PRIVATE KEY", pkcs8), key


def _pem(label, der):
    b64 = base64.b64encode(der).decode("ascii")
    lines = [b64[i:i + 64] for i in range(0, len(b64), 64)]
    return f"-----BEGIN {label}-----\n" + "\n".join(lines) + f"\n-----END {label}-----\n"


# --------------------------------------------------------------------------- files

def fingerprint(cert_path_or_pem):
    """SHA-256 of the certificate (DER) as lowercase hex: what clients pin."""
    pem = cert_path_or_pem
    if "-----BEGIN" not in pem:
        with open(pem, encoding="ascii") as f:
            pem = f.read()
    return hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem)).hexdigest()


def pretty(fp):
    """AB:CD:... -- the way openssl prints it."""
    fp = fp.replace(":", "").upper()
    return ":".join(fp[i:i + 2] for i in range(0, len(fp), 2))


def write_pair(directory, common_name="t5lobby", days=3650, force=False):
    """Create directory/cert.pem and directory/key.pem (key readable by the owner only).
    -> (cert path, key path, fingerprint hex)."""
    os.makedirs(directory, exist_ok=True)
    cert_p, key_p = os.path.join(directory, "cert.pem"), os.path.join(directory, "key.pem")
    if not force and (os.path.exists(cert_p) or os.path.exists(key_p)):
        raise FileExistsError(f"{cert_p} or {key_p} exists (keep it: clients pinned its fingerprint)")
    cert_pem, key_pem, _ = make_certificate(common_name, days)
    tmp = key_p + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="ascii") as f:
        f.write(key_pem)
    os.replace(tmp, key_p)
    with open(cert_p, "w", encoding="ascii") as f:
        f.write(cert_pem)
    return cert_p, key_p, fingerprint(cert_pem)
