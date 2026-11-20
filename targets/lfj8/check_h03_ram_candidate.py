"""Audit candidate H03 RAM against fixed references and selected OEM initializers."""
import argparse
from collections import defaultdict
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from check_h03_link import identify_h03


RAM_START = 0x804000
RAM_END = 0x80A000
SPI = 0x809EFC
FP = 0x808000
FILL = 0xA5
WINDOW = (0x806B40, 0x807000)
FIXTURE_RETURN = 0x001010
CAPTURE_DMA_SFR = (0x800410, 0x800426)
CAPTURE_DMA_CONFIG = {
    0x800410: bytes.fromhex("31 05 0f f4 6a ce"),
    0x800420: bytes.fromhex("31 05 0f f6 6a da"),
}
ROM_FRAGMENTS = (
    (0x030011, 0x030012),
    (0x03001B, 0x03001D),
    (0x030020, 0x031022),
    (0x008A04, 0x008A7C),
    (0x009184, 0x009198),
    (0x00AACC, 0x00AB44),
    (0x00D108, 0x00D28C),
    (0x00D4F8, 0x00D544),
    (0x00F0EC, 0x00F118),
    (0x0404C4, 0x040508),
    (0x0405C0, 0x0405CC),
)


def hex_address(address):
    return f"0x{address:06X}"


def fixed_reference_candidates(rom):
    """Scan aligned instruction encodings and aligned literal words."""
    hits = defaultdict(list)
    lower, upper = WINDOW
    for offset in range(0, len(rom) - 3, 4):
        word = int.from_bytes(rom[offset:offset + 4], "big")
        opcode = word >> 16
        if word >> 28 == 0xE and lower - 3 <= (word & 0xFFFFFF) < upper:
            hits["LD24"].append((offset, word & 0xFFFFFF))
        if lower - 3 <= word < upper:
            hits["aligned_u32"].append((offset, word))
        if opcode & 0xF00F == 0xA00D or opcode & 0xF0FF == 0x80AD:
            displacement = int.from_bytes(rom[offset + 2:offset + 4], "big", signed=True)
            address = FP + displacement
            if lower - 3 <= address < upper:
                hits["FP_relative"].append((offset, address))
    for offset in range(1, len(rom) - 3):
        if offset % 4 != 0:
            word = int.from_bytes(rom[offset:offset + 4], "big")
            if lower <= word < upper:
                hits["unaligned_u32"].append((offset, word))
    return {
        name: [{"rom_offset": hex_address(offset), "ram_address": hex_address(address)}
               for offset, address in hits[name]]
        for name in ("LD24", "aligned_u32", "FP_relative", "unaligned_u32")
    }


def expected_cases(rom):
    return (
        ("application_clear", 0x0404C4, 0x040504, {
            0x804810: bytes(0x8066B4 - 0x804810),
            0x804ADE: b"\x01",
            0x80485F: bytes((5, 1, rom[0x030011], 1)),
        }, True),
        ("can_records_initializer", 0x008A04, FIXTURE_RETURN, {
            0x8066C4 + 14 * index: bytes(13) for index in range(16)
        }, False),
        ("capture_dma_initializer", 0x00AACC, FIXTURE_RETURN, {
            0x806ACE: bytes(0x18),
        }, False),
        ("configuration_clear_fragment", 0x0405C0, 0x0405CC, {
            0x804004: bytes(0x80480E - 0x804004),
        }, False),
        ("stock_service_profile_gate", 0x00D108, 0x00D27C, {
            0x8066AC: b"\x00",
        }, True),
        ("service_buffer_initializer", 0x00D4F8, FIXTURE_RETURN, {
            0x80692E: bytes(4),
            0x807000: rom[0x030022:0x031022],
        }, True),
    )


def simulator_checks(rom, compiler):
    with TemporaryDirectory(prefix="rbm-h03-ram-candidate-") as folder:
        work = Path(folder)
        sections = ["ENTRY(_start)", "SECTIONS {",
                    "  .start 0x1000 : { *(.start) }"]
        assembly = [
            '    .section .start,"ax",@progbits',
            "    .global _start",
            "_start:",
            f"    ld24 sp,#{SPI:#x}",
            f"    ld24 r13,#{FP:#x}",
            "    ld24 r0,#ENTRY_ADDRESS",
            "    jl r0",
            "    nop",
            "fixture_return:",
            "    bra fixture_return",
        ]
        for index, (start, end) in enumerate(ROM_FRAGMENTS):
            fragment = f"rom{index}"
            (work / f"{fragment}.dat").write_bytes(rom[start:end])
            assembly.extend((f'    .section .{fragment},"ax",@progbits',
                             f'    .incbin "{fragment}.dat"'))
            sections.append(f"  .{fragment} {start:#x} : {{ *(.{fragment}) }}")
        sections.extend(("  /DISCARD/ : { *(.note*) *(.comment) }", "}"))
        (work / "fixture.ld").write_text("\n".join(sections) + "\n", encoding="ascii")
        (work / "fixture.S").write_text("\n".join(assembly) + "\n", encoding="ascii")

        def run(*command):
            return subprocess.run(command, cwd=work, capture_output=True, check=True,
                                  timeout=20).stdout

        if run(str(compiler), "-dumpmachine").strip() != b"m32r-elf":
            raise ValueError("A bare-metal M32R compiler is required")
        gdb = compiler.with_name(f"m32r-elf-gdb{compiler.suffix}")
        reports = []
        for name, entry, stop, expected_writes, pushes_lr in expected_cases(rom):
            run(str(compiler), "-m32r", "-Wa,-EB", "-nostdlib", "-Wl,-T,fixture.ld",
                f"-DENTRY_ADDRESS={entry:#x}", "fixture.S", "-o", "fixture.elf")
            dma_case = name == "capture_dma_initializer"
            dma_dump = ""
            if dma_case:
                dma_start, dma_end = CAPTURE_DMA_SFR
                dma_dump = f"dump binary memory dma.dat {dma_start:#x} {dma_end:#x}\n"
            (work / "check.gdb").write_text(
                "set confirm off\n"
                f"target sim --memory-fill {FILL:#x} --memory-region 0x0,0x1000000\n"
                "load\n"
                "tbreak *_start\n"
                "run\n"
                f"dump binary memory before.dat {RAM_START:#x} {RAM_END:#x}\n"
                f"tbreak *{stop:#x}\n"
                "continue\n"
                f"dump binary memory after.dat {RAM_START:#x} {RAM_END:#x}\n"
                f"{dma_dump}"
                'printf "H03 stop: %x\\n", $pc\n', encoding="ascii"
            )
            if name == "stock_service_profile_gate" and rom[0x03001B:0x03001D] != bytes(2):
                raise ValueError("Unexpected H03 service profile")
            before = bytes([FILL]) * (RAM_END - RAM_START)
            expected = bytearray(before)
            for address, data in expected_writes.items():
                offset = address - RAM_START
                expected[offset:offset + len(data)] = data
            if pushes_lr:
                slot = SPI - 4 - RAM_START
                expected[slot:slot + 4] = FIXTURE_RETURN.to_bytes(4, "big")
            confirmation = run(str(gdb), "--batch", "-nx", "-x", "check.gdb", "fixture.elf")
            after = (work / "after.dat").read_bytes()
            if (f"H03 stop: {stop:x}".encode() not in confirmation or
                    (work / "before.dat").read_bytes() != before or after != expected):
                raise ValueError(f"Unexpected CPU or RAM snapshot in {name}")
            lower, upper = (address - RAM_START for address in WINDOW)
            if dma_case:
                dma_registers = bytearray([FILL]) * (dma_end - dma_start)
                for address, data in CAPTURE_DMA_CONFIG.items():
                    offset = address - dma_start
                    dma_registers[offset:offset + len(data)] = data
                if (work / "dma.dat").read_bytes() != dma_registers:
                    raise ValueError("Unexpected capture DMA register setup")
            reports.append({
                "case": name,
                "rom_entry": hex_address(entry),
                "stop": hex_address(stop),
                "ram_bytes_compared": len(after),
                "changed_bytes": sum(a != b for a, b in zip(before, after)),
                "candidate_unchanged": before[lower:upper] == after[lower:upper],
                **({"capture_dma_sfr_values_verified": True} if dma_case else {}),
            })
    return reports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--gcc", required=True, type=Path)
    args = parser.parse_args()
    try:
        identity = identify_h03(args.base)
        rom = args.base.read_bytes()
        if sha256(rom).hexdigest() != identity["sha256"]:
            raise ValueError("H03 changed during the audit")
        report = {
            "base": identity,
            "candidate": list(map(hex_address, WINDOW)),
            "candidate_bytes": WINDOW[1] - WINDOW[0],
            "range_end_exclusive": True,
            "fixed_reference_candidates": fixed_reference_candidates(rom),
            "simulated_initializers": simulator_checks(rom, args.gcc.resolve()),
            "indirect_service_writer_rom": ["0x00DBBC", "0x00DC10"],
            "writer_dispatch_disabled_in_this_rom": {
                "profile_bytes": ["0x03001B", "0x03001C"],
                "selector_byte": "0x8066AC",
                "skipped_dispatch_calls": ["0x00D154", "0x00D1F0"],
            },
            "separate_oem_monitor": {
                "configured_rom_byte_at_0x000201": rom[0x000201],
                "candidate_ownership_restricted_by_other_monitor_paths": True,
            },
            "physical_hardware_executed": False,
            "ram_ownership_verified": False,
            "irq_stack_bound_verified": False,
        }
        print(json.dumps(report, indent=2))
    except subprocess.CalledProcessError as error:
        message = error.stderr or error.stdout or str(error).encode()
        parser.exit(1, message.decode(errors="replace") + "\n")
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
