from hashlib import sha256
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "targets/lfj8"))
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

    def test_native_inputs_with_exact_h03_and_fresh_typed_storage(self):
        names = ("RBM_H03_TEST_BASE", "RBM_H03_TEST_STORAGE", "RBM_H03_TEST_GCC")
        values = [os.environ.get(name) for name in names]
        if not any(values):
            self.skipTest("Native M32R inputs require " + ", ".join(names))
        self.assertTrue(all(values), "Set all three native M32R input variables")
        base, storage_path = (Path(value).resolve(strict=True) for value in values[:2])
        executable = shutil.which(values[2])
        self.assertIsNotNone(executable, "Native M32R compiler was not found")
        compiler = Path(executable).resolve(strict=True)
        sys.path.insert(0, str(ROOT / "tools"))
        from check_h03_image_layout import read_storage_report
        from lfj8_h03_layout import alloc_sections, read_elf
        storage = read_storage_report(storage_path)
        image = base.read_bytes()
        self.assertEqual(sha256(image).hexdigest(), bench.IMAGE_HASH)
        environment = dict(os.environ, PATH=str(compiler.parent) + os.pathsep + os.environ.get("PATH", ""))

        def run(*args):
            return subprocess.run([str(item) for item in args], cwd=ROOT, env=environment,
                                  check=True, capture_output=True, text=True, timeout=60).stdout.strip()

        self.assertEqual(run(compiler, "-dumpmachine"), "m32r-elf")
        with TemporaryDirectory(prefix="h03-native-memory-") as temporary:
            output = os.environ.get("RBM_H03_TEST_OUT")
            stage = Path(output).resolve() if output else Path(temporary)
            if output:
                stage.mkdir(parents=True, exist_ok=False)
            pointer = storage["blocks"]["control"]["end_exclusive"]
            profile = bench.prepare(image, storage, pointer, stage)
            expected = {*profile["symbols"], "rbm_h03_boot_writers_owned"}
            include_flags = [flag for path in ("controller/include", "controller/vendor/toyota/include",
                                               "targets/lfj8", "diagnostics") for flag in ("-I", str(ROOT / path))]
            result = {"artifact_kind": "M32R_REL_MEMORY_INPUTS_COMPONENT_ONLY",
                      "base_sha256": sha256(image).hexdigest(),
                      "storage_sha256": sha256(storage_path.read_bytes()).hexdigest(),
                      "compiler": run(compiler, "--version").splitlines()[0], "models": {},
                      "hardware_verified": False, "flashable_image": None}
            for model in ("medium", "small"):
                destination = stage / model
                destination.mkdir()
                target = ["-m32r", "-mmodel=" + model, "-msdata=none", "-Wa,-EB"]
                common = [*target, "-Os", "-std=c11", "-Wall", "-Wextra", "-Werror",
                          "-Wno-missing-braces", "-Wno-missing-field-initializers", "-ffreestanding",
                          "-fno-builtin", "-fno-common", "-ffunction-sections", "-fdata-sections", *include_flags]
                objects = []
                for name in (*bench.NATIVE_SOURCES, "lfj8_h03_target_memory.c"):
                    source = ROOT / "targets/lfj8" / name
                    obj = destination / (source.stem + ".o")
                    flags = list(bench.native_compile_flags(profile, source))
                    if name == "h03_dma4_guard.S":
                        flags.append("-DRBM_H03_COMMON_DMA4_GUARD=1")
                    run(compiler, *common, *flags, "-c", source, "-o", obj)
                    objects.append(obj)
                symbol_object = destination / "h03_bench_memory_symbols.o"
                run(compiler, *target, "-c", profile["symbol_source"], "-o", symbol_object)
                symbols_elf = read_elf(symbol_object, 1)
                self.assertEqual(alloc_sections(symbols_elf), [], "ABS definitions must allocate no RAM/Flash")
                alternatives = {}
                for kind, extra in (("assembly", [symbol_object]),
                                    ("linker_fragment", ["-Wl,-T," + str(profile["linker_fragment"])])):
                    combined = destination / ("memory-inputs-" + kind + ".o")
                    run(compiler, *target, "-fno-use-linker-plugin", "-r", "-nostdlib", *objects,
                        *extra, "-o", combined)
                    elf = read_elf(combined, 1)
                    undefined = {name for name, symbol in elf["symbols"].items() if symbol["section"] == 0}
                    self.assertFalse(expected & undefined, "A required memory definition remains unresolved")
                    for name, value in profile["symbols"].items():
                        symbol = elf["symbols"][name]
                        self.assertEqual((symbol["section"], symbol["address"]), (0xFFF1, value))
                    self.assertGreater(elf["symbols"]["rbm_h03_boot_writers_owned"]["section"], 0)
                    gate = elf["symbols"]["rbm_h03_early_irq_gate"]
                    latch = elf["symbols"]["rbm_h03_early_irq_bench_latches"]
                    self.assertEqual((latch["section"], latch["address"]), (gate["section"], gate["address"] + 12))
                    alternatives[kind] = {"sha256": elf["sha256"], "bytes": combined.stat().st_size,
                                          "remaining_external_references": sorted(undefined)}
                result["models"][model] = alternatives
            (stage / "native-memory-inputs.json").write_text(
                json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")

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
