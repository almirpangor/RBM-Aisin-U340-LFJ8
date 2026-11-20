# H03-03. Целевой запуск и выпуск событий Toyota

База исходников `f64eff7c24744cef0fe608415039c6d10c677ff1`. H03 `LFJ8-T-D.bin` SHA-256 `844a11b809cda1f2ccaf90cb6a75666009487ccedd2e8190b7eb46137b855544`.

`lfj8_h03_target_platform.c` определяет два символа, уже вызываемых из `rbm_h03_application_binding`. Startup после штатной операции 0x00A838 и сброса программного состояния AN2 проверяет RAM, часы и закрытый допуск под общей блокировкой H03. Подготовка владельцев входов проходит в foreground с закрытым допуском. После неё startup повторно проверяет RAM и часы и сбрасывает единственное состояние выпуска Toyota.

Foreground после штатного обновления входов 0x040324 передаёт уже собранный S51/S83/ATF в существующий `lfj8_h03_toyota_source_take`. С ним действует независимый период на TML0CT 0x8003E0. Первый дедлайн отсчитывается от startup, следующие от предыдущего дедлайна. Поставщик входов сохраняет исходные отметки измерений, source назначает номер события, а приложение подмешивает вход двигателя через общего CAN owner. Просрочка или отказ поставщика идут через существующий отказ приложения и снятие допуска. Проверка в штатном ожидании продолжает действовать при отсутствии фазы выдачи.

## Сборка и модель

- GNU M32R GCC 4.8.0, big-endian, medium model. Новый объект занимает 356 байт загружаемых секций, включая 32 байта постоянного описателя. Собственная writable-секция отсутствует. Финальный план RAM должен предоставить один выровненный на 4 байта объект `rbm_h03_toyota_release_state` размером 16 байт.
- По дизассемблированному объекту целевой startup сохраняет 24 байта, вложенная проверка допуска ещё 8 байт. Обёртка выпуска Toyota занимает 8 байт стека. Расход вызываемых поставщиков и вложенных IRQ сюда не входит.
- В M32R ELF связаны оба новых поставщика, настоящие application binding, Toyota source из сборки 9E1C и ASM-врезки startup, выпуска фазы и foreground. Проверены отказ RAM и часов, отказ подготовки входов, потеря RAM при подготовке, тёплый сброс номера события, переполнение TML0, передача меток входов, просроченный выпуск, отказ захвата и watchdog без фазы. Проверены PSW при входе и возврате и отказ сборки при отсутствующем или несовместимом профиле. Стендовые входы, MMIO и периоды принадлежат только тесту.
- Регрессия `check_h03_phase_boot.py` на точных фрагментах H03 прошла 62 сценария и 96 захватов IRQ с совпавшим контекстом. `check_h03_application_binding.py` и отдельная проверка штатного источника `check_h03_toyota_source.py` также прошли. `check_h03_storage.py` повторно подтвердил измеряемый базовый состав 2728 байт в модели адресов. Новые 16 байт в эту цифру не включены.

```powershell
python -B controller/build_target.py m32r --cc $gcc --out local/platform/controller
python -B targets/lfj8/build.py --output local/platform/bridge --m32r-cc $gcc --base-9e1c $h03
python -B targets/lfj8/check_h03_target_platform.py --gcc $gcc --controller local/platform/controller/rbm_u340e_m32r_be.o --bridge local/platform/bridge/lfj8_9e1c_m32r.o --out local/platform/provider.json
python -B targets/lfj8/check_h03_phase_boot.py --base $h03 --gcc $gcc --controller local/platform/controller/rbm_u340e_m32r_be.o --out local/platform/phase-boot.json
python -B targets/lfj8/check_h03_application_binding.py --gcc $gcc --controller local/platform/controller/rbm_u340e_m32r_be.o --out local/platform/binding.json
python -B targets/lfj8/check_h03_storage.py --base $h03 --gcc $gcc --out local/platform/storage.json
python -B targets/lfj8/check_h03_toyota_source.py --base $h03 --gcc $gcc --controller local/platform/controller/rbm_u340e_m32r_be.o --bridge local/platform/bridge/lfj8_9e1c_m32r.o --storage-report local/platform/storage.json --out local/platform/source.json
```

## Остаток перед полной компоновкой

При интеграции добавить `lfj8_h03_target_platform.c` к `lfj8_h03_application_binding.c` с тем же `RBM_H03_APPLICATION_PROFILE`. В текущей порции эти файлы связаны в M32R проверке. Общий скрипт размещения был зарезервирован VSS-02, типизированный инвентарь RAM удерживал CAN-03. Для финального образа нужны добавление модуля в общий список сборки, поле выпуска в инвентаре, символ линкера и подтверждённый охват этой области в H03-04.

Для целевого профиля ещё нужны доказанный период Toyota и максимальное опоздание в TML0, квалифицированные функции подготовки и формирования входов с нагрузкой и состоянием водителя, а также согласованные соседние владельцы CAN, выходов, старта Toyota, часов и NVM. Функции профиля описаны в `lfj8_h03_target_platform.h`. Аппаратная проверка и итоговый линк пары BIN остаются открыты.
