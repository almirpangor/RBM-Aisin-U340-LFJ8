"""Compare the active R4 CAN sender and diagnostic replies on two native E4M3 snapshots."""

import argparse
from collections import Counter
import json
from pathlib import Path

from audit_toyota_load_inputs import sample_native
from build import build, digest
from verify import SPEED_PHYS, build_native_model, calls


PROFILES = (
    ("pinned_e4m3", {}, {0x5E0, 0x5E1, 0x5E2, 0x5E9}),
    ("model_fields", {"model_fields": True, "compact": True},
     {0x0FA, 0x278, 0x5E0, 0x5E1, 0x5E2, 0x5E9}),
    ("ordinary_model_field", {"model_fields": True, "compact": True, "ordinary_model_field": True},
     {0x0FA, 0x278, 0x5E0, 0x5E1, 0x5E2, 0x5E9}),
)
BASE_RX = {5: 0x7E0, 6: 0x7DF, 11: 0x5E8}
BASE_TX = {1: 0x5E0, 2: 0x5E1, 3: 0x5E2, 4: 0x7E8, 12: 0x5E9}


def snapshot(native, adc, load, denominator, model_base):
    adc_word, pid04 = sample_native(native, adc, load, denominator)
    native.run(0x02D808, stop=0x02D818)
    pid11 = native.mem[0xF40A3]
    return {"adc_word": adc_word, "load_f8d6": load, "denominator_f4686": denominator,
            "model_base_9680": model_base, "pid04": pid04, "pid11": pid11}


def run_sender(image, inputs, mode01, use_model_fields, ordinary):
    from audit_machine import Machine
    from test_can_diag import query, start

    machine = Machine(image)
    machine.native_writes.add(SPEED_PHYS)
    start(machine)
    calls(machine, 8)
    rx, tx = {}, {}
    for slot, obj in enumerate(machine.objects, 1):
        arb = obj["arb2"]
        if arb & 0x8000:
            assert not arb & 0x4000
            (tx if arb & 0x2000 else rx)[slot] = (arb >> 2) & 0x7FF
    if use_model_fields:
        assert rx == BASE_RX | {13: 0x1AE}
        assert tx == BASE_TX | {14: 0x0FA, 15: 0x278}
    else:
        assert rx == BASE_RX and tx == BASE_TX

    base = inputs["model_base_9680"]
    for address, value in (
        (0xFF44, 0x46), (0xFD18, 0x40), (0xF7C4, 4800), (0xF3286, 0), (0xF3288, 0),
        (0xF0616, inputs["adc_word"]), (0xF8D6, inputs["load_f8d6"]),
        (0xF4686, inputs["denominator_f4686"]), (0xF16FC, base + 24000),
        (0xF1680, base), (0xF165A, base - 8000), (0xF325A, 0), (0xF32B0, 0),
        (0xF0FAC, 30000), (0xF0FAE, 0xFFFE), (0xF18E6, 0), (0xFD7C, 0),
        (0xF0382, 180), (0xF32F4, 0), (0xF0B56, 0x2BDA),
    ):
        machine.poke(address, value)
    for record in mode01:
        pid = int(record["pid"], 16)
        data_address = int(record["data_cpu_address"], 16)
        valid_address = int(record["valid_cpu_address"], 16)
        payload = bytes(record["data_bytes"])
        if pid in (0x04, 0x11):
            payload = bytes((inputs[f"pid{pid:02X}"],))
        for i, byte in enumerate(payload):
            machine.poke(data_address + i, byte, 1)
        machine.poke(valid_address, 1, 1)
    first = len(machine.frames)
    for _ in range(250):
        machine.poke(0xFE44, (machine.get(0xFE44) + 125) & 0xFFFF)
        machine.run()
    periodic = [(f["tick"], f["id"], f["data"]) for f in machine.frames[first:]]
    if use_model_fields:
        payload = "12c05f7400230000" if ordinary else "12c05fff00230000"
        assert any(can_id == 0x0FA and data == payload for _, can_id, data in periodic)
    queries = [(1, pid) for pid in (0, 0x20, *(int(rec["pid"], 16) for rec in mode01))]
    queries += [(0x22, 0xF2, selector) for selector in (*range(7), *range(0x10, 0x1A))]
    messages = {}
    for args in queries:
        reply = query(machine, args, steps=60)
        assert reply is not None
        messages[bytes(args).hex()] = reply.hex()
    assert messages["0104"] == "0341048000000000"
    assert messages["0111"] == "0341111900000000"
    return periodic, messages, rx, tx


def audit(engine, s04, decoder):
    # Reproduction verifies the pinned S04 digest and the original R4 builder.
    build(engine, s04)
    native = build_native_model(s04, decoder)
    first = snapshot(native, 100, 1000, 2000, 16000)
    second = snapshot(native, 101, 2000, 4000, 18000)
    assert first["adc_word"] != second["adc_word"]
    mode01 = json.loads((engine / "tools/native_pids.json").read_text(encoding="utf-8"))
    comparisons = {}
    for name, options, identifiers in PROFILES:
        image = build(engine, s04, **options)[0] if options else s04
        observations = [
            run_sender(image, case, mode01, options.get("model_fields", False),
                       options.get("ordinary_model_field", False))
            for case in (first, second)
        ]
        assert observations[0] == observations[1], name
        frames, messages, rx, tx = observations[0]
        counts = Counter(can_id for _, can_id, _ in frames)
        assert counts.keys() == identifiers, (name, counts)
        first_frames = {}
        for _, can_id, payload in frames:
            first_frames.setdefault(f"0x{can_id:03X}", payload)
        comparisons[name] = {
            "sha256": digest(image),
            "configured_rx": {slot: f"0x{can_id:03X}" for slot, can_id in rx.items()},
            "configured_tx": {slot: f"0x{can_id:03X}" for slot, can_id in tx.items()},
            "periodic_frames_equal": len(frames),
            "first_periodic_frames": first_frames,
            "matched_diagnostic_replies": messages,
        }
    return {
        "status": "SOURCE_AUDIT_OFFLINE_ONLY",
        "scope": "R4 CAN wrapper on two seeded snapshots with the indicated native producers executed",
        "s04_sha256": digest(s04),
        "snapshots": [first, second],
        "profiles": comparisons,
        "equipment_tested": False,
    }


def main():
    if not __debug__:
        raise RuntimeError("Enable assertions")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--s04", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit(args.engine.resolve(), args.s04.read_bytes(), args.model), indent=2))


if __name__ == "__main__":
    main()
