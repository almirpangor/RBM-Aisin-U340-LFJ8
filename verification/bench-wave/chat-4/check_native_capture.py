"""Build and replay the TOY-02 capture fragment with the native M32R MMIO implementation."""

import argparse
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[3]
TARGET = ROOT / "targets/lfj8"
NEW_SOURCES = ("lfj8_h03_load_raw", "lfj8_h03_bench_input")
TEST_SOURCES = (
    "test_lfj8_h03_bench_input", "lfj8_h03_input_binding", "lfj8_h03_can_owner",
    "lfj8_h03_atf_tml0", "lfj8_h03_mmio", "lfj8_h03_button_capture",
    "lfj8_donor_io", "lfj8_selector_adc", "lfj8_range_control",
)


def run(command, cwd):
    return subprocess.check_output([str(arg) for arg in command], cwd=cwd, text=True,
                                   encoding="utf-8", errors="replace", stderr=subprocess.STDOUT, timeout=60)


def check(gcc, controller, out):
    out.mkdir(parents=True, exist_ok=True)
    flags = [gcc, "-m32r", "-mmodel=medium", "-msdata=none", "-Wa,-EB",
             "-std=c11", "-Os", "-Wall", "-Wextra", "-Werror",
             "-Wno-missing-braces", "-Wno-missing-field-initializers",
             "-ffunction-sections", "-fdata-sections"]
    for include in (TARGET, ROOT / "diagnostics", ROOT / "controller/include",
                    ROOT / "controller/vendor/toyota/include"):
        flags.extend(("-I", include))
    shim = out / "sim_crt.c"
    shim.write_text("void __init(void) {}\nvoid __fini(void) {}\n", encoding="ascii")
    objects = []
    objdump = gcc.with_name("m32r-elf-objdump" + gcc.suffix)
    sections = {}
    prologues = {}
    for name in NEW_SOURCES:
        obj = out / (name + ".o")
        run([*flags, "-c", TARGET / (name + ".c"), "-o", obj], out)
        objects.append(obj)
        table = run([objdump, "-h", obj], out)
        sections[name] = sum(int(size, 16) for size in re.findall(
            r"^\s+\d+\s+\.(?:text|rodata)(?:\.[\w.]+)?\s+([\da-f]+)", table, re.M))
        disassembly = run([objdump, "-d", obj], out)
        for name, lines in re.findall(r"^[\da-f]+ <([^>]+)>:\n((?:[ \t]+[^\n]*\n){1,8})",
                                      disassembly, re.M):
            prologues[name] = lines.rstrip().splitlines()
    # Compile the actual target caller with declarations for the other
    # domains. Only the independent replay below supplies model values.
    profile = out / "composition_probe.h"
    profile.write_text("""
#include "lfj8_h03_bench_input.h"
#include "lfj8_h03_target_service.h"
extern const Lfj8H03BenchInputProfile probe_input;
extern const Lfj8H03InputBinding probe_binding;
extern Lfj8H03InputProposal probe_proposal;
extern const Lfj8H03InputStartup probe_startup;
extern const Lfj8H03TargetServiceConfig probe_service;
int probe_initialize(void *);
#define RBM_H03_PROFILE_BENCH_INPUT probe_input
#define RBM_H03_PROFILE_BENCH_INPUT_BINDING probe_binding
#define RBM_H03_PROFILE_BENCH_INPUT_PROPOSAL probe_proposal
#define RBM_H03_PROFILE_TOYOTA_INPUT_STARTUP probe_startup
#define RBM_H03_PROFILE_TOYOTA_PERIOD_TICKS 16u
#define RBM_H03_PROFILE_TOYOTA_MAX_PERIOD_TICKS 20u
#define RBM_H03_PROFILE_TOYOTA_MAX_LATENESS_TICKS 2u
#define RBM_H03_PROFILE_CAN_SERVICE_CONFIG probe_service
#define RBM_H03_PROFILE_INITIALIZE_INPUTS probe_initialize
#include "lfj8_h03_bench_input_profile.h"
""", encoding="ascii")
    platform = out / "platform_probe.o"
    run([*flags, "-I", out, '-DRBM_H03_APPLICATION_PROFILE="composition_probe.h"',
         "-c", TARGET / "lfj8_h03_target_platform.c", "-o", platform], out)
    symbols = run([objdump, "-t", platform], out)
    for name in ("lfj8_h03_bench_input_take", "lfj8_h03_bench_input_reset_locked"):
        if not re.search(r"\*UND\*.*" + name + r"$", symbols, re.M):
            raise ValueError("Native target caller lost " + name)
    if "test_input_capture" in symbols or "test_capture_inputs" in symbols:
        raise ValueError("Fixture capture in the native target caller")
    crt = run([*flags, "-print-file-name=crt0.o"], out).strip()
    elf = out / "input-m32r.elf"
    run([*flags, "-nostartfiles", crt, *objects, *(TARGET / (name + ".c") for name in TEST_SOURCES),
         shim, controller, "-Wl,--gc-sections,-e,_start,--start-group",
         "-lc", "-lgloss", "-lgcc", "-Wl,--end-group", "-o", elf], out)
    sim = gcc.with_name("m32r-elf-run" + gcc.suffix)
    result = run([sim, "--memory-size=16M", elf], out).strip()
    if not result.endswith("TOY-02 raw Bosch and native Toyota input profile PASS"):
        raise ValueError(result)
    state, descriptor = map(int, re.search(r"state=(\d+) bytes, capture descriptor=(\d+) bytes", result).groups())
    return {"status": "PASS", "model_console": result, "unplaced_object_flash_bytes": sections,
            "owned_state_bytes": state, "capture_descriptor_bytes": descriptor,
            "native_target_caller": "references bench input take and reset",
            "stack_prologues": prologues, "hardware_tested": False, "flashable_image": None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("gcc", "controller", "out"):
        parser.add_argument("--" + key, type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    try:
        report = check(args.gcc.resolve(), args.controller.resolve(), out)
        (out / "capture.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(report["model_console"])
        print(report["unplaced_object_flash_bytes"])
    except subprocess.CalledProcessError as error:
        parser.exit(1, error.output)


if __name__ == "__main__":
    main()
