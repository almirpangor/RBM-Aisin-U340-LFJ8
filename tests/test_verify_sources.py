from contextlib import redirect_stdout
from hashlib import sha256
import io
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tools import verify_sources


def git(repo, *arguments):
    return subprocess.check_output(["git", "-C", str(repo), *arguments], text=True).strip()


def registered_bytes(content):
    return {"bytes": len(content), "sha256": sha256(content).hexdigest()}


class SourceVerificationTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / "data").mkdir()

    def make_repo(self, name, content):
        repo = self.root / name
        repo.mkdir()
        git(repo, "init", "-q")
        (repo / "source.bin").write_bytes(content)
        git(repo, "add", "source.bin")
        git(repo, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
            "commit", "-qm", "record source")
        return repo, git(repo, "rev-parse", "HEAD")

    def write_registry(self, repositories, *, firmware=(), supporting_materials=()):
        specification = b"specification"
        (self.root / "spec.txt").write_bytes(specification)
        registry = {
            "specification": {"path": "spec.txt", **registered_bytes(specification)},
            "repositories": repositories,
            "firmware": firmware,
            "supporting_materials": supporting_materials,
        }
        (self.root / "data/sources.json").write_text(json.dumps(registry), encoding="utf-8")

    def verify(self, repo, images):
        output = io.StringIO()
        with patch.object(verify_sources, "ROOT", self.root), redirect_stdout(output):
            result = verify_sources.verify(repo, images)
        return result, output.getvalue()

    def test_checks_multiple_repositories_at_pinned_objects(self):
        source = b"correct source"
        r1, pin1 = self.make_repo("r1", b"other source")
        r2, pin2 = self.make_repo("r2", source)
        blob = git(r2, "rev-parse", "HEAD:source.bin")
        (r2 / "source.bin").write_bytes(b"new checkout")
        git(r2, "add", "source.bin")
        git(r2, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
            "commit", "-qm", "update source")
        head = git(r2, "rev-parse", "HEAD")
        self.assertNotEqual(head, pin2)
        (r2 / "source.bin").write_bytes(b"uncommitted local change")

        self.write_registry(
            {"R1": {"commit": pin1}, "R2": {"commit": pin2}},
            firmware=[{"id": "S01", "repository": "R2", "path": "source.bin",
                       "git_blob_sha": blob, **registered_bytes(source)}],
        )
        output = io.StringIO()
        with patch.object(verify_sources, "ROOT", self.root), redirect_stdout(output):
            self.assertTrue(verify_sources.verify(r1, {}, {"R2": r2}))
            with self.assertRaisesRegex(ValueError, "supply --repo R2"):
                verify_sources.verify(r1, {})
            with self.assertRaisesRegex(ValueError, "invalid additional repository ID"):
                verify_sources.verify(r1, {}, {"R1": r2})
        self.assertIn(f"R2 pinned commit: OK; {pin2}", output.getvalue())
        self.assertIn("S01 Git blob: OK", output.getvalue())
        self.assertEqual(git(r2, "rev-parse", "HEAD"), head)
        self.assertEqual((r2 / "source.bin").read_bytes(), b"uncommitted local change")

    def test_unavailable_commit_and_blob_are_rejected(self):
        repo, _ = self.make_repo("r1", b"blob")
        blob = git(repo, "rev-parse", "HEAD:source.bin")
        for revision in ("0" * 40, blob):
            with self.subTest(revision=revision), self.assertRaisesRegex(
                ValueError, "R3: pinned commit .* is unavailable"
            ):
                verify_sources.check_revision("R3", repo, revision)

    def test_reads_original_blob_when_git_has_a_replacement(self):
        original = b"original source"
        replacement = b"replaced source"
        repo, revision = self.make_repo("r1", original)
        object_spec = f"{revision}:source.bin"
        blob = git(repo, "rev-parse", object_spec)
        replacement_file = self.root / "replacement.bin"
        replacement_file.write_bytes(replacement)
        replacement_blob = git(repo, "hash-object", "-w", str(replacement_file))
        git(repo, "replace", blob, replacement_blob)
        self.assertEqual(git(repo, "cat-file", "blob", object_spec), replacement.decode("ascii"))
        self.write_registry(
            {"R1": {"commit": revision}},
            firmware=[{"id": "S01", "repository": "R1", "path": "source.bin",
                       "git_blob_sha": blob, **registered_bytes(original)}],
        )

        passed, output = self.verify(repo, {})
        self.assertTrue(passed)
        self.assertIn(f"S01: OK; {len(original)} bytes; {sha256(original).hexdigest()}", output)
        self.assertIn(f"S01 Git blob: OK; {blob}", output)
        self.assertEqual(git(repo, "rev-parse", f"refs/replace/{blob}"), replacement_blob)

    def test_requires_both_firmware_digest_and_git_blob_identity(self):
        original = b"pinned source"
        other_bytes = b"other content"
        repo, revision = self.make_repo("r1", original)
        blob = git(repo, "rev-parse", f"{revision}:source.bin")
        other_file = self.root / "other.bin"
        other_file.write_bytes(other_bytes)
        other_blob = git(repo, "hash-object", "-w", str(other_file))
        self.assertEqual(len(original), len(other_bytes))
        cases = (
            (original, other_blob, "S01: OK", "S01 Git blob: MISMATCH"),
            (other_bytes, blob, "S01: MISMATCH", "S01 Git blob: OK"),
        )
        for expected_bytes, expected_blob, byte_check, blob_check in cases:
            with self.subTest(expected_blob=expected_blob):
                self.write_registry(
                    {"R1": {"commit": revision}},
                    firmware=[{"id": "S01", "repository": "R1", "path": "source.bin",
                               "git_blob_sha": expected_blob, **registered_bytes(expected_bytes)}],
                )
                passed, output = self.verify(repo, {})
                self.assertFalse(passed)
                self.assertIn(byte_check, output)
                self.assertIn(blob_check, output)

    def test_keeps_h03_separate_from_optional_historical_images(self):
        repo, revision = self.make_repo("r1", b"donor source")
        selected = b"selected H03"
        archived = {"S05": b"archived S05", "S06": b"archived S06"}
        self.write_registry(
            {"R1": {"commit": revision}},
            firmware=[{"id": name, **registered_bytes(data)} for name, data in archived.items()],
            supporting_materials=[
                {"id": "H03", **registered_bytes(selected)},
                {"id": "H02", **registered_bytes(archived["S06"])},
            ],
        )
        paths = {}
        for name, data in {"H03": selected, **archived}.items():
            paths[name] = self.root / f"{name}.bin"
            paths[name].write_bytes(data)

        passed, output = self.verify(repo, {"H03": paths["H03"]})
        self.assertTrue(passed)
        self.assertIn("H03: OK", output)
        self.assertIn("S05: no local path supplied; skipped", output)
        self.assertIn("S06: no local path supplied; skipped", output)
        self.assertNotIn("H02:", output)

        for name in paths:
            with self.subTest(swapped_input=name):
                inputs = {**paths, name: paths["S06" if name == "H03" else "H03"]}
                passed, output = self.verify(repo, inputs)
                self.assertFalse(passed)
                self.assertIn(f"{name}: MISMATCH", output)
                for other in paths.keys() - {name}:
                    self.assertIn(f"{other}: OK", output)
