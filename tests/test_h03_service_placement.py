import struct
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "targets/lfj8"))
import lfj8_h03_service_placement as service


class ServicePlacementTest(unittest.TestCase):
    def setUp(self):
        self.rom = bytearray(b"\xff" * 0x80000)
        self.blocks = {
            "control": (0x806B40, 0x806F8C),
            "communication": (0x808E40, 0x80905C),
            "workspace": (0x80905C, 0x809478),
        }
        self.ranges = service.policy_ranges(self.blocks)
        addresses = [coordinate for interval in self.ranges for coordinate in interval]
        words = [len(self.ranges), *addresses, *([0] * (16 - len(addresses)))]
        guard_start = service.SPLIT_MODEL_WINDOWS[0][0]
        self.guard = self.section(service.GUARD_SECTION, guard_start, b"\x77\x00\xf0\x00" * 4 +
                                  struct.pack(">17I", *words), 1)
        self.symbols = {name: {"address": address} for name, address in service.STOCK_TARGETS.items()}
        self.symbols["rbm_h03_service_policy"] = {"address": guard_start + 16, "size": 68, "section": 1}
        self.sections = [self.guard]
        for index, site in enumerate(service.SITES):
            self.rom[site.address:site.address + 4] = struct.pack(">I", site.stock)
            if site != service.LOCKOUT:
                self.symbols[site.target] = {"address": guard_start + 4 * index, "section": 1}
            branch = site.branch(self.symbols[site.target]["address"])
            self.sections.append(self.section(site.section, site.address, branch, index + 2))

    @staticmethod
    def section(name, address, data, index):
        return {"index": index, "name": name, "address": address, "size": len(data),
                "flags": 6, "type": 1, "alignment": 4, "data": data}

    def overlay(self):
        with patch.object(service, "read_elf", return_value={"sections": self.sections,
                                                            "symbols": self.symbols, "sha256": "fixture"}):
            return service.verify_and_overlay(self.rom, "unused.elf", self.ranges)

    def test_overlay_installs_exact_words_and_preserves_stock_elsewhere(self):
        original = bytes(self.rom)
        model, report = self.overlay()
        self.assertEqual(len(report["sites"]), 5)
        self.assertFalse(report["target_ownership_verified"])
        self.assertEqual(bytes(self.rom), original)
        for section in self.sections:
            start = section["address"]
            self.assertEqual(model[start:start + section["size"]], section["data"])
        self.assertEqual(model[service.LOCKOUT.address:service.LOCKOUT.address + 4], b"\xff\x00\x00\x0b")
        self.assertEqual(model[0x8000:0x8004], original[0x8000:0x8004])

    def test_rejects_changed_stock_site(self):
        self.rom[service.LOCKOUT.address] ^= 1
        with self.assertRaisesRegex(ValueError, "Unexpected H03 service word"):
            self.overlay()

    def test_rejects_bra_at_link_call_site(self):
        span = self.sections[2]
        span["data"] = b"\xff" + span["data"][1:]
        with self.assertRaisesRegex(ValueError, "Wrong linked H03 service branch"):
            self.overlay()

    def test_rejects_overlaid_non_erased_guard(self):
        self.rom[self.guard["address"]] = 0
        with self.assertRaisesRegex(ValueError, "erased candidate window"):
            self.overlay()

    def test_rejects_different_protected_interval(self):
        start, end = self.ranges[0]
        self.ranges[0] = start, end - 4
        with self.assertRaisesRegex(ValueError, "policy differs"):
            self.overlay()

    def test_rejects_model_ram_overlapping_monitor_state(self):
        self.blocks["communication"] = (service.MONITOR_STATE[0], self.blocks["communication"][1])
        with self.assertRaisesRegex(ValueError, "overlapping RAM interval"):
            service.policy_ranges(self.blocks)

    def test_branch_checks_alignment_and_signed_displacement(self):
        site = service.WRITER_SITES[0]
        self.assertEqual(site.branch(site.address - 4), b"\xff\xff\xff\xff")
        for address in (site.address + 2, site.address + (1 << 25), site.address - (1 << 25) - 4):
            with self.assertRaisesRegex(ValueError, "Unreachable M32R service target"):
                site.branch(address)

    def common_writer_model(self):
        resident = service.Window("resident", 0x6000, 0x8000)
        guard_start = 0x6400
        self.guard["address"] = guard_start
        self.symbols["rbm_h03_service_policy"]["address"] = guard_start + 16
        for name in service.STOCK_TARGETS:
            self.symbols[name]["section"] = 0xFFF1
        for index, (site, name) in enumerate(zip(service.SITES, service.WRITER_ROOTS, strict=True)):
            if site != service.LOCKOUT:
                self.symbols[site.target]["address"] = guard_start + 4 * index
            section = self.sections[index + 1]
            section["data"] = site.branch(self.symbols[site.target]["address"])
            self.symbols[name] = {"address": site.address, "size": 4, "section": index + 2}
        return {"sections": [{}, *self.sections], "symbols": self.symbols}, resident

    def test_common_writers_pin_all_sites_and_hold_targets_below_application(self):
        elf, resident = self.common_writer_model()
        patches = service.verify_writers(self.rom, elf, self.ranges, resident)
        self.assertEqual([item["address"] for item in patches], [site.address for site in service.SITES])
        self.assertEqual(patches[-1]["target"], 0x3594)
        self.assertTrue(all(resident.start <= item["target"] < resident.end for item in patches[:-1]))
        self.symbols[service.WRITER_SITES[0].target]["address"] = resident.end
        with self.assertRaisesRegex(ValueError, "escaped resident Flash"):
            service.verify_writers(self.rom, elf, self.ranges, resident)

    def test_common_writer_rejects_modified_call_word_and_wrong_policy(self):
        elf, resident = self.common_writer_model()
        span = self.sections[2]
        original = span["data"]
        span["data"] = b"\xff" + original[1:]
        with self.assertRaisesRegex(ValueError, "Incorrect H03 service writer redirect"):
            service.verify_writers(self.rom, elf, self.ranges, resident)
        span["data"] = original
        with self.assertRaisesRegex(ValueError, "Incorrect resident H03 service policy"):
            service.verify_writers(self.rom, elf, self.ranges[:-1], resident)


if __name__ == "__main__":
    unittest.main()
