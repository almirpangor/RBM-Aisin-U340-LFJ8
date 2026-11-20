# MODE-01 — восстановление кнопок после отклонённого снимка

Основа — `b2ca79d006426a9839d64e8553cd81bf71953fe9`. Компонент принимает уже квалифицированные уровни кнопок и формирует логические заявки. [Контракт контроллера](../../controller/include/rbm_u340e.h)

Регрессия воспроизведена на библиотеке ПК и объекте M32R исходной версии. После корректного отпущенного состояния контроллер отклонял снимок с `selector=UINT8_MAX` и сохранял историю фронтов. В первом корректном снимке удерживаемая M выглядела как новое нажатие и меняла режим.

`rbm_u340e_step` теперь сбрасывает признак действительной истории кнопок при отсутствии или отклонении входного снимка. Текущие Auto/Tiptronic и Overdrive сохраняются. Первый корректный снимок кнопок задаёт исходную маску. Удерживаемая кнопка даёт новое событие после отпускания и повторного нажатия. [Реализация](../../controller/src/rbm_u340e.c)

## Проверки

Отдельный тест C проверяет M, `+`, `−` и OD для двух отказов: отклонённого снимка с недопустимым селектором и отсутствующего снимка. Во всех восьми сценариях первый восстановленный и повторный удерживаемый снимки проходят без фронта. После отпускания и повторного нажатия проверяется смена режима, заявка 3 или 1 либо событие Overdrive соответственно. Ранее существующий тест конфликта удерживаемых `+` и `−` повторён тем же исполняемым файлом. [Сценарии](../../controller/tests/test_shift_buttons.c)

- **ПК.** Zig 0.13.0, 35 шагов и 71 тест Python. Отдельный тест C прошёл с библиотекой из этого прогона. Проверка донора S03 использовала закреплённый образ через `RBM_S03`.
- **Сборка M32R.** GCC 4.8.0 собрал перемещаемый контроллер и мост, связанный с точным H03 `LFJ8-T-D.bin` с SHA-256 `844a11b809cda1f2ccaf90cb6a75666009487ccedd2e8190b7eb46137b855544`. Отдельный тест связан с тем же объектом контроллера.
- **Модель M32R.** Отдельный тест, сквозная компоновочная модель с сохранённой трассой Bosch и 17 компонентных прогонов прошли.

```powershell
python -B tools/build_pc_checks.py --cc $zig --out local/pc-checks
& $zig cc -std=c11 -O2 -Wall -Wextra -Werror -I controller/include -I controller/vendor/toyota/include controller/tests/test_shift_buttons.c local/pc-checks/controller/rbm_u340e.dll -o local/pc-checks/controller/shift-buttons.exe
& ./local/pc-checks/controller/shift-buttons.exe
python -B controller/build_target.py m32r --cc $m32rGcc --out local/audit/controller
python -B targets/lfj8/build.py --output local/audit/bridge --m32r-cc $m32rGcc --base-9e1c $h03
python -B targets/lfj8/check_h03_link.py --base $h03 --gcc $m32rGcc --bridge local/audit/bridge/lfj8_9e1c_m32r.o --controller local/audit/controller/rbm_u340e_m32r_be.o --out local/audit/h03-link.json --bosch-trace verification/e4m3-can-9e1c/ordinary-model/round-trip.json
```

Тест `test_shift_buttons.c` для ПК линкуется с библиотекой из `local/pc-checks/controller`. Для M32R используются объект `rbm_u340e_m32r_be.o`, штатная обвязка `crt0.o` и пустые `__init` и `__fini` по схеме `controller/build_target.py`. Исполняемый ELF запускается через `m32r-elf-run`.

| Локальный отчёт | SHA-256 |
| --- | --- |
| `local/pc-checks/PC-CHECKS.json` | `98c5dc5f781fda95ae249a97e081b30720a61b543331fae3ae11017e1f540378` |
| `local/audit/h03-link.json` | `247b605cfa79759c16b2aa1b108696ddf125a57744f617a659bb170e6144259f` |

## Передача интегратору

`project_status.py --check` перечисляет изменённый контроллер, заголовок и тест. При приёмке нужны записи этих трёх файлов в общем аудите. Физические кнопки и применение заявки в цикле Toyota остаются задачами MODE-02. Аппаратная проверка и выпуск рабочего BIN остаются открытыми.
