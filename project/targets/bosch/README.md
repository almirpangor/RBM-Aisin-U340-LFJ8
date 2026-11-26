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

Доступный обмен не восстанавливает все операнды нагрузки Toyota однозначно. Текущий диалог момента 0x5E8/0x5E9 использует RB, его не следует называть штатным запросом Chery. Профили OFFLINE_ONLY и проверка 51 записи целостности не являются подтверждением работы двигателя на новой связке.
