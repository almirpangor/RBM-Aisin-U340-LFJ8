"""Exercise the H03 wait hook and production phase deadline check in M32R."""

import argparse
from hashlib import sha256
import json
import re
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
IRQ_START = 0x3DE0
IRQ_END = 0x3E40
PSW_HELPERS_START = 0x3E50
PSW_HELPERS_END = 0x3E78
TOP8_START = 0xACD8
TOP8_END = 0xB1C0
RELEASE_SITE = 0x040424
STOCK_RELEASES = (
    ("stock_release", 0x040468, 0x0404C4),
    ("stock_release_helper", 0x00A06C, 0x00A0B0),
)
STOCK_WAIT = bytes.fromhex("E4804ADE2094F000B080FFFE60002004")
FIXTURE = r"""

    /* Route a simulator TRAP into the RAM-backed OEM vector chain. */
    .macro test_irq target
    push r0
    push r1
    ld24 r0,#0x800000
    ld24 r1,#0x1200
    sth r1,@r0
    ld24 r0,#0x1200
    ld24 r1,#0x1204
    st r1,@r0
    ld24 r1,#\target
    st r1,@(4,r0)
    pop r1
    pop r0
    .p2align 2
    trap #3 || nop
    .endm

    /* Record SP without debugger breakpoints in the nested exception path. */
    .macro sample_irq_sp offset
    ld24 r1,#0x1220
    st sp,@(\offset,r1)
    .endm

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
    push r0
    ld24 r0,#0x1238
    ld r0,@r0
    beqz r0,fixture_skip_irq
    pop r0
    ldi r0,#CARRY
    ldi r1,#0
    cmpu r1,r0
    ld24 r0,#0x12345
    ld24 r5,#0x54321
    test_irq fixture_irq_outer
    .p2align 2
fixture_irq_foreground_resume:
    sample_irq_sp 12
    mvfc r1,psw
    and3 r1,r1,#1
    ldi r3,#CARRY
    bne r1,r3,fail
    ld24 r1,#0x12345
    bne r0,r1,fail
    ld24 r1,#0x54321
    bne r5,r1,fail
    bra fixture_enter_poll
fixture_skip_irq:
    pop r0
fixture_enter_poll:
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
    .p2align 2
    .global fixture_callback_return
fixture_callback_return:
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

#if NATIVE_PUBLISH
    .section .text.fixture_native_publish,"ax"
    .p2align 2
    .global fixture_native_publish
fixture_native_publish:
    push lr
    push r9
    ld24 r4,#0x804862
    ldi r0,#0
    stb r0,@r4
    ld24 r4,#0x804861
    ldi r0,#7
    stb r0,@r4
    ld24 r4,#0x804864
    ldi r0,#5
    stb r0,@r4
    ld24 r4,#0x800745
    ldi r0,#0x10
    stb r0,@r4
    ld24 r9,#.Lnative_release_return
    bra.l fixture_native_release_site
    .p2align 2
.Lnative_release_return:
    pop r9
    pop lr
    jmp lr

    .section .native_release_site,"ax"
fixture_native_release_site:
    bl.l rbm_h03_phase_release_hook
    jmp r9 || nop

    .section .stock_release,"ax"
    .global h03_stock_phase_release
h03_stock_phase_release:
    .incbin "stock_release.dat"

    .section .stock_release_helper,"ax"
    .incbin "stock_release_helper.dat"
#endif

    .section .trap_vector,"ax"
    bra.l h03_stock_irq

    .section .oem_irq,"ax"
h03_stock_irq:
    .incbin "irq.dat"

    .section .test_irq,"ax"
    .p2align 2
fixture_irq_outer:
    sample_irq_sp 0
    ld24 r0,#0x11111
    ld24 r5,#0x55555
#if OEM_TOP8
    test_irq fixture_irq_top8
#else
    test_irq fixture_irq_inner
#endif
    .p2align 2
fixture_irq_outer_resume:
    sample_irq_sp 8
    ld24 r1,#0x11111
    bne r0,r1,fixture_irq_fail
    ld24 r1,#0x55555
    bne r5,r1,fixture_irq_fail
    jmp lr
fixture_irq_fail:
    bra.l fail

    .p2align 2
#if OEM_TOP8
fixture_irq_top8:
    sample_irq_sp 4
    bra.l h03_stock_top8
#else
fixture_irq_inner:
    sample_irq_sp 4
    ld24 r0,#0x22222
    ld24 r5,#0x66666
    jmp lr
#endif

    .section .oem_psw,"ax"
    .incbin "psw-helpers.dat"

    .section .oem_top8,"ax"
h03_stock_top8:
    .incbin "top8.dat"
"""
LAYOUT = """ENTRY(_start)
SECTIONS {
  .trap_vector 0x4c : { KEEP(*(.trap_vector)) }
  .entry 0x1000 : { *(.entry) }
  .test_irq 0x1240 : { KEEP(*(.test_irq)) }
  .oem_irq 0x3de0 : { KEEP(*(.oem_irq)) }
  .oem_psw 0x3e50 : { KEEP(*(.oem_psw)) }
  .wait 0x8150 : { *(.wait) }
  ASSERT(SIZEOF(.wait) == 4, "The replacement branch must fit one word")
  .clear 0x815c : { *(.clear) }
  .stock_release_helper 0xa06c : { KEEP(*(.stock_release_helper)) }
  .oem_top8 0xacd8 : { KEEP(*(.oem_top8)) }
  .native_release_site 0x40424 : { KEEP(*(.native_release_site)) }
  .stock_release 0x40468 : { KEEP(*(.stock_release)) }
  .text 0x60000 : { *(.text .text.*) *(.rodata .rodata.*) }
  .data 0x100000 : { *(.data .data.*) }
  .bss : { *(.bss .bss.*) }
  h03_phase_wait_ticks = 0x8003e0;
  ASSERT(h03_phase_wait_ticks % 4 == 0, "The wait clock needs word alignment")
  ASSERT(h03_phase_wait_interval_ticks > 0 && h03_phase_wait_interval_ticks <= 0xffffff,
         "Invalid wait interval")
}
"""


POLL_INTERVAL = 2
STACK_TOP = 0x9FFFFC
WAIT_BYTES = 8
CALLBACK_ENTRY_BYTES = 64
CALLBACK_LR_BYTES = 4
OEM_IRQ_FRAME_BYTES = 48
PROBE_BYTES = 256
GUARD_BYTES = 16
MARKERS = (0xA53C7ED2, 0x5AC3812D)
CALLBACK_SP = STACK_TOP - CALLBACK_ENTRY_BYTES
PROBE_START = CALLBACK_SP - PROBE_BYTES
TICK_DRIVER = f"""
set confirm off
target sim --memory-size 16M
load
set $samples = 0
set $callbacks = 0
set $verified_irq_levels = 0
break *rbm_h03_phase_wait_tick_sample
commands
  silent
  if $sp != {STACK_TOP - WAIT_BYTES:#x}
    printf "UNEXPECTED WAIT SP %x\\n", $sp
    quit
  end
  set $samples = $samples + 1
  if $samples > 32
    printf "TICK DRIVER LIMIT\\n"
    quit
  end
  if $samples % 2 == 0
    set *(unsigned int*)0x8003e0 = *(unsigned int*)0x8003e0 + 1
  end
  if $release_early && $samples == 2
    set *(unsigned char*)0x804ade = 1
  end
  continue
end
break *rbm_h03_phase_wait_callback
commands
  silent
  if $sp != {CALLBACK_SP:#x}
    printf "UNEXPECTED CALLBACK SP %x\\n", $sp
    quit
  end
  set $callbacks = $callbacks + 1
  set *(unsigned int*)0x1238 = $inject_nested && $callbacks == 5
  if $oem_top8 && $callbacks == 5
    set *(unsigned char*)0x800233 = $top8_status
    set *(unsigned short*)0x8002c2 = 0xffff
    set *(unsigned char*)0x806acc = 0x7e
    set *(unsigned char*)0x806acd = 0
    set *(unsigned int*)0x809f94 = $marker
    set *(unsigned int*)0x809f98 = $marker
    set *(unsigned int*)0x809f9c = 0x809f9c
  end
  restore stack-marker.bin binary {PROBE_START:#x}
  continue
end
break *fixture_callback_return
commands
  silent
  if $sp != {CALLBACK_SP:#x}
    printf "UNEXPECTED CALLBACK RETURN SP %x\\n", $sp
    quit
  end
  if $inject_nested && $callbacks == 5
    if *(unsigned int*)0x1220 != {CALLBACK_SP - CALLBACK_LR_BYTES - OEM_IRQ_FRAME_BYTES:#x} || *(unsigned int*)0x1224 != {CALLBACK_SP - CALLBACK_LR_BYTES - 2 * OEM_IRQ_FRAME_BYTES:#x}
      printf "UNEXPECTED IRQ FRAMES\\n"
      quit
    end
    if *(unsigned int*)0x1228 != *(unsigned int*)0x1220 || *(unsigned int*)0x122c != {CALLBACK_SP - CALLBACK_LR_BYTES:#x}
      printf "UNEXPECTED IRQ RETURN FRAMES\\n"
      quit
    end
    if $oem_top8
      if *(unsigned int*)0x809f9c != 0x809f9c
        printf "TOP8 PSW CURSOR CHANGED\\n"
        quit
      end
      if $top8_status & 0x10
        if *(unsigned char*)0x800233 != 0x28 || *(unsigned short*)0x8002c2 != 1249 || *(unsigned char*)0x806acc != 0 || *(unsigned char*)0x806acd != 1
          printf "TOP8 PENDING PATH DID NOT ADVANCE\\n"
          quit
        end
      else
        if *(unsigned char*)0x800233 != 8 || *(unsigned short*)0x8002c2 != 0xffff || *(unsigned char*)0x806acc != 0x7e || *(unsigned char*)0x806acd != 0
          printf "TOP8 IDLE PATH CHANGED TIMER STATE\\n"
          quit
        end
      end
      if *(unsigned int*)0x809f98 == $marker || *(unsigned int*)0x809f94 != $marker
        printf "UNEXPECTED TOP8 PSW STACK WRITE\\n"
        quit
      end
    end
    set $verified_irq_levels = 2
  end
  set $cursor = {PROBE_START:#x}
  while $cursor < {CALLBACK_SP:#x} && *(unsigned int*)$cursor == $marker
    set $cursor = $cursor + 4
  end
  if $cursor < {PROBE_START + GUARD_BYTES:#x}
    printf "CALLBACK STACK GUARD CHANGED %x\\n", $cursor
    quit
  end
  printf "CALLBACK STACK %d %d\\n", $callbacks, {STACK_TOP:#x} - $cursor
  continue
end
tbreak *fixture_exit
run
printf "RESULT %d %d %d %d\\n", $r1, $samples, $callbacks, $verified_irq_levels
"""


def check(base, compiler):
    identity = identify_h03(base)
    rom = base.read_bytes()
    if sha256(rom).hexdigest() != identity["sha256"]:
        raise ValueError("H03 changed while preparing the wait fixture")
    wait_code = rom[WAIT:CONTINUE]
    if wait_code != STOCK_WAIT:
        raise ValueError("Unexpected instructions at the H03 foreground wait")
    if rom[RELEASE_SITE:RELEASE_SITE + 4] != bytes.fromhex("7E11F000"):
        raise ValueError("Unexpected instructions at the H03 publication call")
    with TemporaryDirectory(prefix="rbm-h03-wait-") as directory:
        work = Path(directory)
        shutil.copyfile(HERE / "h03_phase_wait_hook.S", work / "hook.S")
        (work / "fixture.S").write_text(FIXTURE, encoding="ascii")
        (work / "fixture.ld").write_text(LAYOUT, encoding="ascii")
        (work / "clear.dat").write_bytes(wait_code[CLEAR - WAIT:])
        (work / "irq.dat").write_bytes(rom[IRQ_START:IRQ_END])
        (work / "psw-helpers.dat").write_bytes(rom[PSW_HELPERS_START:PSW_HELPERS_END])
        (work / "top8.dat").write_bytes(rom[TOP8_START:TOP8_END])
        for name, start, end in STOCK_RELEASES:
            (work / f"{name}.dat").write_bytes(rom[start:end])
        (work / "tick-driver.gdb").write_text(TICK_DRIVER, encoding="ascii")
        debugger = compiler.with_name(f"m32r-elf-gdb{compiler.suffix}")
        compiler_version = subprocess.run(
            [compiler, "--version"], check=True, capture_output=True, timeout=15,
        ).stdout.decode(errors="replace").splitlines()[0]
        results = []
        sources = [HERE / name for name in (
            "h03_phase_wait_fixture.c", "lfj8_h03_phase_clock.c", "lfj8_h03_takeover.c",
            "lfj8_h03_mmio.c",
        )]
        for scenario, name, calls, samples, nested, top8_status, native in (
            (0, "ready", 1, 0, False, None, False), (1, "delayed_across_wrap", 3, 8, False, None, False),
            (2, "stalled", 6, 20, False, None, False), (3, "flag_before_next_poll", 2, 2, False, None, False),
            (2, "stalled_nested_irq", 6, 20, True, None, False),
            (2, "stalled_nested_top8_idle", 6, 20, True, 0x08, False),
            (2, "stalled_nested_top8_pending", 6, 20, True, 0x18, False),
            (0, "native_ready", 1, 0, False, None, True),
            (1, "native_delayed_across_wrap", 3, 8, False, None, True),
            (2, "native_stalled_then_late", 6, 20, False, None, True),
            (4, "native_coalesced", 1, 0, False, None, True),
        ):
            top8 = top8_status is not None
            release_hook = [HERE / "h03_phase_release_hook.S"] if native else []
            for carry, marker in enumerate(MARKERS):
                (work / "stack-marker.bin").write_bytes(
                    marker.to_bytes(4, "big") * (PROBE_BYTES // 4)
                )
                subprocess.run(
                    [compiler, "-m32r", "-Wa,-EB", "-mmodel=medium", "-msdata=none", "-std=c99", "-Os", "-g",
                     "-Wall", "-Wextra", "-Werror",
                     "-ffunction-sections", "-fdata-sections", "-nostdlib", "-Wl,--gc-sections,-T,fixture.ld",
                     "-I", CONTROLLER / "include", "-I", CONTROLLER / "vendor" / "toyota" / "include",
                     f"-DSCENARIO={scenario}", f"-DCARRY={carry}", f"-DOEM_TOP8={int(top8)}",
                     f"-DNATIVE_PUBLISH={int(native)}",
                     f"-Wl,--defsym,h03_phase_wait_interval_ticks={POLL_INTERVAL}",
                     "fixture.S", "hook.S", *sources, *release_hook, "-lc", "-lgcc", "-o", "fixture.elf"],
                    cwd=work, check=True, capture_output=True, timeout=15,
                )
                output = subprocess.run(
                    [debugger, "--batch", "-nx", "-ex", f"set $release_early = {int(scenario == 3)}",
                     "-ex", f"set $inject_nested = {int(nested)}",
                     "-ex", f"set $oem_top8 = {int(top8)}",
                     "-ex", f"set $top8_status = {top8_status or 0}",
                     "-ex", f"set $marker = (unsigned int){marker:#x}",
                     "-x", "tick-driver.gdb", "fixture.elf"],
                    cwd=work, check=True, capture_output=True, timeout=15,
                ).stdout
                returns = 2 if nested else 0
                if f"RESULT 0 {samples} {calls} {returns}".encode("ascii") not in output.splitlines():
                    raise ValueError(f"Wait fixture failed ({name}, carry={carry}): "
                                     + output[-1200:].decode(errors="replace"))
                trace = re.findall(rb"^CALLBACK STACK (\d+) (\d+)", output, re.M)
                if [int(number) for number, _ in trace] != list(range(1, calls + 1)):
                    raise ValueError(f"Incomplete callback stack trace ({name}, carry={carry})")
                depths = [int(depth) for _, depth in trace]
                if any(depth <= CALLBACK_ENTRY_BYTES for depth in depths):
                    raise ValueError(f"Callback left no stack trace ({name}, carry={carry})")
                results.append({"scenario": name, "initial_carry": carry, "callback_calls": calls,
                                "clock_samples_while_waiting": samples,
                                "callback_stack_written_bytes": depths,
                                "oem_irq_levels_injected": returns,
                                "oem_top8_status_before": top8_status,
                                "native_release_callbacks": (2 if scenario == 4 else 1) if native else 0,
                                "stock_flag_cleared": True, "phase_consumed": scenario not in (2, 4),
                                "command_revoked": scenario in (2, 4)})
    return {"base": identity, "compiler": compiler_version, "wait": f"0x{WAIT:06X}", "stock_clear": f"0x{CLEAR:06X}",
            "native_continuation": f"0x{CONTINUE:06X}", "cases": results,
            "test_poll_interval_ticks": POLL_INTERVAL, "extra_persistent_ram_bytes": 0,
            "wrapper_stack_bytes": {"waiting": WAIT_BYTES, "at_callback_entry": CALLBACK_ENTRY_BYTES},
            "callback_stack_probe": {
                "kind": "deepest overwritten aligned word below initial wrapper SP",
                "marked_below_callback_entry_bytes": PROBE_BYTES, "guard_bytes": GUARD_BYTES,
                "maximum_written_depth_bytes": max(
                    max(case["callback_stack_written_bytes"]) for case in results
                    if not case["oem_irq_levels_injected"] and not case["native_release_callbacks"]
                ),
                "interrupts_injected": False,
            },
            "nested_irq_probe": {
                "oem_dispatcher_range": ["0x003DE0", "0x003E40"],
                "oem_dispatcher_sha256": sha256(rom[IRQ_START:IRQ_END]).hexdigest(),
                "levels": 2, "frame_bytes_each": OEM_IRQ_FRAME_BYTES,
                "checked_return_context": ["SP", "R0", "R5", "foreground C"],
                "maximum_written_depth_bytes": max(
                    max(case["callback_stack_written_bytes"]) for case in results
                    if case["oem_irq_levels_injected"] and case["oem_top8_status_before"] is None
                ),
                "scope": "Original dispatcher and RTE; simulator TRAP entry and synthetic vector targets.",
            },
            "nested_top8_probe": {
                "oem_handler_range": [f"0x{TOP8_START:06X}", f"0x{TOP8_END:06X}"],
                "oem_handler_sha256": sha256(rom[TOP8_START:TOP8_END]).hexdigest(),
                "oem_psw_helper_range": [f"0x{PSW_HELPERS_START:06X}", f"0x{PSW_HELPERS_END:06X}"],
                "oem_psw_helper_sha256": sha256(rom[PSW_HELPERS_START:PSW_HELPERS_END]).hexdigest(),
                "maximum_written_depth_bytes": max(
                    max(case["callback_stack_written_bytes"]) for case in results
                    if case["oem_top8_status_before"] is not None
                ),
                "psw_stack_written_bytes": 4, "psw_cursor_restored": True,
                "pending_timer_state": {"status_before": 0x18, "status_after": 0x28,
                                        "compare": 1249, "next_state": 1},
                "scope": "Synthetic outer handler; original TOP8/9 idle and pending state-0 paths.",
            },
            "native_release_probe": {
                "hook_call": f"0x{RELEASE_SITE:06X}",
                "oem_fragments": {
                    name: {"range": [f"0x{start:06X}", f"0x{end:06X}"],
                           "sha256": sha256(rom[start:end]).hexdigest()}
                    for name, start, end in STOCK_RELEASES
                },
                "scope": "Native phase publisher and foreground wait with common RAM-backed TML0CT.",
            },
            "platform_io": {"clock_address": "0x8003E0", "clock_read_bits": 32,
                            "checks_interrupt_mask_and_restore": True},
            "scope": "Target MMIO, phase clock and takeover code; RAM-backed clock, flag and inhibit.",
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
