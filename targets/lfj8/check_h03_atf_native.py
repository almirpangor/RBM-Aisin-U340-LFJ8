"""Compare stock H03 ATF against the candidate hooks in the M32R simulator."""

import argparse
from hashlib import sha256
from pathlib import Path
import re
import struct
import subprocess
from tempfile import TemporaryDirectory

from check_h03_link import identify_h03


SITES = (0x03B130, 0x03B138, 0x03B178, 0x03B1A4, 0x03B1B0, 0x03B218)
HOOKS = (
    (0x03B110, "begin", "2e7f287f"),
    (0x040178, "adc", "20252eef"),
    (0x03B138, "read", "20b4f000"),
    (0x03B178, "fault", "20467f29"),
    (0x03B1A4, "direct", "20447f1e"),
    (0x03B218, "filtered", "2044f000"),
    (0x03B21C, "end", "28ef2eef"),
)
FIXTURE_FIELDS = (
    "irq_enabled", "acquisitions", "reads", "site", "source", "valid", "sample_us", "q8",
)
REGISTERS = [f"$r{i}" for i in range(13)] + ["$fp", "$lr", "$sp", "$psw", "$accl", "$acch"]
CONTINUATIONS = (0x04017C, 0x03B114, 0x03B13C, 0x03B21C, 0x03B220)
VOLTS = 0x804F04
TEMPERATURE = 0x805028
INITIAL_TEMP = 0x41A00000  # 20 C


def run(*command, directory):
    result = subprocess.run(command, cwd=directory, capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise ValueError(f"{Path(command[0]).name} failed: {result.stderr or result.stdout}")
    return result.stdout


def emulate(directory, debugger, patches, mode, fault, phase, divider, rom_override=None,
            clock_fail=0):
    commands = [
        "set confirm off", "target sim --memory-size 16M", "load",
        "tbreak *_start", "run",
        f"set {{unsigned int}}{TEMPERATURE:#x} = {INITIAL_TEMP:#x}",
        f"set {{unsigned short}}0x0166a4 = {mode}",
        f"set {{unsigned char}}0x8063e7 = {fault}",
        f"set {{unsigned short}}0x80621a = {phase}",
        f"set {{unsigned short}}0x806234 = {divider}",
        f"set atf_fixture_clock_fail = {clock_fail}",
    ]
    commands.extend(f"set {{unsigned int}}{site:#x} = {branch:#x}" for site, branch in patches.items())
    if rom_override is not None:
        commands.append(f"set {{unsigned int}}0x016840 = {rom_override:#x}")
    for site in SITES:
        commands.extend((f"tbreak *{site:#x}", "commands", "silent",
                         f'printf "SITE {site:06x}\\n"', "continue", "end"))
    if mode == 400:
        # Reuse a stack slot containing a plausible timestamp from an older call.
        commands.extend((
            "tbreak *0x03b110", "commands", "silent",
            "set {unsigned int}($sp - 16) = 1", "set {unsigned int}($sp - 12) = 100",
            "continue", "end",
        ))
    register_args = ", ".join(REGISTERS)
    register_format = "%08x " * len(REGISTERS)
    for site in CONTINUATIONS:
        commands.extend((f"break *{site:#x}", "commands", "silent",
                         f'printf "CONTEXT {site:06x} {register_format}\\n", {register_args}',
                         "continue", "end"))
    commands.extend((
        "tbreak *fixture_done", "continue",
        f'printf "VALUES %08x %08x\\n", *(unsigned int*){VOLTS:#x}, '
        f'*(unsigned int*){TEMPERATURE:#x}',
        f'printf "REGS {register_format}\\n", {register_args}',
        "tbreak *fixture_observed", "continue",
        f'printf "ATF {"%08x " * len(FIXTURE_FIELDS)}\\n", '
        + ", ".join(f"atf_fixture_{field}" for field in FIXTURE_FIELDS),
    ))
    script = directory / "probe.gdb"
    script.write_text("\n".join(commands) + "\n", encoding="ascii")
    log = run(debugger, "--batch", "-nx", "-x", script.name, "stock.elf", directory=directory)
    values = re.search(r"^VALUES ([0-9a-f]{8}) ([0-9a-f]{8})$", log, re.M)
    regs = re.search(r"^REGS ((?:[0-9a-f]{8} ){19})$", log, re.M)
    atf = re.search(r"^ATF ((?:[0-9a-f]{8} ){8})$", log, re.M)
    if None in (values, regs, atf):
        raise ValueError(f"ATF routine did not return to the fixture: {log[-1500:]}")
    trace = tuple(int(site, 16) for site in re.findall(r"^SITE ([0-9a-f]{6})$", log, re.M))
    voltage, temperature = (int(word, 16) for word in values.groups())
    contexts = []
    in_temperature_call = False
    for site_hex, words in re.findall(r"^CONTEXT ([0-9a-f]{6}) ((?:[0-9a-f]{8} ){19})$", log, re.M):
        site = int(site_hex, 16)
        state = [int(word, 16) for word in words.split()]
        if site == 0x03B114:
            in_temperature_call = True
        elif site == 0x03B220:
            in_temperature_call = False
        if 0x03B110 in patches and in_temperature_call:
            state[15] += 8
        contexts.append((site, tuple(state)))
    return (trace, voltage, temperature, regs[1], contexts), tuple(int(field, 16) for field in atf[1].split())


def branch_patch(rom, site, target, stock_word, opcode):
    offset = target - site
    if rom[site:site + 4] != bytes.fromhex(stock_word) or offset % 4 or not -(1 << 25) <= offset < 1 << 25:
        raise ValueError(f"The OEM word or branch displacement at {site:#x} is unexpected")
    return opcode | (offset // 4 & 0xFFFFFF)


def branch_patches(rom, directory, gcc):
    nm = gcc.with_name(f"m32r-elf-nm{gcc.suffix}")
    symbols = {name: int(address, 16) for address, name in
               re.findall(r"^([0-9a-f]+) T (\w+)$", run(nm, "stock.elf", directory=directory), re.M)}
    patches = {site: branch_patch(rom, site, symbols[f"rbm_h03_atf_{name}"], expected, 0xFF000000)
               for site, name, expected in HOOKS}
    replacement = branch_patch(rom, 0x03B13C, symbols["fixture_replace_adc"], "feff5049", 0xFE000000)
    return patches, {0x03B13C: replacement}


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
        ("new AN1 with identical bits", (0, 0, 0, 0),
         (0x03B138, 0x03B1A4), measured_voltage),
        ("clock absent at ADC", (0, 0, 0, 0, None, 1),
         (0x03B138, 0x03B1A4), measured_voltage),
        ("clock lost at publication", (0, 0, 0, 0, None, 2),
         (0x03B138, 0x03B1A4), measured_voltage),
        ("clock lost at foreground read", (0, 0, 0, 0, None, 4),
         (0x03B138, 0x03B1A4), measured_voltage),
    )
    with TemporaryDirectory(prefix="rbm-h03-atf-") as temp:
        directory = Path(temp)
        (directory / "h03.bin").write_bytes(rom)
        here = Path(__file__).resolve().parent
        (directory / "stock.S").write_text(
            '.section .oem,"ax"\n.incbin "h03.bin"\n'
            '.section .text,"ax"\n.global _start, fixture_done, fixture_observed, fixture_replace_adc\n'
            '_start:\n  ld24 sp,#0x9ffffc\n  ldi r0,#0x41\n  mvtc r0,psw\n'
            '  ld24 r0,#0x12345\n  mvtachi r0\n  ld24 r0,#0x234567\n  mvtaclo r0\n'
            '  bl acquire\n  ld24 r4,#0x03b110\n  jl r4\n'
            'fixture_done:\n  setpsw #0x40\n  bl atf_fixture_observe\n'
            'fixture_observed:\n  nop\n  .p2align 2\n'
            'acquire:\n  push lr\n  ldi r0,#315\n  ld24 r5,#0x804bc4\n  bra h03_atf_adc_store\n'
            '  .p2align 2\nfixture_replace_adc:\n  push lr\n  push r0\n  push r5\n'
            '  ld24 r5,#atf_fixture_adc_us\n  ldi r0,#101\n  st r0,@r5\n'
            '  bl acquire\n  pop r5\n  pop r0\n  pop lr\n  bra h03_atf_oem_convert\n',
            encoding="ascii",
        )
        (directory / "stock.ld").write_text(
            "ENTRY(_start)\nSECTIONS { .oem 0 : { KEEP(*(.oem)) } "
            ".text 0x100000 : { KEEP(*(.text.rbm_h03_atf_hooks)) *(.text*) *(.rodata*) } }\n"
            "h03_atf_after_begin = 0x03b114; h03_atf_adc_store = 0x040178;\n"
            "h03_atf_after_adc = 0x04017c; h03_atf_after_read = 0x03b13c;\n"
            "h03_atf_resume_done = 0x03b21c; h03_atf_after_end = 0x03b220;\n"
            "h03_atf_oem_convert = 0x00f260;\n", encoding="ascii",
        )
        run(gcc, "-m32r", "-Wa,-EB", "-mmodel=medium", "-msdata=none",
            "-Os", "-g", "-Wall", "-Wextra", "-Werror", "-ffreestanding", "-fno-builtin",
            "-ffunction-sections", "-fdata-sections", "-nostdlib",
            "-Wl,-T,stock.ld,--gc-sections", "-Wl,--wrap=rbm_h03_atf_adc_callback",
            "-Wl,--wrap=rbm_h03_atf_source_callback", "-Wl,--wrap=rbm_h03_atf_publish_callback",
            "stock.S", here / "h03_atf_hooks.S", here / "h03_atf_hook_fixture.c",
            here / "lfj8_h03_atf_target.c", here / "lfj8_h03_atf.c", here / "lfj8_h03_mmio.c",
            "-o", "stock.elf", directory=directory)
        patches, replacement = branch_patches(rom, directory, gcc)
        temperatures = {}
        for label, inputs, expected, expected_voltage in cases:
            replaced = label == "new AN1 with identical bits"
            interruption = replacement if replaced else {}
            stock, _ = emulate(directory, debugger, interruption, *inputs)
            hooked, fixture = emulate(directory, debugger, patches | interruption, *inputs)
            if hooked != stock:
                raise ValueError(f"{label}: OEM outcome or CPU context differs: {stock!r} vs {hooked!r}")
            trace, voltage, temperature, _, contexts = stock
            if trace != expected or voltage != expected_voltage:
                raise ValueError(f"{label}: path or voltage differs: {trace!r}, {voltage:08x}")
            reads = int(0x03B138 in expected)
            expected_continuations = [0x04017C, 0x03B114]
            if reads:
                expected_continuations.append(0x03B13C)
            if replaced:
                expected_continuations.append(0x04017C)
            expected_continuations.extend([0x03B21C, 0x03B220])
            if [site for site, _ in contexts] != expected_continuations:
                raise ValueError(f"{label}: unexpected sequence of OEM continuations")
            temperatures[label] = temperature
            site = expected[-1] if label != "skipped" else 0
            measured = label in ("direct", "filtered")
            source_read = measured or replaced or label in ("clock lost at publication", "clock lost at foreground read")
            source = 100 if source_read else (0xFFFFFFFF if site else 0)
            q8 = {"direct": 25600, "filtered": 16640}.get(label, 0)
            acquisitions = 2 if replaced else int(label != "clock absent at ADC")
            if fixture != (0, acquisitions, reads, site, source, int(measured), 100 if measured else 0, q8):
                raise ValueError(f"{label}: unexpected adapter outcome (IRQ, ADC, read, publication): {fixture!r}")
            print(f"{label}: {' -> '.join(f'{site:06x}' for site in trace)}, {temperature:08x}")
    direct = struct.unpack(">f", temperatures["direct"].to_bytes(4, "big"))[0]
    filtered = struct.unpack(">f", temperatures["filtered"].to_bytes(4, "big"))[0]
    if not (59 < direct < 61 and abs(filtered - (20 + (direct - 20) / 8)) < 0.001
            and temperatures["skipped"] == INITIAL_TEMP and temperatures["fault"] == 0xC2480000
            and temperatures["rom voltage equals AN1"] == temperatures["direct"]
            and temperatures["new AN1 with identical bits"] == temperatures["direct"]):
        raise ValueError(f"Unexpected stock temperature results: {temperatures!r}")
    print(f"PASS: {len(cases)} stock/hooked ATF pairs, base SHA-256 {identity['sha256']}")


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
