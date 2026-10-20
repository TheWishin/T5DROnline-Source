"""The release tooling that runs without the game or a toolchain: CHANGELOG sections
for release notes (tools/release_notes.py) and whether one is ready for players
(release_preflight.py), version strings (package_release.py),
unpacking the pinned LLVM archive (tools/fetch_llvm.py, on a small fake archive)
and the PE import reader of tools/smoke_release.py."""
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

from helpers import PY, TOOLS, load_tool, put

notes = load_tool("release_notes")
package = load_tool("package_release")
fetch = load_tool("fetch_llvm")

CHANGELOG = """# Changelog

Intro text.

## v0.2.0-rc.1 (2026-11-02)

- rc one

## v0.1.0-preview (2026-10-20)

First public test build.

### Game

- boots
- fights

## [0.1.0] - 2026-10-19

- plain

## 0.0.9

## 2026-10-16 (day one)

- old
"""


class ChangelogSection(unittest.TestCase):
    def test_finds_section_with_subheadings(self):
        body = notes.find_section(CHANGELOG, "0.1.0-preview")
        self.assertTrue(body.startswith("First public test build."))
        self.assertIn("### Game", body)
        self.assertIn("- fights", body)
        self.assertNotIn("plain", body)

    def test_leading_v_and_brackets(self):
        self.assertEqual(notes.find_section(CHANGELOG, "v0.1.0"), "- plain")
        self.assertEqual(notes.find_section(CHANGELOG, "0.2.0-rc.1"), "- rc one")

    def test_no_prefix_match(self):
        # 0.1.0 must not pick the 0.1.0-preview heading, nor 0.2.0 the rc heading.
        self.assertEqual(notes.find_section(CHANGELOG, "0.1.0"), "- plain")
        self.assertIsNone(notes.find_section(CHANGELOG, "0.2.0"))
        self.assertIsNone(notes.find_section(CHANGELOG, "0.1.0-pre"))

    def test_empty_and_missing(self):
        self.assertEqual(notes.find_section(CHANGELOG, "0.0.9"), "")
        self.assertIsNone(notes.find_section(CHANGELOG, "9.9.9"))


class ChangelogReadyForPlayers(unittest.TestCase):
    """tools/release_preflight.py step 7: the launcher's update offer shows the notes as plain text, so a
    placeholder comment or an undated heading must not be tagged."""

    def test_dated_sections_without_comments_are_ready(self):
        pf = load_tool("release_preflight")
        for v in ("0.2.0-rc.1", "0.1.0-preview", "0.1.0", "9.9.9"):        # 9.9.9: missing is step 1's job
            self.assertEqual(pf.changelog_leftovers(v, CHANGELOG), [], v)

    def test_placeholders_and_a_missing_date(self):
        pf = load_tool("release_preflight")
        text = ("## v1.2.0 (not released yet)\n\n**Big.** Both players need it<!-- PENDING x: patch -->.\n\n"
                "### Online\n- one\n<!-- PENDING y: its entry\n### Controllers\n-->\n- two <!-- unclosed\n\n"
                "## v1.1.0 (2026-10-19)\n\n- old <!-- not this section -->\n")
        left = pf.changelog_leftovers("1.2.0", text)
        self.assertEqual(left[0], "heading without a release date: ## v1.2.0 (not released yet)")
        self.assertEqual(left[1:], ["comment: <!-- PENDING x: patch -->",
                                    "comment: <!-- PENDING y: its entry ### Controllers -->",
                                    "comment: <!-- unclosed -->"])
        self.assertEqual(pf.changelog_leftovers("1.1.0", text), ["comment: <!-- not this section -->"])

    def test_readme_release_lines(self):
        pf = load_tool("release_preflight")
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "docs"))
            put(os.path.join(d, "README.md"), "# T\n\n**Release 1.1.1 (2026-10-19).** Download\n"
                                              "`T5DR-Online-1.1.1.zip` from https://example.invalid\n\n"
                                              "1. Download `T5DR-Online-<version>.zip`.\n")
            put(os.path.join(d, "docs", "README.de.md"), "**Release 1.2.0 (2026-11-01).** Lade\n"
                                                         "`T5DR-Online-1.2.0.zip` von ...\n")
            self.assertEqual(pf.readme_leftovers("1.2.0", d),
                             ["README.md: the release line names 1.1.1, not 1.2.0"])
            self.assertEqual(pf.readme_leftovers("1.1.1", d),
                             ["docs/README.de.md: the release line names 1.2.0, not 1.1.1"])
            put(os.path.join(d, "README.md"), "**Release 1.2.0 (2026-11-01).** `T5DR-Online-1.1.9.zip`\n")
            self.assertEqual(pf.readme_leftovers("1.2.0", d),
                             ["README.md: the release line names 1.1.9, not 1.2.0"])     # the zip name too


class DisplayPath(unittest.TestCase):
    def test_inside_the_repo(self):
        self.assertEqual(notes.display_path(os.path.join(notes.ROOT, "CHANGELOG.md")), "CHANGELOG.md")

    def test_other_drive_is_shown_whole(self):
        # os.path.relpath raises ValueError between two Windows drives. A CI runner has the
        # checkout on D: and the temp folder on C:, so --changelog <temp file> crashed there
        # (and only there) before display_path.
        other = os.path.join("X:" + os.sep, "tmp", "CHANGELOG.md")
        with mock.patch.object(notes.os.path, "relpath", side_effect=ValueError("path is on mount 'X:', start on mount 'D:'")):
            self.assertEqual(notes.display_path(other), "X:/tmp/CHANGELOG.md")


class ReleaseNotesCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cl = os.path.join(self.tmp.name, "CHANGELOG.md")
        put(self.cl, CHANGELOG)
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("GITHUB_")}

    def run_notes(self, *args):
        r = subprocess.run([PY, os.path.join(TOOLS, "release_notes.py"), "--changelog", self.cl, *args],
                           capture_output=True, text=True, env=self.env)
        return r.returncode, r.stdout + r.stderr

    def test_check(self):
        self.assertEqual(self.run_notes("--version", "0.1.0-preview", "--check")[0], 0)
        code, out = self.run_notes("--version", "0.3.0", "--check")
        self.assertNotEqual(code, 0)
        self.assertIn("## v0.3.0", out)                       # tells what heading to add
        self.assertNotEqual(self.run_notes("--version", "0.0.9", "--check")[0], 0)   # empty section
        self.assertEqual(self.run_notes("--version", "0.3.0", "--check", "--allow-missing")[0], 0)

    def test_full_notes(self):
        rj = os.path.join(self.tmp.name, "release.json")
        put(rj, json.dumps({"version": "0.1.0-preview", "llvm": "23.1.3", "python": "3.12.10",
                            "ps3recomp": "f17bcd3", "patches": ["0001-a.patch", "0002-b.patch"],
                            "code_id": "abcdef0123456789", "commit": "0123456789abcdef0123456789abcdef01234567"}))
        sums = os.path.join(self.tmp.name, "SHA256SUMS")
        put(sums, "ab" * 32 + "  T5DR-Online-0.1.0-preview.zip\n")
        out_md = os.path.join(self.tmp.name, "notes.md")
        code, out = self.run_notes("--version", "v0.1.0-preview", "--release-json", rj, "--sums", sums,
                                   "--repo", "owner/repo", "--out", out_md)
        self.assertEqual(code, 0, out)
        with open(out_md, encoding="utf-8") as f:
            md = f.read()
        self.assertTrue(md.startswith("First public test build."))
        self.assertIn("ab" * 32, md)
        self.assertIn("LLVM 23.1.3", md)
        self.assertIn("CPython 3.12.10", md)
        self.assertIn("+ 2 patches", md)
        self.assertIn("pre-release", md)
        self.assertIn("https://github.com/owner/repo/commit/0123456789abcdef0123456789abcdef01234567", md)
        self.assertIn("no part of the game", md)


class ZipDocs(unittest.TestCase):
    def test_docs_the_public_readmes_point_into_the_zip_ship(self):
        """tools/make_public_repo.py turns every Markdown link of README.md, README.de.md and TROUBLESHOOTING.md to
        a document that is not public into "docs\\NAME (in the release zip)": each of them must be in the zip
        (package_release.OUR_OPTIONAL_FILES)."""
        import re
        pub = load_tool("make_public_repo")
        root = os.path.dirname(TOOLS)
        linked = set()
        for rel in ("README.md", os.path.join("docs", "README.de.md"), os.path.join("docs", "TROUBLESHOOTING.md")):
            with open(os.path.join(root, rel), encoding="utf-8") as f:
                text = f.read()
            for target in re.findall(r"\]\(([^)\s]+)\)", text):
                if target.startswith(("http://", "https://", "#", "mailto:")):
                    continue
                name = target.split("#")[0].split("/")[-1]
                if name.endswith(".md") and name not in pub.FILES:
                    linked.add(name)
        shipped = {os.path.basename(f) for f in package.OUR_OPTIONAL_FILES}
        self.assertTrue({"TRAINING.md", "REPLAYS.md", "SPECTATE.md", "TOURNAMENTS.md", "WEAK_PC.md"} <= linked, linked)
        self.assertEqual(sorted(linked - shipped), [])


class Versions(unittest.TestCase):
    def test_accepted(self):
        for v, want in [("0.1.0", "0.1.0"), ("0.1.0-preview", "0.1.0-preview"), ("v0.2.0-rc.1", "0.2.0-rc.1"),
                        ("1.0.0-rc1", "1.0.0-rc1"), ("0.0.0-dryrun.17", "0.0.0-dryrun.17")]:
            self.assertEqual(package.parse_version(v), want)

    def test_rejected(self):
        for v in ["0.1", "0.1.0-", "0.1.0_x", "0.1.0-pre view", "x0.1.0", "0.1.0+build", "", "v"]:
            with self.assertRaises(SystemExit, msg=v):
                package.parse_version(v)


def tar_xz(path, entries):
    """entries: (name, kind, data_or_linkname); kind in file/dir/hardlink/symlink."""
    with tarfile.open(path, "w:xz") as tf:
        for name, kind, payload in entries:
            ti = tarfile.TarInfo(name)
            if kind == "file":
                ti.size = len(payload)
                tf.addfile(ti, io.BytesIO(payload))
                continue
            ti.type = {"dir": tarfile.DIRTYPE, "hardlink": tarfile.LNKTYPE, "symlink": tarfile.SYMTYPE}[kind]
            if kind != "dir":
                ti.linkname = payload
            tf.addfile(ti)


class FetchLlvmExtract(unittest.TestCase):
    TOP = "clang+llvm-0.0.0-x86_64-pc-windows-msvc"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dest = os.path.join(self.tmp.name, "llvm")
        os.makedirs(self.dest)

    def read(self, rel):
        with open(os.path.join(self.dest, *rel.split("/")), "rb") as f:
            return f.read()

    def test_wanted_parts_and_links(self):
        t = self.TOP
        arc = os.path.join(self.tmp.name, "a.tar.xz")
        tar_xz(arc, [
            (t, "dir", None),
            (f"{t}/LICENSE.TXT", "file", b"license"),
            (f"{t}/lib/libclang.lib", "file", b"big static lib"),     # not unpacked ...
            (f"{t}/bin/lld.exe", "file", b"lld"),
            (f"{t}/bin/clang-cl.exe", "hardlink", f"{t}/lib/libclang.lib"),   # ... unless a wanted link needs it
            (f"{t}/bin/lld-link.exe", "hardlink", f"{t}/bin/lld.exe"),
            (f"{t}/bin/ld.lld.exe", "symlink", "lld.exe"),
            (f"{t}/lib/clang/23/include/stddef.h", "file", b"/* stddef */"),
            (f"{t}/include/llvm/IR/Value.h", "file", b"skipped"),
        ])
        n = fetch.extract(arc, self.dest)
        self.assertEqual(n, 6)
        self.assertEqual(self.read("bin/lld-link.exe"), b"lld")
        self.assertEqual(self.read("bin/ld.lld.exe"), b"lld")
        self.assertEqual(self.read("bin/clang-cl.exe"), b"big static lib")   # second pass
        self.assertEqual(self.read("lib/clang/23/include/stddef.h"), b"/* stddef */")
        self.assertEqual(self.read("LICENSE.TXT"), b"license")
        self.assertFalse(os.path.exists(os.path.join(self.dest, "include")))
        self.assertFalse(os.path.exists(os.path.join(self.dest, "lib", "libclang.lib")))

    def test_unsafe_path_refused(self):
        arc = os.path.join(self.tmp.name, "evil.tar.xz")
        tar_xz(arc, [(f"{self.TOP}/bin/../../../evil.exe", "file", b"x")])
        with self.assertRaises(SystemExit):
            fetch.extract(arc, self.dest)
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, "evil.exe")))

    def test_pin_is_consistent(self):
        self.assertIn(fetch.LLVM_VERSION, fetch.LLVM_URL)
        self.assertTrue(fetch.LLVM_URL.endswith("/" + fetch.LLVM_ASSET))
        self.assertRegex(fetch.LLVM_SHA256, r"^[0-9a-f]{64}$")


@unittest.skipUnless(os.name == "nt", "PE files and System32 exist on Windows only")
class PeImports(unittest.TestCase):
    def test_python_exe(self):
        smoke = load_tool("smoke_release")
        dlls = smoke.pe_imports(sys.executable)
        self.assertIn("kernel32.dll", dlls)
        self.assertTrue(any(d.startswith("python3") for d in dlls), dlls)
        self.assertTrue(smoke.windows_dll("kernel32.dll"))
        self.assertTrue(smoke.windows_dll("api-ms-win-crt-runtime-l1-1-0.dll"))
        self.assertFalse(smoke.windows_dll("vcruntime140.dll"))
        self.assertFalse(smoke.windows_dll("msvcp140.dll"))


if __name__ == "__main__":
    unittest.main()
