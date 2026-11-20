# Кто сейчас работает над проектом

Обновлено UTC: **2026-11-20T16:45:21+00:00**. Изменение № **210**.

Это общий учёт исполнителей. Он не меняет готовность функции по ТЗ и не подтверждает выпуск BIN.
Команды занятия и обновления задачи — в tools/task_coordination.py основной ветки.
Задача и пересекающиеся файлы удерживаются в состояниях «Выполняется», «Ожидает» и «На проверке».
Давняя отметка не освобождается автоматически. Возобновившийся чат обязан проверить свой claim_id.

Каталог задач взят из main b2ca79d006426a9839d64e8553cd81bf71953fe9.

| Задача | Ход работы | Чат | Ветка | Обновление UTC | Что делает / результат |
| --- | --- | --- | --- | --- | --- |
| ORG-01 — Основа проекта и локальная работа | Работа завершена | Основной чат — объединение и проверка результатов \[codex-integration-01a1f76d-20261120\] | codex/integration-01a1f76d-20261120 | 2026-11-20T16:31:04+00:00 | 19 порций объединены в main, свежий аудит и карта опубликованы. 71 тест и M32R PASS, GitHub Actions 44773915924 success. Техническая готовность и два рабочих BIN остаются открытыми. Общие страницы освобождены. / commit b2ca79d006426a9839d64e8553cd81bf71953fe9 |
| TOY-01 — Перенос ядра и единое состояние Toyota | На проверке | Codex TOY-01 — карта переносов GP \[codex-fea1b366-66b6-4667-8206-915153ca1033\] | codex/toy-01-gp-transfer-fea1b366 | 2026-11-20T16:35:39+00:00 | На b2ca79d карта 292 переносов GP 1752→1168 байт; расширенная модель M32R 628 байт выигрыша и запас окна 732→1360. ПК 35 шагов/71 тест, M32R 17 компонентов, стек до/после 704 байта на 23 992 вызовах. Интегратору: учесть отчёт verification/project-audit/toy01-gp-transfer-size.md и два файла в общем аудите. Реальная компоновка и стенд открыты. / commit 8fdce1692a27f0bdf5dcbe0c03d962ab4e87ed39 |
| TOY-02 — Подтверждённая нагрузка двигателя для Toyota | Работа завершена | Codex TOY-02 \[codex-dtc04-mwp5rm2ofhaxjfi9dss\] | codex/toy02-load-feed-mwp5rm2ofhaxjfi9dss | 2026-11-20T16:27:59+00:00 | Порция принята в main 952658b после совместных ПК/M32R проверок. Актуальные доказательства: verification/project-audit/2026-11-20-integration.json. Технические остатки сохранены в карте задач; готовность двух BIN не заявлена. / commit ff7f42b48d58831a8d7a396711042fc45685acd3 |
| TOY-03 — Независимые разрешающие сигналы диапазона | Работа завершена | Codex TOY-03 \[codex-01a1f9a2-d0ae-78d3-86f1-21b27426fd3f\] | codex/toy-03-range-01a1f9a2 | 2026-11-20T16:22:02+00:00 | Порция принята в main 952658b после совместных ПК/M32R проверок. Актуальные доказательства: verification/project-audit/2026-11-20-integration.json. Технические остатки сохранены в карте задач; готовность двух BIN не заявлена. / commit dfc774eee013ba78c6679d3128f493f238f43000 |
| TOY-04 — Полная последовательность переключений | Работа завершена | Codex — цикл переключений Toyota \[codex-32e6ac79-d63f-49c4-9d44-dd51c88bf0d3\] | codex/toy04-cycle-32e6ac79 | 2026-11-20T16:34:19+00:00 | Порция с переходами D принята в опубликованную main b2ca79d. Резерв освобождаю. Полный гидравлический цикл, измерения, нагрузка и R остаются открыты. / commit 439188ac7049314db5c94d261f8e9570092d514b |
| TOY-05 — Обучение и сохранение адаптаций | Работа завершена | Codex TOY-05 \[codex-dtc04-mwp5rm2ofhaxjfi9dss\] | codex/toy05-adaptation-mwp5rm2ofhaxjfi9dss | 2026-11-20T16:33:11+00:00 | Порция принята в main b2ca79d. Совместные проверки и границы: verification/project-audit/2026-11-20-integration-2.json и предшествующий снимок. Технические остатки и отсутствие двух рабочих BIN сохранены в карте. / commit dbc1762ffa86d37e2901b3a62f60b57a71763c24 |
| TOY-06 — Блокировка гидротрансформатора SLU | На проверке | Codex TOY-06 — давление SLU \[codex-fea1b366-66b6-4667-8206-915153ca1033\] | codex/toy-06-slu-pressure-fea1b366 | 2026-11-20T16:44:18+00:00 | 05DCE8 → 055C5E: 15 760 сочетаний совпали с R3, общие 35 шагов ПК/71 тест PASS. M32R: 11 случаев/2 отказа и 17 компонентных прогонов PASS. Расширенная модель: +356 байт во втором окне, запас 324. Интегратору: отчёт verification/project-audit/toy06-slu-pressure.md для общего аудита. 05DC5E, снимок SECONDARY и физический канал открыты. / commit 583cf4a14897616018a6e08ee84dfa5c627b84b9 |
| CAN-01 — Форматы CAN и квалификация RPM/ОЖ | Работа завершена | Codex CAN-01 \[codex-4dcfb03f-87a2-4fbd-bf33-08a54073c7e4\] | codex/can01-1120-c7e4 | 2026-11-20T16:26:06+00:00 | Reviewed RX epoch work integrated by 952658b and recorded in the shared audit. This closes the reservation; stock CAN startup and hardware verification remain open. / commit ca268743dfe173f93121d6b9148e0951932cfc9d |
| CAN-02 — Общий диспетчер CAN13 | Работа завершена | Codex CAN-02 \[codex-dtc04-mwp5rm2ofhaxjfi9dss\] | codex/can02-telemetry-timeout-mwp5rm2ofhaxjfi9dss | 2026-11-20T16:34:59+00:00 | Принято в опубликованную main b2ca79d после независимых и общих проверок. Аудит integration-2 содержит результаты и ограничения. Технические остатки ТЗ остаются открытыми. / commit b48b4e50878c8173a40d65134213fbb8fdc37aa1 |
| CAN-03 — Штатный запуск, IRQ и восстановление CAN0 | На проверке | Codex CAN-03 reset generation \[codex-4dcfb03f-87a2-4fbd-bf33-08a54073c7e4\] | codex/can03-epoch-1120-c7e4 | 2026-11-20T16:39:51+00:00 | Native H03 setup hook revokes TX13 grant before OEM and advances generation on return. PASS 16 lifecycle, 12 TX gate, 17 M32R components. BasicCAN flags persist in RAM shadow. See verification/project-audit/can03-native-epoch.md; target RAM, RX drain and bench remain open. / commit 6fc5a51975cd6bbbdf5bc4985d5d61b811435b6b |
| CAN-04 — Запрос снижения момента по RB | Выполняется | Codex CAN-04 TX loss \[codex-4dcfb03f-87a2-4fbd-bf33-08a54073c7e4\] | codex/can04-tx-loss-1120-c7e4 | 2026-11-20T16:43:43+00:00 | Host and M32R regressions reproduce and prevent wrong-ID completion and old lease reuse; 17 M32R components pass. Checking full PC suite and replaying the Bosch dialogue. |
| CAN-05 — Полнота штатного обмена Chery | На проверке | Codex CAN-05 RX age \[codex-4dcfb03f-87a2-4fbd-bf33-08a54073c7e4\] | codex/can05-rx-age-1120-c7e4 | 2026-11-20T16:34:04+00:00 | Capture-time expiry and ordering for queued 1AE operands. Targeted receiver and all 65536 round-trip vectors PASS, 35 PC steps / 70 tests with S03 rerun, existing ST10 image PASS_OFFLINE_ONLY. Evidence verification/project-audit/can05-rx-age.md. Native capture and calibration remain open. / commit 82947a42cfb33ef5350af1ce98e39055ba6a1508 |
| ECU-01 — Проверочная сборка Bosch E4M3 | На проверке | Codex ECU-01 \[codex-4dcfb03f-87a2-4fbd-bf33-08a54073c7e4\] | codex/ecu01-1120-c7e4 | 2026-11-20T16:25:01+00:00 | E4M3 checksum coverage now requires all 51 exact record offsets. Real omission injection rejected. Eight profiles byte-identical to baseline, 68 unit tests and ordinary compact ST10 PASS_OFFLINE_ONLY. Evidence verification/project-audit/ecu01-checksum-coverage.md. Update shared audit at integration. / commit 84380128b8db2e0a6b24b297dd40aa020598e3ce |
| ECU-02 — Калибровка момента и работа двигателя | На проверке | Codex — обороты и отпускание момента Bosch \[codex-32e6ac79-d63f-49c4-9d44-dd51c88bf0d3\] | codex/ecu02-torque-rpm-32e6ac79 | 2026-11-20T16:35:57+00:00 | Передаю интегратору. Точный обычный компактный образ E4M3 OFFLINE_ONLY: 4 границы RPM, 6 отзывов через air/fast/load, нулевой статус и защита старого токена PASS. Повтор 26 команд и сквозной диалог H03 с потерей статуса PASS. Отчёт ecu02-torque-rpm-guard.md. Аппаратный пуск и калибровки открыты. / commit 06eacf1ff4f42e423886b4b25b849ead054ac924 |
| H03-01 — Выбранная основа 9E1C и карта подключения | На проверке | Codex H03-01 \[codex-dtc04-mwp5rm2ofhaxjfi9dss\] | codex/h03-01-base-guard-mwp5rm2ofhaxjfi9dss | 2026-11-20T16:40:16+00:00 | Строгая сверка H03 с реестром добавлена. Подлинный H03 PASS, изменённая копия с тем же ID отвергнута. Два теста и SOURCES PASS. Отчёт verification/project-audit/h03-01-base-guard.md. Требуется актуализация общего аудита интегратором. / commit cf488af90f0e7beca13fe3c02599cd4854f3668e |
| H03-02 — S51, S83 и температура ATF | На проверке | Codex — привязка ATF H03 \[codex-01a1f9a2-d0ae-78d3-86f1-21b27426fd3f\] | codex/h03-02-atf-01a1f9a2 | 2026-11-20T16:18:28+00:00 | Добавлен условный поставщик TML0: PRS1=9, Clock Bus 1 и внешнее подтверждение физического 1 МГц. M32R: 11 пар и 3 отрицательных проверки PASS; стек 92/120/72 байта. Физические 1 МГц, размещение и IRQ остаются. / commit a376f561dacb33793b7bb65e57a2ea18fdcea08d |
| H03-03 — Единое расписание и запуск приложения H03 | Выполняется | Codex — foreground H03 \[codex-01a1f99f-5cb5-70e0-afd0-60e6b41a5d51\] | codex/h03-03-foreground-01a1f99f | 2026-11-20T16:45:02+00:00 | Запуск и отказы в M32R прошли, проверяю размещение стартового API в адресной компоновке H03. / commit 7122fe326eff5c0f165caa527fd21c6a293743bf |
| H03-04 — Память, стек и сервисные пути | На проверке | Codex — сервисные границы RAM H03 \[codex-32e6ac79-d63f-49c4-9d44-dd51c88bf0d3\] | codex/h03-service-spans-32e6ac79 | 2026-11-20T16:27:39+00:00 | Передаю интегратору. 35 сценариев допуска, все 2380 байт актуальных кандидатов покрыты разрешёнными интервалами; процедуры записи не запускались. STORAGE, M32R, NATIVE и Python PASS. Отчёт h03-service-ram-spans.md. Изоляция прямых/отложенных сервисных записей, запуск и владение RAM открыты. / commit e4ac4b09967f7edf86cf2c1911218ba34e260b24 |
| H03-05 — SLT, силовые выходы и реакция на отказ | Выполняется | Codex — штатное отключение SLT \[codex-01a1f9a2-d0ae-78d3-86f1-21b27426fd3f\] | codex/h03-05-p0745-01a1f9a2 | 2026-11-20T16:44:55+00:00 | Добавляю проверку целевого ELF против страниц Virtual Flash, выбираемых штатным H03. Тестирую все страницы только в симуляторе. |
| IO-01 — Два дополнительных реле | Отложена владельцем | — | — | — | — |
| VSS-01 — Точный расчёт VSS и скорость по CAN | На проверке | Codex VSS-01 \[codex-dtc04-mwp5rm2ofhaxjfi9dss\] | codex/vss01-exact-arithmetic-mwp5rm2ofhaxjfi9dss | 2026-11-20T16:22:43+00:00 | Точная VSS арифметика устраняет промежуточное переполнение. 25 000 сравнений, PC 33 шага/65 тестов, M32R 17 компонентов, Bosch C7FF/C800/FFFF PASS по ожидаемому поведению. Параметры VSS-02 и стенд открыты. Отчёт verification/project-audit/vss01-exact-arithmetic.md. / commit d05896bcac7b731f8d3f85b9aaebd3394e32473c |
| VSS-02 — Кинематика и параметры реальной скорости | На проверке | Codex VSS-02 \[codex-dtc04-mwp5rm2ofhaxjfi9dss\] | codex/vss02-measurement-check-mwp5rm2ofhaxjfi9dss | 2026-11-20T16:37:13+00:00 | Сверка TML0 по независимому времени и допуску ppm, перенос, неправильная частота и остановка проверены. PC 35 шагов/82 теста, M32R 17 компонентов PASS. Реальная частота TML0 и стенд открыты, отчёт verification/project-audit/vss02-measurement-check.md. / commit 0ce144d22b18682e3384b05ec602224f8ec6d159 |
| PANEL-01 — Импульсы Bosch на приборную панель | Отложена владельцем | — | — | — | — |
| MODE-01 — Логика шести положений и кнопок | Работа завершена | Codex MODE-01 \[codex-4dcfb03f-87a2-4fbd-bf33-08a54073c7e4\] | codex/mode01-1120-c7e4 | 2026-11-20T16:31:25+00:00 | Reviewed shift-button conflict fix integrated in b2ca79d with PC/M32R evidence in integration-2. Released this reservation; hardware input and hydraulic execution remain open. / commit ed33ea93653f7bcbc2c6f13736fe1424335085e6 |
| MODE-02 — Подключение селектора, Tiptronic и Overdrive | На проверке | Codex MODE-02 — публикация ADC H03 \[01a1f9c7-675a-78c3-be98-5bd65e44995c\] | codex/mode02-h03-selector-01a1f9c7 | 2026-11-20T16:37:36+00:00 | Передаю интегратору привязку публикации AN2 к штатной записи H03: 4 пары и 3 отрицательные проверки M32R, ПК 35 шагов/71 тест, M32R link и 17 компонентов PASS. Отчёт verification/project-audit/mode02-h03-selector-adc.md. При приёмке внести 3 новых файла в общий аудит и выполнить complete после публикации main. Штатный callback, часы/стек, кнопки и стенд остаются открыты. / commit f92fde84f590460d713dee020ee5ddc6ccd089e4 |
| MODE-03 — Окончательная политика режимов | На проверке | Codex MODE-03 — матрица режимов \[codex-fea1b366-66b6-4667-8206-915153ca1033\] | codex/mode-03-policy-fea1b366 | 2026-11-20T16:27:03+00:00 | Штатная матрица ПК: 128 конфигураций запуска и 501 760 сценариев заявок PASS. Все 35 шагов ПК прошли; донорский тест S03 повторён отдельно с проверенным входом. Интегратору: учесть новые файлы и отчёт verification/project-audit/mode03-policy-matrix.md в аудите. Политика выпуска и подключение к циклу H03 открыты. / commit dd4fdbc2862093359df9329d7e6e9ab211d13940 |
| SRC-01 — Реестр происхождения и контроль исходников | На проверке | Codex SRC-01 \[codex-dtc04-mwp5rm2ofhaxjfi9dss\] | codex/src01-donor-pins-mwp5rm2ofhaxjfi9dss | 2026-11-20T16:43:47+00:00 | Проверка pinned Git объектов R1–R4 добавлена. SOURCES: ТЗ, S01–S04, H03 и четыре ревизии PASS; два теста, совместимая команда R1 и отказ для неверного клона проверены. Отчёт verification/project-audit/src01-donor-pins.md; снимок для интегратора. / commit 72f71983154edb4dcc7f0b3dc931bebfdb0d9b6d |
| AUD-01 — Программный аудит истории E4M3 | Выполняется | Codex AUD-01 \[codex-dtc04-mwp5rm2ofhaxjfi9dss\] | codex/aud01-pinned-replay-mwp5rm2ofhaxjfi9dss | 2026-11-20T16:45:11+00:00 | Привязываю не только историческую трассу E4M3, но и инструменты ST10 к закреплённому Git-коммиту. Проверю из клона без checkout. |
| DTC-01 — Прикладной сеанс и статусы Chery | Работа завершена | Codex DTC-01 \[codex-4dcfb03f-87a2-4fbd-bf33-08a54073c7e4\] | codex/dtc01-1120-c7e4 | 2026-11-20T16:30:54+00:00 | Порция принята в main b2ca79d. Совместные проверки и границы: verification/project-audit/2026-11-20-integration-2.json и предшествующий снимок. Технические остатки и отсутствие двух рабочих BIN сохранены в карте. / commit 79d853bcd09a13b733907eccc3e1ea6dfe642db7 |
| DTC-02 — Штатный приём BasicCAN для диагностического сеанса | Выполняется | Codex — штатный RX BasicCAN H03 \[codex-7bd19ea4-0004-4aec-90c4-f2c6e804c046\] | codex/dtc02-basiccan-7bd19ea4 | 2026-11-20T16:43:59+00:00 | Реализована единая выборка RX14/15 с порядком по CAN timestamp. Семь сценариев на ПК и M32R прошли, включая сеанс 10 86 перед 17 FF 00, оборот, переполнение, потерю и BusOff. Повторяю общие проверки. |
| DTC-03 — Все диагностические события и соответствия Toyota/Chery | Выполняется | Codex DTC-03 — монитор цепи ATF H03 \[01a1f9c7-675a-78c3-be98-5bd65e44995c\] | codex/dtc03-atf-monitor-01a1f9c7 | 2026-11-20T16:45:21+00:00 | 20 проверок пройдены. Включаю адаптер в штатную сборку H03 и её манифест. Общий реестр остаётся у интегратора. |
| DTC-04 — Хранение DTC после выключения питания | На проверке | Codex — подтверждение долговечной очистки DTC \[codex-32e6ac79-d63f-49c4-9d44-dd51c88bf0d3\] | codex/dtc04-durable-clear-32e6ac79 | 2026-11-20T16:43:22+00:00 | Передаю интегратору. При настроенном backend 54 FF 00 выдаётся только после подтверждения пустого журнала. При отказе сохраняется RAM, TX не ставится. 30 прерываний и повтор PASS, PC 35 шагов/71 тест, M32R журнал и 17 компонентов PASS. Отчёт dtc04-durable-clear.md. Носитель и подключение H03 открыты. / commit acd7d12c2e65cbb521331b175365aa2ae8ffc343 |
| REL-01 — Два целевых BIN и воспроизводимый комплект | Работа завершена | Codex — комплект двух BIN \[codex-01a1f9a2-d0ae-78d3-86f1-21b27426fd3f\] | codex/rel-01-pair-01a1f9a2 | 2026-11-20T16:23:09+00:00 | Порция принята в main 952658b после совместных ПК/M32R проверок. Актуальные доказательства: verification/project-audit/2026-11-20-integration.json. Технические остатки сохранены в карте задач; готовность двух BIN не заявлена. / commit b174397fe79ebdb0d0749bcee31fe7f198435a28 |
| REL-02 — Приёмка новой связки на оборудовании | Свободна | — | — | — | — |

## Зарезервированные файлы

### AUD-01

Чат: Codex AUD-01. Claim ID: 69a90e88e1b54af298f0f4e5760e308f.

- targets/bosch/replay_e4m3_torque.py
- verification/project-audit/aud01-pinned-replay.md

### CAN-03

Чат: Codex CAN-03 reset generation. Claim ID: 0b028669dc7e44b69526dde8046610db.

- targets/lfj8/check_h03_can_lifecycle.py
- targets/lfj8/h03_can0_setup_hook.S
- targets/lfj8/h03_can_lifecycle_test.S
- verification/project-audit/can03-native-epoch.md

### CAN-04

Чат: Codex CAN-04 TX loss. Claim ID: 8ac9d38cec054d318a8eb919f6783de2.

- targets/lfj8/lfj8_h03_torque_can.c
- targets/lfj8/test_lfj8_h03_torque_can.c
- verification/project-audit/can04-tx-lease-loss.md

### CAN-05

Чат: Codex CAN-05 RX age. Claim ID: 8bc1c70042a844479c03009561a5e586.

- targets/bosch/chery_torque_rx.c
- targets/bosch/chery_torque_rx.h
- targets/bosch/test_chery_torque_rx.c
- verification/project-audit/can05-rx-age.md

### DTC-02

Чат: Codex — штатный RX BasicCAN H03. Claim ID: 36f7538204a944d68df89f474cc590e4.

- targets/lfj8/check_h03_dtc_basiccan.py
- targets/lfj8/check_h03_dtc_foreground.py
- targets/lfj8/h03_dtc_rx_hook.S
- targets/lfj8/h03_dtc_rx_hook_fixture.c
- targets/lfj8/lfj8_h03_dtc_foreground.c
- targets/lfj8/lfj8_h03_dtc_foreground.h
- targets/lfj8/lfj8_h03_dtc_rx_queue.c
- targets/lfj8/lfj8_h03_dtc_rx_queue.h
- targets/lfj8/test_lfj8_h03_dtc_foreground.c
- targets/lfj8/test_lfj8_h03_dtc_rx_queue.c
- verification/project-audit/dtc02-basiccan-order.md
- verification/project-audit/dtc02-basiccan.md
- verification/project-audit/dtc02-foreground.md
- verification/project-audit/dtc02-native-rx-hook.md
- verification/project-audit/dtc02-preclear-capture.md

### DTC-03

Чат: Codex DTC-03 — монитор цепи ATF H03. Claim ID: d048f56f20764374915133ea2b7bbcde.

- targets/lfj8/build.py
- targets/lfj8/check_h03_atf_fault.py
- targets/lfj8/lfj8_h03_atf_fault.c
- targets/lfj8/lfj8_h03_atf_fault.h
- verification/project-audit/dtc03-h03-atf-monitor.md

### DTC-04

Чат: Codex — подтверждение долговечной очистки DTC. Claim ID: 08c2265b7b3d431fb60bc73ce5c54109.

- diagnostics/chery_dtc.c
- diagnostics/chery_dtc.h
- diagnostics/chery_dtc_can.c
- diagnostics/chery_dtc_can.h
- diagnostics/chery_dtc_link.c
- diagnostics/chery_dtc_link.h
- diagnostics/test_chery_dtc_journal.c
- diagnostics/test_chery_dtc_link.c
- verification/project-audit/dtc04-durable-clear.md

### ECU-01

Чат: Codex ECU-01. Claim ID: a1532b4af90d4794aec52c99f7b434a2.

- targets/bosch/build.py
- tests/test_bosch_build_integrity.py
- verification/project-audit/ecu01-checksum-coverage.md

### ECU-02

Чат: Codex — обороты и отпускание момента Bosch. Claim ID: c8de734571c443c3b11766566ad20891.

- targets/bosch/verify_e4m3_torque_rpm.py
- verification/project-audit/ecu02-torque-rpm-guard.md

### H03-01

Чат: Codex H03-01. Claim ID: 125a9fc02e0b4315aa93ce8efbe1bda1.

- tests/test_inspect_lfj8_tcm.py
- tools/inspect_lfj8_tcm.py
- verification/project-audit/h03-01-base-guard.md

### H03-02

Чат: Codex — привязка ATF H03. Claim ID: 11e70992d32245529e20626f4b9bd867.

- docs/lfj8-h03-atf-native.md
- targets/lfj8/check_h03_atf_native.py
- targets/lfj8/h03_atf_hook_fixture.c
- targets/lfj8/h03_atf_hooks.S
- targets/lfj8/lfj8_h03_atf.h
- targets/lfj8/lfj8_h03_atf_target.c
- targets/lfj8/lfj8_h03_atf_target.h
- targets/lfj8/lfj8_h03_atf_tml0.c
- targets/lfj8/test_lfj8_h03_atf.c

### H03-03

Чат: Codex — foreground H03. Claim ID: 4998c6dec95f4b50b8a66b64e5679c7d.

- docs/lfj8-h03-control-cycle.md
- targets/lfj8/check_h03_link.py
- targets/lfj8/check_h03_phase_wait.py
- targets/lfj8/h03_phase_wait_fixture.c
- targets/lfj8/lfj8_h03_mmio.c
- targets/lfj8/lfj8_h03_mmio.h
- targets/lfj8/lfj8_h03_phase_startup.c
- targets/lfj8/lfj8_h03_phase_startup.h
- verification/e4m3-can-9e1c/h03-phase-wait.json
- verification/project-audit/2026-11-20-h03-wait-stack.json

### H03-04

Чат: Codex — сервисные границы RAM H03. Claim ID: a16c78536102430583d910e97b8385d3.

- targets/lfj8/check_h03_service_isolation.py
- verification/project-audit/h03-service-ram-spans.md

### H03-05

Чат: Codex — штатное отключение SLT. Claim ID: 806db3cf9bd24f39aaf4b40aeb1d341b.

- docs/lfj8-h03-flash.md
- docs/lfj8-slt-calibration.md
- targets/lfj8/check_h03_flash_policy.py
- targets/lfj8/check_h03_slt_fault.py
- targets/lfj8/h03_slt_fault_hook.S
- targets/lfj8/lfj8_h03_takeover.c
- targets/lfj8/lfj8_h03_takeover.h
- targets/lfj8/test_lfj8_h03_takeover.c

### MODE-02

Чат: Codex MODE-02 — публикация ADC H03. Claim ID: e02562d3b21f423d914c1c00a9c88077.

- targets/lfj8/check_h03_selector_adc.py
- targets/lfj8/h03_selector_adc_fixture.c
- targets/lfj8/h03_selector_adc_hook.S
- verification/project-audit/mode02-h03-selector-adc.md

### MODE-03

Чат: Codex MODE-03 — матрица режимов. Claim ID: b0a3618e8676435c94101b0abb236b6a.

- controller/build.py
- controller/tests/test_mode_policy.c
- verification/project-audit/mode03-policy-matrix.md

### SRC-01

Чат: Codex SRC-01. Claim ID: abd55696a19e48a1aaf3a4b0e23f7414.

- tests/test_verify_sources.py
- tools/verify_sources.py
- verification/project-audit/src01-donor-pins.md

### TOY-01

Чат: Codex TOY-01 — карта переносов GP. Claim ID: 4b00bd7fdda2433d8439e95c7b0b1454.

- controller/hydraulic_port.py
- targets/lfj8/check_h03_toyota_stack.py
- verification/project-audit/toy01-gp-transfer-size.md

### TOY-06

Чат: Codex TOY-06 — давление SLU. Claim ID: a8e9ff099358496bacacf60bfcc8aa84.

- targets/lfj8/check_toyota_slu.py
- targets/lfj8/lfj8_h03_slu.c
- targets/lfj8/lfj8_h03_slu.h
- targets/lfj8/test_lfj8_h03_slu_secondary.c
- verification/project-audit/toy06-slu-pressure.md

### VSS-01

Чат: Codex VSS-01. Claim ID: 698c00d00af84972b5562bc8498c8628.

- targets/lfj8/lfj8_bridge.c
- targets/lfj8/test_lfj8_vss_arithmetic.c
- verification/project-audit/vss01-exact-arithmetic.md

### VSS-02

Чат: Codex VSS-02. Claim ID: 6514c671a5e342f0bf87a0fcd4a383c0.

- tests/test_vss_measurements.py
- tools/check_vss_measurements.py
- verification/project-audit/vss02-measurement-check.md

## Последние события

| UTC | Задача | Действие | Чат |
| --- | --- | --- | --- |
| 2026-11-20T16:45:21+00:00 | DTC-03 | heartbeat | 01a1f9c7-675a-78c3-be98-5bd65e44995c |
| 2026-11-20T16:45:11+00:00 | AUD-01 | claim | codex-dtc04-mwp5rm2ofhaxjfi9dss |
| 2026-11-20T16:45:02+00:00 | H03-03 | heartbeat | codex-01a1f99f-5cb5-70e0-afd0-60e6b41a5d51 |
| 2026-11-20T16:44:55+00:00 | H03-05 | resume | codex-01a1f9a2-d0ae-78d3-86f1-21b27426fd3f |
| 2026-11-20T16:44:18+00:00 | TOY-06 | review | codex-fea1b366-66b6-4667-8206-915153ca1033 |
| 2026-11-20T16:44:10+00:00 | DTC-03 | heartbeat | 01a1f9c7-675a-78c3-be98-5bd65e44995c |
| 2026-11-20T16:43:59+00:00 | DTC-02 | heartbeat | codex-7bd19ea4-0004-4aec-90c4-f2c6e804c046 |
| 2026-11-20T16:43:47+00:00 | SRC-01 | review | codex-dtc04-mwp5rm2ofhaxjfi9dss |
| 2026-11-20T16:43:43+00:00 | CAN-04 | heartbeat | codex-4dcfb03f-87a2-4fbd-bf33-08a54073c7e4 |
| 2026-11-20T16:43:22+00:00 | DTC-04 | review | codex-32e6ac79-d63f-49c4-9d44-dd51c88bf0d3 |
| 2026-11-20T16:43:12+00:00 | H03-03 | resume | codex-01a1f99f-5cb5-70e0-afd0-60e6b41a5d51 |
| 2026-11-20T16:42:49+00:00 | CAN-04 | heartbeat | codex-4dcfb03f-87a2-4fbd-bf33-08a54073c7e4 |
| 2026-11-20T16:42:29+00:00 | SRC-01 | heartbeat | codex-dtc04-mwp5rm2ofhaxjfi9dss |
| 2026-11-20T16:41:39+00:00 | H03-05 | review | codex-01a1f9a2-d0ae-78d3-86f1-21b27426fd3f |
| 2026-11-20T16:41:24+00:00 | CAN-04 | claim | codex-4dcfb03f-87a2-4fbd-bf33-08a54073c7e4 |
| 2026-11-20T16:41:21+00:00 | SRC-01 | claim | codex-dtc04-mwp5rm2ofhaxjfi9dss |
| 2026-11-20T16:41:02+00:00 | DTC-03 | heartbeat | 01a1f9c7-675a-78c3-be98-5bd65e44995c |
| 2026-11-20T16:40:57+00:00 | DTC-02 | resume | codex-7bd19ea4-0004-4aec-90c4-f2c6e804c046 |
| 2026-11-20T16:40:44+00:00 | H03-03 | review | codex-01a1f99f-5cb5-70e0-afd0-60e6b41a5d51 |
| 2026-11-20T16:40:32+00:00 | DTC-04 | heartbeat | codex-32e6ac79-d63f-49c4-9d44-dd51c88bf0d3 |
| 2026-11-20T16:40:16+00:00 | H03-01 | review | codex-dtc04-mwp5rm2ofhaxjfi9dss |
| 2026-11-20T16:40:03+00:00 | TOY-06 | heartbeat | codex-fea1b366-66b6-4667-8206-915153ca1033 |
| 2026-11-20T16:39:51+00:00 | CAN-03 | review | codex-4dcfb03f-87a2-4fbd-bf33-08a54073c7e4 |
| 2026-11-20T16:39:43+00:00 | H03-01 | heartbeat | codex-dtc04-mwp5rm2ofhaxjfi9dss |
| 2026-11-20T16:39:32+00:00 | DTC-03 | claim | 01a1f9c7-675a-78c3-be98-5bd65e44995c |
| 2026-11-20T16:39:00+00:00 | DTC-02 | review | codex-7bd19ea4-0004-4aec-90c4-f2c6e804c046 |
| 2026-11-20T16:38:56+00:00 | CAN-03 | heartbeat | codex-4dcfb03f-87a2-4fbd-bf33-08a54073c7e4 |
| 2026-11-20T16:38:48+00:00 | H03-01 | claim | codex-dtc04-mwp5rm2ofhaxjfi9dss |
| 2026-11-20T16:38:33+00:00 | H03-05 | resume | codex-01a1f9a2-d0ae-78d3-86f1-21b27426fd3f |
| 2026-11-20T16:38:27+00:00 | DTC-04 | claim | codex-32e6ac79-d63f-49c4-9d44-dd51c88bf0d3 |
