"""Exercise the native inhibited-output profile at both exact H03 call sites."""

import argparse
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from check_h03_link import HERE, ROOT, identify_h03
from check_h03_native_hooks import COMMIT_SITE, STRATEGY_SITE
from check_h03_range_pnp import LAYOUT, START


MODULES = (
    "h03_bench_outputs_fixture.c", "lfj8_h03_bench_outputs.c",
    "lfj8_h03_application.c", "lfj8_h03_phase_startup.c", "lfj8_h03_phase_clock.c",
    "lfj8_h03_takeover.c", "lfj8_h03_outputs.c", "lfj8_h03_output_inhibit.c",
    "lfj8_h03_mmio.c", "lfj8_h03_target_commit.c", "h03_native_hooks.S",
)
SCENARIOS = (
    "read-only snapshot refuses access before startup",
    "native profile starts phase clock with no actuator authority or isolation claims",
    "first native release remains consumable",
    "commissioning snapshot reports ADC count, timers, mux, latch and feedback bits",
    "valid-looking output generation is refused and all five target paths revoked",
    "phase 3 redirects OEM strategy and revokes owned outputs",
    "second native release remains consumable",
    "phase 2 redirects OEM apply and leaves application and CAN service running",
    "loss of ownership suppresses OEM commands without touching state or outputs",
)

ROM = START.replace('.incbin "h03.rom"', f'''\
.incbin "h03.rom", 0, {STRATEGY_SITE:#x}
    bl rbm_h03_strategy_hook
    .incbin "h03.rom", {STRATEGY_SITE + 4:#x}, {COMMIT_SITE - STRATEGY_SITE - 4:#x}
    bl rbm_h03_commit_hook
    .incbin "h03.rom", {COMMIT_SITE + 4:#x}''')
LINK = LAYOUT + """\
h03_stock_arbiter = 0x0717b8;
h03_stock_commit = 0x046900;
h03_stock_phase3 = 0x046804;
h03_stock_phase2 = 0x04682c;
rbm_h03_strategy_callback = rbm_h03_commit_callback;
"""


def check(compiler, base):
    identity = identify_h03(base)
    rom = base.read_bytes()
    with TemporaryDirectory(prefix="rbm-h03-bench-outputs-") as folder:
        work = Path(folder)

        def run(*args, checked=True):
            return subprocess.run([str(arg) for arg in args], cwd=work,
                                  check=checked, capture_output=True, timeout=60)

        if run(compiler, "-dumpmachine").stdout.strip() != b"m32r-elf":
            raise ValueError("A bare-metal M32R compiler is required")
        (work / "h03.rom").write_bytes(rom)
        (work / "start.S").write_text(ROM, encoding="ascii")
        (work / "layout.ld").write_text(LINK, encoding="ascii")
        objcopy = compiler.with_name(f"m32r-elf-objcopy{compiler.suffix}")
        simulator = compiler.with_name(f"m32r-elf-run{compiler.suffix}")
        for model in ("small", "medium"):
            elf = f"bench-{model}.elf"
            run(compiler, "-m32r", f"-mmodel={model}", "-msdata=none", "-Wa,-EB",
                "-std=c11", "-Os", "-ffreestanding", "-fno-builtin", "-fno-common",
                "-ffunction-sections", "-fdata-sections", "-Wall", "-Wextra", "-Werror",
                "-I", HERE, "-I", ROOT / "controller/include",
                "-I", ROOT / "controller/vendor/toyota/include", "-I", ROOT / "diagnostics",
                "-nostdlib", "-Wl,-T,layout.ld,--gc-sections", "start.S",
                *(HERE / module for module in MODULES), "-lc", "-lgcc", "-o", elf)
            run(objcopy, "-j", ".stock", "-O", "binary", elf, "linked.rom")
            linked = (work / "linked.rom").read_bytes()
            for site in (STRATEGY_SITE, COMMIT_SITE):
                if linked[site:site + 4] == rom[site:site + 4]:
                    raise ValueError(f"{model}: unchanged redirect at {site:#x}")
            restored = bytearray(linked)
            for site in (STRATEGY_SITE, COMMIT_SITE):
                restored[site:site + 4] = rom[site:site + 4]
            if restored != rom:
                raise ValueError(f"{model}: OEM bytes outside the redirects changed")
            outcome = run(simulator, "--memory-size=16M", elf, checked=False)
            if 0 < outcome.returncode <= len(SCENARIOS):
                raise ValueError(f"{model}: {SCENARIOS[outcome.returncode - 1]}")
            outcome.check_returncode()
    return {"status": "PASS", "base": identity, "models": ["small", "medium"],
            "scenarios": SCENARIOS, "hardware_tested": False}


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
        print("H03 native bench outputs: PASS (small, medium)")
    except subprocess.CalledProcessError as error:
        parser.exit(1, (error.stderr or error.stdout or str(error).encode()).decode(errors="replace") + "\n")
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
