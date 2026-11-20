"""Run the pinned portable Toyota SLU reference with model-only MMIO."""

import argparse
from bisect import bisect_right
import ctypes as C
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[2]
ANALOG_PROOF = "research/results/TOYOTA_OUTPUT_ANALOG_VERIFICATION.json"
CHAIN_PROOF = "research/results/C167_SECONDARY_SLU_CHAIN_PROBE.json"
ENTRY = 0x055C5E
GP = 12288
CTRL, PERIOD, CMP, ENABLE = 0xFFFFF602, 0xFFFFF614, 0xFFFFF616, 0xFFFFF41E


def git_bytes(path, name):
    env = {**os.environ, "GIT_NO_LAZY_FETCH": "1"}
    return subprocess.check_output(["git", "-C", str(path), "show", name], env=env)


def compare(library, rom):
    run = library.toyota_output_analog_reference
    enter = C.CFUNCTYPE(C.c_uint32, C.c_void_p)
    leave = C.CFUNCTYPE(None, C.c_void_p, C.c_uint32)
    read = C.CFUNCTYPE(C.c_uint16, C.c_void_p, C.c_uint32, C.c_uint)
    write = C.CFUNCTYPE(None, C.c_void_p, C.c_uint32, C.c_uint, C.c_uint16)

    class Critical(C.Structure):
        _fields_ = [("enter", enter), ("leave", leave), ("user", C.c_void_p)]

    class Services(C.Structure):
        _fields_ = [("critical", Critical), ("read", read), ("write", write), ("user", C.c_void_p)]

    run.argtypes = [C.POINTER(Services), C.POINTER(C.c_uint8), C.c_uint32]
    run.restype = C.c_int
    memory = (C.c_uint8 * 16384)()
    events = []
    ports = {}
    depth = 0

    @enter
    def enter_critical(_):
        nonlocal depth
        previous = depth
        depth += 1
        return previous

    @leave
    def leave_critical(_, token):
        nonlocal depth
        depth = token if depth == token + 1 else -100

    @read
    def read_port(_, address, width):
        value = ports.get(address, 0)
        events.append(("read", address, width, depth, value))
        return value

    @write
    def write_port(_, address, width, value):
        events.append(("write", address, width, depth, value))
        ports[address] = value

    services = Services(Critical(enter_critical, leave_critical, None), read_port, write_port, None)

    def put_word(offset, value):
        memory[GP + offset] = value & 0xFF
        memory[GP + offset + 1] = (value >> 8) & 0xFF

    def get_word(offset):
        return memory[GP + offset] | memory[GP + offset + 1] << 8

    count = rom[0xFD4]
    xs = [x * 256 for x in rom[0xFD5:0xFD5 + count]]
    ys = [y * 256 for y in rom[0xFD5 + count:0xFD5 + 2 * count]]
    assert count == 10 and xs == sorted(xs)

    def curve(raw):
        index = bisect_right(xs, raw) - 1
        if index < 0:
            return ys[0]
        if index == count - 1:
            return ys[-1]
        span = xs[index + 1] - xs[index]
        return (ys[index] * (xs[index + 1] - raw) + ys[index + 1] * (raw - xs[index])) // span

    def check_transaction(*allowed):
        assert depth == 0 and all(level == 1 for _, _, _, level, _ in events)
        widths = {CTRL: 1, PERIOD: 2, CMP: 2, ENABLE: 1}
        assert all(address in allowed and width == widths[address]
                   for _, address, width, _, _ in events)
        return [address for direction, address, _, _, _ in events if direction == "write"]

    memory[GP - 4544] = 165
    memory[GP - 4828] = 128
    memory[GP - 5286] = 1
    for raw in range(65536):
        put_word(-7136, 25600 - raw)
        initial_control = 0x85 if raw & 1 else 0x05
        ports[CTRL] = initial_control
        events.clear()
        assert run(C.byref(services), memory, ENTRY) == 1
        selected = curve(raw)
        assert get_word(-7246) == raw and get_word(-7130) == selected
        assert get_word(-9062) == get_word(-1560) == selected
        assert get_word(-1562) == ports[CMP] == 400 + (9 * selected) // 64
        assert ports[PERIOD] == 4000 and ports[CTRL] == 0x85
        expected_writes = [CTRL, CMP, PERIOD, CTRL] if raw & 1 else [CMP, PERIOD, CTRL]
        assert check_transaction(CTRL, PERIOD, CMP) == expected_writes

    # Force the command and restore each of the two driver modes.
    memory[GP - 4822] = 128
    memory[GP - 5284] = 1
    ports[ENABLE] = 0xB4
    events.clear()
    assert run(C.byref(services), memory, ENTRY) == 1
    assert memory[GP - 5286] == 3 and memory[GP + 1156] & 2
    assert get_word(-9066) == curve(65535) and ports[ENABLE] == 0x34
    assert check_transaction(CTRL, PERIOD, CMP, ENABLE) == [CTRL, CMP, PERIOD, CTRL, ENABLE]

    memory[GP - 4822] = 0
    events.clear()
    assert run(C.byref(services), memory, ENTRY) == 1
    assert memory[GP - 5286] == 2 and not memory[GP + 1156] & 2
    assert get_word(-9066) == 0 and ports[ENABLE] == 0xB4
    assert check_transaction(ENABLE) == [ENABLE]

    memory[GP + 1156] |= 2
    memory[GP - 5286] = 3
    memory[GP - 5284] = 0
    # The stored signed command goes through truncation toward zero after
    # the arithmetic shift. Use -8 so its effect is visible at the compare.
    put_word(-9062, -8)
    events.clear()
    assert run(C.byref(services), memory, ENTRY) == 1
    assert memory[GP - 5286] == 1 and not memory[GP + 1156] & 2
    assert check_transaction(CTRL, PERIOD, CMP) == [CTRL, CMP, PERIOD, CTRL] * 2
    assert [value for direction, address, _, _, value in events if direction == "write" and address == CMP] == [399, 4000]
    assert run(None, memory, ENTRY) == 0
    return {"normal_u16_commands": 65536, "force_resume_cases": 3, "donor_period_register": 4000}


def verify(r1, r3, compiler):
    source_index = json.loads((ROOT / "data/sources.json").read_text(encoding="utf-8"))
    s01 = next(source for source in source_index["firmware"] if source["id"] == "S01")
    r1_commit = source_index["repositories"]["R1"]["commit"]
    r3_commit = source_index["repositories"]["R3"]["commit"]
    rom = git_bytes(r1, f"{r1_commit}:{s01['path']}")
    assert len(rom) == s01["bytes"] and sha256(rom).hexdigest() == s01["sha256"]
    analog_bytes = git_bytes(r3, f"{r3_commit}:{ANALOG_PROOF}")
    chain_bytes = git_bytes(r3, f"{r3_commit}:{CHAIN_PROOF}")
    analog, chain = json.loads(analog_bytes), json.loads(chain_bytes)
    assert analog["donor_sha256"] == s01["sha256"] and analog["status"] == "passed"
    assert chain["comparisons"] == 3072 and chain["physical_slu_output_bound"] is False

    analog_source = "toyota_isolation/output_analog.c"
    core_source = "u340e_logic/factory/src/factory_core.c"
    with TemporaryDirectory(prefix="rbm-toyota-slu-") as directory:
        staged = Path(directory)
        for filename, expected in analog["input_sha256"].items():
            source = git_bytes(r3, f"{r3_commit}:{filename}")
            if sha256(source).hexdigest() != expected:
                # Three factory files were hashed upstream with the checkout's CRLF.
                source = source.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
            assert sha256(source).hexdigest() == expected, filename
            target = staged / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source)
        shared = staged / ("slu.dll" if os.name == "nt" else "slu.so")
        driver = [str(compiler)] + (["cc"] if compiler.stem.lower() == "zig" else [])
        subprocess.run([*driver, "-shared", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                        "-I", str(staged / "u340e_logic/factory/include"), str(staged / analog_source),
                        str(staged / core_source), "-o", str(shared)], check=True)
        library = C.CDLL(str(shared))
        try:
            coverage = compare(library, rom)
        finally:
            if os.name == "nt":
                from _ctypes import FreeLibrary

                FreeLibrary(library._handle)
    return {
        "status": "PASS_DONOR_SLU_HOST_REFERENCE_ONLY",
        "s01_sha256": s01["sha256"],
        "r3_commit": r3_commit,
        "entry": f"{ENTRY:06X}",
        "local_host_checks": coverage,
        "upstream_055c5e_oracle_cases": next(x["cases"] for x in analog["operations"] if x["entry"] == "055C5E"),
        "upstream_secondary_slu_chain_cases": chain["comparisons"],
        "upstream_secondary_slu_chain_call_boundaries": chain["compared_call_boundaries"],
        "upstream_proof_sha256": {ANALOG_PROOF: sha256(analog_bytes).hexdigest(),
                                  CHAIN_PROOF: sha256(chain_bytes).hexdigest()},
        "h03_scheduler_or_snapshot_bound": False,
        "h03_physical_channel_current_or_failure_bound": False,
        "ready_for_flash": False,
    }


def main():
    if not __debug__:
        raise RuntimeError("Assertions must be enabled for the donor SLU test")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--r1", type=Path, default=ROOT / ".sources/R1")
    parser.add_argument("--r3", type=Path, default=ROOT / ".sources/R2")
    parser.add_argument("--cc", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.r1, args.r3, args.cc), indent=2))


if __name__ == "__main__":
    main()
