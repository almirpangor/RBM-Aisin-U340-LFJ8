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
SCHEMA_VERSION = 2
ACTIVE = {"in_progress", "blocked"}
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
    keys = ("id", "title", "status", "current", "remaining", "acceptance", "continuation", "depends")
    return {key: copy.deepcopy(task[key]) for key in keys if key in task}


def upgrade_board(board):
    """Preserve v1 submissions when separating them from editing leases."""
    if not isinstance(board, dict) or not isinstance(board.get("claims"), dict):
        raise CoordinationError("Invalid coordination board")
    version = board.get("schema_version")
    if version not in (1, SCHEMA_VERSION):
        raise CoordinationError("Unsupported coordination board; update tools/task_coordination.py from main")
    board = copy.deepcopy(board)
    if version == 1:
        board["schema_version"] = SCHEMA_VERSION
        board["reviews"] = {}
        for task_id, claim in board["claims"].items():
            if claim["stage"] == "review":
                board["reviews"][claim["claim_id"]] = {
                    **copy.deepcopy(claim), "task": task_id,
                    "submitted_at": claim["updated_at"],
                }
    if not isinstance(board.get("reviews"), dict):
        raise CoordinationError("Missing immutable review queue")
    for key, review in board["reviews"].items():
        if (key != review.get("claim_id") or review.get("stage") not in ("review", "done") or
                not re.fullmatch(r"[0-9a-f]{40}", review.get("result") or "") or
                not review.get("task") or not review.get("owner") or not review.get("branch")):
            raise CoordinationError("Invalid saved review")
    for task_id, claim in board["claims"].items():
        if claim["stage"] == "review":
            review = board["reviews"].get(claim["claim_id"])
            if not review or any(review.get(k) != claim.get(k) for k in ("owner", "result", "stage")) or review["task"] != task_id:
                raise CoordinationError("Submitted claim has no matching review")
    return board


def work_state(task, claim):
    if claim and claim["stage"] in ACTIVE:
        return STAGES[claim["stage"]]
    if claim and claim["stage"] == "review":
        return "Свободна для продолжения; порция на проверке"
    if task["status"] == "deferred":
        return "Отложена владельцем"
    if task["status"] == "closed":
        return "Закрыта по текущему объёму"
    return "Свободна для продолжения"


def task_order(task):
    return task.get("continuation", {}).get("order", 1000), task["id"]


def render_continuations(board):
    tasks = [task for task in board["catalog"] if task["status"] not in ("closed", "deferred")]
    if not tasks:
        return []
    tasks.sort(key=task_order)
    base = PROJECT_WEB + "/blob/" + board["main_commit"]
    lines = [
        "## Что осталось доделать", "",
        "Продолжения относятся к тем же ID задач. Номер пункта не назначает чат.",
        "Рекомендованный чат — подсказка для продолжения прежнего направления, а не резерв.",
        "Сначала обновить свою копию из main, посмотреть список и занять задачу с точными файлами.",
        "Активный исполнитель и пересекающиеся файлы защищены общим резервом.", "",
        "Порядок задаёт приоритет продолжения. Зависимости нужны для итоговой приёмки; независимую часть можно делать сразу.",
        "Свободная задача может требовать ещё не полученных данных. Их отсутствие фиксируется отдельно от готовности кода.",
        f"[Подробное распределение и единый текст для Codex / Claude]({base}/docs/integration-next-tasks.md)", "",
        "| Приоритет | Задача | Занятость | Что сдать | Зависимости приёмки |",
        "| --- | --- | --- | --- | --- |",
    ]
    for task in tasks:
        follow = task.get("continuation", {})
        link = f"[{task['id']}]({base}/docs/project-map.md#{task['id'].lower()})"
        needs = ", ".join(task.get("depends", [])) or "См. входные условия карточки"
        lines.append("| " + " | ".join((
            str(follow.get("order", "—")), link,
            cell(work_state(task, board["claims"].get(task["id"]))),
            cell(follow.get("deliverable", follow.get("action", task.get("remaining", task["title"])))),
            cell(needs),
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
            for key, label in (("inputs", "Исходные условия"), ("deliverable", "Что сдать")):
                if follow.get(key):
                    lines.extend([f"**{label}.** " + cell(follow[key]), ""])
            if follow.get("chat_id"):
                lines.extend(["**Рекомендуемый чат.** " + cell(follow["chat_label"]) +
                              " — " + cell(follow["chat_id"]) + ".", ""])
        if claim and claim["stage"] in ACTIVE:
            label = "Сейчас выполняет" if claim["stage"] == "in_progress" else "Резерв удерживает"
            lines.extend([f"**{label}.** " + cell(claim["label"]) +
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
    ordered = sorted(board["catalog"], key=task_order)
    working = [t for t in ordered if board["claims"].get(t["id"], {}).get("stage") == "in_progress"]
    waiting = [t for t in ordered if board["claims"].get(t["id"], {}).get("stage") == "blocked"]
    pending = [r for r in board.get("reviews", {}).values() if r["stage"] == "review"]
    lines = [
        "# Кто сейчас работает над проектом", "",
        f"Обновлено UTC: **{board['updated_at']}**. Изменение № **{board['sequence']}**.", "",
        "Это общий учёт исполнителей. Он не меняет готовность функции по ТЗ и не подтверждает выпуск BIN.",
        "Команды занятия и обновления задачи — в tools/task_coordination.py основной ветки.",
        "Задача и файлы заняты только в состояниях «Выполняется» и «Ожидает».",
        "«На проверке» сохраняет сданный коммит в отдельной очереди и освобождает резерв для продолжения.",
        "Для продолжения включить относящиеся к задаче или файлам сданные коммиты в свою ветку и выполнить новый claim.",
        "Нужен tools/task_coordination.py из актуальной main: старые клиенты не записывают формат доски 2.",
        "Давняя отметка не освобождается автоматически. Возобновившийся чат обязан проверить свой claim_id.", "",
        f"Каталог задач взят из main {board['main_commit']}.", "",
        f"**В работе: {len(working)} · Ожидают с резервом: {len(waiting)} · Порций на проверке: {len(pending)}.**", "",
        "Занятость определяется подтверждёнными резервами, а не присутствием чата онлайн. Предыдущие исполнители вынесены в историю.", "",
    ]
    for heading, tasks, empty in (
        ("Сейчас выполняются", working, "Нет действующих резервов выполнения."),
        ("Ожидают — резерв сохранён", waiting, "Нет задач, удерживаемых в ожидании."),
    ):
        lines.extend(["## " + heading, ""])
        if not tasks:
            lines.extend([empty, ""])
            continue
        lines.extend(["| Приоритет | Задача | Исполнитель | Обновление UTC | Текущий шаг / причина ожидания |",
                      "| --- | --- | --- | --- | --- |"])
        for task in tasks:
            claim = board["claims"][task["id"]]
            lines.append("| " + " | ".join(map(cell, (
                task.get("continuation", {}).get("order", "—"),
                task["id"] + " — " + task["title"], claim["label"] + " [" + claim["owner"] + "]",
                claim["updated_at"], claim["note"]))) + " |")
        lines.append("")
    lines.extend(["", "## Результаты на проверке — резерв свободен", "",
                  "Эти результаты остаются доступны интегратору, даже если другой чат уже продолжает задачу.",
                  "Новый исполнитель сначала включает нужные коммиты в свою ветку. claim проверяет их наличие.", "",
                  "| Задача | Автор | Коммит | Claim ID для приёмки | Результат |",
                  "| --- | --- | --- | --- | --- |"])
    for review in sorted(pending, key=lambda r: (r["task"], r["submitted_at"], r["claim_id"])):
        commit = f"[{review['result'][:12]}]({PROJECT_WEB}/commit/{review['result']})"
        lines.append("| " + " | ".join((cell(review["task"]), cell(review["label"]), commit,
                                      cell(review["claim_id"]), cell(review["note"]))) + " |")
    if not pending:
        lines.extend(["", "Очередь проверки пуста."])
    lines.extend(["", *render_continuations(board)])
    lines.extend(["## История предыдущих исполнителей", "", "<details>",
                  "<summary>Принятые, сданные и освобождённые порции — это не текущая работа</summary>", "",
                  "| Задача | Состояние порции | Предыдущий исполнитель | Ветка | Результат |",
                  "| --- | --- | --- | --- | --- |"])
    for task in ordered:
        claim = board["claims"].get(task["id"])
        if claim and claim["stage"] not in ACTIVE:
            note = claim["note"] + (" / commit " + claim["result"] if claim.get("result") else "")
            lines.append("| " + " | ".join(map(cell, (task["id"], STAGES[claim["stage"]],
                claim["label"], claim["branch"], note))) + " |")
    lines.extend(["", "</details>", ""])
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
            return None, {"schema_version": SCHEMA_VERSION, "sequence": 0,
                          "claims": {}, "reviews": {}, "events": []}
        names = set(self.git("ls-tree", "--name-only", tip).stdout.decode().splitlines())
        if names != {"board.json", "README.md"}:
            raise CoordinationError("Unexpected coordination branch contents; refusing to replace them")
        board = self.read_json(tip, "board.json")
        return tip, upgrade_board(board)

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

    def pending_dependencies(self, board, task_id, files):
        return sorted(key for key, review in board["reviews"].items()
                      if review["stage"] == "review" and
                      (review["task"] == task_id or
                       any(intersects(a, b) for a in files for b in review["files"])))

    def ensure_dependencies(self, board, dependencies, revision):
        for key in dependencies:
            review = board["reviews"][key]
            commit = review["result"]
            if self.git("cat-file", "-e", commit + "^{commit}", check=False).returncode:
                self.ensure_published(commit, review["branch"])
            if self.git("merge-base", "--is-ancestor", commit, revision, check=False).returncode:
                raise Conflict(f"Include pending result {review['task']} {commit} from {review['branch']} "
                               f"in {revision} before continuing; the review does not reserve these files")

    @staticmethod
    def operation_result(board, operation_id):
        event = next((e for e in board["events"] if e["operation_id"] == operation_id), None)
        if event is None:
            return None
        if "record" in event:
            return copy.deepcopy(event["record"])
        # Compatibility for an acknowledgement retry from before migration.
        record = board["claims"].get(event["task"])
        if record and record["claim_id"] == event["claim_id"]:
            return copy.deepcopy(record)
        raise CoordinationError("The old operation succeeded, but its claim has since changed; inspect list")

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
            already = self.operation_result(observed, op_id)
            if already is not None:
                return already
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
            elif action == "complete":
                submitted = board["reviews"].get(claim_id)
                if (not submitted or submitted["stage"] != "review" or
                        submitted["task"] != task_id or submitted["owner"] != owner or
                        submitted["result"] != result):
                    raise Conflict("Complete only the exact saved review, using its original owner and claim_id")
                self.ensure_published(result, self.main)
                record = copy.deepcopy(submitted)
                record.update(stage="done", updated_at=now, note=note)
                board["reviews"][claim_id] = record
                # A reviewer accepts the immutable submission, never the
                # next editor's reservation of the same task.
                if previous and previous["claim_id"] == claim_id:
                    board["claims"][task_id] = {**previous, "stage": "done",
                                                "updated_at": now, "note": note}
            else:
                if (not previous or previous["stage"] not in ACTIVE or previous["owner"] != owner or
                        previous["claim_id"] != claim_id):
                    raise Conflict("No matching active reservation. A submitted review releases its lease; "
                                   "continue with a new claim and current files/branch")
                record = copy.deepcopy(previous)
                if files is not None:
                    record["files"] = files
                if note is not None:
                    record["note"] = note
                if action == "review":
                    self.ensure_published(result, record["branch"])
                    self.ensure_dependencies(board, record.get("based_on_reviews", []), result)
                    record.update(stage="review", result=result)
                elif action in {"resume", "block", "release"}:
                    record["stage"] = {"resume": "in_progress", "block": "blocked", "release": "released"}[action]
                    if action != "release":
                        record["result"] = None
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
                if action == "claim" or files is not None:
                    dependencies = sorted(set(record.get("based_on_reviews", [])) |
                                          set(self.pending_dependencies(board, task_id, record["files"])))
                    self.ensure_dependencies(board, dependencies, "refs/heads/" + record["branch"])
                    record["based_on_reviews"] = dependencies
            if action != "complete":
                board["claims"][task_id] = record
            if action == "review":
                board["reviews"][record["claim_id"]] = {
                    **copy.deepcopy(record), "task": task_id, "submitted_at": now,
                }
            board.update(updated_at=now, main_commit=main, sequence=board["sequence"] + 1,
                         catalog=[catalog_entry(task) for task in tasks])
            board["events"].append({
                "operation_id": op_id, "task": task_id, "owner": owner,
                "action": action, "claim_id": record["claim_id"], "at": now,
                "record": copy.deepcopy(record),
            })
            commit = self.make_commit(board, parent)
            pushed = self.push(commit)
            # An interrupted push may already have reached the remote.
            tip, confirmed = self.read()
            saved = self.operation_result(confirmed, op_id)
            if saved is not None:
                return saved
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
