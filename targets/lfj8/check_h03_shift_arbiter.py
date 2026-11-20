"""Exercise the H03 shift command arbiter on a GNU M32R simulator."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

from check_h03_link import identify_h03


HERE = Path(__file__).resolve().parent
MODEL = """
ENTRY(_start)
SECTIONS {
  .test_start 0x001000 : { *(.test_start) }
  .oem_calibration 0x0166a4 : { *(.oem_calibration) }
  .oem_constants 0x032910 : { *(.oem_constants) }
  .text 0x060000 : { *(.text*) *(.rodata*) }
  .oem_tail 0x070254 : { *(.oem_tail) }
  .oem_arbiter 0x0717b8 : { *(.oem_arbiter) }
  /DISCARD/ : { *(.note*) *(.comment) }
}
"""
START = """
    .section .test_start,"ax",@progbits
    .global _start
    .global call_stock_tail
_start:
    ld24 sp,#0x9ffffc
    bl main
    bnez r0,exit_test
    ldi r0,#5
    ldi r1,#1
    ld24 r2,#pass_text
    ldi r3,#5
    trap #0
    ldi r0,#0
exit_test:
    mv r1,r0
    ldi r0,#1
    trap #0

    .p2align 2
call_stock_tail:
    push lr
    push r8
    addi sp,#-4
    bra oem_tail
pass_text:
    .ascii "PASS\\n"

    .section .oem_tail,"ax",@progbits
oem_tail:
    .incbin "tail.dat"
    .section .oem_arbiter,"ax",@progbits
    .incbin "arbiter.dat"
    .section .oem_calibration,"a",@progbits
    .incbin "calibration.dat"
    .section .oem_constants,"a",@progbits
    .incbin "constants.dat"
"""


def check(base, compiler):
    identity = identify_h03(base)
    rom = base.read_bytes()
    if sha256(rom).hexdigest() != identity["sha256"]:
        raise ValueError("H03 changed while the fixture was being prepared")

    # These are unchanged instructions and read-only words, placed at H03's addresses.
    fragments = (
        ("calibration", 0x0166A4, 0x0166A6),
        ("constants", 0x032910, 0x032974),
        ("tail", 0x070254, 0x070260),
        ("arbiter", 0x0717B8, 0x071CA4),
    )
    scenarios = (
        "normal_proposals",
        "diagnostic_overrides",
        "individual_faults_precede_override",
        "shared_cut_keeps_pressure_a_proposal",
        "cut_precedes_fallback",
        "fallback",
    )
    with TemporaryDirectory(prefix="rbm-h03-shift-arbiter-") as directory:
        work = Path(directory)

        def run(*args):
            return subprocess.run([str(arg) for arg in args], cwd=work, check=True,
                                  capture_output=True, timeout=30).stdout

        if run(compiler, "-dumpmachine").strip() != b"m32r-elf":
            raise ValueError("A bare-metal M32R compiler is required")
        version = run(compiler, "--version").decode().splitlines()[0]
        for name, start, end in fragments:
            (work / f"{name}.dat").write_bytes(rom[start:end])
        (work / "fixture.ld").write_text(MODEL, encoding="ascii")
        (work / "fixture.S").write_text(START, encoding="ascii")
        shutil.copyfile(HERE / "h03_shift_arbiter_test.c", work / "fixture.c")
        run(compiler, "-m32r", "-Wa,-EB", "-Os", "-ffreestanding", "-nostdlib",
            "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wl,-T,fixture.ld",
            "fixture.S", "fixture.c", "-o", "fixture.elf")
        simulator = compiler.with_name(f"m32r-elf-run{compiler.suffix}")
        try:
            output = run(simulator, "--memory-size", "16M", "fixture.elf")
        except subprocess.CalledProcessError as error:
            if 0 < error.returncode <= len(scenarios):
                raise ValueError(f"Unexpected arbiter result in {scenarios[error.returncode - 1]}") from error
            raise
        if output.strip() != b"PASS":
            raise ValueError(f"Incomplete arbiter test output: {output!r}")

    return {
        "base": identity,
        "compiler": version,
        "native_fragments": {name: [f"0x{start:06X}", f"0x{end:06X}"]
                             for name, start, end in fragments},
        "simulated_scenarios": list(scenarios),
        "pwm_proposals_still_used_by_stock_arbiter": 4,
        "range_ends_exclusive": True,
        "hardware_executed": False,
        "upstream_strategy_executed": False,
        "physical_commit_executed": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--gcc", required=True, type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    try:
        if args.out and (args.out.resolve() == args.base.resolve() or
                         (args.out.exists() and args.out.samefile(args.base))):
            raise ValueError("The report and the H03 base must use different files")
        report = json.dumps(check(args.base, args.gcc.resolve()), indent=2) + "\n"
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(report, encoding="utf-8")
        print(report, end="")
    except subprocess.CalledProcessError as error:
        message = error.stderr or error.stdout or str(error).encode()
        parser.exit(1, message.decode(errors="replace") + "\n")
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
