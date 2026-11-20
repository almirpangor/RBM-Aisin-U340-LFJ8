# Блок управления АКПП Aisin U340E

Проект RB Motors для блока АКПП LFJ8 18 9E1D и двигателя GW4G15 с Bosch ME7.9.71 E4M3. Переключения основаны на логике Toyota U340E. Для связи двигателя и АКПП изучается штатный CAN Chery Tiggo T11 ↔ Continental TA2005.

- [Техническое задание, редакция 1.0](docs/RBM_TZ_Aisin_U340_LFJ8_Codex_v1_0.pdf)
- [Реестр источников, коммитов и SHA-256](data/sources.json)
- [Журнал решений](docs/decisions.md)

## Проверка исходных файлов

Для воспроизведения проверки нужны Git, Python 3.10 или новее, доступ на чтение к R1 и предоставленный владельцем `RB-J-P01.bin`. Из корня проекта выполните следующие команды, подставив локальный путь к дампу.

```powershell
git clone --no-checkout https://github.com/almirpangor/CM-AVEO-TCM-AKP-U340.git .sources/R1
python tools/verify_sources.py --donor-repo .sources/R1 --lfj8 'C:/path/to/RB-J-P01.bin'
```

Проверка сравнивает фактические размеры и SHA-256 с реестром. Для S01–S04 она также сверяет идентификаторы Git blob в зафиксированном коммите. SHA-256 идентифицирует файл. Штатная внутренняя проверка целостности ЭБУ исследуется отдельно.
