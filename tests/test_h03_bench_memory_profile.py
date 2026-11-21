from hashlib import sha256
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "targets/lfj8"))
import lfj8_h03_bench_memory_profile as bench
from lfj8_h03_ram_placement import STACK_STARTUP


class BenchMemoryProfileTest(unittest.TestCase):
    def setUp(self):
        self.rom = bytearray(0x80000)
        for addr, words in STACK_STARTUP.items():
            self.rom[addr:addr + len(words)] = words
        site = bench.DIAGNOSTIC_LIMIT_SITE
        self.rom[site:site + 4] = bench.DIAGNOSTIC_LIMIT_WORD.to_bytes(4, "big")
        self.storage = {
            "blocks": {
                "control": {"address": 0x806B40, "end_exclusive": 0x806FB0},
                "communication": {"address": 0x808E40, "end_exclusive": 0x8090A0},
                "workspace": {"address": 0x8090A0, "end_exclusive": 0x8094D8},
            },
            "fields": {
                "control/application": {"offset": 0x380, "bytes": 8, "alignment": 4},
                "control/clock_qualified": {"offset": 0x388, "bytes": 1, "alignment": 1},
            },
        }

    def test_stock_identity_and_guard_words_required(self):
        with self.assertRaisesRegex(ValueError, "pinned stock H03"):
            bench.pinned_boot_words(self.rom)
        self.rom[0x3001C] = 1
        with patch.object(bench, "IMAGE_HASH", sha256(self.rom).hexdigest()):
            with self.assertRaisesRegex(ValueError, "service flags"):
                bench.pinned_boot_words(self.rom)
        self.rom[0x3001C] = 0
        self.rom[bench.DIAGNOSTIC_LIMIT_SITE + 3] = 0
        with patch.object(bench, "IMAGE_HASH", sha256(self.rom).hexdigest()):
            with self.assertRaisesRegex(ValueError, "diagnostic RAM limit"):
                bench.pinned_boot_words(self.rom)

    def test_uses_absolute_bounds_and_covers_reserved_stack(self):
        with TemporaryDirectory() as directory, patch.object(bench, "IMAGE_HASH", sha256(self.rom).hexdigest()):
            profile = bench.prepare(self.rom, self.storage, 0x806FB0, Path(directory))
            self.assertEqual(set(profile["symbols"]), {
                "rbm_h03_ram_spi_first", "rbm_h03_ram_spi_reserve",
                "rbm_h03_ram_psw_first", "rbm_h03_ram_psw_reserve",
            })
            self.assertEqual(profile["early_bindings"]["rbm_h03_application"], 0x806EC0)
            self.assertEqual(profile["early_bindings"]["rbm_h03_tml0_1mhz_qualified"], 0x806EC8)
            self.assertIn((bench.SPI_FIRST, bench.RAM_LIMIT), profile["policy_ranges"])
            self.assertIn("0x003da4u, 0xe2809efcu", profile["header"].read_text())
            self.assertEqual(profile["spi_top"] - bench.SPI_FIRST, 2044)
            self.assertEqual(profile["psw_cursor"] - bench.PSW_FIRST, 156)

    def test_refuses_stack_overlap_in_inventory_or_actual_link(self):
        allowed = {"section": ".bss.sample", "flags": 3, "address": bench.SPI_FIRST - 4, "bytes": 4}
        bench.verify_ram_placements([allowed])
        with self.assertRaisesRegex(ValueError, "overlaps the stack reservation"):
            bench.verify_ram_placements([dict(allowed, bytes=8)])
        with TemporaryDirectory() as directory, patch.object(bench, "IMAGE_HASH", sha256(self.rom).hexdigest()):
            with self.assertRaisesRegex(ValueError, "stack reservation"):
                bench.prepare(self.rom, self.storage, bench.SPI_FIRST, Path(directory))
            self.storage["blocks"]["workspace"]["end_exclusive"] = bench.SPI_FIRST + 4
            with self.assertRaisesRegex(ValueError, "overlapping RAM interval"):
                bench.prepare(self.rom, self.storage, 0x806FB0, Path(directory))


if __name__ == "__main__":
    unittest.main()
