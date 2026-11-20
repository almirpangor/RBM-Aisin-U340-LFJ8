"""Compare the compiled SECONDARY load qualifier with byte-checked S01 instructions."""

import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import random
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[2]
S01_SHA256 = "a3cd723e7e21bf547ca4c17ec49a1e098d203773547dba4d7af21991a2cbead1"
V850_SHA256 = "e4f356c28220f0132b8b9e99aebe469e9b7388981231e923a9e416af74f3ee19"
LISTING_SHA256 = "1a9daf8b988c21ffc123c58bb9211ded60e2286ccff93e0e216d0573f8a04ff6"
GP_FIELDS = (-8270, -8272, -8306, -8298, -8302, -8310, -7186, -5299)
RPM_CASES = (0, 10239, 10240, 10241, 12799, 12800, 15359, 15360, 65535)
LOAD_CASES = (-32768, -1, 0, 79, 80, 143, 144, 145, 255, 431, 432, 433, 32767)
CASE_COUNT = 8192


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def checked_bytes(path, digest, text=False):
    data = path.read_bytes()
    if text:
        data = data.replace(b"\r\n", b"\n")
    if sha256(data) != digest:
        raise ValueError(f"Unexpected SHA-256 for {path}")
    return data


def native_model(s01_path, model_path, listing_path):
    rom = checked_bytes(s01_path, S01_SHA256)
    source = checked_bytes(model_path, V850_SHA256, text=True)
    listing = checked_bytes(listing_path, LISTING_SHA256, text=True)
    module = {}
    exec(compile(source, str(model_path), "exec"), module)
    machine = module["V850"](rom, listing.decode("ascii"))
    if machine.code[0x054220][:2] != ("jarl", "0x5518c,r31"):
        raise ValueError("Unexpected donor SECONDARY entry")
    return machine, module["GP"]


def native_abi(cc):
    compiler = [cc, "cc"] if Path(cc).stem.lower() == "zig" else [cc]
    with tempfile.TemporaryDirectory(prefix="u340-secondary-abi-") as directory:
        staging = Path(directory)
        source, binary = staging / "abi.c", staging / "abi.exe"
        source.write_text(
            '#include <stdio.h>\n#include "rbm_u340e_runtime.h"\n'
            'int main(void) {\n'
            '    printf("%zu %zu %zu\\n", sizeof(RbmU340eRuntime),\n'
            '           sizeof(FactoryGearState), sizeof(FactoryHydraulics));\n'
            '    return 0;\n'
            '}\n',
            encoding="ascii",
        )
        subprocess.run(
            [
                *compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                "-I", str(ROOT / "controller/include"),
                "-I", str(ROOT / "controller/vendor/toyota/include"),
                str(source), "-o", str(binary),
            ],
            check=True,
        )
        return tuple(map(int, subprocess.check_output([str(binary)], text=True).split()))


def compare(machine, gp, controller, sizes):
    byte, pointer = ctypes.c_uint8, ctypes.c_void_p
    library = ctypes.CDLL(str(controller.resolve()))
    library.rbm_u340e_runtime_init.argtypes = [pointer, pointer, pointer]
    library.rbm_u340e_runtime_init.restype = ctypes.c_int
    library.factory_hydraulics_set.argtypes = [pointer, ctypes.c_int, ctypes.c_uint, ctypes.c_uint32]
    library.factory_hydraulics_set.restype = ctypes.c_int
    library.rbm_u340e_runtime_secondary_load_qualify.argtypes = [pointer, byte, ctypes.POINTER(byte)]
    library.rbm_u340e_runtime_secondary_load_qualify.restype = ctypes.c_int
    runtime, gear, hydraulics = ((byte * length)() for length in sizes)
    if not library.rbm_u340e_runtime_init(runtime, gear, hydraulics):
        raise ValueError("Failed to initialize the host controller")
    randomizer = random.Random(0x05518C)
    coverage = set()
    for index in range(CASE_COUNT):
        machine.reset()
        old_request, inhibit = index & 255, (index >> 5) & 255
        if index < 3072:
            values = [randomizer.randrange(65536) for _ in GP_FIELDS]
        else:
            load_count = 6 if index < 5120 else 2
            values = [randomizer.choice(LOAD_CASES) & 65535 for _ in range(load_count)]
            if load_count == 2:
                values.extend((0, 0, 32767, 32767))
            values.extend((randomizer.choice(RPM_CASES), 0))
        machine.interrupts_disabled = bool(index & 1)
        for field, value in zip(GP_FIELDS, values):
            width = 1 if field == -5299 else 2
            if not library.factory_hydraulics_set(runtime, field, width, value):
                raise ValueError(f"Controller has no GP field {field}")
            machine.write(gp + field, width, value)
        machine.write(gp + 1120, 1, old_request)
        machine.write(gp - 5250, 1, inhibit)
        machine.run(0x054220, stop=0x054224, coverage=coverage)
        expected = machine.read(gp + 1120, 1)
        request = byte(old_request)
        before = bytes(runtime)
        accepted = library.rbm_u340e_runtime_secondary_load_qualify(runtime, inhibit, ctypes.byref(request))
        if not accepted or request.value != expected or bytes(runtime) != before:
            raise ValueError(
                f"Vector {index}, old request {old_request}, inhibit {inhibit}, GP fields {values}, "
                f"V850 {expected}, controller {request.value}, accepted {accepted}"
            )
    if len(coverage) != 186:
        raise ValueError(f"Expected coverage of 186 native instructions, observed {len(coverage)}")
    return len(coverage)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--s01", type=Path, required=True)
    parser.add_argument("--v850-model", type=Path, required=True)
    parser.add_argument("--listing", type=Path, required=True)
    parser.add_argument("--cc", required=True, help="Native compiler used to build the controller library")
    parser.add_argument("--controller-lib", type=Path, required=True)
    parser.add_argument("--out", type=Path, help="Optional report JSON path")
    args = parser.parse_args()
    if not __debug__:
        parser.error("Enable assertions in the byte-checking V850 model")
    inputs = (args.s01, args.v850_model, args.listing, args.controller_lib, Path(args.cc), Path(__file__))
    if args.out and args.out.resolve() in {path.resolve() for path in inputs}:
        parser.error("The report must not overwrite an input")
    model, gp = native_model(args.s01, args.v850_model, args.listing)
    report = {
        "status": "PASS_OFFLINE_ONLY",
        "source": "054220 -> 05518C",
        "s01_sha256": S01_SHA256,
        "oracle_sha256_lf": V850_SHA256,
        "instruction_listing_sha256_lf": LISTING_SHA256,
        "controller_library_sha256": sha256(args.controller_lib.read_bytes()),
        "native_comparisons": CASE_COUNT,
        "original_instructions_covered": compare(model, gp, args.controller_lib, native_abi(args.cc)),
        "target_hardware_tested": False,
    }
    rendered = json.dumps(report, indent=2) + "\n"
    if args.out:
        args.out.write_bytes(rendered.encode("ascii"))
    print(rendered, end="")


if __name__ == "__main__":
    main()
