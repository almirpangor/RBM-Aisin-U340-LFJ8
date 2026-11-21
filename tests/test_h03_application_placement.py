import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "targets/lfj8"))
import lfj8_h03_application_placement as placement
from lfj8_h03_layout import Window


class ApplicationPlacementTest(unittest.TestCase):
    def setUp(self):
        self.rom = bytearray(0x80000)
        self.window = Window("application", 0x20000, 0x30000)
        sections = [{"name": "", "type": 0},
                    {"name": ".text", "type": 1, "flags": 6,
                     "address": self.window.start, "size": 0x100}]
        symbols = {name: {"section": 0xFFF1, "address": address}
                   for name, address in placement.STOCK_SYMBOLS.items()}
        for i, site in enumerate(placement.REDIRECTS):
            target = self.window.start + i * 4
            self.rom[site.address:site.address + 4] = bytes.fromhex(site.stock_word)
            word = site.opcode | (((target - site.address) // 4) & 0xffffff)
            sections.append({"name": site.section, "type": 1, "flags": 6,
                             "address": site.address, "data": word.to_bytes(4, "big")})
            symbols[site.hook] = {"section": 1, "address": target}
        self.elf = {"sections": sections, "symbols": symbols}

    def test_exact_stock_sites_and_branch_types(self):
        source = placement.assembly(self.rom)
        roots = placement.verify_linked(self.rom, self.elf, (self.window,))
        self.assertEqual([patch["address"] for patch in roots], [0x8100, 0x814C, 0x816C, 0x40424])
        self.assertEqual([patch["branch_word"][:2] for patch in roots], ["ff", "fe", "fe", "fe"])
        for item in roots:
            self.assertIn(item["hook"], source)
        self.assertEqual(sum(window.end - window.start for window in placement.REDIRECT_WINDOWS), 16)

    def test_rejects_changed_oem_instructions(self):
        for site in placement.REDIRECTS:
            with self.subTest(site=site.address):
                damaged = bytearray(self.rom)
                damaged[site.address] ^= 1
                with self.assertRaisesRegex(ValueError, "stock word"):
                    placement.assembly(damaged)

    def test_packs_only_one_word_at_each_fixed_location(self):
        sections = [dict(section, size=4, alignment=4) for section in self.elf["sections"][2:]]
        code = self.elf["sections"][1]
        fixed, remaining = placement.fixed_redirects([code, *sections])
        self.assertEqual([item["address"] for item in fixed], [site.address for site in placement.REDIRECTS])
        self.assertEqual(remaining, [code])
        with self.assertRaisesRegex(ValueError, "exactly one"):
            placement.fixed_redirects([*sections, sections[0]])
        sections[0]["size"] = 8
        with self.assertRaisesRegex(ValueError, "Invalid H03 application redirect"):
            placement.fixed_redirects(sections)

    def test_rejects_wrong_address_opcode_or_size(self):
        for update in ({"address": 0x8104}, {"data": b"\xfe\0\0\0"}, {"data": b"\0" * 8}):
            with self.subTest(update=update):
                wrong = copy.deepcopy(self.elf)
                wrong["sections"][2].update(update)
                with self.assertRaisesRegex(ValueError, "Incorrect linked"):
                    placement.verify_linked(self.rom, wrong, (self.window,))

    def test_accepts_canonical_output_section_names(self):
        for i, section in enumerate(self.elf["sections"][2:]):
            section["name"] = f".p{i:04d}"
        self.assertEqual(len(placement.verify_linked(self.rom, self.elf, (self.window,))), 4)

    def test_rejects_missing_unreachable_and_writable_targets(self):
        name = placement.REDIRECTS[0].hook
        for symbol in ({"section": 0, "address": 0},
                       {"section": 1, "address": self.window.end}):
            bad = copy.deepcopy(self.elf)
            bad["symbols"][name] = symbol
            with self.assertRaisesRegex(ValueError, "application hook"):
                placement.verify_linked(self.rom, bad, (self.window,))
        self.elf["sections"][1]["flags"] = 7
        with self.assertRaisesRegex(ValueError, "executable Flash"):
            placement.verify_linked(self.rom, self.elf, (self.window,))

    def test_rejects_changed_continuation(self):
        self.elf["symbols"]["h03_stock_application_after_entry"]["address"] += 4
        with self.assertRaisesRegex(ValueError, "continuation"):
            placement.verify_linked(self.rom, self.elf, (self.window,))


if __name__ == "__main__":
    unittest.main()
