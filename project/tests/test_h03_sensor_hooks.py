import unittest

from targets.lfj8.lfj8_h03_sensor_hooks import SENSOR_HOOKS, STOCK_SYMBOLS, patch_plan, validate_stock
from tools.check_h03_image_layout import sensor_placement


class SensorRedirectTests(unittest.TestCase):
    def setUp(self):
        self.rom = bytearray(0x4017C)
        self.addresses = {}
        for index, (site, hook, word) in enumerate(SENSOR_HOOKS):
            self.rom[site:site + 4] = bytes.fromhex(word)
            self.addresses[hook] = 0x20000 + 4 * index

    def test_plan_contains_nine_reachable_m32r_branches(self):
        validate_stock(self.rom)
        plan = patch_plan(self.rom, self.addresses)
        self.assertEqual(len(plan), 9)
        self.assertEqual(len({entry["site"] for entry in plan}), 9)
        for patch in plan:
            word = bytes.fromhex(patch["branch_word"])
            displacement = int.from_bytes(word[1:], "big", signed=True) * 4
            self.assertEqual(word[0], 0xFF)
            self.assertEqual(patch["site"] + displacement, self.addresses[patch["hook"]])
        patch_by_hook = {entry["hook"]: entry for entry in plan}
        self.assertEqual(STOCK_SYMBOLS["h03_atf_resume_done"], patch_by_hook["rbm_h03_atf_end"]["site"])

    def test_rejects_corrupt_stock_word(self):
        self.rom[0xAA0C] ^= 1
        with self.assertRaisesRegex(ValueError, "stock word"):
            validate_stock(self.rom)
        with self.assertRaisesRegex(ValueError, "stock word"):
            patch_plan(self.rom, self.addresses)

    def test_rejects_missing_unaligned_and_unreachable_entries(self):
        hook = SENSOR_HOOKS[0][1]
        self.addresses.pop(hook)
        with self.assertRaisesRegex(ValueError, "Missing placed"):
            patch_plan(self.rom, self.addresses)
        for address in (0x20002, 0x200AA0C):
            self.addresses[hook] = address
            with self.assertRaisesRegex(ValueError, "cannot reach"):
                patch_plan(self.rom, self.addresses)

    def test_linked_report_requires_exact_absolute_resume_points(self):
        symbols = {
            hook: {"section": 1, "address": address} for hook, address in self.addresses.items()
        }
        symbols.update({name: {"section": 0xFFF1, "address": address}
                        for name, address in STOCK_SYMBOLS.items()})
        report = sensor_placement(self.rom, {"symbols": symbols})
        self.assertEqual(report["status"], "LINKED_ADDRESS_MODEL")
        self.assertFalse(report["installed"])
        symbols["h03_atf_after_read"]["address"] += 4
        with self.assertRaisesRegex(ValueError, "pinned OEM address"):
            sensor_placement(self.rom, {"symbols": symbols})


if __name__ == "__main__":
    unittest.main()
