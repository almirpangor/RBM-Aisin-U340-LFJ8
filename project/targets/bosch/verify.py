#!/usr/bin/env python3
"""Execute the emitted Bosch candidate in the upstream ST10/C_CAN model."""
import argparse
import importlib.util
import json
import sys
from pathlib import Path

from build import AGE, CAN_ID, OBJECT, PHASE, RAW_LIMIT, STALE_CALLS, build, digest

SPEED_PHYS = 0xF18FC
PID_ADDRESS = 0xF01E1
VM_SHA = "7de99b47c8c077cc70f38239d4cdd5162b6faee0760f1b6bb93e46c58f7a6ae3"


def payload(raw, operand1=0x32, operand4=0x35, corrupt=False):
    check = (~(operand1 + operand4) & 255) ^ int(corrupt)
    return bytes((check & 15, operand1, 0x13, 0x30 | (check >> 4), operand4, 0)) + raw.to_bytes(2, "big")


def calls(machine, number):
    for _ in range(number):
        machine.run()


def receive(machine, raw, **kwargs):
    assert machine.inject(CAN_ID, payload(raw, **kwargs))
    calls(machine, 8)


def build_native_model(image, path, *, packed=True):
    if digest(path.read_bytes().replace(b"\r\n", b"\n")) != VM_SHA:
        raise ValueError("C167 model must match the pinned R3 source")
    spec = importlib.util.spec_from_file_location("pinned_c167_subset", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if packed:
        rom = {p + (0x10000 if p >= 0x8000 else 0): byte for p, byte in enumerate(image)}
    else:
        rom = {p: byte for p, byte in enumerate(image) if not 0xE000 <= p <= 0xFFFF}
    return module.C167(rom, dpp=(0x2E, 0x2F, 0x3C, 3))


def probe_frame(engine, s04, image, frame, *, compact=False):
    expected, manifest, _, _ = build(engine, s04, compact=compact)
    if len(frame) != 8:
        raise ValueError("Expected one eight-byte 0x1AE frame")
    if image != expected:
        expected, manifest, _, _ = build(engine, s04, with_engine_signals_tx=True, compact=compact)
        if image != expected:
            expected, manifest, _, _ = build(engine, s04, model_fields=True, compact=True)
            if image != expected:
                for ordinary_compact in (True, False):
                    expected, manifest, _, _ = build(engine, s04, model_fields=True, compact=ordinary_compact,
                                                     ordinary_model_field=True)
                    if image == expected:
                        break
                else:
                    raise ValueError("Image differs from the reproducible Bosch candidates")
    from audit_machine import Machine
    from test_can_diag import start

    machine = Machine(image)
    machine.native_writes.add(SPEED_PHYS)
    start(machine)
    calls(machine, 8)
    assert machine.inject(CAN_ID, frame)
    calls(machine, 8)
    return {
        "status": "OFFLINE_ONLY",
        "sha256": manifest["sha256"],
        "frame": frame.hex(),
        "accepted_speed": machine.get(AGE) > 0,
        "speed_q7": machine.get(SPEED_PHYS),
    }


def verify(engine, s04, image, c167, *, compact=False):
    expected, manifest, _, speed = build(engine, s04, compact=compact)
    assert image == expected, "Candidate differs from reproducible build"
    import audit_machine
    import test_can_diag
    import test_torque

    class CandidateMachine(audit_machine.Machine):
        def __init__(self, contents):
            super().__init__(contents)
            self.native_writes.add(SPEED_PHYS)

    original = audit_machine.Machine(s04)
    test_can_diag.start(original)
    assert not original.inject(CAN_ID, payload(6000))
    assert test_can_diag.query(original, [1, 0]) == bytes.fromhex("064100be3eb81100")

    def initialized(delay=0):
        machine = CandidateMachine(image)
        test_can_diag.start(machine)
        calls(machine, 8)
        assert machine.get(SPEED_PHYS) == 0 and machine.get(AGE) == 0
        assert machine.objects[OBJECT - 1]["arb2"] == 0x8000 | (CAN_ID << 2)
        assert machine.objects[OBJECT - 1]["control"] == 0x1088
        machine.transfer_delay = delay
        return machine

    execution_counts = {"division_boundaries": 0, "can_frame_paths": 0, "native_speed_pid": 0}
    machine = initialized()
    # Feed the same staging word the just-read C_CAN object presents. Stop
    # before the far return so its caller state is irrelevant in this slice.
    for raw in range(0, RAW_LIMIT, 25):
        for value in (raw, raw + 24):
            machine.reg[4] = value
            machine.run(speed.labels["division"], stop=speed.labels["owned"])
            assert machine.get(SPEED_PHYS) == (value // 25) << 5, value
            execution_counts["division_boundaries"] += 1

    for delay in (0, 1, 3):
        machine = initialized(delay)
        for raw in (0, 99, 100, 5937, 6000, 20005, 29661, 51199):
            receive(machine, raw, operand1=0xC1, operand4=0x93)
            assert machine.get(SPEED_PHYS) == (raw // 25) << 5, (delay, raw)
            execution_counts["can_frame_paths"] += 1
        for raw in (RAW_LIMIT, 65535):
            receive(machine, raw)
            assert machine.get(SPEED_PHYS) == 0 and machine.get(AGE) == 0
            execution_counts["can_frame_paths"] += 1
        receive(machine, 6000)
        assert machine.get(SPEED_PHYS) == 7680
        receive(machine, 9000, corrupt=True)
        assert machine.get(SPEED_PHYS) == 7680
        execution_counts["can_frame_paths"] += 1
        assert not machine.inject(CAN_ID, payload(9000), extended=True)
        assert not machine.inject(CAN_ID, payload(9000), remote=True)
        assert not machine.inject(CAN_ID - 1, payload(9000))
        assert machine.inject(CAN_ID, payload(9000), dlc=7)
        calls(machine, 10)
        assert machine.get(SPEED_PHYS) == 7680
        execution_counts["can_frame_paths"] += 1
        calls(machine, machine.get(AGE) - 1)
        assert machine.get(SPEED_PHYS) == 7680
        calls(machine, 1)
        assert machine.get(SPEED_PHYS) == 0 and machine.get(AGE) == 0
        receive(machine, 6000)
        machine.poke(0xEF02, 0x80)
        calls(machine, 1)
        assert machine.get(SPEED_PHYS) == 0 and machine.get(PHASE) == 0

    machine = initialized()
    assert machine.inject(CAN_ID, payload(6000))
    assert machine.inject(CAN_ID, payload(9000))
    calls(machine, 12)
    assert machine.get(SPEED_PHYS) == 0, "Ambiguous overwritten frame was used"
    receive(machine, 6000)
    assert machine.get(SPEED_PHYS) == 7680
    assert any(frame["id"] in (0x5E0, 0x5E9) for frame in machine.frames)
    assert test_can_diag.query(machine, [1, 0]) == bytes.fromhex("064100be3eb81100")

    machine = initialized()
    receive(machine, 1)
    assert machine.get(SPEED_PHYS) == 0 and 0 < machine.get(AGE) <= STALE_CALLS
    machine.transfer_delay = 80
    assert machine.inject(CAN_ID, payload(6000))
    calls(machine, 1)
    assert machine.get(PHASE) == 1
    calls(machine, 50)
    assert machine.get(0xEF00) & 1
    calls(machine, 1)
    assert machine.get(PHASE) == machine.get(AGE) == machine.get(SPEED_PHYS) == 0

    machine = initialized()
    native = build_native_model(image, c167)
    for raw in (0, 100, 6000, 25599, 29661):
        receive(machine, raw)
        native.reset()
        q7 = machine.get(SPEED_PHYS)
        native.write(0x98FC, q7)
        native.write(0x80B9, 0, 1)
        native.write(0xFD00, 0x100)
        native.write(0x86C4, q7)  # Start at equilibrium so a slope is not mistaken for scale.
        native.run(0x24AF2, stop=0x24DA2)
        assert native.read(0x86C6) == native.read(0x86C4) == q7
        native.run(0x2D622)
        machine.poke(PID_ADDRESS, native.read(0x81E1, 1), 1)
        machine.poke(PID_ADDRESS + 1, native.read(0x81E2, 1), 1)
        assert test_can_diag.query(machine, [1, 0x0D]) == bytes((3, 0x41, 0x0D, min(raw // 100, 255), 0, 0, 0, 0))
        execution_counts["native_speed_pid"] += 1

    # Reuse the upstream machine-code torque probes against the new image.
    test_torque.IMAGE = image
    test_torque.Machine = CandidateMachine
    test_torque.unit_tests()
    test_torque.protocol_tests()
    return {
        "status": "PASS_OFFLINE_ONLY",
        "sha256": manifest["sha256"],
        "checksum_records": manifest["checksum_records"],
        "coverage": execution_counts,
        "torque_regressions": test_torque.RESULT,
        "capabilities": ["standard CAN frame receive", "native speed and OBD path", "timeouts", "bus-off reset"],
        "physical_ecu_tested": False,
        "panel_output_tested": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", required=True, type=Path)
    parser.add_argument("--s04", required=True, type=Path)
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--c167", type=Path)
    parser.add_argument("--frame", help="Exercise one eight-byte 0x1AE payload in the register model")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()
    inputs = (args.engine.resolve(), args.s04.read_bytes(), args.image.read_bytes())
    if args.frame is not None:
        report = probe_frame(*inputs, bytes.fromhex(args.frame), compact=args.compact)
    elif args.c167 is not None:
        report = verify(*inputs, args.c167, compact=args.compact)
    else:
        parser.error("Provide --c167 for the suite or --frame for a single-frame probe")
    output = json.dumps(report, indent=2) + "\n"
    if args.report:
        with args.report.open("x", encoding="utf-8") as stream:
            stream.write(output)
    print(output, end="")


if __name__ == "__main__":
    main()
