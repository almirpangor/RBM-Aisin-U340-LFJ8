"""Build an audited H03 address model. Never emit a flashable BIN."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT=Path(__file__).resolve().parents[1]
LFJ8=ROOT/"targets/lfj8"
sys.path.insert(0,str(LFJ8))
import check_h03_link as legacy
import check_h03_sensor_config as sensor_config
from lfj8_h03_layout import (PROFILES,Window,PlacementError,read_elf,alloc_sections,
                            validate_windows,pack,linker_script,verify_linked,
                            symbol_bytes,raw_reference_patterns)
import lfj8_h03_application_placement as application_entries
import lfj8_h03_sensor_hooks as sensor_hooks
import lfj8_h03_dtc_rx_placement as dtc_rx
import lfj8_h03_service_placement as service
import lfj8_h03_ram_placement as ram_owner
import lfj8_h03_can_service_placement as can_service
import lfj8_h03_tx13_placement as tx13

EXTRA_ROOTS=(
    "rbm_u340e_step",
    "lfj8_button_filter_init","lfj8_range_control_step_with_buttons","lfj8_h03_range_snapshot",
    "rbm_u340e_runtime_restore_adaptation","rbm_u340e_s01_adaptation_baseline",
    "rbm_u340e_runtime_prepare_s01_cold",
    "lfj8_h03_atf_circuit_after_monitor",
    "chery_dtc_journal_encode","chery_dtc_journal_restore",
    "lfj8_h03_cycle_tick_with_load","lfj8_h03_cycle_tick_with_slu",
    "lfj8_h03_slu_secondary_from_baseline",
    "lfj8_h03_dtc_foreground_poll","lfj8_h03_dtc_rx_queue_capture_basic",
    "lfj8_h03_dtc_rx_dispatch_begin","lfj8_h03_dtc_rx_dispatch_skip_paired",
    "lfj8_h03_engine_feed_task2_with_model",
)
# Production modules received in later reviews. All their exported functions
# are retained, including entry points not yet called by the final application.
BINDING_MODULES=(
    "lfj8_h03_output_inhibit.c","lfj8_h03_sensor_feed.c","lfj8_h03_application.c",
    "lfj8_h03_can_owner.c","lfj8_h03_dtc_target.c","lfj8_h03_input_binding.c",
    "lfj8_h03_input_target.c","lfj8_h03_nvm.c","lfj8_h03_sensor_target.c",
    "lfj8_h03_atf_target.c","lfj8_h03_atf_tml0.c",
    "lfj8_h03_service_guard.c", "lfj8_h03_button_capture.c",
)
SENSOR_ASSEMBLY = ("h03_sensor_hooks.S", "h03_atf_hooks.S")
APPLICATION_ENTRY_SOURCES = ("h03_application_hooks.S", "h03_phase_startup_hook.S", "h03_phase_release_hook.S")
APPLICATION_REDIRECT_SOURCE = "h03_application_redirects.S"
APPLICATION_CALLBACKS = (
    "rbm_h03_application_cold_gate", "rbm_h03_phase_startup_callback",
    "rbm_h03_application_foreground_callback", "rbm_h03_phase_release_callback",
)
PROFILED_BINDINGS = ("lfj8_h03_application_binding.c", "lfj8_h03_target_platform.c")
TOYOTA_RELEASE_FIELD = "control/toyota_release"
TOYOTA_RELEASE_SYMBOL = "rbm_h03_toyota_release_state"


def save(path,data):
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8",newline="\n")


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def extra_binding_sources(values):
    """Explicit production providers; keep fixtures and outside files out."""
    sources = []
    for value in values:
        path = Path(value)
        path = (ROOT / path).resolve() if not path.is_absolute() else path.resolve()
        if (not path.is_relative_to(LFJ8.resolve()) or not path.is_file()
                or path.suffix not in (".c", ".S")
                or path.name.startswith("test_") or "fixture" in path.name.lower()):
            raise ValueError("Expected a native H03 binding source: " + str(value))
        if path in sources:
            raise ValueError("Duplicate native H03 binding source: " + str(value))
        sources.append(path)
    return sources


def readonly_objects(elf, path):
    """Whole constant sections with no relocations or executable bytes."""
    data = path.read_bytes()
    table = struct.unpack_from(">I", data, 32)[0]
    stride, count = struct.unpack_from(">HH", data, 46)
    relocations = set()
    for index in range(count):
        row = struct.unpack_from(">10I", data, table + index * stride)
        if row[1] in (4, 9) and row[5]:
            relocations.add(row[7])  # ELF sh_info names the relocated section.
    result = {}
    for section in elf["sections"]:
        if (section["flags"] != 2 or section["type"] != 1 or not section["name"].startswith(".rodata.")
                or not section["size"] or section["index"] in relocations):
            continue
        result[section["name"]] = (section["name"], section["size"], sha256(section["data"]).hexdigest())
    return result


def pack_resident_constants(resident, upper, windows, eligible, resident_window):
    """Keep the resident code fixed; spill only approved tables after it."""
    base = pack(resident, (resident_window,))
    try:
        return base + pack(upper, windows), []
    except PlacementError as error:
        original_error = error
    start = (max((p["address"] + p["bytes"] for p in base),
                 default=resident_window.start) + 3) & ~3
    if start >= resident_window.end:
        raise original_error
    spare = Window(resident_window.name, start, resident_window.end)
    moved = []
    candidates = sorted((s for s in upper if s["name"] in eligible and
                         s["flags"] == 2 and s["type"] == 1),
                        key=lambda s: (-s["size"], -s["alignment"], s["name"]))
    for candidate in candidates:
        try:
            low = pack([*moved, candidate], (spare,))
        except PlacementError:
            continue
        moved.append(candidate)
        names = {s["name"] for s in moved}
        try:
            high = pack([s for s in upper if s["name"] not in names], windows)
            return base + low + high, sorted(names)
        except PlacementError:
            continue
    raise original_error


def invalidate_outputs(output,inputs):
    artifacts=[output/name for name in ("layout.elf","early-irq.elf","placement.ld","layout.json","summary.json")]
    if any(p.resolve()==source.resolve() or (p.exists() and source.exists() and p.samefile(source))
           for p in artifacts for source in inputs):
        raise ValueError("Output artifacts must not overwrite inputs")
    output.mkdir(parents=True,exist_ok=True)
    for path in artifacts:
        if path.exists():
            path.unlink()


def read_storage_report(path):
    report=json.loads(path.read_text(encoding="utf-8"))
    if report.get("artifact_kind") != "M32R_ABI_storage_address_model":
        raise ValueError("Expected the typed H03 storage report")
    sources=json.loads((ROOT/"data/sources.json").read_text(encoding="utf-8"))
    expected=next(s for s in sources["supporting_materials"] if s["id"]=="H03")
    if report.get("base",{}).get("sha256") != expected["sha256"]:
        raise ValueError("RAM inventory uses a different base")
    hashes=report.get("input_sha256",{})
    if "targets/lfj8/lfj8_h03_storage.h" not in hashes:
        raise ValueError("RAM inventory has no typed storage provenance")
    for name,expected_hash in hashes.items():
        source=(ROOT/name).resolve()
        if not source.is_relative_to(ROOT) or sha256(source.read_bytes().replace(b"\r\n",b"\n")).hexdigest()!=expected_hash:
            raise ValueError("RAM inventory is stale: "+name)
    from check_h03_storage import address_plan
    if address_plan(report["fields"]) != report["blocks"]:
        raise ValueError("RAM inventory block geometry was altered")
    return report


def storage_space(path):
    if path is None:
        return ()
    # Reserve the complete existing inventory, then place new native globals
    # only in remaining candidate space. This is not a startup implementation.
    blocks=read_storage_report(path)["blocks"]
    windows=tuple(Window(name,start,end) for name,start,end in (
        ("primary_ram_extra",blocks["control"]["end_exclusive"],0x807000),
        ("secondary_ram_extra",blocks["workspace"]["end_exclusive"],0x809600)) if start<end)
    validate_windows(windows)
    if blocks["communication"]["end_exclusive"]>blocks["workspace"]["address"]:
        raise ValueError("Overlapping prior storage inventory")
    return windows


def toyota_release_range(storage):
    field = storage["fields"].get(TOYOTA_RELEASE_FIELD)
    if field is None:
        return None
    control = storage["blocks"]["control"]
    start = control["address"] + field["offset"]
    end = start + field["bytes"]
    if (field["bytes"] != 16 or field["alignment"] != 4 or start % 4 or
            not control["address"] <= start < end <= control["end_exclusive"]):
        raise ValueError("Invalid M32R Toyota release RAM field")
    for name, other in storage["fields"].items():
        if name != TOYOTA_RELEASE_FIELD and name.startswith("control/"):
            other_start = control["address"] + other["offset"]
            if start < other_start + other["bytes"] and other_start < end:
                raise ValueError("Toyota release RAM overlaps " + name)
    return {"field": TOYOTA_RELEASE_FIELD, "symbol": TOYOTA_RELEASE_SYMBOL, "address": start,
            "end_exclusive": end, "bytes": field["bytes"], "alignment": field["alignment"]}


def execute_placed_code(args, elf, stage, run, flags):
    """Simulator harness at 1 MiB; production bytes keep their exact VMAs."""
    payload=[]
    options=[]
    fixed={}
    for i,section in enumerate(alloc_sections(elf)):
        name=f".fixed{i:04d}"
        fixed[name]=section
        kind="nobits" if section["type"]==8 else "progbits"
        attrs="aw" if section["flags"]&1 else ("ax" if section["flags"]&4 else "a")
        payload.append(f'.section {name},"{attrs}",@{kind}')
        payload.extend([f".global __h03_keep_{i}",f"__h03_keep_{i}:"])
        if kind=="nobits":
            payload.append(f'.space {section["size"]}')
        else:
            filename=f"payload{i:04d}.dat"
            (stage/filename).write_bytes(section["data"])
            payload.append(f'.incbin "{filename}"')
        options.append(f'--section-start={name}={section["address"]:#x}')
        options.append(f"--undefined=__h03_keep_{i}")
    (stage/"payload.S").write_text("\n".join(payload)+"\n",encoding="ascii")
    (stage/"fixed-sections.rsp").write_text("\n".join(options)+"\n",encoding="ascii")
    run(args.gcc,*flags,"-c","payload.S","-o","payload.o")
    (stage/"fixture_crt.c").write_text("void __init(void) {}\nvoid __fini(void) {}\n",encoding="ascii")
    crt=run(args.gcc,*flags,"-print-file-name=crt0.o")
    cases=[
        ("runtime",ROOT/"controller/tests/test_runtime.c",["-DRBM_TEST_RUNTIME_STANDALONE"]),
        ("mode-policy",ROOT/"controller/tests/test_mode_policy.c",[]),
        ("cycle",LFJ8/"test_lfj8_h03_cycle.c",[]),
        ("cycle-load",LFJ8/"test_lfj8_h03_cycle_load.c",[]),
        ("can13",LFJ8/"test_lfj8_h03_can13.c",[]),
        ("diagnostic-session",ROOT/"diagnostics/test_chery_dtc_link.c",[]),
    ]
    if "lfj8_h03_sensor_feed_snapshot" in elf["symbols"]:
        cases.append(("sensor-feed",LFJ8/"test_lfj8_h03_sensor_feed.c",[]))
    includes=[ROOT/"controller/include",ROOT/"controller/vendor/toyota/include",LFJ8,ROOT/"diagnostics"]
    rows=[]
    for label,source,defines in cases:
        executable="cpu-"+label+".elf"
        run(args.gcc,*flags,"-Os","-std=c11","-ffunction-sections","-fdata-sections",
            *(x for p in includes for x in ("-I",p)),*defines,"-nostartfiles",crt,source,
            "fixture_crt.c","payload.o","-Wl,--just-symbols=layout.elf",
            "-Wl,@fixed-sections.rsp","-Wl,-Ttext=0x100000,-e,_start,--gc-sections",
            "-Wl,--start-group","-lc","-lgloss","-lgcc","-Wl,--end-group","-o",executable)
        fixture=read_elf(stage/executable,2)
        loaded={s["name"]:s for s in fixture["sections"]}
        for name,original in fixed.items():
            actual=loaded.get(name)
            if actual is None or (actual["address"],actual["size"],actual["data"]) != (
                    original["address"],original["size"],original["data"]):
                raise ValueError("Harness altered or discarded placed production bytes: "+name)
        for name,symbol in elf["symbols"].items():
            if symbol["section"] and name in fixture["symbols"]:
                if fixture["symbols"][name]["address"]!=symbol["address"]:
                    raise ValueError("Harness moved production symbol: "+name)
        output=run(args.gcc.with_name("m32r-elf-run"+args.gcc.suffix),executable)
        if not output.strip():
            raise ValueError("Placed-code CPU test returned no result: "+label)
        rows.append({"case":label,"fixture":source.relative_to(ROOT).as_posix(),
                     "fixture_sha256":digest(source),"output":output,"production_bytes_unchanged":True})
    return {"scope":"Only the fixed linked production bytes execute at their placed addresses; monitor CRT and tests are outside target Flash",
            "hardware_tested":False,"cases":rows,
            "separate_fixture_checks":[{"fixture":"targets/lfj8/test_lfj8_h03_torque.c",
                "reason":"Uses the standalone donor torque wrapper omitted from production; the production workspace cycle calls torque_step. Run the standard component suite separately."}]}


def sensor_placement(rom, elf, provisional=None):
    symbols = elf["symbols"]
    addresses = {}
    if provisional is not None:
        by_section = {entry["section"]: entry["address"] for entry in provisional}
        for _, hook, _ in sensor_hooks.SENSOR_HOOKS:
            symbol = symbols.get(hook)
            if symbol is None or not 0 < symbol["section"] < len(elf["sections"]):
                raise ValueError("Missing retained H03 sensor hook: "+hook)
            section = elf["sections"][symbol["section"]]
            if (not section["flags"] & 4 or symbol["address"] >= section["size"]
                    or section["name"] not in by_section):
                raise ValueError("Sensor hook is outside the provisional executable sections: "+hook)
            addresses[hook] = by_section[section["name"]] + symbol["address"]
    else:
        for name, address in sensor_hooks.STOCK_SYMBOLS.items():
            symbol = symbols.get(name)
            if symbol is None or symbol["section"] != 0xFFF1 or symbol["address"] != address:
                raise ValueError("H03 sensor continuation is not the pinned OEM address: "+name)
        addresses = {hook: symbols[hook]["address"] for _, hook, _ in sensor_hooks.SENSOR_HOOKS
                     if hook in symbols}
    return {"status": "PROVISIONAL_UNLINKED" if provisional is not None else "LINKED_ADDRESS_MODEL",
            "installed": False, "continuations": sensor_hooks.STOCK_SYMBOLS,
            "patches": sensor_hooks.patch_plan(rom, addresses)}


def link_placed_roots(args, stage, run, flags, placement, bindings, roots, name, *, objects=("retained.o",)):
    """Link an independent closure at the addresses from the common plan."""
    obj = f"{name}.o"
    run(args.gcc, *flags, "-r", "-nostdlib", "-Wl,--gc-sections",
        *(f"-Wl,--undefined={root}" for root in roots), *objects, "-o", obj)
    retained = read_elf(stage / obj, 1)
    required = {symbol for symbol, record in retained["symbols"].items() if record["section"] == 0}
    if required - bindings.keys():
        raise ValueError(f"{name} graph requires other providers: {sorted(required - bindings.keys())}")
    names = {section["name"] for section in alloc_sections(retained)}
    selected = [item for item in placement if item["section"] in names]
    if names != {item["section"] for item in selected}:
        raise ValueError(f"A {name} section is missing from the common layout")
    pinned = "".join(f"{symbol} = {bindings[symbol]:#x};\n" for symbol in sorted(required))
    script = pinned + linker_script(selected, object_name=obj, entry=roots[0])
    (stage / f"{name}.ld").write_text(script, encoding="ascii")
    run(args.gcc, *flags, "-nostdlib", f"-Wl,-T,{name}.ld", obj, "-o", f"{name}.elf")
    path = stage / f"{name}.elf"
    linked = read_elf(path, 2)
    verify_linked(linked, selected, roots)
    return path, linked, selected


def application_callback_addresses(elf, placements, windows):
    by_section = {item["section"]: item for item in placements}
    addresses = {}
    for name in APPLICATION_CALLBACKS:
        symbol = elf["symbols"].get(name, {})
        index = symbol.get("section", 0)
        if not 0 < index < len(elf["sections"]):
            raise ValueError(f"Missing retained H03 application callback: {name}")
        section = elf["sections"][index]
        entry = by_section.get(section["name"])
        offset = symbol["address"]
        if section["type"] != 1 or section["flags"] & 7 != 6 or entry is None or not 0 <= offset < entry["bytes"]:
            raise ValueError(f"H03 application callback is outside a placed executable section: {name}")
        address = entry["address"] + offset
        if address % 4 or not any(window.start <= address < window.end for window in windows):
            raise ValueError(f"H03 application callback escaped the upper Flash plan: {name}")
        addresses[name] = address
    return addresses


def early_irq_model(args, stage, run, flags, rom, placement, bindings, ranges, pointer):
    roots = (*service.COMMON_ROOTS, *dtc_rx.REDIRECT_ROOTS)
    with_writers = getattr(args, "with_service_guard", False)
    if with_writers:
        roots += service.WRITER_ROOTS
    path, linked, selected = link_placed_roots(args, stage, run, flags, placement, bindings, roots, "early-irq")
    # Verify the independent graph against the same fixed sites and policy.
    model = {"elf_sha256": linked["sha256"], "placements": selected, "roots": list(roots),
             "irq_pointer": pointer, "policy_ranges": ranges,
             "artifact_kind": "EARLY_IRQ_DMA4_SIMULATOR_ONLY"}
    if with_writers:
        model["service_writers"] = service.verify_writers(rom, linked, ranges, dtc_rx.RX_WINDOW)
    service.early_overlay(rom, path, model)
    shutil.copyfile(path, args.out / "early-irq.elf")
    return model


def build(args):
    application_profile = getattr(args, "application_profile", None)
    extras = extra_binding_sources(getattr(args, "binding_source", ()))
    if extras and (not args.with_bindings or application_profile is None):
        raise ValueError("Extra native bindings require --with-bindings and --application-profile")
    with_application_entries = getattr(args, "with_application_entries", False)
    if with_application_entries and application_profile is None:
        raise ValueError("H03 application entries require --application-profile")
    release_ram = None
    if application_profile is not None:
        application_profile = Path(application_profile).resolve()
        if not args.with_bindings or not application_profile.is_file():
            raise ValueError("Application profile requires --with-bindings and an existing header")
        if args.storage_report is None:
            raise ValueError("Application profile requires a typed --storage-report")
        release_ram = toyota_release_range(read_storage_report(args.storage_report))
    clock_reference = getattr(args, "sensor_clock_reference", None)
    calibration_profile = getattr(args, "sensor_calibration_profile", None)
    sensor_report = None
    sensor_source = None
    if clock_reference is not None or calibration_profile is not None:
        if not args.with_bindings or clock_reference is None or calibration_profile is None:
            raise ValueError("Sensor calibration requires --with-bindings and both sensor input files")
        sensor_report = sensor_config.check_inputs(args.base, clock_reference, calibration_profile)
        sensor_source = sensor_config.config_source(sensor_report).encode("utf-8")

    identity=legacy.identify_h03(args.base)
    rom=args.base.read_bytes()
    if sha256(rom).hexdigest() != identity["sha256"]:
        raise ValueError("H03 changed after identification")
    if args.with_bindings:
        sensor_hooks.validate_stock(rom)
    application_source = application_entries.assembly(rom) if with_application_entries else None
    windows=PROFILES[args.profile]
    with_dtc_rx = getattr(args, "with_dtc_rx", False)
    with_resident_constants = getattr(args, "with_resident_constants", False)
    if with_resident_constants and not with_dtc_rx:
        raise ValueError("Resident constants require --with-dtc-rx")
    with_dma4 = getattr(args, "with_dma4_guard", False)
    with_can_service = getattr(args, "with_can_service", False)
    with_service_guard = getattr(args, "with_service_guard", False)
    if with_service_guard:
        if not with_dma4:
            raise ValueError("The resident service writers require --with-dma4-guard and its RAM policy")
        service.verify_stock(rom)
    with_ram_owner = getattr(args, "with_ram_owner", False)
    if with_ram_owner and not with_service_guard:
        raise ValueError("The RAM owner requires --with-service-guard")
    if with_can_service:
        if not (with_dtc_rx and args.with_bindings and args.storage_report):
            raise ValueError("CAN service requires --with-bindings, --with-dtc-rx and --storage-report")
        can_ram = can_service.typed_alias_ranges(read_storage_report(args.storage_report))
        tx13.validate_stock(rom)
    if with_dma4:
        if not (with_dtc_rx and args.with_bindings and args.storage_report):
            raise ValueError("DMA4 and early IRQ protection require --with-bindings, --with-dtc-rx and --storage-report")
        storage = read_storage_report(args.storage_report)
        if with_ram_owner:
            confirmed_ram = ram_owner.confirmed_ranges(rom, storage["blocks"])
            if application_profile is not None:
                confirmed_ram.update(ram_owner.application_addresses(storage))
        available = storage_space(args.storage_report)
        pointer_layout = pack(({"name": ".bss.irq_target", "type": 8, "flags": 3,
                                "size": 4, "alignment": 4},), available)[0]
        pointer = pointer_layout["address"]
        blocks = {name: (block["address"], block["end_exclusive"])
                  for name, block in storage["blocks"].items()}
        policy = service.policy_ranges(blocks, ((pointer, pointer + 4),))
        ram_windows = tuple(
            Window(w.name, pointer + 4, w.end) if w.name == pointer_layout["window"] else w
            for w in available if w.name != pointer_layout["window"] or pointer + 4 < w.end
        )
        pointer_layout["window"] = "early_irq_pointer"
        service.verify_stock(rom, (site for site, _ in service.COMMON_REDIRECTS))
    flash_windows = (*windows, dtc_rx.RX_WINDOW) if with_dtc_rx else windows
    owner_address = None
    fixed_windows = tuple(
        Window(window.name.removeprefix("."), window.start, window.end)
        for window in application_entries.REDIRECT_WINDOWS
    ) if with_application_entries else ()
    if with_dtc_rx:
        if not args.with_bindings or args.storage_report is None:
            raise ValueError("Resident RX needs --with-bindings and a typed --storage-report")
        dtc_rx.validate_stock(rom)
        # The two pinned OEM words are occupied, unlike the packing windows.
        fixed_windows = (*fixed_windows, *dtc_rx.REDIRECT_WINDOWS, *(service.COMMON_WINDOWS if with_dma4 else ()),
                         *(service.WRITER_WINDOWS if with_service_guard else ()),
                         *((tx13.REDIRECT_WINDOW,) if with_can_service else ()))
        storage_space(args.storage_report)
        owner_address = dtc_rx.owner_address(json.loads(args.storage_report.read_text(encoding="utf-8")))
    validate_windows((*flash_windows, *fixed_windows))
    validate_windows(flash_windows,rom)
    controller_manifest=json.loads((args.controller.parent/"manifest.json").read_text(encoding="utf-8"))
    bridge_manifest=json.loads((args.bridge.parent/"build-manifest.json").read_text(encoding="utf-8"))
    if (controller_manifest["architecture"]!="m32r" or
            controller_manifest["sha256"].get(args.controller.name)!=digest(args.controller)):
        raise ValueError("Controller object identity mismatch")
    if (bridge_manifest["m32r_base"]["sha256"]!=identity["sha256"] or
            bridge_manifest["artifacts"][args.bridge.name]["sha256"]!=digest(args.bridge)):
        raise ValueError("Bridge object identity mismatch")
    if controller_manifest.get("source_hash_format")!="lf" or not controller_manifest.get("source_sha256"):
        raise ValueError("Rebuild the controller with source provenance")
    for name,expected in controller_manifest["source_sha256"].items():
        source=(ROOT/name).resolve()
        if not source.is_relative_to(ROOT/"controller") or sha256(source.read_bytes().replace(b"\r\n",b"\n")).hexdigest()!=expected:
            raise ValueError("Stale controller object: "+name)
    for name,entry in bridge_manifest["sources"].items():
        source=(LFJ8/name).resolve()
        if not source.is_relative_to(ROOT) or digest(source)!=entry["sha256"]:
            raise ValueError("Stale bridge object: "+name)
    flags=[f.replace("-mmodel=medium","-mmodel="+args.memory_model) for f in legacy.TARGET]
    for manifest_flags in (controller_manifest["flags"],
                           bridge_manifest["artifacts"][args.bridge.name]["target_flags"]):
        models=[flag for flag in manifest_flags if flag.startswith("-mmodel=")]
        if models!=["-mmodel="+args.memory_model]:
            raise ValueError("Rebuild both objects with the requested compiler memory model")
    modules=[ROOT/"diagnostics"/name for name in (*legacy.DTC_FILES,"chery_dtc_journal.c")]
    modules += [LFJ8/name for name in ("lfj8_range_control.c","lfj8_h03_outputs.c","lfj8_h03_takeover.c",
                                      *legacy.CAN_EXTENSION_FILES,"lfj8_h03_slu.c","lfj8_h03_dtc_foreground.c")]
    bindings=[LFJ8/name for name in BINDING_MODULES if (LFJ8/name).is_file()] if args.with_bindings else []
    if application_profile is not None:
        bindings.extend(LFJ8 / name for name in PROFILED_BINDINGS)
    bindings.extend(source for source in extras if source not in bindings)
    if args.with_bindings:
        bindings.extend(LFJ8/name for name in SENSOR_ASSEMBLY)
    if with_application_entries:
        bindings.extend(LFJ8 / name for name in APPLICATION_ENTRY_SOURCES)
    if with_dtc_rx:
        bindings.extend(LFJ8/name for name in dtc_rx.MODULES)
    if with_dma4:
        bindings.append(LFJ8 / "h03_dma4_guard.S")
    if with_service_guard:
        bindings.append(LFJ8 / "h03_service_guard_hooks.S")
    if with_ram_owner:
        bindings.extend(LFJ8 / name for name in ram_owner.MODULES if LFJ8 / name not in bindings)
    if with_can_service:
        bindings.extend(LFJ8 / name for name in (*can_service.SERVICE_MODULES, *tx13.MODULES))
    modules=list(dict.fromkeys([*modules,*bindings]))
    roots=set((*legacy.H03_ROOTS,*legacy.DTC_ROOTS,*legacy.CAN_EXTENSION_ROOTS,*EXTRA_ROOTS))
    if with_dtc_rx:
        roots.update(dtc_rx.RX_ROOTS)
        roots.update(dtc_rx.REDIRECT_ROOTS)
    if with_service_guard:
        roots.update(service.WRITER_ROOTS)
    application_roots = tuple(site.root for site in application_entries.REDIRECTS)
    if with_application_entries:
        roots.update(application_roots)
    report={"base":identity,"profile":args.profile,"compiler_memory_model":args.memory_model,
            "input_objects":{p.name:digest(p) for p in (args.bridge,args.controller)},
            "input_sources":{p.relative_to(ROOT).as_posix():digest(p) for p in modules},
            "bindings_included":[p.name for p in bindings],
            "bindings_not_present":[name for name in BINDING_MODULES if not (LFJ8/name).is_file()],
            "raw_reference_patterns":raw_reference_patterns(rom,flash_windows),
            "hardware_verified":False,"target_ownership_verified":False,"flashable_image":None}
    report["extra_binding_sources"] = [path.relative_to(ROOT).as_posix() for path in extras]
    report["translation_units"] = {}
    if sensor_source is not None:
        generator = Path(sensor_config.__file__).resolve()
        report["input_sources"][generator.relative_to(ROOT).as_posix()] = digest(generator)
        report["bindings_included"].append("h03_sensor_config.c")
        report["sensor_config"] = {**sensor_report, "generated_source_sha256": sha256(sensor_source).hexdigest()}
    report["application_profile"] = ({"path": str(application_profile),
        "sha256": digest(application_profile), "hardware_qualified_by_this_tool": False}
        if application_profile is not None else None)
    report["profiled_bindings_omitted"] = ([] if application_profile is not None else
        [f"{name}: requires an explicit application profile" for name in PROFILED_BINDINGS])
    if application_profile is not None:
        report["target_platform"] = {"release_ram": release_ram, "storage_report_sha256": digest(args.storage_report)}
    if args.with_bindings:
        path = Path(sensor_hooks.__file__).resolve()
        report["input_sources"][path.relative_to(ROOT).as_posix()] = digest(path)
    if with_dtc_rx:
        path = Path(dtc_rx.__file__).resolve()
        report["input_sources"][path.relative_to(ROOT).as_posix()] = digest(path)
    if with_dma4:
        path = Path(service.__file__).resolve()
        report["input_sources"][path.relative_to(ROOT).as_posix()] = digest(path)
    if with_can_service:
        for provider in (can_service, tx13):
            path = Path(provider.__file__).resolve()
            report["input_sources"][path.relative_to(ROOT).as_posix()] = digest(path)
    if with_ram_owner:
        path = Path(ram_owner.__file__).resolve()
        report["input_sources"][path.relative_to(ROOT).as_posix()] = digest(path)
    if with_application_entries:
        path = Path(application_entries.__file__).resolve()
        report["input_sources"][path.relative_to(ROOT).as_posix()] = digest(path)
    with TemporaryDirectory(prefix="rbm-h03-placement-") as folder:
        stage=Path(folder)
        if application_source is not None:
            redirects = stage / APPLICATION_REDIRECT_SOURCE
            redirects.write_text(application_source, encoding="ascii", newline="\n")
            modules.append(redirects)
            report["input_sources"]["generated/" + APPLICATION_REDIRECT_SOURCE] = digest(redirects)
        if sensor_source is not None:
            generated = stage / "h03_sensor_config.c"
            generated.write_bytes(sensor_source)
            modules.append(generated)
            bindings.append(generated)
        if with_dma4:
            generated = stage / "h03_service_policy.c"
            generated.write_text(service.policy_source(policy), encoding="ascii")
            modules.append(generated)
            report["input_sources"]["generated/h03_service_policy.c"] = digest(generated)
        if with_service_guard:
            redirects = stage / "h03_service_writer_redirects.S"
            service.write_redirects(redirects, service.SITES, service.WRITER_ROOTS)
            modules.append(redirects)
            report["input_sources"]["generated/h03_service_writer_redirects.S"] = digest(redirects)

        def run(*items):
            return subprocess.run([str(i) for i in items],cwd=stage,check=True,capture_output=True,
                                  text=True,timeout=120).stdout.strip()
        if run(args.gcc,"-dumpmachine")!="m32r-elf":
            raise ValueError("Expected M32R bare-metal compiler")
        shutil.copy2(args.bridge,stage/"bridge.o")
        shutil.copy2(args.controller,stage/"controller.o")
        objects=["bridge.o","controller.o"]
        module_flags=["-Os","-std=c11","-Wall","-Wextra","-Werror","-Wno-missing-braces",
                      "-Wno-missing-field-initializers","-ffreestanding","-fno-builtin","-fno-common",
                      "-ffunction-sections","-fdata-sections"]
        includes=[ROOT/"controller/include",ROOT/"controller/vendor/toyota/include",LFJ8,ROOT/"diagnostics"]
        nm=run(args.gcc,"-print-prog-name=nm")
        for source in modules:
            name=source.with_suffix(".o").name
            if name in objects or source.name.startswith("test_") or "fixture" in source.name:
                raise ValueError("Ambiguous or test-only input module")
            profile_flags = (["-I", application_profile.parent,
                '-DRBM_H03_APPLICATION_PROFILE="' + application_profile.name + '"']
                if source.name in PROFILED_BINDINGS or source in extras else [])
            if source.name == "h03_dma4_guard.S":
                profile_flags.append("-DRBM_H03_COMMON_DMA4_GUARD=1")
            # The profile can include other domain headers. A single top-level
            # header digest does not identify the code actually compiled.
            preprocessed = run(args.gcc, *flags, *module_flags, *profile_flags,
                *(x for p in includes for x in ("-I", p)), "-E", "-P", source)
            report["translation_units"][source.name] = {
                "preprocessed_sha256": sha256(preprocessed.encode("utf-8")).hexdigest(),
                "profile_enabled": bool(application_profile is not None and
                    (source.name in PROFILED_BINDINGS or source in extras)),
            }
            run(args.gcc,*flags,*module_flags,*profile_flags,*(x for p in includes for x in ("-I",p)),
                "-c",source,"-o",name)
            objects.append(name)
            if source in bindings:
                for line in run(nm,"-g","--defined-only",name).splitlines():
                    fields=line.split()
                    if len(fields)==3 and fields[1] in ("T","W"):
                        roots.add(fields[2])
        roots=sorted(roots)
        options=[f"-Wl,--undefined={root}" for root in roots]
        run(args.gcc,*flags,"-fno-use-linker-plugin","-r","-nostdlib","-Wl,--gc-sections",
            *options,*objects,*legacy.LIBRARIES,"-o","retained.o")
        retained=read_elf(stage/"retained.o",1)
        stock_symbols = sensor_hooks.STOCK_SYMBOLS if args.with_bindings else {}
        for name in stock_symbols:
            if retained["symbols"].get(name, {}).get("section") != 0:
                raise ValueError("Unexpected definition or missing reference for H03 sensor continuation: "+name)
        native_bindings = dict(stock_symbols)
        if with_application_entries:
            for name in application_entries.STOCK_SYMBOLS:
                if retained["symbols"].get(name, {}).get("section") != 0:
                    raise ValueError("Unexpected definition or missing H03 application continuation: " + name)
            native_bindings.update(application_entries.STOCK_SYMBOLS)
        platform_flash = set()
        if application_profile is not None:
            if retained["symbols"].get(TOYOTA_RELEASE_SYMBOL, {}).get("section") != 0:
                raise ValueError("The H03 Toyota platform must reference the single typed release RAM alias")
            if release_ram is not None:
                native_bindings[TOYOTA_RELEASE_SYMBOL] = release_ram["address"]
            platform = read_elf(stage / "lfj8_h03_target_platform.o", 1)
            platform_flash = {section["name"] for section in alloc_sections(platform) if not section["flags"] & 1}
        if with_dtc_rx:
            for name in dtc_rx.STOCK_SYMBOLS:
                if retained["symbols"].get(name, {}).get("section") != 0:
                    raise ValueError("Unexpected definition or missing reference for DTC RX continuation: "+name)
            owner_symbol = retained["symbols"].get("h03_can_owner", {})
            if (owner_symbol.get("section") != 0 and
                    (owner_symbol.get("section"), owner_symbol.get("address")) != (0xFFF1, owner_address)):
                raise ValueError("The DTC RX binding must use the existing typed CAN owner")
            native_bindings.update(dtc_rx.STOCK_SYMBOLS, h03_can_owner=owner_address)
        if with_dma4:
            native_bindings.update(service.COMMON_STOCK_TARGETS, h03_dtc_irq_pointer=pointer)
        if with_service_guard:
            for name in service.STOCK_TARGETS:
                if retained["symbols"].get(name, {}).get("section") != 0:
                    raise ValueError("Expected an undefined H03 service writer continuation: " + name)
            native_bindings.update(service.STOCK_TARGETS)
        if with_can_service:
            if retained["symbols"].get(tx13.RESUME, {}).get("section") != 0:
                raise ValueError("Expected the OEM H03 TX13 continuation reference")
            aliases = can_service.referenced_aliases(retained["symbols"], can_ram, native_bindings)
            native_bindings.update(aliases, **{tx13.RESUME: tx13.SITE + 4})
            report["can_service"] = {"typed_aliases": {name: can_ram[name] for name in aliases},
                                     "allocates_new_alias_storage": False}
        if with_ram_owner:
            ram_aliases = ram_owner.bind(retained["symbols"], confirmed_ram, native_bindings)
            native_bindings.update(ram_aliases)
            report["ram_owner"] = {
                "absolute_aliases": ram_aliases,
                "storage_report_sha256": digest(args.storage_report),
                "stock_stack_initialization_sites": list(ram_owner.STACK_STARTUP),
                "unresolved_qualification": [
                    name for name in ram_owner.REQUIRED_QUALIFICATION
                    if retained["symbols"][name]["section"] == 0 and name not in native_bindings
                ],
            }
        unresolved=[name for name,symbol in retained["symbols"].items()
                    if symbol["section"]==0 and name not in native_bindings]
        sections=alloc_sections(retained)
        flash=[s for s in sections if not s["flags"]&1]
        ram=[s for s in sections if s["flags"]&1]
        report.update(required_roots=roots,retained_sections=len(sections),
                      flash_payload_bytes=sum(s["size"] for s in flash),
                      new_static_ram_bytes=sum(s["size"] for s in ram))
        if with_application_entries:
            hook_sections = {f".text.{site.hook}" for site in application_entries.REDIRECTS}
            report["application_entries"] = {
                "status": "AWAITING_PLACEMENT",
                "fixed_branch_bytes": sum(window.end - window.start for window in application_entries.REDIRECT_WINDOWS),
                "wrapper_bytes": sum(section["size"] for section in flash if section["name"] in hook_sections),
                "continuations": application_entries.STOCK_SYMBOLS,
            }

        def place_flash():
            fixed, remaining = application_entries.fixed_redirects(flash) if with_application_entries else ([], flash)
            if not with_dtc_rx:
                return fixed + pack(remaining, windows)
            names = dtc_rx.closure_sections(run, args.gcc, flags, stage)
            dtc_fixed, remaining = dtc_rx.fixed_redirects(remaining)
            fixed.extend(dtc_fixed)
            if with_can_service:
                tx_fixed, remaining = tx13.fixed_redirect(remaining)
                fixed.extend(tx_fixed)
            if with_dma4:
                service_fixed, remaining = service.fixed_common_redirects(remaining)
                fixed.extend(service_fixed)
                names.add(".text.rbm_h03_early_irq_gate")
            if with_service_guard:
                writer_fixed, remaining = service.fixed_writer_redirects(remaining)
                fixed.extend(writer_fixed)
                writer_names = service.writer_closure_sections(run, args.gcc, flags, stage)
                report["service_writer_resident_bytes"] = sum(
                    section["size"] for section in remaining if section["name"] in writer_names
                )
                names.update(writer_names)
            resident, upper = dtc_rx.split_flash(remaining, names)
            if with_resident_constants:
                approved = readonly_objects(retained, stage / "retained.o")
                for name, size, expected in legacy.S01_LINK_TABLES:
                    content = symbol_bytes(retained, name)
                    if len(content) != size or sha256(content).hexdigest() != expected:
                        raise ValueError("Changed donor table before placement: " + name)
                packed, moved = pack_resident_constants(resident, upper, windows, approved, dtc_rx.RX_WINDOW)
                report["resident_constants"] = {"scope": "candidate address model; ownership unverified",
                                                "moved": [dict(section=s,
                                                bytes=approved[s][1], sha256=approved[s][2]) for s in moved]}
                if moved:
                    locations = [p for p in packed if p["section"] in moved]
                    objcopy = run(args.gcc, "-print-prog-name=objcopy")
                    run(objcopy, *(f"--only-section={s}" for s in moved),
                        "retained.o", "resident-constants.o")
                    script = (f"rbm_constant_probe = {locations[0]['address']:#x};\n" +
                              linker_script(locations, object_name="resident-constants.o", entry="rbm_constant_probe"))
                    (stage / "resident-constants.ld").write_text(script, encoding="ascii")
                    run(args.gcc, *flags, "-nostdlib", "-Wl,-T,resident-constants.ld",
                        "resident-constants.o", "-o", "resident-constants.elf")
                    constants = read_elf(stage / "resident-constants.elf", 2)
                    verify_linked(constants, locations, ())
                    for location in locations:
                        name, size, expected = approved[location["section"]]
                        content = next(s["data"] for s in alloc_sections(constants)
                                       if s["address"] == location["address"])
                        if len(content) != size or sha256(content).hexdigest() != expected:
                            raise ValueError("Linked donor table changed: " + name)
                    report["resident_constants"].update(elf_sha256=constants["sha256"],
                                                       placements=locations, linked_bytes_verified=True)
                return fixed + packed
            return fixed + pack(resident, (dtc_rx.RX_WINDOW,)) + pack(upper, windows)

        def place_ram():
            if with_dma4:
                irqs = [s for s in ram if s["name"] == ".bss.irq_target"]
                if (len(irqs) != 1 or
                        (irqs[0]["size"], irqs[0]["type"], irqs[0]["flags"], irqs[0]["alignment"]) != (4, 8, 3, 4)):
                    raise ValueError("Expected the one four-byte native BasicCAN pointer")
                return [pointer_layout, *pack([s for s in ram if s not in irqs], ram_windows)]
            return pack(ram, storage_space(args.storage_report))

        if unresolved:
            try:
                provisional=place_flash()
                if platform_flash:
                    report["target_platform"]["flash_placements"] = [
                        item for item in provisional if item["section"] in platform_flash]
                packing_windows = {w.name for w in flash_windows}
                packed = [p for p in provisional if p["window"] in packing_windows]
                report["known_sections_candidate_plan"]={"sections":len(packed),
                    "capacity_bytes":sum(w.end-w.start for w in flash_windows),
                    "payload_bytes":sum(p["bytes"] for p in packed),
                    "ownership_verified":False,"unresolved_material_counted":False}
                if stock_symbols:
                    report["sensor_redirects"] = sensor_placement(rom, retained, provisional)
                if with_dtc_rx:
                    report["dtc_rx_redirects"] = dtc_rx.describe(
                        rom, retained, provisional, owner_address, linked=False)
                if with_application_entries:
                    # Only the assembly wrappers are linked here. Their C calls use
                    # addresses of retained application code in the common plan.
                    callbacks = application_callback_addresses(retained, provisional, windows)
                    wrapper_objects = tuple(Path(source).with_suffix(".o").name
                                            for source in (*APPLICATION_ENTRY_SOURCES, APPLICATION_REDIRECT_SOURCE))
                    _, app_elf, _ = link_placed_roots(
                        args, stage, run, flags, sorted(provisional, key=lambda p: p["address"]),
                        {**native_bindings, **callbacks}, application_roots, "application-entries",
                        objects=wrapper_objects)
                    for name, address in callbacks.items():
                        symbol = app_elf["symbols"].get(name, {})
                        if (symbol.get("section"), symbol.get("address")) != (0xFFF1, address):
                            raise ValueError(f"H03 wrapper lost the placed application callback: {name}")
                    report["application_entries"].update(
                        status="LINKED_WRAPPERS_AT_COMMON_ADDRESSES", callbacks=callbacks,
                        patches=application_entries.verify_linked(rom, app_elf, windows),
                        wrapper_elf_sha256=app_elf["sha256"])
                if with_can_service:
                    _, tx_elf, tx_places = link_placed_roots(
                        args, stage, run, flags, sorted(provisional, key=lambda p: p["address"]),
                        native_bindings, tx13.ROOTS, "tx13")
                    report["can_service"]["tx13"] = tx13.describe(
                        rom, tx_elf, tx_places, owner_address, linked=True)
                    report["can_service"]["tx13"]["verification_scope"] = "independent_link_at_common_addresses"
                if with_dma4:
                    clock = storage["fields"]["control/clock_qualified"]
                    control = storage["blocks"]["control"]
                    if (clock["bytes"] != 1 or not 0 <= clock["offset"] < control["bytes"]):
                        raise ValueError("Invalid typed H03 clock qualification flag")
                    early_bindings = dict(native_bindings, rbm_h03_tml0_1mhz_qualified=
                                          control["address"] + clock["offset"])
                    report["early_irq_model"] = early_irq_model(
                        args, stage, run, flags, rom, sorted(provisional + place_ram(),
                        key=lambda p: p["address"]), early_bindings, policy, pointer)
            except PlacementError as error:
                report["known_sections_candidate_plan"]=error.report
            report.update(status="FAIL_BINDINGS",accepted_layout=False,
                          unresolved_symbols=sorted(unresolved),
                          size_scope="Known retained objects only; unresolved platform data and code are not counted")
            save(args.out/"layout.json",report)
            raise ValueError("Production bindings unresolved: "+", ".join(sorted(unresolved)))
        try:
            placement=place_flash()
            if ram:
                if args.storage_report is None:
                    raise PlacementError("Native writable state needs a prior RAM inventory",
                                         {"accepted_layout":False,"new_static_ram_bytes":sum(s["size"] for s in ram)})
                placement += place_ram()
            placement.sort(key=lambda p:p["address"])
        except PlacementError as error:
            report.update(status="FAIL_PLACEMENT",failure=error.report,accepted_layout=False)
            save(args.out/"layout.json",report)
            raise
        pinned = "".join(f"{name} = {address:#x};\n" for name, address in native_bindings.items())
        (stage/"placement.ld").write_text(pinned+linker_script(placement),encoding="ascii")
        run(args.gcc,*flags,"-fno-use-linker-plugin","-nostdlib","-Wl,-T,placement.ld",
            "retained.o","-o","layout.elf")
        linked=read_elf(stage/"layout.elf",2,local_symbols=("irq_target",) if with_dma4 else ())
        verify_linked(linked,placement,roots)
        if with_application_entries:
            report["application_entries"].update(
                status="LINKED_ADDRESS_MODEL",
                patches=application_entries.verify_linked(rom, linked, windows))
        if release_ram is not None:
            release = linked["symbols"].get(TOYOTA_RELEASE_SYMBOL, {})
            if (release.get("section"), release.get("address")) != (0xFFF1, release_ram["address"]):
                raise ValueError("Linked Toyota release RAM differs from the typed storage plan")
            report["target_platform"]["flash_placements"] = [
                item for item in placement if item["section"] in platform_flash]
        if with_ram_owner:
            ram_owner.verify_linked(linked["symbols"], ram_aliases)
        if stock_symbols:
            report["sensor_redirects"] = sensor_placement(rom, linked)
        if with_dtc_rx:
            report["dtc_rx_redirects"] = dtc_rx.describe(rom, linked, placement, owner_address, linked=True)
        if with_can_service:
            for name, address in aliases.items():
                symbol = linked["symbols"].get(name, {})
                if (symbol.get("section"), symbol.get("address")) != (0xFFF1, address):
                    raise ValueError("Linked H03 CAN service RAM differs from its typed binding: " + name)
            report["can_service"]["tx13"] = tx13.describe(rom, linked, placement, owner_address, linked=True)
        if with_dma4:
            report["common_service"] = {"patches": service.verify_common(rom, linked, policy, pointer),
                                        "policy_ranges": policy, "irq_pointer": pointer}
            report["early_irq_model"] = early_irq_model(
                args, stage, run, flags, rom, placement, native_bindings, policy, pointer)
        if with_service_guard:
            report["service_writers"] = service.verify_writers(rom, linked, policy, dtc_rx.RX_WINDOW)
        tables={}
        for name,size,expected in legacy.S01_LINK_TABLES:
            content=symbol_bytes(linked,name)
            if len(content)!=size or sha256(content).hexdigest()!=expected:
                raise ValueError("Linked donor calibration changed: "+name)
            tables[name]={"address":linked["symbols"][name]["address"],"bytes":size,"sha256":expected}
        selected_windows = flash_windows
        if ram:
            placed_ram_windows = (*ram_windows, Window("early_irq_pointer", pointer, pointer + 4)) \
                if with_dma4 else storage_space(args.storage_report)
            selected_windows = (*flash_windows, *placed_ram_windows)
        window_results={}
        for w in selected_windows:
            placed=[p for p in placement if p["window"]==w.name]
            end=max((p["address"]+p["bytes"] for p in placed),default=w.start)
            window_results[w.name]={"start":w.start,"end_exclusive":w.end,"capacity":w.end-w.start,
                                   "payload_bytes":sum(p["bytes"] for p in placed),
                                   "extent":end-w.start,"margin":w.end-end}
        report.update(status="PASS_ADDRESS_MODEL_ONLY",accepted_layout=True,windows=window_results,
                      placements=placement,shared_donor_tables=tables,
                      entry_points={root:linked["symbols"][root]["address"] for root in roots},
                      elf_sha256=linked["sha256"],startup_initialization_verified=False,
                      limits=["Not an executable replacement application or release BIN",
                              "FF fill and raw reference patterns do not prove exclusive Flash ownership",
                              "Virtual Flash, full startup, physical outputs and full IRQ stack still require integration",
                              "Existing inventory and native globals are conservatively counted separately"])
        if args.cpu_test:
            report["placed_code_cpu_tests"]=execute_placed_code(args,linked,stage,run,flags)
        shutil.copy2(stage/"layout.elf",args.out/"layout.elf")
        shutil.copy2(stage/"placement.ld",args.out/"placement.ld")
        save(args.out/"layout.json",report)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ("base","gcc","controller","bridge","out"):
        parser.add_argument("--"+name,type=Path,required=True)
    parser.add_argument("--profile",choices=PROFILES,default="two-window")
    parser.add_argument("--memory-model",choices=("medium","small"),default="medium")
    parser.add_argument("--with-bindings",action="store_true")
    parser.add_argument("--with-resident-constants", action="store_true",
                        help="On overflow, place verified relocation-free constant objects after the resident RX closure")
    parser.add_argument("--application-profile",type=Path,
                        help="Include the application binding and platform with an explicit header and --storage-report")
    parser.add_argument("--binding-source", type=Path, action="append", default=[],
                        help="Additional production H03 provider; repeat per file. Uses the explicit application profile")
    parser.add_argument("--sensor-clock-reference", type=Path,
                        help="Paired TML0/TML1 observations against an independent time reference")
    parser.add_argument("--sensor-calibration-profile", type=Path,
                        help="H03 sensor limits and observed maxima for the paired clock reference")
    parser.add_argument("--with-dtc-rx", action="store_true",
                        help="Link the two OEM-site BasicCAN redirects and place the resident RX graph")
    parser.add_argument("--with-dma4-guard", action="store_true",
                        help="Include the DMA4 guard and clear the BasicCAN pointer before the first IRQ")
    parser.add_argument("--with-service-guard", action="store_true",
                        help="Link the resident service write guards and Virtual Flash lockout; requires DMA4")
    parser.add_argument("--with-ram-owner", action="store_true",
                        help="Link the native RAM owner and verified absolute bounds; requires service guards")
    parser.add_argument("--with-application-entries", action="store_true",
                        help="Link the four OEM H03 application redirects; requires --application-profile")
    parser.add_argument("--with-can-service", action="store_true",
                        help="Include native CAN service, typed application RAM and the OEM TX13 redirect")
    parser.add_argument("--cpu-test",action="store_true")
    parser.add_argument("--storage-report",type=Path)
    args=parser.parse_args()
    args.out=args.out.resolve()
    input_names = ("base", "gcc", "controller", "bridge", "storage_report", "application_profile",
                   "sensor_clock_reference", "sensor_calibration_profile")
    for name in input_names:
        if getattr(args,name) is not None:
            setattr(args,name,getattr(args,name).resolve())
    inputs=[getattr(args,name) for name in input_names if getattr(args,name) is not None]
    inputs.extend(Path(path).resolve() for path in args.binding_source)
    # Invalidate the previous result before any new attempt, including failure.
    try:
        invalidate_outputs(args.out,inputs)
    except (ValueError,OSError) as error:
        parser.error(str(error))
    try:
        result=build(args)
    except (ValueError,KeyError,OSError,subprocess.SubprocessError) as error:
        detail=getattr(error,"stderr",None) or str(error)
        save(args.out/"summary.json",{"passed":False,"error":detail,"flashable_image":None})
        print(detail)
        return 1
    summary={key:result[key] for key in ("status","flash_payload_bytes","new_static_ram_bytes",
                                         "bindings_included","accepted_layout","flashable_image")}
    summary["windows"]=result["windows"]
    save(args.out/"summary.json",summary)
    print(json.dumps(summary,ensure_ascii=False))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
