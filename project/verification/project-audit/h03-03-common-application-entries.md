# H03-03 — переходы запуска и foreground в общей компоновке H03

Проверено на `main 06ab447e19de0fa7d864e2ae674dff4a29678b10`. Ветка включает опубликованные порции H03-03 `579b20f72aecf3880f10f05ebeefd6c7c8951135` и H03-04 `396a1729a4194ea3939551d9193a591ac79356ff`. Исходник H03 идентифицирован по SHA-256 `844a11b809cda1f2ccaf90cb6a75666009487ccedd2e8190b7eb46137b855544`.

## Подключение

Общий компоновщик принимает `--with-application-entries` вместе с явным `--application-profile`. Он сверяет исходные слова, собирает три существующих ASM-файла с обёртками, удерживает четыре перехода при сборке с `--gc-sections`, занимает их штатные адреса до упаковки остального кода и разрешает штатные продолжения как абсолютные символы. При полном линке обязательна сверка реальных слов переходов и принадлежности целей исполняемой Flash.

Если известные секции поместились, но часть поставщиков ещё отсутствует, компоновщик отдельно связывает четыре обёртки ровно по адресам общей карты. Их ссылки ведут к действительным размещённым секциям C из `lfj8_h03_application.c`. В отчёте этот результат имеет статус `LINKED_WRAPPERS_AT_COMMON_ADDRESSES`. Он подтверждает переходы и адреса. Исполнение C проверяется отдельным сценарием M32R.

| Участок | Вход в H03 | Цель в общей пробе | Связанное слово |
| --- | --- | --- | --- |
| Холодный вход | `0x008100` | `0x02C95C` | `ff009217` |
| Startup | `0x00814C` | `0x02CB68` | `fe009287` |
| Foreground | `0x00816C` | `0x02CB00` | `fe009265` |
| Публикация фазы | `0x040424` | `0x02C3B8` | `feffafe5` |

## Проверки

- Полный прогон ПК завершился успешно. Все 41 этапов вернули нулевой код, включая 210 тестов Python. SHA-256 `PC-CHECKS.json` — `431780dbfe5ea60212d95dbee4eb76f6825503dfc63ede65921b4b2a3f549b5c`.

- 36 тестов размещения и 13 проверок ELF/карты прошли. Запуск режима без явного профиля отклонён до сборки. В прежнем режиме без флага состав, алиасы и ранний ELF сохраняются.
- `check_h03_phase_boot.py` прошёл 68 сценариев на M32R. Проверены холодный вход, startup, foreground, публикация фазы, продолжения OEM и сохранение регистров в штатных и отказных ветвях. SHA-256 отчёта — `46a1f0ea3ef36305809e6dfcf813d17ba1d2de424c39402116710e87b7c4d1b3`.
- Общая проба с профилем симулятора, RAM owner, защищённым BasicCAN RX, DMA4, TX13 и сервисными переходами сверила четыре связанных слова. SHA-256 отдельно связанного графа обёрток — `269f1859c390050a6ed1c84887a77b4cf8c59074893ee605a91066c3118fd281`. На её раннем ELF повторно прошли холодный и тёплый reset, DMA4, 29 сценариев доступа и 28 сценариев закрытия сервиса.
- `project_status.py --check` отмечает изменения рабочей ветки как ожидающие приёмки. Общий реестр ведёт интегратор.

## Расход и остаток

Включение добавляет 432 байта обёрток в верхней Flash и 16 байт замен по фиксированным адресам. Статическая RAM остаётся 4 байта для указателя BasicCAN. Изолированная проба составила 106 244 байта Flash против 105 796 без флага. Полная проба состава интеграции 39 составила 106 864 байта; верхние окна требуют 102 712 при доступных 102 356, дефицит 356 байт до выравнивания и добавления оставшихся поставщиков. Оба состава имеют `FAIL_BINDINGS`, остаются 14 ссылок, в том числе программа владения RAM при загрузке, нижние границы и резервы стеков, поставщики входов, профиля CAN, тактирования, запуска Toyota и выдачи.

Для завершения H03-03 остаются выпускной профиль входов и startup GP/gear, квалификация RAM/стека и окончательное размещение ожидания, выдачи и монитора. Проверки выполнены на ПК и симуляторе M32R. Аппаратного прогона и выпуска BIN не было.

```powershell
python -B -m unittest discover -s tests -p 'test_h03*placement.py'
python -B -m unittest discover -s tests -p 'test_h03_layout.py'
python -B targets/lfj8/check_h03_phase_boot.py --base $h03 --gcc $gcc --controller $controller --out $phaseReport
python -B tools/check_h03_image_layout.py --base $h03 --gcc $gcc --controller $controller --bridge $bridge --storage-report $storage --profile padding-candidate --with-bindings --with-dtc-rx --with-dma4-guard --with-service-guard --with-ram-owner --with-can-service --application-profile $simulatorHeader --with-application-entries --out $layoutDir
python -B targets/lfj8/check_h03_service_guard.py --base $h03 --gcc $gcc --storage-report $storage --placed-elf "$layoutDir/early-irq.elf" --common-layout "$layoutDir/layout.json" --out $guardReport
python -B targets/lfj8/check_h03_boot_writers.py --base $h03 --gcc $gcc --placed-elf "$layoutDir/early-irq.elf" --layout-report "$layoutDir/layout.json"
```

Заголовок `$simulatorHeader` берётся из `MANUAL_PROFILE` в [проверке целевой платформы](../../targets/lfj8/check_h03_target_platform.py). Для замера полного известного состава использован [сценарий интеграции 39](integration-39-20261121/check-composition.py) с `with_service_guard=True`, `with_ram_owner=True` и `with_application_entries=True` в вызове `layout.build`.
