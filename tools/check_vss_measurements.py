"""Check recorded H03 S51 captures and 0x1AE speed against a measured reference."""

import argparse
from fractions import Fraction
import json
from pathlib import Path

from model.chery_1ae import (
    VEHICLE_SPEED_UNAVAILABLE,
    VEHICLE_SPEED_WRAP_RAW,
    encode_1ae_vehicle_speed,
    parse_1ae_payload,
)
from model.u340 import VSS_PULSES_PER_DIFFERENTIAL_REV


CASES = ("moving", "standstill", "signal_loss")
UINT32_MAX = (1 << 32) - 1
UINT16_MAX = (1 << 16) - 1


def integer(record, key, minimum, maximum=None, *, nullable=False):
    value = record[key]
    if nullable and value is None:
        return None
    if type(value) is not int or value < minimum or (maximum is not None and value > maximum):
        bounds = f"{minimum}..{maximum}" if maximum is not None else f">= {minimum}"
        raise ValueError(f"{key} must be an integer {bounds}")
    return value


def evaluate_clock(reference, tick_hz):
    if not isinstance(reference, dict):
        raise ValueError("clock_reference must be an object")
    tolerance = integer(reference, "max_error_ppm", 0)
    intervals = reference["intervals"]
    if not isinstance(intervals, list) or not intervals:
        raise ValueError("clock_reference.intervals must be a nonempty array")

    rows = []
    for index, interval in enumerate(intervals, start=1):
        try:
            if not isinstance(interval, dict):
                raise ValueError("expected an object")
            start = integer(interval, "start_ticks", 0, UINT32_MAX)
            end = integer(interval, "end_ticks", 0, UINT32_MAX)
            elapsed_us = integer(interval, "elapsed_us", 1)
            # Reject durations that could span a full wrap even within tolerance.
            if tick_hz * elapsed_us * (1_000_000 + tolerance) >= (1 << 32) * 10**12:
                raise ValueError("duration could span a full TML0 revolution")
        except (KeyError, ValueError) as error:
            raise ValueError(f"clock_reference interval {index}: {error}") from error

        elapsed_ticks = (end - start) & UINT32_MAX
        measured_hz = Fraction(elapsed_ticks * 1_000_000, elapsed_us)
        error_ppm = abs(measured_hz - tick_hz) * 1_000_000 / tick_hz
        rows.append({
            "elapsed_ticks": elapsed_ticks,
            "measured_hz": str(measured_hz),
            "error_ppm": str(error_ppm),
            "passed": elapsed_ticks > 0 and error_ppm <= tolerance,
        })
    return {
        "expected_hz": tick_hz,
        "max_error_ppm": tolerance,
        "passed": all(row["passed"] for row in rows),
        "intervals": rows,
    }

def evaluate_sample(sample, distance_per_pulse_um, tick_hz, timeout, tolerance):
    if not isinstance(sample, dict):
        raise ValueError("expected an object")
    case = sample["case"]
    if case not in CASES:
        raise ValueError(f"case must be one of {', '.join(CASES)}")
    interval = integer(sample, "interval_ticks", 1, UINT32_MAX, nullable=True)
    age = integer(sample, "age_ticks", 0, UINT32_MAX, nullable=True)
    if interval is not None and age is None:
        raise ValueError("age_ticks is required with interval_ticks")
    stopped = sample["stopped_confirmed"]
    if type(stopped) is not bool:
        raise ValueError("stopped_confirmed must be a boolean")
    encoded = sample["payload_1ae"]
    if not isinstance(encoded, str):
        raise ValueError("payload_1ae must be an eight-byte hex string")
    try:
        frame = parse_1ae_payload(bytes.fromhex(encoded))
    except ValueError as error:
        raise ValueError("payload_1ae must be an eight-byte hex string") from error
    observed = frame.bytes6_7
    reference = Fraction(
        18 * integer(sample, "reference_distance_um", 0),
        5 * integer(sample, "reference_duration_us", 1),
    )

    capture_valid = interval is not None and interval <= timeout and age <= timeout
    estimated = Fraction(0) if stopped else None
    if capture_valid:
        estimated = distance_per_pulse_um * Fraction(18 * tick_hz, 5_000_000 * interval)
    in_range = estimated is not None and estimated * 100 < VEHICLE_SPEED_WRAP_RAW
    raw = encode_1ae_vehicle_speed(estimated if in_range else None)

    error = None
    problems = []
    if not frame.checksum_matches:
        problems.append("observed 0x1AE payload has an invalid checksum")
    if case == "moving":
        if not capture_valid or stopped or reference <= 0 or not in_range:
            problems.append("moving requires fresh in-range capture and positive reference")
        if observed < VEHICLE_SPEED_WRAP_RAW:
            error = abs(Fraction(observed, 100) - reference)
            if error * 100 > tolerance:
                problems.append("speed error exceeds the supplied tolerance")
    elif case == "standstill":
        if capture_valid or not stopped or reference != 0:
            problems.append("standstill requires independent confirmation and zero reference after capture expires")
    elif capture_valid or stopped or reference <= 0:
        problems.append("signal_loss requires unavailable capture, positive reference and no stop confirmation")
    if observed != raw:
        problems.append("observed 0x1AE speed differs from the capture model")

    return {
        "case": case,
        "capture_valid": capture_valid,
        "expected_raw": raw,
        "observed_raw": observed,
        "reference_kmh": str(reference),
        "error_kmh": None if error is None else str(error),
        "problems": problems,
    }


def evaluate(data):
    if not isinstance(data, dict):
        raise ValueError("expected a JSON object")
    profile, samples = data["profile"], data["samples"]
    if not isinstance(profile, dict) or not isinstance(samples, list):
        raise ValueError("profile must be an object and samples an array")
    tick_hz = integer(profile, "tick_hz", 1, UINT32_MAX)
    timeout = integer(profile, "vss_timeout_ticks", 1, UINT32_MAX)
    circumference = integer(profile, "wheel_um", 1, UINT32_MAX)
    ratio = Fraction(integer(profile, "wheel_num", 1, UINT16_MAX),
                     integer(profile, "wheel_den", 1, UINT16_MAX))
    tolerance = integer(profile, "max_error_centi_kmh", 0)
    distance_per_pulse_um = circumference * ratio / VSS_PULSES_PER_DIFFERENTIAL_REV

    rows = []
    for index, sample in enumerate(samples, start=1):
        try:
            rows.append(evaluate_sample(sample, distance_per_pulse_um, tick_hz, timeout, tolerance))
        except (KeyError, ValueError) as error:
            raise ValueError(f"sample {index}: {error}") from error

    missing = [case for case in CASES if not any(row["case"] == case for row in rows)]
    clock = evaluate_clock(data["clock_reference"], tick_hz) if "clock_reference" in data else None
    failed = missing or any(row["problems"] for row in rows) or (clock is not None and not clock["passed"])
    return {
        "status": "FAIL" if failed else "PASS_OFFLINE_ONLY",
        "clock_reference": clock,
        "missing_cases": missing,
        "samples": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("measurements", type=Path, help="JSON with profile and samples")
    args = parser.parse_args()
    try:
        result = evaluate(json.loads(args.measurements.read_text(encoding="utf-8-sig")))
    except (OSError, KeyError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2))
    return int(result["status"] == "FAIL")


if __name__ == "__main__":
    raise SystemExit(main())
