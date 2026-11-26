"""Measure merged native objects with an explicit SIMULATOR profile, never a BIN.

The profile supplies timing only to retain the real application binding. Platform
providers remain unresolved: no synthetic output driver or sensor config is linked.
"""
import argparse
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT / "targets/lfj8")]
from tools import check_h03_image_layout as layout
import check_h03_can_monitor_revoke as revoke
from check_h03_application_binding import FIXTURE_PROFILE


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("base", "gcc", "controller", "bridge", "storage-report", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    revoke.ALIASES.update({
        "rbm_h03_cycle_state": "control/cycle",
        "rbm_h03_runtime_state": "control/runtime",
        "rbm_h03_cycle_workspace": "workspace/toyota",
        "rbm_h03_cycle_input": "workspace/cycle_input",
    })
    addresses, aliases = revoke.aliases_for(args.base, args.gcc, args.storage_report)
    original = layout.build
    results = {}
    with TemporaryDirectory(prefix="rbm-explicit-model-profile-") as folder:
        profile = Path(folder) / "SIMULATOR_ONLY_PROFILE.h"
        profile.write_text(FIXTURE_PROFILE, encoding="ascii")

        def capture(options):
            options.application_profile = profile
            options.with_dtc_rx = True
            try:
                return original(options)
            finally:
                path = options.out / "layout.json"
                if path.exists():
                    data = json.loads(path.read_text(encoding="utf-8"))
                    data["profile_scope"] = "SIMULATOR_ONLY; no hardware calibration"
                    data["profile_text"] = FIXTURE_PROFILE
                    data["aliases"] = {k: [hex(a), hex(b)] for k, (a, b) in addresses.items()}
                    name = options.out.name
                    (args.out / (name + ".json")).write_text(
                        json.dumps(data, indent=2) + "\n", encoding="utf-8")
                    results[name] = {k: data.get(k) for k in (
                        "status", "flash_payload_bytes", "new_static_ram_bytes",
                        "unresolved_symbols", "known_sections_candidate_plan")}
        layout.build = capture
        try:
            revoke.aggregate_placement(args, aliases)
        finally:
            layout.build = original
    report = {"scope": "Known objects with real binding and explicit simulator timing only",
              "cases": results, "hardware_verified": False, "flashable_image": None}
    (args.out / "summary.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
