"""Replay the H03 bench memory contract through the common layout without a BIN."""

import argparse
import json
from pathlib import Path
import runpy
import subprocess
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
TARGET = ROOT / "targets/lfj8"
sys.path[:0] = [str(ROOT), str(TARGET)]

from tools import check_h03_image_layout as layout
import lfj8_h03_bench_memory_profile as bench


def check(args):
    layout_report = args.out / "layout.json"
    if layout_report.is_file():
        raise ValueError("Choose an output directory without an existing layout.json")
    rom = args.base.read_bytes()
    storage = layout.read_storage_report(args.storage_report)
    irq_pointer = storage["blocks"]["control"]["end_exclusive"]
    args.out.mkdir(parents=True, exist_ok=True)
    memory = bench.prepare(rom, storage, irq_pointer, args.out)
    existing = runpy.run_path(str(ROOT / "verification/project-audit/integration-11-20261121/check-composition.py"))
    application = args.out / "COMPOSITION_SIMULATOR_ONLY.h"
    application.write_text(existing["PROFILE"], encoding="ascii")
    options = argparse.Namespace(
        **vars(args), profile="padding-candidate", memory_model="medium",
        with_bindings=True, with_dtc_rx=True, with_dma4_guard=True, with_can_service=True,
        with_service_guard=True, with_ram_owner=True, with_application_entries=True,
        with_resident_constants=True, application_profile=application, cpu_test=False,
        binding_source=[TARGET / name for name in (*existing["PROVIDERS"], bench.MODULE)],
    )

    # These two assembly/link inputs are the integrator's opt-in points. The
    # replay does not change the shared tool or implement missing providers.
    compile_sources = {bench.MODULE, "lfj8_h03_ram_owner.c", "h03_dma4_guard.S"}
    native_flags = ("-D" + bench.NATIVE_DEFINE, "-I", str(args.out),
                    '-DRBM_H03_BENCH_MEMORY_HEADER="' + memory["header"].name + '"')
    original_bounds = layout.ram_owner.confirmed_ranges
    original_run = subprocess.run

    def bounds(image, blocks):
        return {**original_bounds(image, blocks), **memory["symbols"]}

    def compile_bench(command, *positional, **kwargs):
        if (Path(command[0]) == args.gcc and
                any(Path(part).name in compile_sources for part in command[1:])):
            command = [*command, *native_flags]
        return original_run(command, *positional, **kwargs)

    with patch.object(layout.ram_owner, "confirmed_ranges", bounds), patch.object(subprocess, "run", compile_bench):
        try:
            result = layout.build(options)
        except ValueError:
            if not layout_report.is_file():
                raise
            result = json.loads(layout_report.read_text(encoding="utf-8"))
            if result.get("status") != "FAIL_BINDINGS":
                raise

    required = {*memory["symbols"], "rbm_h03_boot_writers_owned"}
    if required.intersection(result.get("unresolved_symbols", ())) or result.get("flashable_image"):
        raise ValueError("Unexpected unresolved memory provider or generated image")
    aliases = result["can_service"]["typed_aliases"]
    actual = {name: aliases[name][0] for name in memory["early_bindings"]}
    if actual != memory["early_bindings"]:
        raise ValueError("Linked early IRQ latches do not match the bench storage inventory")
    model = result["early_irq_model"]
    if (model["irq_pointer"] != irq_pointer or
            tuple(map(tuple, model["policy_ranges"])) != tuple(memory["policy_ranges"])):
        raise ValueError("Common early IRQ model does not use the bench memory policy")
    bench.verify_ram_placements(model["placements"])
    bench.verify_ram_placements(result.get("placements", ()))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("base", "gcc", "controller", "bridge", "storage-report", "out"):
        parser.add_argument("--" + name, type=lambda value: Path(value).resolve(), required=True)
    result = check(parser.parse_args())
    print(json.dumps({name: result.get(name) for name in (
        "status", "flash_payload_bytes", "new_static_ram_bytes", "unresolved_symbols",
        "known_sections_candidate_plan", "flashable_image",
    )}, indent=2))


if __name__ == "__main__":
    main()
