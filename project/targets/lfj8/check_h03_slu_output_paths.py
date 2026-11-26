"""Exercise the stock H03 Shift E and TIO9 paths in the M32R simulator."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from check_h03_link import identify_h03
from check_h03_range_pnp import START


LAYOUT = """
ENTRY(_start)
SECTIONS {
  .stock 0 : { KEEP(*(.stock)) }
  .boot 0x100000 : { *(.boot) }
  .text : { *(.text*) *(.rodata*) }
}
stock_aux_proposal = 0x07b5b4;
stock_arbitrate = 0x0717b8;
stock_apply = 0x046900;
stock_tio9_apply = 0x00b4b4;
"""

FIXTURE = """
#include <stdint.h>

#define REG8(address) (*(volatile uint8_t *)(uintptr_t)(address))
#define REG16(address) (*(volatile uint16_t *)(uintptr_t)(address))
#define REG32(address) (*(volatile uint32_t *)(uintptr_t)(address))

#define OEM_LOCK_STACK 0x809f9c
#define SUPPLY_VOLTAGE REG32(0x805084)
#define ATF_TEMP REG32(0x805028)
#define AUX_PROPOSAL REG32(0x8060f0)
#define AUX_WIDTH REG16(0x8048ce)
#define E_REQUEST REG8(0x8063d8)
#define E_FINAL REG8(0x8063da)
#define E_FAULT REG8(0x8063b7)
#define E_SERVICE_ENABLE REG8(0x80636f)
#define E_SERVICE_REQUEST REG8(0x8063d9)
#define COMMON_INHIBIT REG8(0x8063f2)
#define P3DATA REG8(0x800703)
#define P9DATA REG8(0x800709)
#define P9SEL REG8(0x800749)
#define TIO9_RL1 REG16(0x800394)
#define TIO9_RL0 REG16(0x800396)
#define OEM_MODE REG8(0x804887)

extern void stock_aux_proposal(void);
extern void stock_arbitrate(void);
extern void stock_apply(void);
extern void stock_tio9_apply(void);

static int check_outputs(uint8_t level, uint16_t width)
{
    stock_arbitrate();
    stock_apply();
    return E_FINAL == level && ((P3DATA & 0x40) != 0) == level &&
           AUX_WIDTH == width && P9SEL == 0xa1 &&
           TIO9_RL1 == 249u - width && TIO9_RL0 == width - 1u &&
           REG32(OEM_LOCK_STACK) == OEM_LOCK_STACK;
}

static int matches_rom_knot(uint32_t knot)
{
    /* The native interpolation/multiply can differ by an ulp at a knot. */
    const uint32_t expected = REG32(knot);
    const uint32_t observed = AUX_PROPOSAL;
    return expected - 1u <= observed && observed <= expected + 1u;
}

int main(void)
{
    REG32(OEM_LOCK_STACK) = OEM_LOCK_STACK;
    SUPPLY_VOLTAGE = 0x41598000; /* 13.59375 V, ROM knot 5. */
    ATF_TEMP = 0x42a00000;       /* 80 C, ROM knot 6. */
    P3DATA = 0xe1;
    P9DATA = 0xa4;
    P9SEL = 0xa0;
    stock_aux_proposal();
    if (!matches_rom_knot(0x0199c0) || !check_outputs(0, 66)) {
        return 1;
    }

    E_REQUEST = 1;
    if (!check_outputs(1, 66)) {
        return 2;
    }
    COMMON_INHIBIT = 1;
    if (!check_outputs(0, 66) || E_REQUEST != 1) {
        return 3;
    }
    COMMON_INHIBIT = 0;
    E_FAULT = 1;
    E_SERVICE_ENABLE = 1;
    E_SERVICE_REQUEST = 1;
    if (!check_outputs(0, 66)) {
        return 4;
    }
    E_FAULT = 0;
    E_REQUEST = 0;
    if (!check_outputs(1, 66) || (P3DATA & 0x1f) != 1) {
        return 5;
    }
    E_SERVICE_ENABLE = 0;

    /* Change one producer input at a time on the native path. */
    SUPPLY_VOLTAGE = 0x4100c000; /* 8.046875 V, ROM knot 0. */
    stock_aux_proposal();
    if (!matches_rom_knot(0x0199ac) || !check_outputs(0, 108)) {
        return 6;
    }
    ATF_TEMP = 0xc2200000; /* -40 C, ROM knot 0. */
    stock_aux_proposal();
    if (!check_outputs(0, 83)) {
        return 7;
    }

    static const struct {
        uint16_t request, width;
        uint8_t mode, alternate, latch;
    } cases[] = {
        {0, 1, 0, 0, 0}, {1, 1, 0, 0, 0}, {2, 2, 0, 0, 0},
        {3, 3, 0, 1, 1}, {247, 247, 0, 1, 1},
        {248, 248, 0, 1, 1}, {249, 248, 0, 1, 1}, {250, 248, 0, 1, 1},
        {65535, 248, 0, 1, 1}, {247, 247, 4, 1, 1}, {248, 248, 4, 0, 1},
    };
    for (unsigned i = 0; i < sizeof(cases) / sizeof(cases[0]); ++i) {
        AUX_WIDTH = cases[i].request;
        OEM_MODE = cases[i].mode;
        P9DATA = 0xa5;
        P9SEL = 0xa1;
        stock_tio9_apply();
        if (AUX_WIDTH != cases[i].width ||
            P9DATA != (0xa4u | cases[i].latch) ||
            P9SEL != (0xa0u | cases[i].alternate) ||
            TIO9_RL1 != 249u - cases[i].width || TIO9_RL0 != cases[i].width - 1u ||
            REG32(OEM_LOCK_STACK) != OEM_LOCK_STACK) {
            return i + 8;
        }
    }
    return 0;
}
"""

SCENARIOS = (
    "nominal supply and ATF", "Shift E on", "common inhibit", "E fault precedes service",
    "E service override", "supply knot", "ATF knot",
    "width 0", "width 1", "width 2", "width 3", "width 247", "width 248", "width 249",
    "width 250", "width 65535", "width 247 in mode 4", "width 248 in mode 4",
)


def check(base, gcc):
    identity = identify_h03(base)
    stock = base.read_bytes()
    if sha256(stock).hexdigest() != identity["sha256"]:
        raise ValueError("H03 changed while preparing the fixture")
    with TemporaryDirectory(prefix="rbm-h03-slu-output-") as directory:
        work = Path(directory)

        def run(*args):
            return subprocess.run(args, cwd=work, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  check=True, timeout=30).stdout

        if run(gcc, "-dumpmachine").strip() != b"m32r-elf":
            raise ValueError("A bare-metal M32R GCC is required")
        version = run(gcc, "--version").decode().splitlines()[0]
        (work / "h03.rom").write_bytes(stock)
        (work / "fixture.S").write_text(START, encoding="ascii")
        (work / "fixture.c").write_text(FIXTURE, encoding="ascii")
        (work / "fixture.ld").write_text(LAYOUT, encoding="ascii")
        run(gcc, "-m32r", "-Wa,-EB", "-Os", "-ffreestanding", "-nostdlib", "-std=c11",
            "-Wall", "-Wextra", "-Werror", "-Wl,-T,fixture.ld",
            "fixture.S", "fixture.c", "-lc", "-lgcc", "-o", "fixture.elf")
        objcopy = gcc.with_name(f"m32r-elf-objcopy{gcc.suffix}")
        run(objcopy, "-j", ".stock", "-O", "binary", "fixture.elf", "linked.rom")
        if (work / "linked.rom").read_bytes() != stock:
            raise ValueError("The linked H03 bytes differ from the verified base")
        sim = gcc.with_name(f"m32r-elf-run{gcc.suffix}")
        try:
            run(sim, "--memory-size", "16M", "fixture.elf")
        except subprocess.CalledProcessError as error:
            if 0 < error.returncode <= len(SCENARIOS):
                raise ValueError(f"Unexpected result in {SCENARIOS[error.returncode - 1]}") from error
            raise
    return {"base": identity, "compiler": version, "scenarios": list(SCENARIOS),
            "shift_e_pin": "P31", "tio9_pin": "P97", "pwm_widths_for_voltage_and_atf": [66, 108, 83],
            "common_inhibit_clears_shift_e_but_keeps_tio9": True,
            "hardware_tested": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--gcc", type=Path, required=True)
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
