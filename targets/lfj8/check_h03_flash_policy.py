"""Replay the exact H03 boot and Flash policy in an isolated M32R simulator."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory

from check_h03_link import elf_info, identify_h03


START, LIMIT = 0x020000, 0x030000
BOOT, APPLICATION, RECOVERY = 0x003DC8, 0x008100, 0x0047D8
ERASE_POLICY, ERASE_CALL, ERASE_DENIED = 0x005200, 0x005254, 0x005248
READBACK, READBACK_DONE = 0x004554, 0x004588
SUM_VALUE, SUM_CURSOR = 0x8048E0, 0x806AC8
VIRTUAL_CONFIG, VIRTUAL_CONFIG_DONE = 0x003550, 0x0035B4
VIRTUAL_SELECT, FCNT1, FESBANK1 = 0x808DB0, 0x8007E2, 0x8007F2
VIRTUAL_S_PAGE_BYTES = 0x1000

LAYOUT = """
ENTRY(_start)
SECTIONS {
  .oem 0x000000 : { *(.oem) }
  .fixture 0x100000 : { *(.fixture) }
  .fixture_data : { *(.fixture_data) }
  /DISCARD/ : { *(.note*) *(.comment) }
  real_diagnostic_sum = 0x00a0cc;
}
"""

FIXTURE = """
    .section .fixture,"ax",@progbits
    .global _start
    .global fixture_ready
    .global fixture_sum
    .global fixture_sum_done
_start:
    ld24 sp,#0x9ffffc
fixture_ready:
    ld24 r4,#fixture_arguments
    ld r2,@r4
    ld r8,@(4,r4)
    ld r9,@(8,r4)
    ld r10,@(12,r4)
    ld r0,@(16,r4)
    jmp r2
    .p2align 2
fixture_sum:
    ldi r11,#513
.Lsum:
    bl real_diagnostic_sum
    addi r11,#-1
    bnez r11,.Lsum
    .p2align 2
fixture_sum_done:
    bra fixture_sum_done

    .section .fixture_data,"aw",@progbits
    .p2align 2
    .global fixture_arguments
fixture_arguments:
    .space 20

    .section .oem,"ax",@progbits
    .incbin "stock.dat"
"""


def replay(run, work, gdb, entry, stops, arguments=(0, 0, 0), memory=(), initial_r0=0):
    commands = ["set confirm off", "target sim --memory-size 16M", "load",
                "tbreak *fixture_ready", "run"]
    commands.extend(f"set {{unsigned int}}((char*)&fixture_arguments+{i * 4}) = {value}"
                    for i, value in enumerate((entry, *arguments, initial_r0)))
    commands.extend(f"set {{{kind}}}{address:#x} = {value:#x}" for kind, address, value in memory)
    commands.extend(f"tbreak *{address}" for address in stops)
    commands.extend(("continue", f'printf "FLASH_POLICY %x %x %x %x %x %x %x %x\\n", '
                     f"$pc, $r0, $r1, $r9, *(unsigned short*){SUM_VALUE:#x}, "
                     f"*(unsigned int*){SUM_CURSOR:#x}, *(unsigned char*){FCNT1:#x}, "
                     f"*(unsigned short*){FESBANK1:#x}"))
    (work / "check.gdb").write_text("\n".join(commands) + "\n", encoding="ascii")
    result = run(gdb, "--batch", "-nx", "-x", "check.gdb", "fixture.elf")
    match = re.search(rb"FLASH_POLICY ((?:[0-9a-f]+ ){7}[0-9a-f]+)", result)
    if match is None:
        raise ValueError(f"Missing simulator state: {result[-1000:].decode(errors='replace')}")
    return tuple(int(value, 16) for value in match[1].split())


def reference_candidates(rom):
    counts = {"wide_branch": [], "medium_branch": [], "short_branch": [], "ld24": [], "u32_be": []}

    def record(kind, source, target):
        if START <= target < LIMIT:
            counts[kind].append([f"0x{source:06X}", f"0x{target:06X}"])

    for source in range(0, len(rom), 4):
        if START <= source < LIMIT:
            continue
        packet = rom[source:source + 4]
        record("u32_be", source, int.from_bytes(packet, "big"))
        opcode = packet[0]
        if 0xE0 <= opcode <= 0xEF:
            record("ld24", source, int.from_bytes(packet[1:], "big"))
        elif 0xF8 <= opcode <= 0xFF:
            record("wide_branch", source, source + 4 * int.from_bytes(packet[1:], "big", signed=True))
        elif 0xB0 <= opcode <= 0xBF:
            record("medium_branch", source, source + 4 * int.from_bytes(packet[2:], "big", signed=True))
        elif opcode < 0x80:
            for slot in (0, 2):
                if 0x78 <= packet[slot] & 0x7F <= 0x7F:
                    displacement = int.from_bytes(packet[slot + 1:slot + 2], "big", signed=True)
                    record("short_branch", source + slot, source + 4 * displacement)
    return counts


def check_placement(elf, flash_bytes, banks):
    identity, sections = elf_info(elf, 2)
    if identity["relocations"]:
        raise ValueError("ELF placement requires resolved relocations")
    if not sections:
        raise ValueError("ELF placement requires allocated sections")
    collisions = []
    for start, size, flags in sections:
        end = start + size
        flash_end = min(end, flash_bytes)
        if start >= flash_end:
            continue
        first_page = start // VIRTUAL_S_PAGE_BYTES
        last_page = (flash_end - 1) // VIRTUAL_S_PAGE_BYTES
        overlapping = [bank for bank in range(first_page, last_page + 1) if bank in banks]
        if overlapping:
            collisions.append({
                "section_start": f"0x{start:06X}", "section_end_exclusive": f"0x{end:06X}",
                "executable": bool(flags & 4), "bytes": size,
                "overlapping_s_banks": [f"0x{bank:02X}" for bank in overlapping],
            })
    return {
        "elf_sha256": identity["sha256"],
        "scope": "allocated ELF sections intersecting internal Flash",
        "observed_selector_entry": f"0x{VIRTUAL_CONFIG:06X}",
        "s_banks_replayed": len(banks),
        "overlaps_stock_selector_pages": bool(collisions),
        "collisions": collisions,
        "physical_remapping_verified": False,
        "external_service_admission_verified": False,
    }


def check(base, compiler, placement_elf=None):
    identity = identify_h03(base)
    rom = base.read_bytes()
    if sha256(rom).hexdigest() != identity["sha256"]:
        raise ValueError("H03 changed while the simulator fixture was being prepared")
    if rom[0x958:0x960] != bytes.fromhex("000200000002fffe"):
        raise ValueError("Unexpected sector start or last even address in the H03 geometry table")

    sector_byte = START + 0x123
    changed_byte = ("unsigned char", sector_byte, 0x5A)
    stock_sum = sum(rom) & 0xFFFF
    changed_sum = (stock_sum - rom[sector_byte] + changed_byte[2]) & 0xFFFF
    boot_cases = [
        ("original", APPLICATION, ()),
        ("sector_has_content", APPLICATION, (changed_byte,)),
        ("begin_marker_changed", RECOVERY, (("unsigned short", 0x008000, 0),)),
        ("end_marker_changed", RECOVERY, (("unsigned short", 0x07FFFE, 0),)),
    ]
    erase_cases = [(0x008000, 0x080000, True), (0x010000, 0x020000, True),
                   (START, LIMIT, True), (0x010000, LIMIT, True),
                   (START + 1, LIMIT, False), (START, LIMIT - 1, False),
                   (START, LIMIT + 1, False), (LIMIT, 0x040000, False)]

    with TemporaryDirectory(prefix="rbm-h03-flash-policy-") as directory:
        work = Path(directory)

        def run(*args):
            return subprocess.run([str(arg) for arg in args], cwd=work, check=True,
                                  capture_output=True, timeout=30).stdout

        if run(compiler, "-dumpmachine").strip() != b"m32r-elf":
            raise ValueError("A bare-metal M32R compiler is required")
        version = run(compiler, "--version").decode().splitlines()[0]
        gdb = compiler.with_name(f"m32r-elf-gdb{compiler.suffix}")
        (work / "stock.dat").write_bytes(rom)
        (work / "fixture.S").write_text(FIXTURE, encoding="ascii")
        (work / "fixture.ld").write_text(LAYOUT, encoding="ascii")
        run(compiler, "-m32r", "-Wa,-EB", "-nostdlib", "-Wl,-T,fixture.ld", "fixture.S", "-o", "fixture.elf")

        for name, expected, changes in boot_cases:
            pc, *_ = replay(run, work, gdb, hex(BOOT), (hex(APPLICATION), hex(RECOVERY)), memory=changes)
            if pc != expected:
                raise ValueError(f"Unexpected H03 reset flow for {name}: {pc:#x}")

        for start, end, allowed in erase_cases:
            pc, r0, r1, *_ = replay(run, work, gdb, hex(ERASE_POLICY),
                                      (hex(ERASE_CALL), hex(ERASE_DENIED)), (start, end, 0))
            if allowed and (pc, r0, r1) != (ERASE_CALL, start, end - start):
                raise ValueError(f"Unexpected dispatched erase range {start:#x}..{end:#x}")
            if not allowed and pc != ERASE_DENIED:
                raise ValueError(f"Unexpectedly accepted erase range {start:#x}..{end:#x}")

        location = LIMIT - 3
        received = tuple(("unsigned char", 0x808117 + index, byte) for index, byte in enumerate(b"\x12\x34\x56"))
        on_flash = tuple((kind, location + index, byte) for index, (kind, _, byte) in enumerate(received))
        for expected, actual in ((0, on_flash), (0xFFFF, (*on_flash[:-1], ("unsigned char", LIMIT - 1, 0x55)))):
            pc, _, _, mismatch, *_ = replay(run, work, gdb, hex(READBACK), (hex(READBACK_DONE),),
                                             (len(received), 0, location), (*received, *actual))
            if pc != READBACK_DONE or mismatch != expected:
                raise ValueError("Unexpected H03 readback comparison result")

        for expected, changes in ((stock_sum, ()), (changed_sum, (changed_byte,))):
            memory = (("unsigned char", 0x804887, 4), *changes)
            pc, _, _, _, total, cursor, *_ = replay(run, work, gdb, "&fixture_sum", ("fixture_sum_done",), memory=memory)
            if pc < 0x100000 or (total, cursor) != (expected, len(rom)):
                raise ValueError(f"Unexpected H03 diagnostic sum {total:#x} at cursor {cursor:#x}")

        banks = tuple(range(len(rom) // VIRTUAL_S_PAGE_BYTES)) if placement_elf else (0x20, 0x2F)
        selected_banks = set()
        for bank in banks:
            memory = (("unsigned int", 0x809F9C, 0x809F9C), ("unsigned short", VIRTUAL_SELECT, bank))
            pc, *_, control, selection = replay(run, work, gdb, hex(VIRTUAL_CONFIG), (hex(VIRTUAL_CONFIG_DONE),),
                                                memory=memory, initial_r0=0x807000)
            if (pc, control, selection) != (VIRTUAL_CONFIG_DONE, 1, 0x8000 | bank):
                raise ValueError(f"Unexpected virtual Flash register shadow for bank {bank:#x}")
            selected_banks.add(bank)

    report = {
        "base": identity,
        "compiler": version,
        "sector": [f"0x{START:06X}", f"0x{LIMIT:06X}"],
        "flash_erase_table_address": "0x000958",
        "flash_erase_last_even_address": "0x02FFFE",
        "boot_dispatch": {name: f"0x{expected:06X}" for name, expected, _ in boot_cases},
        "erase_parser": [{"start": f"0x{start:06X}", "end": f"0x{end:06X}", "allowed": allowed}
                         for start, end, allowed in erase_cases],
        "readback_equality_and_mismatch_verified": True,
        "virtual_flash_selector_register_shadow_cases": [f"0x{0x8000 | bank:04X}" for bank in banks],
        "raw_reference_candidates_outside_the_sector": reference_candidates(rom),
        "stock_diagnostic_sum": f"0x{stock_sum:04X}",
        "diagnostic_sum_after_simulated_sector_change": f"0x{changed_sum:04X}",
        "ends_are_exclusive": True,
        "physical_erase_or_write_executed": False,
        "programmer_compatibility_verified": False,
    }
    if placement_elf:
        report["placement"] = check_placement(placement_elf, len(rom), selected_banks)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--gcc", required=True, type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--placement-elf", type=Path,
                        help="Check all stock S-bank selections against an addressed H03 application ELF")
    args = parser.parse_args()
    try:
        inputs = [path for path in (args.base, args.placement_elf) if path]
        if args.out and any(args.out.resolve() == path.resolve() or
                            (args.out.exists() and args.out.samefile(path)) for path in inputs):
            raise ValueError("The report and input files must use different paths")
        result = check(args.base, args.gcc.resolve(), args.placement_elf)
        report = json.dumps(result, indent=2) + "\n"
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(report, encoding="utf-8")
        print(report, end="")
        if args.placement_elf and result["placement"]["overlaps_stock_selector_pages"]:
            parser.exit(2, "ELF sections overlap pages selectable by the stock H03 Virtual Flash routine\n")
    except subprocess.CalledProcessError as error:
        message = error.stderr or error.stdout or str(error).encode()
        parser.exit(1, message.decode(errors="replace") + "\n")
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
