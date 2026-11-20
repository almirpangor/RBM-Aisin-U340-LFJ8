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

        specification = b"specification"
        (self.root / "spec.txt").write_bytes(specification)
        registry = {
            "specification": {"path": "spec.txt", **registered_bytes(specification)},
            "repositories": {"R1": {"commit": pin1}, "R2": {"commit": pin2}},
            "firmware": [{"id": "S01", "repository": "R2", "path": "source.bin",
                          "git_blob_sha": blob, **registered_bytes(source)}],
            "supporting_materials": [],
        }
        (self.root / "data/sources.json").write_text(json.dumps(registry), encoding="utf-8")
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
