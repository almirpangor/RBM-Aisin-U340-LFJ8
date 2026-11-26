"""Replay Bosch engine frames through the native H03 bench context and receiver."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

from check_h03_link import HERE, ROOT, TARGET, identify_h03

SOURCES = (
    "test_lfj8_h03_engine_context.c", "lfj8_h03_engine_context.c",
    "lfj8_h03_atf_tml0.c", "lfj8_h03_engine_feed.c", "lfj8_h03_engine_rx.c",
    "lfj8_donor_io.c", "ta2005_chery_inputs.c", "ta2005_engine_qualifier.c",
)
FLAGS = ("-Os", "-std=c11", "-Wall", "-Wextra", "-Werror",
         "-ffunction-sections", "-fdata-sections")


def run(directory, *command, timeout=90):
    result = subprocess.run([str(arg) for arg in command], cwd=directory, capture_output=True,
                            text=True, encoding="utf-8", errors="replace", timeout=timeout)
    if result.returncode:
        raise ValueError((result.stderr or result.stdout).strip())
    return result.stdout.strip()


def check(args):
    identity = identify_h03(args.base)
    rom = args.base.read_bytes()
    if sha256(rom).hexdigest() != identity["sha256"] or rom[0x3D86:0x3D89] != b"\x95\xa0\x04":
        raise ValueError("Exact H03 base and stock CAN CONF/BRP are required")
    sys.path.insert(0, str(ROOT / "targets/bosch"))
    from tx import RPM, COOLANT
    if (RPM.identifier, RPM.period, COOLANT.identifier, COOLANT.period) != (0x0FA, 625, 0x278, 1250):
        raise ValueError("Review the paired Bosch schedule before reusing the bench profile")
    trace_data = args.bosch_trace.read_bytes()
    trace = json.loads(trace_data)["bosch_tx_to_tcm"]
    if trace["rpm"] != 1200 or trace["coolant_celsius"] != 87:
        raise ValueError("Expected the pinned 1200 RPM / 87 C Bosch replay")
    args.out.mkdir(parents=True, exist_ok=True)
    lines = []
    for name, key in (("bosch_rpm", "0x0FA"), ("bosch_ect", "0x278")):
        payload = bytes.fromhex(trace[key])
        if len(payload) != 8:
            raise ValueError("Malformed Bosch replay payload")
        literals = ", ".join(f"0x{byte:02x}" for byte in payload)
        lines.append(f"static const uint8_t {name}[8] = {{{literals}}};")
    (args.out / "bosch_replay.h").write_text("\n".join(lines) + "\n", encoding="ascii")
    includes = tuple(arg for path in (args.out, HERE, ROOT / "controller/include",
                     ROOT / "controller/vendor/toyota/include", ROOT / "diagnostics")
                     for arg in ("-I", path))
    sources = (*(HERE / name for name in SOURCES), ROOT / "diagnostics/chery_dtc.c")
    windows = sys.platform == "win32"
    host = args.out / ("engine-context.exe" if windows else "engine-context")
    run(args.out, args.zig, "cc", *FLAGS, *includes, *sources, "-o", host, timeout=300)
    host_output = run(args.out, host)
    crt = run(args.out, args.gcc, *TARGET, "-print-file-name=crt0.o")
    shim = args.out / "sim-crt.c"
    shim.write_text("void __init(void) {}\nvoid __fini(void) {}\n", encoding="ascii")
    elf = args.out / "engine-context.elf"
    run(args.out, args.gcc, *TARGET, *FLAGS, *includes, "-nostartfiles", crt, *sources, shim,
        "-Wl,--gc-sections,-e,_start,--start-group", "-lc", "-lgloss", "-lgcc",
        "-Wl,--end-group", "-o", elf)
    sim = args.gcc.with_name("m32r-elf-run" + args.gcc.suffix)
    native_output = run(args.out, sim, "--memory-size=16M", elf)
    if not all(result.endswith("PASS") for result in (host_output, native_output)):
        raise ValueError("Host and M32R must both reach the engine replay result")
    report = {
        "base": identity, "bosch_image_sha256": trace["sha256"],
        "bosch_trace_sha256": sha256(trace_data).hexdigest(),
        "host": host_output, "m32r": native_output, "model_elf_sha256": sha256(elf.read_bytes()).hexdigest(),
        "hardware_tested": False, "flashable_image": None,
    }
    (args.out / "summary.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("base", "bosch-trace", "zig", "gcc", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    for name, value in vars(args).items():
        setattr(args, name, value.resolve())
    try:
        check(args)
    except (KeyError, ValueError, OSError, subprocess.SubprocessError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
