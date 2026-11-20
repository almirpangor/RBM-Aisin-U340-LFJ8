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


def git_command(repo: Path) -> list[str]:
    return ["git", "--no-replace-objects", "-C", str(repo)]


def check_revision(name: str, repo: Path, revision: str) -> bool:
    try:
        resolved = subprocess.check_output(
            [*git_command(repo), "rev-parse", "--verify", f"{revision}^{{commit}}"],
            text=True, stderr=subprocess.PIPE,
        ).strip()
    except subprocess.CalledProcessError as error:
        raise ValueError(f"{name}: pinned commit {revision} is unavailable in {repo}") from error
    matches = resolved == revision
    print(f"{name} pinned commit: {'OK' if matches else 'MISMATCH'}; {resolved}")
    return matches


def verify(donor_repo: Path, input_images: dict[str, Path],
           additional_repos: dict[str, Path] | None = None) -> bool:
    registry = json.loads((ROOT / "data/sources.json").read_text(encoding="utf-8"))
    repos = {"R1": donor_repo}
    for name, path in (additional_repos or {}).items():
        if name == "R1" or name not in registry["repositories"]:
            raise ValueError(f"invalid additional repository ID: {name}")
        repos[name] = path
    spec = registry["specification"]
    checks = [checked_file(spec, (ROOT / spec["path"]).read_bytes())]
    for name, repo in repos.items():
        checks.append(check_revision(name, repo, registry["repositories"][name]["commit"]))
    # H03 is the active 9E1C input. S05/S06 are historical research donors.
    entries = [*registry["firmware"],
               *(entry for entry in registry["supporting_materials"] if entry["id"] == "H03")]
    for entry in entries:
        source = entry.get("repository")
        if source is None:
            local_path = input_images.get(entry["id"])
            if local_path is None:
                print(f"{entry['id']}: no local path supplied; skipped")
                continue
            checks.append(checked_file(entry, local_path.read_bytes()))
            continue

        revision = registry["repositories"][source]["commit"]
        if source not in repos:
            raise ValueError(f"{entry['id']}: supply --repo {source} PATH for the registered Git source")
        git = git_command(repos[source])
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
    parser.add_argument("--repo", action="append", nargs=2, default=[], metavar=("ID", "PATH"),
                        help="also verify a pinned donor commit from a local clone, e.g. --repo R3 PATH")
    parser.add_argument("--base-9e1c", type=Path, help="Active H03 input LFJ8-T-D.bin")
    parser.add_argument("--pcm-image", "--lfj8", type=Path, help="Optional historical S05 PCM image")
    parser.add_argument("--tcm-donor", type=Path, help="Path to the approved S06 9E1B donor")
    args = parser.parse_args()
    if args.base_9e1c is None and args.pcm_image is None:
        parser.error("Supply --base-9e1c for the active target, or --pcm-image for a historical check")
    input_images = {}
    if args.base_9e1c is not None:
        input_images["H03"] = args.base_9e1c
    if args.pcm_image is not None:
        input_images["S05"] = args.pcm_image
    if args.tcm_donor is not None:
        input_images["S06"] = args.tcm_donor
    additional_repos = {}
    for name, path in args.repo:
        if name in additional_repos:
            parser.error(f"--repo {name} was supplied more than once")
        additional_repos[name] = Path(path)
    try:
        return 0 if verify(args.donor_repo, input_images, additional_repos) else 1
    except (OSError, subprocess.CalledProcessError, ValueError) as error:
        print(f"Verification failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
