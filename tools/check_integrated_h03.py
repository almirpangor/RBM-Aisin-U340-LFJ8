"""Repeat integrated H03 CPU checks; never emit a flashable firmware image."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
LFJ8 = ROOT / "targets/lfj8"


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def native(args):
    common = ["--base", str(args.base), "--gcc", str(args.gcc)]
    cases = [
        ("storage", "check_h03_storage.py", [*common, "--out", str(args.out / "storage.json")]),
        ("atf-native", "check_h03_atf_native.py", common),
        ("atf-fault", "check_h03_atf_fault.py", common),
        ("basiccan", "check_h03_dtc_basiccan.py", [*common, "--with-resident-rx"]),
        ("can-lifecycle", "check_h03_can_lifecycle.py", common),
        ("tx-gate", "check_h03_torque_tx_gate.py", common),
        ("phase-clock", "check_h03_phase_clock.py", [*common, "--out", str(args.out / "phase-clock.json")]),
        ("phase-hook", "check_h03_phase_hook.py", [*common, "--out", str(args.out / "phase-hook.json")]),
        ("phase-boot", "check_h03_phase_boot.py", [*common, "--out", str(args.out / "phase-boot.json")]),
        ("phase-wait", "check_h03_phase_wait.py", [*common, "--out", str(args.out / "phase-wait.json")]),
        ("selector", "check_h03_selector_adc.py", common),
        ("range-pnp", "check_h03_range_pnp.py", common),
        ("application-isolation", "check_h03_application_isolation.py",
         [*common, "--out", str(args.out / "application-isolation.json")]),
        ("can-monitor-startup", "check_h03_can_monitor_startup.py",
         [*common, "--out", str(args.out / "can-monitor-startup.json")]),
        ("slt-fault", "check_h03_slt_fault.py", common),
        ("vflash-lockout", "check_h03_vflash_lockout.py", [*common, "--out", str(args.out / "vflash-lockout.json")]),
        ("native-hooks", "check_h03_native_hooks.py", [*common, "--controller", str(args.controller)]),
        ("dtc-foreground", "check_h03_dtc_foreground.py",
         ["--cc", str(args.gcc), "--controller", str(args.controller)]),
        ("toyota-stack", "check_h03_toyota_stack.py", [*common, "--controller", str(args.controller)]),
    ]

    def run(case):
        name, script, options = case
        command = [sys.executable, "-B", str(LFJ8 / script), *options]
        process = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=1200)
        output = process.stdout + process.stderr
        log = args.out / (name + ".log")
        log.write_bytes(output)
        row = {"name": name, "command": command, "exit_code": process.returncode,
               "log": log.name, "sha256": sha256(output).hexdigest()}
        print(name + ": " + ("PASS" if process.returncode == 0 else "FAIL"), flush=True)
        return row

    rows = []
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for future in as_completed([pool.submit(run, case) for case in cases]):
            rows.append(future.result())
    if next(row for row in rows if row["name"] == "storage")["exit_code"] == 0:
        for name, script in (("service", "check_h03_service_isolation.py"),
                             ("service-guard", "check_h03_service_guard.py"),
                             ("can-monitor-revoke", "check_h03_can_monitor_revoke.py")):
            options = [*common, "--storage-report", str(args.out / "storage.json")]
            if name != "service":
                options += ["--out", str(args.out / (name + ".json"))]
            rows.append(run((name, script, options)))
    rows.sort(key=lambda row: row["name"])
    return {"checks": rows, "passed": all(row["exit_code"] == 0 for row in rows)}


@contextmanager
def link_configuration(link):
    names = ("TARGET", "H03_ROOTS", "DTC_FILES", "DTC_ROOTS", "CAN_EXTENSION_FILES",
             "CAN_EXTENSION_ROOTS", "check_split_layout")
    saved = {name: getattr(link, name) for name in names}
    try:
        yield
    finally:
        for name, value in saved.items():
            setattr(link, name, value)


def rebuild_objects(args, memory_model):
    """Use the public builders so objects and complete provenance agree."""
    controller = args.out / "controller"
    bridge = args.out / "bridge"
    subprocess.run([
        sys.executable, "-B", str(ROOT / "controller/build_target.py"), "m32r",
        "--cc", str(args.gcc), "--out", str(controller), "--memory-model", memory_model,
    ], cwd=ROOT, check=True)
    subprocess.run([
        sys.executable, "-B", str(LFJ8 / "build.py"), "--output", str(bridge),
        "--m32r-cc", str(args.gcc), "--base-9e1c", str(args.base),
        "--m32r-memory-model", memory_model,
    ], cwd=ROOT, check=True)
    args.controller = controller / "rbm_u340e_m32r_be.o"
    args.bridge = bridge / "lfj8_9e1c_m32r.o"


def expanded(args):
    sys.path.insert(0, str(LFJ8))
    import check_h03_link as link
    with link_configuration(link):
        return expanded_check(argparse.Namespace(**vars(args)), link)


def expanded_check(args, link):
    if args.small_model:
        # Optional sizing experiment. Only generated absolute symbol addresses
        # change; runtime pointer ABI is unchanged. GCC documents this model
        # for symbols below 16 MiB. Physical ownership is still unproved.
        rebuild_objects(args, "small")
        link.TARGET = [flag.replace("-mmodel=medium", "-mmodel=small") for flag in link.TARGET]

    link.H03_ROOTS += (
        "lfj8_button_filter_init", "lfj8_range_control_step_with_buttons",
        "lfj8_h03_range_snapshot", "rbm_u340e_runtime_restore_adaptation",
        "lfj8_h03_atf_circuit_after_monitor",
    )
    link.DTC_FILES += ("chery_dtc_journal.c",)
    link.DTC_ROOTS += ("chery_dtc_journal_encode", "chery_dtc_journal_restore")
    link.CAN_EXTENSION_FILES += ("lfj8_h03_dtc_foreground.c",)
    link.CAN_EXTENSION_ROOTS += (
        "lfj8_h03_cycle_tick_with_load", "lfj8_h03_cycle_tick_with_slu",
        "lfj8_h03_dtc_foreground_poll", "lfj8_h03_dtc_rx_queue_capture_basic",
        "lfj8_h03_dtc_rx_dispatch_begin", "lfj8_h03_dtc_rx_dispatch_skip_paired",
        "lfj8_h03_engine_feed_task2_with_model",
    )
    # This is a sizing hypothesis. No reset vector, platform callbacks or
    # physical RAM/Flash ownership is inferred from successful linking.
    original = link.check_split_layout
    moved_roots = ("lfj8_h03_phase_clock_init", "lfj8_h03_phase_clock_release",
                   "lfj8_h03_phase_clock_take")
    def split(stage, compiler, run, base, primary, extension, roots,
              service_ranges=None, dma4_guard=False):
        link.H03_ROOTS += moved_roots
        try:
            kept_roots = tuple(root for root in roots if root not in moved_roots)
            try:
                return original(stage, compiler, run, base,
                                (*primary, "lfj8_h03_phase_clock.o"),
                                [obj for obj in extension if obj != "lfj8_h03_phase_clock.o"],
                                kept_roots, service_ranges, dma4_guard)
            except subprocess.CalledProcessError as error:
                if "window overflow" not in (error.stderr or ""):
                    raise
                # Preserve the strict rejection; this second link measures
                # excess only and is never accepted as a valid placement.
                script = (stage / "split.ld").read_text(encoding="ascii")
                script = "\n".join(line for line in script.splitlines()
                                   if "window overflow" not in line)
                (stage / "split.ld").write_text(script, encoding="ascii")
                run(*error.cmd)
                info, allocated = link.elf_info(stage / "split.elf", 2)
                nm = run(compiler, "-print-prog-name=nm")
                sized_symbols = []
                for row in run(nm, "-S", "--size-sort", "split.elf").splitlines():
                    fields = row.split()
                    if len(fields) == 4:
                        sized_symbols.append({"name": fields[3], "bytes": int(fields[1], 16),
                                              "address": fields[0], "type": fields[2]})
                symbols = {row.split()[-1] for row in run(nm, "--defined-only", "split.elf").splitlines()
                           if len(row.split()) == 3}
                missing = sorted(set(link.H03_ROOTS + kept_roots) - symbols)
                if missing:
                    raise ValueError("Missing expanded roots: " + ", ".join(missing)) from error
                windows = {}
                for name, lo, hi in (("primary", link.FLASH_START, link.FLASH_END),
                                     ("can_extension", link.TAIL_START, link.TAIL_END)):
                    end = max(address + size for address, size, _ in allocated
                              if lo <= address < hi)
                    windows[name] = {"capacity": hi - lo, "bytes": end - lo,
                                     "margin": hi - end}
                save(args.out / "unbounded-sizing.json",
                     {"accepted_layout": False, "windows": windows, "elf": info,
                      "required_roots": list(link.H03_ROOTS + kept_roots),
                      "largest_symbols": sorted(sized_symbols, key=lambda row: -row["bytes"])[:40],
                      "flashable_image": None})
                raise ValueError("Expanded roots exceed reserved windows: " + json.dumps(windows)) from error
        finally:
            link.H03_ROOTS = tuple(root for root in link.H03_ROOTS if root not in moved_roots)
    link.check_split_layout = split
    report = link.check(args.base, args.bridge, args.controller, args.gcc, None,
                        args.bosch_trace, args.out / "expanded-model.elf")
    return {"passed": True, "layout": report,
            "not_included": ["native ASM hooks", "final platform callbacks and startup",
                             "physical output inhibition", "NVM backend", "remaining Toyota producers"]}


def components(args):
    sys.path.insert(0, str(LFJ8))
    from check_h03_link import TARGET
    cases = {
        "vss-arithmetic": ["targets/lfj8/test_lfj8_vss_arithmetic.c", "targets/lfj8/lfj8_bridge.c"],
        "buttons": ["controller/tests/test_shift_buttons.c"],
        "mode-policy": ["controller/tests/test_mode_policy.c"],
        "journal": ["diagnostics/test_chery_dtc_journal.c", "diagnostics/chery_dtc.c",
                    "diagnostics/chery_dtc_journal.c"],
        "atf-circuit": ["diagnostics/test_chery_atf_circuit.c", "diagnostics/chery_atf_circuit.c",
                        "diagnostics/chery_dtc.c"],
        "button-capture": ["targets/lfj8/test_lfj8_h03_button_capture.c",
                           "targets/lfj8/lfj8_h03_button_capture.c", "targets/lfj8/lfj8_range_control.c"],
        "cycle-load": ["targets/lfj8/test_lfj8_h03_cycle_load.c", "targets/lfj8/lfj8_h03_cycle.c",
                       "targets/lfj8/lfj8_h03_torque.c", "targets/lfj8/lfj8_h03_slu.c"],
        "cycle-slu": ["targets/lfj8/test_lfj8_h03_cycle.c", "targets/lfj8/lfj8_h03_cycle.c",
                      "targets/lfj8/lfj8_h03_torque.c", "targets/lfj8/lfj8_h03_slu.c"],
    }
    rows = []
    with TemporaryDirectory(prefix="rbm-integrated-components-") as temp:
        stage = Path(temp)
        crt = subprocess.check_output([str(args.gcc), *TARGET, "-print-file-name=crt0.o"], text=True).strip()
        hooks = stage / "hooks.c"
        hooks.write_text("void __init(void) {}\nvoid __fini(void) {}\n", encoding="ascii")
        includes = [str(ROOT / path) for path in
                    ("controller/include", "controller/vendor/toyota/include", "targets/lfj8", "diagnostics")]
        for name, files in cases.items():
            elf = stage / (name + ".elf")
            command = [str(args.gcc), *TARGET, "-Os", "-std=c11", "-Wall", "-Wextra", "-Werror",
                       "-Wno-missing-braces", "-Wno-missing-field-initializers",
                       "-ffunction-sections", "-fdata-sections", "-nostartfiles", crt,
                       *(flag for path in includes for flag in ("-I", path)),
                       *(str(ROOT / path) for path in files), str(hooks), str(args.controller),
                       "-Wl,--gc-sections,-e,_start,--start-group", "-lc", "-lgloss", "-lgcc",
                       "-Wl,--end-group", "-o", str(elf)]
            build = subprocess.run(command, capture_output=True, timeout=120)
            result = build
            if build.returncode == 0:
                result = subprocess.run([str(args.gcc.with_name("m32r-elf-run" + args.gcc.suffix)), str(elf)],
                                        capture_output=True, timeout=120)
            output = build.stdout + build.stderr + (result.stdout + result.stderr if result is not build else b"")
            (args.out / (name + ".log")).write_bytes(output)
            rows.append({"name": name, "command": command, "exit_code": result.returncode,
                         "sha256": sha256(output).hexdigest()})
            print(name + ": " + ("PASS" if result.returncode == 0 else "FAIL"), flush=True)
    return {"passed": all(row["exit_code"] == 0 for row in rows), "checks": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=("native", "expanded", "components"), required=True)
    for name in ("base", "gcc", "controller", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("bridge", "bosch-trace"):
        parser.add_argument("--" + name, type=Path)
    parser.add_argument("--jobs", type=int, default=3)
    parser.add_argument("--small-model", action="store_true",
                        help="expanded only: rebuild with GCC's below-16-MiB symbol model")
    args = parser.parse_args()
    if not 1 <= args.jobs <= 8:
        parser.error("--jobs must be between 1 and 8")
    if args.suite == "expanded" and (args.bridge is None or args.bosch_trace is None):
        parser.error("expanded requires --bridge and --bosch-trace")
    if args.small_model and args.suite != "expanded":
        parser.error("--small-model is only supported by expanded")
    for name in ("base", "gcc", "controller", "out", "bridge", "bosch_trace"):
        path = getattr(args, name)
        if path is not None:
            setattr(args, name, path.resolve())
    args.out.mkdir(parents=True, exist_ok=True)
    try:
        result = {"native": native, "expanded": expanded, "components": components}[args.suite](args)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        detail = getattr(error, "stderr", None) or getattr(error, "stdout", None) or str(error)
        if isinstance(detail, bytes):
            detail = detail.decode("utf-8", errors="replace")
        result = {"passed": False, "error": detail}
    result.update({"suite": args.suite, "compiler_memory_model": "small" if args.small_model else "medium",
                   "hardware_verified": False, "flashable_image": None})
    save(args.out / "summary.json", result)
    print(json.dumps({k: v for k, v in result.items() if k not in ("layout", "checks")}, ensure_ascii=False))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
