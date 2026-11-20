"""Measure H03 service admission and update bounds in a read-only CPU fixture."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory

from check_h03_flash_policy import LAYOUT
from check_h03_link import identify_h03


MONITOR_GATE, MONITOR_DISPATCH = 0x0034A0, 0x0034B4
ADDRESS_CHECK = 0x003528
INSTALL_BEGIN, INSTALL_ACCEPT, INSTALL_DENY = 0x004F54, 0x004F84, 0x004F7C
SERVICE_CONFIG = 0x000201
RAM_START, RAM_LIMIT = 0x806B40, 0x807000

FIXTURE = """
    .section .fixture,"ax",@progbits
    .global _start
    .global fixture_ready
    .global fixture_return
_start:
    ld24 sp,#0x9ffffc
fixture_ready:
    ld24 lr,#fixture_return
    ld24 r4,#fixture_arguments
    ld r3,@r4
    ld r0,@(4,r4)
    ld r1,@(8,r4)
    ld r5,@(12,r4)
    jmp r3
    .p2align 2
fixture_return:
    bra fixture_return

    .section .fixture_data,"aw",@progbits
    .p2align 2
    .global fixture_arguments
fixture_arguments:
    .space 16

    .section .oem,"ax",@progbits
    .incbin "h03.dat"
"""


def observe(run, work, gdb, entry, args, stops, config):
    commands = ["set confirm off", "target sim --memory-size 16M", "load",
                "tbreak *fixture_ready", "run"]
    commands.extend(f"set {{unsigned int}}((char*)&fixture_arguments+{index * 4}) = {value:#x}"
                    for index, value in enumerate((entry, *args)))
    if config != 1:
        commands.append(f"set {{unsigned char}}{SERVICE_CONFIG:#x} = {config}")
    commands.extend(("set {unsigned char}0x8007e2 = 1", "set {unsigned short}0x8007f2 = 0x8020"))
    commands.extend(f"tbreak *{stop}" for stop in stops)
    commands.extend(("continue", 'printf "H03_ISOLATION %x %x %x %x\\n", $pc, $r0, '
                     "*(unsigned char*)0x8007e2, *(unsigned short*)0x8007f2"))
    (work / "probe.gdb").write_text("\n".join(commands) + "\n", encoding="ascii")
    output = run(gdb, "--batch", "-nx", "-x", "probe.gdb", "fixture.elf")
    match = re.search(rb"H03_ISOLATION ((?:[0-9a-f]+ ){3}[0-9a-f]+)", output)
    if match is None:
        raise ValueError(f"Missing original H03 policy result: {output[-1000:].decode(errors='replace')}")
    pc, r0, fcnt1, bank = (int(value, 16) for value in match[1].split())
    if (fcnt1, bank) != (1, 0x8020):
        raise ValueError("The tested gate unexpectedly changed the virtual Flash configuration")
    return pc, r0


def check(base, compiler):
    identity = identify_h03(base)
    rom = base.read_bytes()
    if sha256(rom).hexdigest() != identity["sha256"] or rom[SERVICE_CONFIG] != 1:
        raise ValueError("The H03 service configuration or source differs")

    admission = []
    install = []
    memory_bounds = []
    with TemporaryDirectory(prefix="rbm-h03-service-isolation-") as directory:
        work = Path(directory)

        def run(*args):
            return subprocess.run([str(arg) for arg in args], cwd=work, check=True,
                                  capture_output=True, timeout=30).stdout

        if run(compiler, "-dumpmachine").strip() != b"m32r-elf":
            raise ValueError("A bare-metal M32R compiler is required")
        gdb = compiler.with_name(f"m32r-elf-gdb{compiler.suffix}")
        (work / "h03.dat").write_bytes(rom)
        (work / "fixture.S").write_text(FIXTURE, encoding="ascii")
        (work / "fixture.ld").write_text(LAYOUT, encoding="ascii")
        run(compiler, "-m32r", "-Wa,-EB", "-nostdlib", "-Wl,-T,fixture.ld", "fixture.S", "-o", "fixture.elf")
        for config in (1, 0):
            pc, value = observe(run, work, gdb, MONITOR_GATE, (0, 0, 0),
                                (hex(MONITOR_DISPATCH), "fixture_return"), config)
            if config and (pc, value) != (MONITOR_DISPATCH, 0x808DFC):
                raise ValueError("The unmodified H03 monitor gate did not dispatch")
            if not config and (pc < 0x100000 or value != 0):
                raise ValueError("The zero-config monitor gate did not return as expected")
            admission.append({"config": config, "dispatch_reached": pc == MONITOR_DISPATCH,
                              "already_enabled_virtual_flash_preserved": True})

            for address, allowed in ((SERVICE_CONFIG, False), (0x003550, False), (0x007FFF, False),
                                     (0x008000, True), (0x020000, True)):
                pc, _ = observe(run, work, gdb, INSTALL_BEGIN, (1, 0, address),
                                (hex(INSTALL_ACCEPT), hex(INSTALL_DENY)), config)
                if pc != (INSTALL_ACCEPT if allowed else INSTALL_DENY):
                    raise ValueError(f"Unexpected update boundary for {address:#x}")
                install.append({"config": config, "start": f"0x{address:06X}", "accepted": allowed})

        for start, allowed in ((RAM_START, True), (RAM_LIMIT - 1, True), (0x808578, False), (0x808DB3, False)):
            pc, result = observe(run, work, gdb, ADDRESS_CHECK, (start, 1, 0), ("fixture_return",), 1)
            if pc < 0x100000 or result != int(allowed):
                raise ValueError(f"Unexpected monitor's address decision for {start:#x}")
            memory_bounds.append({"address": f"0x{start:06X}", "accepted": allowed})

    return {"base": identity, "monitor_config_cases": admission, "update_boundary_cases": install,
            "monitor_address_cases": memory_bounds, "transport_executed": False,
            "flash_or_ram_write_routine_executed": False, "hardware_executed": False}


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
