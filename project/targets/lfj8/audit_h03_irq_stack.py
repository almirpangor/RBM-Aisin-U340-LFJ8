"""Read-only stack CFG audit for the stock LFJ8-18-9E1C H03 image.

Disassemble the exact H03 base image with GNU m32r-elf-objdump.
"""

import argparse
import hashlib
import os
import re
import subprocess
from functools import lru_cache
from pathlib import Path

IMAGE_HASH = "844a11b809cda1f2ccaf90cb6a75666009487ccedd2e8190b7eb46137b855544"
INITIAL_SPI = 0x809EFC
PSW_CURSOR = 0x809F9C
IRQ_SAVE_BYTES = 48
SBI_SAVE_BYTES = 40
SERVICE_DISPATCH_TABLE = 0x0310C8
SERVICE_DISPATCH_ROWS = 30
SERVICE_DISPATCH_STRIDE = 12
STOCK_SERVICE_BRANCHES = {0xD14E: 0xD1E0, 0xD1EA: 0xD27C}
STOCK_SERVICE_COPY = ((0x000320, 0x805000, 0x600), (0x000920, 0x805600, 0xB0))

# Renesas 32176 REJ09B0067-0110 Table 5.4.1 maps the ICU vector slots.
# H03 writes these ILEVELs in 009B06..009B9E and restores them in 009C18..009E56.
IRQ_SOURCES = {
    0: ((0x0AC, "TOP8/9"), (0x0C0, "TOP6/7")),
    1: ((0x0B0, "TOP10"), (0x10C, "CAN0")),
    2: ((0x0B8, "TIO8/9"),),
    3: ((0x0C8, "DMA0-4"), (0x0D4, "SIO0 RX")),
    4: ((0x094, "TIN3"), (0x098, "TIN20-23"), (0x0B4, "TIO4-7")),
    5: ((0x110, "CAN1"),),
    6: ((0x09C, "TIN16-19"), (0x0DC, "ADC0")),
}

# 003A4E and 003C86 load the same four callbacks seeded at 003934..003960.
ADC_CALLBACKS = (0x532C, 0x5330, 0x533C, 0x5348)

# Callback index for IRQ diagnostic record 032768 is zero.
# D358 passes zero, and DD80, DF8C, EA58 reject indexes at or above one.
DIAGNOSTIC_CALLBACK_WORD = {
    0xDDC0: 3,
    0xDDE0: 2,
    0xDE0E: 0,
    0xDEB2: 3,
    0xDF5C: 1,
    0xDFDE: 3,
    0xE154: 1,
    0xEB3E: 4,
    0xEB56: 3,
    0xEBE4: 1,
}
FLOW_EVIDENCE = (
    (0x003C4C, 0x003CA0),
    (0x003D94, 0x003E90),
    (0x003F50, 0x003FC6),
    (0x004164, 0x004204),
    (0x008324, 0x008408),
    (0x008E58, 0x008F34),
    (0x009B06, 0x009BA2),
    (0x00B800, 0x00B890),
    (0x00BAF4, 0x00BB04),
    (0x00D108, 0x00D158),
    (0x00D1E0, 0x00D1F4),
    (0x04043C, 0x040450),
    (0x043E44, 0x043E9C),
    (0x043EA4, 0x043EDC),
)
BRANCH_TARGET = re.compile(r"0x([a-f0-9]+)(?:\s+<[^>]+>)?$", re.IGNORECASE)
SP_RELATIVE = re.compile(r"@\(#?-(?:0x[0-9a-f]+|[0-9]+),\s*r15\)", re.IGNORECASE)
OBJDUMP_WORD = re.compile(r"^\s*([0-9a-f]+):\s+((?:[0-9a-f]{2}\s+){4})(\S.*)$", re.IGNORECASE)
PACKET_SEPARATOR = re.compile(r"\s+(?:->|\|\|)\s+")
REGISTER_ALIAS = re.compile(r"\b(?:sp|lr)\b")


def native_disassembly(base, objdump, image):
    command = [objdump, "-D", "-z", "-b", "binary", "-m", "m32r", "-EB", str(base)]
    listing = subprocess.run(command, check=True, capture_output=True, timeout=30).stdout
    listing = listing.decode("ascii", errors="replace")
    decoded = {}
    next_word = 0
    for line in listing.splitlines():
        match = OBJDUMP_WORD.match(line)
        if not match:
            continue
        address = int(match[1], 16)
        packet = bytes.fromhex(match[2])
        if address != next_word or packet != image[address:address + 4]:
            raise ValueError(f"Objdump bytes differ or skip a word at 0x{next_word:06X}")
        instructions = PACKET_SEPARATOR.split(match[3].strip())
        if len(instructions) == 2:
            offsets = (address, address + 2)
            size = 2
        elif len(instructions) == 1:
            offsets = (address,)
            size = 4
        else:
            raise ValueError(f"Unexpected instruction packet at 0x{address:06X}")
        for offset, native_text in zip(offsets, instructions):
            canonical = REGISTER_ALIAS.sub(
                lambda item: "r15" if item[0] == "sp" else "r14", native_text
            )
            canonical = re.sub(r"\s*,\s*", ",", canonical)
            if canonical in {"*unknown*", "(bad)"}:
                canonical = "<unknown>"
            decoded[offset] = size, canonical
        next_word += 4
    if next_word != len(image):
        raise ValueError(f"Objdump stopped at 0x{next_word:06X}, expected 0x{len(image):06X}")
    return decoded


def word(image, address):
    return int.from_bytes(image[address : address + 4], "big")


def foreground_service_targets(image):
    # 043E48..043E86 stops on service ID 0xFF. The common enable word
    # is intersected with the record halfword before JL at 043ED6.
    end = SERVICE_DISPATCH_TABLE + SERVICE_DISPATCH_ROWS * SERVICE_DISPATCH_STRIDE
    addresses = range(SERVICE_DISPATCH_TABLE, end, SERVICE_DISPATCH_STRIDE)
    if image[end] != 0xFF or any(image[address] == 0xFF for address in addresses):
        raise ValueError("Unexpected H03 foreground service table sentinel")
    enabled = int.from_bytes(image[SERVICE_DISPATCH_TABLE - 4:SERVICE_DISPATCH_TABLE - 2], "big")
    targets = []
    for address in addresses:
        conditions = int.from_bytes(image[address + 8:address + 10], "big")
        if enabled & conditions:
            target = word(image, address + 4)
            if target == 0 or target >= len(image) or target % 2:
                raise ValueError(f"Invalid foreground service target at 0x{address:06X}")
            targets.append(target)
    return tuple(targets)


def verify_stock_service_profile(image, decoded):
    flags = image[0x03001B:0x03001D]
    if flags != b"\x00\x00":
        raise ValueError(f"H03 stock service flags changed ({flags.hex()})")
    # D108 loads those bytes and stores zero to 8066AC before the two tests.
    for address, target in STOCK_SERVICE_BRANCHES.items():
        _, instruction = decoded[address]
        match = BRANCH_TARGET.search(instruction)
        if not instruction.startswith("bnc ") or not match or int(match[1], 16) != target:
            raise ValueError(f"Unexpected H03 stock service branch at 0x{address:06X}")


def relocate_stock_service(image, decoded):
    descriptors = tuple(tuple(word(image, address + offset) for offset in (0, 4, 8))
                        for address in (0x300, 0x30C))
    if descriptors != STOCK_SERVICE_COPY:
        raise ValueError("Unexpected H03 service code copy descriptors")
    offsets = {}
    for source, destination, length in descriptors:
        delta = destination - source
        for address in range(source, source + length, 2):
            if address not in decoded:
                continue
            size, instruction = decoded[address]
            opcode = instruction.split()[0].split(".")[0]
            if opcode.startswith("b"):
                match = BRANCH_TARGET.search(instruction)
                if match:
                    target = int(match[1], 16) + delta
                    instruction = instruction[:match.start()] + f"0x{target:x}"
            relocated = address + delta
            decoded[relocated] = size, instruction
            offsets[relocated] = address
    return offsets


def stock_callbacks(image, service_targets):
    handlers = {0x3A4E: ADC_CALLBACKS, 0x3C86: ADC_CALLBACKS, 0x43ED6: service_targets}
    for address in (0x1474, 0x1C88):
        handlers[address] = tuple(word(image, 0x3D24 + index * 4) for index in range(2))
    for address in (0x162C, 0x1E48):
        handlers[address] = (word(image, 0x3D48), word(image, 0x3D4C))
    for address in (0x16F2, 0x1F0E):
        handlers[address] = (word(image, 0x3D5C),)
    for address, index in DIAGNOSTIC_CALLBACK_WORD.items():
        handlers[address] = (word(image, 0x32768 + index * 4),)
    return handlers


def stack_change(instruction):
    if instruction.startswith("push ") or instruction.startswith("st ") and instruction.endswith(",@-r15"):
        return 4
    if instruction.startswith("pop ") or instruction.startswith("ld ") and instruction.endswith(",@r15+"):
        return -4
    if instruction.startswith(("addi r15,", "add3 r15,r15,")):
        return -int(instruction.rsplit(",", 1)[1].removeprefix("#"), 0)
    return 0


def verify_fixed_frames(decoded):
    dispatcher = sum(stack_change(decoded[address][1])
                     for address in range(0x3DE0, 0x3E04, 2) if address in decoded)
    sbi = sum(stack_change(decoded[address][1]) for address in range(0x3F50, 0x3F62, 2))
    sbi += stack_change(decoded[0x3F78][1])
    if (dispatcher, sbi) != (IRQ_SAVE_BYTES, SBI_SAVE_BYTES):
        raise ValueError(f"Unexpected fixed frames (IRQ {dispatcher} B, SBI {sbi} B)")


def build_analyzer(image, decoded, service_targets, stock_service_profile, relocated_offsets):
    callbacks = stock_callbacks(image, service_targets)
    taken_branches = STOCK_SERVICE_BRANCHES if stock_service_profile else {}
    diagnostic_switch = tuple(range(0x2EDC, 0x2F64, 4))
    active = set()

    @lru_cache(maxsize=None)
    def analyze(entry, reentry_budget):
        key = (entry, reentry_budget)
        if key in active:
            return 0, (), frozenset({(entry, "unresolved recursive edge")})

        active.add(key)
        incoming_depth = {}
        pending = [(entry, 0)]
        maximum = 0
        maximum_path = ()
        issues = set()

        while pending:
            address, depth = pending.pop()
            if address in incoming_depth:
                if depth != incoming_depth[address]:
                    issues.add((address, "different SP depths meet"))
                continue
            incoming_depth[address] = depth

            if address not in decoded:
                issues.add((address, "branch target outside decoded ROM"))
                continue
            size, instruction = decoded[address]
            opcode = instruction.split()[0].split(".")[0]
            following = address + size
            depth += stack_change(instruction)
            if depth > maximum:
                maximum, maximum_path = depth, ((entry, address, depth),)
            if depth < 0:
                issues.add((address, "SP moves above entry value"))
                continue
            if instruction.startswith((
                "mv r15,", "sub r15,", "add r15,", "ld r15,", "ldi8 r15,", "ldi16 r15,"
            )) or SP_RELATIVE.search(instruction):
                issues.add((address, f"SP access needs manual review ({instruction})"))
            if opcode == "<unknown>":
                issues.add((address, "unknown instruction"))
                continue

            branch_match = BRANCH_TARGET.search(instruction)
            target = int(branch_match[1], 16) if branch_match else None
            is_branch = (opcode.startswith("b") and target is not None) or opcode in {"jmp", "jl", "rte"}
            if not is_branch:
                pending.append((following, depth))
                continue

            # An aligned short branch can share its instruction word with a
            # parallel right half. A sequential right half is the fallthrough.
            source_address = relocated_offsets.get(address, address)
            if size == 2 and address % 4 == 0 and image[source_address + 2] & 0x80:
                depth += stack_change(decoded[address + 2][1])
                following += 2
                if depth > maximum:
                    maximum, maximum_path = depth, ((entry, address + 2, depth),)

            if opcode == "bra":
                pending.append((target, depth))
                continue
            if opcode == "jmp":
                if address == 0x2EDA:
                    pending.extend((destination, depth) for destination in diagnostic_switch)
                elif instruction != "jmp r14":
                    issues.add((address, f"unresolved computed jump ({instruction})"))
                elif depth:
                    issues.add((address, "return without restoring entry SP"))
                continue
            if opcode == "rte":
                if depth:
                    issues.add((address, "RTE without restoring entry SP"))
                continue
            if opcode not in {"bl", "jl"}:
                pending.append((target, depth))
                if address not in taken_branches:
                    pending.append((following, depth))
                continue

            if address == 0x2ED4:
                # BL captures the PC in R14, then 002ED8 adjusts it and JMP
                # dispatches through 34 entries. This is not a nested call.
                pending.append((target, depth))
                continue
            targets = (target,) if opcode == "bl" else callbacks.get(address, ())
            if not targets:
                issues.add((address, f"unresolved indirect call ({instruction})"))
            for destination in targets:
                if address == 0x8400 and reentry_budget == 0:
                    continue
                next_budget = reentry_budget - (address == 0x8400)
                call_maximum, call_path, call_issues = analyze(destination, next_budget)
                issues.update(call_issues)
                if depth + call_maximum > maximum:
                    maximum = depth + call_maximum
                    maximum_path = ((entry, address, depth),) + call_path
            pending.append((following, depth))

        active.remove(key)
        return maximum, maximum_path, frozenset(issues)

    return analyze


def show_path(trace):
    return " -> ".join(f"{entry:06X}@{offset:06X} +{depth}" for entry, offset, depth in trace)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True, help="Exact stock H03 BIN")
    tool = parser.add_mutually_exclusive_group(required=True)
    tool.add_argument("--objdump", help="Path or command name for GNU m32r-elf-objdump")
    tool.add_argument("--gcc", help="Path or command name for GNU m32r-elf-gcc")
    parser.add_argument("--evidence", action="store_true", help="Print instructions for stack and reentry anchors")
    parser.add_argument(
        "--stock-service-profile", action="store_true",
        help="Use H03 ROM flags to take D14E and D1EA after D108 clears the service selector",
    )
    parser.add_argument(
        "--stock-relocated-service-code", action="store_true",
        help="Assume the two H03 service code spans have been copied intact from ROM to RAM",
    )
    args = parser.parse_args()
    try:
        image = args.base.read_bytes()
        checksum = hashlib.sha256(image).hexdigest()
        if checksum != IMAGE_HASH:
            raise ValueError(f"Stock H03 SHA-256 mismatch ({checksum})")
        objdump = args.objdump
        if args.gcc:
            result = subprocess.run(
                [args.gcc, "-print-prog-name=objdump"], check=True, capture_output=True, timeout=10
            )
            objdump = os.fsdecode(result.stdout.strip())
            if not objdump:
                raise ValueError("GCC returned an empty objdump command")
        decoded = native_disassembly(args.base.resolve(), objdump, image)
        verify_fixed_frames(decoded)
        service_targets = foreground_service_targets(image)
        if args.stock_service_profile:
            verify_stock_service_profile(image, decoded)
        relocated_offsets = relocate_stock_service(image, decoded) if args.stock_relocated_service_code else {}
    except subprocess.CalledProcessError as exc:
        parser.error(f"Tool exited with status {exc.returncode} ({os.fsdecode(exc.stderr).strip()})")
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        parser.error(str(exc))
    analyze = build_analyzer(image, decoded, service_targets, args.stock_service_profile, relocated_offsets)
    irq_complete = True
    print(f"H03 SHA-256 {checksum}")
    print(f"SPI start 0x{INITIAL_SPI:06X}, separate PSW record cursor 0x{PSW_CURSOR:06X}")
    print(f"Foreground service dispatch at 043ED6 has {len(service_targets)} enabled ROM targets.")
    if args.stock_service_profile:
        print("Using ROM 03001B/03001C = 00/00 to take D14E->D1E0 and D1EA->D27C only.")
    if relocated_offsets:
        print("Modeling the stock service code in RAM, conditional on an intact ROM-to-RAM copy.")
    for reentry_budget in range(3):
        print(f"IRQ local stack bytes excluding {IRQ_SAVE_BYTES} common bytes, B800 extra entries <= {reentry_budget}")
        total = 0
        failed = False
        for priority, sources in IRQ_SOURCES.items():
            priority_maximum = 0
            for vector, name in sources:
                descriptor = word(image, vector)
                entry = word(image, descriptor)
                maximum, path, issues = analyze(entry, reentry_budget)
                priority_maximum = max(priority_maximum, maximum)
                print(f"  {priority} {name:9} {vector:06X}->{descriptor:06X}->{entry:06X} {maximum:3} B {show_path(path)}")
                for offset, issue in sorted(issues):
                    print(f"    {offset:06X} {issue}")
                failed |= bool(issues)
            total += priority_maximum + IRQ_SAVE_BYTES
        if not failed:
            print(f"  sum of per-priority maxima including dispatch {total} B")
            print(f"  sum with separate SBI SPI frame {total + SBI_SAVE_BYTES} B")
        else:
            irq_complete = False
            print("  common and local total withheld because an ISR edge is unresolved")

    for entry, label in ((0x9E0, "reset/foreground"), (0x8100, "foreground"), (0x46804, "phase 3"), (0x4682C, "phase 2")):
        maximum, path, issues = analyze(entry, 2)
        print(f"{label} 0x{entry:06X}, depth on modeled paths {maximum} B {show_path(path)}")
        for offset, issue in sorted(issues):
            print(f"  {offset:06X} {issue}")
    print("The reentry limits model stable normal mode, stable mode 4, and one stock transition to mode 4.")
    print("Local bounds assume stock callback tables and no diagnostic rewriting of the mode or pointer pair.")
    print("The SBI path also adds one record to the separate PSW stack.")
    print("Unknown foreground edges and runtime stack headroom prevent a whole-image SPI floor.")
    if args.evidence:
        for start, end in FLOW_EVIDENCE:
            for address in range(start, end, 2):
                if address in decoded:
                    size, instruction = decoded[address]
                    raw = image[address:address + size].hex(" ", 2)
                    print(f"{address:06X} {raw:9} {instruction}")

    return 0 if irq_complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
