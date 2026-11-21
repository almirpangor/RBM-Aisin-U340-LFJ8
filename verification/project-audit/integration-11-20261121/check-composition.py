"""Measure all submitted H03 providers without inventing hardware bindings.

The profile supplies simulator timing and declarations, never implementations
for the missing input, engine, output or RAM qualification providers. No BIN is
emitted. Keep this probe separate from release-profile generation.
"""
import argparse
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "targets/lfj8")]
from tools import check_h03_image_layout as layout
from check_h03_target_platform import MANUAL_PROFILE
from check_h03_can_monitor_revoke import FIXTURE_PROFILE

# Only declarations and values from the existing simulator are imported.
# The real Task 2 provider and qualified NVM block pair remain undefined.
PROFILE = MANUAL_PROFILE.replace("#define RBM_H03_PROFILE_READ_ADAPTATION NULL", "")
PROFILE += "\nint fixture_engine_context(void *, const Lfj8H03SensorSnapshot *, " \
    "Ta2005EngineQualificationContext *, bool *, uint32_t *);\n"
PROFILE += "\n".join(line for line in FIXTURE_PROFILE.splitlines()
                     if line.startswith("#define RBM_H03_PROFILE_ENGINE_")) + "\n"
PROFILE += ('extern const uint8_t qualified_adaptation_blocks[2];\n'
            '#define RBM_H03_PROFILE_ADAPTATION_BLOCKS qualified_adaptation_blocks\n'
            '#include "lfj8_h03_toyota_nvm_profile.h"\n')

PROVIDERS = (
    "lfj8_h03_target_memory.c", "lfj8_h03_ram_owner.c",
    "lfj8_h03_target_commit.c", "lfj8_h03_nvm_native.c",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("base", "gcc", "controller", "bridge", "storage-report", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    original = layout.BINDING_MODULES
    with TemporaryDirectory(prefix="rbm-all-providers-") as directory:
        profile = Path(directory) / "SIMULATOR_ONLY.h"
        profile.write_text(PROFILE, encoding="ascii")
        options = argparse.Namespace(
            **{key: value.resolve() for key, value in vars(args).items()},
            profile="padding-candidate", memory_model="medium",
            with_bindings=True, with_dtc_rx=True, with_dma4_guard=True,
            with_can_service=True, with_service_guard=True, with_ram_owner=True,
            with_application_entries=True, with_resident_constants=True,
            application_profile=profile, cpu_test=False,
        )
        layout.BINDING_MODULES = tuple(dict.fromkeys((*original, *PROVIDERS)))
        try:
            try:
                report = layout.build(options)
            except ValueError:
                path = args.out / "layout.json"
                if not path.is_file():
                    raise
                report = json.loads(path.read_text(encoding="utf-8"))
                if report.get("status") != "FAIL_BINDINGS":
                    raise
        finally:
            layout.BINDING_MODULES = original
    report.update(
        scope="All submitted C providers; simulator timing and input declarations only",
        simulator_profile=PROFILE,
        extra_providers=list(PROVIDERS),
        hardware_verified=False, flashable_image=None,
        success_does_not_mean_release_ready=True,
    )
    (args.out / "composition.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report.get(key) for key in (
        "status", "flash_payload_bytes", "new_static_ram_bytes", "unresolved_symbols",
        "known_sections_candidate_plan", "known_sections_placement_error")}, indent=2))


if __name__ == "__main__":
    main()
