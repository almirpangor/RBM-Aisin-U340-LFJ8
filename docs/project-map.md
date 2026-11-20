# Подзадачи и карта кода

Сгенерировано из [data/project-tasks.json](../data/project-tasks.json). Изменять реестр, затем запускать `python -B tools/project_status.py --write`.

[Главная страница](../README.md) · [Результат сверки](project-audit-2026-11-20.md) · [Доказательства по ТЗ](working-set.md)

## Границы модулей

| Каталог | Ответственность и вход | Правило изменения |
| --- | --- | --- |
| `controller/` | Переносимая логика Toyota, общий GP, режимы и планирование. [rbm_u340e_runtime.h](../controller/include/rbm_u340e_runtime.h) | Донор controller/vendor/toyota сохранять неизменным по manifest.json. Изменения переноса делать в controller/hydraulic_port.py и собственных адаптерах. |
| `targets/lfj8/` | Только привязка к H03, датчики, CAN0, таймер, память и выдача команд. [lfj8_h03_cycle.h](../targets/lfj8/lfj8_h03_cycle.h) | lfj8_h03_cycle связывает лишь восстановленные стадии. Потребители callback и физический запрет ещё требуют интеграции. |
| `targets/bosch/` | Патчирование E4M3, скорость и публикация данных двигателя. [build.py](../targets/bosch/build.py) | Образы OFFLINE_ONLY остаются проверочными. Сверять SHA-256 и 51 штатную запись целостности. |
| `diagnostics/` | Коды, статусы, сеанс и сегментация Chery. [chery_dtc_link.h](../diagnostics/chery_dtc_link.h) | Прикладной сеанс отделён от CAN0. История в RAM не равна хранению после питания. |
| `model/` | Программные модели и сквозные сценарии. [run_integrated.py](../model/run_integrated.py) | Тестовые значения нагрузки, давления и времени не переносить в калибровку блока. |
| `tests/` | Проверки переносимых моделей. [test_u340_scenario.py](../tests/test_u340_scenario.py) | Тесты C находятся рядом с соответствующим модулем или в controller/tests. |
| `targets/panel/` | Отложенный импульсный выход панели. [panel_pulse.h](../targets/panel/panel_pulse.h) | Не включать в первый выпуск до возобновления владельцем. |
| `targets/pcm-s05/` | Историческое исследование моторного PCM SuperH. [README.md](../targets/pcm-s05/integrity/README.md) | Не использовать как активную цель TCM 9E1C. Физические файлы сохранены для происхождения и старых сборок. |

Исходные пути и соглашения о вызове сохранены, чтобы действующие сборки и доказательства оставались воспроизводимыми. Логическая структура задаётся контрактами модулей и карточками ниже.

## Критические границы интеграции

- `rbm_u340e_step` формирует логический запрос режима/передачи. Его результат пока не подключён целиком к `lfj8_h03_cycle_tick`.
- `lfj8_h03_cycle_tick` выполняет восстановленные стадии на уже подготовленном GP. Часть его производителей и полного расписания ещё отсутствует.
- `lfj8_h03_takeover` вызывает переданные `qualified/arbitrate/apply/inhibit`. Наличие вызова `inhibit` в тесте не доказывает физическое отключение выхода.
- `lfj8_h03_can13` управляет очередью по предоставленному владению. Штатные IRQ и восстановление владения остаются отдельной задачей.
- `diagnostics/` обслуживает RAM и ограниченный CAN-сеанс. Реальный BasicCAN RX и сохранение после питания не входят автоматически в этот результат.

## Статусы и объём

Завершено в указанном объёме: **4** · Проверено программно: **9** · Требуется разработка: **15** · Требуются физические данные: **4** · Отложено владельцем: **2**

«Завершено» применяется к узкому объёму карточки. «Проверено программно» не закрывает реализацию на оборудовании. «Требуется разработка» включает независимые программные шаги и их внешние зависимости. Отложенные задачи не входят в первый файл.

## Быстрый список

| ID | Задача | Статус |
| --- | --- | --- |
| [ORG-01](#org-01) | Основа проекта и локальная работа | Завершено в указанном объёме |
| [TOY-01](#toy-01) | Перенос ядра и единое состояние Toyota | Проверено программно |
| [TOY-02](#toy-02) | Подтверждённая нагрузка двигателя для Toyota | Требуется разработка |
| [TOY-03](#toy-03) | Независимые разрешающие сигналы диапазона | Требуется разработка |
| [TOY-04](#toy-04) | Полная последовательность переключений | Требуется разработка |
| [TOY-05](#toy-05) | Обучение и сохранение адаптаций | Требуется разработка |
| [TOY-06](#toy-06) | Блокировка гидротрансформатора SLU | Требуется разработка |
| [CAN-01](#can-01) | Форматы CAN и квалификация RPM/ОЖ | Проверено программно |
| [CAN-02](#can-02) | Общий диспетчер CAN13 | Проверено программно |
| [CAN-03](#can-03) | Штатный запуск, IRQ и восстановление CAN0 | Требуется разработка |
| [CAN-04](#can-04) | Запрос снижения момента по RB | Проверено программно |
| [CAN-05](#can-05) | Полнота штатного обмена Chery | Требуется разработка |
| [ECU-01](#ecu-01) | Проверочная сборка Bosch E4M3 | Проверено программно |
| [ECU-02](#ecu-02) | Калибровка момента и работа двигателя | Требуются физические данные |
| [H03-01](#h03-01) | Выбранная основа 9E1C и карта подключения | Завершено в указанном объёме |
| [H03-02](#h03-02) | S51, S83 и температура ATF | Проверено программно |
| [H03-03](#h03-03) | Единое расписание и запуск приложения H03 | Требуется разработка |
| [H03-04](#h03-04) | Память, стек и сервисные пути | Требуется разработка |
| [H03-05](#h03-05) | SLT, силовые выходы и реакция на отказ | Требуются физические данные |
| [IO-01](#io-01) | Два дополнительных реле | Отложено владельцем |
| [VSS-01](#vss-01) | Точный расчёт VSS и скорость по CAN | Проверено программно |
| [VSS-02](#vss-02) | Кинематика и параметры реальной скорости | Требуются физические данные |
| [PANEL-01](#panel-01) | Импульсы Bosch на приборную панель | Отложено владельцем |
| [MODE-01](#mode-01) | Логика шести положений и кнопок | Проверено программно |
| [MODE-02](#mode-02) | Подключение селектора, Tiptronic и Overdrive | Требуется разработка |
| [MODE-03](#mode-03) | Окончательная политика режимов | Требуется разработка |
| [SRC-01](#src-01) | Реестр происхождения и контроль исходников | Завершено в указанном объёме |
| [AUD-01](#aud-01) | Программный аудит истории E4M3 | Завершено в указанном объёме |
| [DTC-01](#dtc-01) | Прикладной сеанс и статусы Chery | Проверено программно |
| [DTC-02](#dtc-02) | Штатный приём BasicCAN для диагностического сеанса | Требуется разработка |
| [DTC-03](#dtc-03) | Все диагностические события и соответствия Toyota/Chery | Требуется разработка |
| [DTC-04](#dtc-04) | Хранение DTC после выключения питания | Требуется разработка |
| [REL-01](#rel-01) | Два целевых BIN и воспроизводимый комплект | Требуется разработка |
| [REL-02](#rel-02) | Приёмка новой связки на оборудовании | Требуются физические данные |

<a id="org-01"></a>
## ORG-01 — Основа проекта и локальная работа

**Завершено в указанном объёме** · ТЗ §1

**Сделано.** Объединены ещё 13 опубликованных порций восьми чатов. Добавлены строгая адресная сборка, контроль свежести объектов и общий аудит памяти; продолжения сохраняются в прежних карточках.

**Осталось.** Окончательные BIN и оставшиеся привязки ведутся в REL-01/H03-03/H03-04.

**Критерий результата.** Файлы доступны, источник каждой сборки прослеживается.

**Код.** [tools/package_workset.py](../tools/package_workset.py) · [tools/task_coordination.py](../tools/task_coordination.py) · [tests/test_task_coordination.py](../tests/test_task_coordination.py) · [tools/check_integrated_h03.py](../tools/check_integrated_h03.py)

**Что настраивать.** Публикация в GitHub возобновлена по указанию владельца 20.11.2026. Учёт чатов отделён от готовности прошивки.

**Проверки.** [SOURCES](#check-sources) · [COORD](#check-coord) · [INTEGRATION](#check-integration) · [INTEGRATION3](#check-integration3) · [MEMORY4](#check-memory4)

**Разбор и основания.** [decisions.md](../docs/decisions.md) · [multi-chat.md](../docs/multi-chat.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md) · [lfj8-h03-memory-layout.md](../docs/lfj8-h03-memory-layout.md)

<a id="toy-01"></a>
## TOY-01 — Перенос ядра и единое состояние Toyota

**Проверено программно** · ТЗ §2

**Сделано.** Карта 292 переносов GP сокращена с 1752 до 1168 байт. M32R сохраняет общие getq/putq и границы inc/down_observer: дополнительно сэкономлено 1440 байт. Vendor неизменен, CPU-проверки и стек повторены.

**Осталось.** Довести полный рабочий цикл в TOY-04 и H03-03.

**Критерий результата.** Программный результат относится к проверенным функциям, а не ко всем режимам АКПП.

**Код.** [controller/src/rbm_u340e_runtime.c](../controller/src/rbm_u340e_runtime.c) · [controller/src/rbm_u340e_scheduler.c](../controller/src/rbm_u340e_scheduler.c) · [controller/hydraulic_port.py](../controller/hydraulic_port.py) · [controller/vendor/toyota/manifest.json](../controller/vendor/toyota/manifest.json) · [controller/size_port.py](../controller/size_port.py)

**Что настраивать.** Исходные таблицы S01 и контракт controller/include/rbm_u340e_runtime.h.

**Проверки.** [PC](#check-pc) · [M32R](#check-m32r) · [INTEGRATION3](#check-integration3)

**Разбор и основания.** [toyota-integration.md](../docs/toyota-integration.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md)

<a id="toy-02"></a>
## TOY-02 — Подтверждённая нагрузка двигателя для Toyota

**Требуется разработка** · ТЗ §2, §3, §4

**Сделано.** Квалифицированная нагрузка публикуется перед новым событием цикла; MAIN учитывает старейшую метку. Просрочка, wrap, повтор и потеря события проверены на ПК и M32R. Источники и шкалы Bosch открыты.

**Осталось.** Определить источник и шкалы GP−9046/−8288/−8330 и флаги режимов либо полные результаты арбитража. Подключить квалификацию и отказы.

**Критерий результата.** Трасса происхождения каждого операнда, сравнение с S01 и отдельные переходные режимы. Одного TPS и кадров RPM/ОЖ недостаточно.

**Код.** [controller/src/rbm_u340e_runtime.c](../controller/src/rbm_u340e_runtime.c) · [targets/bosch/tx.py](../targets/bosch/tx.py) · [targets/bosch/audit_bosch_signal_transport.py](../targets/bosch/audit_bosch_signal_transport.py) · [targets/bosch/audit_toyota_load_inputs.py](../targets/bosch/audit_toyota_load_inputs.py) · [controller/include/rbm_u340e_runtime.h](../controller/include/rbm_u340e_runtime.h) · [controller/tests/test_runtime.c](../controller/tests/test_runtime.c)

**Что настраивать.** GP−8270/−8272/−8306/−8298/−8302/−8310, −9044/−9030, −5299.1 и −5250.2. Тестовые слова не являются настройкой выпуска.

**Проверки.** [SIGNALS](#check-signals) · [M32R](#check-m32r) · [INTEGRATION](#check-integration) · [INTEGRATION3](#check-integration3)

**Разбор и основания.** [toyota-integration.md](../docs/toyota-integration.md) · [bosch-integration.md](../docs/bosch-integration.md) · [toy02-load-feed.md](../verification/project-audit/toy02-load-feed.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md)

**Следующий шаг для продолжения.** Установить источники и шкалы нагрузки Bosch, довести их до квалифицированного GP Toyota и повторить сквозной обмен.

**Кто сейчас выполняет.** Проверить [общий список исполнителей](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/tree/task-board). Перед изменениями занять этот ID и точные файлы.

<a id="toy-03"></a>
## TOY-03 — Независимые разрешающие сигналы диапазона

**Требуется разработка** · ТЗ §2, §5

**Сделано.** Пять независимых входов GP−5722/GP−5250.2 проходят проверку поколения и отдельной давности. 32 сочетания проверены на M32R. Физические производители не подключены.

**Осталось.** Установить соответствующие входы H03, условия обновления и недостоверности.

**Критерий результата.** Для каждого бита известны источник, шкала времени и реакция на отказ. Проверка P/N не проверяет сама себя.

**Код.** [targets/lfj8/lfj8_h03_cycle.h](../targets/lfj8/lfj8_h03_cycle.h) · [controller/src/rbm_u340e_runtime.c](../controller/src/rbm_u340e_runtime.c)

**Что настраивать.** Lfj8H03CycleInput.range_5722 и inhibit_5250.

**Проверки.** [M32R](#check-m32r) · [INTEGRATION](#check-integration) · [INTEGRATION3](#check-integration3)

**Разбор и основания.** [lfj8-h03-input-paths.md](../docs/lfj8-h03-input-paths.md) · [toyota-integration.md](../docs/toyota-integration.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md)

<a id="toy-04"></a>
## TOY-04 — Полная последовательность переключений

**Требуется разработка** · ТЗ §2, §8

**Сделано.** 24 точки D при двух синтетических нагрузках проверены в общем цикле: повышения, понижения, холодный запрет четвёртой, потеря события. R, ручное управление и вся гидравлика открыты.

**Осталось.** Связать оставшиеся стадии и входы. Проверить R, 2→3, 3→4, понижения, холодные/горячие режимы, ручные запросы и защитные переходы целым циклом.

**Критерий результата.** Матрица режимов с ожидаемыми результатами S01 и сквозными трассами. Отдельный тест момента не закрывает всё переключение 2→3.

**Код.** [targets/lfj8/lfj8_h03_cycle.c](../targets/lfj8/lfj8_h03_cycle.c) · [controller/src/rbm_u340e_runtime.c](../controller/src/rbm_u340e_runtime.c) · [controller/tests/test_runtime.c](../controller/tests/test_runtime.c) · [targets/lfj8/test_lfj8_h03_cycle.c](../targets/lfj8/test_lfj8_h03_cycle.c)

**Что настраивать.** Раздельные расписания Toyota FAST/SECONDARY/MAIN и H03, начальное состояние GP.

**Проверки.** [PC](#check-pc) · [M32R](#check-m32r) · [NATIVE](#check-native) · [INTEGRATION2](#check-integration2) · [INTEGRATION3](#check-integration3)

**Разбор и основания.** [lfj8-h03-control-cycle.md](../docs/lfj8-h03-control-cycle.md) · [toy04-upper-gears.md](../verification/project-audit/toy04-upper-gears.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md)

**Зависит от.** [TOY-02](#toy-02), [TOY-03](#toy-03), [H03-03](#h03-03), [MODE-02](#mode-02)

**Следующий шаг для продолжения.** Замкнуть оставшиеся стадии полного цикла, R и ручные запросы; затем подключить SLU SECONDARY и назначить одного владельца таймера в TOY-06.

**Кому удобно продолжить.** Чат переключений Toyota — 01a1f9b5-5d41-79e0-8cd2-3dadc922f1ce. Это рекомендация, не резерв.

**Кто сейчас выполняет.** Проверить [общий список исполнителей](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/tree/task-board). Перед изменениями занять этот ID и точные файлы.

<a id="toy-05"></a>
## TOY-05 — Обучение и сохранение адаптаций

**Требуется разработка** · ТЗ §2, §5

**Сделано.** Повреждённые адаптации восстанавливаются из исходного снимка вызывающего кода. M32R: 96 прерываний записи, повреждения битов и wrap поколения прошли. NVM и запуск H03 не подключены.

**Осталось.** Подтвердить исходный снимок сброса, назначить NVM, подключить восстановление к запуску H03 и сохранение адаптаций полного цикла. Проверить долговечность сброса.

**Критерий результата.** Проверены пределы коррекции, повторный пуск, повреждённая запись и сброс адаптаций.

**Код.** [controller/vendor/toyota/src/factory_learning.c](../controller/vendor/toyota/src/factory_learning.c) · [controller/vendor/toyota/src/factory_adaptation_store.c](../controller/vendor/toyota/src/factory_adaptation_store.c) · [controller/tests/test_controller.c](../controller/tests/test_controller.c)

**Что настраивать.** Контракты factory_learning.h и factory_adaptation_store.h. Область NVM ещё не назначена.

**Проверки.** [PC](#check-pc) · [M32R](#check-m32r) · [INTEGRATION2](#check-integration2) · [INTEGRATION3](#check-integration3)

**Разбор и основания.** [toyota-integration.md](../docs/toyota-integration.md) · [lfj8-h03-flash.md](../docs/lfj8-h03-flash.md) · [toy05-adaptation-store.md](../verification/project-audit/toy05-adaptation-store.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md)

**Зависит от.** [TOY-04](#toy-04), [H03-04](#h03-04)

<a id="toy-06"></a>
## TOY-06 — Блокировка гидротрансформатора SLU

**Требуется разработка** · ТЗ §2, §5

**Сделано.** SLU включён в SECONDARY, его канонический таймер продвигается FAST. Общий цикл проверен по новым адресам: пять публикаций и семь отказов.

**Осталось.** Подключить полный целевой снимок, установить физический канал SLU и измерить удержание/снятие блокировки.

**Критерий результата.** Трасса от квалифицированных входов до канала H03, проверка скольжения, удержания и снятия по отказу.

**Код.** [targets/lfj8/check_toyota_slu.py](../targets/lfj8/check_toyota_slu.py) · [targets/lfj8/lfj8_h03_cycle.c](../targets/lfj8/lfj8_h03_cycle.c) · [targets/lfj8/lfj8_h03_outputs.h](../targets/lfj8/lfj8_h03_outputs.h) · [targets/lfj8/lfj8_h03_slu.c](../targets/lfj8/lfj8_h03_slu.c) · [targets/lfj8/lfj8_h03_slu.h](../targets/lfj8/lfj8_h03_slu.h)

**Что настраивать.** Целевой адаптер SLU ещё отсутствует. Результат сравнения регистров Toyota не задаёт ток канала H03.

**Проверки.** [SLU](#check-slu) · [INTEGRATION2](#check-integration2) · [INTEGRATION3](#check-integration3) · [MEMORY4](#check-memory4)

**Разбор и основания.** [toyota-integration.md](../docs/toyota-integration.md) · [lfj8-9e1c-minimum-bench.md](../docs/lfj8-9e1c-minimum-bench.md) · [toy06-slu-command.md](../verification/project-audit/toy06-slu-command.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md) · [lfj8-h03-memory-layout.md](../docs/lfj8-h03-memory-layout.md)

**Зависит от.** [TOY-02](#toy-02), [H03-05](#h03-05)

<a id="can-01"></a>
## CAN-01 — Форматы CAN и квалификация RPM/ОЖ

**Проверено программно** · ТЗ §3

**Сделано.** Повторная проверка RR/EXTID после копирования не допускает принятия исчезнувшего кадра. ПК/M32R и сквозное сравнение с точным Bosch прошли.

**Осталось.** Подключить к штатному запуску и измеренному времени в CAN-03. Остальные поля ведутся в CAN-05.

**Критерий результата.** Результат ограничен перечисленными полями и сценариями приёма.

**Код.** [targets/lfj8/ta2005_chery_inputs.c](../targets/lfj8/ta2005_chery_inputs.c) · [targets/lfj8/ta2005_engine_qualifier.c](../targets/lfj8/ta2005_engine_qualifier.c) · [targets/lfj8/lfj8_h03_engine_feed.c](../targets/lfj8/lfj8_h03_engine_feed.c) · [targets/lfj8/lfj8_chery_tx.c](../targets/lfj8/lfj8_chery_tx.c)

**Что настраивать.** Возраст кадра, поколение CAN, период task2 и разрешение записи истории.

**Проверки.** [PC](#check-pc) · [M32R](#check-m32r) · [BOSCH](#check-bosch) · [INTEGRATION](#check-integration) · [INTEGRATION3](#check-integration3)

**Разбор и основания.** [chery-can-dtc.md](../docs/chery-can-dtc.md) · [toyota-integration.md](../docs/toyota-integration.md) · [can01-rx-epoch.md](../verification/project-audit/can01-rx-epoch.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md)

<a id="can-02"></a>
## CAN-02 — Общий диспетчер CAN13

**Проверено программно** · ТЗ §3

**Сделано.** Сохранены отзыв владения/момента и диагностическая очередь; оптимизация диспетчера дала 48 байт, адаптера момента — 132. Проверки объединённой сборки пройдены.

**Осталось.** Окончательное аппаратное владение и вызовы ведутся в CAN-03/H03-03.

**Критерий результата.** Программные тесты не заменяют измерение окон приёма 0x5E9.

**Код.** [targets/lfj8/lfj8_h03_can13.c](../targets/lfj8/lfj8_h03_can13.c) · [targets/lfj8/lfj8_h03_torque_can.c](../targets/lfj8/lfj8_h03_torque_can.c) · [targets/lfj8/lfj8_h03_dtc_can.c](../targets/lfj8/lfj8_h03_dtc_can.c)

**Что настраивать.** Lfj8H03Can13, предел опроса, лимиты возраста и повторная инициализация.

**Проверки.** [PC](#check-pc) · [M32R](#check-m32r) · [INTEGRATION2](#check-integration2) · [INTEGRATION3](#check-integration3) · [MEMORY4](#check-memory4)

**Разбор и основания.** [lfj8-h03-torque.md](../docs/lfj8-h03-torque.md) · [can02-loan-timeout.md](../verification/project-audit/can02-loan-timeout.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md) · [lfj8-h03-memory-layout.md](../docs/lfj8-h03-memory-layout.md)

<a id="can-03"></a>
## CAN-03 — Штатный запуск, IRQ и восстановление CAN0

**Требуется разработка** · ТЗ §3, §5

**Сделано.** Реализован единый владелец поколения для setup/TX gate, очистка BasicCAN и отзыв CAN13. Его состояние 12 байт включено в общий учёт RAM; целевые проверки прошли.

**Осталось.** Привязать владельца и единые часы к окончательному приложению, установить все обёртки и измерить окна TX/RX.

**Критерий результата.** Штатная ветвь не перезаписывает CAN13, старые кадры не принимаются после сброса, сохранена диагностика и отмена.

**Код.** [targets/lfj8/check_h03_can_lifecycle.py](../targets/lfj8/check_h03_can_lifecycle.py) · [targets/lfj8/check_h03_torque_tx_gate.py](../targets/lfj8/check_h03_torque_tx_gate.py) · [targets/lfj8/lfj8_h03_can13.c](../targets/lfj8/lfj8_h03_can13.c) · [targets/lfj8/lfj8_donor_io.c](../targets/lfj8/lfj8_donor_io.c) · [targets/lfj8/lfj8_h03_can_owner.c](../targets/lfj8/lfj8_h03_can_owner.c) · [targets/lfj8/lfj8_h03_can_owner.h](../targets/lfj8/lfj8_h03_can_owner.h)

**Что настраивать.** CAN0SLIMK/SLIST, флаг владельца, поколение, RX11/12 и TX/RX13.

**Проверки.** [M32R](#check-m32r) · [INTEGRATION](#check-integration) · [INTEGRATION3](#check-integration3) · [MEMORY4](#check-memory4)

**Разбор и основания.** [lfj8-9e1c-base.md](../docs/lfj8-9e1c-base.md) · [lfj8-h03-torque.md](../docs/lfj8-h03-torque.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md) · [lfj8-h03-memory-layout.md](../docs/lfj8-h03-memory-layout.md)

**Зависит от.** [H03-04](#h03-04)

**Следующий шаг для продолжения.** Связать готового CAN owner и RX target с общим временем/запуском; установить setup/TX gate, проверить потерю/возврат допуска.

**Кому удобно продолжить.** Чат CAN — 01a1f9ab-19c7-72c0-ac90-6aa98e4aa488. Это рекомендация, не резерв.

**Кто сейчас выполняет.** Проверить [общий список исполнителей](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/tree/task-board). Перед изменениями занять этот ID и точные файлы.

<a id="can-04"></a>
## CAN-04 — Запрос снижения момента по RB

**Проверено программно** · ТЗ §3, §4

**Сделано.** BusOff и чужое завершение TX13 отзывают подтверждение момента. Повторены нормальный диалог и потеря статуса с точным ordinary Bosch OFFLINE_ONLY.

**Осталось.** Целевые величины снижения и соответствие штатному Chery остаются ECU-02/CAN-05.

**Критерий результата.** Протокол 0x5E8/0x5E9 является RB. Его успешный тест не означает полного штатного Chery CAN.

**Код.** [targets/lfj8/lfj8_h03_torque.c](../targets/lfj8/lfj8_h03_torque.c) · [targets/lfj8/verify_h03_torque.py](../targets/lfj8/verify_h03_torque.py) · [targets/bosch/replay_e4m3_torque.py](../targets/bosch/replay_e4m3_torque.py)

**Что настраивать.** Lfj8TorqueCalibration.up/down, levels, reduction_q8, duration. 32/256 и 200 мс в тесте — испытательный профиль.

**Проверки.** [PC](#check-pc) · [M32R](#check-m32r) · [TORQUE](#check-torque) · [INTEGRATION2](#check-integration2) · [INTEGRATION3](#check-integration3)

**Разбор и основания.** [lfj8-h03-torque.md](../docs/lfj8-h03-torque.md) · [can04-torque-revocation.md](../verification/project-audit/can04-torque-revocation.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md)

<a id="can-05"></a>
## CAN-05 — Полнота штатного обмена Chery

**Требуется разработка** · ТЗ §3, §4

**Сделано.** C-приёмник Bosch сбрасывает операнды при смене поколения и отклоняет старые кадры 0x1AE; проверены 65536 пар. C-проверка отделена от машинного Bosch OFFLINE_ONLY.

**Осталось.** Подключить штатного производителя времени/поколения Bosch, недостающие поля, рабочий арбитраж момента и окончательный контракт двух BIN.

**Критерий результата.** Для каждого требуемого поля есть источник, единицы, период, недостоверность и проверенный потребитель. Замена штатного протокола отдельным RB не считается закрытием §3.

**Код.** [targets/lfj8/lfj8_bridge.h](../targets/lfj8/lfj8_bridge.h) · [targets/lfj8/lfj8_chery_tx.c](../targets/lfj8/lfj8_chery_tx.c) · [targets/bosch/chery_torque_rx.c](../targets/bosch/chery_torque_rx.c) · [targets/bosch/tx.py](../targets/bosch/tx.py) · [targets/bosch/test_chery_1ae_roundtrip.c](../targets/bosch/test_chery_1ae_roundtrip.c) · [tests/test_chery_1ae_roundtrip.py](../tests/test_chery_1ae_roundtrip.py)

**Что настраивать.** Lfj8Chery1ae.byte1/byte3_high/byte4 и флаги. Не заполнять неизвестные поля правдоподобными константами.

**Проверки.** [PC](#check-pc) · [BOSCH](#check-bosch) · [INTEGRATION](#check-integration) · [INTEGRATION3](#check-integration3) · [MEMORY4](#check-memory4)

**Разбор и основания.** [chery-can-dtc.md](../docs/chery-can-dtc.md) · [bosch-integration.md](../docs/bosch-integration.md) · [can05-1ae-roundtrip.md](../verification/project-audit/can05-1ae-roundtrip.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md) · [lfj8-h03-memory-layout.md](../docs/lfj8-h03-memory-layout.md)

**Зависит от.** [TOY-02](#toy-02)

<a id="ecu-01"></a>
## ECU-01 — Проверочная сборка Bosch E4M3

**Проверено программно** · ТЗ §4

**Сделано.** Сверяются все 51 точная запись целостности E4M3. Ordinary образ восстановлен побайтно; ST10, обмен и историческая трасса повторены. Статус OFFLINE_ONLY.

**Осталось.** Окончательный профиль после CAN-05/ECU-02 и выпуск REL-01.

**Критерий результата.** Это образ OFFLINE_ONLY, сохранение всех функций двигателя на машине не подтверждено.

**Код.** [targets/bosch/build.py](../targets/bosch/build.py) · [targets/bosch/tx.py](../targets/bosch/tx.py) · [targets/bosch/compact_branches.py](../targets/bosch/compact_branches.py)

**Что настраивать.** Опции with-model-fields, with-ordinary-model-field и compact. Профиль cruise=false/override=false явно ограничен.

**Проверки.** [BOSCH](#check-bosch) · [INTEGRATION3](#check-integration3)

**Разбор и основания.** [bosch-integration.md](../docs/bosch-integration.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md)

<a id="ecu-02"></a>
## ECU-02 — Калибровка момента и работа двигателя

**Требуются физические данные** · ТЗ §4, §10

**Сделано.** Проверены границы RPM, снятие момента по трём путям и старый токен; повторены 3256 CRC и 26 команд. Измерений новой пары нет.

**Осталось.** Проверить фактическое уменьшение момента для профилей переключений, пуск, впрыск, зажигание и потерю связи на новой паре. Сверить S04 с действующим образом.

**Критерий результата.** Протокол с идентифицированными BIN и измеренным результатом. Исторический стенд STM32 не переносит автоматически приёмку на LFJ8.

**Код.** [targets/lfj8/lfj8_h03_torque.h](../targets/lfj8/lfj8_h03_torque.h) · [targets/bosch/chery_torque_rx.c](../targets/bosch/chery_torque_rx.c)

**Что настраивать.** Шесть профилей up/down в Lfj8TorqueCalibration и применимость E4M3 к конкретному ЭБУ.

**Проверки.** [TORQUE](#check-torque) · [E4AUDIT](#check-e4audit) · [INTEGRATION3](#check-integration3)

**Разбор и основания.** [e4m3-audit.md](../docs/e4m3-audit.md) · [lfj8-9e1c-minimum-bench.md](../docs/lfj8-9e1c-minimum-bench.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md)

**Зависит от.** [CAN-05](#can-05)

<a id="h03-01"></a>
## H03-01 — Выбранная основа 9E1C и карта подключения

**Завершено в указанном объёме** · ТЗ §5

**Сделано.** H03 проверяется по точным SHA-256 и размеру; одного внутреннего ID недостаточно. Подлинный образ принят, изменённый отвергается.

**Осталось.** Физические параметры отдельных каналов учитываются в H03-05 и MODE-02.

**Критерий результата.** Для выбора платформы повторное подтверждение 9E1D и запуск PCMflash не нужны.

**Код.** [tools/inspect_lfj8_tcm.py](../tools/inspect_lfj8_tcm.py) · [tools/verify_sources.py](../tools/verify_sources.py)

**Что настраивать.** H03 LFJ8-T-D.bin, 524 288 байт. S05/S06 только исторические доноры.

**Проверки.** [SOURCES](#check-sources) · [INTEGRATION3](#check-integration3)

**Разбор и основания.** [lfj8-target-identity.md](../docs/lfj8-target-identity.md) · [lfj8-wiring-sources.md](../docs/lfj8-wiring-sources.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md)

<a id="h03-02"></a>
## H03-02 — S51, S83 и температура ATF

**Проверено программно** · ТЗ §5, §7

**Сделано.** Реализованы нативные события S51/S83, единый снимок S51/S83/ATF и владелец эпохи. Сравнения исходного/изменённого пути и общего времени прошли.

**Осталось.** Установить вызовы и единственные состояния в финальном приложении, подтвердить частоты таймеров и датчики U340E.

**Критерий результата.** Компоненты не подменяют окончательную установку обработчиков в BIN.

**Код.** [targets/lfj8/lfj8_donor_io.c](../targets/lfj8/lfj8_donor_io.c) · [targets/lfj8/lfj8_gear_observer.c](../targets/lfj8/lfj8_gear_observer.c) · [targets/lfj8/lfj8_h03_atf.c](../targets/lfj8/lfj8_h03_atf.c) · [targets/lfj8/lfj8_h03_atf_target.c](../targets/lfj8/lfj8_h03_atf_target.c) · [targets/lfj8/lfj8_h03_atf_target.h](../targets/lfj8/lfj8_h03_atf_target.h) · [targets/lfj8/h03_atf_hooks.S](../targets/lfj8/h03_atf_hooks.S) · [targets/lfj8/check_h03_atf_native.py](../targets/lfj8/check_h03_atf_native.py) · [targets/lfj8/lfj8_h03_sensor_target.c](../targets/lfj8/lfj8_h03_sensor_target.c) · [targets/lfj8/h03_sensor_hooks.S](../targets/lfj8/h03_sensor_hooks.S) · [targets/lfj8/check_h03_sensor_native.py](../targets/lfj8/check_h03_sensor_native.py)

**Что настраивать.** Lfj8GearCalibration, частоты таймеров, число фронтов S83, max_age_us/max_skew_us, тарировка ATF.

**Проверки.** [M32R](#check-m32r) · [INTEGRATION](#check-integration) · [INTEGRATION3](#check-integration3) · [MEMORY4](#check-memory4)

**Разбор и основания.** [lfj8-h03-input-paths.md](../docs/lfj8-h03-input-paths.md) · [lfj8-h03-atf-native.md](../docs/lfj8-h03-atf-native.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md) · [lfj8-h03-memory-layout.md](../docs/lfj8-h03-memory-layout.md)

<a id="h03-03"></a>
## H03-03 — Единое расписание и запуск приложения H03

**Требуется разработка** · ТЗ §2, §5

**Сделано.** Холодный запуск и foreground имеют владельца приложения; проверены 32 сценария и штатные пути. Объединённая линковка теперь выдаёт точные отсутствующие определения платформы.

**Осталось.** Определить application_binding, назначить состояния/настройки датчиков, initialize/take_toyota/service_phase и подтверждённые часы; включить все обёртки в итоговую карту.

**Критерий результата.** Полный цикл вызывается автономно, пропуск обнаруживается и без фазы выдачи, тестовые callbacks заменены подтверждёнными целевыми.

**Код.** [targets/lfj8/lfj8_h03_cycle.c](../targets/lfj8/lfj8_h03_cycle.c) · [targets/lfj8/lfj8_h03_phase_clock.c](../targets/lfj8/lfj8_h03_phase_clock.c) · [targets/lfj8/lfj8_h03_takeover.c](../targets/lfj8/lfj8_h03_takeover.c) · [targets/lfj8/h03_phase_release_hook.S](../targets/lfj8/h03_phase_release_hook.S) · [targets/lfj8/h03_native_hooks.S](../targets/lfj8/h03_native_hooks.S) · [targets/lfj8/check_h03_phase_wait.py](../targets/lfj8/check_h03_phase_wait.py) · [targets/lfj8/h03_phase_wait_hook.S](../targets/lfj8/h03_phase_wait_hook.S) · [targets/lfj8/lfj8_h03_application.c](../targets/lfj8/lfj8_h03_application.c) · [targets/lfj8/lfj8_h03_application.h](../targets/lfj8/lfj8_h03_application.h) · [targets/lfj8/h03_application_hooks.S](../targets/lfj8/h03_application_hooks.S)

**Что настраивать.** min_period/max_period/max_age, Lfj8H03TakeoverOps.phase_clock и callbacks. Частоту Toyota нельзя принять равной фазе H03.

**Проверки.** [PC](#check-pc) · [M32R](#check-m32r) · [PHASE](#check-phase) · [NATIVE](#check-native) · [INTEGRATION](#check-integration) · [INTEGRATION3](#check-integration3) · [MEMORY4](#check-memory4)

**Разбор и основания.** [lfj8-h03-control-cycle.md](../docs/lfj8-h03-control-cycle.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md) · [lfj8-h03-memory-layout.md](../docs/lfj8-h03-memory-layout.md)

**Зависит от.** [H03-04](#h03-04)

**Следующий шаг для продолжения.** Определить семь перечисленных привязок, единственные состояния, initialize/take_toyota/service_phase и исходные часы/снимки; объединить нативные обёртки.

**Кому удобно продолжить.** Чат запуска H03 — 01a1f99f-5cb5-70e0-afd0-60e6b41a5d51. Это рекомендация, не резерв.

**Кто сейчас выполняет.** Проверить [общий список исполнителей](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/tree/task-board). Перед изменениями занять этот ID и точные файлы.

<a id="h03-04"></a>
## H03-04 — Память, стек и сервисные пути

**Требуется разработка** · ТЗ §5

**Сделано.** 118 корней общей логики, 434 секции: 82812 байт. Новая компоновка с началом 0x1F7D0 оставляет 916 байт; шесть M32R сценариев исполняются по этим адресам. Все C-привязки требуют уже 89252 байта плюс неизвестная платформа. RAM 2684 + 4 байта.

**Осталось.** Разрешить семь недостающих определений, включить обёртки/настройки, доказать владение расширенными Flash/RAM, закрыть прямой и отложенный сервисный писатель, измерить полный стек/IRQ.

**Критерий результата.** Карта сборки и анализ всех владельцев, подтверждённый запас стека и измерения. Свободное окно в ELF само по себе не разрешает запись.

**Код.** [targets/lfj8/check_h03_link.py](../targets/lfj8/check_h03_link.py) · [targets/lfj8/check_h03_ram_candidate.py](../targets/lfj8/check_h03_ram_candidate.py) · [targets/lfj8/check_h03_flash_residency.py](../targets/lfj8/check_h03_flash_residency.py) · [targets/lfj8/check_h03_service_isolation.py](../targets/lfj8/check_h03_service_isolation.py) · [targets/lfj8/audit_h03_irq_stack.py](../targets/lfj8/audit_h03_irq_stack.py) · [targets/lfj8/lfj8_h03_storage.h](../targets/lfj8/lfj8_h03_storage.h) · [targets/lfj8/check_h03_storage.py](../targets/lfj8/check_h03_storage.py) · [tools/check_h03_image_layout.py](../tools/check_h03_image_layout.py) · [targets/lfj8/lfj8_h03_layout.py](../targets/lfj8/lfj8_h03_layout.py) · [tests/test_h03_layout.py](../tests/test_h03_layout.py) · [targets/lfj8/check_h03_service_writes.py](../targets/lfj8/check_h03_service_writes.py)

**Что настраивать.** Flash: prefix-candidate [0x1F7D0,0x30000), [0x7C118,0x7FFFC), только модель. RAM: [0x806B40,0x806F8C), [0x808E40,0x809054), [0x809054,0x809470); ещё 4 байта native BSS и полный стек вне инвентаря. FF и успешный ELF не подтверждают владение.

**Проверки.** [M32R](#check-m32r) · [NATIVE](#check-native) · [STORAGE](#check-storage) · [INTEGRATION](#check-integration) · [INTEGRATION2](#check-integration2) · [INTEGRATION3](#check-integration3) · [MEMORY4](#check-memory4)

**Разбор и основания.** [lfj8-h03-ram-audit.md](../docs/lfj8-h03-ram-audit.md) · [lfj8-h03-flash.md](../docs/lfj8-h03-flash.md) · [lfj8-h03-service-isolation.md](../docs/lfj8-h03-service-isolation.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md) · [lfj8-h03-memory-layout.md](../docs/lfj8-h03-memory-layout.md)

**Следующий шаг для продолжения.** Закрыть прямые и уже принятые отложенные сервисные записи в проектную RAM, установить политику Virtual Flash; пересчитать окончательную карту и полный стек.

**Кто сейчас выполняет.** Проверить [общий список исполнителей](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/tree/task-board). Перед изменениями занять этот ID и точные файлы.

<a id="h03-05"></a>
## H03-05 — SLT, силовые выходы и реакция на отказ

**Требуются физические данные** · ТЗ §2, §5

**Сделано.** Целевой inhibit отзывает D/E/F и Pressure A, очищает оба банка команд; нативные проверки переходов прошли. Физическая калибровка остаётся открытой.

**Осталось.** Подключить inhibit к финальному запуску; подтвердить каналы/полярность, q Toyota→ток→давление→H03 и реакцию при остановке CPU.

**Критерий результата.** Измеренные таблицы в допустимой области питания/ATF, реакция каждого выхода и гидравлики на отказ, отсутствие старой команды после восстановления.

**Код.** [targets/lfj8/lfj8_h03_outputs.c](../targets/lfj8/lfj8_h03_outputs.c) · [targets/lfj8/lfj8_h03_takeover.c](../targets/lfj8/lfj8_h03_takeover.c) · [targets/lfj8/check_h03_slt_fault.py](../targets/lfj8/check_h03_slt_fault.py) · [targets/lfj8/lfj8_h03_output_inhibit.c](../targets/lfj8/lfj8_h03_output_inhibit.c)

**Что настраивать.** Lfj8H03OutputBinding, Lfj8H03SltCalibration, рабочая область ATF/питания и Lfj8H03TakeoverOps.inhibit. Тестовые 500 мА не являются калибровкой.

**Проверки.** [M32R](#check-m32r) · [NATIVE](#check-native) · [INTEGRATION3](#check-integration3) · [MEMORY4](#check-memory4)

**Разбор и основания.** [lfj8-slt-calibration.md](../docs/lfj8-slt-calibration.md) · [lfj8-h03-output-adapter.md](../docs/lfj8-h03-output-adapter.md) · [lfj8-9e1c-minimum-bench.md](../docs/lfj8-9e1c-minimum-bench.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md) · [lfj8-h03-memory-layout.md](../docs/lfj8-h03-memory-layout.md)

**Следующий шаг для продолжения.** Подключить готовый inhibit в application_binding; квалифицировать полярность и ток–давление отдельно от трасс регистров.

**Кому удобно продолжить.** Чат силовых выходов — 01a1f9a2-d0ae-78d3-86f1-21b27426fd3f. Это рекомендация, не резерв.

**Кто сейчас выполняет.** Проверить [общий список исполнителей](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/tree/task-board). Перед изменениями занять этот ID и точные файлы.

<a id="io-01"></a>
## IO-01 — Два дополнительных реле

**Отложено владельцем** · ТЗ §6

**Сделано.** Таблица R→оба, L→дополнительное, прочие→выключены проверена программно.

**Осталось.** После первого рабочего файла определить два выхода, драйверы и параметры катушек.

**Критерий результата.** Проверены оба физических выхода во всех положениях и при отказах.

**Код.** [controller/src/rbm_u340e.c](../controller/src/rbm_u340e.c) · [targets/lfj8/lfj8_bridge.c](../targets/lfj8/lfj8_bridge.c)

**Что настраивать.** Контакты, полярность и ток ещё не назначены.

**Проверки.** [PC](#check-pc)

**Разбор и основания.** [decisions.md](../docs/decisions.md) · [lfj8-selector.md](../docs/lfj8-selector.md)

<a id="vss-01"></a>
## VSS-01 — Точный расчёт VSS и скорость по CAN

**Проверено программно** · ТЗ §7

**Сделано.** Устранено промежуточное переполнение; 25000 сравнений и профиль 37/8, 3,53 м прошли на ПК/M32R. Bosch принимает кадр скорости. Параметры реального времени и машины учитываются отдельно.

**Осталось.** Рабочие параметры машины ведутся в VSS-02, штатная установка в CAN-03/H03-03.

**Критерий результата.** Округление 4,545 не используется как расчётный коэффициент.

**Код.** [targets/lfj8/lfj8_bridge.c](../targets/lfj8/lfj8_bridge.c) · [targets/lfj8/lfj8_chery_tx.c](../targets/lfj8/lfj8_chery_tx.c) · [targets/bosch/build.py](../targets/bosch/build.py)

**Что настраивать.** lfj8_vss_raw_1ae(ticks,pulse_count,tick_hz,wheel_um,wheel_num,wheel_den,capture_state).

**Проверки.** [PC](#check-pc) · [M32R](#check-m32r) · [BOSCH](#check-bosch) · [INTEGRATION3](#check-integration3)

**Разбор и основания.** [README.md](../targets/lfj8/README.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md)

<a id="vss-02"></a>
## VSS-02 — Кинематика и параметры реальной скорости

**Требуются физические данные** · ТЗ §7

**Сделано.** Общий снимок S51/S83/ATF и эпоха таймера проверены при потере, остановке, wrap и сбросе. Физические частоты и кинематика ещё не измерены.

**Осталось.** Задать подтверждённые тайм-ауты, окружность/передаточное отношение, частоты и независимый критерий остановки; связать с приложением H03-03.

**Критерий результата.** Скорость совпадает с эталоном в согласованном диапазоне, потеря импульсов отличается от остановки.

**Код.** [targets/lfj8/lfj8_bridge.h](../targets/lfj8/lfj8_bridge.h) · [targets/lfj8/lfj8_donor_io.h](../targets/lfj8/lfj8_donor_io.h) · [targets/lfj8/lfj8_gear_observer.h](../targets/lfj8/lfj8_gear_observer.h) · [targets/lfj8/lfj8_h03_sensor_feed.c](../targets/lfj8/lfj8_h03_sensor_feed.c)

**Что настраивать.** wheel_um, wheel_num/wheel_den, частота счётчика, тайм-ауты; 100/22 уже задано.

**Проверки.** [M32R](#check-m32r) · [INTEGRATION3](#check-integration3) · [MEMORY4](#check-memory4)

**Разбор и основания.** [lfj8-9e1c-minimum-bench.md](../docs/lfj8-9e1c-minimum-bench.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md) · [lfj8-h03-memory-layout.md](../docs/lfj8-h03-memory-layout.md)

**Следующий шаг для продолжения.** Связать sensor_target/config с H03-03, установить подтверждённые частоты/тайм-ауты и критерий остановки.

**Кому удобно продолжить.** Чат датчиков — 01a1f9a8-7b61-7763-adaa-0e3e11d1dbf4. Это рекомендация, не резерв.

**Кто сейчас выполняет.** Проверить [общий список исполнителей](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/tree/task-board). Перед изменениями занять этот ID и точные файлы.

<a id="panel-01"></a>
## PANEL-01 — Импульсы Bosch на приборную панель

**Отложено владельцем** · ТЗ §7

**Сделано.** Рассчитаны фронты и коррекция, программно исследован P3.6. В текущем Bosch-кандидате физический выход не реализован.

**Осталось.** После первого файла подключить таймер/вывод, сохранение коэффициента и проверку показаний панели.

**Критерий результата.** Реальные частота, форма, диагностика и сохранение настройки проверены.

**Код.** [targets/panel/panel_pulse.c](../targets/panel/panel_pulse.c) · [targets/bosch/panel_gpio.c](../targets/bosch/panel_gpio.c)

**Что настраивать.** Коэффициент импульсов/км, период, выход GPIO и постоянное хранилище.

**Проверки.** [PC](#check-pc)

**Разбор и основания.** [panel-output.md](../docs/panel-output.md) · [decisions.md](../docs/decisions.md)

<a id="mode-01"></a>
## MODE-01 — Логика шести положений и кнопок

**Проверено программно** · ТЗ §8

**Сделано.** Восстановление после отказа снимка больше не создаёт ложных фронтов кнопок. Удержание требует отпускания и нового нажатия; восемь сценариев ПК/M32R прошли.

**Осталось.** Довести физические входы и применение результата в MODE-02, правила поставки в MODE-03.

**Критерий результата.** Компонентный requested_gear не равен выполненному гидравлическому переключению.

**Код.** [controller/src/rbm_u340e.c](../controller/src/rbm_u340e.c) · [targets/lfj8/lfj8_range_control.c](../targets/lfj8/lfj8_range_control.c) · [targets/lfj8/lfj8_selector_adc.c](../targets/lfj8/lfj8_selector_adc.c) · [controller/tests/test_shift_buttons.c](../controller/tests/test_shift_buttons.c)

**Что настраивать.** RbmU340ePolicy, стабильные кнопки до rbm_u340e_step, окна ADC. Расчётные 2=200 Ом, L=91 Ом требуют проверки.

**Проверки.** [PC](#check-pc) · [M32R](#check-m32r) · [INTEGRATION2](#check-integration2) · [INTEGRATION3](#check-integration3)

**Разбор и основания.** [lfj8-selector.md](../docs/lfj8-selector.md) · [mode01-shift-conflict.md](../verification/project-audit/mode01-shift-conflict.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md)

<a id="mode-02"></a>
## MODE-02 — Подключение селектора, Tiptronic и Overdrive

**Требуется разработка** · ТЗ §5, §8

**Сделано.** Целевой callback AN2 и общая заявка используют независимые GP−5722/GP−5250.2; ПК/M32R и пять пар исходного ADC прошли.

**Осталось.** Назначить состояния/часы, физические Tiptronic/OD и провести принятую requested_gear через весь гидравлический цикл.

**Критерий результата.** Реальные нажатия проходят до исполнения запроса в полном цикле, дребезг/обрыв не создают повторных команд.

**Код.** [targets/lfj8/lfj8_selector_adc.c](../targets/lfj8/lfj8_selector_adc.c) · [targets/lfj8/lfj8_range_control.c](../targets/lfj8/lfj8_range_control.c) · [controller/src/rbm_u340e.c](../controller/src/rbm_u340e.c) · [targets/lfj8/lfj8_h03_cycle.c](../targets/lfj8/lfj8_h03_cycle.c) · [targets/lfj8/lfj8_h03_input_binding.c](../targets/lfj8/lfj8_h03_input_binding.c) · [targets/lfj8/lfj8_h03_input_target.c](../targets/lfj8/lfj8_h03_input_target.c)

**Что настраивать.** AD0DT2, событие 0x804BC6, P1DATA и вход Overdrive. max_age_us задаётся по фактическому ритму ADC.

**Проверки.** [PC](#check-pc) · [M32R](#check-m32r) · [INTEGRATION](#check-integration) · [INTEGRATION3](#check-integration3) · [MEMORY4](#check-memory4)

**Разбор и основания.** [lfj8-selector.md](../docs/lfj8-selector.md) · [lfj8-h03-input-paths.md](../docs/lfj8-h03-input-paths.md) · [mode02-button-input.md](../verification/project-audit/mode02-button-input.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md) · [lfj8-h03-memory-layout.md](../docs/lfj8-h03-memory-layout.md)

**Зависит от.** [H03-03](#h03-03)

**Следующий шаг для продолжения.** Связать физические AN2/Tiptronic/OD и независимые разрешения с общей заявкой; продолжить независимые входы TOY-03.

**Кому удобно продолжить.** Чат селектора и кнопок — 01a1f9c7-675a-78c3-be98-5bd65e44995c. Это рекомендация, не резерв.

**Кто сейчас выполняет.** Проверить [общий список исполнителей](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/tree/task-board). Перед изменениями занять этот ID и точные файлы.

<a id="mode-03"></a>
## MODE-03 — Окончательная политика режимов

**Требуется разработка** · ТЗ §8

**Сделано.** 128 конфигураций и 501760 заявок прошли на ПК и M32R. Политика выпуска и привязка к целевому циклу открыты.

**Осталось.** Определить режим после питания, сохранение выбора, разрешённые положения и ограничения +/−/OD для выпуска.

**Критерий результата.** Политика согласована с донорской логикой и подтверждена матрицей режимов. Тестовые defaults не выдаются за решение владельца.

**Код.** [controller/include/rbm_u340e.h](../controller/include/rbm_u340e.h) · [controller/src/rbm_u340e.c](../controller/src/rbm_u340e.c)

**Что настраивать.** initial_mode, initial_overdrive_enabled, manual_selectors, overdrive_limit_modes, allowed_gears.

**Проверки.** [PC](#check-pc) · [INTEGRATION3](#check-integration3)

**Разбор и основания.** [decisions.md](../docs/decisions.md) · [lfj8-selector.md](../docs/lfj8-selector.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md)

<a id="src-01"></a>
## SRC-01 — Реестр происхождения и контроль исходников

**Завершено в указанном объёме** · ТЗ §9

**Сделано.** Проверены ТЗ, S01–S04, H03 и точные Git-ревизии R1–R4; неверный клон отвергается. Реестр происхождения сохранён.

**Осталось.** Для новых материалов продолжать реестр. Архивные S05/S06 заново не нужны для идентификации H03.

**Критерий результата.** Зафиксированы роли, версии и SHA-256 отдельно от Git blob. Новые материалы не подменяют выбранную основу.

**Код.** [data/sources.json](../data/sources.json) · [controller/vendor/toyota/manifest.json](../controller/vendor/toyota/manifest.json) · [tools/verify_sources.py](../tools/verify_sources.py)

**Что настраивать.** Активная цель H03. S05=PCM SuperH, S06/H02=9E1B для сравнения.

**Проверки.** [SOURCES](#check-sources) · [INTEGRATION3](#check-integration3)

**Разбор и основания.** [decisions.md](../docs/decisions.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md)

<a id="aud-01"></a>
## AUD-01 — Программный аудит истории E4M3

**Завершено в указанном объёме** · ТЗ §10

**Сделано.** Трасса, сборщик и ST10 берутся из одного закреплённого R4. Повторены 3256 CRC и 26 команд ordinary образа; аппаратная часть остаётся в ECU-02.

**Осталось.** Аппаратное подтверждение и целевые профили остаются в ECU-02.

**Критерий результата.** Закрыт объём отчёта и программного исследования. Штатная работа установленного ECU не объявлена проверенной.

**Код.** [data/e4m3-diff.json](../data/e4m3-diff.json) · [targets/bosch/verify.py](../targets/bosch/verify.py) · [targets/bosch/replay_e4m3_torque.py](../targets/bosch/replay_e4m3_torque.py)

**Что настраивать.** S04 идентифицировать по SHA-256, а не повторяющемуся имени BENCH.

**Проверки.** [SOURCES](#check-sources) · [BOSCH](#check-bosch) · [E4AUDIT](#check-e4audit) · [INTEGRATION3](#check-integration3)

**Разбор и основания.** [e4m3-audit.md](../docs/e4m3-audit.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md)

<a id="dtc-01"></a>
## DTC-01 — Прикладной сеанс и статусы Chery

**Проверено программно** · ТЗ §11

**Сделано.** Общий снимок H03 снабжает RPM, ОЖ и модель Chery; BusOff и сбой часов приостанавливают обработку. Общий набор прошёл; штатный вызов и сканер открыты.

**Осталось.** Native RX, прочие мониторы, сохранение и сканер ведутся отдельно.

**Критерий результата.** Поддержан конкретный профиль CAN C0. Остальные FC/сервисы и K-Line не объявлены реализованными.

**Код.** [diagnostics/chery_dtc.c](../diagnostics/chery_dtc.c) · [diagnostics/chery_dtc_can.c](../diagnostics/chery_dtc_can.c) · [diagnostics/chery_dtc_link.c](../diagnostics/chery_dtc_link.c) · [diagnostics/chery_model_monitor.c](../diagnostics/chery_model_monitor.c) · [targets/lfj8/lfj8_h03_engine_feed.c](../targets/lfj8/lfj8_h03_engine_feed.c)

**Что настраивать.** Пять исторических слотов, таблица 96 индексов S03, возраст FC и таймеры сеанса.

**Проверки.** [PC](#check-pc) · [M32R](#check-m32r) · [INTEGRATION2](#check-integration2) · [INTEGRATION3](#check-integration3)

**Разбор и основания.** [diagnostics-integration.md](../docs/diagnostics-integration.md) · [dtc01-session-lease.md](../verification/project-audit/dtc01-session-lease.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md)

<a id="dtc-02"></a>
## DTC-02 — Штатный приём BasicCAN для диагностического сеанса

**Требуется разработка** · ТЗ §5, §11

**Сделано.** Реализованы целевые RX callbacks и foreground с единым CAN owner. В общей сборке проверен путь RX 0x732 → TX 0x722, перезапись, поколения и парный обход.

**Осталось.** Установить нижние обёртки и единственный DTC target/IRQ binding, связать непрерывное время и окончательный CAN foreground; проверить границы записи блока.

**Критерий результата.** Прогон оригинального пути RX с потерей/перезаписью и ложными кадрами. Учтена граница приложения 0x008000.

**Код.** [targets/lfj8/lfj8_h03_dtc_can.c](../targets/lfj8/lfj8_h03_dtc_can.c) · [targets/lfj8/lfj8_h03_can13.c](../targets/lfj8/lfj8_h03_can13.c) · [targets/lfj8/test_lfj8_h03_dtc_can.c](../targets/lfj8/test_lfj8_h03_dtc_can.c) · [targets/lfj8/lfj8_h03_dtc_rx_queue.c](../targets/lfj8/lfj8_h03_dtc_rx_queue.c) · [targets/lfj8/lfj8_h03_dtc_rx_queue.h](../targets/lfj8/lfj8_h03_dtc_rx_queue.h) · [targets/lfj8/test_lfj8_h03_dtc_rx_queue.c](../targets/lfj8/test_lfj8_h03_dtc_rx_queue.c) · [targets/lfj8/check_h03_dtc_basiccan.py](../targets/lfj8/check_h03_dtc_basiccan.py) · [targets/lfj8/lfj8_h03_dtc_target.c](../targets/lfj8/lfj8_h03_dtc_target.c) · [targets/lfj8/lfj8_h03_dtc_target.h](../targets/lfj8/lfj8_h03_dtc_target.h)

**Что настраивать.** RX14/15 0x001500–0x0016F4, копия 0x808526, разбор около 0x001578. Прямой перехват затрагивает область ниже приложения. Очередь: max_age_bits < 32768 и не больше бюджета CAN13, bit_time_us из настройки шины; непрерывное время микросекунд. Конкретное размещение RAM открыто.

**Проверки.** [PC](#check-pc) · [M32R](#check-m32r) · [INTEGRATION](#check-integration) · [INTEGRATION3](#check-integration3) · [MEMORY4](#check-memory4)

**Разбор и основания.** [diagnostics-integration.md](../docs/diagnostics-integration.md) · [lfj8-h03-flash.md](../docs/lfj8-h03-flash.md) · [dtc02-basiccan.md](../verification/project-audit/dtc02-basiccan.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md) · [lfj8-h03-memory-layout.md](../docs/lfj8-h03-memory-layout.md)

**Следующий шаг для продолжения.** Привязать единственный DTC target и IRQ pointer, время/поколение; включить проверенные нижние обёртки в окончательный образ.

**Кому удобно продолжить.** Чат диагностики — 01a1f9ae-4a7e-7e31-951a-f6383e1831ee. Это рекомендация, не резерв.

**Кто сейчас выполняет.** Проверить [общий список исполнителей](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/tree/task-board). Перед изменениями занять этот ID и точные файлы.

<a id="dtc-03"></a>
## DTC-03 — Все диагностические события и соответствия Toyota/Chery

**Требуется разработка** · ТЗ §11

**Сделано.** Нативный монитор ATF включён в перемещаемый мост; 20 сценариев и отрицательные проверки M32R прошли. Другие мониторы и соответствия Chery открыты.

**Осталось.** Завершить и согласовать соответствия ATF, скоростей, соленоидов, давления, SLU и двигателя. Реализовать условия обнаружения/сохранения/сброса.

**Критерий результата.** Код соответствует фактическому отказу и узлу, статусы подтверждены. Отсутствующий прямой аналог явно обозначен.

**Код.** [diagnostics/chery_dtc.c](../diagnostics/chery_dtc.c) · [targets/lfj8/lfj8_h03_engine_feed.c](../targets/lfj8/lfj8_h03_engine_feed.c) · [docs/ta2005-diagnostic-code-table.csv](../docs/ta2005-diagnostic-code-table.csv) · [tests/test_chery_dtc_table.py](../tests/test_chery_dtc_table.py)

**Что настраивать.** Индекс DTC, маски current/history, разрешение записи и пороги монитора.

**Проверки.** [PC](#check-pc) · [M32R](#check-m32r) · [INTEGRATION](#check-integration) · [INTEGRATION3](#check-integration3)

**Разбор и основания.** [diagnostics-integration.md](../docs/diagnostics-integration.md) · [dtc03-table.md](../verification/project-audit/dtc03-table.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md)

**Зависит от.** [H03-05](#h03-05), [TOY-06](#toy-06)

<a id="dtc-04"></a>
## DTC-04 — Хранение DTC после выключения питания

**Требуется разработка** · ТЗ §5, §11

**Сделано.** Восстановлена геометрия 13 блоков H03 и реализован полусловный backend журнала. ПК/M32R: 45 прерываний записи, 33 стирания, 256 битовых отказов и восстановление прошли.

**Осталось.** Назначить носитель/блоки, физический драйвер, исключительное владение и политику износа; подключить долговечную очистку и восстановление перед запуском.

**Критерий результата.** Перезапуск и прерванная запись не восстанавливают очищенную или повреждённую историю.

**Код.** [diagnostics/chery_dtc.h](../diagnostics/chery_dtc.h) · [diagnostics/chery_dtc.c](../diagnostics/chery_dtc.c) · [diagnostics/chery_dtc_journal.c](../diagnostics/chery_dtc_journal.c) · [diagnostics/chery_dtc_journal.h](../diagnostics/chery_dtc_journal.h) · [diagnostics/test_chery_dtc_journal.c](../diagnostics/test_chery_dtc_journal.c) · [targets/lfj8/lfj8_h03_nvm.c](../targets/lfj8/lfj8_h03_nvm.c) · [targets/lfj8/check_h03_nvm.py](../targets/lfj8/check_h03_nvm.py)

**Что настраивать.** Целевая область NVM и политика износа ещё не назначены.

**Проверки.** [PC](#check-pc) · [INTEGRATION](#check-integration) · [INTEGRATION3](#check-integration3) · [MEMORY4](#check-memory4)

**Разбор и основания.** [diagnostics-integration.md](../docs/diagnostics-integration.md) · [lfj8-h03-flash.md](../docs/lfj8-h03-flash.md) · [dtc04-journal.md](../verification/project-audit/dtc04-journal.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md) · [lfj8-h03-memory-layout.md](../docs/lfj8-h03-memory-layout.md)

**Зависит от.** [H03-04](#h03-04)

**Следующий шаг для продолжения.** Назначить носитель и два стираемых блока либо иной обоснованный backend, реализовать физический драйвер и подключить восстановление при старте.

**Кому удобно продолжить.** Чат постоянной памяти — 01a1f9b1-c11a-7b23-abcf-3214ce643805. Это рекомендация, не резерв.

**Кто сейчас выполняет.** Проверить [общий список исполнителей](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/tree/task-board). Перед изменениями занять этот ID и точные файлы.

<a id="rel-01"></a>
## REL-01 — Два целевых BIN и воспроизводимый комплект

**Требуется разработка** · ТЗ §1, §4, §5, §9

**Сделано.** Ещё 13 порций объединены и проверены. Адресная модель общего кода проходит; полный набор привязок отклонён из-за семи определений. Сервисные записи достигают новой RAM. TCM BIN отсутствует, Bosch остаётся OFFLINE_ONLY.

**Осталось.** Завершить привязки и защиту памяти, источники/масштабы входов, арбитраж Bosch, NVM и аппаратные калибровки; затем собрать два целевых BIN и манифест.

**Критерий результата.** Оба образа соответствуют выбранным основам и закрытому объёму первого файла, связаны с исходниками и фактическими результатами проверки.

**Код.** [controller/build_target.py](../controller/build_target.py) · [targets/lfj8/check_h03_link.py](../targets/lfj8/check_h03_link.py) · [targets/bosch/build.py](../targets/bosch/build.py) · [tools/package_workset.py](../tools/package_workset.py)

**Что настраивать.** Отдельные поля build_verified, model_verified и hardware_verified. Не переименовывать ELF/тестовый BIN в рабочую прошивку.

**Проверки.** [SOURCES](#check-sources) · [PC](#check-pc) · [M32R](#check-m32r) · [NATIVE](#check-native) · [BOSCH](#check-bosch) · [INTEGRATION](#check-integration) · [INTEGRATION3](#check-integration3) · [MEMORY4](#check-memory4)

**Разбор и основания.** [verification.md](../docs/verification.md) · [working-set.md](../docs/working-set.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md) · [lfj8-h03-memory-layout.md](../docs/lfj8-h03-memory-layout.md)

**Зависит от.** [TOY-04](#toy-04), [TOY-05](#toy-05), [TOY-06](#toy-06), [CAN-03](#can-03), [CAN-05](#can-05), [ECU-02](#ecu-02), [H03-04](#h03-04), [H03-05](#h03-05), [VSS-02](#vss-02), [MODE-02](#mode-02), [MODE-03](#mode-03), [DTC-02](#dtc-02), [DTC-03](#dtc-03), [DTC-04](#dtc-04)

**Следующий шаг для продолжения.** После закрытия обязательных привязок собрать два целевых BIN, проверить запуск, целостность и отсутствие тестовых функций.

**Кто сейчас выполняет.** Проверить [общий список исполнителей](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/tree/task-board). Перед изменениями занять этот ID и точные файлы.

<a id="rel-02"></a>
## REL-02 — Приёмка новой связки на оборудовании

**Требуются физические данные** · ТЗ §2, §3, §4, §5, §7, §8, §11

**Сделано.** Разбор CANHacker TRC проверяет четыре периодических ID, сроки, контроль и счётчик 0x1AE. Архив и отрицательные случаи проверены; испытаний новой пары не было.

**Осталось.** После подготовки соответствующего образа выполнить входы, CAN, момент, переключения, SLT/SLU, отказы, пуск и проверку сканером в режиме Chery.

**Критерий результата.** Журналы содержат версии BIN, условия, измерения, допуски и результат. Программные тесты учитываются отдельно.

**Код.** [docs/lfj8-9e1c-minimum-bench.md](../docs/lfj8-9e1c-minimum-bench.md) · [docs/verification.md](../docs/verification.md)

**Что настраивать.** Приборы, температуры/нагрузки и численные допуски должны иметь источник. Реле и панель исключены из первой приёмки.

**Проверки.** [INTEGRATION3](#check-integration3)

**Разбор и основания.** [lfj8-9e1c-minimum-bench.md](../docs/lfj8-9e1c-minimum-bench.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md)

**Зависит от.** [REL-01](#rel-01)

## Команды проверок

Команды выполняются из корня. `$h03` — выбранный файл H03, `$m32rGcc` — компилятор M32R с его симулятором, `$zig` — компилятор ПК. `$r4` и `$r4Engine` — зафиксированный R4 и его development/E4M3/engine, `$s04` — образ с SHA-256 из реестра, `$c167Model` — tools/c167_subset.py из R2. Пути локального компьютера хранятся только в local/.

Сначала собираются зависимости. M32R создаёт объекты для NATIVE, PC создаёт исполняемый файл для TORQUE. SOURCES сверяет исходники через Git blob, поэтому рабочее дерево R1 может быть без checkout.

<a id="check-sources"></a>
### SOURCES — Исходники и выбранный H03

```powershell
python -B tools/verify_sources.py --donor-repo .sources/R1 --base-9e1c $h03
```

**Последний сохранённый результат.** [sources.txt](../verification/project-audit/sources.txt)

<a id="check-pc"></a>
### PC — Полный набор проверок на компьютере

```powershell
python -B tools/build_pc_checks.py --cc $zig --out local/pc-checks
```

**Последний сохранённый результат.** [pc-checks.json](../verification/project-audit/integration-3/pc-checks.json)

<a id="check-m32r"></a>
### M32R — Сборка и модель M32R

```powershell
python -B controller/build_target.py m32r --cc $m32rGcc --out local/audit/controller
python -B targets/lfj8/build.py --output local/audit/bridge --m32r-cc $m32rGcc --base-9e1c $h03
python -B targets/lfj8/check_h03_link.py --base $h03 --gcc $m32rGcc --bridge local/audit/bridge/lfj8_9e1c_m32r.o --controller local/audit/controller/rbm_u340e_m32r_be.o --out local/audit/h03-link.json --bosch-trace verification/e4m3-can-9e1c/ordinary-model/round-trip.json
```

**Последний сохранённый результат.** [m32r-link.json](../verification/project-audit/integration-3/m32r-link.json)

<a id="check-phase"></a>
### PHASE — Штатная публикация и потери событий

```powershell
python -B targets/lfj8/check_h03_phase_clock.py --base $h03 --gcc $m32rGcc --out local/audit/h03-phase-clock.json
python -B targets/lfj8/check_h03_phase_hook.py --base $h03 --gcc $m32rGcc --out local/audit/h03-phase-hook.json
```

**Последний сохранённый результат.** [h03-phase-clock.json](../verification/e4m3-can-9e1c/h03-phase-clock.json) · [h03-phase-hook.json](../verification/e4m3-can-9e1c/h03-phase-hook.json)

<a id="check-native"></a>
### NATIVE — Штатные фазы H03 с тестовыми входами

```powershell
python -B targets/lfj8/check_h03_native_hooks.py --base $h03 --gcc $m32rGcc --controller local/audit/controller/rbm_u340e_m32r_be.o --out local/audit/h03-native-phases.json
```

**Последний сохранённый результат.** [h03-native-phases.json](../verification/e4m3-can-9e1c/h03-native-phases.json)

<a id="check-bosch"></a>
### BOSCH — Сборка и модель обычного режима Bosch

```powershell
python -B targets/bosch/build.py --engine $r4Engine --s04 $s04 --outdir local/audit/bosch --with-model-fields --with-ordinary-model-field --compact
python -B targets/bosch/verify_ordinary_model_field.py --engine $r4Engine --s04 $s04 --model $c167Model --image local/audit/bosch/E4M3_CHERY_ORDINARY_MODEL_NO_CRUISE_COMPACT_OFFLINE_ONLY.bin --compact
```

**Последний сохранённый результат.** [manifest.json](../verification/e4m3-can-9e1c/ordinary-model/manifest.json) · [ordinary-model-field.json](../verification/e4m3-can-9e1c/ordinary-model/ordinary-model-field.json)

<a id="check-signals"></a>
### SIGNALS — Проверка неоднозначности нагрузки по доступному CAN

```powershell
python -B targets/bosch/audit_bosch_signal_transport.py --engine $r4Engine --s04 $s04 --model $c167Model
```

**Последний сохранённый результат.** [bosch-signal-transport-audit.json](../verification/e4m3-can-9e1c/bosch-signal-transport-audit.json)

<a id="check-slu"></a>
### SLU — Донорская функция SLU

```powershell
python -B targets/lfj8/check_toyota_slu.py --cc $zig --r1 .sources/R1 --r3 .sources/R2
```

**Последний сохранённый результат.** [toyota-slu-host.json](../verification/e4m3-can-9e1c/toyota-slu-host.json)

<a id="check-torque"></a>
### TORQUE — Диалог Toyota и Bosch с потерей статуса

```powershell
python -B targets/lfj8/verify_h03_torque.py --repo $r4 --image verification/e4m3-can-9e1c/E4M3_CHERY_MODEL_FIELDS_COMPACT_OFFLINE_ONLY.bin --fixture local/pc-checks/controller/lfj8_h03_torque_test.exe
```

**Последний сохранённый результат.** [h03-torque-dialogue.json](../verification/e4m3-can-9e1c/h03-torque-dialogue.json)

<a id="check-e4audit"></a>
### E4AUDIT — Исторический аудит S04 и происхождения E4M3

См. команды и границы проверок в docs/e4m3-audit.md. В этой сверке заново проверены S04, производный образ и обмен, весь исторический комплект R4 повторно не запускался.

**Последний сохранённый результат.** [e4m3-diff.json](../data/e4m3-diff.json)

<a id="check-coord"></a>
### COORD — Общий учёт нескольких чатов и переносимость аудита

```powershell
python -B -m unittest discover -s tests -p test_task_coordination.py -v
python -B -m unittest discover -s tests -p test_project_status.py -v
```

**Последний сохранённый результат.** [coordination-tests.txt](../verification/project-audit/task-board-continuations/coordination-tests.txt) · [status-tests.txt](../verification/project-audit/task-board-continuations/status-tests.txt)

<a id="check-storage"></a>
### STORAGE — Актуальные состояния и кандидаты RAM M32R

```powershell
python -B targets/lfj8/check_h03_storage.py --base $h03 --gcc $m32rGcc --out local/audit/h03-storage.json
python -B -m unittest discover -s tests -p test_h03_storage.py -v
```

**Последний сохранённый результат.** [final-storage.json](../verification/project-audit/integration-3/final-storage.json) · [final-storage-tests.txt](../verification/project-audit/integration-3/final-storage-tests.txt)

<a id="check-integration"></a>
### INTEGRATION — Объединение опубликованных порций 20.11.2026

```powershell
См. docs/working-set.md: объединение 12 порций и verification/project-audit/integration/. Запуск ПК, M32R, штатных путей и упаковщика имеет отдельные границы.
```

**Последний сохранённый результат.** [pc-checks.json](../verification/project-audit/integration/pc-checks.json) · [m32r-link.json](../verification/project-audit/integration/m32r-link.json) · [roundtrip.json](../verification/project-audit/integration/roundtrip.json) · [atf.txt](../verification/project-audit/integration/atf.txt) · [basiccan.json](../verification/project-audit/integration/basiccan.json) · [service.json](../verification/project-audit/integration/service.json) · [phase-wait.json](../verification/project-audit/integration/phase-wait.json) · [package-check.json](../verification/project-audit/integration/package-check.json) · [dtc-table.txt](../verification/project-audit/integration/dtc-table.txt) · [m32r-expanded-link.json](../verification/project-audit/integration/m32r-expanded-link.json) · [can05-roundtrip.txt](../verification/project-audit/integration/can05-roundtrip.txt) · [journal-m32r.txt](../verification/project-audit/integration/journal-m32r.txt)

<a id="check-integration2"></a>
### INTEGRATION2 — Совместная проверка момента, диапазонов и SLU

```powershell
Команды ПК и M32R прежние; дополнительные источники и сохранённые точки входа описаны в docs/working-set.md. Проверка SLU на M32R сохранена как fixture вместе с результатом.
```

**Последний сохранённый результат.** [pc-checks.json](../verification/project-audit/integration-2/pc-checks.json) · [m32r-expanded-link.json](../verification/project-audit/integration-2/m32r-expanded-link.json) · [torque-dialogue.json](../verification/project-audit/integration-2/torque-dialogue.json) · [shift-buttons.json](../verification/project-audit/integration-2/shift-buttons.json) · [slu.json](../verification/project-audit/integration-2/slu.json) · [slu-m32r.txt](../verification/project-audit/integration-2/slu-m32r.txt)

<a id="check-integration3"></a>
### INTEGRATION3 — Общая проверка 31 результата и расширенного состава

```powershell
python -B tools/check_integrated_h03.py --suite native --base $h03 --gcc $m32rGcc --controller local/integration3/controller/rbm_u340e_m32r_be.o --out local/integration3/native
python -B tools/check_integrated_h03.py --suite components --base $h03 --gcc $m32rGcc --controller local/integration3/controller/rbm_u340e_m32r_be.o --out local/integration3/components
--suite expanded с --bridge и --bosch-trace отвергает переполненную компоновку. Границы и повторные проверки после оптимизации: docs/working-set.md.
```

**Последний сохранённый результат.** [pc-checks.json](../verification/project-audit/integration-3/pc-checks.json) · [m32r-link.json](../verification/project-audit/integration-3/m32r-link.json) · [summary.json](../verification/project-audit/integration-3/native/summary.json) · [summary.json](../verification/project-audit/integration-3/components/summary.json) · [summary.json](../verification/project-audit/integration-3/expanded/summary.json) · [unbounded-sizing.json](../verification/project-audit/integration-3/expanded/unbounded-sizing.json) · [final-storage.json](../verification/project-audit/integration-3/final-storage.json) · [final-stack.json](../verification/project-audit/integration-3/final-stack.json) · [torque-dialogue.json](../verification/project-audit/integration-3/torque-dialogue.json)

<a id="check-memory4"></a>
### MEMORY4 — Объединение 13 порций, память и код по конечным адресам

```powershell
python -B tools/check_h03_image_layout.py --base $h03 --gcc $m32rGcc --controller $controller --bridge $bridge --profile prefix-candidate --cpu-test --out $out
# Полный состав отдельно: --profile padding-candidate --with-bindings --storage-report $storageReport
# Ожидается FAIL_BINDINGS до определения платформенных объектов; BIN не создаётся.
```

**Последний сохранённый результат.** [2026-11-20-memory-layout.json](../verification/project-audit/2026-11-20-memory-layout.json) · [summary.json](../verification/project-audit/memory-layout/summary.json)
