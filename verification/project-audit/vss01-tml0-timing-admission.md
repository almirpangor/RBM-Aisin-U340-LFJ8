# VSS-01 — проверка времени и окна S51 в кадре Chery 0x1AE

База `main` — `20bf48d15b27608a39876bc96aacae68c705863a`. Включён предыдущий результат VSS-01 `b48c663b97c1c4d125a4e86396a09f9be979d803`. SHA-256 входного образа H03 LFJ8-18-9E1C — `844a11b809cda1f2ccaf90cb6a75666009487ccedd2e8190b7eb46137b855544`.

## Подключение

- `targets/lfj8/lfj8_chery_tx.c` проверяет предел возраста в существующей ветке передачи `0x1AE`. При тайм-ауте 0 или от `0x80000000` тиков, отсутствии калибровки либо обоих источников передатчик выдаёт `0xFFFF`. При недопустимом тайм-ауте он не читает TML0 через прежний путь и не обнуляет накопленный интервал S51.
- Когда CAN13 передаёт согласованный снимок foreground, передатчик проверяет его возраст на шкале TML0 в 1 МГц и использует снимок как единственный источник. Некорректный снимок не запускает чтение прежнего трекера. Поле окна остаётся 16-битным до проверки. Значения `0x0101`, `0x0102` и `0x0104` больше не превращаются в допустимые окна из одного, двух и четырёх импульсов при упаковке скорости. Существующая функция пересчёта сохраняет точный коэффициент `99/1250000` без приближения `4,545`.
- `targets/lfj8/lfj8_chery_tx.h` фиксирует диапазон и поведение прямого вызова передатчика. Брокер CAN13 по-прежнему квалифицирует поставщиков статуса перед вызовом. Периоды кадров, арбитраж CAN13 и упаковка `0x300` прежние.
- `targets/lfj8/host_check.c` проверяет выходные байты и доступ к TML0. Допустимый максимум тайм-аута и переход TML0 через ноль дают `17 70` на прежнем тестовом векторе. Корректный foreground даёт тот же результат. Отсутствие обоих источников при заявленной остановке даёт `FF FF`. Температура ATF в `0x300` передаётся и при отсутствующих входах скорости.

## Проверки

- До исправления новый тест останавливался на проверке `FF FF` для возраста и тайм-аута ровно в половину оборота TML0. После исправления этот тест и остальные проверки моста прошли на ПК и в модели M32R.
- ПК — 41 шаг, в том числе 129 тестов Python с закреплённым S03. Zig 0.13.0, все коды выхода нулевые.
- M32R — собраны мост и контроллер. Прогон владельца CAN подтвердил передачу `0x1AE` из foreground без прежнего трекера. Строгая компоновка и модель прошли 18 компонентов. Дополнительный прогон `--suite components` прошёл восемь групп, включая арифметику VSS.
- Bosch/TCM — свежий двусторонний прогон на одном закреплённом образе Bosch дал `PASS_OFFLINE_ONLY`. Bosch принял скорость `0x1AE` из сквозной модели, TCM декодировал 1200 об/мин и 87 °C. В строгой компоновке M32R повторены кадры Bosch `0x0FA` и `0x278` из этого журнала.
- Размещение H03 — `prefix-candidate --cpu-test` вернул `PASS_ADDRESS_MODEL_ONLY`. Объём кода и данных 83 170 байт, на 28 больше предыдущей модели VSS-01. В основном окне осталось 552 байта, хвостовое окно заполнено. Новых статических секций RAM нет.
- `project_status.py --check` прошёл на обновлённой базе. Общий реестр результатов ведёт интегратор.

Основные команды для повтора с закреплёнными входами и отдельным каталогом результатов:

```powershell
python -B tools/build_pc_checks.py --cc $zig --out local/pc-checks
python -B targets/lfj8/build.py --zig $zig --m32r-cc $m32rGcc --base-9e1c $h03 --output local/audit/bridge
python -B targets/lfj8/check_h03_can_owner.py --cc $m32rGcc --controller $controller
python -B tools/check_integrated_h03.py --suite components --base $h03 --gcc $m32rGcc --controller $controller --out local/audit/components
python -B targets/lfj8/check_h03_link.py --base $h03 --gcc $m32rGcc --controller $controller --bridge $bridge --bosch-trace $roundtrip --out local/audit/h03-link-ordinary.json
python -B tools/check_h03_image_layout.py --profile prefix-candidate --cpu-test --base $h03 --gcc $m32rGcc --controller $controller --bridge $bridge --out local/audit/placed
```

Для двустороннего журнала использованы точные S04, инструментальное дерево E4M3 и модель C167:

```powershell
python -B targets/bosch/build.py --engine $engine --s04 $s04 --outdir local/audit/bosch-ordinary --with-model-fields --with-ordinary-model-field --compact
$bosch = 'local/audit/bosch-ordinary/E4M3_CHERY_ORDINARY_MODEL_NO_CRUISE_COMPACT_OFFLINE_ONLY.bin'
$txReport = 'local/audit/bosch-ordinary-verification.json'
python -B targets/bosch/verify_ordinary_model_field.py --engine $engine --s04 $s04 --model $c167 --image $bosch --compact > $txReport
python -B -m model.run_integrated --cc $zig --bosch-engine $engine --bosch-s04 $s04 --bosch-image $bosch --bosch-tx-image $bosch --bosch-tx-report $txReport > $roundtrip
```

SHA-256 локальных отчётов для сверки:

| Отчёт | SHA-256 |
| --- | --- |
| `before.log` | `fb55104604a74ca6301abedab1c3d0f070dccb9d8f2b45a32a897f0fe3fb9f64` |
| `bridge/build-manifest.json` | `e828c006d960dda0e6f4a050726b9b954d305a8d0f2ccb75b53766af68c7fca5` |
| `components/summary.json` | `d2c72a1941c7c6ff24ba3b498abf9361e72027dcf5b92d028b4c41f594a4e39a` |
| `placed/summary.json` | `6aacc752d121fd5ea5b5cc4c2017cc414863e45e182a913d0cf1e434956d068c` |
| `bosch-ordinary-verification.json` | `8610c7598b243dc1190d0dac650140f184b58aa782d42020ef5822e83b632013` |
| `bosch-roundtrip-ordinary.json` | `e9df9cbcae6eb741b9863688f7bbacd16f19064c063b76549f8b56939ca03b4b` |
| `h03-link-ordinary.json` | `1f7d53eeee3fc0cf0b856e5b2d301f83849ce3f447513246d0f32a8636a0fee0` |
| `local/pc-checks/PC-CHECKS.json` | `c2d8759fc7a17d3406923efb150232cfa61aff164bd9efa1cc436bc58f7cccfd` |

## Остаток по VSS-01

Целевая привязка `rbm_h03_application_binding.service_phase` должна передавать снимок текущей эпохи TML0, независимое подтверждение остановки и параметры конкретной машины. Для `rbm_h03_sensor_config` остаются физические параметры S51 и геометрия автомобиля. Скорость и индикацию остановки ещё нужно сверить на реальной CAN-шине. Модель и компоновка использовали тестовые векторы. Оборудование не подключалось, блоки не прошивались.
