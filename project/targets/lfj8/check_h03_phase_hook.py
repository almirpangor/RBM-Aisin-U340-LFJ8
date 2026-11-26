"""Compare a timestamp tap at the H03 phase-release call with original code."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory

from check_h03_link import identify_h03


HERE = Path(__file__).resolve().parent
FILES = (
    "h03_phase_hook_fixture.S", "h03_phase_hook_fixture.c", "h03_phase_release_hook.S",
    "lfj8_h03_phase_clock.c", "lfj8_h03_phase_clock.h",
)
SITE = 0x040424
RETURN = SITE + 4
SNAPSHOT_WORDS = 23
LAYOUT = """
ENTRY(_start)
SECTIONS {
  .oem_prefix 0x000000 : { *(.oem_prefix) }
  .hook 0x020000 : { *(.text.rbm_h03_phase_release_hook) }
  .oem_suffix 0x030000 : { *(.oem_suffix) }
  .fixture 0x100000 : { *(.fixture) *(.text*) *(.rodata*) }
  .bss (NOLOAD) : { *(.bss*) *(COMMON) }
  /DISCARD/ : { *(.note*) *(.comment) }
  h03_stock_phase_release = 0x040468;
}
ASSERT(SIZEOF(.hook) <= 0x10000, "Phase hook exceeds ROM window")
"""


def simulate(run, directory, compiler, wrapped):
    variant = f"-DPHASE_HOOK_ENABLED={int(wrapped)}"
    run(compiler, "-m32r", "-Wa,-EB", "-mmodel=medium", "-msdata=none", "-Os",
        "-g", "-Wall", "-Wextra", "-Werror", "-ffreestanding", "-fno-builtin", "-fno-common",
        "-nostdlib", "-Wl,-T,fixture.ld", variant, *[item for item in FILES if not item.endswith(".h")],
        "-Wl,--start-group", "-lc", "-lgcc", "-Wl,--end-group", "-o", "fixture.elf")
    debugger = compiler.with_name(f"m32r-elf-gdb{compiler.suffix}")
    commands = ["set confirm off", "target sim --memory-size 16M", "load",
                "tbreak *phase_fixture_done", "run", 'printf "RESULT %x\\n", $r0']
    for event in range(7):
        arguments = ", ".join(f"phase_snapshots[{event}][{reg}]" for reg in range(SNAPSHOT_WORDS))
        commands.append(f'printf "CONTEXT {"%08x " * SNAPSHOT_WORDS}\\n", {arguments}')
    commands.append(f'printf "PATCH %08x\\n", *(unsigned int*){SITE:#x}')
    (directory / "probe.gdb").write_text("\n".join(commands) + "\n", encoding="ascii")
    output = run(debugger, "--batch", "-nx", "-x", "probe.gdb", "fixture.elf").replace(b"\r", b"")
    pattern = rb"^CONTEXT ((?:[0-9a-f]{8} ){%d})$" % SNAPSHOT_WORDS
    records = re.findall(pattern, output, re.M)
    patch = re.search(rb"^PATCH ([0-9a-f]{8})$", output, re.M)
    if len(records) != 7 or patch is None or b"RESULT 0\n" not in output:
        raise ValueError(f"Phase integration failed (wrapped={wrapped}): {output[-2400:].decode(errors='replace')}")
    return [tuple(int(value, 16) for value in row.split()) for row in records], bytes.fromhex(patch[1].decode())


def check(base, compiler):
    identity = identify_h03(base)
    rom = base.read_bytes()
    if sha256(rom).hexdigest() != identity["sha256"] or rom[SITE:RETURN] != bytes.fromhex("7E11F000"):
        raise ValueError("The verified H03 or its OEM release call differs")
    with TemporaryDirectory(prefix="rbm-h03-phase-hook-") as temp:
        directory = Path(temp)
        (directory / "h03.dat").write_bytes(rom)
        (directory / "fixture.ld").write_text(LAYOUT, encoding="ascii")
        for name in FILES:
            shutil.copyfile(HERE / name, directory / name)

        def run(*args):
            return subprocess.run([str(arg) for arg in args], cwd=directory, check=True,
                                  capture_output=True, timeout=30).stdout

        stock, stock_call = simulate(run, directory, compiler, False)
        wrapped, new_call = simulate(run, directory, compiler, True)
    for index, (before, after) in enumerate(zip(stock, wrapped, strict=True)):
        if before != after or before[14] != RETURN:
            differences = [(i, f"{x:08x}", f"{y:08x}") for i, (x, y) in
                           enumerate(zip(before, after, strict=True)) if x != y]
            raise ValueError(f"OEM continuation differs at event {index}: {differences}")
        expected_p6 = (0xC2, 0xC2, 0x82, 0x82, 0xC2, 0xC2, 0x82)[index]
        if before[19:] != (1, 10, 6 - index, expected_p6):
            raise ValueError(f"Unexpected stock divider or P6 state at event {index}: {before[19:]}")
    if stock_call != rom[SITE:RETURN] or new_call[0] != 0xFE or (
            SITE + 4 * int.from_bytes(new_call[1:], "big", signed=True) != 0x020000):
        raise ValueError("The linked call did not reach the verified phase-hook window")
    return {
        "base": identity, "release_call": f"{SITE:#08x}", "stock_instruction": stock_call.hex(),
        "simulator_instruction": new_call.hex(), "hook_address_in_simulator": "0x020000",
        "stock_return": f"{RETURN:#08x}", "matched_cpu_snapshots": len(stock),
        "matched": ["R0-R15", "PSW", "ACC reads", "ready flag", "two counters", "P6 latch"],
        "observed_psw": sorted({row[16] for row in stock}),
        "observed_acc_reads": sorted({row[17:19] for row in stock}),
        "nonzero_acc_high_qualified": False,
        "cases": ["ordered releases across TML0 wrap", "two releases before one stock consume",
                  "fault persists until reset", "missing release after an accepted event"],
        "simulator_intercepts_continuations": True,
        "hardware_executed": False, "stack_and_irq_latency_qualified": False, "flashable_image": None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("base", "gcc", "out"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    args = parser.parse_args()
    if args.out.suffix.lower() != ".json" or args.out.resolve() == args.base.resolve():
        parser.error("--out must be a separate JSON report")
    try:
        report = json.dumps(check(args.base, args.gcc.resolve()), indent=2) + "\n"
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report, encoding="utf-8")
        print(report, end="")
    except subprocess.CalledProcessError as error:
        details = error.stderr or error.stdout or str(error).encode()
        parser.exit(1, details.decode(errors="replace") + "\n")
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
