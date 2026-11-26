"""Verify and export the studied calibration tables of the LFJ8-18-9E1B donor."""

import argparse
import hashlib
import json
import struct
from pathlib import Path


SHA256 = "624790698dcb39000c2a070c07e14f4857e3a46cc32142c3ee5ac4689fd8b7cc"
SHIFT_MAPS = (
    (0x1B000, 0x4B2E0), (0x1B048, 0x4B300), (0x1B090, 0x4B2A0),
    (0x1B0D8, 0x4B2C0), (0x1B120, 0x4ABB8), (0x1B240, 0x4B11C),
    (0x1B288, 0x4B13C), (0x1B2D0, 0x4B0DC), (0x1B318, 0x4B0FC),
    (0x1B360, 0x4AA84), (0x1B3A8, 0x4AAA4), (0x1B480, 0x4B25C),
    (0x1B4C8, 0x4B27C), (0x1B510, 0x4B21C), (0x1B558, 0x4B23C),
    (0x1B5A0, 0x4AB74), (0x1B6C0, 0x4B098), (0x1B708, 0x4B0B8),
    (0x1B750, 0x4B058), (0x1B798, 0x4B078), (0x1B7E0, 0x4AA40),
    (0x1B828, 0x4AA60), (0x1B990, 0x4B17C), (0x1B9D8, 0x4B19C),
    (0x1BA20, 0x4AB14), (0x1BA68, 0x4AB34), (0x1D338, 0x4AE04),
    (0x1D380, 0x4B410), (0x1D3C8, 0x4AC9C), (0x1D530, 0x4B3E4),
    (0x1D578, 0x4AC50), (0x1D950, 0x4B014), (0x1D998, 0x4B034),
    (0x1D9E0, 0x4AFD4), (0x1DA28, 0x4AFF4), (0x1DA70, 0x4A9FC),
    (0x1DCC8, 0x4B358), (0x1DD58, 0x4A9A4), (0x1DDA0, 0x4C7D8),
)
REGULATION_PAIRS = (
    (0x18168, 0x18090, 0x55DDC), (0x18318, 0x18240, 0x5F10C),
    (0x184C8, 0x183F0, 0x61988), (0x18678, 0x185A0, 0x68880),
    (0x188B8, 0x187E0, 0x5F80C), (0x18A68, 0x18990, 0x60268),
)


def f32(image: bytes, offset: int, count: int) -> tuple[float, ...]:
    return struct.unpack_from(f">{count}f", image, offset)


def check_bytes(image: bytes, offset: int, expected: bytes) -> None:
    if image[offset:offset + len(expected)] != expected:
        raise ValueError(f"Unexpected instruction bytes at {offset:#08x}")


def call_target(image: bytes, offset: int) -> int:
    opcode = image[offset]
    if opcode in (0x7F, 0xFF):
        width = 1 if opcode == 0x7F else 3
        offset += 4 * int.from_bytes(image[offset + 1:offset + 1 + width], "big", signed=True)
    check_bytes(image, offset, b"\xFE")
    return offset + 4 * int.from_bytes(image[offset + 1:offset + 4], "big", signed=True)


def inspect(image: bytes) -> dict:
    digest = hashlib.sha256(image).hexdigest()
    if len(image) != 524288 or digest != SHA256:
        raise ValueError(f"Expected the approved LFJ8-18-9E1B image; got {len(image)} bytes and SHA-256 {digest}")

    shifts = []
    for offset, ref in SHIFT_MAPS:
        output_offset = offset + 36
        check_bytes(image, ref, b"\xE2" + offset.to_bytes(3, "big"))
        check_bytes(image, ref + 4, b"\x61\x09")
        check_bytes(image, ref + 8, b"\xE0" + output_offset.to_bytes(3, "big"))
        if call_target(image, ref + 12) != 0x095B4:
            raise ValueError(f"Unexpected interpolation target after {ref:#08x}")
        shifts.append({"axis_offset": hex(offset), "values_offset": hex(output_offset),
                       "reference": hex(ref), "axis": f32(image, offset, 9),
                       "values": f32(image, output_offset, 9)})

    pairs = []
    for lower, upper, ref in REGULATION_PAIRS:
        check_bytes(image, ref, b"\xE1" + upper.to_bytes(3, "big"))
        check_bytes(image, ref + 4, b"\xE0" + lower.to_bytes(3, "big"))
        if call_target(image, ref + 8) != 0x36FB0:
            raise ValueError(f"Unexpected regulation target after {ref:#08x}")
        pairs.append({"reference": hex(ref),
                      "lower": {"offset": hex(lower), "row_major_values": f32(image, lower, 54)},
                      "upper": {"offset": hex(upper), "row_major_values": f32(image, upper, 54)}})

    for ref, target in ((0x3702C, 0x095B4), (0x37040, 0x095B4), (0x3718C, 0x096D4)):
        if call_target(image, ref) != target:
            raise ValueError(f"Unexpected grid interpolation target at {ref:#08x}")

    lower_reference = f32(image, 0x198D8, 1)[0]
    upper_reference = f32(image, 0x198D4, 1)[0]
    return {"source": {"part_number": "LFJ8-18-9E1B", "sha256": digest},
            "encoding": "ieee754_float32_big_endian",
            "shift_thresholds": shifts,
            "regulation": {"columns_offset": "0x18000", "columns": f32(image, 0x18000, 9),
                           "rows_offset": "0x18bd0", "rows": f32(image, 0x18BD0, 6),
                           "pair_references": [lower_reference, upper_reference], "pairs": pairs}}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--json", action="store_true", help="Print the verified raw values as JSON")
    args = parser.parse_args()
    try:
        result = inspect(args.image.read_bytes())
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")

    if args.json:
        print(json.dumps(result, indent=2, allow_nan=False))
    else:
        print(f"SHA-256 {result['source']['sha256']}")
        print(f"{len(result['shift_thresholds'])} nine-node maps and "
              f"{2 * len(result['regulation']['pairs'])} 6x9 maps verified")


if __name__ == "__main__":
    main()
