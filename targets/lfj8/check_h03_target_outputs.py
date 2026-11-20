"""Check the profiled H03 output binding against the exact OEM ROM in M32R."""

import argparse
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from check_h03_application_binding import FIXTURE_PROFILE
from check_h03_link import HERE, ROOT, identify_h03
from check_h03_native_hooks import COMMIT_SITE, OEM_COMMIT
from check_h03_range_pnp import LAYOUT, START


PROFILE = """\
extern volatile Lfj8H03PhaseClock fixture_phase_clock;
#define RBM_H03_PROFILE_OUTPUT_PHASE_CLOCK fixture_phase_clock
"""

SCENARIOS = (
    "binding and phase startup",
    "stage and OEM arbitration",
    "stock phase 2 applies D/Pressure A and produces TIO9 PWM",
    "prepare before loss of clock",
    "clock mismatch revokes the owned outputs, including TIO9/P97",
    "restoring clock registers cannot replay the rejected apply",
    "prepare before Flash monitor entry",
    "Flash monitor entry revokes outputs",
    "prepare before application shutdown",
    "application shutdown revokes outputs",
    "loss of RAM ownership suppresses OEM apply and preserves TIO9 and staged RAM",
    "a skipped phase cannot commit the older prepared generation",
    "a repeated phase 2 call revokes a consumed generation",
    "phase 2 before application startup inhibits with owned RAM",
    "phase 2 cannot consume the release used by phase 3",
    "a next release that foreground has not consumed cannot apply",
)

MODULES = (
    "h03_target_outputs_fixture.c", "lfj8_h03_application.c", "lfj8_h03_phase_startup.c",
    "lfj8_h03_phase_clock.c", "lfj8_h03_takeover.c", "lfj8_h03_outputs.c",
    "lfj8_h03_mmio.c", "lfj8_h03_atf_tml0.c", "lfj8_h03_output_inhibit.c",
    "lfj8_selector_adc.c",
    "lfj8_h03_target_commit.c", "h03_native_hooks.S",
)


COMMIT_START = START.replace('.incbin "h03.rom"', f'''\
.incbin "h03.rom", 0, {COMMIT_SITE:#x}
    bl rbm_h03_commit_hook
    .incbin "h03.rom", {COMMIT_SITE + 4:#x}''')
# The OEM caller starts one aligned word before its BL and supplies its own
# LR save and return. The simulator runs it directly at the original address.
COMMIT_LAYOUT = LAYOUT + f"""
h03_stock_commit_caller = {COMMIT_SITE - 4:#x};
h03_stock_commit = {OEM_COMMIT:#x};
h03_stock_phase2 = 0x04682c;
"""


def check(compiler, base):
    identity = identify_h03(base)
    rom = base.read_bytes()
    with TemporaryDirectory(prefix="rbm-h03-target-outputs-") as folder:
        work = Path(folder)

        def run(*args, checked=True):
            return subprocess.run([str(arg) for arg in args], cwd=work, check=checked,
                                  capture_output=True, timeout=60)

        if run(compiler, "-dumpmachine").stdout.strip() != b"m32r-elf":
            raise ValueError("A bare-metal M32R compiler is required")
        (work / "h03.rom").write_bytes(rom)
        (work / "start.S").write_text(COMMIT_START, encoding="ascii")
        (work / "layout.ld").write_text(COMMIT_LAYOUT, encoding="ascii")
        profile = work / "fixture-profile.h"
        flags = (
            "-m32r", "-msdata=none", "-Wa,-EB", "-std=c11", "-Os", "-ffreestanding",
            "-fno-builtin", "-fno-common", "-ffunction-sections", "-fdata-sections",
            "-Wall", "-Wextra", "-Werror", "-I", HERE, "-I", work,
            "-I", ROOT / "controller/include", "-I", ROOT / "controller/vendor/toyota/include",
            "-I", ROOT / "diagnostics", '-DRBM_H03_APPLICATION_PROFILE="fixture-profile.h"',
        )
        binding = HERE / "lfj8_h03_application_binding.c"
        for settings, diagnostic in (
            (PROFILE, b"both the isolation mask and owned phase clock"),
            (PROFILE + "#define RBM_H03_PROFILE_OUTPUT_ISOLATION_MASK 0x0f\n",
             b"all spare drivers isolated"),
        ):
            profile.write_text(FIXTURE_PROFILE + settings, encoding="ascii")
            invalid = run(compiler, *flags, "-c", binding, "-o", "invalid.o", checked=False)
            if invalid.returncode == 0 or diagnostic not in invalid.stderr:
                raise ValueError("The application binding did not reject an incomplete output profile")

        nm = compiler.with_name(f"m32r-elf-nm{compiler.suffix}")
        profile.write_text(FIXTURE_PROFILE, encoding="ascii")
        run(compiler, *flags, "-c", binding, "-o", "without-outputs.o")
        symbols = run(nm, "-u", "without-outputs.o").stdout.splitlines()
        if b"U rbm_h03_target_takeover_ops" not in [line.strip() for line in symbols]:
            raise ValueError("An application profile with no output approval gained a native provider")

        profile.write_text(FIXTURE_PROFILE + PROFILE +
                           "#define RBM_H03_PROFILE_OUTPUT_ISOLATION_MASK LFJ8_H03_ALL_SPARE_PWM_ISOLATED\n",
                           encoding="ascii")
        objcopy = compiler.with_name(f"m32r-elf-objcopy{compiler.suffix}")
        simulator = compiler.with_name(f"m32r-elf-run{compiler.suffix}")
        for model in ("small", "medium"):
            elf = f"outputs-{model}.elf"
            run(compiler, *flags, f"-mmodel={model}", "-nostdlib",
                "-Wl,-T,layout.ld,--gc-sections", "start.S", binding,
                *(HERE / module for module in MODULES), "-lc", "-lgcc", "-o", elf)
            run(objcopy, "-j", ".stock", "-O", "binary", elf, "linked.rom")
            linked = (work / "linked.rom").read_bytes()
            if (linked[:COMMIT_SITE] != rom[:COMMIT_SITE] or
                    linked[COMMIT_SITE + 4:] != rom[COMMIT_SITE + 4:] or
                    linked[COMMIT_SITE] != 0xfe or
                    linked[COMMIT_SITE:COMMIT_SITE + 4] == rom[COMMIT_SITE:COMMIT_SITE + 4]):
                raise ValueError(f"Only the phase 2 BL may redirect in the {model} model")
            outcome = run(simulator, "--memory-size=16M", elf, checked=False)
            if 0 < outcome.returncode <= len(SCENARIOS):
                raise ValueError(f"{model}: failed {SCENARIOS[outcome.returncode - 1]}")
            outcome.check_returncode()
    return {"status": "PASS", "base": identity, "models": ["small", "medium"],
            "scenarios": SCENARIOS, "rom_redirect": f"{COMMIT_SITE:#08x}",
            "hardware_tested": False, "flashable_image": None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("gcc", "base", "out"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    if args.out.suffix.lower() != ".json" or any(
            args.out.resolve() == path.resolve() or
            (args.out.exists() and path.exists() and args.out.samefile(path))
            for path in (args.gcc, args.base)):
        parser.error("--out must be a separate JSON report")
    try:
        result = check(args.gcc.resolve(), args.base.resolve())
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print("H03 target output binding: PASS (small, medium)")
    except subprocess.CalledProcessError as error:
        parser.exit(1, (error.stderr or error.stdout or str(error).encode()).decode(errors="replace") + "\n")
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
