#!/usr/bin/env python3
"""Check the shipped PGO profile of the lifted code: only counters keyed by function names.

    python tools/profile_check.py [tools/gamedll/t5dr_lifted.proftext]

tools/gamedll/t5dr_lifted.proftext is the profile build_game_dll.py compiles the lifted code with
(profile-guided optimisation; made by tools/pgo_train.py, docs/BUILD_PERF.md). It is the text form of
an LLVM front-end instrumentation profile, one record per function:

    <function name>
    # Func Hash:
    <structural hash of the function, an integer>
    # Num Counters:
    <n>
    # Counter Values:
    <n integers: how often each region of the function ran>
    <blank line>

A record may name only a lifted PPU function (func_<guest address>), a lifted SPU function
(<image>_spu_func_<local-store address>), an SPU image's register function, or a helper of the
generated code / ps3recomp's headers as "<source file>:<name>". Nothing else may appear: no value
profiles, no bitmaps, no binary ids, no other text. So the file holds no game code or data -- only
function names (guest addresses) and execution counts. tools/check_no_game_data.py and
tools/package_release.py accept the file under its fixed path only when this check passes.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILE_PATH = "tools/gamedll/t5dr_lifted.proftext"     # the one path the guards exempt
MAX_BYTES = 8 << 20
MAX_COUNTERS = 1 << 16

NAME = re.compile(
    r"\?func_[0-9A-F]{8}@@YAXPEAUppu_context@@@Z"                     # lifted PPU function (C++ name)
    r"|[a-z][a-z0-9_]{0,40}_spu_func_[0-9A-F]{8}"                      # lifted SPU function
    r"|[a-z][a-z0-9_]{0,40}_spu_recomp_register|t5dr_spu_register_all"  # SPU image registration
    r"|(?:ppu_recomp_\d{3}\.cpp|spu_recomp\.c|spu_dispatch_mt\.c|spu_workloads\.c|t5dr_game_dll\.c)"
    r":[A-Za-z_?][A-Za-z0-9_?@$]{0,160}")                              # static helper: <file>:<name>
INT = re.compile(r"0|[1-9][0-9]{0,19}")


def check(data):
    """Problems found in the profile's bytes (empty list: it is only names, hashes and counts)."""
    if len(data) > MAX_BYTES:
        return [f"{len(data):,} bytes is over the {MAX_BYTES:,}-byte limit for the profile"]
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError:
        return ["not ASCII text"]
    if "\r" in text:
        text = text.replace("\r\n", "\n")
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    found = []
    i, records, names = 0, 0, set()
    if lines[:1] == [":fe"]:                           # optional header: front-end instrumentation
        i = 1
    elif lines[:2] == ["# IR level Instrumentation Flag", ":ir"]:     # LLVM IR instrumentation
        i = 2

    def bad(msg):
        found.append(f"line {i + 1}: {msg}")

    while i < len(lines) and len(found) < 20:
        if lines[i] == "":
            i += 1
            continue
        name = lines[i]
        if not NAME.fullmatch(name):
            bad("not an allowed function name: %r" % name[:80])
            break
        rec = lines[i + 1:i + 6]
        if len(rec) < 5 or rec[0] != "# Func Hash:" or not INT.fullmatch(rec[1]) or rec[2] != "# Num Counters:" \
                or not INT.fullmatch(rec[3]) or rec[4] != "# Counter Values:":
            bad("record of %s is not: hash, counter count, counter values" % name)
            break
        if (name, rec[1]) in names:         # one name may come with several hashes (same-named helpers)
            bad("function listed twice: %s" % name)
        names.add((name, rec[1]))
        n = int(rec[3])
        if not 1 <= n <= MAX_COUNTERS:
            bad("%d counters" % n)
            break
        vals = lines[i + 6:i + 6 + n]
        if len(vals) != n or not all(INT.fullmatch(v) for v in vals):
            bad("counter values of %s are not %d plain integers" % (name, n))
            break
        i += 6 + n
        if i < len(lines) and lines[i] != "":
            bad("unexpected line after the counters of %s (value profile or bitmap?): %r" % (name, lines[i][:60]))
            break
        records += 1
    if not found and records == 0:
        found.append("no function records")
    return found


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, *PROFILE_PATH.split("/"))
    with open(path, "rb") as f:
        problems = check(f.read())
    for p in problems:
        print(f"{path}: {p}")
    if problems:
        sys.exit(1)
    print(f"ok: {path} holds only function names, hashes and execution counts")


if __name__ == "__main__":
    main()
