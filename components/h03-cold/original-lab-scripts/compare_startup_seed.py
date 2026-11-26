"""Compare the compiled read-only seed and cold projection with S01 replay."""
import ctypes as C
from hashlib import sha256
import json
from pathlib import Path
import sys

LAB = Path(__file__).resolve().parent
sys.path.insert(0, str(LAB / "repo/targets/lfj8"))
from check_toyota_cold_init import projection
Gear, fields, hydraulic_offsets = projection()

class Gp(C.Structure):
    _fields_ = [("data", C.c_uint8 * 561)]

class Runtime(C.Structure):
    _pack_ = 1
    _fields_ = [("gp", Gp), ("private", C.c_uint8 * (C.sizeof(Gear) - 93)),
                ("initialized", C.c_uint8)]

seed_image = (LAB / "m32r-startup-pass/cold-seed-section.dat").read_bytes()
if seed_image != bytes(564):
    raise ValueError("Expected 561 zero seed bytes with alignment from the M32R object")
seed_data = (C.c_uint8 * len(seed_image)).from_buffer_copy(seed_image)
gear = Gear.from_buffer(seed_data)
gp = Gp.from_buffer(seed_data)
manifest = json.loads((LAB / "controller-host/manifest.json").read_text())
dll = LAB / "controller-host/rbm_u340e.dll"
assert sha256(dll.read_bytes()).hexdigest() == manifest["sha256"][dll.name]
lib = C.CDLL(str(dll))
lib.rbm_u340e_runtime_init.argtypes = (C.POINTER(Runtime), C.POINTER(Gear), C.POINTER(Gp))
lib.rbm_u340e_runtime_prepare_s01_cold.argtypes = (C.POINTER(Runtime), C.POINTER(Gear))
runtime = Runtime()
work = Gear()
C.memset(C.byref(runtime), 0xA7, C.sizeof(runtime))
C.memset(C.byref(work), 0x34, C.sizeof(work))
assert lib.rbm_u340e_runtime_init(C.byref(runtime), C.byref(gear), C.byref(gp)) == 1
assert lib.rbm_u340e_runtime_prepare_s01_cold(C.byref(runtime), C.byref(work)) == 1
observed = {address: runtime.gp.data[index] for address, index in hydraulic_offsets.items()}
for name, width, count, address, array in fields:
    value = getattr(work, name)
    for index in range(count):
        selected = value[index] if array else value
        for offset, byte in enumerate(selected.to_bytes(width, "little")):
            position = address + index * width + offset
            if position in observed:
                assert observed[position] == byte
            observed[position] = byte
expected = json.loads((LAB / "evidence/reset-cold-ram.json").read_text())
mismatches = {offset: [expected[str(offset)], observed[offset]]
              for offset in sorted(observed) if expected[str(offset)] != observed[offset]}
assert len(observed) == 828 and not mismatches, mismatches
assert tuple(expected[str(offset)] for offset in (1112,1113,1114,1115,1376,1120)) == (0,)*6
print("PASS 828 GP/gear bytes from the compiled S01 seed match V850 cold reset")
