#!/usr/bin/env python3
"""Owner-local EU Online v02.00 review, without building or running the game.

Run `extract` on the owner's package, then decrypt EBOOT privately with an
owner-verified free-licence method (tools/unself.py does not implement it).
Run `compare` on the two pinned decrypted programs. All generated files stay
outside this repository. See docs/EU.md; candidates are never runtime tables.
"""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import addr_map

EU_CONTENT_ID = "UP0700-NPEA00019_00-TEKKEN5DRO000000"
PROGRAMS = {"us": "be80165b84e30b6334baa6d6331b9db4ffd5a6a4",
            "eu": "a26bc6e037e5a8faf40250849acfa8a40d027fff"}


def checked_program(path, region):
    path = addr_map.outside_repository(path)
    digest = hashlib.sha1(path.read_bytes()).hexdigest()
    if digest != PROGRAMS[region]:
        raise ValueError(f"{region}: decrypted program SHA-1 does not match docs/EU.md; stop")
    return path


def package_id(path):
    with Path(path).open("rb") as f:
        header = f.read(0x60)
    if len(header) < 0x60 or header[:4] != b"\x7fPKG":
        raise ValueError("not a PS3 package")
    return header[0x30:0x54].split(b"\0")[0].decode("ascii")


def run_tool(deps, tool, args, scratch, env=None):
    script = deps / "tools" / (tool + ".py")
    if not script.is_file():
        raise ValueError(f"missing owner's prepared ps3recomp tool: {tool}.py")
    subprocess.run([sys.executable, str(script), *map(str, args)], cwd=scratch, env=env, check=True)


def extract(a):
    package = addr_map.outside_repository(a.package)
    deps = addr_map.outside_repository(a.deps)
    scratch = addr_map.outside_repository(a.scratch)
    if package_id(package) != EU_CONTENT_ID:
        raise ValueError("package content ID is not the documented EU Online edition")
    env = dict(os.environ)
    keys = a.keys or env.get("T5DR_KEYS")
    if keys:
        env["T5DR_KEYS"] = str(addr_map.outside_repository(keys))
    scratch.mkdir(parents=True, exist_ok=False)
    for name in ("PARAM.SFO", "EBOOT.BIN"):
        run_tool(deps, "pkg_extract", [package, scratch / "package", "--only", name], scratch, env)
    print("Extracted privately. Verify PARAM.SFO: TITLE_ID NPEA00019, VERSION 02.00, APP_VER 01.00.")
    print("STOP: tools/unself.py requires a RAP and has no free-licence path. The owner must decrypt locally")
    print("with a verified free-licence method, then use compare. Do not invent a RAP or copy any file here.")


def source_inventory(directory, source_root=None):
    """Review aid only: literals include masks/sizes, and expressions/fields need manual review."""
    root = Path(source_root) if source_root is not None else Path(__file__).resolve().parent.parent
    with (directory / "source_literals.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(("source", "line", "literal", "classification", "owner_notes"))
        for path in sorted((root / "src").rglob("*")):
            if path.suffix not in (".h", ".c", ".cpp"):
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                for literal in re.findall(r"\b0[xX][0-9a-fA-F]{5,8}(?=[uUlL]*\b)", line):
                    writer.writerow((path.relative_to(root).as_posix(), number, literal, "unclassified", ""))


def compare(a):
    us, eu = checked_program(a.us, "us"), checked_program(a.eu, "eu")
    deps = addr_map.outside_repository(a.deps)
    scratch = addr_map.outside_repository(a.scratch)
    scratch.mkdir(parents=True, exist_ok=False)
    programs = []
    for region, elf in (("us", us), ("eu", eu)):
        analysis = scratch / region
        analysis.mkdir()
        run_tool(deps, "ppu_loader", [elf, "-o", analysis], scratch)
        functions = analysis / "functions.json"
        run_tool(deps, "find_functions", [elf, "--seed-json", analysis / "EBOOT.functions.json",
                                         "-o", functions], scratch)
        programs.append(addr_map.Program(elf, functions))
    U, E = programs
    fmap = addr_map.match_functions(U, E)
    dmap = addr_map.pair_data(U, E, fmap)
    review = scratch / "review"
    addr_map.write_review(review, U, E, fmap, dmap, [int(x, 16) for x in a.required])
    source_inventory(review)
    with (review / "programs.json").open("w", encoding="utf-8") as f:
        json.dump({"elf_sha1": PROGRAMS, "crossplay_proven": False,
                   "note": "No runtime support enabled. All mappings require owner review."}, f, indent=2)
    print("Private review tables ready; no lifting, compilation, game run or online access performed.")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = ap.add_subparsers(dest="command", required=True)
    take = commands.add_parser("extract", help="extract only the owner's SFO and EBOOT, then stop")
    take.add_argument("--package", required=True)
    take.add_argument("--keys", help="owner's local key file, passed to package extractor; never printed")
    diff = commands.add_parser("compare", help="analyse pinned decrypted programs; no lifter/build/game")
    diff.add_argument("--us", required=True)
    diff.add_argument("--eu", required=True)
    diff.add_argument("--required", nargs="*", default=[], metavar="US_HEX_ADDRESS",
                      help="addresses already evidenced by repository source, selected by the owner")
    for command in (take, diff):
        command.add_argument("--deps", required=True, help="owner's prepared ps3recomp tree outside this repo")
        command.add_argument("--scratch", required=True, help="NEW private output directory outside this repo")
    a = ap.parse_args(argv)
    try:
        (extract if a.command == "extract" else compare)(a)
    except (ValueError, OSError, subprocess.CalledProcessError) as e:
        ap.error(str(e))
    return 0


if __name__ == "__main__":
    sys.exit(main())
