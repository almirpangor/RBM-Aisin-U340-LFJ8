from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from tools import package_workset
from tools.inspect_lfj8_tcm import IDENTITY_OFFSET


class FirmwarePairTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.commit = "a" * 40
        self.sources = {"firmware": [], "supporting_materials": []}
        self.bosch_audit = {"files": {}}
        self.source_files = {"README.md": b"Synthetic workset test"}
        self.artifacts = []
        for role, size in package_workset.FIRMWARE_SIZES.items():
            content = bytearray(size)
            if role == "tcm_h03":
                metadata = b"LFJ8\x0018\x009E1\x00C\x00LFJ8TC000LFXA0A0\x00SW-LFJ8TC000.HEX\x00"
                content[IDENTITY_OFFSET:IDENTITY_OFFSET + len(metadata)] = metadata
                content[0x8000:0x8002] = b"\x5a\xa5"
                content[-2:] = b"\xa5\x5a"
            else:
                tag = b"ME7.9.71/720/4415EN.2/"
                content[0xA844A:0xA844A + len(tag)] = tag
            file = f"{role}.bin"
            (self.root / file).write_bytes(content)
            artifact = {
                "file": file,
                "path": f"artifacts/{file}",
                "role": role,
                "status": "candidate",
                "sha256": sha256(content).hexdigest(),
                "build_verified": True,
                "model_verified": True,
                "hardware_verified": False,
            }
            if role == "tcm_h03":
                artifact["bench_pair_ready"] = True
            self.artifacts.append(artifact)

    def package(self, output, *, firmware_pair=True):
        self.source_files["data/sources.json"] = json.dumps(self.sources).encode()
        self.source_files["data/e4m3-diff.json"] = json.dumps(self.bosch_audit).encode()
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

    def test_unqualified_image_status_is_rejected_but_remains_valid_evidence(self):
        image = self.artifacts[0]
        for index, status in enumerate(("UNQUALIFIED_LINKED_IMAGE", "PASS_ADDRESS_MODEL_ONLY")):
            with self.subTest(status=status):
                image["status"] = status
                output = self.root / f"pair-{index}.zip"
                with self.assertRaisesRegex(ValueError, "выпускную программную квалификацию"):
                    self.package(output)
                self.assertFalse(output.exists())
        self.package(self.root / "evidence.zip", firmware_pair=False)

    def test_explicit_not_bench_ready_image_is_rejected(self):
        image = self.artifacts[0]
        image["bench_pair_ready"] = False
        output = self.root / "pair.zip"
        with self.assertRaisesRegex(ValueError, "выпускную программную квалификацию"):
            self.package(output)
        self.assertFalse(output.exists())

    def test_tcm_requires_explicit_bench_readiness(self):
        image = self.artifacts[0]
        del image["bench_pair_ready"]
        output = self.root / "pair.zip"
        with self.assertRaisesRegex(ValueError, "выпускную программную квалификацию"):
            self.package(output)
        self.assertFalse(output.exists())
        self.package(self.root / "evidence.zip", firmware_pair=False)

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

    def test_offline_reports_identify_unarchived_images(self):
        digest = self.artifacts[1]["sha256"]
        reports = (
            {"status": "PASS_OFFLINE_ONLY", "sha256": digest},
            {"status": "PASS_OFFLINE_ONLY", "bosch_sha256": digest.upper()},
            {"status": "PASS_OFFLINE_ONLY", "image_sha256": digest},
            {"bosch_candidate_frame_probe": {"status": "OFFLINE_ONLY", "sha256": digest}},
        )
        for index, report in enumerate(reports):
            with self.subTest(report=report):
                self.source_files["verification/st10/trace.json"] = json.dumps(report).encode()
                output = self.root / f"pair-{index}.zip"
                with self.assertRaisesRegex(ValueError, "OFFLINE_ONLY"):
                    self.package(output)
                self.assertFalse(output.exists())

    def test_local_offline_manifest_identifies_renamed_image(self):
        image = self.artifacts[1]
        build_dir = self.root / "bosch"
        build_dir.mkdir()
        (self.root / image["file"]).rename(build_dir / "candidate.bin")
        image["file"] = "bosch/candidate.bin"
        (build_dir / "manifest.json").write_text(json.dumps({
            "status": "OFFLINE_ONLY_NOT_HARDWARE_TESTED",
            "sha256": image["sha256"],
        }), encoding="utf-8")
        output = self.root / "pair.zip"
        with self.assertRaisesRegex(ValueError, "OFFLINE_ONLY"):
            self.package(output)
        self.assertFalse(output.exists())
        self.package(self.root / "evidence.zip", firmware_pair=False)

    def test_offline_report_does_not_mark_base_or_unrelated_hashes(self):
        self.source_files["verification/st10/trace.json"] = json.dumps({
            "status": "PASS_OFFLINE_ONLY",
            "base_sha256": self.artifacts[0]["sha256"],
            "source_sha256": self.artifacts[1]["sha256"],
            "bosch_sha256": "a" * 64,
        }).encode()
        self.package(self.root / "pair.zip")

    def test_registered_inputs_are_rejected_even_when_renamed(self):
        for key, artifact, source_id in (("supporting_materials", self.artifacts[0], "H03"),
                                         ("firmware", self.artifacts[1], "S04")):
            with self.subTest(source=source_id):
                output = self.root / f"pair-{source_id}.zip"
                self.sources[key] = [{"id": source_id, "sha256": artifact["sha256"]}]
                with self.assertRaisesRegex(ValueError, source_id):
                    self.package(output)
                self.sources[key].clear()
                self.assertFalse(output.exists())
        self.package(self.root / "evidence.zip", firmware_pair=False)

    def test_older_bosch_audit_image_is_rejected(self):
        self.bosch_audit["files"]["E4M2"] = {"sha256": self.artifacts[1]["sha256"]}
        output = self.root / "pair.zip"
        with self.assertRaisesRegex(ValueError, "E4M2"):
            self.package(output)
        self.assertFalse(output.exists())

    def test_wrong_identity_or_boot_marker_is_rejected_at_full_size(self):
        cases = (
            (0, IDENTITY_OFFSET + len(b"LFJ8\x0018\x009E1\x00"), b"B", "9E1C"),
            (0, 0x8000, b"\x00", "0x008000"),
            (0, 0x7FFFE, b"\x00", "0x07FFFE"),
            (1, 0xA844A, b"\x00", r"ME7\.9\.71"),
        )
        for index, offset, replacement, error in cases:
            with self.subTest(offset=offset):
                output = self.root / f"pair-{offset}.zip"
                artifact = self.artifacts[index]
                path = self.root / artifact["file"]
                original = path.read_bytes()
                changed = original[:offset] + replacement + original[offset + len(replacement):]
                path.write_bytes(changed)
                artifact["sha256"] = sha256(changed).hexdigest()
                try:
                    with self.assertRaisesRegex(ValueError, error):
                        self.package(output)
                    self.assertFalse(output.exists())
                finally:
                    path.write_bytes(original)
                    artifact["sha256"] = sha256(original).hexdigest()

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
