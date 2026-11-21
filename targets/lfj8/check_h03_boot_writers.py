"""Replay the pinned H03 reset and DMA programming paths in M32R."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory

from check_h03_link import TARGET, identify_h03
from lfj8_h03_layout import read_elf
from lfj8_h03_service_placement import early_overlay


RESET_VECTORS = (0x000000, 0x000020)
IE_BEFORE = 0x003DBC
IE_AFTER = 0x003DC0
BOOTSTRAP = 0x0009E0
FIRST_CALL = 0x000AE0
CLEAR_PROBE = 0x808104
CANDIDATE_IRQ_POINTER = 0x8094C0
SPI_TOP = 0x809EFC
PSW_CURSOR = 0x809F9C
# At each trap GNU M32R exposes the pre-break PSW in the saved byte.
BREAKPOINT_SAVED_IE = 0x4000


def check_common(base, compiler, placed_elf, layout_report):
    identity = identify_h03(base)
    layout = json.loads(layout_report.read_text(encoding="utf-8"))
    if layout["base"] != identity:
        raise ValueError("The early IRQ report uses a different H03 base")
    model = layout["early_irq_model"]
    source = base.read_bytes()
    if sha256(source).hexdigest() != identity["sha256"]:
        raise ValueError("H03 changed before the early IRQ replay")
    rom = early_overlay(source, placed_elf, model)
    pointer = model["irq_pointer"]
    elf = read_elf(placed_elf, 2)
    dispatch = elf["symbols"]["rbm_h03_dtc_rx_begin"]["address"]
    observe = elf["symbols"]["rbm_h03_dtc_rx_observe"]["address"]
    debugger = compiler.with_name(f"m32r-elf-gdb{compiler.suffix}")
    with TemporaryDirectory(prefix="rbm-h03-common-irq-") as directory:
        stage = Path(directory)

        def run(*args):
            return subprocess.run([str(arg) for arg in args], cwd=stage, check=True,
                                  capture_output=True, timeout=60).stdout

        (stage / "placed.rom").write_bytes(rom)
        (stage / "fixture.S").write_text("""
    .section .h03,"ax",@progbits
    .incbin "placed.rom"
    .text
    .global _start, fixture_irq, fixture_dma, fixture_after_denied, fixture_after_allowed
_start:
    ld24 r4,#VECTOR
    jmp r4
    .p2align 2
fixture_irq:
    ld24 r4,#0x004724
    jl r4
    nop
    ldi r8,#14
    ld24 r4,#0x001534
    jmp r4
    .p2align 2
fixture_dma:
    ldi r0,#2
    ld24 r1,#IRQ_POINTER
    ldi r2,#0
    ld24 r4,#0x00cf0c
    jl r4
    nop
    .p2align 2
fixture_after_denied:
    ldi r0,#2
    ld24 r1,#0x80683a
    ldi r2,#0
    ld24 r4,#0x00cf0c
    jl r4
    nop
    .p2align 2
fixture_after_allowed:
    bra fixture_after_allowed
""", encoding="ascii")
        results = []
        read_pointer = f"*(unsigned int*){pointer:#x}"
        for vector in RESET_VECTORS:
            run(compiler, *TARGET, "-nostdlib",
                "-Wl,-Ttext=0x80000,--section-start=.h03=0,-e,_start",
                f"-DVECTOR={vector:#x}", f"-DIRQ_POINTER={pointer:#x}", "fixture.S", "-o", "fixture.elf")
            nm = compiler.with_name(f"m32r-elf-nm{compiler.suffix}")
            symbols = {name.decode(): int(address, 16) for address, _, name in (
                row.split() for row in run(nm, "--defined-only", "fixture.elf").splitlines()
                if b" fixture_" in row
            )}

            def redirect(site, target):
                word = 0xff000000 | (((symbols[target] - site) >> 2) & 0xffffff)
                return f"set {{unsigned int}}{site:#x} = {word:#x}"

            commands = [
                "set confirm off", "target sim --memory-fill 0xa5 --memory-region 0x0,0x1000000",
                "load", f"tbreak *{IE_BEFORE:#x}", "run",
                f'printf "BEFORE %x %x %x\\n", $psw, $sp, {read_pointer}',
                f"tbreak *{IE_AFTER:#x}", "continue",
                f'printf "AFTER %x %x %x\\n", $psw, $sp, {read_pointer}',
                # Force the early OEM CAN entry in the simulator. Plain Flash
                # selects the real callback, which finds no bound application.
                "set {unsigned char}0x80801c = 0", "set {unsigned char}0x804887 = 0",
                "set {unsigned char}0x8007e2 = 0",
                *(f"set {{unsigned short}}{addr:#x} = 0"
                  for addr in (0x8007E8, 0x8007EA, 0x8007F0, 0x8007F2)),
                "set {unsigned short}0x80100c = 1", "set {unsigned char}0x801014 = 0",
                redirect(IE_AFTER, "fixture_irq"), redirect(0x001538, "fixture_dma"),
                f"tbreak *{dispatch:#x}", "continue",
                f'printf "DISPATCH %x %x\\n", $pc, {read_pointer}',
                "tbreak *0x0013f0", "continue",
                'printf "OEM %x\\n", $pc',
                # Exercise the observer's own OEM site without modelling W0C.
                "set {unsigned short}0x80100c = 0", f"tbreak *{observe:#x}", "continue",
                f'printf "OBSERVE %x %x\\n", $pc, {read_pointer}',
                "tbreak *0x001538", "continue",
                'printf "RESUME %x %x\\n", $pc, $r0',
            ]
            for label in ("DENIED", "ALLOWED"):
                commands += [
                    "set {unsigned int}0x809f9c = 0x809f9c",
                    "set {unsigned char}0x800450 = 0x25", "set {unsigned char}0x800451 = 0x07",
                    "set {unsigned short}0x800454 = 0x683b",
                    f"tbreak *{symbols['fixture_after_' + label.lower()]:#x}", "continue",
                    f'printf "{label} %x %x %x %x\\n", *(unsigned char*)0x800450, '
                    f'*(unsigned char*)0x800451, *(unsigned short*)0x800454, {read_pointer}',
                ]
            (stage / "early.gdb").write_text("\n".join(commands) + "\n", encoding="ascii")
            trace = run(debugger, "--batch", "-nx", "-x", "early.gdb", "fixture.elf")
            rows = {key.decode(): [int(word, 16) for word in values.split()]
                    for key, values in re.findall(rb"^([A-Z]+) ([0-9a-f ]+)\r?$", trace, re.M)}
            for name in ("BEFORE", "AFTER"):
                if name in rows:
                    rows[name][0] &= BREAKPOINT_SAVED_IE
            expected = {
                "BEFORE": [0, SPI_TOP, 0xA5A5A5A5],
                "AFTER": [BREAKPOINT_SAVED_IE, SPI_TOP, 0],
                "DISPATCH": [dispatch, 0], "OEM": [0x0013F0],
                "OBSERVE": [observe, 0], "RESUME": [0x001538, 14],
                "DENIED": [0x25, 7, 0x683B, 0], "ALLOWED": [0x6D, 1, 0x683A, 0],
            }
            if {key: rows.get(key) for key in expected} != expected:
                raise ValueError(f"Unexpected H03 reset, early IRQ or DMA4 observations from {vector:#x}: {rows}")
            results.append({"reset_vector": vector, "observations": rows})
    return {"base": identity, "early_model_sha256": model["elf_sha256"],
            "irq_pointer": pointer, "cases": results, "hardware_irq_or_dma_triggered": False,
            "full_boot_writer_ownership_verified": False, "flashable_image": None}


def check(base, compiler):
    identity = identify_h03(base)
    rom = base.read_bytes()
    if sha256(rom).hexdigest() != identity["sha256"]:
        raise ValueError("H03 changed before the boot writer replay")
    with TemporaryDirectory(prefix="rbm-h03-boot-writers-") as directory:
        stage = Path(directory)

        def run(*args):
            return subprocess.run([str(arg) for arg in args], cwd=stage,
                                  check=True, capture_output=True, timeout=60).stdout

        (stage / "h03.dat").write_bytes(rom)
        (stage / "fixture.S").write_text("""
    .section .h03,"ax",@progbits
    .incbin "h03.dat"
    .text
    .global _start
_start:
    ldi r0,#0
    mvtc r0,psw
    ld24 sp,#0x809efc
    ld24 fp,#0x808000
#ifdef DMA
    ld24 r4,#0x809f9c
    st r4,@r4
    ld24 r4,#0x800400
    ldi r0,#2
    stb r0,@r4
    ld24 r4,#0x804887
    ldi r0,#0
    stb r0,@r4
#endif
    ldi r0,#COUNT
    ld24 r1,#DESTINATION
    ldi r2,#0
    ld24 r3,#ENTRY
    jmp r3
""", encoding="ascii")
        debugger = compiler.with_name(f"m32r-elf-gdb{compiler.suffix}")

        def observe(entry, stops, expressions, *, dma=False, count=0, destination=0):
            run(compiler, *TARGET, "-nostdlib",
                "-Wl,-Ttext=0x80000,--section-start=.h03=0,-e,_start",
                f"-DENTRY={entry:#x}", f"-DCOUNT={count}", f"-DDESTINATION={destination:#x}",
                *(("-DDMA",) if dma else ()),
                "fixture.S", "-o", "fixture.elf")
            format_spec = " ".join(["%x"] * (1 + len(expressions)))
            values = ", ".join(("$pc", *expressions))
            rows = []
            for stop in stops:
                commands = ("set confirm off", "target sim --memory-fill 0xa5 --memory-region 0x0,0x1000000",
                            "load", f"tbreak *{stop:#x}", "run", f'printf "OBS {format_spec}\\n", {values}')
                (stage / "observe.gdb").write_text("\n".join(commands) + "\n", encoding="ascii")
                result = run(debugger, "--batch", "-nx", "-x", "observe.gdb", "fixture.elf")
                rows.extend(tuple(int(value, 16) for value in row.split())
                            for row in re.findall(rb"^OBS ([0-9a-f ]+)\r?$", result, re.M))
            if tuple(row[0] for row in rows) != stops:
                raise ValueError(f"H03 replay from {entry:#x} missed the expected stops")
            return rows

        startup = []
        for entry in RESET_VECTORS:
            stops = (IE_BEFORE, IE_AFTER, BOOTSTRAP, FIRST_CALL)
            samples = observe(entry, stops, ("$psw", "$sp",
                f"*(unsigned int*){PSW_CURSOR:#x}", f"*(unsigned char*){CLEAR_PROBE:#x}",
                f"*(unsigned int*){CANDIDATE_IRQ_POINTER:#x}"))
            expected = ((False, 0xa5), (True, 0xa5), (True, 0xa5), (True, 0))
            if tuple((bool(psw & BREAKPOINT_SAVED_IE), marker)
                     for _, psw, _, _, marker, _ in samples) != expected or any(
                    sp != SPI_TOP or cursor != PSW_CURSOR or candidate != 0xA5A5A5A5
                    for _, _, sp, cursor, _, candidate in samples):
                raise ValueError(f"Unexpected masked/early IRQ ordering for vector {entry:#x}: {samples}")
            startup.append({"vector": hex(entry), "samples": [
                {"pc": hex(pc), "irq_enabled": bool(psw & BREAKPOINT_SAVED_IE), "spi": hex(sp),
                 "psw_cursor": hex(cursor), "stock_clear_probe_byte": marker,
                 "candidate_irq_pointer_word": hex(candidate)}
                for pc, psw, sp, cursor, marker, candidate in samples]})

        registers = tuple(expression for base in (0x800410, 0x800420) for expression in (
            f"*(unsigned char*){base:#x}",
            f"*(unsigned char*){base+1:#x}",
            f"*(unsigned short*){base+4:#x}"))
        _, *values = observe(0x00AB44, (0x00ABC8,), registers, dma=True)[0]
        if values != [0x79, 5, 0x6ACE, 0x79, 5, 0x6ADA]:
            raise ValueError(f"Unexpected capture DMA rearm: {values}")

        _, control, transfers, low_destination = observe(
            0x00CE98, (0x00CEF4,), ("*(unsigned char*)0x800440",
            "*(unsigned char*)0x800441", "*(unsigned short*)0x800444"), dma=True, count=2,
            destination=0x80683A)[0]
        if (control, transfers, low_destination) != (0x5E, 0, 0x0113):
            raise ValueError("Unexpected SIO0 DMA3 fixed destination")

        sio = []
        for destination, count in ((0x80683A, 1), (0x80683B, 256), (0x806B40, 2)):
            _, control, transfers, low_destination = observe(
                0x00CF0C, (0x00CF60,), ("*(unsigned char*)0x800450",
                "*(unsigned char*)0x800451", "*(unsigned short*)0x800454"),
                dma=True, count=count, destination=destination)[0]
            if (control, transfers, low_destination) != (0x6D, count - 1, destination & 0xffff):
                raise ValueError(f"Unexpected DMA4 stock argument handling at {destination:#x}")
            sio.append({"destination": hex(destination), "transfers": count, "control": hex(control),
                        "inside_audited_sio0_buffer": 0x80683A <= destination <= 0x80693B - count})

    return {"base": identity, "reset": startup, "candidate_irq_pointer_address": hex(CANDIDATE_IRQ_POINTER),
            "capture_dma_rearm": {"entry": "0x00ab44", "destinations": ["0x806ace", "0x806ada"],
                                  "halfwords_per_channel": 6},
            "sio0_dma3_setup": {"entry": "0x00ce98", "destination": "0x800113",
                                "transfer_control": "0x5e", "count_register": 0},
            "sio0_dma4_setup": {"entry": "0x00cf0c", "cases": sio,
                                "stock_setup_does_not_bound_destination": True},
            "hardware_irq_or_dma_triggered": False,
            "full_boot_writer_ownership_verified": False,
            "flashable_image": None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--gcc", required=True, type=Path)
    parser.add_argument("--placed-elf", type=Path)
    parser.add_argument("--layout-report", type=Path)
    args = parser.parse_args()
    if bool(args.placed_elf) != bool(args.layout_report):
        parser.error("--placed-elf and --layout-report must be used together")
    try:
        result = (check_common(args.base, args.gcc.resolve(), args.placed_elf, args.layout_report)
                  if args.placed_elf else check(args.base, args.gcc.resolve()))
        print(json.dumps(result, indent=2))
    except subprocess.CalledProcessError as error:
        message = error.stderr or error.stdout or str(error).encode()
        parser.exit(1, message.decode(errors="replace") + "\n")
    except (ValueError, KeyError, OSError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
