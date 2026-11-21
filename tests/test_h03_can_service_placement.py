"""Checks for shared CAN service RAM aliases."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "targets/lfj8"))
from lfj8_h03_can_service_placement import typed_alias_ranges


class CanServicePlacementTests(unittest.TestCase):
    def setUp(self):
        self.storage = {
            "blocks": {
                "communication": {"address": 0x100, "end_exclusive": 0x130},
                "workspace": {"address": 0x130, "end_exclusive": 0x150},
            },
            "fields": {
                "communication/can_owner": {"offset": 0, "bytes": 12, "alignment": 4},
                "communication/can_service": {"offset": 12, "bytes": 16, "alignment": 4},
                "workspace/can13_input": {"offset": 0, "bytes": 16, "alignment": 4},
            },
        }
        self.aliases = {
            "h03_can_owner": "communication/can_owner",
            "rbm_h03_can_service": "communication/can_service",
            "rbm_h03_can13_input": "workspace/can13_input",
        }

    def test_shared_owner_and_workspace_resolve_to_distinct_fields(self):
        self.assertEqual(typed_alias_ranges(self.storage, self.aliases), {
            "h03_can_owner": (0x100, 0x10C),
            "rbm_h03_can_service": (0x10C, 0x11C),
            "rbm_h03_can13_input": (0x130, 0x140),
        })

    def test_can_alias_requires_its_field_in_the_current_inventory(self):
        del self.storage["fields"]["communication/can_service"]
        with self.assertRaises(KeyError):
            typed_alias_ranges(self.storage, self.aliases)

    def test_wrong_or_overlapping_can_ram_is_refused(self):
        initial = self.storage["fields"]["communication/can_service"]
        for overrides in ({"offset": 4}, {"offset": -4}, {"offset": 13}, {"offset": 40},
                          {"bytes": 0}, {"alignment": 0}, {"alignment": 3}):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                self.storage["fields"]["communication/can_service"] = {**initial, **overrides}
                typed_alias_ranges(self.storage, self.aliases)
