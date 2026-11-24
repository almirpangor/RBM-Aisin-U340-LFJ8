# Кто сейчас работает над проектом

Обновлено UTC: **2026-11-24T06:41:14+00:00**. Изменение № **1009**.

Это общий учёт исполнителей. Он не меняет готовность функции по ТЗ и не подтверждает выпуск BIN.
Команды занятия и обновления задачи — в tools/task_coordination.py основной ветки.
Задача и файлы заняты только в состояниях «Выполняется» и «Ожидает».
«На проверке» сохраняет сданный коммит в отдельной очереди и освобождает резерв для продолжения.
Для продолжения включить относящиеся к задаче или файлам сданные коммиты в свою ветку и выполнить новый claim.
Нужен tools/task_coordination.py из актуальной main: старые клиенты не записывают формат доски 2.
Давняя отметка не освобождается автоматически. Возобновившийся чат обязан проверить свой claim_id.

Каталог задач взят из main 3fe28938163e1dddc98a37733c229390ab7f0fff.

**В работе: 12 · Ожидают с резервом: 1 · Порций на проверке: 22.**

Занятость определяется подтверждёнными резервами, а не присутствием чата онлайн. Предыдущие исполнители вынесены в историю.

## Сейчас выполняются

| Приоритет | Задача | Исполнитель | Обновление UTC | Текущий шаг / причина ожидания |
| --- | --- | --- | --- | --- |
| 6 | TOY-05 — Обучение и сохранение адаптаций | Codex 12 — TOY-05, стартовое состояние первой стендовой пары \[01a1fa79-a9fd-70c0-80a3-f59592edaf79\] | 2026-11-21T09:13:05+00:00 | По поручению ведущего переношу сброс DTC RAM в защищённый холодный вход. Application C и транспорт остаются у текущих владельцев. |
| 10 | CAN-03 — Штатный запуск, IRQ и восстановление CAN0 | Codex чат 3 — стендовый CAN-сервис H03 \[codex-fea1b366-66b6-4667-8206-915153ca1033\] | 2026-11-21T09:10:01+00:00 | По передаче ведущего резервирую application.c/h, CAN revoke и свободные fixtures. Разделяю блокировку управления и жизнь диагностики; общие binding/strategy и проверки других чатов не правлю. |
| 13 | ECU-01 — Проверочная сборка Bosch E4M3 | Copilot — Bosch paired release \[9d4fcd7f-8d30-447e-b31d-6889553c0e20\] | 2026-11-24T06:31:36+00:00 | ECU-01 software continuation rerun complete: ordinary/qualified candidates repeat exactly; 51 integrity records; native ordinary/torque profiles PASS OFFLINE_ONLY; sourced Toyota mapping and current pair hardware identity remain blocked. |
| 17 | H03-03 — Единое расписание и запуск приложения H03 | Чат 1 — OEM-переходы стендовой H03 \[codex-7bd19ea4-0004-4aec-90c4-f2c6e804c046\] | 2026-11-21T09:12:39+00:00 | Проверены все 23 корня ранней пробы объёма. Дополняю защиту ожидания: ограниченный счётчик итераций повторно вызывает guard при остановке TML0/TOP10. Для теста добавлен файл h03_phase_wait_fixture.c. |
| 22 | VSS-02 — Кинематика и параметры реальной скорости | Copilot LFJ8 sensor measurement contract \[copilot-lfj8-sensor-contract-a4a37091\] | 2026-11-24T05:10:25+00:00 | Deliver source-supported H03 S51/S83/ATF/TML0/TML1 measurement contract and unresolved hardware parameters; no BIN or aggregate layout changes. |
| 25 | MODE-02 — Подключение селектора, Tiptronic и Overdrive | LFJ8 selector measurement contract \[b9841cd6-bb32-4ab5-a5d7-3d1df09009f5\] | 2026-11-24T05:09:17+00:00 | Independent MODE-02 slice: document executable ADC/input commissioning and exact source-vs-hardware evidence; do not change production profile or shared aggregates. |
| 26 | MODE-03 — Окончательная политика режимов | Copilot — MODE-03 manual policy continuation \[copilot-mode03-20261124-0829-9b51a672-80d4-41d8-b003-2ccf7df38731\] | 2026-11-24T05:59:48+00:00 | Продолжаю MODE-03 только в пределах исходно разрешённых пяти путей; сохраняю физически неподтверждённые selector/ADC значения явными блокерами. Проверенный MODE-03 review d77a559150a3c586ca50caa4aa64488b4f02ce22 и обязательный CAN-01 review 50202944bbe2206d79c948757752b5a3e7669007 включены в ветку. |
| 27 | REL-01 — Два целевых BIN и воспроизводимый комплект | Copilot — REL-01 package evidence follow-up \[bd412180-9ccb-4a23-a04a-ad23931a72a0\] | 2026-11-24T06:41:00+00:00 | Fresh follow-up for the published report update at 77f23b8 after the previous review lease ended; no further file changes planned, verify the existing 24-test evidence note and submit the exact SHA. |
| 30 | DTC-02 — Штатный приём BasicCAN для диагностического сеанса | Codex чат 10 — чтение статуса NVM \[01a1fa76-b015-7640-a0ba-433b36dcf55f\] | 2026-11-21T09:12:26+00:00 | Поверх сданного a1e1733 включён DTC-04 4842a32. Добавляю условную страницу статуса NVM/SFR для no-media профиля, проверяю реальные ответы через TX13. Без чтения массива, записи и положительного ACK очистки. |
| 31 | DTC-03 — Все диагностические события и соответствия Toyota/Chery | Copilot — native diagnostic field provider \[copilot-71f474e418d946d2ab3d84e52afb56f1\] | 2026-11-24T06:41:14+00:00 | Implement the DTC-03 source-backed diagnostic event/readout contribution and field contract without editing DTC-02/DTC-04 transport or storage paths, shared registry/audit files, or inventing thresholds/ages/measurements. |
| 32 | DTC-04 — Хранение DTC после выключения питания | Чат 9 — холодный старт и транспорт NVM \[01a1fa76-922b-7b11-a2f2-346a15d1dc95\] | 2026-11-21T09:11:30+00:00 | Включён 4842a32. Совместный офлайн-прогон действующего холодного callback, профиля NVM и штатного CAN-диагностического пути. Проверю отсутствие ложной очистки и поведение после перепривязки. Файлы действующих резервов TOY-05/DTC-02/CAN-03 не затрагиваю. |
| — | ORG-01 — Основа проекта и локальная работа | Ведущй — общая сборка и задания для стендовой пары \[codex-integration-01a1f76d-20261120\] | 2026-11-21T09:15:21+00:00 | Опубликованы план и общая инфраструктура 3fe2893. Ведётся приёмка 12 чатов; локально объединены 9/5/10, native NVM/sensor/BasicCAN readout повторно PASS. Выявлен и передан CAN-03 дефект отключения диагностики при недостоверных датчиках. Окончательный native ELF/BIN ещё не собран. |

## Ожидают — резерв сохранён

| Приоритет | Задача | Исполнитель | Обновление UTC | Текущий шаг / причина ожидания |
| --- | --- | --- | --- | --- |
| 11 | CAN-04 — Запрос снижения момента по RB | Copilot App — запрос снижения момента CAN LFJ8 \[copilot-416d2a7e-79e0-4acb-8e40-27807c492e55\] | 2026-11-23T20:28:41+00:00 | Запуск M32R GCC 4.8.0 собран до probe-стадии: binutils/source downloaded, MSYS2/MinGW installed, but GCC 4.8 build probes fail in this host; WSL unavailable because virtualization is disabled. No unverified or fake TCM/Bosch BIN produced. |


## Результаты на проверке — резерв свободен

Эти результаты остаются доступны интегратору, даже если другой чат уже продолжает задачу.
Новый исполнитель сначала включает нужные коммиты в свою ветку. claim проверяет их наличие.

| Задача | Автор | Коммит | Claim ID для приёмки | Результат |
| --- | --- | --- | --- | --- |
| CAN-01 | Codex чат 2 — Task 2 и профиль двигателя для первой стендовой пары | [3def8b732d27](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/commit/3def8b732d271760e8f62c4e9e6b5b7d1f53804f) | 1bfd0b8442764a5e8a833763cc57815a | Native Task 2 engine context and guarded CAN RX. Host and M32R replay PASS; 68 phase, 20 CAN owner scenarios and 41 PC stages. Scratch composition resolves fixture_engine_context (+636 Flash, 0 static RAM); remaining integration inputs in verification/bench-wave/chat-2/handoff.json. No hardware validation or paired BIN. |
| CAN-01 | Copilot — LFJ8 CAN and torque | [50202944bbe2](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/commit/50202944bbe2206d79c948757752b5a3e7669007) | 43c64ae0c01a43088c77386a743171c9 | Published commit 50202944bbe2206d79c948757752b5a3e7669007. PC evidence: controller host tests PASS under GCC 16.2 after demoting only legacy array-parameter, misleading-indentation, and missing-braces warnings; input-binding fixture compiled with -Werror and PASS; exact-H03 engine-context host replay PASS. M32R evidence: GCC 4.8.0 target m32r-elf; controller target build/simulator suite PASS; check_h03_input_binding.py PASS on M32R simulator; exact-H03 engine-context replay PASS on host and M32R simulator. H03 base: 524288 bytes, SHA-256 844a11b809cda1f2ccaf90cb6a75666009487ccedd2e8190b7eb46137b855544. Pinned Bosch trace SHA-256 e9df9cbcae6eb741b9863688f7bbacd16f19064c063b76549f8b56939ca03b4b. Test ELF SHA-256 43a8448beb0b27773034fc4363f4236a2f92be9fb8d8507862a537089f06e716; M32R controller object SHA-256 13b42c89f3af237bbdc1307149918328561f0226f1443706d53160fc23c36ead. Simulator --version is unsupported; executable SHA-256 85D3CAD2770065C4F4A31571C924F092B8AA1AAC9C6C22F504A64E1003E87F38. Hardware not tested; no flashable image or release BIN created. Full release target-link/integrity gates remain outstanding. GCC 4.8 reports stack-usage computation unsupported for M32R. Independent FA7B fallback is unavailable and remains FF; timing values are engineering bounds, not measurements. project_status --check still reports changed files pending review/retest; no shared audit/registry files were modified. |
| DTC-02 | Codex чат 10 — диагностика H03 для стенда | [a1e173336874](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/commit/a1e173336874cb52dae2bb75f4cf4287df105dff) | 8d2e9979b8b94adab47c6ca68b65d7f6 | Чат 10. Нативный стендовый readout 13 страниц через BasicCAN/C0/TX13, включая полный 3-кадровый ответ TML0/TML1 с Flow Control. 41 этап ПК, S03 96, 18 сравнений IRQ, 9 сервисных и 40 ATF проверок. История сохраняется и ACK не выдаётся без DTC-04 backend. Интеграция --binding-source, +1064 байта Flash к той же модели, RAM без прироста, FAIL_BINDINGS. Контракт verification/bench-wave/chat-10/handoff.json. Без прошивки. |
| DTC-03 | Copilot App — independent DTC-03 ATF evidence | [fd3f5494a3c1](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/commit/fd3f5494a3c1fdb9f862c9cd84a6c53ee0875ec6) | 6f672879c0094563b3ad7fef61831ed9 | Independent ATF qualification guard and focused stale/wrap/oversize/invalid tests; project_status check PASS and only four claimed evidence files changed. C fixture not run: no zig/gcc/cl toolchain in worktree/PATH and .sources/R1 unavailable. Real ATF thresholds, measured max_age_us, H03 integration, BIN and hardware remain open. |
| DTC-03 | Copilot App — DTC-03 M32R verification | [801bc261d28d](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/commit/801bc261d28d3441e8cd6023473330489a4ce805) | 603dc4c445b846078f6c08ebe2f5ae81 | Recorded passing host GCC 16.2 and M32R GCC 4.8 component fixtures, exact output hashes, and fresh project_status RETEST_REQUIRED boundary in verification/project-audit/dtc03-m32r-rerun.json. Exact H03 image path and R1/R2 donor paths were unavailable in this worktree; coordinator has a prior independent H03 check result. DTC-02/DTC-04 checks were intentionally not run because their claims remain active. Hardware, image/BIN, thresholds, and measured max_age_us remain false/open. |
| DTC-03 | Copilot — ATF component evidence | [84f49e6f164f](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/commit/84f49e6f164f2097023b0baa9ab26b83fea56ed5) | 8e8333c68a8848a6878a3cb87d244a76 | Published focused DTC-03 ATF host GCC and M32R simulator reruns; evidence JSON refreshed with artifact hashes. Component fixtures PASS. Exact-H03 and S03/R1 evidence remain unavailable here; thresholds/age and hardware remain unmeasured; no production image or alias export claimed. |
| DTC-04 | Чат 9 — стендовый NVM H03 | [4842a325a0fa](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/commit/4842a325a0fa14c14c1fd5ccb48f9afc2c0bdc29) | fdfd811485f4417a8f450b2e455bc6e3 | Чат 9. Профиль NVM без носителя для первого стенда: штатная база S01, холодный DTC, явный NO_ASSIGNED_MEDIA и native read-only статус SFR/32-байтовый счётчик. Единственные пустые сектора 4/7 заняты резидентом и приложением. NVM ПК/M32R, BasicCAN 18+18, 22 native с двумя повторными проверками и 91 тест компоновки прошли. В модели с реальным bench профилем qualified_adaptation_blocks исключён, 14 внешних символов остаются. Контракт, карта, память и результаты: verification/bench-wave/chat-9/handoff.json. Запись и аппаратная приёмка открыты. |
| ECU-01 | Codex чат 8 — Bosch ST10 для стендовой пары | [9312c056ee46](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/commit/9312c056ee46e8f0495a64840bb82b722c1ee9ca) | bb95576349fc4befa4af7a3779ddb4ae | Нативный RPM-допуск RB подключён к START/REFRESH и трём ветвям ST10; CANCEL сохранён. 51 запись целостности, проверены ordinary, T4, парные сценарии. OFFLINE_ONLY; Toyota raw-контракт и остаток в verification/bench-wave/chat-8/handoff.json. |
| H03-04 | Codex H03-04 — ранний допуск IRQ и стендовый профиль SPI/PSW | [2718128ed693](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/commit/2718128ed693b9fa2f69da981a7e316e7b106fa1) | 734b4f9d3a9c43f6aaa67927cf88ab12 | Стендовый профиль и native boot owner, 5 ссылок разрешены в общей композиции. Оба reset, DMA4, service и Virtual Flash PASS в M32R; 94 теста. Полный link и стек от foreground/IRQ отдельно; нижнюю Flash должен доставить квалифицированный режим записи. Подключение и точные результаты в verification/bench-wave/chat-6/handoff.json. |
| H03-04 | Copilot H03-04 memory integration | [c1c6347c36f5](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/commit/c1c6347c36f55606f0a89e32f975173b8c6520ad) | 2287692bc6564719826ff62c12a7d829 | Published exact SHA. 94 H03 PC tests and 6 storage tests pass; M32R RAM-owner replay not run (worktree lacks local/project-paths.json, H03 donor and m32r-elf-gcc). project_status --check flags retest. Full native link/stack proof, physical SPI/PSW high-water and lower-Flash delivery remain open; no readiness claim. |
| H03-04 | Copilot H03-04 software-only continuation | [f3a320fe7c66](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/commit/f3a320fe7c66dc9f258f23ec14abbf2e5c0d2c60) | 2c436323b8804fc3b5ce732970b858a4 | Published software-only guard update. RAM admission now requires at least the existing H03 profile reserves (SPI 1040 B, PSW 64 B); M32R compilation and boundary tests cover exact fit, under-reserve, and misalignment. Profile/placement Python tests: 8 pass; checker imports; diff check passes. Full donor-based M32R replay, final linked stack proof, physical high-water, and hardware qualification remain open; no BIN. |
| H03-05 | Codex 7 H03-05 bench outputs | [0a9523b203a2](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/commit/0a9523b203a2cae2b21a81da4c14ce910b570ed3) | 9e7f752b72ac4c3ab97038f13486690a | Чат 7: native bench profile запускает phase_startup с mask=0 и без actuator callbacks. D/E/F, Pressure A и TIO9 отозваны в обеих штатных фазах, есть снимок AN3/таймеров. Native 22/22, components 8/8; common small через --binding-source 106944 байта, 14 нерешённых ссылок. Подключение обоих redirect и типизированного alias, пределы и измерения в verification/bench-wave/chat-7/handoff.json. Активный силовой допуск открыт. |
| MODE-02 | Чат 11 · MODE-02, стендовый профиль селектора и ручных режимов | [2d3569d4f7c9](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/commit/2d3569d4f7c9b4cf23fdbf1d262b7c5136e9d667) | 027a36c5f3ef44518bf3ba1bbaf2f464 | Чат 11. Стендовые профили AN2 и ручных режимов подключены штатными точками; проверены 6 положений, независимый P/N, ручной цикл S1/S2, дребезг, удержание/отзыв и логика OD. 41 этап ПК, 216 тестов, native 22, components 8. Физическая карта, поставщики Toyota и порядок допуска релизов остаются явными зависимостями. verification/bench-wave/chat-11/handoff.json. |
| REL-01 | Copilot REL-01 integration | [6465a78db4b6](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/commit/6465a78db4b6a73643e7d4fdcdf1aeb6392a8e33) | 36a5a75d3ef44ab0a4cde5678f96bb0a | Published wrapper signature correction. 51 coordination/package tests pass and diff --check passes. Corrected expanded suite reaches real layout and fails CAN tail overflow 4060 bytes; padding layout fails seven unresolved production bindings. Native/components and project status pass; no BIN emitted. |
| REL-01 | Copilot — REL-01 package gate | [13bbf2bc00c2](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/commit/13bbf2bc00c2d53e01ad1d8cdfd57fbe69cc856c) | 9fafa66119bd4d68a67ffed2cc934265 | Rejects explicit UNQUALIFIED/ADDRESS_MODEL_ONLY image statuses and bench_pair_ready:false in firmware-pair packaging; 11 package tests pass. Evidence-only packaging remains allowed. project_status --check still flags these changed paths and prior integration wrapper for review/retest; no BIN emitted. |
| REL-01 | Copilot — REL-01 package guard documentation | [844a73b5b40b](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/commit/844a73b5b40b6263273a30a791549d53676091a5) | 9c7cba27017d403db01fb18c16725dd9 | Documents that firmware-pair packaging rejects UNQUALIFIED/ADDRESS_MODEL_ONLY output and bench_pair_ready:false while evidence archives remain available; git diff --check passes. |
| REL-01 | Copilot — REL-01 explicit TCM bench readiness | [c812612a35ee](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/commit/c812612a35ee30ef0b4a0295be70b24393db4250) | b29ec3655b034f3c9d994624701a3e5a | Firmware-pair packaging requires explicit TCM bench_pair_ready:true and rejects unqualified/address-model-only statuses; evidence-only packaging remains allowed. H03/image+package tests pass 24/24; git diff --check passes. |
| TOY-02 | Чат 4 — нативные входы Toyota и сырой Bosch CAN | [7a7ac7f97d32](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/commit/7a7ac7f97d328cd6f5de88f02c043b1f8b21efac) | 5d84c76a488c45b6bf0b82f1f835af45 | Сырой контракт Bosch 0x6B2, приём стабильной BasicCAN копии и штатный H03 capture вместо test_input_capture собраны. ПК/M32R RX→GP прошли; найдены все 8 writer S01 и бит режима, сверены 198 инструкций, повторены C167 и аудит CAN. Остались издатель, dispatch, порядок первого release и обоснованные project_load/read_local. Handoff verification/bench-wave/chat-4/handoff.json. |
| TOY-06 | Copilot TOY-06 SLU command | [4a5565f145d2](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/commit/4a5565f145d2a7b3aad81d35cef70b8251f4a24a) | d555acaf033d4dd2a9f3e77e36f3d6dd | Published six-file software-only SLU demand and revoke change. git diff --check and Python AST/ctypes layout checks pass. Focused host/Zig and M32R execution blocked: local project-paths.json and .sources/R1/.sources/R2 are absent; Zig and M32R GCC are not on PATH. No hardware/channel/response verification; no profile, scale, or mapping added. |
| VSS-02 | Codex 5 — нативный стендовый профиль TML0/S51/S83/ATF | [18dcf51f3a76](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/commit/18dcf51f3a765f2d660e142003999cbf627782f4) | cee15d1377aa4207a89e2eb78dd96995 | Нативный OEM_NOMINAL профиль TML0/TML1, S51/S83/ATF и raw capture опубликован. M32R PASS. Интегратору подобрать размещение и подключить согласованный транспорт raw capture. Стендовых замеров и BIN в этой порции нет. |
| VSS-02 | Copilot — VSS-02 H03 sensor profile integration | [a61f97304725](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/commit/a61f973047258103fde0a3e7c9592eb053fa9a67) | 700f8602ef664b24894313c2415fbdb5 | Published VSS-02 source and M32R/native rerun: exact H03 SHA PASS_STOCK_ONLY, M32R bench sensor PASS, S51/S83 hooks PASS, 11 ATF pairs PASS, app/input/binding/target platform and MODE-02 native checks PASS. production_sensor_config remains null; no hardware readiness or two-BIN claim. |
| VSS-02 | Copilot H03 sensor production exports | [20f42a30c48f](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/commit/20f42a30c48f5e80ada0bda5b1fc6f9cc0770edd) | a642d995b84d4360b6b126b543a56c64 | Published typed alias native/layout evidence and exact FAIL_BINDINGS blockers. Production sensor config remains unresolved without paired clock and calibration evidence; aggregate-owned layout files were not edited. |

## Что осталось доделать

Продолжения относятся к тем же ID задач. Номер пункта не назначает чат.
Рекомендованный чат — подсказка для продолжения прежнего направления, а не резерв.
Сначала обновить свою копию из main, посмотреть список и занять задачу с точными файлами.
Активный исполнитель и пересекающиеся файлы защищены общим резервом.

Порядок задаёт приоритет продолжения. Зависимости нужны для итоговой приёмки; независимую часть можно делать сразу.
Свободная задача может требовать ещё не полученных данных. Их отсутствие фиксируется отдельно от готовности кода.
[Подробное распределение и единый текст для Codex / Claude](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/blob/3fe28938163e1dddc98a37733c229390ab7f0fff/docs/integration-next-tasks.md)

| Приоритет | Задача | Занятость | Что сдать | Зависимости приёмки |
| --- | --- | --- | --- | --- |
| 2 | [TOY-01](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/blob/3fe28938163e1dddc98a37733c229390ab7f0fff/docs/project-map.md#toy-01) | Свободна для продолжения | Полное начальное состояние со списком происхождения полей, вызовы cold/warm/restore, дифференциальные прогоны с донором и отсутствие неинициализированных чтений. | См. входные условия карточки |
| 3 | [TOY-02](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/blob/3fe28938163e1dddc98a37733c229390ab7f0fff/docs/project-map.md#toy-02) | Свободна для продолжения; порция на проверке | Таблица всех необходимых операндов и реализованный capture/input backend; контракт для чата 8, реальные source offsets и отрицательные тесты неполного/устаревшего снимка. | См. входные условия карточки |
| 4 | [TOY-03](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/blob/3fe28938163e1dddc98a37733c229390ab7f0fff/docs/project-map.md#toy-03) | Свободна для продолжения | Реальный поставщик и фрагмент профиля со всеми используемыми единицами/метками/таймаутами; replay ошибочного и устаревшего обмена и M32R-сборка. | См. входные условия карточки |
| 5 | [TOY-04](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/blob/3fe28938163e1dddc98a37733c229390ab7f0fff/docs/project-map.md#toy-04) | Свободна для продолжения | Реальный output backend/профиль, завершённая программная последовательность переключений и SLU, ограничение непроверенного включения, проверка отзыва каждой команды и минимальный план замеров после сборки. | TOY-02, TOY-03, H03-03, MODE-02 |
| 6 | [TOY-05](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/blob/3fe28938163e1dddc98a37733c229390ab7f0fff/docs/project-map.md#toy-05) | Выполняется | Полное начальное состояние со списком происхождения полей, вызовы cold/warm/restore, дифференциальные прогоны с донором и отсутствие неинициализированных чтений. | TOY-04, H03-04 |
| 7 | [TOY-06](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/blob/3fe28938163e1dddc98a37733c229390ab7f0fff/docs/project-map.md#toy-06) | Свободна для продолжения; порция на проверке | Реальный output backend/профиль, завершённая программная последовательность переключений и SLU, ограничение непроверенного включения, проверка отзыва каждой команды и минимальный план замеров после сборки. | TOY-02, H03-05 |
| 8 | [CAN-01](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/blob/3fe28938163e1dddc98a37733c229390ab7f0fff/docs/project-map.md#can-01) | Свободна для продолжения; порция на проверке | Реальный поставщик и фрагмент профиля со всеми используемыми единицами/метками/таймаутами; replay ошибочного и устаревшего обмена и M32R-сборка. | См. входные условия карточки |
| 9 | [CAN-02](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/blob/3fe28938163e1dddc98a37733c229390ab7f0fff/docs/project-map.md#can-02) | Свободна для продолжения | Native CAN service profile/config с производителями статуса/момента и точками вызова; двусторонний сценарий и отказные проверки, точные Flash/RAM. | См. входные условия карточки |
| 10 | [CAN-03](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/blob/3fe28938163e1dddc98a37733c229390ab7f0fff/docs/project-map.md#can-03) | Выполняется | Native CAN service profile/config с производителями статуса/момента и точками вызова; двусторонний сценарий и отказные проверки, точные Flash/RAM. | H03-04 |
| 11 | [CAN-04](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/blob/3fe28938163e1dddc98a37733c229390ab7f0fff/docs/project-map.md#can-04) | Ожидает данных / решения | Native CAN service profile/config с производителями статуса/момента и точками вызова; двусторонний сценарий и отказные проверки, точные Flash/RAM. | См. входные условия карточки |
| 12 | [CAN-05](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/blob/3fe28938163e1dddc98a37733c229390ab7f0fff/docs/project-map.md#can-05) | Свободна для продолжения | Воспроизводимый Bosch BIN для стендовой проверки только при наличии всех необходимых программных доказательств, либо точная реально неустранимая причина; source/final SHA, map diff, native integrity, CPU paths и ограничения. Аппаратные проверки честно false. | TOY-02 |
| 13 | [ECU-01](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/blob/3fe28938163e1dddc98a37733c229390ab7f0fff/docs/project-map.md#ecu-01) | Выполняется | Воспроизводимый Bosch BIN для стендовой проверки только при наличии всех необходимых программных доказательств, либо точная реально неустранимая причина; source/final SHA, map diff, native integrity, CPU paths и ограничения. Аппаратные проверки честно false. | См. входные условия карточки |
| 14 | [ECU-02](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/blob/3fe28938163e1dddc98a37733c229390ab7f0fff/docs/project-map.md#ecu-02) | Свободна для продолжения | Воспроизводимый Bosch BIN для стендовой проверки только при наличии всех необходимых программных доказательств, либо точная реально неустранимая причина; source/final SHA, map diff, native integrity, CPU paths и ограничения. Аппаратные проверки честно false. | CAN-05 |
| 16 | [H03-02](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/blob/3fe28938163e1dddc98a37733c229390ab7f0fff/docs/project-map.md#h03-02) | Свободна для продолжения | Компилируемый native профиль часов и датчиков, проверка reset/wrap/stall/clock change; список только действительно аппаратных параметров для замера после прошивки. | См. входные условия карточки |
| 17 | [H03-03](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/blob/3fe28938163e1dddc98a37733c229390ab7f0fff/docs/project-map.md#h03-03) | Выполняется | Полный набор hooks/placement с проверкой original bytes, ссылками на native callbacks, проверкой CPU штатного/отказного/повторного пути; никаких fixture callbacks. | H03-04 |
| 18 | [H03-04](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/blob/3fe28938163e1dddc98a37733c229390ab7f0fff/docs/project-map.md#h03-04) | Свободна для продолжения; порция на проверке | Пять реальных определений/профиль, полный список писателей, linker constraints и доказательства покрытия; стоимость RAM/стеков и сценарии отказа. | См. входные условия карточки |
| 19 | [H03-05](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/blob/3fe28938163e1dddc98a37733c229390ab7f0fff/docs/project-map.md#h03-05) | Свободна для продолжения; порция на проверке | Реальный output backend/профиль, завершённая программная последовательность переключений и SLU, ограничение непроверенного включения, проверка отзыва каждой команды и минимальный план замеров после сборки. | См. входные условия карточки |
| 21 | [VSS-01](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/blob/3fe28938163e1dddc98a37733c229390ab7f0fff/docs/project-map.md#vss-01) | Свободна для продолжения | Компилируемый native профиль часов и датчиков, проверка reset/wrap/stall/clock change; список только действительно аппаратных параметров для замера после прошивки. | См. входные условия карточки |
| 22 | [VSS-02](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/blob/3fe28938163e1dddc98a37733c229390ab7f0fff/docs/project-map.md#vss-02) | Выполняется | Компилируемый native профиль часов и датчиков, проверка reset/wrap/stall/clock change; список только действительно аппаратных параметров для замера после прошивки. | См. входные условия карточки |
| 24 | [MODE-01](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/blob/3fe28938163e1dddc98a37733c229390ab7f0fff/docs/project-map.md#mode-01) | Свободна для продолжения | Native mode/input profile, расчёт диапазонов/резисторов и полная цепь ручного запроса, debounce/hold/opposed/stale/reset tests. | См. входные условия карточки |
| 25 | [MODE-02](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/blob/3fe28938163e1dddc98a37733c229390ab7f0fff/docs/project-map.md#mode-02) | Выполняется | Native mode/input profile, расчёт диапазонов/резисторов и полная цепь ручного запроса, debounce/hold/opposed/stale/reset tests. | H03-03 |
| 26 | [MODE-03](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/blob/3fe28938163e1dddc98a37733c229390ab7f0fff/docs/project-map.md#mode-03) | Выполняется | Native mode/input profile, расчёт диапазонов/резисторов и полная цепь ручного запроса, debounce/hold/opposed/stale/reset tests. | См. входные условия карточки |
| 27 | [REL-01](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/blob/3fe28938163e1dddc98a37733c229390ab7f0fff/docs/project-map.md#rel-01) | Выполняется | TCM BIN + Bosch BIN + SHA/manifest, карты правок, применимость и фактические результаты приёмки. | TOY-04, TOY-05, TOY-06, CAN-03, CAN-05, ECU-02, H03-04, H03-05, VSS-02, MODE-02, MODE-03, DTC-02, DTC-03, DTC-04 |
| 28 | [REL-02](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/blob/3fe28938163e1dddc98a37733c229390ab7f0fff/docs/project-map.md#rel-02) | Свободна для продолжения | Фактические записи входов/CAN/момента/SLT/SLU и отказов с критериями приёмки. | REL-01 |
| 29 | [DTC-01](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/blob/3fe28938163e1dddc98a37733c229390ab7f0fff/docs/project-map.md#dtc-01) | Свободна для продолжения | Полный native diagnostic path и реестр команд/полей; отказные проверки и минимальный протокол после BIN с местом/режимом/критерием измерения; что штатный Chery сканер поддерживает, а что проектный readout. | См. входные условия карточки |
| 30 | [DTC-02](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/blob/3fe28938163e1dddc98a37733c229390ab7f0fff/docs/project-map.md#dtc-02) | Выполняется | Полный native diagnostic path и реестр команд/полей; отказные проверки и минимальный протокол после BIN с местом/режимом/критерием измерения; что штатный Chery сканер поддерживает, а что проектный readout. | См. входные условия карточки |
| 31 | [DTC-03](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/blob/3fe28938163e1dddc98a37733c229390ab7f0fff/docs/project-map.md#dtc-03) | Выполняется | Полный native diagnostic path и реестр команд/полей; отказные проверки и минимальный протокол после BIN с местом/режимом/критерием измерения; что штатный Chery сканер поддерживает, а что проектный readout. | H03-05, TOY-06 |
| 32 | [DTC-04](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/blob/3fe28938163e1dddc98a37733c229390ab7f0fff/docs/project-map.md#dtc-04) | Выполняется | Рабочий backend или конкретная доказанная граница его доступности, профиль носителя/проверка восстановления, подлинные Flash-адреса; телеметрия для получения недостающего после BIN. | H03-04 |

### Сделано и остаток по каждой незакрытой задаче

<details>
<summary>TOY-01 — Перенос ядра и единое состояние Toyota: Свободна для продолжения</summary>

**Сделано.** Объединённый результат 21.11.2026: Нативный независимый источник Toyota от TML0 включён в H03-мост и проверен через take_toyota, включая пропуск первого события и wrap. 18 стандартных M32R и компоновка прошли в своём объёме. Известные 95394 байта; период, владелец RAM и окончательные привязки остаются открыты.

**Осталось доделать.** Довести полный рабочий цикл и его производителей в TOY-04/H03-03; сокращение таблиц не подтверждает всю программу автомобиля.

**Следующий шаг.** Перепроверь утверждение про 685 байт вне cold-проекции: действительно ли это неизвестные калибровки, или штатные BSS/reset/data/нечитаемые до записи поля? Используй S01/R3 и граф read-before-write, не требуй аппаратный снимок если значения следуют из программы. Доведи rbm_h03_target_startup_gp/gear и реальный initialize_inputs (без захвата транспортных модулей других чатов), init/restore/default paths и явные неподтверждённые поля. Не обнулять неизвестное без доказательства.

**Исходные условия.** main abd3cba и позднее; docs/bench-first-wave.md; data/bench-first-wave.json; имеющиеся источники/проверки карточки.

**Что сдать.** Полное начальное состояние со списком происхождения полей, вызовы cold/warm/restore, дифференциальные прогоны с донором и отсутствие неинициализированных чтений.

**Рекомендуемый чат.** Чат 12 — 01a1fa79-a9fd-70c0-80a3-f59592edaf79.

**Исполнитель сейчас.** Задача не занята.

**Критерий приёмки.** Программный результат относится к проверенным функциям, а не ко всем режимам АКПП.

[Код, настройки, зависимости и проверки](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/blob/3fe28938163e1dddc98a37733c229390ab7f0fff/docs/project-map.md#toy-01)

</details>

<details>
<summary>TOY-02 — Подтверждённая нагрузка двигателя для Toyota: Свободна для продолжения; порция на проверке</summary>

**Сделано.** Три группы нагрузки требуют квалификации перед GP и планированием; смена epoch отзывает старые данные. Ручной профиль и основной цикл прошли.

**Осталось доделать.** Определить реальные производители GP 9046/8288/8330 и 5299.1 с масштабами/свежестью. Текущие разностные CAN-коды не восстанавливают их однозначно; квалификатор не заменяет источник.

**Следующий шаг.** Перепроверь все операнды full Toyota cycle: реальный источник Bosch, шкала, знаковость, возраст, startup и отказ. Если имеющийся CAN несёт только разности и обратное восстановление неоднозначно, не делать ещё один qualifier вокруг той же неопределённости. Подготовь минимальный дополнительный явный raw-source контракт Bosch→TCM с происхождением каждого поля и приёмник; штатный Chery сохранить. Документируй предложения/неизвестные поля, не выдумывать физический load. Самостоятельно подключи доступные producer→capture части и избавь native путь от test_input_capture.

**Исходные условия.** main abd3cba и позднее; docs/bench-first-wave.md; data/bench-first-wave.json; имеющиеся источники/проверки карточки.

**Что сдать.** Таблица всех необходимых операндов и реализованный capture/input backend; контракт для чата 8, реальные source offsets и отрицательные тесты неполного/устаревшего снимка.

**Рекомендуемый чат.** Чат 4 — 01a1f9c7-675a-78c3-be98-5bd65e44995c.

**Исполнитель сейчас.** Задача не занята.

**Критерий приёмки.** Трасса происхождения каждого операнда, сравнение с S01 и отдельные переходные режимы. Одного TPS и кадров RPM/ОЖ недостаточно.

[Код, настройки, зависимости и проверки](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/blob/3fe28938163e1dddc98a37733c229390ab7f0fff/docs/project-map.md#toy-02)

</details>

<details>
<summary>TOY-03 — Независимые разрешающие сигналы диапазона: Свободна для продолжения</summary>

**Сделано.** Объединённый результат 21.11.2026: Допуск независимого P/N проверяет AN2, поколения, давность и рассогласование; в снимок идёт старейшая метка. M32R: 1024 AN2, 12 сочетаний P/N, проверки отказа, 5 ADC-сравнений и 8 компонентных групп PASS. Жгут и foreground открыты. Отчёт toy03-independent-pn-qualifier.md.

**Осталось доделать.** Подтвердить физический источник P/N/разрешения пуска и включить квалифицированные диапазоны в общий цикл.

**Следующий шаг.** Реализуй native context_for_task2 вместо fixture_engine_context, независимые разрешающие сигналы и их происхождение. Параметры age/poll/bit time вывести из кода/регистров/периодики там, где это возможно. Для неподтверждённой временной величины нужен явный инженерный диапазон и контроль в runtime, а не требование получить журнал до BIN. Не восстанавливать неоднозначную абсолютную нагрузку из разностей CAN. Общие CAN owner/RX/DTC уже есть.

**Исходные условия.** main abd3cba и позднее; docs/bench-first-wave.md; data/bench-first-wave.json; имеющиеся источники/проверки карточки.

**Что сдать.** Реальный поставщик и фрагмент профиля со всеми используемыми единицами/метками/таймаутами; replay ошибочного и устаревшего обмена и M32R-сборка.

**Рекомендуемый чат.** Чат 2 — 01a1f9b1-c11a-7b23-abcf-3214ce643805.

**Исполнитель сейчас.** Задача не занята.

**Критерий приёмки.** Для каждого бита известны источник, шкала времени и реакция на отказ. Проверка P/N не проверяет сама себя.

[Код, настройки, зависимости и проверки](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/blob/3fe28938163e1dddc98a37733c229390ab7f0fff/docs/project-map.md#toy-03)

</details>

<details>
<summary>TOY-04 — Полная последовательность переключений: Свободна для продолжения</summary>

**Сделано.** Объединённый результат 21.11.2026: Ручная цель подключена в MAIN перед защитами Toyota и проходит выдержки, S1/S2 и гидравлику. 41 этап ПК, 120 тестов с отдельной проверкой S03, 18+8 компонентных, 22 нативные и 6 размещённых M32R. Отчёт verification/project-audit/toy04-manual-cycle.md. Открыты источник и срок удержания цели MODE-02/03, целевая привязка H03-03 и аппаратная приёмка; выпуск пары BIN открыт.

**Осталось доделать.** Связать оставшиеся стадии и входы, провести ручные заявки через гидравлику; проверить R, 2→3, 3→4, понижения и защитные переходы целым целевым циклом.

**Следующий шаг.** Доведи реальные native output ops, mapping D/E/F/Pressure A и весь путь command→arbitrate→apply→inhibit. Перепроверь соответствие SLT/SLU и отказов. Нельзя утверждать электрическую изоляцию TIO9 маской без основания. Если конкретное включение требует неизвестного электрического параметра, реализуй диагностическое/комиссионное измерение и явную блокировку именно этого включения; не останавливать запуск/CAN всей системы. Донорские значения с доказуемой применимостью могут быть начальной инженерной настройкой с явно указанными ограничениями, не выдуманной калибровкой давления. Все аппаратные измерения оформить после BIN.

**Исходные условия.** main abd3cba и позднее; docs/bench-first-wave.md; data/bench-first-wave.json; имеющиеся источники/проверки карточки.

**Что сдать.** Реальный output backend/профиль, завершённая программная последовательность переключений и SLU, ограничение непроверенного включения, проверка отзыва каждой команды и минимальный план замеров после сборки.

**Рекомендуемый чат.** Чат 7 — 01a1f9a2-d0ae-78d3-86f1-21b27426fd3f.

**Исполнитель сейчас.** Задача не занята.

**Критерий приёмки.** Матрица режимов с ожидаемыми результатами S01 и сквозными трассами. Отдельный тест момента не закрывает всё переключение 2→3.

[Код, настройки, зависимости и проверки](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/blob/3fe28938163e1dddc98a37733c229390ab7f0fff/docs/project-map.md#toy-04)

</details>

<details>
<summary>TOY-05 — Обучение и сохранение адаптаций: Выполняется</summary>

**Сделано.** Добавлен штатный читатель пары UFL1 в существующее workspace до допуска фаз; проверены rollover, Virtual Flash и повторный старт. Общий код и NVM-модель прошли.

**Осталось доделать.** Выбрать два доказанно свободных блока, реализовать запись и подключить полный startup GP/gear. Только read-only адаптация не завершает постоянное хранение.

**Следующий шаг.** Перепроверь утверждение про 685 байт вне cold-проекции: действительно ли это неизвестные калибровки, или штатные BSS/reset/data/нечитаемые до записи поля? Используй S01/R3 и граф read-before-write, не требуй аппаратный снимок если значения следуют из программы. Доведи rbm_h03_target_startup_gp/gear и реальный initialize_inputs (без захвата транспортных модулей других чатов), init/restore/default paths и явные неподтверждённые поля. Не обнулять неизвестное без доказательства.

**Исходные условия.** main abd3cba и позднее; docs/bench-first-wave.md; data/bench-first-wave.json; имеющиеся источники/проверки карточки.

**Что сдать.** Полное начальное состояние со списком происхождения полей, вызовы cold/warm/restore, дифференциальные прогоны с донором и отсутствие неинициализированных чтений.

**Рекомендуемый чат.** Чат 12 — 01a1fa79-a9fd-70c0-80a3-f59592edaf79.

**Сейчас выполняет.** Codex 12 — TOY-05, стартовое состояние первой стендовой пары — 01a1fa79-a9fd-70c0-80a3-f59592edaf79.

**Критерий приёмки.** Проверены пределы коррекции, повторный пуск, повреждённая запись и сброс адаптаций.

[Код, настройки, зависимости и проверки](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/blob/3fe28938163e1dddc98a37733c229390ab7f0fff/docs/project-map.md#toy-05)

</details>

<details>
<summary>TOY-06 — Блокировка гидротрансформатора SLU: Свободна для продолжения; порция на проверке</summary>

**Сделано.** Объединённый результат 21.11.2026: 18 штатных сценариев M32R: Shift E/P31 (Mazda TCC 1H) отключается при общем inhibit и P0773, а TIO9/P97 сохраняет PWM. Проверены штатные входы ATF/питания и пороги TIO9. Повторены 6 сценариев арбитра и 59 мониторов. Для Toyota SLU открыты физический канал, отдельное отключение, калибровка и полный снимок. Отчёт toy06-h03-slu-output-paths.md.

**Осталось доделать.** Подключить полный целевой снимок и физический канал SLU; установить масштабы и проверить удержание/снятие блокировки.

**Следующий шаг.** Доведи реальные native output ops, mapping D/E/F/Pressure A и весь путь command→arbitrate→apply→inhibit. Перепроверь соответствие SLT/SLU и отказов. Нельзя утверждать электрическую изоляцию TIO9 маской без основания. Если конкретное включение требует неизвестного электрического параметра, реализуй диагностическое/комиссионное измерение и явную блокировку именно этого включения; не останавливать запуск/CAN всей системы. Донорские значения с доказуемой применимостью могут быть начальной инженерной настройкой с явно указанными ограничениями, не выдуманной калибровкой давления. Все аппаратные измерения оформить после BIN.

**Исходные условия.** main abd3cba и позднее; docs/bench-first-wave.md; data/bench-first-wave.json; имеющиеся источники/проверки карточки.

**Что сдать.** Реальный output backend/профиль, завершённая программная последовательность переключений и SLU, ограничение непроверенного включения, проверка отзыва каждой команды и минимальный план замеров после сборки.

**Рекомендуемый чат.** Чат 7 — 01a1f9a2-d0ae-78d3-86f1-21b27426fd3f.

**Исполнитель сейчас.** Задача не занята.

**Критерий приёмки.** Трасса от квалифицированных входов до канала H03, проверка скольжения, удержания и снятия по отказу.

[Код, настройки, зависимости и проверки](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/blob/3fe28938163e1dddc98a37733c229390ab7f0fff/docs/project-map.md#toy-06)

</details>

<details>
<summary>CAN-01 — Форматы CAN и квалификация RPM/ОЖ: Свободна для продолжения; порция на проверке</summary>

**Сделано.** Реальный дескриптор target_engine включается явным профилем и использует единые engine_rx/qualifier/DTC/CAN owner/TML0. Нативные тесты и свежий обмен с Bosch прошли.

**Осталось доделать.** Задать подтверждённые границы времени и реальный Task 2 context с retained_fd10/fallback_fa7b/retained_e026/e02b и старейшей меткой. В общей пробе внешний fixture_engine_context остаётся неопределённым.

**Следующий шаг.** Реализуй native context_for_task2 вместо fixture_engine_context, независимые разрешающие сигналы и их происхождение. Параметры age/poll/bit time вывести из кода/регистров/периодики там, где это возможно. Для неподтверждённой временной величины нужен явный инженерный диапазон и контроль в runtime, а не требование получить журнал до BIN. Не восстанавливать неоднозначную абсолютную нагрузку из разностей CAN. Общие CAN owner/RX/DTC уже есть.

**Исходные условия.** main abd3cba и позднее; docs/bench-first-wave.md; data/bench-first-wave.json; имеющиеся источники/проверки карточки.

**Что сдать.** Реальный поставщик и фрагмент профиля со всеми используемыми единицами/метками/таймаутами; replay ошибочного и устаревшего обмена и M32R-сборка.

**Рекомендуемый чат.** Чат 2 — 01a1f9b1-c11a-7b23-abcf-3214ce643805.

**Исполнитель сейчас.** Задача не занята.

**Критерий приёмки.** Результат ограничен перечисленными полями и сценариями приёма.

[Код, настройки, зависимости и проверки](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/blob/3fe28938163e1dddc98a37733c229390ab7f0fff/docs/project-map.md#can-01)

</details>

<details>
<summary>CAN-02 — Общий диспетчер CAN13: Свободна для продолжения</summary>

**Сделано.** При отсутствии калибровки S51 передаётся недоступная скорость 0xFFFF в 0x1AE, а ATF 0x300 сохраняется; общая модель обмена прошла.

**Осталось доделать.** Подключить окончательный vehicle/torque/status профиль и проверить полноценный обмен совместно с CAN-03/CAN-04/CAN-05.

**Следующий шаг.** Доведи реальный Lfj8H03TargetServiceConfig, источник времени, сбор T6/status и отправку момента/диагностики через единственный TX13. START/REFRESH/ACK/CANCEL, шедулинг, bus-off, monitor, reset и смена поколения должны иметь реальные входы/выходы. Убери зависимость от test_can_service_config. Полнота CAN включает обратную связь и завершение запросов, а не только RPM/ОЖ.

**Исходные условия.** main abd3cba и позднее; docs/bench-first-wave.md; data/bench-first-wave.json; имеющиеся источники/проверки карточки.

**Что сдать.** Native CAN service profile/config с производителями статуса/момента и точками вызова; двусторонний сценарий и отказные проверки, точные Flash/RAM.

**Рекомендуемый чат.** Чат 3 — 01a1f9b5-5d41-79e0-8cd2-3dadc922f1ce.

**Исполнитель сейчас.** Задача не занята.

**Критерий приёмки.** Программные тесты не заменяют измерение окон приёма 0x5E9.

[Код, настройки, зависимости и проверки](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/blob/3fe28938163e1dddc98a37733c229390ab7f0fff/docs/project-map.md#can-02)

</details>

<details>
<summary>CAN-03 — Штатный запуск, IRQ и восстановление CAN0: Выполняется</summary>

**Сделано.** Общий T6 задаёт расписание S03 4/12; пять некорректных сервисных профилей отвергаются до допуска фаз. Исправлена совместимость CAN13 status_due; общий CAN прошёл.

**Осталось доделать.** Подключить действительный service config, status/torque источники и квалифицированные временные пределы; закончить monitor-переходы.

**Следующий шаг.** Доведи реальный Lfj8H03TargetServiceConfig, источник времени, сбор T6/status и отправку момента/диагностики через единственный TX13. START/REFRESH/ACK/CANCEL, шедулинг, bus-off, monitor, reset и смена поколения должны иметь реальные входы/выходы. Убери зависимость от test_can_service_config. Полнота CAN включает обратную связь и завершение запросов, а не только RPM/ОЖ.

**Исходные условия.** main abd3cba и позднее; docs/bench-first-wave.md; data/bench-first-wave.json; имеющиеся источники/проверки карточки.

**Что сдать.** Native CAN service profile/config с производителями статуса/момента и точками вызова; двусторонний сценарий и отказные проверки, точные Flash/RAM.

**Рекомендуемый чат.** Чат 3 — 01a1f9b5-5d41-79e0-8cd2-3dadc922f1ce.

**Сейчас выполняет.** Codex чат 3 — стендовый CAN-сервис H03 — codex-fea1b366-66b6-4667-8206-915153ca1033.

**Критерий приёмки.** Штатная ветвь не перезаписывает CAN13, старые кадры не принимаются после сброса, сохранена диагностика и отмена.

[Код, настройки, зависимости и проверки](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/blob/3fe28938163e1dddc98a37733c229390ab7f0fff/docs/project-map.md#can-03)

</details>

<details>
<summary>CAN-04 — Запрос снижения момента по RB: Ожидает данных / решения</summary>

**Сделано.** Объединённый результат 21.11.2026: CAN13 отзывает ожидающий RB START/REFRESH на текущем опросе при потере допуска или истечении метки; CANCEL и подтверждение TRFIN сохраняются. Регрессия ПК, 18 групп M32R, 6 проверок размещения и оба диалога Bosch прошли. Физический профиль остаётся открытым. Отчёт: verification/project-audit/can04-pending-tx-revoke.md.

**Осталось доделать.** Подключить реальные временные метки и подтверждённый профиль снижения момента; измерить его действие в целевой паре.

**Следующий шаг.** Доведи реальный Lfj8H03TargetServiceConfig, источник времени, сбор T6/status и отправку момента/диагностики через единственный TX13. START/REFRESH/ACK/CANCEL, шедулинг, bus-off, monitor, reset и смена поколения должны иметь реальные входы/выходы. Убери зависимость от test_can_service_config. Полнота CAN включает обратную связь и завершение запросов, а не только RPM/ОЖ.

**Исходные условия.** main abd3cba и позднее; docs/bench-first-wave.md; data/bench-first-wave.json; имеющиеся источники/проверки карточки.

**Что сдать.** Native CAN service profile/config с производителями статуса/момента и точками вызова; двусторонний сценарий и отказные проверки, точные Flash/RAM.

**Рекомендуемый чат.** Чат 3 — 01a1f9b5-5d41-79e0-8cd2-3dadc922f1ce.

**Резерв удерживает.** Copilot App — запрос снижения момента CAN LFJ8 — copilot-416d2a7e-79e0-4acb-8e40-27807c492e55.

**Критерий приёмки.** Протокол 0x5E8/0x5E9 является RB. Его успешный тест не означает полного штатного Chery CAN.

[Код, настройки, зависимости и проверки](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/blob/3fe28938163e1dddc98a37733c229390ab7f0fff/docs/project-map.md#can-04)

</details>

<details>
<summary>CAN-05 — Полнота штатного обмена Chery: Свободна для продолжения</summary>

**Сделано.** Объединённый результат 21.11.2026: Реальный профиль Bosch включает чтение T4 до пустого опроса 0x1AE, проверку после IF1 и отзыв скорости. Два варианта ST10/C_CAN прошли 26 групп каждый и 51 запись целостности. Проверены RB, 12 прежних сборок, 41 этап ПК и 120 тестов с отдельным повтором S03. Открыты RAM и публикация поколения, потребитель момента, измеренный lease_ticks и ECU-02. Отчёт can05-st10-bound-t4.md.

**Осталось доделать.** Профили с нативным T4/IF1 уже собираются и проверены на ST10. Для выпуска остаются фактическая RAM и поколение, срок lease_ticks, соединение с потребителем/арбитражем ECU-02 и проверка интервалов под нагрузкой.

**Следующий шаг.** Назначен владельцем целевого Bosch BIN. Полностью перепроверь ordinary/no-cruise OFFLINE_ONLY, причины ограничения, hooks, checksum и сохранение старта/впрыска/зажигания. Доделай реальные штатные Chery кадры и RB torque request/reply/cancel плюс требуемые Toyota operands. Чат 4 готовит таблицу исходных операндов и приёмник: совместимость через проверяемый контракт, не подстановку физических значений. Раздели реальные препятствия к первому стендовому образу от моторной калибровки после прошивки. Нельзя просто переименовать bd0afefa… в READY.

**Исходные условия.** main abd3cba и позднее; docs/bench-first-wave.md; data/bench-first-wave.json; имеющиеся источники/проверки карточки.

**Что сдать.** Воспроизводимый Bosch BIN для стендовой проверки только при наличии всех необходимых программных доказательств, либо точная реально неустранимая причина; source/final SHA, map diff, native integrity, CPU paths и ограничения. Аппаратные проверки честно false.

**Рекомендуемый чат.** Чат 8 — 01a1f9ab-19c7-72c0-ac90-6aa98e4aa488.

**Исполнитель сейчас.** Задача не занята.

**Критерий приёмки.** Для каждого требуемого поля есть источник, единицы, период, недостоверность и проверенный потребитель. Замена штатного протокола отдельным RB не считается закрытием §3.

[Код, настройки, зависимости и проверки](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/blob/3fe28938163e1dddc98a37733c229390ab7f0fff/docs/project-map.md#can-05)

</details>

<details>
<summary>ECU-01 — Проверочная сборка Bosch E4M3: Выполняется</summary>

**Сделано.** Повторно собран Bosch ordinary/no-cruise/no-override OFFLINE_ONLY; проверены целостность, 65536 native encoder cases и обмен с текущим TCM-кодом. SHA и результаты в INTEGRATION39.

**Осталось доделать.** Завершить CAN-05/ECU-02, собрать согласованный целевой профиль и проверить происхождение обоих итоговых образов.

**Следующий шаг.** Назначен владельцем целевого Bosch BIN. Полностью перепроверь ordinary/no-cruise OFFLINE_ONLY, причины ограничения, hooks, checksum и сохранение старта/впрыска/зажигания. Доделай реальные штатные Chery кадры и RB torque request/reply/cancel плюс требуемые Toyota operands. Чат 4 готовит таблицу исходных операндов и приёмник: совместимость через проверяемый контракт, не подстановку физических значений. Раздели реальные препятствия к первому стендовому образу от моторной калибровки после прошивки. Нельзя просто переименовать bd0afefa… в READY.

**Исходные условия.** main abd3cba и позднее; docs/bench-first-wave.md; data/bench-first-wave.json; имеющиеся источники/проверки карточки.

**Что сдать.** Воспроизводимый Bosch BIN для стендовой проверки только при наличии всех необходимых программных доказательств, либо точная реально неустранимая причина; source/final SHA, map diff, native integrity, CPU paths и ограничения. Аппаратные проверки честно false.

**Рекомендуемый чат.** Чат 8 — 01a1f9ab-19c7-72c0-ac90-6aa98e4aa488.

**Сейчас выполняет.** Copilot — Bosch paired release — 9d4fcd7f-8d30-447e-b31d-6889553c0e20.

**Критерий приёмки.** Это образ OFFLINE_ONLY, сохранение всех функций двигателя на машине не подтверждено.

[Код, настройки, зависимости и проверки](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/blob/3fe28938163e1dddc98a37733c229390ab7f0fff/docs/project-map.md#ecu-01)

</details>

<details>
<summary>ECU-02 — Калибровка момента и работа двигателя: Свободна для продолжения</summary>

**Сделано.** Объединённый результат 21.11.2026: Приёмник C отклоняет 0x1AE с меткой на границе снятия допуска и раньше. Подтверждено для прямого/отложенного RX, очереди и переполнения T4. ПК 41/120, 65536 пар, старый Bosch ST10 с 51 записью, три диалога H03 и 26 архивных запросов. Машинная привязка CAN-05 и стенд открыты. Отчёт ecu02-torque-permit-boundary.md.

**Осталось доделать.** Завершить машинный арбитраж с квалифицированными входами и подтвердить действие/снятие момента на новой паре блоков.

**Следующий шаг.** Назначен владельцем целевого Bosch BIN. Полностью перепроверь ordinary/no-cruise OFFLINE_ONLY, причины ограничения, hooks, checksum и сохранение старта/впрыска/зажигания. Доделай реальные штатные Chery кадры и RB torque request/reply/cancel плюс требуемые Toyota operands. Чат 4 готовит таблицу исходных операндов и приёмник: совместимость через проверяемый контракт, не подстановку физических значений. Раздели реальные препятствия к первому стендовому образу от моторной калибровки после прошивки. Нельзя просто переименовать bd0afefa… в READY.

**Исходные условия.** main abd3cba и позднее; docs/bench-first-wave.md; data/bench-first-wave.json; имеющиеся источники/проверки карточки.

**Что сдать.** Воспроизводимый Bosch BIN для стендовой проверки только при наличии всех необходимых программных доказательств, либо точная реально неустранимая причина; source/final SHA, map diff, native integrity, CPU paths и ограничения. Аппаратные проверки честно false.

**Рекомендуемый чат.** Чат 8 — 01a1f9ab-19c7-72c0-ac90-6aa98e4aa488.

**Исполнитель сейчас.** Задача не занята.

**Критерий приёмки.** Протокол с идентифицированными BIN и измеренным результатом. Исторический стенд STM32 не переносит автоматически приёмку на LFJ8.

[Код, настройки, зависимости и проверки](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/blob/3fe28938163e1dddc98a37733c229390ab7f0fff/docs/project-map.md#ecu-02)

</details>

<details>
<summary>H03-02 — S51, S83 и температура ATF: Свободна для продолжения</summary>

**Сделано.** Захват датчиков использует время конца чтения; проверены перенос счётчика, задержка и допуск ATF по квалифицированным часам.

**Осталось доделать.** Подключить реальные sensor_config, частоту, периоды и допуски из VSS-02; выполнить квалификацию S51/S83/ATF в общем цикле.

**Следующий шаг.** Доведи rbm_h03_sensor_config и rbm_h03_target_clock_ready для H03, единый TML0 и статус непрерывности. Найди частоты/делители/коэффициенты в исходнике/схеме/регистрах. Раздели вычислимые параметры и будущую измерительную коррекцию; не требовать реальную частоту до выпуска образа. Неподтверждённая оценка должна иметь явный статус и проверку, не называться измеренной. 100/22 сохранять точно, не угадывать окружность колеса. Реализовать выдачу raw speed/capture для будущей калибровки.

**Исходные условия.** main abd3cba и позднее; docs/bench-first-wave.md; data/bench-first-wave.json; имеющиеся источники/проверки карточки.

**Что сдать.** Компилируемый native профиль часов и датчиков, проверка reset/wrap/stall/clock change; список только действительно аппаратных параметров для замера после прошивки.

**Рекомендуемый чат.** Чат 5 — 01a1f9a8-7b61-7763-adaa-0e3e11d1dbf4.

**Исполнитель сейчас.** Задача не занята.

**Критерий приёмки.** Компоненты не подменяют окончательную установку обработчиков в BIN.

[Код, настройки, зависимости и проверки](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/blob/3fe28938163e1dddc98a37733c229390ab7f0fff/docs/project-map.md#h03-02)

</details>

<details>
<summary>H03-03 — Единое расписание и запуск приложения H03: Выполняется</summary>

**Сделано.** В общий компоновщик включены четыре штатных перехода cold/startup/foreground/phase; связанная проверка адресов и 68 сценариев M32R прошли. Поставщики платформы переиспользованы.

**Осталось доделать.** Подключить выпускной профиль запуска, полноценные GP/gear и input capture; закончить strategy/apply/monitor переходы и полный линк без испытательных деклараций.

**Следующий шаг.** Проверь все пути вызова нового цикла от reset до переключения, включая штатные писатели, повторный запуск и monitor. Доделай недостающие OEM redirects на основе точных байтов H03 и предоставь relocatable объекты/план патчей для общего ELF. Четыре существующих entry veneers не доказывают, что все входящие штатные ветки подключены. Проверить конечный граф путей и устранить обходы.

**Исходные условия.** main abd3cba и позднее; docs/bench-first-wave.md; data/bench-first-wave.json; имеющиеся источники/проверки карточки.

**Что сдать.** Полный набор hooks/placement с проверкой original bytes, ссылками на native callbacks, проверкой CPU штатного/отказного/повторного пути; никаких fixture callbacks.

**Рекомендуемый чат.** Чат 1 — 01a1f9ae-4a7e-7e31-951a-f6383e1831ee.

**Сейчас выполняет.** Чат 1 — OEM-переходы стендовой H03 — codex-7bd19ea4-0004-4aec-90c4-f2c6e804c046.

**Критерий приёмки.** Полный цикл вызывается автономно, пропуск обнаруживается и без фазы выдачи, тестовые callbacks заменены подтверждёнными целевыми.

[Код, настройки, зависимости и проверки](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/blob/3fe28938163e1dddc98a37733c229390ab7f0fff/docs/project-map.md#h03-03)

</details>

<details>
<summary>H03-04 — Память, стек и сервисные пути: Свободна для продолжения; порция на проверке</summary>

**Сделано.** В общем составе связаны пять сервисных переходов, 14 алиасов RAM/SPI/PSW и резидентная политика. Интегратор разместил 1532 байта неизменённых таблиц в нижнем запасе; известный верх теперь 102200/102356.

**Осталось доделать.** Завершить пять обязательных определений: boot_writers_owned, нижние границы и резервы SPI/PSW с вложенными IRQ/SBI. После остальных поставщиков повторить полное размещение; текущие 156 байт верхнего запаса не являются окончательным резервом.

**Следующий шаг.** Закрой rbm_h03_boot_writers_owned и четыре диапазона SPI/PSW: first/reserve. Аудит reset/IRQ/DMA/service и стеков по штатному BIN, статический граф и симулятор. Нужно реальное владение RAM и отказ при потере, а не функция всегда true. Предоставь итоговые числовые диапазоны со статическим обоснованием и зарезервированными зонами; аппаратный high-water после BIN не должен мешать доказуемой программной части.

**Исходные условия.** main abd3cba и позднее; docs/bench-first-wave.md; data/bench-first-wave.json; имеющиеся источники/проверки карточки.

**Что сдать.** Пять реальных определений/профиль, полный список писателей, linker constraints и доказательства покрытия; стоимость RAM/стеков и сценарии отказа.

**Рекомендуемый чат.** Чат 6 — 01a1f99f-5cb5-70e0-afd0-60e6b41a5d51.

**Исполнитель сейчас.** Задача не занята.

**Критерий приёмки.** Карта сборки и анализ всех владельцев, подтверждённый запас стека и измерения. Свободное окно в ELF само по себе не разрешает запись.

[Код, настройки, зависимости и проверки](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/blob/3fe28938163e1dddc98a37733c229390ab7f0fff/docs/project-map.md#h03-04)

</details>

<details>
<summary>H03-05 — SLT, силовые выходы и реакция на отказ: Свободна для продолжения; порция на проверке</summary>

**Сделано.** Нативный takeover сокращён на 94 байта medium/86 small без роста RAM. Порядок публикации и 13 флагов проверены, штатные выходные сценарии прошли.

**Осталось доделать.** Подключить квалифицированный output profile/takeover ops и подтвердить SLT/SLU, изоляцию и физическую реакцию выходов.

**Следующий шаг.** Доведи реальные native output ops, mapping D/E/F/Pressure A и весь путь command→arbitrate→apply→inhibit. Перепроверь соответствие SLT/SLU и отказов. Нельзя утверждать электрическую изоляцию TIO9 маской без основания. Если конкретное включение требует неизвестного электрического параметра, реализуй диагностическое/комиссионное измерение и явную блокировку именно этого включения; не останавливать запуск/CAN всей системы. Донорские значения с доказуемой применимостью могут быть начальной инженерной настройкой с явно указанными ограничениями, не выдуманной калибровкой давления. Все аппаратные измерения оформить после BIN.

**Исходные условия.** main abd3cba и позднее; docs/bench-first-wave.md; data/bench-first-wave.json; имеющиеся источники/проверки карточки.

**Что сдать.** Реальный output backend/профиль, завершённая программная последовательность переключений и SLU, ограничение непроверенного включения, проверка отзыва каждой команды и минимальный план замеров после сборки.

**Рекомендуемый чат.** Чат 7 — 01a1f9a2-d0ae-78d3-86f1-21b27426fd3f.

**Исполнитель сейчас.** Задача не занята.

**Критерий приёмки.** Измеренные таблицы в допустимой области питания/ATF, реакция каждого выхода и гидравлики на отказ, отсутствие старой команды после восстановления.

[Код, настройки, зависимости и проверки](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/blob/3fe28938163e1dddc98a37733c229390ab7f0fff/docs/project-map.md#h03-05)

</details>

<details>
<summary>VSS-01 — Точный расчёт VSS и скорость по CAN: Свободна для продолжения</summary>

**Сделано.** Объединённый результат 21.11.2026: 0x1AE отбрасывает тайм-аут вне полуоборота TML0 и окно до сужения. PC 41 шаг, 129 тестов Python; M32R, CAN13 и двусторонний Bosch PASS. Отчёт vss01-tml0-timing-admission.md. Целевые привязки, параметры авто и реальная шина открыты.

**Осталось доделать.** Привязать независимое подтверждение остановки и параметры машины, проверить реальную скорость по CAN.

**Следующий шаг.** Доведи rbm_h03_sensor_config и rbm_h03_target_clock_ready для H03, единый TML0 и статус непрерывности. Найди частоты/делители/коэффициенты в исходнике/схеме/регистрах. Раздели вычислимые параметры и будущую измерительную коррекцию; не требовать реальную частоту до выпуска образа. Неподтверждённая оценка должна иметь явный статус и проверку, не называться измеренной. 100/22 сохранять точно, не угадывать окружность колеса. Реализовать выдачу raw speed/capture для будущей калибровки.

**Исходные условия.** main abd3cba и позднее; docs/bench-first-wave.md; data/bench-first-wave.json; имеющиеся источники/проверки карточки.

**Что сдать.** Компилируемый native профиль часов и датчиков, проверка reset/wrap/stall/clock change; список только действительно аппаратных параметров для замера после прошивки.

**Рекомендуемый чат.** Чат 5 — 01a1f9a8-7b61-7763-adaa-0e3e11d1dbf4.

**Исполнитель сейчас.** Задача не занята.

**Критерий приёмки.** Округление 4,545 не используется как расчётный коэффициент.

[Код, настройки, зависимости и проверки](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/blob/3fe28938163e1dddc98a37733c229390ab7f0fff/docs/project-map.md#vss-01)

</details>

<details>
<summary>VSS-02 — Кинематика и параметры реальной скорости: Выполняется</summary>

**Сделано.** Foreground сравнивает относительный ход TML0/TML1; разрыв отзывает эпоху и очищает S51/S83/ATF. Исправлен воспроизведённый дефект 06ab447; добавлено 12 байт типизированного состояния.

**Осталось доделать.** Сохранить контроль непрерывности и дать квалифицированную абсолютную частоту/профиль датчиков. Относительное совпадение двух счётчиков не доказывает их масштаб.

**Следующий шаг.** Доведи rbm_h03_sensor_config и rbm_h03_target_clock_ready для H03, единый TML0 и статус непрерывности. Найди частоты/делители/коэффициенты в исходнике/схеме/регистрах. Раздели вычислимые параметры и будущую измерительную коррекцию; не требовать реальную частоту до выпуска образа. Неподтверждённая оценка должна иметь явный статус и проверку, не называться измеренной. 100/22 сохранять точно, не угадывать окружность колеса. Реализовать выдачу raw speed/capture для будущей калибровки.

**Исходные условия.** main abd3cba и позднее; docs/bench-first-wave.md; data/bench-first-wave.json; имеющиеся источники/проверки карточки.

**Что сдать.** Компилируемый native профиль часов и датчиков, проверка reset/wrap/stall/clock change; список только действительно аппаратных параметров для замера после прошивки.

**Рекомендуемый чат.** Чат 5 — 01a1f9a8-7b61-7763-adaa-0e3e11d1dbf4.

**Сейчас выполняет.** Copilot LFJ8 sensor measurement contract — copilot-lfj8-sensor-contract-a4a37091.

**Критерий приёмки.** Скорость совпадает с эталоном в согласованном диапазоне, потеря импульсов отличается от остановки.

[Код, настройки, зависимости и проверки](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/blob/3fe28938163e1dddc98a37733c229390ab7f0fff/docs/project-map.md#vss-02)

</details>

<details>
<summary>MODE-01 — Логика шести положений и кнопок: Свободна для продолжения</summary>

**Сделано.** Объединённый результат 21.11.2026: INVALID/OVERRUN сразу отзывают диапазон независимо от метки. 10 сценариев ПК/M32R, input-binding, 18+8 компонентных и 6 размещённых сценариев PASS. +20 байт Flash. Полный линк FAIL_BINDINGS. Отчёт mode01-selector-fault.md.

**Осталось доделать.** Подключить реальный захват к foreground и провести ручную заявку через весь гидравлический цикл.

**Следующий шаг.** Доведи реальные P/R/N/D/2/L, Tiptronic +/−/toggle и OD до Toyota cycle с блокировкой опасных/противоречивых входов. Профиль из схемы, кода и расчёта ADC/резисторов, не test constants. Пересчитай сопротивления 2/L с номиналами/допусками/исходной схемой: если аппаратный делитель известен из исходников, рассчитать до замера; если нет — указать конкретно неизвестный элемент, не выдумывать ом. Режим после reset и допустимость команды фиксировать явно, с происхождением/решением.

**Исходные условия.** main abd3cba и позднее; docs/bench-first-wave.md; data/bench-first-wave.json; имеющиеся источники/проверки карточки.

**Что сдать.** Native mode/input profile, расчёт диапазонов/резисторов и полная цепь ручного запроса, debounce/hold/opposed/stale/reset tests.

**Рекомендуемый чат.** Чат 11 — 01a1fa79-892d-7ca3-bb8a-44698892c53e.

**Исполнитель сейчас.** Задача не занята.

**Критерий приёмки.** Компонентный requested_gear не равен выполненному гидравлическому переключению.

[Код, настройки, зависимости и проверки](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/blob/3fe28938163e1dddc98a37733c229390ab7f0fff/docs/project-map.md#mode-01)

</details>

<details>
<summary>MODE-02 — Подключение селектора, Tiptronic и Overdrive: Выполняется</summary>

**Сделано.** Нативный AN2/P1DATA поддерживает явные окна и политику; startup сбрасывает владельцев до CAN. Общие host/M32R проверки прошли.

**Осталось доделать.** Задать обоснованные окна ADC, карту входов и тайминги; подключить квалифицированные Toyota inputs в окончательном профиле.

**Следующий шаг.** Доведи реальные P/R/N/D/2/L, Tiptronic +/−/toggle и OD до Toyota cycle с блокировкой опасных/противоречивых входов. Профиль из схемы, кода и расчёта ADC/резисторов, не test constants. Пересчитай сопротивления 2/L с номиналами/допусками/исходной схемой: если аппаратный делитель известен из исходников, рассчитать до замера; если нет — указать конкретно неизвестный элемент, не выдумывать ом. Режим после reset и допустимость команды фиксировать явно, с происхождением/решением.

**Исходные условия.** main abd3cba и позднее; docs/bench-first-wave.md; data/bench-first-wave.json; имеющиеся источники/проверки карточки.

**Что сдать.** Native mode/input profile, расчёт диапазонов/резисторов и полная цепь ручного запроса, debounce/hold/opposed/stale/reset tests.

**Рекомендуемый чат.** Чат 11 — 01a1fa79-892d-7ca3-bb8a-44698892c53e.

**Сейчас выполняет.** LFJ8 selector measurement contract — b9841cd6-bb32-4ab5-a5d7-3d1df09009f5.

**Критерий приёмки.** Реальные нажатия проходят до исполнения запроса в полном цикле, дребезг/обрыв не создают повторных команд.

[Код, настройки, зависимости и проверки](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/blob/3fe28938163e1dddc98a37733c229390ab7f0fff/docs/project-map.md#mode-02)

</details>

<details>
<summary>MODE-03 — Окончательная политика режимов: Выполняется</summary>

**Сделано.** Объединённый результат 21.11.2026: На актуальной main с 64dd049 общий контроллер отвергает заявки до принятия профиля и после отказа init. ПК 41/129, матрица и привязка H03 на ПК/M32R, M32R 18+8 и 6 проверок размещения. Карта RAM совпала. Отчёт mode03-policy-init-gate.md. Политика выпуска и стенд открыты.

**Осталось доделать.** Зафиксировать начальный режим, сохранение OD, допустимые ручные диапазоны и ограничения окончательного профиля; связать с реальными входами.

**Следующий шаг.** Доведи реальные P/R/N/D/2/L, Tiptronic +/−/toggle и OD до Toyota cycle с блокировкой опасных/противоречивых входов. Профиль из схемы, кода и расчёта ADC/резисторов, не test constants. Пересчитай сопротивления 2/L с номиналами/допусками/исходной схемой: если аппаратный делитель известен из исходников, рассчитать до замера; если нет — указать конкретно неизвестный элемент, не выдумывать ом. Режим после reset и допустимость команды фиксировать явно, с происхождением/решением.

**Исходные условия.** main abd3cba и позднее; docs/bench-first-wave.md; data/bench-first-wave.json; имеющиеся источники/проверки карточки.

**Что сдать.** Native mode/input profile, расчёт диапазонов/резисторов и полная цепь ручного запроса, debounce/hold/opposed/stale/reset tests.

**Рекомендуемый чат.** Чат 11 — 01a1fa79-892d-7ca3-bb8a-44698892c53e.

**Сейчас выполняет.** Copilot — MODE-03 manual policy continuation — copilot-mode03-20261124-0829-9b51a672-80d4-41d8-b003-2ccf7df38731.

**Критерий приёмки.** Политика согласована с донорской логикой и подтверждена матрицей режимов. Тестовые defaults не выдаются за решение владельца.

[Код, настройки, зависимости и проверки](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/blob/3fe28938163e1dddc98a37733c229390ab7f0fff/docs/project-map.md#mode-03)

</details>

<details>
<summary>REL-01 — Два целевых BIN и воспроизводимый комплект: Выполняется</summary>

**Сделано.** Добавлена детерминированная сборка байтов полного H03 ELF с проверкой исходных участков и всех секций. Проверены 12 новых сценариев. Полного native ELF и TCM BIN ещё нет; работают 12 чатов первой стендовой волны.

**Осталось доделать.** Закончить реальные профили/поставщики, полный native link и все redirects, сериализацию TCM BIN, целевую Bosch пару, целостность, сквозные проверки и манифест. Измерения новой пары следуют после выдачи файлов.

**Следующий шаг.** Интегрировать 12 направлений из bench-first-wave; свести профили и доказать конечный запуск/размещение/целостность; выдать два BIN для первого стенда только после программной готовности.

**Исходные условия.** Все обязательные задачи первого этапа; два реле и панель отложены. Десять unresolved — не весь остаток проекта.

**Что сдать.** TCM BIN + Bosch BIN + SHA/manifest, карты правок, применимость и фактические результаты приёмки.

**Сейчас выполняет.** Copilot — REL-01 package evidence follow-up — bd412180-9ccb-4a23-a04a-ad23931a72a0.

**Критерий приёмки.** Два целевых реализованных BIN, source/final SHA и карта правок, воспроизводимая сборка, подтвержденные software checks, явные ограничения первого стенда. Аппаратная приемка учитывается отдельно в REL-02.

[Код, настройки, зависимости и проверки](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/blob/3fe28938163e1dddc98a37733c229390ab7f0fff/docs/project-map.md#rel-01)

</details>

<details>
<summary>REL-02 — Приёмка новой связки на оборудовании: Свободна для продолжения</summary>

**Сделано.** Объединённый результат 21.11.2026: Нативная проверка десяти DMA-каналов в холодном допуске RAM H03. M32R: 97142 байта, 5214 номинальный остаток. Адресный ELF H03-04: 27 писателей, 28 закрытий сеанса и 512 Virtual Flash. Остаются привязка приложения и датчиков, доказательство последующего владения DMA/SBI/IRQ, запись нижней Flash через PCM Flash; это порция REL-02.

**Осталось доделать.** Аппаратная приемка начинается после получения двух BIN и прошивки владельцем. До этого — подготовить исполнимый минимальный протокол и встроенные средства чтения реальных величин.

**Следующий шаг.** Выполнить минимальный аппаратный протокол на целевой паре после соответствующей программной сборки.

**Исходные условия.** Доступ к оборудованию отсутствует; результат невозможно заменить симуляцией. Не отмечать выполненным без измерений.

**Что сдать.** Фактические записи входов/CAN/момента/SLT/SLU и отказов с критериями приёмки.

**Исполнитель сейчас.** Задача не занята.

**Критерий приёмки.** Журналы содержат версии BIN, условия, измерения, допуски и результат. Программные тесты учитываются отдельно.

[Код, настройки, зависимости и проверки](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/blob/3fe28938163e1dddc98a37733c229390ab7f0fff/docs/project-map.md#rel-02)

</details>

<details>
<summary>DTC-01 — Прикладной сеанс и статусы Chery: Свободна для продолжения</summary>

**Сделано.** Старый сеанс RX очищается до проверки TX/FC timeout; при потере foreground clock допуск отзывается. Host/M32R регрессии прошли.

**Осталось доделать.** Включить транспорт с реальными таймингами и native CAN в итоговый образ; проверить прикладной сеанс на общей целевой конфигурации.

**Следующий шаг.** Доведи штатный запрос→RX→сеанс→TX13 ответ и события всех подсистем, статусы/очистку. Перепроверь таблицу Toyota/Chery и не придумывай code correspondence. Первичный стенд должен позволять получить реальные сырые S51/S83/ATF, clock, voltage/current если доступны АЦП, output command/qualifier, torque handshake и причины inhibit. Добавь компактный реальный измерительный путь/документированные запросы, если имеющихся недостаточно. Никаких sample values; измерительный протокол должен работать в собираемой паре.

**Исходные условия.** main abd3cba и позднее; docs/bench-first-wave.md; data/bench-first-wave.json; имеющиеся источники/проверки карточки.

**Что сдать.** Полный native diagnostic path и реестр команд/полей; отказные проверки и минимальный протокол после BIN с местом/режимом/критерием измерения; что штатный Chery сканер поддерживает, а что проектный readout.

**Рекомендуемый чат.** Чат 10 — 01a1fa76-b015-7640-a0ba-433b36dcf55f.

**Исполнитель сейчас.** Задача не занята.

**Критерий приёмки.** Поддержан конкретный профиль CAN C0. Остальные FC/сервисы и K-Line не объявлены реализованными.

[Код, настройки, зависимости и проверки](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/blob/3fe28938163e1dddc98a37733c229390ab7f0fff/docs/project-map.md#dtc-01)

</details>

<details>
<summary>DTC-02 — Штатный приём BasicCAN для диагностического сеанса: Выполняется</summary>

**Сделано.** Закрыт обход service mode/Flash bank, RX15 повторно проверяется после RX14; нижние переходы и общая CAN-компоновка прошли отдельные адресные проверки.

**Осталось доделать.** Установить полный набор RX/service/monitor переходов в итоговый образ и подтвердить банк Flash и время IRQ в совместной конфигурации.

**Следующий шаг.** Доведи штатный запрос→RX→сеанс→TX13 ответ и события всех подсистем, статусы/очистку. Перепроверь таблицу Toyota/Chery и не придумывай code correspondence. Первичный стенд должен позволять получить реальные сырые S51/S83/ATF, clock, voltage/current если доступны АЦП, output command/qualifier, torque handshake и причины inhibit. Добавь компактный реальный измерительный путь/документированные запросы, если имеющихся недостаточно. Никаких sample values; измерительный протокол должен работать в собираемой паре.

**Исходные условия.** main abd3cba и позднее; docs/bench-first-wave.md; data/bench-first-wave.json; имеющиеся источники/проверки карточки.

**Что сдать.** Полный native diagnostic path и реестр команд/полей; отказные проверки и минимальный протокол после BIN с местом/режимом/критерием измерения; что штатный Chery сканер поддерживает, а что проектный readout.

**Рекомендуемый чат.** Чат 10 — 01a1fa76-b015-7640-a0ba-433b36dcf55f.

**Сейчас выполняет.** Codex чат 10 — чтение статуса NVM — 01a1fa76-b015-7640-a0ba-433b36dcf55f.

**Критерий приёмки.** Прогон оригинального пути RX с потерей/перезаписью и ложными кадрами. Учтена граница приложения 0x008000.

[Код, настройки, зависимости и проверки](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/blob/3fe28938163e1dddc98a37733c229390ab7f0fff/docs/project-map.md#dtc-02)

</details>

<details>
<summary>DTC-03 — Все диагностические события и соответствия Toyota/Chery: Выполняется</summary>

**Сделано.** ATF fault допускается только с квалифицированным источником времени; native сценарии и отказ часов прошли.

**Осталось доделать.** Подключить реальную характеристику ATF, диагностические пороги и временные пределы; проверить их с датчиком.

**Следующий шаг.** Доведи штатный запрос→RX→сеанс→TX13 ответ и события всех подсистем, статусы/очистку. Перепроверь таблицу Toyota/Chery и не придумывай code correspondence. Первичный стенд должен позволять получить реальные сырые S51/S83/ATF, clock, voltage/current если доступны АЦП, output command/qualifier, torque handshake и причины inhibit. Добавь компактный реальный измерительный путь/документированные запросы, если имеющихся недостаточно. Никаких sample values; измерительный протокол должен работать в собираемой паре.

**Исходные условия.** main abd3cba и позднее; docs/bench-first-wave.md; data/bench-first-wave.json; имеющиеся источники/проверки карточки.

**Что сдать.** Полный native diagnostic path и реестр команд/полей; отказные проверки и минимальный протокол после BIN с местом/режимом/критерием измерения; что штатный Chery сканер поддерживает, а что проектный readout.

**Рекомендуемый чат.** Чат 10 — 01a1fa76-b015-7640-a0ba-433b36dcf55f.

**Сейчас выполняет.** Copilot — native diagnostic field provider — copilot-71f474e418d946d2ab3d84e52afb56f1.

**Критерий приёмки.** Код соответствует фактическому отказу и узлу, статусы подтверждены. Отсутствующий прямой аналог явно обозначен.

[Код, настройки, зависимости и проверки](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/blob/3fe28938163e1dddc98a37733c229390ab7f0fff/docs/project-map.md#dtc-03)

</details>

<details>
<summary>DTC-04 — Хранение DTC после выключения питания: Выполняется</summary>

**Сделано.** Без постоянного носителя нет ложного успешного clear; штатный запрос 14FF00 потребляется, P0710 сохраняется. Restore блокируется при неподходящем банке Flash.

**Осталось доделать.** Реализовать и привязать постоянный NVM backend с доказанными двумя стираемыми блоками, владением записью и отказами питания; read-only array path не является записью.

**Следующий шаг.** Доведи реальный read/write/erase backend с геометрией и исключением стёртых программных областей, two-slot commit и поведение при прерывании питания. Не назначать два пустых блока по догадке. Если безопасная запись объективно не выводится из имеющихся данных, доведи bootable non-destructive inspection/readout и явный статус unavailable persistence для первичного стенда, сохрани финальное требование открытым. Такую деградацию нельзя выдавать за полное выполнение ТЗ. Подготовь независимый backend без fixture qualified_adaptation_blocks.

**Исходные условия.** main abd3cba и позднее; docs/bench-first-wave.md; data/bench-first-wave.json; имеющиеся источники/проверки карточки.

**Что сдать.** Рабочий backend или конкретная доказанная граница его доступности, профиль носителя/проверка восстановления, подлинные Flash-адреса; телеметрия для получения недостающего после BIN.

**Рекомендуемый чат.** Чат 9 — 01a1fa76-922b-7b11-a2f2-346a15d1dc95.

**Сейчас выполняет.** Чат 9 — холодный старт и транспорт NVM — 01a1fa76-922b-7b11-a2f2-346a15d1dc95.

**Критерий приёмки.** Перезапуск и прерванная запись не восстанавливают очищенную или повреждённую историю.

[Код, настройки, зависимости и проверки](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/blob/3fe28938163e1dddc98a37733c229390ab7f0fff/docs/project-map.md#dtc-04)

</details>

## История предыдущих исполнителей

<details>
<summary>Принятые, сданные и освобождённые порции — это не текущая работа</summary>

| Задача | Состояние порции | Предыдущий исполнитель | Ветка | Результат |
| --- | --- | --- | --- | --- |
| TOY-01 | Порция принята | Codex TOY-01 H03 independent release clock | codex/toy01-h03-release-clock-01a1f99f | Порция включена и проверена в main 55b9a240338e. Проверки относятся к указанному объёму; готовность BIN не объявлена. / commit c53aaf01d85f38f3fded16ae2c75ef52009f5bd9 |
| TOY-02 | На проверке | Чат 4 — нативные входы Toyota и сырой Bosch CAN | codex/toy02-load-evidence-01a1f9c7 | Сырой контракт Bosch 0x6B2, приём стабильной BasicCAN копии и штатный H03 capture вместо test_input_capture собраны. ПК/M32R RX→GP прошли; найдены все 8 writer S01 и бит режима, сверены 198 инструкций, повторены C167 и аудит CAN. Остались издатель, dispatch, порядок первого release и обоснованные project_load/read_local. Handoff verification/bench-wave/chat-4/handoff.json. / commit 7a7ac7f97d328cd6f5de88f02c043b1f8b21efac |
| TOY-03 | Порция принята | Codex TOY-03 — допуск независимого P/N | codex/toy03-independent-pn-mwp5rm2ofhaxjfi9dss | Порция включена и проверена в main 55b9a240338e. Проверки относятся к указанному объёму; готовность BIN не объявлена. / commit 3f2596f31930203fe9cd7918e9b62f81ea82699c |
| TOY-04 | Порция принята | Codex TOY-04 — ручная заявка в цикле | codex/toy04-manual-cycle-892d | Порция включена и проверена в main 55b9a240338e. Проверки относятся к указанному объёму; готовность BIN не объявлена. / commit c7b0568cde39ddc27e71432e5028db9c9a351e16 |
| TOY-06 | На проверке | Copilot TOY-06 SLU command | almir458765-toy-06-slu-outputs | Published six-file software-only SLU demand and revoke change. git diff --check and Python AST/ctypes layout checks pass. Focused host/Zig and M32R execution blocked: local project-paths.json and .sources/R1/.sources/R2 are absent; Zig and M32R GCC are not on PATH. No hardware/channel/response verification; no profile, scale, or mapping added. / commit 4a5565f145d2a7b3aad81d35cef70b8251f4a24a |
| CAN-01 | На проверке | Copilot — LFJ8 CAN and torque | almirpangor-lfj8-can-and-torque | Published commit 50202944bbe2206d79c948757752b5a3e7669007. PC evidence: controller host tests PASS under GCC 16.2 after demoting only legacy array-parameter, misleading-indentation, and missing-braces warnings; input-binding fixture compiled with -Werror and PASS; exact-H03 engine-context host replay PASS. M32R evidence: GCC 4.8.0 target m32r-elf; controller target build/simulator suite PASS; check_h03_input_binding.py PASS on M32R simulator; exact-H03 engine-context replay PASS on host and M32R simulator. H03 base: 524288 bytes, SHA-256 844a11b809cda1f2ccaf90cb6a75666009487ccedd2e8190b7eb46137b855544. Pinned Bosch trace SHA-256 e9df9cbcae6eb741b9863688f7bbacd16f19064c063b76549f8b56939ca03b4b. Test ELF SHA-256 43a8448beb0b27773034fc4363f4236a2f92be9fb8d8507862a537089f06e716; M32R controller object SHA-256 13b42c89f3af237bbdc1307149918328561f0226f1443706d53160fc23c36ead. Simulator --version is unsupported; executable SHA-256 85D3CAD2770065C4F4A31571C924F092B8AA1AAC9C6C22F504A64E1003E87F38. Hardware not tested; no flashable image or release BIN created. Full release target-link/integrity gates remain outstanding. GCC 4.8 reports stack-usage computation unsupported for M32R. Independent FA7B fallback is unavailable and remains FF; timing values are engineering bounds, not measurements. project_status --check still reports changed files pending review/retest; no shared audit/registry files were modified. / commit 50202944bbe2206d79c948757752b5a3e7669007 |
| CAN-02 | Порция принята | Codex CAN-02 — деградация скорости в телеметрии H03 | codex/can02-telemetry-availability-fea1b366 | Порция включена в main 06ab447. Общая проверка сохранена в integration-39-20261121; приёмка порции не означает готовность BIN. Остаток отражён в карточке. / commit d87bf6438a30efd448feb8cac1d732f7d677a20c |
| CAN-05 | Порция принята | Codex CAN-05 — время приёма ST10 | codex/can05-st10-bound-t4-01a1f9a2 | Порция включена и проверена в main 55b9a240338e. Проверки относятся к указанному объёму; готовность BIN не объявлена. / commit f3bb5000ebfdaaa30a33665bac1eab06ddb9165c |
| ECU-02 | Порция принята | Codex ECU-02 — граница допуска момента Bosch | codex/ecu02-torque-permit-boundary-7bd19ea4 | Порция включена и проверена в main 55b9a240338e. Проверки относятся к указанному объёму; готовность BIN не объявлена. / commit 85b2e9320cf8f6e4a3729915ed3ebbd0fc00a732 |
| H03-02 | Порция принята | Codex H03-02 — граница свежести общего снимка S51/S83/ATF | codex/h03-02-capture-end-age-32e6ac79 | Порция включена в main 06ab447. Общая проверка сохранена в integration-39-20261121; приёмка порции не означает готовность BIN. Остаток отражён в карточке. / commit 3e9e9b2fb888e7d26161dde12e2bd0dcf3600c53 |
| H03-04 | На проверке | Copilot H03-04 software-only continuation | almirpangor-lfj8-h03-platform | Published software-only guard update. RAM admission now requires at least the existing H03 profile reserves (SPI 1040 B, PSW 64 B); M32R compilation and boundary tests cover exact fit, under-reserve, and misalignment. Profile/placement Python tests: 8 pass; checker imports; diff check passes. Full donor-based M32R replay, final linked stack proof, physical high-water, and hardware qualification remain open; no BIN. / commit f3a320fe7c66dc9f258f23ec14abbf2e5c0d2c60 |
| H03-05 | На проверке | Codex 7 H03-05 bench outputs | codex/h03-05-bench-output-01a1f9a2 | Чат 7: native bench profile запускает phase_startup с mask=0 и без actuator callbacks. D/E/F, Pressure A и TIO9 отозваны в обеих штатных фазах, есть снимок AN3/таймеров. Native 22/22, components 8/8; common small через --binding-source 106944 байта, 14 нерешённых ссылок. Подключение обоих redirect и типизированного alias, пределы и измерения в verification/bench-wave/chat-7/handoff.json. Активный силовой допуск открыт. / commit 0a9523b203a2cae2b21a81da4c14ce910b570ed3 |
| VSS-01 | Порция принята | Codex VSS-01 — допуск времени и окна S51 для 0x1AE | codex/vss01-tml0-timing-admission-32e6ac79 | Порция включена и проверена в main 55b9a240338e. Проверки относятся к указанному объёму; готовность BIN не объявлена. / commit 1bcfe06eb116940db1921a70130629bacb17da3a |
| MODE-01 | Порция принята | Codex MODE-01 — отзыв диапазона при отказе ADC | codex/mode01-selector-fault-mwp5rm2ofhaxjfi9dss | Порция включена и проверена в main 55b9a240338e. Проверки относятся к указанному объёму; готовность BIN не объявлена. / commit 8974a4a5002fd1786eb02ad8d7c19a829c47ad6f |
| REL-02 | Порция принята | Codex REL-02 H03 DMA admission | codex/rel02-h03-ram-owner-01a1f99f | Порция включена и проверена в main 55b9a240338e. Проверки относятся к указанному объёму; готовность BIN не объявлена. / commit 8ce841939a365433161c7e1fe5c51f9c0ca3a27b |
| DTC-01 | Порция принята | Codex DTC-01 — граница RX при тайм-ауте протокола | codex/dtc01-transport-expiry-rx-7bd19ea4 | Порция включена в main 06ab447. Общая проверка сохранена в integration-39-20261121; приёмка порции не означает готовность BIN. Остаток отражён в карточке. / commit 0941e55fb9be406f3f8d5b3cb7d378aa18205349 |
| AUD-01 | Освобождена | Codex AUD-01 — проверка архивного пакета R4 | codex/aud01-e4m3-diff-check-922b7b11 | Изолированный архивный прогон R4 завершён: 50 хешей и точная пересборка E4M3, статическая проверка, ST10, CAN и ISO-TP прошли. Отчёт сохранён только локально. Резерв освобождён. |
| H03-01 | Порция принята | Codex H03-01 — сверка прочитанного образа | codex/h03-01-readback-01a1f9a2 | Порция включена и проверена в main 55b9a240338e. Проверки относятся к указанному объёму; готовность BIN не объявлена. / commit 57bf9ee7cfa47b68da922524f729a284a69f54b4 |
| SRC-01 | Порция принята | Codex SRC-01 — регрессия происхождения исходников | codex/src01-pinned-input-tests-922b7b11 | Порция включена и проверена в main 55b9a240338e. Проверки относятся к указанному объёму; готовность BIN не объявлена. / commit 30a37a9f5672164bb8326dcc76d9581dc83c01db |

</details>


## Зарезервированные файлы

### CAN-03

Чат: Codex чат 3 — стендовый CAN-сервис H03. Claim ID: 75c3a1267f8f44f4b4f8ee55b2209a3d.

- targets/lfj8/bench_can_profile.h
- targets/lfj8/check_h03_can_monitor_revoke.py
- targets/lfj8/h03_application_binding_fixture.c
- targets/lfj8/h03_phase_boot_fixture.c
- targets/lfj8/lfj8_h03_application.c
- targets/lfj8/lfj8_h03_application.h
- targets/lfj8/lfj8_h03_can_monitor_revoke.c
- targets/lfj8/lfj8_h03_can_service_placement.py
- targets/lfj8/lfj8_h03_target_service.c
- targets/lfj8/lfj8_h03_target_service.h
- verification/bench-wave/chat-3/handoff.json

### CAN-04

Чат: Copilot App — запрос снижения момента CAN LFJ8. Claim ID: ce83cd1a727f4f35b11669ace40612a6.

- targets/bosch/replay_e4m3_torque.py
- targets/lfj8/lfj8_h03_torque.c
- targets/lfj8/lfj8_h03_torque.h
- targets/lfj8/test_lfj8_h03_torque.c
- targets/lfj8/verify_h03_torque.py

### DTC-02

Чат: Codex чат 10 — чтение статуса NVM. Claim ID: 01ed3d5484bc4ed8ba80d481a8f6bf41.

- targets/lfj8/check_h03_dtc_basiccan.py
- targets/lfj8/lfj8_h03_bench_diag.c
- targets/lfj8/test_lfj8_h03_bench_diag.c
- verification/bench-wave/chat-10/diagnostic-readout.md
- verification/bench-wave/chat-10/handoff.json

### DTC-03

Чат: Copilot — native diagnostic field provider. Claim ID: 20021c325c344497a1a35bf986ba306c.

- docs/diagnostics-integration.md
- targets/lfj8/check_h03_atf_fault.py
- targets/lfj8/h03_atf_fault_hook_fixture.c
- targets/lfj8/lfj8_h03_dtc_target.c
- targets/lfj8/lfj8_h03_dtc_target.h
- verification/project-audit/dtc03-ta2005-p0710.md

### DTC-04

Чат: Чат 9 — холодный старт и транспорт NVM. Claim ID: da790f0c3ad843249d6f874c176bc923.

- targets/lfj8/check_h03_bench_nvm_startup_transport.py
- targets/lfj8/h03_bench_nvm_startup_transport_fixture.c
- verification/bench-wave/chat-9/startup-transport.json

### ECU-01

Чат: Copilot — Bosch paired release. Claim ID: bc0dfc8cdfdc4082a71ddedafc6073dc.

- targets/bosch/build.py
- targets/bosch/compact_branches.py
- targets/bosch/tx.py
- tests/test_bosch_build_integrity.py

### H03-03

Чат: Чат 1 — OEM-переходы стендовой H03. Claim ID: b97db66371c34c108201a317218dcc3f.

- targets/lfj8/check_h03_bench_entries.py
- targets/lfj8/check_h03_phase_boot.py
- targets/lfj8/check_h03_phase_wait.py
- targets/lfj8/h03_bench_strategy_fixture.c
- targets/lfj8/h03_native_hooks.S
- targets/lfj8/h03_phase_wait_fixture.c
- targets/lfj8/h03_phase_wait_hook.S
- targets/lfj8/lfj8_h03_application_placement.py
- targets/lfj8/lfj8_h03_bench_entry_profile.py
- targets/lfj8/lfj8_h03_target_strategy.c
- targets/lfj8/lfj8_h03_target_strategy.h
- tests/test_h03_application_placement.py
- verification/bench-wave/chat-1/handoff.json

### MODE-02

Чат: LFJ8 selector measurement contract. Claim ID: 6e1c036c5cc7436590b1e7c909edb2d2.

- verification/bench-wave/chat-selector-measurement-contract.md

### MODE-03

Чат: Copilot — MODE-03 manual policy continuation. Claim ID: 3e90cfe1f0d4488aa17308b72d24d98e.

- controller/include/rbm_u340e.h
- controller/src/rbm_u340e.c
- controller/tests/test_mode_policy.c
- targets/lfj8/lfj8_h03_input_binding.c
- targets/lfj8/test_lfj8_h03_input_binding.c

### ORG-01

Чат: Ведущй — общая сборка и задания для стендовой пары. Claim ID: ae03538ba15145cc876e680b118fd0ae.

- AGENTS.md
- README.md
- data/bench-first-wave.json
- data/project-tasks.json
- docs/bench-first-wave.md
- docs/decisions.md
- docs/integration-next-tasks.md
- docs/project-map.md
- docs/working-set.md
- tests/test_h03_image.py
- tools/check_h03_image_layout.py
- tools/h03_image.py
- verification/project-audit/bench-first-20261121/

### REL-01

Чат: Copilot — REL-01 package evidence follow-up. Claim ID: 7cb4836dcb9343c6bfcec71a4e5371e6.

- verification/project-audit/rel01-offline-report-guard.md

### TOY-05

Чат: Codex 12 — TOY-05, стартовое состояние первой стендовой пары. Claim ID: 5ec8d9943cbd4616ab0bbf37dcec141b.

- controller/include/rbm_u340e_runtime.h
- controller/src/rbm_u340e_runtime.c
- controller/tests/test_runtime.c
- targets/lfj8/bench_startup_profile.c
- targets/lfj8/bench_startup_profile.h
- targets/lfj8/check_h03_bench_startup.py
- targets/lfj8/h03_application_hooks.S
- targets/lfj8/h03_bench_startup_fixture.c
- verification/bench-wave/chat-12/handoff.json

### VSS-02

Чат: Copilot LFJ8 sensor measurement contract. Claim ID: b1e4a5f6767647a0b73dba524a900759.

- verification/bench-wave/chat-5/handoff.json

## Последние события

| UTC | Задача | Действие | Чат |
| --- | --- | --- | --- |
| 2026-11-24T06:41:14+00:00 | DTC-03 | claim | copilot-71f474e418d946d2ab3d84e52afb56f1 |
| 2026-11-24T06:41:00+00:00 | REL-01 | claim | bd412180-9ccb-4a23-a04a-ad23931a72a0 |
| 2026-11-24T06:39:01+00:00 | REL-01 | review | bd412180-9ccb-4a23-a04a-ad23931a72a0 |
| 2026-11-24T06:38:21+00:00 | REL-01 | claim | bd412180-9ccb-4a23-a04a-ad23931a72a0 |
| 2026-11-24T06:38:09+00:00 | H03-04 | review | 6f772758-d43b-4665-ad67-3eeb2481501a |
| 2026-11-24T06:36:28+00:00 | DTC-03 | review | copilot-0bc0cbc673de4134ab7d7b9afeb082a2 |
| 2026-11-24T06:36:22+00:00 | REL-01 | review | bd412180-9ccb-4a23-a04a-ad23931a72a0 |
| 2026-11-24T06:36:08+00:00 | DTC-03 | heartbeat | copilot-0bc0cbc673de4134ab7d7b9afeb082a2 |
| 2026-11-24T06:35:54+00:00 | REL-01 | claim | bd412180-9ccb-4a23-a04a-ad23931a72a0 |
| 2026-11-24T06:35:14+00:00 | H03-04 | heartbeat | 6f772758-d43b-4665-ad67-3eeb2481501a |
| 2026-11-24T06:34:37+00:00 | H03-04 | heartbeat | 6f772758-d43b-4665-ad67-3eeb2481501a |
| 2026-11-24T06:33:44+00:00 | H03-04 | claim | 6f772758-d43b-4665-ad67-3eeb2481501a |
| 2026-11-24T06:33:28+00:00 | REL-01 | review | bd412180-9ccb-4a23-a04a-ad23931a72a0 |
| 2026-11-24T06:32:15+00:00 | DTC-03 | heartbeat | copilot-0bc0cbc673de4134ab7d7b9afeb082a2 |
| 2026-11-24T06:31:49+00:00 | REL-01 | claim | bd412180-9ccb-4a23-a04a-ad23931a72a0 |
| 2026-11-24T06:31:41+00:00 | DTC-03 | heartbeat | copilot-0bc0cbc673de4134ab7d7b9afeb082a2 |
| 2026-11-24T06:31:36+00:00 | ECU-01 | heartbeat | 9d4fcd7f-8d30-447e-b31d-6889553c0e20 |
| 2026-11-24T06:31:14+00:00 | DTC-03 | claim | copilot-0bc0cbc673de4134ab7d7b9afeb082a2 |
| 2026-11-24T06:29:14+00:00 | ECU-01 | heartbeat | 9d4fcd7f-8d30-447e-b31d-6889553c0e20 |
| 2026-11-24T06:07:38+00:00 | TOY-06 | review | 631778fb-a3af-4621-8fcd-9b34d66cd355 |
| 2026-11-24T06:07:12+00:00 | TOY-06 | heartbeat | 631778fb-a3af-4621-8fcd-9b34d66cd355 |
| 2026-11-24T05:59:48+00:00 | MODE-03 | claim | copilot-mode03-20261124-0829-9b51a672-80d4-41d8-b003-2ccf7df38731 |
| 2026-11-24T05:59:44+00:00 | TOY-06 | claim | 631778fb-a3af-4621-8fcd-9b34d66cd355 |
| 2026-11-24T05:10:25+00:00 | VSS-02 | claim | copilot-lfj8-sensor-contract-a4a37091 |
| 2026-11-24T05:09:17+00:00 | MODE-02 | claim | b9841cd6-bb32-4ab5-a5d7-3d1df09009f5 |
| 2026-11-24T05:07:50+00:00 | ECU-01 | heartbeat | 9d4fcd7f-8d30-447e-b31d-6889553c0e20 |
| 2026-11-24T05:07:01+00:00 | ECU-01 | heartbeat | 9d4fcd7f-8d30-447e-b31d-6889553c0e20 |
| 2026-11-24T04:48:43+00:00 | VSS-02 | review | 2a528e3d-3ef6-473c-a1f9-4222181d2edf |
| 2026-11-24T04:48:14+00:00 | VSS-02 | block | 2a528e3d-3ef6-473c-a1f9-4222181d2edf |
| 2026-11-24T04:40:08+00:00 | VSS-02 | claim | 2a528e3d-3ef6-473c-a1f9-4222181d2edf |
