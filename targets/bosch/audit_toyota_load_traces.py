"""Check pinned Toyota load scales and compare available Bosch trace fields."""

import argparse
from collections import Counter, defaultdict
import gzip
import json
from pathlib import Path
import subprocess
import sys

from build import digest
from replay_e4m3_torque import R4, TRACE, TRACE_SHA

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.check_bench_can_trace import ARCHIVED_FLAGS, parse_record


R1 = "8cf4308d8539253d4ac994dd99c9650f02da6236"
R3 = "7585de6945b4b6b3ef381c6062070a5f417cf588"
S01_PATH = "firmware/tcm/toyota-u340e/89663-52f01/4770806_89663-52F01.bin"
S01_SHA = "a3cd723e7e21bf547ca4c17ec49a1e098d203773547dba4d7af21991a2cbead1"
STORES = {9046: 0x033F82, 8288: 0x033EEE, 8330: 0x033EE0}
TRACES = (
    ("development/E4M3/evidence/E4M2_BENCH_20261013/input_trace.trc",
     "7d541499762d5a5aa73e8613722da05eac597773704d6224ef06e45cbb9e4175"),
    (TRACE, TRACE_SHA),
)


def git_blob(repo, revision, path):
    return subprocess.check_output(
        ["git", "--no-replace-objects", "-C", str(repo), "show", f"{revision}:{path}"],
    )


def read_proof(repo, name):
    return json.loads(git_blob(repo, R3, f"research/results/{name}.json"))


def toyota_evidence(r1, r3):
    image = git_blob(r1, R1, S01_PATH)
    if digest(image) != S01_SHA:
        raise ValueError("Unexpected Toyota S01")
    stores = {}
    for offset, address in STORES.items():
        raw = image[address:address + 4]
        opcode = int.from_bytes(raw[:2], "little")
        displacement = int.from_bytes(raw[2:], "little", signed=True)
        if opcode & 0x7FF != 0x764 or displacement != -offset:
            raise ValueError(f"Unexpected halfword store at {address:#08x}")
        stores[f"GP-{offset}"] = {"address": f"{address:#08x}", "bytes": raw.hex()}

    limits = tuple(int.from_bytes(image[at:at + 2], "little") for at in (0x5CE4, 0x5CE6))
    provenance = read_proof(r3, "LOAD_PROVENANCE")
    arithmetic = read_proof(r3, "LOAD_PATH_VERIFICATION")
    arbitration = read_proof(r3, "LOAD_ARBITRATION_VERIFICATION")
    contract = provenance["numeric_contracts"]
    if (limits != (contract["toyota_upper_limit_raw"], contract["toyota_fallback_raw"]) or
            any(proof["toyota_sha256"] != S01_SHA
                for proof in (provenance, arithmetic, arbitration))):
        raise ValueError("Toyota results and ROM do not have the same provenance")
    return {"image_sha256": S01_SHA, "stores": stores, "upper_raw": limits[0],
            "fallback_raw": limits[1], "normalization": contract["toyota_load_code"],
            "arithmetic_cases": arithmetic["cases"], "arbitration_cases": arbitration["cases"],
            "hardware_test": arithmetic["hardware_test"] or arbitration["hardware_test"],
            "gw_mapping_verified": arbitration["gw_mapping_verified"]}


def trace_evidence(repo, path, expected_sha):
    raw = git_blob(repo, R4, path)
    if path.endswith(".gz"):
        raw = gzip.decompress(raw)
    if digest(raw) != expected_sha:
        raise ValueError(f"Unexpected CAN capture {path}")
    counts, operations = Counter(), Counter()
    positive_rpm = []
    groups = defaultdict(list)
    for number, line in enumerate(raw.decode("latin-1").splitlines(), 1):
        if not line.strip() or line.startswith(("@", "#")):
            continue
        record = parse_record(line)
        data = record.payload
        if record.flags != ARCHIVED_FLAGS or len(data) != 8:
            continue
        counts[record.can_id] += 1
        if record.can_id == "5E8" and data[0] == 0xA4:
            operations[data[1]] += 1
        if record.can_id != "5E0" or data[6] & 7 != 7:
            continue
        rpm = int.from_bytes(data[:2], "little")
        if rpm:
            positive_rpm.append(rpm)
            groups[record.stream, rpm, data[2]].append((data[3], number))

    # Same recorded RPM and integer TPS can have different diagnostic load.
    spread, key, low, high = max(
        (max(rows)[0] - min(rows)[0], key, min(rows), max(rows))
        for key, rows in groups.items()
    )
    return {"path": path, "sha256": expected_sha, "frame_counts": dict(sorted(counts.items())),
            "torque_starts": operations[1], "valid_running_samples": len(positive_rpm),
            "rpm_range": [min(positive_rpm), max(positive_rpm)],
            "same_rpm_tps": {"stream": key[0], "rpm": key[1], "tps_percent": key[2],
                             "spread": spread, "load_min_and_line": low, "load_max_and_line": high}}


def audit(r1, r3, r4):
    toyota = toyota_evidence(r1, r3)
    traces = [trace_evidence(r4, path, sha) for path, sha in TRACES]
    duplicate = "firmware/can/rb-bench/input_trace.trc"
    if digest(git_blob(r1, R1, duplicate)) != traces[0]["sha256"]:
        raise ValueError("R1 trace differs from the R4 copy")
    bench_probe = read_proof(r3, "GW_BENCH_DIAGNOSTICS_PROBE")
    if toyota["hardware_test"] or toyota["gw_mapping_verified"] or bench_probe["hardware_tested"]:
        raise ValueError("Evidence provenance changed; review the mapping criteria")
    if any(trace["frame_counts"].get("6B1") for trace in traces):
        raise ValueError("Unexpected raw Bosch diagnostic frames in pinned captures")
    return {"status": "NO_PAIRED_GP_SAMPLES", "toyota_s01": toyota, "bosch_traces": traces,
            "duplicate_trace_in_r1": duplicate, "raw_load_bench_probe": bench_probe["status"],
            "paired_transition_samples": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("r1", "r3", "r4"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit(args.r1, args.r3, args.r4), indent=2))


if __name__ == "__main__":
    main()
