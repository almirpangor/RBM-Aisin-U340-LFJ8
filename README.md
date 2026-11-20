# Блок управления АКПП Aisin U340E

Проект RB Motors для Aisin U340E и двигателя GW4G15 с Bosch ME7.9.71 E4M3. Владелец выбрал исходным образом для блока АКПП `RB-J-P01.bin` (S05). Это программа Mazda PCM `LFJ8-18-881F` на SuperH. Переключения моделируются по Toyota U340E, обмен между блоками восстанавливается по Chery Tiggo T11 и Continental TA2005.

- [Состав комплекта и результаты по пунктам ТЗ](docs/working-set.md)
- [Исходное техническое задание, редакция 1.0](docs/RBM_TZ_Aisin_U340_LFJ8_Codex_v1_0.pdf)
- [Реестр источников, коммитов и SHA-256](data/sources.json)
- [Выбор платформы и журнал решений](docs/decisions.md)
- [План подключения, приёмки и восстановления](docs/verification.md)

Исходное ТЗ указывает отдельный TCM `LFJ8-18-9E1D`. Ранее согласованный образ `9E1B` — донор для исследования этой платформы. Для прошивки на основе S05 применяются адреса и драйверы SuperH. [Сверка образов Mazda](docs/lfj8-target-identity.md)

## Проверка исходных файлов

Для воспроизведения проверки нужны Git, Python 3.10 или новее, доступ на чтение к R1 и предоставленный владельцем `RB-J-P01.bin`. Подставьте локальные пути к PCM S05 и донору TCM S06.

```powershell
git clone --no-checkout https://github.com/almirpangor/CM-AVEO-TCM-AKP-U340.git .sources/R1
python tools/verify_sources.py --donor-repo .sources/R1 --pcm-image 'C:/path/to/RB-J-P01.bin' --tcm-donor 'C:/path/to/LFJ8TB000LFXA0A0-20260806-160523(TCM-adapt).bin'
```

Проверка сравнивает фактические размеры и SHA-256 с реестром. Для S01–S04 она также сверяет идентификаторы Git blob в зафиксированном коммите. Проверки внутренней целостности Mazda и Bosch описаны в отчётах соответствующих сборок.

## Запуск программной модели

```powershell
python -B -m unittest discover -s tests -v
python -B tools/build_pc_checks.py --cc zig --out local/pc-checks
```
