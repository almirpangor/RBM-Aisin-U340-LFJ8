"""Check the indexed Chery service 0x17 table against the S03 extraction."""

import csv
import hashlib
import json
import os
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
TABLE = ROOT / "docs/ta2005-diagnostic-code-table.csv"
IMPLEMENTATION = ROOT / "diagnostics/chery_dtc.c"
INDEX_COUNT = 96
CODE_OFFSET = 0xEBE2
STATUS_OFFSET = 0xECA2


class CheryDtcTableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with TABLE.open(encoding="utf-8", newline="") as source:
            cls.rows = [
                {column: int(value, 16) for column, value in row.items()}
                for row in csv.DictReader(source)
            ]

    def test_service_table_matches_extraction_in_index_order(self):
        source = IMPLEMENTATION.read_text(encoding="utf-8")
        table = re.search(r"\bdtc_table\s*\[[^]]+\]\s*=\s*\{(.*?)\};", source, re.S)
        self.assertIsNotNone(table, "Missing dtc_table initializer")
        entry = re.compile(r"\{\s*(0x[0-9a-f]+)u\s*,\s*(0x[0-9a-f]+)u\s*\}\s*,", re.I)
        body = table.group(1)
        self.assertFalse(entry.sub("", body).strip(), "Unrecognized dtc_table entry")
        actual = [tuple(int(field, 16) for field in match) for match in entry.findall(body)]
        self.assertEqual(len(self.rows), INDEX_COUNT)
        self.assertEqual(len(actual), INDEX_COUNT)

        for index, (row, (word, inactive)) in enumerate(zip(self.rows, actual)):
            with self.subTest(index=f"0x{index:02X}"):
                self.assertEqual(row["internal_index"], index)
                self.assertEqual(row["code_word_file_offset"], CODE_OFFSET + 2 * index)
                self.assertEqual(row["service_17_mode_90_word"], word)
                self.assertEqual(row["snapshot_masked_word"], word & 0x0FFF)
                self.assertEqual(row["service_17_status_current_bit_clear"], inactive)
                self.assertEqual(inactive & 0x60, 0x40)
                self.assertEqual(row["service_17_status_current_bit_set"], inactive | 0x20)

    @unittest.skipUnless(os.environ.get("RBM_S03"), "Set RBM_S03 to verify the donor image")
    def test_extraction_matches_pinned_s03_image(self):
        manifest = json.loads((ROOT / "data/sources.json").read_text(encoding="utf-8"))
        s03 = next(item for item in manifest["firmware"] if item["id"] == "S03")
        image = Path(os.environ["RBM_S03"]).read_bytes()
        self.assertEqual(len(image), s03["bytes"])
        self.assertEqual(hashlib.sha256(image).hexdigest(), s03["sha256"])
        self.assertEqual(len(self.rows), INDEX_COUNT)

        for index, row in enumerate(self.rows):
            with self.subTest(index=f"0x{index:02X}"):
                offset = CODE_OFFSET + 2 * index
                word = int.from_bytes(image[offset:offset + 2], "little")
                status = image[STATUS_OFFSET + index]
                self.assertEqual(row["service_17_mode_90_word"], word)
                self.assertEqual(row["service_17_status_current_bit_clear"], status | 0x40)


if __name__ == "__main__":
    unittest.main()
