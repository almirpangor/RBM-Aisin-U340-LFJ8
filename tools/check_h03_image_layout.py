"""Build an audited H03 address model. Never emit a flashable BIN."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT=Path(__file__).resolve().parents[1]
LFJ8=ROOT/"targets/lfj8"
sys.path.insert(0,str(LFJ8))
import check_h03_link as legacy
from lfj8_h03_layout import (PROFILES,Window,PlacementError,read_elf,alloc_sections,
                            validate_windows,pack,linker_script,verify_linked,
                            symbol_bytes,raw_reference_patterns)
import lfj8_h03_sensor_hooks as sensor_hooks
import lfj8_h03_dtc_rx_placement as dtc_rx

EXTRA_ROOTS=(
    "rbm_u340e_step",
    "lfj8_button_filter_init","lfj8_range_control_step_with_buttons","lfj8_h03_range_snapshot",
    "rbm_u340e_runtime_restore_adaptation","rbm_u340e_s01_adaptation_baseline",
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


def save(path,data):
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n",encoding="utf-8",newline="\n")


def digest(path):
    return sha256(Path(path).read_bytes()).hexdigest()


def invalidate_outputs(output,inputs):
    artifacts=[output/name for name in ("layout.elf","placement.ld","layout.json","summary.json")]
    if any(p.resolve()==source.resolve() or (p.exists() and source.exists() and p.samefile(source))
           for p in artifacts for source in inputs):
        raise ValueError("Output artifacts must not overwrite inputs")
    output.mkdir(parents=True,exist_ok=True)
    for path in artifacts:
        if path.exists():
            path.unlink()


def storage_space(path):
    if path is None:
        return ()
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
    # Reserve the complete existing inventory, then place new native globals
    # only in remaining candidate space. This is not a startup implementation.
    blocks=report["blocks"]
    windows=tuple(Window(name,start,end) for name,start,end in (
        ("primary_ram_extra",blocks["control"]["end_exclusive"],0x807000),
        ("secondary_ram_extra",blocks["workspace"]["end_exclusive"],0x809600)) if start<end)
    validate_windows(windows)
    if blocks["communication"]["end_exclusive"]>blocks["workspace"]["address"]:
        raise ValueError("Overlapping prior storage inventory")
    return windows


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


def build(args):
    identity=legacy.identify_h03(args.base)
    rom=args.base.read_bytes()
    if sha256(rom).hexdigest() != identity["sha256"]:
        raise ValueError("H03 changed after identification")
    if args.with_bindings:
        sensor_hooks.validate_stock(rom)
    windows=PROFILES[args.profile]
    with_dtc_rx = getattr(args, "with_dtc_rx", False)
    flash_windows = (*windows, dtc_rx.RX_WINDOW) if with_dtc_rx else windows
    owner_address = None
    if with_dtc_rx:
        if not args.with_bindings or args.storage_report is None:
            raise ValueError("Resident RX needs --with-bindings and a typed --storage-report")
        dtc_rx.validate_stock(rom)
        storage_space(args.storage_report)
        owner_address = dtc_rx.owner_address(json.loads(args.storage_report.read_text(encoding="utf-8")))
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
    if args.with_bindings:
        bindings.extend(LFJ8/name for name in SENSOR_ASSEMBLY)
    if with_dtc_rx:
        bindings.extend(LFJ8/name for name in dtc_rx.MODULES)
    modules=list(dict.fromkeys([*modules,*bindings]))
    roots=set((*legacy.H03_ROOTS,*legacy.DTC_ROOTS,*legacy.CAN_EXTENSION_ROOTS,*EXTRA_ROOTS))
    if with_dtc_rx:
        roots.update(dtc_rx.RX_ROOTS)
    report={"base":identity,"profile":args.profile,"compiler_memory_model":args.memory_model,
            "input_objects":{p.name:digest(p) for p in (args.bridge,args.controller)},
            "input_sources":{p.relative_to(ROOT).as_posix():digest(p) for p in modules},
            "bindings_included":[p.name for p in bindings],
            "bindings_not_present":[name for name in BINDING_MODULES if not (LFJ8/name).is_file()],
            "raw_reference_patterns":raw_reference_patterns(rom,flash_windows),
            "hardware_verified":False,"target_ownership_verified":False,"flashable_image":None}
    if args.with_bindings:
        path = Path(sensor_hooks.__file__).resolve()
        report["input_sources"][path.relative_to(ROOT).as_posix()] = digest(path)
    if with_dtc_rx:
        path = Path(dtc_rx.__file__).resolve()
        report["input_sources"][path.relative_to(ROOT).as_posix()] = digest(path)
    with TemporaryDirectory(prefix="rbm-h03-placement-") as folder:
        stage=Path(folder)
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
            run(args.gcc,*flags,*module_flags,*(x for p in includes for x in ("-I",p)),
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
        if with_dtc_rx:
            for name in dtc_rx.STOCK_SYMBOLS:
                if retained["symbols"].get(name, {}).get("section") != 0:
                    raise ValueError("Unexpected definition or missing reference for DTC RX continuation: "+name)
            owner_symbol = retained["symbols"].get("h03_can_owner", {})
            if (owner_symbol.get("section") != 0 and
                    (owner_symbol.get("section"), owner_symbol.get("address")) != (0xFFF1, owner_address)):
                raise ValueError("The DTC RX binding must use the existing typed CAN owner")
            native_bindings.update(dtc_rx.STOCK_SYMBOLS, h03_can_owner=owner_address)
        unresolved=[name for name,symbol in retained["symbols"].items()
                    if symbol["section"]==0 and name not in native_bindings]
        sections=alloc_sections(retained)
        flash=[s for s in sections if not s["flags"]&1]
        ram=[s for s in sections if s["flags"]&1]
        report.update(required_roots=roots,retained_sections=len(sections),
                      flash_payload_bytes=sum(s["size"] for s in flash),
                      new_static_ram_bytes=sum(s["size"] for s in ram))
        def place_flash():
            if not with_dtc_rx:
                return pack(flash,windows)
            names = dtc_rx.closure_sections(run, args.gcc, flags, stage)
            resident, upper = dtc_rx.split_flash(flash, names)
            return pack(resident, (dtc_rx.RX_WINDOW,)) + pack(upper, windows)

        if unresolved:
            try:
                provisional=place_flash()
                report["known_sections_candidate_plan"]={"sections":len(provisional),
                    "capacity_bytes":sum(w.end-w.start for w in flash_windows),
                    "payload_bytes":sum(p["bytes"] for p in provisional),
                    "ownership_verified":False,"unresolved_material_counted":False}
                if stock_symbols:
                    report["sensor_redirects"] = sensor_placement(rom, retained, provisional)
                if with_dtc_rx:
                    report["dtc_rx_redirects"] = dtc_rx.describe(
                        rom, retained, provisional, owner_address, linked=False)
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
                placement += pack(ram,storage_space(args.storage_report))
            placement.sort(key=lambda p:p["address"])
        except PlacementError as error:
            report.update(status="FAIL_PLACEMENT",failure=error.report,accepted_layout=False)
            save(args.out/"layout.json",report)
            raise
        pinned = "".join(f"{name} = {address:#x};\n" for name, address in native_bindings.items())
        (stage/"placement.ld").write_text(pinned+linker_script(placement),encoding="ascii")
        run(args.gcc,*flags,"-fno-use-linker-plugin","-nostdlib","-Wl,-T,placement.ld",
            "retained.o","-o","layout.elf")
        linked=read_elf(stage/"layout.elf",2)
        verify_linked(linked,placement,roots)
        if stock_symbols:
            report["sensor_redirects"] = sensor_placement(rom, linked)
        if with_dtc_rx:
            report["dtc_rx_redirects"] = dtc_rx.describe(rom, linked, placement, owner_address, linked=True)
        tables={}
        for name,size,expected in legacy.S01_LINK_TABLES:
            content=symbol_bytes(linked,name)
            if len(content)!=size or sha256(content).hexdigest()!=expected:
                raise ValueError("Linked donor calibration changed: "+name)
            tables[name]={"address":linked["symbols"][name]["address"],"bytes":size,"sha256":expected}
        selected_windows=(*flash_windows,*storage_space(args.storage_report)) if ram else flash_windows
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
    parser.add_argument("--with-dtc-rx", action="store_true",
                        help="Place the protected BasicCAN RX graph in the lower H03 sector")
    parser.add_argument("--cpu-test",action="store_true")
    parser.add_argument("--storage-report",type=Path)
    args=parser.parse_args()
    args.out=args.out.resolve()
    for name in ("base","gcc","controller","bridge","storage_report"):
        if getattr(args,name) is not None:
            setattr(args,name,getattr(args,name).resolve())
    inputs=[getattr(args,name) for name in ("base","gcc","controller","bridge","storage_report") if getattr(args,name) is not None]
    # Invalidate the previous result before any new attempt, including failure.
    try:
        invalidate_outputs(args.out,inputs)
    except (ValueError,OSError) as error:
        parser.error(str(error))
    try:
        result=build(args)
    except (ValueError,OSError,subprocess.SubprocessError) as error:
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
