"""Read-only verification of the reverse-engineered Mazda PCM S05 image checks."""

import argparse
import hashlib
import json
import struct
from pathlib import Path


IMAGE_SIZE = 0x100000
SOURCE_SHA256 = "3d55f5be4cfda23a065371d71e84cc233aa111c8b237d063b1e8fc205337850d"
PROGRAM_START = 0x029000
COMPENSATION_OFFSET = 0x03FFC0
PROGRAM_SUM = 0x5AA55AA5
WORD_MASK = 0xFFFFFFFF
MARKERS = {0x008002: 0x5AA5, 0x0FFFFE: 0xA55A}
SOFTWARE_ID_OFFSET = 0x01EBFE
SOFTWARE_ID = b"LFJ8EF030LFXF0A0"
CVN_PERIOD_OFFSET = 0x01E9A0
CVN_START = 0x00803C
CVN_STOP = 0x0FFFFC

# Contiguous instructions and literal pools involved in the verified checks.
CHECK_ANCHORS = (
    (0x004470, 0x00449C, "e4d42f87b4f766268dbbc2db95119674ca8d4116c3d602e4c10c8025f1604c80"),
    (0x0052F4, 0x005340, "3d838c9064ec644d5bb1dfd3ca7d9f398f0ad32dbfc28fdc86d331fd7ab8b482"),
    (0x0054BC, 0x0054C0, "ead3d9571641095e14cda0700222ab3e49c563521d2130d6603f5583eb9c6e2f"),
    (0x029050, 0x029056, "e0a161774d727bb989994eae2f2eb7ee88e45d6450ada501766f61621d7a9fa9"),
    (0x02909C, 0x0290A0, "5bbd35f1b5b388bde94eeea4dd707dca45020d939568c46ace257f210facafbe"),
    (0x0B2DCC, 0x0B30B0, "502807052d38d3264eaaa4b223035400f90cd47f8e11cdcd9cecb4b02fd6f50c"),
    (0x0FE166, 0x0FE176, "cbbf3391c652bc27366b64615e1e86126055bda448ce98e0989f840c9eb3fb56"),
)


def program_sum(image):
    """Return the PCM's arithmetic sum over the S05 program window."""
    if len(image) != IMAGE_SIZE:
        raise ValueError(f"Expected {IMAGE_SIZE} bytes, got {len(image)}")
    return sum(word for word, in struct.iter_unpack(">I", image[PROGRAM_START:IMAGE_SIZE])) & WORD_MASK


def _expected_word(checksum, stored_word):
    return (PROGRAM_SUM - checksum + stored_word) & WORD_MASK


def compensation_bytes(image):
    """Calculate the four bytes at 0x03FFC0 without changing the image."""
    checksum = program_sum(image)
    stored_word, = struct.unpack_from(">I", image, COMPENSATION_OFFSET)
    return struct.pack(">I", _expected_word(checksum, stored_word))


def diagnostic_cvn(image):
    """Reproduce the CVN supplied under OBD service 09 PID 06."""
    period = image[CVN_PERIOD_OFFSET]
    quotient_sum = 0
    masked_sum = 0
    index = 1
    for word, in struct.iter_unpack(">H", image[CVN_START:CVN_STOP]):
        quotient_sum += word // index
        masked_sum += word & (index - 1)
        if index == period:
            index = 1
        elif index < 0xFF:
            index += 1
    return ((quotient_sum & 0xFFFF) << 16) | (masked_sum & 0xFFFF)


def inspect(image):
    checksum = program_sum(image)
    sha256 = hashlib.sha256(image).hexdigest()
    software_id = image[SOFTWARE_ID_OFFSET:SOFTWARE_ID_OFFSET + len(SOFTWARE_ID)]
    mismatched_anchors = [
        f"0x{start:06X}–0x{stop - 1:06X}"
        for start, stop, digest in CHECK_ANCHORS
        if hashlib.sha256(image[start:stop]).hexdigest() != digest
    ]
    markers = []
    for offset, expected in MARKERS.items():
        actual, = struct.unpack_from(">H", image, offset)
        markers.append({
            "offset": f"0x{offset:06X}",
            "value": f"0x{actual:04X}",
            "expected": f"0x{expected:04X}",
            "match": actual == expected,
        })

    stored_word, = struct.unpack_from(">I", image, COMPENSATION_OFFSET)
    expected_word = _expected_word(checksum, stored_word)
    static_checks_pass = (
        software_id == SOFTWARE_ID
        and not mismatched_anchors
        and all(marker["match"] for marker in markers)
        and checksum == PROGRAM_SUM
    )
    return {
        "size_bytes": len(image),
        "sha256": sha256,
        "matches_original_sha256": sha256 == SOURCE_SHA256,
        "matches_s05_software_id": software_id == SOFTWARE_ID,
        "mismatched_check_anchors": mismatched_anchors,
        "markers": markers,
        "program_sum": f"0x{checksum:08X}",
        "expected_program_sum": f"0x{PROGRAM_SUM:08X}",
        "compensation_word_offset": f"0x{COMPENSATION_OFFSET:06X}",
        "compensation_word": f"0x{stored_word:08X}",
        "expected_compensation_word": f"0x{expected_word:08X}",
        "diagnostic_cvn": f"0x{diagnostic_cvn(image):08X}",
        "passes_verified_s05_static_checks": static_checks_pass,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, help="Full-width LFJ8EF030 S05 binary")
    parser.add_argument("--expect-original", action="store_true", help="Also require the source SHA-256")
    args = parser.parse_args()
    try:
        report = inspect(args.image.read_bytes())
    except (OSError, ValueError) as error:
        parser.exit(1, f"Verification failed: {error}\n")

    print(json.dumps(report, ensure_ascii=True, indent=2))
    if args.expect_original and not report["matches_original_sha256"]:
        return 1
    return 0 if report["passes_verified_s05_static_checks"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
