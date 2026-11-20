"""Exercise the H03 wait hook and production phase deadline check in M32R."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

from check_h03_link import identify_h03


HERE = Path(__file__).resolve().parent
CONTROLLER = HERE.parent.parent / "controller"
WAIT = 0x8150
CLEAR = 0x815C
CONTINUE = 0x8160
STOCK_WAIT = bytes.fromhex("E4804ADE2094F000B080FFFE60002004")
FIXTURE = r"""
    .section .entry,"ax"
    .global _start
_start:
    ld24 sp,#0x9ffffc
    bl.l fixture_init
    bnez r0,entry_initialized
    bra.l fail
entry_initialized:
    ld24 lr,#0x123400
    ld24 r1,#0x654321
    ld24 r2,#0x789abc
    mvtaclo r2
    ldi r2,#0x40+CARRY
    mvtc r2,psw
    ld24 r2,#0x234567
    ld24 r8,#0x13579b
    bra phase_wait_site

    .section .wait,"ax"
phase_wait_site:
    bra.l rbm_h03_phase_wait_hook

    .section .clear,"ax"
    .global h03_stock_phase_clear
h03_stock_phase_clear:
    .incbin "clear.dat"
    bra check_return

    .text
    .global rbm_h03_phase_wait_callback
rbm_h03_phase_wait_callback:
    push lr
    bl fixture_poll
    pop lr
    beqz r0,fail
    ldi r0,#0
    mvtaclo r0
    mvtachi r0
    ldi r1,#1
#if CARRY
    cmpu r0,r1
#else
    cmpu r1,r0
#endif
    jmp lr

check_return:
    ld24 r3,#0x234567
    bne r2,r3,fail
    ld24 r3,#0x13579b
    bne r8,r3,fail
    mvfc r3,psw
    and3 r3,r3,#1
    ldi r2,#CARRY
    bne r3,r2,fail
    bnez r0,fail
    ld24 r2,#0x654321
    bne r1,r2,fail
    ld24 r2,#0x804ade
    bne r4,r2,fail
    ldub r2,@r4
    bnez r2,fail
    ld24 r2,#0x123400
    bne lr,r2,fail
    ld24 r2,#0x9ffffc
    bne sp,r2,fail
    mvfaclo r3
    ld24 r2,#0x789abc
    bne r3,r2,fail
    bl fixture_finish
    beqz r0,fail
    ldi r1,#0
    bra finish
fail:
    ldi r1,#1
finish:
    ldi r0,#1
    .p2align 2
    .global fixture_exit
fixture_exit:
    trap #0
"""
LAYOUT = """ENTRY(_start)
SECTIONS {
  .entry 0x1000 : { *(.entry) }
  .wait 0x8150 : { *(.wait) }
  ASSERT(SIZEOF(.wait) == 4, "The replacement branch must fit one word")
  .clear 0x815c : { *(.clear) }
  .text 0x60000 : { *(.text .text.*) *(.rodata .rodata.*) }
  .data 0x100000 : { *(.data .data.*) }
  .bss : { *(.bss .bss.*) }
  h03_phase_wait_ticks = fixture_ticks;
  ASSERT(h03_phase_wait_ticks % 4 == 0, "The wait clock needs word alignment")
  ASSERT(h03_phase_wait_interval_ticks > 0 && h03_phase_wait_interval_ticks <= 0xffffff,
         "Invalid wait interval")
}
"""


POLL_INTERVAL = 2
TICK_DRIVER = """
set confirm off
target sim --memory-size 16M
load
set $samples = 0
set $callbacks = 0
break *rbm_h03_phase_wait_tick_sample
commands
  silent
  if $sp != 0x9ffff4
    printf "UNEXPECTED WAIT SP %x\\n", $sp
    quit
  end
  set $samples = $samples + 1
  if $samples > 32
    printf "TICK DRIVER LIMIT\\n"
    quit
  end
  if $samples % 2 == 0
    set variable fixture_ticks = fixture_ticks + 1
  end
  if $release_early && $samples == 2
    set *(unsigned char*)0x804ade = 1
  end
  continue
end
break *rbm_h03_phase_wait_callback
commands
  silent
  if $sp != 0x9fffbc
    printf "UNEXPECTED CALLBACK SP %x\\n", $sp
    quit
  end
  set $callbacks = $callbacks + 1
  continue
end
tbreak *fixture_exit
run
printf "RESULT %d %d %d\\n", $r1, $samples, $callbacks
"""


def check(base, compiler):
    identity = identify_h03(base)
    rom = base.read_bytes()
    if sha256(rom).hexdigest() != identity["sha256"]:
        raise ValueError("H03 changed while preparing the wait fixture")
    wait_code = rom[WAIT:CONTINUE]
    if wait_code != STOCK_WAIT:
        raise ValueError("Unexpected instructions at the H03 foreground wait")
    with TemporaryDirectory(prefix="rbm-h03-wait-") as directory:
        work = Path(directory)
        shutil.copyfile(HERE / "h03_phase_wait_hook.S", work / "hook.S")
        (work / "fixture.S").write_text(FIXTURE, encoding="ascii")
        (work / "fixture.ld").write_text(LAYOUT, encoding="ascii")
        (work / "clear.dat").write_bytes(wait_code[CLEAR - WAIT:])
        (work / "tick-driver.gdb").write_text(TICK_DRIVER, encoding="ascii")
        debugger = compiler.with_name(f"m32r-elf-gdb{compiler.suffix}")
        results = []
        sources = [HERE / name for name in (
            "h03_phase_wait_fixture.c", "lfj8_h03_phase_clock.c", "lfj8_h03_takeover.c",
        )]
        for scenario, name, calls, samples in (
            (0, "ready", 1, 0), (1, "delayed_across_wrap", 3, 8),
            (2, "stalled", 6, 20), (3, "flag_before_next_poll", 2, 2),
        ):
            for carry in (0, 1):
                subprocess.run(
                    [compiler, "-m32r", "-Wa,-EB", "-mmodel=medium", "-msdata=none", "-std=c99", "-Os", "-g",
                     "-Wall", "-Wextra", "-Werror",
                     "-ffunction-sections", "-fdata-sections", "-nostdlib", "-Wl,--gc-sections,-T,fixture.ld",
                     "-I", CONTROLLER / "include", "-I", CONTROLLER / "vendor" / "toyota" / "include",
                     f"-DSCENARIO={scenario}", f"-DCARRY={carry}",
                     f"-Wl,--defsym,h03_phase_wait_interval_ticks={POLL_INTERVAL}",
                     "fixture.S", "hook.S", *sources, "-lc", "-lgcc", "-o", "fixture.elf"],
                    cwd=work, check=True, capture_output=True, timeout=15,
                )
                output = subprocess.run(
                    [debugger, "--batch", "-nx", "-ex", f"set $release_early = {int(scenario == 3)}",
                     "-x", "tick-driver.gdb", "fixture.elf"],
                    cwd=work, check=True, capture_output=True, timeout=15,
                ).stdout
                if f"RESULT 0 {samples} {calls}".encode("ascii") not in output.splitlines():
                    raise ValueError(f"Wait fixture failed ({name}, carry={carry}): "
                                     + output[-1200:].decode(errors="replace"))
                results.append({"scenario": name, "initial_carry": carry, "callback_calls": calls,
                                "clock_samples_while_waiting": samples,
                                "stock_flag_cleared": True, "phase_consumed": scenario != 2,
                                "command_revoked": scenario == 2})
    return {"base": identity, "wait": f"0x{WAIT:06X}", "stock_clear": f"0x{CLEAR:06X}",
            "native_continuation": f"0x{CONTINUE:06X}", "cases": results,
            "test_poll_interval_ticks": POLL_INTERVAL, "extra_persistent_ram_bytes": 0,
            "wrapper_stack_bytes": {"waiting": 8, "at_callback_entry": 64},
            "scope": "Real C phase clock and takeover check; synthetic clock, OEM flag and inhibit.",
            "hardware_executed": False, "flashable_image": None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--gcc", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.suffix.lower() != ".json" or args.out.resolve() == args.base.resolve():
        parser.error("--out must be a separate JSON report")
    try:
        result = check(args.base, args.gcc.resolve())
    except subprocess.CalledProcessError as error:
        parser.exit(1, (error.stderr or str(error).encode()).decode(errors="replace") + "\n")
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"{error}\n")
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
