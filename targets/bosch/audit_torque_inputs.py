#!/usr/bin/env python3
"""Compare the Chery donor's two request operands with an isolated E4M3 CAN model."""

import argparse
import json
from pathlib import Path

from build import CAN_ID, S04_SHA, build, digest
from verify import SPEED_PHYS, build_native_model, calls, payload

DONOR_SHA = "99dc271a861ab6d9e6749e8beb4637ab5c6c7e111f3ff0d9df4e147b2a0a6e1c"


def signed_word(word):
    return word if word < 32768 else word - 65536


def decoded_operand(raw):
    numerator = (raw - 50) * 102 * 16384
    result = abs(numerator) // 6375
    return min(32767, -result if numerator < 0 else result)


def verify(engine, base, image, model):
    if digest(base) != S04_SHA:
        raise ValueError("Expected the pinned S04 project image")
    donor = (engine / "build_inputs/CHERY_REFERENCE_DO_NOT_FLASH.bin").read_bytes()
    if digest(donor) != DONOR_SHA:
        raise ValueError("Expected the pinned S02 Chery donor")
    expected, manifest, _, _ = build(engine, base, with_engine_signals_tx=True)
    if image != expected:
        raise ValueError("Expected the reproducible E4M3 transmitter/receiver candidate")

    # The donor stores CPU addresses in a flat file. E4M3 has a packed layout.
    vm = build_native_model(donor, model, packed=False)
    assert vm.rom[0xA819F] == 102

    def execute_pair(first, second):
        vm.reset()
        vm.write(0x8173, first, 1)
        vm.write(0x8172, second, 1)
        vm.run(0x28F02, stop=0x28F92)
        values = [signed_word(vm.read(address)) for address in (0x8C86, 0x8C84)]
        assert values == [decoded_operand(raw) for raw in (first, second)]
        return values

    # A bijection on bytes varies each channel across its entire range.
    for first in range(256):
        execute_pair(first, (59 * first + 17) & 255)

    from audit_machine import Machine
    from test_can_diag import start
    from torque_patch import EPOCH, MODE, RED

    ecu = Machine(image)
    ecu.native_writes.add(SPEED_PHYS)
    start(ecu)
    calls(ecu, 8)
    ecu.poke(0xF7C4, 4800)
    ecu.poke(0xFD18, 0x40)
    ecu.poke(0xFF44, 0x46)
    vectors = []
    for values in ((40, 60), (50, 50), (60, 40), (255, 50)):
        frame = payload(6000, operand1=values[0], operand4=values[1])
        ecu.poke(SPEED_PHYS, 0)
        before = [ecu.get(address) for address in (MODE, RED, EPOCH)]
        assert ecu.inject(CAN_ID, frame)
        calls(ecu, 10)
        speed_q7 = ecu.get(SPEED_PHYS)
        assert speed_q7 == 7680
        after = [ecu.get(address) for address in (MODE, RED, EPOCH)]
        assert before == after == [0, 0, 0]
        vectors.append({
            "frame_hex": frame.hex(),
            "chery_raw_operands": list(values),
            "chery_arithmetic_results": execute_pair(*values),
            "chery_reserved_fields": [value == 255 for value in values],
            "e4m3_speed_q7": speed_q7,
            "e4m3_request_mode_reduction_generation": after,
        })
    return {
        "status": "PASS_OFFLINE_READ_ONLY",
        "s02_sha256": DONOR_SHA,
        "e4m3_candidate_sha256": manifest["sha256"],
        "donor_pairs_executed": 256,
        "vectors": vectors,
        "chery_qualification_not_executed_by_this_audit": True,
        "common_physical_request_units_proven": False,
        "torque_output_implemented_by_candidate": False,
        "hardware_tested": False,
    }


def main():
    if not __debug__:
        raise RuntimeError("Enable Python assertions for original-instruction verification")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", required=True, type=Path)
    parser.add_argument("--s04", required=True, type=Path)
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--c167", required=True, type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = verify(args.engine.resolve(), args.s04.read_bytes(), args.image.read_bytes(), args.c167)
    text = json.dumps(report, indent=2) + "\n"
    if args.report:
        with args.report.open("x", encoding="utf-8") as output:
            output.write(text)
    print(text, end="")


if __name__ == "__main__":
    main()
