"""Link the native H03 startup and Toyota release providers in an M32R test ELF."""

import argparse
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from check_h03_link import HERE, ROOT, TARGET
from lfj8_h03_layout import alloc_sections, read_elf


RELEASE_SYMBOL = "rbm_h03_toyota_release_state"
PLATFORM_ENTRIES = ("rbm_h03_target_initialize", "rbm_h03_target_take_toyota")


# Only this simulator translates the profile to the stand-in input and clock providers.
PROFILE = """\
#include "lfj8_h03_target_platform.h"
#include "lfj8_h03_target_service.h"
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
extern const Lfj8H03TargetServiceConfig test_can_service_config;
#define RBM_H03_PROFILE_CAN_SERVICE_CONFIG test_can_service_config
"""

MANUAL_PROFILE = (
    PROFILE.replace("MAX_PERIOD_TICKS 20u", "MAX_PERIOD_TICKS 70u")
    .replace("PERIOD_TICKS 16u", "PERIOD_TICKS 64u")
    .replace("#define RBM_H03_PROFILE_CAPTURE_TOYOTA test_capture_inputs", """
#include "lfj8_h03_input_binding.h"
extern const Lfj8H03ToyotaInputCapture test_input_capture;
#define RBM_H03_PROFILE_TOYOTA_INPUT_CAPTURE test_input_capture
#include "lfj8_h03_toyota_input_profile.h"
""".strip())
)


def common_placement(run, work, base, compiler, controller, bridge, profile):
    storage = work / "storage.json"
    layout = work / "layout"
    run(sys.executable, "-B", HERE / "check_h03_storage.py", "--base", base, "--gcc", compiler,
        "--out", storage)
    attempt = run(sys.executable, "-B", ROOT / "tools/check_h03_image_layout.py",
                  "--base", base, "--gcc", compiler, "--controller", controller, "--bridge", bridge,
                  "--profile", "padding-candidate", "--with-bindings", "--with-dtc-rx",
                  "--storage-report", storage, "--application-profile", profile, "--out", layout,
                  checked=False)
    report_path = layout / "layout.json"
    if not report_path.is_file():
        attempt.check_returncode()
        raise ValueError("Common layout did not produce an address report")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if attempt.returncode and report["status"] != "FAIL_BINDINGS":
        attempt.check_returncode()
    target = report["target_platform"]
    unresolved = report.get("unresolved_symbols", [])
    release = target["release_ram"]
    if (not release or release["symbol"] != RELEASE_SYMBOL or release["bytes"] != 16 or
            release["alignment"] != 4 or release["address"] % 4 or
            any(symbol in unresolved for symbol in (RELEASE_SYMBOL, *PLATFORM_ENTRIES))):
        raise ValueError("Common layout did not resolve the platform and its typed Toyota release RAM")
    return {**target, "common_layout_status": report["status"], "unresolved_symbols": unresolved,
            "base_sha256": report["base"]["sha256"],
            "common_flash_bytes": report["flash_payload_bytes"],
            "typed_inventory_bytes": json.loads(storage.read_text(encoding="utf-8"))["storage_bytes"]}


def placed_objects(run, compiler, flags, profile_flag, sources, sections, placement):
    flash = placement.get("flash_placements", [])
    expected = {section["name"]: (section["size"], section["flags"]) for section in sections}
    actual = {item["section"]: (item["bytes"], item["flags"]) for item in flash}
    if actual != expected or len(flash) != len(expected):
        raise ValueError("Common layout does not cover the compiled platform sections exactly")

    objcopy = run(compiler, "-print-prog-name=objcopy").stdout.strip()
    names = {item["section"]: f".platform_at_{index}" for index, item in enumerate(flash)}
    run(objcopy, *(f"--rename-section={old}={new}" for old, new in names.items()),
        "platform.o", "placed-platform.o")
    run(*flags, profile_flag, "-fno-common", "-c", sources[0], "-o", "fixture.o")
    # Replace the fixture's ordinary allocation with the common layout's absolute alias.
    run(objcopy, f"--weaken-symbol={RELEASE_SYMBOL}", "fixture.o", "placed-fixture.o")
    address = placement["release_ram"]["address"]
    options = ["-Wl,-N", f"-Wl,--defsym={RELEASE_SYMBOL}={address:#x}"]
    options.extend(f'-Wl,--section-start={names[item["section"]]}={item["address"]:#x}' for item in flash)
    return ("placed-platform.o", "placed-fixture.o", *sources[1:]), options, names


def verify_placed_elf(linked, placement, names):
    sections = {section["name"]: section for section in linked["sections"]}
    for item in placement["flash_placements"]:
        section = sections[names[item["section"]]]
        if (section["address"], section["size"], section["flags"]) != (
                item["address"], item["bytes"], item["flags"]):
            raise ValueError("Simulator ELF moved platform section " + item["section"])
    address = placement["release_ram"]["address"]
    release = linked["symbols"][RELEASE_SYMBOL]
    if (release["section"], release["address"]) != (0xFFF1, address):
        raise ValueError("Simulator ELF did not bind the absolute Toyota release address")
    descriptor = sections[names[".rodata.toyota_source"]]["data"]
    if int.from_bytes(descriptor[:4], "big") != address:
        raise ValueError("Linked Toyota source descriptor does not point to the typed release field")


def check(compiler, controller, bridge, *, base=None):
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
        profile_flag = '-DRBM_H03_APPLICATION_PROFILE="test-profile.h"'
        profile.write_text(PROFILE.replace("#define RBM_H03_PROFILE_CAN_SERVICE_CONFIG test_can_service_config", ""),
                           encoding="ascii")
        refused = run(*compile_platform, profile_flag, checked=False)
        if refused.returncode == 0 or "Define RBM_H03_PROFILE_CAN_SERVICE_CONFIG" not in refused.stderr:
            raise ValueError("Platform accepted an absent CAN service profile")
        profile.write_text(PROFILE.replace("MAX_PERIOD_TICKS 20u", "MAX_PERIOD_TICKS 17u"), encoding="ascii")
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
        source_names = (
            "test_lfj8_h03_target_platform.c", "h03_application_hooks.S", "h03_phase_startup_hook.S",
            "h03_phase_release_hook.S", "lfj8_h03_application_binding.c",
            "lfj8_h03_application.c", "lfj8_h03_phase_startup.c", "lfj8_h03_phase_clock.c",
            "lfj8_h03_takeover.c", "lfj8_h03_cycle.c", "lfj8_h03_torque.c",
            "lfj8_h03_sensor_target.c", "lfj8_h03_sensor_feed.c", "lfj8_h03_atf_tml0.c",
            "lfj8_h03_engine_feed.c", "ta2005_engine_qualifier.c",
        )
        sources = tuple(HERE / name for name in source_names)
        objects = ("platform.o", *sources)
        placed = None
        link_options = []
        if base is not None:
            placed = common_placement(run, work, base, compiler, controller, bridge, profile)
            objects, link_options, names = placed_objects(
                run, compiler, flags, profile_flag, sources, sections, placed)
        run(*flags, profile_flag, "-nostartfiles", crt, *objects, *link_options,
            ROOT / "diagnostics/chery_dtc.c", shim, bridge, controller,
            "-Wl,--gc-sections,-e,_start,--start-group", "-lc", "-lgloss", "-lgcc", "-Wl,--end-group",
            "-o", "platform.elf")
        linked = read_elf(work / "platform.elf", 2)
        if placed is not None:
            verify_placed_elf(linked, placed, names)
        else:
            release = linked["symbols"][RELEASE_SYMBOL]
            if (release["size"] != 16 or release["address"] % 4 or
                    not linked["sections"][release["section"]]["flags"] & 1):
                raise ValueError("The simulator release alias disagrees with the target RAM requirement")
        simulator = compiler.with_name(f"m32r-elf-run{compiler.suffix}")
        output = run(simulator, "--memory-size=16M", "platform.elf").stdout.strip()
        expected = "H03 target platform: native startup, CAN service lifecycle, Toyota rollover and inhibition PASS"
        if output != expected:
            raise ValueError(f"Unexpected M32R result: {output}")

        (work / "manual-profile.h").write_text(MANUAL_PROFILE, encoding="ascii")
        manual_flag = '-DRBM_H03_APPLICATION_PROFILE="manual-profile.h"'
        manual_flags = [*flags, "-DRBM_H03_TEST_MANUAL_PROFILE"]
        run(*compile_platform, manual_flag)
        manual_sections = alloc_sections(read_elf(work / "platform.o", 1))
        if any(section["flags"] & 1 for section in manual_sections):
            raise ValueError("The manual profile added writable storage to the platform object")
        manual_sources = ("lfj8_h03_input_target.c", "lfj8_h03_input_binding.c",
                          "lfj8_h03_button_capture.c", "lfj8_range_control.c")
        manual_objects = ("platform.o", *sources)
        manual_options = []
        manual_placed = None
        if base is not None:
            manual_layout = work / "manual-layout"
            manual_layout.mkdir()
            manual_placed = common_placement(
                run, manual_layout, base, compiler, controller, bridge, work / "manual-profile.h")
            manual_objects, manual_options, manual_names = placed_objects(
                run, compiler, manual_flags, manual_flag, sources, manual_sections, manual_placed)
        run(*manual_flags, manual_flag, "-nostartfiles", crt,
            *manual_objects, *(HERE / name for name in manual_sources), *manual_options,
            ROOT / "diagnostics/chery_dtc.c", shim, bridge, controller,
            "-Wl,--gc-sections,-e,_start,--start-group", "-lc", "-lgloss", "-lgcc", "-Wl,--end-group",
            "-o", "manual.elf")
        if manual_placed is not None:
            verify_placed_elf(read_elf(work / "manual.elf", 2), manual_placed, manual_names)
        manual = run(simulator, "--memory-size=16M", "manual.elf").stdout.strip()
        if manual != "H03 manual profile: native foreground, Toyota hold, MAIN S1/S2 and revocation PASS":
            raise ValueError(f"Unexpected manual profile result: {manual}")
        return {"status": "PASS", "m32r": output, "unprofiled_and_inconsistent_timing_refused": True,
                "missing_can_service_profile_refused": True,
                "manual_profile_m32r": manual,
                "manual_profile_flash_section_bytes": sum(section["size"] for section in manual_sections),
                "manual_placed_model": manual_placed,
                "flash_section_bytes": flash,
                "required_release_alias_bytes": 16, "platform_object_writable_bytes": 0,
                "placed_model": placed, "hardware_tested": False, "flashable_image": None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("gcc", "controller", "bridge", "out"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--base", type=Path, help="Also run the M32R model at the common layout's Flash and typed RAM addresses")
    args = parser.parse_args()
    inputs = [getattr(args, name).resolve() for name in ("gcc", "controller", "bridge")]
    base = args.base.resolve() if args.base else None
    if args.out.suffix.lower() != ".json" or any(args.out.resolve() == path or
            (args.out.exists() and path.exists() and args.out.samefile(path))
            for path in (*inputs, base) if path is not None):
        parser.error("Use a separate JSON report")
    try:
        report = check(*inputs, base=base)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(report["m32r"])
        print(report["manual_profile_m32r"])
    except subprocess.CalledProcessError as error:
        parser.exit(1, (error.stderr or error.stdout or str(error)) + "\n")
    except (KeyError, OSError, ValueError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
