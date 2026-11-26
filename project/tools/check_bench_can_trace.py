"""Офлайн-проверка периодических CAN-кадров в журнале стенда CANHacker TEXT v3."""

import argparse
import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from model.chery_1ae import parse_1ae_payload


PERIODIC_IDS = ("0FA", "278", "1AE", "300")
ARCHIVED_FLAGS = (0x00000004, 0x00000000)
MINUTE_US = 60_000_000


@dataclass(frozen=True)
class Record:
    time_us: int
    stream: str
    can_id: str
    flags: tuple[int, int]
    payload: bytes


def parse_record(line: str) -> Record:
    columns = [column.strip() for column in line.split("\t")]
    if len(columns) < 7:
        raise ValueError("Ожидаются как минимум семь полей TRC")
    time, stream, flags, can_id, dlc, data, tail = columns[:7]
    stamp = re.fullmatch(r"([0-9]+)[,.]([0-9]{1,6})", time)
    if stamp is None or re.fullmatch(r"[0-9]+", stream) is None:
        raise ValueError("Некорректная метка времени или номер потока")
    if not all(re.fullmatch(r"[0-9A-Fa-f]{8}", value) for value in (flags, tail)):
        raise ValueError("Некорректное поле флагов")
    if re.fullmatch(r"[0-9A-Fa-f]{1,8}", can_id) is None or int(can_id, 16) > 0x1FFFFFFF:
        raise ValueError("Некорректный идентификатор CAN")
    octets = data.split()
    if dlc not in "0 1 2 3 4 5 6 7 8".split() or len(octets) != int(dlc):
        raise ValueError("Поле DLC не соответствует числу байтов")
    if any(re.fullmatch(r"[0-9A-Fa-f]{2}", octet) is None for octet in octets):
        raise ValueError("Некорректный байт CAN")
    seconds, fraction = stamp.groups()
    time_us = int(seconds) * 1_000_000 + int(fraction.ljust(6, "0"))
    return Record(
        time_us, stream, f"{int(can_id, 16):03X}",
        (int(flags, 16), int(tail, 16)), bytes.fromhex(data),
    )


@dataclass
class PeriodicFrames:
    accepted: int = 0
    excluded: int = 0
    gaps: Counter[int] = field(default_factory=Counter)
    checksum_errors: int = 0
    counter_errors: int = 0
    previous_time_us: int | None = None
    previous_counter: int | None = None

    def reset_comparison(self) -> None:
        self.previous_time_us = None
        self.previous_counter = None

    def observe(self, record: Record, time_us: int) -> None:
        if record.flags != ARCHIVED_FLAGS or len(record.payload) != 8:
            self.excluded += 1
            self.reset_comparison()
            return
        self.accepted += 1
        if self.previous_time_us is not None:
            self.gaps[time_us - self.previous_time_us] += 1
        self.previous_time_us = time_us
        if record.can_id != "1AE":
            return
        fields = parse_1ae_payload(record.payload)
        if not fields.checksum_matches:
            self.checksum_errors += 1
            self.previous_counter = None
            return
        counter = fields.counter_low_three_bits
        if fields.flag_fd18_4:
            wrong_counter = (
                self.previous_counter is not None and fields.counter_delta(self.previous_counter) != 1
            )
        else:
            wrong_counter = counter != 0
        if wrong_counter:
            self.counter_errors += 1
        self.previous_counter = counter

    def report(self, can_id: str) -> dict:
        report = {
            "accepted_frames": self.accepted,
            "excluded_frames": self.excluded,
            "intervals": sum(self.gaps.values()),
            "min_interval_us": min(self.gaps, default=None),
            "max_interval_us": max(self.gaps, default=None),
        }
        if can_id == "1AE":
            report.update(checksum_errors=self.checksum_errors, counter_errors=self.counter_errors)
        return report


@dataclass
class Stream:
    counts: Counter[str] = field(default_factory=Counter)
    flags: set[tuple[int, int]] = field(default_factory=set)
    periodic: dict[str, PeriodicFrames] = field(
        default_factory=lambda: {can_id: PeriodicFrames() for can_id in PERIODIC_IDS}
    )
    previous_raw_us: int | None = None
    wraps: int = 0
    discontinuities: int = 0

    def observe(self, record: Record, minute_wrap: bool) -> None:
        if minute_wrap and record.time_us >= MINUTE_US:
            raise ValueError("Для --minute-wrap метки должны быть меньше 60 секунд")
        if self.previous_raw_us is not None and record.time_us < self.previous_raw_us:
            if minute_wrap:
                self.wraps += 1
            else:
                self.discontinuities += 1
                for frames in self.periodic.values():
                    frames.reset_comparison()
        self.previous_raw_us = record.time_us
        self.counts[record.can_id] += 1
        self.flags.add(record.flags)
        if record.can_id in self.periodic:
            self.periodic[record.can_id].observe(record, record.time_us + self.wraps * MINUTE_US)

    def report(self) -> dict:
        return {
            "counts": dict(self.counts),
            "flag_pairs": [[f"{value:08X}" for value in pair] for pair in sorted(self.flags)],
            "minute_wraps": self.wraps,
            "timestamp_discontinuities": self.discontinuities,
            "periodic": {can_id: frames.report(can_id) for can_id, frames in self.periodic.items()},
        }


def read_streams(raw: bytes, minute_wrap: bool) -> dict[str, Stream]:
    lines = raw.removeprefix(b"\xef\xbb\xbf").splitlines()
    if not lines or re.match(rb"\s*@\s*TEXT\s*@\s*3\s*@", lines[0]) is None:
        raise ValueError("Ожидается заголовок CANHacker TEXT v3")
    streams: dict[str, Stream] = {}
    for line_number, line in enumerate(lines[1:], start=2):
        if not line.strip() or line.lstrip().startswith(b"#"):
            continue
        try:
            record = parse_record(line.decode("latin-1"))
            if record.stream not in streams:
                streams[record.stream] = Stream()
            streams[record.stream].observe(record, minute_wrap)
        except ValueError as exc:
            raise ValueError(f"Строка {line_number}: {exc}") from exc
    if not streams:
        raise ValueError("В журнале нет записей CAN")
    return streams


def check_interval(stream: Stream, can_id: str, minimum_us: int, maximum_us: int) -> dict:
    frames = stream.periodic[can_id]
    out_of_bounds = sum(
        count for gap, count in frames.gaps.items() if not minimum_us <= gap <= maximum_us
    )
    problems = []
    if not frames.gaps:
        problems.append("no_intervals")
    if frames.excluded:
        problems.append("excluded_records")
    if stream.discontinuities:
        problems.append("timestamp_discontinuity")
    if out_of_bounds:
        problems.append("interval_out_of_bounds")
    if frames.checksum_errors:
        problems.append("checksum_error")
    if frames.counter_errors:
        problems.append("counter_error")
    return {
        "limits_us": [minimum_us, maximum_us],
        "intervals_out_of_bounds": out_of_bounds,
        "problems": problems,
        "pass": not problems,
    }


def interval_argument(value: str) -> tuple[str, int, int]:
    limit = re.fullmatch(r"(?:0x)?([0-9a-f]{1,3}):([0-9]+):([0-9]+)", value, re.IGNORECASE)
    if limit is None:
        raise argparse.ArgumentTypeError("Ожидается ID:MIN_US:MAX_US, например 1AE:9000:11000")
    can_id = limit[1].upper().zfill(3)
    minimum_us, maximum_us = int(limit[2]), int(limit[3])
    if can_id not in PERIODIC_IDS or minimum_us > maximum_us:
        raise argparse.ArgumentTypeError("Допустимые ID: 0FA, 278, 1AE и 300. MIN_US <= MAX_US")
    return can_id, minimum_us, maximum_us


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path, help="Исходный файл TRC")
    parser.add_argument("--stream", help="Номер потока TRC для проверки по допускам")
    parser.add_argument("--minute-wrap", action="store_true", help="Подтверждён минутный счётчик без рестартов записи")
    parser.add_argument("--interval", action="append", type=interval_argument, default=[],
                        metavar="ID:MIN_US:MAX_US", help="Включительные границы в микросекундах")
    args = parser.parse_args(argv)
    if args.interval and args.stream is None:
        parser.error("Для проверки интервалов укажите --stream")
    limits = {can_id: (lo, hi) for can_id, lo, hi in args.interval}
    if len(limits) != len(args.interval):
        parser.error("Для каждого ID допускается одна пара границ")

    try:
        raw = args.trace.read_bytes()
        streams = read_streams(raw, args.minute_wrap)
    except (OSError, ValueError) as exc:
        parser.error(f"{args.trace}: {exc}")
    if args.stream is not None and args.stream not in streams:
        parser.error(f"Поток {args.stream} отсутствует, доступны: {', '.join(streams)}")

    checks = {
        can_id: check_interval(streams[args.stream], can_id, *limit)
        for can_id, limit in limits.items()
    }
    passed = all(check["pass"] for check in checks.values())
    verdict = "OBSERVED_OFFLINE_ONLY"
    if checks:
        verdict = "PERIODIC_CHECKS_PASS" if passed else "PERIODIC_CHECKS_FAIL"
    report = {
        "trace_sha256": hashlib.sha256(raw).hexdigest(),
        "minute_wrap_enabled": args.minute_wrap,
        "streams": {name: stream.report() for name, stream in streams.items()},
        "checked_stream": args.stream if checks else None,
        "interval_checks": checks,
        "verdict": verdict,
        "hardware_verified": False,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
