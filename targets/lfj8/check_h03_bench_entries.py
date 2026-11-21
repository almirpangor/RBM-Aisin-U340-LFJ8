"""Export converted H03 entry objects and verify the linked OEM CPU paths."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

from check_h03_link import HERE, ROOT, TARGET, identify_h03
from lfj8_h03_application_placement import fixed_redirects
import lfj8_h03_bench_entry_profile as profile
from lfj8_h03_layout import alloc_sections, read_elf


def undefined(elf):
    return sorted(name for name, symbol in elf["symbols"].items() if symbol["section"] == 0)


def external_oem_entries(rom):
    """List known external entry edges from the adjoining provider modules."""
    from check_h03_can_monitor_startup import PATCHES as monitor_patches
    from check_h03_selector_adc import STORE_SITE, STOCK_WORD
    from check_h03_slt_fault import LATCHES
    from lfj8_h03_atf_fault_hook import CALL_SITE, HOOK_SYMBOL, STOCK_CALL
    import lfj8_h03_dtc_rx_placement as rx
    import lfj8_h03_sensor_hooks as sensors
    import lfj8_h03_service_placement as service
    import lfj8_h03_tx13_placement as tx13

    inventory = []

    def add(address, stock, hook, root, owner):
        if rom[address:address + 4] != bytes.fromhex(stock):
            raise ValueError(f"Unexpected H03 word for external root {hook} at {address:#08x}")
        inventory.append({"address": address, "stock_word": stock, "hook": hook, "root": root, "owner": owner})

    for address, stock, hook, _ in monitor_patches:
        add(address, f"{stock:08x}", hook, hook, "CAN-03 monitor setup and recovery")
    for address, hook, stock, _, root in rx.REDIRECTS:
        add(address, stock, hook, root, "DTC-02 resident BasicCAN RX")
    for site, root in (*service.COMMON_REDIRECTS, *zip(service.SITES, service.WRITER_ROOTS, strict=True)):
        add(site.address, f"{site.stock:08x}", site.target, root, "H03-04 reset, DMA4 and service writers")
    add(tx13.SITE, tx13.STOCK, tx13.GATE, tx13.REDIRECT, "CAN-03 TX13")
    for address, hook, stock in sensors.SENSOR_HOOKS:
        add(address, stock, hook, hook, "VSS-02/H03-02 capture and ATF")
    add(STORE_SITE, STOCK_WORD.hex(), "rbm_h03_selector_adc_hook", "rbm_h03_selector_adc_hook", "MODE-02 AN2")
    add(CALL_SITE, STOCK_CALL.hex(), HOOK_SYMBOL, HOOK_SYMBOL, "DTC-03 ATF monitor")
    for address, channel, _ in LATCHES:
        hook = f"rbm_h03_{channel}_fault_hook"
        add(address, rom[address:address + 4].hex(), hook, hook, "H03-05 output fault latches")
    return sorted(inventory, key=lambda entry: entry["address"])


def export_entries(base, compiler, out, memory_model, controller=None):
    identity = identify_h03(base)
    rom = base.read_bytes()
    if sha256(rom).hexdigest() != identity["sha256"]:
        raise ValueError("H03 changed during entry export")
    source = profile.redirect_source(rom)
    target = tuple(flag.replace("medium", memory_model) for flag in TARGET)
    c_flags = (*target, "-Os", "-std=c99", "-Wall", "-Wextra", "-Werror", "-ffreestanding",
               "-fno-builtin", "-ffunction-sections", "-fdata-sections",
               "-I", ROOT / "controller/include", "-I", ROOT / "controller/vendor/toyota/include",
               "-I", ROOT / "diagnostics")
    names = ("h03-bench-entries.o", "lfj8_h03_target_strategy.o", "h03-bench-redirects.S", "plan.json")
    paths = (base, compiler) if controller is None else (base, compiler, controller)
    if any((out / name).resolve() == path.resolve() or
           ((out / name).exists() and (out / name).samefile(path)) for name in names for path in paths):
        raise ValueError("The output paths must not overwrite input artifacts")
    out.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="rbm-h03-entries-", dir=out) as folder:
        work = Path(folder)

        def run(*args):
            return subprocess.run([str(arg) for arg in args], cwd=work, check=True,
                                  capture_output=True, timeout=120).stdout

        if run(compiler, "-dumpmachine").strip() != b"m32r-elf":
            raise ValueError("Expected the bare-metal M32R compiler")
        redirect_source = work / names[2]
        redirect_source.write_text(source, encoding="ascii", newline="\n")
        assembly_objects = []
        for path in (redirect_source, *(HERE / name for name in profile.ASSEMBLY_SOURCES)):
            obj = path.with_suffix(".o").name
            run(compiler, *target, *profile.ASSEMBLY_FLAGS.get(path.name, ()), "-c", path, "-o", obj)
            assembly_objects.append(obj)
        run(compiler, *target, "-r", "-nostdlib", "-Wl,--gc-sections",
            *(f"-Wl,--undefined={name}" for name in profile.ROOTS),
            *assembly_objects, "-o", names[0])
        run(compiler, *c_flags, *profile.NATIVE_STRATEGY_FLAGS,
            "-c", HERE / "lfj8_h03_target_strategy.c", "-o", names[1])
        hooks = read_elf(work / names[0], 1)
        strategy = read_elf(work / names[1], 1)
        sections = alloc_sections(hooks)
        fixed, wrappers = fixed_redirects(sections, redirects=profile.REDIRECTS)
        expected = set((*profile.NATIVE_CALLBACKS, *profile.STOCK_SYMBOLS, profile.INTERVAL_SYMBOL))
        if set(undefined(hooks)) != expected or any(section["flags"] & 1 for section in sections):
            raise ValueError("Unexpected external call, legacy route or writable section in the H03 entry object")
        if any(hooks["symbols"][name]["section"] == 0 for name in profile.ROOTS):
            raise ValueError("The relocatable object lost an OEM entry root")
        strategy_sections = alloc_sections(strategy)
        if (strategy["symbols"]["rbm_h03_strategy_callback"]["section"] == 0 or
                "rbm_h03_target_strategy_snapshot" not in undefined(strategy) or
                any(section["flags"] & 1 for section in strategy_sections)):
            raise ValueError("The native strategy must reference the qualified provider and own no static RAM")
        plan = {
            "base": identity, "memory_model": memory_model,
            "artifacts": {names[0]: hooks["sha256"], names[1]: strategy["sha256"],
                          names[2]: sha256(redirect_source.read_bytes()).hexdigest()},
            "roots": list(profile.ROOTS), "required_callbacks": list(profile.NATIVE_CALLBACKS),
            "redirects": [{"address": site.address, "stock_word": site.stock_word, "hook": site.hook,
                           "opcode": site.opcode >> 24, "root": site.root, "section": site.section}
                          for site in profile.REDIRECTS],
            "stock_symbols": profile.STOCK_SYMBOLS,
            "native_strategy_c_flags": list(profile.NATIVE_STRATEGY_FLAGS),
            "external_oem_entries": external_oem_entries(rom),
            "indirect_entry_constraints": [
                {"entry": ".rodata.native_owner_ops", "edges": [".text.native_rx_epoch", ".text.native_poll_owner"],
                 "rule": "Use the DTC-02 IRQ closure keep rule for the indirect epoch adapter"},
                {"entry": "lfj8_h03_mmio", "edges": ["read8", "read16", "read32", "write8", "enter", "leave"],
                 "rule": "Keep actual relocated table targets in the resident IRQ closure"},
                {"entry": "rbm_h03_application_binding", "edges": ["initialize", "ram_owned", "clock_ready",
                     "read_adaptation", "stop_service_locked", "take_toyota", "service_phase",
                     "engine.context_for_task2", "takeover_ops"],
                 "rule": "Follow relocations from the selected native profile and qualified tables"},
                {"entry": "rbm_h03_target_takeover_ops", "edges": ["write32", "clock_ticks", "qualified",
                     "arbitrate", "apply", "inhibit", "phase_clock"],
                 "rule": "Keep the selected output providers; OEM electrical routines stay in stock ROM"},
                {"entry": ["0x805000", "0x8051E8", "SBI and IRQ vector tables"],
                 "rule": "Resolve any target callbacks from runtime RAM and populated vectors before pruning"}],

            "configuration": {profile.INTERVAL_SYMBOL: {"value": None, "units": "TML0CT ticks"}},
            "verified_original_packets": [
                {"address": address, "word": word, "purpose": purpose}
                for address, (word, purpose) in profile.RETAINED_PACKETS.items()
            ],
            "fixed_branch_bytes": sum(item["bytes"] for item in fixed),
            "wrapper_flash_bytes": sum(section["size"] for section in wrappers),
            "wrapper_sections": {section["name"]: section["size"] for section in wrappers},
            "strategy_flash_bytes": sum(section["size"] for section in strategy_sections),
            "new_static_ram_bytes": 0,
            "strategy_local_stack": None,  # Live calls are measured in the CPU scenarios.
            "strategy_unresolved": undefined(strategy),
            "target_adapter_is_fixture": False,
            "hardware_tested": False,
            "flashable_image": None,
        }
        if controller is not None:
            plan["linked_cpu"] = simulate_strategy(run, work, compiler, rom, c_flags, controller)
        for name in names[:-1]:
            shutil.copyfile(work / name, out / name)
        (out / names[-1]).write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
        return plan


def simulate_strategy(run, work, compiler, rom, flags, controller):
    from check_h03_native_hooks import FULL_PHASE_LAYOUT, inspect_phase_image
    from check_h03_link import FLASH_END, FLASH_START, elf_info

    manifest = json.loads((controller.parent / "manifest.json").read_text(encoding="utf-8"))
    obj = elf_info(controller, 1)[0]
    models = [flag for flag in flags if isinstance(flag, str) and flag.startswith("-mmodel=")]
    if (manifest["architecture"] != "m32r" or manifest["sha256"].get(controller.name) != obj["sha256"] or
            [flag for flag in manifest["flags"] if flag.startswith("-mmodel=")] != models):
        raise ValueError("Unexpected controller object or provenance for the CPU fixture")
    layout = FULL_PHASE_LAYOUT.replace(
        "KEEP(*(.strategy_site))", "KEEP(*(.h03_app_redirect_036f30))").replace(
        "KEEP(*(.commit_site))", "KEEP(*(.h03_app_redirect_07c10c))")
    (work / "bench.ld").write_text(layout, encoding="ascii")
    for name, start, end in (
        ("oem-prefix", 0, FLASH_START), ("oem-before-tail", FLASH_END, profile.STRATEGY.address),
        ("oem-between", profile.STRATEGY.address + 4, profile.APPLY.address),
        ("oem-after", profile.APPLY.address + 4, len(rom)),
    ):
        (work / f"{name}.dat").write_bytes(rom[start:end])
    sources = ("lfj8_h03_target_commit.c", "lfj8_h03_cycle.c", "lfj8_h03_takeover.c",
               "lfj8_h03_outputs.c", "lfj8_h03_mmio.c")
    for name in sources:
        run(compiler, *flags, "-Wno-missing-braces", "-Wno-missing-field-initializers",
            "-ffixed-r13", "-c", HERE / name, "-o",
            "sim-" + Path(name).with_suffix(".o").name)
    simulator = compiler.with_name(f"m32r-elf-run{compiler.suffix}")
    debugger = compiler.with_name(f"m32r-elf-gdb{compiler.suffix}")
    cases = ("adjacent_release_wrap", "combined_same_release", "missing_snapshot", "unowned_ram",
             "phase_not_consumed", "monitor_after_prepare", "repeat_apply", "stale_after_restart")
    observations = {}
    for index, case in enumerate(cases):
        run(compiler, *flags, "-ffixed-r13", "-nostdlib", "-DH03_FULL_PHASE_FIXTURE",
            f"-DRBM_BENCH_STRATEGY_CASE={index}",
            "-Wno-missing-braces", "-Wno-missing-field-initializers",
            "-Wl,-T,bench.ld,--gc-sections", HERE / "h03_native_hooks_fixture.S",
            HERE / "h03_bench_strategy_fixture.c", "h03-bench-entries.o",
            "lfj8_h03_target_strategy.o", *("sim-" + Path(name).with_suffix(".o").name for name in sources),
            controller, "-Wl,--start-group", "-lc", "-lgcc", "-Wl,--end-group", "-o", "bench.elf")
        inspected = inspect_phase_image(run, work, compiler, rom, "bench.elf")
        try:
            run(simulator, "--memory-size", "16M", "bench.elf")
        except subprocess.CalledProcessError as error:
            raise ValueError(f"Native strategy CPU case {case} returned {error.returncode}") from error
        debugger_log = run(debugger, "--batch", "-nx", "-ex", "target sim --memory-size 16M",
                           "-ex", "load", "-ex", "break *h03_phase_fixture_exit", "-ex", "run",
                           "-ex", 'printf "RETURN %08x %08x\\n", $sp, $r0',
                           "-ex", "dump binary memory stack.dat 0x9fc000 0x9ffffc", "bench.elf")
        stack = (work / "stack.dat").read_bytes()
        pattern = bytes.fromhex("a55a6996")
        if (b"RETURN 009ffffc 00000000" not in debugger_log or len(stack) != 0x3FFC or
                stack[:4] != pattern):
            raise ValueError(f"Unbalanced stack or guard damage in native case {case}")
        used = next((len(stack) - offset for offset in range(4, len(stack), 4)
                     if stack[offset:offset + 4] != pattern), 0)
        observations[case] = {"stack_bytes_without_irq": used, "stock_overlay": inspected}
    return {"controller_sha256": obj["sha256"], "cases": observations, "fixture_inputs_only": True,
            "native_strategy_and_commit_callbacks": True, "hardware_tested": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("base", "gcc", "out"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--memory-model", choices=("small", "medium"), default="medium")
    parser.add_argument("--controller", type=Path, help="Also run the linked CPU scenarios with the M32R fixture")
    args = parser.parse_args()
    try:
        result = export_entries(args.base.resolve(), args.gcc.resolve(), args.out.resolve(),
                                args.memory_model, args.controller.resolve() if args.controller else None)
    except subprocess.CalledProcessError as error:
        parser.exit(1, (error.stderr or error.stdout or str(error).encode()).decode(errors="replace") + "\n")
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"{error}\n")
    print(f'{len(result["roots"])} H03 roots, {result["fixed_branch_bytes"]} fixed bytes, '
          f'{result["wrapper_flash_bytes"]} wrapper bytes, {result["strategy_flash_bytes"]} strategy bytes')


if __name__ == "__main__":
    main()
