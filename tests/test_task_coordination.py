"""Integration tests of reservations with two real Git clients and a bare remote."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory, gettempdir
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from task_coordination import TaskBoard, Conflict, CoordinationError, edit_paths


class CoordinationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix="rbm-coordination-tests-")
        self.root = Path(self.temp.name).resolve()
        assert self.root.parent == Path(gettempdir()).resolve()
        assert self.root.name.startswith("rbm-coordination-tests-")
        self.addCleanup(self.temp.cleanup)
        self.remote = self.root / "remote.git"
        self.a, self.b = self.root / "a", self.root / "b"
        self.run_git(self.root, "init", "--bare", str(self.remote))
        self.run_git(self.root, "init", "-b", "main", str(self.a))
        self.identity(self.a)
        (self.a / "data").mkdir()
        registry = {"tasks": [
            {"id": "TEST-01", "title": "First", "status": "open", "code": ["a.c"]},
            {"id": "TEST-02", "title": "Second", "status": "open", "code": ["b.c"]},
            {"id": "TEST-03", "title": "Third", "status": "model", "code": ["c.c"]},
            {"id": "WAIT-01", "title": "Deferred", "status": "deferred", "code": ["d.c"]},
        ]}
        (self.a / "data/project-tasks.json").write_text(json.dumps(registry), encoding="utf-8")
        self.run_git(self.a, "add", ".")
        self.run_git(self.a, "commit", "-m", "Initial registry")
        self.run_git(self.a, "remote", "add", "origin", str(self.remote))
        self.run_git(self.a, "push", "-u", "origin", "main")
        self.run_git(self.root, "clone", "--branch", "main", str(self.remote), str(self.b))
        self.identity(self.b)
        self.seed = self.run_git(self.a, "rev-parse", "HEAD")
        self.ca, self.cb = TaskBoard(self.a), TaskBoard(self.b)

    @staticmethod
    def run_git(repo, *args):
        result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True)
        if result.returncode:
            raise AssertionError(result.stderr.decode("utf-8", "replace"))
        return result.stdout.decode("utf-8").strip()

    def identity(self, repo):
        self.run_git(repo, "config", "user.name", "Coordination test")
        self.run_git(repo, "config", "user.email", "coordination@example.invalid")
        self.run_git(repo, "config", "core.autocrlf", "false")

    def claim(self, client=None, task="TEST-01", owner="chat-a", files=None, branch=None):
        return (client or self.ca).change("claim", task, owner, label=owner,
                                         branch=branch or "codex/" + owner, files=files, note="Working")

    def race(self, first_task, second_task, first_files=None, second_files=None):
        barrier = threading.Barrier(2)

        class RacingBoard(TaskBoard):
            first = True
            def push(self, commit):
                if self.first:
                    self.first = False
                    barrier.wait(timeout=20)
                return super().push(commit)

        def worker(repo, task, owner, files):
            try:
                return self.claim(RacingBoard(repo), task, owner, files)
            except Conflict as error:
                return error

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(worker, self.a, first_task, "chat-a", first_files),
                pool.submit(worker, self.b, second_task, "chat-b", second_files),
            ]
            return [f.result(timeout=60) for f in futures]

    def test_same_task_simultaneous_claim_has_one_winner(self):
        outcomes = self.race("TEST-01", "TEST-01")
        self.assertEqual(sum(isinstance(o, dict) for o in outcomes), 1)
        self.assertEqual(sum(isinstance(o, Conflict) for o in outcomes), 1)
        _, board = self.ca.read()
        self.assertEqual(board["sequence"], 1)
        self.assertEqual(len(board["claims"]), 1)

    def test_different_tasks_simultaneous_claim_preserves_both(self):
        outcomes = self.race("TEST-01", "TEST-02")
        self.assertTrue(all(isinstance(o, dict) for o in outcomes))
        _, board = self.cb.read()
        self.assertEqual(board["sequence"], 2)
        self.assertEqual(set(board["claims"]), {"TEST-01", "TEST-02"})

    def test_simultaneous_overlapping_directory_reservation_has_one_winner(self):
        outcomes = self.race("TEST-01", "TEST-02", ["targets/LFJ8/"], ["targets/lfj8/input.c"])
        self.assertEqual(sum(isinstance(o, dict) for o in outcomes), 1)
        self.assertEqual(sum(isinstance(o, Conflict) for o in outcomes), 1)

    def test_read_and_write_leave_worktree_index_and_branch_intact(self):
        (self.a / "local-notes.txt").write_text("Unrelated staged work", encoding="utf-8")
        self.run_git(self.a, "add", "local-notes.txt")
        before = [self.run_git(self.a, *args) for args in (
            ("rev-parse", "HEAD"), ("write-tree",), ("status", "--porcelain"),
            ("symbolic-ref", "HEAD"))]
        self.claim()
        self.ca.view()
        after = [self.run_git(self.a, *args) for args in (
            ("rev-parse", "HEAD"), ("write-tree",), ("status", "--porcelain"),
            ("symbolic-ref", "HEAD"))]
        self.assertEqual(before, after)
        self.assertEqual(self.run_git(self.a, "for-each-ref", "refs/rbm-coordination"), "")

    def test_other_owner_and_old_generation_cannot_release(self):
        first = self.claim()
        with self.assertRaises(Conflict):
            self.cb.change("release", "TEST-01", "chat-b", claim_id=first["claim_id"], note="Wrong owner")
        self.ca.change("release", "TEST-01", "chat-a", claim_id=first["claim_id"], note="Handoff")
        second = self.claim()
        self.assertNotEqual(first["claim_id"], second["claim_id"])
        with self.assertRaises(Conflict):
            self.ca.change("release", "TEST-01", "chat-a", claim_id=first["claim_id"], note="Stale client")
        self.assertEqual(self.ca.read()[1]["claims"]["TEST-01"]["claim_id"], second["claim_id"])

    def test_block_resume_review_and_complete_require_published_result(self):
        record = self.claim()
        key = {"claim_id": record["claim_id"]}
        self.ca.change("block", "TEST-01", "chat-a", note="Need source data", **key)
        with self.assertRaises(Conflict):
            self.claim(self.cb, owner="chat-b")
        self.ca.change("resume", "TEST-01", "chat-a", **key)
        self.run_git(self.a, "checkout", "-b", "codex/chat-a")
        (self.a / "a.c").write_text("/* result */\n", encoding="utf-8")
        self.run_git(self.a, "add", "a.c")
        self.run_git(self.a, "commit", "-m", "Task result")
        result = self.run_git(self.a, "rev-parse", "HEAD")
        with self.assertRaises(CoordinationError):
            self.ca.change("review", "TEST-01", "chat-a", result=result, note="Not published", **key)
        self.run_git(self.a, "push", "origin", "codex/chat-a")
        self.ca.change("review", "TEST-01", "chat-a", result=result, note="Ready to review", **key)
        with self.assertRaises(CoordinationError):
            self.ca.change("complete", "TEST-01", "chat-a", result=result, note="Not merged", **key)
        self.run_git(self.a, "push", "origin", result + ":refs/heads/main")
        done = self.ca.change("complete", "TEST-01", "chat-a", result=result, note="Merged and checked", **key)
        self.assertEqual(done["stage"], "done")
        self.claim(self.cb, owner="chat-b")

    def test_result_typo_or_unknown_commit_cannot_complete(self):
        record = self.claim()
        for result in ("shortsha", "f" * 40):
            with self.assertRaises(CoordinationError):
                self.ca.change("complete", "TEST-01", "chat-a", claim_id=record["claim_id"],
                               result=result, note="Invalid result")
        self.assertEqual(self.ca.read()[1]["claims"]["TEST-01"]["stage"], "in_progress")

    def test_unknown_and_deferred_tasks_are_not_claimed(self):
        for task in ("NONE-01", "WAIT-01"):
            with self.assertRaises(CoordinationError):
                self.claim(task=task)
        self.assertIsNone(self.ca.read()[0])

    def test_invalid_paths_cannot_be_reserved(self):
        for value in ("../a.c", "C:/a.c", "/a.c", ".git/config", "*", ".", "a\nb"):
            with self.assertRaises(CoordinationError):
                edit_paths([value])
        self.assertEqual(edit_paths(["targets\\lfj8\\a.c"]), ["targets/lfj8/a.c"])

    def test_file_extension_and_same_branch_conflict(self):
        first = self.claim()
        self.claim(self.cb, "TEST-02", "chat-b")
        with self.assertRaises(Conflict):
            self.ca.change("heartbeat", "TEST-01", "chat-a", claim_id=first["claim_id"], files=["b.c"])
        with self.assertRaises(Conflict):
            self.claim(self.cb, "TEST-03", "chat-c", branch="codex/chat-a")
        self.assertEqual(self.ca.read()[1]["claims"]["TEST-01"]["files"], ["a.c"])

    def test_successful_push_with_lost_ack_is_not_duplicated(self):
        class LostAck(TaskBoard):
            def push(self, commit):
                actual = super().push(commit)
                if actual.returncode == 0:
                    return subprocess.CompletedProcess([], 1, b"", b"Simulated lost acknowledgement")
                return actual
        self.claim(LostAck(self.a))
        self.assertEqual(self.ca.read()[1]["sequence"], 1)

    def test_rejected_push_does_not_claim_locally(self):
        class Rejected(TaskBoard):
            def push(self, commit):
                return subprocess.CompletedProcess([], 1, b"", b"Simulated server rejection")
        with self.assertRaises(CoordinationError):
            self.claim(Rejected(self.a))
        self.assertIsNone(self.ca.read()[0])

    def test_existing_unrelated_branch_is_not_overwritten(self):
        self.run_git(self.a, "push", "origin", self.seed + ":refs/heads/task-board")
        with self.assertRaises(CoordinationError):
            self.claim()
        self.assertEqual(self.ca.fetch_tip("task-board"), self.seed)

    def test_remote_error_is_not_treated_as_empty_board(self):
        self.run_git(self.a, "remote", "set-url", "origin", str(self.root / "missing.git"))
        with self.assertRaises(CoordinationError):
            self.ca.view()

    def test_old_claim_does_not_expire_automatically(self):
        self.claim()
        tip, board = self.ca.read()
        board["claims"]["TEST-01"]["updated_at"] = "2000-01-01T00:00:00+00:00"
        self.assertEqual(self.ca.push(self.ca.make_commit(board, tip)).returncode, 0)
        with self.assertRaises(Conflict):
            self.claim(self.cb, owner="chat-b")


if __name__ == "__main__":
    unittest.main()
