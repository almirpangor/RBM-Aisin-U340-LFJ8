# Aisin U340E • H03 и Bosch E4M3

Комплект RB Motors от 26 ноября 2026 года. Оба BIN предназначены для симуляторов. Полное управление U340E и активное согласование момента Chery ещё в разработке. Испытания на стенде не проводились.

[Скачать полный архив](https://github.com/almirpangor/RBM-Aisin-U340-LFJ8/releases/download/u340e-offline-20261126/RBM_U340E_H03_E4M3_OFFLINE_ONLY.zip) · [Сверка 11 разделов ТЗ](СВЕРКА_ТЗ.txt) · [Исходное ТЗ](project/docs/RBM_TZ_Aisin_U340_LFJ8_Codex_v1_0.pdf)

| Образ | Что проверено |
| --- | --- |
| [H03 LFJ8-18-9E1C](offline/LFJ8_H03_EARLY_IRQ_DMA4_SERVICE_GUARDS_OFFLINE_ONLY.bin) | Два пути сброса, защита IRQ, DMA4 и сервисных записей |
| [Bosch ME7.9.71 E4M3](offline/E4M3_CHERY_ORDINARY_MODEL_NO_CRUISE_RX_TIMESTAMP_RB_NATIVE_PERMIT_CHERY_PASSIVE_CAPTURE_COMPACT_OFFLINE_ONLY.bin) | Пассивный приём двух байтов кадра Chery `0x1AE`, 51 проверка целостности и все 65 536 сочетаний байтов |

Исходники находятся в `project/`, `sources/` и `components/`, согласованные доноры в `inputs/`, журналы в `checks/`. В архив включён Windows-компилятор M32R. Повторная сборка из распакованного архива с Python 3.13:

```powershell
python -X utf8 -B rebuild.py --out rebuilt --verify
```

[Манифест образов](release.json) · [Контрольные суммы всех файлов](SHA256SUMS.txt)
