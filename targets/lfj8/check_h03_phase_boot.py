"""Run the H03 application entry and candidate phase startup hook in M32R."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory

from check_h03_link import TARGET, identify_h03


HERE = Path(__file__).resolve().parent
CONTROLLER = HERE.parent.parent / "controller"
FRAGMENTS = (
    ("reset_dispatch", 0x003DC8, 0x003DE0),
    ("marker_check", 0x004210, 0x00423C),
    ("header_marker", 0x008000, 0x008002),
    ("trailer_marker", 0x07FFFE, 0x080000),
    ("handoff", 0x008084, 0x008088),
    ("startup", 0x008100, 0x00814C),
    ("startup_call", 0x00814C, 0x008150),
    ("first_wait", 0x008150, 0x008160),
    ("stock_timer", 0x00A82C, 0x00A868),
    ("release_helper", 0x00A06C, 0x00A0B0),
    ("stock_release", 0x040468, 0x0404C4),
)
# Other initialization routines are not exercised by this fixture. The CAN
# initialization stub is special: it advances TML0CT and leaves a stock flag.
STUBS = (0x00B704, 0x0404C4, 0x04054C, 0x04050C, 0x0089EC,
         0x034000, 0x046774, 0x008FFC, 0x004784, 0x034004)
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
    seth r1,#0x1234
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
    .section .startup,"ax"
    .incbin "startup.dat"
    .section .startup_call,"ax"
#if BOOT_CASE == 0
    .incbin "startup_call.dat"
#else
    bl.l rbm_h03_phase_startup_hook
#endif
    .section .first_wait,"ax"
    .incbin "first_wait.dat"
    .section .after_wait,"ax"
    bra.l fixture_after_wait

    .section .stock_timer,"ax"
    .incbin "stock_timer.dat"

    .section .release_helper,"ax"
    .incbin "release_helper.dat"
    .section .stock_release,"ax"
    .incbin "stock_release.dat"
    .section .release_site,"ax"
release_site:
    bl.l rbm_h03_phase_release_hook
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
    .global rbm_h03_phase_startup_callback
rbm_h03_phase_startup_callback:
    push lr
    bl fixture_start_native_phase
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
    .p2align 2
    .global fixture_done
fixture_done:
    bra fixture_done
"""
SECTIONS = (
    ("entry", 0x1000),
    ("reset_dispatch", 0x3DC8),
    ("marker_check", 0x4210),
    ("recovery_stop", 0x47D8),
    ("header_marker", 0x8000),
    ("handoff", 0x8084),
    ("startup", 0x8100),
    ("startup_call", 0x814C),
    ("first_wait", 0x8150),
    ("after_wait", 0x8160),
    ("stock_timer", 0xA82C),
    ("release_helper", 0xA06C),
    ("release_site", 0x40424),
    ("stock_release", 0x40468),
    ("mock_can_start", 0xB75C),
    ("trailer_marker", 0x7FFFE),
)


def check(base, compiler):
    identity = identify_h03(base)
    rom = base.read_bytes()
    if sha256(rom).hexdigest() != identity["sha256"]:
        raise ValueError("H03 changed while preparing the startup fixture")
    if rom[0x814C:0x8150] != bytes.fromhex("FE0009BB"):
        raise ValueError("The final H03 startup call is not the expected stock A838 call")
    if rom[0x40424:0x40428] != bytes.fromhex("7E11F000"):
        raise ValueError("The H03 phase publication call differs from stock")


    with TemporaryDirectory(prefix="rbm-h03-native-startup-") as directory:
        work = Path(directory)

        def run(*args):
            return subprocess.run(
                [str(arg) for arg in args], cwd=work, check=True, capture_output=True, timeout=15,
            ).stdout

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
        placement = [
            (name, address, f"KEEP(*(.{name}))") for name, address in SECTIONS
        ] + [
            (f"mock_{address:x}", address, f"KEEP(*(.mock_{address:x}))") for address in STUBS
        ] + [
            ("text", 0x60000, "*(.text .text.*) *(.rodata .rodata.*)"),
            ("data", 0x100000, "*(.data .data.*)"),
        ]
        layout = "\n".join(
            f"  .{name} {address:#x} : {{ {inputs} }}"
            for name, address, inputs in sorted(placement, key=lambda part: part[1])
        )
        (work / "boot.ld").write_text(
            f"ENTRY(_start)\nSECTIONS {{\n{layout}\n"
            "  .bss : { *(.bss .bss.*) }\n  h03_stock_startup_record = 0xa838;\n"
            "  h03_stock_phase_release = 0x40468;\n"
            '  ASSERT(SIZEOF(.startup_call) == 4, "Startup hook must fit one word")\n}\n',
            encoding="ascii",
        )
        context = ", ".join(f"boot_context[{i}]" for i in range(19))
        debugger = compiler.with_name(f"m32r-elf-gdb{compiler.suffix}")
        (work / "boot.gdb").write_text(
            "set confirm off\ntarget sim --memory-size 16M\nload\ntbreak *fixture_done\nrun\n"
            f'printf "CONTEXT {"%08x " * 19}\\n", {context}\n'
            'printf "RESULT %d %x %x %x %x\\n", $r0, *(unsigned int*)0x814c, '
            '*(unsigned short*)0x80481a, *(unsigned short*)0x80481c, *(unsigned char*)0x804ade\n',
            encoding="ascii",
        )
        sources = [HERE / name for name in (
            "h03_phase_startup_hook.S", "h03_phase_release_hook.S", "h03_phase_boot_fixture.c", "lfj8_h03_phase_startup.c",
            "lfj8_h03_phase_clock.c", "lfj8_h03_mmio.c", "lfj8_h03_takeover.c",
        )]
        cases = []
        for initial_max in (2, 11):
            stock = None
            for number, name in enumerate(("stock", "owned", "invalid_period", "unowned",
                                           "bad_header", "bad_trailer")):
                run(compiler, *TARGET, "-Os", "-g", "-Wall", "-Wextra", "-Werror", "-std=c99",
                    "-ffunction-sections", "-fdata-sections", "-nostdlib", "-Wl,--gc-sections,-T,boot.ld",
                    "-I", CONTROLLER / "include", "-I", CONTROLLER / "vendor" / "toyota" / "include",
                    f"-DBOOT_CASE={number}", f"-DINITIAL_MAX={initial_max}", "boot.S", *sources,
                    "-lc", "-lgcc", "-o", "boot.elf")
                output = run(debugger, "--batch", "-nx", "-x", "boot.gdb", "boot.elf").replace(b"\r", b"")
                if name in ("bad_header", "bad_trailer"):
                    recovery = re.search(rb"^RESULT 0 [0-9a-f]+ 0 ([0-9a-f]+) 0$", output, re.M)
                    if not recovery or int(recovery[1], 16) != initial_max:
                        raise ValueError(f"H03 marker failure did not bypass startup ({name}): "
                                         + output[-1200:].decode(errors="replace"))
                    cases.append({"path": name, "initial_oem_max": initial_max,
                                  "recovery_entry_reached": True, "startup_armed": False})
                    continue
                result = re.search(rb"^RESULT 0 ([0-9a-f]+) 7 ([0-9a-f]+) ([01])$", output, re.M)
                snapshot = re.search(rb"^CONTEXT ((?:[0-9a-f]{8} ){19})$", output, re.M)
                if (not result or not snapshot or int(result[2], 16) != max(initial_max, 7)
                        or int(result[3]) != (name == "owned")):
                    raise ValueError(f"H03 startup failed ({name}, initial max={initial_max}): "
                                     + output[-1200:].decode(errors="replace"))
                registers = tuple(int(word, 16) for word in snapshot[1].split())
                if registers[14:16] != (0x8150, 0x9FFFF0):
                    raise ValueError(f"Wrong LR or SP after the OEM first wait: {registers[14:16]}")
                if stock is None:
                    stock = registers
                if stock != registers:
                    raise ValueError(f"The startup hook changed the OEM context ({name})")
                cases.append({"path": name, "initial_oem_max": initial_max,
                              "startup_call": result[1].decode(), "oem_elapsed_ticks": 7,
                              "oem_max_after": max(initial_max, 7), "stock_flag_cleared": True,
                              "startup_armed": name == "owned", "first_project_event": name == "owned",
                              "oem_flag_at_end": int(result[3]), "oem_context_matches_stock": True})

    return {"base": identity, "fragments": fragments, "cases": cases,
            "reset_dispatch": "0x003DC8", "handoff": "0x008084", "recovery_entry": "0x0047D8",
            "hook_site": "0x00814C", "stock_continuation": "0x008150",
            "stubbed_oem_entries": [f"0x{address:06X}" for address in (*STUBS, 0xB75C)],
            "first_project_event": "OEM phase release and timestamp hook after the first stock wait",
            "callback_clobbers_for_test": ["R0-R7", "C", "ACC"],
            "context_checked": "R0-R15, CR0 and observable ACC at 0x008160",
            "hardware_executed": False, "flashable_image": None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--gcc", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if args.out.suffix.lower() != ".json" or args.out.resolve() == args.base.resolve():
        parser.error("--out must be a separate JSON report")
    try:
        result = check(args.base, args.gcc.resolve())
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    except subprocess.CalledProcessError as error:
        parser.exit(1, (error.stderr or str(error).encode()).decode(errors="replace") + "\n")
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
