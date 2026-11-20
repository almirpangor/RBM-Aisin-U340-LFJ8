from types import SimpleNamespace
import unittest

from targets.bosch.build import checksum_records


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
