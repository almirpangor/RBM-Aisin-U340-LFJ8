"""Compare compiled C0 model-field diagnostics with the two original S03 instruction windows."""

import argparse
import ctypes as ct
import json
import os
import random
import shutil
import subprocess
import sys
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType


HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
U8, U16, BOOL = ct.c_uint8, ct.c_uint16, ct.c_bool
VM_SHA = "7de99b47c8c077cc70f38239d4cdd5162b6faee0760f1b6bb93e46c58f7a6ae3"


class Monitor(ct.Structure):
    _fields_ = [(k, U8) for k in ("now", "limit", "now_count", "limit_count")] + [
        ("now_failed", BOOL), ("limit_pending", BOOL)]


class Dtc(ct.Structure):
    _fields_ = [("history", U8 * 12), ("current", U8 * 12), ("slots", U8 * 5),
                ("clear_pending", BOOL)]


class Snapshot(ct.Structure):
    _fields_ = [("rpm", U16), ("coolant", U8), ("usable", U8), ("model", U8 * 3)]


class Context(ct.Structure):
    _fields_ = [("rpm", U16), ("flags", U8), ("low_speed", BOOL), ("mode", BOOL), ("inhibit", BOOL)]


def source_blob(repo, commit, path):
    return subprocess.check_output(["git", "-C", str(repo), "show", f"{commit}:{path}"])


def native_vm(r1, ta_repo):
    manifest = json.loads((ROOT / "data/sources.json").read_text(encoding="utf-8"))
    repos = manifest["repositories"]
    s03 = next(record for record in manifest["firmware"] if record["id"] == "S03")
    rom = source_blob(r1, repos["R1"]["commit"], s03["path"])
    executor = source_blob(ta_repo, repos["R3"]["commit"], "tools/c167_subset.py")
    if sha256(rom).hexdigest() != s03["sha256"] or sha256(executor).hexdigest() != VM_SHA:
        raise ValueError("Unexpected S03 firmware or C167 instruction executor")
    module = ModuleType("pinned_c167")
    exec(compile(executor, "c167_subset.py", "exec"), module.__dict__)
    return module.C167(dict(enumerate(rom, 0x40000))), s03["sha256"]


def seed_native(vm, blank_ram, m, d):
    vm.reset()
    vm.mem = blank_ram.copy()
    for addr, value in zip((0xf9c4, 0xf9f3, 0xe016, 0xe018), (m.now, m.limit, m.now_count, m.limit_count)):
        vm.write(addr, value, 1)
    vm.write(0xe027, 0xa0 | int(m.now_failed), 1)
    vm.write(0xfd14, 0x8400 | (int(m.limit_pending) << 1))
    for i in range(12):
        vm.write(0xe028 + i, d.current[i], 1)
        vm.write(0xe0ac + i, d.history[i], 1)
    for i, index in enumerate(d.slots):
        vm.write(0xe0f8 + 14 * i, index, 1)
        vm.write(0xe105 + 14 * i, 0 if index == 255 else 0x80, 1)


def run_window(vm, entry, stop):
    # Each bounded region gets its own call frame. The actual subroutine
    # at 05C7F2 and every call it makes run from the unmodified S03 ROM.
    vm.r[0], vm.sp = 0xe600, 0xfd80
    vm.run(entry, stop=stop)
    assert vm.r[0] == 0xe600


def compare_step(lib, vm, m, d, now, limit, context, bus, rpm_latched):
    d.current[3] = bus
    d.current[2] = (d.current[2] & 0xdf) | (0x20 if rpm_latched else 0)
    snapshot = Snapshot(model=(now, 255, limit))
    lib.chery_model_monitor_task2(ct.byref(m), ct.byref(d), ct.byref(snapshot), ct.byref(context))

    for addr, value in ((0xf9d8, now), (0xf914, limit), (0xf83b, int(context.mode)),
                        (0xe026, context.flags), (0xe02b, bus)):
        vm.write(addr, value, 1)
    vm.write(0xe02a, (vm.read(0xe02a, 1) & 0xdf) | (0x20 if rpm_latched else 0), 1)
    vm.write(0xfa62, context.rpm)
    vm.write(0xfd1c, 0x0800 if context.low_speed else 0)
    vm.write(0xfd00, 0x0020 if context.inhibit else 0)
    run_window(vm, 0x06d800, 0x06d8da)
    if not bus & 0x84:  # Early RETS in the first window skips the rest of the native routine.
        run_window(vm, 0x06d9da, 0x06da6c)
    native = (
        *(vm.read(a, 1) for a in (0xf9c4, 0xf9f3, 0xe016, 0xe018)),
        vm.read(0xe027, 1), vm.read(0xfd14),
        bytes(vm.read(0xe028 + i, 1) for i in range(12)),
        bytes(vm.read(0xe0ac + i, 1) for i in range(12)),
        bytes(vm.read(0xe0f8 + 14*i, 1) if vm.read(0xe105 + 14*i, 1) else 255 for i in range(5)),
    )
    target = (m.now, m.limit, m.now_count, m.limit_count, 0xa0 | m.now_failed, 0x8400 | (m.limit_pending << 1),
              bytes(d.current), bytes(d.history), bytes(d.slots))
    if native != target:
        raise AssertionError((now, limit, bytes(context).hex(), bus, rpm_latched, native, target))


def verify(lib, vm):
    for name, args in (("chery_model_monitor_init", (Monitor,)), ("chery_dtc_init", (Dtc,)),
                       ("chery_model_monitor_task2", (Monitor, Dtc, Snapshot, Context))):
        fn = getattr(lib, name)
        fn.argtypes, fn.restype = [ct.POINTER(arg) for arg in args], None
    blank = dict.fromkeys(range(0xe000, 0x10000), 0)
    m, d = Monitor(), Dtc()
    lib.chery_model_monitor_init(ct.byref(m))
    lib.chery_dtc_init(ct.byref(d))
    vm.mem = blank.copy()
    vm.run(0x06d7e4)
    assert (m.now, m.limit) == (vm.read(0xf9c4, 1), vm.read(0xf9f3, 1))
    rng = random.Random(0x6d800)
    single, continuous = 0, 0
    for count in range(256):
        for latched in (0, 1, 4, 5):
            for missing in range(4):
                lib.chery_dtc_init(ct.byref(d))
                d.current[2] = 0x80 | latched
                m = Monitor(73, 24, count, 255 - count, bool(count & 1), bool(count & 2))
                seed_native(vm, blank, m, d)
                context = Context(rng.choice((0x0bff, 0x0c00, 0x0c01)), rng.randrange(8),
                                  rng.randrange(2), rng.randrange(2), rng.randrange(2))
                bus = rng.choice((0, 4, 0x80, 0x84)) if count % 19 == 0 else 0
                compare_step(lib, vm, m, d, 255 if missing & 1 else rng.randrange(255),
                             255 if missing & 2 else rng.randrange(255), context, bus, rng.randrange(2))
                single += 1
    for slots in ((255,)*5, (3, 7, 255, 9, 255), (3, 5, 7, 9, 11), (18, 16, 7, 255, 255)):
        for history in (0, 1, 4, 5):
            for inhibit in (False, True):
                lib.chery_dtc_init(ct.byref(d))
                d.slots[:] = slots
                d.history[2] = history
                for idx in slots:
                    if idx != 255:
                        d.history[idx // 8] |= 1 << (idx % 8)
                m = Monitor(95, 35, 101, 101, False, True)
                seed_native(vm, blank, m, d)
                compare_step(lib, vm, m, d, 255, 255, Context(inhibit=inhibit), 0, False)
                single += 1
    for missing, mask in ((1, 4), (2, 1), (3, 5)):
        lib.chery_model_monitor_init(ct.byref(m))
        lib.chery_dtc_init(ct.byref(d))
        seed_native(vm, blank, m, d)
        for i in range(1, 103):
            compare_step(lib, vm, m, d, 255 if missing & 1 else 95,
                         255 if missing & 2 else 35, Context(), 0, False)
            assert d.current[2] == (mask if i == 102 else 0)
            continuous += 1
        for i in range(1, 253):
            compare_step(lib, vm, m, d, 88, 24, Context(), 0, False)
            assert d.current[2] == (mask if i < 252 else 0)
            continuous += 1
    required = {0x6d812, 0x6d856, 0x6d87a, 0x6d8c0, 0x6da20, 0x6da42, 0x5c7f2,
                0x5c864, 0x5c8ca, 0x5c920, 0x655ea}
    if not required <= vm.coverage:
        raise AssertionError(f"Unvisited native paths: {sorted(required - vm.coverage)}")
    return {"single_step_comparisons": single, "continuous_step_comparisons": continuous,
            "fault_from_zero_calls": 102, "recovery_from_zero_calls": 252,
            "native_instructions_visited": len(vm.coverage)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cc", default="zig")
    parser.add_argument("--r1", type=Path, default=ROOT / ".sources/R1")
    parser.add_argument("--ta-repo", type=Path, default=ROOT / ".sources/R2",
                        help="local TA2005 checkout containing the R3 commit in data/sources.json")
    args = parser.parse_args()
    vm, digest = native_vm(args.r1, args.ta_repo)
    cc = shutil.which(args.cc)
    if not cc:
        parser.error(f"C compiler not found: {args.cc}")
    driver = [cc, "cc"] if Path(cc).stem.lower() == "zig" else [cc]
    with TemporaryDirectory(prefix="u340-c0-monitor-") as tmp:
        library = Path(tmp) / ("monitor.dll" if os.name == "nt" else "monitor.so")
        flags = ["-Wl,--export-all-symbols"] if os.name == "nt" else ["-fPIC"]
        subprocess.run([*driver, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-shared", *flags,
                        "-I", str(ROOT / "targets/lfj8"), str(HERE / "chery_model_monitor.c"),
                        str(HERE / "chery_dtc.c"), "-o", str(library)], check=True)
        lib = ct.CDLL(str(library))
        try:
            report = verify(lib, vm)
        finally:
            if sys.platform == "win32":
                from _ctypes import FreeLibrary
                FreeLibrary(lib._handle)
    print(json.dumps({"status": "PASS_OFFLINE_ONLY", "s03_sha256": digest, "executor_sha256": VM_SHA,
                      "equipment_tested": False, **report}, indent=2))


if __name__ == "__main__":
    main()
