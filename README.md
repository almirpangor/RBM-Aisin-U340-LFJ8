# Кто сейчас работает над проектом

Обновлено UTC: **2026-11-20T16:04:31+00:00**. Изменение № **49**.

Это общий учёт исполнителей. Он не меняет готовность функции по ТЗ и не подтверждает выпуск BIN.
Команды занятия и обновления задачи — в tools/task_coordination.py основной ветки.
Задача и пересекающиеся файлы удерживаются в состояниях «Выполняется», «Ожидает» и «На проверке».
Давняя отметка не освобождается автоматически. Возобновившийся чат обязан проверить свой claim_id.

Каталог задач взят из main 9fa9c8aa18cd88543ba464f98fc8f7fc6a21a7d1.

| Задача | Ход работы | Чат | Ветка | Обновление UTC | Что делает / результат |
| --- | --- | --- | --- | --- | --- |
| ORG-01 — Основа проекта и локальная работа | Работа завершена | Текущий чат — совместная работа Codex \[codex-coordination-27a510e\] | main | 2026-11-20T15:37:39+00:00 | Опубликованы карта задач и общий учёт чатов. Пройдены 59 локальных тестов; GitHub Actions 44764817941 завершён успешно. Настройка совместной работы завершена. / commit 2875ed80264fd7714d44047f849e2df4b04123ef |
| TOY-01 — Перенос ядра и единое состояние Toyota | Свободна | — | — | — | — |
| TOY-02 — Подтверждённая нагрузка двигателя для Toyota | Выполняется | Codex TOY-02 \[codex-dtc04-mwp5rm2ofhaxjfi9dss\] | codex/toy02-load-feed-mwp5rm2ofhaxjfi9dss | 2026-11-20T16:04:06+00:00 | Публикация одного снимка нагрузки и проверки отказа реализованы. Контроллер собран и проверен в M32R. Идут H03 link, ПК и повтор аудита Bosch. |
| TOY-03 — Независимые разрешающие сигналы диапазона | На проверке | Codex TOY-03 \[codex-01a1f9a2-d0ae-78d3-86f1-21b27426fd3f\] | codex/toy-03-range-01a1f9a2 | 2026-11-20T15:48:28+00:00 | Карта битов Toyota, проверка вариантов проводки Mazda и сценарии стенда опубликованы. Проверка реестра и git diff --check PASS. Физические источники целевого жгута пока не подтверждены. / commit dfc774eee013ba78c6679d3128f493f238f43000 |
| TOY-04 — Полная последовательность переключений | Свободна | — | — | — | — |
| TOY-05 — Обучение и сохранение адаптаций | Свободна | — | — | — | — |
| TOY-06 — Блокировка гидротрансформатора SLU | Свободна | — | — | — | — |
| CAN-01 — Форматы CAN и квалификация RPM/ОЖ | Выполняется | Codex CAN-01 \[codex-4dcfb03f-87a2-4fbd-bf33-08a54073c7e4\] | codex/can01-1120-c7e4 | 2026-11-20T16:03:00+00:00 | Check startup and drain/recovery epoch of CAN RX timestamps. Reproduce and fix admission of pre-epoch RPM/ECT frames. |
| CAN-02 — Общий диспетчер CAN13 | Свободна | — | — | — | — |
| CAN-03 — Штатный запуск, IRQ и восстановление CAN0 | На проверке | Codex — CAN0 H03 \[codex-01a1f99f-5cb5-70e0-afd0-60e6b41a5d51\] | codex/can-03-h03-01a1f99f | 2026-11-20T15:50:27+00:00 | Сведено с main 264f249. 16 прогонов lifecycle, 12 TX gate и project_status --check PASS. Протокол CANHacker добавлен. Штатная привязка и аппаратная приёмка открыты. / commit 507ba30e1a3e68c727b137ef209d1a45333591ad |
| CAN-04 — Запрос снижения момента по RB | Свободна | — | — | — | — |
| CAN-05 — Полнота штатного обмена Chery | На проверке | Codex CAN-05 \[codex-4dcfb03f-87a2-4fbd-bf33-08a54073c7e4\] | codex/u340-1120-c7e4 | 2026-11-20T16:01:03+00:00 | Host 1AE round trip: 65536 operand pairs and validity transitions PASS. PC 33 steps / 59 tests PASS. Bosch compact build and ST10 model PASS OFFLINE_ONLY. Evidence can05-1ae-roundtrip.md; integrator to record the two new test files in the active audit. Native integration and hardware open. / commit 20247416c28972443bc2992d06d9706566c677d3 |
| ECU-01 — Проверочная сборка Bosch E4M3 | Свободна | — | — | — | — |
| ECU-02 — Калибровка момента и работа двигателя | Свободна | — | — | — | — |
| H03-01 — Выбранная основа 9E1C и карта подключения | Свободна | — | — | — | — |
| H03-02 — S51, S83 и температура ATF | Выполняется | Codex — привязка ATF H03 \[codex-01a1f9a2-d0ae-78d3-86f1-21b27426fd3f\] | codex/h03-02-atf-01a1f9a2 | 2026-11-20T16:00:34+00:00 | Реализую обвязку штатных чтений и записей ATF, проверю парные прогоны OEM в M32R. / commit cb64fe124bdd2602cf363ba463a6e01e591367c5 |
| H03-03 — Единое расписание и запуск приложения H03 | На проверке | Codex — foreground H03 \[codex-01a1f99f-5cb5-70e0-afd0-60e6b41a5d51\] | codex/h03-03-foreground-01a1f99f | 2026-11-20T16:04:31+00:00 | Обёртка 008150 вызывает реальную проверку фазы в M32R. 6 сценариев, отрицательная проверка, 59 Python-тестов и реестр PASS. Реальное время, inhibit, измерения IRQ и целевой BIN открыты. / commit 40d391b8eeb33e9e04f13cff5b59908527f6b144 |
| H03-04 — Память, стек и сервисные пути | Выполняется | Основной чат — память целевого H03 \[codex-h03-04-01a1f76d-20261120\] | codex/h03-04-storage-01a1f76d | 2026-11-20T16:03:20+00:00 | Принята опубликованная часть H03-03 (9fa9c8a) с повтором M32R. Пересобрана карта памяти на этих заголовках: размеры прежние 2324 байта. Закрепляю общие страницы для интеграции H03-04. |
| H03-05 — SLT, силовые выходы и реакция на отказ | Свободна | — | — | — | — |
| IO-01 — Два дополнительных реле | Отложена владельцем | — | — | — | — |
| VSS-01 — Точный расчёт VSS и скорость по CAN | Свободна | — | — | — | — |
| VSS-02 — Кинематика и параметры реальной скорости | Свободна | — | — | — | — |
| PANEL-01 — Импульсы Bosch на приборную панель | Отложена владельцем | — | — | — | — |
| MODE-01 — Логика шести положений и кнопок | Свободна | — | — | — | — |
| MODE-02 — Подключение селектора, Tiptronic и Overdrive | Выполняется | Codex — входы Tiptronic H03 \[codex-32e6ac79-d63f-49c4-9d44-dd51c88bf0d3\] | codex/u340-32e6ac79 | 2026-11-20T16:04:25+00:00 | Квалификация входных снимков M, плюс, минус и OD перед существующей логикой диапазона. Проверю дребезг, потерю признака, устаревание и повторное разрешение после отпускания. Привязка к конкретным контактам остаётся открытой. |
| MODE-03 — Окончательная политика режимов | Свободна | — | — | — | — |
| SRC-01 — Реестр происхождения и контроль исходников | Свободна | — | — | — | — |
| AUD-01 — Программный аудит истории E4M3 | Свободна | — | — | — | — |
| DTC-01 — Прикладной сеанс и статусы Chery | Свободна | — | — | — | — |
| DTC-02 — Штатный приём BasicCAN для диагностического сеанса | Выполняется | Codex — штатный RX BasicCAN H03 \[codex-7bd19ea4-0004-4aec-90c4-f2c6e804c046\] | codex/dtc02-basiccan-7bd19ea4 | 2026-11-20T16:00:26+00:00 | Прогон штатного RX14/15 H03: момент очистки TRFIN, содержимое копии, потеря или перезапись и сохранение OEM-маршрута. Только изолированный прогон. |
| DTC-03 — Все диагностические события и соответствия Toyota/Chery | На проверке | Codex DTC-03 \[codex-dtc04-mwp5rm2ofhaxjfi9dss\] | codex/dtc03-table-mwp5rm2ofhaxjfi9dss | 2026-11-20T16:00:19+00:00 | Все 96 индексов сверены с проверенным S03. 33 шага ПК и 61 тест PASS. Отчёт verification/project-audit/dtc03-table.md. Мониторы отказов и привязка H03 открыты; снимок аудита передан интегратору. / commit fbeea2ca6b1ceb47be58f4bf05c9f3817c5664a2 |
| DTC-04 — Хранение DTC после выключения питания | На проверке | Codex DTC-04 \[codex-dtc04-mwp5rm2ofhaxjfi9dss\] | codex/dtc04-mwp5rm2ofhaxjfi9dss | 2026-11-20T15:56:49+00:00 | Журнал DTC опубликован. ПК: 35 шагов и 59 тестов PASS. Модель: прерывание записи и очистка; H03 NVM, порядок подтверждения и стенд открыты. Доказательства: verification/project-audit/dtc04-journal.md. Общий снимок и реестр переданы интегратору. / commit 4ef63cb5d0a93d31c2db76411890d31593783f2e |
| REL-01 — Два целевых BIN и воспроизводимый комплект | На проверке | Codex — комплект двух BIN \[codex-01a1f9a2-d0ae-78d3-86f1-21b27426fd3f\] | codex/rel-01-pair-01a1f9a2 | 2026-11-20T15:51:56+00:00 | Проверка комплекта двух BIN опубликована. Детерминированность ZIP, проверка хешей и отказ на некорректных входах пройдены. H03 собирается в объект ELF; Bosch BIN проходит модель со статусом OFFLINE_ONLY. Целевых BIN нет. / commit b174397fe79ebdb0d0749bcee31fe7f198435a28 |
| REL-02 — Приёмка новой связки на оборудовании | Свободна | — | — | — | — |

## Зарезервированные файлы

### CAN-01

Чат: Codex CAN-01. Claim ID: 8af57ad2c27440c6822dea2579b051d2.

- targets/lfj8/host_check.c
- targets/lfj8/lfj8_h03_engine_rx.c
- targets/lfj8/lfj8_h03_engine_rx.h
- verification/project-audit/can01-rx-epoch.md

### CAN-03

Чат: Codex — CAN0 H03. Claim ID: a73f1e3a06f84907b57da164cb6018f5.

- docs/lfj8-9e1c-minimum-bench.md
- docs/lfj8-h03-torque.md
- targets/lfj8/check_h03_can_lifecycle.py
- targets/lfj8/h03_can_lifecycle_test.S
- verification/e4m3-can-9e1c/h03-can-lifecycle.json
- verification/project-audit/2026-11-20-dtc02-queue.json

### CAN-05

Чат: Codex CAN-05. Claim ID: 39e9816a3049466a955d4f49cf740da4.

- targets/bosch/test_chery_1ae_roundtrip.c
- tests/test_chery_1ae_roundtrip.py
- verification/project-audit/can05-1ae-roundtrip.md

### DTC-02

Чат: Codex — штатный RX BasicCAN H03. Claim ID: 36f7538204a944d68df89f474cc590e4.

- targets/lfj8/check_h03_dtc_basiccan.py
- verification/project-audit/dtc02-basiccan.md

### DTC-03

Чат: Codex DTC-03. Claim ID: b8f5993a9046405492ff005c31e01675.

- tests/test_chery_dtc_table.py
- verification/project-audit/dtc03-table.md

### DTC-04

Чат: Codex DTC-04. Claim ID: b714560b3e9a4abba849b7ea649a1622.

- diagnostics/chery_dtc_journal.c
- diagnostics/chery_dtc_journal.h
- diagnostics/test_chery_dtc_journal.c
- tools/build_pc_checks.py
- verification/project-audit/dtc04-journal.md

### H03-02

Чат: Codex — привязка ATF H03. Claim ID: 11e70992d32245529e20626f4b9bd867.

- docs/lfj8-h03-atf-native.md
- targets/lfj8/check_h03_atf_native.py
- targets/lfj8/h03_atf_hook_fixture.c
- targets/lfj8/h03_atf_hooks.S
- targets/lfj8/lfj8_h03_atf.h
- targets/lfj8/test_lfj8_h03_atf.c

### H03-03

Чат: Codex — foreground H03. Claim ID: 1d3260143aa94ebf9474e17cf1deacb7.

- docs/lfj8-h03-control-cycle.md
- targets/lfj8/check_h03_phase_wait.py
- targets/lfj8/h03_phase_wait_fixture.c
- verification/e4m3-can-9e1c/h03-phase-wait.json
- verification/project-audit/2026-11-20-h03-phase-wait.json

### H03-04

Чат: Основной чат — память целевого H03. Claim ID: 83b9428ce0f2463f92341fea12156d66.

- README.md
- data/project-tasks.json
- docs/lfj8-h03-ram-audit.md
- docs/project-map.md
- targets/lfj8/check_h03_ram_candidate.py
- targets/lfj8/check_h03_storage.py
- targets/lfj8/h03_storage_layout.c
- targets/lfj8/lfj8_h03_storage.h
- tests/test_h03_storage.py
- verification/e4m3-can-9e1c/h03-storage.json
- verification/project-audit/2026-11-20-h03-storage.json
- verification/project-audit/h03-phase-integration-link.json
- verification/project-audit/h03-storage-tests.txt

### MODE-02

Чат: Codex — входы Tiptronic H03. Claim ID: 2b87aa66de244cf9b30a828391ad9001.

- targets/lfj8/lfj8_range_control.c
- targets/lfj8/lfj8_range_control.h
- tests/u340_integration_host.c
- verification/project-audit/mode02-button-input.md

### REL-01

Чат: Codex — комплект двух BIN. Claim ID: 38bcfd017d9a4719a6054450645d79ab.

- tools/package_workset.py

### TOY-02

Чат: Codex TOY-02. Claim ID: 04163e758d304ae28f99c09cf17d8d25.

- controller/include/rbm_u340e_runtime.h
- controller/src/rbm_u340e_runtime.c
- controller/tests/test_runtime.c
- verification/project-audit/toy02-load-feed.md

### TOY-03

Чат: Codex TOY-03. Claim ID: f014bd3c6bba42f5bb7e5fa23c121d0d.

- docs/lfj8-h03-input-paths.md

## Последние события

| UTC | Задача | Действие | Чат |
| --- | --- | --- | --- |
| 2026-11-20T16:04:31+00:00 | H03-03 | review | codex-01a1f99f-5cb5-70e0-afd0-60e6b41a5d51 |
| 2026-11-20T16:04:25+00:00 | MODE-02 | claim | codex-32e6ac79-d63f-49c4-9d44-dd51c88bf0d3 |
| 2026-11-20T16:04:06+00:00 | TOY-02 | heartbeat | codex-dtc04-mwp5rm2ofhaxjfi9dss |
| 2026-11-20T16:04:02+00:00 | H03-03 | claim | codex-01a1f99f-5cb5-70e0-afd0-60e6b41a5d51 |
| 2026-11-20T16:03:20+00:00 | H03-04 | heartbeat | codex-h03-04-01a1f76d-20261120 |
| 2026-11-20T16:03:00+00:00 | CAN-01 | claim | codex-4dcfb03f-87a2-4fbd-bf33-08a54073c7e4 |
| 2026-11-20T16:02:15+00:00 | H03-03 | complete | codex-01a1f99f-5cb5-70e0-afd0-60e6b41a5d51 |
| 2026-11-20T16:01:53+00:00 | TOY-02 | claim | codex-dtc04-mwp5rm2ofhaxjfi9dss |
| 2026-11-20T16:01:03+00:00 | CAN-05 | review | codex-4dcfb03f-87a2-4fbd-bf33-08a54073c7e4 |
| 2026-11-20T16:00:49+00:00 | H03-03 | resume | codex-01a1f99f-5cb5-70e0-afd0-60e6b41a5d51 |
| 2026-11-20T16:00:34+00:00 | H03-02 | resume | codex-01a1f9a2-d0ae-78d3-86f1-21b27426fd3f |
| 2026-11-20T16:00:26+00:00 | DTC-02 | claim | codex-7bd19ea4-0004-4aec-90c4-f2c6e804c046 |
| 2026-11-20T16:00:19+00:00 | DTC-03 | review | codex-dtc04-mwp5rm2ofhaxjfi9dss |
| 2026-11-20T16:00:00+00:00 | H03-04 | heartbeat | codex-h03-04-01a1f76d-20261120 |
| 2026-11-20T15:59:46+00:00 | H03-03 | review | codex-01a1f99f-5cb5-70e0-afd0-60e6b41a5d51 |
| 2026-11-20T15:59:20+00:00 | H03-02 | review | codex-01a1f9a2-d0ae-78d3-86f1-21b27426fd3f |
| 2026-11-20T15:59:02+00:00 | DTC-03 | heartbeat | codex-dtc04-mwp5rm2ofhaxjfi9dss |
| 2026-11-20T15:57:52+00:00 | DTC-03 | claim | codex-dtc04-mwp5rm2ofhaxjfi9dss |
| 2026-11-20T15:57:48+00:00 | CAN-05 | heartbeat | codex-4dcfb03f-87a2-4fbd-bf33-08a54073c7e4 |
| 2026-11-20T15:57:32+00:00 | H03-03 | resume | codex-01a1f99f-5cb5-70e0-afd0-60e6b41a5d51 |
| 2026-11-20T15:57:27+00:00 | H03-02 | resume | codex-01a1f9a2-d0ae-78d3-86f1-21b27426fd3f |
| 2026-11-20T15:56:49+00:00 | DTC-04 | review | codex-dtc04-mwp5rm2ofhaxjfi9dss |
| 2026-11-20T15:56:36+00:00 | CAN-05 | claim | codex-4dcfb03f-87a2-4fbd-bf33-08a54073c7e4 |
| 2026-11-20T15:56:16+00:00 | H03-03 | review | codex-01a1f99f-5cb5-70e0-afd0-60e6b41a5d51 |
| 2026-11-20T15:55:29+00:00 | H03-02 | review | codex-01a1f9a2-d0ae-78d3-86f1-21b27426fd3f |
| 2026-11-20T15:55:12+00:00 | H03-04 | heartbeat | codex-h03-04-01a1f76d-20261120 |
| 2026-11-20T15:54:58+00:00 | DTC-04 | heartbeat | codex-dtc04-mwp5rm2ofhaxjfi9dss |
| 2026-11-20T15:54:48+00:00 | H03-03 | resume | codex-01a1f99f-5cb5-70e0-afd0-60e6b41a5d51 |
| 2026-11-20T15:54:09+00:00 | H03-02 | claim | codex-01a1f9a2-d0ae-78d3-86f1-21b27426fd3f |
| 2026-11-20T15:53:33+00:00 | DTC-04 | claim | codex-dtc04-mwp5rm2ofhaxjfi9dss |
