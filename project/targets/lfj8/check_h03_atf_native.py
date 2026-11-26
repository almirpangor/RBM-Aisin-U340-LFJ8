"""Compare stock H03 ATF against the candidate hooks in the M32R simulator."""

import argparse
from hashlib import sha256
from pathlib import Path
import re
import struct
import subprocess
from tempfile import TemporaryDirectory

from check_h03_link import identify_h03
from lfj8_h03_sensor_hooks import ATF_HOOKS as HOOKS, STOCK_SYMBOLS, branch_patch


SITES = (0x03B130, 0x03B138, 0x03B178, 0x03B1A4, 0x03B1B0, 0x03B218)
TML0_EVIDENCE = (
    (0x009E78, "e4800202602720046109440121044078"),  # PRS1 = 9 at initialization
    (0x009F18, "e180020320916209b00200022201f000"),  # restore PRS1 if changed
    (0x00A82C, "e28003e021c22140"),                 # stock 32-bit counter read
    (0x00A86C, "e48003eb60012004"),                 # select Clock Bus 1
    (0x00A92C, "e18003eb20916201b00200022201f000"),  # restore TML0CR if changed
)
FIXTURE_FIELDS = (
    "irq_enabled", "acquisitions", "reads", "site", "source", "valid", "sample_us", "q8",
)
REGISTERS = [f"$r{i}" for i in range(13)] + ["$fp", "$lr", "$sp", "$psw", "$accl", "$acch"]
CONTINUATIONS = (0x04017C, 0x03B114, 0x03B13C, 0x03B21C, 0x03B220)
VOLTS = 0x804F04
TEMPERATURE = 0x805028
STACK_END = 0x9FFFFC
STACK_FLOOR = STACK_END - 1024
STACK_STAGES = ("adc", "temperature", "snapshot")
INITIAL_TEMP = 0x41A00000  # 20 C


def run(*command, directory):
    result = subprocess.run(command, cwd=directory, capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise ValueError(f"{Path(command[0]).name} failed: {result.stderr or result.stdout}")
    return result.stdout


def emulate(directory, debugger, patches, mode, fault, phase, divider, rom_override=None,
            clock_fail=0, adc_us=100, publish_us=102, *, stack_word=0xA55A6996):
    stack_seed = stack_word.to_bytes(4, "big") * ((STACK_END - STACK_FLOOR) // 4)
    (directory / "stack.seed").write_bytes(stack_seed)
    seed_stack = f"restore stack.seed binary {STACK_FLOOR:#x}"

    def dump_stack(stage):
        return f"dump binary memory stack-{stage}.bin {STACK_FLOOR:#x} {STACK_END:#x}"

    check_sp = (f"if $sp != {STACK_END:#x}", 'printf "Unbalanced fixture stack: %08x\\n", $sp',
                "quit 1", "end")
    commands = [
        "set confirm off", "target sim --memory-size 16M", "load",
        "tbreak *_start", "run", seed_stack,
        f"set {{unsigned int}}{TEMPERATURE:#x} = {INITIAL_TEMP:#x}",
        f"set {{unsigned short}}0x0166a4 = {mode}",
        f"set {{unsigned char}}0x8063e7 = {fault}",
        f"set {{unsigned short}}0x80621a = {phase}",
        f"set {{unsigned short}}0x806234 = {divider}",
        f"set atf_fixture_clock_fail = {clock_fail}",
        f"set atf_fixture_adc_us = {adc_us:#x}",
        f"set atf_fixture_publish_us = {publish_us:#x}",
    ]
    commands.extend(f"set {{unsigned int}}{site:#x} = {branch:#x}" for site, branch in patches.items())
    if rom_override is not None:
        commands.append(f"set {{unsigned int}}0x016840 = {rom_override:#x}")
    for site in SITES:
        commands.extend((f"tbreak *{site:#x}", "commands", "silent",
                         f'printf "SITE {site:06x}\\n"', "continue", "end"))
    commands.extend(("tbreak *0x03b110", "commands", "silent", *check_sp, dump_stack("adc"), seed_stack))
    if mode == 400:
        # Reuse a stack slot containing a plausible timestamp from an older call.
        commands.extend(("set {unsigned int}($sp - 16) = 1", "set {unsigned int}($sp - 12) = 100"))
    commands.extend(("continue", "end"))
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
        *check_sp, dump_stack("temperature"), seed_stack,
        "tbreak *fixture_observed", "continue", *check_sp, dump_stack("snapshot"),
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
    depths = []
    for stage in STACK_STAGES:
        stack = (directory / f"stack-{stage}.bin").read_bytes()
        if len(stack) != len(stack_seed) or stack[:16] != stack_seed[:16]:
            raise ValueError(f"The stack measurement guard was overwritten during {stage}")
        first_write = next((i for i, (before, after) in enumerate(zip(stack_seed, stack))
                            if before != after), len(stack))
        depths.append(len(stack) - first_write)
    return ((trace, voltage, temperature, regs[1], contexts),
            tuple(int(field, 16) for field in atf[1].split()), tuple(depths))


def measure(directory, debugger, variant, inputs):
    first, adapter, written = emulate(directory, debugger, variant, *inputs)
    second, second_adapter, second_written = emulate(
        directory, debugger, variant, *inputs, stack_word=0x5AA59669)
    if (first, adapter) != (second, second_adapter):
        raise ValueError("Stack fill changed the program's result")
    return first, adapter, tuple(max(left, right) for left, right in zip(written, second_written))


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
    for address, instruction in TML0_EVIDENCE:
        expected = bytes.fromhex(instruction)
        if rom[address:address + len(expected)] != expected:
            raise ValueError(f"Unexpected stock TML0 setup at {address:#x}")
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
        ("clock unqualified at ADC", (0, 0, 0, 0, None, 1),
         (0x03B138, 0x03B1A4), measured_voltage),
        ("PRS1 changed at publication", (0, 0, 0, 0, None, 2),
         (0x03B138, 0x03B1A4), measured_voltage),
        ("TML0 source changed at foreground read", (0, 0, 0, 0, None, 4),
         (0x03B138, 0x03B1A4), measured_voltage),
        ("TML0 rollover", (0, 0, 0, 0, None, 0, 0xFFFFFFFE, 1),
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
            + "".join(f"{name} = {address:#x};\n" for name, address in STOCK_SYMBOLS.items()
                      if name.startswith("h03_atf_"))
            + "h03_atf_adc_store = 0x040178; h03_atf_oem_convert = 0x00f260;\n",
            encoding="ascii",
        )
        run(gcc, "-m32r", "-Wa,-EB", "-mmodel=medium", "-msdata=none",
            "-Os", "-g", "-Wall", "-Wextra", "-Werror", "-ffreestanding", "-fno-builtin",
            "-ffunction-sections", "-fdata-sections", "-nostdlib",
            "-Wl,-T,stock.ld,--gc-sections", "-Wl,--wrap=rbm_h03_atf_adc_callback",
            "-Wl,--wrap=rbm_h03_atf_source_callback", "-Wl,--wrap=rbm_h03_atf_publish_callback",
            "-Wl,--wrap=rbm_h03_atf_now_us",
            "stock.S", here / "h03_atf_hooks.S", here / "h03_atf_hook_fixture.c",
            here / "lfj8_h03_atf_target.c", here / "lfj8_h03_atf_tml0.c",
            here / "lfj8_h03_atf.c", here / "lfj8_h03_mmio.c",
            "-o", "stock.elf", directory=directory)
        patches, replacement = branch_patches(rom, directory, gcc)
        temperatures = {}
        for label, inputs, expected, expected_voltage in cases:
            replaced = label == "new AN1 with identical bits"
            interruption = replacement if replaced else {}
            stock, _, stock_stack = measure(directory, debugger, interruption, inputs)
            hooked, fixture, hooked_stack = measure(directory, debugger, patches | interruption, inputs)
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
            clock_fail = inputs[5] if len(inputs) > 5 else 0
            adc_us = inputs[6] if len(inputs) > 6 else 100
            source_read = reads and site in (0x03B1A4, 0x03B218) and clock_fail != 1
            source = adc_us if source_read else (0xFFFFFFFF if site else 0)
            measured = source_read and not replaced and not clock_fail
            q8 = {0x03B1A4: 25600, 0x03B218: 16640}[site] if measured else 0
            acquisitions = 2 if replaced else int(clock_fail != 1)
            if fixture != (0, acquisitions, reads, site, source, int(measured), adc_us if measured else 0, q8):
                raise ValueError(f"{label}: unexpected adapter outcome (IRQ, ADC, read, publication): {fixture!r}")
            print(f"{label}: stock {stock_stack}, hooked {hooked_stack} bytes "
                  "(AN1 / temperature / foreground read)")
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
