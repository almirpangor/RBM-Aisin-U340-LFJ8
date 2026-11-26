"""A full upper window may use verified tables, never code, in lower spare Flash."""
import sys
import struct
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "targets/lfj8")]
from check_h03_image_layout import pack_resident_constants, readonly_objects
from lfj8_h03_layout import PlacementError, Window, pack


def section(name, size, flags=2, alignment=4):
    return dict(name=name, size=size, flags=flags, alignment=alignment, type=1)


class ResidentConstantsTests(unittest.TestCase):
    low = Window("resident", 0x6000, 0x6040)
    high = (Window("upper", 0x10000, 0x10040),)

    def test_relocation_metadata_excludes_pointer_tables_in_both_elf_formats(self):
        for relocation_type in (4, 9):
            with self.subTest(relocation_type=relocation_type), TemporaryDirectory() as directory:
                data = bytearray(52 + 5 * 40)
                struct.pack_into(">I", data, 32, 52)
                struct.pack_into(">HH", data, 46, 40, 5)
                struct.pack_into(">10I", data, 52 + 4 * 40,
                                 0, relocation_type, 0, 0, 0, 8, 0, 2, 4, 8)
                path = Path(directory) / "retained.o"
                path.write_bytes(data)
                sections = [dict(index=i, data=b"abcd", **section(name, 4, flags)) for i, name, flags in (
                    (1, ".rodata.values", 2), (2, ".rodata.pointers", 2),
                    (3, ".rodata.executable", 6))]
                approved = readonly_objects({"sections": sections}, path)
                self.assertEqual(set(approved), {".rodata.values"})

    def test_overflow_moves_only_approved_table_and_preserves_resident_code(self):
        resident = [section(".text.irq", 20, 6)]
        upper = [section(".text.app", 48, 6), section(".rodata.table", 32, alignment=16)]
        with self.assertRaises(PlacementError):
            pack(upper, self.high)
        result, moved = pack_resident_constants(resident, upper, self.high, {".rodata.table"}, self.low)
        self.assertEqual(moved, [".rodata.table"])
        by_name = {p["section"]: p for p in result}
        self.assertEqual(by_name[".text.irq"], pack(resident, (self.low,))[0])
        self.assertEqual(by_name[".rodata.table"]["address"], 0x6020)
        self.assertEqual(by_name[".text.app"]["window"], "upper")
        self.assertEqual(sum(p["bytes"] for p in result), 100)
        self.assertEqual((result, moved), pack_resident_constants(
            resident, list(reversed(upper)), self.high, {".rodata.table"}, self.low))

    def test_sufficient_upper_capacity_keeps_original_plan(self):
        resident = [section(".text.irq", 8, 6)]
        upper = [section(".rodata.table", 32)]
        plan, moved = pack_resident_constants(resident, upper, self.high, {".rodata.table"}, self.low)
        self.assertEqual(plan, pack(resident, (self.low,)) + pack(upper, self.high))
        self.assertEqual(moved, [])

    def test_unapproved_code_or_writable_data_cannot_use_spare(self):
        for name, flags, eligible in ((".rodata.table", 2, set()),
                                      (".text.app", 6, {".text.app"}),
                                      (".data.state", 3, {".data.state"})):
            with self.subTest(name=name, flags=flags):
                with self.assertRaises(PlacementError):
                    pack_resident_constants([], [section(".text.fixed", 48, 6),
                                                section(name, 32, flags)], self.high, eligible, self.low)

    def test_full_resident_window_and_insufficient_total_capacity_fail(self):
        for resident_size in (64, 48):
            with self.assertRaises(PlacementError):
                pack_resident_constants([section(".text.irq", resident_size, 6)],
                    [section(".text.app", 64, 6), section(".rodata.table", 32)],
                    self.high, {".rodata.table"}, self.low)

    def test_oversized_table_does_not_prevent_using_smaller_one(self):
        upper = [section(".rodata.big", 48), section(".rodata.small", 32)]
        plan, moved = pack_resident_constants([section(".text.irq", 32, 6)], upper,
                    self.high, {s["name"] for s in upper}, self.low)
        self.assertEqual(moved, [".rodata.small"])
        self.assertEqual(sum(p["bytes"] for p in plan), 112)


if __name__ == "__main__":
    unittest.main()
