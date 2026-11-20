"""Single task register, generated navigation and audit freshness checks.

This command never builds firmware, flashes hardware or changes an audit snapshot.
A successful --check means the register and recorded evidence are consistent.
It does not declare the target firmware ready.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
REGISTER = ROOT / "data/project-tasks.json"
START = "<!-- PROJECT-STATUS:START -->"
END = "<!-- PROJECT-STATUS:END -->"


def digest(path, normalize=False):
    content = path.read_bytes()
    if normalize:
        content = content.replace(b"\r\n", b"\n")
    return hashlib.sha256(content).hexdigest()


def source_files(normalize=False):
    """Include production code, fixtures and all local verification tools."""
    result = {}
    for directory in ("controller", "targets", "diagnostics", "model", "tests", "tools"):
        for path in sorted((ROOT / directory).rglob("*")):
            if path.is_file() and path.suffix in (".c", ".h", ".S", ".py"):
                result[path.relative_to(ROOT).as_posix()] = digest(path, normalize)
    path = ROOT / "controller/vendor/toyota/manifest.json"
    result[path.relative_to(ROOT).as_posix()] = digest(path, normalize)
    return dict(sorted(result.items()))


def local_file(value):
    path = Path(value)
    if path.is_absolute() or "\\" in value or ":" in value or ".." in path.parts:
        raise ValueError(f"Path must be relative to the project: {value}")
    resolved = (ROOT / path).resolve()
    if ROOT.resolve() not in resolved.parents or not resolved.is_file():
        raise ValueError(f"Missing project file: {value}")
    return resolved


def validate(data):
    expected = set(range(1, 12))
    if {section["id"] for section in data["sections"]} != expected:
        raise ValueError("The register must cover specification sections 1 through 11")
    tasks = data["tasks"]
    ids = [task["id"] for task in tasks]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate task ID")
    lookup = {task["id"]: task for task in tasks}
    covered = set()
    for task in tasks:
        if not re.fullmatch(r"[A-Z][A-Z0-9]+-[0-9]{2}", task["id"]):
            raise ValueError(f"Invalid task ID: {task['id']}")
        if task["status"] not in data["status_labels"]:
            raise ValueError(f"Unknown task status: {task['id']}")
        for key in ("title", "current", "remaining", "acceptance", "settings"):
            if not isinstance(task[key], str) or not task[key].strip():
                raise ValueError(f"Empty {key}: {task['id']}")
        follow = task.get("continuation")
        if follow is not None:
            if (not isinstance(follow, dict) or task["status"] in ("closed", "deferred") or
                    not isinstance(follow.get("action"), str) or not follow["action"].strip() or
                    type(follow.get("order")) is not int or follow["order"] < 1):
                raise ValueError(f"Invalid continuation: {task['id']}")
            if "chat_id" in follow and (
                    not isinstance(follow["chat_id"], str) or
                    not re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", follow["chat_id"]) or
                    not isinstance(follow.get("chat_label"), str) or not follow["chat_label"].strip()):
                raise ValueError(f"Invalid continuation chat: {task['id']}")
            for key in ("inputs", "deliverable"):
                if key in follow and (not isinstance(follow[key], str) or not follow[key].strip()):
                    raise ValueError(f"Invalid continuation {key}: {task['id']}")
        if not task["sections"] or not set(task["sections"]) <= expected:
            raise ValueError(f"Invalid specification section: {task['id']}")
        covered.update(task["sections"])
        for key in ("code", "docs"):
            if not task[key]:
                raise ValueError(f"Missing {key}: {task['id']}")
            for value in task[key]:
                local_file(value)
        if task["status"] in ("closed", "model") and not task["checks"]:
            raise ValueError(f"Missing checks for stated result: {task['id']}")
        for check in task["checks"]:
            if check not in data["checks"]:
                raise ValueError(f"Unknown check {check}: {task['id']}")
        for dependency in task["depends"]:
            if dependency not in lookup or dependency == task["id"]:
                raise ValueError(f"Unknown or self dependency: {task['id']} -> {dependency}")
    if covered != expected:
        raise ValueError("Some specification sections have no tasks")
    seen, active = set(), set()

    def visit(name):
        if name in active:
            raise ValueError(f"Cyclic dependency at {name}")
        if name not in seen:
            active.add(name)
            for dependency in lookup[name]["depends"]:
                visit(dependency)
            active.remove(name)
            seen.add(name)
    for name in lookup:
        visit(name)
    for name in data["next"]:
        if name not in lookup or lookup[name]["status"] in ("closed", "deferred"):
            raise ValueError(f"Invalid next task: {name}")
    for module in data["modules"]:
        local_file(module["entry"])
        if not (ROOT / module["path"]).is_dir():
            raise ValueError(f"Missing module: {module['path']}")
    for check in data["checks"].values():
        if not check["command"] or not check["reports"]:
            raise ValueError("Each check requires its command and evidence")
        for report in check["reports"]:
            local_file(report)
    if data["release_ready"] and any(task["status"] not in ("closed", "deferred") for task in tasks):
        raise ValueError("An open task prevents claiming release readiness")
    source_index = json.loads((ROOT / "data/sources.json").read_text(encoding="utf-8"))
    h03 = next(entry for entry in source_index["supporting_materials"] if entry["id"] == "H03")
    if data["target"]["sha256"] != h03["sha256"]:
        raise ValueError("Task register and active H03 source disagree")


def mdlink(path, prefix="", label=None):
    return f"[{label or Path(path).name}]({prefix}{path})"


def counts(data):
    count = Counter(task["status"] for task in data["tasks"])
    return " · ".join(f"{label}: **{count[state]}**" for state, label in data["status_labels"].items())


def render_status(data):
    tasks = data["tasks"]
    lookup = {task["id"]: task for task in tasks}
    lines = [
        START,
        "## Состояние проекта",
        "",
        f"Сверка **{data['date']}**. Цель — **{data['target']['tcm']} / {data['target']['gearbox']}**, основа **{data['target']['base']}**.",
        "",
        "**Рабочий BIN не выпущен.** Проверочные ELF и Bosch OFFLINE_ONLY не являются готовым комплектом для автомобиля.",
        "",
        f"**{len(tasks)} подзадачи.** {counts(data)}.",
        "",
        "Счётчик относится к подзадачам разного размера, поэтому не является процентом готовности прошивки. «Проверено программно» означает только сценарии, перечисленные в карточке. Аппаратная приёмка новой пары не выполнена.",
        "",
        "[Подзадачи и карта кода](docs/project-map.md) · [Отчёт повторной сверки](docs/project-audit-2026-11-20.md) · [Подробные доказательства по ТЗ](docs/working-set.md)",
        "",
        "| ТЗ | Что требуется | На данный момент | Подзадачи |",
        "| --- | --- | --- | --- |",
    ]
    for section in data["sections"]:
        # Keep the front page compact; cross-section dependencies live in the cards.
        refs = ", ".join(f"[{t['id']}](docs/project-map.md#{t['id'].lower()})"
                         for t in tasks if t["id"].split("-")[0] in section["prefixes"])
        lines.append(f"| §{section['id']} | {section['title']} | {section['summary']} | {refs} |")
    lines.extend([
        "| Выпуск | Два BIN, манифест, подключение и проверка | Открыт. Образ TCM для записи ещё не собран. | [REL-01](docs/project-map.md#rel-01), [REL-02](docs/project-map.md#rel-02) |",
        "",
        "### Куда идти дальше",
        "",
    ])
    for index, name in enumerate(data["next"], 1):
        task = lookup[name]
        lines.append(f"{index}. [{name}: {task['title']}](docs/project-map.md#{name.lower()}). {task['remaining']}")
    lines.extend([
        "",
        "Этот порядок относится к доступной программной работе. Незакрытая зависимость ограничивает интеграцию, но не мешает отдельно исследовать модуль. Физические ограничения перечислены в карточках и в [протоколе приёмки](docs/lfj8-9e1c-minimum-bench.md).",
        "",
        "### Быстрое продолжение",
        "",
        "```powershell",
        "python -B tools/project_status.py --check",
        "python -B tools/project_status.py --task DTC-02",
        "```",
        "",
        "Первая команда проверяет ссылки, зависимости, актуальность карты и контрольные суммы проверенного кода/отчётов. Она не повторяет симуляции. Вторая показывает точные файлы, настройки, ограничения и команды выбранной подзадачи. При изменении кода повторяются затронутые проверки.",
        "",
        "Статусы редактируются в [едином реестре](data/project-tasks.json), затем страницы обновляются командой `python -B tools/project_status.py --write`. Сам отчёт проверки этой командой не обновляется.",
        END,
    ])
    return "\n".join(lines)


def render_map(data):
    tasks = sorted(data["tasks"], key=lambda task: (
        2 if task["status"] == "deferred" else 1 if task["status"] == "closed" else 0,
        task.get("continuation", {}).get("order", 1000), task["id"]))
    lines = [
        "# Подзадачи и карта кода",
        "",
        "Сгенерировано из [data/project-tasks.json](../data/project-tasks.json). Изменять реестр, затем запускать `python -B tools/project_status.py --write`.",
        "",
        "[Главная страница](../README.md) · [Результат сверки](project-audit-2026-11-20.md) · [Доказательства по ТЗ](working-set.md)",
        "",
        "## Границы модулей",
        "",
        "| Каталог | Ответственность и вход | Правило изменения |",
        "| --- | --- | --- |",
    ]
    for module in data["modules"]:
        lines.append(f"| `{module['path']}/` | {module['purpose']}. {mdlink(module['entry'], '../')} | {module['rules']} |")
    lines.extend([
        "",
        "Исходные пути и соглашения о вызове сохранены, чтобы действующие сборки и доказательства оставались воспроизводимыми. Логическая структура задаётся контрактами модулей и карточками ниже.",
        "",
        "## Критические границы интеграции",
        "",
        "- `rbm_u340e_step` формирует логический запрос режима/передачи. Его результат пока не подключён целиком к `lfj8_h03_cycle_tick`.",
        "- `lfj8_h03_cycle_tick` выполняет восстановленные стадии на уже подготовленном GP. Часть его производителей и полного расписания ещё отсутствует.",
        "- `lfj8_h03_takeover` вызывает переданные `qualified/arbitrate/apply/inhibit`. Наличие вызова `inhibit` в тесте не доказывает физическое отключение выхода.",
        "- `lfj8_h03_can13` управляет очередью по предоставленному владению. Штатные IRQ и восстановление владения остаются отдельной задачей.",
        "- `diagnostics/` обслуживает RAM и ограниченный CAN-сеанс. Реальный BasicCAN RX и сохранение после питания не входят автоматически в этот результат.",
        "",
        "## Статусы и объём",
        "",
        counts(data),
        "",
        "«Завершено» применяется к узкому объёму карточки. «Проверено программно» не закрывает реализацию на оборудовании. «Требуется разработка» включает независимые программные шаги и их внешние зависимости. Отложенные задачи не входят в первый файл.",
        "",
        "## Быстрый список",
        "",
        "| Приоритет | ID | Задача | Статус |",
        "| --- | --- | --- | --- |",
    ])
    for task in tasks:
        order = task.get("continuation", {}).get("order", "—")
        lines.append(f"| {order} | [{task['id']}](#{task['id'].lower()}) | {task['title']} | {data['status_labels'][task['status']]} |")
    for task in tasks:
        name = task["id"]
        lines.extend([
            "",
            f'<a id="{name.lower()}"></a>',
            f"## {name} — {task['title']}",
            "",
            f"**{data['status_labels'][task['status']]}** · ТЗ " + ", ".join(f"§{x}" for x in task["sections"]),
            "",
            f"**Сделано.** {task['current']}",
            "",
            f"**Осталось.** {task['remaining']}",
            "",
            f"**Критерий результата.** {task['acceptance']}",
            "",
            "**Код.** " + " · ".join(mdlink(path, "../", path) for path in task["code"]),
            "",
            f"**Что настраивать.** {task['settings']}",
            "",
            "**Проверки.** " + (" · ".join(f"[{name}](#check-{name.lower()})" for name in task["checks"]) or "Физический протокол, программных доказательств приёмки нет."),
            "",
            "**Разбор и основания.** " + " · ".join(mdlink(path, "../") for path in task["docs"]),
        ])
        if task["depends"]:
            lines.extend(["", "**Зависит от.** " + ", ".join(f"[{name}](#{name.lower()})" for name in task["depends"])])
        if task.get("continuation"):
            follow = task["continuation"]
            lines.extend(["", "**Следующий шаг для продолжения.** " + follow["action"]])
            for key, label in (("order", "Приоритет продолжения"), ("inputs", "Исходные условия"),
                               ("deliverable", "Что сдать")):
                if key in follow:
                    lines.extend(["", f"**{label}.** " + str(follow[key])])
            if follow.get("chat_id"):
                lines.extend(["", "**Кому удобно продолжить.** " + follow["chat_label"] +
                              " — " + follow["chat_id"] + ". Это рекомендация, не резерв."])
            lines.extend(["", "**Кто сейчас выполняет.** Проверить [общий список исполнителей]"
                          "(https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/tree/task-board). "
                          "Перед изменениями занять этот ID и точные файлы."])
    lines.extend([
        "",
        "## Команды проверок",
        "",
        "Команды выполняются из корня. `$h03` — выбранный файл H03, `$m32rGcc` — компилятор M32R с его симулятором, `$zig` — компилятор ПК. `$r4` и `$r4Engine` — зафиксированный R4 и его development/E4M3/engine, `$s04` — образ с SHA-256 из реестра, `$c167Model` — tools/c167_subset.py из R2. Пути локального компьютера хранятся только в local/.",
        "",
        "Сначала собираются зависимости. M32R создаёт объекты для NATIVE, PC создаёт исполняемый файл для TORQUE. SOURCES сверяет исходники через Git blob, поэтому рабочее дерево R1 может быть без checkout.",
    ])
    for name, check in data["checks"].items():
        lines.extend(["", f'<a id="check-{name.lower()}"></a>', f"### {name} — {check['title']}", ""])
        if name == "E4AUDIT":
            lines.append(check["command"])
        else:
            lines.extend(["```powershell", check["command"], "```"])
        lines.extend(["", "**Последний сохранённый результат.** " + " · ".join(mdlink(path, "../") for path in check["reports"])])
    return "\n".join(lines) + "\n"


def expected_readme(data):
    path = ROOT / "README.md"
    content = path.read_text(encoding="utf-8")
    if content.count(START) != 1 or content.count(END) != 1:
        raise ValueError("README must contain exactly one pair of PROJECT-STATUS markers")
    first, tail = content.split(START)
    _, last = tail.split(END)
    return first + render_status(data) + last


def audit_errors(data):
    audit = json.loads(local_file(data["audit"]).read_text(encoding="utf-8"))
    errors = []
    normalize = audit.get("text_hash_format") == "lf"
    current = source_files(normalize)
    recorded = audit["source_sha256"]
    for name in sorted(set(recorded) | set(current)):
        if recorded.get(name) != current.get(name):
            errors.append(f"Code needs review/retest: {name}")
    for name, expected in audit["evidence_sha256"].items():
        if digest(local_file(name), normalize) != expected:
            errors.append(f"Evidence changed since the audit: {name}")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--task", help="Show one task and its check commands")
    args = parser.parse_args()
    try:
        data = json.loads(REGISTER.read_text(encoding="utf-8"))
        validate(data)
        if args.task:
            task = next((t for t in data["tasks"] if t["id"] == args.task.upper()), None)
            if task is None:
                raise ValueError(f"Unknown task: {args.task}")
            print(json.dumps({"task": task, "checks": {name: data["checks"][name] for name in task["checks"]}},
                             ensure_ascii=False, indent=2))
            return 0
        expected = {ROOT / "README.md": expected_readme(data),
                    ROOT / "docs/project-map.md": render_map(data)}
        if args.write:
            for path, content in expected.items():
                path.write_text(content, encoding="utf-8", newline="\n")
            print("Updated README and project map. Audit evidence was not changed.")
            return 0
        errors = [f"Generated page is stale: {path.relative_to(ROOT)}"
                  for path, content in expected.items()
                  if not path.is_file() or path.read_text(encoding="utf-8") != content]
        errors.extend(audit_errors(data))
        if errors:
            print("\n".join(errors), file=sys.stderr)
            return 1
        print(f"PASS: {len(data['tasks'])} tasks, 11 specification sections, valid links/dependencies, "
              "unchanged audited code and evidence. Release readiness is NOT implied.")
        print(counts(data))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Project status check failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
