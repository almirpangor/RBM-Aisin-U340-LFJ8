"""Identify a full-length LFJ8 TCM image from its embedded metadata."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re


SOURCE_REGISTRY = Path(__file__).resolve().parents[1] / "data/sources.json"
H03_PART_NUMBER = "LFJ8-18-9E1C"
IMAGE_SIZE = 0x80000
IDENTITY_OFFSET = 0x031033
IDENTITY = re.compile(
    rb"LFJ8\x0018\x009E1\x00([A-Z])\x00"
    rb"(LFJ8T[A-Z0-9]{11})\x00(SW-LFJ8T[A-Z0-9]{4}\.HEX)\x00"
)


def inspect(image: bytes, expected: str) -> dict:
    record = {
        "bytes": len(image),
        "sha256": sha256(image).hexdigest(),
        "expected_id": expected,
        "embedded_id": None,
        "matches_expected_id": False,
    }
    if len(image) != IMAGE_SIZE:
        record["reason"] = "source length differs from the full-size archived TCM images"
        return record

    match = IDENTITY.match(image, IDENTITY_OFFSET)
    if not match:
        record["reason"] = "embedded metadata at the known LFJ8 TCM offset was not recognized"
        return record

    revision, software, hex_name = (value.decode("ascii") for value in match.groups())
    hardware = f"LFJ8-18-9E1{revision}"
    record.update(
        embedded_id=hardware,
        software=software,
        hex_name=hex_name,
        metadata_offset=f"0x{IDENTITY_OFFSET:06X}",
        matches_expected_id=hardware == expected,
    )
    return record


def check_h03(record: dict, registry: dict) -> bool:
    approved = next((entry for entry in registry["supporting_materials"] if entry["id"] == "H03"), None)
    if approved is None:
        raise ValueError("H03 is missing from the source registry")
    matches = (record["embedded_id"] == H03_PART_NUMBER and
               record["bytes"] == approved["bytes"] and record["sha256"] == approved["sha256"])
    record.update(expected_h03_sha256=approved["sha256"], matches_h03=matches)
    return matches


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--expect", default=H03_PART_NUMBER, help="expected embedded TCM part number")
    parser.add_argument("--require-h03", action="store_true",
                        help="require the registered H03 size, SHA-256 and embedded 9E1C identity")
    args = parser.parse_args()
    expected = args.expect.strip().upper()
    if args.require_h03 and expected != H03_PART_NUMBER:
        parser.error("--require-h03 requires LFJ8-18-9E1C")
    try:
        record = inspect(args.image.read_bytes(), expected)
        matches = record["matches_expected_id"]
        if args.require_h03:
            registry = json.loads(SOURCE_REGISTRY.read_text(encoding="utf-8"))
            matches = check_h03(record, registry)
    except (OSError, KeyError, ValueError) as error:
        parser.exit(2, f"Cannot inspect image: {error}\n")
    print(json.dumps(record, indent=2))
    return 0 if matches else 1


if __name__ == "__main__":
    raise SystemExit(main())
