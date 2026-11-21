"""Deterministic bytes from a fully linked H03 ELF and explicit OEM patches.

This layer does not qualify execution, Flash ownership or physical outputs.
It cannot promote an address model to a bench/road release. The release builder
must run those checks against the resulting image separately.
"""
from hashlib import sha256
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "targets/lfj8"))
from lfj8_h03_layout import alloc_sections, read_elf, verify_linked
from tools.inspect_lfj8_tcm import H03_PART_NUMBER, IDENTITY, IDENTITY_OFFSET, IMAGE_SIZE, inspect

H03_SHA256 = "844a11b809cda1f2ccaf90cb6a75666009487ccedd2e8190b7eb46137b855544"
MARKERS = ((0x8000, b"\x5a\xa5"), (0x7fffe, b"\xa5\x5a"))


def _image_identity(image):
    if not inspect(image, H03_PART_NUMBER)["matches_expected_id"]:
        raise ValueError("Expected full H03 9E1C image identity")
    if any(image[start:start + len(value)] != value for start, value in MARKERS):
        raise ValueError("H03 boot marker differs")
    match = IDENTITY.match(image, IDENTITY_OFFSET)
    return match.span()


def _nonoverlapping(items):
    previous = None
    for item in sorted(items, key=lambda row: (row["address"], row["end"])):
        if previous is not None and item["address"] < previous["end"]:
            raise ValueError("Overlapping image writes: " + previous["name"] + " / " + item["name"])
        previous = item


def _patches(base, records):
    result = []
    for record in records:
        address = record.get("address")
        if type(address) is not int:
            raise ValueError("Patch address must be an integer")
        try:
            before = bytes.fromhex(record["before"])
            after = bytes.fromhex(record["after"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("Patch must give exact before/after bytes") from error
        if (not before or len(before) != len(after) or address < 0
                or address + len(after) > IMAGE_SIZE):
            raise ValueError("Patch span or length is invalid")
        if base[address:address + len(before)] != before:
            raise ValueError(f"Patch preimage differs at {address:#x}")
        if not isinstance(record.get("name"), str) or not record["name"]:
            raise ValueError("Patch requires its source name")
        result.append(dict(address=address, end=address + len(after),
                           data=after, name=record["name"]))
    _nonoverlapping(result)
    return result


def compose(base, elf, layout, patches=()):
    """Return bytes and an UNQUALIFIED manifest; never write either to disk.

    patches explicitly authorize occupied OEM locations. A patch may exactly
    match one ELF section (a fixed redirect) or lie outside every ELF section
    (e.g. a capture branch). Partial overlap and conflicting bytes are rejected.
    NOLOAD RAM has no file bytes and is never copied into Flash.
    """
    digest = sha256(base).hexdigest()
    if len(base) != IMAGE_SIZE or digest != H03_SHA256:
        raise ValueError("Base is not the pinned H03")
    identity_start, identity_end = _image_identity(base)
    if (layout.get("status") != "PASS_ADDRESS_MODEL_ONLY"
            or layout.get("accepted_layout") is not True
            or layout.get("unresolved_symbols")
            or layout.get("base", {}).get("sha256") != digest
            or layout.get("elf_sha256") != elf.get("sha256")):
        raise ValueError("A complete matching linked layout is required")
    if not layout.get("required_roots") or not layout.get("placements"):
        raise ValueError("Missing complete roots or placement plan")
    verify_linked(elf, layout["placements"], layout["required_roots"])

    approved = _patches(base, patches)
    by_span = {(item["address"], item["end"]): item for item in approved}
    allocated = alloc_sections(elf)
    writes = []
    ram_bytes = 0
    for section in allocated:
        if section["type"] == 8:
            ram_bytes += section["size"]
            continue
        start, length = section["address"], section["size"]
        end = start + length
        if start < 0 or end > IMAGE_SIZE or len(section["data"]) != length:
            raise ValueError("ELF Flash section outside image or truncated")
        authorized = by_span.get((start, end))
        if authorized is not None:
            if authorized["data"] != section["data"]:
                raise ValueError("ELF redirect differs from its authorized patch")
        elif base[start:end] != b"\xff" * length:
            raise ValueError(f"Occupied OEM bytes lack an exact patch at {start:#x}")
        writes.append(dict(address=start, end=end, data=section["data"],
                           name=section["name"]))

    # Multiple ELF sections must not alias even if their bytes happen to match.
    _nonoverlapping(writes)
    spans = {(item["address"], item["end"]) for item in writes}
    writes.extend(item for item in approved if (item["address"], item["end"]) not in spans)
    _nonoverlapping(writes)
    protected = [(identity_start, identity_end), *( (s, s + len(v)) for s, v in MARKERS)]
    for item in writes:
        if any(item["address"] < last and first < item["end"] for first, last in protected):
            raise ValueError("A write touches protected H03 identity or boot markers")

    result = bytearray(base)
    manifest_writes = []
    changed = low_changed = 0
    for item in sorted(writes, key=lambda row: row["address"]):
        first, last = item["address"], item["end"]
        before, after = base[first:last], item["data"]
        delta = sum(a != b for a, b in zip(before, after))
        changed += delta
        low_changed += sum(before[i] != after[i] for i in range(max(0, min(last, 0x8000) - first)))
        result[first:last] = after
        manifest_writes.append(dict(address=first, bytes=last-first, name=item["name"],
            before_sha256=sha256(before).hexdigest(), after_sha256=sha256(after).hexdigest(),
            changed_bytes=delta))
    result = bytes(result)
    if not changed:
        raise ValueError("The result is an unchanged source image")
    _image_identity(result)
    return result, {
        "status": "UNQUALIFIED_LINKED_IMAGE", "bench_pair_ready": False,
        "hardware_verified": False, "execution_qualified_by_this_tool": False,
        "base_sha256": digest, "elf_sha256": elf["sha256"],
        "bytes": len(result), "sha256": sha256(result).hexdigest(),
        "changed_bytes": changed, "changed_below_application_boundary": low_changed,
        "requires_write_below_0x8000": bool(low_changed),
        "noload_ram_bytes_not_serialized": ram_bytes, "writes": manifest_writes,
        "diagnostic_byte_sum16": f"{sum(result) & 0xffff:04x}",
        "integrity_scope": "Preserved boot markers and identity; sum16 is diagnostic, not a proven updater acceptance checksum",
    }


def from_files(base_path, elf_path, layout, patches=()):
    """Parse the final executable ELF; unresolved ET_REL files cannot enter."""
    return compose(Path(base_path).read_bytes(), read_elf(elf_path, 2), layout, patches)

