"""Compile native H03 profile entry points; never produce a flashable image."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MODULES = (
    "lfj8_h03_bench_application_profile.c", "lfj8_h03_application_binding.c",
    "lfj8_h03_target_platform.c", "bench_sensor_profile.c",
    "lfj8_h03_engine_context.c", "lfj8_h03_bench_outputs.c",
)
NATIVE_PROVIDERS = (
    "rbm_h03_bench_native_input_capture", "rbm_h03_bench_native_input_startup",
    "rbm_h03_bench_native_can_service", "rbm_h03_bench_prepare_startup_inputs",
)
SELFTEST_PROFILE = """/* SELFTEST ONLY: not a release profile. */
#define RBM_H03_BENCH_TOYOTA_PERIOD_TICKS 5000u
#define RBM_H03_BENCH_TOYOTA_MAX_LATENESS_TICKS 1000u
#define RBM_H03_BENCH_TOYOTA_WATCHDOG_TICKS 6000u
#define RBM_H03_BENCH_STARTUP_RANGE {0}
#define RBM_H03_BENCH_STARTUP_REQUEST_1120 0u
#include "bench_application_profile.h"
"""
SELFTEST = r"""
#include "SELFTEST_ONLY_PROFILE.h"
#include "lfj8_h03_mmio.h"
#include "lfj8_selector_adc.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static Lfj8H03InputBinding binding;
static Lfj8H03InputProposal proposal;
static Lfj8RangeControl control;
static int owned, startup_result, sample_result, take_result;
static unsigned startups, samples, takes;
static unsigned locked, entries, leaves, timer_reads, an2_reads, p1_reads, prs_reads;
static uint32_t first_tick=100u, last_tick=110u;
static uint16_t an2=347u;
static uint8_t p1=0xa5u, prs=9u;
static int change_an2, change_p1, change_prs;
static uint32_t enter(void *context)
{
    assert(context == NULL && !locked); ++entries; locked=1u; return 0x41u;
}
static void leave(void *context, uint32_t saved)
{
    assert(context == NULL && locked && saved == 0x41u); ++leaves; locked=0u;
}
static uint8_t read8(void *context, uint32_t address)
{
    assert(context == NULL && locked);
    if (address == 0x800701u) return (uint8_t)(p1 ^ (change_p1 && p1_reads++ ? 1u : 0u));
    if (address == 0x800203u) return (uint8_t)(prs ^ (change_prs && prs_reads++ ? 1u : 0u));
    if (address == 0x8003ebu) return 1u;
    assert(address == 0x800febu); return 0x31u;
}
static uint16_t read16(void *context, uint32_t address)
{
    assert(context == NULL && locked && address == 0x804bc6u);
    return (uint16_t)(an2 + (change_an2 && an2_reads++ ? 1u : 0u));
}
static uint32_t read32(void *context, uint32_t address)
{
    assert(context == NULL && locked && address == 0x8003e0u);
    return timer_reads++ ? last_tick : first_tick;
}
const Lfj8RegisterIo lfj8_h03_mmio = {.enter=enter,.leave=leave,.read8=read8,.read16=read16,.read32=read32};
volatile Lfj8SelectorAdc rbm_h03_selector_adc_state;
const Lfj8H03InputStartup rbm_h03_bench_native_input_startup = {0};
const Lfj8H03TargetServiceConfig rbm_h03_bench_native_can_service = {0};

static int ram_owned(void *context) { assert(context == &owned); return owned; }
static int read_input(void *context, const Lfj8H03SensorSnapshot *sensors,
    uint32_t due, Lfj8H03CycleInput *input, Lfj8H03CycleLoad *load,
    Lfj8H03InputSources *sources)
{
    (void)context; (void)sensors; (void)due; (void)input; (void)load; (void)sources;
    assert(0); /* The glue delegates to the existing capture adapter. */
    return 0;
}
const Lfj8H03ToyotaInputCapture rbm_h03_bench_native_input_capture = {
    .binding=&binding, .proposal=&proposal, .platform=&owned,
    .ram_owned=ram_owned, .read=read_input,
};
int rbm_h03_bench_prepare_startup_inputs(void *context) { (void)context; return 0; }

int lfj8_h03_input_startup(const Lfj8H03InputBinding *value, const Lfj8H03InputStartup *startup)
{
    assert(value == &binding && startup == &rbm_h03_bench_native_input_startup);
    ++startups;
    return startup_result;
}
int lfj8_h03_input_capture(const Lfj8H03InputBinding *value, const Lfj8ButtonReading *buttons,
                          uint32_t now)
{
    assert(value == &binding && buttons == NULL && now == 42u);
    ++samples;
    return sample_result;
}
int lfj8_h03_input_capture_toyota(void *context, const Lfj8H03SensorSnapshot *sensors,
    uint32_t due, Lfj8H03CycleInput *input, Lfj8H03CycleLoad *load)
{
    assert(context == &rbm_h03_bench_native_input_capture && sensors && input && load && due == 42u);
    ++takes;
    return take_result;
}

int main(void)
{
    binding = (Lfj8H03InputBinding){.io=&lfj8_h03_mmio, .adc=&rbm_h03_selector_adc_state,
                                  .control=&control, .selector_only=1u};
    assert(!rbm_h03_bench_profile_reset_inputs() && !startups);
    assert(!rbm_h03_bench_profile_sample_inputs(42u, 0u) && !samples);
    owned = 1;
    assert(!rbm_h03_bench_profile_reset_inputs() && startups == 1u);
    startup_result = 1;
    assert(rbm_h03_bench_profile_reset_inputs() && startups == 2u);
    assert(!rbm_h03_bench_profile_sample_inputs(42u, 0u) && samples == 1u);
    sample_result = 1;
    control.manual_gear = 2u;
    assert(rbm_h03_bench_profile_sample_inputs(42u, 2u));
    assert(!rbm_h03_bench_profile_sample_inputs(42u, 3u));
    assert(rbm_h03_bench_profile_sample_inputs(42u, 0u));
    Lfj8H03SensorSnapshot sensors = {0};
    Lfj8H03CycleInput input = {0};
    Lfj8H03CycleLoad load = {0};
    assert(!rbm_h03_bench_profile_capture(&owned, &sensors, 42u, &input, &load) && !takes);
    assert(!rbm_h03_bench_profile_capture(NULL, &sensors, 42u, &input, &load) && takes == 1u);
    take_result = 1;
    assert(rbm_h03_bench_profile_capture(NULL, &sensors, 42u, &input, &load) && takes == 2u);
    binding.io = NULL;
    assert(!rbm_h03_bench_profile_reset_inputs() && startups == 2u);
    assert(!rbm_h03_bench_profile_sample_inputs(42u, 0u));
    assert(!rbm_h03_bench_profile_capture(NULL, &sensors, 42u, &input, &load) && takes == 2u);
    binding.io = &lfj8_h03_mmio;
    binding.adc = NULL;
    assert(!rbm_h03_bench_profile_capture(NULL, &sensors, 42u, &input, &load) && takes == 2u);
    Lfj8H03BenchLocalRaw raw = {0};
    assert(!rbm_h03_bench_raw_local_snapshot(NULL) && !entries);
    assert(rbm_h03_bench_raw_local_snapshot(&raw) && entries == 1u && leaves == 1u && !locked);
    assert(raw.an2_raw == 347u && raw.p1data == 0xa5u && raw.first_tml0 == 100u && raw.last_tml0 == 110u);
    assert(raw.flags == 7u && raw.reserved == 0u);
    const Lfj8H03BenchLocalRaw saved = raw;
    for (unsigned which=0; which<5u; ++which) {
        timer_reads=an2_reads=p1_reads=prs_reads=0u;
        change_an2=which==0u; change_p1=which==1u; change_prs=which==2u;
        last_tick=which==3u ? 601u : which==4u ? 99u : 110u;
        assert(!rbm_h03_bench_raw_local_snapshot(&raw));
        assert(!memcmp(&raw,&saved,sizeof raw) && entries == leaves && !locked);
    }
    change_an2=change_p1=change_prs=0;
    timer_reads=an2_reads=p1_reads=prs_reads=0u;
    first_tick=UINT32_MAX-2u; last_tick=3u;
    assert(rbm_h03_bench_raw_local_snapshot(&raw) && raw.flags == 7u);
    timer_reads=0u; first_tick=last_tick=0u; an2=UINT16_MAX; prs=0u;
    assert(rbm_h03_bench_raw_local_snapshot(&raw) && raw.flags == 0u && raw.an2_raw == UINT16_MAX);
    assert(entries == leaves && !locked);
    puts("PASS native profile glue: startup, sample, capture, ownership and native I/O refusal");
    return 0;
}
"""


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cc", type=Path, required=True)
    parser.add_argument("--target", choices=("m32r", "host"), default="m32r")
    parser.add_argument("--memory-model", choices=("medium", "small"), default="medium")
    parser.add_argument("--profile", type=Path, help="Actual top-level native header; not a fixture")
    parser.add_argument("--base", type=Path, help="Optional exact H03 identity check")
    parser.add_argument("--self-test", action="store_true", help="Host-only harness, never a release profile")
    parser.add_argument("--raw-only", action="store_true", help="Build the independent native MMIO snapshot without Toyota providers")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.self_test and args.target != "host":
        parser.error("--self-test is host-only; use a real profile for M32R compilation")
    if args.raw_only and (args.self_test or args.profile is not None):
        parser.error("--raw-only is independent of --profile and --self-test")
    if not args.raw_only and not args.self_test and args.profile is None:
        parser.error("Supply the actual --profile or select --target host --self-test")
    compiler = args.cc.resolve(strict=True)
    output = args.out.resolve()
    output.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ, PATH=str(compiler.parent) + os.pathsep + os.environ.get("PATH", ""))
    report = {"target": args.target, "compiler": str(compiler), "commands": [], "objects": [],
              "h03_identity_verified": False, "hardware_verified": False, "flashable_image": None,
              "bench_pair_ready": False, "raw_api_only": args.raw_only,
              "required_native_providers": [] if args.raw_only else list(NATIVE_PROVIDERS)}
    includes = [HERE, ROOT / "controller/include", ROOT / "controller/vendor/toyota/include", ROOT / "diagnostics"]
    flags = ["-Os", "-std=c11", "-Wall", "-Wextra", "-Werror", "-ffunction-sections", "-fdata-sections",
             *(value for path in includes for value in ("-I", str(path)))]
    if args.target == "m32r":
        flags += ["-m32r", "-mmodel=" + args.memory_model, "-msdata=none", "-Wa,-EB"]

    def run(command, *, expected=0):
        process = subprocess.run(list(map(str, command)), env=environment, capture_output=True, timeout=60)
        text = (process.stdout + process.stderr).decode("utf-8", errors="replace")
        report["commands"].append({"argv": list(map(str, command)), "exit_code": process.returncode,
                                   "expected_exit": expected, "output": text})
        if expected == "nonzero":
            if process.returncode == 0:
                raise ValueError("An invalid profile was unexpectedly accepted")
        elif process.returncode != expected:
            raise ValueError(text or f"Compiler failed: {process.returncode}")
        return text

    try:
        report["compiler_version"] = run([compiler, "--version"]).splitlines()[0]
        report["compiler_sha256"] = digest(compiler)
        report["source_sha256"] = {source: digest(HERE / source) for source in
                                    (*MODULES, "bench_application_profile.h", "bench_sensor_profile.h",
                                     "bench_engine_profile.h", "bench_output_profile.h")}
        if args.base:
            registry = json.loads((ROOT / "data/sources.json").read_text(encoding="utf-8"))
            h03 = next(value for value in registry["supporting_materials"] if value["id"] == "H03")
            if args.base.stat().st_size != h03["bytes"] or digest(args.base) != h03["sha256"]:
                raise ValueError("Supply the exact H03 source")
            from check_h03_bench_sensor_profile import check_stock
            report["h03_clock_sensor_source"] = check_stock(args.base)
            rom = args.base.read_bytes()
            if rom[0x040370:0x040374] != bytes.fromhex("20246103"):
                raise ValueError("H03 AN2 store differs from the verified native input path")
            call = rom[0x040184:0x040188]
            if call[0] != 0xfe:
                raise ValueError("H03 P1 source call is not the expected BL")
            target = 0x040184 + 4 * int.from_bytes(call[1:], "big", signed=True)
            if bytes.fromhex("800701") not in rom[target:target+64]:
                raise ValueError("H03 P1 source no longer uses the recorded native P1DATA")
            report["raw_local_source"] = {"an2_ram": "0x804BC6", "an2_store": "0x040370",
                                          "p1data": "0x800701", "p1_callee": f"0x{target:06X}",
                                          "tml0ct": "0x8003E0", "conversion_age_known": False,
                                          "independent_pn_qualified": False}
            report["h03_identity_verified"] = True
        with TemporaryDirectory(prefix="rbm-native-profile-") as temporary:
            stage = Path(temporary)
            if args.raw_only:
                profile = None
            elif args.self_test:
                profile = stage / "SELFTEST_ONLY_PROFILE.h"
                profile.write_text(SELFTEST_PROFILE, encoding="ascii")
            else:
                profile = args.profile.resolve(strict=True)
                if re.search(r"(?:^|[_-])(?:fixture|simulator|selftest|test)(?:[_\-.]|$)", profile.name, re.I):
                    raise ValueError("A fixture/simulator header is not a native application profile")
            profile_flags = (["-I", str(profile.parent), '-DRBM_H03_APPLICATION_PROFILE="' + profile.name + '"']
                             if profile is not None else [])
            for source in ((MODULES[0],) if args.raw_only else MODULES):
                destination = output / (Path(source).stem + ".o")
                run([compiler, *flags, *profile_flags, "-c", HERE / source, "-o", destination])
                report["objects"].append({"name": source, "path": str(destination),
                                          "sha256": digest(destination), "bytes": destination.stat().st_size})
            if args.raw_only:
                nm = run([compiler, "-print-prog-name=nm"]).strip()
                undefined = run([nm, "--undefined-only", "--format=posix", destination])
                symbols = []
                for line in undefined.splitlines():
                    if not line.strip():
                        continue
                    match = re.fullmatch(r"(\S+)\s+U\s*", line)
                    if not match:
                        raise ValueError("Unrecognized native nm output: " + line)
                    symbol = match.group(1)
                    if symbol.startswith("_"):
                        symbol = symbol[1:]
                    symbols.append(symbol)
                if "lfj8_h03_mmio" not in symbols or set(symbols) - {"lfj8_h03_mmio", "memcpy", "memset"}:
                    raise ValueError("Raw capture depends on unexpected providers: " + ", ".join(symbols))
                report["raw_only_dependencies"] = sorted(symbols)
            if args.self_test:
                fixture = stage / "glue-test.c"
                fixture.write_text(SELFTEST, encoding="ascii")
                executable = stage / ("glue-test.exe" if os.name == "nt" else "glue-test")
                run([compiler, *flags, *profile_flags, fixture,
                     output / "lfj8_h03_bench_application_profile.o", "-o", executable])
                result = run([executable])
                if not result.startswith("PASS native profile glue:"):
                    raise ValueError("The host harness did not finish")
                probe = stage / "reject.c"
                probe.write_text('#include "bench_application_profile.h"\n', encoding="ascii")
                run([compiler, *flags, "-c", probe, "-o", stage / "reject.o"], expected="nonzero")
                for extra in ("#undef RBM_H03_BENCH_TOYOTA_MAX_LATENESS_TICKS\n"
                              "#define RBM_H03_BENCH_TOYOTA_MAX_LATENESS_TICKS 5000u\n",
                              "#define RBM_H03_PROFILE_OUTPUT_ISOLATION_MASK 15u\n"):
                    bad = SELFTEST_PROFILE.replace('#include "bench_application_profile.h"',
                                                   extra + '#include "bench_application_profile.h"')
                    (stage / "BAD_SELFTEST_ONLY.h").write_text(bad, encoding="ascii")
                    probe.write_text('#include "BAD_SELFTEST_ONLY.h"\n', encoding="ascii")
                    run([compiler, *flags, "-I", stage, "-c", probe, "-o", stage / "reject.o"], expected="nonzero")
                report["status"] = "PASS_HOST_GLUE_ONLY"
            elif args.raw_only:
                report["status"] = "PASS_RAW_CAPTURE_OBJECT_ONLY"
            else:
                report["status"] = "PASS_RELOCATABLE_OBJECTS_ONLY"
            report["profile_sha256"] = digest(profile) if profile is not None else None
            report["self_test_profile"] = args.self_test
            report["memory_cost"] = {"flash_bytes": None, "ram_bytes": None, "stack_bytes": None,
                                      "reason": "Requires final M32R placement and inclusive stack analysis"}
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        report.update(status="FAILED", error=str(error))
    (output / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report.get(key) for key in
                      ("status", "target", "error", "h03_identity_verified", "bench_pair_ready", "flashable_image")}))
    return 1 if report["status"] == "FAILED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
