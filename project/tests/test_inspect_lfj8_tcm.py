import hashlib
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from tools.inspect_lfj8_tcm import H03_PART_NUMBER, IDENTITY_OFFSET, IMAGE_SIZE, check_h03, inspect


def image_for(revision=b"C"):
    image = bytearray(IMAGE_SIZE)
    metadata = b"LFJ8\x0018\x009E1\x00" + revision + b"\x00LFJ8TC000LFXA0A0\x00SW-LFJ8TC000.HEX\x00"
    image[IDENTITY_OFFSET:IDENTITY_OFFSET + len(metadata)] = metadata
    return bytes(image)


class H03IdentityTests(unittest.TestCase):
    def test_strict_check_requires_identity_length_and_digest(self):
        image = image_for()
        registry = {"supporting_materials": [
            {"id": "H03", "bytes": len(image), "sha256": hashlib.sha256(image).hexdigest()},
        ]}
        self.assertTrue(check_h03(inspect(image, H03_PART_NUMBER), registry))
        changed = bytes((1,)) + image[1:]
        record = inspect(changed, H03_PART_NUMBER)
        self.assertTrue(record["matches_expected_id"])
        self.assertFalse(check_h03(record, registry))
        self.assertFalse(record["matches_h03"])
        self.assertFalse(check_h03(inspect(image[:-1], H03_PART_NUMBER), registry))
        wrong = image_for(b"B")
        registry["supporting_materials"][0]["sha256"] = hashlib.sha256(wrong).hexdigest()
        self.assertFalse(check_h03(inspect(wrong, "LFJ8-18-9E1B"), registry))

    def test_default_and_strict_cli_exit_codes(self):
        script = Path(__file__).resolve().parents[1] / "tools/inspect_lfj8_tcm.py"
        with TemporaryDirectory() as temp:
            sample = Path(temp) / "LFJ8-T-D.bin"
            sample.write_bytes(image_for())
            for flags, expected in (([], 0), (["--require-h03"], 1),
                                    (["--require-h03", "--expect", "LFJ8-18-9E1B"], 2)):
                with self.subTest(flags=flags):
                    result = subprocess.run(
                        [sys.executable, "-B", str(script), str(sample), *flags],
                        capture_output=True, text=True,
                    )
                    self.assertEqual(result.returncode, expected, result.stderr)
                    if expected == 1:
                        record = json.loads(result.stdout)
                        self.assertTrue(record["matches_expected_id"])
                        self.assertFalse(record["matches_h03"])
