"""Run the original S51/S83 store bundles and candidate hooks at H03 addresses."""

import argparse
import json
from pathlib import Path
import subprocess

from check_h03_link import identify_h03


HERE = Path(__file__).resolve().parent
TARGET = ("-m32r", "-mmodel=medium", "-msdata=none", "-Wa,-EB")
SITES = ((0xAA0C, "s51", "2244f000"), (0xAA70, "s83", "2045f000"))
SOURCES = (
    "lfj8_bridge.c", "lfj8_donor_io.c", "lfj8_h03_mmio.c",
    "lfj8_h03_atf.c", "lfj8_h03_atf_target.c", "lfj8_h03_atf_tml0.c",
    "lfj8_h03_sensor_feed.c", "lfj8_h03_sensor_target.c",
    "h03_sensor_hooks.S", "h03_sensor_hook_fixture.c",
)


def run(*args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise ValueError(f"{Path(args[0]).name} failed:\n{result.stdout}{result.stderr}")
    return result.stdout.strip()


def check(base, gcc, output):
    identity = identify_h03(base)
    rom = base.read_bytes()
    for address, name, stock in SITES:
        if rom[address:address + 4].hex() != stock:
            raise ValueError(f"Unexpected H03 store bundle for {name}")

    output.mkdir(parents=True, exist_ok=True)
    shim = output / "sim_crt.c"
    shim.write_text("void __init(void) {}\nvoid __fini(void) {}\n", encoding="ascii")
    crt = run(gcc, *TARGET, "-print-file-name=crt0.o")
    nm = gcc.with_name("m32r-elf-nm" + gcc.suffix)
    objcopy = gcc.with_name("m32r-elf-objcopy" + gcc.suffix)
    sim = gcc.with_name("m32r-elf-run" + gcc.suffix)
    placements = [f"-Wl,--section-start=.sensor_{name}={address:#x}" for address, name, _ in SITES]
    results = {}
    for variant, define in (("stock", ("-DSENSOR_STOCK",)), ("hooked", ())):
        elf = output / f"{variant}.elf"
        run(gcc, *TARGET, "-std=c11", "-Os", "-Wall", "-Wextra", "-Werror",
            "-ffunction-sections", "-fdata-sections", *define, "-nostartfiles", crt,
            *(HERE / source for source in SOURCES), shim, *placements,
            "-Wl,-e,_start,--gc-sections", "-Wl,--start-group", "-lc", "-lgloss", "-lgcc",
            "-Wl,--end-group", "-o", elf)
        symbols = {row.split()[-1]: int(row.split()[0], 16)
                   for row in run(nm, "--defined-only", elf).splitlines() if len(row.split()) == 3}
        for address, name, stock in SITES:
            if (symbols[f"fixture_{name}_site"], symbols[f"h03_sensor_after_{name}"]) != (
                address, address + 4,
            ):
                raise ValueError(f"{variant} {name} store or resume address differs")
            bundle = output / f"{variant}-{name}.dat"
            run(objcopy, "-O", "binary", "-j", f".sensor_{name}", elf, bundle)
            word = bundle.read_bytes()[:4]
            if variant == "stock" and word.hex() != stock:
                raise ValueError(f"{name} stock fixture does not match the H03 instruction")
            if variant == "hooked":
                displacement = int.from_bytes(word[1:], "big", signed=True) * 4
                if word[0] != 0xFF or address + displacement != symbols[f"rbm_h03_{name}_capture_hook"]:
                    raise ValueError(f"{name} long branch does not reach the hook")
        result = run(sim, "--memory-size=16M", elf)
        if "PASS" not in result:
            raise ValueError(f"{variant} simulation did not report PASS: {result}")
        results[variant] = result

    report = {
        "source": identity, "runs": results,
        "capture_store_addresses": [f"{address:#08x}" for address, _, _ in SITES],
        "scope": "native store bundles with simulated MMIO and isolated foreground invocation",
        "hardware_tested": False, "flashable_image": None,
    }
    (output / "sensor-native.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("base", "gcc", "out"):
        parser.add_argument("--" + key, type=Path, required=True)
    args = parser.parse_args()
    try:
        check(args.base.resolve(), args.gcc.resolve(), args.out.resolve())
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
