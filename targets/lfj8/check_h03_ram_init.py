"""Measure H03 boot and reset-preamble RAM contents in the GNU M32R simulator."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory

from check_h03_link import identify_h03


BOOTSTRAP = 0x0009E0
STOP = 0x000AE0
INIT_SOURCE = 0x003D90
RESET_PREAMBLE = 0x003D94
RESET_RETURN = 0x003DC4
RAM_START = 0x804000
RAM_LIMIT = 0x80A000
INITIALIZED_BYTE = 0x808100
CLEAR_START = 0x808104
CLEAR_LIMIT = 0x808E06
STACK_POINTER = 0x809EFC
FRAME_POINTER = 0x808000
SAVED_PSW_POINTER = 0x809F9C
INTERRUPT_PRIORITY_SHADOW = 0x800004
FILL = 0xA5


def check(base, compiler):
    identity = identify_h03(base)
    rom = base.read_bytes()
    if sha256(rom).hexdigest() != identity["sha256"]:
        raise ValueError("H03 changed while the bootstrap fixture was being prepared")
    bootstrap = rom[BOOTSTRAP:STOP + 4]
    reset = rom[RESET_PREAMBLE:RESET_RETURN]
    expected = bytearray([FILL]) * (RAM_LIMIT - RAM_START)
    expected[INITIALIZED_BYTE - RAM_START] = 0xFF
    expected[CLEAR_START - RAM_START:CLEAR_LIMIT - RAM_START] = bytes(CLEAR_LIMIT - CLEAR_START)
    cases = []

    with TemporaryDirectory(prefix="rbm-h03-ram-init-") as directory:
        work = Path(directory)
        (work / "bootstrap.dat").write_bytes(bootstrap)
        (work / "init-source.dat").write_bytes(rom[INIT_SOURCE:INIT_SOURCE + 1])
        (work / "reset.dat").write_bytes(reset)
        (work / "fixture.S").write_text(
            '    .section .h03_boot,"ax",@progbits\n'
            'h03_boot:\n    .incbin "bootstrap.dat"\n'
            '    .section .h03_data,"a",@progbits\n'
            '    .incbin "init-source.dat"\n'
            '    .section .h03_reset,"ax",@progbits\n'
            'h03_reset:\n    .incbin "reset.dat"\n'
            '    .section .fixture_start,"ax",@progbits\n'
            '    .global _start\n'
            '_start:\n    bra FIXTURE_ENTRY\n',
            encoding="ascii",
        )
        (work / "fixture.ld").write_text(
            "ENTRY(_start)\nSECTIONS {\n"
            f"  .h03_boot {BOOTSTRAP:#x} : {{ *(.h03_boot) }}\n"
            "  .fixture_start 0x1000 : { *(.fixture_start) }\n"
            f"  .h03_data {INIT_SOURCE:#x} : {{ *(.h03_data) }}\n"
            f"  .h03_reset {RESET_PREAMBLE:#x} : {{ *(.h03_reset) }}\n"
            "  /DISCARD/ : { *(.note*) *(.comment) }\n}\n",
            encoding="ascii",
        )
        (work / "check.gdb").write_text(
            "set confirm off\n"
            f"target sim --memory-fill {FILL:#x} --memory-region 0x0,0x1000000\n"
            "load\n"
            "tbreak *_start\n"
            "run\n"
            f"dump binary memory before.dat {RAM_START:#x} {RAM_LIMIT:#x}\n"
            f"tbreak *{STOP:#x}\n"
            "continue\n"
            f"dump binary memory after.dat {RAM_START:#x} {RAM_LIMIT:#x}\n"
            f"dump binary memory irq.dat {INTERRUPT_PRIORITY_SHADOW:#x} "
            f"{INTERRUPT_PRIORITY_SHADOW + 1:#x}\n"
            'printf "H03 stop pc=%x sp=%x fp=%x\\n", $pc, $sp, $fp\n',
            encoding="ascii",
        )

        def run(*args):
            return subprocess.run([str(arg) for arg in args], cwd=work,
                                  capture_output=True, check=True, timeout=15).stdout

        if run(compiler, "-dumpmachine").strip() != b"m32r-elf":
            raise ValueError("A bare-metal M32R compiler is required")
        gdb = compiler.with_name(f"m32r-elf-gdb{compiler.suffix}")
        for entry, address in (("h03_boot", BOOTSTRAP), ("h03_reset", RESET_PREAMBLE)):
            run(compiler, "-m32r", "-Wa,-EB", "-nostdlib", "-Wl,-T,fixture.ld",
                f"-DFIXTURE_ENTRY={entry}", "fixture.S", "-o", "fixture.elf")
            output = run(gdb, "--batch", "-nx", "-x", "check.gdb", "fixture.elf")
            before = (work / "before.dat").read_bytes()
            after = (work / "after.dat").read_bytes()
            irq_shadow = (work / "irq.dat").read_bytes()

            registers = re.search(rb"H03 stop pc=([0-9a-f]+) sp=([0-9a-f]+) fp=([0-9a-f]+)", output)
            if registers is None or tuple(int(value, 16) for value in registers.groups()) != (
                STOP, STACK_POINTER, FRAME_POINTER
            ):
                raise ValueError(f"Unexpected H03 startup CPU state from {address:#x}")
            if before != bytes([FILL]) * (RAM_LIMIT - RAM_START):
                raise ValueError(f"Unexpected initial simulator RAM contents from {address:#x}")

            psw_pointer = None
            irq_value = FILL
            if address == RESET_PREAMBLE:
                psw_pointer = SAVED_PSW_POINTER
                offset = SAVED_PSW_POINTER - RAM_START
                expected[offset:offset + 4] = psw_pointer.to_bytes(4, "big")
                irq_value = 0
            if after != expected or irq_shadow != bytes([irq_value]):
                raise ValueError(f"Unexpected final simulator memory contents from {address:#x}")
            cases.append({
                "entry": f"0x{address:06X}",
                "saved_psw_pointer_initialized": psw_pointer is not None,
                "interrupt_priority_shadow_after": irq_value,
            })

    return {
        "base": identity,
        "bootstrap": [f"0x{BOOTSTRAP:06X}", f"0x{STOP:06X}"],
        "bootstrap_sha256": sha256(bootstrap[:-4]).hexdigest(),
        "reset_preamble": [f"0x{RESET_PREAMBLE:06X}", f"0x{RESET_RETURN:06X}"],
        "reset_preamble_sha256": sha256(reset).hexdigest(),
        "pc_before_first_call": f"0x{STOP:06X}",
        "stack_pointer": f"0x{STACK_POINTER:06X}",
        "frame_pointer": f"0x{FRAME_POINTER:06X}",
        "ram_compared": [f"0x{RAM_START:06X}", f"0x{RAM_LIMIT:06X}"],
        "ram_bytes_compared": len(after),
        "initial_fill_byte": FILL,
        "init_source": f"0x{INIT_SOURCE:06X}",
        "copied_byte_address": f"0x{INITIALIZED_BYTE:06X}",
        "copied_byte_value": after[INITIALIZED_BYTE - RAM_START],
        "cleared_range": [f"0x{CLEAR_START:06X}", f"0x{CLEAR_LIMIT:06X}"],
        "cleared_bytes": CLEAR_LIMIT - CLEAR_START,
        "saved_psw_pointer_address_and_value": f"0x{SAVED_PSW_POINTER:06X}",
        "interrupt_priority_shadow_address": f"0x{INTERRUPT_PRIORITY_SHADOW:06X}",
        "cases": cases,
        "ends_are_exclusive": True,
        "hardware_executed": False,
        "runtime_ram_ownership_verified": False,
    }


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
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
