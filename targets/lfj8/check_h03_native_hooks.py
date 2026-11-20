"""Verify H03 dispatch hooks with the OEM routine bytes and GNU M32R simulator."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
import subprocess
from tempfile import TemporaryDirectory

from check_h03_link import identify_h03


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
STRATEGY_SITE = 0x036F30
COMMIT_SITE = 0x07C10C
OEM_STRATEGY = 0x06FED4
OEM_ARBITER = 0x0717B8
OEM_COMMIT = 0x046900
LAYOUT = """
ENTRY(_start)
SECTIONS {
  .oem_before 0x000000 : { KEEP(*(.oem_before)) }
  .strategy_site 0x036f30 : { KEEP(*(.strategy_site)) }
  .oem_between 0x036f34 : { KEEP(*(.oem_between)) }
  .commit_site 0x07c10c : { KEEP(*(.commit_site)) }
  .oem_after 0x07c110 : { KEEP(*(.oem_after)) }
  .fixture_start 0x100000 : { *(.fixture_start) }
  .text : { *(.text*) *(.rodata*) }
  .data : { *(.data*) }
  .bss (NOLOAD) : { *(.bss*) *(COMMON) }
  /DISCARD/ : { *(.note*) *(.comment) }
  h03_stock_strategy = 0x06fed4;
  h03_stock_arbiter = 0x0717b8;
  h03_stock_commit = 0x046900;
  h03_stock_phase3 = 0x046804;
  h03_stock_phase2 = 0x04682c;
  h03_stock_combined = 0x036ea4;
}
"""


def print_state(label):
    registers = [f"$r{i}" for i in range(13)] + ["$fp", "$lr", "$sp", "$psw", "$accl", "$acch"]
    values = ["$pc", *registers, "fixture_strategy_calls", "fixture_commit_calls",
              "*(unsigned char*)0x8063d7", "*(unsigned char*)0x8063da", "*(unsigned char*)0x8063dd",
              "*(unsigned int*)0x805094", "*(unsigned char*)0x800703"]
    return f'printf "{label} {"%08x " * len(values)}\\n", {", ".join(values)}\n'


def simulate(run, work, gdb, site, decision, image):
    continuation = site + 4
    (work / "check.gdb").write_text(
        "set confirm off\n"
        "target sim --memory-size 16M\n"
        "load\n"
        "tbreak *fixture_ready\n"
        "run\n"
        + print_state("HOOK_READY")
        + f"set variable fixture_decision = {decision}\n"
        + f"set variable fixture_commit_site = {int(site == COMMIT_SITE)}\n"
        + "".join(f"tbreak *{address:#x}\n" for address in (continuation, OEM_STRATEGY, OEM_ARBITER, OEM_COMMIT))
        + "continue\n"
        + print_state("HOOK_ENTRY")
        + f"if $pc != {continuation:#x}\n"
        + "delete breakpoints\n"
        + f"tbreak *{continuation:#x}\n"
        + "continue\nend\n"
        + print_state("HOOK_RETURN"),
        encoding="ascii",
    )
    log = run(gdb, "--batch", "-nx", "-x", "check.gdb", image).replace(b"\r", b"")
    states = []
    for label in (b"HOOK_READY", b"HOOK_ENTRY", b"HOOK_RETURN"):
        state = re.search(rb"^" + label + rb" ((?:[0-9a-f]{8} ){27})$", log, re.M)
        if state is None:
            raise ValueError(f"Missing simulated state at {site:#x}: {log[-1500:].decode(errors='replace')}")
        states.append(tuple(int(value, 16) for value in state[1].split()))
    return states


def check_full_phases(run, work, compiler, simulator, gdb, flags):
    sources = (
        "h03_full_phase_fixture.c", "lfj8_h03_takeover.c", "lfj8_h03_outputs.c",
        "lfj8_h03_mmio.c",
    )
    for name in (*sources, *(header.name for header in HERE.glob("*.h"))):
        shutil.copyfile(HERE / name, work / name)
    controller = ROOT / "controller"
    vendor = controller / "vendor/toyota"
    shutil.copytree(controller / "include", work / "controller")
    shutil.copytree(vendor / "include", work / "toyota")
    donor_sources = ("factory_core.c", "factory_outputs.c", "factory_correction.c", "factory_phase_modes.c")
    for name in (*donor_sources, "donor_calibration.h"):
        shutil.copyfile(vendor / "src" / name, work / name)
    shutil.copyfile(controller / "src/rbm_u340e.c", work / "rbm_u340e.c")

    cases = {
        "fresh_across_clock_wrap": "SCENARIO_NORMAL",
        "expired_at_commit": "SCENARIO_TIMEOUT",
        "pressure_fault_after_prepare": "SCENARIO_LATE_FAULT",
        "final_byte_changed_after_prepare": "SCENARIO_FINAL_CHANGED",
        "external_authority_lost": "SCENARIO_AUTHORITY_LOST",
        "repeat_commit": "SCENARIO_REPEAT",
        "startup_cutout": "SCENARIO_STARTUP_SKIP",
        "stock_combined_entry": "SCENARIO_COMBINED_ENTRY",
        "p3_changed_after_prepare": "SCENARIO_P3_CHANGED",
        "missing_pressure_calibration": "SCENARIO_NO_CALIBRATION",
        "unrepresentable_real_edge_order": "SCENARIO_WRONG_ORDER",
    }
    stack_used = {}
    for label, scenario in cases.items():
        run(compiler, *flags, "-std=c11", "-Icontroller", "-Itoyota", "-ffixed-r13", "-DH03_FULL_PHASE_FIXTURE",
            "-Wno-missing-braces", "-Wno-missing-field-initializers",
            f"-DH03_PHASE_SCENARIO={scenario}", "-Wl,-T,fixture.ld", "h03_native_hooks.S",
            "h03_native_hooks_fixture.S", *sources, "rbm_u340e.c", *donor_sources,
            "-ffunction-sections",
            "-fdata-sections", "-Wl,--gc-sections,--undefined=rbm_h03_strategy_hook",
            "-Wl,--undefined=rbm_h03_commit_hook", "-Wl,--start-group", "-lc", "-lgcc",
            "-Wl,--end-group", "-o", "full-phase.elf")
        try:
            run(simulator, "--memory-size", "16M", "full-phase.elf")
        except subprocess.CalledProcessError as error:
            failure = run(
                gdb, "--batch", "-nx", "-ex", "target sim --memory-size 16M", "-ex", "load",
                "-ex", "break *h03_phase_fixture_exit", "-ex", "run",
                "-ex", "x/2hu 0x800344", "-ex", "x/1xb 0x80074a",
                "full-phase.elf",
            ).decode(errors="replace")
            raise ValueError(f"H03 scenario {label} failed, exit code {error.returncode}\n{failure}") from error
        gdb_log = run(
            gdb, "--batch", "-nx", "-ex", "target sim --memory-size 16M", "-ex", "load",
            "-ex", "break *h03_phase_fixture_exit", "-ex", "run",
            "-ex", 'printf "PHASE_RETURN %08x %08x\n", $sp, $r0',
            "-ex", "dump binary memory stack.dat 0x9fc000 0x9ffffc",
            "full-phase.elf",
        )
        if b"PHASE_RETURN 009ffffc 00000000" not in gdb_log:
            raise ValueError(f"Incorrect stack pointer or result after scenario {label}: {gdb_log[-1000:]!r}")
        stack = (work / "stack.dat").read_bytes()
        pattern = bytes.fromhex("a55a6996")
        if len(stack) != 0x3FFC or stack[:4] != pattern:
            raise ValueError(f"Stack fixture guard was lost in {label}")
        first_write = next((offset for offset in range(4, len(stack), 4)
                            if stack[offset:offset + 4] != pattern), len(stack))
        stack_used[label] = len(stack) - first_write
    return {"cases": list(cases), "fixture_state_outside_h03_ram": True,
            "observed_stack_bytes": stack_used,
            "toyota_output_algorithms_executed": True,
            "toyota_fixture_raw_slt": 5120,
            "toyota_expected_compare": 652,
            "slt_calibration": "synthetic fixture points",
            "physical_inhibit_tested": False,
            "stock_entries": ["0x046804", "0x04682C", "0x036EA4"],
            "address_space": "GNU M32R test ELF with registers backed by simulator memory"}


def check(base, compiler):
    identity = identify_h03(base)
    rom = base.read_bytes()
    if sha256(rom).hexdigest() != identity["sha256"]:
        raise ValueError("H03 changed while the fixture was being prepared")
    sites = (
        ("strategy", STRATEGY_SITE, OEM_STRATEGY, bytes.fromhex("fe00eb5c")),
        ("commit", COMMIT_SITE, OEM_COMMIT, bytes.fromhex("2eef1fce")),
    )
    for _, site, destination, continuation in sites:
        packet = rom[site:site + 4]
        target = site + 4 * int.from_bytes(packet[1:], "big", signed=True)
        if packet[0] != 0xFE or target != destination or rom[site + 4:site + 8] != continuation:
            raise ValueError(f"Unexpected H03 BL or continuation at {site:#x}")

    cases = []
    with TemporaryDirectory(prefix="rbm-h03-native-hooks-") as directory:
        work = Path(directory)

        def run(*args):
            return subprocess.run([str(arg) for arg in args], cwd=work, check=True,
                                  capture_output=True, timeout=30).stdout

        if run(compiler, "-dumpmachine").strip() != b"m32r-elf":
            raise ValueError("A bare-metal M32R compiler is required")
        gdb = compiler.with_name(f"m32r-elf-gdb{compiler.suffix}")
        objdump = compiler.with_name(f"m32r-elf-objdump{compiler.suffix}")
        simulator = compiler.with_name(f"m32r-elf-run{compiler.suffix}")
        (work / "fixture.ld").write_text(LAYOUT, encoding="ascii")
        for name in ("h03_native_hooks.S", "h03_native_hooks.h", "h03_native_hooks_fixture.S",
                     "h03_native_hooks_fixture.c"):
            shutil.copyfile(HERE / name, work / name)
        regions = (
            ("oem-before", 0, STRATEGY_SITE),
            ("strategy-site", STRATEGY_SITE, STRATEGY_SITE + 4),
            ("oem-between", STRATEGY_SITE + 4, COMMIT_SITE),
            ("commit-site", COMMIT_SITE, COMMIT_SITE + 4),
            ("oem-after", COMMIT_SITE + 4, len(rom)),
        )
        for name, start, end in regions:
            (work / f"{name}.dat").write_bytes(rom[start:end])

        flags = ["-m32r", "-Wa,-EB", "-mmodel=medium", "-msdata=none", "-Os", "-g", "-nostdlib",
                 "-ffreestanding", "-Wall", "-Wextra", "-Werror", "-Wundef"]
        run(compiler, *flags, "-c", "h03_native_hooks.S", "-o", "hooks.o")
        listing = run(objdump, "-d", "-r", "hooks.o").decode()
        if ("h03_stock_strategy" in listing or listing.count("mvfachi r0") != 2 or
                listing.count("mvtachi r0") != 4):
            raise ValueError("Unexpected default fallback or ACC high instruction coverage")

        for carry in (0, 1):
            run(compiler, *flags, f"-DFIXTURE_CONTEXT_CARRY={carry}", "-Wl,-Ttext,0x100000",
                "h03_native_hooks.S", "h03_native_hooks_fixture.S", "-o", "context.elf")
            try:
                run(simulator, "--memory-size", "16M", "context.elf")
            except subprocess.CalledProcessError as error:
                raise ValueError(f"PSW changed around no-dispatch callback with carry={carry}") from error

        baseline = {}
        for variant, options, decisions in (
            ("stock", ["-DFIXTURE_STOCK"], (0,)),
            ("takeover", [], (-1, 0, 1, 2)),
            ("legacy_bench", ["-DRBM_H03_ALLOW_LEGACY_BENCH=1"], (0, 1, 2)),
        ):
            image = f"{variant}.elf"
            run(compiler, *flags, *options, "-Wl,-T,fixture.ld", "h03_native_hooks.S",
                "h03_native_hooks_fixture.S", "h03_native_hooks_fixture.c", "-o", image)
            for name, site, old_destination, _ in sites:
                for decision in decisions:
                    ready, entry, returning = simulate(run, work, gdb, site, decision, image)
                    destination = site + 4
                    if variant == "stock" or variant == "legacy_bench" and decision == 0:
                        destination = old_destination
                    elif decision == 1:
                        destination = OEM_ARBITER if name == "strategy" else OEM_COMMIT
                    expected_entry = (*ready[1:15], site + 4, ready[16], ready[18])
                    expected_calls = ((1, 0) if name == "strategy" else (0, 1)) if variant != "stock" else (0, 0)
                    if (entry[0] != destination or (*entry[1:17], entry[18]) != expected_entry or
                            entry[20:22] != expected_calls or entry[19] != ready[19]):
                        raise ValueError(f"Changed CPU context or dispatch from {site:#x} in {variant} {decision}")
                    if returning[0] != site + 4 or returning[16] != ready[16]:
                        raise ValueError(f"Unbalanced stack or wrong return at {site:#x} in {variant} {decision}")
                    if variant == "stock":
                        baseline[site] = (*returning[1:20], *returning[22:])
                    elif (variant == "legacy_bench" and decision == 0) or (name == "commit" and decision == 1):
                        if (*returning[1:20], *returning[22:]) != baseline[site]:
                            raise ValueError(f"Changed OEM return behavior from {site:#x}")
                    if name == "strategy" and decision == 1 and returning[22:26] != (1, 0, 1, 0x3F000000):
                        raise ValueError("The original electrical arbiter did not apply test proposals")
                    if destination == site + 4 and returning[22:] != ready[22:]:
                        raise ValueError(f"Rejected command changed actuator state from {site:#x}")
                    cases.append({"variant": variant, "hook": name, "decision": decision,
                                  "dispatch": f"0x{destination:06X}", "return": f"0x{site + 4:06X}"})

        phase_program = check_full_phases(run, work, compiler, simulator, gdb, flags)

    return {
        "base": identity,
        "phase_program_with_takeover": phase_program,
        "cases": cases,
        "wrapper_frame_bytes": 72,
        "psw_preserved_in_non_debugger_probes_with_carry": [0, 1],
        "acc_low_observed": True,
        "acc_high_save_restore_present": True,
        "acc_high_nonzero_verified": False,
        "real_hardware_executed": False,
        "interrupt_stack_verified": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--gcc", required=True, type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    try:
        if args.out and (args.out.resolve() == args.base.resolve() or
                         (args.out.exists() and args.out.samefile(args.base))):
            raise ValueError("The report and the H03 base must use different files")
        report = json.dumps(check(args.base, args.gcc.resolve()), indent=2) + "\n"
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(report, encoding="utf-8")
        print(report, end="")
    except subprocess.CalledProcessError as error:
        message = error.stderr or error.stdout or str(error).encode()
        parser.exit(1, message.decode(errors="replace") + "\n")
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
