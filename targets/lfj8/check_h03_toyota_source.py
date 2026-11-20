"""Run the native Toyota release adapter from the production LFJ8 bridge."""

import argparse
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from check_h03_can_monitor_revoke import aggregate_placement, aliases_for
from check_h03_link import HERE, ROOT, TARGET, identify_h03


RELEASE_ROOTS = ("lfj8_h03_toyota_source_reset", "lfj8_h03_toyota_source_take")


def simulate(compiler, bridge, controller):
    def run(*args):
        result = subprocess.run([str(arg) for arg in args], check=True, capture_output=True, timeout=90)
        return result.stdout.decode(errors="replace").strip()

    crt = run(compiler, *TARGET, "-print-file-name=crt0.o")
    includes = (ROOT / "controller/include", ROOT / "controller/vendor/toyota/include",
                ROOT / "diagnostics")
    with TemporaryDirectory(prefix="rbm-h03-toyota-release-") as directory:
        work = Path(directory)
        shim = work / "crt.c"
        shim.write_text("void __init(void) {}\nvoid __fini(void) {}\n", encoding="ascii")
        elf = work / "release.elf"
        run(compiler, *TARGET, "-Os", "-std=c11", "-Wall", "-Wextra", "-Werror",
            "-Wno-missing-braces", "-Wno-missing-field-initializers",
            "-ffunction-sections", "-fdata-sections",
            *(option for folder in includes for option in ("-I", folder)),
            "-nostartfiles", crt, HERE / "test_lfj8_h03_toyota_source.c",
            HERE / "lfj8_h03_input_binding.c", HERE / "lfj8_range_control.c",
            HERE / "lfj8_h03_button_capture.c", bridge, controller, shim,
            "-Wl,-e,_start,--gc-sections", "-Wl,--start-group", "-lc", "-lgloss", "-lgcc",
            "-Wl,--end-group", "-o", elf)
        simulator = compiler.with_name(f"m32r-elf-run{compiler.suffix}")
        result = run(simulator, "--memory-size=16M", elf)
        if result != "H03 Toyota release: native TML0, fixed deadlines, faults, rollover and manual target PASS":
            raise ValueError(f"Unexpected M32R result: {result}")
        return result


def check(args):
    sys.path.insert(0, str(ROOT))
    from tools import check_h03_image_layout as layout

    identity = identify_h03(args.base)
    compiler = args.gcc.resolve()
    _, aliases = aliases_for(args.base, compiler, args.storage_report)
    result = simulate(compiler, args.bridge.resolve(), args.controller.resolve())
    previous_roots = layout.EXTRA_ROOTS
    layout.EXTRA_ROOTS += RELEASE_ROOTS
    try:
        placement = aggregate_placement(args, aliases)
    finally:
        layout.EXTRA_ROOTS = previous_roots
    return {
        "base": identity,
        "m32r": result,
        "native_counter": "TML0CT 0x8003E0",
        "release_state_bytes": 16,
        "allocated_release_state_bytes": 0,
        "aggregate_placement": placement,
        "physical_toyota_period_verified": False,
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
        report = check(args)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or error.stdout or str(error).encode()).decode(errors="replace")
        parser.exit(1, f"{detail}\n")
    except (KeyError, OSError, ValueError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
