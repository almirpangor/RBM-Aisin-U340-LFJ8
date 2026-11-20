"""Audit H03 timing and generate its sensor config from supplied calibration evidence."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
from struct import unpack_from
import sys

from check_h03_link import ROOT, identify_h03

sys.path.insert(0, str(ROOT))
from tools.check_vss_measurements import UINT16_MAX, evaluate_clock, integer


# Instruction bundles, excluding the constants they load. A literal's role
# follows from the producer and its consumer, not just a matching bit pattern.
STOCK_SITES = {
    "prescaler": (0x009E78, "e4800202602720046109440121044078"),
    "capture_clock_selection": (0x00A86C, "e48003eb60012004e5800feb61312105"),
    "s51_reload": (0x034A80, "e401719420c4f000e5804ec4204528ef"),
    "s51_decay": (0x03B670, "e4804ec420c4f000e580503c21c5f000feff4ec51189f000feffe263e4804ec420442ac4"),
    "s83_reload": (0x034AB8, "e401703c21c42146"),
    "s83_capture_divider": (0x034AC0, "e48061da21a4f000b0d1002762072224"),
    "s83_diagnostic_gate": (0x03BF6C, "e5804ee020c51188feff4d2fb0c00005e48048d420c41188feff4d2bb0d00004"),
    "s83_decay": (0x03BFA0, "e4804ee020c4f000e580503c21c5f000feff4c791188f000feffe017e4804ee02044f000"),
    "atf_an1": (0x040160, "6101f000e0804bc2feff27a3e4804bc220b45006e5804bc420252eef"),
    "atf_consumer": (0x03B134, "e4804bc420b4f000feff5049"),
}
REQUIRED_CLOCK_HZ = 1_000_000
MAX_SERIAL_AGE = (1 << 31) - 1
# One capture timeout limits both the period and the age of its last edge.
CONFIG_FIELDS = {
    "s51_timeout_ticks": (1, MAX_SERIAL_AGE, ("s51_period_ticks", "s51_age_ticks")),
    "s83_timeout_ticks": (1, MAX_SERIAL_AGE, ("s83_period_ticks", "s83_age_ticks")),
    "atf_max_age_us": (1, MAX_SERIAL_AGE, ("atf_age_us",)),
    "max_read_span_ticks": (0, UINT16_MAX, ("read_span_ticks",)),
}


def stock_evidence(base):
    identity = identify_h03(base)
    rom = base.read_bytes()
    if sha256(rom).hexdigest() != identity["sha256"]:
        raise ValueError("H03 changed before the sensor audit")
    sites = {}
    for name, (address, expected) in STOCK_SITES.items():
        expected = bytes.fromhex(expected)
        observed = rom[address:address + len(expected)]
        if observed != expected:
            raise ValueError(f"Unexpected H03 sensor instructions at {address:#08x}: {name}")
        sites[name] = {"address": f"0x{address:06X}", "bytes": observed.hex()}

    return {
        "base": identity,
        "instruction_sites": sites,
        "configured_registers": {"PRS1": 9, "TML0CR": 0x01, "TML1CR": 0x31},
        "required_timer_hz": REQUIRED_CLOCK_HZ,
        "oem_freshness_reload_ms": {
            "S51": {"address": "0x017194", "value": unpack_from(">f", rom, 0x017194)[0]},
            "S83": {"address": "0x01703C", "value": unpack_from(">f", rom, 0x01703C)[0]},
        },
        "oem_s83_interval_update_edges": 8,
        "production_sensor_config": None,
        "flashable_image": None,
    }


def paired_clock_evidence(record):
    if not isinstance(record, dict) or not isinstance(record.get("intervals"), list):
        raise ValueError("Expected a paired clock reference with an intervals array")
    channels = {"tml0": [], "tml1": []}
    for index, interval in enumerate(record["intervals"], start=1):
        if not isinstance(interval, dict) or "elapsed_us" not in interval:
            raise ValueError(f"Interval {index} must include an independent elapsed_us")
        for name, rows in channels.items():
            pair = interval.get(name)
            if not isinstance(pair, list) or len(pair) != 2:
                raise ValueError(f"Interval {index} must include {name} as [start_ticks, end_ticks]")
            rows.append({"start_ticks": pair[0], "end_ticks": pair[1], "elapsed_us": interval["elapsed_us"]})

    clocks = {name: evaluate_clock({"max_error_ppm": record["max_error_ppm"], "intervals": rows},
                                  REQUIRED_CLOCK_HZ) for name, rows in channels.items()}
    return {"passed": all(clock["passed"] for clock in clocks.values()), **clocks}


def calibration_evidence(profile, base_sha256):
    if not isinstance(profile, dict) or profile.get("base_sha256") != base_sha256:
        raise ValueError("Calibration profile must identify the exact H03 base by SHA-256")
    evidence_id = profile.get("evidence_id")
    if not isinstance(evidence_id, str) or not evidence_id.strip():
        raise ValueError("Calibration profile requires a bench record identifier (evidence_id)")
    limits = profile.get("limits")
    observations = profile.get("observed_maxima")
    if not isinstance(limits, dict) or not isinstance(observations, dict):
        raise ValueError("Calibration profile requires limits and observed_maxima objects")

    config = {}
    maxima = {}
    for field, (minimum, maximum, measurements) in CONFIG_FIELDS.items():
        limit = integer(limits, field, minimum, maximum)
        for measurement in measurements:
            observed = integer(observations, measurement, int(measurement.endswith("_period_ticks")), maximum)
            if observed > limit:
                raise ValueError(f"Observed {measurement} ({observed}) exceeds {field} ({limit})")
            maxima[measurement] = observed
        config[field] = limit
    return {"evidence_id": evidence_id.strip(), "limits": config, "observed_maxima": maxima}


def config_source(report):
    fields = report["production_sensor_config"]
    profile_hash = report["calibration_profile"]["sha256"]
    clock_hash = report["clock_reference_sha256"]
    base_hash = report["base"]["sha256"]
    lines = [
        "/* Generated by check_h03_sensor_config.py from supplied calibration data.",
        f" * H03 SHA-256:     {base_hash}",
        f" * Profile SHA-256: {profile_hash}",
        f" * Clocks SHA-256:  {clock_hash}",
        " */",
        '#include "lfj8_h03_sensor_target.h"',
        "",
        "const Lfj8H03SensorFeedConfig rbm_h03_sensor_config = {",
    ]
    for field, value in fields.items():
        width = 16 if field == "max_read_span_ticks" else 32
        lines.append(f"    .{field} = UINT{width}_C({value}),")
    return "\n".join([*lines, "};", ""])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--clock-reference", type=Path)
    parser.add_argument("--calibration-profile", type=Path,
                        help="explicit H03 limits and bench observation maxima")
    parser.add_argument("--emit-config", action="store_true",
                        help="write the qualified C definition to stdout")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.calibration_profile and not args.clock_reference:
        parser.error("--calibration-profile requires --clock-reference")
    if args.emit_config and not args.calibration_profile:
        parser.error("--emit-config requires --calibration-profile")
    inputs = [path for path in (args.base, args.clock_reference, args.calibration_profile) if path is not None]
    if args.out.suffix.lower() != ".json" or any(
            args.out.resolve() == path.resolve() or
            (args.out.exists() and path.exists() and args.out.samefile(path)) for path in inputs):
        parser.error("Use a separate JSON report")
    try:
        report = stock_evidence(args.base)
        reference = None
        if args.clock_reference:
            clock_data = args.clock_reference.read_bytes()
            reference = paired_clock_evidence(json.loads(clock_data.decode("utf-8-sig")))
            if args.calibration_profile:
                report["clock_reference_sha256"] = sha256(clock_data).hexdigest()
        report["clock_reference"] = reference
        report["status"] = ("PASS_STOCK_ONLY" if reference is None else
                            "PASS_RECORDED_CLOCKS" if reference["passed"] else "FAIL_RECORDED_CLOCKS")
        if args.calibration_profile:
            profile_data = args.calibration_profile.read_bytes()
            profile = calibration_evidence(json.loads(profile_data.decode("utf-8-sig")), report["base"]["sha256"])
            report["calibration_profile"] = {**profile, "sha256": sha256(profile_data).hexdigest()}
            report["hardware_verified"] = False
            if reference["passed"]:
                report["production_sensor_config"] = profile["limits"]
                report["status"] = "PASS_CONFIG_INPUTS"
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        if args.emit_config and report["status"] == "PASS_CONFIG_INPUTS":
            sys.stdout.write(config_source(report))
    except (OSError, KeyError, ValueError) as error:
        parser.exit(2, f"{error}\n")
    return int(reference is not None and not reference["passed"])


if __name__ == "__main__":
    sys.exit(main())
