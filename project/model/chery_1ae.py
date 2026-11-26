"""Офлайн-разбор и воспроизведение штатной упаковки TA2005 0x1AE."""

from dataclasses import dataclass
from fractions import Fraction


VEHICLE_SPEED_UNAVAILABLE = 0xFFFF
VEHICLE_SPEED_WRAP_RAW = (0x10000 >> 5) * 25


def encode_1ae_vehicle_speed(speed_kmh: Fraction | int | None) -> int:
    """Кодировать скорость для 0x1AE[6:8], усекать дробную часть отсчёта."""
    if speed_kmh is None:
        return VEHICLE_SPEED_UNAVAILABLE
    if not isinstance(speed_kmh, (Fraction, int)) or isinstance(speed_kmh, bool) or speed_kmh < 0:
        raise ValueError("Скорость задаётся неотрицательным Fraction или int, либо None")
    raw = int(speed_kmh * 100)
    if raw >= VEHICLE_SPEED_WRAP_RAW:
        raise ValueError("Скорость превышает диапазон 16-разрядного преобразования в Chery ECM")
    return raw


def _control_value(byte1: int, byte4: int) -> int:
    return ~(byte1 + byte4) & 0xFF


@dataclass(frozen=True)
class Raw1AEFields:
    byte0_bits7_5: int
    flag_f842_5: bool
    checksum_low: int
    byte1: int
    flag_fd18_4: bool
    flag_fd10_7: bool
    f8e1_low_two_bits: int
    counter_low_three_bits: int
    flag_f83e_4: bool
    byte3_high: int
    checksum_high: int
    byte4: int
    byte5: int
    bytes6_7: int

    @property
    def checksum(self) -> int:
        return (self.checksum_high << 4) | self.checksum_low

    @property
    def expected_checksum(self) -> int:
        return _control_value(self.byte1, self.byte4)

    @property
    def checksum_matches(self) -> bool:
        return self.checksum == self.expected_checksum

    @property
    def byte1_is_reserved(self) -> bool:
        return self.byte1 == 0xFF

    @property
    def byte4_is_reserved(self) -> bool:
        return self.byte4 == 0xFF

    @property
    def byte5_is_reserved(self) -> bool:
        return self.byte5 == 0xFF

    @property
    def bytes6_7_is_reserved(self) -> bool:
        return self.bytes6_7 == VEHICLE_SPEED_UNAVAILABLE

    def counter_delta(self, previous_counter: int) -> int:
        """Разность по модулю 8 для отдельного критерия последовательности."""
        if type(previous_counter) is not int or not 0 <= previous_counter <= 7:
            raise ValueError("Предыдущий счётчик задаётся целым числом от 0 до 7")
        return (self.counter_low_three_bits - previous_counter) & 7


def parse_1ae_payload(payload: bytes) -> Raw1AEFields:
    """Разложить восемь байтов записи, сохраняя сырые и резервные значения."""
    if not isinstance(payload, bytes) or len(payload) != 8:
        raise ValueError("Для разбора 0x1AE требуется ровно восемь байтов")
    byte0, byte1, byte2, byte3, byte4, byte5, byte6, byte7 = payload
    return Raw1AEFields(
        byte0_bits7_5=byte0 >> 5,
        flag_f842_5=bool(byte0 & 0x10),
        checksum_low=byte0 & 0xF,
        byte1=byte1,
        flag_fd18_4=bool(byte2 & 1),
        flag_fd10_7=bool(byte2 & 2),
        f8e1_low_two_bits=(byte2 >> 2) & 3,
        counter_low_three_bits=(byte2 >> 4) & 7,
        flag_f83e_4=bool(byte2 & 0x80),
        byte3_high=byte3 >> 4,
        checksum_high=byte3 & 0xF,
        byte4=byte4,
        byte5=byte5,
        bytes6_7=(byte6 << 8) | byte7,
    )


@dataclass(frozen=True, kw_only=True)
class PackerInputs:
    byte1: int
    byte3_high: int
    byte4: int
    raw_fa5f: int
    raw_fad2: int
    raw_f8e1: int
    counter_f8e4: int
    flag_f842_5: bool
    flag_fd18_4: bool
    flag_fd10_7: bool
    flag_f83e_4: bool
    flag_e026_0: bool

    def __post_init__(self) -> None:
        for name in ("byte1", "byte4", "raw_fa5f", "raw_f8e1", "counter_f8e4"):
            value = getattr(self, name)
            if type(value) is not int or not 0 <= value <= 0xFF:
                raise ValueError(f"{name} должен быть беззнаковым байтом")
        if type(self.byte3_high) is not int or not 0 <= self.byte3_high <= 0xF:
            raise ValueError("byte3_high должен быть беззнаковым полубайтом")
        if type(self.raw_fad2) is not int or not 0 <= self.raw_fad2 <= 0xFFFF:
            raise ValueError("raw_fad2 должен быть беззнаковым 16-битным словом")
        for name in ("flag_f842_5", "flag_fd18_4", "flag_fd10_7", "flag_f83e_4", "flag_e026_0"):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} должен быть булевым значением")


@dataclass(frozen=True)
class Packed1AE:
    payload: bytes
    next_counter_f8e4: int


def pack_1ae_payload(inputs: PackerInputs) -> Packed1AE:
    """Воспроизвести один вызов исходного упаковщика 0x057028 в памяти."""
    checksum = _control_value(inputs.byte1, inputs.byte4)
    next_counter = (inputs.counter_f8e4 + 1) & 0xFF if inputs.flag_fd18_4 else 0
    byte2 = (
        inputs.flag_fd18_4
        | (inputs.flag_fd10_7 << 1)
        | ((inputs.raw_f8e1 & 3) << 2)
        | ((next_counter & 7) << 4)
        | (inputs.flag_f83e_4 << 7)
    )
    byte5 = 0xFF if inputs.flag_e026_0 else min(2 * inputs.raw_fa5f, 0xFE)
    payload = bytes((
        (inputs.flag_f842_5 << 4) | (checksum & 0xF),
        inputs.byte1,
        byte2,
        (inputs.byte3_high << 4) | (checksum >> 4),
        inputs.byte4,
        byte5,
    )) + inputs.raw_fad2.to_bytes(2, "big")
    return Packed1AE(payload, next_counter)
