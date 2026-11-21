# VSS-02 — контроль согласованности TML0 и TML1 в штатном H03

База для сравнения — `06ab447e19de0fa7d864e2ae674dff4a29678b10`. Предыдущая порция проверки входного профиля — `b703627c2b40b90867d0989a5dd3bfc58a62eeea`, уже в базе. SHA-256 исходного H03 — `844a11b809cda1f2ccaf90cb6a75666009487ccedd2e8190b7eb46137b855544`.

## Подключение

`lfj8_h03_capture_pair` использует уже выполняемые под исключением прерываний чтения TML0, TML1, TML0. По конечному чтению TML0 вычисляется нижняя граница разности TML1−TML0, по ширине окна — верхняя. В ширине остаётся прежний предел `max_read_span_ticks` из профиля. Дополнительных обращений к MMIO и нового порога времени нет. Перевод даты S83 и её погрешность сохраняют прежний смысл. Границы смещения вычисляются и при отсутствии фронтов S51/S83.

При первом согласованном чтении после открытия эпохи `lfj8_h03_sensor_feed_snapshot` запоминает интервал смещения. Затем пересекает сохранённый интервал с текущим по модулю 2³². Если пересечение пусто, снимок очищается, история S51/S83/ATF отбрасывается, а `rbm_h03_sensor_foreground` отзывает общую квалификацию и меняет эпоху под той же блокировкой. Штатный `rbm_h03_application_foreground_callback` использует существующий отказ до вызовов Toyota и CAN-сервиса. Начать новую эпоху можно через штатный повторный запуск. В фазовом пути TML0 сохраняются свои проверки хода и давности.

## Проверки

- На исходной `main` расширенная проверка нативной привязки воспроизводит дефект. При неподвижном TML1 и штатных PRS1/TML0CR/TML1CR счётчики вызовов Toyota/CAN превышают ожидаемые. С новым кодом прошли повтор запуска и отзыв в штатном foreground после OEM-производителя входов, включая очистку ATF/S51 и отмену ожидающего выхода.
- Прямой тест снимка прошёл на ПК и в M32R. Он покрывает смещение через ноль, допустимые перемещения внутри окна, пошаговую остановку TML1 на интервалах меньше окна, скачок счётчика, очистку снимка и повторную эпоху. Нативные S51/S83 на штатных адресах прошли с закрытием общей квалификации и повторной привязкой.
- Контроллер и мост собраны для M32R. Проверки startup/foreground с модельным профилем прошли в обычном и адресном запусках. Профили испытательных запусков используются только в проверке.
- На ПК прошёл 41 этап, включая 194 теста Python. Сквозная модель с Bosch завершилась статусом `PASS_OFFLINE_ONLY`.
- Прошли 22 нативные и 8 компонентных групп M32R, 68 сценариев startup/foreground и шесть групп для размещённого ядра. Ядро занимает 85 504 байта и имеет статус `PASS_ADDRESS_MODEL_ONLY`.
- `tools/project_status.py --check` на исходном `06ab447` прошёл. В рабочей ветке он помечает изменённые файлы для повторной проверки. Этот отчёт фиксирует повторённые проверки для интегратора общего аудита.

## Память и компоновка

| Показатель | `06ab447` | После изменения | Разница |
| --- | ---: | ---: | ---: |
| Flash, та же композиция известных C-поставщиков | 106 016 | 106 184 | +168 |
| Flash, верхние окна | 102 428 | 102 596 | +168 |
| Типизированная RAM, control | 1 128 | 1 132 | +4 |
| Типизированная RAM, communication | 608 | 608 | 0 |
| Типизированная RAM, workspace | 1 068 | 1 076 | +8 |
| Кадр `rbm_h03_application_foreground_callback` | 180 | 184 | +4 |
| Кадр `rbm_h03_sensor_foreground` | 56 | 60 | +4 |
| Кадр `lfj8_h03_sensor_feed_snapshot` | 52 | 52 | 0 |
| Кадр `lfj8_h03_capture_pair` | 40 | 40 | 0 |

В RAM учтены новый интервал в состоянии датчиков и расширение двух структур в workspace. Стек подсчитан по прологам объектов M32R GCC 4.8.0, `-Os -mmodel=medium -msdata=none`. Кадры четырёх показанных функций дают +8 байт по цепочке foreground → снимок → чтение. Измерение полного стека с вложенными IRQ остаётся у H03-04.

Для верхних окон при 102 356 доступных байтах уже известных секций требуется 102 596 байт. Дефицит вырос с 72 до **240 байт**, до добавления ещё отсутствующих модулей. Общая проверка сохранила `FAIL_BINDINGS` с прежним множеством из 32 неопределённых ссылок. В частности, выпускная композиция ещё требует профиль датчиков для `rbm_h03_sensor_config` и `rbm_h03_target_clock_ready`, а работа H03-04 — привязки RAM и окончательный план размещения.

## Повтор

```powershell
python -B targets/lfj8/check_h03_sensor_native.py --base $h03 --gcc $gcc --out $sensorNative
python -B targets/lfj8/check_h03_application_binding.py --gcc $gcc --controller $controller --out $applicationBinding
python -B targets/lfj8/check_h03_target_platform.py --base $h03 --gcc $gcc --controller $controller --bridge $bridge --out $targetPlatform
python -B tools/check_integrated_h03.py --suite native --base $h03 --gcc $gcc --controller $controller --out $native
python -B tools/check_integrated_h03.py --suite components --base $h03 --gcc $gcc --controller $controller --out $components
python -B tools/check_h03_image_layout.py --base $h03 --gcc $gcc --controller $controller --bridge $bridge --profile padding-candidate --cpu-test --out $placed
python -B verification/project-audit/integration-39-20261121/check-composition.py --base $h03 --gcc $gcc --controller $controller --bridge $bridge --storage-report $storage --out $composition
```

SHA-256 отчётов в локальном `local/checks` собственного worktree.

| Отчёт | SHA-256 |
| --- | --- |
| `stack/baseline-freeze.log` | `f6e5401be6898b09f5c3b0a01d1cb72683274d6bf0dc476be205bb4ca00104f9` |
| `stack/prologues.txt` | `2b212f02761841c174573bb5156df647f2ef09336ab424a5939664fe413967d1` |
| `sensor-unit/m32r.log`, `sensor-unit/host.log` | `fc5f9edc58f0c1f4012118c77036fbaeaf7de45617590b9d15b492406af2b572` |
| `phase-boot.json` | `d1d271d1719cbf8732592a94acc0d96e69c5071eec99fd48b66129cc2b093c0d` |
| `final-target-platform.json` | `7693d7bb4de259825f5700c973be7c0490909611bde54bc9a0f2ad333f0dd9d8` |
| `final-native/summary.json` | `03ccf9a9f3bbc045b45cac42170ee3a01104b2e48c9a4289c500fadd710a2cba` |
| `components/summary.json` | `83fcbb68b0df1bcb425a9b97762f6928e7dcbcf95b9d458b9569d8f59328fc01` |
| `final-placed/layout.json` | `d6efd2349c9fc1ceddaad8e49478b08097aa4b79010ac20043ee9d5222d5b0ad` |
| `final-storage.json` | `61a5007937919b9070f897c1bee3ace3aa6854aca490e9a396801979b67e3ad8` |
| `final-composition/composition.json` | `e4c8156c0d6e11dbf58c9620230cffc2e27f2c5d0f4e85789611cc364ead3402` |
| `pc/PC-CHECKS.json` | `ab9b13192fbdafc9c94e4152afbb2c594e8bc609d67b978352de6a530dc8bec1` |

## Остаток VSS-02

На блоке нужны парные отсчёты с эталоном времени и проверка стабильности смещения при штатной инициализации, работе и перезапуске таймеров. Требуются измеренные пределы S51/S83, возраста ATF и окна чтения. Для скорости по CAN остаются кинематика, независимое подтверждение остановки и сверка с эталоном. Контроль относительного смещения начинает действовать после первого согласованного снимка. Общий синхронный сброс двух счётчиков сам по себе сохраняет относительное смещение, поэтому остаются необходимы штатный контроль TML0 и отзыв эпохи при известных перенастройках. Аппаратная проверка и выпуск BIN в эту порцию не входили.
