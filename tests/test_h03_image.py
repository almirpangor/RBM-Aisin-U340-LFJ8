"""Final-image byte assembly must not silently drop, relocate or overwrite code."""
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from tools import h03_image as image
from tools import check_h03_image_layout as builder


class ImageTests(unittest.TestCase):
    def setUp(self):
        self.base = bytearray(b"\xff" * image.IMAGE_SIZE)
        tag = b"LFJ8\x0018\x009E1\x00C\x00LFJ8TC000LFXA0A0\x00SW-LFJ8TC000.HEX\x00"
        self.base[image.IDENTITY_OFFSET:image.IDENTITY_OFFSET + len(tag)] = tag
        for offset, value in image.MARKERS:
            self.base[offset:offset + len(value)] = value
        self.base[0x8100:0x8104] = b"\x2e\x7f\x4f\xfc"
        self.base = bytes(self.base)
        self.hash_patch = patch.object(image, "H03_SHA256", sha256(self.base).hexdigest())
        self.hash_patch.start()
        self.addCleanup(self.hash_patch.stop)
        self.elf = {"sha256": "e" * 64, "sections": [
            dict(index=0,name="",type=0,flags=0,address=0,size=0,alignment=1,data=b""),
            dict(index=1,name=".p0000",type=1,flags=6,address=0x20000,size=8,alignment=4,data=b"abcdefgh"),
            dict(index=2,name=".p0001",type=8,flags=3,address=0x806000,size=12,alignment=4,data=b""),
        ], "symbols": {"entry": dict(section=1,address=0x20000,size=8,type=2)}}
        self.layout = {
            "status": "PASS_ADDRESS_MODEL_ONLY", "accepted_layout": True,
            "base": {"sha256": sha256(self.base).hexdigest()}, "elf_sha256": self.elf["sha256"],
            "required_roots": ["entry"],
            "placements": [
                dict(section=".text.entry", address=0x20000,bytes=8,noload=False,flags=6),
                dict(section=".bss.state", address=0x806000,bytes=12,noload=True,flags=3),
            ]}
        self.patch = dict(address=0x8100,before="2e7f4ffc",after="ff007fc0",name="startup redirect")

    def test_reproducible_complete_image_preserves_every_unpatched_byte(self):
        output, record = image.compose(self.base, self.elf, self.layout, [self.patch])
        expected = bytearray(self.base)
        expected[0x20000:0x20008] = b"abcdefgh"
        expected[0x8100:0x8104] = bytes.fromhex(self.patch["after"])
        self.assertEqual(output, expected)
        self.assertEqual(len(output), 0x80000)
        self.assertEqual(record["noload_ram_bytes_not_serialized"], 12)
        self.assertEqual(record["status"], "UNQUALIFIED_LINKED_IMAGE")
        self.assertFalse(record["bench_pair_ready"])
        self.assertEqual((output, record), image.compose(self.base, self.elf, self.layout, [self.patch]))
        self.assertEqual(record["diagnostic_byte_sum16"], f"{sum(output) & 0xffff:04x}")

    def test_partial_model_stale_elf_or_wrong_base_rejected(self):
        for change in ({"status":"FAIL_BINDINGS"}, {"accepted_layout":False},
                       {"unresolved_symbols":["input"]}, {"elf_sha256":"wrong"}, {"base":{}}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                image.compose(self.base, self.elf, {**self.layout, **change})
        with self.assertRaisesRegex(ValueError, "pinned"):
            image.compose(b"x" + self.base[1:], self.elf, self.layout)

    def test_missing_or_orphan_sections_and_undefined_symbols_fail(self):
        for alter in ("missing","orphan","undefined","relocation"):
            elf = deepcopy(self.elf)
            if alter == "missing": elf["sections"].pop()
            elif alter == "orphan":
                elf["sections"].append(dict(elf["sections"][1],index=3,name=".unexpected"))
            elif alter == "undefined": elf["symbols"]["missing"] = dict(section=0)
            else: elf["sections"].append(dict(index=3,name=".rel",flags=0,type=9,size=8))
            with self.subTest(alter=alter), self.assertRaises(ValueError):
                image.compose(self.base, elf, self.layout)

    def test_patch_requires_exact_preimage_and_equal_lengths(self):
        for change in ({"before":"00000000"},{"after":"ff"},{"address":-1},{"before":"nonhex"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                image.compose(self.base,self.elf,self.layout,[{**self.patch,**change}])

    def test_occupied_elf_section_requires_explicit_matching_patch(self):
        elf, layout = deepcopy(self.elf), deepcopy(self.layout)
        elf["sections"][1].update(address=0x8100,size=4,data=bytes.fromhex(self.patch["after"]))
        elf["symbols"]["entry"].update(address=0x8100,size=4)
        layout["placements"][0].update(address=0x8100,bytes=4)
        with self.assertRaisesRegex(ValueError,"Occupied"):
            image.compose(self.base,elf,layout)
        _,record = image.compose(self.base,elf,layout,[self.patch])
        self.assertEqual(len(record["writes"]),1)
        with self.assertRaisesRegex(ValueError,"differs"):
            image.compose(self.base,elf,layout,[{**self.patch,"after":"ff000000"}])

    def test_partial_overlap_and_duplicate_patches_fail(self):
        with self.assertRaisesRegex(ValueError,"Overlapping"):
            image.compose(self.base,self.elf,self.layout,[self.patch,self.patch])
        overlap=dict(address=0x20004,before="ffffffffffffffff",after="0000000000000000",name="overlap")
        with self.assertRaisesRegex(ValueError,"Overlapping"):
            image.compose(self.base,self.elf,self.layout,[overlap])

    def test_low_flash_writes_are_reported_not_assumed_programmable(self):
        patch_low=dict(address=0x6000,before="ffffffff",after="01020304",name="resident")
        _,record = image.compose(self.base,self.elf,self.layout,[patch_low])
        self.assertTrue(record["requires_write_below_0x8000"])
        self.assertEqual(record["changed_below_application_boundary"],4)
        self.assertFalse(record["hardware_verified"])

    def test_flash_extent_and_initialized_ram_are_rejected(self):
        for change in ({"address":0x80000},{"flags":3}):
            elf,layout=deepcopy(self.elf),deepcopy(self.layout)
            elf["sections"][1].update(change)
            layout["placements"][0].update(change)
            elf["symbols"]["entry"]["address"]=elf["sections"][1]["address"]
            with self.subTest(change=change),self.assertRaises(ValueError):
                image.compose(self.base,elf,layout)

    def test_boot_markers_and_identity_cannot_be_patched(self):
        for start,length in ((0x8000,2),(0x7fffe,2),(image.IDENTITY_OFFSET,4)):
            protected=dict(address=start,before=self.base[start:start+length].hex(),after="00"*length,name="bad")
            with self.subTest(start=start),self.assertRaisesRegex(ValueError,"protected"):
                image.compose(self.base,self.elf,self.layout,[protected])

    def test_ram_bytes_do_not_mask_overlapping_flash_sections(self):
        elf,layout=deepcopy(self.elf),deepcopy(self.layout)
        elf["sections"][2].update(type=1,flags=2,address=0x20004,size=4,data=b"1234")
        layout["placements"][1].update(address=0x20004,bytes=4,noload=False,flags=2)
        with self.assertRaisesRegex(ValueError,"Overlapping"):
            image.compose(self.base,elf,layout)


class ExtraBindingTests(unittest.TestCase):
    def test_accepts_explicit_native_c_and_asm(self):
        for name in ("lfj8_h03_target_commit.c","h03_sensor_hooks.S"):
            self.assertEqual(builder.extra_binding_sources([builder.LFJ8/name]),[(builder.LFJ8/name).resolve()])

    def test_rejects_duplicates_and_fixture_outside_or_nonexistent_sources(self):
        good=builder.LFJ8/"lfj8_h03_target_commit.c"
        for values in ([good,good],[builder.LFJ8/"h03_nvm_native_fixture.c"],
                       [builder.LFJ8/"lfj8_h03_storage.h"],
                       [builder.ROOT/"tools/h03_image.py"],[builder.LFJ8/"missing.c"]):
            with self.subTest(values=values),self.assertRaises(ValueError):
                builder.extra_binding_sources(values)


if __name__ == "__main__":
    unittest.main()

