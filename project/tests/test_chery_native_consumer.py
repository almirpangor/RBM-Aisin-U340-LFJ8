"""ABI and actual-instruction regressions for the Chery ST10 component.

Set RBM_C167_MODEL to the pinned external c167_subset.py for CPU tests.  The
standalone verification command additionally requires S02 and executes OEM
instructions as its oracle; this small suite is not that original-byte proof.
"""

import importlib.util
import hashlib
import os
from pathlib import Path
import sys
import unittest


BOSCH = Path(__file__).resolve().parents[1] / "targets/bosch"
sys.path.insert(0, str(BOSCH))
from chery_native_consumer import CONTEXT_BYTES, DONOR_SHA256, FIELDS, LAYOUT, assemble


MODEL = Path(os.environ.get("RBM_C167_MODEL", "F:/АКПП/bosch-handoff/R2/tools/c167_subset.py"))
DONOR = Path(os.environ.get("RBM_CHERY_DONOR", "F:/АКПП/bosch-handoff/R4/development/E4M3/engine/build_inputs/CHERY_REFERENCE_DO_NOT_FLASH.bin"))
S04 = Path(os.environ.get("RBM_BOSCH_S04", "F:/АКПП/bosch-handoff/R1/firmware/engine/gw4g15/e4m3/GW4G15_REV8_E4M3.bin"))
S04_SHA256 = "e25a1c97492ae556b1a52043e6ae85b88d2da86c03a78ef01dc2151c8a0a4a2a"


class CheryNativeComponentABI(unittest.TestCase):
    def test_rejects_unrepresentable_and_segment_crossing_origins(self):
        for origin in (-2, 1, 0x1000000, 0x06FFF0):
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                assemble(origin)

    def test_context_has_distinct_aligned_slots(self):
        self.assertEqual(len(FIELDS), len(set(FIELDS)))
        self.assertEqual(set(LAYOUT.values()), set(range(0, CONTEXT_BYTES, 2)))
        self.assertGreater(CONTEXT_BYTES, 64)
        self.assertFalse(assemble().manifest()["target_adapter_installed"])


@unittest.skipUnless(MODEL.is_file(), "Set RBM_C167_MODEL for actual ST10 execution")
class CheryNativeMachine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("chery_consumer_test_isa", MODEL)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls.VM = module.C167

    def test_every_raw_operand_truncates_toward_zero(self):
        part = assemble()
        vm = self.VM(dict(enumerate(part.code, part.origin)))
        for raw in range(256):
            vm.reset()
            vm.r[4] = raw
            vm.run(part.labels["operand"])
            numerator = (raw - 50) * 102 * 16384
            expected = min(32767, (abs(numerator) // 6375) * (-1 if numerator < 0 else 1))
            self.assertEqual(vm.r[4], expected & 65535, raw)

    def test_numeric_command_and_context_follow_caller_dpp(self):
        for origin, page in ((0x068000, 0x13), (0x074000, 0x19)):
            with self.subTest(origin=origin, dpp2=page):
                part = assemble(origin)
                vm = self.VM(dict(enumerate(part.code, origin)), dpp=(0x12, 0x14, page, 3))
                vm.sp = 0xFC00
                vm.r[14], vm.r[15] = 0xA800, 0xA000
                for name in FIELDS:
                    vm.write(0xA000 + LAYOUT[name], 0)
                for name, value in (("flags_fd02", 8192), ("offset_98ca", 32000),
                                    ("source_98a4", 32000)):
                    vm.write(0xA000 + LAYOUT[name], value)
                for index, value in enumerate((0x0B, 40, 0x11, 0x39, 60, 25, 0x17, 0x70)):
                    vm.write(0xA800 + index, value, 1)
                before = list(vm.r)
                vm.md = [0xA55A, 0x5AA5]
                vm.write(0xFF10, 0xA5BF)
                vm.run(part.labels["cycle"])
                self.assertEqual(vm.read(0xA000 + LAYOUT["request_8c86"]), (-2621) & 65535)
                self.assertEqual(vm.read(0xA000 + LAYOUT["request_8c84"]), 2621)
                self.assertEqual(vm.read(0xA000 + LAYOUT["published_8c9c"]), 26758)
                self.assertEqual(vm.read(0xA000 + LAYOUT["published_8186"]), 104)
                self.assertEqual(vm.read(0xA000 + LAYOUT["published_8187"]), 151)
                self.assertEqual(vm.r, before)
                self.assertEqual(vm.md, [0xA55A, 0x5AA5])
                self.assertEqual(vm.read(0xFF10), 0xA5BF)

    def original_pair(self):
        if not DONOR.is_file() or not S04.is_file():
            self.skipTest("Set RBM_CHERY_DONOR and RBM_BOSCH_S04 for producer proof")
        chery, gw = DONOR.read_bytes(), S04.read_bytes()
        self.assertEqual(hashlib.sha256(chery).hexdigest(), DONOR_SHA256)
        self.assertEqual(hashlib.sha256(gw).hexdigest(), S04_SHA256)
        first = self.VM({address: value for address, value in enumerate(chery)
                         if not 0xE000 <= address <= 0xFFFF}, dpp=(0x2E, 0x2F, 0x3C, 3))
        second = self.VM({address + (0x10000 if address >= 0x8000 else 0): value
                          for address, value in enumerate(gw)}, dpp=(0x2E, 0x2F, 0x3C, 3))
        return first, second

    def test_original_model_base_and_limit_producer_windows(self):
        chery, gw = self.original_pair()
        for value in range(65536):
            upper = (value * 40503 + 17) & 65535
            results = []
            for vm, start, stop, source, output in (
                (chery, 0x05B0F8, 0x05B122, 0x98C6, 0x98CA),
                (gw, 0x059D94, 0x059DBE, 0x967C, 0x9680),
            ):
                vm.reset()
                vm.sp = 0xFC00
                vm.r[4] = value
                vm.write(source, upper)
                vm.run(start, stop=stop)
                results.append(vm.read(output))
            self.assertEqual(results[0], results[1], value)
        for value in range(65536):
            low, high = sorted((value, (value * 2053 + 11) & 65535))
            results = []
            for vm, start, stop, output in (
                (chery, 0x05AA12, 0x05AA2A, 0x98A4),
                (gw, 0x059678, 0x059690, 0x965A),
            ):
                vm.reset()
                vm.r[7:10] = [high, low, value]
                vm.run(start, stop=stop)
                results.append(vm.read(output))
            self.assertEqual(results, [min(max(value, low), high)] * 2, value)

    def test_original_lower_bound_producer_windows(self):
        chery, gw = self.original_pair()
        for value in range(65536):
            second = (value * 2053 + 11) & 65535
            results = []
            for vm, start, stop, first_input, second_input, output in (
                (chery, 0x059A94, 0x059AAC, 0x981E, 0x9820, 0x9822),
                (gw, 0x05828E, 0x0582A6, 0x95B2, 0x95B4, 0x95B6),
            ):
                vm.reset()
                vm.write(first_input, value)
                vm.write(second_input, second)
                vm.run(start, stop=stop)
                results.append(vm.read(output))
            self.assertEqual(results, [max(value, second)] * 2, value)

    def test_original_integrator_source_fault_selection(self):
        chery, gw = self.original_pair()
        for value in range(65536):
            for fault in (0, 1):
                results = []
                for vm, start, stop, fault_input, source, output in (
                    (chery, 0x02685E, 0x026874, 0xB316, 0x8964, 0x8966),
                    (gw, 0x024E24, 0x024E3A, 0xB314, 0x86C0, 0x86C2),
                ):
                    vm.reset()
                    vm.write(fault_input, 0xA500 | fault)
                    vm.write(source, value)
                    vm.run(start, stop=stop)
                    results.append(vm.read(output))
                self.assertEqual(results, [0 if fault else value] * 2, (value, fault))


if __name__ == "__main__":
    unittest.main()
