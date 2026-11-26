import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "targets" / "lfj8"))
import lfj8_h03_tx13_placement as tx13


def word(value):
    return value.to_bytes(4, "big")


def pinned_rom():
    rom = bytearray(b"\xff" * 0x80000)
    rom[tx13.SITE:tx13.SITE + 4] = bytes.fromhex(tx13.STOCK)
    return rom


class Tx13PlacementTests(unittest.TestCase):
    def test_patch_checks_original_entry_and_executable_address(self):
        rom = pinned_rom()
        tx13.validate_stock(rom)
        plan = tx13.patch_plan(rom, 0x20000)
        self.assertEqual((plan["site"], plan["branch_word"]), (0xC34C, "ff004f2d"))
        for target in (0x7FFC, 0x20002, 0x80000, tx13.SITE):
            with self.subTest(target=target), self.assertRaises(ValueError):
                tx13.patch_plan(rom, target)
        rom[tx13.SITE] ^= 1
        with self.assertRaisesRegex(ValueError, "stock word"):
            tx13.patch_plan(rom, 0x20000)

    def test_only_one_aligned_fixed_word_is_accepted(self):
        entry = {"name": f".text.{tx13.REDIRECT}", "size": 4, "alignment": 4, "type": 1, "flags": 6}
        other = {"name": f".text.{tx13.GATE}"}
        fixed, remaining = tx13.fixed_redirect((other, entry))
        self.assertEqual((fixed[0]["address"], fixed[0]["bytes"]), (0xC34C, 4))
        self.assertEqual(remaining, [other])
        for invalid in ((other,), (entry, entry), ({**entry, "flags": 2},), ({**entry, "size": 8},)):
            with self.assertRaisesRegex(ValueError, "one aligned executable"):
                tx13.fixed_redirect(invalid)

    def test_linked_words_are_checked_independently(self):
        rom = pinned_rom()
        owner, gate = 0x808F48, 0x20000
        branch_back = 0xFF000000 | (((0xC350 - (gate + 8)) // 4) & 0xFFFFFF)
        payload = word(0xE1000000 | owner) + bytes.fromhex(tx13.STOCK) + word(branch_back)
        patch = tx13.patch_plan(rom, gate)
        sections = [
            {},
            {"name": ".p0000", "address": tx13.SITE, "size": 4,
             "flags": 6, "data": bytes.fromhex(patch["branch_word"])},
            {"name": ".p0001", "address": gate, "size": len(payload), "flags": 6, "data": payload},
        ]
        symbols = {
            tx13.REDIRECT: {"section": 1, "address": tx13.SITE, "size": 4},
            tx13.GATE: {"section": 2, "address": gate, "size": len(payload)},
            tx13.OWNER_LOAD: {"section": 2, "address": gate, "size": 4},
            tx13.REPLAY: {"section": 2, "address": gate + 4, "size": 4},
            tx13.RESUME_BRANCH: {"section": 2, "address": gate + 8, "size": 4},
            tx13.RESUME: {"section": 0xFFF1, "address": 0xC350},
            tx13.OWNER: {"section": 0xFFF1, "address": owner},
        }
        placements = [{"section": f".text.{tx13.GATE}", "bytes": len(payload), "address": gate}]
        elf = {"sections": sections, "symbols": symbols}
        self.assertTrue(tx13.describe(rom, elf, placements, owner, linked=True)["elf_words_verified"])
        for offset, label in enumerate((tx13.OWNER_LOAD, tx13.REPLAY, tx13.RESUME_BRANCH)):
            with self.subTest(label=label), self.assertRaisesRegex(ValueError, label):
                changed = bytearray(payload)
                changed[4 * offset + 3] ^= 1
                sections[2]["data"] = changed
                tx13.describe(rom, elf, placements, owner, linked=True)
        sections[2]["data"] = payload
        symbols[tx13.OWNER]["address"] += 4
        with self.assertRaisesRegex(ValueError, "native binding"):
            tx13.describe(rom, elf, placements, owner, linked=True)
        symbols[tx13.OWNER]["address"] = owner
        sections[1]["data"] = bytes(4)
        with self.assertRaisesRegex(ValueError, "differs from the OEM-site plan"):
            tx13.describe(rom, elf, placements, owner, linked=True)
