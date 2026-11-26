"""Compare the P0710 implementation with the pinned S03 instruction path."""

import argparse
import ctypes as ct
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from types import ModuleType

from verify_model_monitor import Dtc, HERE, ROOT, VM_SHA, source_blob


CURRENT = 0xE028
HISTORY = 0xE0AC
COUNTER = 0xE061
P0710 = 0x10
EMPTY_SLOTS = (255,) * 5
TARGET = ("-m32r", "-Wa,-EB", "-mmodel=medium", "-msdata=none")
FLAGS = ("-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-UNDEBUG")
PASS_FIXTURE = "PASS P0710 debounce, service 17, history inhibit, recovery and diagnostic clear"


class Circuit(ct.Structure):
    _fields_ = [("count", ct.c_uint8)]


def native_atf(r1, ta_repo):
    manifest = json.loads((ROOT / "data/sources.json").read_text(encoding="utf-8"))
    repos = manifest["repositories"]
    s03 = next(record for record in manifest["firmware"] if record["id"] == "S03")
    rom = source_blob(r1, repos["R1"]["commit"], s03["path"])
    executor = source_blob(ta_repo, repos["R3"]["commit"], "tools/c167_subset.py")
    if sha256(rom).hexdigest() != s03["sha256"] or sha256(executor).hexdigest() != VM_SHA:
        raise ValueError("Unexpected S03 firmware or C167 instruction executor")

    # Same two opcode extensions as R3's check of the original ADC3 handler.
    anchor = "            elif op in (0xF6,0xF7):\n"
    extension = (
        "            elif op==0xB4 and hi==0:\n"
        "                self.write(word(),self.mov(self.read(self.r[lo],1),8),1)\n"
        "                pc+=2\n"
        "            elif op==0xCC and arg==0:\n"
        "                pass\n"
    )
    source = executor.decode("utf-8")
    if source.count(anchor) != 1:
        raise ValueError("Unexpected executor extension point")
    module = ModuleType("pinned_c167_adc3")
    exec(compile(source.replace(anchor, extension + anchor), "c167_subset.py[ADC3]", "exec"),
         module.__dict__)
    return module.C167(dict(enumerate(rom, 0x40000))), s03["sha256"]


def compare(lib, vm):
    lib.chery_dtc_init.argtypes = [ct.POINTER(Dtc)]
    lib.chery_dtc_init.restype = None
    lib.chery_atf_circuit_step.argtypes = [ct.POINTER(Circuit), ct.POINTER(Dtc), ct.c_int, ct.c_bool]
    lib.chery_atf_circuit_step.restype = None
    assert vm.read(0x3360, 1) & 1 == 0  # Stock ADC3 range check is enabled.
    assert (vm.read(0xAB92), vm.read(0xAB90)) == (495, 529)
    assert (vm.read(0xAB23, 1), vm.read(0xAB21, 1)) == (10, 252)
    assert (vm.read(0xAA73, 1), vm.read(0xAA8B, 1)) == (125, 125)
    blank = dict.fromkeys(range(0xE000, 0x10000), 0)
    monitor, dtc = Circuit(), Dtc()

    def seed(count=0, active=False, slots=EMPTY_SLOTS):
        lib.chery_dtc_init(ct.byref(dtc))
        monitor.count = count
        dtc.current[0] = 0x80 | (P0710 if active else 0)
        dtc.slots[:] = slots
        vm.reset()
        vm.mem = blank.copy()
        vm.write(COUNTER, count, 1)
        vm.write(CURRENT, dtc.current[0], 1)
        for i, index in enumerate(slots):
            if index != 255:
                dtc.history[index // 8] |= 1 << (index % 8)
            vm.write(0xE0F8 + 14 * i, index, 1)
            vm.write(0xE105 + 14 * i, 0 if index == 255 else 0x80, 1)
        for i, bits in enumerate(dtc.history):
            vm.write(HISTORY + i, bits, 1)

    def step(raw, reference, inhibit=False):
        if not 495 <= reference <= 529:
            sample = 0  # SKIPPED
        else:
            adc8 = (raw + (2 if raw < 1022 else 0)) >> 2
            sample = 1 if 10 <= adc8 <= 252 else 2
        before = (monitor.count, dtc.current[0], tuple(dtc.slots))
        lib.chery_atf_circuit_step(ct.byref(monitor), ct.byref(dtc), sample, inhibit)
        vm.write(0xF620, 0x4000 | raw)
        vm.write(0xF61C, 0x6000 | reference)
        vm.write(0xFD00, 0x20 if inhibit else 0)
        vm.run(0x06EE20)
        assert vm.r[0] == 0xE600 and vm.sp == 0xFD80
        native = (
            vm.read(COUNTER, 1),
            bytes(vm.read(CURRENT + i, 1) for i in range(12)),
            bytes(vm.read(HISTORY + i, 1) for i in range(12)),
            tuple(vm.read(0xE0F8 + 14 * i, 1) if vm.read(0xE105 + 14 * i, 1) else 255
                  for i in range(5)),
        )
        actual = (monitor.count, bytes(dtc.current), bytes(dtc.history), tuple(dtc.slots))
        assert actual == native, (before, raw, reference, inhibit, native, actual)

    counter_checks = 0
    for count in range(256):
        for active in (False, True):
            for raw, reference in ((0, 512), (1023, 512), (200, 512), (0, 494), (1023, 530)):
                seed(count, active)
                step(raw, reference, inhibit=bool(count & 1))
                counter_checks += 1

    adc_checks = 0
    for reference in (494, 495, 529, 530):
        for raw in range(1024):
            seed(126)
            step(raw, reference, inhibit=True)
            adc_checks += 1

    history_checks = 0
    for slots in (EMPTY_SLOTS, (3, 255, 7, 9, 255), (3, 5, 7, 9, 11), (3, 4, 7, 255, 255)):
        for inhibit in (False, True):
            seed(126, slots=slots)
            step(0, 512, inhibit)
            history_checks += 1

    seed()
    for call in range(127):
        step(0, 512)
        assert bool(dtc.current[0] & P0710) == (call == 126)
    step(0, 494)
    step(200, 512)
    step(1023, 512)
    for call in range(126):
        step(200, 512)
        assert bool(dtc.current[0] & P0710) == (call < 125)
    assert dtc.history[0] == P0710 and dtc.slots[0] == 4
    required = {0x06EE20, 0x06EEAC, 0x05C7F2}
    assert required <= vm.coverage, [hex(address) for address in sorted(required - vm.coverage)]

    return {"counter_comparisons": counter_checks, "adc_comparisons": adc_checks,
            "history_comparisons": history_checks, "sequence_comparisons": 256,
            "fault_from_zero_calls": 127, "recovery_calls": 126}


def verify(args):
    vm, digest = native_atf(args.r1, args.ta_repo)
    compiler = Path(shutil.which(args.cc) or args.cc).resolve()
    driver = (compiler, "cc") if compiler.stem.casefold() == "zig" else (compiler,)

    with TemporaryDirectory(prefix="rbm-p0710-") as temp:
        stage = Path(temp)
        for name in ("chery_atf_circuit.c", "chery_atf_circuit.h", "chery_dtc.c", "chery_dtc.h",
                     "test_chery_atf_circuit.c"):
            shutil.copyfile(HERE / name, stage / name)

        def run(*cmd):
            return subprocess.run([str(arg) for arg in cmd], cwd=stage, check=True,
                                  capture_output=True, text=True, timeout=60).stdout.strip()

        sources = ("chery_atf_circuit.c", "chery_dtc.c")
        fixture = (*sources, "test_chery_atf_circuit.c")
        windows = sys.platform == "win32"
        exe = stage / ("fixture.exe" if windows else "fixture")
        dll = stage / ("monitor.dll" if windows else "monitor.so")
        run(*driver, *FLAGS, *fixture, "-o", exe)
        if run(exe) != PASS_FIXTURE:
            raise ValueError("PC fixture did not report PASS")
        run(*driver, *FLAGS, "-shared", "-Wl,--export-all-symbols" if windows else "-fPIC",
            *sources, "-o", dll)
        library = ct.CDLL(str(dll))
        try:
            results = compare(library, vm)
        finally:
            if windows:
                from _ctypes import FreeLibrary
                FreeLibrary(library._handle)

        if args.m32r_gcc:
            gcc = args.m32r_gcc.resolve()
            if run(gcc, "-dumpmachine") != "m32r-elf":
                raise ValueError("Expected an m32r-elf compiler")
            crt = run(gcc, *TARGET, "-print-file-name=crt0.o")
            (stage / "crt_hooks.c").write_text("void __init(void) {}\nvoid __fini(void) {}\n", encoding="ascii")
            run(gcc, *TARGET, *FLAGS, "-Wno-missing-braces", "-Wno-missing-field-initializers",
                "-nostartfiles", crt, *fixture, "crt_hooks.c",
                "-Wl,-e,_start,--start-group", "-lc", "-lgloss", "-lgcc", "-Wl,--end-group",
                "-o", "fixture.elf")
            simulator = gcc.with_name("m32r-elf-run" + gcc.suffix)
            if run(simulator, "fixture.elf") != PASS_FIXTURE:
                raise ValueError("M32R fixture did not report PASS")

    return {"status": "PASS_OFFLINE_ONLY", "s03_sha256": digest, "executor_sha256": VM_SHA,
            "pc_fixture": "PASS", "m32r_fixture": "PASS" if args.m32r_gcc else "not run",
            "equipment_tested": False, **results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cc", default="zig")
    parser.add_argument("--m32r-gcc", type=Path)
    parser.add_argument("--r1", type=Path, default=ROOT / ".sources/R1")
    parser.add_argument("--ta-repo", type=Path, default=ROOT / ".sources/R2")
    args = parser.parse_args()
    if not __debug__:
        parser.error("Run without Python -O")
    try:
        print(json.dumps(verify(args), indent=2))
    except subprocess.CalledProcessError as error:
        parser.exit(1, (error.stderr or error.stdout or str(error)) + "\n")


if __name__ == "__main__":
    main()
