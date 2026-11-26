# TOY-06. Сброс и диагностика в SECONDARY SLU

База `760628bd249b19051339403f5663e78187d12a9a`. В допущенном SECONDARY порядок численных стадий теперь `05DA44 → 05DC5E → 05DCE8 → 055C5E → 05B6DE`.

- `05DA44` очищает `GP+1636.1` и обнуляет `GP−7028` в копии квалифицированного снимка перед расчётом. Следующая стадия давления при выборе смещения использует `GP−7030`. Значения после сброса публикуются в `Lfj8H03SluOutput` при успешном событии и доступны владельцу внешних полей.
- `05B6DE` использует выбранное слово `GP−7246`. При значении выше 2 560 сбрасывается `GP−4741`, а после 12 отсчётов `GP−4740` устанавливается `GP−4829.2`. Иначе сбрасывается `GP−4740`, а при четырёх отсчётах `GP−4741` бит очищается. FAST уже продвигает оба счётчика в существующем банке, как и `GP−4735`. Обновление GP сериализовано с остальной частью цикла, соседние биты сохраняются. [Отчёт R3 для 05DA44](https://github.com/almirpangor/Chery-TA2005-U340E/blob/7585de6945b4b6b3ef381c6062070a5f417cf588/research/results/C167_SECONDARY_SLU_RESET_PROBE.json), [отчёт R3 для 05B6DE](https://github.com/almirpangor/Chery-TA2005-U340E/blob/7585de6945b4b6b3ef381c6062070a5f417cf588/research/results/C167_SECONDARY_SLU_DIAGNOSTICS_PROBE.json).

## Проверки

- **Сравнение с R3.** Прошли 1 280 сочетаний для сброса и 38 400 для диагностики, включая все значения байта флагов, границы слова команды, пороги 4 и 12 и края счётчиков 0/255. Использован R3 из `data/sources.json`, SHA исходников проверены перед сборкой. Компилятор ПК предупреждает о знаковом сравнении в закреплённом исходнике R3. Значение перед сравнением лежит в диапазоне 0…65 535.
- **Общий цикл.** На ПК и M32R прошли пять публикаций за 37 событий и семь отказов. Проверены выбор смещения после сброса, обе диагностические границы, сохранение соседних битов, насыщение и продвижение счётчиков в FAST, пропуск, повтор и истечение срока снимка. Повторены прежние численные тесты SLU на ПК и в изолированном прогоне M32R.
- **Регрессия.** На ПК прошли 37 шагов и 113 тестов Python. На M32R прошли 18 компонентов строгой модели, 17 штатных групп и шесть дополнительных компонентных групп.
- **Адресная модель.** Профиль `prefix-candidate --cpu-test` выполнил шесть сценариев с кодом по рассчитанным адресам. Размер кода и констант 83 048 байт, на 236 больше опубликованной базы. Запас основного окна 680 байт, второе окно использовано полностью. [Опубликованная база](memory-layout/summary.json).

```powershell
python -B targets/lfj8/check_toyota_slu.py --cc $zig --m32r-cc $m32rGcc --r1 $r1 --r3 $r3
python -B tools/build_pc_checks.py --cc $zig --out local/toy06-stage-boundaries/pc
python -B tools/check_integrated_h03.py --suite components --base $h03 --gcc $m32rGcc --controller $controller --out local/toy06-stage-boundaries/components
python -B tools/check_integrated_h03.py --suite native --base $h03 --gcc $m32rGcc --controller $controller --out local/toy06-stage-boundaries/native
python -B targets/lfj8/check_h03_link.py --base $h03 --gcc $m32rGcc --controller $controller --bridge $bridge --bosch-trace verification/e4m3-can-9e1c/ordinary-model/round-trip.json --out local/toy06-stage-boundaries/strict.json
python -B tools/check_h03_image_layout.py --base $h03 --gcc $m32rGcc --controller $controller --bridge $bridge --profile prefix-candidate --cpu-test --out local/toy06-stage-boundaries/placed
```

Использованы Zig 0.13.0, GCC M32R 4.8.0 и проверенный S03 из `RBM_S03`. M32R запускался из копии проверенных исходников с ASCII-путём. `project_status.py --check` отмечает пять изменённых файлов до обновления общего снимка интегратором.

## Остаток

Полный целевой производитель снимка и публикация сброшенных внешних полей у владельца приложения ещё открыты. Путь до физического канала SLU, ток, скольжение и снятие блокировки при отказе требуют аппаратной проверки. Проверки этой порции относятся к ПК, симуляторам и ELF.
