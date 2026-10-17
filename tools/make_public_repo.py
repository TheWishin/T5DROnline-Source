#!/usr/bin/env python3
"""Render the public repository (README-only, like Tekken 6 Native Online).

    python tools/make_public_repo.py --out C:/T5DR-public

Development happens in the private repository (TheWishin/T5DROnline-Dev). The
public one (TheWishin/T5DROnline) holds only what a player reads -- README.md,
README.de.md, TROUBLESHOOTING.md, LICENSE -- plus the release zips. This writes
those files from this checkout: the player part of each README (no "Building
from source"), links to private docs turned into "in the release zip" notes.

Commit the result with a neutral author that is not linked to a GitHub account,
so the public repository shows no contributors (docs/RELEASING.md).
"""
import argparse
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUBLIC = "https://github.com/TheWishin/T5DROnline"
FILES = {"README.md", "README.de.md", "TROUBLESHOOTING.md", "LICENSE"}
IN_ZIP = {"en": " (in the release zip)", "de": " (im Release-Zip)"}


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


def english():
    s = read("README.md")
    end = s.index("<!-- players:end -->")
    return s[:end].replace("<!-- players:start -->\n", "").rstrip() + "\n"


def german():
    s = read("docs/README.de.md")
    cut = s.find("\n## Aus dem Quellcode bauen")
    return (s if cut < 0 else s[:cut]).rstrip() + "\n"


def fix_links(text, lang):
    note = IN_ZIP[lang]
    # absolute links into the (now private) source tree
    text = text.replace(PUBLIC + "/blob/main/docs/README.de.md", "[README.de.md](README.de.md)")
    text = text.replace(PUBLIC + "/blob/main/docs/TROUBLESHOOTING.md", "[TROUBLESHOOTING.md](TROUBLESHOOTING.md)")
    text = re.sub(re.escape(PUBLIC) + r"/blob/main/docs/([\w.\-]+)", lambda m: f"`docs\\{m.group(1)}`{note}", text)
    text = text.replace("[../README.md](../README.md)", "[README.md](README.md)")

    def md(m):
        label, target = m.group(1), m.group(2)
        if target.startswith(("http://", "https://", "#", "mailto:")):
            return m.group(0)
        name = target.split("#")[0].split("/")[-1]
        if name in FILES:
            return f"[{label}]({name})"
        return f"`docs\\{name}`{note}"
    return re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", md, text)


def check(out):
    bad = []
    for name in FILES - {"LICENSE"}:
        with open(os.path.join(out, name), encoding="utf-8") as f:
            text = f.read()
        for target in re.findall(r"\]\(([^)\s]+)\)", text):
            if target.startswith(("http://", "https://", "#", "mailto:")):
                continue
            if target.split("#")[0] not in FILES:
                bad.append(f"{name}: link to {target}")
        if "/blob/main/" in text and PUBLIC + "/blob/main/" in text:
            bad.append(f"{name}: link into the private source tree")
    return bad


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    docs = {
        "README.md": fix_links(english(), "en"),
        "README.de.md": fix_links(german(), "de"),
        "TROUBLESHOOTING.md": fix_links(read("docs/TROUBLESHOOTING.md"), "en"),
    }
    for name, text in docs.items():
        with open(os.path.join(a.out, name), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    shutil.copyfile(os.path.join(ROOT, "LICENSE"), os.path.join(a.out, "LICENSE"))
    bad = check(a.out)
    for b in bad:
        print("ERROR:", b)
    print(f"wrote {', '.join(sorted(FILES))} to {a.out}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
