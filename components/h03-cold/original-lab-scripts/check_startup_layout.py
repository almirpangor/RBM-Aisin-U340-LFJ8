"""Verify native H03 placement with the real S01 seed and diagnostic timing."""
import argparse
from contextlib import contextmanager
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

LAB = Path(__file__).resolve().parent
ROOT = LAB / "repo"
sys.path.insert(0, str(ROOT))
from tools import link_h03_bench_candidate as native

base = Path(r"F:\LFJ8-T-D.bin")
gcc = Path(r"F:\RBM-Codex-temp\toolchains\SysGCC-m32r-elf-4.8.0\bin\m32r-elf-gcc.exe")
storage_path = LAB / "h03-storage.json"
storage = native.layout.read_storage_report(storage_path)
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--out", required=True, type=Path)
parser.add_argument("--include-startup", action="store_true")
parser.add_argument("--keep-link-scratch", action="store_true")
args = parser.parse_args()
out = args.out.resolve()
if not out.is_relative_to(ROOT / "local"):
    raise ValueError("Keep the diagnostic output under repo/local")
layout_dir = out / "layout"
memory_dir = out / "memory"
layout_dir.mkdir(parents=True, exist_ok=False)
memory_dir.mkdir()
memory = native.bench.prepare(base.read_bytes(), storage,
                              storage["blocks"]["control"]["end_exclusive"], memory_dir)
source_names = [
    "lfj8_h03_bench_application_profile.c", "bench_sensor_profile.c",
    "lfj8_h03_engine_context.c", "lfj8_h03_bench_outputs.c",
    "bench_mode_profile.c", "lfj8_h03_bench_can_service.c",
    "h03_s01_verified_phase_clock_alias.S", native.bench.MODULE,
]
if args.include_startup:
    source_names += ["lfj8_h03_s01_cold_start.c", "h03_s01_cold_seed.S"]
sources = [native.TARGET / name for name in source_names] + [memory["symbol_source"]]
options = argparse.Namespace(
    base=base, gcc=gcc, out=layout_dir,
    controller=LAB / "controller-small/rbm_u340e_m32r_be.o",
    bridge=LAB / "bridge-small/lfj8_9e1c_m32r.o",
    application_profile=ROOT / "local/diagnostic-input/h03_test_sizing.h",
    binding_source=sources, storage_report=storage_path,
    sensor_clock_reference=None, sensor_calibration_profile=None,
    profile="padding-candidate", memory_model="small",
    with_bindings=True, with_dtc_rx=True, with_dma4_guard=True,
    with_service_guard=True, with_ram_owner=True, with_application_entries=True,
    with_can_service=True, with_resident_constants=True, cpu_test=False,
)
summary = {
    "artifact_kind": "H03_STARTUP_DIAGNOSTIC_LINK",
    "source_revision": subprocess.check_output(["git", "-C", ROOT, "rev-parse", "HEAD"], text=True).strip(),
    "diagnostic_timing_ticks": {"period": 5000, "lateness": 1000, "watchdog": 6000},
    "startup_included": args.include_startup,
    "bench_pair_ready": False, "hardware_verified": False, "flashable_image": None,
}
@contextmanager
def retained_scratch(prefix):
    path = out / "diagnostic-link-scratch"
    path.mkdir(exist_ok=False)
    yield str(path)

previous_temporary_directory = native.layout.TemporaryDirectory
if args.keep_link_scratch:
    native.layout.TemporaryDirectory = retained_scratch
try:
    with native.memory_inputs(gcc, memory):
        native.layout.build(options)
except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
    summary["error"] = str(error)
    if isinstance(error, subprocess.CalledProcessError) and error.stderr:
        summary["stderr"] = error.stderr
finally:
    native.layout.TemporaryDirectory = previous_temporary_directory
report_path = layout_dir / "layout.json"
if report_path.is_file():
    report = json.loads(report_path.read_text(encoding="utf-8"))
    for key in ("status", "accepted_layout", "unresolved_symbols", "known_sections_candidate_plan",
                "flash_payload_bytes", "new_static_ram_bytes", "retained_sections"):
        if key in report:
            summary[key] = report[key]
    summary["unit_sources"] = {name: sha256((native.TARGET / name).read_bytes()).hexdigest()
                               for name in source_names}
native.save(out / "summary.json", summary)
print(json.dumps({name: value for name, value in summary.items() if name != "retained_sections"}, indent=2))
