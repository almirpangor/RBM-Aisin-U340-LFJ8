"""Check M32R relocation against the H03 address model without emitting a ROM image."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import struct
import subprocess
from tempfile import TemporaryDirectory


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FLASH_START = 0x020000
FLASH_END = 0x030000
TARGET = ["-m32r", "-mmodel=medium", "-msdata=none", "-Wa,-EB"]
LIBRARIES = ["-Wl,--start-group", "-lc", "-lgcc", "-Wl,--end-group"]

# Keep the recovered control, adaptation and platform entry points even
# when no target scheduler calls them yet. Helpers reachable from these
# functions are retained by the linker.
H03_ROOTS = (
    "lfj8_selector_adc_init", "lfj8_selector_adc_publish_9e1c", "lfj8_selector_adc_take",
    "lfj8_range_control_init", "lfj8_range_control_step",
    "lfj8_9e1c_raw_vss_init", "lfj8_9e1c_raw_vss_after_capture_store",
    "lfj8_9e1c_raw_nt_init", "lfj8_9e1c_raw_nt_after_capture_store",
    "lfj8_h03_capture_pair", "lfj8_gear_observer_init", "lfj8_gear_observe_pair",
    "lfj8_h03_atf_init", "lfj8_h03_atf_after_adc_store", "lfj8_h03_atf_after_store",
    "lfj8_h03_atf_snapshot", "lfj8_h03_engine_rx_init", "lfj8_h03_engine_rx_m32r",
    "lfj8_chery_tx_init", "lfj8_chery_tx_poll",
    "rbm_u340e_outputs_init", "rbm_u340e_outputs_step", "lfj8_h03_plan_outputs",
    "rbm_u340e_runtime_init", "rbm_u340e_runtime_snapshot_gears", "rbm_u340e_runtime_gears_outputs",
    "lfj8_h03_takeover_init", "lfj8_h03_takeover_prepare", "lfj8_h03_takeover_apply",
    "factory_hydraulics_control_main",
    "factory_hydraulics_fast_learning", "factory_hydraulics_load_main",
    "factory_hydraulics_load_observer", "factory_hydraulics_counters_begin",
    "factory_hydraulics_counters_end", "factory_donor_engine_gate",
    "factory_hydraulics_capture", "factory_hydraulics_restore",
    "factory_adaptation_load", "factory_adaptation_save",
)
DTC_FILES = ("chery_dtc.c", "chery_dtc_can.c", "chery_dtc_link.c")
DTC_ROOTS = (
    "chery_dtc_init", "chery_dtc_set_current", "chery_dtc_store_snapshot",
    "chery_dtc_link_init", "chery_dtc_link_end_session", "chery_dtc_link_expire",
    "chery_dtc_link_receive", "chery_dtc_link_confirm_tx",
)


def identify_h03(path):
    sources = json.loads((ROOT / "data/sources.json").read_text(encoding="utf-8"))
    expected = next(record for record in sources["supporting_materials"] if record["id"] == "H03")
    source = path.read_bytes()
    digest = sha256(source).hexdigest()
    if len(source) != expected["bytes"] or digest != expected["sha256"]:
        raise ValueError("The supplied image does not match the approved H03 base")
    if source[0x00816C:0x008170] != bytes.fromhex("FE00E06E"):
        raise ValueError("The H03 foreground call at 0x00816C is different")
    if source[FLASH_START:FLASH_END] != b"\xff" * (FLASH_END - FLASH_START):
        raise ValueError("The entire hypothesis ROM window must have FF fill in H03")
    return {"id": "H03", "bytes": len(source), "sha256": digest}


def elf_info(path, kind):
    data = path.read_bytes()
    if (data[:7] != b"\x7fELF\x01\x02\x01" or len(data) < 52 or
            struct.unpack_from(">HHI", data, 16) != (kind, 88, 1)):
        raise ValueError(f"Expected ELF32 big-endian M32R: {path.name}")
    start = struct.unpack_from(">I", data, 32)[0]
    stride, count, _ = struct.unpack_from(">HHH", data, 46)
    if stride != 40 or not count or start + stride * count > len(data):
        raise ValueError(f"Invalid ELF section table: {path.name}")
    totals = {"code": 0, "read_only_data": 0, "writable_data": 0, "bss": 0}
    relocations = 0
    allocated = []
    for index in range(count):
        _, section_type, flags, address, _, size, _, _, _, entry_size = struct.unpack_from(
            ">10I", data, start + index * stride
        )
        if section_type in (4, 9):
            if not entry_size or size % entry_size:
                raise ValueError(f"Invalid ELF relocation section: {path.name}")
            relocations += size // entry_size
        if size and flags & 2:
            allocated.append((address, size, flags))
            if flags & 1:
                category = "bss" if section_type == 8 else "writable_data"
            else:
                category = "code" if flags & 4 else "read_only_data"
            totals[category] += size
    return {
        "bytes": len(data), "sha256": sha256(data).hexdigest(),
        "flags": struct.unpack_from(">I", data, 36)[0],
        "alloc_bytes": totals, "relocations": relocations,
    }, allocated


def stage_test(stage):
    shutil.copytree(ROOT / "controller/include", stage / "controller")
    shutil.copytree(ROOT / "controller/vendor/toyota/include", stage / "toyota")
    sources = [
        ROOT / "tests/u340_integration_host.c",
        HERE / "test_lfj8_selector_adc.c",
        HERE / "lfj8_range_control.c",
        ROOT / "targets/panel/panel_pulse.c",
    ]
    headers = [*HERE.glob("*.h"), ROOT / "targets/panel/panel_pulse.h"]
    diagnostics = ROOT / "diagnostics"
    dtc_inputs = [*(diagnostics / name for name in DTC_FILES), *diagnostics.glob("*.h"),
                  diagnostics / "test_chery_dtc_link.c"]
    for item in (*sources, *headers, *dtc_inputs, HERE / "host_check.c", HERE / "test_lfj8_h03_atf.c",
                 HERE / "test_lfj8_h03_mmio.c", HERE / "test_lfj8_gear_observer.c",
                 HERE / "lfj8_h03_outputs.c", HERE / "test_lfj8_h03_outputs.c",
                 HERE / "lfj8_h03_takeover.c", HERE / "test_lfj8_h03_takeover.c",
                 ROOT / "controller/tests/test_runtime.c"):
        shutil.copyfile(item, stage / item.name)
    (stage / "sim_crt.c").write_text(
        "int integration_test(int argc, char **argv);\n"
        "void __init(void) {}\n"
        "void __fini(void) {}\n"
        "int main(void) { return integration_test(1, (char **)0); }\n",
        encoding="ascii",
    )
    return [item.name for item in sources]


def check(base, bridge, controller, compiler, simulator_output):
    report = {"source": identify_h03(base), "artifact_kind": "address_model_and_cpu_test"}

    with TemporaryDirectory(prefix="rbm-h03-link-") as directory:
        stage = Path(directory)
        staged_objects = [(bridge, stage / "bridge.o"), (controller, stage / "controller.o")]
        report["inputs"] = {}
        for source, staged in staged_objects:
            shutil.copyfile(source, staged)
            report["inputs"][source.name] = elf_info(staged, 1)[0]
        manifest = json.loads((bridge.parent / "build-manifest.json").read_text(encoding="utf-8"))
        if (manifest["m32r_base"]["sha256"] != report["source"]["sha256"] or
                manifest["artifacts"][bridge.name]["sha256"] != report["inputs"][bridge.name]["sha256"]):
            raise ValueError("The bridge object and its manifest do not match the H03 build")

        def run(*args):
            return subprocess.run([str(arg) for arg in args], cwd=stage, text=True, check=True,
                                  capture_output=True, timeout=60).stdout.strip()

        if run(compiler, "-dumpmachine") != "m32r-elf":
            raise ValueError("A bare-metal M32R compiler is required")
        report["compiler"] = run(compiler, "--version").splitlines()[0]
        nm = run(compiler, "-print-prog-name=nm")
        simulator = compiler.with_name(f"m32r-elf-run{compiler.suffix}")
        integration, selector_test, range_source, panel = stage_test(stage)
        flags = ["-Os", "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wno-missing-braces",
                 "-Wno-missing-field-initializers", "-I.", "-Icontroller", "-Itoyota"]
        module_flags = [*flags, "-ffreestanding", "-fno-builtin", "-ffunction-sections", "-fdata-sections"]
        run(compiler, *TARGET, *module_flags, "-c", range_source,
            "-o", "range.o")
        report["inputs"]["range.o"] = elf_info(stage / "range.o", 1)[0]
        run(compiler, *TARGET, *module_flags, "-c", "lfj8_h03_outputs.c",
            "-o", "output-plan.o")
        report["inputs"]["output-plan.o"] = elf_info(stage / "output-plan.o", 1)[0]
        run(compiler, *TARGET, *module_flags, "-c", "lfj8_h03_takeover.c", "-o", "takeover.o")
        report["inputs"]["takeover.o"] = elf_info(stage / "takeover.o", 1)[0]
        libraries = ["-fno-use-linker-plugin", "-nostdlib", *LIBRARIES]
        run(compiler, *TARGET, "-r", "bridge.o", "controller.o", "range.o", "output-plan.o", *libraries,
            "-o", "combined.o")
        if run(nm, "-u", "combined.o"):
            raise ValueError("Combined object has unresolved link symbols")
        report["combined"] = elf_info(stage / "combined.o", 1)[0]
        (stage / "unbounded-reference.ld").write_text(
            f"""ENTRY(rbm_u340e_step)
SECTIONS {{
  . = {FLASH_START:#x};
  .text : {{ *(.text .text.*) }}
  .rodata : {{ *(.rodata .rodata.*) }}
  .data : {{ *(.data .data.* .sdata .sdata.*) }}
  .bss (NOLOAD) : {{ *(.bss .bss.* .sbss .sbss.*) *(COMMON) }}
  /DISCARD/ : {{ *(.note*) *(.comment) }}
}}
ASSERT(SIZEOF(.data) == 0, "Unexpected initialized writable data")
ASSERT(SIZEOF(.bss) == 0, "Unexpected writable static state")
""", encoding="ascii",
        )
        (stage / "model.ld").write_text(
            "INCLUDE unbounded-reference.ld\n"
            f'ASSERT(ADDR(.rodata) + SIZEOF(.rodata) <= {FLASH_END:#x}, "Address-model ROM overflow")\n',
            encoding="ascii",
        )

        def root_flags(roots):
            return ["-Wl,--gc-sections", *(f"-Wl,--undefined={root}" for root in roots)]

        def link_model(name, object_file, roots=()):
            linker_script = "model.ld" if roots else "unbounded-reference.ld"
            run(compiler, *TARGET, "-fno-use-linker-plugin", "-nostdlib", f"-Wl,-T,{linker_script}",
                object_file, "-o", name)
            linked, allocated = elf_info(stage / name, 2)
            if linked["relocations"] or any(
                start < FLASH_START or (roots and start + size > FLASH_END) or flags & 1
                for start, size, flags in allocated
            ):
                raise ValueError("Unresolved relocation or allocation outside the test ROM window")
            layout = {
                "start": f"0x{FLASH_START:06X}", "end_exclusive": f"0x{FLASH_END:06X}",
                "oem_erase_start_record": "0x000958", "target_ownership_verified": False,
                "section_bytes": linked["alloc_bytes"], "relocations": linked["relocations"],
                "rom_extent_bytes": max(start + size for start, size, _ in allocated) - FLASH_START,
            }
            layout["window_margin_bytes"] = FLASH_END - FLASH_START - layout["rom_extent_bytes"]
            if roots:
                symbols = {line.split()[-1] for line in run(nm, "--defined-only", name).splitlines()
                           if line.strip()}
                if not set(roots) <= symbols:
                    raise ValueError("Compact link discarded a required symbol")
                layout["retained_entry_points"] = roots
            return layout

        report["address_model"] = link_model("linked-model.elf", "combined.o")
        report["address_model"]["role"] = "unbounded_reference_with_no_takeover_or_dtc"
        run(compiler, *TARGET, "-r", *root_flags(H03_ROOTS), "combined.o", "takeover.o",
            *libraries, "-o", "compact.o")
        compact = link_model("compact-model.elf", "compact.o", H03_ROOTS)
        report["compact_address_model"] = compact
        dtc_objects = []
        for source in DTC_FILES:
            obj = Path(source).with_suffix(".o").name
            run(compiler, *TARGET, *module_flags, "-c", source, "-o", obj)
            dtc_objects.append(obj)
        roots_with_dtc = H03_ROOTS + DTC_ROOTS
        run(compiler, *TARGET, "-r", *root_flags(roots_with_dtc), "compact.o", *dtc_objects,
            *libraries, "-o", "compact-with-dtc.o")
        compact_with_dtc = link_model("compact-with-dtc.elf", "compact-with-dtc.o", roots_with_dtc)
        compact_with_dtc["dtc_increment_bytes"] = compact_with_dtc["rom_extent_bytes"] - compact["rom_extent_bytes"]
        report["compact_address_model_with_dtc"] = compact_with_dtc

        crt = run(compiler, *TARGET, "-print-file-name=crt0.o")
        run(compiler, *TARGET, *flags, "-Dmain=integration_test", "-c", integration,
            "-o", "integration.o")
        run(compiler, *TARGET, *flags, "-nostartfiles", crt, selector_test, panel, "sim_crt.c",
            "integration.o", "combined.o", "-Wl,-e,_start", "-Wl,--start-group", "-lc", "-lgloss", "-lgcc",
            "-Wl,--end-group", "-o", "sim.elf")
        result = json.loads(run(simulator, "sim.elf"))
        if (result.get("selector_adc_events"), result.get("selector_timeout")) != ("PASS", "PASS"):
            raise ValueError("The M32R integration check did not report a passing result")
        report["emulated_integration"] = result
        (stage / "component_crt.c").write_text(
            "void __init(void) {}\nvoid __fini(void) {}\n", encoding="ascii",
        )
        report["emulated_components"] = {}
        component_tests = [
            ("lfj8_io", "host_check.c", "bridge.o"),
            ("h03_atf", "test_lfj8_h03_atf.c", "compact.o"),
            ("h03_mmio", "test_lfj8_h03_mmio.c", "compact.o"),
            ("gear_observer", "test_lfj8_gear_observer.c", "compact.o"),
            ("h03_output_plan", "test_lfj8_h03_outputs.c", "compact.o"),
            ("h03_takeover", "test_lfj8_h03_takeover.c", "compact.o"),
            ("toyota_gp_runtime", "test_runtime.c", "compact.o"),
            ("chery_dtc", "test_chery_dtc_link.c", "compact-with-dtc.o"),
        ]
        for name, source, object_file in component_tests:
            elf = f"{name}.elf"
            test_flags = ["-DRBM_TEST_RUNTIME_STANDALONE"] if name == "toyota_gp_runtime" else []
            run(compiler, *TARGET, *flags, *test_flags, "-nostartfiles", crt, source, "component_crt.c",
                object_file, "-Wl,-e,_start", "-Wl,--start-group", "-lc", "-lgloss", "-lgcc",
                "-Wl,--end-group", "-o", elf)
            report["emulated_components"][name] = run(simulator, elf)
        if simulator_output is not None:
            simulator_output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(stage / "sim.elf", simulator_output)
            report["simulator_elf"] = {
                "file": simulator_output.name, **elf_info(stage / "sim.elf", 2)[0],
            }

    report.update({
        "candidate_call": {"offset": "0x00816C", "oem_target": "0x040324", "return": "0x008170"},
        "target_stack_budget_verified": False,
        "target_ram_ownership_verified": False,
        "flashable_image": None,
    })
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for argument in ("base", "bridge", "controller", "gcc", "out"):
        parser.add_argument(f"--{argument}", required=True, type=Path)
    parser.add_argument("--sim-out", type=Path, help="optional simulator ELF with the test fixture")
    args = parser.parse_args()
    input_paths = {path.resolve() for path in (args.base, args.bridge, args.controller, args.gcc)}
    if args.out.suffix.lower() != ".json" or args.out.resolve() in input_paths:
        parser.error("--out must be a separate JSON report")
    if args.sim_out is not None and (args.sim_out.suffix.lower() != ".elf" or
            args.sim_out.resolve() in input_paths | {args.out.resolve()}):
        parser.error("--sim-out must be a separate simulator ELF")
    try:
        report = check(args.base, args.bridge, args.controller, args.gcc.resolve(), args.sim_out)
        report_text = json.dumps(report, indent=2) + "\n"
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report_text, encoding="utf-8")
        print(report_text, end="")
    except (ValueError, OSError, KeyError, StopIteration, subprocess.SubprocessError) as error:
        parser.exit(1, f"{getattr(error, 'stderr', None) or error}\n")


if __name__ == "__main__":
    main()
