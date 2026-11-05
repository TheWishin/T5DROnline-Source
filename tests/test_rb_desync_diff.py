"""Diagnostic dumps must be decoded against the recorded edition layout."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest

from helpers import ROOT

spec = importlib.util.spec_from_file_location("rb_desync_diff", Path(ROOT) / "tools/rb_desync_diff.py")
diff = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diff)


class DesyncDiff(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def dump(self, role, frame=224, value=1, actual=0x1000, canonical=0x1000, dynamic=False):
        folder = self.root / role
        folder.mkdir(exist_ok=True)
        path = folder / f"np_desync_f{frame}.bin"
        path.write_bytes(value.to_bytes(4, "big"))
        region = dict(offset=0, address=actual, length=4, us_address=canonical, us_length=4)
        if dynamic:
            region.update(dynamic=True, root_us=0x1008EBA0, object_offset=0x18)
        path.with_suffix(".regions.json").write_text(json.dumps(dict(schema=1, bytes=4, ranges=[region], mixed=True)))
        return path

    def test_mapped_addresses_and_dynamic_root_are_printed(self):
        a, b = self.dump("a", actual=0x2000, dynamic=True), self.dump("b", value=2, actual=0x3000, dynamic=True)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            diff.main([str(a.parent), str(b.parent)])
        self.assertIn("*1008EBA0+18[A=00002000,B=00003000]:00000001/00000002", output.getvalue())

    def test_unequal_length_is_never_truncated(self):
        a, b = self.dump("a"), self.dump("b")
        b.write_bytes(b"\x00" * 8)
        with self.assertRaisesRegex(ValueError, "refusing truncation"):
            diff.compared_dump(a, b)

    def test_equal_lengths_with_different_canonical_regions_are_rejected(self):
        a, b = self.dump("a"), self.dump("b", canonical=0x2000)
        with self.assertRaisesRegex(ValueError, "different hash layouts"):
            diff.compared_dump(a, b)

    def test_raw_legacy_layout_requires_opt_in_and_exact_size(self):
        a, b = self.dump("a"), self.dump("b")
        for p in (a, b):
            p.with_suffix(".regions.json").unlink()
        with self.assertRaisesRegex(ValueError, "--legacy-us"):
            diff.compared_dump(a, b)
        with self.assertRaisesRegex(ValueError, "expected"):
            diff.compared_dump(a, b, legacy_us=True)
        for p in (a, b):
            p.write_bytes(bytes(sum(n for _, n in diff.REGIONS)))
        diff.compared_dump(a, b, legacy_us=True)

    def test_numeric_frame_order_and_coverage_validation(self):
        names = ["np_desync_f100.bin", "np_desync_f20.bin", "np_desync_f3.bin"]
        self.assertEqual(sorted(names, key=diff.frame_order), [names[2], names[1], names[0]])
        a = self.dump("a")
        meta = json.loads(a.with_suffix(".regions.json").read_text())
        meta["ranges"][0]["offset"] = 4
        a.with_suffix(".regions.json").write_text(json.dumps(meta))
        with self.assertRaisesRegex(ValueError, "noncontiguous"):
            diff.layout(a, 4)

    def test_edition_specific_struct_length_is_rejected(self):
        a = self.dump("a")
        meta = json.loads(a.with_suffix(".regions.json").read_text())
        meta["ranges"][0]["us_length"] = 8
        a.with_suffix(".regions.json").write_text(json.dumps(meta))
        with self.assertRaisesRegex(ValueError, "per-field mapping required"):
            diff.layout(a, 4)


if __name__ == "__main__":
    unittest.main()
