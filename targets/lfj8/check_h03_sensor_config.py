"""Trace H03 sensor timing constants to stock ROM and check paired clock observations."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
from struct import unpack_from
import sys

from check_h03_link import ROOT, identify_h03

sys.path.insert(0, str(ROOT))
from tools.check_vss_measurements import evaluate_clock


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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--clock-reference", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    inputs = [path for path in (args.base, args.clock_reference) if path is not None]
    if args.out.suffix.lower() != ".json" or any(
            args.out.resolve() == path.resolve() or
            (args.out.exists() and path.exists() and args.out.samefile(path)) for path in inputs):
        parser.error("Use a separate JSON report")
    try:
        report = stock_evidence(args.base)
        reference = None
        if args.clock_reference:
            reference = paired_clock_evidence(json.loads(args.clock_reference.read_text(encoding="utf-8")))
        report["clock_reference"] = reference
        report["status"] = ("PASS_STOCK_ONLY" if reference is None else
                            "PASS_RECORDED_CLOCKS" if reference["passed"] else "FAIL_RECORDED_CLOCKS")
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    except (OSError, KeyError, ValueError) as error:
        parser.exit(2, f"{error}\n")
    return int(reference is not None and not reference["passed"])


if __name__ == "__main__":
    sys.exit(main())
