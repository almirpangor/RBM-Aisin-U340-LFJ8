"""Check selected Bosch S04 load producers on original C167 instructions."""

import argparse
import json
from pathlib import Path

from audit_toyota_load_inputs import REV8_SHA
from build import S04_SHA, digest
from verify import build_native_model


WINDOWS = (
    (0x021450, 0x02145E),  # Unsigned saturated addition.
    (0x02146E, 0x02149C),  # Signed corrections and signed saturated addition.
    (0x021598, 0x0215A4),  # Unsigned subtraction clamped at zero.
    (0x0219A4, 0x0219B6),  # Adjacent load-state calculation in the same slice.
    (0x048878, 0x04888A),  # Mode source.
    (0x04889E, 0x04894E),  # Selection and F8D6/F8CF publication.
    (0x0496DE, 0x0496FA),  # 9156 reset.
    (0x059D6A, 0x059DBE),  # 967C and 9680 calculation.
    (0x0C1E80, 0x0C1E98),  # Constant-load publication.
)


def rom_window(image, start, end):
    return image[start - 0x10000:end - 0x10000]


def check_mode_source(native, image):
    # The pinned emulator stops before BMOVN. Verify that instruction in ROM,
    # then exercise both values of its destination in the consumer separately.
    assert rom_window(image, 0x048886, 0x04888A) == bytes.fromhex("3a882065")
    for prior in (0, 0x40):
        for source in (0, 1, 0xFE, 0xFF):
            native.reset()
            native.write(0xFF10, prior)
            native.write(0xA88B, source, 1)
            native.run(0x048878, stop=0x048886)
            assert (native.read(0xFF10) & 0x40) == (source & 1) << 6
    return {"prelude_cases": 8, "bit_copy_instruction": "0x048886 BMOVN T2.5,PSW.6"}


def load_case(native, selector, regular, alternate, contribution):
    native.reset()
    for address, value in (
        (0x90E6, regular), (0x924E, alternate), (0x9156, contribution),
        (0x90E2, 320), (0x924C, 450), (0x9246, 500), (0x924A, 600),
        (0x923C, 900), (0x90D6, 55), (0x90DA, 66), (0x90DE, 777),
        (0x907E, 100), (0xF8D6, 1777), (0xFD40, selector << 5),
    ):
        native.write(address, value)
    native.write(0xA88B, 1 - selector, 1)
    native.run(0x04889E, stop=0x04894E)
    selected = alternate if selector else regular
    load = min(0xFFFF, selected + contribution)
    assert native.read(0x90F6) == selected
    assert native.read(0x90F4) == (450 if selector else 320)
    assert native.read(0xF8D6) == load
    assert native.read(0xF8CF, 1) == min(255, load >> 5)
    return {"t2_bit5": selector, "load_regular_90e6": regular, "load_alternate_924e": alternate,
            "contribution_9156": contribution, "selected_90f6": selected,
            "load_f8d6": load, "compressed_f8cf": native.read(0xF8CF, 1)}


def check_separate_paths(native):
    native.reset()
    native.write(0x9148, 1234)
    native.write(0x9156, 65000)
    native.run(0x0496DE, stop=0x0496FA)
    assert native.read(0x9156) == 0
    assert native.read(0x9150) == native.read(0x914E) == native.read(0x9152) == 1234

    native.reset()
    native.run(0x0C1E80, stop=0x0C1E98)
    assert native.read(0xF8D4) == native.read(0x90F6) == native.read(0xF8D6) == 0x10AB
    assert native.read(0xF8CF, 1) == 0x85
    return {"reset_at_0496f2": {"contribution_9156": 0},
            "constant_path_at_0c1e80": {"load_f8d6": 0x10AB, "compressed_f8cf": 0x85}}


def model_base_case(native, map_result, addend, correction, bias_input, filter_word):
    native.reset()
    native.r[4] = map_result
    native.write(0xF8D6, 1500)
    native.write(0x968A, addend)
    native.write(0x968C, correction & 0xFFFF)
    native.write(0x95C6, filter_word)
    # 059D86 runs under EXTP 0x3D, so logical 0790 is physical F4790.
    native.mem.update(enumerate((bias_input & 0xFFFF).to_bytes(2, "little"), 0xF4790))
    native.run(0x059D6A, stop=0x059DBE)
    base = min(0xFFFF, max(0, min(0xFFFF, map_result + addend) + correction))
    bias = min(32767, bias_input + (filter_word >> 1))
    width = (abs(bias) << 1) & 0xFFFF
    result = max(0, base - width) if bias < 0 else min(0xFFFF, base + width)
    assert native.read(0x967C) == base and native.r[8] == (bias & 0xFFFF)
    assert native.read(0x9680) == result and native.read(0xF8D6) == 1500
    return {"map_result_r4": map_result, "addend_968a": addend, "correction_968c": correction,
            "bias_input_f4790": bias_input, "filter_word_95c6": filter_word, "base_967c": base,
            "signed_bias_r8": bias, "published_9680": result, "load_f8d6": 1500}


def audit(rev8, s04, model):
    if digest(rev8) != REV8_SHA or digest(s04) != S04_SHA:
        raise ValueError("Expected the pinned REV8 and S04 images")
    native = build_native_model(s04, model)
    windows = []
    for start, end in WINDOWS:
        data = rom_window(s04, start, end)
        assert data == rom_window(rev8, start, end), f"ROM mismatch at {start:#08x}"
        windows.append({"start": f"{start:#08x}", "end_exclusive": f"{end:#08x}", "sha256": digest(data)})
    source = check_mode_source(native, s04)
    loads = [load_case(native, *inputs) for inputs in (
        (0, 1000, 2000, 500), (1, 1000, 2000, 500), (1, 900, 1400, 100),
        (0, 0, 65535, 0), (0, 8000, 10, 159), (0, 8000, 10, 160),
        (1, 8000, 8161, 0), (1, 1, 65000, 600),
    )]
    assert loads[0]["t2_bit5"] != loads[2]["t2_bit5"]
    assert loads[0]["load_f8d6"] == loads[2]["load_f8d6"]
    bases = [model_base_case(native, *inputs) for inputs in (
        (10000, 2000, 100, -300, 400), (10000, 2000, 100, 400, 400),
        (1000, 300, -2000, -300, 60), (65000, 900, 100, 500, 0),
        (10000, 2000, -100, -32768, 0), (3000, 100, 0, 32767, 2),
        (3000, 100, 0, 1, 3), (3000, 100, 0, -2, 3),
    )]
    assert bases[0]["published_9680"] != bases[1]["published_9680"]
    return {"status": "SOURCE_AUDIT_OFFLINE_ONLY", "s04_sha256": S04_SHA, "rev8_sha256": REV8_SHA,
            "matching_windows": windows, "mode_source": source, "load_cases": loads,
            "separate_paths": check_separate_paths(native), "model_base_cases": bases,
            "toyota_load_mapping_verified": False}


def main():
    if not __debug__:
        raise RuntimeError("Enable assertions")
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("rev8", "s04", "model"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit(args.rev8.read_bytes(), args.s04.read_bytes(), args.model), indent=2))


if __name__ == "__main__":
    main()
