"""Replay the pinned H03 reset and DMA programming paths in M32R."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory

from check_h03_link import TARGET, identify_h03


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
    args = parser.parse_args()
    try:
        print(json.dumps(check(args.base, args.gcc.resolve()), indent=2))
    except subprocess.CalledProcessError as error:
        message = error.stderr or error.stdout or str(error).encode()
        parser.exit(1, message.decode(errors="replace") + "\n")
    except (ValueError, OSError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
