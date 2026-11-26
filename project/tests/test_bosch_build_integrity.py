from types import SimpleNamespace
import unittest

from targets.bosch.build import checksum_records, section_offsets


class BoschBuildIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.records = [
            {"file_offset": offset}
            for offset in (*range(0xA7800, 0xA7B00, 16), 0xA83CC, 0xA83DC, 0xA83EC)
        ]

    def check_records(self, records):
        return checksum_records(SimpleNamespace(checks=lambda _: records), b"")

    def test_complete_table_is_accepted_without_requiring_order(self):
        records = self.records[::-1]
        self.assertIs(self.check_records(records), records)

    def test_empty_or_partial_table_is_rejected(self):
        for records in ([], self.records[1:]):
            with self.subTest(records=len(records)):
                with self.assertRaisesRegex(ValueError, "checksum table"):
                    self.check_records(records)

    def test_duplicate_or_unexpected_offset_is_rejected(self):
        for replacement in (self.records[0], {"file_offset": 0xA83FC}):
            with self.subTest(replacement=replacement):
                with self.assertRaisesRegex(ValueError, "checksum table"):
                    self.check_records(self.records[:-1] + [replacement])


class BoschSectionLayoutTests(unittest.TestCase):
    @staticmethod
    def offset(address):
        if 0 <= address < 0x8000:
            return address
        if 0x18000 <= address < 0xe0000:
            return address - 0x10000
        raise ValueError("Unmapped flash")

    def place(self, *sections, image_size=0xd0000):
        return section_offsets(image_size, self.offset, sections, slice(0x70000, 0x70004))

    def test_adjacent_sections_are_accepted_in_input_order(self):
        self.assertEqual(self.place(("second", 0x66002, b"ab"), ("first", 0x66000, b"cd")),
                         [0x56002, 0x56000])

    def test_overlapping_sections_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "transmitter section overlaps receiver"):
            self.place(("receiver", 0x66000, b"abcd"), ("transmitter", 0x66003, b"ef"))

    def test_native_torque_code_and_full_checksum_records_are_reserved(self):
        for address, protected in ((0x80003, "native torque code"),
                                   (0xb7800, "E4M3 checksum record"),
                                   (0xb83fb, "E4M3 checksum record")):
            with self.subTest(address=hex(address)):
                with self.assertRaisesRegex(ValueError, f"patch section overlaps {protected}"):
                    self.place(("patch", address, b"ab"))

    def test_invalid_lengths_and_discontinuous_ranges_are_rejected(self):
        for address, code, image_size, message in (
            (0x66000, b"", 0xd0000, "empty"),
            (0xdffff, b"ab", 0xd0000, "outside mapped flash"),
            (0x7fff, bytes(0x10002), 0xd0000, "outside contiguous image bytes"),
            (0x66000, b"ab", 0x56001, "outside contiguous image bytes"),
        ):
            with self.subTest(address=hex(address), bytes=len(code)):
                with self.assertRaisesRegex(ValueError, message):
                    self.place(("patch", address, code), image_size=image_size)
