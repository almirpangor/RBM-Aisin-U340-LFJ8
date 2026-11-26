"""Run the CAN-05 host round trip using the pinned Chery donor Git blobs."""

import argparse
import json
from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
DONOR_DIR = "engine_integration/native_chery"
QUALIFICATION = "chery_request_qualification"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--donor-repo", required=True, type=Path, help="Local R3 Git repository")
    parser.add_argument("--cc", default="zig", help="Zig, GCC or Clang executable")
    args = parser.parse_args()
    sources = json.loads((ROOT / "data/sources.json").read_text(encoding="utf-8"))
    revision = sources["repositories"]["R3"]["commit"]
    compiler = [args.cc]
    if Path(args.cc).stem.lower() == "zig":
        compiler.append("cc")

    with tempfile.TemporaryDirectory(prefix="chery-1ae-") as tmp:
        work = Path(tmp)
        for suffix in (".h", ".c"):
            name = QUALIFICATION + suffix
            blob = subprocess.check_output([
                "git", "-C", str(args.donor_repo), "show", f"{revision}:{DONOR_DIR}/{name}",
            ])
            (work / name).write_bytes(blob)

        executable = work / "chery_1ae_roundtrip.exe"
        subprocess.run([
            *compiler, "-std=c11", "-O2", "-UNDEBUG", "-Wall", "-Wextra", "-Werror",
            "-pedantic", "-I", str(work), "targets/lfj8/lfj8_bridge.c",
            "targets/bosch/chery_torque_rx.c", str(work / (QUALIFICATION + ".c")),
            "targets/bosch/test_chery_1ae_roundtrip.c", "-o", str(executable),
        ], cwd=ROOT, check=True)
        subprocess.run([str(executable)], check=True)


if __name__ == "__main__":
    main()
