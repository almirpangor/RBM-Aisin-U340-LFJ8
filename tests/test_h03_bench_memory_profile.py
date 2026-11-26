from hashlib import sha256
from copy import deepcopy
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

    def test_prepares_real_absolute_link_inputs_without_ram_objects(self):
        with TemporaryDirectory() as directory, patch.object(bench, "IMAGE_HASH", sha256(self.rom).hexdigest()):
            profile = bench.prepare(self.rom, self.storage, 0x806FB0, Path(directory))
            assembly = profile["symbol_source"].read_text(encoding="ascii")
            script = profile["linker_fragment"].read_text(encoding="ascii")
            for name in ("header", "symbol_source", "linker_fragment"):
                self.assertNotIn(b"\r", profile[name].read_bytes())
            for name, value in profile["symbols"].items():
                self.assertIn(f".globl {name}\n.equ {name}, {value:#x}\n", assembly)
                self.assertIn(f"{name} = ABSOLUTE({value:#x});", script)
            self.assertNotIn(".space", assembly)
            self.assertNotIn(".long", assembly)
            self.assertNotIn("SECTIONS {", script)
            self.assertIn("H03 SPI reserve exceeds its region", script)
            self.assertIn("H03 PSW reserve exceeds its region", script)

    def test_native_options_are_limited_to_actual_memory_consumers(self):
        with TemporaryDirectory(prefix="h03 memory ") as directory, patch.object(bench, "IMAGE_HASH", sha256(self.rom).hexdigest()):
            profile = bench.prepare(self.rom, self.storage, 0x806FB0, Path(directory))
            for source in bench.NATIVE_SOURCES:
                flags = bench.native_compile_flags(profile, Path("targets/lfj8") / source)
                self.assertIn("-D" + bench.NATIVE_DEFINE, flags)
                self.assertEqual(flags[flags.index("-I") + 1], directory)
                self.assertIn('-DRBM_H03_BENCH_MEMORY_HEADER="h03_bench_memory_profile.h"', flags)
            self.assertEqual(bench.native_compile_flags(profile, "lfj8_h03_torque.c"), ())
            self.assertEqual(bench.native_compile_flags(profile, profile["symbol_source"]), ())

    def test_rejects_bad_identity_before_emitting_link_inputs(self):
        with TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "pinned stock H03"):
                bench.prepare(self.rom, self.storage, 0x806FB0, Path(directory))
            self.assertEqual(list(Path(directory).iterdir()), [])

    def linked_elf(self, profile):
        symbols = {name: {"section": 0xFFF1, "address": value}
                   for name, value in {**profile["symbols"], **profile["early_bindings"]}.items()}
        symbols.update({
            "rbm_h03_boot_writers_owned": {"section": 1, "address": 0x20000},
            "rbm_h03_early_irq_gate": {"section": 2, "address": 0x7000},
            "rbm_h03_early_irq_bench_latches": {"section": 2, "address": 0x700C},
        })
        return {"symbols": symbols, "sections": [
            {"name": "", "flags": 0, "address": 0, "size": 0},
            {"name": ".boot_owner", "flags": 6, "address": 0x20000, "size": 0x80},
            {"name": ".early", "flags": 6, "address": 0x7000, "size": 0x30},
            {"name": ".bss", "flags": 3, "address": 0x806B40, "size": 0x470},
        ]}

    def test_verifies_final_symbols_early_opt_in_and_actual_ram_placements(self):
        with TemporaryDirectory() as directory, patch.object(bench, "IMAGE_HASH", sha256(self.rom).hexdigest()):
            profile = bench.prepare(self.rom, self.storage, 0x806FB0, Path(directory))
            elf = self.linked_elf(profile)
            result = bench.verify_linked_profile(profile, elf)
            self.assertEqual(result["early_latch_address"], 0x700C)
            for name in ("symbols", "early_bindings"):
                changed_profile = deepcopy(profile)
                changed_profile[name] = {}
                with self.assertRaisesRegex(ValueError, "Incomplete or changed"):
                    bench.verify_linked_profile(changed_profile, elf)
            for name in (*profile["symbols"], *profile["early_bindings"]):
                for field, value in (("section", 1), ("address", elf["symbols"][name]["address"] + 4)):
                    with self.subTest(symbol=name, field=field):
                        changed = deepcopy(elf)
                        changed["symbols"][name][field] = value
                        with self.assertRaisesRegex(ValueError, "ABS symbol differs"):
                            bench.verify_linked_profile(profile, changed)
            changed = deepcopy(elf)
            changed["symbols"]["rbm_h03_early_irq_bench_latches"]["address"] += 4
            with self.assertRaisesRegex(ValueError, "bench latch stores"):
                bench.verify_linked_profile(profile, changed)
            changed = deepcopy(elf)
            changed["symbols"]["rbm_h03_boot_writers_owned"]["section"] = 0
            with self.assertRaisesRegex(ValueError, "Missing executable"):
                bench.verify_linked_profile(profile, changed)
            changed = deepcopy(elf)
            changed["sections"][3].update(address=bench.SPI_FIRST, size=4)
            with self.assertRaisesRegex(ValueError, "overlaps the stack reservation"):
                bench.verify_linked_profile(profile, changed)


if __name__ == "__main__":
    unittest.main()
