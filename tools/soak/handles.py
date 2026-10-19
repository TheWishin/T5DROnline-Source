"""Handle counts of one process by object type (Event, File, Thread, Semaphore, ...).

    python tools/soak/handles.py PID [--save FILE] [--diff FILE]

Read-only: one system-wide handle table query (NtQuerySystemInformation,
SystemExtendedHandleInformation), filtered to PID, and the object type names
(NtQueryObject, ObjectTypesInformation). --save writes the counts as JSON;
--diff prints what changed since such a file -- for a handle count that
creeps during a soak.
"""
import argparse
import ctypes
import ctypes.wintypes as wt
import json
import sys
from collections import Counter

ntdll = ctypes.WinDLL("ntdll")
ntdll.NtQuerySystemInformation.argtypes = [ctypes.c_ulong, ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong)]
ntdll.NtQueryObject.argtypes = [wt.HANDLE, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong)]


class HANDLE_EX(ctypes.Structure):
    _fields_ = [("Object", ctypes.c_void_p), ("UniqueProcessId", ctypes.c_size_t), ("HandleValue", ctypes.c_size_t),
                ("GrantedAccess", ctypes.c_ulong), ("CreatorBackTraceIndex", ctypes.c_ushort),
                ("ObjectTypeIndex", ctypes.c_ushort), ("HandleAttributes", ctypes.c_ulong), ("Reserved", ctypes.c_ulong)]


class UNICODE_STRING(ctypes.Structure):
    _fields_ = [("Length", ctypes.c_ushort), ("MaximumLength", ctypes.c_ushort), ("Buffer", ctypes.c_void_p)]


def query(cls, fn, *pre):
    size = 1 << 20
    while True:
        buf = ctypes.create_string_buffer(size)
        ret = ctypes.c_ulong()
        st = fn(*pre, cls, buf, size, ctypes.byref(ret)) & 0xFFFFFFFF
        if st == 0xC0000004 or st == 0x80000005:          # STATUS_INFO_LENGTH_MISMATCH / BUFFER_OVERFLOW
            size = max(size * 2, ret.value + 4096)
            continue
        if st:
            raise OSError(f"NT status 0x{st:08X}")
        return buf


def type_names():
    """{type index: name} from ObjectTypesInformation (class 3)."""
    buf = query(3, ntdll.NtQueryObject, None)
    n = ctypes.c_ulong.from_buffer(buf).value
    off = ctypes.sizeof(ctypes.c_void_p)                    # NumberOfTypes, padded
    names = {}
    for _ in range(n):
        us = UNICODE_STRING.from_buffer(buf, off)
        name = ctypes.wstring_at(us.Buffer, us.Length // 2) if us.Buffer else "?"
        idx = ctypes.c_ubyte.from_buffer(buf, off + 0x5A).value   # OBJECT_TYPE_INFORMATION.TypeIndex
        names[idx] = name
        size = 0x68 + ((us.MaximumLength + 7) & ~7)             # the record, then the name, 8-aligned
        off += size
    return names


def counts(pid):
    buf = query(64, ntdll.NtQuerySystemInformation)
    n = ctypes.c_size_t.from_buffer(buf).value
    base = 2 * ctypes.sizeof(ctypes.c_size_t)
    arr = (HANDLE_EX * n).from_buffer(buf, base)
    names = type_names()
    c = Counter()
    for h in arr:
        if h.UniqueProcessId == pid:
            c[names.get(h.ObjectTypeIndex, f"type{h.ObjectTypeIndex}")] += 1
    return c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pid", type=int)
    ap.add_argument("--save")
    ap.add_argument("--diff")
    a = ap.parse_args()
    c = counts(a.pid)
    if a.diff:
        with open(a.diff) as f:
            old = Counter(json.load(f))
        for k in sorted(set(c) | set(old), key=lambda k: -(c[k] - old[k])):
            if c[k] != old[k]:
                print(f"{k:24s} {old[k]:6d} -> {c[k]:6d} ({c[k] - old[k]:+d})")
    else:
        for k, v in c.most_common():
            print(f"{k:24s} {v:6d}")
        print(f"{'total':24s} {sum(c.values()):6d}")
    if a.save:
        with open(a.save, "w") as f:
            json.dump(c, f)


if __name__ == "__main__":
    sys.exit(main())
