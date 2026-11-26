"""Serialize a complete linked H03 candidate and retain its unqualified status.

This is the byte-production step, not a release qualification. It accepts an
actual executable ELF and the matching complete placement report. No fixtures,
partial links, unchanged source BINs, or status overrides are accepted.
"""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from tempfile import TemporaryDirectory

if __package__:
    from . import h03_image
    from .package_workset import BOSCH_ID, BOSCH_ID_OFFSET, FIRMWARE_SIZES
else:
    import h03_image
    from package_workset import BOSCH_ID, BOSCH_ID_OFFSET, FIRMWARE_SIZES


def _json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def compose_images(base, elf, layout_path, patches_path, output, *, source_commit,
                   ecu=None, memory_profile=None):
    if not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise ValueError("Supply a full source commit SHA")
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("Use a new output directory; existing artifacts are never replaced")
    layout = _json(layout_path)
    patches = _json(patches_path) if patches_path is not None else []
    if not isinstance(patches, list):
        raise ValueError("Patches must be a list of exact before/after records")
    parsed = h03_image.read_elf(elf, 2)
    forbidden = sorted(name for name in parsed["symbols"]
                       if "fixture" in name.casefold() or name.startswith(("test_", "rbm_test_"))
                       or name == "integration_test")
    if forbidden:
        raise ValueError("Linked image still contains test providers: " + ", ".join(forbidden))
    if memory_profile is not None:
        from lfj8_h03_bench_memory_profile import verify_linked_profile
        verify_linked_profile(_json(memory_profile), parsed)
    image, tcm_manifest = h03_image.compose(Path(base).read_bytes(), parsed, layout, patches)
    if (tcm_manifest.get("status") != "UNQUALIFIED_LINKED_IMAGE"
            or tcm_manifest.get("bench_pair_ready") is not False):
        raise ValueError("Composition unexpectedly changed its qualification status")
    tcm_name = "TCM_H03_UNQUALIFIED_LINKED_IMAGE.bin"
    artifacts = {tcm_name: image}
    manifest = {
        "status": "UNQUALIFIED_LINKED_IMAGES", "bench_pair_ready": False,
        "hardware_verified": False, "source_commit": source_commit,
        "builder_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "layout_sha256": sha256(Path(layout_path).read_bytes()).hexdigest(),
        "patches_sha256": (sha256(Path(patches_path).read_bytes()).hexdigest()
                           if patches_path is not None else None),
        "memory_profile_sha256": (sha256(Path(memory_profile).read_bytes()).hexdigest()
                                  if memory_profile is not None else None),
        "tcm": {"file": tcm_name, **tcm_manifest},
        "ecu": None,
        "qualification": "Requires final-image execution, ownership, integrity and paired release checks",
    }
    if ecu is not None:
        data = Path(ecu).read_bytes()
        if (len(data) != FIRMWARE_SIZES["ecu_e4m3"] or data.startswith(b"\x7fELF")
                or not data.startswith(BOSCH_ID, BOSCH_ID_OFFSET)):
            raise ValueError("Expected a full Bosch E4M3 image with its platform identifier")
        name = "BOSCH_UNQUALIFIED_INPUT_COPY.bin"
        artifacts[name] = data
        manifest["ecu"] = {
            "file": name, "input_name": Path(ecu).name,
            "bytes": len(data), "sha256": sha256(data).hexdigest(),
            "status": "UNQUALIFIED_INPUT_COPY", "bench_pair_ready": False,
            "disposition": "Byte-identical input copy; no new ECU behavior or qualification is asserted",
        }
    # Prepare all content before publishing the new directory. A failed link,
    # provenance check, or copy never leaves a half-written candidate package.
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".h03-compose-", dir=output.parent) as temporary:
        staged = Path(temporary) / "images"
        staged.mkdir()
        for name, data in artifacts.items():
            (staged / name).write_bytes(data)
        (staged / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (staged / "SHA256SUMS.txt").write_text(
            "".join(f"{sha256(data).hexdigest()}  {name}\n" for name, data in artifacts.items()),
            encoding="ascii")
        (staged / "NOT_FOR_FLASHING.txt").write_text(
            "UNQUALIFIED LINKED CANDIDATE — NOT A BENCH/VEHICLE RELEASE.\n"
            "Inspect manifest.json. Final execution, integrity, ownership and paired checks are required.\n",
            encoding="utf-8")
        if output.exists():
            raise ValueError("Output directory was created by another process")
        os.rename(staged, output)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("base", "elf", "layout", "out"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    for name in ("patches", "ecu", "memory-profile"):
        parser.add_argument("--" + name, type=Path)
    args = parser.parse_args()
    try:
        result = compose_images(args.base, args.elf, args.layout, args.patches, args.out,
                                source_commit=args.source_commit, ecu=args.ecu,
                                memory_profile=args.memory_profile)
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"No candidate images produced: {error}\n")
    print(json.dumps({"status": result["status"], "out": str(args.out),
                      "tcm_sha256": result["tcm"]["sha256"], "bench_pair_ready": False}))


if __name__ == "__main__":
    main()
