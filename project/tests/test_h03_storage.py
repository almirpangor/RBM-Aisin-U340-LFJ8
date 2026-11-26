"""Reject malformed target layout tables and memory-plan overflows."""
from pathlib import Path
import struct
import sys
import unittest

TARGET = Path(__file__).resolve().parents[1] / "targets/lfj8"
sys.path.insert(0, str(TARGET))
try:
    import check_h03_storage as storage
finally:
    sys.path.pop(0)


def packed(rows, pointer=4):
    data = struct.pack(">4I", 0x52424D31, 1, pointer, len(rows))
    for name, offset, size, alignment in rows:
        data += struct.pack(">32s3I", name.encode("ascii"), offset, size, alignment)
    return data


def rows():
    return [
        ("control", 0, 12, 4), ("control/first", 0, 4, 4), ("control/second", 4, 8, 4),
        ("communication", 0, 8, 4), ("communication/only", 0, 8, 4),
        ("workspace", 0, 16, 8), ("workspace/only", 0, 16, 8),
    ]


class H03StorageTests(unittest.TestCase):
    def test_layout_uses_target_alignment_and_disjoint_ranges(self):
        measured = storage.decode_layout(packed(rows()))
        plan = storage.address_plan(measured)
        self.assertEqual(plan["control"]["address"], 0x806B40)
        self.assertEqual(plan["communication"]["address"], 0x808E40)
        self.assertEqual(plan["workspace"]["address"], 0x808E48)
        self.assertEqual(plan["workspace"]["end_exclusive"], 0x808E58)

    def test_wrong_abi_endian_and_truncation(self):
        raw = packed(rows())
        for bad in [packed(rows(), pointer=8), raw[:12], raw[:-1], raw + b"\0",
                    struct.pack("<4I", 0x52424D31, 1, 4, len(rows())) + raw[16:]]:
            with self.subTest(length=len(bad)), self.assertRaises(ValueError):
                storage.decode_layout(bad)

    def test_duplicate_missing_and_unknown_groups(self):
        variants = [rows() + [rows()[0]], rows()[1:], rows() + [("unknown", 0, 4, 4)],
                    [row for row in rows() if row[0] != "workspace/only"]]
        for variant in variants:
            with self.subTest(rows=variant), self.assertRaises(ValueError):
                storage.decode_layout(packed(variant))

    def test_field_overlap_bounds_and_alignment(self):
        for replacement in [("control/second", 0, 8, 4),
                            ("control/second", 8, 8, 4),
                            ("control/second", 3, 8, 4),
                            ("control/second", 4, 8, 3),
                            ("control/second", 4, 0, 4),
                            ("control/second", 8, 4, 8)]:
            variant = rows()
            variant[2] = replacement
            with self.subTest(replacement=replacement), self.assertRaises(ValueError):
                storage.decode_layout(packed(variant))

    def test_primary_and_secondary_overflow_are_refused(self):
        for group, size in [("control", 1217), ("communication", 0x1000), ("workspace", 0x1000)]:
            measured = storage.decode_layout(packed(rows()))
            measured[group]["bytes"] = size
            with self.subTest(group=group), self.assertRaises(ValueError):
                storage.address_plan(measured)

    def test_no_implicit_overlay_when_primary_has_spare_space(self):
        measured = storage.decode_layout(packed(rows()))
        measured["control"]["bytes"] = 1048
        measured["communication"]["bytes"] = 492
        measured["workspace"]["bytes"] = 784
        measured["workspace"]["alignment"] = 4
        plan = storage.address_plan(measured)
        self.assertEqual(plan["workspace"]["end_exclusive"], 0x80933C)
        self.assertLessEqual(plan["communication"]["end_exclusive"], plan["workspace"]["address"])
        self.assertEqual(sum(block["bytes"] for block in plan.values()), 2324)


if __name__ == "__main__":
    unittest.main()
