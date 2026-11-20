"""Audit which engine model operands are discarded by the current CAN publisher."""

import argparse
import json
from pathlib import Path

from build import S04_SHA, build, digest
from verify import SPEED_PHYS, build_native_model, calls

REV8_SHA = "2e1621c4329661f3b6991cf540aea188497fff2a88e32e4eaa6a172b6d7360a0"

WINDOWS = (
    ("raw_throttle_adc_pair", 0x020D48, 0x020D64),
    ("primary_diagnostic_throttle", 0x02D808, 0x02D818),
    ("secondary_diagnostic_throttle", 0x02D842, 0x02D86C),
    ("primary_relative_throttle", 0x041722, 0x041768),
    ("secondary_relative_throttle", 0x041816, 0x041856),
    ("model_load_publication", 0x048928, 0x04894E),
    ("pid04_denominator", 0x049026, 0x0490A0),
    ("pid04_publication", 0x0490AC, 0x049190),
    ("pid04_arithmetic", 0x0249EA, 0x024A0A),
    ("relative_throttle_gain", 0x0C08C0, 0x0C08D2),
    ("relative_throttle_calibration", 0x0BB5B8, 0x0BB5F0),
    ("model_limit_publication", 0x0C76EE, 0x0C7722),
)


def matching_windows(rev8, s04):
    result = []
    for name, start, end in WINDOWS:
        # In these packed ROM blocks, the file offset is CPU address - 0x10000.
        area = slice(start - 0x10000, end - 0x10000)
        assert rev8[area] == s04[area], name
        result.append({"name": name, "cpu_start": f"0x{start:06X}",
                       "cpu_end_exclusive": f"0x{end:06X}", "sha256": digest(s04[area])})
    return result


def relative_throttle_cases(native):
    native.run(0x0C08C0, stop=0x0C08D2)
    gain = native.read(0x8F44)
    assert gain == 43733
    vectors = ((400, 200, 266), (400, 300, 133), (400, 500, -134), (404, 204, 266))
    for adc_word, learned_zero, expected in vectors:
        native.reset()
        for address, word in ((0x8616, adc_word), (0x8F56, learned_zero), (0x8F44, gain)):
            native.write(address, word)
        native.run(0x041722)
        assert native.read(0xF85C) == expected & 0xFFFF
    return {"gain": gain, "cases": [
        {"adc_word_8616": adc, "learned_zero_8f56": zero, "relative_throttle_f85c": result}
        for adc, zero, result in vectors
    ]}


def sample_native(native, adc, load, denominator):
    native.reset()
    native.write(0xFBE6, adc)
    native.write(0xFBE2, adc)
    native.run(0x020D48, stop=0x020D64)
    native.write(0x90F6, load // 2)
    native.write(0x9156, load - load // 2)
    native.run(0x048928, stop=0x04894E)
    native.write(0xF7C2, 1, 1)
    native.mem.update(enumerate(denominator.to_bytes(2, "little"), 0xF4686))
    native.run(0x0490AC, stop=0x049142)
    assert native.read(0x8616) == adc * 4
    assert native.read(0xF8D6) == load
    assert native.mem[0xF4195] == load * 256 // denominator
    return native.read(0x8616), native.mem[0xF4195]


def transmitted_frames(image, adc_word, load, denominator, model_base):
    from audit_machine import Machine
    from test_can_diag import start

    machine = Machine(image)
    machine.native_writes.add(SPEED_PHYS)
    start(machine)
    calls(machine, 8)
    # The paired Chery differences remain +24000 and -8000 as base changes.
    for address, value in (
        (0xFF44, 0x46), (0xFD18, 0x40), (0xF7C4, 4800),
        (0xF16FC, model_base + 24000), (0xF1680, model_base), (0xF165A, model_base - 8000),
        (0xF325A, 0), (0xF32B0, 0), (0xF0616, adc_word),
        (0xF8D6, load), (0xF4686, denominator),
        (0xF0FAC, 30000), (0xF0FAE, 0xFFFE),
        (0xF18E6, 0), (0xFD7C, 0), (0xF3286, 0), (0xF3288, 0),
    ):
        machine.poke(address, value)
    machine.poke(0xF7C2, 1, 1)
    seen = {}
    for _ in range(175):
        previous = len(machine.frames)
        machine.poke(0xFE44, (machine.get(0xFE44) + 125) & 0xFFFF)
        machine.run()
        for frame in machine.frames[previous:]:
            if frame["id"] in (0x0FA, 0x5E0):
                seen.setdefault(f"0x{frame['id']:03X}", frame["data"])
        if len(seen) == 2:
            return seen
    raise AssertionError("Candidate did not publish both CAN frames")


def audit(engine, rev8, s04, model, image):
    if (digest(rev8), digest(s04)) != (REV8_SHA, S04_SHA):
        raise ValueError("Expected the pinned REV8 and S04")
    for ordinary in (False, True):
        rebuilt, manifest, _, _ = build(engine, s04, model_fields=True, compact=True,
                                         ordinary_model_field=ordinary)
        if rebuilt == image:
            break
    else:
        raise ValueError("Compact offline image does not match either exact profile")
    native = build_native_model(s04, model)
    rows = []
    for adc, load, denominator, model_base in (
        (100, 1000, 2000, 16000), (101, 2000, 4000, 18000), (500, 2000, 4000, 18000),
    ):
        adc_word, pid04 = sample_native(native, adc, load, denominator)
        frames = transmitted_frames(image, adc_word, load, denominator, model_base)
        rows.append({"adc_code": adc, "gw_load_f8d6": load, "gw_denominator_f4686": denominator,
                     "pid04": pid04, "gw_base_9680": model_base, "frames": frames})
    expected_chery = "12c05f7400230000" if ordinary else "12c05fff00230000"
    assert rows[0]["frames"] == rows[1]["frames"] == {"0x0FA": expected_chery, "0x5E0": "b004093200000701"}
    assert rows[2]["frames"] == {"0x0FA": expected_chery, "0x5E0": "b004313200000701"}
    return {
        "status": "SOURCE_AUDIT_OFFLINE_ONLY",
        "rev8_sha256": REV8_SHA, "s04_sha256": S04_SHA, "image_sha256": manifest["sha256"],
        "matching_rev8_and_e4m3_windows": matching_windows(rev8, s04),
        "relative_throttle": relative_throttle_cases(build_native_model(s04, model)),
        "can_cases": rows,
        "scope": "Original instruction slices and compact CAN publication on seeded RAM snapshots.",
        "physical_trajectory_verified": False,
        "toyota_load_mapping_verified": False,
        "output_authorization": False,
    }


def main():
    if not __debug__:
        raise RuntimeError("Enable assertions")
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("engine", "rev8", "s04", "model", "image"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.engine.resolve(), args.rev8.read_bytes(), args.s04.read_bytes(),
                   args.model, args.image.read_bytes())
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
