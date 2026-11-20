"""Test the H03 RAM owner against linked service veneers and the real cold gate."""

import argparse
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from check_h03_can_monitor_revoke import aggregate_placement, aliases_for
from check_h03_link import HERE, ROOT, TARGET, identify_h03


SITES = {"DIRECT": 0x002924, "SPAN": 0x00294C, "COPY": 0x002D1C,
         "CLOSE": 0x002E9C, "VIRTUAL": 0x003568}
CONTINUATIONS = {
    "h03_service_direct_after_entry": 0x002928,
    "h03_service_stock_span_check": 0x003528,
    "h03_service_copy_after_entry": 0x002D20,
    "h03_service_close_after_store": 0x002EA0,
    "rbm_h03_service_policy": 0x030000,
}


def simulate(base, compiler):
    rom = base.read_bytes()

    def run(*args):
        process = subprocess.run([str(arg) for arg in args], check=True, capture_output=True, timeout=90)
        return process.stdout.decode(errors="replace").strip()

    crt = run(compiler, *TARGET, "-print-file-name=crt0.o")
    includes = (ROOT / "controller/include", ROOT / "controller/vendor/toyota/include",
                ROOT / "diagnostics")
    sources = ("test_lfj8_h03_ram_owner.c", "lfj8_h03_ram_owner.c", "lfj8_h03_application.c",
               "lfj8_h03_mmio.c", "lfj8_h03_service_guard.c", "h03_service_guard_hooks.S")
    with TemporaryDirectory(prefix="rbm-h03-ram-owner-") as directory:
        folder = Path(directory)
        shim = folder / "crt.c"
        shim.write_text("void __init(void) {}\nvoid __fini(void) {}\n", encoding="ascii")
        elf = folder / "ram-owner.elf"
        run(compiler, *TARGET, "-Os", "-std=c11", "-Wall", "-Wextra", "-Werror",
            "-ffunction-sections", "-fdata-sections",
            *(option for path in includes for option in ("-I", path)),
            *(f"-DROM_{name}=0x{rom[address:address + 4].hex()}u" for name, address in SITES.items()),
            "-nostartfiles", crt, *(HERE / source for source in sources), shim,
            "-Wl,-e,_start,-Ttext=0x10000,--gc-sections",
            *(f"-Wl,--defsym={name}={address:#x}" for name, address in CONTINUATIONS.items()),
            "-Wl,--start-group", "-lc", "-lgloss", "-lgcc", "-Wl,--end-group", "-o", elf)
        simulator = compiler.with_name(f"m32r-elf-run{compiler.suffix}")
        result = run(simulator, "--memory-size=16M", elf)
        if result != "H03 RAM owner: cold gate, native service words and protected bounds PASS":
            raise ValueError(f"Unexpected M32R result: {result}")
        return result


def check(args):
    sys.path.insert(0, str(ROOT))
    from tools import check_h03_image_layout as layout

    identity = identify_h03(args.base)
    compiler = args.gcc.resolve()
    _, aliases = aliases_for(args.base, compiler, args.storage_report)
    result = simulate(args.base, compiler)
    old_modules = layout.BINDING_MODULES
    layout.BINDING_MODULES += ("lfj8_h03_ram_owner.c",)
    try:
        placement = aggregate_placement(args, aliases)
    finally:
        layout.BINDING_MODULES = old_modules
    return {
        "base": identity,
        "m32r": result,
        "stock_hook_sites_checked": [f"0x{address:06X}" for address in SITES.values()],
        "linked_service_veneers_and_real_cold_gate": True,
        "external_writers_qualification_supplied_by_fixture": True,
        "aggregate_placement": placement,
        "hardware_tested": False,
        "flashable_image": None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("base", "gcc", "controller", "bridge", "storage-report", "out"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    inputs = (args.base, args.gcc, args.controller, args.bridge, args.storage_report)
    if args.out.suffix.lower() != ".json" or any(
            args.out.resolve() == path.resolve() or
            (args.out.exists() and path.exists() and args.out.samefile(path)) for path in inputs):
        parser.error("Use a separate JSON report")
    try:
        result = check(args)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or error.stdout or str(error).encode()).decode(errors="replace")
        parser.exit(1, f"{detail}\n")
    except (KeyError, OSError, ValueError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
