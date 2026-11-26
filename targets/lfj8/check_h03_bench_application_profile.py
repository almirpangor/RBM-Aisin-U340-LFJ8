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

static Lfj8H03InputBinding binding;
static Lfj8H03InputProposal proposal;
static Lfj8RangeControl control;
static int owned, startup_result, sample_result, take_result;
static unsigned startups, samples, takes;
const Lfj8RegisterIo lfj8_h03_mmio = {0};
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
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.self_test and args.target != "host":
        parser.error("--self-test is host-only; use a real profile for M32R compilation")
    if not args.self_test and args.profile is None:
        parser.error("Supply the actual --profile or select --target host --self-test")
    compiler = args.cc.resolve(strict=True)
    output = args.out.resolve()
    output.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ, PATH=str(compiler.parent) + os.pathsep + os.environ.get("PATH", ""))
    report = {"target": args.target, "compiler": str(compiler), "commands": [], "objects": [],
              "h03_identity_verified": False, "hardware_verified": False, "flashable_image": None,
              "bench_pair_ready": False, "required_native_providers": list(NATIVE_PROVIDERS)}
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
            report["h03_identity_verified"] = True
        with TemporaryDirectory(prefix="rbm-native-profile-") as temporary:
            stage = Path(temporary)
            if args.self_test:
                profile = stage / "SELFTEST_ONLY_PROFILE.h"
                profile.write_text(SELFTEST_PROFILE, encoding="ascii")
            else:
                profile = args.profile.resolve(strict=True)
                if re.search(r"(?:^|[_-])(?:fixture|simulator|selftest|test)(?:[_\-.]|$)", profile.name, re.I):
                    raise ValueError("A fixture/simulator header is not a native application profile")
            profile_flags = ["-I", str(profile.parent), '-DRBM_H03_APPLICATION_PROFILE="' + profile.name + '"']
            for source in MODULES:
                destination = output / (Path(source).stem + ".o")
                run([compiler, *flags, *profile_flags, "-c", HERE / source, "-o", destination])
                report["objects"].append({"name": source, "path": str(destination),
                                          "sha256": digest(destination), "bytes": destination.stat().st_size})
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
            else:
                report["status"] = "PASS_RELOCATABLE_OBJECTS_ONLY"
            report["profile_sha256"] = digest(profile)
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
