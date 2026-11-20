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
from task_coordination import TaskBoard, Conflict, CoordinationError, edit_paths, render_board


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

    def submit_result(self):
        claim = self.claim()
        self.run_git(self.a, "checkout", "-b", "codex/chat-a")
        (self.a / "a.c").write_text("/* first submitted result */\n", encoding="utf-8")
        self.run_git(self.a, "add", "a.c")
        self.run_git(self.a, "commit", "-m", "First portion")
        result = self.run_git(self.a, "rev-parse", "HEAD")
        self.run_git(self.a, "push", "origin", "codex/chat-a")
        self.ca.change("review", "TEST-01", "chat-a", claim_id=claim["claim_id"],
                       result=result, note="First review")
        return claim, result

    def include_review(self, repo, branch, result):
        self.run_git(repo, "fetch", "origin", "codex/chat-a")
        self.run_git(repo, "branch", branch, result)

    def test_review_releases_same_task_and_preserves_submission(self):
        first, result = self.submit_result()
        self.run_git(self.b, "branch", "codex/chat-b", self.seed)
        with self.assertRaisesRegex(Conflict, "Include pending result"):
            self.claim(self.cb, owner="chat-b")
        self.run_git(self.b, "checkout", "codex/chat-b")
        self.run_git(self.b, "merge", "--ff-only", result)
        second = self.claim(self.cb, owner="chat-b")
        self.assertNotEqual(second["claim_id"], first["claim_id"])
        self.assertEqual(second["based_on_reviews"], [first["claim_id"]])
        _, board = self.ca.view()
        self.assertEqual(board["reviews"][first["claim_id"]]["result"], result)
        self.assertEqual(board["reviews"][first["claim_id"]]["stage"], "review")
        self.assertEqual(board["claims"]["TEST-01"], second)
        page = render_board(board)
        self.assertIn("Результаты на проверке — резерв свободен", page)
        self.assertIn(result[:12], page)
        for action in ("resume", "heartbeat", "release"):
            with self.assertRaises(Conflict):
                self.ca.change(action, "TEST-01", "chat-a", claim_id=first["claim_id"], note="Stale lease")

    def test_complete_uses_saved_review_without_touching_new_editor(self):
        first, result = self.submit_result()
        self.include_review(self.b, "codex/chat-b", result)
        second = self.claim(self.cb, owner="chat-b")
        key = {"claim_id": first["claim_id"]}
        with self.assertRaises(CoordinationError):
            self.ca.change("complete", "TEST-01", "chat-a", result=result, note="Not in main", **key)
        self.run_git(self.a, "push", "origin", result + ":refs/heads/main")
        for owner, task, wrong_result in (("chat-b", "TEST-01", result),
                                           ("chat-a", "TEST-02", result),
                                           ("chat-a", "TEST-01", self.seed)):
            with self.assertRaises(Conflict):
                self.ca.change("complete", task, owner, result=wrong_result, note="Wrong review", **key)
        done = self.ca.change("complete", "TEST-01", "chat-a", result=result, note="Accepted",
                              operation_id="accepted-first", **key)
        board = self.ca.read()[1]
        self.assertEqual(done["stage"], "done")
        self.assertEqual(board["claims"]["TEST-01"], second)
        self.assertEqual(board["reviews"][first["claim_id"]]["stage"], "done")
        retried = self.ca.change("complete", "TEST-01", "chat-a", result=result, note="Retry",
                                 operation_id="accepted-first", **key)
        self.assertEqual(retried, done)
        self.assertEqual(self.ca.read()[1]["sequence"], board["sequence"])

    def test_review_allows_unrelated_files_and_requires_shared_file_ancestry(self):
        first, result = self.submit_result()
        unrelated = self.claim(self.cb, task="TEST-02", owner="chat-b")
        with self.assertRaisesRegex(Conflict, "Include pending result"):
            self.cb.change("heartbeat", "TEST-02", "chat-b", claim_id=unrelated["claim_id"],
                           files=["a.c", "b.c"])
        self.assertEqual(self.ca.read()[1]["claims"]["TEST-02"]["files"], ["b.c"])
        self.include_review(self.b, "codex/chat-b", result)
        extended = self.cb.change("heartbeat", "TEST-02", "chat-b", claim_id=unrelated["claim_id"],
                                  files=["a.c", "b.c"])
        self.assertEqual(extended["based_on_reviews"], [first["claim_id"]])
        with self.assertRaises(Conflict):
            self.claim(task="TEST-03", owner="chat-c", files=["A.c"])

    def test_same_editor_can_continue_with_new_claim_on_same_branch(self):
        first, result = self.submit_result()
        second = self.claim()
        self.assertNotEqual(second["claim_id"], first["claim_id"])
        self.assertEqual(second["based_on_reviews"], [first["claim_id"]])
        self.assertEqual(self.ca.read()[1]["reviews"][first["claim_id"]]["result"], result)

    def test_new_submission_cannot_drop_its_pending_dependency(self):
        first, result = self.submit_result()
        second = self.claim()
        with self.assertRaisesRegex(Conflict, "Include pending result"):
            self.ca.change("review", "TEST-01", "chat-a", claim_id=second["claim_id"],
                           result=self.seed, note="Loses first result")
        board = self.ca.read()[1]
        self.assertEqual(board["claims"]["TEST-01"]["stage"], "in_progress")
        self.assertEqual(board["reviews"][first["claim_id"]]["result"], result)

    def test_multiple_reviews_survive_later_claims_and_acceptance(self):
        first, result = self.submit_result()
        second = self.claim()
        self.run_git(self.a, "commit", "--allow-empty", "-m", "Second portion")
        result2 = self.run_git(self.a, "rev-parse", "HEAD")
        self.run_git(self.a, "push", "origin", "codex/chat-a")
        self.ca.change("review", "TEST-01", "chat-a", claim_id=second["claim_id"],
                       result=result2, note="Second review")
        third = self.claim()
        self.assertEqual(set(third["based_on_reviews"]), {first["claim_id"], second["claim_id"]})
        self.run_git(self.a, "push", "origin", result2 + ":refs/heads/main")
        for c, sha in ((first, result), (second, result2)):
            self.ca.change("complete", "TEST-01", "chat-a", claim_id=c["claim_id"],
                           result=sha, note="Accepted portion")
        board = self.ca.read()[1]
        self.assertEqual(board["claims"]["TEST-01"], third)
        self.assertEqual(len(board["reviews"]), 2)
        self.assertTrue(all(r["stage"] == "done" for r in board["reviews"].values()))

    def test_simultaneous_continuations_have_one_winner(self):
        first, result = self.submit_result()
        self.include_review(self.b, "codex/chat-b", result)
        outcomes = self.race("TEST-01", "TEST-01")
        self.assertEqual(sum(isinstance(o, dict) for o in outcomes), 1)
        self.assertEqual(sum(isinstance(o, Conflict) for o in outcomes), 1)
        self.assertEqual(self.ca.read()[1]["reviews"][first["claim_id"]]["result"], result)

    def test_acceptance_racing_with_new_claim_preserves_new_work(self):
        first, result = self.submit_result()
        self.include_review(self.b, "codex/chat-b", result)
        self.run_git(self.a, "push", "origin", result + ":refs/heads/main")
        producer = self.cb
        new_claim = []
        class ContinuedBeforePush(TaskBoard):
            first_push = True
            def push(self, commit):
                if self.first_push:
                    self.first_push = False
                    new_claim.append(producer.change("claim", "TEST-01", "chat-b", label="chat-b",
                                                     branch="codex/chat-b", note="Continue"))
                return super().push(commit)
        accepted = ContinuedBeforePush(self.a).change(
            "complete", "TEST-01", "chat-a", result=result, claim_id=first["claim_id"], note="Accept old portion")
        board = self.ca.read()[1]
        self.assertEqual(accepted["stage"], "done")
        self.assertEqual(board["claims"]["TEST-01"], new_claim[0])
        self.assertEqual(board["reviews"][first["claim_id"]]["stage"], "done")

    def test_review_ack_after_another_chat_claims_returns_original_submission(self):
        record = self.claim()
        self.run_git(self.a, "push", "origin", self.seed + ":refs/heads/codex/chat-a")
        self.run_git(self.b, "branch", "codex/chat-b", self.seed)
        producer = self.cb
        new_claim = []
        class ClaimedBeforeAck(TaskBoard):
            def push(self, commit):
                result = super().push(commit)
                if result.returncode == 0:
                    new_claim.append(producer.change("claim", "TEST-01", "chat-b", label="chat-b",
                                                     branch="codex/chat-b", note="Continue immediately"))
                return result
        submitted = ClaimedBeforeAck(self.a).change(
            "review", "TEST-01", "chat-a", claim_id=record["claim_id"], result=self.seed,
            note="Review", operation_id="review-with-new-editor")
        self.assertEqual(submitted["claim_id"], record["claim_id"])
        self.assertEqual(submitted["stage"], "review")
        self.assertEqual(self.ca.read()[1]["claims"]["TEST-01"], new_claim[0])
        replay = self.ca.change("review", "TEST-01", "chat-a", claim_id=record["claim_id"],
                                result=self.seed, note="Retry", operation_id="review-with-new-editor")
        self.assertEqual(replay, submitted)

    def test_v1_migration_preserves_active_claims_and_pending_result(self):
        first, result = self.submit_result()
        active = self.claim(task="TEST-02", owner="chat-b")
        blocked = self.ca.change("block", "TEST-02", "chat-b", claim_id=active["claim_id"],
                                 note="Waiting")
        tip, legacy = self.ca.read()
        legacy["schema_version"] = 1
        legacy.pop("reviews")
        for event in legacy["events"]:
            event.pop("record", None)
        self.assertEqual(self.ca.push(self.ca.make_commit(legacy, tip)).returncode, 0)
        read_tip, migrated = self.cb.read()
        self.assertEqual(migrated["schema_version"], 2)
        self.assertEqual(migrated["claims"], legacy["claims"])
        self.assertEqual(migrated["reviews"][first["claim_id"]]["result"], result)
        self.assertEqual(self.ca.read_json(read_tip, "board.json")["schema_version"], 1)
        self.ca.change("heartbeat", "TEST-02", "chat-b", claim_id=active["claim_id"])
        saved = self.ca.read_json(self.ca.fetch_tip("task-board"), "board.json")
        self.assertEqual(saved["schema_version"], 2)
        self.assertEqual(saved["claims"]["TEST-02"]["stage"], blocked["stage"])
        self.assertEqual(saved["claims"]["TEST-02"]["claim_id"], active["claim_id"])
        self.assertEqual(saved["reviews"][first["claim_id"]]["result"], result)
        with self.assertRaises(Conflict):
            self.claim(self.cb, "TEST-02", "chat-c")
        page = render_board(migrated)
        self.assertIn("Свободна для продолжения; порция на проверке", page)
        reserved = page.split("## Зарезервированные файлы", 1)[1].split("## Последние события", 1)[0]
        self.assertNotIn("### TEST-01", reserved)
        self.assertIn("### TEST-02", reserved)

    def test_missing_review_queue_is_rejected(self):
        self.claim()
        tip, board = self.ca.read()
        board.pop("reviews")
        self.assertEqual(self.ca.push(self.ca.make_commit(board, tip)).returncode, 0)
        with self.assertRaisesRegex(CoordinationError, "Missing immutable review queue"):
            self.cb.read()

    def test_linked_worktrees_fetch_without_shared_tracking_ref_updates(self):
        linked = self.root / "linked"
        self.run_git(self.a, "worktree", "add", "-b", "linked", str(linked))
        self.run_git(self.b, "commit", "--allow-empty", "-m", "Remote advance")
        self.run_git(self.b, "push", "origin", "main")
        tip = self.run_git(self.b, "rev-parse", "HEAD")
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(TaskBoard(repo).fetch_tip, "main") for repo in (self.a, linked)]
            self.assertEqual([f.result(timeout=30) for f in futures], [tip, tip])
        self.assertEqual(self.run_git(self.a, "rev-parse", "refs/remotes/origin/main"), self.seed)
        self.assertEqual(self.run_git(self.a, "for-each-ref", "refs/rbm-coordination"), "")

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

    def test_continuation_tracks_main_without_reopening_accepted_work(self):
        path = self.a / "data/project-tasks.json"
        registry = json.loads(path.read_text(encoding="utf-8"))
        task = registry["tasks"][0]
        task.update(current="Model passed", remaining="Connect target input",
                    acceptance="Input reaches shared cycle",
                    continuation={"order": 1, "action": "Bind the input", "chat_id": "prior-chat",
                                  "chat_label": "Input chat"})
        path.write_text(json.dumps(registry), encoding="utf-8")
        self.run_git(self.a, "add", "data/project-tasks.json")
        self.run_git(self.a, "commit", "-m", "Describe continuation")
        result = self.run_git(self.a, "rev-parse", "HEAD")
        self.run_git(self.a, "push", "origin", "main", result + ":refs/heads/codex/chat-a")
        record = self.claim()
        key = {"claim_id": record["claim_id"]}
        self.ca.change("review", "TEST-01", "chat-a", result=result, note="Portion", **key)
        self.ca.change("complete", "TEST-01", "chat-a", result=result, note="Accepted", **key)
        _, before = self.ca.read()
        page = render_board(before)
        self.assertIn("Свободна для продолжения", page)
        self.assertIn("Model passed", page)
        self.assertIn("Connect target input", page)
        self.assertIn("Bind the input", page)
        self.assertIn("Рекомендованный чат — подсказка", page)
        self.assertNotIn("prior-chat", [claim["owner"] for claim in before["claims"].values()])

        task["remaining"] = "Verify reset invalidates old sample"
        task["continuation"]["action"] = "Bind reset to the input"
        path.write_text(json.dumps(registry), encoding="utf-8")
        self.run_git(self.a, "add", "data/project-tasks.json")
        self.run_git(self.a, "commit", "-m", "Update remaining work")
        self.run_git(self.a, "push", "origin", "main")
        _, preview = self.cb.view()
        self.assertIn(task["remaining"], render_board(preview))
        self.assertEqual(preview["claims"], before["claims"])
        self.assertEqual(self.cb.read()[1]["sequence"], before["sequence"])

        self.claim(self.cb, task="TEST-02", owner="chat-b")
        _, published = self.cb.read()
        self.assertEqual(published["claims"]["TEST-01"], before["claims"]["TEST-01"])
        self.assertEqual(published["catalog"][0]["status"], "open")
        self.assertIn(task["remaining"], render_board(published))
        saved_page = self.run_git(self.a, "show", self.ca.fetch_tip("task-board") + ":README.md")
        self.assertIn(task["continuation"]["action"], saved_page)

    def test_busy_continuation_does_not_appear_free_or_take_recommended_owner(self):
        self.claim()
        _, board = self.ca.view()
        board["catalog"][0]["continuation"] = {
            "order": 1, "action": "Continue", "chat_label": "Recommended", "chat_id": "different-chat"}
        page = render_board(board)
        card = page.split("<summary>TEST-01", 1)[1].split("</details>", 1)[0]
        self.assertIn("Выполняется", card)
        self.assertNotIn("Свободна для продолжения", card)
        self.assertIn("**Сейчас выполняет.** chat-a", card)
        self.assertIn("Recommended", card)
        self.assertNotIn("<summary>WAIT-01", page)


if __name__ == "__main__":
    unittest.main()
