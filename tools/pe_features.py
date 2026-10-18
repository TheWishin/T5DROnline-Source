#!/usr/bin/env python3
"""The PE features that antivirus machine-learning models look at, for one or more files.

    python tools/pe_features.py FILE [FILE ...] [--json]
    python tools/pe_features.py --table FILE [FILE ...]      one line per file

Standard library only, reads the files and changes nothing, uploads nothing. It reports what a
static scanner sees without running the program: the headers (timestamp, checksum, DLL
characteristics, subsystem), the Rich header (which Microsoft tools made the object files), the
debug directory (PDB path), the sections (entropy, flags), the overlay (bytes after the last
section), the Authenticode signature, the imports and the version information strings.

tools/package_release.py builds `T5DR Online.exe` in several ways (docs/RELEASING.md "The launcher
stub"); this tool shows how each looks next to ordinary programs.
"""
import argparse
import json
import math
import os
import struct
import sys

DLL_CHARS = [(0x0020, "HIGH_ENTROPY_VA"), (0x0040, "DYNAMIC_BASE"), (0x0080, "FORCE_INTEGRITY"),
             (0x0100, "NX_COMPAT"), (0x0200, "NO_ISOLATION"), (0x0400, "NO_SEH"), (0x0800, "NO_BIND"),
             (0x1000, "APPCONTAINER"), (0x2000, "WDM_DRIVER"), (0x4000, "GUARD_CF"),
             (0x8000, "TERMINAL_SERVER_AWARE")]
SECTION_FLAGS = [(0x20, "code"), (0x40, "idata"), (0x80, "udata"), (0x20000000, "X"), (0x40000000, "R"),
                 (0x80000000, "W")]
DEBUG_TYPES = {1: "COFF", 2: "CODEVIEW", 3: "FPO", 4: "MISC", 9: "BORLAND", 10: "RESERVED10", 11: "CLSID",
               12: "VC_FEATURE", 13: "POGO", 14: "ILTCG", 16: "REPRO", 20: "EX_DLLCHARACTERISTICS"}
SUBSYSTEMS = {1: "native", 2: "windows GUI", 3: "windows console", 9: "windows CE GUI"}
# Rich header product ids that name the tool (high 16 bits of the comp.id): the common MSVC ones.
RICH_PRODUCTS = {0x00: "unknown", 0x01: "import", 0x0F: "ASM (masm)", 0x5D: "C (cl)", 0x5E: "C++ (cl)",
                 0x5F: "resource (cvtres)", 0x60: "export", 0x61: "link import lib", 0x93: "MASM", 0x104: "ASM",
                 0x105: "C (cl, 2019+)", 0x106: "C++ (cl, 2019+)", 0x107: "link", 0x109: "resource", 0x10A: "link"}


def entropy(data):
    if not data:
        return 0.0
    counts = [0] * 256
    for b in data:
        counts[b] += 1
    n = len(data)
    return -sum(c / n * math.log2(c / n) for c in counts if c)


def pe_checksum(data, checksum_off):
    """The PE checksum as imagehlp's CheckSumMappedFile computes it."""
    total = 0
    n = len(data)
    padded = data + (b"\0" * (n % 4 and 4 - n % 4))
    for i in range(0, len(padded), 4):
        if i == checksum_off:
            continue
        total += struct.unpack_from("<I", padded, i)[0]
        total = (total & 0xFFFFFFFF) + (total >> 32)
    total = (total & 0xFFFF) + (total >> 16)
    total = (total & 0xFFFF) + (total >> 16)
    return (total + n) & 0xFFFFFFFF


def flags(value, table):
    return [name for bit, name in table if value & bit]


def parse(path):
    with open(path, "rb") as f:
        data = f.read()
    out = {"file": os.path.basename(path), "size": len(data), "entropy": round(entropy(data), 2)}
    if data[:2] != b"MZ":
        out["error"] = "not a PE file"
        return out
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        out["error"] = "no PE signature"
        return out
    machine, nsec, stamp, _, _, optsz, chars = struct.unpack_from("<HHIIIHH", data, pe + 4)
    opt = pe + 24
    magic = struct.unpack_from("<H", data, opt)[0]
    plus = magic == 0x20B
    entry = struct.unpack_from("<I", data, opt + 16)[0]
    link_major, link_minor = data[opt + 2], data[opt + 3]
    checksum_off = opt + 64
    checksum = struct.unpack_from("<I", data, checksum_off)[0]
    subsystem, dllchars = struct.unpack_from("<HH", data, opt + 68)
    os_ver = struct.unpack_from("<HH", data, opt + 40)
    subsys_ver = struct.unpack_from("<HH", data, opt + 48)
    ddir = opt + (112 if plus else 96)
    dirs = [struct.unpack_from("<II", data, ddir + 8 * i) for i in range(16)]
    secs = opt + optsz
    sections = []
    for i in range(nsec):
        name, vsize, vaddr, rawsize, rawptr = struct.unpack_from("<8sIIII", data, secs + 40 * i)
        schars = struct.unpack_from("<I", data, secs + 40 * i + 36)[0]
        body = data[rawptr:rawptr + rawsize]
        sections.append({"name": name.rstrip(b"\0").decode("latin-1"), "vsize": vsize, "vaddr": vaddr,
                         "rawsize": rawsize, "rawptr": rawptr, "entropy": round(entropy(body), 2),
                         "flags": flags(schars, SECTION_FLAGS)})

    def off(rva):
        for s in sections:
            if s["vaddr"] <= rva < s["vaddr"] + max(s["vsize"], s["rawsize"]):
                return rva - s["vaddr"] + s["rawptr"]
        return None

    out.update({
        "machine": hex(machine), "timestamp": stamp,
        "timestamp_utc": __import__("datetime").datetime.fromtimestamp(stamp, __import__("datetime").timezone.utc)
        .strftime("%Y-%m-%d %H:%M:%S") if stamp else "0",
        "linker": f"{link_major}.{link_minor}", "subsystem": SUBSYSTEMS.get(subsystem, str(subsystem)),
        "os_version": ".".join(map(str, os_ver)), "subsystem_version": ".".join(map(str, subsys_ver)),
        "dll_characteristics": flags(dllchars, DLL_CHARS), "entry_section": next(
            (s["name"] for s in sections if s["vaddr"] <= entry < s["vaddr"] + max(s["vsize"], s["rawsize"])), "?"),
        "checksum": hex(checksum), "checksum_valid": checksum != 0 and checksum == pe_checksum(data, checksum_off),
        "sections": sections,
    })
    # overlay = bytes after the last section's raw data; the certificate table lives there when signed
    end = max((s["rawptr"] + s["rawsize"] for s in sections), default=0)
    cert_pos, cert_size = dirs[4]
    out["signed"] = bool(cert_pos and cert_size)
    out["overlay"] = max(0, len(data) - end - (cert_size if out["signed"] else 0))
    # Rich header
    rich = data.find(b"Rich", 0x80, pe)
    rich_list = []
    if rich > 0:
        key = struct.unpack_from("<I", data, rich + 4)[0]
        # walk back from "Rich" to the "DanS" marker (xor-masked)
        pos = rich - 4
        while pos >= 0x80 and (struct.unpack_from("<I", data, pos)[0] ^ key) != 0x536E6144:
            pos -= 4
        if pos >= 0x80:
            for q in range(pos + 16, rich, 8):
                comp, count = struct.unpack_from("<II", data, q)
                comp ^= key
                count ^= key
                rich_list.append({"product": RICH_PRODUCTS.get(comp >> 16, hex(comp >> 16)), "build": comp & 0xFFFF,
                                  "count": count})
    out["rich_header"] = rich_list
    # debug directory
    debug = []
    dva, dsz = dirs[6]
    d_off = off(dva) if dva else None
    for i in range(dsz // 28 if d_off else 0):
        ch, st, major, minor, typ, size, rva, ptr = struct.unpack_from("<IIHHIIII", data, d_off + 28 * i)
        item = {"type": DEBUG_TYPES.get(typ, str(typ)), "size": size}
        if typ == 2 and ptr and data[ptr:ptr + 4] == b"RSDS":
            item["pdb"] = data[ptr + 24:data.find(b"\0", ptr + 24)].decode("utf-8", "replace")
        debug.append(item)
    out["debug_directory"] = debug
    # imports (normal and delay-load)
    imports = {}
    ioff = off(dirs[1][0]) if dirs[1][0] else None
    while ioff:
        ilt, _, _, name_rva, iat = struct.unpack_from("<IIIII", data, ioff)
        if not name_rva:
            break
        dll = data[off(name_rva):data.find(b"\0", off(name_rva))].decode("latin-1").lower()
        funcs = []
        t = off(ilt or iat)
        step = 8 if plus else 4
        while t:
            v = struct.unpack_from("<Q" if plus else "<I", data, t)[0]
            if not v:
                break
            if v >> (63 if plus else 31):
                funcs.append(f"#{v & 0xFFFF}")
            else:
                n = off(v & 0x7FFFFFFF)
                funcs.append(data[n + 2:data.find(b"\0", n + 2)].decode("latin-1"))
            t += step
        imports[dll] = funcs
        ioff += 20
    delay = []
    doff = off(dirs[13][0]) if dirs[13][0] else None
    while doff:
        attrs, name_rva = struct.unpack_from("<II", data, doff)
        if not name_rva:
            break
        n = off(name_rva) if attrs & 1 else None
        if n:
            delay.append(data[n:data.find(b"\0", n)].decode("latin-1").lower())
        doff += 32
    out["imports"] = imports
    out["delay_imports"] = delay
    out["import_count"] = sum(len(v) for v in imports.values())
    out["has_tls"] = bool(dirs[9][0])
    out["has_exports"] = bool(dirs[0][0])
    out["has_resources"] = bool(dirs[2][0])
    # version information: the UTF-16 key/value pairs of the StringFileInfo block
    version = {}
    for key in ("CompanyName", "FileDescription", "FileVersion", "InternalName", "LegalCopyright",
                "OriginalFilename", "ProductName", "ProductVersion"):
        k = key.encode("utf-16-le") + b"\0\0"
        i = data.find(k)
        if i >= 0:
            j = i + len(k)
            while j % 4:
                j += 1
            end = j
            while end + 1 < len(data) and data[end:end + 2] != b"\0\0":
                end += 2
            version[key] = data[j:end].decode("utf-16-le", "replace")
    out["version_info"] = version
    return out


def table_row(r):
    if "error" in r:
        return f"{r['file']:<28} {r['error']}"
    stamp = r["timestamp_utc"][:10]
    pdb = any("pdb" in d for d in r["debug_directory"])
    return (f"{r['file'][:28]:<28} {r['size']:>10,} H={r['entropy']:<4} {stamp:>10} rich={'y' if r['rich_header'] else 'n'} "
            f"dbg={len(r['debug_directory'])}{'+pdb' if pdb else ''} "
            f"chk={'ok' if r['checksum_valid'] else 'no'} cfg={'y' if 'GUARD_CF' in r['dll_characteristics'] else 'n'} "
            f"aslr={'y' if 'DYNAMIC_BASE' in r['dll_characteristics'] else 'n'}"
            f"{'+he' if 'HIGH_ENTROPY_VA' in r['dll_characteristics'] else ''} "
            f"sign={'y' if r['signed'] else 'n'} overlay={r['overlay']} imp={r['import_count']}/{len(r['imports'])}dll "
            f"ver={'y' if r['version_info'].get('ProductName') else 'n'}")


def show(r):
    if "error" in r:
        print(f"{r['file']}: {r['error']}")
        return
    print(f"== {r['file']}  ({r['size']:,} bytes, entropy {r['entropy']})")
    print(f"  built {r['timestamp_utc']} UTC, linker {r['linker']}, {r['subsystem']}, OS {r['os_version']}, "
          f"entry in {r['entry_section']}")
    print(f"  checksum {r['checksum']} ({'valid' if r['checksum_valid'] else 'not set or wrong'}), "
          f"signed: {r['signed']}, overlay: {r['overlay']} bytes, TLS: {r['has_tls']}")
    print(f"  DLL characteristics: {', '.join(r['dll_characteristics']) or '-'}")
    print("  Rich header: " + ("; ".join(f"{x['product']} build {x['build']} x{x['count']}" for x in r["rich_header"])
                               or "none"))
    print("  debug directory: " + ("; ".join(d["type"] + (f" ({d['pdb']})" if "pdb" in d else "") for d in
                                              r["debug_directory"]) or "none"))
    print("  sections: " + ", ".join(f"{s['name']} {s['rawsize']:,}B H={s['entropy']}" for s in r["sections"]))
    for dll, fns in r["imports"].items():
        print(f"  imports {dll}: {len(fns)}" + (f" ({', '.join(fns[:12])}{', ...' if len(fns) > 12 else ''})"
                                                if len(fns) <= 40 else ""))
    if r["delay_imports"]:
        print(f"  delay-load: {', '.join(r['delay_imports'])}")
    if r["version_info"]:
        print("  version info: " + "; ".join(f"{k}={v}" for k, v in r["version_info"].items()))
    else:
        print("  version info: none")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("files", nargs="+")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--table", action="store_true", help="one line per file")
    a = ap.parse_args()
    results = []
    for p in a.files:
        try:
            results.append(parse(p))
        except (OSError, struct.error, ValueError, TypeError) as e:
            results.append({"file": os.path.basename(p), "error": str(e)})
    if a.json:
        print(json.dumps(results, indent=1))
    elif a.table:
        for r in results:
            print(table_row(r))
    else:
        for r in results:
            show(r)


if __name__ == "__main__":
    sys.exit(main())
