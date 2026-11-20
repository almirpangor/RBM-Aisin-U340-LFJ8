"""Compare current GP/gear cold preparation to the pinned, V850-checked R3 port."""

import argparse
import ctypes as ct
from hashlib import sha256
import json
from pathlib import Path
import random
import re
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

from check_toyota_adaptation_baseline import ROOT, check_proof_input, git_bytes, require


def digest(data):
    return sha256(data).hexdigest()


def projection():
    header = ROOT / "controller/vendor/toyota/include/factory_gears_state.h"
    rows = re.findall(r"uint(8|16|32)_t\s+(\w+)(?:\[(\d+)\])?;\s*/\* gp([+-]\d+) \*/",
                      header.read_text(encoding="utf-8"))
    require(len(rows) == header.read_text(encoding="utf-8").count("/* gp"), "Unparsed gear field")
    fields, mapping = [], []
    for bits, name, count, gp in rows:
        scalar = {"8": ct.c_uint8, "16": ct.c_uint16, "32": ct.c_uint32}[bits]
        fields.append((name, scalar * int(count) if count else scalar))
        mapping.append((name, int(bits) // 8, int(count or 1), int(gp), bool(count)))
    gear = type("Gear", (ct.Structure,), {"_fields_": fields})
    source = (ROOT / "controller/vendor/toyota/src/hydraulic_mapping.h").read_text(encoding="utf-8")
    ranges = [tuple(map(int, row)) for row in re.findall(r"\{(-?\d+),(\d+),(\d+)\}",
                                                         source.split("};")[0])]
    hydraulic = {gp + i: pos + i for gp, pos, size in ranges for i in range(size)}
    require(sorted(hydraulic.values()) == list(range(561)), "Changed hydraulic GP layout")
    return gear, mapping, hydraulic


def verify(args):
    registry = json.loads((ROOT / "data/sources.json").read_text(encoding="utf-8"))
    revision = registry["repositories"]["R3"]["commit"]
    read = lambda path: git_bytes(args.r3, revision, path)
    proof_path = "research/results/C167_TOYOTA_COLD_INIT_PROBE.json"
    proof_data = read(proof_path)
    proof = json.loads(proof_data)
    require(proof["status"] == "passed_analysis_only" and proof["original_root"] == "0540B0" and
            proof["machine_comparisons"] == 256, "Missing R3 V850 cold-init evidence")
    layout_path = "research/results/TOYOTA_TCU_STATE_LAYOUT.json"
    layout_data = read(layout_path)
    check_proof_input(layout_path, layout_data, proof["input_sha256"][layout_path])
    layout = json.loads(layout_data)
    reference = {gp + i: pos + i for gp, pos, size in layout["ranges"] for i in range(size)}
    require(sorted(reference.values()) == list(range(843)), "Changed reference GP projection")

    # Reject a stale controller DLL, not merely an ABI-compatible one.
    manifest = json.loads(args.controller_lib.with_name("manifest.json").read_text(encoding="utf-8"))
    require(manifest["sha256"][args.controller_lib.name] == digest(args.controller_lib.read_bytes()),
            "Controller library differs from its build manifest")
    for path, expected in manifest["source_sha256"].items():
        require(digest((ROOT / "controller" / path).read_bytes()) == expected,
                f"Controller build is stale: {path}")
    Gear, gear_fields, hydraulic = projection()
    Runtime = type("Runtime", (ct.Structure,), {"_pack_": 1, "_fields_": [
        ("gp", ct.c_uint8 * 561), ("private", ct.c_uint8 * (ct.sizeof(Gear) - 93)),
        ("initialized", ct.c_uint8)]})
    owned = set(hydraulic) | {gp + i for _, width, count, gp, _ in gear_fields
                              for i in range(width * count)}
    require(owned <= reference.keys(), "Current state extends outside the checked reference")
    target = ct.CDLL(str(args.controller_lib.resolve()))
    target.rbm_u340e_runtime_init.argtypes = [ct.POINTER(Runtime), ct.POINTER(Gear), ct.c_void_p]
    target.rbm_u340e_runtime_init.restype = ct.c_int
    prepare = target.rbm_u340e_runtime_prepare_s01_cold
    prepare.argtypes, prepare.restype = [ct.POINTER(Runtime), ct.POINTER(Gear)], ct.c_int
    snapshot = target.rbm_u340e_runtime_snapshot_gears
    snapshot.argtypes, snapshot.restype = [ct.POINTER(Runtime), ct.POINTER(Gear)], ct.c_int

    tree = subprocess.check_output(["git", "--no-replace-objects", "-C", str(args.r3), "ls-tree",
                                    "-r", "--name-only", revision], text=True).splitlines()
    compiler = shutil.which(args.cc)
    require(compiler, "Host compiler not found")
    driver = [compiler, "cc"] if Path(compiler).stem.lower() == "zig" else [compiler]
    hashes = {}
    with TemporaryDirectory(prefix="rbm-s01-cold-") as temp:
        stage = Path(temp)

        def extract(path):
            if path in hashes:
                return
            data = read(path)
            if path in proof["input_sha256"]:
                check_proof_input(path, data, proof["input_sha256"][path])
            hashes[path] = digest(data)
            (stage / Path(path).name).write_bytes(data)
            for name in re.findall(rb'^\s*#include\s+"([^"]+)"', data, re.MULTILINE):
                matches = [candidate for candidate in tree if Path(candidate).name == name.decode()]
                require(len(matches) == 1, f"Ambiguous reference header {name!r}")
                extract(matches[0])

        sources = ("c167_toyota_cold_init.c", "c167_fast_hold_cold_prepare.c")
        for name in sources:
            extract("research/probes/" + name)
        wrapper = stage / "wrapper.c"
        wrapper.write_text('''#include "c167_toyota_cold_init.h"
#include <string.h>
int run_cold(unsigned char *bytes) {
    FactoryTcuState core;
    ToyotaCompactNt nt = {0};
    ToyotaCompactCorrectionTail tail = {0};
    ToyotaColdRestoreExtra extra = {0};
    _Static_assert(sizeof core.data == 843, "R3 core layout");
    memcpy(core.data, bytes, sizeof core.data);
    int result = toyota_compact_cold_init_fallback(&core, &nt, &tail, &extra);
    memcpy(bytes, core.data, sizeof core.data);
    return result;
}
''', encoding="ascii")
        name = "reference.dll" if sys.platform == "win32" else "reference.so"
        shared = ["-shared", "-Wl,--export-all-symbols"] if sys.platform == "win32" else ["-shared", "-fPIC"]
        subprocess.run([*driver, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", *shared,
                        *sources, wrapper.name, "-o", name], cwd=stage, check=True, timeout=120)
        oracle = ct.CDLL(str(stage / name))
        try:
            oracle.run_cold.argtypes, oracle.run_cold.restype = [ct.c_void_p], ct.c_int
            rng = random.Random(0x0540B0)
            changed, cases = set(), 258
            for trial in range(cases):
                before = bytearray([0 if trial == 256 else 255] * 843) if trial >= 256 else bytearray(
                    rng.randrange(256) for _ in range(843))
                for gp in (-4835, -4830, -4828):
                    before[reference[gp]] = trial & 255
                expected = (ct.c_uint8 * 843).from_buffer_copy(before)
                require(oracle.run_cold(expected) == 1, "Reference rejected valid input")
                source = Gear()
                for member, width, count, gp, array in gear_fields:
                    for i in range(count):
                        value = int.from_bytes(bytes(before[reference[gp + i * width + j]]
                                                     for j in range(width)), "little")
                        if array:
                            getattr(source, member)[i] = value
                        else:
                            setattr(source, member, value)
                raw = (ct.c_uint8 * 561)()
                for gp, pos in hydraulic.items():
                    raw[pos] = before[reference[gp]]
                state, work, repeat = Runtime(), Gear(), Gear()
                require(target.rbm_u340e_runtime_init(ct.byref(state), ct.byref(source), raw) == 1,
                        "Shared GP input mismatch")
                require(prepare(ct.byref(state), ct.byref(work)) == 1, "Cold preparation rejected")
                require(snapshot(ct.byref(state), ct.byref(repeat)) == 1 and bytes(work) == bytes(repeat),
                        "Cold working view differs from canonical state")
                actual = {gp: state.gp[pos] for gp, pos in hydraulic.items()}
                for member, width, count, gp, array in gear_fields:
                    for i in range(count):
                        value = getattr(work, member)[i] if array else getattr(work, member)
                        for j, byte in enumerate(value.to_bytes(width, "little")):
                            field = gp + i * width + j
                            require(field not in actual or actual[field] == byte, "Shared GP diverged")
                            actual[field] = byte
                for gp, byte in actual.items():
                    require(byte == expected[reference[gp]], f"Cold mismatch trial {trial}, GP{gp:+d}")
                    if byte != before[reference[gp]]:
                        changed.add(gp)
                once = bytes(state)
                require(prepare(ct.byref(state), ct.byref(work)) == 1 and bytes(state) == once,
                        "Cold preparation is not idempotent")
        finally:
            if sys.platform == "win32":
                from _ctypes import FreeLibrary
                FreeLibrary(oracle._handle)
    if sys.platform == "win32":
        from _ctypes import FreeLibrary
        FreeLibrary(target._handle)
    return {
        "status": "PASS_COLD_PROJECTION_ONLY", "r3_commit": revision,
        "reference_proof_sha256": digest(proof_data), "reference_sources": hashes,
        "comparison_cases": cases, "compared_gp_bytes": len(owned),
        "changed_gp_bytes": len(changed), "remaining_gp_bytes_preserved": len(owned - changed),
        "inherited_v850_cases": proof["machine_comparisons"], "v850_replayed_this_run": False,
        "source_sha256": {path: digest((ROOT / path).read_bytes().replace(b"\r\n", b"\n")) for path in (
            "controller/src/rbm_u340e_runtime.c", "controller/include/rbm_u340e_runtime.h",
            "controller/tests/test_runtime.c", "targets/lfj8/check_toyota_cold_init.py")},
        "controller_library_sha256": digest(args.controller_lib.read_bytes()),
        "complete_startup_snapshots": False, "hardware_tested": False, "ready_for_flash": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ("r3", "controller-lib", "out"):
        parser.add_argument("--" + option, required=True, type=Path)
    parser.add_argument("--cc", default="zig")
    args = parser.parse_args()
    if args.out.suffix.lower() != ".json" or args.out.resolve() == args.controller_lib.resolve():
        parser.error("Use a separate JSON output")
    try:
        report = verify(args)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Cold startup check failed: {error}\n")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
