"""Execute newly emitted ST10 bytes against the complete pinned S02 functions.

The independent C reference is additionally compiled from the supplied R2
source.  The original-byte oracle is never hooked and no return is fabricated.
The VM-local BMOVN/CPLB ISA additions are the existing primitive-tested R2
extensions, confined to this verifier; emitted code needs neither addition.
"""

from __future__ import annotations

import argparse
import ctypes as C
from datetime import datetime, timezone
import hashlib
import importlib
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import types

from chery_native_consumer import (
    BYTE_FIELDS, CONTEXT_BYTES, DONOR_SHA256, ENTRIES, FIELDS, LAYOUT, assemble,
)


ALIASES = {
    "raw_8172": "b8172", "raw_8173": "b8173", "checksum_8168": "b8168",
    "sequence_8166": "b8166", "flags_01": "flags_fd02", "flags_08": "flags_fd10",
    "flags_09": "flags_fd12", "flags_3a": "flags_fd74",
    "request_8c96": "published_8c96", "request_8c90": "published_8c90",
}


def canonical(name):
    return ALIASES.get(name, name)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_evidence(reference, model):
    tools = reference / "tools"
    sys.path.insert(0, str(tools))
    rx = importlib.import_module("verify_chery_rx_native")
    prefix = importlib.import_module("verify_chery_request_qualification")
    tail = importlib.import_module("verify_chery_request_tail")
    # Check the exact extension sites.  No callback or numeric algorithm is
    # injected; these implement missing actual ISA instructions in old VM.
    original = model.read_text(encoding="utf-8")
    first = "elif op==0x4A:"
    second = "value=(y&~mask)|(mask if bit else 0)"
    third = "            elif op in (0x81,0x91):"
    if any(original.count(anchor) != 1 for anchor in (first, second, third)):
        raise ValueError("Unexpected supplied C167 model extension anchors")
    source = original.replace(first, "elif op in (0x3A,0x4A):").replace(
        second, "value=(y&~mask)|(mask if (bit if op==0x4A else not bit) else 0)")
    source = source.replace(third, tail.EXTENSION + third)
    namespace = types.ModuleType("chery_consumer_actual_isa")
    exec(compile(source, str(model) + "+BMOVN+CPLB", "exec"), namespace.__dict__)
    return rx, prefix, tail, namespace.C167, hashlib.sha256(source.encode()).hexdigest()


def compile_reference(reference, compiler, outdir):
    native = reference / "engine_integration/native_chery"
    sources = [native / f"chery_{name}.c" for name in
               ("rx_native", "request_qualification", "request_tail")]
    output = outdir / "chery_native_reference.dll"
    command = [str(compiler), "-std=c11", "-O2", "-shared", "-Wall", "-Wextra",
               "-Werror", *(str(path) for path in sources), "-o", str(output)]
    env = dict(os.environ)
    env["PATH"] = str(compiler.parent) + os.pathsep + env.get("PATH", "")
    result = subprocess.run(command, env=env, check=True, capture_output=True, text=True)
    (outdir / "compiler.stdout.txt").write_text(result.stdout, encoding="utf-8")
    (outdir / "compiler.stderr.txt").write_text(result.stderr, encoding="utf-8")
    version = subprocess.run([str(compiler), "--version"], env=env, check=True,
                             capture_output=True, text=True).stdout.splitlines()[0]
    return C.CDLL(str(output)), {"command": command, "compiler_sha256": sha(compiler),
                                 "version": version, "dll_sha256": sha(output)}


def run_verification(reference, donor_path, model, compiler, outdir, exhaustive=False):
    if not __debug__:
        raise RuntimeError("Python assertions must be enabled")
    donor = donor_path.read_bytes()
    if hashlib.sha256(donor).hexdigest() != DONOR_SHA256:
        raise ValueError("Pinned S02 donor SHA256 mismatch")
    outdir.mkdir(parents=True, exist_ok=False)
    rx, prefix, tail, VM, vm_sha = load_evidence(reference, model)
    library, compiler_result = compile_reference(reference, compiler, outdir)
    c_rx = library.chery_rx_native_reference
    c_rx.argtypes = [C.POINTER(rx.State), C.POINTER(C.c_uint8)]
    c_rx.restype = C.c_int
    c_default = library.chery_rx_defaults_reference
    c_default.argtypes = [C.POINTER(rx.State), C.c_uint32]
    c_default.restype = C.c_int
    c_qualify = library.chery_request_qualification_reference
    c_qualify.argtypes = [C.POINTER(prefix.State)]
    c_qualify.restype = C.c_int
    c_tail = library.chery_request_tail_reference
    c_tail.argtypes = [C.POINTER(tail.State)]
    c_tail.restype = C.c_int
    part = assemble()
    (outdir / "CHERY_NATIVE_CONSUMER_ST10_COMPONENT.bin").write_bytes(part.code)
    ranges = ([(0xA21F4, 0xA2472), (0x230C4, 0x230D4),
               (0x232CA, 0x232DE), (0xB85A8, 0xB85A9)] +
              prefix.RANGES + tail.TAIL_RANGES + tail.CAL_RANGES)
    native_rom = {address: donor[address] for start, end in ranges for address in range(start, end)}
    native = VM(native_rom, dpp=(0x2E, 0x2F, 0x3C, 3))
    class WritesObservedVM(VM):
        def reset(self):
            super().reset()
            self.written = set()

        def write(self, address, value, size=2, extend=True):
            physical = self.physical(address, extend)
            super().write(address, value, size, extend)
            self.written.update(range(physical, physical + size))

    candidate = WritesObservedVM(dict(enumerate(part.code, part.origin)))
    rng = random.Random(0x20261126)
    counts, coverage = {}, set()
    maximum_stack = 0
    component_writes = set()
    # Fixture addresses belong only to the ISA test.  They are not deployment
    # addresses or a reservation of target RAM.  Second DPP configuration below
    # independently checks that all context access follows the caller mapping.
    context_pointer, raw_pointer = 0xA000, 0xA800
    written_inputs = [Path(__file__), Path(__file__).with_name("chery_native_consumer.py"),
                      donor_path, model]
    native_dir = reference / "engine_integration/native_chery"
    for name in ("rx_native", "request_qualification", "request_tail"):
        written_inputs.extend((native_dir / f"chery_{name}.c", native_dir / f"chery_{name}.h"))
    written_inputs.extend(Path(module.__file__) for module in (rx, prefix, tail))
    input_hashes = {str(path): sha(path) for path in written_inputs}

    def fresh():
        return {name: rng.randrange(256 if name in BYTE_FIELDS else 65536) for name in FIELDS}

    def c_step(state, entry, raw):
        s = dict(state)
        if entry in ("decode", "defaults_invalid", "defaults_zero", "cycle"):
            x = rx.State(**{name: s[canonical(name)] for name, _ in rx.FIELDS})
            if entry in ("decode", "cycle"):
                assert c_rx(C.byref(x), (C.c_uint8 * 8)(*raw)) == 1
            else:
                assert c_default(C.byref(x), 0xA23A2 if entry == "defaults_invalid" else 0xA240A) == 1
            s.update({canonical(name): getattr(x, name) for name, _ in rx.FIELDS})
        if entry in ("qualify", "cycle", "request_cycle"):
            x = prefix.State(**{name: s[canonical(name)] for name, _, _ in prefix.FIELDS})
            assert c_qualify(C.byref(x)) == 1
            s.update({canonical(name): getattr(x, name) for name, _, _ in prefix.FIELDS})
        if entry in ("tail", "cycle", "request_cycle"):
            x = tail.State(**{name: s[canonical(name)] for name, _, _ in tail.FIELDS})
            assert c_tail(C.byref(x)) == 1
            s.update({canonical(name): getattr(x, name) for name, _, _ in tail.FIELDS})
        return s

    rx_locations = [(name, int(name[6:] if name.startswith("flags_") else name[1:], 16), C.sizeof(kind))
                    for name, kind in rx.FIELDS]
    native_locations = {canonical(name): (address, size)
                        for name, address, size in rx_locations + prefix.FIELDS + tail.FIELDS}
    assert set(native_locations) == set(FIELDS), (set(FIELDS) - set(native_locations),
                                                 set(native_locations) - set(FIELDS))

    def execute_native(state, entry, raw):
        native.reset()
        native.sp = 0xFC00  # Keeps real FD74 flags separate from native CALLS.
        for name, (address, size) in native_locations.items():
            native.write(address, state[name], size)
        if entry in ("decode", "defaults_invalid", "defaults_zero", "cycle"):
            for index, value in enumerate(raw):
                native.write(0x8536 + index, value, 1)
            native.run({"decode": 0xA21F4, "defaults_invalid": 0xA23A2,
                        "defaults_zero": 0xA240A, "cycle": 0xA21F4}[entry])
        if entry in ("cycle", "request_cycle"):
            native.run(0x28CD0)
        elif entry == "qualify":
            native.run(0x28CD0, stop=0x29128)
        # Standalone tail needs the original function's real prefix-created
        # user stack.  It is compared with C, whereas composed request_cycle
        # additionally runs the full unmodified original prefix and tail.
        if entry == "tail":
            return None
        return {name: native.read(address, size) for name, (address, size) in native_locations.items()}

    def execute_candidate(state, entry, raw, mapped=False):
        nonlocal maximum_stack
        candidate.reset()
        candidate.dpp = (0x12, 0x14, 0x19 if mapped else 0x13, 3)
        candidate.sp = 0xFC00
        candidate.r = [rng.randrange(65536) for _ in range(16)]
        candidate.r[0] = 0xE600
        candidate.r[14], candidate.r[15] = raw_pointer, context_pointer
        initial_registers = list(candidate.r)
        candidate.md = [0xA55A, 0x5AA5]
        candidate.write(0xFF10, rng.randrange(65536))
        initial_psw = candidate.read(0xFF10)
        for name in FIELDS:
            candidate.write(context_pointer + LAYOUT[name], state[name])
        for index, value in enumerate(raw):
            candidate.write(raw_pointer + index, value, 1)
        candidate.written.clear()
        candidate.coverage = set()
        if entry == "request_cycle":
            candidate.run(part.labels["qualify"])
            candidate.run(part.labels["tail"])
        else:
            candidate.run(part.labels[entry])
        assert candidate.r == initial_registers, (entry, candidate.r, initial_registers)
        assert candidate.sp == 0xFC00
        assert candidate.md == [0xA55A, 0x5AA5]
        assert candidate.read(0xFF10) == initial_psw
        maximum_stack = max(maximum_stack, 0xFC00 - candidate.min_system)
        allowed = {candidate.physical(context_pointer + index) for index in range(CONTEXT_BYTES)}
        stack = set(range(0xFC00 - 44, 0xFC00))
        arithmetic_sfr = set(range(0xFE0C, 0xFE10)) | {0xFF10, 0xFF11}
        assert candidate.written <= allowed | stack | arithmetic_sfr, (
            entry, sorted(candidate.written - allowed - stack - arithmetic_sfr))
        component_writes.update(candidate.written & allowed)
        coverage.update(candidate.coverage)
        return {name: candidate.read(context_pointer + LAYOUT[name]) for name in FIELDS}

    def check(state, entry, raw, group, original=True, mapped=False):
        expected = c_step(state, entry, raw)
        actual = execute_candidate(state, entry, raw, mapped=mapped)
        assert actual == expected, {"group": group, "case": counts.get(group, 0),
                                    "entry": entry, "before": state, "raw": raw,
                                    "differences": {name: (expected[name], actual[name])
                                                    for name in FIELDS if actual[name] != expected[name]}}
        if original:
            oracle = execute_native(state, entry, raw)
            assert oracle == expected, {"group": group, "case": counts.get(group, 0),
                                        "oracle_differences": {name: (oracle[name], expected[name])
                                                               for name in FIELDS if oracle[name] != expected[name]}}
        counts[group] = counts.get(group, 0) + 1
        if counts[group] % 2048 == 0:
            print(json.dumps({"progress": group, "cases": counts[group]}), flush=True)
        return actual

    # Full raw16 speed domain includes wrap in the native uint16 scaled output.
    for value in range(0, 65536, 1 if exhaustive else 257):
        raw = [value & 255, (value * 59) & 255, (value * 73) & 255,
               (value * 109) & 255, (value * 149) & 255, (value * 197) & 255,
               value >> 8, value & 255]
        check(fresh(), "decode", raw, "all_speed_words" if exhaustive else "sampled_speed_words")
    # All 256 values in both independently decoded operand channels.
    for value in range(256):
        raw = [(value * 7) & 255, value, (value * 73) & 255, (value * 109) & 255,
               (value * 59 + 17) & 255, value, value, (value * 83) & 255]
        check(fresh(), "decode", raw, "raw_operands_and_flags")
        for code in range(16):
            s = fresh()
            s["b816d"] = value
            s["flags_fd12"] = (s["flags_fd12"] & ~256) | ((value & 1) << 8)
            raw[3] = (code << 4) | (value & 15)
            check(s, "decode", raw, "gear_retention")
    for entry in ("defaults_invalid", "defaults_zero"):
        for flags in range(0, 65536, 1 if exhaustive else 257):
            s = fresh()
            s.update(flags_fd82=flags, flags_fd10=flags, flags_fd12=flags)
            check(s, entry, [0] * 8, entry)
    pair_values = range(65536) if exhaustive else range(0, 65536, 17)
    for pair in pair_values:
        for bad in (0, 1):
            s = fresh()
            s.update(b8172=pair & 255, b8173=pair >> 8,
                     b8168=(~((pair & 255) + (pair >> 8)) & 255) ^ bad,
                     b8166=1, previous_8184=0, flags_fd10=8192,
                     flags_fd74=0, flags_8182=0, latch_8ca4=0,
                     count_8ca2=0, count_8cb8=0,
                     recovery_8cba=0, recovery_count_8cbb=0,
                     recovery_8ca0=0, recovery_count_8ca1=0,
                     good_8cb4=0, bad_8cb6=0, good_count_8cb5=0, bad_count_8cb7=0)
            check(s, "qualify", [0] * 8, "operand_pairs_bad" if bad else "operand_pairs_good")
    # Arbitrary states and saturating accumulator boundaries exercise the
    # complete unmodified OEM prefix-to-return, then independently the C model.
    for index in range(8192 if exhaustive else 2048):
        s = fresh()
        if index & 1:
            s["b8168"] = ~(s["b8172"] + s["b8173"]) & 255
        check(s, "request_cycle", [0] * 8, "complete_original_request_cycle", mapped=bool(index & 2))
    boundaries = (0, 1, 99, 100, 249, 250, 13107, 17694, 17695, 32765, 32766,
                  32767, 32768, 65023, 65024, 65534, 65535)
    for field in ("timer_8cbe", "timer_8cbc", "accumulator_high_8cca",
                  "accumulator_high_8cc6", "state_8cc2", "state_8cc0",
                  "source_98a4", "offset_98ca", "lower_9822"):
        for value in boundaries:
            for active in (0, 8192):
                s = fresh()
                s[field], s["flags_fd10"] = value, active
                check(s, "request_cycle", [0] * 8, "tail_boundaries")
    # Deliberately admissible snapshots are essential: arbitrary fault bytes
    # would hide every real command-producing path behind inhibit conditions.
    for first, second in ((40, 60), (60, 40), (50, 50), (200, 51), (51, 200)):
        for offset in (0, 10000, 32000, 65535):
            for source in (0, 6, 7, 32000, 65535):
                s = {name: 0 for name in FIELDS}
                s.update(b8172=second, b8173=first, b8168=(~(first + second) & 255),
                         b8166=1, flags_fd10=8192, flags_fd02=8192,
                         offset_98ca=offset, source_98a4=source)
                check(s, "request_cycle", [0] * 8, "admitted_numeric_commands")
    for scenario in range(16):
        s = fresh()
        for cycle in range(320):
            first, second = (cycle * 3 + scenario) & 255, (cycle * 5 + scenario) & 255
            checksum = (~(first + second) & 255) ^ int(30 <= cycle % 64 < 40)
            sequence = cycle & 7 if not 70 <= cycle % 96 < 80 else 0
            raw = [checksum & 15, first, (sequence << 4) | int(cycle < 270),
                   0x30 | (checksum >> 4), second, 25, 0x17, 0x70]
            s["flags_fd02"] = 8192 if cycle % 40 < 32 else 0
            s["flags_fd74"] = 4096 if 40 <= cycle % 64 < 48 else 0
            s = check(s, "cycle", raw, "stateful_full_decoder_and_request_cycle")
    # Exact table interpolation can be checked across its entire domain with
    # actual OEM lookup bytes and emitted helper bytes, independently of C.
    table_native, table_candidate = VM(native_rom, dpp=(0x2E, 0x2F, 0x3C, 3)), VM(candidate.rom)
    for value in range(0, 65536, 1 if exhaustive else 17):
        table_native.reset()
        table_native.sp = 0xFC00
        table_native.r[12:15] = [0x22D0, 0x2A, value]
        table_native.run(0x2475C)
        table_candidate.reset()
        table_candidate.r[4] = value
        table_candidate.run(part.labels["threshold"])
        assert table_candidate.r[4] == table_native.r[4], (value, table_candidate.r[4], table_native.r[4])
        coverage.update(table_candidate.coverage)
        counts["original_table_words"] = counts.get("original_table_words", 0) + 1
    assert input_hashes == {str(path): sha(path) for path in written_inputs}, "Evidence inputs changed"
    manifest = part.manifest()
    manifest.update({"verification": "PASSED_ACTUAL_ST10_AND_ORIGINAL_S02",
                     "checked_at_utc": datetime.now(timezone.utc).isoformat(),
                     "cases": counts, "total_cases": sum(counts.values()),
                     "maximum_observed_system_stack_bytes": maximum_stack,
                     "executed_component_instruction_addresses": len(coverage),
                     "component_instruction_count": len(part.rows),
                     "unexecuted_component_instruction_addresses": [hex(pc) for pc, _, _ in part.rows if pc not in coverage],
                     "compiler": compiler_result, "input_sha256": input_hashes,
                     "extended_c167_model_sha256": vm_sha,
                     "no_native_hooks_or_substituted_returns": True,
                     "context_dpp_relocation_tested": True,
                     "unexpected_component_writes_rejected": True})
    (outdir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("reference", "donor", "model", "compiler", "outdir"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--exhaustive", action="store_true")
    args = parser.parse_args()
    report = run_verification(*(getattr(args, name).resolve() for name in
                                ("reference", "donor", "model", "compiler", "outdir")),
                              exhaustive=args.exhaustive)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
