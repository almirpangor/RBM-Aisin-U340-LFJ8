#!/usr/bin/env python3
"""Verify the optional diagnostic transmitter without connecting a CAN bus."""

import argparse
import json
from pathlib import Path

from build import CAN_ID, build
from tx import COOLANT, RPM
from verify import SPEED_PHYS, calls, payload

V3_SHA = "cde5d04fb871043ffcc387d4cb1e7087659745ca0f4b0cf406604fd76facf4b3"


def verify_transmitter(engine, base, candidate, *, compact=False, model_fields=False, ordinary_model_field=False):
    expected, manifest, _, _ = build(engine, base, with_engine_signals_tx=True,
                                    compact=compact, model_fields=model_fields,
                                    ordinary_model_field=ordinary_model_field)
    assert expected == candidate, "Candidate differs from its exact rebuild"
    v3, v3_manifest, _, _ = build(engine, base)
    assert v3_manifest["sha256"] == V3_SHA, "Default speed-only output changed"
    from audit_machine import Machine
    from test_can_diag import query, start

    def initialized(image, delay):
        machine = Machine(image)
        machine.native_writes.add(SPEED_PHYS)
        start(machine)
        calls(machine, 8)
        machine.transfer_delay = delay
        return machine

    def exercise(machine, count, *, speed=False, quantum=125):
        before = len(machine.frames)
        new_speed = payload(6000)
        for index in range(count):
            machine.poke(0xFE44, (machine.get(0xFE44) + quantum) & 65535)
            if speed and index % 12 == 0:
                assert machine.inject(CAN_ID, new_speed)
            machine.run()
        return machine.frames[before:]

    original = initialized(v3, 0)
    new_objects = {RPM.object_number, COOLANT.object_number}
    for number in new_objects:
        assert original.objects[number - 1]["arb2"] == 0, "Original v3 already owns this object"

    reports = []
    for delay in (0, 1, 3):
        machine = initialized(candidate, delay)
        for number, (old, new) in enumerate(zip(original.objects, machine.objects, strict=True), 1):
            if number not in new_objects:
                for field in ("mask1", "mask2", "arb1", "arb2"):
                    assert old[field] == new[field], (number, field)
                assert old["control"] & 0x1C8F == new["control"] & 0x1C8F, number
        for signal in (RPM, COOLANT):
            obj = machine.objects[signal.object_number - 1]
            assert obj["arb2"] == (0xA000 | (signal.identifier << 2))
            assert obj["control"] == 0x88

        machine.poke(0xFF44, 0x46)
        machine.poke(0xFE44, 0xFF00)  # Cross the native 16-bit T4 wrap.
        machine.poke(0xFD18, 0x40)
        machine.poke(0xFD1A, 0)
        machine.poke(0xF7C4, 4800)
        machine.poke(0xF0382, 180, 1)
        machine.poke(0xF32F4, 0)
        if model_fields:
            machine.poke(0xF325A, 1)
            machine.poke(0xF32B0, 1)
        if ordinary_model_field:
            machine.poke(0xF3286, 1)
            machine.poke(0xF3288, 1)
        frames = exercise(machine, 240, speed=True)
        assert machine.get(SPEED_PHYS) == 7680, ("speed RX", delay)
        rpm_frames = [frame["data"] for frame in frames if frame["id"] == RPM.identifier]
        ect_frames = [frame["data"] for frame in frames if frame["id"] == COOLANT.identifier]
        assert len(rpm_frames) >= 4 and set(rpm_frames) == {"12c0ffff00ff0000"}, (delay, rpm_frames)
        assert len(ect_frames) >= 4 and set(ect_frames) == {"b4ffffffffffffff"}, (delay, ect_frames)
        assert {0x5E0, 0x5E1, 0x5E2, 0x5E9} <= {frame["id"] for frame in frames}, delay
        assert query(machine, [1, 0]) == bytes.fromhex("064100be3eb81100")
        machine.poke(0xFD18, 0)
        machine.poke(0xF32F4, 1)
        frames = exercise(machine, 80)
        fault_rpm = [frame["data"] for frame in frames if frame["id"] == RPM.identifier]
        fault_ect = [frame["data"] for frame in frames if frame["id"] == COOLANT.identifier]
        assert fault_rpm and fault_rpm[-1] == "ffffffff00ff0000"
        assert fault_ect and fault_ect[-1] == "ffffffffffffffff"
        assert machine.get(SPEED_PHYS) == 0
        machine.poke(0xFF44, 0)
        frames = exercise(machine, 40)
        # Allow one command already handed to IF1 to finish.
        assert sum(frame["id"] in (RPM.identifier, COOLANT.identifier) for frame in frames) <= 1
        reports.append({
            "if1_delay": delay,
            "rpm_valid_frames": len(rpm_frames),
            "coolant_valid_frames": len(ect_frames),
            "rpm_invalid_vectors": len(fault_rpm),
            "coolant_invalid_vectors": len(fault_ect),
            "speed_received": True,
            "rb_and_obd_observed": True,
            "model_stack_bytes": machine.max_stack,
        })

    original.poke(0xFF44, 0x46)
    frames = exercise(original, 80, speed=True)
    assert original.get(SPEED_PHYS) == 7680
    assert not any(frame["id"] in (RPM.identifier, COOLANT.identifier) for frame in frames)
    assert query(original, [1, 0]) == bytes.fromhex("064100be3eb81100")
    return {
        "status": "PASS_OFFLINE_ONLY",
        "sha256": manifest["sha256"],
        "speed_only_v3_sha256": V3_SHA,
        "checksum_records": manifest["checksum_records"],
        "original_can_object_configurations_preserved": 32 - len(new_objects),
        "wire_vectors": [
            {"can_id": "0x0fa", "payload_hex": rpm_frames[0], "rpm": 1200},
            {"can_id": "0x278", "payload_hex": ect_frames[0], "coolant_celsius": 87},
        ],
        "scenarios": reports,
        "hardware_tested": False,
        "native_producer_execution_in_this_test": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", required=True, type=Path)
    parser.add_argument("--s04", required=True, type=Path)
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()
    report = verify_transmitter(args.engine.resolve(), args.s04.read_bytes(), args.image.read_bytes(),
                                compact=args.compact)
    output = json.dumps(report, indent=2) + "\n"
    if args.report:
        with args.report.open("x", encoding="utf-8") as stream:
            stream.write(output)
    print(output, end="")


if __name__ == "__main__":
    main()
