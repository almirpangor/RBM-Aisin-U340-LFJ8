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
            "-I", "targets/lfj8", "diagnostics/chery_model_monitor.c", "targets/lfj8/ta2005_chery_inputs.c",
            "diagnostics/test_chery_dtc_link.c", "-o", str(diagnostic_link_check),
        ])
        run("Сеанс Chery C0, сегментация и тайм-ауты", [str(diagnostic_link_check)])
        panel_check = output / f"panel_pulse_test{suffix}"
        run("Сборка расчёта импульсов панели", [*driver, *common_flags,
                                               "targets/panel/panel_pulse.c",
                                               "targets/panel/test_panel_pulse.c",
                                               "-o", str(panel_check)])
        run("Частота, коррекция и хранение калибровки панели", [str(panel_check)])
        panel_gpio_check = output / f"bosch_panel_gpio_test{suffix}"
        run("Сборка планировщика вывода Bosch для панели", [
            *driver, *common_flags, "-pedantic", "-I", "targets/panel",
            "targets/panel/panel_pulse.c", "targets/bosch/panel_gpio.c",
            "targets/bosch/test_panel_gpio.c", "-o", str(panel_gpio_check),
        ])
        run("Фронты панели и приоритет штатного выхода Bosch", [str(panel_gpio_check)])
        takeover_check = output / f"lfj8_h03_takeover_test{suffix}"
        run("Сборка передачи управления LFJ8 H03", [
            *driver, *common_flags, "-pedantic",
            "-I", "controller/include", "-I", "controller/vendor/toyota/include",
            "targets/lfj8/lfj8_h03_takeover.c", "targets/lfj8/lfj8_h03_outputs.c",
            "targets/lfj8/test_lfj8_h03_takeover.c", "controller/vendor/toyota/src/factory_core.c",
            "-o", str(takeover_check),
        ])
        run("Синхронизация команд и блокировки LFJ8 H03", [str(takeover_check)])
        dtc_io_check = output / f"lfj8_h03_dtc_can_test{suffix}"
        run("Сборка транспорта диагностики для CAN0 H03", [
            *driver, *common_flags, "-pedantic", "-I", "diagnostics", "-I", "targets/lfj8",
            "diagnostics/chery_dtc.c", "diagnostics/chery_dtc_can.c", "diagnostics/chery_dtc_link.c",
            "targets/lfj8/lfj8_bridge.c", "targets/lfj8/lfj8_donor_io.c",
            "targets/lfj8/lfj8_h03_dtc_can.c", "targets/lfj8/test_lfj8_h03_dtc_can.c",
            "-o", str(dtc_io_check),
        ])
        run("Диагностика H03 с подтверждением передачи CAN", [str(dtc_io_check)])
        controller_dir = output / "controller"
        library_by_platform = {"win32": "rbm_u340e.dll", "darwin": "librbm_u340e.dylib"}
        library = controller_dir / library_by_platform.get(sys.platform, "librbm_u340e.so")
        torque_check = controller_dir / f"lfj8_h03_torque_test{suffix}"
        runtime_link = [] if suffix else [f"-Wl,-rpath,{controller_dir}"]
        run("Сборка запроса снижения момента U340E", [
            *driver, *common_flags, "-pedantic", "-I", "controller/vendor/toyota/include",
            "targets/lfj8/lfj8_h03_torque.c", "targets/lfj8/test_lfj8_h03_torque.c",
            str(library), *runtime_link, "-o", str(torque_check),
        ])
        run("Запрос, подтверждение и снятие снижения момента", [str(torque_check)])
        torque_io_check = controller_dir / f"lfj8_h03_torque_can_test{suffix}"
        run("Сборка адаптера CAN0 для момента", [
            *driver, *common_flags, "-pedantic", "-I", "controller/vendor/toyota/include",
            "targets/lfj8/lfj8_bridge.c", "targets/lfj8/lfj8_donor_io.c",
            "targets/lfj8/lfj8_h03_torque.c", "targets/lfj8/lfj8_h03_torque_can.c",
            "targets/lfj8/test_lfj8_h03_torque_can.c", str(library), *runtime_link,
            "-o", str(torque_io_check),
        ])
        run("Передача запроса и приём статуса момента в CAN0", [str(torque_io_check)])
        can13_check = controller_dir / f"lfj8_h03_can13_test{suffix}"
        run("Сборка управления CAN13 H03", [
            *driver, *common_flags, "-pedantic", "-I", "targets/lfj8", "-I", "diagnostics",
            "-I", "controller/vendor/toyota/include",
            "diagnostics/chery_dtc.c", "diagnostics/chery_dtc_can.c", "diagnostics/chery_dtc_link.c",
            "targets/lfj8/lfj8_bridge.c", "targets/lfj8/lfj8_donor_io.c", "targets/lfj8/lfj8_chery_tx.c",
            "targets/lfj8/lfj8_h03_torque.c", "targets/lfj8/lfj8_h03_torque_can.c",
            "targets/lfj8/lfj8_h03_dtc_can.c", "targets/lfj8/lfj8_h03_can13.c",
            "targets/lfj8/test_lfj8_h03_can13.c", str(library), *runtime_link, "-o", str(can13_check),
        ])
        run("Передача CAN13 между моментом, диагностикой и скоростью", [str(can13_check)])
        engine_check = output / f"ta2005_engine_qualifier_test{suffix}"
        run("Сборка квалификации оборотов и температуры TA2005", [
            *driver, *common_flags, "-pedantic", "-I", "controller/include",
            "-I", "controller/vendor/toyota/include", "targets/lfj8/ta2005_chery_inputs.c",
            "targets/lfj8/ta2005_engine_qualifier.c", "targets/lfj8/test_ta2005_engine_qualifier.c",
            "-o", str(engine_check),
        ])
        run("Отказ и восстановление оборотов и температуры", [str(engine_check)])
        engine_feed_check = output / f"lfj8_h03_engine_feed_test{suffix}"
        run("Сборка тракта оборотов, ОЖ и диагностических кодов", [
            *driver, *common_flags, "-pedantic", "-I", "diagnostics", "-I", "controller/include",
            "-I", "controller/vendor/toyota/include", "diagnostics/chery_dtc.c",
            "targets/lfj8/lfj8_bridge.c", "targets/lfj8/lfj8_donor_io.c",
            "targets/lfj8/ta2005_chery_inputs.c", "targets/lfj8/ta2005_engine_qualifier.c",
            "targets/lfj8/lfj8_h03_engine_rx.c", "targets/lfj8/lfj8_h03_engine_feed.c",
            "targets/lfj8/test_lfj8_h03_engine_feed.c", "-o", str(engine_feed_check),
        ])
        run("Обороты и ОЖ, активные DTC, история и очистка", [str(engine_feed_check)])
        cycle_check = controller_dir / f"lfj8_h03_cycle_test{suffix}"
        run("Сборка цикла Toyota с адаптером H03", [
            *driver, *common_flags, "-pedantic", "-I", "controller/include",
            "-I", "controller/vendor/toyota/include", "targets/lfj8/lfj8_h03_cycle.c",
            "targets/lfj8/lfj8_h03_torque.c", "targets/lfj8/lfj8_h03_takeover.c",
            "targets/lfj8/lfj8_h03_outputs.c", "targets/lfj8/test_lfj8_h03_cycle.c",
            str(library), *runtime_link, "-o", str(cycle_check),
        ])
        run("Цикл включения D, переключение и потеря события", [str(cycle_check)])
        phase_clock_check = output / f"lfj8_h03_phase_clock_test{suffix}"
        run("Сборка контроля тактов H03", [
            *driver, *common_flags, "-pedantic", "targets/lfj8/lfj8_h03_phase_clock.c",
            "targets/lfj8/test_lfj8_h03_phase_clock.c", "-o", str(phase_clock_check),
        ])
        run("Очередность, пропуск и давность тактов H03", [str(phase_clock_check)])
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
