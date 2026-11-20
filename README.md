# Кто сейчас работает над проектом

Обновлено UTC: **2026-11-20T17:46:57+00:00**. Изменение № **304**.

Это общий учёт исполнителей. Он не меняет готовность функции по ТЗ и не подтверждает выпуск BIN.
Команды занятия и обновления задачи — в tools/task_coordination.py основной ветки.
Задача и пересекающиеся файлы удерживаются в состояниях «Выполняется», «Ожидает» и «На проверке».
Давняя отметка не освобождается автоматически. Возобновившийся чат обязан проверить свой claim_id.

Каталог задач взят из main 48e51c80bac085fe67f60e1b399328879916dd28.

| Задача | Ход работы | Чат | Ветка | Обновление UTC | Что делает / результат |
| --- | --- | --- | --- | --- | --- |
| ORG-01 — Основа проекта и локальная работа | Выполняется | Основной чат — общая сборка 31 результата \[codex-integration-01a1f76d-20261120\] | codex/integration-01a1f76d-20261120 | 2026-11-20T17:36:11+00:00 | 31 порция объединена; общие проверки и аудит готовы. Публикую интеграцию, отдельные аппаратные и компоновочные остатки не закрываю. |
| TOY-01 — Перенос ядра и единое состояние Toyota | Работа завершена | Codex TOY-01 — карта переносов GP \[codex-fea1b366-66b6-4667-8206-915153ca1033\] | codex/toy-01-gp-transfer-fea1b366 | 2026-11-20T17:46:57+00:00 | 袩芯褉褑懈褟 锌褉懈薪褟褌邪 胁 main 320b72e 锌芯褋谢械 芯斜褖械泄 锌褉芯胁械褉泻懈. 袚芯褌芯胁薪芯褋褌褜 孝袟 薪械 蟹邪泻褉褘褌邪 邪胁褌芯屑邪褌懈褔械褋泻懈; 芯褋褌邪褌泻懈 懈 薪芯胁褘械 蟹邪写邪薪懈褟: docs/integration-next-tasks.md. / commit 8fdce1692a27f0bdf5dcbe0c03d962ab4e87ed39 |
| TOY-02 — Подтверждённая нагрузка двигателя для Toyota | Работа завершена | Codex TOY-02 — допуск нагрузки в цикл \[codex-fea1b366-66b6-4667-8206-915153ca1033\] | codex/toy-02-cycle-load-fea1b366 | 2026-11-20T17:40:25+00:00 | Порция принята в main 320b72e после общей проверки. Готовность ТЗ не закрыта автоматически; остатки и новые задания: docs/integration-next-tasks.md. / commit 3acdebe7db08758da32805ec04bd77ff9e3ba329 |
| TOY-03 — Независимые разрешающие сигналы диапазона | Работа завершена | Codex TOY-03 — квалификация независимых входов \[01a1f9c7-675a-78c3-be98-5bd65e44995c\] | codex/toy03-range-freshness-01a1f9c7 | 2026-11-20T17:37:42+00:00 | Порция принята в main 320b72e после общей проверки. Готовность ТЗ не закрыта автоматически; остатки и новые задания: docs/integration-next-tasks.md. / commit e7264c651d3fafe77e4bbff78e5a8fd8aa4e25ee |
| TOY-04 — Полная последовательность переключений | Работа завершена | Codex — переключения Toyota под нагрузкой \[codex-32e6ac79-d63f-49c4-9d44-dd51c88bf0d3\] | codex/toy04-loaded-map-32e6ac79 | 2026-11-20T17:43:29+00:00 | 袩芯褉褑懈褟 锌褉懈薪褟褌邪 胁 main 320b72e 锌芯褋谢械 芯斜褖械泄 锌褉芯胁械褉泻懈. 袚芯褌芯胁薪芯褋褌褜 孝袟 薪械 蟹邪泻褉褘褌邪 邪胁褌芯屑邪褌懈褔械褋泻懈; 芯褋褌邪褌泻懈 懈 薪芯胁褘械 蟹邪写邪薪懈褟: docs/integration-next-tasks.md. / commit 08b06eb14f7ccb6f46b3589f7f0131e143d529d8 |
| TOY-05 — Обучение и сохранение адаптаций | Работа завершена | Codex — восстановление адаптаций Toyota \[codex-32e6ac79-d63f-49c4-9d44-dd51c88bf0d3\] | codex/toy05-safe-restore-32e6ac79 | 2026-11-20T17:42:29+00:00 | 袩芯褉褑懈褟 锌褉懈薪褟褌邪 胁 main 320b72e 锌芯褋谢械 芯斜褖械泄 锌褉芯胁械褉泻懈. 袚芯褌芯胁薪芯褋褌褜 孝袟 薪械 蟹邪泻褉褘褌邪 邪胁褌芯屑邪褌懈褔械褋泻懈; 芯褋褌邪褌泻懈 懈 薪芯胁褘械 蟹邪写邪薪懈褟: docs/integration-next-tasks.md. / commit 8d6a6f1f62d70c827531f672c98d309e708df595 |
| TOY-06 — Блокировка гидротрансформатора SLU | Работа завершена | Codex TOY-06 — давление SLU \[codex-fea1b366-66b6-4667-8206-915153ca1033\] | codex/toy-06-slu-pressure-fea1b366 | 2026-11-20T17:44:14+00:00 | 袩芯褉褑懈褟 锌褉懈薪褟褌邪 胁 main 320b72e 锌芯褋谢械 芯斜褖械泄 锌褉芯胁械褉泻懈. 袚芯褌芯胁薪芯褋褌褜 孝袟 薪械 蟹邪泻褉褘褌邪 邪胁褌芯屑邪褌懈褔械褋泻懈; 芯褋褌邪褌泻懈 懈 薪芯胁褘械 蟹邪写邪薪懈褟: docs/integration-next-tasks.md. / commit ff3f49cf2fe324d9ee4fe253cd621f496af7459f |
| CAN-01 — Форматы CAN и квалификация RPM/ОЖ | Работа завершена | Codex CAN-01 FullCAN coherence \[codex-4dcfb03f-87a2-4fbd-bf33-08a54073c7e4\] | codex/can01-rx-coherence-1120-c7e4 | 2026-11-20T17:40:45+00:00 | Порция принята в main 320b72e после общей проверки. Готовность ТЗ не закрыта автоматически; остатки и новые задания: docs/integration-next-tasks.md. / commit 6820992a15300275c3dd9c98398151e661a42925 |
| CAN-02 — Общий диспетчер CAN13 | Работа завершена | Codex CAN-02 telemetry submission \[codex-4dcfb03f-87a2-4fbd-bf33-08a54073c7e4\] | codex/can02-telemetry-submit-1120-c7e4 | 2026-11-20T17:43:49+00:00 | 袩芯褉褑懈褟 锌褉懈薪褟褌邪 胁 main 320b72e 锌芯褋谢械 芯斜褖械泄 锌褉芯胁械褉泻懈. 袚芯褌芯胁薪芯褋褌褜 孝袟 薪械 蟹邪泻褉褘褌邪 邪胁褌芯屑邪褌懈褔械褋泻懈; 芯褋褌邪褌泻懈 懈 薪芯胁褘械 蟹邪写邪薪懈褟: docs/integration-next-tasks.md. / commit a45c2f67a80a5f7e0d939816cfb12551fd6edd96 |
| CAN-03 — Штатный запуск, IRQ и восстановление CAN0 | Работа завершена | Codex CAN-03 reset generation \[codex-4dcfb03f-87a2-4fbd-bf33-08a54073c7e4\] | codex/can03-epoch-1120-c7e4 | 2026-11-20T17:37:21+00:00 | Порция принята в main 320b72e после общей проверки. Готовность ТЗ не закрыта автоматически; остатки и новые задания: docs/integration-next-tasks.md. / commit 6fc5a51975cd6bbbdf5bc4985d5d61b811435b6b |
| CAN-04 — Запрос снижения момента по RB | Работа завершена | Codex CAN-04 TX loss \[codex-4dcfb03f-87a2-4fbd-bf33-08a54073c7e4\] | codex/can04-tx-loss-1120-c7e4 | 2026-11-20T17:42:49+00:00 | 袩芯褉褑懈褟 锌褉懈薪褟褌邪 胁 main 320b72e 锌芯褋谢械 芯斜褖械泄 锌褉芯胁械褉泻懈. 袚芯褌芯胁薪芯褋褌褜 孝袟 薪械 蟹邪泻褉褘褌邪 邪胁褌芯屑邪褌懈褔械褋泻懈; 芯褋褌邪褌泻懈 懈 薪芯胁褘械 蟹邪写邪薪懈褟: docs/integration-next-tasks.md. / commit e02095c6b8d294dacd71db21ea36f970019d0790 |
| CAN-05 — Полнота штатного обмена Chery | Работа завершена | Codex CAN-05 RX age \[codex-4dcfb03f-87a2-4fbd-bf33-08a54073c7e4\] | codex/can05-rx-age-1120-c7e4 | 2026-11-20T17:39:43+00:00 | Порция принята в main 320b72e после общей проверки. Готовность ТЗ не закрыта автоматически; остатки и новые задания: docs/integration-next-tasks.md. / commit 82947a42cfb33ef5350af1ce98e39055ba6a1508 |
| ECU-01 — Проверочная сборка Bosch E4M3 | Работа завершена | Codex ECU-01 \[codex-4dcfb03f-87a2-4fbd-bf33-08a54073c7e4\] | codex/ecu01-1120-c7e4 | 2026-11-20T17:46:01+00:00 | 袩芯褉褑懈褟 锌褉懈薪褟褌邪 胁 main 320b72e 锌芯褋谢械 芯斜褖械泄 锌褉芯胁械褉泻懈. 袚芯褌芯胁薪芯褋褌褜 孝袟 薪械 蟹邪泻褉褘褌邪 邪胁褌芯屑邪褌懈褔械褋泻懈; 芯褋褌邪褌泻懈 懈 薪芯胁褘械 蟹邪写邪薪懈褟: docs/integration-next-tasks.md. / commit 84380128b8db2e0a6b24b297dd40aa020598e3ce |
| ECU-02 — Калибровка момента и работа двигателя | На проверке | Codex — обороты и отпускание момента Bosch \[codex-32e6ac79-d63f-49c4-9d44-dd51c88bf0d3\] | codex/ecu02-torque-rpm-32e6ac79 | 2026-11-20T16:35:57+00:00 | Передаю интегратору. Точный обычный компактный образ E4M3 OFFLINE_ONLY: 4 границы RPM, 6 отзывов через air/fast/load, нулевой статус и защита старого токена PASS. Повтор 26 команд и сквозной диалог H03 с потерей статуса PASS. Отчёт ecu02-torque-rpm-guard.md. Аппаратный пуск и калибровки открыты. / commit 06eacf1ff4f42e423886b4b25b849ead054ac924 |
| H03-01 — Выбранная основа 9E1C и карта подключения | На проверке | Codex H03-01 \[codex-dtc04-mwp5rm2ofhaxjfi9dss\] | codex/h03-01-base-guard-mwp5rm2ofhaxjfi9dss | 2026-11-20T16:40:16+00:00 | Строгая сверка H03 с реестром добавлена. Подлинный H03 PASS, изменённая копия с тем же ID отвергнута. Два теста и SOURCES PASS. Отчёт verification/project-audit/h03-01-base-guard.md. Требуется актуализация общего аудита интегратором. / commit cf488af90f0e7beca13fe3c02599cd4854f3668e |
| H03-02 — S51, S83 и температура ATF | Работа завершена | Codex — привязка ATF H03 \[codex-01a1f9a2-d0ae-78d3-86f1-21b27426fd3f\] | codex/h03-02-atf-01a1f9a2 | 2026-11-20T17:39:23+00:00 | Порция принята в main 320b72e после общей проверки. Готовность ТЗ не закрыта автоматически; остатки и новые задания: docs/integration-next-tasks.md. / commit f8535218156ba32282a6e299e256a77ef0ae752d |
| H03-03 — Единое расписание и запуск приложения H03 | Работа завершена | Codex — foreground H03 \[codex-01a1f99f-5cb5-70e0-afd0-60e6b41a5d51\] | codex/h03-03-foreground-01a1f99f | 2026-11-20T17:38:22+00:00 | Порция принята в main 320b72e после общей проверки. Готовность ТЗ не закрыта автоматически; остатки и новые задания: docs/integration-next-tasks.md. / commit abaa51c3e09d017366e05906cafd1fe3de32515c |
| H03-04 — Память, стек и сервисные пути | Работа завершена | Codex — сервисные границы RAM H03 \[codex-32e6ac79-d63f-49c4-9d44-dd51c88bf0d3\] | codex/h03-service-spans-32e6ac79 | 2026-11-20T17:38:42+00:00 | Порция принята в main 320b72e после общей проверки. Готовность ТЗ не закрыта автоматически; остатки и новые задания: docs/integration-next-tasks.md. / commit e4ac4b09967f7edf86cf2c1911218ba34e260b24 |
| H03-05 — SLT, силовые выходы и реакция на отказ | Работа завершена | Codex — штатное отключение SLT \[codex-01a1f9a2-d0ae-78d3-86f1-21b27426fd3f\] | codex/h03-05-p0745-01a1f9a2 | 2026-11-20T17:45:20+00:00 | 袩芯褉褑懈褟 锌褉懈薪褟褌邪 胁 main 320b72e 锌芯褋谢械 芯斜褖械泄 锌褉芯胁械褉泻懈. 袚芯褌芯胁薪芯褋褌褜 孝袟 薪械 蟹邪泻褉褘褌邪 邪胁褌芯屑邪褌懈褔械褋泻懈; 芯褋褌邪褌泻懈 懈 薪芯胁褘械 蟹邪写邪薪懈褟: docs/integration-next-tasks.md. / commit 5813eaf480e4814fc5e78ed19d65b171e5f39a86 |
| IO-01 — Два дополнительных реле | Отложена владельцем | — | — | — | — |
| VSS-01 — Точный расчёт VSS и скорость по CAN | Работа завершена | Codex VSS-01 \[codex-dtc04-mwp5rm2ofhaxjfi9dss\] | codex/vss01-exact-arithmetic-mwp5rm2ofhaxjfi9dss | 2026-11-20T17:44:55+00:00 | 袩芯褉褑懈褟 锌褉懈薪褟褌邪 胁 main 320b72e 锌芯褋谢械 芯斜褖械泄 锌褉芯胁械褉泻懈. 袚芯褌芯胁薪芯褋褌褜 孝袟 薪械 蟹邪泻褉褘褌邪 邪胁褌芯屑邪褌懈褔械褋泻懈; 芯褋褌邪褌泻懈 懈 薪芯胁褘械 蟹邪写邪薪懈褟: docs/integration-next-tasks.md. / commit 01293a5be56c519cb2b01ad54f82637c0be823f6 |
| VSS-02 — Кинематика и параметры реальной скорости | Работа завершена | Codex VSS-02 \[codex-dtc04-mwp5rm2ofhaxjfi9dss\] | codex/vss02-measurement-check-mwp5rm2ofhaxjfi9dss | 2026-11-20T17:46:37+00:00 | 袩芯褉褑懈褟 锌褉懈薪褟褌邪 胁 main 320b72e 锌芯褋谢械 芯斜褖械泄 锌褉芯胁械褉泻懈. 袚芯褌芯胁薪芯褋褌褜 孝袟 薪械 蟹邪泻褉褘褌邪 邪胁褌芯屑邪褌懈褔械褋泻懈; 芯褋褌邪褌泻懈 懈 薪芯胁褘械 蟹邪写邪薪懈褟: docs/integration-next-tasks.md. / commit 0ce144d22b18682e3384b05ec602224f8ec6d159 |
| PANEL-01 — Импульсы Bosch на приборную панель | Отложена владельцем | — | — | — | — |
| MODE-01 — Логика шести положений и кнопок | Работа завершена | Codex MODE-01 — восстановление кнопок после отказа входа \[01a1f9c7-675a-78c3-be98-5bd65e44995c\] | codex/mode01-button-rebaseline-01a1f9c7 | 2026-11-20T17:43:09+00:00 | 袩芯褉褑懈褟 锌褉懈薪褟褌邪 胁 main 320b72e 锌芯褋谢械 芯斜褖械泄 锌褉芯胁械褉泻懈. 袚芯褌芯胁薪芯褋褌褜 孝袟 薪械 蟹邪泻褉褘褌邪 邪胁褌芯屑邪褌懈褔械褋泻懈; 芯褋褌邪褌泻懈 懈 薪芯胁褘械 蟹邪写邪薪懈褟: docs/integration-next-tasks.md. / commit 6bbc342ce3f6a2a60a9b58f23044e7a6a02fbd31 |
| MODE-02 — Подключение селектора, Tiptronic и Overdrive | Работа завершена | Codex MODE-02 — публикация ADC H03 \[01a1f9c7-675a-78c3-be98-5bd65e44995c\] | codex/mode02-h03-selector-01a1f9c7 | 2026-11-20T17:42:09+00:00 | 袩芯褉褑懈褟 锌褉懈薪褟褌邪 胁 main 320b72e 锌芯褋谢械 芯斜褖械泄 锌褉芯胁械褉泻懈. 袚芯褌芯胁薪芯褋褌褜 孝袟 薪械 蟹邪泻褉褘褌邪 邪胁褌芯屑邪褌懈褔械褋泻懈; 芯褋褌邪褌泻懈 懈 薪芯胁褘械 蟹邪写邪薪懈褟: docs/integration-next-tasks.md. / commit f92fde84f590460d713dee020ee5ddc6ccd089e4 |
| MODE-03 — Окончательная политика режимов | Работа завершена | Codex MODE-03 — матрица режимов \[codex-fea1b366-66b6-4667-8206-915153ca1033\] | codex/mode-03-policy-fea1b366 | 2026-11-20T17:45:40+00:00 | 袩芯褉褑懈褟 锌褉懈薪褟褌邪 胁 main 320b72e 锌芯褋谢械 芯斜褖械泄 锌褉芯胁械褉泻懈. 袚芯褌芯胁薪芯褋褌褜 孝袟 薪械 蟹邪泻褉褘褌邪 邪胁褌芯屑邪褌懈褔械褋泻懈; 芯褋褌邪褌泻懈 懈 薪芯胁褘械 蟹邪写邪薪懈褟: docs/integration-next-tasks.md. / commit dd4fdbc2862093359df9329d7e6e9ab211d13940 |
| SRC-01 — Реестр происхождения и контроль исходников | На проверке | Codex SRC-01 \[codex-dtc04-mwp5rm2ofhaxjfi9dss\] | codex/src01-donor-pins-mwp5rm2ofhaxjfi9dss | 2026-11-20T16:43:47+00:00 | Проверка pinned Git объектов R1–R4 добавлена. SOURCES: ТЗ, S01–S04, H03 и четыре ревизии PASS; два теста, совместимая команда R1 и отказ для неверного клона проверены. Отчёт verification/project-audit/src01-donor-pins.md; снимок для интегратора. / commit 72f71983154edb4dcc7f0b3dc931bebfdb0d9b6d |
| AUD-01 — Программный аудит истории E4M3 | На проверке | Codex AUD-01 \[codex-dtc04-mwp5rm2ofhaxjfi9dss\] | codex/aud01-pinned-replay-mwp5rm2ofhaxjfi9dss | 2026-11-20T16:47:07+00:00 | Трасса и инструменты из одного R4. Два повтора без checkout совпали с сохранёнными отчётами; 3256 CRC и 26 команд в каждом. Ordinary BOSCH и SOURCES PASS. Отчёт verification/project-audit/aud01-pinned-replay.md; стенд ECU-02 открыт. / commit 6748075bd8cda69a0b6c2b9d6e2a471a00463434 |
| DTC-01 — Прикладной сеанс и статусы Chery | Работа завершена | Codex — снимок полей модели Chery в H03 \[codex-32e6ac79-d63f-49c4-9d44-dd51c88bf0d3\] | codex/dtc01-shared-engine-snapshot-32e6ac79 | 2026-11-20T17:44:35+00:00 | 袩芯褉褑懈褟 锌褉懈薪褟褌邪 胁 main 320b72e 锌芯褋谢械 芯斜褖械泄 锌褉芯胁械褉泻懈. 袚芯褌芯胁薪芯褋褌褜 孝袟 薪械 蟹邪泻褉褘褌邪 邪胁褌芯屑邪褌懈褔械褋泻懈; 芯褋褌邪褌泻懈 懈 薪芯胁褘械 蟹邪写邪薪懈褟: docs/integration-next-tasks.md. / commit 6cdb95e861728cffbc7635d0d9f366a1d0fd51a4 |
| DTC-02 — Штатный приём BasicCAN для диагностического сеанса | Работа завершена | Codex — штатный RX BasicCAN H03 \[codex-7bd19ea4-0004-4aec-90c4-f2c6e804c046\] | codex/dtc02-basiccan-7bd19ea4 | 2026-11-20T17:37:01+00:00 | Порция принята в main 320b72e после общей проверки. Готовность ТЗ не закрыта автоматически; остатки и новые задания: docs/integration-next-tasks.md. / commit f38da53a7796dd1c71f7fe39e206f1334c6b9071 |
| DTC-03 — Все диагностические события и соответствия Toyota/Chery | Работа завершена | Codex DTC-03 — монитор цепи ATF H03 \[01a1f9c7-675a-78c3-be98-5bd65e44995c\] | codex/dtc03-atf-monitor-01a1f9c7 | 2026-11-20T17:40:03+00:00 | Порция принята в main 320b72e после общей проверки. Готовность ТЗ не закрыта автоматически; остатки и новые задания: docs/integration-next-tasks.md. / commit d487840ba2505064c7f281305a10813cbdf3b695 |
| DTC-04 — Хранение DTC после выключения питания | Работа завершена | Codex — подтверждение долговечной очистки DTC \[codex-32e6ac79-d63f-49c4-9d44-dd51c88bf0d3\] | codex/dtc04-durable-clear-32e6ac79 | 2026-11-20T17:39:02+00:00 | Порция принята в main 320b72e после общей проверки. Готовность ТЗ не закрыта автоматически; остатки и новые задания: docs/integration-next-tasks.md. / commit acd7d12c2e65cbb521331b175365aa2ae8ffc343 |
| REL-01 — Два целевых BIN и воспроизводимый комплект | Работа завершена | Codex REL-01 binary identity \[codex-4dcfb03f-87a2-4fbd-bf33-08a54073c7e4\] | codex/rel01-bin-identity-1120-c7e4 | 2026-11-20T17:38:02+00:00 | Порция принята в main 320b72e после общей проверки. Готовность ТЗ не закрыта автоматически; остатки и новые задания: docs/integration-next-tasks.md. / commit 3fda923bffc63005e8c2372b22e5197f8d4b7db1 |
| REL-02 — Приёмка новой связки на оборудовании | На проверке | Codex REL-02 — проверка записи CAN \[codex-fea1b366-66b6-4667-8206-915153ca1033\] | codex/rel-02-can-trace-fea1b366 | 2026-11-20T17:00:17+00:00 | Программная подготовка REL-02: офлайн-разбор TRC и проверка периодических ID по заданным допускам. Python 77/77; R1 25261 запись, четыре перехода, ожидаемый отказ по отсутствующим ID. Доказательства verification/project-audit/rel02-can-trace.md. Общий аудит обновляет интегратор. Для приёмки нужны измерения новой пары H03/E4M3. / commit 2ebae711ad169cf22528a0a7297d8d3b210d4e0a |

## Зарезервированные файлы

### AUD-01

Чат: Codex AUD-01. Claim ID: 69a90e88e1b54af298f0f4e5760e308f.

- targets/bosch/replay_e4m3_torque.py
- verification/project-audit/aud01-pinned-replay.md

### ECU-02

Чат: Codex — обороты и отпускание момента Bosch. Claim ID: c8de734571c443c3b11766566ad20891.

- targets/bosch/verify_e4m3_torque_rpm.py
- verification/project-audit/ecu02-torque-rpm-guard.md

### H03-01

Чат: Codex H03-01. Claim ID: 125a9fc02e0b4315aa93ce8efbe1bda1.

- tests/test_inspect_lfj8_tcm.py
- tools/inspect_lfj8_tcm.py
- verification/project-audit/h03-01-base-guard.md

### ORG-01

Чат: Основной чат — общая сборка 31 результата. Claim ID: d5108ac7030f46e2afe22bca1a1ee468.

- README.md
- controller/build_target.py
- controller/size_port.py
- data/project-tasks.json
- docs/integration-next-tasks.md
- docs/project-map.md
- docs/working-set.md
- targets/lfj8/lfj8_h03_storage.h
- tools/check_integrated_h03.py
- verification/project-audit/2026-11-20-integration-3.json
- verification/project-audit/integration-3/

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

## Последние события

| UTC | Задача | Действие | Чат |
| --- | --- | --- | --- |
| 2026-11-20T17:46:57+00:00 | TOY-01 | complete | codex-fea1b366-66b6-4667-8206-915153ca1033 |
| 2026-11-20T17:46:37+00:00 | VSS-02 | complete | codex-dtc04-mwp5rm2ofhaxjfi9dss |
| 2026-11-20T17:46:01+00:00 | ECU-01 | complete | codex-4dcfb03f-87a2-4fbd-bf33-08a54073c7e4 |
| 2026-11-20T17:45:40+00:00 | MODE-03 | complete | codex-fea1b366-66b6-4667-8206-915153ca1033 |
| 2026-11-20T17:45:20+00:00 | H03-05 | complete | codex-01a1f9a2-d0ae-78d3-86f1-21b27426fd3f |
| 2026-11-20T17:44:55+00:00 | VSS-01 | complete | codex-dtc04-mwp5rm2ofhaxjfi9dss |
| 2026-11-20T17:44:35+00:00 | DTC-01 | complete | codex-32e6ac79-d63f-49c4-9d44-dd51c88bf0d3 |
| 2026-11-20T17:44:14+00:00 | TOY-06 | complete | codex-fea1b366-66b6-4667-8206-915153ca1033 |
| 2026-11-20T17:43:49+00:00 | CAN-02 | complete | codex-4dcfb03f-87a2-4fbd-bf33-08a54073c7e4 |
| 2026-11-20T17:43:29+00:00 | TOY-04 | complete | codex-32e6ac79-d63f-49c4-9d44-dd51c88bf0d3 |
| 2026-11-20T17:43:09+00:00 | MODE-01 | complete | 01a1f9c7-675a-78c3-be98-5bd65e44995c |
| 2026-11-20T17:42:49+00:00 | CAN-04 | complete | codex-4dcfb03f-87a2-4fbd-bf33-08a54073c7e4 |
| 2026-11-20T17:42:29+00:00 | TOY-05 | complete | codex-32e6ac79-d63f-49c4-9d44-dd51c88bf0d3 |
| 2026-11-20T17:42:09+00:00 | MODE-02 | complete | 01a1f9c7-675a-78c3-be98-5bd65e44995c |
| 2026-11-20T17:40:45+00:00 | CAN-01 | complete | codex-4dcfb03f-87a2-4fbd-bf33-08a54073c7e4 |
| 2026-11-20T17:40:25+00:00 | TOY-02 | complete | codex-fea1b366-66b6-4667-8206-915153ca1033 |
| 2026-11-20T17:40:03+00:00 | DTC-03 | complete | 01a1f9c7-675a-78c3-be98-5bd65e44995c |
| 2026-11-20T17:39:43+00:00 | CAN-05 | complete | codex-4dcfb03f-87a2-4fbd-bf33-08a54073c7e4 |
| 2026-11-20T17:39:23+00:00 | H03-02 | complete | codex-01a1f9a2-d0ae-78d3-86f1-21b27426fd3f |
| 2026-11-20T17:39:02+00:00 | DTC-04 | complete | codex-32e6ac79-d63f-49c4-9d44-dd51c88bf0d3 |
| 2026-11-20T17:38:42+00:00 | H03-04 | complete | codex-32e6ac79-d63f-49c4-9d44-dd51c88bf0d3 |
| 2026-11-20T17:38:22+00:00 | H03-03 | complete | codex-01a1f99f-5cb5-70e0-afd0-60e6b41a5d51 |
| 2026-11-20T17:38:02+00:00 | REL-01 | complete | codex-4dcfb03f-87a2-4fbd-bf33-08a54073c7e4 |
| 2026-11-20T17:37:42+00:00 | TOY-03 | complete | 01a1f9c7-675a-78c3-be98-5bd65e44995c |
| 2026-11-20T17:37:21+00:00 | CAN-03 | complete | codex-4dcfb03f-87a2-4fbd-bf33-08a54073c7e4 |
| 2026-11-20T17:37:01+00:00 | DTC-02 | complete | codex-7bd19ea4-0004-4aec-90c4-f2c6e804c046 |
| 2026-11-20T17:36:11+00:00 | ORG-01 | heartbeat | codex-integration-01a1f76d-20261120 |
| 2026-11-20T17:29:56+00:00 | ORG-01 | heartbeat | codex-integration-01a1f76d-20261120 |
| 2026-11-20T17:27:09+00:00 | ORG-01 | heartbeat | codex-integration-01a1f76d-20261120 |
| 2026-11-20T17:16:57+00:00 | ORG-01 | claim | codex-integration-01a1f76d-20261120 |
