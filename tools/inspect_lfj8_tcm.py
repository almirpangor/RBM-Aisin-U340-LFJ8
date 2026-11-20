"""Identify a full-length LFJ8 TCM image from its embedded metadata."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--expect", default="LFJ8-18-9E1D", help="expected embedded TCM part number")
    args = parser.parse_args()
    try:
        record = inspect(args.image.read_bytes(), args.expect.strip().upper())
    except OSError as error:
        parser.exit(2, f"Cannot read image: {error}\n")
    print(json.dumps(record, indent=2))
    return 0 if record["matches_expected_id"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
