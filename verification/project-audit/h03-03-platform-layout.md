# H03-03. Размещение платформы выпуска Toyota

Исходная база `f64eff7c24744cef0fe608415039c6d10c677ff1`. В ветку включены сданный платформенный модуль H03-03 `1c0942de670d`, профиль VSS-02 `007f28ea1e3f` и typed storage CAN-03 `cf5f2879f589`. Проверен точный H03 с SHA-256 `844a11b809cda1f2ccaf90cb6a75666009487ccedd2e8190b7eb46137b855544`.

Общая компоновка с `--with-bindings --application-profile` собирает `lfj8_h03_application_binding.c` и `lfj8_h03_target_platform.c` с одним явно переданным профилем. Она требует свежий `--storage-report`. Если в инвентаре присутствует `control/toyota_release`, компоновщик связывает `rbm_h03_toyota_release_state` с этим полем. Проверяются 16 байт, выравнивание 4, границы блока и отсутствие пересечений. Для итогового ELF предусмотрена сверка абсолютного адреса символа. При отсутствии поля ссылка остаётся неопределённой, и общий линк останавливается.

## Проверка на M32R

GCC 4.8.0, medium, big-endian. В общей модели на точном H03 удерживаются все четыре секции платформы.

| Секция | Адрес в проверенном плане | Байт |
| --- | --- | --- |
| `.text.rbm_h03_target_initialize` | `0x028118` | 176 |
| `.text.rbm_h03_target_take_toyota` | `0x02BBA0` | 84 |
| `.text.startup_allowed_locked` | `0x02CB10` | 64 |
| `.rodata.toyota_source` | `0x02DA2C` | 32 |

План с тестовым профилем удержал 97 784 байта известных секций Flash и 4 байта отдельного указателя DTC IRQ. Обе функции платформы определены. Общая композиция вернула `FAIL_BINDINGS`, среди открытых ссылок остались `rbm_h03_toyota_release_state` и поставщики профиля. В этом прогоне ELF общей композиции не создан.

Отдельный проверочный ELF связал эти четыре секции по адресам таблицы через `objcopy --rename-section` и `ld --section-start`. VMA, размеры и флаги сверены после линка. На этих адресах прошли штатный запуск и foreground, переполнение TML0, отказ входов и watchdog без фазы. ELF использовал модельное RAM-состояние из существующего теста. Период и входы в тесте остаются модельными.

Отдельная C-проба ABI M32R добавила `Lfj8H03ToyotaRelease` после существующего `Lfj8H03ControlStorage` в испытательной структуре. Она измерила смещение 1100, размер 16 и выравнивание 4. Размер контрольного блока в этой пробе вырос с 1100 до 1116 байт. Сценарии повторно прошли с тестовым RAM-символом в NOLOAD по `0x806F8C–0x806F9C` (конец исключён), затем с абсолютным символом `--defsym` по тому же адресу. Этот диапазон проверен в модели для данного состава и пока отсутствует в общем инвентаре.

Сборки controller и 9E1C прошли. Размещённое ядро прошло шесть групп CPU. Все 22 группы `check_integrated_h03.py --suite native` прошли, включая 62 сценария запуска и 96 совпадений контекста IRQ. Также прошли восемь групп `--suite components`, `check_h03_application_binding.py`, `check_h03_target_platform.py` и 44 теста Python семейства `test_h03*.py`.

```powershell
python -B controller/build_target.py m32r --cc $gcc --out local/placed/controller
python -B targets/lfj8/build.py --output local/placed/bridge --m32r-cc $gcc --base-9e1c $h03
python -B targets/lfj8/check_h03_storage.py --base $h03 --gcc $gcc --out local/placed/storage.json
python -B tools/check_h03_image_layout.py --base $h03 --gcc $gcc --controller $controller --bridge $bridge --profile padding-candidate --with-bindings --with-dtc-rx --storage-report local/placed/storage.json --application-profile $profile --out local/placed/profiled
python -B tools/check_h03_image_layout.py --base $h03 --gcc $gcc --controller $controller --bridge $bridge --profile padding-candidate --cpu-test --out local/placed/kernel
python -B tools/check_integrated_h03.py --suite native --base $h03 --gcc $gcc --controller $controller --out local/placed/native
python -B -m unittest discover -s tests -p "test_h03*.py"
```

Для воспроизведения профильной адресной проверки `$profile` можно взять из константы `PROFILE` в `check_h03_target_platform.py`. Общий компоновщик получает только заголовок. Реализации модельных поставщиков в эту сборку не входят.

## Остаток

Инвентарь RAM и тесты lifecycle удерживает CAN-03. В проверенной ревизии типизированная RAM занимает 2768 байт. Поля `control/toyota_release` пока нет. После освобождения файла нужно добавить в конец `LFJ8_H03_CONTROL_FIELDS` поле `toyota_release` типа `Lfj8H03ToyotaRelease`, переснять инвентарь и подтвердить ссылку по его адресу. Итоговый охват RAM и стек остаются задачей H03-04. Для полноценной линковки нужны подтверждённый профиль времени, владельцы входов и остальные поставщики общей композиции. Оборудование не подключалось.
