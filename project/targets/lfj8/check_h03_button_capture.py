"""Compile button capture checks and replay the exact stock H03 P1DATA instructions."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
from shutil import copyfile
from tempfile import TemporaryDirectory

from check_h03_link import identify_h03
from check_h03_selector_adc import run


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
C_SOURCES = ("lfj8_h03_button_capture.c", "test_lfj8_h03_button_capture.c", "lfj8_range_control.c")
FLAGS = ("-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-I.")
TARGET = ("-m32r", "-Wa,-EB", "-mmodel=medium", "-msdata=none")
FRAGMENTS = (
    ("access_p1", 0x00C99C, 0x00CA00, ""),
    ("range_profile", 0x013874, 0x013878, ""),
    ("range_fallback", 0x016528, 0x01652C, ""),
    ("stock_p1_profile", 0x03AC2C, 0x03AC6C, "jmp lr || nop\n"),
    ("stock_p1_dispatch", 0x03ACA4, 0x03ACB0, "bra.l stock_p1_project\n"),
    ("stock_p1_project", 0x03AD18, 0x03AD38, "jmp lr || nop\n"),
    ("stock_p1_fallback", 0x03AD60, 0x03AD70, ""),
    ("stock_p1_clear", 0x03AEC0, 0x03AEE8, "jmp lr || nop\n"),
    ("stock_p1", 0x040180, 0x040210, "pop lr || nop\njmp lr || nop\n"),
)
CAPTURE_PASS = "H03 button capture: 512 source combinations, invalid wiring and debounce handoff PASS"
STOCK_PASS = "H03 stock P1DATA: 256 raw bytes, five flags, stock selector and both projections PASS"


def stage_stock(stage, rom):
    assembly, placements, evidence = [], [], {}
    for name, start, end, tail in FRAGMENTS:
        data = rom[start:end]
        (stage / (name + ".dat")).write_bytes(data)
        assembly.extend((f'.section .{name},"ax"', f".global {name}", f"{name}:",
                         f'.incbin "{name}.dat"', tail))
        placements.append(f"-Wl,--section-start=.{name}={start:#x}")
        evidence[name] = {"start": f"{start:#08x}", "end_exclusive": f"{end:#08x}",
                          "sha256": sha256(data).hexdigest()}
    # Skip unrelated OEM arithmetic at the entry to the fallback.
    assembly.append('.section .fallback_resume,"ax"\nbra.l stock_p1_clear\n')
    placements.append("-Wl,--section-start=.fallback_resume=0x03AE30")
    (stage / "stock.S").write_text("\n".join(assembly), encoding="ascii")
    return placements, evidence


def check(base, zig, gcc, pc_controller, m32r_controller):
    identity = identify_h03(base)
    rom = base.read_bytes()
    if sha256(rom).hexdigest() != identity["sha256"] or (rom[0x013874], rom[0x01652A]) != (2, 1):
        raise ValueError("Expected unmodified H03 with the verified range profile and fallback")

    with TemporaryDirectory(prefix="rbm-h03-p1data-") as temp:
        stage = Path(temp)
        for folder in ("controller/include", "controller/vendor/toyota/include", "targets/lfj8"):
            for header in (ROOT / folder).glob("*.h"):
                copyfile(header, stage / header.name)
        for name in C_SOURCES:
            copyfile(HERE / name, stage / name)
        copyfile(pc_controller, stage / pc_controller.name)
        copyfile(m32r_controller, stage / m32r_controller.name)

        windows = pc_controller.suffix.lower() == ".dll"
        exe = "button_capture.exe" if windows else "button_capture"
        rpath = () if windows else ("-Wl,-rpath,$ORIGIN",)
        run(stage, zig, "cc", *FLAGS, *C_SOURCES, pc_controller.name, *rpath, "-o", exe)
        pc = run(stage, stage / exe).strip()
        if pc != CAPTURE_PASS:
            raise ValueError(f"Unexpected PC output: {pc}")

        if run(stage, gcc, "-dumpmachine").strip() != "m32r-elf":
            raise ValueError("A bare-metal M32R compiler is required")
        crt = run(stage, gcc, *TARGET, "-print-file-name=crt0.o").strip()
        (stage / "startup.c").write_text("void __init(void) {}\nvoid __fini(void) {}\n", encoding="ascii")
        placements, fragments = stage_stock(stage, rom)
        run(stage, gcc, *TARGET, *FLAGS, "-Wno-missing-field-initializers", "-Wno-missing-braces",
            "-DCHECK_H03_STOCK_P1", "-nostartfiles", crt, "startup.c", *C_SOURCES, "stock.S",
            m32r_controller.name, "-Wl,-Ttext,0x100000,-e,_start,--start-group", *placements,
            "-lc", "-lgloss", "-lgcc", "-Wl,--end-group", "-o", "button_capture.elf")
        simulator = gcc.with_name(f"m32r-elf-run{gcc.suffix}")
        target = run(stage, simulator, "--memory-size", "16M", "button_capture.elf").strip().splitlines()
        if target != [CAPTURE_PASS, STOCK_PASS]:
            raise ValueError(f"Unexpected M32R output: {target}")

    return {"status": "PASS_OFFLINE_ONLY", "base": identity, "range_profile_013874": rom[0x013874],
            "fallback_selector_01652a": rom[0x01652A],
            "native_fragments": fragments, "pc_test": pc, "m32r_tests": target,
            "equipment_tested": False, "flashable_image": None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("base", "zig", "gcc", "pc-controller", "m32r-controller", "out"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    out = args.out.resolve()
    inputs = (args.base, args.pc_controller, args.m32r_controller)
    if out.suffix.lower() != ".json" or any(
        out == item.resolve() or (out.exists() and out.samefile(item)) for item in inputs
    ):
        parser.error("--out must be a separate JSON report")
    try:
        result = check(args.base.resolve(), args.zig.resolve(), args.gcc.resolve(),
                       args.pc_controller.resolve(), args.m32r_controller.resolve())
        statement = json.dumps(result, indent=2) + "\n"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(statement, encoding="utf-8")
        print(statement, end="")
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
