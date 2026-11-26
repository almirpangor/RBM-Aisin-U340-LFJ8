"""Проверочный сценарий VSS → 0x1AE → расчёт импульса панели."""

from dataclasses import dataclass, replace
from fractions import Fraction

from .chery_1ae import VEHICLE_SPEED_WRAP_RAW, Packed1AE, PackerInputs, encode_1ae_vehicle_speed, pack_1ae_payload
from .chery_can import CapturedFrame, DecodeStatus, decode_chery_frame
from .chery_transport import DonorReceiveChannel, ReceivePoll, ReceiveSelection
from .u340 import SpeedCalibration


def pack_vss_sample(
    calibration: SpeedCalibration, vss_hz: Fraction | int, inputs: PackerInputs
) -> Packed1AE:
    vehicle_kmh = calibration.estimate(vss_hz).vehicle_kmh
    available_speed = vehicle_kmh if vehicle_kmh < Fraction(VEHICLE_SPEED_WRAP_RAW, 100) else None
    raw_speed = encode_1ae_vehicle_speed(available_speed)
    return pack_1ae_payload(replace(inputs, raw_fad2=raw_speed))


@dataclass(frozen=True)
class PanelSample:
    speed_q7: int
    pid_0d: int
    pulse_hz: Fraction


class DonorSpeedPanelScenario:
    """Штатный расчёт скорости S02 и расчётный выход панели из §7 ТЗ."""

    def __init__(self, calibration: SpeedCalibration) -> None:
        self._can = DonorReceiveChannel(0x1AE)
        self._calibration = calibration
        self._target_q7 = 0
        self._speed_q7 = 0

    def receive_tick(
        self,
        frame: CapturedFrame | None,
        *,
        exchange_enabled: bool,
        busoff_diagnostic_b254: bool,
    ) -> ReceivePoll:
        decoded = decode_chery_frame(frame) if frame is not None and frame.arbitration_id == 0x1AE else None
        matching_data = decoded is not None and decoded.status is DecodeStatus.DECODED
        status = self._can.step(
            exchange_enabled=exchange_enabled,
            matching_new_data=matching_data,
            busoff_diagnostic_b254=busoff_diagnostic_b254,
        )
        if status.selection in (ReceiveSelection.ENABLED_FALLBACK, ReceiveSelection.DISABLED_DEFAULT):
            self._target_q7 = 0
        elif status.selection is ReceiveSelection.PAYLOAD:
            assert decoded is not None and decoded.reading is not None
            self._target_q7 = (decoded.reading.raw // 25) << 5 if decoded.reading.value is not None else 0
        return status

    def speed_tick(self) -> PanelSample:
        # S02 limits one pass of the separate speed task by 128 Q7 units.
        self._speed_q7 += max(-128, min(128, self._target_q7 - self._speed_q7))
        speed_kmh = Fraction(self._speed_q7, 128)
        return PanelSample(
            self._speed_q7,
            min(self._speed_q7 >> 7, 255),
            speed_kmh * self._calibration.panel_hz_per_kmh,
        )
