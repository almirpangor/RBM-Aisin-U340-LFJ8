# H03-03. Платформа с типизированной RAM в адресной модели

Ветка основана на `main` `f64eff7c24744cef0fe608415039c6d10c677ff1`. В неё включены H03-03 `10acac98126b` с общей компоновкой и CAN-03 `b0c2eda62974` с полем `control/toyota_release` и жизненным циклом сервиса. Рабочий компоновщик оставался в резерве DTC-02.

`check_h03_target_platform.py --base` теперь снимает свежий инвентарь на точном H03, запускает общий компоновщик с тестовым заголовком профиля и берёт адреса из его отчёта. Общая проверка получает только заголовок. Реализации тестовых поставщиков используются в отдельном ELF симулятора.

Оба callback H03-03 и ссылка `rbm_h03_toyota_release_state` разрешены в общем адресном плане. Для ELF симулятора проверяются точное совпадение адресов, размеров и флагов четырёх секций, абсолютный RAM-символ и его адрес в слинкованном дескрипторе `toyota_source`. По этим адресам прошли холодный и тёплый запуск, жизненный цикл CAN, foreground, переполнение TML0 и снятие допуска при отказе.

| Объект | Адрес в данном составе | Байт |
| --- | --- | --- |
| `control/toyota_release` | `0x806EFC`, конец `0x806F0C` исключён | 16 |
| `.text.rbm_h03_target_initialize` | `0x027900` | 204 |
| `.text.rbm_h03_target_take_toyota` | `0x02BED8` | 84 |
| `.text.startup_allowed_locked` | `0x02CE78` | 64 |
| `.rodata.toyota_source` | `0x02DCE8` | 32 |

Поле имеет выравнивание 4. Общий инвентарь этого состава занимает 2792 байта, из них 1116 байт в блоке управления. Модуль платформы занимает 384 байта Flash и 0 байт собственной writable RAM. Адрес `0x806EFC` получен из действующего поля после `control/application`. Предыдущая проба по `0x806F8C` моделировала добавление поля в конец блока.

Сборки controller и 9E1C, штатный и размещённый тесты платформы, связанная проверка CAN monitor/service по тому же RAM-адресу, 62 сценария boot с 96 совпадениями IRQ-контекста и 44 теста семейства `test_h03*.py` прошли.

```powershell
python -B controller/build_target.py m32r --cc $gcc --out local/typed/controller
python -B targets/lfj8/build.py --output local/typed/bridge --m32r-cc $gcc --base-9e1c $h03
python -B targets/lfj8/check_h03_target_platform.py --base $h03 --gcc $gcc --controller local/typed/controller/rbm_u340e_m32r_be.o --bridge local/typed/bridge/lfj8_9e1c_m32r.o --out local/typed/platform-placed.json
python -B targets/lfj8/check_h03_storage.py --base $h03 --gcc $gcc --out local/typed/storage.json
python -B targets/lfj8/check_h03_can_monitor_revoke.py --base $h03 --gcc $gcc --storage-report local/typed/storage.json --out local/typed/can-service.json
python -B targets/lfj8/check_h03_phase_boot.py --base $h03 --gcc $gcc --controller local/typed/controller/rbm_u340e_m32r_be.o --out local/typed/phase-boot.json
python -B -m unittest discover -s tests -p "test_h03*.py"
```

При известном объёме 98 544 байта Flash общий линк сохраняет `FAIL_BINDINGS`. В незамкнутую часть входят включение сервиса CAN в общий список, оставшиеся адреса и поставщики приложения, а также квалифицированные периоды и входы профиля. Проверочный ELF содержит только модельное выполнение. Окончательное владение RAM и стеком, аппаратная приёмка и выпуск BIN открыты.
