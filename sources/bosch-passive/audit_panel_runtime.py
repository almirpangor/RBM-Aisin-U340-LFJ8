#!/usr/bin/env python3
"""Join the Bosch panel phase, compare and IRQ experiments in an unchanged-ROM model."""

import argparse
from itertools import product
import json
from pathlib import Path

import audit_panel_compare as compare
import audit_panel_irq as irq
from audit_panel_handoff import load_fixture
from build import S04_SHA, build, digest
from verify import build_native_model

PHASE_CODE, READBACK_CODE, READBACK_HOOKS = 0x010000, 0x010400, 0x010500
SERVICE_CODE, LATCH_CODE = 0x010700, 0x010800
READ_SITES = ((0x09AE6C, "4ae2ff60"), (0x09C302, "3ae28866"), (0x09C512, "9ae20960"))
DEADLINE_LOW, DEADLINE_HIGH, PHASE_STATE, CARRY = 0xE7B8, 0xE7BA, 0xE7BC, 0xE7BE
PORT3, DP3, PORT_BIT = 0xFFC4, 0xFFC6, 0x0040
OWNED, LEVEL_HIGH, NATIVE_HIGH, Q_MASK = 0x8000, 0x4000, 0x2000, 0x07FF
RELEASE, PLAN, DRIVE_LOW, DRIVE_HIGH, WAIT = range(5)
HALF_PHASE_NUMERATOR = 93750  # 6000 imp/km, 50%, T4 /512 at nominal fCPU 40 MHz.


def assemble_phase(diag):
    """R5 qualified Q7>>5; R6 allowed lateness; R7 route/lease; R12:R13 now.

    R4 returns the action and R14:R15 the absolute deadline. The caller owns
    serialization, compare activation, hardware permission and stock handoff.
    """
    a = diag.BasicAsm(PHASE_CODE, READBACK_CODE)
    a.cmp(7, 1)
    a.branch(3, "release")
    a.cmp(5, 0)
    a.branch(2, "release")
    a.cmp(5, Q_MASK)
    a.branch(14, "release")
    a.ld(3, PHASE_STATE)
    a.rr(2, 3)
    a.andi(2, OWNED)
    a.branch(2, "acquire")
    a.ld(4, irq.STATE)
    a.cmp(4, irq.ARMED)
    a.branch(2, "wait")
    a.cmp(4, irq.WAKEUP)
    a.branch(2, "read_deadline")
    a.cmp(4, irq.REBASE)
    a.branch(3, "release")
    a.label("read_deadline")
    a.ld(14, DEADLINE_LOW)
    a.ld(15, DEADLINE_HIGH)
    a.rr(1, 12)
    a.rr(2, 13)
    a.sub(1, 14)
    a.op(0x30, 2, 15, "SUBC")
    a.rr(4, 2)
    a.andi(4, 0x8000)
    a.branch(3, "early")
    a.cmp(2, 0)
    a.branch(3, "release")
    a.cmpreg(1, 6)
    a.branch(14, "release")

    a.rr(2, 3)
    a.andi(2, LEVEL_HIGH)
    a.branch(2, "rise")
    a.andi(3, 0xFFFF ^ LEVEL_HIGH)
    a.rr(2, 3)
    a.andi(2, Q_MASK)
    a.cmpreg(2, 5)
    a.branch(2, "fall")
    a.andi(3, 0xFFFF ^ Q_MASK)
    a.either(3, 5)
    a.zero(CARRY)
    a.label("fall")
    a.imm(4, DRIVE_LOW)
    a.branch(0, "advance")
    a.label("rise")
    a.ori(3, LEVEL_HIGH)
    a.imm(4, DRIVE_HIGH)
    a.branch(0, "advance")

    a.label("acquire")
    a.ld(4, irq.STATE)
    a.cmp(4, irq.RELEASED)
    a.branch(3, "release")
    a.ld(4, DP3)
    a.andi(4, PORT_BIT)
    a.branch(2, "release")
    a.ld(4, PORT3)
    a.andi(4, PORT_BIT)
    a.branch(2, "release")  # Preserve the known native idle latch on acquisition.
    a.rr(3, 5)
    a.ori(3, OWNED | LEVEL_HIGH | NATIVE_HIGH)
    a.zero(CARRY)
    a.rr(14, 12)
    a.rr(15, 13)
    a.imm(4, PLAN)

    a.label("advance")
    a.st(PHASE_STATE, 3)
    a.andi(3, Q_MASK)
    a.cmp(3, 0)
    a.branch(2, "release")
    a.cmp(3, 1)
    a.branch(2, "low_speed")  # DIVLU quotient for q=1 does not fit one word.
    a.raw("ec06ec07", "PUSH MDH; PUSH MDL")
    a.emit(bytes.fromhex("e606") + diag.word(HALF_PHASE_NUMERATOR >> 16), "MOV MDH,#1")
    a.emit(bytes.fromhex("e607") + diag.word(HALF_PHASE_NUMERATOR), "MOV MDL,#6E36h")
    a.raw("7b33", "DIVLU R3")
    a.ld(1, 0xFE0E)
    a.ld(2, 0xFE0C)
    a.raw("fc07fc06", "POP MDL; POP MDH")
    a.ld(6, CARRY)
    a.cmpreg(6, 3)
    a.branch(9, "release")
    a.add(6, 2)
    a.cmpreg(6, 3)
    a.branch(8, "save_carry")
    a.sub(6, 3)
    a.addi(1, 1)
    a.label("save_carry")
    a.st(CARRY, 6)
    a.imm(2, 0)
    a.branch(0, "save_deadline")
    a.label("low_speed")
    a.zero(CARRY)
    a.imm(1, HALF_PHASE_NUMERATOR & 0xFFFF)
    a.imm(2, 1)
    a.label("save_deadline")
    a.add(14, 1)
    a.op(0x10, 15, 2, "ADDC")
    a.st(DEADLINE_LOW, 14)
    a.st(DEADLINE_HIGH, 15)
    a.raw("db00", "RETS")
    a.label("early")
    a.imm(4, PLAN)
    a.raw("db00", "RETS")
    a.label("wait")
    a.imm(4, WAIT)
    a.raw("db00", "RETS")
    a.label("release")
    # Preserve the old latch witness until the caller has restored native control.
    a.zero(irq.STATE)
    a.imm(4, RELEASE)
    a.raw("db00", "RETS")
    return a.finish()


def assemble_readback(diag):
    a = diag.BasicAsm(READBACK_CODE, READBACK_CODE + 0x100)
    a.ld(4, DP3)
    a.andi(4, PORT_BIT)
    a.branch(2, "port")
    a.ld(4, PHASE_STATE)
    a.rr(5, 4)
    a.andi(5, OWNED)
    a.branch(2, "port")
    a.andi(4, NATIVE_HIGH)
    a.shift(4, 13)
    a.raw("db00", "RETS")
    a.label("port")
    a.ld(4, PORT3)
    a.andi(4, PORT_BIT)
    a.shift(4, 6)
    a.raw("db00", "RETS")
    return a.finish()


def assemble_readback_hooks(diag):
    a = diag.BasicAsm(READBACK_HOOKS, READBACK_HOOKS + 0x200)
    for index, (site, _) in enumerate(READ_SITES):
        a.label(f"read_{index}")
        a.raw("ec88ecf4ecf5", "PUSH PSW; PUSH R4; PUSH R5")
        a.emit(diag.far(0xDA, READBACK_CODE), "CALLS read_native_latch")
        a.cmp(4, 0)
        a.branch(2, f"low_{index}")
        for high, source in ((True, 0x8F), (False, 0x8E)):
            if not high:
                a.label(f"low_{index}")
            a.raw("fcf5fcf4fc88", "POP R5; POP R4; POP PSW")
            continuation = site + 4
            if index == 0:
                a.emit(bytes((0x4A, source, 0xFF, 0)), "BMOV R15.0,original latch")
            elif index == 1:
                a.label(f"negated_{int(high)}")
                a.emit(bytes((0x3A, source, 0x88, 6)), "BMOVN PSW.6,original latch")
            elif not high:
                continuation += 18  # Native JNB relative displacement: 9 words.
            a.emit(diag.far(0xFA, continuation), "JMPS native continuation")
    return a.finish(), a.labels


def execute_bmovn(vm, pc):
    opcode, source, destination, bits = irq.rom_bytes(vm, pc, 4)
    assert (opcode, destination, bits) == (0x3A, 0x88, 6) and source in (0x8E, 0x8F)
    high = bool(vm.get(source) & 1)
    previous = vm.read(irq.PSW)
    # PM0036: the destination is negated, while N/Z describe the source bit.
    vm.write(irq.PSW, (previous & ~0x5F) | (0x0001 if high else 0x0048))


def assemble_service(diag):
    a = diag.BasicAsm(SERVICE_CODE, LATCH_CODE)
    a.cmp(8, 1)  # No claimed compare or I/O ownership.
    a.branch(3, "unavailable")
    a.raw("ecf7", "PUSH R7")
    a.rr(6, 11)
    a.rr(7, 9)
    a.emit(diag.far(0xDA, PHASE_CODE), "CALLS update_phase")
    a.raw("fcf7", "POP R7")
    a.cmp(4, WAIT)
    a.branch(2, "return")
    a.cmp(4, RELEASE)
    a.branch(2, "release")
    a.raw("ecf4", "PUSH R4 ; keep phase action through compare preparation")
    a.emit(diag.far(0xDA, compare.ORIGIN), "CALLS arm_compare")
    a.cmp(4, compare.EDGE)
    a.branch(2, "publish")
    a.cmp(4, compare.CHECKPOINT)
    a.branch(2, "publish")
    a.raw("fcf4", "POP R4")
    a.label("release")
    a.imm(9, 0)
    a.emit(diag.far(0xDA, compare.ORIGIN), "CALLS cancel_compare")
    a.imm(12, RELEASE)
    a.branch(0, "latch")
    a.label("publish")
    a.raw("fcfc", "POP R12 ; phase action")
    a.label("latch")
    a.emit(diag.far(0xDA, LATCH_CODE), "CALLS apply_latch_and_publish")
    a.branch(0, "return")
    a.label("unavailable")
    a.imm(4, RELEASE)
    a.label("return")
    a.raw("db00", "RETS")
    return a.finish()


def assemble_latch(diag, set_bit, clear_bit):
    a = diag.BasicAsm(LATCH_CODE, LATCH_CODE + 0x100)
    a.cmp(12, RELEASE)
    a.branch(2, "release")
    a.cmp(12, DRIVE_LOW)
    a.branch(3, "try_high")
    a.emit(clear_bit, "BCLR P3.6")
    a.branch(0, "commit")
    a.label("try_high")
    a.cmp(12, DRIVE_HIGH)
    a.branch(3, "commit")
    a.emit(set_bit, "BSET P3.6")
    a.label("commit")
    a.set(irq.STATE, irq.ARMED)
    a.branch(0, "return")
    a.label("release")
    a.ld(4, DP3)
    a.andi(4, PORT_BIT)
    a.branch(2, "clear_state")
    a.ld(4, PHASE_STATE)
    a.andi(4, OWNED)
    a.branch(2, "clear_state")
    a.ld(4, PHASE_STATE)
    a.andi(4, NATIVE_HIGH)
    a.branch(2, "restore_low")
    a.emit(set_bit, "BSET P3.6 ; restore native latch")
    a.branch(0, "clear_state")
    a.label("restore_low")
    a.emit(clear_bit, "BCLR P3.6 ; restore native latch")
    a.label("clear_state")
    for address in (DEADLINE_LOW, DEADLINE_HIGH, PHASE_STATE, CARRY, irq.STATE):
        a.zero(address)
    a.label("return")
    a.rr(4, 12)
    a.raw("db00", "RETS")
    return a.finish()


def verify(engine, s04, image, c167):
    if digest(s04) != S04_SHA:
        raise ValueError("Expected the pinned S04 project image")
    expected, manifest, _, _ = build(engine, s04, with_engine_signals_tx=True)
    if image != expected:
        raise ValueError("Expected the reproducible E4M3 transmitter/receiver candidate")
    import build_can_diag as diag

    vm = build_native_model(image, c167)
    for address, encoded in (*READ_SITES, (0x01B8D4, "e6e3feb5")):
        assert irq.rom_bytes(vm, address, len(bytes.fromhex(encoded))) == bytes.fromhex(encoded)
    reservation = irq.probe_stack_reservation(diag, image)
    phase = assemble_phase(diag)
    readback = assemble_readback(diag)
    hooks, hook_symbols = assemble_readback_hooks(diag)
    load_fixture(vm, PHASE_CODE, phase)
    load_fixture(vm, READBACK_CODE, readback)
    load_fixture(vm, READBACK_HOOKS, hooks)
    for index, (site, _) in enumerate(READ_SITES):
        vm.rom.update(enumerate(diag.far(0xFA, hook_symbols[f"read_{index}"]), site))

    native_switches = [(site, bytes.fromhex(encoded)) for site, encoded in irq.SWITCHES]
    interrupt_code, irq_symbols = irq.assemble(diag, native_switches)
    for address, code in ((compare.ORIGIN, compare.assemble(diag)), (irq.ORIGIN, interrupt_code)):
        assert irq.rom_bytes(vm, address, len(code)) == b"\xff" * len(code)
        vm.rom.update(enumerate(code, address))
    assert irq.rom_bytes(vm, irq.VECTOR, 4) == b"\xfa\x00\xc8\x00"
    vm.rom.update(enumerate(diag.far(0xFA, irq_symbols["interrupt"]), irq.VECTOR))
    for index, (site, original) in enumerate(native_switches):
        assert irq.rom_bytes(vm, site, len(original)) == original
        vm.rom.update(enumerate(diag.far(0xFA, irq_symbols[f"switch_{index}"]), site))

    service_code = assemble_service(diag)
    set_bit, clear_bit = irq.rom_bytes(vm, 0x0C19CA, 2), irq.rom_bytes(vm, 0x0C19CE, 2)
    assert (set_bit, clear_bit) == (b"\x6f\xe2", b"\x6e\xe2")
    latch_code = assemble_latch(diag, set_bit, clear_bit)
    load_fixture(vm, SERVICE_CODE, service_code)
    load_fixture(vm, LATCH_CODE, latch_code)

    def seed():
        vm.reset()
        for address in (DEADLINE_LOW, DEADLINE_HIGH, PHASE_STATE, CARRY, irq.STATE):
            vm.write(address, 0)
        vm.write(PORT3, 0xAFDF)
        vm.write(DP3, 0xB5FE)
        vm.md[:] = [0xCAFE, 0xBABE]

    def event(now, q, late=2, enabled=True):
        vm.r[5:8] = [q, late, int(enabled)]
        vm.r[12:14] = [now & 0xFFFF, now >> 16]
        vm.run(PHASE_CODE)
        assert vm.md == [0xCAFE, 0xBABE] and vm.sp == 0xFD80
        assert vm.r[12:14] == [now & 0xFFFF, now >> 16]
        return vm.r[4], vm.r[14] | vm.r[15] << 16

    vectors = 0
    for q in range(1, Q_MASK + 1):
        seed()
        start = 0xFFFF0000
        now = start
        for index in range(1, 33):
            action, deadline = event(now, q)
            assert action == (PLAN if index == 1 else (DRIVE_LOW if index % 2 == 0 else DRIVE_HIGH))
            elapsed, residue = divmod(index * HALF_PHASE_NUMERATOR, q)
            assert deadline == (start + elapsed) & 0xFFFFFFFF and vm.read(CARRY) == residue
            assert vm.read(PHASE_STATE) & Q_MASK == q
            vm.write(irq.STATE, irq.WAKEUP)
            now = deadline
            vectors += 1

    for output, owner, stock, physical in product((False, True), repeat=4):
        seed()
        vm.write(DP3, PORT_BIT if output else 0)
        vm.write(PORT3, PORT_BIT if physical else 0)
        vm.write(PHASE_STATE, (OWNED if owner else 0) | (NATIVE_HIGH if stock else 0))
        vm.run(READBACK_CODE)
        expected_bit = stock if output and owner else physical
        assert vm.r[4] == expected_bit
        for index, (site, _) in enumerate(READ_SITES):
            vm.r[1:] = [0xA100 + offset for offset in range(1, 16)]
            registers = vm.r.copy()
            vm.write(irq.PSW, 0x291F)
            end = site + 4 + (18 if index == 2 and not expected_bit else 0)
            if index == 1:
                negated = hook_symbols[f"negated_{int(expected_bit)}"]
                irq.run_to(vm, site, negated)
                execute_bmovn(vm, negated)
                irq.run_to(vm, negated + 4, end)
            else:
                irq.run_to(vm, site, end)
            if index == 0:
                registers[15] = (registers[15] & ~1) | int(expected_bit)
                assert vm.read(irq.PSW) == (0x2901 if expected_bit else 0x2908)
            elif index == 1:
                assert vm.read(irq.PSW) == (0x2901 if expected_bit else 0x2948)
            else:
                assert vm.read(irq.PSW) == 0x291F
            assert vm.r == registers and vm.read(PORT3) == (PORT_BIT if physical else 0)

    def runtime(now, q, permitted=True, elapsed_limit=3):
        vm.r[5] = q
        vm.r[7:12] = [2, 1, int(permitted), 0x15, elapsed_limit]
        vm.r[12:14] = [now & 0xFFFF, now >> 16]
        vm.run(SERVICE_CODE)
        assert vm.md == [0xCAFE, 0xBABE] and vm.sp == 0xFD80
        return vm.r[4]

    def wakeup():
        vm.write(compare.T8, vm.read(compare.CC18))
        irq.accept_irq(vm, irq_symbols["reti"], 0x09405C, 0x1805)
        assert vm.read(irq.STATE) == irq.WAKEUP

    for index, initial_mode in enumerate((compare.T8_FAST, compare.T8_SLOW)):
        seed()
        for address, value in ((compare.T4CON, 0x46), (compare.T8REL, 0), (compare.T8, 0xFFF0),
                               (compare.T78CON, initial_mode | 0x004A), (compare.CCM4, 0xA07D),
                               (compare.CC18IC, 0), (compare.CC18, 0xFFFF),
                               (irq.DPP3, 3), (irq.NATIVE_BIT_WORD, 0), (irq.PSW, 0x1805)):
            vm.write(address, value)
        start = 0xFFFFFF80
        first = (start + 195) & 0xFFFFFFFF
        assert runtime(start, 480) == PLAN and vm.read(irq.STATE) == irq.ARMED
        assert runtime(start + 1, 480) == WAIT
        site, original = native_switches[index]
        pair = irq_symbols[f"pair_{index}"]
        irq.run_to(vm, site, pair)
        irq.execute_native_pair(vm, pair)
        irq.run_to(vm, pair + len(original), site + len(original))
        assert vm.read(irq.STATE) == irq.REBASE and vm.read(compare.CC18IC) == 0
        irq.accept_irq(vm, irq_symbols["reti"], 0x09405C, 0x1805)
        assert vm.read(irq.STATE) == irq.REBASE  # Stale match must not trigger a phase.
        assert runtime(start + 5, 480) == PLAN
        wakeup()
        assert runtime(first - 10, 480) == PLAN and vm.read(PORT3) & PORT_BIT
        wakeup()
        assert runtime(first, 480) == DRIVE_LOW and not vm.read(PORT3) & PORT_BIT
        assert vm.read(irq.STATE) == irq.ARMED
        irq.run_to(vm, READ_SITES[0][0], READ_SITES[0][0] + 4)
        assert vm.r[15] & 1  # Diagnostic response still sees the captured stock high.
        assert runtime(first + 1, 480, permitted=False) == RELEASE
        assert vm.read(PORT3) == 0xAFDF and vm.read(compare.CC18IC) == 0
        assert all(vm.read(address) == 0 for address in
                   (DEADLINE_LOW, DEADLINE_HIGH, PHASE_STATE, CARRY, irq.STATE))

    return {
        "status": "PASS_OFFLINE_PANEL_RUNTIME_PHASE_AND_READBACK",
        "candidate_sha256": manifest["sha256"],
        "phase_model_bytes": len(phase),
        "readback_model_bytes": len(readback),
        "readback_hooks_model_bytes": len(hooks),
        "nominal_fractional_phase_steps": vectors,
        "readback_truth_table_cases": 16,
        "native_readback_site_cases": 48,
        "linked_compare_irq_gpio_sequences": 2,
        "reservation": reservation,
        "candidate_modified": False,
    }


def main():
    if not __debug__:
        raise RuntimeError("Enable Python assertions for the panel runtime fixture")
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
