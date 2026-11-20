"""Recompute the archived Bosch E4M3 file comparisons from local Git objects."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess

from tools.verify_sources import git_command


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_COMPARISONS = {
    ("REV8", "E4M2"),
    ("REV8", "E4M3"),
    ("E4M2", "E4M3"),
}
REQUIRED_COPY_GROUPS = (
    frozenset(("REV8", "REV8_E4R32")),
    frozenset(("E4M2", "E4M2_E4R32")),
    frozenset(("E4M3", "E4M3_PUBLICATION", "E4M3_E4R32")),
)
REQUIRED_IMAGES = {"S02"} | set().union(*REQUIRED_COPY_GROUPS)


def read_image(name, entry, repositories):
    repo, pinned_commit = repositories[entry["repository"]]
    if entry["commit"] != pinned_commit:
        raise ValueError(f"{name}: audit commit differs from the source registry")

    git = git_command(repo)
    object_spec = f"{pinned_commit}:{entry['path']}"
    blob = subprocess.check_output(
        [*git, "rev-parse", "--verify", object_spec], text=True, stderr=subprocess.PIPE,
    ).strip()
    if blob != entry["git_blob_sha1"]:
        raise ValueError(f"{name}: Git blob ID differs from the audit record")
    image = subprocess.check_output([*git, "cat-file", "blob", blob], stderr=subprocess.PIPE)
    if len(image) != entry["bytes"] or sha256(image).hexdigest() != entry["sha256"]:
        raise ValueError(f"{name}: image length or SHA-256 differs from the audit record")
    return image


def changed_ranges(old: bytes, new: bytes) -> list[list[int]]:
    """Return inclusive zero-based offsets of maximal runs of changed bytes."""
    if len(old) != len(new):
        raise ValueError("Cannot compare images of different lengths")
    ranges = []
    start = None
    for offset, (old_byte, new_byte) in enumerate(zip(old, new)):
        if old_byte != new_byte:
            if start is None:
                start = offset
        elif start is not None:
            ranges.append([start, offset - 1])
            start = None
    if start is not None:
        ranges.append([start, len(old) - 1])
    return ranges


def require_archive_coverage(files, groups, comparisons):
    missing_images = REQUIRED_IMAGES.difference(files)
    if missing_images:
        raise ValueError(f"Missing archived image entries: {', '.join(sorted(missing_images))}")

    pairs = [(row["old"], row["new"]) for row in comparisons]
    observed_pairs = set(pairs)
    missing_pairs = REQUIRED_COMPARISONS - observed_pairs
    if missing_pairs:
        missing = ", ".join(f"{old} -> {new}" for old, new in sorted(missing_pairs))
        raise ValueError(f"Missing archived comparisons: {missing}")
    if len(pairs) != len(observed_pairs):
        raise ValueError("Duplicate archived comparison")

    copy_groups = [frozenset(group) for group in groups]
    for required in REQUIRED_COPY_GROUPS:
        if not any(required <= observed for observed in copy_groups):
            missing = ", ".join(sorted(required))
            raise ValueError(f"Missing or incomplete archived copy group: {missing}")
    if len(copy_groups) != len(set(copy_groups)) or any(
        len(group) != len(members) for group, members in zip(groups, copy_groups)
    ):
        raise ValueError("Duplicate archived copy group or member")


def verify(manifest, registry, r1, r4):
    if manifest["schema_version"] != 1:
        raise ValueError("Unsupported E4M3 audit schema")
    files = manifest["files"]
    groups = manifest["byte_identical_groups"]
    comparisons = manifest["comparisons"]
    require_archive_coverage(files, groups, comparisons)

    repositories = {}
    for identifier, directory in (("R1", r1), ("R4", r4)):
        source = registry["repositories"][identifier]
        name = source["url"].removeprefix("https://github.com/")
        repositories[name] = (directory, source["commit"])

    s04 = next((item for item in registry["firmware"] if item["id"] == "S04"), None)
    e4m3 = files["E4M3"]
    if (s04 is None or s04["repository"] != "R1" or
        registry["repositories"]["R1"]["url"] != f"https://github.com/{e4m3['repository']}" or
        any(e4m3[field] != s04[field] for field in ("path", "bytes", "sha256")) or
        e4m3["git_blob_sha1"] != s04["git_blob_sha"]):
        raise ValueError("E4M3 audit entry differs from the registered S04")

    images = {name: read_image(name, entry, repositories) for name, entry in files.items()}
    for group in groups:
        if len(set(group)) < 2 or any(images[name] != images[group[0]] for name in group[1:]):
            raise ValueError(f"Images are not byte-identical: {', '.join(group)}")

    results = []
    for comparison in comparisons:
        old, new = comparison["old"], comparison["new"]
        ranges = changed_ranges(images[old], images[new])
        actual = {
            "changed_bytes": sum(end - start + 1 for start, end in ranges),
            "contiguous_range_count": len(ranges),
            "inclusive_file_offset_ranges": ranges,
        }
        for field, computed in actual.items():
            if comparison[field] != computed:
                raise ValueError(f"{old} -> {new}: {field} differs from the recorded audit")
        results.append({"old": old, "new": new, "changed_bytes": actual["changed_bytes"],
                        "contiguous_range_count": actual["contiguous_range_count"]})

    return {
        "status": "PASS_OFFLINE_ONLY",
        "image_count": len(images),
        "byte_identical_groups": groups,
        "comparisons": results,
        "hardware_verified": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--r1", required=True, type=Path, help="Local R1 Git repository")
    parser.add_argument("--r4", required=True, type=Path, help="Local R4 Git repository")
    args = parser.parse_args()
    try:
        manifest = json.loads((ROOT / "data/e4m3-diff.json").read_text(encoding="utf-8"))
        registry = json.loads((ROOT / "data/sources.json").read_text(encoding="utf-8"))
        report = verify(manifest, registry, args.r1, args.r4)
    except subprocess.CalledProcessError as error:
        parser.exit(1, f"Could not read a pinned Git object: {error.stderr!r}\n")
    except (KeyError, OSError, ValueError) as error:
        parser.exit(1, f"E4M3 offline check failed: {error}\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
