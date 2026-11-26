"""Verify coalesced native H03 phase releases in the GNU M32R simulator."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory

from check_h03_flash_policy import LAYOUT
from check_h03_link import identify_h03


RELEASE = 0x040424
RELEASE_RETURN = 0x040428
TAKE = 0x008150
TAKE_RETURN = 0x008160
OEM_FLAG = 0x804ADE
OEM_DIVIDER = 0x804862

FIXTURE = r"""
    .section .oem,"ax",@progbits
    .incbin "h03.dat",0,0x008160
    jmp lr || nop
    .incbin "h03.dat",0x008164,0x040428-0x008164
    jmp r8 || nop
    .incbin "h03.dat",0x04042c

    .section .fixture,"ax",@progbits
    .global _start
    .global fixture_snapshot

    .macro release
    ld24 r4,#0x804862
    ldi r0,#0
    stb r0,@r4
    ld24 r8,#.Lreturn\@
    ld24 r4,#0x040424
    jmp r4
    .p2align 2
.Lreturn\@:
    bl fixture_snapshot
    .endm

    .macro take
    ld24 r4,#0x008150
    jl r4
    .p2align 2
    bl fixture_snapshot
    .endm

_start:
    ld24 sp,#0x9ffffc
    ld24 r4,#0x804864
    ldi r0,#5
    stb r0,@r4
    .p2align 2
    release
    release
    take
    release
    take
fixture_done:
    bra fixture_done

fixture_snapshot:
    jmp lr || nop
"""


def check(base, compiler):
    identity = identify_h03(base)
    rom = base.read_bytes()
    if sha256(rom).hexdigest() != identity["sha256"]:
        raise ValueError("H03 changed during verification")
    if rom[RELEASE:RELEASE_RETURN] != bytes.fromhex("7E11F000"):
        raise ValueError("H03 phase release no longer calls 040468")

    # Two consecutive releases with no foreground visit must count as a
    # single ready bit. Run the original store and clear packets in both cases.
    steps = [(RELEASE, RELEASE_RETURN), (RELEASE, RELEASE_RETURN), (TAKE, TAKE_RETURN),
             (RELEASE, RELEASE_RETURN), (TAKE, TAKE_RETURN)]
    commands = ["set confirm off", "target sim --memory-size 16M", "load",
                "break *fixture_snapshot"]
    for index, _ in enumerate(steps):
        commands.extend(("continue" if index else "run",
                         f'printf "PHASE {index} %x %x\\n", '
                         f"*(unsigned char*){OEM_FLAG:#x}, *(unsigned char*){OEM_DIVIDER:#x}"))

    with TemporaryDirectory(prefix="rbm-h03-phase-release-") as directory:
        work = Path(directory)

        def run(*args):
            return subprocess.run([str(arg) for arg in args], cwd=work, check=True,
                                  capture_output=True, timeout=20).stdout

        (work / "h03.dat").write_bytes(rom)
        (work / "fixture.S").write_text(FIXTURE, encoding="ascii")
        (work / "fixture.ld").write_text(LAYOUT, encoding="ascii")
        (work / "probe.gdb").write_text("\n".join(commands) + "\n", encoding="ascii")
        run(compiler, "-m32r", "-Wa,-EB", "-nostdlib", "-Wl,-T,fixture.ld", "fixture.S", "-o", "fixture.elf")
        debugger = compiler.with_name(f"m32r-elf-gdb{compiler.suffix}")
        output = run(debugger, "--batch", "-nx", "-x", "probe.gdb", "fixture.elf")

    observed = re.findall(rb"PHASE (\d+) ([\da-f]+) ([\da-f]+)", output)
    expected = [(index, bit, 10) for index, bit in enumerate((1, 1, 0, 1, 0))]
    if [tuple(int(value, 16) for value in row) for row in observed] != expected:
        raise ValueError(f"Unexpected OEM phase trace: {output[-1300:].decode(errors='replace')}")
    return {
        "base": identity,
        "cases": [{"entry": f"0x{entry:06X}", "continuation": f"0x{stop:06X}",
                   "oem_flag_after": bit, "oem_divider_after": divider}
                  for (entry, stop), (_, bit, divider) in zip(steps, expected, strict=True)],
        "stock_bit_retains_event_count": False,
        "stock_instruction_ranges_executed_unmodified": [["0x040424", "0x040428"],
                                                          ["0x008150", "0x008160"],
                                                          ["0x040468", "0x0404C4"]],
        "simulator_intercepts_continuations": True,
        "hardware_executed": False,
        "flashable_image": None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--gcc", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if args.out.suffix.lower() != ".json" or args.out.resolve() == args.base.resolve():
        parser.error("--out must be a separate JSON report")
    try:
        result = json.dumps(check(args.base, args.gcc.resolve()), indent=2) + "\n"
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(result, encoding="utf-8")
        print(result, end="")
    except subprocess.CalledProcessError as error:
        message = error.stderr or error.stdout or str(error).encode()
        parser.exit(1, message.decode(errors="replace") + "\n")
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
