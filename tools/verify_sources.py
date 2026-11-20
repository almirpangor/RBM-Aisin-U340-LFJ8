"""Verify the specification and registered firmware inputs, without modifying them."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def checked_file(entry: dict, content: bytes) -> bool:
    digest = hashlib.sha256(content).hexdigest()
    label = entry.get("id", "SPEC")
    matches = digest == entry["sha256"] and len(content) == entry["bytes"]
    print(f"{label}: {'OK' if matches else 'MISMATCH'}; {len(content)} bytes; {digest}")
    return matches


def verify(donor_repo: Path, lfj8: Path) -> bool:
    registry = json.loads((ROOT / "data/sources.json").read_text(encoding="utf-8"))
    spec = registry["specification"]
    checks = [checked_file(spec, (ROOT / spec["path"]).read_bytes())]
    for entry in registry["firmware"]:
        source = entry["repository"]
        if source is None:
            checks.append(checked_file(entry, lfj8.read_bytes()))
            continue

        revision = registry["repositories"][source]["commit"]
        git = ["git", "-C", str(donor_repo)]
        object_spec = f"{revision}:{entry['path']}"
        blob = subprocess.check_output([*git, "rev-parse", "--verify", object_spec], text=True).strip()
        content = subprocess.check_output([*git, "cat-file", "blob", object_spec])
        checks.append(checked_file(entry, content))
        blob_matches = blob == entry["git_blob_sha"]
        print(f"{entry['id']} Git blob: {'OK' if blob_matches else 'MISMATCH'}; {blob}")
        checks.append(blob_matches)
    return all(checks)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--donor-repo", required=True, type=Path, help="Local Git clone of R1")
    parser.add_argument("--lfj8", required=True, type=Path, help="Path to the original S05 dump")
    args = parser.parse_args()
    try:
        return 0 if verify(args.donor_repo, args.lfj8) else 1
    except (OSError, subprocess.CalledProcessError, ValueError) as error:
        print(f"Verification failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
