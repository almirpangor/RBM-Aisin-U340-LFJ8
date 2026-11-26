"""Compare local H03 readback bytes with the intended 9E1C image."""

import argparse
from hashlib import sha256
import json
from pathlib import Path

if __package__:
    from .inspect_lfj8_tcm import H03_PART_NUMBER, IMAGE_SIZE, inspect
else:
    from inspect_lfj8_tcm import H03_PART_NUMBER, IMAGE_SIZE, inspect


EXIT_STATUS = {"MATCH": 0, "MISMATCH": 1, "PARTIAL_MATCH": 3}


def hex_address(address):
    return f"0x{address:06X}"


def missing_ranges(coverage):
    cursor = 0
    while (start := coverage.find(b"\x00", cursor)) != -1:
        end = coverage.find(b"\x01", start)
        cursor = len(coverage) if end == -1 else end
        yield {"start": hex_address(start), "end_exclusive": hex_address(cursor)}


def compare(expected, reads):
    identity = inspect(expected, H03_PART_NUMBER)
    if not identity["matches_expected_id"]:
        raise ValueError("The expected file must be a full-size LFJ8-18-9E1C image")

    covered = bytearray(IMAGE_SIZE)
    different = bytearray(IMAGE_SIZE)
    records = []
    for start, data in reads:
        end = start + len(data)
        if not 0 <= start < end <= IMAGE_SIZE:
            raise ValueError(f"Read at {start:#x} with {len(data)} bytes lies outside the image or is empty")

        covered[start:end] = b"\x01" * len(data)
        target = expected[start:end]
        first = None
        last = None
        count = 0
        if target != data:
            for address, (wanted, actual) in enumerate(zip(target, data, strict=True), start):
                if wanted != actual:
                    if first is None:
                        first = address
                    last = address
                    count += 1
                    different[address] = 1
        record = {"start": hex_address(start), "end_exclusive": hex_address(end),
                  "sha256": sha256(data).hexdigest(), "mismatched_bytes": count}
        if first is not None:
            record["first_mismatch"] = {
                "address": hex_address(first), "expected": expected[first], "observed": data[first - start],
            }
            record["last_mismatch_address"] = hex_address(last)
        records.append(record)

    if not records:
        raise ValueError("At least one readback file is required")
    covered_bytes = covered.count(1)
    mismatched_bytes = different.count(1)
    unread = IMAGE_SIZE - covered_bytes
    status = "MISMATCH" if mismatched_bytes else "PARTIAL_MATCH" if unread else "MATCH"
    return {"status": status, "expected": identity, "covered_bytes": covered_bytes,
            "unread_bytes": unread, "mismatched_bytes": mismatched_bytes,
            "unread_ranges": list(missing_ranges(covered)), "reads": records}


def read_image(path):
    with path.open("rb") as stream:
        data = stream.read(IMAGE_SIZE + 1)
    if len(data) > IMAGE_SIZE:
        raise ValueError(f"{path} exceeds the size of a full 9E1C image")
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected", required=True, type=Path, help="Intended full-size 9E1C BIN")
    parser.add_argument("--read", action="append", nargs=2, required=True, metavar=("ADDRESS", "FILE"),
                        help="Raw binary bytes beginning at ADDRESS in the image. Repeat for more reads.")
    args = parser.parse_args()
    try:
        spans = [(int(address, 0), Path(path)) for address, path in args.read]
        report = compare(read_image(args.expected),
                         ((address, read_image(path)) for address, path in spans))
    except (OSError, ValueError) as error:
        parser.exit(2, f"Readback check failed: {error}\n")
    for record, (_, path) in zip(report["reads"], spans, strict=True):
        record["file"] = str(path)
    print(json.dumps(report, indent=2))
    return EXIT_STATUS[report["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
