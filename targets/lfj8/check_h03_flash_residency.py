"""Check whether exact H03 phase gates exclude an existing virtual Flash overlay."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory

from check_h03_flash_policy import LAYOUT, FCNT1, FESBANK1
from check_h03_link import identify_h03


FIXTURE = """
    .section .fixture,"ax",@progbits
    .global _start
    .global fixture_ready
    .global fixture_session_close
_start:
    ld24 sp,#0x9ffffc
fixture_ready:
    ld24 r0,#fixture_arguments
    ld r0,@r0
    jmp r0

    .p2align 2
fixture_session_close:
    ld24 r10,#0x808578
    ld24 lr,#fixture_after_close
    /* Match the stack of the dispatcher whose close branch is tested. */
    push lr
    push r10
    push r9
    push r8
    bra oem_session_close
    .p2align 2
fixture_after_close:
    ld24 r0,#fixture_arguments
    ld r0,@(4,r0)
    jmp r0

    .section .fixture_data,"aw",@progbits
    .global fixture_arguments
    .p2align 2
fixture_arguments:
    .space 8

    .section .oem,"ax",@progbits
    .incbin "original.dat"
"""

SESSION_FLAGS = 0x808580
SCHEDULER_MODE = 0x804887
PROGRAMMING_MODE = 0x80801C
STRATEGY_GATE, STRATEGY_CALL = 0x0081D4, 0x0081E0
COMMIT_GATE, COMMIT_CALL = 0x0081E8, 0x0081F4
PHASE_SKIP = 0x00821C


def observe(run, work, gdb, entry, phase, stops, mode, in_service):
    commands = ["set confirm off", "target sim --memory-size 16M", "load",
                "tbreak *fixture_ready", "run",
                f"set {{unsigned int}}&fixture_arguments = {entry}",
                f"set {{unsigned int}}((char*)&fixture_arguments+4) = {phase:#x}",
                f"set {{unsigned char}}{SESSION_FLAGS:#x} = {0x20 if in_service else 0}",
                f"set {{unsigned char}}{SCHEDULER_MODE:#x} = {mode}",
                f"set {{unsigned char}}{PROGRAMMING_MODE:#x} = 0",
                f"set {{unsigned char}}{FCNT1:#x} = 1",
                f"set {{unsigned short}}{FESBANK1:#x} = 0x8020"]
    commands.extend(f"tbreak *{address:#x}" for address in stops)
    commands.extend(("continue", 'printf "H03_RESIDENCY %x %x %x %x %x\\n", $pc, '
                     f"*(unsigned char*){SESSION_FLAGS:#x}, *(unsigned char*){PROGRAMMING_MODE:#x}, "
                     f"*(unsigned char*){FCNT1:#x}, *(unsigned short*){FESBANK1:#x}"))
    (work / "probe.gdb").write_text("\n".join(commands) + "\n", encoding="ascii")
    output = run(gdb, "--batch", "-nx", "-x", "probe.gdb", "fixture.elf")
    match = re.search(rb"H03_RESIDENCY ((?:[0-9a-f]+ ){4}[0-9a-f]+)", output)
    if match is None:
        raise ValueError(f"Missing residency observation: {output[-1000:].decode(errors='replace')}")
    return tuple(int(value, 16) for value in match[1].split())


def check(base, compiler):
    identity = identify_h03(base)
    rom = base.read_bytes()
    if sha256(rom).hexdigest() != identity["sha256"] or rom[0x000201] != 1:
        raise ValueError("The H03 source or service configuration differs")

    results = []
    with TemporaryDirectory(prefix="rbm-h03-flash-residency-") as directory:
        work = Path(directory)

        def run(*args):
            return subprocess.run([str(arg) for arg in args], cwd=work, check=True,
                                  capture_output=True, timeout=30).stdout

        if run(compiler, "-dumpmachine").strip() != b"m32r-elf":
            raise ValueError("A bare-metal M32R compiler is required")
        gdb = compiler.with_name(f"m32r-elf-gdb{compiler.suffix}")
        (work / "original.dat").write_bytes(rom)
        (work / "fixture.S").write_text(FIXTURE, encoding="ascii")
        (work / "fixture.ld").write_text(LAYOUT + "oem_session_close = 0x002e80;\n", encoding="ascii")
        run(compiler, "-m32r", "-Wa,-EB", "-nostdlib", "-Wl,-T,fixture.ld", "fixture.S", "-o", "fixture.elf")

        for name, gate, call in (("strategy", STRATEGY_GATE, STRATEGY_CALL), ("commit", COMMIT_GATE, COMMIT_CALL)):
            for path, entry, from_service, expected_flags in (
                ("active", hex(gate), True, 0x20),
                ("closed", "&fixture_session_close", True, 0x10),
                ("idle", hex(gate), False, 0),
            ):
                for mode in (0, 4):
                    observed = observe(run, work, gdb, entry, gate, (call, PHASE_SKIP), mode, from_service)
                    expected = (call if mode == 0 else PHASE_SKIP, expected_flags, 0, 1, 0x8020)
                    if observed != expected:
                        raise ValueError(f"Unexpected H03 phase state for {name}, {path}, mode={mode}: {observed}")
                    results.append({"phase": name, "session": path, "mode": mode,
                                    "stop": f"0x{observed[0]:06X}", "session_flags": observed[1],
                                    "femmod": 1, "fesbank1": "0x8020"})

        warm = observe(run, work, gdb, "0x003e40", 0, (0x000AE0,), 0, True)
        if warm != (0x000AE0, 0, 0, 1, 0x8020):
            raise ValueError(f"Unexpected original software restart state: {warm}")

    return {"base": identity, "cases": results,
            "software_restart_stop": "0x000AE0", "software_restart_keeps_overlay_shadow": True,
            "flash_alias_peripheral_modelled": False, "device_accessed": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--gcc", required=True, type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(check(args.base, args.gcc.resolve()), indent=2))
    except subprocess.CalledProcessError as error:
        parser.exit(1, (error.stderr or error.stdout or str(error).encode()).decode(errors="replace") + "\n")
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
