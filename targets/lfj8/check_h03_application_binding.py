"""Exercise the native H03 application binding in an M32R simulator ELF."""

import argparse
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from check_h03_link import HERE, ROOT, TARGET


FIXTURE_PROFILE = """\
#define RBM_H03_PROFILE_PHASE_CONFIG {8u, 12u, 2u, 24u}
#define RBM_H03_PROFILE_STARTUP_RANGE {0}
#define RBM_H03_PROFILE_TOYOTA_MAX_PERIOD_TICKS 23u
#define RBM_H03_PROFILE_STARTUP_REQUEST_1120 0u
#define RBM_H03_PROFILE_READ_ADAPTATION NULL
"""


def check(compiler, controller):
    compiler = compiler.resolve()
    controller = controller.resolve()
    source = HERE / "lfj8_h03_application_binding.c"
    with TemporaryDirectory(prefix="rbm-h03-binding-") as directory:
        work = Path(directory)

        def run(command, *, checked=True):
            return subprocess.run([str(item) for item in command], cwd=work, check=checked,
                                  capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)

        flags = [compiler, *TARGET, "-Os", "-std=c11", "-Wall", "-Wextra", "-Werror",
                 "-Wno-missing-braces", "-Wno-missing-field-initializers",
                 "-ffunction-sections", "-fdata-sections", "-I", ROOT / "controller/include",
                 "-I", ROOT / "controller/vendor/toyota/include", "-I", ROOT / "diagnostics"]
        refused = run([*flags, "-c", source, "-o", "binding-without-profile.o"], checked=False)
        if refused.returncode == 0 or "Define RBM_H03_APPLICATION_PROFILE" not in refused.stderr:
            raise ValueError("The native binding did not explicitly reject an absent profile")

        (work / "fixture-profile.h").write_text(FIXTURE_PROFILE, encoding="ascii")
        shim = work / "sim-crt.c"
        shim.write_text("void __init(void) {}\nvoid __fini(void) {}\n", encoding="ascii")
        crt = run([compiler, *TARGET, "-print-file-name=crt0.o"]).stdout.strip()
        sources = (
            "h03_application_binding_fixture.c", "h03_application_hooks.S", "lfj8_h03_application.c",
            "lfj8_h03_phase_startup.c", "lfj8_h03_phase_clock.c", "lfj8_h03_mmio.c",
            "lfj8_h03_takeover.c", "lfj8_h03_cycle.c", "lfj8_h03_torque.c",
            "lfj8_h03_sensor_target.c", "lfj8_h03_sensor_feed.c", "lfj8_selector_adc.c",
            "lfj8_donor_io.c", "lfj8_bridge.c", "lfj8_h03_atf.c", "lfj8_h03_atf_tml0.c",
            "lfj8_h03_engine_feed.c", "lfj8_h03_engine_rx.c",
            "ta2005_chery_inputs.c", "ta2005_engine_qualifier.c",
        )
        run([*flags, "-I", work, '-DRBM_H03_APPLICATION_PROFILE="fixture-profile.h"',
             "-nostartfiles", crt, source, *(HERE / name for name in sources),
             ROOT / "diagnostics/chery_dtc.c", shim, controller,
             "-Wl,--gc-sections,-e,_start,--start-group", "-lc", "-lgloss", "-lgcc", "-Wl,--end-group",
             "-o", "binding.elf"])
        simulator = compiler.with_name(f"m32r-elf-run{compiler.suffix}")
        output = run([simulator, "--memory-size=16M", "binding.elf"]).stdout.strip()
        if not output.endswith("PASS"):
            raise ValueError("The native binding fixture did not reach its verified result")
        return {"status": "PASS", "fixture_result": output, "unprofiled_compile_rejected": True,
                "hardware_tested": False, "flashable_image": None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("gcc", "controller", "out"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    if args.out.suffix.lower() != ".json" or any(
            args.out.resolve() == path.resolve() or
            (args.out.exists() and path.exists() and args.out.samefile(path))
            for path in (args.gcc, args.controller)):
        parser.error("--out must be a separate JSON report")
    try:
        result = check(args.gcc, args.controller)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(result["fixture_result"])
    except subprocess.CalledProcessError as error:
        parser.exit(1, (error.stderr or error.stdout or str(error)) + "\n")
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
