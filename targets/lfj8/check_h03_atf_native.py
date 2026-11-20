"""Trace the stock H03 ATF routine in the M32R simulator."""

import argparse
from hashlib import sha256
from pathlib import Path
import re
import struct
import subprocess
from tempfile import TemporaryDirectory

from check_h03_link import identify_h03


SITES = (0x03B130, 0x03B138, 0x03B178, 0x03B1A4, 0x03B1B0, 0x03B218)
ADC = 0x804BC4
VOLTS = 0x804F04
TEMPERATURE = 0x805028
INITIAL_TEMP = 0x41A00000  # 20 C


def run(*command, directory):
    result = subprocess.run(command, cwd=directory, capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise ValueError(f"{Path(command[0]).name} failed: {result.stderr or result.stdout}")
    return result.stdout


def emulate(directory, debugger, mode, fault, phase, divider, rom_override=None):
    commands = [
        "set confirm off", "target sim --memory-size 16M", "load",
        "tbreak *_start", "run",
        f"set {{unsigned short}}{ADC:#x} = 315",
        f"set {{unsigned int}}{TEMPERATURE:#x} = {INITIAL_TEMP:#x}",
        f"set {{unsigned short}}0x0166a4 = {mode}",
        f"set {{unsigned char}}0x8063e7 = {fault}",
        f"set {{unsigned short}}0x80621a = {phase}",
        f"set {{unsigned short}}0x806234 = {divider}",
    ]
    if rom_override is not None:
        commands.append(f"set {{unsigned int}}0x016840 = {rom_override:#x}")
    for site in SITES:
        commands.extend((f"break *{site:#x}", "commands", "silent",
                         f'printf "SITE {site:06x}\\n"', "continue", "end"))
    commands.extend((
        "tbreak *fixture_done", "continue",
        f'printf "VALUES %08x %08x\\n", *(unsigned int*){VOLTS:#x}, '
        f'*(unsigned int*){TEMPERATURE:#x}',
    ))
    script = directory / "probe.gdb"
    script.write_text("\n".join(commands) + "\n", encoding="ascii")
    log = run(debugger, "--batch", "-nx", "-x", script.name, "stock.elf", directory=directory)
    values = re.search(r"^VALUES ([0-9a-f]{8}) ([0-9a-f]{8})$", log, re.M)
    if values is None:
        raise ValueError(f"ATF routine did not return to the fixture: {log[-1500:]}")
    trace = tuple(int(site, 16) for site in re.findall(r"^SITE ([0-9a-f]{6})$", log, re.M))
    voltage, temperature = (int(word, 16) for word in values.groups())
    return trace, voltage, temperature


def check(base, gcc):
    identity = identify_h03(base)
    rom = base.read_bytes()
    if sha256(rom).hexdigest() != identity["sha256"]:
        raise ValueError("H03 changed after identification")
    debugger = gcc.with_name(f"m32r-elf-gdb{gcc.suffix}")
    measured_voltage = 0x3FC4E000  # 315 * 5 / 1024 as binary32
    rom_voltage = int.from_bytes(rom[0x016840:0x016844], "big")
    cases = (
        ("direct", (0, 0, 0, 0), (0x03B138, 0x03B1A4), measured_voltage),
        ("filtered", (0, 0, 3, 0), (0x03B138, 0x03B1B0, 0x03B218), measured_voltage),
        ("skipped", (0, 0, 3, 1), (0x03B138, 0x03B1B0), measured_voltage),
        ("fault", (0, 1, 0, 0), (0x03B138, 0x03B178), measured_voltage),
        ("rom voltage", (400, 0, 0, 0), (0x03B130, 0x03B1A4), rom_voltage),
        ("rom voltage equals AN1", (400, 0, 0, 0, measured_voltage),
         (0x03B130, 0x03B1A4), measured_voltage),
    )
    with TemporaryDirectory(prefix="rbm-h03-atf-") as temp:
        directory = Path(temp)
        (directory / "h03.bin").write_bytes(rom)
        (directory / "stock.S").write_text(
            '.section .oem,"ax"\n.incbin "h03.bin"\n'
            '.section .text,"ax"\n.global _start, fixture_done\n'
            '_start:\n  ld24 sp,#0x9ffffc\n  ld24 r4,#0x03b110\n  jl r4\n'
            'fixture_done:\n  nop\n', encoding="ascii",
        )
        (directory / "stock.ld").write_text(
            "ENTRY(_start)\nSECTIONS { .oem 0 : { *(.oem) } "
            ".text 0x100000 : { *(.text) } }\n", encoding="ascii",
        )
        run(gcc, "-m32r", "-Wa,-EB", "-nostdlib", "-Wl,-T,stock.ld",
            "stock.S", "-o", "stock.elf", directory=directory)
        temperatures = {}
        for label, inputs, expected, expected_voltage in cases:
            trace, voltage, temperature = emulate(directory, debugger, *inputs)
            if trace != expected or voltage != expected_voltage:
                raise ValueError(f"{label}: path or voltage differs: {trace!r}, {voltage:08x}")
            temperatures[label] = temperature
            print(f"{label}: {' -> '.join(f'{site:06x}' for site in trace)}, {temperature:08x}")
    direct = struct.unpack(">f", temperatures["direct"].to_bytes(4, "big"))[0]
    filtered = struct.unpack(">f", temperatures["filtered"].to_bytes(4, "big"))[0]
    if not (59 < direct < 61 and abs(filtered - (20 + (direct - 20) / 8)) < 0.001
            and temperatures["skipped"] == INITIAL_TEMP and temperatures["fault"] == 0xC2480000
            and temperatures["rom voltage equals AN1"] == temperatures["direct"]):
        raise ValueError(f"Unexpected stock temperature results: {temperatures!r}")
    print(f"PASS: {len(cases)} H03 ATF scenarios, base SHA-256 {identity['sha256']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--gcc", required=True, type=Path)
    args = parser.parse_args()
    try:
        check(args.base.resolve(), args.gcc.resolve())
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"H03 ATF probe failed: {error}\n")


if __name__ == "__main__":
    main()
