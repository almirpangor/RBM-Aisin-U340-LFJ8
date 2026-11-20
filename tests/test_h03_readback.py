from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from tools.check_h03_readback import compare
from tools.inspect_lfj8_tcm import IDENTITY_OFFSET, IMAGE_SIZE


def expected_image():
    image = bytearray(b"\xff" * IMAGE_SIZE)
    identity = b"LFJ8\x0018\x009E1\x00C\x00LFJ8TC000LFXA0A0\x00SW-LFJ8TC000.HEX\x00"
    image[IDENTITY_OFFSET:IDENTITY_OFFSET + len(identity)] = identity
    return bytes(image)


class H03ReadbackTests(unittest.TestCase):
    def setUp(self):
        self.expected = expected_image()

    def test_full_image_matches_even_with_reordered_overlapping_reads(self):
        report = compare(self.expected, [(0x8000, self.expected[0x8000:]),
                                         (0, self.expected[:0x9000])])
        self.assertEqual(report["status"], "MATCH")
        self.assertEqual(report["covered_bytes"], IMAGE_SIZE)
        self.assertEqual(report["unread_ranges"], [])
        self.assertEqual(report["expected"]["sha256"], sha256(self.expected).hexdigest())
        self.assertEqual(report["reads"][0]["sha256"], sha256(self.expected[0x8000:]).hexdigest())

    def test_gaps_include_boot_middle_and_tail(self):
        report = compare(self.expected, [(0x8000, self.expected[0x8000:0x9000]),
                                         (0xA000, self.expected[0xA000:0xB000])])
        self.assertEqual(report["status"], "PARTIAL_MATCH")
        self.assertEqual(report["covered_bytes"], 0x2000)
        self.assertEqual(report["unread_ranges"], [
            {"start": "0x000000", "end_exclusive": "0x008000"},
            {"start": "0x009000", "end_exclusive": "0x00A000"},
            {"start": "0x00B000", "end_exclusive": "0x080000"},
        ])

    def test_conflicting_overlap_cannot_be_hidden_by_a_matching_read(self):
        report = compare(self.expected, [(0x8000, b"\x00\xff\x42"),
                                         (0x8002, b"\x42"), (0, self.expected)])
        self.assertEqual(report["status"], "MISMATCH")
        self.assertEqual(report["mismatched_bytes"], 2)
        self.assertEqual(report["reads"][0]["first_mismatch"],
                         {"address": "0x008000", "expected": 255, "observed": 0})
        self.assertEqual(report["reads"][0]["last_mismatch_address"], "0x008002")

    def test_invalid_geometry_is_rejected(self):
        for reads in ([], [(-1, b"x")], [(0, b"")], [(IMAGE_SIZE, b"x")], [(IMAGE_SIZE - 1, b"xx")]):
            with self.subTest(reads=reads), self.assertRaises(ValueError):
                compare(self.expected, reads)
        for expected in (self.expected[:-1], bytes(IMAGE_SIZE)):
            with self.subTest(size=len(expected)), self.assertRaisesRegex(ValueError, "9E1C"):
                compare(expected, [(0, b"x")])

    def test_cli_status_codes(self):
        script = Path(__file__).resolve().parents[1] / "tools/check_h03_readback.py"
        with TemporaryDirectory() as directory:
            expected = Path(directory) / "expected.bin"
            observed = Path(directory) / "observed.bin"
            expected.write_bytes(self.expected)
            command = [sys.executable, "-B", str(script), "--expected", str(expected)]
            for data, code, status in (
                (self.expected, 0, "MATCH"), (self.expected[:1], 3, "PARTIAL_MATCH"), (b"x", 1, "MISMATCH"),
            ):
                observed.write_bytes(data)
                result = subprocess.run([*command, "--read", "0x0", str(observed)],
                                        capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, code, result.stderr)
                self.assertEqual(json.loads(result.stdout)["status"], status)
            result = subprocess.run([*command, "--read", "0x80000", str(observed)],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 2)
            self.assertIn("outside the image", result.stderr)


if __name__ == "__main__":
    unittest.main()
