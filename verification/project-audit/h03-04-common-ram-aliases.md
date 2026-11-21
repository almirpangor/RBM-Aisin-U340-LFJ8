# H03-04 — абсолютные алиасы RAM, SPI и PSW

База `main` — `06ab447e19de0fa7d864e2ae674dff4a29678b10`. Продолжение включает переданный на review коммит сервисных переходов `1cf7aa5eb5c8ead6866eb1be12a7a3fad8f6fbbe`. Исходный H03 `LFJ8-T-D.bin` имеет SHA-256 `844a11b809cda1f2ccaf90cb6a75666009487ccedd2e8190b7eb46137b855544`.

## Подключение

Режим `--with-ram-owner` в общем компоновщике включает `lfj8_h03_target_memory.c` и `lfj8_h03_ram_owner.c`. Он использует `--with-service-guard`, защищённый DMA4 и проверенный типизированный инвентарь M32R. Общий линкер связывает дескриптор `rbm_h03_target_ram_owned` с восемью абсолютными символами. При подключении `lfj8_h03_application_binding.c` через профиль тот же линкер привязывает шесть объектов приложения к полям трёх областей инвентаря.

| Объект | Адрес или интервал |
| --- | --- |
| Control | `[0x806B40, 0x806FA8)` |
| Communication | `[0x808E40, 0x8090A0)` |
| Workspace | `[0x8090A0, 0x8094CC)` |
| SPI, верхняя граница | `0x809EFC` |
| PSW, исключающий конец слова курсора | `0x809FA0` |
| `rbm_h03_runtime_state` | `0x806B40` |
| `rbm_h03_cycle_state` | `0x806E80` |
| `rbm_h03_takeover_state` | `0x806EA0` |
| `rbm_h03_main_result` | `0x809074` |
| `rbm_h03_cycle_workspace` | `0x8090A0` |
| `rbm_h03_cycle_input` | `0x809360` |

Загрузки SPI сверены по словам H03 в `0x0009E0–0x0009E7` и `0x003DA4–0x003DAB`. Слова `0x003DAC–0x003DB7` сохраняют значение `0x809F9C` по адресу `0x809F9C`. Включение этого четырёхбайтного слова даёт верхнюю границу `0x809FA0`. Линкер отклоняет конфликтующие или повторно выделенные символы. Размер и адрес областей берутся из [проверяемого инвентаря RAM](../../targets/lfj8/check_h03_storage.py).

Проверка владельца RAM принимает четыре связанных хука и политику в одном резидентном окне `[0x006000, 0x008000)` либо вместе в прежнем верхнем диапазоне. Для обоих размещений она сверяет штатные переходы, загрузки адреса политики и вызовы охранных функций. Смешанное размещение отклоняется.

## Проверки и расход памяти

- Полный прогон ПК для предыдущей порции сервисных переходов завершился с нулевыми кодами всех 41 этапов, включая 196 тестов Python. SHA-256 `PC-CHECKS.json` — `9513e3f19d343bd5cacb441e9c6956cac0d3cb9125916063ef6975f82fd7f06d`.
- Для этой порции прошли 27 тестов размещения. Симулятор M32R проверил холодный вход и защиту записей для обоих вариантов размещения, отказ при смешивании, контроль SPI/PSW, DMA, штатный SBI и запуск Toyota. Независимая частичная линковка M32R подтвердила все 14 символов `SHN_ABS`, разрешила вызов `rbm_h03_target_ram_owned` из привязки приложения и сохранила пять обязательных неопределённых ссылок.
- На `early-irq.elf` из общей компоновки прошли 29 сценариев доступа, 28 сценариев закрытия сервиса, 20 проверок политики и повтор раннего reset и DMA4. SHA-256 этого ELF — `b7388f61b9de992da31e600f52215e59a7baaf3b06a072caba62d6ad419548f2`.
- Полная проба состава интеграции 39 дала `FAIL_BINDINGS`. Известные секции занимают **106 416 байт Flash**, включая 102 280 в верхних окнах при вместимости 102 356, 4096 резидентных и 40 байт фиксированных переходов. Относительно сервисной порции добавилось 56 байт Flash за проверку двух допустимых размещений. Абсолютные алиасы новых байтов не выделяют. Статическая RAM по-прежнему составляет 4 байта для IRQ-указателя BasicCAN по адресу `0x806FA8`.
- Без `--with-ram-owner` проба с теми же поставщиками показывает 28 неопределённых ссылок. С этим режимом остаётся 14. Запуск режима без `--with-service-guard` отклоняется.
- `project_status.py --check` на рабочей ветке отмечает изменённые файлы как ожидающие проверки. Общий реестр этой порцией не менялся.

```powershell
python -B -m unittest discover -s tests -p 'test_h03*placement.py'
python -B targets/lfj8/check_h03_ram_owner.py --base $h03 --gcc $gcc --controller $controller --bridge $bridge --storage-report $storage --out $ownerReport
python -B tools/check_h03_image_layout.py --base $h03 --gcc $gcc --controller $controller --bridge $bridge --storage-report $storage --profile padding-candidate --with-bindings --with-dtc-rx --with-dma4-guard --with-service-guard --with-ram-owner --out $layoutDir
python -B targets/lfj8/check_h03_service_guard.py --base $h03 --gcc $gcc --storage-report $storage --placed-elf "$layoutDir/early-irq.elf" --common-layout "$layoutDir/layout.json" --out $guardReport
python -B targets/lfj8/check_h03_boot_writers.py --base $h03 --gcc $gcc --placed-elf "$layoutDir/early-irq.elf" --layout-report "$layoutDir/layout.json"
```

Для измерения полного известного состава использован [сценарий интеграции 39](integration-39-20261121/check-composition.py) с `with_service_guard=True` и `with_ram_owner=True` в вызове `layout.build`. Его испытательный профиль используется для оценки состава и оставляет неподтверждённые поставщики неопределёнными.

## Остаток

Для снятия блокировки `target_ram_owned` нужны подтверждённые нижние границы `rbm_h03_ram_spi_first` и `rbm_h03_ram_psw_first`, резервы `rbm_h03_ram_spi_reserve` и `rbm_h03_ram_psw_reserve` с учётом вложенных IRQ/SBI и реализация `rbm_h03_boot_writers_owned` после проверки всех писателей. Для всей компоновки также открыты профиль и поставщики запуска, входов, тактирования, CAN и выходов. Результаты получены на ПК и в симуляторе M32R. Физический блок и выпуск BIN остаются за пределами этой порции.
