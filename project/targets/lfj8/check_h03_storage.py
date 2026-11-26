"""Measure current H03 storage using M32R ABI and check a candidate address model."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
from tempfile import TemporaryDirectory

from check_h03_link import HERE, ROOT, TARGET, elf_info, identify_h03
from check_h03_ram_candidate import fixed_reference_candidates, simulator_checks, WINDOW, WORKSPACE_WINDOW

GROUPS = ("control", "communication", "workspace")
SECONDARY_START = 0x808E40
SECONDARY_LIMIT = 0x809600  # Hypothesis only, below the existing conditional stack budget.
STACK_LOWER_HYPOTHESIS = 0x809700


def decode_layout(raw):
    if len(raw) < 16:
        raise ValueError("Truncated layout header")
    magic, version, pointer, count = struct.unpack_from(">4I", raw)
    if (magic, version, pointer) != (0x52424D31, 1, 4) or len(raw) != 16 + count * 44:
        raise ValueError("Wrong ABI, version or record length")
    records = {}
    for index in range(count):
        name, offset, size, alignment = struct.unpack_from(">32s3I", raw, 16 + 44 * index)
        if b"\0" not in name:
            raise ValueError("Unterminated name")
        name = name.split(b"\0", 1)[0].decode("ascii")
        if not re.fullmatch(r"[a-z][a-z0-9_]*(/[a-z][a-z0-9_]*)?", name) or name in records:
            raise ValueError("Invalid or duplicate name")
        if not size or not alignment or alignment & (alignment - 1) or offset % alignment:
            raise ValueError("Invalid size/alignment")
        records[name] = {"offset": offset, "bytes": size, "alignment": alignment}
    if set(name.split("/")[0] for name in records) != set(GROUPS):
        raise ValueError("Unexpected storage group")
    for group in GROUPS:
        parent = records.get(group)
        if parent is None or parent["offset"] or parent["bytes"] % parent["alignment"]:
            raise ValueError("Missing or misaligned aggregate")
        children = [value for name, value in records.items() if name.startswith(group + "/")]
        if not children:
            raise ValueError("Aggregate has no fields")
        end = 0
        for child in sorted(children, key=lambda value: value["offset"]):
            if child["offset"] < end or child["alignment"] > parent["alignment"]:
                raise ValueError("Overlapping or misaligned fields")
            end = child["offset"] + child["bytes"]
            if end > parent["bytes"]:
                raise ValueError("Field exceeds aggregate")
    return records


def aligned(address, alignment):
    return (address + alignment - 1) & ~(alignment - 1)


def address_plan(records):
    starts = {"control": aligned(WINDOW[0], records["control"]["alignment"]),
              "communication": aligned(SECONDARY_START, records["communication"]["alignment"])}
    starts["workspace"] = aligned(starts["communication"] + records["communication"]["bytes"],
                                  records["workspace"]["alignment"])
    blocks = {group: {**records[group], "address": starts[group],
                       "end_exclusive": starts[group] + records[group]["bytes"]} for group in GROUPS}
    if blocks["control"]["end_exclusive"] > WINDOW[1]:
        raise ValueError("Control storage exceeds the primary RAM candidate")
    if blocks["workspace"]["end_exclusive"] > SECONDARY_LIMIT:
        raise ValueError("Communication/workspace exceed the secondary RAM hypothesis")
    return blocks


def check(base, compiler):
    identity = identify_h03(base)
    rom = base.read_bytes()
    if sha256(rom).hexdigest() != identity["sha256"]:
        raise ValueError("H03 changed during storage audit")
    sources = [HERE / "h03_storage_layout.c", *HERE.glob("*.h"),
               *(ROOT / "diagnostics").glob("*.h"),
               *(ROOT / "controller/include").glob("*.h"),
               *(ROOT / "controller/vendor/toyota/include").glob("*.h")]
    with TemporaryDirectory(prefix="rbm-h03-storage-") as directory:
        stage = Path(directory)
        for source in sources:
            destination = stage / source.name
            if destination.exists() and destination.read_bytes() != source.read_bytes():
                raise ValueError("Ambiguous staged header: " + source.name)
            shutil.copyfile(source, destination)

        def run(*args):
            return subprocess.run([str(arg) for arg in args], cwd=stage, capture_output=True,
                                  text=True, check=True, timeout=60).stdout.strip()

        if run(compiler, "-dumpmachine") != "m32r-elf":
            raise ValueError("Use the M32R target compiler")
        run(compiler, *TARGET, "-std=c11", "-Os", "-Wall", "-Wextra", "-Werror",
            "-ffreestanding", "-fno-common", "-I.", "-c", "h03_storage_layout.c", "-o", "layout.o")
        object_info = elf_info(stage / "layout.o", 1)[0]
        objcopy = run(compiler, "-print-prog-name=objcopy")
        run(objcopy, "-j", ".rbm_layout", "-O", "binary", "layout.o", "layout.dat")
        records = decode_layout((stage / "layout.dat").read_bytes())
        blocks = address_plan(records)
        script = ["SECTIONS {", " .layout 0x100000 : { *(.rbm_layout) }"]
        for name, block in blocks.items():
            script.append(f" .{name} {block['address']:#x} (NOLOAD) : {{ *(.bss.rbm_{name}) }}")
        script.extend([" /DISCARD/ : { *(.comment) *(.note*) }", "}"])
        script.extend([f'ASSERT(SIZEOF(.{name}) == {block["bytes"]}, "Storage size mismatch")'
                       for name, block in blocks.items()])
        script.extend([f'ASSERT(ADDR(.control) + SIZEOF(.control) <= {WINDOW[1]:#x}, "Primary overflow")',
                       f'ASSERT(ADDR(.workspace) + SIZEOF(.workspace) <= {SECONDARY_LIMIT:#x}, "Secondary overflow")'])
        (stage / "storage.ld").write_text("\n".join(script) + "\n", encoding="ascii")
        run(compiler, *TARGET, "-nostdlib", "-Wl,-T,storage.ld", "layout.o", "-o", "storage.elf")
        linked = elf_info(stage / "storage.elf", 2)[0]
        nm = run(compiler, "-print-prog-name=nm")
        rows = [line.split() for line in run(nm, "-S", "--defined-only", "storage.elf").splitlines()]
        for name, block in blocks.items():
            matches = [row for row in rows if len(row) == 4 and row[3] == "rbm_h03_" + name]
            if len(matches) != 1 or (int(matches[0][0], 16), int(matches[0][1], 16), matches[0][2]) != (
                    block["address"], block["bytes"], "B"):
                raise ValueError("Linked storage disagrees with ABI table: " + name)
        compiler_name = run(compiler, "--version").splitlines()[0]

    secondary_end = blocks["workspace"]["end_exclusive"]
    windows = {"control": WINDOW, "communication_and_workspace": (SECONDARY_START, secondary_end)}
    references = {name: fixed_reference_candidates(rom, window) for name, window in windows.items()}
    initializers = simulator_checks(rom, compiler, workspace_window=windows["communication_and_workspace"])
    if not all(row["candidate_unchanged"] and row["workspace_candidate_unchanged"] for row in initializers):
        raise ValueError("A selected OEM initializer overwrites proposed storage")
    measured = sum(block["bytes"] for block in blocks.values())
    nominal_capacity = WINDOW[1] - WINDOW[0] + WORKSPACE_WINDOW[1] - WORKSPACE_WINDOW[0]
    return {
        "base": identity, "compiler": compiler_name,
        "artifact_kind": "M32R_ABI_storage_address_model",
        "blocks": blocks, "fields": records,
        "storage_bytes": measured, "previous_two_window_capacity_bytes": nominal_capacity,
        "previous_capacity_deficit_bytes": max(0, measured - nominal_capacity),
        "primary_unused_bytes": WINDOW[1] - blocks["control"]["end_exclusive"],
        "expanded_secondary_candidate": [SECONDARY_START, secondary_end],
        "extra_secondary_bytes_over_old_workspace": max(0, secondary_end - WORKSPACE_WINDOW[1]),
        "gap_to_conditional_stack_lower_bound": STACK_LOWER_HYPOTHESIS - secondary_end,
        "fixed_reference_candidates": references,
        "simulated_initializers": initializers,
        "compiled_object": object_info, "linked_storage_model": linked,
        "input_sha256": {source.relative_to(ROOT).as_posix():
                         sha256(source.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
                         for source in sorted(sources)},
        "not_included": ["native globals outside this inventory, including the DTC IRQ binding pointer",
                         "DTC/adaptation NVM transaction buffers on the stack and physical driver state",
                         "remaining Toyota stages", "platform callback/context storage",
                         "stack frames and nested interrupts", "read-only calibration and callback tables"],
        "exclusive_ram_ownership_verified": False, "stack_bound_verified": False,
        "startup_initialization_implemented": False, "hardware_executed": False,
        "flashable_image": None,
        "limits": ["Selected OEM initializers and fixed reference classes only",
                   "Indirect monitor writes, DMA and remapping still require service isolation",
                   "Typed inventory is not a permission to overwrite original H03 RAM",
                   "No new runtime overlap or packing assumptions were introduced"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("base", "gcc", "out"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    if args.out.suffix.lower() != ".json" or args.out.resolve() == args.base.resolve():
        parser.error("--out must be a separate JSON report")
    try:
        result = check(args.base.resolve(), args.gcc.resolve())
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({key: result[key] for key in (
            "storage_bytes", "previous_capacity_deficit_bytes", "blocks",
            "gap_to_conditional_stack_lower_bound", "flashable_image")}, indent=2))
    except subprocess.CalledProcessError as error:
        parser.exit(1, str(error.stderr or error.stdout or error) + "\n")
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    main()
