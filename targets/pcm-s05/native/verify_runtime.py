"""Verify statically established S05 runtime anchors against the original BIN."""

import argparse
import hashlib
from pathlib import Path


SIZE = 0x100000
SHA256 = "3d55f5be4cfda23a065371d71e84cc233aa111c8b237d063b1e8fc205337850d"


def read(image, offset, size):
    return int.from_bytes(image[offset:offset + size], "big")


def signature(image, offset, expected):
    expected = bytes.fromhex(expected)
    if image[offset:offset + len(expected)] != expected:
        raise ValueError(f"instruction signature differs at ROM 0x{offset:06X}")


def literal_address(instruction, address):
    if instruction >> 12 == 0xD:
        return ((address + 4) & ~3) + 4 * (instruction & 0xFF)
    if instruction >> 12 == 0x9:
        return address + 4 + 2 * (instruction & 0xFF)
    raise ValueError(f"expected PC-relative load at ROM 0x{address:06X}")


def literal(image, address, expected):
    instruction = read(image, address, 2)
    source = literal_address(instruction, address)
    size = 4 if instruction >> 12 == 0xD else 2
    if read(image, source, size) != expected:
        raise ValueError(f"unexpected literal value loaded at ROM 0x{address:06X}")
    return source


def branch(image, address, expected):
    instruction = read(image, address, 2)
    bits = 12 if instruction >> 12 in (0xA, 0xB) else 8
    if bits == 8 and instruction >> 8 not in (0x89, 0x8B, 0x8D, 0x8F):
        raise ValueError(f"expected relative branch at ROM 0x{address:06X}")
    displacement = instruction & ((1 << bits) - 1)
    if displacement & (1 << (bits - 1)):
        displacement -= 1 << bits
    if address + 4 + 2 * displacement != expected:
        raise ValueError(f"unexpected branch target at ROM 0x{address:06X}")


def vector(image, number, stub, handler):
    if read(image, 4 * number, 4) != stub:
        raise ValueError(f"unexpected entry for vector {number}")
    signature(image, stub, "2f06")
    literal(image, stub + 2, handler)
    signature(image, stub + 4, "402b60f6")


def verify(image):
    digest = hashlib.sha256(image).hexdigest()
    if len(image) != SIZE or digest != SHA256:
        raise ValueError(f"S05 identity mismatch. Size {len(image)} bytes, SHA-256 {digest}")

    signature(image, 0x003726, "da56 4a0b 0009")
    literal(image, 0x003726, 0x004470)
    signature(image, 0x004484, "d004 400b 0009")
    literal(image, 0x004484, 0x0FFF20)
    signature(image, 0x0FFF20, "2f06 d028 402b 60f6")
    literal(image, 0x0FFF22, 0x0294C2)
    signature(image, 0x0294C2, "7ffc 4f22 2fe6 6ef3 2f16 61e3 7108 da95 4a0b 0009")
    literal(image, 0x0294D0, 0x0AC2AC)
    signature(image, 0x0295EE, "da5e 6aa0 2aa8 8df3 0009 ea00 db5b 2ba0 6413 da58 4a0b 0009")
    literal(image, 0x0295EE, 0xFFFF3026)
    literal(image, 0x0295FA, 0xFFFF3026)
    branch(image, 0x0295F4, 0x0295DE)
    branch(image, 0x029982, 0x0295EE)
    branch(image, 0x02998C, 0x0295EE)

    call_literal = literal(image, 0x029600, 0x0B2B54)
    if call_literal != 0x029764:
        raise ValueError("main loop call literal moved")
    literal_loads = [
        address
        for address in range(call_literal - 1024, call_literal, 2)
        if (instruction := read(image, address, 2)) >> 12 == 0xD
        and literal_address(instruction, address) == call_literal
    ]
    if literal_loads != [0x029600]:
        raise ValueError(f"unexpected PC-relative readers of ROM 0x029764: {literal_loads}")
    literal(image, 0x0B2B58, 0xFFFFF430)
    signature(image, 0x0B2B5A, "6aa2 24a1 6ef6 000b 0009")

    vector(image, 188, 0x0FFE30, 0x0B1AC4)
    signature(image, 0x0B1B28, "da17 4a0b 0009")
    literal(image, 0x0B1B28, 0x029F3C)
    literal(image, 0x029F46, 0xFFFF21DC)
    signature(image, 0x029F48, "60a0 70ff 2a00")
    signature(image, 0x029020, "ea01 db15 2ba0")
    literal(image, 0x029022, 0xFFFF21DC)
    literal(image, 0x02A022, 0xFFFF21DC)
    signature(image, 0x02A024, "6aa0 2aa8 8f05 0009 b1a8 0009")
    branch(image, 0x02A02C, 0x02A380)
    signature(image, 0x02A386, "ea0a db38 2ba0 ea01 db36 2ba0")
    literal(image, 0x02A388, 0xFFFF21DC)
    literal(image, 0x02A38E, 0xFFFF3026)
    literal(image, 0x0AC2D2, 0x0B1CD8)
    signature(image, 0x0B1CF6, "ea41 db53 2ba1 9a81 db51 2ba1 ea41 db4e 2ba1 9a7a db4c 2ba1")
    literal(image, 0x0B1CF8, 0xFFFFF712)
    literal(image, 0x0B1CFC, 249)
    literal(image, 0x0B1CFE, 0xFFFFF716)
    literal(image, 0x0B1D04, 0xFFFFF718)
    literal(image, 0x0B1D08, 1249)
    literal(image, 0x0B1D0A, 0xFFFFF71C)
    signature(image, 0x0AC8BE, "ea03 db22 2ba1")
    literal(image, 0x0AC8C0, 0xFFFFF710)

    vector(image, 192, 0x0FFE40, 0x0B1B94)
    vector(image, 228, 0x0FFF00, 0x0A9FF0)
    vector(image, 229, 0x0FFF08, 0x0AA0C0)
    vector(image, 230, 0x0FFF10, 0x00445C)
    vector(image, 231, 0x0FFF18, 0x00445C)
    literal(image, 0x0AC684, 0x0A9180)
    signature(image, 0x0A91EE, "9a56 db9d 2ba1 eaff db9b 2ba1 db99 2ba1")
    literal(image, 0x0A91EE, 0xFF3F)
    literal(image, 0x0A91F0, 0xFFFFD80A)
    literal(image, 0x0A91F6, 0xFFFFD852)
    literal(image, 0x0A91FA, 0xFFFFD850)
    literal(image, 0x0B1BEC, 0x0AB10E)
    signature(image, 0x0B1BFC, "600c 8800 8d4a 0009")
    branch(image, 0x0B1C00, 0x0B1C98)
    literal(image, 0x0B1C42, 0x0A9778)
    signature(image, 0x0B1C44, "400b 0009")
    literal(image, 0x0B1C50, 0x0A9948)
    literal(image, 0x0A97AC, 0xFFFFD842)
    literal(image, 0x0A97B0, 0xFFFF75DA)
    literal(image, 0x0A97BA, 0xFFFFD840)
    literal(image, 0x0A97BE, 0xFFFF75DC)
    literal(image, 0x0A97DE, 0x025F00)
    literal(image, 0x0A97E8, 0xFFFF2B8A)
    branch(image, 0x0A982A, 0x0A9630)
    signature(image, 0x0A9858, "5d11 9a3f 3da6 8f03 0009 6483 4d0b 0009")
    signature(image, 0x0A98A8, "85e8 da26 2a01 85e6 da22 2a01")

    literal(image, 0x0041EA, 0x000658)
    literal(image, 0x0041EE, 0x000668)
    literal(image, 0x000874, 0x000660)
    signature(image, 0x00065C, "ffffb930 ffffa930 ffffb130 0000373a 0000371c")
    signature(image, 0x0008F6, "6020 caaa c8ff 8f03 0009 7201 aff1 0009")
    return digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, help="Path to the original RB-J-P01.bin")
    args = parser.parse_args()
    try:
        digest = verify(args.image.read_bytes())
    except (OSError, ValueError) as error:
        parser.exit(1, f"Verification failed: {error}\n")

    print(f"S05 SHA-256 {digest}")
    print("Main loop 0x0295EE, OEM call 0x029600 via ROM 0x029764")
    print("One encoded PC-relative longword load of that literal in its reachable window")
    print("CMT0 publishes flag 0xFFFF3026 every 80,000 peripheral clocks in steady state")
    print("CMT1 polls HCAN1 through 0x0A9778 and calls 0x0A9948 when 0x0AB10E permits it")
    print("Task 1 stack 0xFFFFB130..0xFFFFB92F")
    print("Available stack margin and ownership of additional RAM remain unverified")
    print("No image changes were made")


if __name__ == "__main__":
    main()
