"""Link the complete H03 address model with the explicit bench memory inputs.

This orchestrates the existing multi-window linker. It does not provide missing
application callbacks, choose startup/timing settings, or serialize a BIN.
"""
import argparse
from contextlib import contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "targets/lfj8"
sys.path[:0] = [str(ROOT), str(TARGET)]

from tools import check_h03_image_layout as layout
import lfj8_h03_bench_memory_profile as bench
from lfj8_h03_layout import read_elf


def json_value(value):
    if isinstance(value, Path):
        return str(value)
    raise TypeError(type(value).__name__)


def save(path, value):
    path.write_text(json.dumps(value, default=json_value, indent=2) + "\n",
                    encoding="utf-8", newline="\n")


def compiler_path(value):
    executable = shutil.which(str(value))
    if executable is None:
        raise ValueError("M32R compiler was not found: " + str(value))
    return Path(executable).resolve(strict=True)


@contextmanager
def memory_inputs(compiler, profile):
    """Scope the two missing opt-in points to this one common-build invocation.

    Only this module's reference to subprocess is replaced. The standard library
    module, other tools and the RAM owner/verifiers are never patched. A generated
    source exception applies to one canonical ABS-only file, not its directory.
    """
    compiler = Path(compiler).resolve(strict=True)
    generated = Path(profile["symbol_source"]).resolve(strict=True)
    if (profile["symbols"] != bench.stack_symbols()
            or generated.name != bench.SYMBOL_SOURCE
            or generated.read_bytes() != bench.absolute_symbol_source(profile["symbols"]).encode("ascii")):
        raise ValueError("Expected the canonical generated H03 ABS source")
    generated_bytes = generated.read_bytes()
    consumers = {(TARGET / name).resolve(): name for name in bench.NATIVE_SOURCES}
    previous_process = layout.subprocess
    previous_sources = layout.extra_binding_sources
    applied = {name: {"preprocess": 0, "compile": 0} for name in bench.NATIVE_SOURCES}

    def extra_sources(values):
        ordinary, count = [], 0
        for value in values:
            path = Path(value)
            path = (ROOT / path).resolve() if not path.is_absolute() else path.resolve()
            if path == generated:
                count += 1
            else:
                ordinary.append(value)
        if count != 1 or generated.read_bytes() != generated_bytes:
            raise ValueError("Supply the one unchanged generated H03 ABS source exactly once")
        return [*previous_sources(ordinary), generated]

    class CompilerProcess:
        def __getattr__(self, name):
            return getattr(previous_process, name)

        def run(self, command, *args, **kwargs):
            command = [str(part) for part in command]
            if command and Path(command[0]).resolve() == compiler and ("-E" in command or "-c" in command):
                sources = [Path(part).resolve() for part in command[1:]
                           if not part.startswith("-") and Path(part).resolve() in consumers]
                if len(sources) > 1:
                    raise ValueError("Compile each native H03 memory consumer separately")
                if sources:
                    source = sources[0]
                    command[1:1] = bench.native_compile_flags(profile, source)
                    applied[consumers[source]]["preprocess" if "-E" in command else "compile"] += 1
            return previous_process.run(command, *args, **kwargs)

    try:
        layout.subprocess = CompilerProcess()
        layout.extra_binding_sources = extra_sources
        yield applied
    finally:
        layout.subprocess = previous_process
        layout.extra_binding_sources = previous_sources


def link_candidate(args):
    """Return compose input paths only after a complete verified ET_EXEC exists."""
    output = Path(args.out).resolve()
    if output.exists():
        raise ValueError("Choose a new output directory")
    # The common linker records every source relative to the repository. Keep
    # generated inputs in that same provenance namespace, including in CI.
    if not output.is_relative_to(ROOT):
        raise ValueError("Use a new output directory inside this repository")
    application = Path(args.application_profile).resolve(strict=True)
    if re.search(r"(?:^|[_-])(?:fixture|simulator|selftest|test)(?:[_\-.]|$)", application.name, re.I):
        raise ValueError("Supply an actual native application header")
    compiler = compiler_path(args.gcc)
    base = Path(args.base).resolve(strict=True)
    storage_path = Path(args.storage_report).resolve(strict=True)
    storage = layout.read_storage_report(storage_path)
    controller = Path(args.controller).resolve(strict=True)
    bridge = Path(args.bridge).resolve(strict=True)
    ordinary_sources = list(getattr(args, "binding_source", ()) or ())
    # Validate all caller-supplied sources with the unchanged production policy
    # before introducing the single generated-source exception.
    ordinary_sources = layout.extra_binding_sources(ordinary_sources)
    image = base.read_bytes()
    output.mkdir(parents=True, exist_ok=False)
    memory_dir = output / "memory"
    memory_dir.mkdir()
    layout_dir = output / "layout"
    layout_dir.mkdir()
    state = {"artifact_kind": "H03_COMPLETE_LINK_ATTEMPT", "bench_pair_ready": False,
             "hardware_verified": False, "flashable_image": None,
             "base_sha256": sha256(image).hexdigest(),
             "storage_sha256": sha256(storage_path.read_bytes()).hexdigest(),
             "application_profile": application, "compiler": compiler}
    try:
        pointer = storage["blocks"]["control"]["end_exclusive"]
        memory = bench.prepare(image, storage, pointer, memory_dir)
        memory_path = memory_dir / "memory-profile.json"
        save(memory_path, memory)
        sources = list(dict.fromkeys([*ordinary_sources, TARGET / bench.MODULE,
                                      memory["symbol_source"]]))
        options = argparse.Namespace(
            base=base, gcc=compiler, controller=controller, bridge=bridge,
            storage_report=storage_path, out=layout_dir,
            application_profile=application, binding_source=sources,
            sensor_clock_reference=getattr(args, "sensor_clock_reference", None),
            sensor_calibration_profile=getattr(args, "sensor_calibration_profile", None),
            profile="padding-candidate", memory_model=args.memory_model,
            with_bindings=True, with_dtc_rx=True, with_dma4_guard=True,
            with_service_guard=True, with_ram_owner=True, with_application_entries=True,
            with_can_service=True, with_resident_constants=True, cpu_test=False,
        )
        with memory_inputs(compiler, memory) as applied:
            report = layout.build(options)
        if any(not phases[phase] for phases in applied.values() for phase in ("preprocess", "compile")):
            raise ValueError("The common build omitted a native memory preprocessing/compile step")
        if report.get("status") != "PASS_ADDRESS_MODEL_ONLY" or report.get("accepted_layout") is not True:
            raise ValueError("A complete common linked address model is required")
        elf_path = layout_dir / "layout.elf"
        elf = read_elf(elf_path, 2)
        forbidden = [name for name in elf["symbols"] if re.search(
            r"(?:^|[_-])(?:fixture|simulator|selftest|test)(?:[_\-.]|$)", name, re.I)]
        if forbidden:
            raise ValueError("Test providers in linked image: " + ", ".join(sorted(forbidden)))
        verified = bench.verify_linked_profile(memory, elf)
        state.update(status="LINKED_ADDRESS_MODEL_ONLY", memory_verification=verified,
                     native_compile_steps=applied, flash_payload_bytes=report["flash_payload_bytes"],
                     new_static_ram_bytes=report["new_static_ram_bytes"],
                     compose_inputs={"base": base, "elf": elf_path,
                                     "layout": layout_dir / "layout.json", "memory_profile": memory_path})
        save(output / "link-result.json", state)
        return state
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        state.update(status="FAILED_NO_COMPLETE_IMAGE", error=str(error), error_type=type(error).__name__)
        report_path = layout_dir / "layout.json"
        if report_path.is_file():
            report = json.loads(report_path.read_text(encoding="utf-8"))
            state["common_layout_status"] = report.get("status")
            for key in ("unresolved_symbols", "flash_payload_bytes", "new_static_ram_bytes",
                        "known_sections_candidate_plan"):
                if key in report:
                    state[key] = report[key]
        save(output / "link-result.json", state)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("base", "gcc", "controller", "bridge", "storage-report", "application-profile", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--binding-source", action="append", type=Path, default=[])
    parser.add_argument("--memory-model", choices=("medium", "small"), default="medium")
    for name in ("sensor-clock-reference", "sensor-calibration-profile"):
        parser.add_argument("--" + name, type=Path)
    args = parser.parse_args()
    try:
        result = link_candidate(args)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        parser.exit(1, f"No complete linked candidate: {error}\n")
    print(json.dumps(result, default=json_value, indent=2))


if __name__ == "__main__":
    main()
