"""Verify the compiled bench selector and calculate its divider margins."""

import argparse
from fractions import Fraction
from hashlib import sha256
import json
from math import ceil, floor
from pathlib import Path
import re
import struct
import subprocess
from tempfile import TemporaryDirectory

from check_h03_link import HERE, ROOT, TARGET
from lfj8_h03_layout import alloc_sections, read_elf


# The earlier R=1500 ohm proposal crosses the lower R window at the model corner.
NOMINAL_OHMS = {"P": 4300, "R": 1650, "N": 750, "D": 390, "2": 200, "L": 91}
H03_LIMIT_OFFSETS = ((0x016760, 0x01675C), (0x016768, 0x016764), (0x016758, 0x016754),
                     (0x016744, 0x016740), (0x016770, 0x01676C), (0x01674C, 0x016748))
PULLUP_OHMS = (390, 430)
SUPPLY_TO_REFERENCE = (Fraction(98, 100), Fraction(102, 100))
RESISTOR_TOLERANCE = Fraction(1, 100)


def adc_code(resistance, pullup, ratio=1):
    return 1024 * ratio * resistance / (resistance + pullup)


def divider(windows, image):
    rows = {}
    for (position, nominal), (lower, upper), offsets in zip(
            NOMINAL_OHMS.items(), windows, H03_LIMIT_OFFSETS, strict=True):
        rom_volts = [struct.unpack_from(">f", image, offset)[0] for offset in offsets]
        rom_codes = [round(value * 1024 / 5) for value in rom_volts]
        if lower not in (rom_codes[0], rom_codes[0] + 1) or upper not in (rom_codes[1], rom_codes[1] + 1):
            raise ValueError(f"{position}: compiled window does not match the H03 voltage boundaries")
        pull_min, pull_max = PULLUP_OHMS
        ratio_min, ratio_max = SUPPLY_TO_REFERENCE
        low_r = nominal * (1 - RESISTOR_TOLERANCE)
        high_r = nominal * (1 + RESISTOR_TOLERANCE)
        low = floor(adc_code(low_r, pull_max, ratio_min))
        high = ceil(adc_code(high_r, pull_min, ratio_max))
        if not lower <= low <= high < upper:
            raise ValueError(f"{position}: predicted code [{low}, {high}] leaves compiled window [{lower}, {upper})")
        min_nominal = lower * pull_max / ((1024 * ratio_min - lower) * (1 - RESISTOR_TOLERANCE))
        max_nominal = (upper - 1) * pull_min / ((1024 * ratio_max - upper + 1) * (1 + RESISTOR_TOLERANCE))
        nominal_code = adc_code(Fraction(nominal), pull_min)
        rows[position] = {
            "resistor_ohms": nominal,
            "nominal_input_volts_at_5_v": round(float(nominal_code * 5 / 1024), 4),
            "nominal_adc_code_floor": floor(nominal_code),
            "qualified_adc_window_half_open": [lower, upper],
            "h03_rom_boundary_addresses": [f"{address:#08x}" for address in offsets],
            "h03_rom_boundary_volts": rom_volts,
            "conservative_adc_span_inclusive": [low, high],
            "minimum_margin_codes": min(low - lower, upper - 1 - high),
            "admissible_nominal_resistor_ohms_under_model": [ceil(min_nominal), floor(max_nominal)],
        }
    return rows


def check(compiler, base):
    image = base.read_bytes()
    image_hash = sha256(image).hexdigest()
    registry = json.loads((ROOT / "data/sources.json").read_text(encoding="utf-8"))
    approved = next(entry["sha256"] for entry in registry["supporting_materials"] if entry["id"] == "H03")
    if image_hash != approved:
        raise ValueError("Expected the pinned LFJ8-T-D H03 base")

    with TemporaryDirectory(prefix="rbm-bench-mode-") as directory:
        work = Path(directory)
        flags = [compiler, *TARGET, "-Os", "-std=c11", "-Wall", "-Wextra", "-Werror",
                 "-Wno-missing-braces", "-Wno-missing-field-initializers",
                 "-ffreestanding", "-fno-common", "-fno-builtin", "-ffunction-sections",
                 "-fdata-sections",
                 *("-I" + str(folder) for folder in (HERE, ROOT / "controller/include",
                                                      ROOT / "controller/vendor/toyota/include"))]
        for source in ("bench_mode_profile", "lfj8_h03_input_binding"):
            subprocess.run([*flags, "-c", HERE / (source + ".c"), "-o", source + ".o"],
                           cwd=work, check=True, timeout=30)
        sections = {entry["name"]: entry for entry in
                    alloc_sections(read_elf(work / "bench_mode_profile.o", 1))}
        binding_sections = alloc_sections(read_elf(work / "lfj8_h03_input_binding.o", 1))
        if any(entry["flags"] & 1 for entry in (*sections.values(), *binding_sections)):
            raise ValueError("The bench constants must not add writable RAM")
        selector = sections[".rodata.lfj8_h03_bench_selector"]["data"]
        windows = list(struct.iter_unpack(">HH", selector[:24]))
        if len(selector) != 26 or selector[24] != 4:
            raise ValueError("Expected the four-observation 10-bit selector profile")
        for mode, policy in (("selector", bytes([0, 0, 0, 1])), ("manual", bytes([16, 2, 0, 1]))):
            startup = sections[f".rodata.lfj8_h03_bench_{mode}_startup"]["data"]
            if startup != policy + struct.pack(">3I", 10000, 20000, 10000):
                raise ValueError(f"Unexpected {mode} startup policy or timing")
        objdump = compiler.with_name("m32r-elf-objdump" + compiler.suffix)
        disassembly = subprocess.check_output([objdump, "-d", "lfj8_h03_input_binding.o"], cwd=work,
                                              encoding="ascii", timeout=30)
        stack = {}
        for section in disassembly.split("Disassembly of section .text.")[1:]:
            name = section.split(":", 1)[0]
            instructions = re.findall(r"\bpush (?:r\d+|lr|fp)\b|\baddi sp,#-\d+", section)
            stack[name] = instructions
    return {
        "status": "PASS",
        "h03_sha256": image_hash,
        "divider_model": {"adc_counts_full_scale": 1024, "pullup_ohms": list(PULLUP_OHMS),
                          "supply_to_reference": [float(ratio) for ratio in SUPPLY_TO_REFERENCE],
                          "resistor_tolerance": float(RESISTOR_TOLERANCE),
                          "physical_pullup_and_reference_verified": False},
        "positions": divider(windows, image),
        "profile_flash_data_bytes": sum(entry["size"] for entry in sections.values()),
        "input_binding_object_flash_bytes": sum(entry["size"] for entry in binding_sections),
        "profile_mutable_storage_bytes": 0,
        "binding_stack_decrements_in_disassembly": stack,
        "hardware_tested": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("gcc", "base", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    if args.out.suffix.lower() != ".json" or (args.out.exists() and args.out.samefile(args.base)):
        parser.error("Use a separate JSON report")
    try:
        report = check(args.gcc.resolve(), args.base.resolve())
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print("H03 bench mode: compiled selector, reset policy and divider margins PASS")
    except (KeyError, OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
