import json
from pathlib import Path
import unittest
from unittest.mock import patch

from tools import check_e4m3_diff


class E4M3ArchiveCoverageTests(unittest.TestCase):
    def setUp(self):
        path = check_e4m3_diff.ROOT / "data/e4m3-diff.json"
        self.manifest = json.loads(path.read_text(encoding="utf-8"))
        self.files = self.manifest["files"]
        self.groups = self.manifest["byte_identical_groups"]
        self.comparisons = self.manifest["comparisons"]

    def assert_invalid_coverage(self, message):
        with patch.object(check_e4m3_diff, "read_image") as read_image:
            with self.assertRaisesRegex(ValueError, message):
                check_e4m3_diff.verify(self.manifest, {}, Path("."), Path("."))
            read_image.assert_not_called()

    def test_accepts_complete_archive_in_any_order(self):
        self.groups.reverse()
        for group in self.groups:
            group.reverse()
        self.comparisons.reverse()
        check_e4m3_diff.require_archive_coverage(self.files, self.groups, self.comparisons)

    def test_rejects_missing_reference_image(self):
        del self.files["S02"]
        self.assert_invalid_coverage("Missing archived image entries: S02")

    def test_rejects_missing_historical_comparison(self):
        self.comparisons.pop()
        self.assert_invalid_coverage("Missing archived comparisons: E4M2 -> E4M3")

    def test_rejects_comparison_repeated_with_correct_totals(self):
        self.comparisons.append(self.comparisons[0].copy())
        self.assert_invalid_coverage("Duplicate archived comparison")

    def test_rejects_copy_group_missing_publication(self):
        group = next(group for group in self.groups if "E4M3" in group)
        group.remove("E4M3_PUBLICATION")
        self.assert_invalid_coverage("Missing or incomplete archived copy group: .*E4M3_PUBLICATION")

    def test_rejects_repeated_copy_group_or_member(self):
        with self.subTest("group"):
            self.groups.append(self.groups[0][::-1])
            self.assert_invalid_coverage("Duplicate archived copy group or member")
        self.groups.pop()
        with self.subTest("member"):
            self.groups[0].append(self.groups[0][0])
            self.assert_invalid_coverage("Duplicate archived copy group or member")
