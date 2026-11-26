"""Build and execute the H03 cold-start component under the GNU M32R simulator."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess

LAB = Path(__file__).resolve().parent
ROOT = LAB.parents[1] / "project"
GCC = LAB.parents[1] / "tools/SysGCC-m32r-elf-4.8.0/bin/m32r-elf-gcc.exe"
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--out", type=Path, default=LAB / "m32r-startup-check")
OUT = parser.parse_args().out.resolve()
OUT.mkdir(exist_ok=False)
flags = ["-m32r", "-mmodel=small", "-msdata=none", "-Wa,-EB", "-Os", "-std=c11",
         "-Wall", "-Wextra", "-Werror", "-ffunction-sections", "-fdata-sections"]
includes = []
for name in ("controller/include", "controller/vendor/toyota/include", "targets/lfj8", "diagnostics"):
    includes += ["-I", ROOT / name]

def run(program, *arguments):
    try:
        return subprocess.run([str(word) for word in (program, *arguments)], cwd=OUT,
                              check=True, capture_output=True, text=True, timeout=60).stdout
    except subprocess.CalledProcessError as error:
        raise RuntimeError(error.stderr.rstrip() or error.stdout.rstrip()) from error

component = LAB / "component"
code = OUT / "startup.o"
seed = OUT / "cold-seed.o"
seed_data = OUT / "cold-seed-section.dat"
run(GCC, *flags, *includes, "-ffreestanding", "-fno-builtin", "-fno-common",
    "-c", component / "lfj8_h03_s01_cold_start.c", "-o", code)
run(GCC, *flags[:4], "-c", component / "h03_s01_cold_seed.S", "-o", seed)
run(GCC.with_name("m32r-elf-objcopy.exe"), "-O", "binary", "-j", ".rodata.h03_s01_cold_seed", seed, seed_data)
assert seed_data.read_bytes() == bytes(564)
symbols = run(GCC.with_name("m32r-elf-nm.exe"), "-S", seed)
assert "00000000 00000168 R rbm_h03_target_startup_gear" in symbols
assert "00000000 00000231 R rbm_h03_target_startup_gp" in symbols
assert " U rbm_h03_bench_consume_cold_admission_locked" in run(GCC.with_name("m32r-elf-nm.exe"), "-u", code)
startup = run(GCC, *flags[:4], "-print-file-name=crt0.o").strip()
image = OUT / "startup-sim.elf"
run(GCC, *flags, *includes, "-nostartfiles", startup, code, seed, LAB / "startup_component_fixture.c",
    ROOT / "diagnostics/chery_dtc.c", LAB / "controller-small/rbm_u340e_m32r_be.o",
    "-Wl,-e,_start,--gc-sections", "-Wl,--start-group", "-lc", "-lgloss", "-lgcc", "-Wl,--end-group",
    "-o", image)
sim = run(GCC.with_name("m32r-elf-run.exe"), image).strip()
assert sim.startswith("PASS cold startup:")
report = {
    "artifact_kind": "M32R_COLD_START_COMPONENT_ONLY",
    "hardware_verified": False,
    "bench_pair_ready": False,
    "flashable_image": None,
    "source_revision": "e61b319",
    "seed_payload_bytes": 561,
    "seed_aligned_flash_bytes": seed_data.stat().st_size,
    "seed_sha256": sha256(seed_data.read_bytes()).hexdigest(),
    "seed_symbols": symbols.splitlines(),
    "own_prologue": run(GCC.with_name("m32r-elf-objdump.exe"), "-d", code).splitlines()[7:14],
    "startup_admission_provider_linked_in_target": False,
    "simulator": sim,
}
(OUT / "summary.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, indent=2))
