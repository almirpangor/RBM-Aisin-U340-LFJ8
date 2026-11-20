"""Run the stock H03 P0745 monitor, arbiter and output path in the M32R simulator."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from check_h03_link import identify_h03


START = """
    .section .stock,"ax",@progbits
    .incbin "stock.bin"

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
  .stock 0 : { *(.stock) }
  .boot 0x100000 : { *(.boot) }
  .text : { *(.text*) *(.rodata*) }
  /DISCARD/ : { *(.note*) *(.comment) }
}
"""

FIXTURE = """
#include <stdint.h>

#define RAM8(a) (*(volatile uint8_t *)(uintptr_t)(a))
#define RAM16(a) (*(volatile uint16_t *)(uintptr_t)(a))
#define RAM32(a) (*(volatile uint32_t *)(uintptr_t)(a))

enum {
    VOLTAGE_VBAT = 0x805084,
    PRESSURE_PROPOSAL = 0x80508C,
    CURRENT_REQUEST = 0x805094,
    PWM_WIDTH = 0x8048CC,
    OEM_CRITICAL_STACK = 0x809F9C,
    ADC0_AN3 = 0x804BC0,
    REMAINING = 0x804EAC,
    P0745 = 0x806356,
    CLEAR_REQUEST = 0x80637C,
    P10DATA = 0x80070A,
    P10SEL = 0x80074A,
    TIO4RL1 = 0x800344,
    TIO4RL0 = 0x800346,
};

enum {
    ONE_AMP = 0x3F800000,
    TWELVE_VOLTS = 0x41400000,
    EIGHT_VOLTS = 0x41000000,
    BELOW_MONITOR_THRESHOLD = 0x3DCFFFBC,
    FULL_COUNTDOWN = 0x42C80000,  /* binary32 100 */
    ONE_MONITOR_STEP = 0x40A00000, /* binary32 5 */
};

static void sample(unsigned count)
{
    void (*monitor)(void) = (void (*)(void))(uintptr_t)0x0346F0;
    for (unsigned i = 0; i < count; ++i) {
        monitor();
    }
}

static int check_actuator_path(void)
{
    void (*arbitrate)(void) = (void (*)(void))(uintptr_t)0x0717B8;
    void (*apply)(void) = (void (*)(void))(uintptr_t)0x046900;
    void (*clear)(void) = (void (*)(void))(uintptr_t)0x071FF4;

    RAM32(OEM_CRITICAL_STACK) = OEM_CRITICAL_STACK;
    RAM32(PRESSURE_PROPOSAL) = ONE_AMP;
    RAM32(VOLTAGE_VBAT) = TWELVE_VOLTS;
    RAM8(P0745) = 0;
    RAM8(P10SEL) = 0xa0u;
    RAM8(P10DATA) = 0xf3u;
    arbitrate();
    apply();
    if (RAM32(CURRENT_REQUEST) != ONE_AMP || RAM16(PWM_WIDTH) != 1000u ||
        RAM8(P10SEL) != 0xa1u || RAM16(TIO4RL1) != 1999u || RAM16(TIO4RL0) != 999u) {
        return 11;
    }

    RAM16(ADC0_AN3) = 307u << 6;
    sample(1);
    RAM16(ADC0_AN3) = 0;
    sample(20);
    if (RAM8(P0745) != 1u || RAM32(CURRENT_REQUEST) != ONE_AMP ||
        RAM8(P10SEL) != 0xa1u || RAM16(TIO4RL1) != 1999u || RAM16(TIO4RL0) != 999u) {
        return 12;
    }

    arbitrate();
    if (RAM32(CURRENT_REQUEST) != 0u || RAM32(PRESSURE_PROPOSAL) != ONE_AMP ||
        RAM8(P10SEL) != 0xa1u || RAM16(TIO4RL1) != 1999u || RAM16(TIO4RL0) != 999u) {
        return 13;
    }

    apply();
    if (RAM8(P10SEL) != 0xa0u || RAM8(P10DATA) != 0xf2u ||
        RAM16(PWM_WIDTH) != 1u || RAM16(TIO4RL1) != 2998u || RAM16(TIO4RL0) != 0u) {
        return 14;
    }

    RAM8(CLEAR_REQUEST) = 1;
    clear();
    apply();
    if (RAM8(P0745) || RAM32(CURRENT_REQUEST) != 0u ||
        RAM8(P10SEL) != 0xa0u || RAM8(P10DATA) != 0xf2u) {
        return 15;
    }

    /* Stock arbitration can reuse that proposal after the diagnostic clear. */
    arbitrate();
    apply();
    if (RAM32(CURRENT_REQUEST) != ONE_AMP || RAM8(P10SEL) != 0xa1u ||
        RAM16(TIO4RL1) != 1999u || RAM16(TIO4RL0) != 999u) {
        return 16;
    }
    return 0;
}

int main(void)
{
    void (*clear)(void) = (void (*)(void))(uintptr_t)0x071FF4;

    RAM32(CURRENT_REQUEST) = ONE_AMP;
    RAM32(VOLTAGE_VBAT) = TWELVE_VOLTS;
    RAM8(P0745) = 0;
    RAM32(REMAINING) = 0;
    RAM16(ADC0_AN3) = 307u << 6; /* In-window feedback at this request. */
    RAM8(P10DATA) = 0xf3u;
    RAM8(P10SEL) = 0xa1u;
    RAM16(TIO4RL1) = 0x0219u;
    RAM16(TIO4RL0) = 0x010fu;
    sample(1);
    if (RAM32(REMAINING) != FULL_COUNTDOWN || RAM8(P0745)) {
        return 1;
    }

    RAM16(ADC0_AN3) = 0;
    sample(19);
    if (RAM32(REMAINING) != ONE_MONITOR_STEP || RAM8(P0745)) {
        return 2;
    }
    sample(1);
    if (RAM32(REMAINING) != 0 || RAM8(P0745) != 1) {
        return 3;
    }
    if (RAM32(CURRENT_REQUEST) != ONE_AMP || RAM8(P10DATA) != 0xf3u ||
        RAM8(P10SEL) != 0xa1u || RAM16(TIO4RL1) != 0x0219u ||
        RAM16(TIO4RL0) != 0x010fu) {
        return 4;
    }

    RAM16(ADC0_AN3) = 307u << 6;
    sample(1);
    if (RAM32(REMAINING) != FULL_COUNTDOWN || RAM8(P0745) != 1) {
        return 5;
    }
    RAM8(CLEAR_REQUEST) = 0;
    clear();
    if (RAM8(P0745) != 1) {
        return 6;
    }
    RAM8(CLEAR_REQUEST) = 1;
    clear();
    if (RAM8(P0745)) {
        return 7;
    }
    RAM8(CLEAR_REQUEST) = 0;

    RAM16(ADC0_AN3) = 608u << 6;
    sample(20);
    if (RAM32(REMAINING) != 0 || RAM8(P0745) != 1) {
        return 8;
    }
    RAM8(P0745) = 0;
    RAM32(VOLTAGE_VBAT) = EIGHT_VOLTS;
    sample(25);
    if (RAM32(REMAINING) != FULL_COUNTDOWN || RAM8(P0745)) {
        return 9;
    }
    RAM32(VOLTAGE_VBAT) = TWELVE_VOLTS;
    RAM32(CURRENT_REQUEST) = BELOW_MONITOR_THRESHOLD;
    sample(25);
    if (RAM32(REMAINING) != FULL_COUNTDOWN || RAM8(P0745)) {
        return 10;
    }
    return check_actuator_path();
}
"""

SCENARIOS = (
    "in_range_loads_countdown",
    "low_feedback_at_19_calls",
    "low_feedback_latches_at_20_calls",
    "fault_latch_leaves_actuator_registers_unchanged",
    "in_range_feedback_does_not_clear_latch",
    "separate_clear_path_without_request",
    "separate_clear_path_with_request",
    "high_feedback_latches_at_20_calls",
    "voltage_at_8v_does_not_arm_monitor",
    "current_below_arm_threshold_does_not_arm_monitor",
    "actuator_path_starts_with_pwm_applied",
    "second_fault_before_arbitration_preserves_pwm",
    "arbitration_zeroes_request_but_leaves_pwm_until_apply",
    "apply_selects_gpio_low_and_updates_reloads",
    "clear_then_apply_keeps_last_zero_result",
    "stock_rearbitration_can_restore_the_old_proposal",
)


def check(base, compiler):
    identity = identify_h03(base)
    rom = base.read_bytes()
    if sha256(rom).hexdigest() != identity["sha256"]:
        raise ValueError("H03 changed while the fixture was being prepared")

    with TemporaryDirectory(prefix="rbm-h03-slt-fault-") as directory:
        work = Path(directory)

        def run(*args):
            return subprocess.run([str(arg) for arg in args], cwd=work, check=True,
                                  capture_output=True, timeout=30).stdout

        if run(compiler, "-dumpmachine").strip() != b"m32r-elf":
            raise ValueError("A bare-metal M32R compiler is required")
        version = run(compiler, "--version").decode().splitlines()[0]
        (work / "stock.bin").write_bytes(rom)
        (work / "fixture.S").write_text(START, encoding="ascii")
        (work / "fixture.ld").write_text(LAYOUT, encoding="ascii")
        (work / "fixture.c").write_text(FIXTURE, encoding="ascii")
        run(compiler, "-m32r", "-Wa,-EB", "-Os", "-ffreestanding", "-nostdlib",
            "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wl,-T,fixture.ld",
            "fixture.S", "fixture.c", "-o", "fixture.elf")
        simulator = compiler.with_name(f"m32r-elf-run{compiler.suffix}")
        try:
            run(simulator, "--memory-size", "16M", "fixture.elf")
        except subprocess.CalledProcessError as error:
            if 0 < error.returncode <= len(SCENARIOS):
                raise ValueError(f"Unexpected P0745 result in {SCENARIOS[error.returncode - 1]}") from error
            raise

    return {
        "base": identity,
        "compiler": version,
        "simulated_scenarios": list(SCENARIOS),
        "native_monitor": "0x0346F0",
        "native_clear_path": "0x071FF4",
        "consecutive_out_of_range_calls_before_fault": 20,
        "in_range_feedback_clears_fault": False,
        "latch_writes_actuator_registers": False,
        "native_pressure_arbiter": "0x0717B8",
        "native_apply_path": "0x046900",
        "arbiter_zero_disconnects_pwm_without_apply": False,
        "apply_after_zero_selects_gpio_low": True,
        "stock_rearbitration_after_clear_can_reuse_unchanged_proposal": True,
        "hardware_executed": False,
        "target_image_emitted": False,
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
