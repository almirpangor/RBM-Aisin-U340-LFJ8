"""Check all S01 load writes and reproduce the boundary with pinned Bosch data."""

import argparse
import json
from pathlib import Path
from struct import unpack_from
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "targets/bosch"))
from audit_toyota_load_traces import R1, S01_PATH, S01_SHA, audit, digest, git_blob, read_proof

WRITERS = {
    8270: (0x03338C,), 8272: (0x033388,), 8306: (0x033AAE,),
    8298: (0x03412C,), 8302: (0x034122, 0x034130), 8310: (0x033AC0, 0x033ACA),
    9044: (0x032B00,), 9030: (0x033380,), 9046: (0x033F82,),
    8288: (0x033EEE,), 8330: (0x033EE0,),
}
MODE_WRITERS = (0x051A10, 0x082ECE)
GROUPS = (
    "lower_limit", "raw_load_clamp", "upper_limit_initialization", "additional_limits_initialization",
    "load_source_selection", "load_arbitration_publication",
)


def check_s01(r1, r3):
    rom = git_blob(r1, R1, S01_PATH)
    if digest(rom) != S01_SHA:
        raise ValueError("Unexpected Toyota S01")
    writers = {}
    for field, addresses in WRITERS.items():
        writers[str(field)] = {}
        for addr in addresses:
            opcode, offset = unpack_from("<Hh", rom, addr)
            if opcode & 0x7ff != 0x764 or offset != -field:
                raise ValueError(f"Unexpected store at {addr:#x}")
            writers[str(field)][f"{addr:06x}"] = rom[addr:addr + 4].hex()
    mode = {f"{addr:06x}": rom[addr:addr + 4].hex() for addr in MODE_WRITERS}
    if set(mode.values()) != {"c40f4deb"}:
        raise ValueError("Expected set1 1,-5299[gp] at both mode writers")
    provenance = read_proof(r3, "LOAD_PROVENANCE")
    groups = {}
    for name in GROUPS:
        rows = provenance["toyota_groups"][name]["instructions"]
        for row in rows:
            addr = int(row["address"], 16)
            data = bytes.fromhex(row["bytes"])
            if rom[addr:addr + len(data)] != data:
                raise ValueError(f"Stale ROM listing for {name} at {addr:#x}")
        groups[name] = len(rows)
    upper, fallback = unpack_from("<hh", rom, 0x05CE4)
    # Algebraic witnesses for the independent operands read by the verified
    # instruction groups, separate from the pinned V850 emulator evidence.
    floor = [min(upper, src >> 2) for src in (0, 8000, 65535)]
    # In channel 0, hold the filter output fixed and vary a valid learned zero.
    main = [max(0, 4000 - 4 * zero) for zero in (319, 811)]
    if floor != [0, 2000, 11010] or main != [2724, 756] or fallback != 786:
        raise ValueError("Unexpected S01 arithmetic")
    return {"sha256": S01_SHA, "signed_gp_writers": writers, "mode_set1_writers": mode,
            "matched_listing_instructions": groups, "upper_raw": upper, "fallback_raw": fallback,
            "gp_8306_active_floor_from_8248": {"input": [0, 8000, 65535], "result": floor},
            "gp_9044_at_filter_4000": {"learned_zero": [319, 811], "result": main},
            "inherited_emulator_cases": {
                name: read_proof(r3, name)["cases"] for name in (
                    "LOAD_ACQUISITION_VERIFICATION", "LOAD_ARBITRATION_VERIFICATION", "LOAD_PATH_VERIFICATION")
            },
            "bosch_raw_fields_do_not_include_these_independent_inputs": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("r1", "r3", "r4", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    report = {"s01": check_s01(args.r1, args.r3),
              "pinned_bench_traces": audit(args.r1, args.r3, args.r4),
              "hardware_tested": False, "toyota_mapping_verified": False}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("TOY-02 S01 writers, instruction groups and independent input witnesses PASS")


if __name__ == "__main__":
    main()
