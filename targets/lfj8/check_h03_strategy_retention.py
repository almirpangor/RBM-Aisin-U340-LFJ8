"""Exercise the H03 hysteresis prefix and its original caller in M32R simulation."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import struct
import subprocess
from tempfile import TemporaryDirectory

from check_h03_link import identify_h03


OEM_STRATEGY, HYSTERESIS, PROPOSAL_SUFFIX = 0x06FED4, 0x071124, 0x071204
EPILOGUE, END = 0x0714C8, 0x0714D0
RAM_START, RAM_END = 0x804000, 0x80A000
FLAG1, FLAG2 = 0x80658A, 0x8065F9
PROPOSALS = (0x8063D5, 0x8063D8, 0x804F6C, 0x804F78, 0x804F84)

FIXTURE = """
    .section .fixture,"ax",@progbits
    .global _start
    .global fixture_ready
    .global fixture_stop
_start:
    ld24 sp,#0x9ffffc
    ldi r8,#0x48
    ldi r9,#0x49
fixture_ready:
    ld24 lr,#fixture_stop
    ld24 r0,#fixture_entry
    ld r0,@r0
    jmp r0
    .p2align 2
fixture_stop:
    bra fixture_stop

    .section .fixture_data,"aw",@progbits
    .global fixture_entry
fixture_entry:
    .long 0

    .section .oem,"ax",@progbits
    .incbin "oem.dat"
"""
LAYOUT = """
ENTRY(_start)
SECTIONS {
  .oem 0x0 : { *(.oem) }
  .fixture 0x100000 : { *(.fixture) }
  .fixture_data : { *(.fixture_data) }
  /DISCARD/ : { *(.note*) *(.comment) }
}
"""


def float_bits(value):
    return int.from_bytes(struct.pack(">f", value), "big")


def observe(run, work, gdb, entry, stops, memory):
    commands = ["set confirm off", "target sim --memory-size 16M", "load", "tbreak *fixture_ready", "run",
                f"set {{unsigned int}}&fixture_entry = {entry:#x}"]
    commands.extend(f"set {{{kind}}}{address:#x} = {value:#x}" for kind, address, value in memory)
    commands.append(f"dump binary memory before.dat {RAM_START:#x} {RAM_END:#x}")
    commands.extend(f"tbreak *{stop}" for stop in stops)
    commands.extend(("continue", 'printf "H03_STRATEGY %x %x %x %x\\n", $pc, $sp, $r8, $r9',
                     f"dump binary memory after.dat {RAM_START:#x} {RAM_END:#x}"))
    (work / "probe.gdb").write_text("\n".join(commands) + "\n", encoding="ascii")
    result = run(gdb, "--batch", "-nx", "-x", "probe.gdb", "fixture.elf")
    match = re.search(rb"H03_STRATEGY ((?:[0-9a-f]+ ){3}[0-9a-f]+)", result)
    if match is None:
        raise ValueError(f"Missing strategy observation: {result[-1000:].decode(errors='replace')}")
    return (tuple(int(word, 16) for word in match[1].split()),
            (work / "before.dat").read_bytes(), (work / "after.dat").read_bytes())


def check(base, compiler):
    identity = identify_h03(base)
    original = base.read_bytes()
    if sha256(original).hexdigest() != identity["sha256"]:
        raise ValueError("H03 changed while the fixture was being prepared")
    if original[EPILOGUE:END] != bytes.fromhex("28ef29ef2eef1fce") or original[0x01716C] != 0:
        raise ValueError("The H03 profile or original restoring return instructions differ")

    # In this fixture alone, deliberately end the saved prefix before the proposal writes.
    prefix = original[:PROPOSAL_SUFFIX] + original[EPILOGUE:END] + original[PROPOSAL_SUFFIX + 8:]
    thresholds = (
        ("clear_below_both", 2.0, 18.75, (1, 1), (0, 0)),
        ("fixed_lower_boundary_holds", 3.0, 18.75, (1, 0), (1, 0)),
        ("fixed_upper_boundary_sets", 5.0, 18.75, (0, 1), (1, 0)),
        ("fixed_deadband_holds_clear", 4.0, 18.75, (0, 0), (0, 0)),
        ("map_upper_boundary_sets", 43.0, 18.75, (1, 0), (1, 1)),
        ("map_lower_boundary_holds", 41.0, 18.75, (1, 1), (1, 1)),
        ("map_below_lower_clears", 40.0, 18.75, (1, 1), (1, 0)),
        ("map_interpolated_boundary_sets", 41.5, 13.875, (1, 0), (1, 1)),
    )
    gates = ((299.0, 0, 0, 0x07015C), (300.0, 0, 0, HYSTERESIS),
             (300.0, 1, 0, 0x07015C), (300.0, 0, 1, 0x070E00))
    report = []
    with TemporaryDirectory(prefix="rbm-h03-strategy-retention-") as directory:
        work = Path(directory)

        def run(*args):
            return subprocess.run([str(arg) for arg in args], cwd=work, check=True,
                                  capture_output=True, timeout=30).stdout

        if run(compiler, "-dumpmachine").strip() != b"m32r-elf":
            raise ValueError("A bare-metal M32R compiler is required")
        gdb = compiler.with_name(f"m32r-elf-gdb{compiler.suffix}")
        (work / "fixture.S").write_text(FIXTURE, encoding="ascii")
        (work / "fixture.ld").write_text(LAYOUT, encoding="ascii")
        for name, image in (("stock", original), ("prefix", prefix)):
            (work / "oem.dat").write_bytes(image)
            run(compiler, "-m32r", "-Wa,-EB", "-nostdlib", "-Wl,-T,fixture.ld", "fixture.S", "-o", "fixture.elf")

            if name == "stock":
                for inlet, blocked, selector, expected in gates:
                    memory = (("unsigned int", 0x804FBC, float_bits(inlet)),
                              ("unsigned char", 0x806379, blocked), ("unsigned short", 0x806234, selector))
                    (pc, *_), _, _ = observe(run, work, gdb, OEM_STRATEGY,
                                             tuple(hex(address) for address in (0x07015C, HYSTERESIS, 0x070E00)), memory)
                    if pc != expected:
                        raise ValueError(f"Unexpected original strategy branch to {pc:#x}, expected {expected:#x}")

            for scenario, speed, axis, prior, expected in thresholds:
                memory = (("unsigned int", 0x8050A0, float_bits(speed)),
                          ("unsigned int", 0x80502C, float_bits(axis)),
                          ("unsigned short", 0x80621C, 1),
                          ("unsigned char", FLAG1, prior[0]), ("unsigned char", FLAG2, prior[1]),
                          *(("unsigned char", address, 0xA5) for address in PROPOSALS[:2]),
                          *(("unsigned int", address, 0x3F800000) for address in PROPOSALS[2:]))
                (pc, sp, r8, r9), before, after = observe(run, work, gdb, HYSTERESIS, ("fixture_stop",), memory)
                if pc < 0x100000 or (sp, r8, r9) != (0x9FFFFC, 0x48, 0x49):
                    raise ValueError(f"Incorrect return from {name} routine in {scenario}")
                observed = (after[FLAG1 - RAM_START], after[FLAG2 - RAM_START])
                if observed != expected or len(before) != RAM_END - RAM_START or len(before) != len(after):
                    raise ValueError(f"Unexpected flags or RAM capture for {name} in {scenario}: {observed}")
                changed = {address for address, (old, new) in enumerate(zip(before, after), RAM_START) if old != new}
                flags = {FLAG1, FLAG2}
                if name == "prefix" and changed - flags:
                    raise ValueError(f"Prefix wrote beyond the hysteresis flags in {scenario}")
                if name == "stock" and not changed.intersection(PROPOSALS):
                    raise ValueError(f"The expected OEM proposal writes were missing in {scenario}")
                report.append({"variant": name, "scenario": scenario, "flags": list(observed),
                               "changed_ram_bytes": sorted(f"0x{address:06X}" for address in changed)})

    return {
        "base": identity,
        "original_entry": f"0x{HYSTERESIS:06X}",
        "prefix_end_exclusive": f"0x{PROPOSAL_SUFFIX:06X}",
        "simulator_only_return_relocation": [f"0x{EPILOGUE:06X}", f"0x{PROPOSAL_SUFFIX:06X}"],
        "original_gate_probes": len(gates),
        "compared_ram_bytes_per_probe": RAM_END - RAM_START,
        "cases": report,
        "target_image_emitted": False,
    }


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
