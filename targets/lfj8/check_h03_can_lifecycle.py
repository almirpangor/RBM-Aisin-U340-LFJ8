"""Exercise H03 CAN0 setup and continuation instructions in an isolated M32R simulator."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import struct
import subprocess
from tempfile import TemporaryDirectory

from check_h03_link import identify_h03


HERE = Path(__file__).resolve().parent
OEM_ENTRY = 0x00BAF4
TEST_SP = 0x9FFFFC
ROM_FRAGMENTS = (
    ("guards", ".oem_guards", 0x003E50, 0x003E78),
    ("select", ".oem_select", 0x008324, 0x008408),
    ("config", ".oem_config", OEM_ENTRY, 0x00BD5C),
    ("variant", ".oem_variant", 0x01652A, 0x01652B),
    ("config-mask", ".oem_config_mask", 0x0310C4, 0x0310C6),
    ("slot-tables", ".oem_slot_tables", 0x032628, 0x032768),
    ("rx-table", ".oem_rx_table", 0x032EC4, 0x032F74),
)
FIXTURE_SECTIONS = (
    (".test_start", 0x1000),
    (".mock_8a04", 0x008A04),
    (".mock_b800", 0x00B800),
    (".mock_bad4", 0x00BAD4),
    (".test_code", 0x060000),
    (".text.h03_can0_setup_hook", 0x060800),
    (".test_data", 0x100000),
)


def check(base, compiler):
    identity = identify_h03(base)
    rom = base.read_bytes()
    if sha256(rom).hexdigest() != identity["sha256"]:
        raise ValueError("H03 changed while the fixture was being prepared")
    with TemporaryDirectory(prefix="rbm-h03-can-lifecycle-") as directory:
        work = Path(directory)
        shutil.copyfile(HERE / "h03_can_lifecycle_test.S", work / "fixture.S")
        shutil.copyfile(HERE / "h03_can0_setup_hook.S", work / "setup_hook.S")
        for name, _, start, end in ROM_FRAGMENTS:
            (work / f"{name}.dat").write_bytes(rom[start:end])

        def run(*args):
            return subprocess.run([str(arg) for arg in args], cwd=work, check=True,
                                  capture_output=True, timeout=15).stdout

        if run(compiler, "-dumpmachine").strip() != b"m32r-elf":
            raise ValueError("A bare-metal M32R compiler is required")
        version = run(compiler, "--version").decode().splitlines()[0]
        simulator = compiler.with_name(f"m32r-elf-run{compiler.suffix}")
        results = []
        for path, site, tail_end, initial, status, expected, mask, slot13 in (
            ("startup", 0x00B7D0, 0x00B800, 0, 0, 6, 0x8007, 0),
            ("recovery_in_reset", 0x00B878, 0x00B8CC, 3, 0x0100, 4, 0x8003, 0x80),
            ("recovery_reset_released", 0x00B878, 0x00B8CC, 3, 0, 7, 0x8003, 0x40),
            ("recovery_bus_off_in_shadow", 0x00B878, 0x00B8CC, 3, 0x4000, 7, 0x8003, 0x81),
        ):
            original_call = rom[site:site + 4]
            target = site + 4 * int.from_bytes(original_call[1:], "big", signed=True)
            if original_call[0] != 0xFE or target != OEM_ENTRY:
                raise ValueError(f"Expected original wide BL at {site:#x}")
            (work / "call.dat").write_bytes(original_call)
            (work / "tail.dat").write_bytes(rom[site + 4:tail_end])
            placements = [*FIXTURE_SECTIONS, (".test_site", site)]
            placements.extend((section, start) for _, section, start, _ in ROM_FRAGMENTS)
            sections = "\n".join(f"  {section} {address:#x} : {{ *({section}) }}"
                                 for section, address in sorted(placements, key=lambda item: item[1]))
            (work / "test.ld").write_text(
                f"ENTRY(_start)\nSECTIONS {{\n{sections}\n"
                "  /DISCARD/ : { *(.note*) *(.comment) }\n}\n",
                encoding="ascii",
            )

            generation_seed = -1 if status == 0x4000 else 17
            old_generation = generation_seed & 0xFFFFFFFF
            new_generation = (old_generation + 1) & 0xFFFFFFFF
            for tail in (0, 1):
                variants = []
                for wrapped in (0, 1):
                    run(compiler, "-m32r", "-Wa,-EB", "-nostdlib", "-Wl,-T,test.ld",
                        f"-DTEST_STATE={initial}", f"-DTEST_STATUS={status}",
                        f"-DTEST_MASK={mask}", f"-DTEST_SLOT13={slot13}",
                        f"-DRUN_TAIL={tail}", f"-DWRAPPED={wrapped}", f"-DTEST_GENERATION={generation_seed}",
                        "fixture.S", "setup_hook.S", "-o", "sim.elf")
                    stdout = run(simulator, "--memory-size", "16M", "sim.elf")
                    if len(stdout) != 344:
                        raise ValueError(f"Incomplete snapshot for {path}: {len(stdout)} bytes")
                    variants.append(struct.unpack(">43I", bytes.fromhex(stdout.decode("ascii"))))
                stock, wrapped = variants
                if stock[:24] != wrapped[:24]:
                    raise ValueError(f"Wrapper changed OEM state in {path}, tail={tail}")
                if not tail and stock[14] != site + 4:
                    raise ValueError(f"The original LR does not match the continuation in {path}")
                if stock[15] != TEST_SP - (0 if tail else 4):
                    raise ValueError(f"Unbalanced stack in {path}, tail={tail}")
                if stock[17:24] != (8 if tail else 9, status, expected if tail else initial,
                                    0x40, 0, 0, 0x809F9C):
                    raise ValueError(f"Unexpected OEM controller values in {path}: {stock[17:24]}")
                if stock[24:31] != (0,) * 7 or wrapped[24:31] != (1, 9, status, initial, 0, 0, TEST_SP - 16):
                    raise ValueError(f"Unexpected observation of the post-BAF4 point in {path}")
                if stock[31:33] != wrapped[31:33]:
                    raise ValueError(f"Wrapper changed OEM slot 13 state in {path}, tail={tail}")
                if stock[33:35] != (0, 0) or wrapped[33:35] != (mask, 0):
                    raise ValueError(f"Unexpected mask/control at the observer in {path}: {wrapped[33:35]}")
                if stock[35:39] != (0, 0, 1, old_generation):
                    raise ValueError(f"Stock CAN setup unexpectedly changed project state in {path}")
                if wrapped[35:39] != (0, old_generation, 0, new_generation):
                    raise ValueError(f"Wrong grant/generation at OEM entry or return in {path}: {wrapped[35:39]}")
                basiccan = wrapped[39:41]
                # This is RAM, so a peripheral reset does not erase BasicCAN flags.
                if stock[39:] != (0, 0, 0x41, 0x45) or wrapped[39:] != (0x41, 0x45, 0x41, 0x45):
                    raise ValueError(f"Unexpected BasicCAN control in {path}: {stock[39:]}, {wrapped[39:]}")
                if stock[31:33] != (mask, 0):
                    raise ValueError(f"Unexpected mask/control after OEM in {path}: {stock[31:33]}")
            results.append({
                "path": path,
                "call": f"0x{site:06X}",
                "return": f"0x{site + 4:06X}",
                "call_bytes": original_call.hex().upper(),
                "before_oem": {"can0slimk": mask, "slot13_msc": slot13, "basiccan_msc": [0x41, 0x45]},
                "wrapped_oem_entry": {"grant": 0, "generation": old_generation},
                "wrapped_oem_return": {"grant": 0, "generation": new_generation},
                "at_observer": {"can0cnt": 9, "can0stat": status, "oem_state": initial,
                                "slot11_msc": 0, "slot12_msc": 0,
                                "can0slimk": mask, "slot13_msc": 0, "basiccan_msc": basiccan},
                "after_oem_tail": {"can0cnt": 8, "can0stat": status, "oem_state": expected,
                                   "can0slimk": mask, "slot13_msc": 0, "basiccan_msc": stock[41:43]},
            })
    return {
        "base": identity,
        "compiler": version,
        "native_fragments": {
            name: {"start": f"0x{start:06X}", "end_exclusive": f"0x{end:06X}",
                   "sha256": sha256(rom[start:end]).hexdigest()}
            for name, _, start, end in ROM_FRAGMENTS
        },
        "executed_cases": 4 * len(results),
        "compared_state": ["R0-R15", "CR0", "CAN0 CNT/STAT in RAM", "slots 10-15 control bytes", "CAN0SLIMK",
                           "OEM saved-PSW pointer"],
        "observer_own_stack_bytes": 12,
        "setup_hook_own_stack_bytes": 16,
        "setup_hook_grant_and_generation_bound": "simulation only",
        "implemented_peripheral_behavior": "none; CAN0 register addresses are RAM shadows",
        "cases": results,
        "hardware_executed": False,
        "flashable_image": None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--gcc", required=True, type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.out and (args.out.suffix.lower() != ".json" or args.out.resolve() == args.base.resolve()):
        parser.error("--out must be a separate JSON report")
    try:
        result = json.dumps(check(args.base, args.gcc.resolve()), indent=2) + "\n"
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(result, encoding="utf-8")
        print(result, end="")
    except subprocess.CalledProcessError as error:
        message = error.stderr or error.stdout or str(error).encode()
        parser.exit(1, message.decode(errors="replace") + "\n")
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
