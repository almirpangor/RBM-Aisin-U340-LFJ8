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
TAIL_START = 0x07C118
TAIL_END = 0x07FFFC
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
    "lfj8_h03_tml0ct_m32r",
    "lfj8_chery_tx_init", "lfj8_chery_tx_poll",
    "rbm_u340e_outputs_init", "rbm_u340e_outputs_step", "lfj8_h03_plan_outputs",
    "rbm_u340e_runtime_init", "rbm_u340e_runtime_snapshot_gears", "rbm_u340e_runtime_gears_outputs",
    "rbm_u340e_runtime_prepare_engine", "rbm_u340e_runtime_main_coolant",
    "rbm_u340e_runtime_main_engine_speed",
    "rbm_u340e_runtime_secondary_load_qualify",
    "rbm_u340e_range_fast", "rbm_u340e_runtime_main_range",
    "rbm_u340e_runtime_main_range_complete",
    "rbm_u340e_schedule_finish_init", "rbm_u340e_schedule_timer_irq",
    "rbm_u340e_schedule_producer_publish", "rbm_u340e_schedule_producer_done",
    "rbm_u340e_schedule_fast_claim", "rbm_u340e_schedule_fast_begin",
    "rbm_u340e_schedule_fast_end", "rbm_u340e_schedule_fast_done",
    "rbm_u340e_schedule_secondary_claim", "rbm_u340e_schedule_secondary_done",
    "rbm_u340e_schedule_main_done",
    "lfj8_h03_takeover_init", "lfj8_h03_takeover_prepare", "lfj8_h03_takeover_apply",
    "factory_hydraulics_control_main",
    "factory_hydraulics_fast_learning", "factory_hydraulics_load_main",
    "factory_hydraulics_load_observer", "factory_hydraulics_counters_begin",
    "factory_hydraulics_counters_end", "factory_donor_engine_gate",
    "factory_hydraulics_capture", "factory_hydraulics_restore",
    "factory_adaptation_load", "factory_adaptation_save",
)
DTC_FILES = ("chery_dtc.c", "chery_dtc_can.c", "chery_dtc_link.c", "chery_model_monitor.c")
DTC_ROOTS = (
    "chery_dtc_init", "chery_dtc_set_current", "chery_dtc_store_snapshot",
    "chery_dtc_link_init", "chery_dtc_link_end_session", "chery_dtc_link_expire",
    "chery_dtc_link_receive", "chery_dtc_link_confirm_tx",
    "chery_model_monitor_init", "chery_model_monitor_task2",
)
CAN_EXTENSION_FILES = ("lfj8_h03_torque.c", "lfj8_h03_dtc_can.c", "lfj8_h03_dtc_rx_queue.c",
                       "lfj8_h03_torque_can.c", "ta2005_engine_qualifier.c", "lfj8_h03_cycle.c",
                       "lfj8_h03_phase_clock.c", "lfj8_h03_phase_startup.c",
                       "lfj8_h03_engine_feed.c", "lfj8_h03_can13.c")
CAN_EXTENSION_ROOTS = (
    "lfj8_h03_torque_demand", "lfj8_h03_torque_init", "lfj8_h03_torque_poll",
    "lfj8_h03_torque_tx_done", "lfj8_h03_torque_receive", "lfj8_h03_torque_applied",
    "lfj8_h03_dtc_can_decode_basic", "lfj8_h03_dtc_can_init", "lfj8_h03_dtc_can_poll",
    "lfj8_h03_dtc_rx_queue_init", "lfj8_h03_dtc_rx_queue_reset",
    "lfj8_h03_dtc_rx_queue_publish", "lfj8_h03_dtc_rx_queue_peek", "lfj8_h03_dtc_rx_queue_consume",
    "lfj8_h03_torque_can_init", "lfj8_h03_torque_can_poll",
    "ta2005_engine_qualifier_init", "ta2005_engine_qualifier_task2",
    "lfj8_h03_cycle_init", "lfj8_h03_cycle_tick", "lfj8_h03_cycle_slt_inputs",
    "lfj8_h03_cycle_prepare_outputs",
    "lfj8_h03_phase_clock_init", "lfj8_h03_phase_clock_release", "lfj8_h03_phase_clock_take",
    "lfj8_h03_phase_startup", "lfj8_h03_takeover_check_phase", "lfj8_h03_takeover_take_phase",
    "lfj8_h03_engine_feed_task2", "lfj8_h03_can13_init", "lfj8_h03_can13_poll",
)
S01_LINK_TABLES = (
    ("learning_001C3C", 800, "8276650f90e31262d21eca82fd06ce04c9ed0456b74c9456cebf2b11b0b9fd5b"),
    ("pressure_0015FC", 36, "57d409e7acd5e96573b9857bd4275a2e850990facad3e1e668a7109b8600e41f"),
    ("gear_000D08", 8, "297dcae8b2e253f2f4087110887391050045684a250054e96ebf7b81624df67b"),
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


def check_shared_tables(stage, compiler, run, elf):
    objcopy = run(compiler, "-print-prog-name=objcopy")
    nm = run(compiler, "-print-prog-name=nm")
    run(objcopy, "-O", "binary", elf, "linked-rom.dat")
    rom = (stage / "linked-rom.dat").read_bytes()
    rows = [line.split() for line in run(nm, "-S", elf).splitlines()]
    tables = {}
    for name, size, digest in S01_LINK_TABLES:
        matches = [row for row in rows if len(row) == 4 and row[3] == name]
        if len(matches) != 1 or int(matches[0][1], 16) != size or matches[0][2] != "R":
            raise ValueError(f"Expected one read-only instance of S01 table {name}")
        address = int(matches[0][0], 16)
        offset = address - FLASH_START
        if offset < 0 or sha256(rom[offset:offset + size]).hexdigest() != digest:
            raise ValueError(f"S01 calibration mismatch in the linked image: {name}")
        tables[name] = {"address": address, "bytes": size, "sha256": digest}
    return tables


def check_split_layout(stage, compiler, run, base, primary_objects, extension_objects, extension_roots):
    """Link independent CAN modules into a second read-only window for sizing."""
    rom = base.read_bytes()
    if rom[TAIL_START:TAIL_END] != b"\xff" * (TAIL_END - TAIL_START):
        raise ValueError("Unexpected bytes in the H03 tail address window")
    extension_input = "\n    ".join(
        f"{name}(.text .text.* .rodata .rodata.*)" for name in extension_objects
    )
    script = f"""ENTRY(rbm_u340e_step)
SECTIONS {{
  .can_extension {TAIL_START:#x} : {{
    {extension_input}
    *(.text.lfj8_h03_can0_torque_* .text.pause_torque_listener .text.torque_slot_available)
    *(.text.lfj8_h03_can0_diag_* .text.lfj8_h03_can0_telemetry_status
      .text.lfj8_h03_can0_slot13_timestamp .text.slot13_status)
    *(.text.rbm_u340e_runtime_secondary_load_qualify .text.rbm_u340e_hydraulics_control_main_workspace)
    *(.text.lfj8_h03_takeover_check_phase .text.lfj8_h03_takeover_take_phase)
  }}
  .text {FLASH_START:#x} : {{ *(.text .text.*) }}
  .rodata : {{ *(.rodata .rodata.*) }}
  .data : {{ *(.data .data.* .sdata .sdata.*) }}
  .bss (NOLOAD) : {{ *(.bss .bss.* .sbss .sbss.*) *(COMMON) }}
  /DISCARD/ : {{ *(.note*) *(.comment) }}
}}
ASSERT(ADDR(.rodata) + SIZEOF(.rodata) <= {FLASH_END:#x}, "Primary H03 window overflow")
ASSERT(ADDR(.can_extension) + SIZEOF(.can_extension) <= {TAIL_END:#x}, "CAN extension window overflow")
ASSERT(SIZEOF(.data) == 0 && SIZEOF(.bss) == 0, "Unexpected writable static state")
"""
    (stage / "split.ld").write_text(script, encoding="ascii")
    roots = H03_ROOTS + extension_roots
    options = [f"-Wl,--undefined={root}" for root in roots]
    run(compiler, *TARGET, "-fno-use-linker-plugin", "-nostdlib", "-Wl,-T,split.ld,--gc-sections",
        *options, *primary_objects, *extension_objects, *LIBRARIES, "-o", "split.elf")
    linked, allocated = elf_info(stage / "split.elf", 2)
    ranges = ((FLASH_START, FLASH_END), (TAIL_START, TAIL_END))
    if linked["relocations"] or any(flags & 1 or not any(lo <= address and address + size <= hi
                                   for lo, hi in ranges) for address, size, flags in allocated):
        raise ValueError("Split layout has an unresolved relocation or unexpected allocation")
    nm = run(compiler, "-print-prog-name=nm")
    symbols = {row.split()[-1]: int(row.split()[0], 16)
               for row in run(nm, "--defined-only", "split.elf").splitlines() if len(row.split()) == 3}
    if not set(roots) <= symbols.keys():
        raise ValueError("Split layout discarded a required entry point")
    if not all(TAIL_START <= symbols[root] < TAIL_END for root in extension_roots):
        raise ValueError("An extended CAN entry point escaped the tail window")
    windows = {}
    for role, (lo, hi) in zip(("primary", "can_extension"), ranges):
        placed = [(address + size) for address, size, _ in allocated if lo <= address < hi]
        if not placed:
            raise ValueError(f"Expected an allocated section in the {role} window")
        end = max(placed)
        windows[role] = {
            "start": f"0x{lo:06X}", "end_exclusive": f"0x{hi:06X}",
            "rom_extent_bytes": end - lo, "window_margin_bytes": hi - end,
        }
    return {
        "windows": windows, "section_bytes": linked["alloc_bytes"],
        "entry_points": {root: f"0x{symbols[root]:06X}" for root in roots},
        "relocations": linked["relocations"], "target_ownership_verified": False,
        "shared_s01_tables": check_shared_tables(stage, compiler, run, "split.elf"),
    }


def stage_test(stage, engine_payloads):
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
    can_extension = [HERE / name for name in (*CAN_EXTENSION_FILES, "test_lfj8_h03_torque.c",
                    "test_lfj8_h03_dtc_can.c", "test_lfj8_h03_dtc_rx_queue.c", "test_lfj8_h03_torque_can.c",
                    "test_ta2005_engine_qualifier.c", "test_lfj8_h03_cycle.c", "test_lfj8_h03_phase_clock.c",
                    "test_lfj8_h03_engine_feed.c", "test_lfj8_h03_can13.c")]
    for item in (*sources, *headers, *dtc_inputs, *can_extension, HERE / "host_check.c", HERE / "test_lfj8_h03_atf.c",
                 HERE / "test_lfj8_h03_mmio.c", HERE / "test_lfj8_gear_observer.c",
                 HERE / "lfj8_h03_outputs.c", HERE / "test_lfj8_h03_outputs.c",
                 HERE / "lfj8_h03_takeover.c", HERE / "test_lfj8_h03_takeover.c",
                 ROOT / "controller/tests/test_runtime.c"):
        shutil.copyfile(item, stage / item.name)
    launch = "return integration_test(1, (char **)0);"
    if engine_payloads:
        rpm, coolant = (payload.hex() for payload in engine_payloads)
        launch = f'char *args[] = {{"sim", "{rpm}", "{coolant}", (char *)0}}; return integration_test(3, args);'
    (stage / "sim_crt.c").write_text(
        "int integration_test(int argc, char **argv);\n"
        "void __init(void) {}\n"
        "void __fini(void) {}\n"
        f"int main(void) {{ {launch} }}\n",
        encoding="ascii",
    )
    return [item.name for item in sources]


def check(base, bridge, controller, compiler, simulator_output, bosch_trace=None, address_model_output=None):
    report = {"source": identify_h03(base), "artifact_kind": "address_model_and_cpu_test"}
    engine_payloads = ()
    if bosch_trace is not None:
        trace_bytes = bosch_trace.read_bytes()
        trace = json.loads(trace_bytes)
        tx = trace["bosch_tx_to_tcm"]
        if (trace["status"] != "PASS_OFFLINE_ONLY" or trace["same_bosch_image_both_directions"] is not True
                or tx["sha256"] != trace["bosch_candidate_frame_probe"]["sha256"]):
            raise ValueError("Expected a passing bidirectional Bosch trace from one image")
        engine_payloads = tuple(bytes.fromhex(tx[key]) for key in ("0x0FA", "0x278"))
        if any(len(payload) != 8 for payload in engine_payloads):
            raise ValueError("The Bosch trace must contain two eight-byte engine messages")
        report["bosch_trace_replay"] = {
            "trace_sha256": sha256(trace_bytes.replace(b"\r\n", b"\n")).hexdigest(),
            "bosch_image_sha256": tx["sha256"], "0x0FA": engine_payloads[0].hex(), "0x278": engine_payloads[1].hex(),
        }

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
        control_manifest = json.loads((controller.parent / "manifest.json").read_text(encoding="utf-8"))
        if (control_manifest["architecture"] != "m32r" or
                control_manifest["sha256"].get(controller.name) != report["inputs"][controller.name]["sha256"]):
            raise ValueError("The controller object does not match its M32R build manifest")

        def run(*args):
            return subprocess.run([str(arg) for arg in args], cwd=stage, text=True, check=True,
                                  capture_output=True, timeout=60).stdout.strip()

        if run(compiler, "-dumpmachine") != "m32r-elf":
            raise ValueError("A bare-metal M32R compiler is required")
        report["compiler"] = run(compiler, "--version").splitlines()[0]
        nm = run(compiler, "-print-prog-name=nm")
        simulator = compiler.with_name(f"m32r-elf-run{compiler.suffix}")
        integration, selector_test, range_source, panel = stage_test(stage, engine_payloads)
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

        def link_model(name, object_file, roots=(), *, enforce_window=True):
            bounded = bool(roots) and enforce_window
            linker_script = "model.ld" if bounded else "unbounded-reference.ld"
            run(compiler, *TARGET, "-fno-use-linker-plugin", "-nostdlib", f"-Wl,-T,{linker_script}",
                object_file, "-o", name)
            linked, allocated = elf_info(stage / name, 2)
            if linked["relocations"] or any(
                start < FLASH_START or (bounded and start + size > FLASH_END) or flags & 1
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
            layout["fits_window"] = layout["window_margin_bytes"] >= 0
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
        def compile_modules(sources):
            objects = []
            for source in sources:
                obj = Path(source).with_suffix(".o").name
                run(compiler, *TARGET, *module_flags, "-c", source, "-o", obj)
                objects.append(obj)
            return objects

        dtc_objects = compile_modules(DTC_FILES)
        roots_with_dtc = H03_ROOTS + DTC_ROOTS
        run(compiler, *TARGET, "-r", *root_flags(roots_with_dtc), "compact.o", *dtc_objects,
            *libraries, "-o", "compact-with-dtc.o")
        # This one-window comparison predates the split layout. Report its
        # real excess if the complete application no longer fits.
        compact_with_dtc = link_model("compact-with-dtc.elf", "compact-with-dtc.o",
                                      roots_with_dtc, enforce_window=False)
        # Verify the bytes in the final linked image against the three S01 slices.
        compact_with_dtc["shared_s01_tables"] = check_shared_tables(stage, compiler, run, "compact-with-dtc.elf")
        compact_with_dtc["dtc_increment_bytes"] = compact_with_dtc["rom_extent_bytes"] - compact["rom_extent_bytes"]
        report["compact_address_model_with_dtc"] = compact_with_dtc
        can_extension_objects = compile_modules(CAN_EXTENSION_FILES)
        report["split_address_model"] = check_split_layout(
            stage, compiler, run, base, ("combined.o", "takeover.o"),
            dtc_objects + can_extension_objects, DTC_ROOTS + CAN_EXTENSION_ROOTS,
        )

        crt = run(compiler, *TARGET, "-print-file-name=crt0.o")
        run(compiler, *TARGET, *flags, "-Dmain=integration_test", "-c", integration,
            "-o", "integration.o")
        run(compiler, *TARGET, *flags, "-nostartfiles", crt, selector_test, panel, "sim_crt.c",
            "integration.o", "combined.o", *dtc_objects, "ta2005_engine_qualifier.o",
            "-Wl,-e,_start", "-Wl,--start-group", "-lc", "-lgloss", "-lgcc",
            "-Wl,--end-group", "-o", "sim.elf")
        result = json.loads(run(simulator, "sim.elf"))
        if (result.get("selector_adc_events"), result.get("selector_timeout")) != ("PASS", "PASS"):
            raise ValueError("The M32R integration check did not report a passing result")
        if engine_payloads and result != trace["host_controller_and_lfj8"]:
            raise ValueError("The M32R replay does not match the host results for the same Bosch frames")
        report["emulated_integration"] = result
        (stage / "component_crt.c").write_text(
            "void __init(void) {}\nvoid __fini(void) {}\n", encoding="ascii",
        )
        report["emulated_components"] = {}
        component_tests = [
            ("lfj8_io", "host_check.c", ("bridge.o",)),
            ("h03_atf", "test_lfj8_h03_atf.c", ("compact.o",)),
            ("h03_mmio", "test_lfj8_h03_mmio.c", ("compact.o",)),
            ("gear_observer", "test_lfj8_gear_observer.c", ("compact.o",)),
            ("h03_output_plan", "test_lfj8_h03_outputs.c", ("compact.o",)),
            ("h03_takeover", "test_lfj8_h03_takeover.c",
             ("combined.o", "takeover.o", "lfj8_h03_phase_clock.o")),
            ("toyota_gp_runtime", "test_runtime.c", ("compact.o",)),
            ("chery_dtc", "test_chery_dtc_link.c", ("compact-with-dtc.o",)),
            ("h03_torque_can", "test_lfj8_h03_torque.c", ("combined.o", "lfj8_h03_torque.o")),
            ("h03_dtc_can_io", "test_lfj8_h03_dtc_can.c", ("combined.o", *dtc_objects, "lfj8_h03_dtc_can.o")),
            ("h03_dtc_rx_queue", "test_lfj8_h03_dtc_rx_queue.c",
             ("combined.o", *dtc_objects, "lfj8_h03_dtc_can.o", "lfj8_h03_dtc_rx_queue.o")),
            ("h03_torque_can_io", "test_lfj8_h03_torque_can.c",
             ("combined.o", "lfj8_h03_torque.o", "lfj8_h03_torque_can.o")),
            ("h03_engine_qualifier", "test_ta2005_engine_qualifier.c", ("combined.o", "ta2005_engine_qualifier.o")),
            ("h03_cycle", "test_lfj8_h03_cycle.c",
             ("combined.o", "takeover.o", "lfj8_h03_phase_clock.o", "lfj8_h03_torque.o",
              "lfj8_h03_cycle.o")),
            ("h03_phase_clock", "test_lfj8_h03_phase_clock.c", ("lfj8_h03_phase_clock.o",)),
            ("h03_engine_feed", "test_lfj8_h03_engine_feed.c",
             ("combined.o", "chery_dtc.o", "ta2005_engine_qualifier.o", "lfj8_h03_engine_feed.o")),
            ("h03_can13", "test_lfj8_h03_can13.c",
             ("combined.o", *dtc_objects, "lfj8_h03_torque.o", "lfj8_h03_torque_can.o",
              "lfj8_h03_dtc_can.o", "lfj8_h03_can13.o")),
        ]
        for name, source, object_files in component_tests:
            elf = f"{name}.elf"
            test_flags = ["-DRBM_TEST_RUNTIME_STANDALONE"] if name == "toyota_gp_runtime" else []
            run(compiler, *TARGET, *flags, *test_flags, "-nostartfiles", crt, source, "component_crt.c",
                *object_files, "-Wl,-e,_start", "-Wl,--start-group", "-lc", "-lgloss", "-lgcc",
                "-Wl,--end-group", "-o", elf)
            report["emulated_components"][name] = run(simulator, elf)
        if simulator_output is not None:
            simulator_output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(stage / "sim.elf", simulator_output)
            report["simulator_elf"] = {
                "file": simulator_output.name, **elf_info(stage / "sim.elf", 2)[0],
            }
        if address_model_output is not None:
            address_model_output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(stage / "split.elf", address_model_output)
            report["split_address_model"]["elf"] = {
                "file": address_model_output.name, "sha256": sha256(address_model_output.read_bytes()).hexdigest(),
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
    parser.add_argument("--address-model-out", type=Path, help="optional ELF with the two checked address windows")
    parser.add_argument("--bosch-trace", type=Path, help="optional round-trip JSON from model.run_integrated")
    args = parser.parse_args()
    input_paths = {path.resolve() for path in (args.base, args.bridge, args.controller, args.gcc)}
    if args.bosch_trace is not None:
        input_paths.add(args.bosch_trace.resolve())
    if args.out.suffix.lower() != ".json" or args.out.resolve() in input_paths:
        parser.error("--out must be a separate JSON report")
    paths_in_use = input_paths | {args.out.resolve()}
    for name, destination in (("--sim-out", args.sim_out), ("--address-model-out", args.address_model_out)):
        if destination is not None:
            if destination.suffix.lower() != ".elf" or destination.resolve() in paths_in_use:
                parser.error(f"{name} must be a separate ELF")
            paths_in_use.add(destination.resolve())
    try:
        report = check(args.base, args.bridge, args.controller, args.gcc.resolve(), args.sim_out,
                       args.bosch_trace, args.address_model_out)
        report_text = json.dumps(report, indent=2) + "\n"
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report_text, encoding="utf-8")
        print(report_text, end="")
    except (ValueError, OSError, KeyError, StopIteration, subprocess.SubprocessError) as error:
        parser.exit(1, f"{getattr(error, 'stderr', None) or error}\n")


if __name__ == "__main__":
    main()
