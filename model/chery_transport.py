"""Модель проверенных окон приёма S02 в единицах вызовов задач."""

from dataclasses import dataclass
from enum import Enum

from .chery_1ae import Raw1AEFields


class ReceiveSelection(Enum):
    KEEP = "keep_previous"
    PAYLOAD = "payload_received"
    ENABLED_FALLBACK = "enabled_fallback"
    DISABLED_DEFAULT = "disabled_default"


@dataclass(frozen=True)
class ReceivePoll:
    polled: bool
    unsuccessful_polls: int
    loss_flag: bool
    selection: ReceiveSelection


class DonorReceiveChannel:
    """Моделирует отдельную ветвь S02 для результата аппаратного опроса."""

    def __init__(self, arbitration_id: int, *, initial_skip: int = 0) -> None:
        if arbitration_id == 0x1AE:
            self._skip_reload, self._miss_threshold = 1, 15
        elif arbitration_id == 0x300:
            self._skip_reload, self._miss_threshold = 5, 5
        else:
            raise ValueError("Модель поддерживает ветви S02 для 0x1AE и 0x300")
        if type(initial_skip) is not int or not 0 <= initial_skip <= self._skip_reload:
            raise ValueError("Начальный счётчик пропуска должен быть в пределах периода опроса")
        self._skip = initial_skip
        self._misses = 0
        self._lost = False

    def step(
        self, *, exchange_enabled: bool, matching_new_data: bool, busoff_diagnostic_b254: bool
    ) -> ReceivePoll:
        if not exchange_enabled:
            return ReceivePoll(False, self._misses, self._lost, ReceiveSelection.DISABLED_DEFAULT)
        if self._skip:
            self._skip -= 1
            return ReceivePoll(False, self._misses, self._lost, ReceiveSelection.KEEP)

        self._skip = self._skip_reload
        if matching_new_data:
            self._misses = 0
            self._lost = False
        elif self._misses >= self._miss_threshold:
            self._lost = True
        else:
            self._misses += 1

        if self._lost or busoff_diagnostic_b254:
            selection = ReceiveSelection.ENABLED_FALLBACK
        elif matching_new_data:
            selection = ReceiveSelection.PAYLOAD
        else:
            selection = ReceiveSelection.KEEP
        return ReceivePoll(True, self._misses, self._lost, selection)


class _DonorQualifier:
    def __init__(self, threshold: int) -> None:
        self._threshold = threshold
        self._count = 0
        self._asserted = False

    def step(self, enabled: bool) -> bool:
        if not enabled:
            self._count = 0
            self._asserted = False
        elif self._count < self._threshold:
            self._count += 1
        else:
            self._asserted = True
        return self._asserted


@dataclass(frozen=True)
class RequestQualification:
    checksum_error: bool
    sequence_error: bool
    checksum_fault: bool
    sequence_fault: bool
    combined_latch: bool
    byte1_fallback: bool
    byte4_fallback: bool


class Donor1AERequestQualifier:
    """Воспроизводит биты диагностики и резерва S02 в 028CD0..029128."""

    def __init__(self) -> None:
        self._previous_counter = 0
        self._checksum_errors = 0
        self._sequence_errors = 0
        self._combined_latch = False
        self._checksum_recovery = _DonorQualifier(3)
        self._combined_clear = _DonorQualifier(3)
        self._combined_set = _DonorQualifier(3)

    def step(
        self, fields: Raw1AEFields, *, sequence_enabled: bool, external_invalid_flag: bool
    ) -> RequestQualification:
        checksum_error = not fields.checksum_matches
        sequence_error = sequence_enabled and fields.counter_delta(self._previous_counter) not in (1, 2)
        self._previous_counter = fields.counter_low_three_bits
        if checksum_error:
            self._checksum_errors = min(3, self._checksum_errors + 1)
        if self._checksum_recovery.step(not checksum_error):
            self._checksum_errors = 0
        self._sequence_errors = min(3, self._sequence_errors + 1) if sequence_error else 0

        sample_invalid = checksum_error or sequence_error
        can_clear = self._combined_clear.step(not sample_invalid)
        must_set = self._combined_set.step(sample_invalid)
        if can_clear:
            self._combined_latch = False
        elif must_set:
            self._combined_latch = True

        checksum_fault = self._checksum_errors == 3
        sequence_fault = self._sequence_errors == 3
        fallback = self._combined_latch or checksum_fault or sequence_fault or external_invalid_flag
        return RequestQualification(
            checksum_error,
            sequence_error,
            checksum_fault,
            sequence_fault,
            self._combined_latch,
            fallback or fields.byte1_is_reserved,
            fallback or fields.byte4_is_reserved,
        )
