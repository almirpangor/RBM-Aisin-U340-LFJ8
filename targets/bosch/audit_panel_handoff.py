#!/usr/bin/env python3
"""Run a model-only ST10 GPIO handoff next to the untouched E4M3 owners."""

import argparse
from itertools import product
import json
from pathlib import Path

from build import AGE, S04_SHA, SPEED, build, digest
from verify import build_native_model

FIXTURE = 0x10000  # Only mapped by this test; absent from the candidate ROM map.
PHASE_PARAMETERS = FIXTURE + 0x100
PHASE_STEP = FIXTURE + 0x200
HALF_PHASE_NUMERATOR = 46875  # T8 at 40 MHz / 1024, 6000 imp/km, 50% duty, Q7 >> 5.
NATIVE = 0x0C547E
CONTINUE = 0x0C549E
ACTUATOR = 0x0C19AE
ACTUATOR_RETURN = 0x0C19DE
FORCED_HIGH = 0x0C54F2
PORT3 = 0xFFC4
PORT_BIT = 0x0040
ACTUATOR_MASK = 0x8FD8
OVERRIDE_MODE = 0x80F2
RELAY_STATE = 0xFD2C
RELAY_BIT = 0x0400
SPEED_LOGICAL = 0x98FC
COMMAND_LOW, COMMAND_HIGH = 1, 2  # Matches BoschPanelGpioCommand.


def assemble(diag, set_bit, clear_bit):
    asm = diag.BasicAsm(FIXTURE, FIXTURE + 0x100)
    asm.raw("ec88ecf4", "PUSH PSW; PUSH R4")
    asm.raw("48d1", "CMP R13,#1 ; armed")
    asm.branch(3, "native")
    asm.ld(4, ACTUATOR_MASK)
    asm.andi(4, 0x0100)
    asm.branch(3, "native")
    asm.raw("f3f8f2804981", "MOVB RL4,80F2h; CMPB RL4,#1")
    asm.branch(14, "native")  # Unsigned greater than 1.
    asm.ld(4, RELAY_STATE)
    asm.andi(4, RELAY_BIT)
    asm.branch(3, "native")
    asm.ld(4, AGE)
    asm.cmp(4, 0)
    asm.branch(2, "native")
    asm.ld(4, SPEED_LOGICAL)
    asm.cmp(4, 0)
    asm.branch(2, "native")
    asm.raw("48c2", "CMP R12,#2 ; drive high")
    asm.branch(2, "high")
    asm.raw("48c1", "CMP R12,#1 ; drive low")
    asm.branch(3, "native")
    asm.emit(clear_bit, "BCLR P3.6 (original diagnostic encoding)")
    asm.branch(0, "resume")
    asm.label("high")
    asm.emit(set_bit, "BSET P3.6 (original diagnostic encoding)")
    asm.label("resume")
    asm.raw("fcf4fc88", "POP R4; POP PSW")
    asm.emit(diag.far(0xFA, CONTINUE), "JMPS native continuation")
    asm.label("native")
    asm.raw("fcf4fc88", "POP R4; POP PSW")
    asm.emit(diag.far(0xFA, NATIVE), "JMPS untouched native P3.6 owner")
    return asm.finish()


def load_fixture(vm, address, code):
    for cpu_address, value in enumerate(code, address):
        assert cpu_address not in vm.rom
        vm.rom[cpu_address] = value


def verify_fractional_phase(vm, diag):
    setup = diag.BasicAsm(PHASE_PARAMETERS, PHASE_STEP)
    setup.rr(6, 4)  # R4 = native speed Q7; R6 = units of 0.25 km/h.
    setup.shift(6, 5)
    setup.imm(5, 0)
    setup.imm(7, 0)
    setup.cmp(6, 0)
    setup.branch(2, "return")
    setup.emit(bytes.fromhex("e607") + diag.word(HALF_PHASE_NUMERATOR), "MOV MDL,#46875")
    setup.raw("5b66", "DIVU R6")
    setup.ld(5, 0xFE0E)  # Quotient.
    setup.ld(7, 0xFE0C)  # Remainder.
    setup.label("return")
    setup.raw("db00", "RETS")
    load_fixture(vm, PHASE_PARAMETERS, setup.finish())

    step = diag.BasicAsm(PHASE_STEP, PHASE_STEP + 0x100)
    step.rr(4, 5)
    step.add(8, 7)
    step.cmpreg(8, 6)
    step.branch(8, "deadline")  # No extra tick if remainder sum is below the divisor.
    step.sub(8, 6)
    step.addi(4, 1)
    step.label("deadline")
    step.add(9, 4)  # Relative to the previous planned match, modulo the comparison counter.
    step.raw("db00", "RETS")
    load_fixture(vm, PHASE_STEP, step.finish())

    vm.reset()
    vm.run(PHASE_PARAMETERS)
    assert vm.r[5:8] == [0, 0, 0]
    boundary_cases = 0
    for quarter_kph in range(1, 2048):
        vm.r[4] = quarter_kph << 5
        vm.run(PHASE_PARAMETERS)
        whole, remainder = divmod(HALF_PHASE_NUMERATOR, quarter_kph)
        assert vm.r[5:8] == [whole, quarter_kph, remainder]
        for carry in {0, quarter_kph - 1, quarter_kph - remainder - 1}:
            vm.r[8:10] = [carry, 0xFFF0]
            vm.run(PHASE_STEP)
            extra, expected_carry = divmod(carry + remainder, quarter_kph)
            assert vm.r[8:10] == [expected_carry, (0xFFF0 + whole + extra) & 0xFFFF]
            boundary_cases += 1

    stable_examples = []
    for quarter_kph in (1, 240, 480, 1186, 2047):
        vm.r[4] = quarter_kph << 5
        vm.run(PHASE_PARAMETERS)
        vm.r[8:10] = [0, 0xFF00]
        spans = set()
        for edge in range(1, 2049):
            vm.run(PHASE_STEP)
            ideal_whole, ideal_remainder = divmod(edge * HALF_PHASE_NUMERATOR, quarter_kph)
            assert vm.r[8:10] == [ideal_remainder, (0xFF00 + ideal_whole) & 0xFFFF]
            spans.add(vm.r[4])
        stable_examples.append({"quarter_kph": quarter_kph, "phase_ticks": sorted(spans)})

    return {
        "nonzero_speed_words": 2047,
        "carry_boundaries": boundary_cases,
        "successive_edges_per_example": 2048,
        "examples": stable_examples,
        "requires_intermediate_compare_above_half_counter_range": True,
    }


def verify(engine, s04, image, c167):
    if digest(s04) != S04_SHA:
        raise ValueError("Expected the pinned S04 project image")
    expected, manifest, _, _ = build(engine, s04, with_engine_signals_tx=True)
    if image != expected:
        raise ValueError("Expected the reproducible E4M3 transmitter/receiver candidate")

    import build_can_diag as diag

    def read_rom(blob, address, length):
        offset = diag.offset(address)
        return blob[offset:offset + length]

    timer_anchors = {
        0x0000C8: "fa00c800",          # CC18 vector loops to itself.
        0x0000D0: "fa00d000",          # CC20 vector loops to itself.
        0x01B88E: "e6a00000e6a15b00e6904a47",  # T2CON, T3CON, T78CON.
        0x01B8D0: "e6e2dfafe6e3feb5",  # P3 and DP3 startup.
        0x01B964: "e632ffff",          # CC18.
        0x01B96C: "e634ffff",          # CC20.
        0x01B9AC: "e6910d00e6920005",  # CCM4 and CCM5.
        0x01B9FC: "d1b0e6b05c00e6b11700e6b20000e6b35300",  # EXTR and CC16–19IC.
        0x01BA0E: "d1b0e6b40000",      # EXTR and CC20IC.
        0x09C302: "3ae28866",          # Native status reads P3.6 in the foreground.
        0x09C512: "9ae20960",          # Native read of P3.6 in the 80F2 override path.
    }
    for address, encoded in timer_anchors.items():
        raw = bytes.fromhex(encoded)
        assert read_rom(image, address, len(raw)) == read_rom(s04, address, len(raw)) == raw

    for start, end in ((NATIVE, CONTINUE), (ACTUATOR, ACTUATOR_RETURN + 2),
                       (FORCED_HIGH, FORCED_HIGH + 2)):
        assert read_rom(image, start, end - start) == read_rom(s04, start, end - start)
    set_bit = read_rom(image, 0x0C19CA, 2)
    clear_bit = read_rom(image, 0x0C19CE, 2)
    assert (set_bit, clear_bit) == (b"\x6f\xe2", b"\x6e\xe2")
    assert SPEED_LOGICAL & 0x3FFF == SPEED

    vm = build_native_model(image, c167)
    fixture = assemble(diag, set_bit, clear_bit)
    load_fixture(vm, FIXTURE, fixture)

    coverage = {"native_handoff": 0, "drive_low": 0, "drive_high": 0}
    commands = (0, COMMAND_LOW, COMMAND_HIGH, 3, 0xFFFF)
    for command, armed, mask, mode, relay, fresh, moving, high in product(
        commands, (0, 1, 2), (0x1, 0x101), (0, 1, 2, 3, 255),
        (False, True), (False, True), (False, True), (False, True),
    ):
        vm.reset()
        vm.r[1:] = [0xA500 + reg for reg in range(1, 16)]
        vm.r[12:14] = [command, armed]
        registers = vm.r.copy()
        port = 0xB5BE | (PORT_BIT if high else 0)
        vm.write(PORT3, port)
        status = 0x081F if high else 0x0800
        vm.write(0xFF10, status)
        vm.write(ACTUATOR_MASK, mask)
        vm.write(OVERRIDE_MODE, mode, 1)
        vm.write(RELAY_STATE, RELAY_BIT if relay else 0)
        vm.write(AGE, 32 if fresh else 0)
        vm.write(SPEED_LOGICAL, 7680 if moving else 0)

        allowed = (command in (COMMAND_LOW, COMMAND_HIGH) and armed == 1 and
                   not mask & 0x100 and mode <= 1 and not relay and fresh and moving)
        expected_port = port
        outcome = "native_handoff"
        if allowed and command == COMMAND_LOW:
            expected_port &= ~PORT_BIT
            outcome = "drive_low"
        if allowed and command == COMMAND_HIGH:
            expected_port |= PORT_BIT
            outcome = "drive_high"

        initial_memory = vm.mem.copy()
        vm.run(FIXTURE, stop=CONTINUE if allowed else NATIVE)
        assert vm.read(PORT3) == expected_port and vm.read(0xFF10) == status
        assert vm.r == registers and vm.sp == 0xFD7C  # Only the harness return remains.
        # No writes outside the register latch and the harness/fixture stack.
        assert {a for a, v in vm.mem.items() if initial_memory.get(a) != v} <= (
            {PORT3} | set(range(0xFD78, 0xFD80))
        )
        coverage[outcome] += 1

    for command in (COMMAND_LOW, COMMAND_HIGH):
        vm.reset()
        vm.r[12] = 3 if command == COMMAND_LOW else 2  # Native service ABI.
        vm.write(PORT3, 0xB5BE | (PORT_BIT if command == COMMAND_LOW else 0))
        vm.run(ACTUATOR, stop=ACTUATOR_RETURN)
        assert vm.r[4] == 0x26
        assert vm.read(PORT3) == 0xB5BE | (PORT_BIT if command == COMMAND_HIGH else 0)
    vm.reset()
    vm.write(PORT3, 0xB5BE)
    vm.run(FORCED_HIGH, stop=FORCED_HIGH + 2)
    assert vm.read(PORT3) == 0xB5BE | PORT_BIT

    return {
        "status": "PASS_OFFLINE_ISA_FIXTURE",
        "candidate_sha256": manifest["sha256"],
        "handoff_fixture_bytes": len(fixture),
        "unchanged_timer_instruction_windows": len(timer_anchors),
        "fixture_address_model_only": hex(FIXTURE),
        "coverage": coverage,
        "original_actuator_set_clear_and_forced_high": "PASS",
        "original_normal_owner_reached_with_entry_state_intact": True,
        "fractional_nominal_t8_compare_model": verify_fractional_phase(vm, diag),
        "candidate_modified": False,
        "interrupt_or_electrical_timing_tested": False,
    }


def main():
    if not __debug__:
        raise RuntimeError("Enable Python assertions for the ISA fixture")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", required=True, type=Path)
    parser.add_argument("--s04", required=True, type=Path)
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--c167", required=True, type=Path)
    args = parser.parse_args()
    report = verify(args.engine.resolve(), args.s04.read_bytes(), args.image.read_bytes(), args.c167)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
