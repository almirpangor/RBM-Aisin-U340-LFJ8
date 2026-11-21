"""Check H03 geometry, the DTC journal model and native array reads without hardware."""

import argparse
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
from tempfile import TemporaryDirectory

from check_h03_link import FLASH_END, FLASH_START, HERE, TARGET, TAIL_END, TAIL_START, elf_info, identify_h03


GEOMETRY_OFFSET = 0x000920
# Renesas REJ09B0067-0110, table 6.5.3 (M32176F4).
ERASE_ENDS = (0x01FFE, 0x02FFE, 0x03FFE, 0x05FFE, 0x07FFE, 0x0FFFE, 0x1FFFE,
              0x2FFFE, 0x3FFFE, 0x4FFFE, 0x5FFFE, 0x6FFFE, 0x7FFFE)
RESERVATIONS = (
    ("stock service area", 0, 0x008000),
    ("application layout primary", FLASH_START, FLASH_END),
    ("application layout tail", TAIL_START, TAIL_END),
    ("stock application end marker", 0x07FFFE, 0x080000),
)
DIAGNOSTICS = HERE.parents[1] / "diagnostics"


def check_geometry(base):
    identity = identify_h03(base)
    image = base.read_bytes()
    bounds = tuple(struct.iter_unpack(">II", image[GEOMETRY_OFFSET:GEOMETRY_OFFSET + 8 * len(ERASE_ENDS)]))
    want = tuple(zip((0, *(end + 2 for end in ERASE_ENDS[:-1])), ERASE_ENDS))
    if bounds != want:
        raise ValueError("H03 erase table disagrees with the M32176F4 geometry")

    blocks = []
    for index, (first, last_even) in enumerate(bounds):
        end = last_even + 2
        data = image[first:end]
        blocks.append({
            "block": index, "first": f"0x{first:06X}", "end_exclusive": f"0x{end:06X}",
            "last_even": f"0x{last_even:06X}", "erase_bytes": end - first,
            "non_ff_bytes": len(data) - data.count(0xFF),
            "overlaps": [role for role, lo, hi in RESERVATIONS if first < hi and lo < end],
        })
    return {
        "base": identity, "oem_geometry_offset": f"0x{GEOMETRY_OFFSET:06X}",
        "halfword_bytes": 2, "blocks": blocks, "assigned_nvm_blocks": [],
    }


def run_backend_checks(cc, gcc, controller=None):
    flags = ("-std=c11", "-Os", "-Wall", "-Wextra", "-Werror")
    inputs = (
        HERE / "lfj8_h03_nvm.h", HERE / "lfj8_h03_nvm.c", HERE / "test_lfj8_h03_nvm.c",
        DIAGNOSTICS / "chery_dtc.h", DIAGNOSTICS / "chery_dtc.c",
        DIAGNOSTICS / "chery_dtc_journal.h", DIAGNOSTICS / "chery_dtc_journal.c",
    )
    host = [str(cc), "cc"] if cc.stem.lower() == "zig" else [str(cc)]
    with TemporaryDirectory(prefix="rbm-h03-nvm-") as directory:
        stage = Path(directory)
        for path in inputs:
            shutil.copyfile(path, stage / path.name)
        sources = [path.name for path in inputs if path.suffix == ".c"]
        hooks = stage / "hooks.c"
        hooks.write_text("void __init(void) {}\nvoid __fini(void) {}\n", encoding="ascii")
        env = dict(os.environ, PATH=str(gcc.parent) + os.pathsep + os.environ.get("PATH", ""))

        def run(*command):
            return subprocess.run(command, cwd=stage, env=env, text=True, check=True,
                                  stdout=subprocess.PIPE, timeout=120).stdout.strip()

        host_exe = "host.exe" if os.name == "nt" else "host"
        run(*host, *flags, "-pedantic", *sources, "-o", host_exe)
        pc = run(str(stage / host_exe))
        crt = run(str(gcc), *TARGET, "-print-file-name=crt0.o")
        run(str(gcc), *TARGET, *flags, "-nostartfiles", crt, *sources, hooks.name,
            "-Wl,-e,_start,--start-group", "-lc", "-lgloss", "-lgcc",
            "-Wl,--end-group", "-o", "nvm.elf")
        elf, _ = elf_info(stage / "nvm.elf", 2)
        m32r = run(str(gcc.with_name("m32r-elf-run" + gcc.suffix)), "nvm.elf")

        controller_root = HERE.parents[1] / "controller"
        if controller is None:
            controller_out = stage / "controller"
            run(sys.executable, "-B", controller_root / "build_target.py",
                "m32r", "--cc", gcc, "--out", controller_out)
            controller = controller_out / "rbm_u340e_m32r_be.o"
        native_flags = (*TARGET, *flags, "-ffunction-sections", "-fdata-sections",
                        "-I", HERE, "-I", DIAGNOSTICS, "-I", controller_root / "include",
                        "-I", controller_root / "vendor/toyota/include")
        run(str(gcc), *native_flags, "-c", HERE / "lfj8_h03_nvm_native.c")
        native_object, _ = elf_info(stage / "lfj8_h03_nvm_native.o", 1)
        run(str(gcc), *native_flags, "-nostartfiles", crt,
            "lfj8_h03_nvm.c", "chery_dtc.c", "chery_dtc_journal.c", "lfj8_h03_nvm_native.o",
            HERE / "lfj8_h03_mmio.c", HERE / "h03_nvm_native_fixture.c", hooks.name, controller,
            "-Wl,-Ttext,0x100000,--gc-sections,-e,_start,--start-group", "-lc", "-lgloss", "-lgcc",
            "-Wl,--end-group", "-o", "nvm-native.elf")
        _, allocated = elf_info(stage / "nvm-native.elf", 2)
        if any(address < ERASE_ENDS[-1] + 2 for address, _, _ in allocated):
            raise ValueError("Simulator ELF overlaps the H03 flash used by the read fixture")
        native = run(str(gcc.with_name("m32r-elf-run" + gcc.suffix)),
                     "--memory-size", "16M", "nvm-native.elf")

    expected = "H03 erase ends:" + "".join(f" {end:05X}" for end in ERASE_ENDS)
    if pc != m32r or not pc.startswith(expected + "\n") or not pc.endswith("restart PASS"):
        raise ValueError("PC/M32R backend checks disagree or did not finish")
    native_lines = native.splitlines()
    if len(native_lines) != 3 or not all(line.startswith("PASS native H03 array:") for line in native_lines):
        raise ValueError("Native H03 array checks did not finish")
    return {"pc": pc.splitlines(), "m32r": m32r.splitlines(), "m32r_simulator_elf": elf,
            "m32r_native_read": native_lines, "m32r_native_reader_object": native_object}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("base", "gcc", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--cc", default="zig")
    parser.add_argument("--controller", type=Path, help="Reuse a built big-endian M32R controller object")
    args = parser.parse_args()
    cc = shutil.which(args.cc)
    if not cc:
        parser.error(f"C compiler not found: {args.cc}")
    inputs = (args.base, args.gcc, *(p for p in (args.controller,) if p is not None))
    if args.out.suffix.lower() != ".json" or any(args.out.resolve() == p.resolve() for p in inputs):
        parser.error("--out must be a separate JSON report")
    try:
        report = check_geometry(args.base)
        controller = args.controller.resolve() if args.controller is not None else None
        report["checks"] = run_backend_checks(Path(cc).resolve(), args.gcc.resolve(), controller)
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        parser.exit(1, f"H03 NVM check failed: {error}\n")
    report.update(status="PASS_OFFLINE_ONLY", equipment_tested=False, flash_operations_executed=False)
    output = json.dumps(report, indent=2) + "\n"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(output, encoding="utf-8")
    print(output, end="")


if __name__ == "__main__":
    main()
