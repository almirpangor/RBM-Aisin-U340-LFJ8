import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "targets" / "lfj8"))
import lfj8_h03_dtc_rx_placement as placement


def pinned_low_rom():
    rom = bytearray(b"\xff" * 0x8000)
    rom[0x0009D8:0x0009DC] = bytes.fromhex("00004724")
    rom[0x000940:0x00094C] = bytes.fromhex("0000600000007ffe00008000")
    for site, _, stock, _ in placement.REDIRECTS:
        rom[site:site + 4] = bytes.fromhex(stock)
    return rom


class DtcResidentPlacementTests(unittest.TestCase):
    def test_pinned_vector_geometry_and_redirects(self):
        rom = pinned_low_rom()
        placement.validate_stock(rom)
        for changed in (0x0009D8, 0x000940, 0x001534, 0x004738):
            with self.subTest(changed=changed):
                damaged = rom.copy()
                damaged[changed] ^= 1
                with self.assertRaises(ValueError):
                    placement.validate_stock(damaged)

    def test_both_redirect_opcodes_and_application_boundary(self):
        rom = pinned_low_rom()
        hooks = [hook for _, hook, _, _ in placement.REDIRECTS]
        addresses = dict(zip(hooks, (0x6034, 0x609C)))
        patches = placement.patch_plan(rom, addresses)
        self.assertEqual([p["branch_word"] for p in patches], ["ff0012c0", "fe000659"])
        for target in (0x5FFC, 0x8000, 0x6035):
            with self.subTest(target=target), self.assertRaises(ValueError):
                placement.patch_plan(rom, {**addresses, hooks[0]: target})

    def test_only_readonly_irq_graph_is_allocated_low(self):
        sections = [{"name": name} for name in
                    (placement.POLL_ADAPTER, placement.OWNER_OPS, placement.IRQ_ADAPTER)]
        resident = {placement.OWNER_OPS, placement.IRQ_ADAPTER}
        low, upper = placement.split_flash(sections, resident)
        self.assertEqual([s["name"] for s in low], [placement.OWNER_OPS, placement.IRQ_ADAPTER])
        self.assertEqual([s["name"] for s in upper], [placement.POLL_ADAPTER])
        with self.assertRaisesRegex(ValueError, "missing from combined link"):
            placement.split_flash(sections[:1], resident)

    def test_linked_indirect_addresses_must_match_their_bindings(self):
        rom = pinned_low_rom()
        owner = 0x808F3C
        irq, poll = 0x6100, 0x20A00
        symbols = {name: {"section": 0xFFF1, "address": address} for name, address in
                   {**placement.STOCK_SYMBOLS, "h03_can_owner": owner}.items()}
        sections = [{"address": 0, "size": 0}]
        entries = []

        def add(name, address, flags, data):
            entries.append({"section": name, "address": address, "bytes": len(data),
                            "window": placement.RX_WINDOW.name if address < 0x8000 else "primary"})
            sections.append({"address": address, "size": len(data), "flags": flags, "data": data})
            return {"section": len(sections) - 1, "address": address, "size": len(data)}

        def words(*values):
            return b"".join(value.to_bytes(4, "big") for value in values)

        for i, (_, hook, _, _) in enumerate(placement.REDIRECTS):
            symbols[hook] = add(f".text.{hook}", 0x6000 + i * 4, 4, bytes(4))
        add(placement.IRQ_ADAPTER, irq, 4, bytes(4))
        add(placement.POLL_ADAPTER, poll, 4, bytes(4))
        ops = add(placement.OWNER_OPS, 0x6200, 0, words(irq, poll, owner))
        mmio = add(".rodata.lfj8_h03_mmio", 0x6240, 0, words(0, *([irq] * 6)))
        symbols["lfj8_h03_mmio"] = mmio
        elf = {"symbols": symbols, "sections": sections}

        result = placement.describe(rom, elf, entries, owner, linked=True)
        self.assertTrue(result["indirect_targets_verified"])
        sections[ops["section"]]["data"] = words(irq, poll, owner + 4)
        with self.assertRaisesRegex(ValueError, "native CAN owner operations"):
            placement.describe(rom, elf, entries, owner, linked=True)
        sections[ops["section"]]["data"] = words(irq, poll, owner)
        sections[mmio["section"]]["data"] = words(0, poll, *([irq] * 5))
        with self.assertRaisesRegex(ValueError, "outside the resident window"):
            placement.describe(rom, elf, entries, owner, linked=True)
