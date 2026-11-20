"""Shared chat reservations on a dedicated Git branch.

Each change is a normal fast-forward push of a child of the observed board tip.
Concurrent sibling commits cannot both win. No force push, checkout or index
mutation is used. Reservations are separate from firmware readiness.
"""
import argparse
import copy
from datetime import datetime, timezone
import html
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
ACTIVE = {"in_progress", "blocked", "review"}
STAGES = {
    "in_progress": "Выполняется", "blocked": "Ожидает данных / решения",
    "review": "На проверке", "done": "Порция принята", "released": "Освобождена",
}
PROJECT_WEB = "https://github.com/almirpangor/RBM-Aisin-U340-LFJ8"


class CoordinationError(RuntimeError):
    pass


class Conflict(CoordinationError):
    pass


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean_text(value, name, limit=1500):
    if not value or len(value) > limit or any(ord(c) < 32 for c in value):
        raise CoordinationError(f"Invalid {name}; use nonempty single-line text, at most {limit} characters")
    return value


def edit_paths(values):
    result = set()
    for value in values:
        value = value.replace("\\", "/")
        path = PurePosixPath(value)
        if (not value or path.is_absolute() or ":" in value or ".." in path.parts or
                any(c in value for c in "*?[\r\n\t") or
                not path.parts or path.parts[0].casefold() == ".git"):
            raise CoordinationError(f"Invalid edit reservation: {value!r}")
        normalized = path.as_posix()
        if normalized == ".":
            raise CoordinationError("Reserve specific files or directories, not the whole repository")
        result.add(normalized + ("/" if value.endswith("/") else ""))
    if not result:
        raise CoordinationError("Reserve at least one file or directory")
    return sorted(result)


def intersects(left, right):
    a, b = left.casefold(), right.casefold()
    return (a.rstrip("/") == b.rstrip("/") or
            (a.endswith("/") and b.startswith(a)) or
            (b.endswith("/") and a.startswith(b)))


def cell(value):
    text = html.escape(str(value)).replace("\n", " ")
    for char in "\\|*[]" + chr(96):
        text = text.replace(char, "\\" + char)
    return text


def catalog_entry(task):
    """Carry continuation text from the same published register as readiness."""
    keys = ("id", "title", "status", "current", "remaining", "acceptance", "continuation")
    return {key: copy.deepcopy(task[key]) for key in keys if key in task}


def work_state(task, claim):
    if claim and claim["stage"] in ACTIVE:
        return STAGES[claim["stage"]]
    if task["status"] == "deferred":
        return "Отложена владельцем"
    if task["status"] == "closed":
        return "Закрыта по текущему объёму"
    return "Свободна для продолжения"


def render_continuations(board):
    tasks = [task for task in board["catalog"] if task["status"] not in ("closed", "deferred")]
    if not tasks:
        return []
    tasks.sort(key=lambda task: (task.get("continuation", {}).get("order", 1000), task["id"]))
    base = PROJECT_WEB + "/blob/" + board["main_commit"]
    lines = [
        "## Что осталось доделать", "",
        "Продолжения относятся к тем же ID задач. Номер пункта не назначает чат.",
        "Рекомендованный чат — подсказка для продолжения прежнего направления, а не резерв.",
        "Сначала обновить свою копию из main, посмотреть список и занять задачу с точными файлами.",
        "Активный исполнитель и пересекающиеся файлы защищены общим резервом.", "",
        "| Задача | Сейчас | Следующий шаг | Кому удобно продолжить |",
        "| --- | --- | --- | --- |",
    ]
    for task in tasks:
        follow = task.get("continuation")
        if follow:
            link = f"[{task['id']}]({base}/docs/project-map.md#{task['id'].lower()})"
            lines.append("| " + " | ".join((
                link, cell(work_state(task, board["claims"].get(task["id"]))),
                cell(follow["action"]), cell(follow.get("chat_label", "Любой свободный чат")),
            )) + " |")
    lines.extend(["", "### Сделано и остаток по каждой незакрытой задаче", ""])
    for task in tasks:
        claim = board["claims"].get(task["id"])
        follow = task.get("continuation", {})
        lines.extend([
            "<details>",
            f"<summary>{cell(task['id'] + ' — ' + task['title'])}: {cell(work_state(task, claim))}</summary>", "",
            "**Сделано.** " + cell(task.get("current", "См. карточку в main.")), "",
            "**Осталось доделать.** " + cell(task.get("remaining", "См. карточку в main.")), "",
        ])
        if follow:
            lines.extend(["**Следующий шаг.** " + cell(follow["action"]), ""])
            if follow.get("chat_id"):
                lines.extend(["**Рекомендуемый чат.** " + cell(follow["chat_label"]) +
                              " — " + cell(follow["chat_id"]) + ".", ""])
        if claim and claim["stage"] in ACTIVE:
            lines.extend(["**Сейчас выполняет.** " + cell(claim["label"]) +
                          " — " + cell(claim["owner"]) + ".", ""])
        else:
            lines.extend(["**Исполнитель сейчас.** Задача не занята.", ""])
        lines.extend([
            "**Критерий приёмки.** " + cell(task.get("acceptance", "См. карточку в main.")), "",
            f"[Код, настройки, зависимости и проверки]({base}/docs/project-map.md#{task['id'].lower()})",
            "", "</details>", "",
        ])
    return lines


def render_board(board):
    lines = [
        "# Кто сейчас работает над проектом", "",
        f"Обновлено UTC: **{board['updated_at']}**. Изменение № **{board['sequence']}**.", "",
        "Это общий учёт исполнителей. Он не меняет готовность функции по ТЗ и не подтверждает выпуск BIN.",
        "Команды занятия и обновления задачи — в tools/task_coordination.py основной ветки.",
        "Задача и пересекающиеся файлы удерживаются в состояниях «Выполняется», «Ожидает» и «На проверке».",
        "Давняя отметка не освобождается автоматически. Возобновившийся чат обязан проверить свой claim_id.", "",
        f"Каталог задач взят из main {board['main_commit']}.", "",
        "| Задача | Ход работы | Текущий / предыдущий чат | Ветка | Обновление UTC | Что делает / результат |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for task in board["catalog"]:
        claim = board["claims"].get(task["id"])
        title = f"{task['id']} — {task['title']}"
        if not claim:
            state = work_state(task, claim)
            lines.append(f"| {cell(title)} | {state} | — | — | — | — |")
        else:
            note = claim["note"]
            if claim["stage"] == "done":
                note = "Предыдущая порция принята. " + note
            if claim.get("result"):
                note += " / commit " + claim["result"]
            lines.append("| " + " | ".join(map(cell, (
                title, work_state(task, claim),
                ("" if claim["stage"] in ACTIVE else "Предыдущий: ") + claim["label"] + " [" + claim["owner"] + "]",
                claim["branch"], claim["updated_at"], note))) + " |")
    lines.extend(["", *render_continuations(board)])
    lines.extend(["", "## Зарезервированные файлы", ""])
    for task_id, claim in sorted(board["claims"].items()):
        if claim["stage"] in ACTIVE:
            lines.extend([
                f"### {task_id}", "",
                f"Чат: {cell(claim['label'])}. Claim ID: {claim['claim_id']}.", "",
                *("- " + cell(name) for name in claim["files"]), "",
            ])
    lines.extend(["## Последние события", "",
                  "| UTC | Задача | Действие | Чат |", "| --- | --- | --- | --- |"])
    for event in reversed(board["events"][-30:]):
        lines.append("| " + " | ".join(cell(event[key]) for key in ("at", "task", "action", "owner")) + " |")
    return "\n".join(lines) + "\n"


class TaskBoard:
    def __init__(self, repo=ROOT, remote="origin", branch="task-board", main="main"):
        self.repo = Path(repo).resolve()
        self.remote, self.branch, self.main = remote, branch, main
        if branch == main:
            raise CoordinationError("Coordination branch must differ from the code branch")
        for name in (branch, main):
            self.git("check-ref-format", "--branch", name)
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", remote) or remote.startswith("-"):
            raise CoordinationError("Use a configured remote name")
        self.git("remote", "get-url", remote)

    def git(self, *args, input_data=None, check=True):
        result = subprocess.run(
            ["git", "-C", str(self.repo), *args], input=input_data,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        if check and result.returncode:
            raise CoordinationError(result.stderr.decode("utf-8", "replace").strip() or
                                    f"git {args[0]} failed ({result.returncode})")
        return result

    def fetch_tip(self, branch, optional=False):
        remote_ref = f"refs/heads/{branch}"
        found = self.git("ls-remote", "--exit-code", "--heads", self.remote, remote_ref, check=False)
        if found.returncode == 2 and optional:
            return None
        if found.returncode:
            raise CoordinationError(found.stderr.decode("utf-8", "replace").strip() or
                                    f"Remote branch does not exist: {branch}")
        private_ref = "refs/rbm-coordination/" + uuid.uuid4().hex
        try:
            self.git("fetch", "--quiet", "--no-tags", "--no-write-fetch-head",
                     "--refmap=", self.remote, f"{remote_ref}:{private_ref}")
            return self.git("rev-parse", private_ref).stdout.decode().strip()
        finally:
            self.git("update-ref", "-d", private_ref, check=False)

    def read_json(self, revision, file):
        try:
            return json.loads(self.git("show", f"{revision}:{file}").stdout)
        except (ValueError, UnicodeDecodeError) as error:
            raise CoordinationError(f"Invalid JSON at {revision}:{file}") from error

    def catalog(self):
        tip = self.fetch_tip(self.main)
        registry = self.read_json(tip, "data/project-tasks.json")
        return tip, registry["tasks"]

    def read(self):
        tip = self.fetch_tip(self.branch, optional=True)
        if tip is None:
            return None, {"schema_version": 1, "sequence": 0, "claims": {}, "events": []}
        names = set(self.git("ls-tree", "--name-only", tip).stdout.decode().splitlines())
        if names != {"board.json", "README.md"}:
            raise CoordinationError("Unexpected coordination branch contents; refusing to replace them")
        board = self.read_json(tip, "board.json")
        if board.get("schema_version") != 1 or not isinstance(board.get("claims"), dict):
            raise CoordinationError("Unsupported coordination board")
        return tip, board

    def view(self):
        tip, board = self.read()
        main, tasks = self.catalog()
        board.update(main_commit=main, catalog=[catalog_entry(task) for task in tasks])
        board.setdefault("updated_at", "ещё нет записей")
        return tip, board

    def ensure_published(self, commit, branch):
        if not commit or not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise CoordinationError("Supply a full, published commit SHA")
        tip = self.fetch_tip(branch)
        if self.git("merge-base", "--is-ancestor", commit, tip, check=False).returncode:
            raise CoordinationError(f"Result commit is not published in {branch}")

    def make_commit(self, board, parent):
        contents = {
            "board.json": (json.dumps(board, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
            "README.md": render_board(board).encode("utf-8"),
        }
        tree_lines = []
        for name, content in sorted(contents.items()):
            oid = self.git("hash-object", "-w", "--stdin", input_data=content).stdout.decode().strip()
            tree_lines.append(f"100644 blob {oid}\t{name}\n")
        tree = self.git("mktree", input_data="".join(tree_lines).encode()).stdout.decode().strip()
        parents = ["-p", parent] if parent else []
        message = f"Task board #{board['sequence']}: {board['events'][-1]['action']} {board['events'][-1]['task']}\n"
        return self.git("commit-tree", tree, *parents, input_data=message.encode()).stdout.decode().strip()

    def push(self, commit):
        # Never force a board update. A concurrent sibling must be rejected.
        return self.git("push", "--porcelain", self.remote,
                        f"{commit}:refs/heads/{self.branch}", check=False)

    def change(self, action, task_id, owner, *, claim_id=None, label=None, branch=None,
               files=None, note=None, result=None, operation_id=None):
        owner = clean_text(owner, "owner", 160)
        task_id = task_id.upper()
        if not re.fullmatch(r"[A-Z][A-Z0-9]+-[0-9]{2}", task_id):
            raise CoordinationError("Invalid task ID")
        op_id = operation_id or uuid.uuid4().hex
        new_claim_id = uuid.uuid4().hex
        main, tasks = self.catalog()
        task = next((task for task in tasks if task["id"] == task_id), None)
        if task is None:
            raise CoordinationError(f"No such task in remote main: {task_id}")
        if note is not None:
            clean_text(note, "note")
        if action in {"claim", "block", "review", "complete", "release"} and not note:
            raise CoordinationError("This action requires a note")
        if action == "claim":
            if task["status"] == "deferred":
                raise Conflict(f"{task_id} is deferred by the owner")
            label = clean_text(label, "chat label", 160)
            if not branch:
                raise CoordinationError("Specify the working branch")
            self.git("check-ref-format", "--branch", branch)
            if branch == self.branch:
                raise CoordinationError("Do not use the coordination branch for code")
            files = edit_paths(files if files is not None else task["code"])
        elif action not in {"heartbeat", "resume", "block", "review", "complete", "release"}:
            raise CoordinationError(f"Unknown action: {action}")
        elif files is not None:
            files = edit_paths(files)

        for _ in range(8):
            parent, observed = self.read()
            if any(event["operation_id"] == op_id for event in observed["events"]):
                return observed["claims"][task_id]
            board = copy.deepcopy(observed)
            previous = board["claims"].get(task_id)
            now = utc_now()
            if action == "claim":
                if previous and previous["stage"] in ACTIVE:
                    raise Conflict(f"{task_id} is held by {previous['label']} [{previous['owner']}]")
                record = {
                    "owner": owner, "label": label, "branch": branch, "files": files,
                    "stage": "in_progress", "claim_id": new_claim_id,
                    "claimed_at": now, "updated_at": now, "note": note, "result": None,
                }
            else:
                if (not previous or previous["stage"] not in ACTIVE or previous["owner"] != owner or
                        previous["claim_id"] != claim_id):
                    raise Conflict("Claim is absent, finished or owned by another chat/generation")
                record = copy.deepcopy(previous)
                if files is not None:
                    record["files"] = files
                if note is not None:
                    record["note"] = note
                if action == "review":
                    self.ensure_published(result, record["branch"])
                    record.update(stage="review", result=result)
                elif action == "complete":
                    if previous["stage"] != "review" or result != previous.get("result"):
                        raise Conflict("Complete only the exact result currently under review")
                    self.ensure_published(result, self.main)
                    record.update(stage="done", result=result)
                elif action in {"resume", "block", "release"}:
                    record["stage"] = {"resume": "in_progress", "block": "blocked", "release": "released"}[action]
                    if action != "release":
                        record["result"] = None
                elif (action == "heartbeat" and files is not None and
                      files != previous["files"] and previous["stage"] == "review"):
                    # New work invalidates the previous review, but keeps the reservation.
                    record.update(stage="in_progress", result=None)
                record["updated_at"] = now
            if record["stage"] in ACTIVE:
                for other_id, other in board["claims"].items():
                    if other_id == task_id or other["stage"] not in ACTIVE:
                        continue
                    if record["branch"] == other["branch"]:
                        raise Conflict(f"Branch {record['branch']} is held by {other_id} ({other['label']})")
                    overlap = [(a, b) for a in record["files"] for b in other["files"] if intersects(a, b)]
                    if overlap:
                        raise Conflict(f"Files conflict with {other_id} ({other['label']}): {overlap}")
            board["claims"][task_id] = record
            board.update(updated_at=now, main_commit=main, sequence=board["sequence"] + 1,
                         catalog=[catalog_entry(task) for task in tasks])
            board["events"].append({
                "operation_id": op_id, "task": task_id, "owner": owner,
                "action": action, "claim_id": record["claim_id"], "at": now,
            })
            commit = self.make_commit(board, parent)
            pushed = self.push(commit)
            # An interrupted push may already have reached the remote.
            tip, confirmed = self.read()
            if any(event["operation_id"] == op_id for event in confirmed["events"]):
                return confirmed["claims"][task_id]
            if pushed.returncode == 0:
                raise CoordinationError("Push succeeded but the operation is absent from the remote board")
            if tip == parent:
                raise CoordinationError(pushed.stderr.decode("utf-8", "replace").strip() or "Push rejected")
        raise CoordinationError("Board changed repeatedly; inspect the live state and retry")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--board-branch", default="task-board")
    parser.add_argument("--main-branch", default="main")
    sub = parser.add_subparsers(dest="action", required=True)
    listing = sub.add_parser("list")
    listing.add_argument("--json", action="store_true")
    for action in ("claim", "heartbeat", "resume", "block", "review", "complete", "release"):
        command = sub.add_parser(action)
        command.add_argument("task")
        command.add_argument("--owner", required=True, help="Unique chat ID, not shared GitHub login")
        command.add_argument("--note", required=action in {"claim", "block", "review", "complete", "release"})
        if action == "claim":
            command.add_argument("--label", required=True, help="Human-readable chat name")
            command.add_argument("--branch", required=True, help="Separate working branch for this chat")
        else:
            command.add_argument("--claim-id", required=True, help="ID returned by successful claim")
        if action in {"claim", "heartbeat", "resume"}:
            command.add_argument("--files", nargs="+", help="File or directory/ reservations; defaults to task.code")
        if action in {"review", "complete"}:
            command.add_argument("--result", required=True, help="Full published commit SHA")
    args = parser.parse_args()
    try:
        board = TaskBoard(args.repo, args.remote, args.board_branch, args.main_branch)
        if args.action == "list":
            _, snapshot = board.view()
            print(json.dumps(snapshot, ensure_ascii=False, indent=2) if args.json else render_board(snapshot))
        else:
            kwargs = {key: getattr(args, key) for key in
                      ("claim_id", "label", "branch", "files", "note", "result") if hasattr(args, key)}
            record = board.change(args.action, args.task, args.owner, **kwargs)
            print(json.dumps(record, ensure_ascii=False, indent=2))
        return 0
    except (CoordinationError, OSError, ValueError, KeyError, TypeError) as error:
        print(f"Coordination failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
