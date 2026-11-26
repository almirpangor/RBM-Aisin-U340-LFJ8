# Контроллер Toyota U340E

Карточки [TOY-01…06 и MODE-01…03](../docs/project-map.md). Состояние всего проекта — в [README](../README.md).

| Что менять | Файлы и назначение |
| --- | --- |
| Режимы, кнопки, допустимая передача | [rbm_u340e.h](include/rbm_u340e.h), [rbm_u340e.c](src/rbm_u340e.c) |
| Общий GP и последовательность стадий | [rbm_u340e_runtime.h](include/rbm_u340e_runtime.h), [rbm_u340e_runtime.c](src/rbm_u340e_runtime.c) |
| Планировщик Toyota | [rbm_u340e_scheduler.c](src/rbm_u340e_scheduler.c) |
| Снижение расхода стека | [hydraulic_port.py](hydraulic_port.py), [rbm_u340e_hydraulic_workspace.h](include/rbm_u340e_hydraulic_workspace.h) |
| Исходные алгоритмы/таблицы S01 | [vendor/toyota/manifest.json](vendor/toyota/manifest.json), каталог vendor/toyota |
| Проверки и сборка | [build.py](build.py), [build_target.py](build_target.py), [test_runtime.c](tests/test_runtime.c), [test_controller.c](tests/test_controller.c) |

Донорские файлы сверяются по SHA-256. Изменения переноса выполняются над проверенной временной копией. Произвольная правка vendor с обновлением хеша разрушает смысл сверки происхождения.

`rbm_u340e_step` выдаёт логическое предложение передачи. `lfj8_h03_cycle_tick` находится в targets/lfj8 и использует восстановленные стадии. Между ними ещё требуется рабочая интеграция режимов. Производители GP-нагрузки, независимые сигналы диапазона и физическая калибровка не появляются автоматически от вызова ядра.

Настройки режимов — `RbmU340ePolicy`, допуск передач — `allowed_gears`. Входы нагрузки и начальное GP описаны в [интерфейсе runtime](include/rbm_u340e_runtime.h). Выпускного набора калибровок пока нет.
