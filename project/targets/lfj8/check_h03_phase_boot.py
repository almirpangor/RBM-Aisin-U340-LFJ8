"""Run the H03 reset, application owner and native foreground hooks in M32R."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory

from check_h03_link import TARGET, identify_h03
from check_h03_sensor_native import SITES as SENSOR_SITES
from check_h03_phase_wait import IRQ_START, IRQ_END, PSW_HELPERS_START, PSW_HELPERS_END
import lfj8_h03_application_placement as application_placement
from lfj8_h03_layout import PROFILES, read_elf


HERE = Path(__file__).resolve().parent
CONTROLLER = HERE.parent.parent / "controller"
DIAGNOSTICS = CONTROLLER.parent / "diagnostics"
FRAGMENTS = (
    ("reset_dispatch", 0x003DC8, 0x003DE0),
    ("marker_check", 0x004210, 0x00423C),
    ("header_marker", 0x008000, 0x008002),
    ("trailer_marker", 0x07FFFE, 0x080000),
    ("handoff", 0x008084, 0x008088),
    ("cold_entry", 0x008100, 0x008104),
    ("startup", 0x008104, 0x00814C),
    ("startup_call", 0x00814C, 0x008150),
    ("first_wait", 0x008150, 0x008160),
    ("input_call", 0x00816C, 0x008170),
    ("stock_inputs", 0x040324, 0x04039C),
    ("stock_timer", 0x00A82C, 0x00A868),
    ("release_helper", 0x00A06C, 0x00A0B0),
    ("stock_release", 0x040468, 0x0404C4),
    ("irq", IRQ_START, IRQ_END),
    ("psw_helpers", PSW_HELPERS_START, PSW_HELPERS_END),
    ("s51_irq", 0x00A9EC, 0x00AA50),
    ("s83_irq", 0x00AA50, 0x00AAA8),
)
# Other initialization routines are not exercised by this fixture. The CAN
# initialization stub is special: it advances TML0CT and leaves a stock flag.
STUBS = (0x00B704, 0x0404C4, 0x04054C, 0x04050C, 0x0089EC,
         0x034000, 0x046774, 0x008FFC, 0x004784, 0x034004,
         0x00A0CC, 0x00BED8, 0x00D108, 0x04039C, 0x0403C0, 0x046794, 0x0467A0)
CASES = ("stock", "owned", "invalid_period", "unowned", "bad_header", "bad_trailer",
         "partial", "stopped_h03", "duplicate", "toyota_gap", "restart", "stopped_toyota",
         "bad_clock", "no_provider", "coalesced", "overtaken", "sensor_clock_changed",
         "sensor_bad_config", "sensor_bad_startup", "adapt_no_store", "adapt_erased",
         "adapt_saved", "adapt_corrupt", "adapt_torn", "adapt_unreadable", "adapt_reset",
         "adapt_restart", "adapt_alias", "adapt_s01_cold", "adapt_bad_kind",
         "adapt_cold_no_work", "engine", "engine_bad_time", "engine_bad_config")
CLOSED_AT_START = {"invalid_period", "unowned", "partial", "bad_clock", "no_provider",
                   "sensor_bad_startup", "adapt_alias", "adapt_bad_kind", "adapt_cold_no_work",
                   "engine_bad_config"}
BOOT_WINDOW = PROFILES["prefix-candidate"][0]
CANDIDATE_START, CANDIDATE_END = BOOT_WINDOW.start, BOOT_WINDOW.end
FIXTURE = r"""
    .section .entry,"ax"
    .global _start
_start:
    ld24 sp,#0x9ffffc
    ld24 r8,#0x34567
    ld24 r9,#0x45678
    ld24 r0,#0x0789ab
    mvtaclo r0
    mvtachi r0
    ldi r0,#0x40
    mvtc r0,psw
    ld24 r0,#0x8003e0
    seth r1,#0xffff
    or3 r1,r1,#0xfffc
    st r1,@r0
    ld24 r0,#0x80481c
    ldi r1,#INITIAL_MAX
    sth r1,@r0
    bra.l reset_dispatch

    .section .reset_dispatch,"ax"
reset_dispatch:
    .incbin "reset_dispatch.dat"
    .section .marker_check,"ax"
    .incbin "marker_check.dat"
    .section .header_marker,"a"
#if BOOT_CASE == 4
    .short 0
#else
    .incbin "header_marker.dat"
#endif
    .section .trailer_marker,"a"
#if BOOT_CASE == 5
    .short 0
#else
    .incbin "trailer_marker.dat"
#endif
    .section .recovery_stop,"ax"
    bl.l fixture_recovery
    bra.l fixture_done

    .section .handoff,"ax"
    .incbin "handoff.dat"
#if BOOT_CASE == 0
    .section .h03_app_redirect_008100,"ax"
    .incbin "cold_entry.dat"
#endif
    .section .startup,"ax"
    .incbin "startup.dat"
#if BOOT_CASE == 0
    .section .h03_app_redirect_00814c,"ax"
    .incbin "startup_call.dat"
#endif
    .section .first_wait,"ax"
wait_site:
#if BOOT_CASE == 0
    .incbin "first_wait.dat"
#else
    bra.l rbm_h03_phase_wait_hook
    .incbin "first_wait.dat",4,12
#endif
    .section .after_wait,"ax"
    bra.l fixture_after_wait

#if BOOT_CASE == 0
    .section .h03_app_redirect_00816c,"ax"
    .incbin "input_call.dat"
#endif
    .section .input_return,"ax"
    jmp r9 || nop

    .section .stock_inputs,"ax"
    .incbin "stock_inputs.dat"

    .section .mock_adc,"ax"
    ld24 r2,#0x56ff
    sth r2,@r0
    jmp lr

    .section .stock_timer,"ax"
    .incbin "stock_timer.dat"

    .section .trap_vector,"ax"
    bra.l fixture_oem_irq

    .section .irq,"ax"
fixture_oem_irq:
    .incbin "irq.dat"

    .section .psw_helpers,"ax"
    .incbin "psw_helpers.dat"

    .macro capture_handler channel
    .section .\channel\()_irq,"ax"
fixture_\channel\()_irq:
    .incbin "\channel\()_irq.dat",0,0x20
    .global fixture_\channel\()_store
fixture_\channel\()_store:
#if BOOT_CASE == 0
    .incbin "\channel\()_irq.dat",0x20,4
#else
    bra.l rbm_h03_\channel\()_capture_hook
#endif
    .global h03_sensor_after_\channel
h03_sensor_after_\channel:
    .incbin "\channel\()_irq.dat",0x24
    .endm
    capture_handler s51
    capture_handler s83

    .section .release_helper,"ax"
    .incbin "release_helper.dat"
    .section .stock_release,"ax"
    .incbin "stock_release.dat"
    .section .release_return,"ax"
    jmp r9 || nop


    .section .mock_can_start,"ax"
    ld24 r0,#0x8003e0
    ld r1,@r0
    addi r1,#7
    st r1,@r0
    ld24 r0,#0x1200
    ldi r1,#1
    stb r1,@r0
    ld24 r0,#0x804ade
    stb r1,@r0
    jmp lr

    .text
    .p2align 2
    .global fixture_publish_first_phase
fixture_publish_first_phase:
    push lr
    push r9
    ld24 r4,#0x804864
    ldi r0,#5
    stb r0,@r4
    ld24 r9,#.Lfixture_release_return
    bra.l release_site
    .p2align 2
.Lfixture_release_return:
    pop r9
    pop lr
    jmp lr

    .p2align 2
    .macro drive site
    push lr
    push r9
    ld24 r9,#.Ldrive_return\@
    bra.l \site
    .p2align 2
.Ldrive_return\@:
    pop r9
    pop lr
    jmp lr
    .endm

    .global fixture_run_foreground
fixture_run_foreground:
    drive input_site

    .macro save_irq_context buffer
    push r0
    push r1
    ld24 r0,#\buffer
    .set offset,8
    .irp reg,r2,r3,r4,r5,r6,r7,r8,r9,r10,r11,r12,r13,lr
    st \reg,@(offset,r0)
    .set offset,offset+4
    .endr
    ld r1,@sp
    st r1,@(4,r0)
    ld r1,@(4,sp)
    st r1,@r0
    add3 r1,sp,#8
    st r1,@(60,r0)
    mvfc r1,psw
    and3 r1,r1,#0xff
    st r1,@(64,r0)
    mvfaclo r1
    st r1,@(68,r0)
    mvfachi r1
    st r1,@(72,r0)
    pop r1
    pop r0
    .endm

    .global fixture_capture_irq
fixture_capture_irq:
    /* Software IRQ via TRAP #3 and the real dispatcher/RTE. Model IVECT
       with the same two-level RAM indirection the dispatcher reads. */
    ld24 r1,#0x800000
    ld24 r2,#0x1220
    sth r2,@r1
    ld24 r1,#0x1224
    st r1,@r2
    st r0,@r1
    ld24 r0,#0x0789ab
    mvtaclo r0
    mvtachi r0
#if INITIAL_MAX > 7
    ldi r0,#0x41
#else
    ldi r0,#0x40
#endif
    mvtc r0,psw
    ld24 r1,#0x165432
    ld24 r2,#0x234567
    ld24 r3,#0x376543
    ld24 r4,#0x435679
    ld24 r5,#0x543210
    ld24 r6,#0x656789
    ld24 r7,#0x765432
    save_irq_context capture_before
    .p2align 2
    trap #3 || nop
    save_irq_context capture_after
    jmp lr

    .global fixture_run_wait
fixture_run_wait:
    ld24 r0,#fixture_again
    ldi r1,#1
    stb r1,@r0
    drive wait_site

    .section .bss.fixture_again,"aw",@nobits
fixture_again:
    .space 1
    .text
    .p2align 2

    .global __wrap_rbm_h03_phase_startup_callback
__wrap_rbm_h03_phase_startup_callback:
    push lr
    bl __real_rbm_h03_phase_startup_callback
    ldi r0,#0
    mvtaclo r0
    mvtachi r0
    ldi r1,#1
#if INITIAL_MAX < 7
    cmpu r1,r0
#else
    cmpu r0,r1
#endif
    ldi r0,#-1
    ldi r1,#-2
    ldi r2,#-3
    ldi r3,#-4
    ldi r4,#-5
    ldi r5,#-6
    ldi r6,#-7
    ldi r7,#-8
    pop lr
    jmp lr

    .p2align 2
fixture_after_wait:
    push r0
    push r1
    ld24 r0,#fixture_again
    ldub r1,@r0
    bnez r1,.Lresume_fixture_wait
    ld24 r0,#boot_context
    .set offset,8
    .irp reg,r2,r3,r4,r5,r6,r7,r8,r9,r10,r11,r12,r13,lr
    st \reg,@(offset,r0)
    .set offset,offset+4
    .endr
    ld r1,@sp
    st r1,@(4,r0)
    ld r1,@(4,sp)
    st r1,@r0
    add3 r1,sp,#8
    st r1,@(60,r0)
    mvfc r1,psw
    st r1,@(64,r0)
    mvfaclo r1
    st r1,@(68,r0)
    mvfachi r1
    st r1,@(72,r0)
    pop r1
    pop r0
    bl fixture_complete
    bra fixture_done
.Lresume_fixture_wait:
    ldi r1,#0
    stb r1,@r0
    pop r1
    pop r0
    jmp r9
    .p2align 2
    .global fixture_done
fixture_done:
    bra fixture_done
"""
SECTIONS = (
    ("trap_vector", 0x4C),
    ("entry", 0x1000),
    ("reset_dispatch", 0x3DC8),
    ("irq", IRQ_START),
    ("psw_helpers", PSW_HELPERS_START),
    ("marker_check", 0x4210),
    ("recovery_stop", 0x47D8),
    ("header_marker", 0x8000),
    ("handoff", 0x8084),
    ("startup", 0x8104),
    ("first_wait", 0x8150),
    ("after_wait", 0x8160),
    ("input_return", 0x8170),
    ("mock_adc", 0x9FF4),
    ("stock_inputs", 0x40324),
    ("stock_timer", 0xA82C),
    ("s51_irq", 0xA9EC),
    ("s83_irq", 0xAA50),
    ("release_helper", 0xA06C),
    ("release_return", 0x40428),
    ("stock_release", 0x40468),
    ("mock_can_start", 0xB75C),
    ("trailer_marker", 0x7FFFE),
)


def verify_application_branches(rom, elf):
    sections = {section["name"]: section for section in elf["sections"]}
    symbols = elf["symbols"]
    sites = (
        (".first_wait", 0x8150, 0xFF, "rbm_h03_phase_wait_hook"),
        (".s51_irq", 0xAA0C, 0xFF, "rbm_h03_s51_capture_hook"),
        (".s83_irq", 0xAA70, 0xFF, "rbm_h03_s83_capture_hook"),
    )
    installed = application_placement.verify_linked(rom, elf, (BOOT_WINDOW,))
    placed = {f"{patch['address']:#08x}": f"{patch['target']:#08x}" for patch in installed}
    for section_name, site, opcode, hook in sites:
        section = sections[section_name]
        offset = site - section["address"]
        word = section["data"][offset:offset + 4]
        target = symbols[hook]["address"]
        if (offset < 0 or len(word) != 4 or word[0] != opcode or
                site + int.from_bytes(word[1:], "big", signed=True) * 4 != target or
                not CANDIDATE_START <= target < CANDIDATE_END):
            raise ValueError(f"Invalid branch to {hook} from {site:#x}")
        placed[f"{site:#08x}"] = f"{target:#08x}"
    for site, channel, _ in SENSOR_SITES:
        if symbols[f"h03_sensor_after_{channel}"]["address"] != site + 4:
            raise ValueError(f"Invalid resume from {channel} capture hook")
    placed["text_bytes"] = sections[".text"]["size"]
    return placed


def check(base, compiler, controller=None):
    identity = identify_h03(base)
    rom = base.read_bytes()
    if sha256(rom).hexdigest() != identity["sha256"]:
        raise ValueError("H03 changed while preparing the startup fixture")
    redirects = application_placement.assembly(rom)
    for address, name, stock in SENSOR_SITES:
        if rom[address:address + 4].hex() != stock:
            raise ValueError(f"Unexpected {name} capture store at {address:#x}")
    if any(byte != 0xFF for byte in rom[CANDIDATE_START:CANDIDATE_END]):
        raise ValueError("The candidate H03 application window is no longer blank")

    with TemporaryDirectory(prefix="rbm-h03-native-startup-") as directory:
        work = Path(directory)

        def run(*args, timeout=15):
            return subprocess.run(
                [str(arg) for arg in args], cwd=work, check=True, capture_output=True, timeout=timeout,
            ).stdout

        if controller is None:
            run(sys.executable, "-B", CONTROLLER / "build_target.py", "m32r",
                "--cc", compiler, "--out", work / "controller", timeout=120)
            controller = work / "controller/rbm_u340e_m32r_be.o"

        fragments = {}
        for name, start, end in FRAGMENTS:
            data = rom[start:end]
            (work / f"{name}.dat").write_bytes(data)
            fragments[name] = {"range": [f"0x{start:06X}", f"0x{end:06X}"],
                               "sha256": sha256(data).hexdigest()}
        assembly = FIXTURE + "".join(
            f'\n    .section .mock_{address:x},"ax"\n    jmp lr || nop\n' for address in STUBS
        )
        (work / "boot.S").write_text(assembly, encoding="ascii")
        (work / "application-redirects.S").write_text(redirects, encoding="ascii")
        # The stock control still uses the fixture's separate phase-release driver.
        (work / "release-redirect.S").write_text(
            application_placement.assembly(rom, application_placement.REDIRECTS[-1:]),
            encoding="ascii")
        placement = [
            (name, address, f"KEEP(*(.{name}))") for name, address in SECTIONS
        ] + [
            (window.name[1:], window.start, f"KEEP(*({window.name}))")
            for window in application_placement.REDIRECT_WINDOWS
        ] + [
            (f"mock_{address:x}", address, f"KEEP(*(.mock_{address:x}))") for address in STUBS
        ] + [
            ("text", CANDIDATE_START, "*(.text .text.*) *(.rodata .rodata.*)"),
            ("data", 0x100000, "*(.data .data.*)"),
        ]
        layout = "\n".join(
            f"  .{name} {address:#x} : {{ {inputs} }}"
            for name, address, inputs in sorted(placement, key=lambda part: part[1])
        )
        native_symbols = "".join(f"  {name} = {address:#x};\n"
                                 for name, address in application_placement.STOCK_SYMBOLS.items())
        fixed_layout = "".join(
            f'  ASSERT(SIZEOF({window.name}) == 4, "H03 redirect must occupy one word")\n'
            for window in application_placement.REDIRECT_WINDOWS)
        (work / "boot.ld").write_text(
            f"ENTRY(_start)\nSECTIONS {{\n{layout}\n"
            "  .bss : { *(.bss .bss.*) }\n"
            f"{native_symbols}{fixed_layout}"
            "  input_site = 0x816c;\n"
            "  release_site = 0x40424;\n"
            "  h03_stock_phase_clear = 0x815c;\n"
            "  h03_phase_wait_ticks = 0x8003e0;\n"
            "  h03_phase_wait_interval_ticks = 2;\n"
            f'  ASSERT(ADDR(.text) + SIZEOF(.text) <= {CANDIDATE_END:#x}, "Candidate code exceeds H03 window")\n'
            "}\n",
            encoding="ascii",
        )
        context = ", ".join(f"boot_context[{i}]" for i in range(19))
        debugger = compiler.with_name(f"m32r-elf-gdb{compiler.suffix}")
        (work / "boot.gdb").write_text(
            "set confirm off\ntarget sim --memory-size 16M\nload\ntbreak *fixture_done\nrun\n"
            f'printf "CONTEXT {"%08x " * 19}\\n", {context}\n'
            'printf "RESULT %d %x %x %x %x\\n", $r0, *(unsigned int*)0x814c, '
            '*(unsigned short*)0x80481a, *(unsigned short*)0x80481c, *(unsigned char*)0x804ade\n'
            'printf "OWNER %d %d %d %d %d %d\\n", rbm_h03_application.running, cold_inhibit, '
            'initialize_calls, inhibit_calls, phase_calls, main_calls\n'
            'printf "SENSOR %d %d\\n", capture_irqs, sensor_samples\n',
            encoding="ascii",
        )
        sources = [HERE / name for name in (
            "h03_application_hooks.S", "h03_phase_startup_hook.S", "h03_phase_wait_hook.S",
            "h03_phase_release_hook.S", "h03_phase_boot_fixture.c", "lfj8_h03_application.c",
            "lfj8_h03_phase_startup.c", "lfj8_h03_phase_clock.c", "lfj8_h03_mmio.c",
            "lfj8_h03_takeover.c", "lfj8_h03_cycle.c", "lfj8_h03_torque.c",
            "h03_sensor_hooks.S", "lfj8_h03_sensor_target.c", "lfj8_h03_sensor_feed.c",
            "lfj8_donor_io.c", "lfj8_bridge.c", "lfj8_h03_atf.c", "lfj8_h03_atf_target.c",
            "lfj8_h03_atf_tml0.c", "lfj8_h03_engine_feed.c", "lfj8_h03_engine_rx.c",
            "ta2005_chery_inputs.c", "ta2005_engine_qualifier.c",
        )] + [DIAGNOSTICS / "chery_dtc.c"]
        fixture = HERE / "h03_phase_boot_fixture.c"
        flags = (*TARGET, "-Os", "-g", "-Wall", "-Wextra", "-Werror", "-std=c99",
                 "-Wno-missing-braces", "-Wno-missing-field-initializers",
                 "-ffunction-sections", "-fdata-sections", "-I", CONTROLLER / "include",
                 "-I", CONTROLLER / "vendor" / "toyota" / "include", "-I", DIAGNOSTICS)
        # Only boot.S and the fixture depend on the per-case defines.
        common = [source for source in sources if source != fixture]
        run(compiler, *flags, "-c", *common, timeout=120)
        inputs = [source if source == fixture else source.with_suffix(".o").name for source in sources]
        cases = []
        for initial_max in (2, 11):
            stock = None
            for number, name in enumerate(CASES):
                redirect_source = "release-redirect.S" if name == "stock" else "application-redirects.S"
                run(compiler, *flags, "-nostdlib",
                    "-Wl,--gc-sections,-T,boot.ld,--wrap=rbm_h03_phase_startup_callback",
                    f"-DBOOT_CASE={number}", f"-DINITIAL_MAX={initial_max}", "boot.S", redirect_source, *inputs,
                    controller, "-lc", "-lgcc", "-o", "boot.elf", timeout=60)
                output = run(debugger, "--batch", "-nx", "-x", "boot.gdb", "boot.elf",
                             timeout=30).replace(b"\r", b"")
                if name in ("bad_header", "bad_trailer"):
                    recovery = re.search(rb"^RESULT 0 [0-9a-f]+ 0 ([0-9a-f]+) 0$", output, re.M)
                    if not recovery or int(recovery[1], 16) != initial_max:
                        raise ValueError(f"H03 marker failure did not bypass startup ({name}): "
                                         + output[-1200:].decode(errors="replace"))
                    cases.append({"path": name, "initial_oem_max": initial_max,
                                  "recovery_entry_reached": True, "startup_armed": False})
                    continue
                result = re.search(rb"^RESULT 0 ([0-9a-f]+) 7 ([0-9a-f]+) 0$", output, re.M)
                owner = re.search(rb"^OWNER ((?:[0-9]+ ){5}[0-9]+)$", output, re.M)
                snapshot = re.search(rb"^CONTEXT ((?:[0-9a-f]{8} ){19})$", output, re.M)
                sensors = re.search(rb"^SENSOR ([0-9]+) ([0-9]+)$", output, re.M)
                if not result or not owner or not snapshot or not sensors or int(result[2], 16) != max(initial_max, 7):
                    raise ValueError(f"H03 startup failed ({name}, initial max={initial_max}): "
                                     + output[-1200:].decode(errors="replace"))
                registers = tuple(int(word, 16) for word in snapshot[1].split())
                if registers[14:16] != (0x8150, 0x9FFFF0):
                    raise ValueError(f"Wrong LR or SP after the OEM first wait: {registers[14:16]}")
                if stock is None:
                    stock = registers
                if stock != registers:
                    raise ValueError(f"The startup hook changed the OEM context ({name})")
                running, cold, init, inhibit, phases, main = map(int, owner[1].split())
                branches = (None if name == "stock" else
                            verify_application_branches(rom, read_elf(work / "boot.elf", 2)))
                cases.append({"path": name, "initial_oem_max": initial_max,
                              "startup_call": result[1].decode(), "oem_elapsed_ticks": 7,
                              "oem_max_after": max(initial_max, 7), "stock_flag_cleared": True,
                              "startup_armed": name not in CLOSED_AT_START and name != "stock",
                              "application_running_at_end": bool(running) if cold else None,
                              "cold_inhibit": cold, "initializer_calls": init, "inhibit_calls": inhibit,
                              "phase_calls": phases, "main_calls": main,
                              "capture_irqs_with_matching_context": int(sensors[1]),
                              "verified_first_sensor_snapshots": int(sensors[2]),
                              "fixture_placement": branches,
                              "oem_context_matches_stock": True})

    return {"base": identity, "fragments": fragments, "cases": cases,
            "reset_dispatch": "0x003DC8", "handoff": "0x008084", "recovery_entry": "0x0047D8",
            "hook_site": "0x00814C", "stock_continuation": "0x008150",
            "stubbed_oem_entries": [f"0x{address:06X}" for address in (*STUBS, 0xB75C)],
            "cold_gate_site": "0x008100", "foreground_call": "0x00816C",
            "capture_sites": [f"0x{address:06X}" for address, _, _ in SENSOR_SITES],
            "candidate_code_window": [f"{addr:#08x}" for addr in (CANDIDATE_START, CANDIDATE_END)],
            "capture_irq": "TRAP #3 -> OEM dispatcher -> S51/S83 -> OEM RTE, RAM-backed MMIO",
            "capture_irq_context": "R0-R15, active PSW, observable ACC and separate OEM PSW stack cursor",
            "first_project_event": "OEM phase release -> bounded wait -> stock inputs -> application owner",
            "toyota_source": "Independent simulated release, every other H03 publication in the steady case",
            "clock": "Simulated TML0CT, wraps across the reset-time OEM sample",
            "limits": "No real RAM placement, IRQ schedule, inhibit driver or input/task calibration",
            "callback_clobbers_for_test": ["R0-R7", "C", "ACC"],
            "context_checked": "R0-R15, CR0 and observable ACC at 0x008160",
            "hardware_executed": False, "flashable_image": None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--gcc", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--controller", type=Path, help="Reuse a built M32R controller object")
    args = parser.parse_args()
    if args.out.suffix.lower() != ".json" or args.out.resolve() == args.base.resolve():
        parser.error("--out must be a separate JSON report")
    try:
        result = check(args.base, args.gcc.resolve(), args.controller.resolve() if args.controller else None)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    except subprocess.CalledProcessError as error:
        parser.exit(1, (error.stderr or str(error).encode()).decode(errors="replace") + "\n")
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
