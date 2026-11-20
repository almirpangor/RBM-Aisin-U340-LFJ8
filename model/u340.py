"""Проверяемая модель требований, независимая от контроллера и шины CAN."""

from dataclasses import dataclass
from enum import Enum, IntEnum
from fractions import Fraction


VSS_PULSES_PER_DIFFERENTIAL_REV = Fraction(100, 22)


@dataclass(frozen=True)
class RelayCommands:
    reverse_lamp: bool
    auxiliary: bool


def relay_commands(selector: str) -> RelayCommands:
    """Вычислить команды реле по декодированному положению селектора."""
    return RelayCommands(reverse_lamp=selector == "R", auxiliary=selector in ("R", "L"))


@dataclass(frozen=True)
class SpeedEstimate:
    vehicle_kmh: Fraction
    panel_hz: Fraction


@dataclass(frozen=True)
class SpeedCalibration:
    wheel_rev_per_differential_rev: Fraction
    wheel_circumference_m: Fraction
    panel_hz_per_kmh: Fraction

    def __post_init__(self) -> None:
        for value in (
            self.wheel_rev_per_differential_rev,
            self.wheel_circumference_m,
            self.panel_hz_per_kmh,
        ):
            if not isinstance(value, (Fraction, int)) or isinstance(value, bool) or value <= 0:
                raise ValueError("Калибровка требует положительных точных значений Fraction или int")

    def estimate(self, vss_hz: Fraction | int) -> SpeedEstimate:
        if not isinstance(vss_hz, (Fraction, int)) or isinstance(vss_hz, bool) or vss_hz < 0:
            raise ValueError("Частота VSS должна быть неотрицательным Fraction или int")
        differential_rev_per_s = vss_hz / VSS_PULSES_PER_DIFFERENTIAL_REV
        wheel_rev_per_s = differential_rev_per_s * self.wheel_rev_per_differential_rev
        meters_per_s = wheel_rev_per_s * self.wheel_circumference_m
        vehicle_kmh = meters_per_s * Fraction(18, 5)
        return SpeedEstimate(vehicle_kmh, vehicle_kmh * self.panel_hz_per_kmh)


class DriveMode(Enum):
    AUTO = "Auto"
    TIPTRONIC = "Tiptronic"

    def toggled(self) -> "DriveMode":
        return DriveMode.TIPTRONIC if self is DriveMode.AUTO else DriveMode.AUTO


class ShiftRequest(IntEnum):
    DOWN = -1
    UP = 1


@dataclass(frozen=True)
class Buttons:
    mode: bool = False
    up: bool = False
    down: bool = False
    overdrive: bool = False


@dataclass(frozen=True)
class DriverRequests:
    mode: DriveMode
    shift: ShiftRequest | None
    overdrive_button_pressed: bool
    simultaneous_shift_inputs: bool


class _ButtonPress:
    def __init__(self) -> None:
        self.stable: bool | None = None
        self.candidate = False
        self.candidate_since_ms = 0

    def update(self, pressed: bool, now_ms: int, debounce_ms: int) -> bool:
        if self.stable is None:
            self.stable = self.candidate = pressed
            self.candidate_since_ms = now_ms
            return False

        if pressed != self.candidate:
            self.candidate = pressed
            self.candidate_since_ms = now_ms

        if self.candidate == self.stable or now_ms - self.candidate_since_ms < debounce_ms:
            return False

        self.stable = self.candidate
        return self.stable


class DriverControls:
    """Преобразовать выбор режима и нажатия в запросы водителя."""

    def __init__(self, *, starting_mode: DriveMode, debounce_ms: int) -> None:
        if not isinstance(starting_mode, DriveMode):
            raise ValueError("Требуется явно заданный начальный режим DriveMode")
        if type(debounce_ms) is not int or debounce_ms < 0:
            raise ValueError("Время устранения дребезга задаётся целым числом миллисекунд")
        self.mode = starting_mode
        self.debounce_ms = debounce_ms
        self._last_ms: int | None = None
        self._mode_button = _ButtonPress()
        self._up_button = _ButtonPress()
        self._down_button = _ButtonPress()
        self._overdrive_button = _ButtonPress()

    def sample(self, now_ms: int, buttons: Buttons) -> DriverRequests:
        if type(now_ms) is not int or now_ms < 0:
            raise ValueError("Время отсчёта задаётся целым числом миллисекунд от начала сценария")
        if self._last_ms is not None and now_ms < self._last_ms:
            raise ValueError("Время отсчёта не должно идти назад")
        self._last_ms = now_ms

        mode_pressed = self._mode_button.update(buttons.mode, now_ms, self.debounce_ms)
        up_pressed = self._up_button.update(buttons.up, now_ms, self.debounce_ms)
        down_pressed = self._down_button.update(buttons.down, now_ms, self.debounce_ms)
        od_pressed = self._overdrive_button.update(buttons.overdrive, now_ms, self.debounce_ms)

        if mode_pressed:
            self.mode = self.mode.toggled()

        simultaneous_shift_inputs = (up_pressed and down_pressed) or (
            mode_pressed and (up_pressed or down_pressed)
        )
        shift = None
        if self.mode is DriveMode.TIPTRONIC and not simultaneous_shift_inputs:
            if up_pressed:
                shift = ShiftRequest.UP
            elif down_pressed:
                shift = ShiftRequest.DOWN

        return DriverRequests(self.mode, shift, od_pressed, simultaneous_shift_inputs)
