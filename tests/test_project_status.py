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

    def test_continuation_cannot_reopen_closed_or_deferred_scope(self):
        registry = json.loads(status.REGISTER.read_text(encoding="utf-8"))
        for state in ("closed", "deferred"):
            modified = copy.deepcopy(registry)
            task = next(task for task in modified["tasks"] if task["status"] == state)
            task["continuation"] = {"action": "More work", "order": 1}
            with self.assertRaisesRegex(ValueError, "Invalid continuation"):
                status.validate(modified)

    def test_continuation_rejects_missing_action_and_invalid_chat(self):
        registry = json.loads(status.REGISTER.read_text(encoding="utf-8"))
        for follow in ({"order": 1}, {"order": 1, "action": "Work", "chat_id": 7}):
            modified = copy.deepcopy(registry)
            task = next(task for task in modified["tasks"] if task["status"] == "open")
            task["continuation"] = follow
            with self.assertRaisesRegex(ValueError, "Invalid continuation"):
                status.validate(modified)

    def test_handoff_fields_reject_empty_or_nontext_values(self):
        registry = json.loads(status.REGISTER.read_text(encoding="utf-8"))
        for key in ("inputs", "deliverable"):
            for value in ("", "  ", [], 3):
                modified = copy.deepcopy(registry)
                task = next(task for task in modified["tasks"] if task["status"] == "open")
                task["continuation"] = {"order": 1, "action": "Work", key: value}
                with self.assertRaisesRegex(ValueError, "Invalid continuation"):
                    status.validate(modified)

    def test_handoff_fields_are_visible_in_task_map(self):
        registry = json.loads(status.REGISTER.read_text(encoding="utf-8"))
        task = next(task for task in registry["tasks"] if task["status"] == "open")
        task["continuation"] = {"order": 1, "action": "Bind", "inputs": "Pinned signals",
                                "deliverable": "Compiled provider"}
        page = status.render_map(registry)
        self.assertIn("**Приоритет продолжения.** 1", page)
        self.assertIn("**Исходные условия.** Pinned signals", page)
        self.assertIn("**Что сдать.** Compiled provider", page)

    def test_task_map_orders_queue_before_closed_and_deferred(self):
        registry = json.loads(status.REGISTER.read_text(encoding="utf-8"))
        page = status.render_map(registry)
        queue = sorted((t for t in registry["tasks"] if t.get("continuation")),
                       key=lambda t: (t["continuation"]["order"], t["id"]))
        anchors = [page.index(f'<a id="{t["id"].lower()}">') for t in queue]
        self.assertEqual(anchors, sorted(anchors))
        for task in registry["tasks"]:
            if task["status"] in ("closed", "deferred"):
                self.assertGreater(page.index(f'<a id="{task["id"].lower()}">'), anchors[-1])


if __name__ == "__main__":
    unittest.main()
