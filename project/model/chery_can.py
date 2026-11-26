"""Офлайн-разбор проверенных полей донорского CAN Chery, раздел 3 ТЗ."""

from dataclasses import dataclass
from enum import Enum
from fractions import Fraction

from .chery_1ae import Raw1AEFields, VEHICLE_SPEED_WRAP_RAW, parse_1ae_payload


class FrameFormat(Enum):
    STANDARD_DATA = "classic_standard_data"
    EXTENDED_DATA = "classic_extended_data"
    REMOTE = "classic_remote"
    FD = "fd"
    UNKNOWN = "unknown"


class Direction(Enum):
    ECM_TO_TA2005 = "chery_ecm_to_ta2005"
    TA2005_TO_ECM = "ta2005_to_chery_ecm"


class DirectionEvidence(Enum):
    DONOR_TX_AND_RX = "donor_tx_and_rx_code"
    DONOR_RX_TX_CANDIDATE = "donor_rx_code_and_tx_candidate"


class DecodeStatus(Enum):
    FORMAT_UNSUPPORTED = "format_unsupported"
    ID_UNKNOWN = "id_unknown"
    LENGTH_MISMATCH = "length_mismatch"
    PAYLOAD_NOT_DECODED = "payload_not_decoded"
    DIRECTION_UNKNOWN = "direction_unknown"
    DIRECTION_MISMATCH = "direction_mismatch"
    DECODED = "decoded"


@dataclass(frozen=True, kw_only=True)
class CapturedFrame:
    arbitration_id: int
    payload: bytes
    dlc: int
    frame_format: FrameFormat
    observed_direction: Direction | None = None


@dataclass(frozen=True)
class SignalReading:
    signal: str
    unit: str
    raw: int
    value: Fraction | None


@dataclass(frozen=True)
class DecodeResult:
    frame: CapturedFrame
    status: DecodeStatus
    donor_direction: Direction | None = None
    direction_evidence: DirectionEvidence | None = None
    reading: SignalReading | None = None
    fields_1ae: Raw1AEFields | None = None


def decode_chery_frame(frame: CapturedFrame) -> DecodeResult:
    """Разобрать кадр, идентифицированный в записи штатной донорской пары."""
    if frame.frame_format is not FrameFormat.STANDARD_DATA or not 0 <= frame.arbitration_id <= 0x7FF:
        return DecodeResult(frame, DecodeStatus.FORMAT_UNSUPPORTED)

    if frame.arbitration_id in (0x0FA, 0x278):
        direction = Direction.ECM_TO_TA2005
    elif frame.arbitration_id in (0x1AE, 0x300):
        direction = Direction.TA2005_TO_ECM
    else:
        return DecodeResult(frame, DecodeStatus.ID_UNKNOWN)

    evidence = DirectionEvidence.DONOR_TX_AND_RX
    if frame.dlc != 8 or len(frame.payload) != frame.dlc:
        return DecodeResult(frame, DecodeStatus.LENGTH_MISMATCH, direction, evidence)
    if frame.observed_direction is None:
        return DecodeResult(frame, DecodeStatus.DIRECTION_UNKNOWN, direction, evidence)
    if frame.observed_direction is not direction:
        return DecodeResult(frame, DecodeStatus.DIRECTION_MISMATCH, direction, evidence)

    if frame.arbitration_id == 0x1AE:
        fields = parse_1ae_payload(frame.payload)
        raw = fields.bytes6_7
        speed = Fraction(raw, 100) if raw < VEHICLE_SPEED_WRAP_RAW else None
        reading = SignalReading("vehicle_speed", "km/h", raw, speed)
        return DecodeResult(frame, DecodeStatus.DECODED, direction, evidence, reading, fields)
    if frame.arbitration_id == 0x0FA:
        raw = int.from_bytes(frame.payload[:2], "big")
        rpm = None if raw == 0xFFFF else Fraction(raw, 4)
        reading = SignalReading("engine_speed", "rpm", raw, rpm)
    elif frame.arbitration_id == 0x300:
        raw = frame.payload[3]
        atf_c = None if raw == 0xFF else Fraction(min(raw, 144) - 40)
        reading = SignalReading("atf_temperature", "°C", raw, atf_c)
    else:
        raw = frame.payload[0]
        coolant_c = None if raw == 0xFF else Fraction(3 * raw, 4) - 48
        reading = SignalReading("coolant_temperature", "°C", raw, coolant_c)

    return DecodeResult(frame, DecodeStatus.DECODED, direction, evidence, reading)
