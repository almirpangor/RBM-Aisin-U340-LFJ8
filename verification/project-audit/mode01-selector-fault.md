# MODE-01 — отзыв диапазона при явном отказе АЦП

База ветки — `main ae393e8`. В проверке по штатному H03
LFJ8-18-9E1C использован SHA-256
`844a11b809cda1f2ccaf90cb6a75666009487ccedd2e8190b7eb46137b855544`.

На исходном коде сквозной тест подтвердил диапазон L, затем
передал `INVALID` с меткой последнего принятого АЦП. Обработка
пропустила сообщение по порядку меток и сохранила диапазон L.
Проверка, требующая отзыва, завершилась ошибкой.

`lfj8_range_control_sample_selector` теперь сбрасывает
подтверждённый диапазон и накопленные отсчёты при `INVALID`
или `OVERRUN` до проверки пригодности метки. Некорректное время
отказа не продвигает последнюю принятую метку. Повтор последней
принятой метки со статусом `VALUE` не учитывается.
Для повторного подтверждения требуются четыре свежих согласованных
отсчёта, как при обычном распознавании положения.

Изменены `targets/lfj8/lfj8_range_control.c` и комментарий к
интерфейсу в `lfj8_range_control.h`. Тест добавлен в
`tests/u340_integration_host.c`, который исполняется как на ПК,
так и в интеграционной проверке на M32R. Текущая обвязка
`lfj8_h03_input_propose` отказывает при неизвестном диапазоне.

## Проверки

- На ПК сквозной сценарий прошёл со статусом `PASS_OFFLINE_ONLY`.
  Проверены 10 комбинаций двух отказов и пяти вариантов меток
  около перехода через ноль. В каждой сразу отзываются логические
  предложения передачи и реле. Проверены неизменность метки при
  отказе времени и восстановление на четвёртом отсчёте.
- `check_h03_input_binding.py` в M32R прошёл проверку шести
  диапазонов, обработки кнопок, независимых допусков, потери и
  повторного подтверждения АЦП.
- `check_h03_link.py` исполнил сквозной тест с десятью новыми
  сценариями в M32R, 18 компонентных групп и сравнение с
  сохранённой трассой Bosch. INTEGRATION21 components прошёл
  восемь дополнительных групп, включая захват кнопок и SLU.
- Базовый `prefix-candidate --cpu-test` прошёл шесть сценариев
  исполнения по адресам размещения. Объём Flash 83 062 байта,
  прирост 20 байт. Новых статических объектов в RAM нет.
- Расширенный состав с нативным CAN и свежим ABI-отчётом RAM
  удержал 94 790 байт. Известные секции размещаются в
  кандидатных окнах. Ожидаемый `FAIL_BINDINGS` перечисляет
  `rbm_h03_application_binding` и `rbm_h03_sensor_config`.

## Воспроизведение

```powershell
python -B -m model.run_integrated --cc $zig
python -B targets/lfj8/check_h03_input_binding.py --gcc $gcc --controller $controller --out local/mode01-selector-fault/input-binding.json
python -B targets/lfj8/check_h03_link.py --base $h03 --gcc $gcc --controller $controller --bridge $bridge --bosch-trace verification/e4m3-can-9e1c/ordinary-model/round-trip.json --out local/mode01-selector-fault/link.json
python -B tools/check_integrated_h03.py --suite components --base $h03 --gcc $gcc --controller $controller --out local/mode01-selector-fault/components
python -B tools/check_h03_image_layout.py --base $h03 --gcc $gcc --controller $controller --bridge $bridge --profile prefix-candidate --cpu-test --out local/mode01-selector-fault/prefix
```

Проверка относится к программному отзыву диапазона. Для завершения
MODE-01 остаются целевая карта входов, выпуск штатного foreground и
проверка ручной заявки на физической гидравлике.

`project_status.py --check` на ветке перечисляет изменённые
файлы исходников и теста. Общий снимок обновляет интегратор.
