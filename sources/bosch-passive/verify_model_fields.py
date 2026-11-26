"""Compare two E4M3 model publications and the new wire payload with native Chery."""

import argparse
import json
from pathlib import Path
from random import Random

from audit_torque_inputs import DONOR_SHA
from build import build, digest
from verify import SPEED_PHYS, build_native_model, calls
from verify_tx import verify_transmitter


def compare_producers(chery, gw):
    rng = Random(0x9E1C)
    cases = 0
    for value in [0, 1, 32767, 32768, 65534, 65535] + [rng.randrange(65536) for _ in range(128)]:
        gain = rng.randrange(256)
        lower, upper = sorted(rng.sample(range(65536), 2))
        for stage in ("base", "now", "clamp", "difference"):
            outputs = []
            for vm, is_gw in ((chery, False), (gw, True)):
                vm.reset()
                if stage == "base":
                    vm.r[4] = value
                    vm.write(0x967C if is_gw else 0x98C6, upper)
                    start, end, dest = (0x59D94, 0x59DBE, 0x9680) if is_gw else (0x5B0F8, 0x5B122, 0x98CA)
                elif stage == "now":
                    vm.r[4] = value
                    vm.write(0x8459 if is_gw else 0x8428, gain, 1)
                    start, end, dest = (0x5AFA0, 0x5AFCA, 0x96FC) if is_gw else (0x5C302, 0x5C32C, 0x9946)
                elif stage == "clamp":
                    vm.r[7:10] = [upper, lower, value]
                    start, end, dest = (0x59678, 0x596A2, 0x965A) if is_gw else (0x5AA12, 0x5AA3C, 0x98A4)
                else:
                    vm.write(0x9664 if is_gw else 0x98AE, value)
                    vm.write(0x9A20 if is_gw else 0x9C66, upper)
                    start, end, dest = (0x59692, 0x596A2, 0x965A) if is_gw else (0x5AA2C, 0x5AA3C, 0x98A4)
                vm.run(start, stop=end)
                outputs.append(vm.read(dest))
            assert outputs[0] == outputs[1], (stage, value, outputs)
            cases += 1
    return cases


def compare_fault_bits(chery, gw):
    # In both firmwares these adjacent tests send either set fault bit down
    # the same existing ECU error branch. Chery's CAN packer combines them
    # separately below. Exercise each branch of each source ECU.
    for vm, start, fallthrough, fault, first_flag in (
        (chery, 0x389B8, 0x389C8, 0x389F0, 0xB256),
        (gw, 0x39138, 0x39148, 0x39170, 0xB25A),
    ):
        for a in (0x200, 0x201):
            for b in (0x400, 0x401):
                vm.reset()
                vm.write(first_flag, a)
                vm.write(0xB2B0, b)
                vm.run(start, limit=5, stop=fault if (a | b) & 1 else fallthrough)


def unresolved_third_byte(chery):
    results = []
    for word in (0, 25700, 51400):
        chery.reset()
        for addr, value in ((0xB280, 0), (0xB282, 0), (0xFD36, 0), (0x91C2, 10000)):
            chery.write(addr, value)
        chery.mem.update(enumerate(word.to_bytes(2, "little"), 0xF4630))
        chery.run(0xA20F4, stop=0xA2186)
        results.append(chery.read(0x85B1, 1))
    assert results == [38, 100, 200]
    return results


def chery_pair(vm, first, base, second, fault_a, fault_b):
    vm.reset()
    for addr, value in ((0x9946, first), (0x98CA, base), (0x98A4, second),
                        (0xB256, fault_a), (0xB2B0, fault_b)):
        vm.write(addr, value)
    if fault_a & fault_b & 1:
        vm.run(0xA2012, stop=0xA20F4)
    else:
        vm.run(0xA2012, stop=0xA206E)
        # The subset lacks MOV [R0],mem. The next MOV/CMP overwrites its flags.
        assert bytes(vm.rom[i] for i in range(0xA206E, 0xA2072)) == bytes.fromhex("8400a498")
        vm.write(vm.r[0], vm.read(0x98A4))
        vm.run(0xA2072, stop=0xA20F4)
    return vm.read(0x85B0, 1), vm.read(0x85B3, 1)


def verify(engine, base_image, model, image):
    rebuilt, manifest, _, _ = build(engine, base_image, model_fields=True, compact=True)
    if image != rebuilt:
        raise ValueError("Expected exact compact model-field candidate")
    donor = (engine / "build_inputs/CHERY_REFERENCE_DO_NOT_FLASH.bin").read_bytes()
    if digest(donor) != DONOR_SHA:
        raise ValueError("Expected S02")
    chery = build_native_model(donor, model, packed=False)
    gw = build_native_model(base_image, model)
    producers = compare_producers(chery, gw)
    compare_fault_bits(chery, gw)
    independent_codes = unresolved_third_byte(chery)

    from audit_machine import Machine
    from test_can_diag import start
    machine = Machine(image)
    machine.native_writes.add(SPEED_PHYS)
    start(machine)
    calls(machine, 8)
    machine.poke(0xFF44, 0x46)
    machine.poke(0xFD18, 0x40)
    machine.poke(0xF7C4, 4800)

    def transmit():
        previous = len(machine.frames)
        for _ in range(50):
            machine.poke(0xFE44, (machine.get(0xFE44) + 125) & 65535)
            machine.run()
            for frame in machine.frames[previous:]:
                if frame["id"] == 0x0FA:
                    return bytes.fromhex(frame["data"])
            previous = len(machine.frames)
        raise AssertionError("RPM/model frame was not transmitted")

    boundaries = {0, 1, 65534, 65535}
    for code in range(1, 125):
        threshold = (code * 65536 + 124) // 125
        boundaries.update((threshold - 1, threshold, threshold + 1))
    vectors = [(value, 0, 65535 - value) for value in sorted(boundaries)]
    vectors += [(0, value, 65535) for value in sorted(boundaries)]
    rng = Random(0x0FA)
    vectors += [tuple(rng.randrange(65536) for _ in range(3)) for _ in range(128)]
    for index, (first, base, second) in enumerate(vectors):
        flags = (index % 3 == 1, index % 3 == 2)
        for addr, value in zip((0xF16FC, 0xF1680, 0xF165A, 0xF325A, 0xF32B0),
                               (first, base, second, *flags)):
            machine.poke(addr, value)
        x, y = chery_pair(chery, first, base, second, *flags)
        assert transmit() == bytes((0x12, 0xC0, x, 255, 0, y, 0, 0)), (index, x, y)
    for addr in (0xF325A, 0xF32B0):
        machine.poke(addr, 1)
    assert chery_pair(chery, 10000, 16000, 19000, 1, 1) == (255, 255)
    assert transmit() == bytes.fromhex("12c0ffff00ff0000")
    machine.poke(0xF325A, 0)
    trigger = int(manifest["engine_signals_tx_symbols"]["model_now_magnitude"], 16)
    def change_base(vm, pc):
        if pc == trigger:
            vm.poke(0xF1680, vm.get(0xF1680) ^ 1)
    machine.instruction_hook = change_base
    assert transmit() == bytes.fromhex("12c0ffff00ff0000")
    machine.instruction_hook = None
    machine.poke(0xFD18, 0)
    x, y = chery_pair(chery, first, machine.get(0xF1680), second, 0, 1)
    assert transmit() == bytes((255, 255, x, 255, 0, y, 0, 0))
    machine.poke(0xFD18, 0x40)
    for addr, value in ((0xF16FC, 40000), (0xF1680, 16000), (0xF165A, 8000)):
        machine.poke(addr, value)
    wire = transmit()
    x, y = chery_pair(chery, 40000, 16000, 8000, 0, 1)
    assert wire == bytes((0x12, 0xC0, x, 255, 0, y, 0, 0))
    regressions = verify_transmitter(engine, base_image, image, compact=True, model_fields=True)
    return {"status": "PASS_OFFLINE_ONLY", "sha256": digest(image), "paired_producer_cases": producers,
            "native_encoder_wire_vectors": len(vectors), "joint_fault": True,
            "changing_base_rejected": True, "invalid_rpm_independent": True,
            "third_byte_independent_native_examples": independent_codes,
            "if1_delay_cases": len(regressions["scenarios"]), "hardware_tested": False,
            "wire_vectors": [{"can_id": "0x0fa", "payload_hex": wire.hex()},
                             regressions["wire_vectors"][1]]}


if __name__ == "__main__":
    if not __debug__:
        raise RuntimeError("Enable assertions")
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("engine", "s04", "model", "image"):
        parser.add_argument("--" + arg, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.engine.resolve(), args.s04.read_bytes(), args.model, args.image.read_bytes()), indent=2))
