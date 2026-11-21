# Bosch ME7.9.71 E4M3

Карточки [ECU-01/02](../../docs/project-map.md#ecu-01), [CAN-05](../../docs/project-map.md#can-05), [AUD-01](../../docs/project-map.md#aud-01). База — S04 по [реестру SHA-256](../../data/sources.json).

| Изменение | Куда идти |
| --- | --- |
| Патчирование S04, скорость и сборка | [build.py](build.py) |
| Публикация 0x0FA/0x278 | [tx.py](tx.py) |
| Сокращение переходов | [compact_branches.py](compact_branches.py) |
| Вход штатного запроса Chery | [chery_torque_rx.c](chery_torque_rx.c) |
| Границы восстановления нагрузки/TPS | [audit_bosch_signal_transport.py](audit_bosch_signal_transport.py), [audit_toyota_load_inputs.py](audit_toyota_load_inputs.py) |
| Обычный режим без круиза | [verify_ordinary_model_field.py](verify_ordinary_model_field.py) |
| Историческая трасса момента E4M3 | [replay_e4m3_torque.py](replay_e4m3_torque.py) |
| Панель, отложенный этап | [panel_gpio.c](panel_gpio.c), audit_panel_* |

Команды BOSCH/SIGNALS/TORQUE находятся в [карте проекта](../../docs/project-map.md#команды-проверок). R4 читается из зафиксированной копии, доработка выполняется в этом проекте.

## Обычный профиль с RPM-допуском RB

Сборка с `--with-rb-native-permit --with-model-fields --with-ordinary-model-field --compact` добавляет в общий штатный для S04 путь допуска RB проверку `FD18.6=1` и `FD1A.14=0`. Те же биты квалифицируют обороты для `0x0FA`. Проверка участвует в приёме START/REFRESH `0x5E8` и в трёх точках изменения запроса двигателя. CANCEL принимается независимо от квалификации RPM. Существуют отдельные условия E4M3 по T4, CAN, диапазону оборотов, токену и сроку RB.

ST10 переходит из `0x064E60` к проверке по `0x066F00` и возвращается в исходную ветвь допуска или отказа. Переходы в том же сегменте сохраняют рамку исходного вызова. Добавлено 44 байта Flash, заменены 4 байта входа. Дополнительной RAM и дополнительной глубины стека вызовов нет. Без новой опции прежние образы воспроизводятся побайтно.

```powershell
python -B targets/bosch/build.py --engine $r4Engine --s04 $s04 --outdir $out --with-model-fields --with-ordinary-model-field --compact --with-rb-native-permit
$image = Join-Path $out 'E4M3_CHERY_ORDINARY_MODEL_NO_CRUISE_RB_NATIVE_PERMIT_COMPACT_OFFLINE_ONLY.bin'
python -B targets/bosch/verify_ordinary_model_field.py --engine $r4Engine --s04 $s04 --model $c167Model --image $image --compact --with-rb-native-permit
python -B targets/bosch/verify_bench_profile.py --engine $r4Engine --s04 $s04 --image $image
```

Для отдельной проверки совместимости можно добавить `--with-rx-timestamp` и к сборке, и к `verify_bench_profile.py`. В одном образе исполняются обе проверки ST10. Для диалога с компилированным запросчиком H03 верификатор принимает `--h03-fixture`.

[Передача ECU-01](../../verification/bench-wave/chat-8/handoff.json) содержит карту изменений S04, точные SHA, численные источники, контракт сырых операндов для TOY-02 и остаток по стендовой паре. Проверки запуска исполняют выбранные инструкции инициализации стека. Полный пуск, впрыск и зажигание на блоке остаются предметом стендовой приёмки.

Доступный обмен не восстанавливает все операнды нагрузки Toyota однозначно. Текущий диалог момента 0x5E8/0x5E9 использует RB, его не следует называть штатным запросом Chery. Профили OFFLINE_ONLY и проверка 51 записи целостности не являются подтверждением работы двигателя на новой связке.
