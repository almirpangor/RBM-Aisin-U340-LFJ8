"""Measure the vendored Toyota runtime's observed stack writes on M32R SPU."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory

from check_h03_link import HERE, ROOT, TARGET, elf_info, identify_h03


FUNCTIONS = (
    "factory_hydraulics_control_main",
    "rbm_u340e_runtime_main_range",
    "rbm_u340e_runtime_gears_outputs",
    "rbm_u340e_range_fast",
    "rbm_u340e_runtime_main_range_complete",
    "rbm_u340e_hydraulics_control_main_workspace",
)
CYCLE_FUNCTION = "lfj8_h03_cycle_tick"


def parse_observed(raw, names):
    rows = re.findall(r"^stack ([0-9]+) ([0-9]+) ([0-9]+)$", raw, re.M)
    if len(rows) != len(names) or [int(row[0]) for row in rows] != list(range(len(names))):
        raise ValueError(f"Incomplete stack probe: {raw}")
    return {name: {"calls": int(calls), "high_water_bytes_written": int(depth)}
            for name, (_, calls, depth) in zip(names, rows)}


def check(base, compiler, controller):
    identity = identify_h03(base)
    controller_hash = elf_info(controller, 1)[0]["sha256"]
    manifest = json.loads((controller.parent / "manifest.json").read_bytes())
    if manifest["architecture"] != "m32r" or manifest["sha256"].get(controller.name) != controller_hash:
        raise ValueError("The controller does not match its M32R build manifest")
    with TemporaryDirectory(prefix="rbm-h03-toyota-stack-") as directory:
        stage = Path(directory)
        shutil.copytree(ROOT / "controller/include", stage / "controller")
        shutil.copytree(ROOT / "controller/vendor/toyota/include", stage / "toyota")
        inputs = (ROOT / "controller/tests/test_runtime.c",
                  HERE / "h03_toyota_stack_fixture.c", HERE / "h03_toyota_stack_fixture.S")
        cycle_sources = tuple(HERE / f"{name}.c" for name in
                              ("test_lfj8_h03_cycle", "lfj8_h03_cycle", "lfj8_h03_torque", "lfj8_h03_slu",
                               "lfj8_h03_takeover", "lfj8_h03_phase_clock", "lfj8_h03_outputs"))
        cycle_headers = tuple(HERE / f"{name}.h" for name in
                              ("lfj8_h03_cycle", "lfj8_h03_torque", "lfj8_h03_takeover", "lfj8_h03_slu",
                               "lfj8_h03_phase_clock", "lfj8_h03_outputs", "lfj8_donor_io"))
        for source in (*inputs, *cycle_sources, *cycle_headers, controller):
            shutil.copyfile(source, stage / source.name)

        def run(*args):
            return subprocess.run([str(arg) for arg in args], cwd=stage, check=True,
                                  capture_output=True, text=True, timeout=60).stdout.strip()

        if run(compiler, "-dumpmachine") != "m32r-elf":
            raise ValueError("A bare-metal M32R compiler is required")
        startup = run(compiler, *TARGET, "-print-file-name=crt0.o")
        flags = [*TARGET, "-Os", "-std=c11", "-Wall", "-Wextra", "-Werror",
                 "-Wno-missing-braces", "-Wno-missing-field-initializers", "-Icontroller", "-Itoyota"]
        run(compiler, *flags, "-DRBM_TEST_QUIET",
            "-Dfactory_hydraulics_control_main=h03_stack_probe_compare_main",
            "-c", inputs[0].name, "-o", "runtime_test.o")
        run(compiler, *flags, "-nostartfiles", startup, "runtime_test.o",
            *(path.name for path in inputs[1:]), controller.name,
            *(f"-Wl,--wrap={symbol}" for symbol in FUNCTIONS),
            "-Wl,-e,_start,--start-group", "-lc", "-lgloss", "-lgcc", "-Wl,--end-group", "-o", "probe.elf")
        elf_info(stage / "probe.elf", 2)
        simulator = compiler.with_name(f"m32r-elf-run{compiler.suffix}")
        raw = run(simulator, "probe.elf")
        observed = parse_observed(raw, FUNCTIONS)
        layout = re.search(r"^layout ([0-9]+) ([0-9]+) ([0-9]+)$", raw, re.M)
        if layout is None:
            raise ValueError(f"Missing workspace layout: {raw}")
        gear_bytes, transaction_bytes, workspace_bytes = map(int, layout.groups())
        main = observed["factory_hydraulics_control_main"]["high_water_bytes_written"]
        workspace = observed["rbm_u340e_hydraulics_control_main_workspace"]["high_water_bytes_written"]
        comparisons = observed["factory_hydraulics_control_main"]["calls"]
        if observed["rbm_u340e_hydraulics_control_main_workspace"]["calls"] != comparisons + 2:
            raise ValueError("One of the workspace guard tests did not enter the measured function")
        run(compiler, *flags, "-Dmain=h03_stack_probe_cycle_test",
            "-c", cycle_sources[0].name, "-o", "cycle_test.o")
        run(compiler, *flags, "-DH03_PROBE_CYCLE_ONLY", "-nostartfiles", startup, "cycle_test.o",
            *(path.name for path in (*inputs[1:], *cycle_sources[1:])), controller.name,
            f"-Wl,--wrap={CYCLE_FUNCTION}",
            "-Wl,-e,_start,--start-group", "-lc", "-lgloss", "-lgcc", "-Wl,--end-group", "-o", "cycle_probe.elf")
        elf_info(stage / "cycle_probe.elf", 2)
        cycle_raw = run(simulator, "cycle_probe.elf")
        observed.update(parse_observed(cycle_raw, (CYCLE_FUNCTION,)))
        cycle_layout = re.search(r"^cycle_layout ([0-9]+) ([0-9]+) ([0-9]+) ([0-9]+)$", cycle_raw, re.M)
        if cycle_layout is None:
            raise ValueError(f"Missing cycle layout: {cycle_raw}")
        cycle_state, cycle_work, cycle_in, cycle_out = map(int, cycle_layout.groups())
        if cycle_work != workspace_bytes:
            raise ValueError("The cycle workspace and checked union layouts differ")

    # Existing H03 assembly wrappers and the independently audited maximum
    # for the H03 interrupt models. Neither term is simulated in this probe.
    stock_and_hook = 36 + 72
    stock_irq_and_sbi = 824
    primary_window = 0x809EFC - 0x809700
    subtotal = main + stock_and_hook + stock_irq_and_sbi
    workspace_subtotal = workspace + stock_and_hook + stock_irq_and_sbi
    cycle_subtotal = observed[CYCLE_FUNCTION]["high_water_bytes_written"] + stock_and_hook + stock_irq_and_sbi
    return {
        "base": identity,
        "status": "PASS_SIMULATOR_ONLY",
        "controller_sha256": controller_hash,
        "fixture_source_sha256": {src.name: sha256(src.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
                                  for src in (*inputs, *cycle_sources, *cycle_headers)},
        "observed": observed,
        "simulator_probe_stack_bytes": 4096,
        "guard_bytes_each": 32,
        "returned_with_both_stack_pointers_restored": True,
        "bytewise_hydraulic_gp_equivalence_cases": comparisons,
        "workspace": {
            "gear_bytes": gear_bytes,
            "transaction_bytes": transaction_bytes,
            "union_bytes": workspace_bytes,
            "stack_bytes_saved_observed": main - workspace,
            "late_torque_failure_left_active_gp_unchanged": True,
        },
        "cycle_abi_bytes": {
            "persistent_state": cycle_state, "workspace": cycle_work, "input": cycle_in, "result": cycle_out,
        },
        "existing_system_stack_hypothesis": {
            "window_bytes": primary_window,
            "observed_main_high_water_bytes": main,
            "oem_frames_and_hook_bytes": stock_and_hook,
            "independent_irq_and_sbi_model_bytes": stock_irq_and_sbi,
            "subtotal_before_adapter_bytes": subtotal,
            "margin_before_adapter_bytes": primary_window - subtotal,
            "workspace_subtotal_before_adapter_bytes": workspace_subtotal,
            "workspace_margin_before_adapter_bytes": primary_window - workspace_subtotal,
            "full_simulated_cycle_subtotal_before_adapter_bytes": cycle_subtotal,
            "full_simulated_cycle_margin_before_adapter_bytes": primary_window - cycle_subtotal,
        },
        "full_irq_model_executed": False,
        "target_stack_budget_verified": False,
        "target_ram_ownership_verified": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("base", "gcc", "controller"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    try:
        if args.out and args.out.resolve() in {args.base.resolve(), args.controller.resolve()}:
            raise ValueError("The stack report must be written to a separate file")
        report = json.dumps(check(args.base.resolve(), args.gcc.resolve(), args.controller.resolve()), indent=2) + "\n"
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(report, encoding="utf-8")
        print(report, end="")
    except subprocess.CalledProcessError as error:
        parser.exit(1, (error.stderr or error.stdout or str(error)) + "\n")
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
