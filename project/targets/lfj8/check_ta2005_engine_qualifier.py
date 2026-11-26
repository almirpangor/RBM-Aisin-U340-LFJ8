"""Compare the compiled LFJ8 engine qualifier with the pinned S03 instructions."""

import argparse
import hashlib
import json
from pathlib import Path
import random
import subprocess


ROOT = Path(__file__).resolve().parents[2]
R3_COMMIT = "7585de6945b4b6b3ef381c6062070a5f417cf588"
EXECUTOR_PATH = "tools/c167_subset.py"
RPM_EVENT_PC = 0x06E8E0
COOLANT_EVENT_PC = 0x06EDBC


def read_git(repository, revision, path):
    return subprocess.check_output(["git", "-C", str(repository), "show", f"{revision}:{path}"])


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def native_oracle(inputs):
    registry = json.loads((ROOT / "data/sources.json").read_text(encoding="utf-8"))
    source = next(entry for entry in registry["firmware"] if entry["id"] == "S03")
    s03 = read_git(inputs.r1, registry["repositories"]["R1"]["commit"], source["path"])
    if len(s03) != source["bytes"] or sha256(s03) != source["sha256"]:
        raise ValueError("Invalid S03 donor bytes")
    executor = read_git(inputs.r3, R3_COMMIT, EXECUTOR_PATH)
    namespace = {"__name__": "pinned_s03_executor"}
    # Execute the checked-in instruction executor from the pinned local revision.
    exec(compile(executor, EXECUTOR_PATH, "exec"), namespace)
    oracle = namespace["C167"](dict(enumerate(s03, 0x40000)))
    assert tuple(oracle.read(address, 1) for address in (0xAA68, 0xAA7D, 0xAA62, 0xAA8F, 0x335F)) == (
        100, 200, 250, 250, 0xA8
    )
    return oracle, {"s03": source["sha256"], "c167_executor": sha256(executor), "r3_commit": R3_COMMIT}


def seed_oracle(oracle, seed):
    speed, rpm_count, coolant_count, flags = seed
    oracle.reset()
    for address, value, width in (
        (0xFA62, speed, 2), (0xE04C, rpm_count, 1), (0xE020, coolant_count, 1),
        (0xE02A, (0x20 if flags & 1 else 0) | (0x10 if flags & 2 else 0), 1),
        (0xFD16, 4 if flags & 8 else 0, 2), (0xE026, 2 if flags & 4 else 0, 1),
        (0xFD00, 32, 2), (0xF947, 255, 1), (0xFD1C, 0, 2), (0xF83B, 0xA5, 1),
    ):
        oracle.write(address, value, width)


def verify_clear_prefix(oracle):
    """Execute the original reset loop before its unrelated SFR operations."""
    seed_oracle(oracle, (9600, 101, 201, 15))
    oracle.run(0x0652FC, stop=0x065314)
    assert all(oracle.read(address, 1) == 0 for address in (0xE04C, 0xE020, 0xE02A, 0xE026))
    assert oracle.read(0xFA62) == 9600 and oracle.read(0xFD16) == 4
    return {
        "entry": "0x0652FC",
        "stop_before": "0x065314",
        "cleared": ["E04C", "E020", "E02A", "E026"],
        "retained": ["FA62", "FD16.2"],
    }


def evaluate_oracle(oracle, raw_speed, raw_coolant, usable, fd10, fallback, e026, bus, can):
    for address, value, width in (
        (0xFAD8, raw_speed if usable & 1 else 65535, 2),
        (0xF9E9, raw_coolant if usable & 2 else 255, 1),
        (0xFA7B, fallback, 1), (0xFD10, fd10, 2),
        (0xE026, (e026 & 0xFD) | (oracle.read(0xE026, 1) & 2), 1), (0xE02B, bus, 1),
    ):
        oracle.write(address, value, width)
    oracle.mem[oracle.physical(0x335F)] = 0xA0 | (8 if can == 1 else 0)
    oracle.coverage.clear()
    oracle.run(0x06E856)
    oracle.run(0x06ED70)
    assert oracle.r[0] == 0xE600 and oracle.sp == 0xFD80
    e02a = oracle.read(0xE02A, 1)
    e026 = oracle.read(0xE026, 1)
    flags = ((1 if e02a & 0x20 else 0) | (2 if e02a & 0x10 else 0) |
             (4 if e026 & 2 else 0) | (8 if oracle.read(0xFD16) & 4 else 0))
    events = 1 | (2 if RPM_EVENT_PC in oracle.coverage else 0) | (4 if COOLANT_EVENT_PC in oracle.coverage else 0)
    return (events, oracle.read(0xFA62), oracle.read(0xE04C, 1), oracle.read(0xE020, 1), flags,
            oracle.read(0xFD10), oracle.read(0xF9B8, 1), e026, 1)


def compare_program(oracle, test_prefix, test_program):
    randomizer = random.Random(0x6E8566ED70)
    vectors, expected, coverage = [], [], set()

    def verify(seed, speed, coolant, usable, bus, can):
        context = (randomizer.randrange(65536), randomizer.randrange(256), randomizer.randrange(256), bus, can)
        operands = (speed, coolant, usable, *context)
        vectors.append((*seed, *operands))
        outcome = evaluate_oracle(oracle, *operands)
        expected.append(outcome)
        coverage.update(oracle.coverage)
        return outcome

    for count in range(256):
        for latch in range(4):
            for usable in range(4):
                for can in range(2):
                    flags = latch | (count >> 3 & 12)
                    seed = (randomizer.randrange(65536), count, 255 - count, flags)
                    seed_oracle(oracle, seed)
                    bus = (0, 4, 128, 132)[(count + latch + usable) % 4]
                    verify(seed, randomizer.randrange(65535), randomizer.randrange(255), usable, bus, can)
    for _ in range(1024):
        seed = (randomizer.randrange(65536), randomizer.randrange(256), randomizer.randrange(256),
                randomizer.randrange(16))
        seed_oracle(oracle, seed)
        verify(seed, randomizer.choice((65535, randomizer.randrange(65535))),
               randomizer.choice((255, randomizer.randrange(255))),
               randomizer.randrange(4), randomizer.randrange(256), randomizer.randrange(3))
    seed = (7000, 101, 201, 8)
    seed_oracle(oracle, seed)
    assert verify(seed, 65535, 255, 3, 0, 1)[0] == 7
    snapshots = len(vectors)

    for usable in (0, 1, 2):
        seed = (8000, 0, 0, 8)
        seed_oracle(oracle, seed)
        for tick in range(1, 271):
            outcome = verify(seed, 8000, 130, usable, 0, 1)
            assert bool(outcome[0] & 2) == (not (usable & 1) and tick == 102)
            assert bool(outcome[0] & 4) == (not (usable & 2) and tick == 202)
            seed = outcome[1:5]
        for tick in range(1, 253):
            outcome = verify(seed, 8400, 134, 3, 0, 1)
            assert bool(outcome[4] & 1) == (not (usable & 1) and tick < 252)
            assert bool(outcome[4] & 2) == (not (usable & 2) and tick < 252)
            seed = outcome[1:5]

    stdin = "".join(" ".join(map(str, row)) + "\n" for row in vectors)
    result = subprocess.run([*test_prefix, str(test_program), "--native-vectors"], input=stdin, capture_output=True,
                            text=True, check=True, timeout=120)
    outputs = [tuple(map(int, line.split())) for line in result.stdout.splitlines()]
    if len(outputs) != len(expected):
        raise ValueError(f"Expected {len(expected)} vectors, received {len(outputs)}")
    for vector, wanted, received in zip(vectors, expected, outputs):
        if wanted != received:
            raise ValueError(f"Input {vector}: S03 {wanted}, compiled qualifier {received}")
    return {
        "single_snapshot_checks": snapshots, "continuous_steps": len(vectors) - snapshots,
        "rpm_dtc_events": sum(bool(record[0] & 2) for record in expected),
        "coolant_dtc_events": sum(bool(record[0] & 4) for record in expected),
        "oem_machine_instructions_covered": len(coverage),
    }


def main():
    if not __debug__:
        raise RuntimeError("Enable assertions for the equivalence checks")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--r1", type=Path, default=ROOT / ".sources/R1")
    parser.add_argument("--r3", type=Path, default=ROOT / ".sources/R2")
    parser.add_argument("--test", required=True, type=Path, help="Built test_ta2005_engine_qualifier")
    parser.add_argument("--run-with", type=Path, help="Optional runner, e.g. m32r-elf-run")
    args = parser.parse_args()
    oracle, sources = native_oracle(args)
    clear_prefix = verify_clear_prefix(oracle)
    result = compare_program(oracle, [str(args.run_with)] if args.run_with else [], args.test.resolve())
    print(json.dumps({"status": "PASS_OFFLINE_ONLY", "physical_hardware_tested": False,
                      "inputs": sources, **result, "native_diagnostic_clear_prefix": clear_prefix},
                     indent=2))


if __name__ == "__main__":
    main()
