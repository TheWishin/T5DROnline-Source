#!/usr/bin/env python3
"""Authenticode helpers for the release: which files we sign, whether a signed file is the file we
built, and whether Windows trusts its signature.

    python tools/code_signing.py list DIR           the files of a release folder that we sign
    python tools/code_signing.py verify FILE ...    Windows' verdict on each file (exit 1 unless all Valid)

What we sign (docs/RELEASING.md "Code signing"): the programs and DLLs we build ourselves --
`T5DR Online.exe`, `runtime/t5dr.exe` and any DLL we add next to them. Not `python/` (python.org's
files carry the Python Software Foundation's signature, vcruntime140.dll Microsoft's) and not
`toolchain/llvm/` (LLVM's release binaries are unsigned, but they are not ours to sign).

tools/package_release.py uses these functions in `--sign-stage finish`: a signing service only adds
a certificate to a file, so the signed copy must equal the built one in every other byte.
"""
import os
import subprocess
import sys

SIGN_EXTENSIONS = (".exe", ".dll")
# Whole folders of the release that hold other people's programs.
NOT_OURS = ("python", "toolchain")


def signable_files(root):
    """Relative paths ('/' separators, sorted) of the programs in a release folder that we sign."""
    found = []
    for dp, dns, fns in os.walk(root):
        rel_dir = os.path.relpath(dp, root).replace("\\", "/")
        if rel_dir == ".":
            dns[:] = [d for d in dns if d not in NOT_OURS]
        for f in fns:
            if f.lower().endswith(SIGN_EXTENSIONS):
                found.append(f if rel_dir == "." else f"{rel_dir}/{f}")
    return sorted(found)


def _u32(data, off):
    return int.from_bytes(data[off:off + 4], "little")


def _pe_layout(data):
    """(offset of CheckSum, offset of the certificate-table entry in the data directory)."""
    if data[:2] != b"MZ":
        raise ValueError("not a PE file (no MZ header)")
    pe = _u32(data, 0x3C)
    if data[pe:pe + 4] != b"PE\0\0":
        raise ValueError("not a PE file (no PE signature)")
    opt = pe + 24
    magic = int.from_bytes(data[opt:opt + 2], "little")
    if magic == 0x20B:           # PE32+
        ddir = opt + 112
    elif magic == 0x10B:         # PE32
        ddir = opt + 96
    else:
        raise ValueError(f"unknown optional header magic {magic:#x}")
    return opt + 64, ddir + 4 * 8        # data directory entry 4 = security (certificate table)


def certificate_table(data):
    """(file offset, size) of the Authenticode certificate table, (0, 0) when the file is unsigned."""
    _, sec = _pe_layout(data)
    return _u32(data, sec), _u32(data, sec + 4)


def strip_signature(data):
    """The PE image without its Authenticode signature: certificate table cut off, its directory entry
    and the header checksum zeroed (the three things signing changes), trailing zero padding removed.
    Equal results = the same program."""
    chk, sec = _pe_layout(data)
    pos, size = certificate_table(data)
    b = bytearray(data)
    b[chk:chk + 4] = bytes(4)
    if pos or size:
        if pos == 0 or pos + size > len(data):
            raise ValueError("the certificate table lies outside the file")
        del b[pos:]
    b[sec:sec + 8] = bytes(8)
    return bytes(b).rstrip(b"\0")


def same_program(built, signed):
    """True when `signed` is `built` plus a signature (and nothing else changed)."""
    return strip_signature(built) == strip_signature(signed)


PS_STATUS = ("$s = Get-AuthenticodeSignature -LiteralPath $env:T5DR_SIGFILE; "
             "$n = ''; if ($s.SignerCertificate) { $n = $s.SignerCertificate.Subject }; "
             "[Console]::Out.Write($s.Status.ToString() + '|' + $n)")


def authenticode_status(path):
    """(status, signer subject) as Windows PowerShell's Get-AuthenticodeSignature reports it:
    'Valid', 'NotSigned', 'NotTrusted', 'HashMismatch', ... ('Error' when it could not ask)."""
    env = dict(os.environ, T5DR_SIGFILE=os.path.abspath(path))
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                            "-Command", PS_STATUS], capture_output=True, text=True, errors="replace", env=env,
                           timeout=180)
    except (OSError, subprocess.SubprocessError):
        return "Error", ""
    status, _, subject = r.stdout.strip().partition("|")
    return (status or "Error"), subject


def main():
    args = sys.argv[1:]
    if len(args) >= 2 and args[0] == "list":
        print("\n".join(signable_files(args[1])))
        return 0
    if len(args) >= 2 and args[0] == "verify":
        bad = 0
        for p in args[1:]:
            status, subject = authenticode_status(p)
            print(f"{status:<12} {p}" + (f"   {subject}" if subject else ""))
            bad += status != "Valid"
        return 1 if bad else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
