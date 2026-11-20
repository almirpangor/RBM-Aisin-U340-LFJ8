"""Run the stock H03 P0745 monitor, arbiter and output path in the M32R simulator."""

import argparse
from hashlib import sha256
import json
import re
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from check_h03_link import identify_h03


START = """
    .section .stock,"ax",@progbits
#if H03_SLT_FAULT_HOOK
    .incbin "stock.bin",0,0x03484c
    bra rbm_h03_slt_fault_hook
    .incbin "stock.bin",0x034850
#else
    .incbin "stock.bin"
#endif

    .section .boot,"ax",@progbits
    .global _start
_start:
    ld24 sp,#0x9ffffc
    setpsw #0x40
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
  /DISCARD/ : { *(.note*) *(.comment) }
}
h03_slt_fault_resume = 0x034850;
"""

FIXTURE = """
#include <stdint.h>
#include "lfj8_h03_mmio.h"
#include "lfj8_h03_takeover.h"

#define RAM8(a) (*(volatile uint8_t *)(uintptr_t)(a))
#define RAM16(a) (*(volatile uint16_t *)(uintptr_t)(a))
#define RAM32(a) (*(volatile uint32_t *)(uintptr_t)(a))

enum {
    VOLTAGE_VBAT = 0x805084,
    PRESSURE_PROPOSAL = 0x80508C,
    CURRENT_REQUEST = 0x805094,
    PWM_WIDTH = 0x8048CC,
    OEM_CRITICAL_STACK = 0x809F9C,
    STARTUP_COUNT = 0x80621A,
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

Lfj8H03Takeover rbm_h03_takeover_state;
static unsigned inhibits;
static unsigned delivered;
static unsigned fault_notifications;
static uint32_t notification_ie;

static void write_word(void *context, uint32_t address, uint32_t value)
{
    (void)context;
    RAM32(address) = value;
}

static uint32_t clock_ticks(void *context)
{
    (void)context;
    return 100;
}

static int qualified(void *context)
{
    (void)context;
    return 1;
}

static void arbitrate(void *context)
{
    (void)context;
    ((void (*)(void))(uintptr_t)0x0717B8)();
}

static void apply(void *context)
{
    (void)context;
    ++delivered;
    ((void (*)(void))(uintptr_t)0x046900)();
}

static void inhibit(void *context)
{
    (void)context;
    ++inhibits;
    if (RAM8(P0745)) {
        uint32_t psw;
        __asm__ volatile ("mvfc %0,psw" : "=r"(psw));
        ++fault_notifications;
        notification_ie |= psw & 0x40u;
    }
}

static int check_revocation(void)
{
    static const Lfj8H03TakeoverOps ops = {
        .io = &lfj8_h03_mmio, .write32 = write_word, .clock_ticks = clock_ticks,
        .qualified = qualified, .arbitrate = arbitrate, .apply = apply, .inhibit = inhibit,
        .isolated_pwm_mask = LFJ8_H03_ALL_SPARE_PWM_ISOLATED,
    };
    const Lfj8H03OutputPlan plan = {
        .pressure_mailbox = PRESSURE_PROPOSAL, .pressure_binary32 = ONE_AMP,
        .pressure_request_ma = 1000u, .toyota_compare = 400u,
    };
    Lfj8H03Takeover *state = &rbm_h03_takeover_state;
    RAM16(STARTUP_COUNT) = 3u;
    RAM8(CLEAR_REQUEST) = 0u;
    RAM16(ADC0_AN3) = 307u << 6;
    sample(1);
    if (!lfj8_h03_takeover_init(state, &ops, 10) ||
        !lfj8_h03_takeover_prepare_plan(state, &plan, 1, 100)) {
        return 17;
    }
    RAM16(ADC0_AN3) = 0;
    sample(20);
    if (RAM8(P0745) != 1u || state->pending != 1u - H03_SLT_FAULT_HOOK ||
        fault_notifications != H03_SLT_FAULT_HOOK || notification_ie != 0u) {
        return 18;
    }

    RAM8(CLEAR_REQUEST) = 1u;
    ((void (*)(void))(uintptr_t)0x071FF4)();
    if (RAM8(P0745) || lfj8_h03_takeover_apply(state, 1) != 1 - H03_SLT_FAULT_HOOK ||
        delivered != 1u - H03_SLT_FAULT_HOOK || inhibits != 2u * H03_SLT_FAULT_HOOK) {
        return 19;
    }
    if (lfj8_h03_takeover_prepare_plan(state, &plan, 1, 100) ||
        !lfj8_h03_takeover_prepare_plan(state, &plan, 2, 100) ||
        !lfj8_h03_takeover_apply(state, 2) || delivered != 2u - H03_SLT_FAULT_HOOK) {
        return 20;
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
    const int result = check_actuator_path();
    return result ? result : check_revocation();
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
    "takeover_prepares_one_generation_before_fault",
    "latch_reaches_revoke_only_in_the_hooked_variant",
    "cleared_fault_accepts_old_generation_only_without_hook",
    "duplicate_prepare_rejects_and_next_generation_can_be_applied",
)


def probe_fault_hook(run, work, debugger, active):
    script = work / "probe-hook.gdb"
    condition = "!=" if active else "=="
    preserved = [f"$r{i}" for i in range(1, 13)] + ["$fp", "$lr", "$psw", "$accl", "$acch"]
    registers = ", ".join(preserved)
    register_format = " ".join(["%08x"] * len(preserved))
    script.write_text(f"""
set confirm off
set pagination off
target sim --memory-size 16M
load
break *rbm_h03_slt_fault_hook if rbm_h03_takeover_state.ops {condition} 0
run
printf "CPU_BEFORE {register_format}\\n", {registers}
set $start_sp = $sp
set $low_sp = $sp
set $steps = 0
set $mask_start = -1
set $mask_end = -1
while $pc != 0x034850 && $steps < 512
  if $pc == &h03_slt_fault_mask_irq
    set $mask_start = $steps
  end
  if $pc == &h03_slt_fault_restore_irq
    set $mask_end = $steps + 1
  end
  stepi
  if $sp < $low_sp
    set $low_sp = $sp
  end
  set $steps = $steps + 1
end
printf "HOOK %08x %08x %08x %08x %d %d %d\\n", $pc, $start_sp, $low_sp, $sp, $steps, $mask_start, $mask_end
printf "CPU_AFTER {register_format}\\n", {registers}
printf "LATCH %08x %08x\\n", $r0, *(unsigned char*)0x806356
""", encoding="ascii")
    log = run(debugger, "--batch", "-nx", "-x", script.name, "fixture.elf")
    result = re.search(rb"^HOOK ((?:[0-9a-f]{8} ){4})([0-9-]+ [0-9-]+ [0-9-]+)\r?$", log, re.M)
    if result is None:
        raise ValueError(f"P0745 hook trace did not complete (owner active={active}): {log[-1200:]!r}")
    pc, start, low, end = (int(field, 16) for field in result[1].split())
    steps, mask_start, mask_end = (int(field) for field in result[2].split())
    if pc != 0x034850 or start != end or low >= start or not 0 <= mask_start < mask_end <= steps:
        raise ValueError(f"Invalid P0745 stack or mask trace (owner active={active}): {result[0]!r}")
    before = re.search(rb"^CPU_BEFORE ([0-9a-f ]+)\r?$", log, re.M)
    after = re.search(rb"^CPU_AFTER ([0-9a-f ]+)\r?$", log, re.M)
    if before is None or after is None or before[1] != after[1] or (
            re.search(rb"^LATCH 00000001 00000001\r?$", log, re.M) is None):
        raise ValueError(f"P0745 hook changed the continuation context (owner active={active})")
    return {"additional_stack_bytes": start - low, "simulator_steps": steps,
            "mask_through_restore_steps": mask_end - mask_start}


def check(base, compiler):
    identity = identify_h03(base)
    rom = base.read_bytes()
    if sha256(rom).hexdigest() != identity["sha256"]:
        raise ValueError("H03 changed while the fixture was being prepared")
    if rom[0x03484C:0x034850] != bytes.fromhex("60012004"):
        raise ValueError("Unexpected stock P0745 latch word")

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
        here = Path(__file__).resolve().parent
        root = here.parents[1]
        simulator = compiler.with_name(f"m32r-elf-run{compiler.suffix}")
        objcopy = compiler.with_name(f"m32r-elf-objcopy{compiler.suffix}")
        for hooked in (0, 1):
            run(compiler, "-m32r", "-Wa,-EB", "-Os", "-g", "-ffreestanding", "-nostdlib",
                "-ffunction-sections", "-fdata-sections",
                "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wl,-T,fixture.ld,--gc-sections",
                f"-DH03_SLT_FAULT_HOOK={hooked}", f"-I{here}", f"-I{root / 'controller/include'}",
                f"-I{root / 'controller/vendor/toyota/include'}",
                "fixture.S", "fixture.c", here / "h03_slt_fault_hook.S", here / "lfj8_h03_takeover.c",
                here / "lfj8_h03_outputs.c", here / "lfj8_h03_mmio.c", "-lc", "-lgcc",
                "-o", "fixture.elf")
            run(objcopy, "-j", ".stock", "-O", "binary", "fixture.elf", "linked-stock.bin")
            linked = (work / "linked-stock.bin").read_bytes()
            if len(linked) != len(rom) or linked[:0x03484C] != rom[:0x03484C] or linked[0x034850:] != rom[0x034850:]:
                raise ValueError("The simulator ROM differs outside the P0745 latch word")
            if (hooked and linked[0x03484C] != 0xFF) or (not hooked and linked != rom):
                raise ValueError("P0745 latch was not linked as expected")
            try:
                run(simulator, "--memory-size", "16M", "fixture.elf")
            except subprocess.CalledProcessError as error:
                if 0 < error.returncode <= len(SCENARIOS):
                    scenario = SCENARIOS[error.returncode - 1]
                    raise ValueError(f"Unexpected P0745 result in {scenario} (hooked={hooked})") from error
                raise

        debugger = compiler.with_name(f"m32r-elf-gdb{compiler.suffix}")
        hook_probe = {
            "owner_uninitialized": probe_fault_hook(run, work, debugger, False),
            "active_revoke_with_test_inhibit": probe_fault_hook(run, work, debugger, True),
        }

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
        "latch_hook": "0x03484C",
        "takeover_can_apply_old_generation_after_clear_without_latch_hook": True,
        "latch_hook_revokes_old_generation_and_invokes_inhibit": True,
        "latch_hook_probe": hook_probe,
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
