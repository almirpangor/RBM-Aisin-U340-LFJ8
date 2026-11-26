"""Check the third Chery model field against pinned S02 and E4M3 machine code."""

import argparse
import json
from itertools import product
from pathlib import Path
from random import Random

from audit_torque_inputs import DONOR_SHA
from build import S04_SHA, digest
from verify import build_native_model


def original_calls(vm, first, end):
    targets = []
    for address in range(first, end, 4):
        opcode, high, low, middle = (vm.rom[address + i] for i in range(4))
        assert opcode == 0xDA
        targets.append((high << 16) | (middle << 8) | low)
    return targets


def scheduler(chery, gw):
    calls = original_calls(chery, 0x0949D4, 0x0949FC)
    assert calls == [0x03B314, 0x04871E, 0x046EE2, 0x04720E, 0x047450,
                     0x047FFE, 0x046CD2, 0x041846, 0x05D238, 0x03DED4]
    matching = original_calls(gw, 0x094508, 0x094518)
    assert matching == [0x03BA9A, 0x041EB4, 0x05BF32, 0x03E654]
    return {"chery_dispatch": "0x0949D4", "gw_dispatch": "0x094508",
            "chery_calls_between_matching_neighbours": [f"0x{x:06X}" for x in calls[1:7]]}


def inactive_source(chery, gw):
    # Recalculate the original C0/C1 signal even when prior RAM is nonzero.
    for selection, request, enabled in product((0, 3), (0, 1000), (0, 1)):
        chery.reset()
        chery.write(0x82DC, selection, 1)
        chery.write(0x82DE, 0xA5, 1)
        chery.write(0x927C, request)
        chery.run(0x0485F6, stop=0x048616)
        active = bool(selection or request)
        assert chery.read(0x82DE, 1) == (0xA4 | active)
        chery.write(0xFD02, enabled << 12)
        chery.write(0x82D5, 0, 1)
        chery.write(0x923C, 25000)
        chery.write(0x923A, 123)
        chery.run(0x046E60, stop=0x046ED6)
        assert (chery.mem[0xF4630] | chery.mem[0xF4631] << 8) == (25000 if active else 0)
        assert chery.read(0x923A) == (123 if active else 0)
    for prior, step, keep in product((0, 1000, 65000), (1, 3000), (0, 1)):
        gw.reset()
        gw.mem.update(enumerate(prior.to_bytes(2, "little"), 0xF4630))
        gw.write(0x829A, keep << 1, 1)
        gw.write(0xF8D0, step)
        gw.run(0x03A58C, stop=0x03A5B4)
        result = gw.mem[0xF4630] | gw.mem[0xF4631] << 8
        assert result == min(65535, (prior if keep else 0) + step)
    return {"inactive_and_held_chery_cases": 8, "gw_accumulator_cases": 12}


def verify_mode_and_flags(chery, gw):
    for value, chery_mode in product((0, 1), repeat=2):
        chery.reset()
        gw.reset()
        chery.write(0xFD3A, value)
        chery.write(0xFD36, chery_mode << 2)
        gw.write(0xFD34, value << 14)
        gw.write(0xFD36, (1 - value) << 2)
        chery.run(0x041676, stop=0x04167A)
        gw.run(0x041C7A, stop=0x041C7E)
        assert (chery.read(0xFD3A) >> 4) & 1 == value
        assert (gw.read(0xFD36) >> 2) & 1 == value
        assert (chery.read(0xFD36) >> 2) & 1 == chery_mode
    # These four matched loads read the two diagnostic sources into the same
    # stack positions. Source addresses are also event-base plus twice index.
    for vm, site, code, event_base, index, addresses in (
        (chery, 0x042EB8, "840080b2f2f582b2c4500200", 0xB244, 0x1E, (0xB280, 0xB282)),
        (gw, 0x043526, "840086b2f2f588b2c4500200", 0xB252, 0x1A, (0xB286, 0xB288)),
    ):
        data = bytes(vm.rom[site + i] for i in range(12))
        assert data == bytes.fromhex(code)
        assert tuple(int.from_bytes(data[i:i + 2], "little") for i in (2, 6)) == addresses
        assert (event_base + index * 2, event_base + (index + 1) * 2) == addresses
    return {"chery_mode": "FD36.2", "gw_same_address_homolog": "chery FD3A.4",
            "mode_alias_rejected_cases": 4,
            "fault_words": {"chery": ["B280", "B282"], "gw": ["B286", "B288"]}}


def compare_ordinary_operand(chery, gw, rng):
    vectors = list(product((0, 1, 255, 256, 257, 65535), (0, 4, 128, 1020), (0, 1, 254, 255)))
    vectors += [(rng.randrange(65536), 4 * rng.randrange(256), rng.randrange(256)) for _ in range(256)]
    for incoming, cap_q2, calibration in vectors:
        outputs = []
        for vm, start, stop, current, previous, cal in (
            (chery, 0x042B00, 0x042B2E, 0x91C2, 0x91D6, 0x09C1),
            (gw, 0x04316E, 0x04319C, 0x8FAC, 0x8FC0, 0x0A01),
        ):
            vm.reset()
            vm.mem[vm.physical(cal)] = calibration
            vm.r[8:10] = incoming, cap_q2
            vm.write(current, 12345)
            vm.run(start, stop=stop)
            assert vm.read(previous) == 12345
            outputs.append(vm.read(current))
        assert outputs[0] == outputs[1], (incoming, cap_q2, calibration, outputs)
    return {"matched_calibration_and_input_cases": len(vectors), "chery": "91C2", "gw": "8FAC"}


def compare_encoder(chery, rng):
    values = {0, 65534, 65535}
    for n in range(1, 255):
        values.update((257 * n - 1, 257 * n, 257 * n + 1))
    pairs = [(value, 0) for value in sorted(values)] + [(0, value) for value in sorted(values)]
    pairs += [(rng.randrange(65536), rng.randrange(65536)) for _ in range(128)]
    for (cruise, ordinary), mode, fault_a, fault_b in product(pairs, (0, 1), (0, 1), (0, 1)):
        chery.reset()
        for address, value in ((0x91C2, ordinary), (0xB280, fault_a),
                               (0xB282, fault_b), (0xFD36, mode << 2)):
            chery.write(address, value)
        chery.mem.update(enumerate(cruise.to_bytes(2, "little"), 0xF4630))
        chery.run(0x0A20F4, stop=0x0A2186)
        if fault_a and fault_b:
            expected = 255
        elif mode:
            expected = max(254, cruise // 257)
        else:
            expected = min(253, max(ordinary, cruise) // 257)
        assert chery.read(0x85B1, 1) == expected
        assert chery.read(0x8180, 1) == expected
    return len(pairs) * 8


def main():
    if not __debug__:
        raise RuntimeError("Enable assertions")
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("s02", "s04", "model"):
        parser.add_argument("--" + arg, type=Path, required=True)
    args = parser.parse_args()
    s02, s04 = args.s02.read_bytes(), args.s04.read_bytes()
    if digest(s02) != DONOR_SHA or digest(s04) != S04_SHA:
        raise ValueError("Expected the pinned S02 and S04 images")
    chery = build_native_model(s02, args.model, packed=False)
    gw = build_native_model(s04, args.model)
    rng = Random(0x0FA03)
    print(json.dumps({
        "status": "SOURCE_AUDIT_OFFLINE_ONLY",
        "s02_sha256": DONOR_SHA, "s04_sha256": S04_SHA,
        "scheduler": scheduler(chery, gw),
        "physical_0xf4630": inactive_source(chery, gw),
        "mode_and_faults": verify_mode_and_flags(chery, gw),
        "ordinary_operand": compare_ordinary_operand(chery, gw, rng),
        "native_encoder_cases": compare_encoder(chery, rng),
        "open": ["GW owner equivalent to the Chery cruise-dependent word F4630",
                 "GW owner equivalent to the Chery override selector FD36.2"],
        "wire_publication_changed": False,
    }, indent=2))


if __name__ == "__main__":
    main()
