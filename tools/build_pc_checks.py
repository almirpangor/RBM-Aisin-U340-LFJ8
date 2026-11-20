"""Собрать и проверить компоненты проекта для ПК."""

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def build(compiler: str, output: Path, bosch: tuple[Path, Path, Path] | None) -> None:
    resolved = shutil.which(compiler)
    if resolved is None:
        raise ValueError(f"Компилятор не найден: {compiler}")
    using_zig = Path(resolved).stem.casefold() == "zig"
    driver = [resolved, "cc"] if using_zig else [resolved]
    version_flag = "version" if using_zig else "--version"
    version = subprocess.check_output([resolved, version_flag], text=True).splitlines()[0]

    output.mkdir(parents=True, exist_ok=True)
    runs = []

    def run(name: str, command: list[str]) -> None:
        result = subprocess.run(command, cwd=ROOT, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, encoding="utf-8", errors="replace")
        print(f"{name} [{result.returncode}]")
        print(result.stdout, end="")
        runs.append({"name": name, "exit_code": result.returncode, "output": result.stdout})
        result.check_returncode()

    python = [sys.executable, "-B"]
    suffix = ".exe" if sys.platform == "win32" else ""
    common_flags = ["-std=c11", "-O2", "-UNDEBUG", "-Wall", "-Wextra", "-Werror"]

    try:
        run("Toyota U340E", [*python, "controller/build.py", "--cc", resolved,
                            "--out", str(output / "controller")])
        diagnostic_check = output / f"chery_dtc_test{suffix}"
        run("Сборка диагностики Chery", [*driver, *common_flags, "-pedantic",
                                       "diagnostics/chery_dtc.c", "diagnostics/test_chery_dtc.c",
                                       "-o", str(diagnostic_check)])
        run("Чтение, очистка и повтор DTC", [str(diagnostic_check)])
        diagnostic_can_check = output / f"chery_dtc_can_test{suffix}"
        run("Сборка CAN-кадров диагностики Chery", [
            *driver, *common_flags, "-pedantic", "diagnostics/chery_dtc.c",
            "diagnostics/chery_dtc_can.c", "diagnostics/test_chery_dtc_can.c",
            "-o", str(diagnostic_can_check),
        ])
        run("Кадры диагностики Chery CAN", [str(diagnostic_can_check)])
        diagnostic_link_check = output / f"chery_dtc_link_test{suffix}"
        run("Сборка транспорта диагностики Chery C0", [
            *driver, *common_flags, "-pedantic", "diagnostics/chery_dtc.c",
            "diagnostics/chery_dtc_can.c", "diagnostics/chery_dtc_link.c",
            "diagnostics/test_chery_dtc_link.c", "-o", str(diagnostic_link_check),
        ])
        run("Сеанс Chery C0, сегментация и тайм-ауты", [str(diagnostic_link_check)])
        panel_check = output / f"panel_pulse_test{suffix}"
        run("Сборка расчёта импульсов панели", [*driver, *common_flags,
                                               "targets/panel/panel_pulse.c",
                                               "targets/panel/test_panel_pulse.c",
                                               "-o", str(panel_check)])
        run("Частота, коррекция и хранение калибровки панели", [str(panel_check)])
        run("Тесты модели", [*python, "-m", "unittest", "discover", "-s", "tests", "-v"])
        integrated = [*python, "-m", "model.run_integrated", "--cc", resolved]
        if bosch is not None:
            engine, source, image = bosch
            integrated.extend(["--bosch-engine", str(engine), "--bosch-s04", str(source),
                               "--bosch-image", str(image)])
        run("Сквозной сценарий с компонентами C", integrated)
    finally:
        report = {"runtime": "host", "platform": sys.platform, "compiler": version, "runs": runs}
        (output / "PC-CHECKS.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                                               encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cc", default="zig", help="Исполняемый файл Zig, GCC или Clang")
    parser.add_argument("--out", type=Path, default=ROOT / "local/pc-checks")
    parser.add_argument("--bosch-engine", type=Path, help="Каталог инструментария E4M3 из R4")
    parser.add_argument("--bosch-s04", type=Path, help="Исходный образ Bosch S04")
    parser.add_argument("--bosch-image", type=Path, help="Собранный кандидат Bosch")
    arguments = parser.parse_args()
    bosch = (arguments.bosch_engine, arguments.bosch_s04, arguments.bosch_image)
    if any(part is not None for part in bosch) and not all(bosch):
        parser.error("Для сквозной проверки Bosch задайте все три аргумента --bosch-*")
    try:
        inputs = tuple(path.resolve() for path in bosch) if all(bosch) else None
        build(arguments.cc, arguments.out.resolve(), inputs)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Проверка на ПК остановлена: {error}\n")


if __name__ == "__main__":
    main()
