# Кто сейчас работает над проектом

Обновлено UTC: **2026-11-20T15:57:32+00:00**. Изменение № **30**.

Это общий учёт исполнителей. Он не меняет готовность функции по ТЗ и не подтверждает выпуск BIN.
Команды занятия и обновления задачи — в tools/task_coordination.py основной ветки.
Задача и пересекающиеся файлы удерживаются в состояниях «Выполняется», «Ожидает» и «На проверке».
Давняя отметка не освобождается автоматически. Возобновившийся чат обязан проверить свой claim_id.

Каталог задач взят из main 264f2498002dbd7ee0d0ca8723ccbb88632ec11d.

| Задача | Ход работы | Чат | Ветка | Обновление UTC | Что делает / результат |
| --- | --- | --- | --- | --- | --- |
| ORG-01 — Основа проекта и локальная работа | Работа завершена | Текущий чат — совместная работа Codex \[codex-coordination-27a510e\] | main | 2026-11-20T15:37:39+00:00 | Опубликованы карта задач и общий учёт чатов. Пройдены 59 локальных тестов; GitHub Actions 44764817941 завершён успешно. Настройка совместной работы завершена. / commit 2875ed80264fd7714d44047f849e2df4b04123ef |
| TOY-01 — Перенос ядра и единое состояние Toyota | Свободна | — | — | — | — |
| TOY-02 — Подтверждённая нагрузка двигателя для Toyota | Свободна | — | — | — | — |
| TOY-03 — Независимые разрешающие сигналы диапазона | На проверке | Codex TOY-03 \[codex-01a1f9a2-d0ae-78d3-86f1-21b27426fd3f\] | codex/toy-03-range-01a1f9a2 | 2026-11-20T15:48:28+00:00 | Карта битов Toyota, проверка вариантов проводки Mazda и сценарии стенда опубликованы. Проверка реестра и git diff --check PASS. Физические источники целевого жгута пока не подтверждены. / commit dfc774eee013ba78c6679d3128f493f238f43000 |
| TOY-04 — Полная последовательность переключений | Свободна | — | — | — | — |
| TOY-05 — Обучение и сохранение адаптаций | Свободна | — | — | — | — |
| TOY-06 — Блокировка гидротрансформатора SLU | Свободна | — | — | — | — |
| CAN-01 — Форматы CAN и квалификация RPM/ОЖ | Свободна | — | — | — | — |
| CAN-02 — Общий диспетчер CAN13 | Свободна | — | — | — | — |
| CAN-03 — Штатный запуск, IRQ и восстановление CAN0 | На проверке | Codex — CAN0 H03 \[codex-01a1f99f-5cb5-70e0-afd0-60e6b41a5d51\] | codex/can-03-h03-01a1f99f | 2026-11-20T15:50:27+00:00 | Сведено с main 264f249. 16 прогонов lifecycle, 12 TX gate и project_status --check PASS. Протокол CANHacker добавлен. Штатная привязка и аппаратная приёмка открыты. / commit 507ba30e1a3e68c727b137ef209d1a45333591ad |
| CAN-04 — Запрос снижения момента по RB | Свободна | — | — | — | — |
| CAN-05 — Полнота штатного обмена Chery | Выполняется | Codex CAN-05 \[codex-4dcfb03f-87a2-4fbd-bf33-08a54073c7e4\] | codex/u340-1120-c7e4 | 2026-11-20T15:56:36+00:00 | Cross-check the LFJ8 1AE encoder against the Bosch native Chery receiver model, including qualification and loss of validity. |
| ECU-01 — Проверочная сборка Bosch E4M3 | Свободна | — | — | — | — |
| ECU-02 — Калибровка момента и работа двигателя | Свободна | — | — | — | — |
| H03-01 — Выбранная основа 9E1C и карта подключения | Свободна | — | — | — | — |
| H03-02 — S51, S83 и температура ATF | Выполняется | Codex — привязка ATF H03 \[codex-01a1f9a2-d0ae-78d3-86f1-21b27426fd3f\] | codex/h03-02-atf-01a1f9a2 | 2026-11-20T15:57:27+00:00 | Проверяю штатную функцию ATF в M32R: чтение AN1, три записи, пропуск записи, режим напряжения из ROM. / commit ced3c86de36fca6e77812025e15595dd67a3fa93 |
| H03-03 — Единое расписание и запуск приложения H03 | Выполняется | Codex — foreground H03 \[codex-01a1f99f-5cb5-70e0-afd0-60e6b41a5d51\] | codex/h03-03-foreground-01a1f99f | 2026-11-20T15:57:32+00:00 | Подключаю отзыв при ожидании без потребления события к проверке M32R. / commit 2584dd654ded6cfaae0d0ab65520eb443bcb8445 |
| H03-04 — Память, стек и сервисные пути | Выполняется | Основной чат — память целевого H03 \[codex-h03-04-01a1f76d-20261120\] | codex/h03-04-storage-01a1f76d | 2026-11-20T15:55:12+00:00 | Полный набор состояний раскладываю на раздельные блоки; расширяю существующий прогон шести OEM-инициализаций для проверки вычисленной границы второго окна, сохраняя прежние значения по умолчанию. |
| H03-05 — SLT, силовые выходы и реакция на отказ | Свободна | — | — | — | — |
| IO-01 — Два дополнительных реле | Отложена владельцем | — | — | — | — |
| VSS-01 — Точный расчёт VSS и скорость по CAN | Свободна | — | — | — | — |
| VSS-02 — Кинематика и параметры реальной скорости | Свободна | — | — | — | — |
| PANEL-01 — Импульсы Bosch на приборную панель | Отложена владельцем | — | — | — | — |
| MODE-01 — Логика шести положений и кнопок | Свободна | — | — | — | — |
| MODE-02 — Подключение селектора, Tiptronic и Overdrive | Свободна | — | — | — | — |
| MODE-03 — Окончательная политика режимов | Свободна | — | — | — | — |
| SRC-01 — Реестр происхождения и контроль исходников | Свободна | — | — | — | — |
| AUD-01 — Программный аудит истории E4M3 | Свободна | — | — | — | — |
| DTC-01 — Прикладной сеанс и статусы Chery | Свободна | — | — | — | — |
| DTC-02 — Штатный приём BasicCAN для диагностического сеанса | Работа завершена | Основной чат — приём диагностики CAN \[codex-dtc02-01a1f76d-20261120\] | codex/dtc-02-rx-20261120 | 2026-11-20T15:48:07+00:00 | В main принята часть DTC-02: очередь с проверкой давности и поколения. 33 шага ПК, 17 M32R и GitHub Actions 44766797993 PASS. Остаток DTC-02 открыт: штатный когерентный RX, OEM-сервис и foreground. Резерв файлов освобождён. / commit 264f2498002dbd7ee0d0ca8723ccbb88632ec11d |
| DTC-03 — Все диагностические события и соответствия Toyota/Chery | Свободна | — | — | — | — |
| DTC-04 — Хранение DTC после выключения питания | На проверке | Codex DTC-04 \[codex-dtc04-mwp5rm2ofhaxjfi9dss\] | codex/dtc04-mwp5rm2ofhaxjfi9dss | 2026-11-20T15:56:49+00:00 | Журнал DTC опубликован. ПК: 35 шагов и 59 тестов PASS. Модель: прерывание записи и очистка; H03 NVM, порядок подтверждения и стенд открыты. Доказательства: verification/project-audit/dtc04-journal.md. Общий снимок и реестр переданы интегратору. / commit 4ef63cb5d0a93d31c2db76411890d31593783f2e |
| REL-01 — Два целевых BIN и воспроизводимый комплект | На проверке | Codex — комплект двух BIN \[codex-01a1f9a2-d0ae-78d3-86f1-21b27426fd3f\] | codex/rel-01-pair-01a1f9a2 | 2026-11-20T15:51:56+00:00 | Проверка комплекта двух BIN опубликована. Детерминированность ZIP, проверка хешей и отказ на некорректных входах пройдены. H03 собирается в объект ELF; Bosch BIN проходит модель со статусом OFFLINE_ONLY. Целевых BIN нет. / commit b174397fe79ebdb0d0749bcee31fe7f198435a28 |
| REL-02 — Приёмка новой связки на оборудовании | Свободна | — | — | — | — |

## Зарезервированные файлы

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
- targets/lfj8/lfj8_h03_atf.h
- targets/lfj8/test_lfj8_h03_atf.c

### H03-03

Чат: Codex — foreground H03. Claim ID: ef041474d8994309836820d6cd886071.

- data/project-tasks.json
- docs/lfj8-h03-control-cycle.md
- targets/lfj8/check_h03_phase_wait.py
- targets/lfj8/h03_phase_wait_hook.S
- targets/lfj8/lfj8_h03_phase_clock.c
- targets/lfj8/lfj8_h03_phase_clock.h
- targets/lfj8/lfj8_h03_takeover.c
- targets/lfj8/lfj8_h03_takeover.h
- targets/lfj8/test_lfj8_h03_takeover.c
- verification/e4m3-can-9e1c/h03-foreground.json
- verification/e4m3-can-9e1c/h03-phase-wait.json
- verification/project-audit/2026-11-20-h03-phase-wait.json

### H03-04

Чат: Основной чат — память целевого H03. Claim ID: 83b9428ce0f2463f92341fea12156d66.

- docs/lfj8-h03-ram-audit.md
- targets/lfj8/check_h03_ram_candidate.py
- targets/lfj8/check_h03_storage.py
- targets/lfj8/h03_storage_layout.c
- targets/lfj8/lfj8_h03_storage.h
- tests/test_h03_storage.py
- verification/e4m3-can-9e1c/h03-storage.json

### REL-01

Чат: Codex — комплект двух BIN. Claim ID: 38bcfd017d9a4719a6054450645d79ab.

- tools/package_workset.py

### TOY-03

Чат: Codex TOY-03. Claim ID: f014bd3c6bba42f5bb7e5fa23c121d0d.

- docs/lfj8-h03-input-paths.md

## Последние события

| UTC | Задача | Действие | Чат |
| --- | --- | --- | --- |
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
| 2026-11-20T15:53:30+00:00 | H03-04 | claim | codex-h03-04-01a1f76d-20261120 |
| 2026-11-20T15:52:36+00:00 | H03-03 | review | codex-01a1f99f-5cb5-70e0-afd0-60e6b41a5d51 |
| 2026-11-20T15:51:56+00:00 | REL-01 | review | codex-01a1f9a2-d0ae-78d3-86f1-21b27426fd3f |
| 2026-11-20T15:51:48+00:00 | H03-03 | claim | codex-01a1f99f-5cb5-70e0-afd0-60e6b41a5d51 |
| 2026-11-20T15:50:42+00:00 | REL-01 | claim | codex-01a1f9a2-d0ae-78d3-86f1-21b27426fd3f |
| 2026-11-20T15:50:27+00:00 | CAN-03 | review | codex-01a1f99f-5cb5-70e0-afd0-60e6b41a5d51 |
| 2026-11-20T15:49:41+00:00 | CAN-03 | heartbeat | codex-01a1f99f-5cb5-70e0-afd0-60e6b41a5d51 |
| 2026-11-20T15:49:11+00:00 | CAN-03 | resume | codex-01a1f99f-5cb5-70e0-afd0-60e6b41a5d51 |
| 2026-11-20T15:48:28+00:00 | TOY-03 | review | codex-01a1f9a2-d0ae-78d3-86f1-21b27426fd3f |
| 2026-11-20T15:48:07+00:00 | DTC-02 | complete | codex-dtc02-01a1f76d-20261120 |
| 2026-11-20T15:47:17+00:00 | DTC-02 | review | codex-dtc02-01a1f76d-20261120 |
| 2026-11-20T15:47:02+00:00 | TOY-03 | claim | codex-01a1f9a2-d0ae-78d3-86f1-21b27426fd3f |
| 2026-11-20T15:46:30+00:00 | DTC-02 | heartbeat | codex-dtc02-01a1f76d-20261120 |
| 2026-11-20T15:46:14+00:00 | CAN-03 | review | codex-01a1f99f-5cb5-70e0-afd0-60e6b41a5d51 |
| 2026-11-20T15:44:32+00:00 | CAN-03 | claim | codex-01a1f99f-5cb5-70e0-afd0-60e6b41a5d51 |
| 2026-11-20T15:39:41+00:00 | DTC-02 | claim | codex-dtc02-01a1f76d-20261120 |
| 2026-11-20T15:37:39+00:00 | ORG-01 | complete | codex-coordination-27a510e |
| 2026-11-20T15:35:56+00:00 | ORG-01 | review | codex-coordination-27a510e |
| 2026-11-20T15:30:42+00:00 | ORG-01 | claim | codex-coordination-27a510e |
