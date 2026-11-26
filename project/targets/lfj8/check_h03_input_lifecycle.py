"""Run the exact H03 S51/S83 entry words with the production application gate."""

import argparse
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from check_h03_link import ROOT, identify_h03
from check_h03_sensor_native import HERE, SITES, SOURCES, TARGET, run


def check(base, gcc):
    identity = identify_h03(base)
    rom = base.read_bytes()
    for address, channel, stock in SITES:
        if rom[address:address + 4].hex() != stock:
            raise ValueError(f"Unexpected H03 capture store for {channel}")
    tool = gcc.with_name
    crt = run(gcc, *TARGET, "-print-file-name=crt0.o")
    includes = (ROOT / "controller/include", ROOT / "controller/vendor/toyota/include",
                ROOT / "diagnostics")
    with TemporaryDirectory(prefix="rbm-h03-input-lifecycle-") as directory:
        work = Path(directory)
        shim = work / "sim_crt.c"
        shim.write_text("void __init(void) {}\nvoid __fini(void) {}\n", encoding="ascii")
        elf = work / "input-gate.elf"
        run(gcc, *TARGET, "-std=c11", "-Os", "-Wall", "-Wextra", "-Werror",
            "-ffunction-sections", "-fdata-sections", "-DSENSOR_APPLICATION_GATE",
            *(option for folder in includes for option in ("-I", folder)),
            "-nostartfiles", crt, *(HERE / name for name in SOURCES),
            HERE / "lfj8_h03_application.c", shim,
            *(f"-Wl,--section-start=.sensor_{channel}={address:#x}" for address, channel, _ in SITES),
            "-Wl,-e,_start,--gc-sections", "-Wl,--start-group", "-lc", "-lgloss", "-lgcc",
            "-Wl,--end-group", "-o", elf)

        nm = tool(f"m32r-elf-nm{gcc.suffix}")
        objcopy = tool(f"m32r-elf-objcopy{gcc.suffix}")
        symbols = {row[2]: int(row[0], 16) for row in
                   (line.split() for line in run(nm, "--defined-only", elf).splitlines()) if len(row) == 3}
        for address, channel, _ in SITES:
            section = f".sensor_{channel}"
            bundle = work / f"{channel}.dat"
            run(objcopy, "-O", "binary", "-j", section, elf, bundle)
            word = bundle.read_bytes()[:4]
            offset = int.from_bytes(word[1:], "big", signed=True) * 4
            if (word[0] != 0xFF or symbols[f"fixture_{channel}_site"] != address or
                    symbols[f"h03_sensor_after_{channel}"] != address + 4 or
                    symbols[f"rbm_h03_{channel}_capture_hook"] != address + offset):
                raise ValueError(f"Unexpected entry/resume path for {channel}")
        sim = tool(f"m32r-elf-run{gcc.suffix}")
        observed = run(sim, "--memory-size=16M", elf).splitlines()
        expected = [
            "H03 input lifecycle: unowned RAM and stopped application PASS",
            "H03 sensors: native stores, common clock revocation and new epoch PASS",
        ]
        if observed != expected:
            raise ValueError(f"Unexpected input lifecycle output: {observed}")
    return {
        "base": identity,
        "native_sites": {channel: f"{address:#08x}" for address, channel, _ in SITES},
        "production_application_gate_linked": True,
        "closed_gate_cases": ["unowned_ram_with_retained_running_flag", "owned_ram_before_application_start"],
        "result": observed,
        "ram_ownership_fixture_supplied": True,
        "hardware_tested": False,
        "flashable_image": None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("base", "gcc", "out"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    if args.out.suffix.lower() != ".json" or any(
            args.out.resolve() == path.resolve() or
            (args.out.exists() and path.exists() and args.out.samefile(path)) for path in (args.base, args.gcc)):
        parser.error("Use a separate JSON output")
    try:
        report = check(args.base.resolve(), args.gcc.resolve())
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
