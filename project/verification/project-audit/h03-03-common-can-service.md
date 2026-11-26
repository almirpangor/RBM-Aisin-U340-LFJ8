# H03-03. Привязки сервиса CAN в профильной сборке

База `main` `f64eff7c24744cef0fe608415039c6d10c677ff1`. Включены проверка платформы H03-03 `17e55b554758`, OEM-переходы DTC-02 `1bc3c22b1811`, отзыв TX13 `40d644fdc0de` и связанный переход TX13 `1eefa2abd890` от CAN-03. SHA-256 исходного H03 `844a11b809cda1f2ccaf90cb6a75666009487ccedd2e8190b7eb46137b855544`.

`lfj8_h03_can_service_placement.py` задаёт состав из четырёх штатных C-модулей и 11 привязок к существующим полям RAM. При привязке проверяются границы блока, выравнивание и отсутствие пересечений. M32R-проверка CAN использует тот же список и получает адреса из свежего инвентаря. В модели одна копия каждого поля, включая общего CAN owner, DTC target и брокер CAN13.

При запуске `check_h03_can_monitor_revoke.py` с объектами сборки выполняется отдельная профильная композиция через общий компоновщик. В неё входят настоящее приложение с `rbm_h03_application_binding`, сервис CAN, отзыв TX13 и нижний BasicCAN. Адресная проверка разрешила все 11 алиасов и точки подготовки, foreground, остановки, отзыва TX13 и gate. Удерживаемая часть помещается в кандидатные окна с размером 101 052 байта Flash, включая два нижних OEM-перехода DTC, и 4 байта отдельного указателя IRQ. CAN owner находится по `0x808F48`, CAN service по `0x80904C`.

Общий линк этой модели возвращает `FAIL_BINDINGS` из-за остальных привязок приложения и поставщиков профиля. Для общей проверки передаётся только заголовок модельного профиля. Реализации испытательных поставщиков входят в отдельный ELF симулятора. В нём прошли 16 шагов штатного сервиса и два сценария отказа. Отдельный ELF TX13 подтвердил слово на `0x00C34C`, возврат на `0x00C350` и 18 сценариев штатного foreground и CAN0 IRQ.

```powershell
python -B controller/build_target.py m32r --cc $gcc --out local/common-can/controller
python -B targets/lfj8/build.py --output local/common-can/bridge --m32r-cc $gcc --base-9e1c $h03
python -B targets/lfj8/check_h03_storage.py --base $h03 --gcc $gcc --out local/common-can/storage.json
python -B targets/lfj8/check_h03_can_monitor_revoke.py --base $h03 --gcc $gcc --controller local/common-can/controller/rbm_u340e_m32r_be.o --bridge local/common-can/bridge/lfj8_9e1c_m32r.o --storage-report local/common-can/storage.json --out local/common-can/service-profiled.json
python -B targets/lfj8/check_h03_torque_tx_gate.py --base $h03 --gcc $gcc --out local/common-can/tx-gate.json
python -B -m unittest discover -s tests -p "test_h03*.py"
```

Прошли все 22 группы `check_integrated_h03.py --suite native` и отдельная адресная проверка `check_h03_target_platform.py --base`. После включения связанного TX13 повторены профильный сервис CAN, ELF TX13 и 51 тест семейства `test_h03*.py`.

На момент проверки основной файл компоновщика был зарезервирован H03-04. Остаётся зарегистрировать в нём состав сервиса и привязки RAM, закрепить OEM-слово TX13 рядом с двумя нижними переходами в плане и проверить его через `lfj8_h03_tx13_placement.describe`. Код штатного CAN monitor startup проверялся в отдельной модели. Для выпуска также требуются проверенный профиль, размещение остальных поставщиков и аппаратная приёмка.
