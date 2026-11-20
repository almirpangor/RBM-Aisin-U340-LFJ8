# Кто сейчас работает над проектом

Обновлено UTC: **2026-11-20T17:00:49+00:00**. Изменение № **253**.

Это общий учёт исполнителей. Он не меняет готовность функции по ТЗ и не подтверждает выпуск BIN.
Команды занятия и обновления задачи — в tools/task_coordination.py основной ветки.
Задача и пересекающиеся файлы удерживаются в состояниях «Выполняется», «Ожидает» и «На проверке».
Давняя отметка не освобождается автоматически. Возобновившийся чат обязан проверить свой claim_id.

Каталог задач взят из main b2ca79d006426a9839d64e8553cd81bf71953fe9.

| Задача | Ход работы | Чат | Ветка | Обновление UTC | Что делает / результат |
| --- | --- | --- | --- | --- | --- |
| ORG-01 — Основа проекта и локальная работа | Работа завершена | Основной чат — объединение и проверка результатов \[codex-integration-01a1f76d-20261120\] | codex/integration-01a1f76d-20261120 | 2026-11-20T16:31:04+00:00 | 19 порций объединены в main, свежий аудит и карта опубликованы. 71 тест и M32R PASS, GitHub Actions 44773915924 success. Техническая готовность и два рабочих BIN остаются открытыми. Общие страницы освобождены. / commit b2ca79d006426a9839d64e8553cd81bf71953fe9 |
| TOY-01 — Перенос ядра и единое состояние Toyota | На проверке | Codex TOY-01 — карта переносов GP \[codex-fea1b366-66b6-4667-8206-915153ca1033\] | codex/toy-01-gp-transfer-fea1b366 | 2026-11-20T16:35:39+00:00 | На b2ca79d карта 292 переносов GP 1752→1168 байт; расширенная модель M32R 628 байт выигрыша и запас окна 732→1360. ПК 35 шагов/71 тест, M32R 17 компонентов, стек до/после 704 байта на 23 992 вызовах. Интегратору: учесть отчёт verification/project-audit/toy01-gp-transfer-size.md и два файла в общем аудите. Реальная компоновка и стенд открыты. / commit 8fdce1692a27f0bdf5dcbe0c03d962ab4e87ed39 |
| TOY-02 — Подтверждённая нагрузка двигателя для Toyota | На проверке | Codex TOY-02 — допуск нагрузки в цикл \[codex-fea1b366-66b6-4667-8206-915153ca1033\] | codex/toy-02-cycle-load-fea1b366 | 2026-11-20T16:52:23+00:00 | Квалифицированный вход цикла публикует нагрузку до расписания и учитывает старейшую метку; отказ отзывает результат. ПК 37 шагов/71 тест, M32R целевой сценарий +17 компонентов, SIGNALS PASS. Второе окно +168 байт; прежняя точка 720 байт наблюдаемого стека. Интегратору: отчёт verification/project-audit/toy02-cycle-load-gate.md. Источник/шкалы Bosch, бюджет давности и foreground остаются открыты. / commit 3acdebe7db08758da32805ec04bd77ff9e3ba329 |
| TOY-03 — Независимые разрешающие сигналы диапазона | На проверке | Codex TOY-03 — квалификация независимых входов \[01a1f9c7-675a-78c3-be98-5bd65e44995c\] | codex/toy03-range-freshness-01a1f9c7 | 2026-11-20T16:56:25+00:00 | Передаю интегратору квалификатор независимых GP−5722 и GP−5250.2. ПК 35 шагов/71 тест. M32R 32 сочетания, индивидуальная давность, смена поколения, полный link и 17 компонентов PASS. Отчёт verification/project-audit/toy03-range-freshness.md. При приёмке учесть 3 файла кода в аудите и выполнить complete после публикации main. Физические источники и вызов в штатном цикле открыты. / commit e7264c651d3fafe77e4bbff78e5a8fd8aa4e25ee |
| TOY-04 — Полная последовательность переключений | На проверке | Codex — переключения Toyota под нагрузкой \[codex-32e6ac79-d63f-49c4-9d44-dd51c88bf0d3\] | codex/toy04-loaded-map-32e6ac79 | 2026-11-20T16:50:12+00:00 | Передаю интегратору. 24 точки D при двух синтетических нагрузках, пороги из S01, GP из квалифицированного снимка, логические S1/S2 и потеря события PASS. PC 35 шагов/71 тест, M32R 17 компонентов, NATIVE 16+15. Отчёт toy04-loaded-gears.md. Физическая нагрузка, R, ручное управление и гидравлика открыты. / commit 08b06eb14f7ccb6f46b3589f7f0131e143d529d8 |
| TOY-05 — Обучение и сохранение адаптаций | На проверке | Codex — восстановление адаптаций Toyota \[codex-32e6ac79-d63f-49c4-9d44-dd51c88bf0d3\] | codex/toy05-safe-restore-32e6ac79 | 2026-11-20T16:57:40+00:00 | Восстановление после повреждения записи сброса адаптаций проверено на ПК и M32R. Отчёт verification/project-audit/toy05-recovery-policy.md. Запуск H03 и страницы NVM открыты. Снимок аудита и реестр передаю интегратору. / commit 8d6a6f1f62d70c827531f672c98d309e708df595 |
| TOY-06 — Блокировка гидротрансформатора SLU | На проверке | Codex TOY-06 — давление SLU \[codex-fea1b366-66b6-4667-8206-915153ca1033\] | codex/toy-06-slu-pressure-fea1b366 | 2026-11-20T16:44:18+00:00 | 05DCE8 → 055C5E: 15 760 сочетаний совпали с R3, общие 35 шагов ПК/71 тест PASS. M32R: 11 случаев/2 отказа и 17 компонентных прогонов PASS. Расширенная модель: +356 байт во втором окне, запас 324. Интегратору: отчёт verification/project-audit/toy06-slu-pressure.md для общего аудита. 05DC5E, снимок SECONDARY и физический канал открыты. / commit 583cf4a14897616018a6e08ee84dfa5c627b84b9 |
| CAN-01 — Форматы CAN и квалификация RPM/ОЖ | На проверке | Codex CAN-01 FullCAN coherence \[codex-4dcfb03f-87a2-4fbd-bf33-08a54073c7e4\] | codex/can01-rx-coherence-1120-c7e4 | 2026-11-20T16:57:02+00:00 | Revalidate FullCAN RR and EXTID after the copy. Reproduced RR-loss bug. All 35 PC checks including 71 unit tests, 17 M32R components and Bosch PASS_OFFLINE_ONLY. Evidence verification/project-audit/can01-rx-coherence.md. OEM binding and hardware open. / commit 6820992a15300275c3dd9c98398151e661a42925 |
| CAN-02 — Общий диспетчер CAN13 | Выполняется | Codex CAN-02 telemetry submission \[codex-4dcfb03f-87a2-4fbd-bf33-08a54073c7e4\] | codex/can02-telemetry-submit-1120-c7e4 | 2026-11-20T16:59:25+00:00 | Propagate fatal telemetry submission errors to the slot13 broker in the same poll, with model coverage for BusOff across submission. |
| CAN-03 — Штатный запуск, IRQ и восстановление CAN0 | На проверке | Codex CAN-03 reset generation \[codex-4dcfb03f-87a2-4fbd-bf33-08a54073c7e4\] | codex/can03-epoch-1120-c7e4 | 2026-11-20T16:39:51+00:00 | Native H03 setup hook revokes TX13 grant before OEM and advances generation on return. PASS 16 lifecycle, 12 TX gate, 17 M32R components. BasicCAN flags persist in RAM shadow. See verification/project-audit/can03-native-epoch.md; target RAM, RX drain and bench remain open. / commit 6fc5a51975cd6bbbdf5bc4985d5d61b811435b6b |
| CAN-04 — Запрос снижения момента по RB | На проверке | Codex CAN-04 TX loss \[codex-4dcfb03f-87a2-4fbd-bf33-08a54073c7e4\] | codex/can04-tx-loss-1120-c7e4 | 2026-11-20T16:45:25+00:00 | Wrong-ID TX13 completion and BusOff now revoke RB torque confirmation and block reuse until a fresh generation. 35 PC steps/71 tests, 17 M32R component runs, Bosch normal and lost-status dialogues PASS_OFFLINE_ONLY. See verification/project-audit/can04-tx-lease-loss.md. / commit e02095c6b8d294dacd71db21ea36f970019d0790 |
| CAN-05 — Полнота штатного обмена Chery | На проверке | Codex CAN-05 RX age \[codex-4dcfb03f-87a2-4fbd-bf33-08a54073c7e4\] | codex/can05-rx-age-1120-c7e4 | 2026-11-20T16:34:04+00:00 | Capture-time expiry and ordering for queued 1AE operands. Targeted receiver and all 65536 round-trip vectors PASS, 35 PC steps / 70 tests with S03 rerun, existing ST10 image PASS_OFFLINE_ONLY. Evidence verification/project-audit/can05-rx-age.md. Native capture and calibration remain open. / commit 82947a42cfb33ef5350af1ce98e39055ba6a1508 |
| ECU-01 — Проверочная сборка Bosch E4M3 | На проверке | Codex ECU-01 \[codex-4dcfb03f-87a2-4fbd-bf33-08a54073c7e4\] | codex/ecu01-1120-c7e4 | 2026-11-20T16:25:01+00:00 | E4M3 checksum coverage now requires all 51 exact record offsets. Real omission injection rejected. Eight profiles byte-identical to baseline, 68 unit tests and ordinary compact ST10 PASS_OFFLINE_ONLY. Evidence verification/project-audit/ecu01-checksum-coverage.md. Update shared audit at integration. / commit 84380128b8db2e0a6b24b297dd40aa020598e3ce |
| ECU-02 — Калибровка момента и работа двигателя | На проверке | Codex — обороты и отпускание момента Bosch \[codex-32e6ac79-d63f-49c4-9d44-dd51c88bf0d3\] | codex/ecu02-torque-rpm-32e6ac79 | 2026-11-20T16:35:57+00:00 | Передаю интегратору. Точный обычный компактный образ E4M3 OFFLINE_ONLY: 4 границы RPM, 6 отзывов через air/fast/load, нулевой статус и защита старого токена PASS. Повтор 26 команд и сквозной диалог H03 с потерей статуса PASS. Отчёт ecu02-torque-rpm-guard.md. Аппаратный пуск и калибровки открыты. / commit 06eacf1ff4f42e423886b4b25b849ead054ac924 |
| H03-01 — Выбранная основа 9E1C и карта подключения | На проверке | Codex H03-01 \[codex-dtc04-mwp5rm2ofhaxjfi9dss\] | codex/h03-01-base-guard-mwp5rm2ofhaxjfi9dss | 2026-11-20T16:40:16+00:00 | Строгая сверка H03 с реестром добавлена. Подлинный H03 PASS, изменённая копия с тем же ID отвергнута. Два теста и SOURCES PASS. Отчёт verification/project-audit/h03-01-base-guard.md. Требуется актуализация общего аудита интегратором. / commit cf488af90f0e7beca13fe3c02599cd4854f3668e |
| H03-02 — S51, S83 и температура ATF | На проверке | Codex — привязка ATF H03 \[codex-01a1f9a2-d0ae-78d3-86f1-21b27426fd3f\] | codex/h03-02-atf-01a1f9a2 | 2026-11-20T16:18:28+00:00 | Добавлен условный поставщик TML0: PRS1=9, Clock Bus 1 и внешнее подтверждение физического 1 МГц. M32R: 11 пар и 3 отрицательных проверки PASS; стек 92/120/72 байта. Физические 1 МГц, размещение и IRQ остаются. / commit a376f561dacb33793b7bb65e57a2ea18fdcea08d |
| H03-03 — Единое расписание и запуск приложения H03 | Выполняется | Codex — foreground H03 \[codex-01a1f99f-5cb5-70e0-afd0-60e6b41a5d51\] | codex/h03-03-foreground-01a1f99f | 2026-11-20T17:00:11+00:00 | Повторяю допуск RAM, отключение выходов и проверку наложения на текущем ELF; сверяю протокол CANHacker. / commit 42a4ffecdb9f99004aa0c5b4d9e889fc90658738 |
| H03-04 — Память, стек и сервисные пути | На проверке | Codex — сервисные границы RAM H03 \[codex-32e6ac79-d63f-49c4-9d44-dd51c88bf0d3\] | codex/h03-service-spans-32e6ac79 | 2026-11-20T16:27:39+00:00 | Передаю интегратору. 35 сценариев допуска, все 2380 байт актуальных кандидатов покрыты разрешёнными интервалами; процедуры записи не запускались. STORAGE, M32R, NATIVE и Python PASS. Отчёт h03-service-ram-spans.md. Изоляция прямых/отложенных сервисных записей, запуск и владение RAM открыты. / commit e4ac4b09967f7edf86cf2c1911218ba34e260b24 |
| H03-05 — SLT, силовые выходы и реакция на отказ | На проверке | Codex — штатное отключение SLT \[codex-01a1f9a2-d0ae-78d3-86f1-21b27426fd3f\] | codex/h03-05-p0745-01a1f9a2 | 2026-11-20T16:51:27+00:00 | ELF-чек подтверждает все 128 страниц и через штатную внутреннюю ветвь активации 003364, с двумя отрицательными граничными адресами. ELF 020000/07C118 отклонён. Проверка внешнего сеанса и аппаратного наложения открыта. / commit 5813eaf480e4814fc5e78ed19d65b171e5f39a86 |
| IO-01 — Два дополнительных реле | Отложена владельцем | — | — | — | — |
| VSS-01 — Точный расчёт VSS и скорость по CAN | На проверке | Codex VSS-01 \[codex-dtc04-mwp5rm2ofhaxjfi9dss\] | codex/vss01-exact-arithmetic-mwp5rm2ofhaxjfi9dss | 2026-11-20T16:22:43+00:00 | Точная VSS арифметика устраняет промежуточное переполнение. 25 000 сравнений, PC 33 шага/65 тестов, M32R 17 компонентов, Bosch C7FF/C800/FFFF PASS по ожидаемому поведению. Параметры VSS-02 и стенд открыты. Отчёт verification/project-audit/vss01-exact-arithmetic.md. / commit d05896bcac7b731f8d3f85b9aaebd3394e32473c |
| VSS-02 — Кинематика и параметры реальной скорости | На проверке | Codex VSS-02 \[codex-dtc04-mwp5rm2ofhaxjfi9dss\] | codex/vss02-measurement-check-mwp5rm2ofhaxjfi9dss | 2026-11-20T16:37:13+00:00 | Сверка TML0 по независимому времени и допуску ppm, перенос, неправильная частота и остановка проверены. PC 35 шагов/82 теста, M32R 17 компонентов PASS. Реальная частота TML0 и стенд открыты, отчёт verification/project-audit/vss02-measurement-check.md. / commit 0ce144d22b18682e3384b05ec602224f8ec6d159 |
| PANEL-01 — Импульсы Bosch на приборную панель | Отложена владельцем | — | — | — | — |
| MODE-01 — Логика шести положений и кнопок | Работа завершена | Codex MODE-01 \[codex-4dcfb03f-87a2-4fbd-bf33-08a54073c7e4\] | codex/mode01-1120-c7e4 | 2026-11-20T16:31:25+00:00 | Reviewed shift-button conflict fix integrated in b2ca79d with PC/M32R evidence in integration-2. Released this reservation; hardware input and hydraulic execution remain open. / commit ed33ea93653f7bcbc2c6f13736fe1424335085e6 |
| MODE-02 — Подключение селектора, Tiptronic и Overdrive | На проверке | Codex MODE-02 — публикация ADC H03 \[01a1f9c7-675a-78c3-be98-5bd65e44995c\] | codex/mode02-h03-selector-01a1f9c7 | 2026-11-20T16:37:36+00:00 | Передаю интегратору привязку публикации AN2 к штатной записи H03: 4 пары и 3 отрицательные проверки M32R, ПК 35 шагов/71 тест, M32R link и 17 компонентов PASS. Отчёт verification/project-audit/mode02-h03-selector-adc.md. При приёмке внести 3 новых файла в общий аудит и выполнить complete после публикации main. Штатный callback, часы/стек, кнопки и стенд остаются открыты. / commit f92fde84f590460d713dee020ee5ddc6ccd089e4 |
| MODE-03 — Окончательная политика режимов | На проверке | Codex MODE-03 — матрица режимов \[codex-fea1b366-66b6-4667-8206-915153ca1033\] | codex/mode-03-policy-fea1b366 | 2026-11-20T16:27:03+00:00 | Штатная матрица ПК: 128 конфигураций запуска и 501 760 сценариев заявок PASS. Все 35 шагов ПК прошли; донорский тест S03 повторён отдельно с проверенным входом. Интегратору: учесть новые файлы и отчёт verification/project-audit/mode03-policy-matrix.md в аудите. Политика выпуска и подключение к циклу H03 открыты. / commit dd4fdbc2862093359df9329d7e6e9ab211d13940 |
| SRC-01 — Реестр происхождения и контроль исходников | На проверке | Codex SRC-01 \[codex-dtc04-mwp5rm2ofhaxjfi9dss\] | codex/src01-donor-pins-mwp5rm2ofhaxjfi9dss | 2026-11-20T16:43:47+00:00 | Проверка pinned Git объектов R1–R4 добавлена. SOURCES: ТЗ, S01–S04, H03 и четыре ревизии PASS; два теста, совместимая команда R1 и отказ для неверного клона проверены. Отчёт verification/project-audit/src01-donor-pins.md; снимок для интегратора. / commit 72f71983154edb4dcc7f0b3dc931bebfdb0d9b6d |
| AUD-01 — Программный аудит истории E4M3 | На проверке | Codex AUD-01 \[codex-dtc04-mwp5rm2ofhaxjfi9dss\] | codex/aud01-pinned-replay-mwp5rm2ofhaxjfi9dss | 2026-11-20T16:47:07+00:00 | Трасса и инструменты из одного R4. Два повтора без checkout совпали с сохранёнными отчётами; 3256 CRC и 26 команд в каждом. Ordinary BOSCH и SOURCES PASS. Отчёт verification/project-audit/aud01-pinned-replay.md; стенд ECU-02 открыт. / commit 6748075bd8cda69a0b6c2b9d6e2a471a00463434 |
| DTC-01 — Прикладной сеанс и статусы Chery | Выполняется | Codex — снимок полей модели Chery в H03 \[codex-32e6ac79-d63f-49c4-9d44-dd51c88bf0d3\] | codex/dtc01-shared-engine-snapshot-32e6ac79 | 2026-11-20T17:00:49+00:00 | Делаю доступный для модели Chery снимок того же task 2 с признаком запрета по CAN. Проверю независимые поля, timeout и BusOff на ПК и M32R. |
| DTC-02 — Штатный приём BasicCAN для диагностического сеанса | Выполняется | Codex — штатный RX BasicCAN H03 \[codex-7bd19ea4-0004-4aec-90c4-f2c6e804c046\] | codex/dtc02-basiccan-7bd19ea4 | 2026-11-20T17:00:34+00:00 | Проверяю исполняемую компоновку обеих RX-точек ниже границы приложения, включая штатный обход callbacks в режиме программирования. |
| DTC-03 — Все диагностические события и соответствия Toyota/Chery | На проверке | Codex DTC-03 — монитор цепи ATF H03 \[01a1f9c7-675a-78c3-be98-5bd65e44995c\] | codex/dtc03-atf-monitor-01a1f9c7 | 2026-11-20T16:47:24+00:00 | Передаю интегратору адаптер штатного статуса ATF H03. Код встроен в перемещаемый мост, 20 сценариев и 2 отрицательные проверки M32R, ПК 35 шагов/71 тест, H03 link 17 компонентов PASS. Отчёт verification/project-audit/dtc03-h03-atf-monitor.md. Четыре файла кода внести в общий аудит при приёмке и выполнить complete после публикации main. Штатный вызов, отображение P0710 и стенд открыты. / commit d487840ba2505064c7f281305a10813cbdf3b695 |
| DTC-04 — Хранение DTC после выключения питания | На проверке | Codex — подтверждение долговечной очистки DTC \[codex-32e6ac79-d63f-49c4-9d44-dd51c88bf0d3\] | codex/dtc04-durable-clear-32e6ac79 | 2026-11-20T16:43:22+00:00 | Передаю интегратору. При настроенном backend 54 FF 00 выдаётся только после подтверждения пустого журнала. При отказе сохраняется RAM, TX не ставится. 30 прерываний и повтор PASS, PC 35 шагов/71 тест, M32R журнал и 17 компонентов PASS. Отчёт dtc04-durable-clear.md. Носитель и подключение H03 открыты. / commit acd7d12c2e65cbb521331b175365aa2ae8ffc343 |
| REL-01 — Два целевых BIN и воспроизводимый комплект | На проверке | Codex REL-01 binary identity \[codex-4dcfb03f-87a2-4fbd-bf33-08a54073c7e4\] | codex/rel01-bin-identity-1120-c7e4 | 2026-11-20T16:50:31+00:00 | Reject known OFFLINE_ONLY firmware in paired worksets by SHA-256. Two real renamed Bosch artifacts rejected; accepted evidence packaging remains. SOURCES and PC 35 steps/74 tests PASS. Evidence verification/project-audit/rel01-offline-identity.md. Target pair still open. / commit 3fda923bffc63005e8c2372b22e5197f8d4b7db1 |
| REL-02 — Приёмка новой связки на оборудовании | На проверке | Codex REL-02 — проверка записи CAN \[codex-fea1b366-66b6-4667-8206-915153ca1033\] | codex/rel-02-can-trace-fea1b366 | 2026-11-20T17:00:17+00:00 | Программная подготовка REL-02: офлайн-разбор TRC и проверка периодических ID по заданным допускам. Python 77/77; R1 25261 запись, четыре перехода, ожидаемый отказ по отсутствующим ID. Доказательства verification/project-audit/rel02-can-trace.md. Общий аудит обновляет интегратор. Для приёмки нужны измерения новой пары H03/E4M3. / commit 2ebae711ad169cf22528a0a7297d8d3b210d4e0a |

## Зарезервированные файлы

### AUD-01

Чат: Codex AUD-01. Claim ID: 69a90e88e1b54af298f0f4e5760e308f.

- targets/bosch/replay_e4m3_torque.py
- verification/project-audit/aud01-pinned-replay.md

### CAN-01

Чат: Codex CAN-01 FullCAN coherence. Claim ID: f0173bc6291a4dd2b8fc72ad0de8fffc.

- targets/lfj8/host_check.c
- targets/lfj8/lfj8_donor_io.c
- verification/project-audit/can01-rx-coherence.md

### CAN-02

Чат: Codex CAN-02 telemetry submission. Claim ID: 90cda8d0e88e47969f50d8225f329437.

- targets/lfj8/lfj8_chery_tx.c
- targets/lfj8/lfj8_chery_tx.h
- targets/lfj8/lfj8_h03_can13.c
- targets/lfj8/test_lfj8_h03_can13.c
- verification/project-audit/can02-telemetry-submit.md

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

### DTC-01

Чат: Codex — снимок полей модели Chery в H03. Claim ID: 57db4a43b5754a71a19f9ab77e4c69f4.

- targets/lfj8/lfj8_h03_engine_feed.c
- targets/lfj8/lfj8_h03_engine_feed.h
- targets/lfj8/test_lfj8_h03_engine_feed.c
- verification/project-audit/dtc01-shared-engine-snapshot.md

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
- verification/project-audit/dtc02-h03-rx-binding.md
- verification/project-audit/dtc02-native-paired-rx.md
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

- docs/lfj8-9e1c-minimum-bench.md
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

### REL-01

Чат: Codex REL-01 binary identity. Claim ID: 76adb69439704129b7ae37eeace39df2.

- tests/test_package_workset.py
- tools/package_workset.py
- verification/project-audit/rel01-offline-identity.md

### REL-02

Чат: Codex REL-02 — проверка записи CAN. Claim ID: 9df078bb4f93459f8e1b8d34220dd825.

- tests/test_bench_can_trace.py
- tools/check_bench_can_trace.py
- verification/project-audit/rel02-can-trace.md

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

### TOY-02

Чат: Codex TOY-02 — допуск нагрузки в цикл. Claim ID: 1377d30e649940088e8dccd1a6fae0cf.

- targets/lfj8/lfj8_h03_cycle.c
- targets/lfj8/lfj8_h03_cycle.h
- targets/lfj8/test_lfj8_h03_cycle_load.c
- tools/build_pc_checks.py
- verification/project-audit/toy02-cycle-load-gate.md

### TOY-03

Чат: Codex TOY-03 — квалификация независимых входов. Claim ID: 8ab2489d68c04ca68447e7036ec190df.

- targets/lfj8/lfj8_range_control.c
- targets/lfj8/lfj8_range_control.h
- tests/u340_integration_host.c
- verification/project-audit/toy03-range-freshness.md

### TOY-04

Чат: Codex — переключения Toyota под нагрузкой. Claim ID: 5e4502867edb4625887df3f56fafb8b0.

- targets/lfj8/test_lfj8_h03_cycle.c
- verification/project-audit/toy04-loaded-gears.md

### TOY-05

Чат: Codex — восстановление адаптаций Toyota. Claim ID: 5e8a320b9b764646ac4a68af00a061dd.

- controller/include/rbm_u340e_runtime.h
- controller/src/rbm_u340e_runtime.c
- controller/tests/test_controller.c
- verification/project-audit/toy05-recovery-policy.md

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
| 2026-11-20T17:00:49+00:00 | DTC-01 | claim | codex-32e6ac79-d63f-49c4-9d44-dd51c88bf0d3 |
| 2026-11-20T17:00:34+00:00 | DTC-02 | heartbeat | codex-7bd19ea4-0004-4aec-90c4-f2c6e804c046 |
| 2026-11-20T17:00:17+00:00 | REL-02 | review | codex-fea1b366-66b6-4667-8206-915153ca1033 |
| 2026-11-20T17:00:11+00:00 | H03-03 | resume | codex-01a1f99f-5cb5-70e0-afd0-60e6b41a5d51 |
| 2026-11-20T16:59:29+00:00 | REL-02 | heartbeat | codex-fea1b366-66b6-4667-8206-915153ca1033 |
| 2026-11-20T16:59:25+00:00 | CAN-02 | claim | codex-4dcfb03f-87a2-4fbd-bf33-08a54073c7e4 |
| 2026-11-20T16:58:23+00:00 | DTC-02 | review | codex-7bd19ea4-0004-4aec-90c4-f2c6e804c046 |
| 2026-11-20T16:57:40+00:00 | TOY-05 | heartbeat | codex-32e6ac79-d63f-49c4-9d44-dd51c88bf0d3 |
| 2026-11-20T16:57:10+00:00 | TOY-05 | review | codex-32e6ac79-d63f-49c4-9d44-dd51c88bf0d3 |
| 2026-11-20T16:57:02+00:00 | CAN-01 | review | codex-4dcfb03f-87a2-4fbd-bf33-08a54073c7e4 |
| 2026-11-20T16:56:57+00:00 | REL-02 | heartbeat | codex-fea1b366-66b6-4667-8206-915153ca1033 |
| 2026-11-20T16:56:43+00:00 | H03-03 | review | codex-01a1f99f-5cb5-70e0-afd0-60e6b41a5d51 |
| 2026-11-20T16:56:25+00:00 | TOY-03 | review | 01a1f9c7-675a-78c3-be98-5bd65e44995c |
| 2026-11-20T16:55:09+00:00 | DTC-02 | heartbeat | codex-7bd19ea4-0004-4aec-90c4-f2c6e804c046 |
| 2026-11-20T16:54:53+00:00 | TOY-05 | heartbeat | codex-32e6ac79-d63f-49c4-9d44-dd51c88bf0d3 |
| 2026-11-20T16:54:37+00:00 | REL-02 | claim | codex-fea1b366-66b6-4667-8206-915153ca1033 |
| 2026-11-20T16:54:19+00:00 | TOY-03 | heartbeat | 01a1f9c7-675a-78c3-be98-5bd65e44995c |
| 2026-11-20T16:53:57+00:00 | CAN-01 | heartbeat | codex-4dcfb03f-87a2-4fbd-bf33-08a54073c7e4 |
| 2026-11-20T16:53:04+00:00 | TOY-05 | claim | codex-32e6ac79-d63f-49c4-9d44-dd51c88bf0d3 |
| 2026-11-20T16:52:48+00:00 | CAN-01 | claim | codex-4dcfb03f-87a2-4fbd-bf33-08a54073c7e4 |
| 2026-11-20T16:52:23+00:00 | TOY-02 | review | codex-fea1b366-66b6-4667-8206-915153ca1033 |
| 2026-11-20T16:51:27+00:00 | H03-05 | review | codex-01a1f9a2-d0ae-78d3-86f1-21b27426fd3f |
| 2026-11-20T16:51:21+00:00 | H03-03 | resume | codex-01a1f99f-5cb5-70e0-afd0-60e6b41a5d51 |
| 2026-11-20T16:51:17+00:00 | TOY-03 | claim | 01a1f9c7-675a-78c3-be98-5bd65e44995c |
| 2026-11-20T16:51:10+00:00 | DTC-02 | resume | codex-7bd19ea4-0004-4aec-90c4-f2c6e804c046 |
| 2026-11-20T16:50:41+00:00 | DTC-02 | resume | codex-7bd19ea4-0004-4aec-90c4-f2c6e804c046 |
| 2026-11-20T16:50:31+00:00 | REL-01 | review | codex-4dcfb03f-87a2-4fbd-bf33-08a54073c7e4 |
| 2026-11-20T16:50:12+00:00 | TOY-04 | review | codex-32e6ac79-d63f-49c4-9d44-dd51c88bf0d3 |
| 2026-11-20T16:49:33+00:00 | H03-05 | resume | codex-01a1f9a2-d0ae-78d3-86f1-21b27426fd3f |
| 2026-11-20T16:49:11+00:00 | TOY-02 | heartbeat | codex-fea1b366-66b6-4667-8206-915153ca1033 |
