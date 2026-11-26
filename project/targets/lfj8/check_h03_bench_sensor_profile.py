"""Check the exact H03 sources, native sensor link and M32R bench scenarios."""

import argparse
import json
from pathlib import Path
from struct import unpack_from

from check_h03_sensor_config import stock_evidence
from check_h03_sensor_native import HERE, TARGET, run


PROFILE = "bench_sensor_profile.c"
SENSORS = (
    "lfj8_donor_io.c", "lfj8_h03_atf.c", "lfj8_h03_atf_target.c",
    "lfj8_h03_atf_tml0.c", "lfj8_h03_sensor_feed.c", "lfj8_h03_sensor_target.c",
)
FLAGS = (
    *TARGET, "-std=c11", "-Os", "-Wall", "-Wextra", "-Werror",
    "-ffreestanding", "-ffunction-sections", "-fdata-sections",
)
STOCK_CLOCK_SITES = {
    "nt_ticks_to_ms": (0x03BF4C, "e480618420c4f000feff4cc3d4c00003a1c428acfeff4cd1"),
    "top10_setup": (0x003FF4, "e58002ea90f0300021b501e02125617c45f82125e68002e02126f000"),
    "top10_phase_divider": (0x040468, "2e7ff000e4804862600a2004"),
    "oem_five_step_reload": (0x040480, "e48048642094f000b090000961052104"),
    "an1_task_call": (0x040008, "7e53f000"),
    "atf_consumer_call": (0x03A838, "fe000236"),
}


def check_stock(base):
    stock = stock_evidence(base)
    rom = base.read_bytes()
    sites = stock["instruction_sites"]
    for name, (address, expected) in STOCK_CLOCK_SITES.items():
        actual = rom[address:address + len(expected) // 2].hex()
        if actual != expected:
            raise ValueError(f"Unexpected stock H03 instructions for {name} at {address:#x}")
        sites[name] = {"address": f"0x{address:06X}", "bytes": actual}

    # The OEM loads this binary32 constant and multiplies the raw count by it.
    # Fit the documented 0.001 ms/tick scale rather than using its binary32 error.
    if rom[0x0328AC:0x0328B0] != bytes.fromhex("3a83126f"):
        raise ValueError("The H03 tick-to-millisecond constant has changed")
    tml_hz = round(1000 / unpack_from(">f", rom, 0x0328AC)[0])
    prs1_divisor = stock["configured_registers"]["PRS1"] + 1
    prs0_divisor = rom[0x009E7D] + 1
    bclk_hz = 2 * tml_hz * prs1_divisor
    top10_divisor = rom[0x004003] + 1
    top10_ticks = top10_divisor * prs0_divisor // prs1_divisor
    phase_ticks = rom[0x040471] * top10_ticks
    sweep_ticks = rom[0x04048D] * phase_ticks
    reloads = stock["oem_freshness_reload_ms"]
    return {
        "base": stock["base"],
        "instruction_sites": sites,
        "clock_basis": "OEM_NOMINAL",
        "tml_ticks_to_ms_literal_address": "0x0328AC",
        "tml_nominal_hz": tml_hz,
        "bclk_nominal_hz": bclk_hz,
        "cpu_nominal_hz": 2 * bclk_hz,
        "top10_ticks": top10_ticks,
        "phase_ticks": phase_ticks,
        "sweep_ticks": sweep_ticks,
        "config": {
            "s51_timeout_ticks": int(reloads["S51"]["value"] * tml_hz / 1000),
            "s83_timeout_ticks": int(reloads["S83"]["value"] * tml_hz / 1000),
            "atf_max_age_us": 2 * sweep_ticks * 1_000_000 // tml_hz,
            "max_read_span_ticks": top10_ticks,
        },
    }


def check(base, gcc, out):
    report = check_stock(base)
    out.mkdir(parents=True, exist_ok=True)
    compiled = {}
    for name in (PROFILE, *SENSORS, "lfj8_h03_mmio.c"):
        obj = out / Path(name).with_suffix(".o")
        run(gcc, *FLAGS, "-c", HERE / name, "-o", obj)
        compiled[name] = obj

    def tool(name):
        return gcc.with_name(f"m32r-elf-{name}{gcc.suffix}")

    native = out / "native-sensors.o"
    entries = (
        "rbm_h03_target_clock_ready", "rbm_h03_bench_raw_capture",
        "rbm_h03_sensor_clock_rebase", "rbm_h03_sensor_foreground",
        "rbm_h03_s51_capture_callback", "rbm_h03_s83_capture_callback",
        "rbm_h03_atf_adc_callback", "rbm_h03_atf_source_callback", "rbm_h03_atf_publish_callback",
    )
    run(gcc, *TARGET, "-nostdlib", "-Wl,-r,--gc-sections",
        *(f"-Wl,-u,{name}" for name in entries), *compiled.values(), "-o", native)
    undefined = set(run(tool("nm"), "-u", native).split()[1::2])
    # GNU ld -r can retain unreferenced undefined names from discarded
    # sections, including the unrelated CAN read helper in the MMIO file.
    relocations = (line.split() for line in run(tool("objdump"), "-r", native).splitlines())
    referenced = {fields[2].split("+")[0] for fields in relocations
                  if len(fields) == 3 and fields[1].startswith("R_M32R")}
    symbols = undefined & referenced
    expected = {"lfj8_h03_application_running_locked", "rbm_h03_sensor_state",
                "rbm_h03_atf_state", "rbm_h03_tml0_1mhz_qualified", "memcpy", "memset"}
    if symbols != expected:
        raise ValueError(f"Unexpected native sensor dependencies: {sorted(symbols)}")

    profile = compiled[PROFILE]
    config_bytes = out / "sensor-config.dat"
    run(tool("objcopy"), "-O", "binary", "-j", ".rodata.rbm_h03_sensor_config", profile, config_bytes)
    raw_config = config_bytes.read_bytes()
    if len(raw_config) != 16 or tuple(report["config"].values()) != unpack_from(">IIIH", raw_config):
        raise ValueError("Native sensor config differs from the stock H03 derivation")

    sim_inputs = out / "h03-evidence.c"
    sim_inputs.write_text(
        '#include "bench_sensor_profile.h"\n'
        f'_Static_assert(LFJ8_H03_BENCH_TML_NOMINAL_HZ == {report["tml_nominal_hz"]}u, "TML");\n'
        f'_Static_assert(LFJ8_H03_BENCH_CPU_NOMINAL_HZ == {report["cpu_nominal_hz"]}u, "CPU");\n'
        f'_Static_assert(LFJ8_H03_BENCH_PHASE_TICKS == {report["phase_ticks"]}u, "phase");\n'
        f'_Static_assert(LFJ8_H03_BENCH_SWEEP_TICKS == {report["sweep_ticks"]}u, "sweep");\n'
        'void __init(void) {}\nvoid __fini(void) {}\n', encoding="ascii",
    )
    crt = run(gcc, *TARGET, "-print-file-name=crt0.o")
    fixture = out / "bench-sensors.elf"
    run(gcc, *FLAGS, "-nostartfiles", crt, "-I", HERE, sim_inputs,
        HERE / "test_h03_bench_sensor_profile.c", profile, *(compiled[src] for src in SENSORS),
        "-Wl,-e,_start,--gc-sections,--start-group", "-lc", "-lgloss", "-lgcc",
        "-Wl,--end-group", "-o", fixture)
    result = run(tool("run"), "--memory-size=16M", fixture)
    if not result.startswith("PASS H03 bench profile"):
        raise ValueError(f"M32R verification did not pass: {result}")

    sections = {}
    for line in run(tool("size"), "-A", profile).splitlines():
        fields = line.split()
        if len(fields) == 3 and fields[0].startswith(".") and int(fields[1]):
            sections[fields[0]] = int(fields[1])
    (out / "native-sensors.dis").write_text(run(tool("objdump"), "-dr", native) + "\n", encoding="ascii")
    report.update(status="PASS_BENCH_SENSOR_NATIVE", m32r_model=result,
                  linked_dependencies=sorted(symbols), profile_sections=sections,
                  disassembly="native-sensors.dis",
                  hardware_tested=False, flashable_image=None)
    (out / "bench-sensor-profile.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(result)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("base", "gcc", "out"):
        parser.add_argument("--" + key, type=Path, required=True)
    args = parser.parse_args()
    try:
        check(args.base.resolve(), args.gcc.resolve(), args.out.resolve())
    except (ValueError, OSError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
