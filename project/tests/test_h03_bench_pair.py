"""Artifact publication checks; the pinned-image composer has its own tests."""
from hashlib import sha256
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import build_h03_bench_pair as builder


class CandidateImagesTests(unittest.TestCase):
    def run_candidate(self, folder, *, symbols=None, compose_error=None, ecu=None):
        base, elf, layout = [folder / name for name in ("base.bin", "linked.elf", "layout.json")]
        base.write_bytes(b"unit-test base, never a delivered firmware")
        elf.write_bytes(b"unit-test executable metadata")
        layout.write_text('{}', encoding='utf-8')
        image = b"unit-test composed bytes"
        metadata = {"status": "UNQUALIFIED_LINKED_IMAGE", "bench_pair_ready": False,
                    "sha256": sha256(image).hexdigest(), "bytes": len(image)}
        with patch.object(builder.h03_image, "read_elf", return_value={"symbols": symbols or {}}):
            with patch.object(builder.h03_image, "compose", return_value=(image, metadata),
                              side_effect=compose_error):
                result = builder.compose_images(base, elf, layout, None, folder / 'output',
                                                source_commit='a' * 40, ecu=ecu)
        return result, image

    def test_publishes_exact_bytes_and_unqualified_status(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            result, image = self.run_candidate(folder)
            self.assertEqual((folder / 'output' / result['tcm']['file']).read_bytes(), image)
            saved = json.loads((folder / 'output/manifest.json').read_text(encoding='utf-8'))
            self.assertIs(saved['bench_pair_ready'], False)
            self.assertEqual(saved['status'], 'UNQUALIFIED_LINKED_IMAGES')
            self.assertIn(sha256(image).hexdigest(), (folder / 'output/SHA256SUMS.txt').read_text())
            self.assertTrue((folder / 'output/NOT_FOR_FLASHING.txt').is_file())

    def test_rejected_composition_publishes_nothing(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            with self.assertRaisesRegex(ValueError, 'unresolved'):
                self.run_candidate(folder, compose_error=ValueError('unresolved binding'))
            self.assertFalse((folder / 'output').exists())

    def test_fixture_image_is_not_serialized(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            with self.assertRaisesRegex(ValueError, 'test providers'):
                self.run_candidate(folder, symbols={'fixture_engine_context': {}})
            self.assertFalse((folder / 'output').exists())

    def test_existing_output_and_input_files_are_preserved(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / 'output').mkdir()
            (folder / 'output/existing.bin').write_bytes(b'preserve')
            with self.assertRaisesRegex(ValueError, 'new output directory'):
                self.run_candidate(folder)
            self.assertEqual((folder / 'output/existing.bin').read_bytes(), b'preserve')

    def test_invalid_ecu_never_leaves_a_partial_tcm(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            ecu = folder / 'ecu.bin'
            ecu.write_bytes(b'not a full Bosch image')
            with self.assertRaisesRegex(ValueError, 'full Bosch'):
                self.run_candidate(folder, ecu=ecu)
            self.assertFalse((folder / 'output').exists())


if __name__ == '__main__':
    unittest.main()
