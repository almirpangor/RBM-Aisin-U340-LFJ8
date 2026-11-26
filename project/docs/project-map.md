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

Завершено в указанном объёме: **4** · Проверено программно: **9** · Требуется разработка: **18** · Требуются физические данные: **1** · Отложено владельцем: **2**

«Завершено» применяется к узкому объёму карточки. «Проверено программно» не закрывает реализацию на оборудовании. «Требуется разработка» включает независимые программные шаги и их внешние зависимости. Отложенные задачи не входят в первый файл.

## Быстрый список

| Приоритет | ID | Задача | Статус |
| --- | --- | --- | --- |
| 2 | [TOY-01](#toy-01) | Перенос ядра и единое состояние Toyota | Проверено программно |
| 3 | [TOY-02](#toy-02) | Подтверждённая нагрузка двигателя для Toyota | Требуется разработка |
| 4 | [TOY-03](#toy-03) | Независимые разрешающие сигналы диапазона | Требуется разработка |
| 5 | [TOY-04](#toy-04) | Полная последовательность переключений | Требуется разработка |
| 6 | [TOY-05](#toy-05) | Обучение и сохранение адаптаций | Требуется разработка |
| 7 | [TOY-06](#toy-06) | Блокировка гидротрансформатора SLU | Требуется разработка |
| 8 | [CAN-01](#can-01) | Форматы CAN и квалификация RPM/ОЖ | Проверено программно |
| 9 | [CAN-02](#can-02) | Общий диспетчер CAN13 | Проверено программно |
| 10 | [CAN-03](#can-03) | Штатный запуск, IRQ и восстановление CAN0 | Требуется разработка |
| 11 | [CAN-04](#can-04) | Запрос снижения момента по RB | Проверено программно |
| 12 | [CAN-05](#can-05) | Полнота штатного обмена Chery | Требуется разработка |
| 13 | [ECU-01](#ecu-01) | Проверочная сборка Bosch E4M3 | Проверено программно |
| 14 | [ECU-02](#ecu-02) | Калибровка момента и работа двигателя | Требуется разработка |
| 16 | [H03-02](#h03-02) | S51, S83 и температура ATF | Проверено программно |
| 17 | [H03-03](#h03-03) | Единое расписание и запуск приложения H03 | Требуется разработка |
| 18 | [H03-04](#h03-04) | Память, стек и сервисные пути | Требуется разработка |
| 19 | [H03-05](#h03-05) | SLT, силовые выходы и реакция на отказ | Требуется разработка |
| 21 | [VSS-01](#vss-01) | Точный расчёт VSS и скорость по CAN | Проверено программно |
| 22 | [VSS-02](#vss-02) | Кинематика и параметры реальной скорости | Требуется разработка |
| 24 | [MODE-01](#mode-01) | Логика шести положений и кнопок | Проверено программно |
| 25 | [MODE-02](#mode-02) | Подключение селектора, Tiptronic и Overdrive | Требуется разработка |
| 26 | [MODE-03](#mode-03) | Окончательная политика режимов | Требуется разработка |
| 27 | [REL-01](#rel-01) | Два целевых BIN и воспроизводимый комплект | Требуется разработка |
| 28 | [REL-02](#rel-02) | Приёмка новой связки на оборудовании | Требуются физические данные |
| 29 | [DTC-01](#dtc-01) | Прикладной сеанс и статусы Chery | Проверено программно |
| 30 | [DTC-02](#dtc-02) | Штатный приём BasicCAN для диагностического сеанса | Требуется разработка |
| 31 | [DTC-03](#dtc-03) | Все диагностические события и соответствия Toyota/Chery | Требуется разработка |
| 32 | [DTC-04](#dtc-04) | Хранение DTC после выключения питания | Требуется разработка |
| — | [AUD-01](#aud-01) | Программный аудит истории E4M3 | Завершено в указанном объёме |
| — | [H03-01](#h03-01) | Выбранная основа 9E1C и карта подключения | Завершено в указанном объёме |
| — | [ORG-01](#org-01) | Основа проекта и локальная работа | Завершено в указанном объёме |
| — | [SRC-01](#src-01) | Реестр происхождения и контроль исходников | Завершено в указанном объёме |
| — | [IO-01](#io-01) | Два дополнительных реле | Отложено владельцем |
| — | [PANEL-01](#panel-01) | Импульсы Bosch на приборную панель | Отложено владельцем |

<a id="toy-01"></a>
## TOY-01 — Перенос ядра и единое состояние Toyota

**Проверено программно** · ТЗ §2

**Сделано.** Объединённый результат 21.11.2026: Нативный независимый источник Toyota от TML0 включён в H03-мост и проверен через take_toyota, включая пропуск первого события и wrap. 18 стандартных M32R и компоновка прошли в своём объёме. Известные 95394 байта; период, владелец RAM и окончательные привязки остаются открыты.

**Осталось.** Довести полный рабочий цикл и его производителей в TOY-04/H03-03; сокращение таблиц не подтверждает всю программу автомобиля.

**Критерий результата.** Программный результат относится к проверенным функциям, а не ко всем режимам АКПП.

**Код.** [controller/src/rbm_u340e_runtime.c](../controller/src/rbm_u340e_runtime.c) · [controller/src/rbm_u340e_scheduler.c](../controller/src/rbm_u340e_scheduler.c) · [controller/hydraulic_port.py](../controller/hydraulic_port.py) · [controller/vendor/toyota/manifest.json](../controller/vendor/toyota/manifest.json) · [controller/size_port.py](../controller/size_port.py)

**Что настраивать.** Исходные таблицы S01 и контракт controller/include/rbm_u340e_runtime.h.

**Проверки.** [PC](#check-pc) · [M32R](#check-m32r) · [INTEGRATION3](#check-integration3) · [INTEGRATION21](#check-integration21) · [FINAL_INTEGRATION](#check-final_integration)

**Разбор и основания.** [toyota-integration.md](../docs/toyota-integration.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md) · [toy01-gp-descriptor-size.md](../verification/project-audit/toy01-gp-descriptor-size.md) · [bench-first-wave.md](../docs/bench-first-wave.md)

**Следующий шаг для продолжения.** Перепроверь утверждение про 685 байт вне cold-проекции: действительно ли это неизвестные калибровки, или штатные BSS/reset/data/нечитаемые до записи поля? Используй S01/R3 и граф read-before-write, не требуй аппаратный снимок если значения следуют из программы. Доведи rbm_h03_target_startup_gp/gear и реальный initialize_inputs (без захвата транспортных модулей других чатов), init/restore/default paths и явные неподтверждённые поля. Не обнулять неизвестное без доказательства.

**Приоритет продолжения.** 2

**Исходные условия.** main abd3cba и позднее; docs/bench-first-wave.md; data/bench-first-wave.json; имеющиеся источники/проверки карточки.

**Что сдать.** Полное начальное состояние со списком происхождения полей, вызовы cold/warm/restore, дифференциальные прогоны с донором и отсутствие неинициализированных чтений.

**Кому удобно продолжить.** Чат 12 — 01a1fa79-a9fd-70c0-80a3-f59592edaf79. Это рекомендация, не резерв.

**Кто сейчас выполняет.** Проверить [общий список исполнителей](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/tree/task-board). Перед изменениями занять этот ID и точные файлы.

<a id="toy-02"></a>
## TOY-02 — Подтверждённая нагрузка двигателя для Toyota

**Требуется разработка** · ТЗ §2, §3, §4

**Сделано.** Три группы нагрузки требуют квалификации перед GP и планированием; смена epoch отзывает старые данные. Ручной профиль и основной цикл прошли.

**Осталось.** Определить реальные производители GP 9046/8288/8330 и 5299.1 с масштабами/свежестью. Текущие разностные CAN-коды не восстанавливают их однозначно; квалификатор не заменяет источник.

**Критерий результата.** Трасса происхождения каждого операнда, сравнение с S01 и отдельные переходные режимы. Одного TPS и кадров RPM/ОЖ недостаточно.

**Код.** [controller/src/rbm_u340e_runtime.c](../controller/src/rbm_u340e_runtime.c) · [targets/bosch/tx.py](../targets/bosch/tx.py) · [targets/bosch/audit_bosch_signal_transport.py](../targets/bosch/audit_bosch_signal_transport.py) · [targets/bosch/audit_toyota_load_inputs.py](../targets/bosch/audit_toyota_load_inputs.py) · [controller/include/rbm_u340e_runtime.h](../controller/include/rbm_u340e_runtime.h) · [controller/tests/test_runtime.c](../controller/tests/test_runtime.c) · [targets/bosch/audit_toyota_load_producers.py](../targets/bosch/audit_toyota_load_producers.py) · [targets/bosch/audit_toyota_load_traces.py](../targets/bosch/audit_toyota_load_traces.py) · [targets/lfj8/lfj8_h03_cycle.c](../targets/lfj8/lfj8_h03_cycle.c) · [targets/lfj8/lfj8_h03_cycle.h](../targets/lfj8/lfj8_h03_cycle.h) · [targets/lfj8/test_lfj8_h03_cycle.c](../targets/lfj8/test_lfj8_h03_cycle.c) · [targets/lfj8/test_lfj8_h03_cycle_load.c](../targets/lfj8/test_lfj8_h03_cycle_load.c)

**Что настраивать.** GP−8270/−8272/−8306/−8298/−8302/−8310, −9044/−9030, −5299.1 и −5250.2. Тестовые слова не являются настройкой выпуска.

**Проверки.** [SIGNALS](#check-signals) · [M32R](#check-m32r) · [INTEGRATION](#check-integration) · [INTEGRATION3](#check-integration3) · [INTEGRATION21](#check-integration21) · [FINAL_INTEGRATION](#check-final_integration) · [INTEGRATION39](#check-integration39)

**Разбор и основания.** [toyota-integration.md](../docs/toyota-integration.md) · [bosch-integration.md](../docs/bosch-integration.md) · [toy02-load-feed.md](../verification/project-audit/toy02-load-feed.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md) · [toy02-bosch-load-producers.md](../verification/project-audit/toy02-bosch-load-producers.md) · [toy02-load-traces.md](../verification/project-audit/toy02-load-traces.md) · [report.md](../verification/project-audit/integration-39-20261121/report.md) · [bench-first-wave.md](../docs/bench-first-wave.md)

**Следующий шаг для продолжения.** Перепроверь все операнды full Toyota cycle: реальный источник Bosch, шкала, знаковость, возраст, startup и отказ. Если имеющийся CAN несёт только разности и обратное восстановление неоднозначно, не делать ещё один qualifier вокруг той же неопределённости. Подготовь минимальный дополнительный явный raw-source контракт Bosch→TCM с происхождением каждого поля и приёмник; штатный Chery сохранить. Документируй предложения/неизвестные поля, не выдумывать физический load. Самостоятельно подключи доступные producer→capture части и избавь native путь от test_input_capture.

**Приоритет продолжения.** 3

**Исходные условия.** main abd3cba и позднее; docs/bench-first-wave.md; data/bench-first-wave.json; имеющиеся источники/проверки карточки.

**Что сдать.** Таблица всех необходимых операндов и реализованный capture/input backend; контракт для чата 8, реальные source offsets и отрицательные тесты неполного/устаревшего снимка.

**Кому удобно продолжить.** Чат 4 — 01a1f9c7-675a-78c3-be98-5bd65e44995c. Это рекомендация, не резерв.

**Кто сейчас выполняет.** Проверить [общий список исполнителей](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/tree/task-board). Перед изменениями занять этот ID и точные файлы.

<a id="toy-03"></a>
## TOY-03 — Независимые разрешающие сигналы диапазона

**Требуется разработка** · ТЗ §2, §5

**Сделано.** Объединённый результат 21.11.2026: Допуск независимого P/N проверяет AN2, поколения, давность и рассогласование; в снимок идёт старейшая метка. M32R: 1024 AN2, 12 сочетаний P/N, проверки отказа, 5 ADC-сравнений и 8 компонентных групп PASS. Жгут и foreground открыты. Отчёт toy03-independent-pn-qualifier.md.

**Осталось.** Подтвердить физический источник P/N/разрешения пуска и включить квалифицированные диапазоны в общий цикл.

**Критерий результата.** Для каждого бита известны источник, шкала времени и реакция на отказ. Проверка P/N не проверяет сама себя.

**Код.** [targets/lfj8/lfj8_h03_cycle.h](../targets/lfj8/lfj8_h03_cycle.h) · [controller/src/rbm_u340e_runtime.c](../controller/src/rbm_u340e_runtime.c) · [targets/lfj8/check_h03_range_pnp.py](../targets/lfj8/check_h03_range_pnp.py)

**Что настраивать.** Lfj8H03CycleInput.range_5722 и inhibit_5250.

**Проверки.** [M32R](#check-m32r) · [INTEGRATION](#check-integration) · [INTEGRATION3](#check-integration3) · [INTEGRATION21](#check-integration21) · [FINAL_INTEGRATION](#check-final_integration)

**Разбор и основания.** [lfj8-h03-input-paths.md](../docs/lfj8-h03-input-paths.md) · [toyota-integration.md](../docs/toyota-integration.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md) · [toy03-h03-pnp-source.md](../verification/project-audit/toy03-h03-pnp-source.md) · [bench-first-wave.md](../docs/bench-first-wave.md)

**Следующий шаг для продолжения.** Реализуй native context_for_task2 вместо fixture_engine_context, независимые разрешающие сигналы и их происхождение. Параметры age/poll/bit time вывести из кода/регистров/периодики там, где это возможно. Для неподтверждённой временной величины нужен явный инженерный диапазон и контроль в runtime, а не требование получить журнал до BIN. Не восстанавливать неоднозначную абсолютную нагрузку из разностей CAN. Общие CAN owner/RX/DTC уже есть.

**Приоритет продолжения.** 4

**Исходные условия.** main abd3cba и позднее; docs/bench-first-wave.md; data/bench-first-wave.json; имеющиеся источники/проверки карточки.

**Что сдать.** Реальный поставщик и фрагмент профиля со всеми используемыми единицами/метками/таймаутами; replay ошибочного и устаревшего обмена и M32R-сборка.

**Кому удобно продолжить.** Чат 2 — 01a1f9b1-c11a-7b23-abcf-3214ce643805. Это рекомендация, не резерв.

**Кто сейчас выполняет.** Проверить [общий список исполнителей](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/tree/task-board). Перед изменениями занять этот ID и точные файлы.

<a id="toy-04"></a>
## TOY-04 — Полная последовательность переключений

**Требуется разработка** · ТЗ §2, §8

**Сделано.** Объединённый результат 21.11.2026: Ручная цель подключена в MAIN перед защитами Toyota и проходит выдержки, S1/S2 и гидравлику. 41 этап ПК, 120 тестов с отдельной проверкой S03, 18+8 компонентных, 22 нативные и 6 размещённых M32R. Отчёт verification/project-audit/toy04-manual-cycle.md. Открыты источник и срок удержания цели MODE-02/03, целевая привязка H03-03 и аппаратная приёмка; выпуск пары BIN открыт.

**Осталось.** Связать оставшиеся стадии и входы, провести ручные заявки через гидравлику; проверить R, 2→3, 3→4, понижения и защитные переходы целым целевым циклом.

**Критерий результата.** Матрица режимов с ожидаемыми результатами S01 и сквозными трассами. Отдельный тест момента не закрывает всё переключение 2→3.

**Код.** [targets/lfj8/lfj8_h03_cycle.c](../targets/lfj8/lfj8_h03_cycle.c) · [controller/src/rbm_u340e_runtime.c](../controller/src/rbm_u340e_runtime.c) · [controller/tests/test_runtime.c](../controller/tests/test_runtime.c) · [targets/lfj8/test_lfj8_h03_cycle.c](../targets/lfj8/test_lfj8_h03_cycle.c) · [targets/lfj8/lfj8_h03_outputs.c](../targets/lfj8/lfj8_h03_outputs.c)

**Что настраивать.** Раздельные расписания Toyota FAST/SECONDARY/MAIN и H03, начальное состояние GP.

**Проверки.** [PC](#check-pc) · [M32R](#check-m32r) · [NATIVE](#check-native) · [INTEGRATION2](#check-integration2) · [INTEGRATION3](#check-integration3) · [INTEGRATION21](#check-integration21) · [FINAL_INTEGRATION](#check-final_integration)

**Разбор и основания.** [lfj8-h03-control-cycle.md](../docs/lfj8-h03-control-cycle.md) · [toy04-upper-gears.md](../verification/project-audit/toy04-upper-gears.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md) · [toy04-output-flash-size.md](../verification/project-audit/toy04-output-flash-size.md) · [bench-first-wave.md](../docs/bench-first-wave.md)

**Зависит от.** [TOY-02](#toy-02), [TOY-03](#toy-03), [H03-03](#h03-03), [MODE-02](#mode-02)

**Следующий шаг для продолжения.** Доведи реальные native output ops, mapping D/E/F/Pressure A и весь путь command→arbitrate→apply→inhibit. Перепроверь соответствие SLT/SLU и отказов. Нельзя утверждать электрическую изоляцию TIO9 маской без основания. Если конкретное включение требует неизвестного электрического параметра, реализуй диагностическое/комиссионное измерение и явную блокировку именно этого включения; не останавливать запуск/CAN всей системы. Донорские значения с доказуемой применимостью могут быть начальной инженерной настройкой с явно указанными ограничениями, не выдуманной калибровкой давления. Все аппаратные измерения оформить после BIN.

**Приоритет продолжения.** 5

**Исходные условия.** main abd3cba и позднее; docs/bench-first-wave.md; data/bench-first-wave.json; имеющиеся источники/проверки карточки.

**Что сдать.** Реальный output backend/профиль, завершённая программная последовательность переключений и SLU, ограничение непроверенного включения, проверка отзыва каждой команды и минимальный план замеров после сборки.

**Кому удобно продолжить.** Чат 7 — 01a1f9a2-d0ae-78d3-86f1-21b27426fd3f. Это рекомендация, не резерв.

**Кто сейчас выполняет.** Проверить [общий список исполнителей](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/tree/task-board). Перед изменениями занять этот ID и точные файлы.

<a id="toy-05"></a>
## TOY-05 — Обучение и сохранение адаптаций

**Требуется разработка** · ТЗ §2, §5

**Сделано.** Добавлен штатный читатель пары UFL1 в существующее workspace до допуска фаз; проверены rollover, Virtual Flash и повторный старт. Общий код и NVM-модель прошли.

**Осталось.** Выбрать два доказанно свободных блока, реализовать запись и подключить полный startup GP/gear. Только read-only адаптация не завершает постоянное хранение.

**Критерий результата.** Проверены пределы коррекции, повторный пуск, повреждённая запись и сброс адаптаций.

**Код.** [controller/vendor/toyota/src/factory_learning.c](../controller/vendor/toyota/src/factory_learning.c) · [controller/vendor/toyota/src/factory_adaptation_store.c](../controller/vendor/toyota/src/factory_adaptation_store.c) · [controller/tests/test_controller.c](../controller/tests/test_controller.c) · [controller/include/rbm_u340e_runtime.h](../controller/include/rbm_u340e_runtime.h) · [controller/src/rbm_u340e_runtime.c](../controller/src/rbm_u340e_runtime.c) · [targets/lfj8/check_toyota_adaptation_baseline.py](../targets/lfj8/check_toyota_adaptation_baseline.py) · [targets/lfj8/check_toyota_cold_init.py](../targets/lfj8/check_toyota_cold_init.py) · [controller/tests/test_runtime.c](../controller/tests/test_runtime.c) · [targets/lfj8/check_h03_phase_boot.py](../targets/lfj8/check_h03_phase_boot.py) · [targets/lfj8/h03_phase_boot_fixture.c](../targets/lfj8/h03_phase_boot_fixture.c) · [targets/lfj8/lfj8_h03_application.c](../targets/lfj8/lfj8_h03_application.c) · [targets/lfj8/lfj8_h03_application.h](../targets/lfj8/lfj8_h03_application.h) · [targets/lfj8/lfj8_h03_application_binding.c](../targets/lfj8/lfj8_h03_application_binding.c) · [targets/lfj8/lfj8_h03_target_platform.c](../targets/lfj8/lfj8_h03_target_platform.c) · [targets/lfj8/lfj8_h03_target_platform.h](../targets/lfj8/lfj8_h03_target_platform.h) · [targets/lfj8/test_lfj8_h03_target_platform.c](../targets/lfj8/test_lfj8_h03_target_platform.c) · [targets/lfj8/check_h03_nvm.py](../targets/lfj8/check_h03_nvm.py) · [targets/lfj8/h03_nvm_native_fixture.c](../targets/lfj8/h03_nvm_native_fixture.c) · [targets/lfj8/lfj8_h03_cycle.h](../targets/lfj8/lfj8_h03_cycle.h) · [targets/lfj8/lfj8_h03_nvm_native.c](../targets/lfj8/lfj8_h03_nvm_native.c) · [targets/lfj8/lfj8_h03_nvm_native.h](../targets/lfj8/lfj8_h03_nvm_native.h) · [targets/lfj8/lfj8_h03_toyota_nvm_profile.h](../targets/lfj8/lfj8_h03_toyota_nvm_profile.h)

**Что настраивать.** Контракты factory_learning.h и factory_adaptation_store.h. Область NVM ещё не назначена.

**Проверки.** [PC](#check-pc) · [M32R](#check-m32r) · [INTEGRATION2](#check-integration2) · [INTEGRATION3](#check-integration3) · [INTEGRATION21](#check-integration21) · [FINAL_INTEGRATION](#check-final_integration) · [S01_COLD](#check-s01_cold) · [INTEGRATION39](#check-integration39) · [INTEGRATION11](#check-integration11)

**Разбор и основания.** [toyota-integration.md](../docs/toyota-integration.md) · [lfj8-h03-flash.md](../docs/lfj8-h03-flash.md) · [toy05-adaptation-store.md](../verification/project-audit/toy05-adaptation-store.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md) · [toy05-s01-baseline.md](../verification/project-audit/toy05-s01-baseline.md) · [toy05-s01-cold-state.md](../verification/project-audit/toy05-s01-cold-state.md) · [report.md](../verification/project-audit/integration-39-20261121/report.md) · [bench-first-wave.md](../docs/bench-first-wave.md)

**Зависит от.** [TOY-04](#toy-04), [H03-04](#h03-04)

**Следующий шаг для продолжения.** Перепроверь утверждение про 685 байт вне cold-проекции: действительно ли это неизвестные калибровки, или штатные BSS/reset/data/нечитаемые до записи поля? Используй S01/R3 и граф read-before-write, не требуй аппаратный снимок если значения следуют из программы. Доведи rbm_h03_target_startup_gp/gear и реальный initialize_inputs (без захвата транспортных модулей других чатов), init/restore/default paths и явные неподтверждённые поля. Не обнулять неизвестное без доказательства.

**Приоритет продолжения.** 6

**Исходные условия.** main abd3cba и позднее; docs/bench-first-wave.md; data/bench-first-wave.json; имеющиеся источники/проверки карточки.

**Что сдать.** Полное начальное состояние со списком происхождения полей, вызовы cold/warm/restore, дифференциальные прогоны с донором и отсутствие неинициализированных чтений.

**Кому удобно продолжить.** Чат 12 — 01a1fa79-a9fd-70c0-80a3-f59592edaf79. Это рекомендация, не резерв.

**Кто сейчас выполняет.** Проверить [общий список исполнителей](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/tree/task-board). Перед изменениями занять этот ID и точные файлы.

<a id="toy-06"></a>
## TOY-06 — Блокировка гидротрансформатора SLU

**Требуется разработка** · ТЗ §2, §5

**Сделано.** Объединённый результат 21.11.2026: 18 штатных сценариев M32R: Shift E/P31 (Mazda TCC 1H) отключается при общем inhibit и P0773, а TIO9/P97 сохраняет PWM. Проверены штатные входы ATF/питания и пороги TIO9. Повторены 6 сценариев арбитра и 59 мониторов. Для Toyota SLU открыты физический канал, отдельное отключение, калибровка и полный снимок. Отчёт toy06-h03-slu-output-paths.md.

**Осталось.** Подключить полный целевой снимок и физический канал SLU; установить масштабы и проверить удержание/снятие блокировки.

**Критерий результата.** Трасса от квалифицированных входов до канала H03, проверка скольжения, удержания и снятия по отказу.

**Код.** [targets/lfj8/check_toyota_slu.py](../targets/lfj8/check_toyota_slu.py) · [targets/lfj8/lfj8_h03_cycle.c](../targets/lfj8/lfj8_h03_cycle.c) · [targets/lfj8/lfj8_h03_outputs.h](../targets/lfj8/lfj8_h03_outputs.h) · [targets/lfj8/lfj8_h03_slu.c](../targets/lfj8/lfj8_h03_slu.c) · [targets/lfj8/lfj8_h03_slu.h](../targets/lfj8/lfj8_h03_slu.h) · [targets/lfj8/test_lfj8_h03_cycle.c](../targets/lfj8/test_lfj8_h03_cycle.c)

**Что настраивать.** Целевой адаптер SLU ещё отсутствует. Результат сравнения регистров Toyota не задаёт ток канала H03.

**Проверки.** [SLU](#check-slu) · [INTEGRATION2](#check-integration2) · [INTEGRATION3](#check-integration3) · [MEMORY4](#check-memory4) · [INTEGRATION21](#check-integration21) · [FINAL_INTEGRATION](#check-final_integration)

**Разбор и основания.** [toyota-integration.md](../docs/toyota-integration.md) · [lfj8-9e1c-minimum-bench.md](../docs/lfj8-9e1c-minimum-bench.md) · [toy06-slu-command.md](../verification/project-audit/toy06-slu-command.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md) · [lfj8-h03-memory-layout.md](../docs/lfj8-h03-memory-layout.md) · [toy06-slu-stage-boundaries.md](../verification/project-audit/toy06-slu-stage-boundaries.md) · [bench-first-wave.md](../docs/bench-first-wave.md)

**Зависит от.** [TOY-02](#toy-02), [H03-05](#h03-05)

**Следующий шаг для продолжения.** Доведи реальные native output ops, mapping D/E/F/Pressure A и весь путь command→arbitrate→apply→inhibit. Перепроверь соответствие SLT/SLU и отказов. Нельзя утверждать электрическую изоляцию TIO9 маской без основания. Если конкретное включение требует неизвестного электрического параметра, реализуй диагностическое/комиссионное измерение и явную блокировку именно этого включения; не останавливать запуск/CAN всей системы. Донорские значения с доказуемой применимостью могут быть начальной инженерной настройкой с явно указанными ограничениями, не выдуманной калибровкой давления. Все аппаратные измерения оформить после BIN.

**Приоритет продолжения.** 7

**Исходные условия.** main abd3cba и позднее; docs/bench-first-wave.md; data/bench-first-wave.json; имеющиеся источники/проверки карточки.

**Что сдать.** Реальный output backend/профиль, завершённая программная последовательность переключений и SLU, ограничение непроверенного включения, проверка отзыва каждой команды и минимальный план замеров после сборки.

**Кому удобно продолжить.** Чат 7 — 01a1f9a2-d0ae-78d3-86f1-21b27426fd3f. Это рекомендация, не резерв.

**Кто сейчас выполняет.** Проверить [общий список исполнителей](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/tree/task-board). Перед изменениями занять этот ID и точные файлы.

<a id="can-01"></a>
## CAN-01 — Форматы CAN и квалификация RPM/ОЖ

**Проверено программно** · ТЗ §3

**Сделано.** Реальный дескриптор target_engine включается явным профилем и использует единые engine_rx/qualifier/DTC/CAN owner/TML0. Нативные тесты и свежий обмен с Bosch прошли.

**Осталось.** Задать подтверждённые границы времени и реальный Task 2 context с retained_fd10/fallback_fa7b/retained_e026/e02b и старейшей меткой. В общей пробе внешний fixture_engine_context остаётся неопределённым.

**Критерий результата.** Результат ограничен перечисленными полями и сценариями приёма.

**Код.** [targets/lfj8/ta2005_chery_inputs.c](../targets/lfj8/ta2005_chery_inputs.c) · [targets/lfj8/ta2005_engine_qualifier.c](../targets/lfj8/ta2005_engine_qualifier.c) · [targets/lfj8/lfj8_h03_engine_feed.c](../targets/lfj8/lfj8_h03_engine_feed.c) · [targets/lfj8/lfj8_chery_tx.c](../targets/lfj8/lfj8_chery_tx.c) · [targets/lfj8/lfj8_h03_engine_feed.h](../targets/lfj8/lfj8_h03_engine_feed.h) · [targets/lfj8/lfj8_h03_engine_rx.c](../targets/lfj8/lfj8_h03_engine_rx.c) · [targets/lfj8/lfj8_h03_engine_rx.h](../targets/lfj8/lfj8_h03_engine_rx.h) · [targets/lfj8/test_lfj8_h03_engine_feed.c](../targets/lfj8/test_lfj8_h03_engine_feed.c) · [targets/lfj8/h03_phase_boot_fixture.c](../targets/lfj8/h03_phase_boot_fixture.c) · [targets/lfj8/lfj8_h03_application.c](../targets/lfj8/lfj8_h03_application.c) · [targets/lfj8/lfj8_h03_application.h](../targets/lfj8/lfj8_h03_application.h) · [targets/lfj8/check_h03_can_monitor_revoke.py](../targets/lfj8/check_h03_can_monitor_revoke.py) · [targets/lfj8/lfj8_h03_application_binding.c](../targets/lfj8/lfj8_h03_application_binding.c) · [targets/lfj8/lfj8_h03_can_service_placement.py](../targets/lfj8/lfj8_h03_can_service_placement.py)

**Что настраивать.** Возраст кадра, поколение CAN, период task2 и разрешение записи истории.

**Проверки.** [PC](#check-pc) · [M32R](#check-m32r) · [BOSCH](#check-bosch) · [INTEGRATION](#check-integration) · [INTEGRATION3](#check-integration3) · [INTEGRATION21](#check-integration21) · [FINAL_INTEGRATION](#check-final_integration) · [INTEGRATION39](#check-integration39) · [INTEGRATION11](#check-integration11)

**Разбор и основания.** [chery-can-dtc.md](../docs/chery-can-dtc.md) · [toyota-integration.md](../docs/toyota-integration.md) · [can01-rx-epoch.md](../verification/project-audit/can01-rx-epoch.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md) · [can01-engine-rx-generation.md](../verification/project-audit/can01-engine-rx-generation.md) · [report.md](../verification/project-audit/integration-39-20261121/report.md) · [bench-first-wave.md](../docs/bench-first-wave.md)

**Следующий шаг для продолжения.** Реализуй native context_for_task2 вместо fixture_engine_context, независимые разрешающие сигналы и их происхождение. Параметры age/poll/bit time вывести из кода/регистров/периодики там, где это возможно. Для неподтверждённой временной величины нужен явный инженерный диапазон и контроль в runtime, а не требование получить журнал до BIN. Не восстанавливать неоднозначную абсолютную нагрузку из разностей CAN. Общие CAN owner/RX/DTC уже есть.

**Приоритет продолжения.** 8

**Исходные условия.** main abd3cba и позднее; docs/bench-first-wave.md; data/bench-first-wave.json; имеющиеся источники/проверки карточки.

**Что сдать.** Реальный поставщик и фрагмент профиля со всеми используемыми единицами/метками/таймаутами; replay ошибочного и устаревшего обмена и M32R-сборка.

**Кому удобно продолжить.** Чат 2 — 01a1f9b1-c11a-7b23-abcf-3214ce643805. Это рекомендация, не резерв.

**Кто сейчас выполняет.** Проверить [общий список исполнителей](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/tree/task-board). Перед изменениями занять этот ID и точные файлы.

<a id="can-02"></a>
## CAN-02 — Общий диспетчер CAN13

**Проверено программно** · ТЗ §3

**Сделано.** При отсутствии калибровки S51 передаётся недоступная скорость 0xFFFF в 0x1AE, а ATF 0x300 сохраняется; общая модель обмена прошла.

**Осталось.** Подключить окончательный vehicle/torque/status профиль и проверить полноценный обмен совместно с CAN-03/CAN-04/CAN-05.

**Критерий результата.** Программные тесты не заменяют измерение окон приёма 0x5E9.

**Код.** [targets/lfj8/lfj8_h03_can13.c](../targets/lfj8/lfj8_h03_can13.c) · [targets/lfj8/lfj8_h03_torque_can.c](../targets/lfj8/lfj8_h03_torque_can.c) · [targets/lfj8/lfj8_h03_dtc_can.c](../targets/lfj8/lfj8_h03_dtc_can.c) · [targets/lfj8/test_lfj8_h03_can13.c](../targets/lfj8/test_lfj8_h03_can13.c) · [targets/lfj8/lfj8_h03_can13.h](../targets/lfj8/lfj8_h03_can13.h) · [targets/lfj8/lfj8_h03_target_service.c](../targets/lfj8/lfj8_h03_target_service.c) · [targets/lfj8/lfj8_h03_target_service.h](../targets/lfj8/lfj8_h03_target_service.h)

**Что настраивать.** Lfj8H03Can13, предел опроса, лимиты возраста и повторная инициализация.

**Проверки.** [PC](#check-pc) · [M32R](#check-m32r) · [INTEGRATION2](#check-integration2) · [INTEGRATION3](#check-integration3) · [MEMORY4](#check-memory4) · [INTEGRATION21](#check-integration21) · [FINAL_INTEGRATION](#check-final_integration) · [INTEGRATION39](#check-integration39)

**Разбор и основания.** [lfj8-h03-torque.md](../docs/lfj8-h03-torque.md) · [can02-loan-timeout.md](../verification/project-audit/can02-loan-timeout.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md) · [lfj8-h03-memory-layout.md](../docs/lfj8-h03-memory-layout.md) · [can02-torque-submit.md](../verification/project-audit/can02-torque-submit.md) · [report.md](../verification/project-audit/integration-39-20261121/report.md) · [bench-first-wave.md](../docs/bench-first-wave.md)

**Следующий шаг для продолжения.** Доведи реальный Lfj8H03TargetServiceConfig, источник времени, сбор T6/status и отправку момента/диагностики через единственный TX13. START/REFRESH/ACK/CANCEL, шедулинг, bus-off, monitor, reset и смена поколения должны иметь реальные входы/выходы. Убери зависимость от test_can_service_config. Полнота CAN включает обратную связь и завершение запросов, а не только RPM/ОЖ.

**Приоритет продолжения.** 9

**Исходные условия.** main abd3cba и позднее; docs/bench-first-wave.md; data/bench-first-wave.json; имеющиеся источники/проверки карточки.

**Что сдать.** Native CAN service profile/config с производителями статуса/момента и точками вызова; двусторонний сценарий и отказные проверки, точные Flash/RAM.

**Кому удобно продолжить.** Чат 3 — 01a1f9b5-5d41-79e0-8cd2-3dadc922f1ce. Это рекомендация, не резерв.

**Кто сейчас выполняет.** Проверить [общий список исполнителей](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/tree/task-board). Перед изменениями занять этот ID и точные файлы.

<a id="can-03"></a>
## CAN-03 — Штатный запуск, IRQ и восстановление CAN0

**Требуется разработка** · ТЗ §3, §5

**Сделано.** Общий T6 задаёт расписание S03 4/12; пять некорректных сервисных профилей отвергаются до допуска фаз. Исправлена совместимость CAN13 status_due; общий CAN прошёл.

**Осталось.** Подключить действительный service config, status/torque источники и квалифицированные временные пределы; закончить monitor-переходы.

**Критерий результата.** Штатная ветвь не перезаписывает CAN13, старые кадры не принимаются после сброса, сохранена диагностика и отмена.

**Код.** [targets/lfj8/check_h03_can_lifecycle.py](../targets/lfj8/check_h03_can_lifecycle.py) · [targets/lfj8/check_h03_torque_tx_gate.py](../targets/lfj8/check_h03_torque_tx_gate.py) · [targets/lfj8/lfj8_h03_can13.c](../targets/lfj8/lfj8_h03_can13.c) · [targets/lfj8/lfj8_donor_io.c](../targets/lfj8/lfj8_donor_io.c) · [targets/lfj8/lfj8_h03_can_owner.c](../targets/lfj8/lfj8_h03_can_owner.c) · [targets/lfj8/lfj8_h03_can_owner.h](../targets/lfj8/lfj8_h03_can_owner.h) · [targets/lfj8/check_h03_can_monitor_startup.py](../targets/lfj8/check_h03_can_monitor_startup.py) · [targets/lfj8/h03_can_monitor_startup_hooks.S](../targets/lfj8/h03_can_monitor_startup_hooks.S) · [targets/lfj8/lfj8_h03_can_monitor_startup.c](../targets/lfj8/lfj8_h03_can_monitor_startup.c) · [targets/lfj8/lfj8_h03_can_monitor_startup.h](../targets/lfj8/lfj8_h03_can_monitor_startup.h) · [targets/lfj8/check_h03_can_monitor_revoke.py](../targets/lfj8/check_h03_can_monitor_revoke.py) · [targets/lfj8/lfj8_h03_storage.h](../targets/lfj8/lfj8_h03_storage.h) · [targets/lfj8/lfj8_h03_target_service.c](../targets/lfj8/lfj8_h03_target_service.c) · [targets/lfj8/lfj8_h03_target_service.h](../targets/lfj8/lfj8_h03_target_service.h) · [targets/lfj8/check_h03_target_platform.py](../targets/lfj8/check_h03_target_platform.py) · [targets/lfj8/h03_application_binding_fixture.c](../targets/lfj8/h03_application_binding_fixture.c) · [targets/lfj8/lfj8_h03_application.c](../targets/lfj8/lfj8_h03_application.c) · [targets/lfj8/lfj8_h03_application.h](../targets/lfj8/lfj8_h03_application.h) · [targets/lfj8/lfj8_h03_application_binding.c](../targets/lfj8/lfj8_h03_application_binding.c) · [targets/lfj8/lfj8_h03_target_platform.c](../targets/lfj8/lfj8_h03_target_platform.c) · [targets/lfj8/lfj8_h03_target_platform.h](../targets/lfj8/lfj8_h03_target_platform.h) · [targets/lfj8/test_lfj8_h03_target_platform.c](../targets/lfj8/test_lfj8_h03_target_platform.c) · [targets/lfj8/h03_can13_tx_gate.S](../targets/lfj8/h03_can13_tx_gate.S) · [targets/lfj8/h03_torque_tx_gate_fixture.S](../targets/lfj8/h03_torque_tx_gate_fixture.S) · [targets/lfj8/lfj8_donor_io.h](../targets/lfj8/lfj8_donor_io.h) · [targets/lfj8/lfj8_h03_can_monitor_revoke.c](../targets/lfj8/lfj8_h03_can_monitor_revoke.c) · [targets/lfj8/test_lfj8_h03_can_owner.c](../targets/lfj8/test_lfj8_h03_can_owner.c) · [targets/lfj8/h03_can13_tx_redirect.S](../targets/lfj8/h03_can13_tx_redirect.S) · [targets/lfj8/lfj8_h03_tx13_placement.py](../targets/lfj8/lfj8_h03_tx13_placement.py) · [targets/lfj8/check_h03_dtc_basiccan.py](../targets/lfj8/check_h03_dtc_basiccan.py) · [targets/lfj8/h03_dtc_rx_hook_fixture.c](../targets/lfj8/h03_dtc_rx_hook_fixture.c) · [targets/lfj8/lfj8_h03_can13.h](../targets/lfj8/lfj8_h03_can13.h) · [targets/lfj8/lfj8_h03_dtc_native.c](../targets/lfj8/lfj8_h03_dtc_native.c) · [targets/lfj8/lfj8_h03_dtc_native.h](../targets/lfj8/lfj8_h03_dtc_native.h) · [targets/lfj8/lfj8_h03_dtc_target.c](../targets/lfj8/lfj8_h03_dtc_target.c) · [targets/lfj8/lfj8_h03_dtc_target.h](../targets/lfj8/lfj8_h03_dtc_target.h) · [targets/lfj8/test_lfj8_h03_can13.c](../targets/lfj8/test_lfj8_h03_can13.c)

**Что настраивать.** CAN0SLIMK/SLIST, флаг владельца, поколение, RX11/12 и TX/RX13.

**Проверки.** [M32R](#check-m32r) · [INTEGRATION](#check-integration) · [INTEGRATION3](#check-integration3) · [MEMORY4](#check-memory4) · [INTEGRATION21](#check-integration21) · [FINAL_INTEGRATION](#check-final_integration) · [INTEGRATION39](#check-integration39) · [INTEGRATION11](#check-integration11)

**Разбор и основания.** [lfj8-9e1c-base.md](../docs/lfj8-9e1c-base.md) · [lfj8-h03-torque.md](../docs/lfj8-h03-torque.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md) · [lfj8-h03-memory-layout.md](../docs/lfj8-h03-memory-layout.md) · [can03-h03-monitor-startup.md](../verification/project-audit/can03-h03-monitor-startup.md) · [report.md](../verification/project-audit/integration-39-20261121/report.md) · [bench-first-wave.md](../docs/bench-first-wave.md)

**Зависит от.** [H03-04](#h03-04)

**Следующий шаг для продолжения.** Доведи реальный Lfj8H03TargetServiceConfig, источник времени, сбор T6/status и отправку момента/диагностики через единственный TX13. START/REFRESH/ACK/CANCEL, шедулинг, bus-off, monitor, reset и смена поколения должны иметь реальные входы/выходы. Убери зависимость от test_can_service_config. Полнота CAN включает обратную связь и завершение запросов, а не только RPM/ОЖ.

**Приоритет продолжения.** 10

**Исходные условия.** main abd3cba и позднее; docs/bench-first-wave.md; data/bench-first-wave.json; имеющиеся источники/проверки карточки.

**Что сдать.** Native CAN service profile/config с производителями статуса/момента и точками вызова; двусторонний сценарий и отказные проверки, точные Flash/RAM.

**Кому удобно продолжить.** Чат 3 — 01a1f9b5-5d41-79e0-8cd2-3dadc922f1ce. Это рекомендация, не резерв.

**Кто сейчас выполняет.** Проверить [общий список исполнителей](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/tree/task-board). Перед изменениями занять этот ID и точные файлы.

<a id="can-04"></a>
## CAN-04 — Запрос снижения момента по RB

**Проверено программно** · ТЗ §3, §4

**Сделано.** Объединённый результат 21.11.2026: CAN13 отзывает ожидающий RB START/REFRESH на текущем опросе при потере допуска или истечении метки; CANCEL и подтверждение TRFIN сохраняются. Регрессия ПК, 18 групп M32R, 6 проверок размещения и оба диалога Bosch прошли. Физический профиль остаётся открытым. Отчёт: verification/project-audit/can04-pending-tx-revoke.md.

**Осталось.** Подключить реальные временные метки и подтверждённый профиль снижения момента; измерить его действие в целевой паре.

**Критерий результата.** Протокол 0x5E8/0x5E9 является RB. Его успешный тест не означает полного штатного Chery CAN.

**Код.** [targets/lfj8/lfj8_h03_torque.c](../targets/lfj8/lfj8_h03_torque.c) · [targets/lfj8/verify_h03_torque.py](../targets/lfj8/verify_h03_torque.py) · [targets/bosch/replay_e4m3_torque.py](../targets/bosch/replay_e4m3_torque.py) · [targets/lfj8/lfj8_h03_torque.h](../targets/lfj8/lfj8_h03_torque.h) · [targets/lfj8/test_lfj8_h03_torque.c](../targets/lfj8/test_lfj8_h03_torque.c)

**Что настраивать.** Lfj8TorqueCalibration.up/down, levels, reduction_q8, duration. 32/256 и 200 мс в тесте — испытательный профиль.

**Проверки.** [PC](#check-pc) · [M32R](#check-m32r) · [TORQUE](#check-torque) · [INTEGRATION2](#check-integration2) · [INTEGRATION3](#check-integration3) · [INTEGRATION21](#check-integration21) · [FINAL_INTEGRATION](#check-final_integration)

**Разбор и основания.** [lfj8-h03-torque.md](../docs/lfj8-h03-torque.md) · [can04-torque-revocation.md](../verification/project-audit/can04-torque-revocation.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md) · [can04-progress-deadline.md](../verification/project-audit/can04-progress-deadline.md) · [bench-first-wave.md](../docs/bench-first-wave.md)

**Следующий шаг для продолжения.** Доведи реальный Lfj8H03TargetServiceConfig, источник времени, сбор T6/status и отправку момента/диагностики через единственный TX13. START/REFRESH/ACK/CANCEL, шедулинг, bus-off, monitor, reset и смена поколения должны иметь реальные входы/выходы. Убери зависимость от test_can_service_config. Полнота CAN включает обратную связь и завершение запросов, а не только RPM/ОЖ.

**Приоритет продолжения.** 11

**Исходные условия.** main abd3cba и позднее; docs/bench-first-wave.md; data/bench-first-wave.json; имеющиеся источники/проверки карточки.

**Что сдать.** Native CAN service profile/config с производителями статуса/момента и точками вызова; двусторонний сценарий и отказные проверки, точные Flash/RAM.

**Кому удобно продолжить.** Чат 3 — 01a1f9b5-5d41-79e0-8cd2-3dadc922f1ce. Это рекомендация, не резерв.

**Кто сейчас выполняет.** Проверить [общий список исполнителей](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/tree/task-board). Перед изменениями занять этот ID и точные файлы.

<a id="can-05"></a>
## CAN-05 — Полнота штатного обмена Chery

**Требуется разработка** · ТЗ §3, §4

**Сделано.** Объединённый результат 21.11.2026: Реальный профиль Bosch включает чтение T4 до пустого опроса 0x1AE, проверку после IF1 и отзыв скорости. Два варианта ST10/C_CAN прошли 26 групп каждый и 51 запись целостности. Проверены RB, 12 прежних сборок, 41 этап ПК и 120 тестов с отдельным повтором S03. Открыты RAM и публикация поколения, потребитель момента, измеренный lease_ticks и ECU-02. Отчёт can05-st10-bound-t4.md.

**Осталось.** Профили с нативным T4/IF1 уже собираются и проверены на ST10. Для выпуска остаются фактическая RAM и поколение, срок lease_ticks, соединение с потребителем/арбитражем ECU-02 и проверка интервалов под нагрузкой.

**Критерий результата.** Для каждого требуемого поля есть источник, единицы, период, недостоверность и проверенный потребитель. Замена штатного протокола отдельным RB не считается закрытием §3.

**Код.** [targets/lfj8/lfj8_bridge.h](../targets/lfj8/lfj8_bridge.h) · [targets/lfj8/lfj8_chery_tx.c](../targets/lfj8/lfj8_chery_tx.c) · [targets/bosch/chery_torque_rx.c](../targets/bosch/chery_torque_rx.c) · [targets/bosch/tx.py](../targets/bosch/tx.py) · [targets/bosch/test_chery_1ae_roundtrip.c](../targets/bosch/test_chery_1ae_roundtrip.c) · [tests/test_chery_1ae_roundtrip.py](../tests/test_chery_1ae_roundtrip.py) · [targets/bosch/audit_chery_rx_clock.py](../targets/bosch/audit_chery_rx_clock.py)

**Что настраивать.** Lfj8Chery1ae.byte1/byte3_high/byte4 и флаги. Не заполнять неизвестные поля правдоподобными константами.

**Проверки.** [PC](#check-pc) · [BOSCH](#check-bosch) · [INTEGRATION](#check-integration) · [INTEGRATION3](#check-integration3) · [MEMORY4](#check-memory4) · [INTEGRATION21](#check-integration21) · [FINAL_INTEGRATION](#check-final_integration)

**Разбор и основания.** [chery-can-dtc.md](../docs/chery-can-dtc.md) · [bosch-integration.md](../docs/bosch-integration.md) · [can05-1ae-roundtrip.md](../verification/project-audit/can05-1ae-roundtrip.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md) · [lfj8-h03-memory-layout.md](../docs/lfj8-h03-memory-layout.md) · [can05-st10-rx-clock.md](../verification/project-audit/can05-st10-rx-clock.md) · [bench-first-wave.md](../docs/bench-first-wave.md)

**Зависит от.** [TOY-02](#toy-02)

**Следующий шаг для продолжения.** Назначен владельцем целевого Bosch BIN. Полностью перепроверь ordinary/no-cruise OFFLINE_ONLY, причины ограничения, hooks, checksum и сохранение старта/впрыска/зажигания. Доделай реальные штатные Chery кадры и RB torque request/reply/cancel плюс требуемые Toyota operands. Чат 4 готовит таблицу исходных операндов и приёмник: совместимость через проверяемый контракт, не подстановку физических значений. Раздели реальные препятствия к первому стендовому образу от моторной калибровки после прошивки. Нельзя просто переименовать bd0afefa… в READY.

**Приоритет продолжения.** 12

**Исходные условия.** main abd3cba и позднее; docs/bench-first-wave.md; data/bench-first-wave.json; имеющиеся источники/проверки карточки.

**Что сдать.** Воспроизводимый Bosch BIN для стендовой проверки только при наличии всех необходимых программных доказательств, либо точная реально неустранимая причина; source/final SHA, map diff, native integrity, CPU paths и ограничения. Аппаратные проверки честно false.

**Кому удобно продолжить.** Чат 8 — 01a1f9ab-19c7-72c0-ac90-6aa98e4aa488. Это рекомендация, не резерв.

**Кто сейчас выполняет.** Проверить [общий список исполнителей](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/tree/task-board). Перед изменениями занять этот ID и точные файлы.

<a id="ecu-01"></a>
## ECU-01 — Проверочная сборка Bosch E4M3

**Проверено программно** · ТЗ §4

**Сделано.** Повторно собран Bosch ordinary/no-cruise/no-override OFFLINE_ONLY; проверены целостность, 65536 native encoder cases и обмен с текущим TCM-кодом. SHA и результаты в INTEGRATION39.

**Осталось.** Завершить CAN-05/ECU-02, собрать согласованный целевой профиль и проверить происхождение обоих итоговых образов.

**Критерий результата.** Это образ OFFLINE_ONLY, сохранение всех функций двигателя на машине не подтверждено.

**Код.** [targets/bosch/build.py](../targets/bosch/build.py) · [targets/bosch/tx.py](../targets/bosch/tx.py) · [targets/bosch/compact_branches.py](../targets/bosch/compact_branches.py) · [tests/test_bosch_build_integrity.py](../tests/test_bosch_build_integrity.py)

**Что настраивать.** Опции with-model-fields, with-ordinary-model-field и compact. Профиль cruise=false/override=false явно ограничен.

**Проверки.** [BOSCH](#check-bosch) · [INTEGRATION3](#check-integration3) · [INTEGRATION21](#check-integration21) · [FINAL_INTEGRATION](#check-final_integration) · [INTEGRATION39](#check-integration39)

**Разбор и основания.** [bosch-integration.md](../docs/bosch-integration.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md) · [ecu01-bosch-section-layout.md](../verification/project-audit/ecu01-bosch-section-layout.md) · [bench-first-wave.md](../docs/bench-first-wave.md)

**Следующий шаг для продолжения.** Назначен владельцем целевого Bosch BIN. Полностью перепроверь ordinary/no-cruise OFFLINE_ONLY, причины ограничения, hooks, checksum и сохранение старта/впрыска/зажигания. Доделай реальные штатные Chery кадры и RB torque request/reply/cancel плюс требуемые Toyota operands. Чат 4 готовит таблицу исходных операндов и приёмник: совместимость через проверяемый контракт, не подстановку физических значений. Раздели реальные препятствия к первому стендовому образу от моторной калибровки после прошивки. Нельзя просто переименовать bd0afefa… в READY.

**Приоритет продолжения.** 13

**Исходные условия.** main abd3cba и позднее; docs/bench-first-wave.md; data/bench-first-wave.json; имеющиеся источники/проверки карточки.

**Что сдать.** Воспроизводимый Bosch BIN для стендовой проверки только при наличии всех необходимых программных доказательств, либо точная реально неустранимая причина; source/final SHA, map diff, native integrity, CPU paths и ограничения. Аппаратные проверки честно false.

**Кому удобно продолжить.** Чат 8 — 01a1f9ab-19c7-72c0-ac90-6aa98e4aa488. Это рекомендация, не резерв.

**Кто сейчас выполняет.** Проверить [общий список исполнителей](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/tree/task-board). Перед изменениями занять этот ID и точные файлы.

<a id="ecu-02"></a>
## ECU-02 — Калибровка момента и работа двигателя

**Требуется разработка** · ТЗ §4, §10

**Сделано.** Объединённый результат 21.11.2026: Приёмник C отклоняет 0x1AE с меткой на границе снятия допуска и раньше. Подтверждено для прямого/отложенного RX, очереди и переполнения T4. ПК 41/120, 65536 пар, старый Bosch ST10 с 51 записью, три диалога H03 и 26 архивных запросов. Машинная привязка CAN-05 и стенд открыты. Отчёт ecu02-torque-permit-boundary.md.

**Осталось.** Завершить машинный арбитраж с квалифицированными входами и подтвердить действие/снятие момента на новой паре блоков.

**Критерий результата.** Протокол с идентифицированными BIN и измеренным результатом. Исторический стенд STM32 не переносит автоматически приёмку на LFJ8.

**Код.** [targets/lfj8/lfj8_h03_torque.h](../targets/lfj8/lfj8_h03_torque.h) · [targets/bosch/chery_torque_rx.c](../targets/bosch/chery_torque_rx.c) · [targets/bosch/verify_e4m3_torque_rpm.py](../targets/bosch/verify_e4m3_torque_rpm.py)

**Что настраивать.** Шесть профилей up/down в Lfj8TorqueCalibration и применимость E4M3 к конкретному ЭБУ.

**Проверки.** [TORQUE](#check-torque) · [E4AUDIT](#check-e4audit) · [INTEGRATION3](#check-integration3) · [INTEGRATION21](#check-integration21) · [FINAL_INTEGRATION](#check-final_integration)

**Разбор и основания.** [e4m3-audit.md](../docs/e4m3-audit.md) · [lfj8-9e1c-minimum-bench.md](../docs/lfj8-9e1c-minimum-bench.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md) · [ecu02-rb-lease-timeout.md](../verification/project-audit/ecu02-rb-lease-timeout.md) · [bench-first-wave.md](../docs/bench-first-wave.md)

**Зависит от.** [CAN-05](#can-05)

**Следующий шаг для продолжения.** Назначен владельцем целевого Bosch BIN. Полностью перепроверь ordinary/no-cruise OFFLINE_ONLY, причины ограничения, hooks, checksum и сохранение старта/впрыска/зажигания. Доделай реальные штатные Chery кадры и RB torque request/reply/cancel плюс требуемые Toyota operands. Чат 4 готовит таблицу исходных операндов и приёмник: совместимость через проверяемый контракт, не подстановку физических значений. Раздели реальные препятствия к первому стендовому образу от моторной калибровки после прошивки. Нельзя просто переименовать bd0afefa… в READY.

**Приоритет продолжения.** 14

**Исходные условия.** main abd3cba и позднее; docs/bench-first-wave.md; data/bench-first-wave.json; имеющиеся источники/проверки карточки.

**Что сдать.** Воспроизводимый Bosch BIN для стендовой проверки только при наличии всех необходимых программных доказательств, либо точная реально неустранимая причина; source/final SHA, map diff, native integrity, CPU paths и ограничения. Аппаратные проверки честно false.

**Кому удобно продолжить.** Чат 8 — 01a1f9ab-19c7-72c0-ac90-6aa98e4aa488. Это рекомендация, не резерв.

**Кто сейчас выполняет.** Проверить [общий список исполнителей](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/tree/task-board). Перед изменениями занять этот ID и точные файлы.

<a id="h03-02"></a>
## H03-02 — S51, S83 и температура ATF

**Проверено программно** · ТЗ §5, §7

**Сделано.** Захват датчиков использует время конца чтения; проверены перенос счётчика, задержка и допуск ATF по квалифицированным часам.

**Осталось.** Подключить реальные sensor_config, частоту, периоды и допуски из VSS-02; выполнить квалификацию S51/S83/ATF в общем цикле.

**Критерий результата.** Компоненты не подменяют окончательную установку обработчиков в BIN.

**Код.** [targets/lfj8/lfj8_donor_io.c](../targets/lfj8/lfj8_donor_io.c) · [targets/lfj8/lfj8_gear_observer.c](../targets/lfj8/lfj8_gear_observer.c) · [targets/lfj8/lfj8_h03_atf.c](../targets/lfj8/lfj8_h03_atf.c) · [targets/lfj8/lfj8_h03_atf_target.c](../targets/lfj8/lfj8_h03_atf_target.c) · [targets/lfj8/lfj8_h03_atf_target.h](../targets/lfj8/lfj8_h03_atf_target.h) · [targets/lfj8/h03_atf_hooks.S](../targets/lfj8/h03_atf_hooks.S) · [targets/lfj8/check_h03_atf_native.py](../targets/lfj8/check_h03_atf_native.py) · [targets/lfj8/lfj8_h03_sensor_target.c](../targets/lfj8/lfj8_h03_sensor_target.c) · [targets/lfj8/h03_sensor_hooks.S](../targets/lfj8/h03_sensor_hooks.S) · [targets/lfj8/check_h03_sensor_native.py](../targets/lfj8/check_h03_sensor_native.py) · [targets/lfj8/h03_atf_hook_fixture.c](../targets/lfj8/h03_atf_hook_fixture.c) · [targets/lfj8/h03_sensor_hook_fixture.c](../targets/lfj8/h03_sensor_hook_fixture.c) · [targets/lfj8/lfj8_h03_atf_tml0.c](../targets/lfj8/lfj8_h03_atf_tml0.c) · [targets/lfj8/host_check.c](../targets/lfj8/host_check.c) · [targets/lfj8/lfj8_donor_io.h](../targets/lfj8/lfj8_donor_io.h) · [targets/lfj8/test_lfj8_h03_sensor_feed.c](../targets/lfj8/test_lfj8_h03_sensor_feed.c)

**Что настраивать.** Lfj8GearCalibration, частоты таймеров, число фронтов S83, max_age_us/max_skew_us, тарировка ATF.

**Проверки.** [M32R](#check-m32r) · [INTEGRATION](#check-integration) · [INTEGRATION3](#check-integration3) · [MEMORY4](#check-memory4) · [INTEGRATION21](#check-integration21) · [FINAL_INTEGRATION](#check-final_integration) · [INTEGRATION39](#check-integration39)

**Разбор и основания.** [lfj8-h03-input-paths.md](../docs/lfj8-h03-input-paths.md) · [lfj8-h03-atf-native.md](../docs/lfj8-h03-atf-native.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md) · [lfj8-h03-memory-layout.md](../docs/lfj8-h03-memory-layout.md) · [h03-02-shared-clock.md](../verification/project-audit/h03-02-shared-clock.md) · [report.md](../verification/project-audit/integration-39-20261121/report.md) · [bench-first-wave.md](../docs/bench-first-wave.md)

**Следующий шаг для продолжения.** Доведи rbm_h03_sensor_config и rbm_h03_target_clock_ready для H03, единый TML0 и статус непрерывности. Найди частоты/делители/коэффициенты в исходнике/схеме/регистрах. Раздели вычислимые параметры и будущую измерительную коррекцию; не требовать реальную частоту до выпуска образа. Неподтверждённая оценка должна иметь явный статус и проверку, не называться измеренной. 100/22 сохранять точно, не угадывать окружность колеса. Реализовать выдачу raw speed/capture для будущей калибровки.

**Приоритет продолжения.** 16

**Исходные условия.** main abd3cba и позднее; docs/bench-first-wave.md; data/bench-first-wave.json; имеющиеся источники/проверки карточки.

**Что сдать.** Компилируемый native профиль часов и датчиков, проверка reset/wrap/stall/clock change; список только действительно аппаратных параметров для замера после прошивки.

**Кому удобно продолжить.** Чат 5 — 01a1f9a8-7b61-7763-adaa-0e3e11d1dbf4. Это рекомендация, не резерв.

**Кто сейчас выполняет.** Проверить [общий список исполнителей](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/tree/task-board). Перед изменениями занять этот ID и точные файлы.

<a id="h03-03"></a>
## H03-03 — Единое расписание и запуск приложения H03

**Требуется разработка** · ТЗ §2, §5

**Сделано.** В общий компоновщик включены четыре штатных перехода cold/startup/foreground/phase; связанная проверка адресов и 68 сценариев M32R прошли. Поставщики платформы переиспользованы.

**Осталось.** Подключить выпускной профиль запуска, полноценные GP/gear и input capture; закончить strategy/apply/monitor переходы и полный линк без испытательных деклараций.

**Критерий результата.** Полный цикл вызывается автономно, пропуск обнаруживается и без фазы выдачи, тестовые callbacks заменены подтверждёнными целевыми.

**Код.** [targets/lfj8/lfj8_h03_cycle.c](../targets/lfj8/lfj8_h03_cycle.c) · [targets/lfj8/lfj8_h03_phase_clock.c](../targets/lfj8/lfj8_h03_phase_clock.c) · [targets/lfj8/lfj8_h03_takeover.c](../targets/lfj8/lfj8_h03_takeover.c) · [targets/lfj8/h03_phase_release_hook.S](../targets/lfj8/h03_phase_release_hook.S) · [targets/lfj8/h03_native_hooks.S](../targets/lfj8/h03_native_hooks.S) · [targets/lfj8/check_h03_phase_wait.py](../targets/lfj8/check_h03_phase_wait.py) · [targets/lfj8/h03_phase_wait_hook.S](../targets/lfj8/h03_phase_wait_hook.S) · [targets/lfj8/lfj8_h03_application.c](../targets/lfj8/lfj8_h03_application.c) · [targets/lfj8/lfj8_h03_application.h](../targets/lfj8/lfj8_h03_application.h) · [targets/lfj8/h03_application_hooks.S](../targets/lfj8/h03_application_hooks.S) · [targets/lfj8/check_h03_phase_boot.py](../targets/lfj8/check_h03_phase_boot.py) · [targets/lfj8/h03_phase_boot_fixture.c](../targets/lfj8/h03_phase_boot_fixture.c) · [targets/lfj8/lfj8_h03_application_binding.c](../targets/lfj8/lfj8_h03_application_binding.c) · [targets/lfj8/lfj8_h03_application_binding.h](../targets/lfj8/lfj8_h03_application_binding.h) · [targets/lfj8/check_h03_application_binding.py](../targets/lfj8/check_h03_application_binding.py) · [targets/lfj8/check_h03_target_platform.py](../targets/lfj8/check_h03_target_platform.py) · [targets/lfj8/lfj8_h03_target_platform.c](../targets/lfj8/lfj8_h03_target_platform.c) · [targets/lfj8/lfj8_h03_target_platform.h](../targets/lfj8/lfj8_h03_target_platform.h) · [targets/lfj8/test_lfj8_h03_target_platform.c](../targets/lfj8/test_lfj8_h03_target_platform.c) · [targets/lfj8/check_h03_can_monitor_revoke.py](../targets/lfj8/check_h03_can_monitor_revoke.py) · [targets/lfj8/lfj8_h03_can_service_placement.py](../targets/lfj8/lfj8_h03_can_service_placement.py) · [targets/lfj8/lfj8_h03_application_placement.py](../targets/lfj8/lfj8_h03_application_placement.py)

**Что настраивать.** min_period/max_period/max_age, Lfj8H03TakeoverOps.phase_clock и callbacks. Частоту Toyota нельзя принять равной фазе H03.

**Проверки.** [PC](#check-pc) · [M32R](#check-m32r) · [PHASE](#check-phase) · [NATIVE](#check-native) · [INTEGRATION](#check-integration) · [INTEGRATION3](#check-integration3) · [MEMORY4](#check-memory4) · [INTEGRATION21](#check-integration21) · [FINAL_INTEGRATION](#check-final_integration) · [S01_COLD](#check-s01_cold) · [INTEGRATION39](#check-integration39) · [INTEGRATION11](#check-integration11)

**Разбор и основания.** [lfj8-h03-control-cycle.md](../docs/lfj8-h03-control-cycle.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md) · [lfj8-h03-memory-layout.md](../docs/lfj8-h03-memory-layout.md) · [h03-03-sensor-foreground.md](../verification/project-audit/h03-03-sensor-foreground.md) · [report.md](../verification/project-audit/integration-39-20261121/report.md) · [bench-first-wave.md](../docs/bench-first-wave.md)

**Зависит от.** [H03-04](#h03-04)

**Следующий шаг для продолжения.** Проверь все пути вызова нового цикла от reset до переключения, включая штатные писатели, повторный запуск и monitor. Доделай недостающие OEM redirects на основе точных байтов H03 и предоставь relocatable объекты/план патчей для общего ELF. Четыре существующих entry veneers не доказывают, что все входящие штатные ветки подключены. Проверить конечный граф путей и устранить обходы.

**Приоритет продолжения.** 17

**Исходные условия.** main abd3cba и позднее; docs/bench-first-wave.md; data/bench-first-wave.json; имеющиеся источники/проверки карточки.

**Что сдать.** Полный набор hooks/placement с проверкой original bytes, ссылками на native callbacks, проверкой CPU штатного/отказного/повторного пути; никаких fixture callbacks.

**Кому удобно продолжить.** Чат 1 — 01a1f9ae-4a7e-7e31-951a-f6383e1831ee. Это рекомендация, не резерв.

**Кто сейчас выполняет.** Проверить [общий список исполнителей](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/tree/task-board). Перед изменениями занять этот ID и точные файлы.

<a id="h03-04"></a>
## H03-04 — Память, стек и сервисные пути

**Требуется разработка** · ТЗ §5

**Сделано.** В общем составе связаны пять сервисных переходов, 14 алиасов RAM/SPI/PSW и резидентная политика. Интегратор разместил 1532 байта неизменённых таблиц в нижнем запасе; известный верх теперь 102200/102356.

**Осталось.** Завершить пять обязательных определений: boot_writers_owned, нижние границы и резервы SPI/PSW с вложенными IRQ/SBI. После остальных поставщиков повторить полное размещение; текущие 156 байт верхнего запаса не являются окончательным резервом.

**Критерий результата.** Карта сборки и анализ всех владельцев, подтверждённый запас стека и измерения. Свободное окно в ELF само по себе не разрешает запись.

**Код.** [targets/lfj8/check_h03_link.py](../targets/lfj8/check_h03_link.py) · [targets/lfj8/check_h03_ram_candidate.py](../targets/lfj8/check_h03_ram_candidate.py) · [targets/lfj8/check_h03_flash_residency.py](../targets/lfj8/check_h03_flash_residency.py) · [targets/lfj8/check_h03_service_isolation.py](../targets/lfj8/check_h03_service_isolation.py) · [targets/lfj8/audit_h03_irq_stack.py](../targets/lfj8/audit_h03_irq_stack.py) · [targets/lfj8/lfj8_h03_storage.h](../targets/lfj8/lfj8_h03_storage.h) · [targets/lfj8/check_h03_storage.py](../targets/lfj8/check_h03_storage.py) · [tools/check_h03_image_layout.py](../tools/check_h03_image_layout.py) · [targets/lfj8/lfj8_h03_layout.py](../targets/lfj8/lfj8_h03_layout.py) · [tests/test_h03_layout.py](../tests/test_h03_layout.py) · [targets/lfj8/check_h03_service_writes.py](../targets/lfj8/check_h03_service_writes.py) · [targets/lfj8/lfj8_h03_service_guard.c](../targets/lfj8/lfj8_h03_service_guard.c) · [targets/lfj8/lfj8_h03_service_guard.h](../targets/lfj8/lfj8_h03_service_guard.h) · [targets/lfj8/h03_service_guard_hooks.S](../targets/lfj8/h03_service_guard_hooks.S) · [targets/lfj8/check_h03_service_guard.py](../targets/lfj8/check_h03_service_guard.py) · [targets/lfj8/check_h03_ram_owner.py](../targets/lfj8/check_h03_ram_owner.py) · [targets/lfj8/lfj8_h03_ram_owner.h](../targets/lfj8/lfj8_h03_ram_owner.h) · [targets/lfj8/lfj8_h03_target_memory.c](../targets/lfj8/lfj8_h03_target_memory.c) · [targets/lfj8/test_lfj8_h03_ram_owner.c](../targets/lfj8/test_lfj8_h03_ram_owner.c) · [targets/lfj8/check_h03_boot_writers.py](../targets/lfj8/check_h03_boot_writers.py) · [targets/lfj8/lfj8_h03_ram_owner.c](../targets/lfj8/lfj8_h03_ram_owner.c) · [targets/lfj8/check_h03_dma4_guard.py](../targets/lfj8/check_h03_dma4_guard.py) · [targets/lfj8/h03_dma4_guard.S](../targets/lfj8/h03_dma4_guard.S) · [targets/lfj8/lfj8_h03_service_placement.py](../targets/lfj8/lfj8_h03_service_placement.py) · [targets/lfj8/lfj8_h03_ram_placement.py](../targets/lfj8/lfj8_h03_ram_placement.py)

**Что настраивать.** RAM 2692 + 4 Б: [0x806B40,0x806F8C), [0x808E40,0x80905C), [0x80905C,0x809478). Известный расширенный Flash-состав 94770 Б, номинальный остаток 7586 до окончательной обвязки; владение не подтверждено.

**Проверки.** [M32R](#check-m32r) · [NATIVE](#check-native) · [STORAGE](#check-storage) · [INTEGRATION](#check-integration) · [INTEGRATION2](#check-integration2) · [INTEGRATION3](#check-integration3) · [MEMORY4](#check-memory4) · [SERVICE_GUARD](#check-service_guard) · [INTEGRATION21](#check-integration21) · [FINAL_INTEGRATION](#check-final_integration) · [S01_COLD](#check-s01_cold) · [INTEGRATION39](#check-integration39) · [INTEGRATION11](#check-integration11) · [BENCH_PREP](#check-bench_prep)

**Разбор и основания.** [lfj8-h03-ram-audit.md](../docs/lfj8-h03-ram-audit.md) · [lfj8-h03-flash.md](../docs/lfj8-h03-flash.md) · [lfj8-h03-service-isolation.md](../docs/lfj8-h03-service-isolation.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md) · [lfj8-h03-memory-layout.md](../docs/lfj8-h03-memory-layout.md) · [h03-04-service-guard.md](../verification/project-audit/h03-04-service-guard.md) · [h03-04-service-cancel.md](../verification/project-audit/h03-04-service-cancel.md) · [report.md](../verification/project-audit/integration-39-20261121/report.md) · [bench-first-wave.md](../docs/bench-first-wave.md)

**Следующий шаг для продолжения.** Закрой rbm_h03_boot_writers_owned и четыре диапазона SPI/PSW: first/reserve. Аудит reset/IRQ/DMA/service и стеков по штатному BIN, статический граф и симулятор. Нужно реальное владение RAM и отказ при потере, а не функция всегда true. Предоставь итоговые числовые диапазоны со статическим обоснованием и зарезервированными зонами; аппаратный high-water после BIN не должен мешать доказуемой программной части.

**Приоритет продолжения.** 18

**Исходные условия.** main abd3cba и позднее; docs/bench-first-wave.md; data/bench-first-wave.json; имеющиеся источники/проверки карточки.

**Что сдать.** Пять реальных определений/профиль, полный список писателей, linker constraints и доказательства покрытия; стоимость RAM/стеков и сценарии отказа.

**Кому удобно продолжить.** Чат 6 — 01a1f99f-5cb5-70e0-afd0-60e6b41a5d51. Это рекомендация, не резерв.

**Кто сейчас выполняет.** Проверить [общий список исполнителей](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/tree/task-board). Перед изменениями занять этот ID и точные файлы.

<a id="h03-05"></a>
## H03-05 — SLT, силовые выходы и реакция на отказ

**Требуется разработка** · ТЗ §2, §5

**Сделано.** Нативный takeover сокращён на 94 байта medium/86 small без роста RAM. Порядок публикации и 13 флагов проверены, штатные выходные сценарии прошли.

**Осталось.** Подключить квалифицированный output profile/takeover ops и подтвердить SLT/SLU, изоляцию и физическую реакцию выходов.

**Критерий результата.** Измеренные таблицы в допустимой области питания/ATF, реакция каждого выхода и гидравлики на отказ, отсутствие старой команды после восстановления.

**Код.** [targets/lfj8/lfj8_h03_outputs.c](../targets/lfj8/lfj8_h03_outputs.c) · [targets/lfj8/lfj8_h03_takeover.c](../targets/lfj8/lfj8_h03_takeover.c) · [targets/lfj8/check_h03_slt_fault.py](../targets/lfj8/check_h03_slt_fault.py) · [targets/lfj8/lfj8_h03_output_inhibit.c](../targets/lfj8/lfj8_h03_output_inhibit.c) · [targets/lfj8/check_h03_can_monitor_revoke.py](../targets/lfj8/check_h03_can_monitor_revoke.py) · [targets/lfj8/lfj8_h03_can_monitor_revoke.c](../targets/lfj8/lfj8_h03_can_monitor_revoke.c) · [targets/lfj8/check_h03_target_outputs.py](../targets/lfj8/check_h03_target_outputs.py) · [targets/lfj8/h03_target_outputs_fixture.c](../targets/lfj8/h03_target_outputs_fixture.c) · [targets/lfj8/lfj8_h03_application_binding.c](../targets/lfj8/lfj8_h03_application_binding.c) · [targets/lfj8/lfj8_h03_takeover.h](../targets/lfj8/lfj8_h03_takeover.h) · [targets/lfj8/lfj8_h03_target_commit.c](../targets/lfj8/lfj8_h03_target_commit.c) · [targets/lfj8/lfj8_h03_output_inhibit.h](../targets/lfj8/lfj8_h03_output_inhibit.h) · [targets/lfj8/test_lfj8_h03_takeover.c](../targets/lfj8/test_lfj8_h03_takeover.c)

**Что настраивать.** Lfj8H03OutputBinding, Lfj8H03SltCalibration, рабочая область ATF/питания и Lfj8H03TakeoverOps.inhibit. Тестовые 500 мА не являются калибровкой.

**Проверки.** [M32R](#check-m32r) · [NATIVE](#check-native) · [INTEGRATION3](#check-integration3) · [MEMORY4](#check-memory4) · [INTEGRATION21](#check-integration21) · [FINAL_INTEGRATION](#check-final_integration) · [INTEGRATION39](#check-integration39) · [INTEGRATION11](#check-integration11)

**Разбор и основания.** [lfj8-slt-calibration.md](../docs/lfj8-slt-calibration.md) · [lfj8-h03-output-adapter.md](../docs/lfj8-h03-output-adapter.md) · [lfj8-9e1c-minimum-bench.md](../docs/lfj8-9e1c-minimum-bench.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md) · [lfj8-h03-memory-layout.md](../docs/lfj8-h03-memory-layout.md) · [h03-05-can-revoke-bindings.md](../verification/project-audit/h03-05-can-revoke-bindings.md) · [report.md](../verification/project-audit/integration-39-20261121/report.md) · [bench-first-wave.md](../docs/bench-first-wave.md)

**Следующий шаг для продолжения.** Доведи реальные native output ops, mapping D/E/F/Pressure A и весь путь command→arbitrate→apply→inhibit. Перепроверь соответствие SLT/SLU и отказов. Нельзя утверждать электрическую изоляцию TIO9 маской без основания. Если конкретное включение требует неизвестного электрического параметра, реализуй диагностическое/комиссионное измерение и явную блокировку именно этого включения; не останавливать запуск/CAN всей системы. Донорские значения с доказуемой применимостью могут быть начальной инженерной настройкой с явно указанными ограничениями, не выдуманной калибровкой давления. Все аппаратные измерения оформить после BIN.

**Приоритет продолжения.** 19

**Исходные условия.** main abd3cba и позднее; docs/bench-first-wave.md; data/bench-first-wave.json; имеющиеся источники/проверки карточки.

**Что сдать.** Реальный output backend/профиль, завершённая программная последовательность переключений и SLU, ограничение непроверенного включения, проверка отзыва каждой команды и минимальный план замеров после сборки.

**Кому удобно продолжить.** Чат 7 — 01a1f9a2-d0ae-78d3-86f1-21b27426fd3f. Это рекомендация, не резерв.

**Кто сейчас выполняет.** Проверить [общий список исполнителей](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/tree/task-board). Перед изменениями занять этот ID и точные файлы.

<a id="vss-01"></a>
## VSS-01 — Точный расчёт VSS и скорость по CAN

**Проверено программно** · ТЗ §7

**Сделано.** Объединённый результат 21.11.2026: 0x1AE отбрасывает тайм-аут вне полуоборота TML0 и окно до сужения. PC 41 шаг, 129 тестов Python; M32R, CAN13 и двусторонний Bosch PASS. Отчёт vss01-tml0-timing-admission.md. Целевые привязки, параметры авто и реальная шина открыты.

**Осталось.** Привязать независимое подтверждение остановки и параметры машины, проверить реальную скорость по CAN.

**Критерий результата.** Округление 4,545 не используется как расчётный коэффициент.

**Код.** [targets/lfj8/lfj8_bridge.c](../targets/lfj8/lfj8_bridge.c) · [targets/lfj8/lfj8_chery_tx.c](../targets/lfj8/lfj8_chery_tx.c) · [targets/bosch/build.py](../targets/bosch/build.py) · [targets/lfj8/host_check.c](../targets/lfj8/host_check.c) · [targets/lfj8/lfj8_chery_tx.h](../targets/lfj8/lfj8_chery_tx.h) · [targets/lfj8/lfj8_donor_io.c](../targets/lfj8/lfj8_donor_io.c) · [targets/lfj8/lfj8_donor_io.h](../targets/lfj8/lfj8_donor_io.h)

**Что настраивать.** lfj8_vss_raw_1ae(ticks,pulse_count,tick_hz,wheel_um,wheel_num,wheel_den,capture_state).

**Проверки.** [PC](#check-pc) · [M32R](#check-m32r) · [BOSCH](#check-bosch) · [INTEGRATION3](#check-integration3) · [INTEGRATION21](#check-integration21) · [FINAL_INTEGRATION](#check-final_integration)

**Разбор и основания.** [README.md](../targets/lfj8/README.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md) · [vss01-standstill-guard.md](../verification/project-audit/vss01-standstill-guard.md) · [bench-first-wave.md](../docs/bench-first-wave.md)

**Следующий шаг для продолжения.** Доведи rbm_h03_sensor_config и rbm_h03_target_clock_ready для H03, единый TML0 и статус непрерывности. Найди частоты/делители/коэффициенты в исходнике/схеме/регистрах. Раздели вычислимые параметры и будущую измерительную коррекцию; не требовать реальную частоту до выпуска образа. Неподтверждённая оценка должна иметь явный статус и проверку, не называться измеренной. 100/22 сохранять точно, не угадывать окружность колеса. Реализовать выдачу raw speed/capture для будущей калибровки.

**Приоритет продолжения.** 21

**Исходные условия.** main abd3cba и позднее; docs/bench-first-wave.md; data/bench-first-wave.json; имеющиеся источники/проверки карточки.

**Что сдать.** Компилируемый native профиль часов и датчиков, проверка reset/wrap/stall/clock change; список только действительно аппаратных параметров для замера после прошивки.

**Кому удобно продолжить.** Чат 5 — 01a1f9a8-7b61-7763-adaa-0e3e11d1dbf4. Это рекомендация, не резерв.

**Кто сейчас выполняет.** Проверить [общий список исполнителей](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/tree/task-board). Перед изменениями занять этот ID и точные файлы.

<a id="vss-02"></a>
## VSS-02 — Кинематика и параметры реальной скорости

**Требуется разработка** · ТЗ §7

**Сделано.** Foreground сравнивает относительный ход TML0/TML1; разрыв отзывает эпоху и очищает S51/S83/ATF. Исправлен воспроизведённый дефект 06ab447; добавлено 12 байт типизированного состояния.

**Осталось.** Сохранить контроль непрерывности и дать квалифицированную абсолютную частоту/профиль датчиков. Относительное совпадение двух счётчиков не доказывает их масштаб.

**Критерий результата.** Скорость совпадает с эталоном в согласованном диапазоне, потеря импульсов отличается от остановки.

**Код.** [targets/lfj8/lfj8_bridge.h](../targets/lfj8/lfj8_bridge.h) · [targets/lfj8/lfj8_donor_io.h](../targets/lfj8/lfj8_donor_io.h) · [targets/lfj8/lfj8_gear_observer.h](../targets/lfj8/lfj8_gear_observer.h) · [targets/lfj8/lfj8_h03_sensor_feed.c](../targets/lfj8/lfj8_h03_sensor_feed.c) · [targets/lfj8/check_h03_sensor_config.py](../targets/lfj8/check_h03_sensor_config.py) · [targets/lfj8/check_h03_application_binding.py](../targets/lfj8/check_h03_application_binding.py) · [targets/lfj8/h03_application_binding_fixture.c](../targets/lfj8/h03_application_binding_fixture.c) · [targets/lfj8/h03_phase_boot_fixture.c](../targets/lfj8/h03_phase_boot_fixture.c) · [targets/lfj8/h03_sensor_hook_fixture.c](../targets/lfj8/h03_sensor_hook_fixture.c) · [targets/lfj8/lfj8_donor_io.c](../targets/lfj8/lfj8_donor_io.c) · [targets/lfj8/lfj8_h03_sensor_feed.h](../targets/lfj8/lfj8_h03_sensor_feed.h) · [targets/lfj8/lfj8_h03_sensor_target.c](../targets/lfj8/lfj8_h03_sensor_target.c) · [targets/lfj8/test_lfj8_h03_sensor_feed.c](../targets/lfj8/test_lfj8_h03_sensor_feed.c) · [targets/lfj8/test_lfj8_h03_target_platform.c](../targets/lfj8/test_lfj8_h03_target_platform.c)

**Что настраивать.** wheel_um, wheel_num/wheel_den, частота счётчика, тайм-ауты; 100/22 уже задано.

**Проверки.** [M32R](#check-m32r) · [INTEGRATION3](#check-integration3) · [MEMORY4](#check-memory4) · [INTEGRATION21](#check-integration21) · [FINAL_INTEGRATION](#check-final_integration) · [INTEGRATION39](#check-integration39) · [INTEGRATION11](#check-integration11)

**Разбор и основания.** [lfj8-9e1c-minimum-bench.md](../docs/lfj8-9e1c-minimum-bench.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md) · [lfj8-h03-memory-layout.md](../docs/lfj8-h03-memory-layout.md) · [vss02-h03-sensor-config.md](../verification/project-audit/vss02-h03-sensor-config.md) · [report.md](../verification/project-audit/integration-39-20261121/report.md) · [bench-first-wave.md](../docs/bench-first-wave.md)

**Следующий шаг для продолжения.** Доведи rbm_h03_sensor_config и rbm_h03_target_clock_ready для H03, единый TML0 и статус непрерывности. Найди частоты/делители/коэффициенты в исходнике/схеме/регистрах. Раздели вычислимые параметры и будущую измерительную коррекцию; не требовать реальную частоту до выпуска образа. Неподтверждённая оценка должна иметь явный статус и проверку, не называться измеренной. 100/22 сохранять точно, не угадывать окружность колеса. Реализовать выдачу raw speed/capture для будущей калибровки.

**Приоритет продолжения.** 22

**Исходные условия.** main abd3cba и позднее; docs/bench-first-wave.md; data/bench-first-wave.json; имеющиеся источники/проверки карточки.

**Что сдать.** Компилируемый native профиль часов и датчиков, проверка reset/wrap/stall/clock change; список только действительно аппаратных параметров для замера после прошивки.

**Кому удобно продолжить.** Чат 5 — 01a1f9a8-7b61-7763-adaa-0e3e11d1dbf4. Это рекомендация, не резерв.

**Кто сейчас выполняет.** Проверить [общий список исполнителей](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/tree/task-board). Перед изменениями занять этот ID и точные файлы.

<a id="mode-01"></a>
## MODE-01 — Логика шести положений и кнопок

**Проверено программно** · ТЗ §8

**Сделано.** Объединённый результат 21.11.2026: INVALID/OVERRUN сразу отзывают диапазон независимо от метки. 10 сценариев ПК/M32R, input-binding, 18+8 компонентных и 6 размещённых сценариев PASS. +20 байт Flash. Полный линк FAIL_BINDINGS. Отчёт mode01-selector-fault.md.

**Осталось.** Подключить реальный захват к foreground и провести ручную заявку через весь гидравлический цикл.

**Критерий результата.** Компонентный requested_gear не равен выполненному гидравлическому переключению.

**Код.** [controller/src/rbm_u340e.c](../controller/src/rbm_u340e.c) · [targets/lfj8/lfj8_range_control.c](../targets/lfj8/lfj8_range_control.c) · [targets/lfj8/lfj8_selector_adc.c](../targets/lfj8/lfj8_selector_adc.c) · [controller/tests/test_shift_buttons.c](../controller/tests/test_shift_buttons.c) · [targets/lfj8/lfj8_range_control.h](../targets/lfj8/lfj8_range_control.h) · [tests/u340_integration_host.c](../tests/u340_integration_host.c)

**Что настраивать.** RbmU340ePolicy, стабильные кнопки до rbm_u340e_step, окна ADC. Расчётные 2=200 Ом, L=91 Ом требуют проверки.

**Проверки.** [PC](#check-pc) · [M32R](#check-m32r) · [INTEGRATION2](#check-integration2) · [INTEGRATION3](#check-integration3) · [INTEGRATION21](#check-integration21) · [FINAL_INTEGRATION](#check-final_integration)

**Разбор и основания.** [lfj8-selector.md](../docs/lfj8-selector.md) · [mode01-shift-conflict.md](../verification/project-audit/mode01-shift-conflict.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md) · [mode01-button-source-loss.md](../verification/project-audit/mode01-button-source-loss.md) · [bench-first-wave.md](../docs/bench-first-wave.md)

**Следующий шаг для продолжения.** Доведи реальные P/R/N/D/2/L, Tiptronic +/−/toggle и OD до Toyota cycle с блокировкой опасных/противоречивых входов. Профиль из схемы, кода и расчёта ADC/резисторов, не test constants. Пересчитай сопротивления 2/L с номиналами/допусками/исходной схемой: если аппаратный делитель известен из исходников, рассчитать до замера; если нет — указать конкретно неизвестный элемент, не выдумывать ом. Режим после reset и допустимость команды фиксировать явно, с происхождением/решением.

**Приоритет продолжения.** 24

**Исходные условия.** main abd3cba и позднее; docs/bench-first-wave.md; data/bench-first-wave.json; имеющиеся источники/проверки карточки.

**Что сдать.** Native mode/input profile, расчёт диапазонов/резисторов и полная цепь ручного запроса, debounce/hold/opposed/stale/reset tests.

**Кому удобно продолжить.** Чат 11 — 01a1fa79-892d-7ca3-bb8a-44698892c53e. Это рекомендация, не резерв.

**Кто сейчас выполняет.** Проверить [общий список исполнителей](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/tree/task-board). Перед изменениями занять этот ID и точные файлы.

<a id="mode-02"></a>
## MODE-02 — Подключение селектора, Tiptronic и Overdrive

**Требуется разработка** · ТЗ §5, §8

**Сделано.** Нативный AN2/P1DATA поддерживает явные окна и политику; startup сбрасывает владельцев до CAN. Общие host/M32R проверки прошли.

**Осталось.** Задать обоснованные окна ADC, карту входов и тайминги; подключить квалифицированные Toyota inputs в окончательном профиле.

**Критерий результата.** Реальные нажатия проходят до исполнения запроса в полном цикле, дребезг/обрыв не создают повторных команд.

**Код.** [targets/lfj8/lfj8_selector_adc.c](../targets/lfj8/lfj8_selector_adc.c) · [targets/lfj8/lfj8_range_control.c](../targets/lfj8/lfj8_range_control.c) · [controller/src/rbm_u340e.c](../controller/src/rbm_u340e.c) · [targets/lfj8/lfj8_h03_cycle.c](../targets/lfj8/lfj8_h03_cycle.c) · [targets/lfj8/lfj8_h03_input_binding.c](../targets/lfj8/lfj8_h03_input_binding.c) · [targets/lfj8/lfj8_h03_input_target.c](../targets/lfj8/lfj8_h03_input_target.c) · [targets/lfj8/check_h03_button_capture.py](../targets/lfj8/check_h03_button_capture.py) · [targets/lfj8/lfj8_h03_button_capture.c](../targets/lfj8/lfj8_h03_button_capture.c) · [targets/lfj8/lfj8_h03_button_capture.h](../targets/lfj8/lfj8_h03_button_capture.h) · [targets/lfj8/test_lfj8_h03_button_capture.c](../targets/lfj8/test_lfj8_h03_button_capture.c) · [targets/lfj8/check_h03_toyota_source.py](../targets/lfj8/check_h03_toyota_source.py) · [targets/lfj8/lfj8_h03_input_binding.h](../targets/lfj8/lfj8_h03_input_binding.h) · [targets/lfj8/lfj8_range_control.h](../targets/lfj8/lfj8_range_control.h) · [targets/lfj8/test_lfj8_h03_input_binding.c](../targets/lfj8/test_lfj8_h03_input_binding.c) · [targets/lfj8/test_lfj8_h03_toyota_source.c](../targets/lfj8/test_lfj8_h03_toyota_source.c) · [targets/lfj8/check_h03_target_platform.py](../targets/lfj8/check_h03_target_platform.py) · [targets/lfj8/lfj8_h03_target_platform.c](../targets/lfj8/lfj8_h03_target_platform.c) · [targets/lfj8/lfj8_h03_target_platform.h](../targets/lfj8/lfj8_h03_target_platform.h) · [targets/lfj8/lfj8_h03_toyota_input_profile.h](../targets/lfj8/lfj8_h03_toyota_input_profile.h) · [targets/lfj8/test_lfj8_h03_target_platform.c](../targets/lfj8/test_lfj8_h03_target_platform.c) · [controller/include/rbm_u340e.h](../controller/include/rbm_u340e.h)

**Что настраивать.** AD0DT2, событие 0x804BC6, P1DATA и вход Overdrive. max_age_us задаётся по фактическому ритму ADC.

**Проверки.** [PC](#check-pc) · [M32R](#check-m32r) · [INTEGRATION](#check-integration) · [INTEGRATION3](#check-integration3) · [MEMORY4](#check-memory4) · [INTEGRATION21](#check-integration21) · [FINAL_INTEGRATION](#check-final_integration) · [INTEGRATION39](#check-integration39) · [INTEGRATION11](#check-integration11)

**Разбор и основания.** [lfj8-selector.md](../docs/lfj8-selector.md) · [lfj8-h03-input-paths.md](../docs/lfj8-h03-input-paths.md) · [mode02-button-input.md](../verification/project-audit/mode02-button-input.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md) · [lfj8-h03-memory-layout.md](../docs/lfj8-h03-memory-layout.md) · [mode02-h03-button-capture.md](../verification/project-audit/mode02-h03-button-capture.md) · [report.md](../verification/project-audit/integration-39-20261121/report.md) · [bench-first-wave.md](../docs/bench-first-wave.md)

**Зависит от.** [H03-03](#h03-03)

**Следующий шаг для продолжения.** Доведи реальные P/R/N/D/2/L, Tiptronic +/−/toggle и OD до Toyota cycle с блокировкой опасных/противоречивых входов. Профиль из схемы, кода и расчёта ADC/резисторов, не test constants. Пересчитай сопротивления 2/L с номиналами/допусками/исходной схемой: если аппаратный делитель известен из исходников, рассчитать до замера; если нет — указать конкретно неизвестный элемент, не выдумывать ом. Режим после reset и допустимость команды фиксировать явно, с происхождением/решением.

**Приоритет продолжения.** 25

**Исходные условия.** main abd3cba и позднее; docs/bench-first-wave.md; data/bench-first-wave.json; имеющиеся источники/проверки карточки.

**Что сдать.** Native mode/input profile, расчёт диапазонов/резисторов и полная цепь ручного запроса, debounce/hold/opposed/stale/reset tests.

**Кому удобно продолжить.** Чат 11 — 01a1fa79-892d-7ca3-bb8a-44698892c53e. Это рекомендация, не резерв.

**Кто сейчас выполняет.** Проверить [общий список исполнителей](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/tree/task-board). Перед изменениями занять этот ID и точные файлы.

<a id="mode-03"></a>
## MODE-03 — Окончательная политика режимов

**Требуется разработка** · ТЗ §8

**Сделано.** Объединённый результат 21.11.2026: На актуальной main с 64dd049 общий контроллер отвергает заявки до принятия профиля и после отказа init. ПК 41/129, матрица и привязка H03 на ПК/M32R, M32R 18+8 и 6 проверок размещения. Карта RAM совпала. Отчёт mode03-policy-init-gate.md. Политика выпуска и стенд открыты.

**Осталось.** Зафиксировать начальный режим, сохранение OD, допустимые ручные диапазоны и ограничения окончательного профиля; связать с реальными входами.

**Критерий результата.** Политика согласована с донорской логикой и подтверждена матрицей режимов. Тестовые defaults не выдаются за решение владельца.

**Код.** [controller/include/rbm_u340e.h](../controller/include/rbm_u340e.h) · [controller/src/rbm_u340e.c](../controller/src/rbm_u340e.c) · [controller/tests/test_mode_policy.c](../controller/tests/test_mode_policy.c) · [targets/lfj8/lfj8_h03_input_binding.c](../targets/lfj8/lfj8_h03_input_binding.c) · [targets/lfj8/test_lfj8_h03_input_binding.c](../targets/lfj8/test_lfj8_h03_input_binding.c)

**Что настраивать.** initial_mode, initial_overdrive_enabled, manual_selectors, overdrive_limit_modes, allowed_gears.

**Проверки.** [PC](#check-pc) · [INTEGRATION3](#check-integration3) · [INTEGRATION21](#check-integration21) · [FINAL_INTEGRATION](#check-final_integration)

**Разбор и основания.** [decisions.md](../docs/decisions.md) · [lfj8-selector.md](../docs/lfj8-selector.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md) · [mode03-conflict-policy.md](../verification/project-audit/mode03-conflict-policy.md) · [bench-first-wave.md](../docs/bench-first-wave.md)

**Следующий шаг для продолжения.** Доведи реальные P/R/N/D/2/L, Tiptronic +/−/toggle и OD до Toyota cycle с блокировкой опасных/противоречивых входов. Профиль из схемы, кода и расчёта ADC/резисторов, не test constants. Пересчитай сопротивления 2/L с номиналами/допусками/исходной схемой: если аппаратный делитель известен из исходников, рассчитать до замера; если нет — указать конкретно неизвестный элемент, не выдумывать ом. Режим после reset и допустимость команды фиксировать явно, с происхождением/решением.

**Приоритет продолжения.** 26

**Исходные условия.** main abd3cba и позднее; docs/bench-first-wave.md; data/bench-first-wave.json; имеющиеся источники/проверки карточки.

**Что сдать.** Native mode/input profile, расчёт диапазонов/резисторов и полная цепь ручного запроса, debounce/hold/opposed/stale/reset tests.

**Кому удобно продолжить.** Чат 11 — 01a1fa79-892d-7ca3-bb8a-44698892c53e. Это рекомендация, не резерв.

**Кто сейчас выполняет.** Проверить [общий список исполнителей](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/tree/task-board). Перед изменениями занять этот ID и точные файлы.

<a id="rel-01"></a>
## REL-01 — Два целевых BIN и воспроизводимый комплект

**Требуется разработка** · ТЗ §1, §4, §5, §9

**Сделано.** Добавлена детерминированная сборка байтов полного H03 ELF с проверкой исходных участков и всех секций. Проверены 12 новых сценариев. Полного native ELF и TCM BIN ещё нет; работают 12 чатов первой стендовой волны.

**Осталось.** Закончить реальные профили/поставщики, полный native link и все redirects, сериализацию TCM BIN, целевую Bosch пару, целостность, сквозные проверки и манифест. Измерения новой пары следуют после выдачи файлов.

**Критерий результата.** Два целевых реализованных BIN, source/final SHA и карта правок, воспроизводимая сборка, подтвержденные software checks, явные ограничения первого стенда. Аппаратная приемка учитывается отдельно в REL-02.

**Код.** [controller/build_target.py](../controller/build_target.py) · [targets/lfj8/check_h03_link.py](../targets/lfj8/check_h03_link.py) · [targets/bosch/build.py](../targets/bosch/build.py) · [tools/package_workset.py](../tools/package_workset.py) · [tests/test_package_workset.py](../tests/test_package_workset.py) · [tools/h03_image.py](../tools/h03_image.py)

**Что настраивать.** Отдельные поля build_verified, model_verified и hardware_verified. Не переименовывать ELF/тестовый BIN в рабочую прошивку.

**Проверки.** [SOURCES](#check-sources) · [PC](#check-pc) · [M32R](#check-m32r) · [NATIVE](#check-native) · [BOSCH](#check-bosch) · [INTEGRATION](#check-integration) · [INTEGRATION3](#check-integration3) · [MEMORY4](#check-memory4) · [SERVICE_GUARD](#check-service_guard) · [INTEGRATION21](#check-integration21) · [FINAL_INTEGRATION](#check-final_integration) · [INTEGRATION39](#check-integration39) · [INTEGRATION11](#check-integration11) · [BENCH_PREP](#check-bench_prep)

**Разбор и основания.** [verification.md](../docs/verification.md) · [working-set.md](../docs/working-set.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md) · [lfj8-h03-memory-layout.md](../docs/lfj8-h03-memory-layout.md) · [rel01-offline-report-guard.md](../verification/project-audit/rel01-offline-report-guard.md)

**Зависит от.** [TOY-04](#toy-04), [TOY-05](#toy-05), [TOY-06](#toy-06), [CAN-03](#can-03), [CAN-05](#can-05), [ECU-02](#ecu-02), [H03-04](#h03-04), [H03-05](#h03-05), [VSS-02](#vss-02), [MODE-02](#mode-02), [MODE-03](#mode-03), [DTC-02](#dtc-02), [DTC-03](#dtc-03), [DTC-04](#dtc-04)

**Следующий шаг для продолжения.** Интегрировать 12 направлений из bench-first-wave; свести профили и доказать конечный запуск/размещение/целостность; выдать два BIN для первого стенда только после программной готовности.

**Приоритет продолжения.** 27

**Исходные условия.** Все обязательные задачи первого этапа; два реле и панель отложены. Десять unresolved — не весь остаток проекта.

**Что сдать.** TCM BIN + Bosch BIN + SHA/manifest, карты правок, применимость и фактические результаты приёмки.

**Кто сейчас выполняет.** Проверить [общий список исполнителей](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/tree/task-board). Перед изменениями занять этот ID и точные файлы.

<a id="rel-02"></a>
## REL-02 — Приёмка новой связки на оборудовании

**Требуются физические данные** · ТЗ §2, §3, §4, §5, §7, §8, §11

**Сделано.** Объединённый результат 21.11.2026: Нативная проверка десяти DMA-каналов в холодном допуске RAM H03. M32R: 97142 байта, 5214 номинальный остаток. Адресный ELF H03-04: 27 писателей, 28 закрытий сеанса и 512 Virtual Flash. Остаются привязка приложения и датчиков, доказательство последующего владения DMA/SBI/IRQ, запись нижней Flash через PCM Flash; это порция REL-02.

**Осталось.** Аппаратная приемка начинается после получения двух BIN и прошивки владельцем. До этого — подготовить исполнимый минимальный протокол и встроенные средства чтения реальных величин.

**Критерий результата.** Журналы содержат версии BIN, условия, измерения, допуски и результат. Программные тесты учитываются отдельно.

**Код.** [docs/lfj8-9e1c-minimum-bench.md](../docs/lfj8-9e1c-minimum-bench.md) · [docs/verification.md](../docs/verification.md) · [targets/lfj8/check_h03_application_isolation.py](../targets/lfj8/check_h03_application_isolation.py) · [targets/lfj8/lfj8_h03_monitor_quiesce.c](../targets/lfj8/lfj8_h03_monitor_quiesce.c) · [targets/lfj8/lfj8_h03_monitor_quiesce.h](../targets/lfj8/lfj8_h03_monitor_quiesce.h)

**Что настраивать.** Приборы, температуры/нагрузки и численные допуски должны иметь источник. Реле и панель исключены из первой приёмки.

**Проверки.** [INTEGRATION3](#check-integration3) · [INTEGRATION21](#check-integration21) · [FINAL_INTEGRATION](#check-final_integration)

**Разбор и основания.** [lfj8-9e1c-minimum-bench.md](../docs/lfj8-9e1c-minimum-bench.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md) · [rel02-h03-application-isolation.md](../verification/project-audit/rel02-h03-application-isolation.md)

**Зависит от.** [REL-01](#rel-01)

**Следующий шаг для продолжения.** Выполнить минимальный аппаратный протокол на целевой паре после соответствующей программной сборки.

**Приоритет продолжения.** 28

**Исходные условия.** Доступ к оборудованию отсутствует; результат невозможно заменить симуляцией. Не отмечать выполненным без измерений.

**Что сдать.** Фактические записи входов/CAN/момента/SLT/SLU и отказов с критериями приёмки.

**Кто сейчас выполняет.** Проверить [общий список исполнителей](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/tree/task-board). Перед изменениями занять этот ID и точные файлы.

<a id="dtc-01"></a>
## DTC-01 — Прикладной сеанс и статусы Chery

**Проверено программно** · ТЗ §11

**Сделано.** Старый сеанс RX очищается до проверки TX/FC timeout; при потере foreground clock допуск отзывается. Host/M32R регрессии прошли.

**Осталось.** Включить транспорт с реальными таймингами и native CAN в итоговый образ; проверить прикладной сеанс на общей целевой конфигурации.

**Критерий результата.** Поддержан конкретный профиль CAN C0. Остальные FC/сервисы и K-Line не объявлены реализованными.

**Код.** [diagnostics/chery_dtc.c](../diagnostics/chery_dtc.c) · [diagnostics/chery_dtc_can.c](../diagnostics/chery_dtc_can.c) · [diagnostics/chery_dtc_link.c](../diagnostics/chery_dtc_link.c) · [diagnostics/chery_model_monitor.c](../diagnostics/chery_model_monitor.c) · [targets/lfj8/lfj8_h03_engine_feed.c](../targets/lfj8/lfj8_h03_engine_feed.c) · [diagnostics/chery_dtc_link.h](../diagnostics/chery_dtc_link.h) · [diagnostics/test_chery_dtc_link.c](../diagnostics/test_chery_dtc_link.c) · [diagnostics/verify_c0_session_timer.py](../diagnostics/verify_c0_session_timer.py) · [targets/lfj8/lfj8_h03_dtc_can.c](../targets/lfj8/lfj8_h03_dtc_can.c) · [targets/lfj8/lfj8_h03_dtc_can.h](../targets/lfj8/lfj8_h03_dtc_can.h) · [targets/lfj8/test_lfj8_h03_dtc_can.c](../targets/lfj8/test_lfj8_h03_dtc_can.c) · [targets/lfj8/lfj8_h03_dtc_foreground.c](../targets/lfj8/lfj8_h03_dtc_foreground.c) · [targets/lfj8/lfj8_h03_dtc_foreground.h](../targets/lfj8/lfj8_h03_dtc_foreground.h) · [targets/lfj8/test_lfj8_h03_dtc_foreground.c](../targets/lfj8/test_lfj8_h03_dtc_foreground.c)

**Что настраивать.** Пять исторических слотов, таблица 96 индексов S03, возраст FC и таймеры сеанса.

**Проверки.** [PC](#check-pc) · [M32R](#check-m32r) · [INTEGRATION2](#check-integration2) · [INTEGRATION3](#check-integration3) · [INTEGRATION21](#check-integration21) · [FINAL_INTEGRATION](#check-final_integration) · [INTEGRATION39](#check-integration39)

**Разбор и основания.** [diagnostics-integration.md](../docs/diagnostics-integration.md) · [dtc01-session-lease.md](../verification/project-audit/dtc01-session-lease.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md) · [dtc01-c0-session-timer.md](../verification/project-audit/dtc01-c0-session-timer.md) · [report.md](../verification/project-audit/integration-39-20261121/report.md) · [bench-first-wave.md](../docs/bench-first-wave.md)

**Следующий шаг для продолжения.** Доведи штатный запрос→RX→сеанс→TX13 ответ и события всех подсистем, статусы/очистку. Перепроверь таблицу Toyota/Chery и не придумывай code correspondence. Первичный стенд должен позволять получить реальные сырые S51/S83/ATF, clock, voltage/current если доступны АЦП, output command/qualifier, torque handshake и причины inhibit. Добавь компактный реальный измерительный путь/документированные запросы, если имеющихся недостаточно. Никаких sample values; измерительный протокол должен работать в собираемой паре.

**Приоритет продолжения.** 29

**Исходные условия.** main abd3cba и позднее; docs/bench-first-wave.md; data/bench-first-wave.json; имеющиеся источники/проверки карточки.

**Что сдать.** Полный native diagnostic path и реестр команд/полей; отказные проверки и минимальный протокол после BIN с местом/режимом/критерием измерения; что штатный Chery сканер поддерживает, а что проектный readout.

**Кому удобно продолжить.** Чат 10 — 01a1fa76-b015-7640-a0ba-433b36dcf55f. Это рекомендация, не резерв.

**Кто сейчас выполняет.** Проверить [общий список исполнителей](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/tree/task-board). Перед изменениями занять этот ID и точные файлы.

<a id="dtc-02"></a>
## DTC-02 — Штатный приём BasicCAN для диагностического сеанса

**Требуется разработка** · ТЗ §5, §11

**Сделано.** Закрыт обход service mode/Flash bank, RX15 повторно проверяется после RX14; нижние переходы и общая CAN-компоновка прошли отдельные адресные проверки.

**Осталось.** Установить полный набор RX/service/monitor переходов в итоговый образ и подтвердить банк Flash и время IRQ в совместной конфигурации.

**Критерий результата.** Прогон оригинального пути RX с потерей/перезаписью и ложными кадрами. Учтена граница приложения 0x008000.

**Код.** [targets/lfj8/lfj8_h03_dtc_can.c](../targets/lfj8/lfj8_h03_dtc_can.c) · [targets/lfj8/lfj8_h03_can13.c](../targets/lfj8/lfj8_h03_can13.c) · [targets/lfj8/test_lfj8_h03_dtc_can.c](../targets/lfj8/test_lfj8_h03_dtc_can.c) · [targets/lfj8/lfj8_h03_dtc_rx_queue.c](../targets/lfj8/lfj8_h03_dtc_rx_queue.c) · [targets/lfj8/lfj8_h03_dtc_rx_queue.h](../targets/lfj8/lfj8_h03_dtc_rx_queue.h) · [targets/lfj8/test_lfj8_h03_dtc_rx_queue.c](../targets/lfj8/test_lfj8_h03_dtc_rx_queue.c) · [targets/lfj8/check_h03_dtc_basiccan.py](../targets/lfj8/check_h03_dtc_basiccan.py) · [targets/lfj8/lfj8_h03_dtc_target.c](../targets/lfj8/lfj8_h03_dtc_target.c) · [targets/lfj8/lfj8_h03_dtc_target.h](../targets/lfj8/lfj8_h03_dtc_target.h) · [targets/lfj8/h03_dtc_rx_resident.ld](../targets/lfj8/h03_dtc_rx_resident.ld) · [targets/lfj8/check_h03_dtc_service_gate.py](../targets/lfj8/check_h03_dtc_service_gate.py) · [targets/lfj8/h03_dtc_rx_hook.S](../targets/lfj8/h03_dtc_rx_hook.S) · [targets/lfj8/h03_dtc_rx_redirects.S](../targets/lfj8/h03_dtc_rx_redirects.S) · [targets/lfj8/lfj8_h03_dtc_rx_placement.py](../targets/lfj8/lfj8_h03_dtc_rx_placement.py)

**Что настраивать.** RX14/15 0x001500–0x0016F4, копия 0x808526, разбор около 0x001578. Прямой перехват затрагивает область ниже приложения. Очередь: max_age_bits < 32768 и не больше бюджета CAN13, bit_time_us из настройки шины; непрерывное время микросекунд. Конкретное размещение RAM открыто.

**Проверки.** [PC](#check-pc) · [M32R](#check-m32r) · [INTEGRATION](#check-integration) · [INTEGRATION3](#check-integration3) · [MEMORY4](#check-memory4) · [INTEGRATION21](#check-integration21) · [FINAL_INTEGRATION](#check-final_integration) · [INTEGRATION39](#check-integration39)

**Разбор и основания.** [diagnostics-integration.md](../docs/diagnostics-integration.md) · [lfj8-h03-flash.md](../docs/lfj8-h03-flash.md) · [dtc02-basiccan.md](../verification/project-audit/dtc02-basiccan.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md) · [lfj8-h03-memory-layout.md](../docs/lfj8-h03-memory-layout.md) · [dtc02-resident-target-rx.md](../verification/project-audit/dtc02-resident-target-rx.md) · [report.md](../verification/project-audit/integration-39-20261121/report.md) · [bench-first-wave.md](../docs/bench-first-wave.md)

**Следующий шаг для продолжения.** Доведи штатный запрос→RX→сеанс→TX13 ответ и события всех подсистем, статусы/очистку. Перепроверь таблицу Toyota/Chery и не придумывай code correspondence. Первичный стенд должен позволять получить реальные сырые S51/S83/ATF, clock, voltage/current если доступны АЦП, output command/qualifier, torque handshake и причины inhibit. Добавь компактный реальный измерительный путь/документированные запросы, если имеющихся недостаточно. Никаких sample values; измерительный протокол должен работать в собираемой паре.

**Приоритет продолжения.** 30

**Исходные условия.** main abd3cba и позднее; docs/bench-first-wave.md; data/bench-first-wave.json; имеющиеся источники/проверки карточки.

**Что сдать.** Полный native diagnostic path и реестр команд/полей; отказные проверки и минимальный протокол после BIN с местом/режимом/критерием измерения; что штатный Chery сканер поддерживает, а что проектный readout.

**Кому удобно продолжить.** Чат 10 — 01a1fa76-b015-7640-a0ba-433b36dcf55f. Это рекомендация, не резерв.

**Кто сейчас выполняет.** Проверить [общий список исполнителей](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/tree/task-board). Перед изменениями занять этот ID и точные файлы.

<a id="dtc-03"></a>
## DTC-03 — Все диагностические события и соответствия Toyota/Chery

**Требуется разработка** · ТЗ §11

**Сделано.** ATF fault допускается только с квалифицированным источником времени; native сценарии и отказ часов прошли.

**Осталось.** Подключить реальную характеристику ATF, диагностические пороги и временные пределы; проверить их с датчиком.

**Критерий результата.** Код соответствует фактическому отказу и узлу, статусы подтверждены. Отсутствующий прямой аналог явно обозначен.

**Код.** [diagnostics/chery_dtc.c](../diagnostics/chery_dtc.c) · [targets/lfj8/lfj8_h03_engine_feed.c](../targets/lfj8/lfj8_h03_engine_feed.c) · [docs/ta2005-diagnostic-code-table.csv](../docs/ta2005-diagnostic-code-table.csv) · [tests/test_chery_dtc_table.py](../tests/test_chery_dtc_table.py) · [diagnostics/chery_atf_circuit.c](../diagnostics/chery_atf_circuit.c) · [diagnostics/chery_atf_circuit.h](../diagnostics/chery_atf_circuit.h) · [diagnostics/test_chery_atf_circuit.c](../diagnostics/test_chery_atf_circuit.c) · [diagnostics/verify_atf_circuit.py](../diagnostics/verify_atf_circuit.py) · [targets/lfj8/check_h03_atf_fault.py](../targets/lfj8/check_h03_atf_fault.py) · [targets/lfj8/h03_atf_fault_hook_fixture.c](../targets/lfj8/h03_atf_fault_hook_fixture.c) · [targets/lfj8/lfj8_h03_dtc_target.c](../targets/lfj8/lfj8_h03_dtc_target.c) · [targets/lfj8/lfj8_h03_dtc_target.h](../targets/lfj8/lfj8_h03_dtc_target.h)

**Что настраивать.** Индекс DTC, маски current/history, разрешение записи и пороги монитора.

**Проверки.** [PC](#check-pc) · [M32R](#check-m32r) · [INTEGRATION](#check-integration) · [INTEGRATION3](#check-integration3) · [INTEGRATION21](#check-integration21) · [FINAL_INTEGRATION](#check-final_integration) · [INTEGRATION39](#check-integration39)

**Разбор и основания.** [diagnostics-integration.md](../docs/diagnostics-integration.md) · [dtc03-table.md](../verification/project-audit/dtc03-table.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md) · [dtc03-ta2005-p0710.md](../verification/project-audit/dtc03-ta2005-p0710.md) · [report.md](../verification/project-audit/integration-39-20261121/report.md) · [bench-first-wave.md](../docs/bench-first-wave.md)

**Зависит от.** [H03-05](#h03-05), [TOY-06](#toy-06)

**Следующий шаг для продолжения.** Доведи штатный запрос→RX→сеанс→TX13 ответ и события всех подсистем, статусы/очистку. Перепроверь таблицу Toyota/Chery и не придумывай code correspondence. Первичный стенд должен позволять получить реальные сырые S51/S83/ATF, clock, voltage/current если доступны АЦП, output command/qualifier, torque handshake и причины inhibit. Добавь компактный реальный измерительный путь/документированные запросы, если имеющихся недостаточно. Никаких sample values; измерительный протокол должен работать в собираемой паре.

**Приоритет продолжения.** 31

**Исходные условия.** main abd3cba и позднее; docs/bench-first-wave.md; data/bench-first-wave.json; имеющиеся источники/проверки карточки.

**Что сдать.** Полный native diagnostic path и реестр команд/полей; отказные проверки и минимальный протокол после BIN с местом/режимом/критерием измерения; что штатный Chery сканер поддерживает, а что проектный readout.

**Кому удобно продолжить.** Чат 10 — 01a1fa76-b015-7640-a0ba-433b36dcf55f. Это рекомендация, не резерв.

**Кто сейчас выполняет.** Проверить [общий список исполнителей](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/tree/task-board). Перед изменениями занять этот ID и точные файлы.

<a id="dtc-04"></a>
## DTC-04 — Хранение DTC после выключения питания

**Требуется разработка** · ТЗ §5, §11

**Сделано.** Без постоянного носителя нет ложного успешного clear; штатный запрос 14FF00 потребляется, P0710 сохраняется. Restore блокируется при неподходящем банке Flash.

**Осталось.** Реализовать и привязать постоянный NVM backend с доказанными двумя стираемыми блоками, владением записью и отказами питания; read-only array path не является записью.

**Критерий результата.** Перезапуск и прерванная запись не восстанавливают очищенную или повреждённую историю.

**Код.** [diagnostics/chery_dtc.h](../diagnostics/chery_dtc.h) · [diagnostics/chery_dtc.c](../diagnostics/chery_dtc.c) · [diagnostics/chery_dtc_journal.c](../diagnostics/chery_dtc_journal.c) · [diagnostics/chery_dtc_journal.h](../diagnostics/chery_dtc_journal.h) · [diagnostics/test_chery_dtc_journal.c](../diagnostics/test_chery_dtc_journal.c) · [targets/lfj8/lfj8_h03_nvm.c](../targets/lfj8/lfj8_h03_nvm.c) · [targets/lfj8/check_h03_nvm.py](../targets/lfj8/check_h03_nvm.py) · [targets/lfj8/lfj8_h03_nvm.h](../targets/lfj8/lfj8_h03_nvm.h) · [targets/lfj8/test_lfj8_h03_nvm.c](../targets/lfj8/test_lfj8_h03_nvm.c) · [targets/lfj8/check_h03_dtc_basiccan.py](../targets/lfj8/check_h03_dtc_basiccan.py) · [targets/lfj8/lfj8_h03_dtc_can.c](../targets/lfj8/lfj8_h03_dtc_can.c) · [targets/lfj8/lfj8_h03_dtc_can.h](../targets/lfj8/lfj8_h03_dtc_can.h) · [targets/lfj8/lfj8_h03_dtc_native.c](../targets/lfj8/lfj8_h03_dtc_native.c) · [targets/lfj8/lfj8_h03_dtc_native.h](../targets/lfj8/lfj8_h03_dtc_native.h) · [targets/lfj8/h03_nvm_native_fixture.c](../targets/lfj8/h03_nvm_native_fixture.c) · [targets/lfj8/lfj8_h03_nvm_native.c](../targets/lfj8/lfj8_h03_nvm_native.c) · [targets/lfj8/lfj8_h03_nvm_native.h](../targets/lfj8/lfj8_h03_nvm_native.h)

**Что настраивать.** Целевая область NVM и политика износа ещё не назначены.

**Проверки.** [PC](#check-pc) · [INTEGRATION](#check-integration) · [INTEGRATION3](#check-integration3) · [MEMORY4](#check-memory4) · [INTEGRATION21](#check-integration21) · [FINAL_INTEGRATION](#check-final_integration) · [INTEGRATION39](#check-integration39)

**Разбор и основания.** [diagnostics-integration.md](../docs/diagnostics-integration.md) · [lfj8-h03-flash.md](../docs/lfj8-h03-flash.md) · [dtc04-journal.md](../verification/project-audit/dtc04-journal.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md) · [lfj8-h03-memory-layout.md](../docs/lfj8-h03-memory-layout.md) · [dtc04-retired-history.md](../verification/project-audit/dtc04-retired-history.md) · [report.md](../verification/project-audit/integration-39-20261121/report.md) · [bench-first-wave.md](../docs/bench-first-wave.md)

**Зависит от.** [H03-04](#h03-04)

**Следующий шаг для продолжения.** Доведи реальный read/write/erase backend с геометрией и исключением стёртых программных областей, two-slot commit и поведение при прерывании питания. Не назначать два пустых блока по догадке. Если безопасная запись объективно не выводится из имеющихся данных, доведи bootable non-destructive inspection/readout и явный статус unavailable persistence для первичного стенда, сохрани финальное требование открытым. Такую деградацию нельзя выдавать за полное выполнение ТЗ. Подготовь независимый backend без fixture qualified_adaptation_blocks.

**Приоритет продолжения.** 32

**Исходные условия.** main abd3cba и позднее; docs/bench-first-wave.md; data/bench-first-wave.json; имеющиеся источники/проверки карточки.

**Что сдать.** Рабочий backend или конкретная доказанная граница его доступности, профиль носителя/проверка восстановления, подлинные Flash-адреса; телеметрия для получения недостающего после BIN.

**Кому удобно продолжить.** Чат 9 — 01a1fa76-922b-7b11-a2f2-346a15d1dc95. Это рекомендация, не резерв.

**Кто сейчас выполняет.** Проверить [общий список исполнителей](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/tree/task-board). Перед изменениями занять этот ID и точные файлы.

<a id="aud-01"></a>
## AUD-01 — Программный аудит истории E4M3

**Завершено в указанном объёме** · ТЗ §10

**Сделано.** Объединённый результат 21.11.2026: Вторая порция AUD-01: неполный архив отклоняется. Повторно прошли шесть тестов и сверка 8 файлов, 3 групп и 1057 диапазонов. Основана на отдельной порции e340c61.

**Осталось.** Аппаратное подтверждение и целевые профили остаются в ECU-02.

**Критерий результата.** Закрыт объём отчёта и программного исследования. Штатная работа установленного ECU не объявлена проверенной.

**Код.** [data/e4m3-diff.json](../data/e4m3-diff.json) · [targets/bosch/verify.py](../targets/bosch/verify.py) · [targets/bosch/replay_e4m3_torque.py](../targets/bosch/replay_e4m3_torque.py)

**Что настраивать.** S04 идентифицировать по SHA-256, а не повторяющемуся имени BENCH.

**Проверки.** [SOURCES](#check-sources) · [BOSCH](#check-bosch) · [E4AUDIT](#check-e4audit) · [INTEGRATION3](#check-integration3) · [FINAL_INTEGRATION](#check-final_integration)

**Разбор и основания.** [e4m3-audit.md](../docs/e4m3-audit.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md)

<a id="h03-01"></a>
## H03-01 — Выбранная основа 9E1C и карта подключения

**Завершено в указанном объёме** · ТЗ §5

**Сделано.** Объединённый результат 21.11.2026: Сверка локальных чтений LFJ8-18-9E1C выдаёт полный MATCH только после сравнения всех 524288 байт, считает пропуски и пересекающиеся расхождения. Пять новых тестов, два теста идентификации и SOURCES прошли. На срезах точного H03 проверены полный, частичный и конфликтующий readback. Отчёт h03-01-readback.md. Физическое считывание и выпуск открыты.

**Осталось.** Физические параметры отдельных каналов учитываются в H03-05 и MODE-02.

**Критерий результата.** Для выбора платформы повторное подтверждение 9E1D и запуск PCMflash не нужны.

**Код.** [tools/inspect_lfj8_tcm.py](../tools/inspect_lfj8_tcm.py) · [tools/verify_sources.py](../tools/verify_sources.py)

**Что настраивать.** H03 LFJ8-T-D.bin, 524 288 байт. S05/S06 только исторические доноры.

**Проверки.** [SOURCES](#check-sources) · [INTEGRATION3](#check-integration3) · [FINAL_INTEGRATION](#check-final_integration)

**Разбор и основания.** [lfj8-target-identity.md](../docs/lfj8-target-identity.md) · [lfj8-wiring-sources.md](../docs/lfj8-wiring-sources.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md)

<a id="org-01"></a>
## ORG-01 — Основа проекта и локальная работа

**Завершено в указанном объёме** · ТЗ §1

**Сделано.** После интеграции 39 порций объединены ещё 11 опубликованных SHA. Обновлены точные остатки и доказательства общей компоновки; готовность BIN учитывается отдельно.

**Осталось.** Окончательные BIN и оставшиеся привязки ведутся в REL-01/H03-03/H03-04.

**Критерий результата.** Файлы доступны, источник каждой сборки прослеживается.

**Код.** [tools/package_workset.py](../tools/package_workset.py) · [tools/task_coordination.py](../tools/task_coordination.py) · [tests/test_task_coordination.py](../tests/test_task_coordination.py) · [tools/check_integrated_h03.py](../tools/check_integrated_h03.py)

**Что настраивать.** Публикация в GitHub возобновлена по указанию владельца 20.11.2026. Учёт чатов отделён от готовности прошивки.

**Проверки.** [SOURCES](#check-sources) · [COORD](#check-coord) · [INTEGRATION](#check-integration) · [INTEGRATION3](#check-integration3) · [MEMORY4](#check-memory4) · [COORD_REVIEW](#check-coord_review) · [FINAL_INTEGRATION](#check-final_integration) · [COORD_HANDOFF](#check-coord_handoff) · [INTEGRATION39](#check-integration39) · [INTEGRATION11](#check-integration11) · [BENCH_PREP](#check-bench_prep)

**Разбор и основания.** [decisions.md](../docs/decisions.md) · [multi-chat.md](../docs/multi-chat.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md) · [lfj8-h03-memory-layout.md](../docs/lfj8-h03-memory-layout.md)

<a id="src-01"></a>
## SRC-01 — Реестр происхождения и контроль исходников

**Завершено в указанном объёме** · ТЗ §9

**Сделано.** Объединённый результат 21.11.2026: Опубликованы только тесты происхождения и отчёт. Повторно прошли пять тестов проверки исходников и два теста определения H03. Результат для проверки интегратором.

**Осталось.** Для новых материалов продолжать реестр. Архивные S05/S06 заново не нужны для идентификации H03.

**Критерий результата.** Зафиксированы роли, версии и SHA-256 отдельно от Git blob. Новые материалы не подменяют выбранную основу.

**Код.** [data/sources.json](../data/sources.json) · [controller/vendor/toyota/manifest.json](../controller/vendor/toyota/manifest.json) · [tools/verify_sources.py](../tools/verify_sources.py)

**Что настраивать.** Активная цель H03. S05=PCM SuperH, S06/H02=9E1B для сравнения.

**Проверки.** [SOURCES](#check-sources) · [INTEGRATION3](#check-integration3) · [FINAL_INTEGRATION](#check-final_integration)

**Разбор и основания.** [decisions.md](../docs/decisions.md) · [integration-next-tasks.md](../docs/integration-next-tasks.md)

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

<a id="check-service_guard"></a>
### SERVICE_GUARD — Запрет прямой и отложенной сервисной записи

```powershell
python -B targets/lfj8/check_h03_service_guard.py --base $h03 --gcc $m32rGcc --storage-report $storageReport --out $guardReport
```

**Последний сохранённый результат.** [2026-11-20-service-guard.json](../verification/project-audit/2026-11-20-service-guard.json) · [native.json](../verification/project-audit/service-guard/native.json) · [all-bindings.json](../verification/project-audit/service-guard/all-bindings.json)

<a id="check-integration21"></a>
### INTEGRATION21 — 28 новых результатов и общая проверка 21.11.2026

```powershell
Команды и границы: docs/lfj8-h03-memory-layout.md. Итоговая компоновка ожидаемо FAIL_BINDINGS; готовый BIN не создан.
```

**Последний сохранённый результат.** [2026-11-21-integration.json](../verification/project-audit/2026-11-21-integration.json) · [PC-CHECKS.json](../verification/project-audit/integration-20261121/pc/PC-CHECKS.json) · [standard-link.json](../verification/project-audit/integration-20261121/standard-link.json) · [summary.json](../verification/project-audit/integration-20261121/native/summary.json) · [summary.json](../verification/project-audit/integration-20261121/components/summary.json) · [bindings.json](../verification/project-audit/integration-20261121/bindings.json) · [summary.json](../verification/project-audit/integration-20261121/extra/summary.json)

<a id="check-coord_review"></a>
### COORD_REVIEW — Свободное продолжение review и сохранение очереди сдачи

```powershell
python -B -m unittest discover -s tests -v
```

**Последний сохранённый результат.** [unit-tests.txt](../verification/project-audit/review-continuations/unit-tests.txt) · [migration-preview.json](../verification/project-audit/review-continuations/migration-preview.json) · [README.md](../verification/project-audit/review-continuations/README.md)

<a id="check-final_integration"></a>
### FINAL_INTEGRATION — Общая сборка 42 порций и локального CAN-01

```powershell
python -B tools/build_pc_checks.py --cc $zig --out $out/pc
python -B tools/check_integrated_h03.py --suite native --base $h03 --gcc $m32rGcc --controller $out/controller/rbm_u340e_m32r_be.o --out $out/native-final
python -B tools/check_h03_image_layout.py --base $h03 --gcc $m32rGcc --controller $out/controller/rbm_u340e_m32r_be.o --bridge $out/bridge/lfj8_9e1c_m32r.o --profile padding-candidate --cpu-test --out $out/placed-padding
```

**Последний сохранённый результат.** [README.md](../verification/project-audit/final-integration-20261121/README.md) · [PC-CHECKS.json](../verification/project-audit/final-integration-20261121/pc/PC-CHECKS.json) · [summary.json](../verification/project-audit/final-integration-20261121/native-final/summary.json) · [protected_padding.json](../verification/project-audit/final-integration-20261121/combined-profile/protected_padding.json)

<a id="check-s01_cold"></a>
### S01_COLD — Холодная ветвь Toyota и новая общая композиция

```powershell
python -B targets/lfj8/check_toyota_cold_init.py --r3 $r3 --controller-lib $controllerLibrary --cc $zig --out $report
```

**Последний сохранённый результат.** [toy05-s01-cold-state.md](../verification/project-audit/toy05-s01-cold-state.md) · [toy05-s01-cold-state.json](../verification/project-audit/toy05-s01-cold-state.json) · [combined-summary.json](../verification/project-audit/startup-integration-20261121/combined-summary.json) · [placed-layout.json](../verification/project-audit/startup-integration-20261121/placed-layout.json)

<a id="check-coord_handoff"></a>
### COORD_HANDOFF — Очередь, разделение резервов и передача Codex/Claude

```powershell
python -B -m unittest discover -s tests -p test_task_coordination.py -v
python -B -m unittest discover -s tests -p test_project_status.py -v
python -B tools/project_status.py --check
```

**Последний сохранённый результат.** [task_coordination.log](../verification/project-audit/coordination-handoff-20261121/task_coordination.log) · [project_status.log](../verification/project-audit/coordination-handoff-20261121/project_status.log) · [registry-check.json](../verification/project-audit/coordination-handoff-20261121/registry-check.json) · [integration-next-tasks.md](../docs/integration-next-tasks.md)

<a id="check-integration39"></a>
### INTEGRATION39 — Общая сборка 39 новых результатов, 21.11.2026

```powershell
Команды каждого фактического запуска сохранены в build-summary.json, target-summary.json, corrected-summary.json и final-summary.json рядом с отчётом. check-composition.py сохраняет честный FAIL_BINDINGS и не выпускает BIN.
```

**Последний сохранённый результат.** [report.md](../verification/project-audit/integration-39-20261121/report.md) · [summary.json](../verification/project-audit/integration-39-20261121/summary.json) · [composition.json](../verification/project-audit/integration-39-20261121/composition.json) · [roundtrip.json](../verification/project-audit/integration-39-20261121/roundtrip.json)

<a id="check-integration11"></a>
### INTEGRATION11 — Общая сборка 11 новых порций и размещение таблиц

```powershell
Команды сохранены в build-summary.json, target-summary.json, placement-summary.json и final-summary.json рядом с отчётом. check-composition.py не выпускает BIN и сохраняет FAIL_BINDINGS.
```

**Последний сохранённый результат.** [report.md](../verification/project-audit/integration-11-20261121/report.md) · [summary.json](../verification/project-audit/integration-11-20261121/summary.json) · [composition.json](../verification/project-audit/integration-11-20261121/composition.json) · [roundtrip.json](../verification/project-audit/integration-11-20261121/roundtrip.json)

<a id="check-bench_prep"></a>
### BENCH_PREP — Пересверка и сборка байтов H03

```powershell
build-summary.json; python -B -m unittest tests.test_h03_image и тесты размещения; repeat-composition.py сохраняет FAIL_BINDINGS.
```

**Последний сохранённый результат.** [report.md](../verification/project-audit/bench-first-20261121/report.md) · [summary.json](../verification/project-audit/bench-first-20261121/summary.json) · [composition.json](../verification/project-audit/bench-first-20261121/composition.json)
