"""Link the native H03 startup and Toyota release providers in an M32R test ELF."""

import argparse
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from check_h03_link import HERE, ROOT, TARGET
from lfj8_h03_layout import alloc_sections, read_elf


# Only this simulator translates the profile to the stand-in input and clock providers.
PROFILE = """\
#include "lfj8_h03_target_platform.h"
int test_initialize_inputs(void *);
int test_capture_inputs(void *, const Lfj8H03SensorSnapshot *, uint32_t,
                        Lfj8H03CycleInput *, Lfj8H03CycleLoad *);
#define RBM_H03_PROFILE_PHASE_CONFIG {8u, 13u, 4u, 24u}
#define RBM_H03_PROFILE_STARTUP_RANGE {0}
#define RBM_H03_PROFILE_TOYOTA_MAX_PERIOD_TICKS 20u
#define RBM_H03_PROFILE_STARTUP_REQUEST_1120 0u
#define RBM_H03_PROFILE_READ_ADAPTATION NULL
#define RBM_H03_PROFILE_TOYOTA_PERIOD_TICKS 16u
#define RBM_H03_PROFILE_TOYOTA_MAX_LATENESS_TICKS 2u
#define RBM_H03_PROFILE_INITIALIZE_INPUTS test_initialize_inputs
#define RBM_H03_PROFILE_CAPTURE_TOYOTA test_capture_inputs
"""


def check(compiler, controller, bridge):
    source = HERE / "lfj8_h03_target_platform.c"
    with TemporaryDirectory(prefix="rbm-h03-target-platform-") as directory:
        work = Path(directory)

        def run(*command, checked=True):
            return subprocess.run([str(item) for item in command], cwd=work, check=checked,
                                  capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90)

        includes = (HERE, ROOT / "controller/include", ROOT / "controller/vendor/toyota/include",
                    ROOT / "diagnostics", work)
        flags = [compiler, *TARGET, "-Os", "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wno-missing-braces",
                 "-Wno-missing-field-initializers",
                 "-ffunction-sections", "-fdata-sections",
                 *(arg for folder in includes for arg in ("-I", folder))]
        compile_platform = [*flags, "-ffreestanding", "-fno-builtin", "-fno-common",
                            "-c", source, "-o", "platform.o"]
        refused = run(*compile_platform, checked=False)
        if refused.returncode == 0 or "Define RBM_H03_APPLICATION_PROFILE" not in refused.stderr:
            raise ValueError("Platform accepted an absent application profile")

        profile = work / "test-profile.h"
        profile.write_text(PROFILE.replace("MAX_PERIOD_TICKS 20u", "MAX_PERIOD_TICKS 17u"), encoding="ascii")
        profile_flag = '-DRBM_H03_APPLICATION_PROFILE="test-profile.h"'
        refused = run(*compile_platform, profile_flag, checked=False)
        if refused.returncode == 0 or "lateness must fit the application watchdog" not in refused.stderr:
            raise ValueError("Platform accepted timing outside the application watchdog")
        profile.write_text(PROFILE, encoding="ascii")
        run(*compile_platform, profile_flag)

        sections = alloc_sections(read_elf(work / "platform.o", 1))
        if any(section["flags"] & 1 for section in sections):
            raise ValueError("Platform allocated writable storage outside the release RAM alias")
        flash = sum(section["size"] for section in sections)

        shim = work / "sim-crt.c"
        shim.write_text("void __init(void) {}\nvoid __fini(void) {}\n", encoding="ascii")
        crt = run(compiler, *TARGET, "-print-file-name=crt0.o").stdout.strip()
        sources = (
            "test_lfj8_h03_target_platform.c", "h03_application_hooks.S", "h03_phase_startup_hook.S",
            "h03_phase_release_hook.S", "lfj8_h03_application_binding.c",
            "lfj8_h03_application.c", "lfj8_h03_phase_startup.c", "lfj8_h03_phase_clock.c",
            "lfj8_h03_takeover.c", "lfj8_h03_cycle.c", "lfj8_h03_torque.c",
            "lfj8_h03_sensor_target.c", "lfj8_h03_sensor_feed.c", "lfj8_h03_atf_tml0.c",
            "lfj8_h03_engine_feed.c", "ta2005_engine_qualifier.c",
        )
        run(*flags, profile_flag, "-nostartfiles", crt, "platform.o", *(HERE / name for name in sources),
            ROOT / "diagnostics/chery_dtc.c", shim, bridge, controller,
            "-Wl,--gc-sections,-e,_start,--start-group", "-lc", "-lgloss", "-lgcc", "-Wl,--end-group",
            "-o", "platform.elf")
        linked = read_elf(work / "platform.elf", 2)
        release = linked["symbols"]["rbm_h03_toyota_release_state"]
        if (release["size"] != 16 or release["address"] % 4 or
                not linked["sections"][release["section"]]["flags"] & 1):
            raise ValueError("The simulator release alias disagrees with the target RAM requirement")
        simulator = compiler.with_name(f"m32r-elf-run{compiler.suffix}")
        output = run(simulator, "--memory-size=16M", "platform.elf").stdout.strip()
        expected = "H03 target platform: native startup and foreground, Toyota rollover and inhibition PASS"
        if output != expected:
            raise ValueError(f"Unexpected M32R result: {output}")
        return {"status": "PASS", "m32r": output, "unprofiled_and_inconsistent_timing_refused": True,
                "flash_section_bytes": flash,
                "required_release_alias_bytes": 16, "platform_object_writable_bytes": 0,
                "hardware_tested": False, "flashable_image": None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("gcc", "controller", "bridge", "out"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    inputs = [getattr(args, name).resolve() for name in ("gcc", "controller", "bridge")]
    if args.out.suffix.lower() != ".json" or any(args.out.resolve() == path or
            (args.out.exists() and path.exists() and args.out.samefile(path)) for path in inputs):
        parser.error("Use a separate JSON report")
    try:
        report = check(*inputs)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(report["m32r"])
    except subprocess.CalledProcessError as error:
        parser.exit(1, (error.stderr or error.stdout or str(error)) + "\n")
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
