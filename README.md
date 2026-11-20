# Кто сейчас работает над проектом

Обновлено UTC: **2026-11-20T16:12:22+00:00**. Изменение № **77**.

Это общий учёт исполнителей. Он не меняет готовность функции по ТЗ и не подтверждает выпуск BIN.
Команды занятия и обновления задачи — в tools/task_coordination.py основной ветки.
Задача и пересекающиеся файлы удерживаются в состояниях «Выполняется», «Ожидает» и «На проверке».
Давняя отметка не освобождается автоматически. Возобновившийся чат обязан проверить свой claim_id.

Каталог задач взят из main a52ab8ce955959ed109d53e6c554beb68f814c2e.

| Задача | Ход работы | Чат | Ветка | Обновление UTC | Что делает / результат |
| --- | --- | --- | --- | --- | --- |
| ORG-01 — Основа проекта и локальная работа | Выполняется | Основной чат — объединение и проверка результатов \[codex-integration-01a1f76d-20261120\] | codex/integration-01a1f76d-20261120 | 2026-11-20T16:10:26+00:00 | Исправляю две гонки учёта параллельных чатов. Проверяю опубликованные порции CAN, диагностики и комплекта двух BIN перед совместной интеграцией. Общий реестр пока занят другим чатом. |
| TOY-01 — Перенос ядра и единое состояние Toyota | Свободна | — | — | — | — |
| TOY-02 — Подтверждённая нагрузка двигателя для Toyota | На проверке | Codex TOY-02 \[codex-dtc04-mwp5rm2ofhaxjfi9dss\] | codex/toy02-load-feed-mwp5rm2ofhaxjfi9dss | 2026-11-20T16:06:58+00:00 | Публикация квалифицированной нагрузки в GP проверена. PC 33 шага/59 тестов, M32R и 17 компонентов, три профиля SIGNALS PASS. Источники GW, бюджет возраста и допуск H03 открыты. Отчёт verification/project-audit/toy02-load-feed.md, общий снимок для интегратора. / commit ff7f42b48d58831a8d7a396711042fc45685acd3 |
| TOY-03 — Независимые разрешающие сигналы диапазона | На проверке | Codex TOY-03 \[codex-01a1f9a2-d0ae-78d3-86f1-21b27426fd3f\] | codex/toy-03-range-01a1f9a2 | 2026-11-20T15:48:28+00:00 | Карта битов Toyota, проверка вариантов проводки Mazda и сценарии стенда опубликованы. Проверка реестра и git diff --check PASS. Физические источники целевого жгута пока не подтверждены. / commit dfc774eee013ba78c6679d3128f493f238f43000 |
| TOY-04 — Полная последовательность переключений | Свободна | — | — | — | — |
| TOY-05 — Обучение и сохранение адаптаций | Выполняется | Codex TOY-05 \[codex-dtc04-mwp5rm2ofhaxjfi9dss\] | codex/toy05-adaptation-mwp5rm2ofhaxjfi9dss | 2026-11-20T16:09:48+00:00 | Симулятор M32R подтвердил 96 прерываний и 768 одиночных повреждений. Зафиксирован откат на предыдущий слот при порче записи сброса. Идут PC и H03 link. |
| TOY-06 — Блокировка гидротрансформатора SLU | Свободна | — | — | — | — |
| CAN-01 — Форматы CAN и квалификация RPM/ОЖ | На проверке | Codex CAN-01 \[codex-4dcfb03f-87a2-4fbd-bf33-08a54073c7e4\] | codex/can01-1120-c7e4 | 2026-11-20T16:10:06+00:00 | CAN RX epoch guard; reproduced old startup and drain race, fixed regressions on host and M32R. PC 33 steps/59 tests, M32R 17 components and Bosch OFFLINE_ONLY PASS. Evidence verification/project-audit/can01-rx-epoch.md. Integrator to update the shared audit; OEM startup and hardware timing remain open. / commit ca268743dfe173f93121d6b9148e0951932cfc9d |
| CAN-02 — Общий диспетчер CAN13 | Свободна | — | — | — | — |
| CAN-03 — Штатный запуск, IRQ и восстановление CAN0 | На проверке | Codex — CAN0 H03 \[codex-01a1f99f-5cb5-70e0-afd0-60e6b41a5d51\] | codex/can-03-h03-01a1f99f | 2026-11-20T15:50:27+00:00 | Сведено с main 264f249. 16 прогонов lifecycle, 12 TX gate и project_status --check PASS. Протокол CANHacker добавлен. Штатная привязка и аппаратная приёмка открыты. / commit 507ba30e1a3e68c727b137ef209d1a45333591ad |
| CAN-04 — Запрос снижения момента по RB | Выполняется | Codex CAN-04 — снятие RB-запроса \[codex-fea1b366-66b6-4667-8206-915153ca1033\] | codex/can-04-torque-fea1b366 | 2026-11-20T16:12:09+00:00 | Исправление прошло M32R, 17 компонентных прогонов. Bosch ST10 OFFLINE_ONLY прошёл обычный диалог и потерю статуса. Завершаю проверку ПК и отчёт. |
| CAN-05 — Полнота штатного обмена Chery | На проверке | Codex CAN-05 \[codex-4dcfb03f-87a2-4fbd-bf33-08a54073c7e4\] | codex/u340-1120-c7e4 | 2026-11-20T16:01:03+00:00 | Host 1AE round trip: 65536 operand pairs and validity transitions PASS. PC 33 steps / 59 tests PASS. Bosch compact build and ST10 model PASS OFFLINE_ONLY. Evidence can05-1ae-roundtrip.md; integrator to record the two new test files in the active audit. Native integration and hardware open. / commit 20247416c28972443bc2992d06d9706566c677d3 |
| ECU-01 — Проверочная сборка Bosch E4M3 | Свободна | — | — | — | — |
| ECU-02 — Калибровка момента и работа двигателя | Свободна | — | — | — | — |
| H03-01 — Выбранная основа 9E1C и карта подключения | Свободна | — | — | — | — |
| H03-02 — S51, S83 и температура ATF | Выполняется | Codex — привязка ATF H03 \[codex-01a1f9a2-d0ae-78d3-86f1-21b27426fd3f\] | codex/h03-02-atf-01a1f9a2 | 2026-11-20T16:12:16+00:00 | Измеряю глубину записи стека отдельно для AN1, расчёта OEM и чтения снимка. / commit c0d00d60ef355e660eb97d98d33c10e7c1117242 |
| H03-03 — Единое расписание и запуск приложения H03 | На проверке | Codex — foreground H03 \[codex-01a1f99f-5cb5-70e0-afd0-60e6b41a5d51\] | codex/h03-03-foreground-01a1f99f | 2026-11-20T16:11:52+00:00 | Совмещено с H03-04 a52ab8c. В M32R измерены 8 байт при ожидании и 64 байта до callback. 8 сценариев, контроль лишнего слова, 65 тестов и реестр PASS. Стек callback/IRQ и аппаратный inhibit открыты. / commit 895e031ad2decca9c3d833c683539876fd467a3f |
| H03-04 — Память, стек и сервисные пути | Работа завершена | Основной чат — память целевого H03 \[codex-h03-04-01a1f76d-20261120\] | codex/h03-04-storage-01a1f76d | 2026-11-20T16:07:21+00:00 | Принята в main порция H03-04: актуальные типы, карта и проверки памяти. GitHub Actions 44769703890 PASS. Карточка ТЗ остаётся open до сервисной изоляции, запуска и полного стека. Общие страницы освобождены для других чатов. / commit a52ab8ce955959ed109d53e6c554beb68f814c2e |
| H03-05 — SLT, силовые выходы и реакция на отказ | Свободна | — | — | — | — |
| IO-01 — Два дополнительных реле | Отложена владельцем | — | — | — | — |
| VSS-01 — Точный расчёт VSS и скорость по CAN | Свободна | — | — | — | — |
| VSS-02 — Кинематика и параметры реальной скорости | Свободна | — | — | — | — |
| PANEL-01 — Импульсы Bosch на приборную панель | Отложена владельцем | — | — | — | — |
| MODE-01 — Логика шести положений и кнопок | Выполняется | Codex MODE-01 \[codex-4dcfb03f-87a2-4fbd-bf33-08a54073c7e4\] | codex/mode01-1120-c7e4 | 2026-11-20T16:11:44+00:00 | Reproduce and fix Tiptronic accepting an opposite shift while the other key is still held. Align C and Python models; leave MODE-02 hardware input and its files to their owner. |
| MODE-02 — Подключение селектора, Tiptronic и Overdrive | На проверке | Codex — входы Tiptronic H03 \[codex-32e6ac79-d63f-49c4-9d44-dd51c88bf0d3\] | codex/u340-32e6ac79 | 2026-11-20T16:10:33+00:00 | Передаю интегратору. ПК 33 шага / 65 тестов PASS, M32R сборка с H03, сквозной прогон с трассой Bosch и 17 компонентов PASS. Отчёт mode02-button-input.md содержит хеши для общего аудита. Подключение к расписанию H03, измерение входов и полный гидравлический цикл остаются открытыми. / commit 53c5f27e40f4ed48fd5873d002a0ab315f448bcf |
| MODE-03 — Окончательная политика режимов | Свободна | — | — | — | — |
| SRC-01 — Реестр происхождения и контроль исходников | Свободна | — | — | — | — |
| AUD-01 — Программный аудит истории E4M3 | Свободна | — | — | — | — |
| DTC-01 — Прикладной сеанс и статусы Chery | Свободна | — | — | — | — |
| DTC-02 — Штатный приём BasicCAN для диагностического сеанса | Выполняется | Codex — штатный RX BasicCAN H03 \[codex-7bd19ea4-0004-4aec-90c4-f2c6e804c046\] | codex/dtc02-basiccan-7bd19ea4 | 2026-11-20T16:12:22+00:00 | Продолжаю после review 345d949. Добавляю проверяемый предсбросовый снимок RX14/15 для очереди, с двойным контролем MSC и без записи в CAN0. / commit 345d9490df4d8c177ab4d5eaff32224cf3f4f2c5 |
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

### CAN-04

Чат: Codex CAN-04 — снятие RB-запроса. Claim ID: 9575e38186c74fb9bb027e3985074fd3.

- targets/lfj8/lfj8_h03_torque.c
- targets/lfj8/lfj8_h03_torque.h
- targets/lfj8/test_lfj8_h03_torque.c
- verification/project-audit/can04-torque-revocation.md

### CAN-05

Чат: Codex CAN-05. Claim ID: 39e9816a3049466a955d4f49cf740da4.

- targets/bosch/test_chery_1ae_roundtrip.c
- tests/test_chery_1ae_roundtrip.py
- verification/project-audit/can05-1ae-roundtrip.md

### DTC-02

Чат: Codex — штатный RX BasicCAN H03. Claim ID: 36f7538204a944d68df89f474cc590e4.

- targets/lfj8/check_h03_dtc_basiccan.py
- targets/lfj8/lfj8_h03_dtc_rx_queue.c
- targets/lfj8/lfj8_h03_dtc_rx_queue.h
- targets/lfj8/test_lfj8_h03_dtc_rx_queue.c
- verification/project-audit/dtc02-basiccan.md
- verification/project-audit/dtc02-preclear-capture.md

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
- targets/lfj8/lfj8_h03_atf_target.c
- targets/lfj8/lfj8_h03_atf_target.h
- targets/lfj8/test_lfj8_h03_atf.c

### H03-03

Чат: Codex — foreground H03. Claim ID: 1d3260143aa94ebf9474e17cf1deacb7.

- data/project-tasks.json
- docs/lfj8-h03-control-cycle.md
- targets/lfj8/check_h03_phase_wait.py
- targets/lfj8/h03_phase_wait_fixture.c
- targets/lfj8/h03_phase_wait_hook.S
- verification/e4m3-can-9e1c/h03-phase-wait.json
- verification/project-audit/2026-11-20-h03-phase-wait.json
- verification/project-audit/2026-11-20-h03-wait-stack.json

### MODE-01

Чат: Codex MODE-01. Claim ID: 5a7d7e355e8042b7b3e05cdba92c350f.

- controller/src/rbm_u340e.c
- controller/tests/test_shift_buttons.c
- model/u340.py
- tests/test_u340.py
- verification/project-audit/mode01-shift-conflict.md

### MODE-02

Чат: Codex — входы Tiptronic H03. Claim ID: 2b87aa66de244cf9b30a828391ad9001.

- targets/lfj8/lfj8_range_control.c
- targets/lfj8/lfj8_range_control.h
- tests/u340_integration_host.c
- verification/project-audit/mode02-button-input.md

### ORG-01

Чат: Основной чат — объединение и проверка результатов. Claim ID: 68c8347a91944cb3929878ea53cc9204.

- docs/multi-chat.md
- tests/test_task_coordination.py
- tools/task_coordination.py
- verification/project-audit/integration/

### REL-01

Чат: Codex — комплект двух BIN. Claim ID: 38bcfd017d9a4719a6054450645d79ab.

- tools/package_workset.py

### TOY-02

Чат: Codex TOY-02. Claim ID: 04163e758d304ae28f99c09cf17d8d25.

- controller/include/rbm_u340e_runtime.h
- controller/src/rbm_u340e_runtime.c
- controller/tests/test_runtime.c
- targets/lfj8/check_h03_link.py
- verification/project-audit/toy02-load-feed.md

### TOY-03

Чат: Codex TOY-03. Claim ID: f014bd3c6bba42f5bb7e5fa23c121d0d.

- docs/lfj8-h03-input-paths.md

### TOY-05

Чат: Codex TOY-05. Claim ID: 2bd31f54ff254c59802d402cf6dabb9b.

- controller/tests/test_controller.c
- verification/project-audit/toy05-adaptation-store.md

## Последние события

| UTC | Задача | Действие | Чат |
| --- | --- | --- | --- |
| 2026-11-20T16:12:22+00:00 | DTC-02 | resume | codex-7bd19ea4-0004-4aec-90c4-f2c6e804c046 |
| 2026-11-20T16:12:16+00:00 | H03-02 | resume | codex-01a1f9a2-d0ae-78d3-86f1-21b27426fd3f |
| 2026-11-20T16:12:09+00:00 | CAN-04 | heartbeat | codex-fea1b366-66b6-4667-8206-915153ca1033 |
| 2026-11-20T16:11:52+00:00 | H03-03 | review | codex-01a1f99f-5cb5-70e0-afd0-60e6b41a5d51 |
| 2026-11-20T16:11:44+00:00 | MODE-01 | claim | codex-4dcfb03f-87a2-4fbd-bf33-08a54073c7e4 |
| 2026-11-20T16:10:33+00:00 | MODE-02 | review | codex-32e6ac79-d63f-49c4-9d44-dd51c88bf0d3 |
| 2026-11-20T16:10:26+00:00 | ORG-01 | claim | codex-integration-01a1f76d-20261120 |
| 2026-11-20T16:10:06+00:00 | CAN-01 | review | codex-4dcfb03f-87a2-4fbd-bf33-08a54073c7e4 |
| 2026-11-20T16:09:48+00:00 | TOY-05 | heartbeat | codex-dtc04-mwp5rm2ofhaxjfi9dss |
| 2026-11-20T16:09:33+00:00 | H03-03 | resume | codex-01a1f99f-5cb5-70e0-afd0-60e6b41a5d51 |
| 2026-11-20T16:09:22+00:00 | H03-02 | review | codex-01a1f9a2-d0ae-78d3-86f1-21b27426fd3f |
| 2026-11-20T16:09:14+00:00 | CAN-04 | claim | codex-fea1b366-66b6-4667-8206-915153ca1033 |
| 2026-11-20T16:08:55+00:00 | MODE-02 | heartbeat | codex-32e6ac79-d63f-49c4-9d44-dd51c88bf0d3 |
| 2026-11-20T16:08:34+00:00 | DTC-02 | review | codex-7bd19ea4-0004-4aec-90c4-f2c6e804c046 |
| 2026-11-20T16:08:24+00:00 | H03-03 | review | codex-01a1f99f-5cb5-70e0-afd0-60e6b41a5d51 |
| 2026-11-20T16:08:20+00:00 | TOY-05 | claim | codex-dtc04-mwp5rm2ofhaxjfi9dss |
| 2026-11-20T16:07:46+00:00 | CAN-01 | review | codex-4dcfb03f-87a2-4fbd-bf33-08a54073c7e4 |
| 2026-11-20T16:07:21+00:00 | H03-04 | complete | codex-h03-04-01a1f76d-20261120 |
| 2026-11-20T16:06:58+00:00 | TOY-02 | review | codex-dtc04-mwp5rm2ofhaxjfi9dss |
| 2026-11-20T16:06:43+00:00 | H03-02 | resume | codex-01a1f9a2-d0ae-78d3-86f1-21b27426fd3f |
| 2026-11-20T16:06:28+00:00 | MODE-02 | heartbeat | codex-32e6ac79-d63f-49c4-9d44-dd51c88bf0d3 |
| 2026-11-20T16:06:24+00:00 | DTC-02 | heartbeat | codex-7bd19ea4-0004-4aec-90c4-f2c6e804c046 |
| 2026-11-20T16:06:05+00:00 | H03-03 | resume | codex-01a1f99f-5cb5-70e0-afd0-60e6b41a5d51 |
| 2026-11-20T16:05:54+00:00 | CAN-01 | heartbeat | codex-4dcfb03f-87a2-4fbd-bf33-08a54073c7e4 |
| 2026-11-20T16:05:43+00:00 | H03-04 | review | codex-h03-04-01a1f76d-20261120 |
| 2026-11-20T16:05:24+00:00 | H03-02 | review | codex-01a1f9a2-d0ae-78d3-86f1-21b27426fd3f |
| 2026-11-20T16:04:54+00:00 | DTC-02 | heartbeat | codex-7bd19ea4-0004-4aec-90c4-f2c6e804c046 |
| 2026-11-20T16:04:41+00:00 | TOY-02 | heartbeat | codex-dtc04-mwp5rm2ofhaxjfi9dss |
| 2026-11-20T16:04:31+00:00 | H03-03 | review | codex-01a1f99f-5cb5-70e0-afd0-60e6b41a5d51 |
| 2026-11-20T16:04:25+00:00 | MODE-02 | claim | codex-32e6ac79-d63f-49c4-9d44-dd51c88bf0d3 |
