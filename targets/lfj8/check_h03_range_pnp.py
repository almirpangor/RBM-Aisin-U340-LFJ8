"""Trace the stock H03 P/N flag back to AN2 in the M32R simulator."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from check_h03_link import identify_h03


START = """
    .section .stock,"ax",@progbits
    .incbin "h03.rom"

    .section .boot,"ax",@progbits
    .global _start
_start:
    ld24 sp,#0x9ffffc
    bl main
    mv r1,r0
    ldi r0,#1
    trap #0
"""

LAYOUT = """
ENTRY(_start)
SECTIONS {
  .stock 0 : { KEEP(*(.stock)) }
  .boot 0x100000 : { *(.boot) }
  .text : { *(.text*) *(.rodata*) }
}
stock_an2_voltage = 0x034d14;
stock_range_flags = 0x03ac28;
"""

FIXTURE = """
#include <stdint.h>

#define MEM8(address) (*(volatile uint8_t *)(address))
#define MEM16(address) (*(volatile uint16_t *)(address))
#define MEM32(address) (*(volatile uint32_t *)(address))
#define AN2 MEM16(0x804bc6)
#define RANGE_FLAGS MEM16(0x80622c)
#define P_OR_N MEM8(0x806446)
#define P MEM8(0x80644b)
#define N MEM8(0x806447)
#define R MEM8(0x80644f)
#define D MEM8(0x80640a)

extern void stock_an2_voltage(void);
extern void stock_range_flags(void);

static volatile uint32_t *const history = (volatile uint32_t *)0x804f08;
enum position { UNKNOWN, DRIVE, PARK, NEUTRAL, REVERSE };

static int check_adc(void)
{
    uint32_t expected[4] = {0, 0, 0, 0};
    for (unsigned raw = 0; raw < 1024; ++raw) {
        const union { float voltage; uint32_t word; } sample = {
            .voltage = raw * (5.0f / 1024.0f)
        };
        AN2 = raw;
        stock_an2_voltage();
        for (unsigned i = 3; i > 0; --i) {
            expected[i] = expected[i - 1];
        }
        expected[0] = sample.word;
        for (unsigned i = 0; i < 4; ++i) {
            if (history[i] != expected[i]) {
                return 0;
            }
        }
    }
    return 1;
}

static int check_range(enum position position)
{
    static const uint16_t flags[] = {
        [UNKNOWN] = 0, [DRIVE] = 16, [PARK] = 2, [NEUTRAL] = 2, [REVERSE] = 1
    };
    stock_an2_voltage();
    stock_range_flags();
    return RANGE_FLAGS == flags[position] && P_OR_N == (position == PARK || position == NEUTRAL) &&
           P == (position == PARK) && N == (position == NEUTRAL) &&
           R == (position == REVERSE) && D == (position == DRIVE);
}

int main(void)
{
    if (!check_adc()) {
        return 1;
    }
    static const struct { uint16_t raw; enum position position; } replay[] = {
        {490, DRIVE}, {955, PARK}, {670, NEUTRAL}, {825, REVERSE}, {490, DRIVE}
    };
    for (unsigned i = 0; i < sizeof(replay) / sizeof(replay[0]); ++i) {
        /* Later range calls reuse the same captured AN2 word. */
        AN2 = replay[i].raw;
        for (unsigned sample = 0; sample < 4; ++sample) {
            const enum position position = sample < 3 ? UNKNOWN : replay[i].position;
            if (!check_range(position)) {
                return 2 + 4 * i + sample;
            }
        }
    }

    /* Change calibration only in simulator memory. The last AN2 sample decoded as D. */
    MEM32(0x016840) = 0x40500000; /* 3.25 V is inside the stock N window. */
    MEM16(0x0166a4) = 300;
    static const uint16_t raw[] = {490, 955, 825, 0};
    for (unsigned i = 0; i < 4; ++i) {
        AN2 = raw[i];
        if (!check_range(i < 3 ? UNKNOWN : NEUTRAL) || history[0] != 0x40500000) {
            return 22 + i;
        }
    }
    return 0;
}
"""


def check(base, compiler):
    identity = identify_h03(base)
    rom = base.read_bytes()
    if sha256(rom).hexdigest() != identity["sha256"]:
        raise ValueError("H03 changed while the fixture was being prepared")

    with TemporaryDirectory(prefix="rbm-h03-range-pnp-") as directory:
        work = Path(directory)

        def run(*command):
            return subprocess.run(command, cwd=work, capture_output=True, check=True, timeout=30).stdout

        if run(compiler, "-dumpmachine").strip() != b"m32r-elf":
            raise ValueError("A bare-metal M32R compiler is required")
        version = run(compiler, "--version").decode().splitlines()[0]
        (work / "h03.rom").write_bytes(rom)
        (work / "fixture.S").write_text(START, encoding="ascii")
        (work / "fixture.ld").write_text(LAYOUT, encoding="ascii")
        (work / "fixture.c").write_text(FIXTURE, encoding="ascii")
        run(compiler, "-m32r", "-Wa,-EB", "-Os", "-ffreestanding", "-nostdlib",
            "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wl,-T,fixture.ld",
            "fixture.S", "fixture.c", "-lc", "-lgcc", "-o", "fixture.elf")
        objcopy = compiler.with_name(f"m32r-elf-objcopy{compiler.suffix}")
        run(objcopy, "-j", ".stock", "-O", "binary", "fixture.elf", "linked.rom")
        if (work / "linked.rom").read_bytes() != rom:
            raise ValueError("Linked stock ROM differs from the approved H03 base")
        simulator = compiler.with_name(f"m32r-elf-run{compiler.suffix}")
        try:
            run(simulator, "--memory-size", "16M", "fixture.elf")
        except subprocess.CalledProcessError as error:
            stage = error.returncode
            if stage == 1:
                raise ValueError("Stock voltage conversion or history differs from AN2") from error
            if 2 <= stage < 22:
                raise ValueError(f"Unexpected stock range flags on replay call {stage - 1}") from error
            if 22 <= stage < 26:
                raise ValueError(f"Unexpected calibration override on call {stage - 21}") from error
            raise

    return {
        "base": identity,
        "compiler": version,
        "voltage_routine": "0x034D14",
        "range_routine": "0x03AC28",
        "range_window_routine": "0x039DAC",
        "p_or_n_flag": "0x806446",
        "adc_codes_checked": 1024,
        "voltage_history_samples": 4,
        "stock_sequence": ["D", "P", "N", "R", "D"],
        "stock_range_calls": 20,
        "stock_an2_writes_during_replay": 5,
        "unclassified_calls_per_transition": 3,
        "simulator_rom_override_calls": 4,
        "simulator_override_voltage": 3.25,
        "simulator_override_decoded_as": "N",
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
