"""Check the exact H03 RAM stores with and without the Virtual Flash lockout."""

import argparse
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory

from check_h03_flash_policy import FCNT1, FESBANK1, LAYOUT, VIRTUAL_SELECT
from check_h03_flash_residency import CHECKSUM_REMAINING, COPY_REMAINING, SESSION_FLAGS
from check_h03_link import identify_h03
from check_h03_service_isolation import storage_blocks
from check_h03_vflash_lockout import DISABLE_BRANCH, SITE, STOCK_WORD, VIRTUAL_RAM_BASE


DIRECT = 0x002924
ADC0 = 0x003608
COPY_COMPLETE = 0x002DF4
MONITOR = 0x808578
ADC0_TICKS = 0x808DC0
SOURCE = 0x101000
BANK = 0x20
COPY_SLICE = 256
SENTINEL = 0xCC

FIXTURE = f"""
    .section .fixture,"ax",@progbits
    .p2align 2
    .global _start,fixture_ready,fixture_dispatch,fixture_done
_start:
    ld24 sp,#0x9ffffc
fixture_ready:
    ld24 r0,#{VIRTUAL_RAM_BASE:#x}
    bl.l stock_selector
    ld24 r4,#fixture_arguments
    ld r3,@(16,r4)
    beqz r3,fixture_dispatch
    bl.l fixture_close
fixture_dispatch:
    ld24 r4,#fixture_arguments
    ld r3,@r4
    ld r0,@(4,r4)
    ld r1,@(8,r4)
    ld r2,@(12,r4)
    ld24 lr,#fixture_done
    jmp r3
    .p2align 2
fixture_done:
    ld24 r4,#fixture_arguments
    ld r3,@(20,r4)
    addi r3,#-1
    st r3,@(20,r4)
    bnez r3,fixture_dispatch
.Lstop:
    bra .Lstop

    .p2align 2
fixture_close:
    /* Supply the four saved words normally set up at 002E10. */
    ld24 r10,#{MONITOR:#x}
    push lr
    push r10
    push r9
    push r8
    bra.l stock_close

    .section .fixture_data,"aw",@progbits
    .p2align 2
    .global fixture_arguments
fixture_arguments:
    .space 24

    .section .oem,"ax",@progbits
    .incbin "h03.dat"
"""


@dataclass(frozen=True)
class Case:
    name: str
    entry: int
    address: int
    count: int
    bytes_per_call: tuple
    close: bool = False
    checksum: int = 0


def scenarios(blocks):
    for block, (start, end) in blocks.items():
        for edge, address in (("first", start), ("last", end - 1)):
            yield Case(f"{block}_{edge}_direct", DIRECT, address, 1, (1,))
            yield Case(f"{block}_{edge}_after_close", ADC0, address, 1, (1,), close=True)
    start, end = blocks["control"]
    if end - start < COPY_SLICE + 1:
        raise ValueError("Control block is too small for the deferred slice test")
    yield Case("crosses_into_control", ADC0, start - 1, 2, (2,), close=True)
    yield Case("control_two_adc0_passes", ADC0, start, COPY_SLICE + 1, (COPY_SLICE, 1), close=True)
    yield Case("no_pending_copy", ADC0, start, 0, (0,), close=True)
    yield Case("checksum_delays_copy", ADC0, start, 1, (0,), close=True, checksum=COPY_SLICE + 1)
    yield Case("stock_protected_direct", DIRECT, MONITOR + 0x28, 1, (0,))
    yield Case("stock_protected_prepared_copy", ADC0, MONITOR + 0x28, 1, (1,), close=True)


def assignment(kind, address, value):
    return f"set {{{kind}}}{address} = {value:#x}"


def report_line(name):
    return (f'printf "{name} %x %x %x %x %x %x %x %x %x %x %x\\n", $pc, $r0, '
            f"*(unsigned char*){SESSION_FLAGS:#x}, *(unsigned char*){FCNT1:#x}, "
            f"*(unsigned short*){FESBANK1:#x}, *(unsigned short*){ADC0_TICKS:#x}, "
            f"*(unsigned int*){CHECKSUM_REMAINING:#x}, *(unsigned int*){COPY_REMAINING:#x}, "
            f"*(unsigned int*){MONITOR + 12:#x}, *(unsigned int*){MONITOR + 20:#x}, "
            f"*(unsigned short*){MONITOR + 4:#x}")


def observation(output, name):
    match = re.search(rb"^" + name.encode("ascii") + rb" ((?:[0-9a-f]+ ){10}[0-9a-f]+)\r?$", output, re.M)
    if match is None:
        raise ValueError(f"Missing {name} observation: {output[-1400:].decode(errors='replace')}")
    return tuple(int(field, 16) for field in match[1].split())


def run_case(run, work, gdb, case, lockout):
    width = max(case.count, 1)
    scratch_start = case.address - 1
    scratch_end = case.address + width + 1
    # Fixed simulator data. No service messages, capture replay or device I/O.
    payload = bytes(0x80 | (index & 0x3F) for index in range(max(width, case.checksum)))
    sentinel = bytes([SENTINEL]) * (width + 2)
    (work / "payload.dat").write_bytes(payload)
    (work / "sentinel.dat").write_bytes(sentinel)
    pending = case.count if case.entry == ADC0 else 0
    arguments = (case.entry, 0, case.count, SOURCE, case.close, len(case.bytes_per_call))
    seed = (
        ("unsigned int", 0x809F9C, 0x809F9C),
        ("unsigned short", VIRTUAL_SELECT, BANK),
        ("unsigned char", FCNT1, 1),
        ("unsigned short", FESBANK1, 0x8000 | BANK),
        ("unsigned char", SESSION_FLAGS, 0x20),
        ("unsigned short", ADC0_TICKS, 0),
        ("unsigned int", MONITOR + 12, case.address if case.entry == DIRECT else SOURCE),
        ("unsigned int", MONITOR + 16, case.address),
        ("unsigned int", MONITOR + 20, SOURCE),
        ("unsigned short", MONITOR + 4, 0),
        ("unsigned int", CHECKSUM_REMAINING, case.checksum),
        ("unsigned int", COPY_REMAINING, pending),
        ("unsigned int", COPY_REMAINING + 4, pending),
    )
    commands = ["set confirm off", "target sim --memory-size 16M", "load",
                "tbreak *fixture_ready", "run"]
    commands.extend(assignment(kind, hex(address), value) for kind, address, value in seed)
    if lockout:
        commands.append(assignment("unsigned int", hex(SITE), DISABLE_BRANCH))
    commands.extend(assignment("unsigned int", f"((char*)&fixture_arguments+{index * 4})", value)
                    for index, value in enumerate(arguments))
    commands.extend((f"restore sentinel.dat binary {scratch_start:#x}", f"restore payload.dat binary {SOURCE:#x}",
                     "tbreak *fixture_dispatch", "continue", report_line("READY")))
    for index in range(len(case.bytes_per_call)):
        if index:
            # Continue the exact same pending request on the next ADC0 entry.
            commands.extend(("delete breakpoints", "tbreak *fixture_dispatch", "continue"))
        commands.extend(("tbreak *fixture_done", f"tbreak *{COPY_COMPLETE:#x}", "continue",
                         report_line(f"STORE_{index}"),
                         f"dump binary memory ram-{index}.dat {scratch_start:#x} {scratch_end:#x}"))
    (work / "probe.gdb").write_text("\n".join(commands) + "\n", encoding="ascii")
    try:
        output = run(gdb, "--batch", "-nx", "-x", "probe.gdb", "fixture.elf")
    except subprocess.CalledProcessError as error:
        raise ValueError(f"{case.name}, lockout={lockout}: "
                         + (error.stderr or str(error).encode()).decode(errors="replace")) from error

    flags, fcnt1, bank = (0x10 if case.close else 0x20), int(not lockout), (0 if lockout else 0x8000) | BANK
    base_pointer = case.address if case.entry == DIRECT else SOURCE
    _, _, *ready = observation(output, "READY")
    if tuple(ready) != (flags, fcnt1, bank, 0, case.checksum, pending, base_pointer, SOURCE, 0):
        raise ValueError(f"{case.name}: unexpected state before store, lockout={lockout}: {ready}")

    written = 0
    rows = []
    for index, count in enumerate(case.bytes_per_call):
        written += count
        observed = observation(output, f"STORE_{index}")
        pc, result, session, control, select, adc, checksum, remaining, pointer, sum_addr, total = observed
        expected_ram = sentinel[:1] + payload[:written] + sentinel[written + 1:]
        expected_adc = index + 1 if case.entry == ADC0 else 0
        expected_checksum = max(case.checksum - COPY_SLICE, 0)
        expected_remaining = pending - written if case.entry == ADC0 else 0
        expected_pointer = base_pointer + (case.count if case.entry == DIRECT else 0)
        summed = min(case.checksum, COPY_SLICE)
        expected_result = int(count > 0) if case.entry == DIRECT else int(bool(remaining or checksum))
        at_completion = case.entry == ADC0 and count > 0 and expected_remaining == 0
        expected = (flags, fcnt1, bank, expected_adc, expected_checksum, expected_remaining,
                    expected_pointer, SOURCE + summed, sum(payload[:summed]) & 0xFFFF)
        if (session, control, select, adc, checksum, remaining, pointer, sum_addr, total) != expected:
            raise ValueError(f"{case.name}: inconsistent state on pass {index + 1}, "
                             f"lockout={lockout}: observed {observed[2:]}, expected {expected}")
        if at_completion:
            if pc != COPY_COMPLETE:
                raise ValueError(f"{case.name}: missed original copy completion")
        elif pc < 0x100000 or result != expected_result:
            raise ValueError(f"{case.name}: wrong native return on pass {index + 1}: {(pc, result)}")
        if (work / f"ram-{index}.dat").read_bytes() != expected_ram:
            raise ValueError(f"{case.name}: unexpected RAM bytes or modified sentinel on pass {index + 1}")
        rows.append({"bytes_written": count, "remaining": remaining, "checksum_remaining": checksum,
                     "adc0_ticks": adc, "stop": f"0x{pc:06X}"})
    return {"case": case.name, "destination": f"0x{case.address:06X}", "count": case.count,
            "entry": f"0x{case.entry:06X}", "session_flags": f"0x{flags:02X}", "lockout": lockout,
            "fcnt1": fcnt1, "fesbank1": f"0x{bank:04X}", "calls": rows}


def check(base, compiler, storage_report):
    identity = identify_h03(base)
    rom = base.read_bytes()
    if sha256(rom).hexdigest() != identity["sha256"]:
        raise ValueError("H03 changed while reading its instructions")
    if int.from_bytes(rom[SITE:SITE + 4], "big") != STOCK_WORD:
        raise ValueError("Unexpected stock selector instruction")
    storage_raw = storage_report.read_bytes()
    blocks = storage_blocks(storage_raw, identity)
    required = {"control", "communication", "workspace"}
    if set(blocks) != required:
        raise ValueError("Expected all three H03 candidate RAM blocks")

    with TemporaryDirectory(prefix="rbm-h03-service-writes-") as directory:
        work = Path(directory)

        def run(*args):
            completed = subprocess.run(
                [str(arg) for arg in args], cwd=work, check=True, capture_output=True, timeout=30,
            )
            return completed.stdout

        if run(compiler, "-dumpmachine").strip() != b"m32r-elf":
            raise ValueError("A bare-metal M32R compiler is required")
        gdb = compiler.with_name(f"m32r-elf-gdb{compiler.suffix}")
        (work / "h03.dat").write_bytes(rom)
        (work / "fixture.S").write_text(FIXTURE, encoding="ascii")
        (work / "fixture.ld").write_text(
            LAYOUT + "stock_selector = 0x003550;\nstock_close = 0x002e80;\n", encoding="ascii",
        )
        run(compiler, "-m32r", "-Wa,-EB", "-nostdlib", "-Wl,-T,fixture.ld", "fixture.S", "-o", "fixture.elf")
        results = [run_case(run, work, gdb, case, lockout)
                   for case in scenarios(blocks) for lockout in (False, True)]

    return {
        "base": identity,
        "storage_report_sha256_lf": sha256(storage_raw.replace(b"\r\n", b"\n")).hexdigest(),
        "storage_bytes": sum(end - start for start, end in blocks.values()),
        "storage_blocks": {name: [f"0x{start:06X}", f"0x{end:06X}"] for name, (start, end) in blocks.items()},
        "results": results,
        "prepared_internal_state_only": True,
        "physical_remapping_modelled": False,
        "external_programmer_verified": False,
        "hardware_executed": False,
        "flashable_image": None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--gcc", type=Path, required=True)
    parser.add_argument("--storage-report", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if (args.out.suffix.lower() != ".json" or
            args.out.resolve() in (args.base.resolve(), args.storage_report.resolve())):
        parser.error("--out must be a separate JSON report")
    try:
        result = check(args.base, args.gcc.resolve(), args.storage_report)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or str(error).encode()).decode(errors="replace")
        parser.exit(1, detail + "\n")
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
