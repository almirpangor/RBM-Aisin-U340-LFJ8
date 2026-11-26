# VSS-02 — допуск часов TML0/TML1 при запуске H03

База — `f64eff7c24744cef0fe608415039c6d10c677ff1`. В неё входит предыдущая порция VSS-01 `1bcfe06eb116940db1921a70130629bacb17da3a`. Проверки использовали H03 LFJ8-18-9E1C с SHA-256 `844a11b809cda1f2ccaf90cb6a75666009487ccedd2e8190b7eb46137b855544`.

## Подключение

`check_h03_sensor_config.py --emit-config` теперь выдаёт одним исходником `rbm_h03_sensor_config` и `rbm_h03_target_clock_ready`. Для генерации нужны наблюдения обоих таймеров против независимого эталона времени и профиль пределов S51, S83, ATF и окна чтения с SHA точного H03. Генератор сохраняет SHA входов и переносит заданные пределы без пересчёта. Положительный результат означает согласованность переданных данных.

В `lfj8_h03_application_binding.c` уже есть ссылка на `rbm_h03_target_clock_ready`. Сгенерированный поставщик вызывает штатную проверку регистра делителя `PRS1 = 9` и регистров `TML0CR = 0x01`, `TML1CR = 0x31`. Проверка выполняется под исключением прерываний до инициализации и перед открытием эпохи. В работе существующий общий путь проверяет текущий флаг допуска, настройки таймеров и возраст фазы. Отказ закрывает приложение и отзывает общую эпоху датчиков. Возврат прежнего значения регистра сам по себе не открывает приложение. У штатного пути остаётся единственный владелец часов и состояния датчиков.

Адресный сборщик принимает пару `--sensor-clock-reference` и `--sensor-calibration-profile` с `--with-bindings`. Он заново проверяет оба файла, генерирует C во временной папке, компилирует его в общий состав и записывает доказательства и SHA исходника в `layout.json`. Отсутствующая половина пары или рассогласование часов останавливают сборку до компиляции. Сами тестовые числа существуют только в проверках и локальных артефактах.

## Проверки

- До правки регрессия в `test_h03_sensor_config.py` обнаружила, что генератор не выдавал символ `rbm_h03_target_clock_ready`. После правки прошли все пять его проверок и 11 проверок измерений VSS.
- Модель `check_h03_application_binding.py` теперь связывает сгенерированный поставщик с настоящей application binding. Она прошла отказ при отсутствии владения RAM, отдельный отказ по `PRS1`, `TML0CR`, `TML1CR`, переход TML0 через ноль, потерю настройки TML1 при работающем приложении, очистку накопленного S51, обнаруживаемый на расписании сброс TML0, явный повторный запуск и истечение фазы. Отсутствие фронтов остаётся недоступной скоростью в foreground. Нативные прогоны обоих штатных фронтов S51/S83 и кандидатных hooks прошли отдельно.
- На ПК прошёл 41 этап, включая 179 тестов Python с закреплённым S03 и сквозную модель.
- Контроллер и мост собраны для M32R. Прошли 22 штатные и восемь компонентных групп, включая арифметику VSS.
- В прямой адресной проверке отсутствующий второй вход и рассогласованные отсчёты завершились отказом без ELF. При синтетических согласованных входах оба определения разрешились. В расширенном составе с типизированными псевдонимами RAM и BasicCAN число неразрешённых символов уменьшилось с 10 до 8, статус остался `FAIL_BINDINGS`. Известный состав вырос с 101 460 до 101 492 байт Flash. Прироста RAM нет. Учтённая секция в 4 байта совпадает в обоих прогонах. Статический разбор изолированной цепочки показывает 4 байта стека на входе нового callback и ещё 12 в существующей функции проверки регистров. Это не замер полного стека, времени исполнения или вложенных IRQ.

```powershell
python -B targets/lfj8/check_h03_sensor_config.py --base $h03 --clock-reference $clockReference --calibration-profile $sensorProfile --out $sensorReport --emit-config > $sensorSource
python -B targets/lfj8/check_h03_application_binding.py --gcc $gcc --controller $controller --out $bindingReport
python -B targets/lfj8/check_h03_sensor_native.py --base $h03 --gcc $gcc --out $nativeSensors
python -B tools/check_h03_image_layout.py --base $h03 --gcc $gcc --controller $controller --bridge $bridge --profile padding-candidate --with-bindings --with-dtc-rx --storage-report $storageReport --application-profile $applicationProfile --sensor-clock-reference $clockReference --sensor-calibration-profile $sensorProfile --out $layout
```

Расширенный замер использует `final-integration-20261121/check-combined-profile.py` и его типизированные псевдонимы RAM. В повторе с датчиками в вызов `layout.build(options)` для `protected_padding` переданы проверочные JSON через `options.sensor_clock_reference` и `options.sensor_calibration_profile`. Для базового прогона эти параметры опущены.

SHA-256 локальных отчётов для сверки.

| Отчёт | SHA-256 |
| --- | --- |
| `sensor-emit-before.log` | `734b16f06f54ebc8dce9701bf7ad4f2e9aa1a1e479468c6694e2e1c394741f7a` |
| `sensor-config.json` | `f32d0c4a323572cad6b27c67ee8756aa6b53a40bd8ec0b1ce8369ccb046d3d3e` |
| `application-binding.json` | `151db41c1d28a58b2b2ee604ca960a8d7bbcee528e0a074ddc969afb66061f08` |
| `sensor-native/sensor-native.json` | `3aaf5d6659d410ea61f8d3a59fda317831a86cb144897b9c21d61bab07b1a80c` |
| `baseline-link.log` | `139f8b84e15a670981e7c957718f9c390723a4c4635c4e0e3cecf2e934f98c82` |
| `combined-no-sensors/protected_padding.json` | `b4b186e067906355f9c2c9ec8432465b39865dd7d5a0412e42bb340d94792e78` |
| `combined-clock/protected_padding.json` | `69065643262d77230daeed53da3c5aca5cece4303a64d3edfd51d0ce8d520751` |
| `native/summary.json` | `5315afd317aa2c26fbdf1cbfa23fe10d1fbeb2fe2f6e65eed8e232ad3d944917` |
| `components/summary.json` | `3b8d4c706837f6ded5c163991495919554c4526df947a3a5d6bf468dc586cb37` |
| `../pc-checks/PC-CHECKS.json` | `d51e3a1b473c86ffb6dc121e54191edffab7a72d3fa8f387aa0ebe661091576c` |

На текущей ветке и на чистой `main` стандартный `check_h03_link.py` одинаково останавливается при линковке `test_runtime.c`. Компактная тестовая компоновка не удерживает ссылку на добавленную в `da6b13b` функцию `rbm_u340e_runtime_prepare_s01_cold`. В диагностическом повторе с добавлением этой функции в H03_ROOTS только на время процесса прошли строгая компоновка и все 18 компонентных прогонов. SHA-256 отчёта — 173aabe7460d780e3658990f7de2859edd200c8e88ad240916486a50fab578ef.

## Остаток

Для целевой сборки нужны фактические парные отсчёты TML0/TML1 на блоке, допустимое отклонение частоты и измеренные рабочие пределы S51/S83, ATF и окна чтения. Для калибровки скорости остаются фронты S83 на оборот, геометрия автомобиля и независимое подтверждение остановки, а затем сверка скорости с эталоном на CAN. При известном перенастраивании или сбросе таймера владелец должен закрыть текущую эпоху до повторной квалификации.

В общей компоновке остаются `rbm_h03_target_engine`, `rbm_h03_target_initialize`, `rbm_h03_target_ram_owned`, `rbm_h03_target_service_phase`, `rbm_h03_target_startup_gear`, `rbm_h03_target_startup_gp`, `rbm_h03_target_take_toyota` и `rbm_h03_target_takeover_ops`. В этом прогоне использовано моделирование. Аппаратных измерений и выпуска BIN не было.
