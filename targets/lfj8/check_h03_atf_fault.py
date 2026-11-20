"""Run the H03 ATF circuit monitor and its status adapter on M32R."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
from shutil import copyfile
import struct
import subprocess
from tempfile import TemporaryDirectory

from check_h03_link import identify_h03


HERE = Path(__file__).resolve().parent
MONITOR = 0x0753A4
CALL_SITE = 0x0725B0
ATF_LIMITS = (0x0165DC, 0x0165D8)
DTC_RECORDS = {0x0712: 0x031510, 0x0713: 0x031524}

START = """
    .section .stock,"ax",@progbits
    .incbin "h03.bin"
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
  .text 0x100000 : { KEEP(*(.boot)) *(.text*) *(.rodata*) }
  .data : { *(.data*) }
  .bss : { *(.bss*) *(COMMON) }
}
"""

FIXTURE = r"""
#include "lfj8_h03_atf_fault.h"

#define RAM8(address) (*(volatile uint8_t *)(uintptr_t)(address))
#define RAM16(address) (*(volatile uint16_t *)(uintptr_t)(address))
#define WORD(address) (*(volatile uint32_t *)(uintptr_t)(address))

enum {
    VOLTAGE = 0x804F04,
    DELTA = 0x805F10,
    HIGH_REMAINING = 0x805EE4,
    LOW_REMAINING = 0x805EE8,
    GOOD_REMAINING = 0x805EFC,
    ACTIVE = 0x8063E7,
    HIGH = 0x8065EB,
    LOW = 0x8065EC,
    RECOVERED = 0x8065F0,
    ENABLE = 0x8065F3,
    ALT_ENABLE_1 = 0x8065B6,
    ALT_ENABLE_2 = 0x8065B7,
    OVERRIDE_1 = 0x8062DA,
    OVERRIDE_2 = 0x8062DC,
    SERVICE_CLEAR = 0x80637C,
    LONG_DELAY = 0x48127C00,  /* binary32 150000 */
    OVERRIDE_DELAY = 0x447A0000, /* binary32 1000 */
    RECOVERY_DELAY = 0x44FA0000, /* binary32 2000 */
    STEP_5000 = 0x459C4000,
    STEP_500 = 0x43FA0000,
};

static unsigned locked, reads, errors;

static uint32_t enter(void *context)
{
    (void)context;
    errors |= locked;
    locked = 1;
    return 0x1234u;
}

static void leave(void *context, uint32_t saved)
{
    (void)context;
    errors |= !locked || saved != 0x1234u;
    locked = 0;
}

static uint8_t read8(void *context, uint32_t address)
{
    (void)context;
    errors |= !locked;
    ++reads;
    return RAM8(address);
}

static const Lfj8RegisterIo io = {.read8 = read8, .enter = enter, .leave = leave};

static int snapshot(Lfj8H03AtfCircuitStatus expected)
{
    reads = 0;
    return lfj8_h03_atf_circuit_after_monitor(&io) == expected &&
        reads == 4 && !locked && !errors;
}

static void reset_fixture(void)
{
    WORD(HIGH_REMAINING) = LONG_DELAY;
    WORD(LOW_REMAINING) = LONG_DELAY;
    WORD(GOOD_REMAINING) = RECOVERY_DELAY;
    RAM8(ACTIVE) = 0;
    RAM8(HIGH) = 0;
    RAM8(LOW) = 0;
    RAM8(RECOVERED) = 0;
    RAM8(ENABLE) = 1;
    RAM8(ALT_ENABLE_1) = 0;
    RAM8(ALT_ENABLE_2) = 0;
    RAM16(OVERRIDE_1) = 0;
    RAM16(OVERRIDE_2) = 0;
    RAM8(SERVICE_CLEAR) = 0;
}

static void sample(uint32_t voltage, uint32_t step, unsigned count)
{
    void (*monitor)(void) = (void (*)(void))(uintptr_t)0x0753a4;
    WORD(VOLTAGE) = voltage;
    WORD(DELTA) = step;
    while (count--) {
        monitor();
    }
}

int main(void)
{
    const uint32_t lower = WORD(0x0165dc);
    const uint32_t upper = WORD(0x0165d8);
    reset_fixture();
    sample(upper, STEP_5000, 29);
    if (RAM8(ACTIVE) || !snapshot(LFJ8_H03_ATF_CIRCUIT_UNKNOWN)) {
        return 1;
    }
    sample(upper, STEP_5000, 1);
    if (WORD(HIGH_REMAINING) || !snapshot(LFJ8_H03_ATF_CIRCUIT_HIGH)) {
        return 2;
    }
    sample(lower, STEP_5000, 29);
    if (!snapshot(LFJ8_H03_ATF_CIRCUIT_HIGH)) {
        return 3;
    }
    sample(lower, STEP_5000, 1);
    if (WORD(LOW_REMAINING) || !snapshot(LFJ8_H03_ATF_CIRCUIT_BOTH)) {
        return 4;
    }
    sample(lower + 1u, STEP_500, 3);
    if (!snapshot(LFJ8_H03_ATF_CIRCUIT_BOTH)) {
        return 5;
    }
    sample(upper - 1u, STEP_500, 1);
    if (WORD(GOOD_REMAINING) || !snapshot(LFJ8_H03_ATF_CIRCUIT_NO_CURRENT_FAULT)) {
        return 6;
    }

    reset_fixture();
    sample(lower, STEP_5000, 29);
    sample(upper - 1u, STEP_5000, 1);
    if (WORD(LOW_REMAINING) != LONG_DELAY ||
        !snapshot(LFJ8_H03_ATF_CIRCUIT_NO_CURRENT_FAULT)) {
        return 7;
    }
    sample(lower, STEP_5000, 30);
    if (!snapshot(LFJ8_H03_ATF_CIRCUIT_LOW)) {
        return 8;
    }

    reset_fixture();
    RAM8(ENABLE) = 0;
    sample(upper, STEP_5000, 40);
    if (WORD(HIGH_REMAINING) != LONG_DELAY || !snapshot(LFJ8_H03_ATF_CIRCUIT_UNKNOWN)) {
        return 9;
    }
    RAM8(ALT_ENABLE_1) = 1;
    sample(upper, STEP_5000, 30);
    if (!snapshot(LFJ8_H03_ATF_CIRCUIT_HIGH)) {
        return 10;
    }
    reset_fixture();
    RAM8(ENABLE) = 0;
    RAM8(ALT_ENABLE_2) = 1;
    sample(lower, STEP_5000, 30);
    if (!snapshot(LFJ8_H03_ATF_CIRCUIT_LOW)) {
        return 11;
    }

    reset_fixture();
    RAM16(OVERRIDE_1) = 1;
    sample(upper, STEP_500, 40);
    if (WORD(HIGH_REMAINING) != OVERRIDE_DELAY ||
        !snapshot(LFJ8_H03_ATF_CIRCUIT_UNKNOWN)) {
        return 12;
    }
    RAM16(OVERRIDE_1) = 0;
    sample(upper, STEP_500, 1);
    if (!snapshot(LFJ8_H03_ATF_CIRCUIT_UNKNOWN)) {
        return 13;
    }
    sample(upper, STEP_500, 1);
    if (!snapshot(LFJ8_H03_ATF_CIRCUIT_HIGH)) {
        return 14;
    }

    /* This call includes the OEM service-reset branch and its normal tail. */
    void (*service)(void) = (void (*)(void))(uintptr_t)0x072390;
    RAM8(SERVICE_CLEAR) = 1;
    service();
    if (RAM8(ACTIVE) || RAM8(RECOVERED) || RAM8(HIGH) != 1 ||
        !snapshot(LFJ8_H03_ATF_CIRCUIT_UNKNOWN)) {
        return 15;
    }
    RAM8(SERVICE_CLEAR) = 0;
    RAM8(ENABLE) = 1;
    sample(lower, STEP_5000, 30);
    if (!snapshot(LFJ8_H03_ATF_CIRCUIT_BOTH)) {
        return 16;
    }
    sample(lower + 1u, STEP_500, 4);
    if (!snapshot(LFJ8_H03_ATF_CIRCUIT_NO_CURRENT_FAULT)) {
        return 17;
    }

    RAM8(ACTIVE) = 1;
    RAM8(HIGH) = 2;
    RAM8(RECOVERED) = 0;
    if (!snapshot(LFJ8_H03_ATF_CIRCUIT_UNKNOWN) ||
        lfj8_h03_atf_circuit_after_monitor(0) != LFJ8_H03_ATF_CIRCUIT_UNKNOWN) {
        return 18;
    }
    RAM8(HIGH) = 0;
    if (!snapshot(LFJ8_H03_ATF_CIRCUIT_UNKNOWN)) {
        return 19;
    }
    RAM8(HIGH) = 1;
    RAM8(RECOVERED) = 1;
    if (!snapshot(LFJ8_H03_ATF_CIRCUIT_UNKNOWN)) {
        return 20;
    }
    return 0;
}
"""

SCENARIOS = (
    "high_at_limit_still_pending_after_29_calls",
    "high_at_limit_active_on_call_30",
    "high_remains_active_during_low_countdown",
    "opposite_direction_can_latch_without_clearing_first",
    "both_still_active_after_three_good_steps",
    "fourth_good_step_clears_both_and_confirms_recovery",
    "one_good_step_resets_unqualified_low_countdown",
    "low_at_limit_active_on_call_30",
    "disabled_gate_reloads_high_countdown",
    "first_alternate_gate_admits_high_monitor",
    "second_alternate_gate_admits_low_monitor",
    "override_holds_stock_short_countdown",
    "first_step_after_override_remains_pending",
    "second_step_after_override_latches_high",
    "service_clear_leaves_unqualified_directional_flag",
    "old_direction_can_reappear_when_opposite_fault_qualifies",
    "fresh_recovery_clears_stale_direction",
    "unsupported_flag_value_and_missing_io",
    "aggregate_without_direction_is_unknown",
    "fault_with_recovery_flag_is_inconsistent",
)


def check(base, gcc):
    identity = identify_h03(base)
    rom = base.read_bytes()
    if sha256(rom).hexdigest() != identity["sha256"]:
        raise ValueError("H03 changed during identification")
    call = rom[CALL_SITE:CALL_SITE + 4]
    if call[0] != 0xFE or CALL_SITE + 4 * int.from_bytes(call[1:], "big", signed=True) != MONITOR:
        raise ValueError("The expected native monitor call is absent")
    low, high = (struct.unpack_from(">f", rom, address)[0] for address in ATF_LIMITS)
    counts = [raw for raw in range(1024) if low < raw * 5 / 1024 < high]
    for code, address in DTC_RECORDS.items():
        if struct.unpack_from(">I", rom, address)[0] != code << 16:
            raise ValueError(f"Unexpected H03 DTC word for P{code:04X}")

    with TemporaryDirectory(prefix="rbm-h03-atf-circuit-") as temp:
        work = Path(temp)

        def run(*command):
            return subprocess.run(command, cwd=work, check=True, capture_output=True,
                                  timeout=30).stdout

        if run(gcc, "-dumpmachine").strip() != b"m32r-elf":
            raise ValueError("A bare-metal M32R compiler is required")
        version = run(gcc, "--version").decode().splitlines()[0]
        (work / "h03.bin").write_bytes(rom)
        (work / "fixture.S").write_text(START, encoding="ascii")
        (work / "fixture.ld").write_text(LAYOUT, encoding="ascii")
        (work / "fixture.c").write_text(FIXTURE, encoding="ascii")
        for name in ("lfj8_h03_atf_fault.c", "lfj8_h03_atf_fault.h", "lfj8_donor_io.h"):
            copyfile(HERE / name, work / name)
        run(gcc, "-m32r", "-Wa,-EB", "-Os", "-mmodel=medium", "-msdata=none", "-ffreestanding",
            "-nostdlib", "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wl,-T,fixture.ld",
            "fixture.S", "fixture.c", "lfj8_h03_atf_fault.c", "-o", "fixture.elf")
        simulator = gcc.with_name(f"m32r-elf-run{gcc.suffix}")
        try:
            run(simulator, "--memory-size", "16M", "fixture.elf")
        except subprocess.CalledProcessError as error:
            if 0 < error.returncode <= len(SCENARIOS):
                raise ValueError(f"Unexpected ATF result: {SCENARIOS[error.returncode - 1]}") from error
            raise

    return {
        "base": identity, "compiler": version,
        "native_call": f"{CALL_SITE:#08x}", "native_monitor": f"{MONITOR:#08x}",
        "lower_limit_v_exclusive": low, "upper_limit_v_exclusive": high,
        "inclusive_10bit_counts": [counts[0], counts[-1]],
        "native_dtc_record_addresses": {f"P{code:04X}": f"{address:#08x}"
                                        for code, address in DTC_RECORDS.items()},
        "stock_countdown_values": {"direction": 150000, "override": 1000, "recovery": 2000},
        "simulated_scenarios": list(SCENARIOS),
        "hardware_executed": False, "target_image_emitted": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--gcc", required=True, type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.out and (args.out.suffix.lower() != ".json" or args.out.resolve() == args.base.resolve() or
                     (args.out.exists() and args.out.samefile(args.base))):
        parser.error("--out must be a separate JSON report")
    try:
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
