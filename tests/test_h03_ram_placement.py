import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "targets/lfj8"))
import lfj8_h03_ram_placement as ram


class RamPlacementTest(unittest.TestCase):
    def setUp(self):
        self.rom = bytearray(0x4000)
        for address, data in ram.STACK_STARTUP.items():
            self.rom[address:address + len(data)] = data
        self.blocks = {
            "control": {"address": 0x806B40, "end_exclusive": 0x806F8C},
            "communication": {"address": 0x808E40, "end_exclusive": 0x80905C},
            "workspace": {"address": 0x80905C, "end_exclusive": 0x809478},
        }
        self.bounds = ram.confirmed_ranges(self.rom, self.blocks)
        self.symbols = {name: {"section": 0, "address": 0} for name in self.bounds}

    def test_binds_only_confirmed_ends_and_typed_spans(self):
        self.assertEqual(ram.bind(self.symbols, self.bounds, {}), {
            "rbm_h03_ram_control_first": 0x806B40,
            "rbm_h03_ram_control_end": 0x806F8C,
            "rbm_h03_ram_communication_first": 0x808E40,
            "rbm_h03_ram_communication_end": 0x80905C,
            "rbm_h03_ram_workspace_first": 0x80905C,
            "rbm_h03_ram_workspace_end": 0x809478,
            "rbm_h03_ram_spi_end": 0x809EFC,
            "rbm_h03_ram_psw_end": 0x809FA0,
        })
        self.assertFalse(self.bounds.keys() & set(ram.REQUIRED_QUALIFICATION))

    def test_rejects_changes_to_either_spi_load_or_the_psw_cursor_store(self):
        for address in (0x0009E3, 0x003DA7, 0x003DA9, 0x003DB3, 0x003DB5):
            with self.subTest(address=address):
                changed = bytearray(self.rom)
                changed[address] ^= 1
                with self.assertRaisesRegex(ValueError, "stack initialization"):
                    ram.confirmed_ranges(changed, self.blocks)

    def test_rejects_allocated_conflicting_or_missing_aliases(self):
        name = "rbm_h03_ram_psw_end"
        with self.assertRaisesRegex(ValueError, "Conflicting existing"):
            ram.bind(self.symbols, self.bounds, {name: 0x809F9C})
        for section, address in ((1, self.bounds[name]), (0xFFF1, 0x809F9C)):
            self.symbols[name] = {"section": section, "address": address}
            with self.assertRaisesRegex(ValueError, "Native H03 symbol"):
                ram.bind(self.symbols, self.bounds, {})
        del self.symbols[name]
        with self.assertRaisesRegex(ValueError, "Missing RAM owner or application references"):
            ram.bind(self.symbols, self.bounds, {})

    def test_uses_typed_offsets_for_the_application_objects(self):
        groups = {
            "control": ("runtime", "cycle", "takeover"),
            "communication": ("main_result",),
            "workspace": ("toyota", "cycle_input"),
        }
        fields = {f"{group}/{name}": {"offset": 8 * (index + 1), "bytes": 4, "alignment": 4}
                  for group, names in groups.items() for index, name in enumerate(names)}
        self.assertEqual(ram.application_addresses({"blocks": self.blocks, "fields": fields}), {
            "rbm_h03_runtime_state": 0x806B48, "rbm_h03_cycle_state": 0x806B50,
            "rbm_h03_takeover_state": 0x806B58, "rbm_h03_main_result": 0x808E48,
            "rbm_h03_cycle_workspace": 0x809064, "rbm_h03_cycle_input": 0x80906C,
        })

    def test_validates_the_final_absolute_symbols(self):
        linked = {name: {"section": 0xFFF1, "address": address}
                  for name, address in self.bounds.items()}
        ram.verify_linked(linked, self.bounds)
        linked["rbm_h03_ram_spi_end"]["section"] = 1
        with self.assertRaisesRegex(ValueError, "differs"):
            ram.verify_linked(linked, self.bounds)
