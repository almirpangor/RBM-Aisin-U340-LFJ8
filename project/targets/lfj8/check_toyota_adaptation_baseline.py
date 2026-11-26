"""Compare the controller's S01 baseline with donor ROM and the pinned R3 restore."""

import argparse
import ctypes as ct
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[2]
GP = 0x03FF4000
ORIGIN = 12288
DESCRIPTORS = 0x00ACA0
WRAPPER_BYTES = 0x00B0E0
RESTORE_ENTRIES = (0x0545E0, 0x054962, 0x055E74)
FIELDS = (
    ("learned_flags", -4619, 2), ("up_counts", -4600, 6), ("down_counts", -4594, 2),
    ("up", -4579, 18), ("down", -4554, 5), ("down_seen", -4603, 1),
)
OFFSETS = tuple(offset + i for _, offset, count in FIELDS for i in range(count))


def git_bytes(repo, commit, path):
    return subprocess.check_output(["git", "-C", str(repo), "show", f"{commit}:{path}"], timeout=60)


def digest(data):
    return sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def check_proof_input(path, data, expected):
    # Some R3 reports hash a Windows checkout instead of the Git blob.
    lf = data.replace(b"\r\n", b"\n")
    require(expected in (digest(data), digest(lf), digest(lf.replace(b"\n", b"\r\n"))),
            f"R3 proof does not cover {path}")


def word(rom, offset):
    return struct.unpack_from("<I", rom, offset)[0]


def extract(rom, proof):
    raw = rom[DESCRIPTORS:DESCRIPTORS + 96 * 8]
    require(proof["status"] == "passed" and proof["descriptor_table"]["sha256"] == digest(raw),
            "S01 restore descriptor table does not match the R3 proof")
    selected = {}
    for row, (source, kind, index, address) in enumerate(struct.iter_unpack("<BBHI", raw)):
        offset = address - GP
        width = 1 if kind < 3 else 2
        if not any(offset + i in OFFSETS for i in range(width)):
            continue
        require(source == 1 and kind in (1, 2) and offset in OFFSETS and offset not in selected and index < 45,
                f"Unexpected S01 adaptation descriptor {row}")
        pointer = word(rom, WRAPPER_BYTES + 4 * index)
        require(pointer < len(rom), f"Invalid S01 default pointer for descriptor {row}")
        selected[offset] = {"row": row, "index": index, "gp": offset,
                            "rom": f"0x{pointer:06X}", "value": rom[pointer]}
    require(set(selected) == set(OFFSETS), "Incomplete S01 adaptation projection")
    return [selected[offset] for offset in OFFSETS]


def verify_cold_projection(read_r3):
    report = json.loads(read_r3("research/results/C167_TOYOTA_COLD_INIT_PROBE.json"))
    layout_path = "research/results/TOYOTA_TCU_STATE_LAYOUT.json"
    source_path = "research/probes/c167_toyota_cold_init.c"
    layout, source = read_r3(layout_path), read_r3(source_path)
    for path, data in ((layout_path, layout), (source_path, source)):
        check_proof_input(path, data, report["input_sha256"][path])
    projection = {gp + i: mapped + i for gp, mapped, size in json.loads(layout)["ranges"] for i in range(size)}
    projected = sorted(projection[offset] for offset in OFFSETS)
    require(report["status"] == "passed_analysis_only" and report["original_root"] == "0540B0",
            "R3 cold-init proof is missing or unsuccessful")
    require(projected == list(range(443, 477)) and
            re.search(rb"\bLEARNED_RECORD\s*=\s*443\b", source) and
            re.search(rb"fill\(core->data\s*\+\s*LEARNED_RECORD,\s*34,\s*0\)", source),
            "R3 cold-init proof does not cover the whole adaptation projection")
    return report["machine_comparisons"]


class RestorePlatform(ct.Structure):
    _fields_ = [("mirror", ct.c_uint8 * 164), ("irq_disabled", ct.c_uint8)]


def mirror_fixture(rom, descriptors, mode, signature, bad, seed):
    data = bytearray([seed * 29 + 11] * 16384)
    mirror = bytearray(164)
    # Valid encoded defaults for groups 4 and 7 let the warm case reach all
    # descriptors. The two halves of each stored value complement one another.
    for group, count8, count16, gp_base, ext_base in (
        (4, 39, 14, -10944, 28), (7, 46, 8, -10864, 132)
    ):
        byte_table = word(rom, 0xA740 - 28964 + 4 * group)
        half_table = word(rom, 0xA740 - 29000 + 4 * group)
        for index in range(count8):
            value = rom[word(rom, byte_table + 4 * index)]
            struct.pack_into("<H", data, ORIGIN + gp_base + 2 * index, (value << 8) | (value ^ 0xFF))
        for index in range(count16):
            value = struct.unpack_from("<H", rom, word(rom, half_table + 4 * index))[0]
            struct.pack_into("<I", mirror, ext_base + 4 * index, (value << 16) | (value ^ 0xFFFF))
    for row in descriptors:
        struct.pack_into("<H", data, ORIGIN - 10864 + 2 * row["index"], 0x01FE)
    data[ORIGIN - 1422] = mode
    data[ORIGIN - 5274] = bad
    struct.pack_into("<H", data, ORIGIN - 10004, signature)
    return data, mirror


def compare_restore(rom, descriptors, function, baseline):
    memory_type = ct.c_uint8 * 16384
    function.argtypes = (ct.c_uint32, ct.POINTER(ct.c_uint8), ct.POINTER(RestorePlatform))
    function.restype = ct.c_int
    cold, warm = 0, 0
    for entry in RESTORE_ENTRIES:
        for seed in range(8):
            for mode in range(4):
                for signature, bad in ((0, 0), (0x5AA5, 1), (0x5AA5, 0)):
                    data, mirror = mirror_fixture(rom, descriptors, mode, signature, bad, seed)
                    gp = memory_type.from_buffer(data)
                    platform = RestorePlatform((ct.c_uint8 * 164).from_buffer_copy(mirror), seed & 1)
                    require(function(entry, gp, ct.byref(platform)) == 1, f"R3 rejected {entry:06X}")
                    actual = bytes(data[ORIGIN + offset] for offset in OFFSETS)
                    restore_warm = signature == 0x5AA5 and bad == 0 and mode < 2
                    expected = bytes([1] * len(OFFSETS)) if restore_warm else baseline
                    require(actual == expected and platform.irq_disabled == (seed & 1),
                            f"R3 restore mismatch at {entry:06X}, seed {seed}, mode {mode}, flag {bad}")
                    cold += not restore_warm
                    warm += restore_warm
    return cold, warm


def verify(args):
    index = json.loads((ROOT / "data/sources.json").read_text(encoding="utf-8"))
    s01 = next(item for item in index["firmware"] if item["id"] == "S01")
    r1 = index["repositories"][s01["repository"]]["commit"]
    r3 = index["repositories"]["R3"]["commit"]

    def read_r3(path):
        return git_bytes(args.r3, r3, path)

    rom = git_bytes(args.r1, r1, s01["path"])
    require(len(rom) == s01["bytes"] and digest(rom) == s01["sha256"], "S01 identity mismatch")
    proof = json.loads(read_r3("research/results/TOYOTA_EVENT_RESTORE_VERIFICATION.json"))
    require(proof["donor_sha256"] == digest(rom), "R3 restore proof applies to a different donor")
    descriptors = extract(rom, proof)
    baseline = bytes(row["value"] for row in descriptors)
    prior_cold_cases = verify_cold_projection(read_r3)

    controller = ct.CDLL(str(args.controller_lib.resolve()))
    get_baseline = controller.rbm_u340e_s01_adaptation_baseline
    get_baseline.argtypes, get_baseline.restype = (), ct.c_void_p
    pointer = get_baseline()
    require(pointer and ct.string_at(pointer, len(baseline)) == baseline,
            "Compiled controller baseline disagrees with S01")

    cc = shutil.which(args.cc)
    require(cc, f"Compiler not found: {args.cc}")
    driver = [cc, "cc"] if Path(cc).stem.lower() == "zig" else [cc]
    library_name = "restore.dll" if sys.platform == "win32" else "restore.so"
    shared = ["-shared", "-Wl,--export-all-symbols"] if sys.platform == "win32" else ["-shared", "-fPIC"]
    with TemporaryDirectory(prefix="rbm-s01-baseline-") as temp:
        work = Path(temp)
        files = ("event_restore.c", "event_restore.h", "event_restore_tables.h", "stage_bindings.h", "scheduler.h")
        hashes = {}
        for name in files:
            path = f"toyota_isolation/{name}"
            data = read_r3(path)
            check_proof_input(path, data, proof["input_sha256"][path])
            (work / name).write_bytes(data)
            hashes[name] = digest(data)
        subprocess.run([*driver, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", *shared,
                        "event_restore.c", "-o", library_name], cwd=work, check=True, timeout=120)
        lib = ct.CDLL(str(work / library_name))
        try:
            cold, warm = compare_restore(rom, descriptors, lib.toyota_event_restore_step, baseline)
        finally:
            if sys.platform == "win32":
                from _ctypes import FreeLibrary
                FreeLibrary(lib._handle)

    return {"status": "PASS_OFFLINE_ONLY", "s01_sha256": digest(rom), "r1_commit": r1, "r3_commit": r3,
            "compiled_controller_sha256": digest(args.controller_lib.read_bytes()),
            "baseline_hex": baseline.hex(), "descriptors": descriptors,
            "r3_cold_cases": cold, "r3_valid_mirror_cases": warm, "r3_sources": hashes,
            "inherited_v850_cold_init_cases": prior_cold_cases, "v850_replayed_this_run": False,
            "equipment_tested": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("r1", "r3", "controller-lib", "out"):
        parser.add_argument("--" + option, type=Path, required=True)
    parser.add_argument("--cc", default="zig")
    args = parser.parse_args()
    if args.out.suffix.lower() != ".json" or args.out.resolve() == args.controller_lib.resolve():
        parser.error("--out must be a separate JSON report")
    try:
        report = json.dumps(verify(args), indent=2) + "\n"
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        parser.exit(1, f"S01 adaptation baseline check failed: {error}\n")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report, encoding="utf-8")
    print(report, end="")


if __name__ == "__main__":
    main()
