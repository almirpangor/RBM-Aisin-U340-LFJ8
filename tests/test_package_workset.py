from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from tools import package_workset


class FirmwarePairTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.commit = "a" * 40
        self.source_files = {"README.md": b"Synthetic workset test"}
        self.artifacts = []
        for role, size in package_workset.FIRMWARE_SIZES.items():
            content = role.encode("ascii").ljust(size, b"\x00")
            file = f"{role}.bin"
            (self.root / file).write_bytes(content)
            self.artifacts.append({
                "file": file,
                "path": f"artifacts/{file}",
                "role": role,
                "status": "candidate",
                "sha256": sha256(content).hexdigest(),
                "build_verified": True,
                "model_verified": True,
                "hardware_verified": False,
            })

    def package(self, output, *, firmware_pair=True):
        record = self.root / "record.json"
        record.write_text(json.dumps({"source_commit": self.commit, "artifacts": self.artifacts}),
                          encoding="utf-8")
        with BytesIO() as buffer:
            with ZipFile(buffer, "w") as source:
                for name, content in self.source_files.items():
                    source.writestr(name, content)
            commands = [self.commit.encode("ascii"), buffer.getvalue()]
        with patch.object(package_workset, "git", side_effect=commands):
            return package_workset.create_workset(record, output, firmware_pair=firmware_pair)

    def test_renamed_archived_offline_image_is_rejected(self):
        image = self.artifacts[1]
        self.source_files["verification/old_OFFLINE_ONLY.bin"] = (self.root / image["file"]).read_bytes()
        output = self.root / "pair.zip"
        with self.assertRaisesRegex(ValueError, "OFFLINE_ONLY"):
            self.package(output)
        self.assertFalse(output.exists())

    def test_offline_manifest_identifies_unarchived_image(self):
        self.source_files["verification/ordinary/manifest.json"] = json.dumps({
            "status": "OFFLINE_ONLY_NOT_HARDWARE_TESTED",
            "sha256": self.artifacts[1]["sha256"],
        }).encode("utf-8")
        output = self.root / "pair.zip"
        with self.assertRaisesRegex(ValueError, "OFFLINE_ONLY"):
            self.package(output)
        self.assertFalse(output.exists())
        self.package(self.root / "evidence.zip", firmware_pair=False)

    def test_distinct_candidate_is_deterministic(self):
        self.source_files["verification/other_OFFLINE_ONLY.bin"] = b"another artifact"
        first = self.root / "first.zip"
        second = self.root / "second.zip"
        self.assertEqual(self.package(first), self.package(second))
        self.assertEqual(first.read_bytes(), second.read_bytes())
        with ZipFile(first) as archive:
            manifest = json.loads(archive.read("MANIFEST.json"))
        self.assertEqual(manifest["source_commit"], self.commit)
        self.assertEqual([row["hardware_verified"] for row in manifest["files"] if "role" in row],
                         [False, False])
