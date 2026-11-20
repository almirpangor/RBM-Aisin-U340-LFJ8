"""The audit must distinguish a code change from Git newline conversion."""
import copy
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory, gettempdir
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import project_status as status


class ProjectStatusTests(unittest.TestCase):
    def test_lf_hash_survives_clone_conversion_and_detects_code_change(self):
        with TemporaryDirectory(prefix="rbm-status-tests-") as directory:
            root = Path(directory).resolve()
            assert root.parent == Path(gettempdir()).resolve()
            source = root / "controller/probe.c"
            source.parent.mkdir()
            source.write_bytes(b"int value = 1;\n")
            vendor = root / "controller/vendor/toyota/manifest.json"
            vendor.parent.mkdir(parents=True)
            vendor.write_bytes(b"{}\n")
            report = root / "report.json"
            report.write_bytes(b'{"result": "passed"}\n')
            audit = root / "audit.json"
            with patch.object(status, "ROOT", root):
                saved = {
                    "text_hash_format": "lf",
                    "source_sha256": status.source_files(normalize=True),
                    "evidence_sha256": {"report.json": status.digest(report, normalize=True)},
                }
                audit.write_text(json.dumps(saved), encoding="utf-8")
                source.write_bytes(b"int value = 1;\r\n")
                vendor.write_bytes(b"{}\r\n")
                report.write_bytes(b'{"result": "passed"}\r\n')
                self.assertEqual(status.audit_errors({"audit": "audit.json"}), [])
                source.write_bytes(b"int value = 2;\r\n")
                errors = status.audit_errors({"audit": "audit.json"})
                self.assertEqual(errors, ["Code needs review/retest: controller/probe.c"])
                source.write_bytes(b"int value = 1;\n")
                (root / "controller/new.c").write_bytes(b"void untested(void) {}\n")
                self.assertIn("Code needs review/retest: controller/new.c",
                              status.audit_errors({"audit": "audit.json"}))

    def test_default_digest_preserves_exact_binary_bytes(self):
        with TemporaryDirectory(prefix="rbm-status-tests-") as directory:
            root = Path(directory).resolve()
            assert root.parent == Path(gettempdir()).resolve()
            a, b = root / "a.bin", root / "b.bin"
            a.write_bytes(b"\x00\xff\r\n")
            b.write_bytes(b"\x00\xff\n")
            self.assertNotEqual(status.digest(a), status.digest(b))

    def test_register_cannot_claim_release_with_open_work(self):
        registry = json.loads(status.REGISTER.read_text(encoding="utf-8"))
        modified = copy.deepcopy(registry)
        modified["release_ready"] = True
        with self.assertRaisesRegex(ValueError, "open task"):
            status.validate(modified)

    def test_dependency_cycle_is_rejected(self):
        registry = json.loads(status.REGISTER.read_text(encoding="utf-8"))
        modified = copy.deepcopy(registry)
        modified["tasks"][0]["depends"] = [modified["tasks"][1]["id"]]
        modified["tasks"][1]["depends"] = [modified["tasks"][0]["id"]]
        with self.assertRaisesRegex(ValueError, "Cyclic dependency"):
            status.validate(modified)


if __name__ == "__main__":
    unittest.main()
