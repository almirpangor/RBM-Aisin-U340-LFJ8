"""Verify the explicit no-cruise E4M3 field against S02 and the assembled CAN sender."""

import argparse
import json
from itertools import product
from pathlib import Path

from audit_torque_inputs import DONOR_SHA
from build import build, digest
from verify import SPEED_PHYS, build_native_model, calls
from verify_tx import verify_transmitter


def verify_mode_guard(chery, gw):
    anchors = (
        (chery, 0x05B3DC, "f2f4e49842f47c928d03f2f4e4980d02f2f47c92f6f43699"),
        (chery, 0x05B40A, "8a350460c2f4de8268422d02"),
        (gw, 0x05A078, "f2f49a9642f4e6988d03f2f49a960d02f2f4e698f6f4ec96"),
        (gw, 0x05A0A6, "8a3303708a3e0140"),
        (gw, 0x0C9CFC, "f68ee6984e3e"),
    )
    for vm, pc, encoded in anchors:
        code = bytes.fromhex(encoded)
        assert bytes(vm.rom[pc + i] for i in range(len(code))) == code

    for vm, start, source, output in (
        (chery, 0x042E7A, 0x91C0, 0x91C4), (gw, 0x0434E8, 0x8FAA, 0x8FAE),
    ):
        for word in (0, 1, 65534, 65535):
            vm.reset()
            vm.write(source, word)
            vm.run(start, stop=start + 8)
            assert vm.read(output) == word

    cases = 0
    for prior, guard, mode, load in product(
        (0, 1), (0, 1), (65534, 65535), (0, 851, 852, 853, 867, 868, 65535)
    ):
        chery.reset()
        for address, value in ((0xFD36, prior << 2), (0xFD3C, guard << 10),
                               (0x91C4, mode), (0x91BC, load)):
            chery.write(address, value)
        chery.run(0x0C1ED4, stop=0x0C1F04)
        expected = not (guard or mode < 65535 or load <= 852) and (load >= 868 or prior)
        assert bool(chery.read(0xFD36) & 4) == bool(expected), (prior, guard, mode, load)
        cases += 1
    return cases


def compare_words(chery, candidate, start, stop):
    for value in range(65536):
        # Both single-fault states are admissible, as is the fault-free state.
        fault_a, fault_b = ((0, 0), (1, 0), (0, 1))[value % 3]
        chery.reset()
        for address, word in ((0x91C2, value), (0xB280, fault_a), (0xB282, fault_b), (0xFD36, 0)):
            chery.write(address, word)
        chery.mem.update({0xF4630: 0, 0xF4631: 0})
        chery.run(0x0A20F4, stop=0x0A2186)
        native = chery.read(0x85B1, 1)

        candidate.reset()
        candidate.sp = 0xFC00  # Keep the synthetic return address away from FD7C.
        candidate.write(0xEF1E, 0xC012)
        lower_byte = value & 255
        candidate.write(0xEF20, 0xFF00 | lower_byte)
        for address, word in ((0x8FAC, value), (0xB286, fault_a), (0xB288, fault_b),
                              (0x98E6, 0), (0xFD7C, 0), (0x8FAE, 10000)):
            candidate.write(address, word)
        candidate.md = [0xA55A, 0x5AA5]
        candidate.r[9] = 0xBCDE
        candidate.run(start, stop=stop)
        packed = candidate.read(0xEF20)
        assert packed == (native << 8) | lower_byte, (value, native, packed)
        assert candidate.md == [0xA55A, 0x5AA5] and candidate.r[9] == 0xBCDE
    return 65536


def verify_wire(image, symbols):
    from audit_machine import Machine
    from test_can_diag import start

    machine = Machine(image)
    machine.native_writes.add(SPEED_PHYS)
    start(machine)
    calls(machine, 8)
    for address, value in (
        (0xFF44, 0x46), (0xFD18, 0x40), (0xFD1A, 0), (0xF7C4, 4800),
        (0xF16FC, 40000), (0xF1680, 16000), (0xF165A, 8000), (0xF325A, 0), (0xF32B0, 0),
        (0xF0FAC, 30000),
    ):
        machine.poke(address, value)

    def transmit():
        for _ in range(50):
            before = len(machine.frames)
            machine.poke(0xFE44, (machine.get(0xFE44) + 125) & 65535)
            machine.run()
            for frame in machine.frames[before:]:
                if frame["id"] == 0x0FA:
                    return bytes.fromhex(frame["data"])
        raise AssertionError("RPM/model frame was not transmitted")

    combinations = 0
    for fault_a, fault_b, request, auxiliary, rpm_ready, mode_uncertain in product((0, 1), repeat=6):
        for address, value in (
            (0xF3286, 0x8000 | fault_a), (0xF3288, 0x2000 | fault_b), (0xF18E6, request),
            (0xFD7C, 0x40 | (auxiliary << 4)), (0xFD18, rpm_ready << 6),
            (0xF0FAE, 0xFFFF if mode_uncertain else 0xFFFE),
        ):
            machine.poke(address, value)
        blocked = (fault_a and fault_b) or request or auxiliary or not rpm_ready or mode_uncertain
        ordinary = 255 if blocked else 30000 // 257
        rpm = (0x12, 0xC0) if rpm_ready else (0xFF, 0xFF)
        assert transmit() == bytes((*rpm, 95, ordinary, 0, 35, 0, 0))
        combinations += 1

    inputs = {0xF3286: 0, 0xF3288: 0, 0xF18E6: 0, 0xFD7C: 0, 0xF0FAC: 30000, 0xF0FAE: 0xFFFE}
    machine.poke(0xFD18, 0x40)
    recheck = int(symbols["ordinary_model_recheck"], 16)
    for changed in inputs:
        bit = 0x10 if changed == 0xFD7C else 1
        for address, value in inputs.items():
            machine.poke(address, value)

        def change_input(vm, pc):
            if pc == recheck:
                vm.poke(changed, inputs[changed] ^ bit)

        machine.instruction_hook = change_input
        assert transmit() == bytes.fromhex("12c05fff00230000"), hex(changed)
        machine.instruction_hook = None
    for address, value in inputs.items():
        machine.poke(address, value)
    wire = transmit()
    assert wire == bytes.fromhex("12c05f7400230000")
    return combinations, len(inputs), wire


def verify(engine, s04, model, image, compact, *, rb_native_permit=False):
    rebuilt, manifest, _, _ = build(engine, s04, model_fields=True, compact=compact,
                                     ordinary_model_field=True, rb_native_permit=rb_native_permit)
    if image != rebuilt:
        raise ValueError("Expected the exact no-cruise profile rebuild")
    default, _, _, _ = build(engine, s04, model_fields=True, compact=True)
    assert digest(default) == "624d47d74bb19a6bdcf8aa662ec0b4e1361c51d635a9495765f36a6d7f0978f0"
    donor = (engine / "build_inputs/CHERY_REFERENCE_DO_NOT_FLASH.bin").read_bytes()
    if digest(donor) != DONOR_SHA:
        raise ValueError("Expected the pinned S02 reference image")
    symbols = manifest["engine_signals_tx_symbols"]
    chery = build_native_model(donor, model, packed=False)
    candidate = build_native_model(image, model)
    mode_guard = verify_mode_guard(chery, candidate)
    operands = compare_words(chery, candidate, int(symbols["ordinary_model_field"], 16),
                             int(symbols["ordinary_model_done"], 16))
    gates, changes, wire = verify_wire(image, symbols)
    regressions = verify_transmitter(engine, s04, image, compact=compact, model_fields=True,
                                     ordinary_model_field=True, rb_native_permit=rb_native_permit)
    return {
        "status": "PASS_OFFLINE_ONLY",
        "sha256": digest(image),
        "profile": manifest["chery_model_field_3_profile"],
        "native_mode_guard_cases": mode_guard,
        "native_encoder_cases": operands,
        "qualification_wire_cases": gates,
        "changed_input_wire_cases": changes,
        "if1_delay_cases": len(regressions["scenarios"]),
        "checksum_records": manifest["checksum_records"],
        "wire_vectors": [{"can_id": "0x0fa", "payload_hex": wire.hex()}, regressions["wire_vectors"][1]],
        "hardware_tested": False,
    }


def main():
    if not __debug__:
        raise RuntimeError("Enable assertions")
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("engine", "s04", "model", "image"):
        parser.add_argument("--" + arg, type=Path, required=True)
    parser.add_argument("--compact", action="store_true")
    parser.add_argument("--with-rb-native-permit", action="store_true")
    args = parser.parse_args()
    report = verify(args.engine.resolve(), args.s04.read_bytes(), args.model, args.image.read_bytes(),
                    args.compact, rb_native_permit=args.with_rb_native_permit)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
