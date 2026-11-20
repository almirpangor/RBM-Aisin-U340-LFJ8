"""Compare stock H03 AN2 acquisition with a selector-mailbox hook on M32R."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
from shutil import copyfile
import subprocess
from tempfile import TemporaryDirectory

from check_h03_foreground import FIXTURE_SECTIONS, CALL_SITE, OEM_ENTRY, OEM_END
from check_h03_link import identify_h03


HERE = Path(__file__).resolve().parent
STORE_SITE = 0x040370
STOCK_WORD = bytes.fromhex("20246103")
RETURN_SITE = STORE_SITE + len(STOCK_WORD)
AN2 = 0x804BC6
AN3 = 0x804BC0
AN3_SENTINEL = 0xCAFE
HOOK_FRAME_BYTES = 44
REGISTERS = [f"$r{i}" for i in range(13)] + ["$fp", "$lr", "$sp", "$psw", "$acch", "$accl"]


def run(directory, *command):
    try:
        result = subprocess.run(command, cwd=directory, capture_output=True, text=True, timeout=20)
    except subprocess.TimeoutExpired as error:
        output = error.output or ""
        if isinstance(output, bytes):
            output = output.decode(errors="replace")
        raise ValueError(f"{Path(command[0]).name} timed out: {output[-2000:]}") from error
    if result.returncode:
        raise ValueError(f"{Path(command[0]).name} failed: {result.stderr or result.stdout}")
    return result.stdout


def probe(directory, debugger, branch, sample, psw, captured_us, pending, clock_available):
    register_format = " ".join(["%08x"] * len(REGISTERS))
    register_args = ", ".join(REGISTERS)
    commands = [
        "set confirm off", "set pagination off", "target sim --memory-size 16M", "load",
        "tbreak *_start", "run",
        # Configure the fixture's first LDI r0,#0x40. The old GNU simulator
        # does not support setting CR0 directly through GDB.
        'printf "BOOT %04x\\n", *(unsigned short*)&_start',
        f"set {{unsigned short}}&_start = {0x6000 | psw:#x}",
        # Only the reduced ADC peripheral result is simulated. Low bits are noise
        # to check that H03, not the hook, performs the right shift.
        f"set {{unsigned short}}((char*)&mock_adc_results + 4) = {(sample << 6) | 0x3F:#x}",
        f"set variable selector_fixture_captured_us = {captured_us:#x}",
        f"set variable selector_fixture_clock_available = {int(clock_available)}",
        "set variable rbm_h03_selector_adc_state.pending_raw = 65535",
        "set variable rbm_h03_selector_adc_state.pending_event = 0",
        f"set {{unsigned short}}{AN2:#x} = 0xffff",
        f"set {{unsigned short}}{AN3:#x} = {AN3_SENTINEL:#x}",
    ]
    if pending:
        commands.extend((
            "set variable rbm_h03_selector_adc_state.pending_us = 98",
            "set variable rbm_h03_selector_adc_state.pending_raw = 512",
            "set variable rbm_h03_selector_adc_state.pending_event = 1",
        ))
    if branch is not None:
        commands.append(f"set {{unsigned int}}{STORE_SITE:#x} = {branch:#x}")
    # The simulator implements breakpoints with traps. Do not stop between
    # fixture initialization and the first instruction after the hook.
    commands.extend((
        f"tbreak *{RETURN_SITE:#x}", "continue",
        f'printf "CONT {register_format}\\n", {register_args}',
        "tbreak *snapshot_return", "continue",
        f'printf "EXIT {register_format}\\n", {register_args}',
        'printf "CALL %08x %08x %08x %08x %08x %08x\\n", selector_fixture_calls, '
        'selector_fixture_psw, selector_fixture_argument, selector_fixture_stock_word, '
        'selector_fixture_an3_before, selector_fixture_callback_sp',
        'printf "MAIL %08x %08x %08x\\n", rbm_h03_selector_adc_state.pending_event, '
        'rbm_h03_selector_adc_state.pending_raw, rbm_h03_selector_adc_state.pending_us',
        f'printf "RAM %08x %08x %08x %08x\\n", *(unsigned short*){AN2:#x}, '
        f'*(unsigned short*){AN3:#x}, *(unsigned short*)0x804bca, *(unsigned char*)0x804ae6',
    ))
    script = directory / "selector.gdb"
    script.write_text("\n".join(commands) + "\n", encoding="ascii")
    log = run(directory, debugger, "--batch", "-nx", "-x", script.name, "selector.elf")
    if not re.search(r"^BOOT 6040$", log, re.M):
        raise ValueError("The fixture no longer starts with LDI r0,#0x40")
    result = {}
    for key, words in (("CONT", 19), ("EXIT", 19), ("CALL", 6), ("MAIL", 3), ("RAM", 4)):
        match = re.search(rf"^{key} ((?:[0-9a-f]{{8}} ){{{words - 1}}}[0-9a-f]{{8}})$", log, re.M)
        if match is None:
            raise ValueError(f"The simulator did not record {key}: {log[-1800:]}")
        result[key] = tuple(int(word, 16) for word in match[1].split())
    return result


def check(base, gcc):
    identity = identify_h03(base)
    rom = base.read_bytes()
    if sha256(rom).hexdigest() != identity["sha256"]:
        raise ValueError("H03 changed during identification")
    call = rom[CALL_SITE:CALL_SITE + 4]
    if call[0] != 0xFE or CALL_SITE + 4 * int.from_bytes(call[1:], "big", signed=True) != OEM_ENTRY:
        raise ValueError("Unexpected stock call to the H03 foreground routine")
    if rom[STORE_SITE:RETURN_SITE] != STOCK_WORD:
        raise ValueError("The H03 AN2 store bundle differs from the expected word")

    with TemporaryDirectory(prefix="rbm-h03-selector-") as temp:
        directory = Path(temp)
        (directory / "call-site.dat").write_bytes(call)
        (directory / "stock-task.dat").write_bytes(rom[OEM_ENTRY:OEM_END])
        sections = "\n".join(f"  {section} {address:#x} : {{ KEEP(*({section})) }}"
                             for section, address in FIXTURE_SECTIONS)
        (directory / "selector.ld").write_text(
            f"ENTRY(_start)\nSECTIONS {{\n{sections}\n"
            "  .text 0x110000 : { KEEP(*(.text.rbm_h03_selector_adc_hook)) *(.text*) *(.rodata*) }\n"
            "  .data : { *(.data*) }\n"
            "  .bss : { *(.bss*) *(COMMON) }\n"
            f"}}\nh03_selector_adc_resume = {RETURN_SITE:#x};\n", encoding="ascii",
        )
        if run(directory, gcc, "-dumpmachine").strip() != "m32r-elf":
            raise ValueError("A bare-metal M32R compiler is required")
        version = run(directory, gcc, "--version").splitlines()[0]
        sources = ("h03_foreground_test.S", "h03_selector_adc_hook.S",
                   "h03_selector_adc_fixture.c", "lfj8_h03_input_target.c",
                   "lfj8_selector_adc.c", "lfj8_h03_mmio.c")
        headers = ("lfj8_selector_adc.h", "lfj8_h03_mmio.h", "lfj8_h03_engine_rx.h",
                   "lfj8_donor_io.h", "ta2005_chery_inputs.h", "lfj8_h03_atf_target.h",
                   "lfj8_h03_atf.h")
        # Legacy Windows M32R GCC cannot open non-ASCII checkout paths.
        for name in (*sources, *headers):
            copyfile(HERE / name, directory / name)
        run(directory, gcc, "-m32r", "-Wa,-EB", "-mmodel=medium", "-msdata=none",
            "-Os", "-g", "-ffreestanding", "-fno-builtin", "-Wall", "-Wextra", "-Werror",
            "-ffunction-sections", "-fdata-sections", "-nostdlib",
            "-Wl,-T,selector.ld,--gc-sections,--wrap=rbm_h03_selector_adc_capture",
            "-DADC2_SAMPLE=0", "-DINITIAL_FLAG=0",
            *sources, "-o", "selector.elf")
        nm = gcc.with_name(f"m32r-elf-nm{gcc.suffix}")
        symbol = re.search(r"^([0-9a-f]+) T rbm_h03_selector_adc_hook$",
                           run(directory, nm, "selector.elf"), re.M)
        if symbol is None:
            raise ValueError("The selector hook was not linked")
        displacement = int(symbol[1], 16) - STORE_SITE
        if displacement % 4 or not -(1 << 25) <= displacement < 1 << 25:
            raise ValueError("The selector hook is outside wide BRA range")
        branch = 0xFF000000 | (displacement // 4 & 0xFFFFFF)
        debugger = gcc.with_name(f"m32r-elf-gdb{gcc.suffix}")
        cases = []
        for sample, psw, captured_us, pending, clock_available in (
            (0, 0x40, 0, False, True),
            (347, 0x41, 101, False, True),
            (1023, 0x00, 0xFFFFFFFF, False, True),
            (347, 0x01, 102, True, True),
            (347, 0x41, 103, True, False),
        ):
            arguments = (sample, psw, captured_us, pending, clock_available)
            stock = probe(directory, debugger, None, *arguments)
            hooked = probe(directory, debugger, branch, *arguments)
            if any(stock[key] != hooked[key] for key in ("CONT", "EXIT", "RAM")):
                raise ValueError(f"The hook changed OEM execution for ADC={sample}, PSW={psw:#x}")
            if (stock["CONT"][:2] != (sample, 3) or stock["CONT"][4] != AN2 or
                    stock["RAM"][:3] != (sample, 0x7D3B, 100)):
                raise ValueError("The OEM AN2 store or following AN3/AN4 path differed")
            continuation_psw = stock["CONT"][16]
            if ((continuation_psw >> 8) & 0x41) != psw:
                raise ValueError(f"Requested fixture PSW bits {psw:#x}, saw {continuation_psw:#x}")
            count, callback_psw, argument, stored, prior_an3, callback_sp = hooked["CALL"]
            if (any(stock["CALL"]) or callback_psw & 0x40 or
                    (count, argument, stored, prior_an3) != (1, sample, sample, AN3_SENTINEL)):
                raise ValueError("The callback did not see one completed AN2 store with IRQs masked")
            if hooked["CONT"][15] - callback_sp != HOOK_FRAME_BYTES:
                raise ValueError("Unexpected stack use at the selector callback entry")
            if not clock_available:
                expected_mail, event = (4, 65535, 0), "CLOCK_LOST"
            elif pending:
                expected_mail, event = (3, 65535, captured_us), "OVERRUN"
            else:
                expected_mail, event = (1, sample, captured_us), "VALUE"
            if hooked["MAIL"] != expected_mail:
                raise ValueError(f"The selector mailbox contains {hooked['MAIL']}, expected {expected_mail}")
            cases.append({
                "adc2_10bit": sample, "entry_ie": bool(psw & 0x40), "entry_c": bool(psw & 1),
                "irq_masked_in_callback": True, "callback_count": 1,
                "sample_us": captured_us if clock_available else None, "mailbox_event": event,
                "stock_cpu_and_ram_match": True,
            })
    return {
        "base": identity, "compiler": version, "stock_store_bundle": STOCK_WORD.hex(),
        "store_site": f"{STORE_SITE:#08x}", "continuation": f"{RETURN_SITE:#08x}",
        "compared": ["R0-R15", "CR0", "ACC", "stock ADC words", "OEM status byte"],
        "hook_assembly_frame_bytes": HOOK_FRAME_BYTES,
        "cases": cases, "hardware_executed": False, "flashable_image": None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--gcc", required=True, type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.out and (args.out.suffix.lower() != ".json" or args.out.resolve() == args.base.resolve()):
        parser.error("--out must be a separate JSON report")
    try:
        result = json.dumps(check(args.base, args.gcc.resolve()), indent=2) + "\n"
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(result, encoding="utf-8")
        print(result, end="")
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
