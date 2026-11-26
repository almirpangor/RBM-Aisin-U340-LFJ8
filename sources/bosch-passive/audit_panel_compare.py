#!/usr/bin/env python3
"""Run a bounded ST10 compare service in the model alongside the pinned E4M3."""

import argparse
from itertools import product
import json
from pathlib import Path

from build import S04_SHA, build, digest
from verify import build_native_model

ORIGIN, LIMIT = 0x066300, 0x066500  # Exact candidate padding, overlaid only in the emulator.
CC18, CC18IC, CCM4 = 0xFE64, 0xF164, 0xFF22
T8, T8REL, T78CON, T4CON, PORT3 = 0xF052, 0xF056, 0xFF20, 0xFF44, 0xFFC4
MODE_MASK, COMPARE_T8 = 0x0F00, 0x0C00
T8_MASK, T8_SLOW, T8_FAST = 0x4F00, 0x4700, 0x4400
HORIZON = 0x7FFF
RELEASED, EDGE, CHECKPOINT, DUE = range(4)


def assemble(diag):
    """R12:R13 now and R14:R15 deadline are low:high coherent T4 words.

    R7 minimum T8 lead, R8 ownership, R9 enable, R10 prequalified IRQ bits.
    Requires DPP3=3. Clobbers R1..R6/R11 and flags. Caller serializes native divisor changes and
    IRQ service. Ownership requires an installed vector and a reserved channel.
    """
    a = diag.BasicAsm(ORIGIN, LIMIT)
    a.imm(4, RELEASED)
    a.cmp(8, 1)
    a.branch(3, "return")
    a.ld(6, CCM4)
    a.rr(5, 6)
    a.andi(5, MODE_MASK)
    a.branch(2, "owned")
    a.cmp(5, COMPARE_T8)
    a.branch(3, "return")
    a.label("owned")
    a.andi(6, 0xFFFF ^ MODE_MASK)
    a.st(CCM4, 6)
    a.zero(CC18IC)
    a.cmp(9, 1)
    a.branch(3, "return")
    a.cmp(7, 0)
    a.branch(2, "return")
    a.cmp(7, HORIZON)
    a.branch(14, "return")
    a.cmp(10, 0x3F)
    a.branch(14, "return")
    a.rr(3, 10)
    a.andi(3, 0x3C)
    a.branch(2, "return")
    a.cmp(3, 0x38)  # Keep the PEC-selected interrupt levels out of this service.
    a.branch(9, "return")
    a.ld(3, T4CON)
    a.andi(3, 0x01FF)
    a.cmp(3, 0x0046)
    a.branch(3, "return")
    a.ld(3, T8REL)
    a.cmp(3, 0)
    a.branch(3, "return")

    a.rr(2, 14)
    a.rr(1, 15)
    a.sub(2, 12)
    a.op(0x30, 1, 13, "SUBC")
    a.rr(3, 1)
    a.andi(3, 0x8000)
    a.branch(3, "due")
    a.rr(3, 1)
    a.either(3, 2)
    a.branch(2, "due")

    a.ld(5, T78CON)
    a.andi(5, T8_MASK)
    a.cmp(5, T8_SLOW)
    a.branch(2, "convert")
    a.cmp(5, T8_FAST)
    a.branch(3, "return")
    a.label("convert")
    a.imm(4, EDGE)
    a.cmp(1, 0)
    a.branch(3, "checkpoint")
    a.rr(3, 2)
    a.cmp(5, T8_SLOW)
    a.branch(3, "fast")
    a.shift(3, 1)
    a.andi(2, 1)
    a.add(3, 2)
    a.cmp(3, HORIZON)
    a.branch(14, "checkpoint")
    a.branch(0, "schedule")
    a.label("fast")
    a.cmp(3, HORIZON // 4)
    a.branch(14, "checkpoint")
    a.shift(3, 2, True)
    a.branch(0, "schedule")
    a.label("checkpoint")
    a.imm(4, CHECKPOINT)
    a.imm(3, HORIZON)

    a.label("schedule")
    a.ld(11, T8)
    a.add(11, 3)
    a.st(CC18, 11)
    a.ld(3, T78CON)
    a.andi(3, T8_MASK)
    a.cmpreg(3, 5)
    a.branch(3, "abort")
    a.ld(3, T8)
    a.rr(2, 11)
    a.sub(2, 3)
    a.cmpreg(2, 7)
    a.branch(8, "abort")
    a.cmp(2, HORIZON)
    a.branch(14, "abort")
    # Enable IE while match generation is off; never clear IR after enabling.
    a.rr(3, 10)
    a.ori(3, 0x40)
    a.st(CC18IC, 3)
    a.ori(6, COMPARE_T8)
    a.st(CCM4, 6)
    a.branch(0, "return")
    a.label("abort")
    a.imm(4, RELEASED)
    a.branch(0, "return")
    a.label("due")
    a.imm(4, DUE)
    a.label("return")
    a.raw("db00", "RETS")
    return a.finish()


def verify(engine, s04, image, c167):
    if digest(s04) != S04_SHA:
        raise ValueError("Expected the pinned S04 project image")
    expected, manifest, _, _ = build(engine, s04, with_engine_signals_tx=True)
    if image != expected:
        raise ValueError("Expected the reproducible E4M3 transmitter/receiver candidate")

    import build_can_diag as diag

    native = {
        0x0000C8: "fa00c800",  # CC18 vector is not installed in the candidate.
        0x01B964: "e632ffff",
        0x01B9AC: "e6910d00",
        0x018BB4: "e6f4bfff64f444ff",  # Native T4 reinitialization stops the timer.
        0x018BFC: "2804ec88",          # Native coherent T4 reader entry.
        0x045ACA: "1a900707",
        0x045E24: "1a900407",
    }
    for address, encoded in native.items():
        offset = diag.offset(address)
        raw = bytes.fromhex(encoded)
        assert image[offset:offset + len(raw)] == s04[offset:offset + len(raw)] == raw, hex(address)

    vm = build_native_model(image, c167)
    code = assemble(diag)
    offset = diag.offset(ORIGIN)
    padding = b"\xff" * (LIMIT - ORIGIN)
    assert image[offset:offset + len(padding)] == s04[offset:offset + len(padding)] == padding
    vm.rom.update(enumerate(code, ORIGIN))

    def run(now, delta, *, start=0xFFF0, elapsed=0, mode=T8_SLOW, changed_mode=None,
            original_mode=COMPARE_T8, own=1, enable=1, minimum_lead=2, priority=0x15,
            t4_mode=0x46, reload=0):
        vm.reset()
        vm.r[7:11] = [minimum_lead, own, enable, priority]
        deadline = (now + delta) & 0xFFFFFFFF
        vm.r[12:16] = [now & 65535, now >> 16, deadline & 65535, deadline >> 16]
        inputs = vm.r[7:11] + vm.r[12:16]
        for address, value in ((CC18, 0xFFFF), (CC18IC, 0xD5), (CCM4, 0xA07D | original_mode),
                               (T8, start), (T78CON, mode | 0x004A), (T4CON, t4_mode),
                               (T8REL, reload), (PORT3, 0xAFDF)):
            vm.write(address, value)

        read, write = vm.read, vm.write
        accesses = {T8: 0, T78CON: 0}
        writes = []

        def live_read(address, size=2, extend=True):
            if address in accesses and size == 2:
                accesses[address] += 1
                if accesses[address] == 2:
                    if address == T8:
                        return (start + elapsed) & 0xFFFF
                    if changed_mode is not None:
                        return changed_mode | 0x004A
            return read(address, size, extend)

        def traced_write(address, value, size=2, extend=True):
            if address not in (0xFD7C, 0xFD7E):  # The model's synthetic call return.
                writes.append((address, value))
            write(address, value, size, extend)

        vm.read, vm.write = live_read, traced_write
        try:
            vm.run(ORIGIN)
        finally:
            vm.read, vm.write = read, write
        assert vm.r[7:11] + vm.r[12:16] == inputs
        assert vm.sp == 0xFD80 and vm.read(T78CON) == mode | 0x004A
        assert all(address in (CC18, CC18IC, CCM4) for address, _ in writes)
        return vm.r[4], writes

    vectors = 0
    lead_aborts = 0
    for mode, now, start, delta, elapsed in product(
            (T8_FAST, T8_SLOW), (0, 0x0000FFFF, 0xFFFFFFFE), (0x0020, 0xFFF0),
            (-32768, -1, 0, 1, 2, 3, 4, 79, 196, 8191, 8192, 65534, 65535, 65536, 0x7FFFFFFF),
            (0, 1, 7),
    ):
        actual, writes = run(now, delta, start=start, elapsed=elapsed, mode=mode)
        disabled = [(CCM4, 0xA07D), (CC18IC, 0)]
        if delta <= 0:
            assert (actual, writes) == (DUE, disabled)
        else:
            projected = (delta + 1) // 2 if mode == T8_SLOW else 4 * delta
            span = min(projected, HORIZON)
            programmed = disabled + [(CC18, (start + span) & 0xFFFF)]
            if span - elapsed < 2:
                assert (actual, writes) == (RELEASED, programmed)
                lead_aborts += 1
            else:
                status = EDGE if projected <= HORIZON else CHECKPOINT
                assert (actual, writes) == (status, programmed + [(CC18IC, 0x55), (CCM4, 0xAC7D)])
        vectors += 1

    assert run(0, 100, own=0) == (RELEASED, [])
    assert run(0, 100, original_mode=0x0500) == (RELEASED, [])
    disabled = [(CCM4, 0xA07D), (CC18IC, 0)]
    for kwargs in ({"enable": 0}, {"priority": 0}, {"priority": 0x40}, {"priority": 0x38},
                   {"minimum_lead": 0}, {"minimum_lead": 0x8000}, {"mode": 0x0700},
                   {"t4_mode": 0x45}, {"reload": 1}):
        assert run(0, 100, **kwargs) == (RELEASED, disabled)
    assert run(0, 100, changed_mode=T8_FAST) == (RELEASED, disabled + [(CC18, 0x0022)])
    assert run(0, 100, mode=T8_FAST, changed_mode=T8_SLOW) == (
        RELEASED, disabled + [(CC18, 0x0180)]
    )
    assert run(0, 4, original_mode=0)[0] == EDGE
    # Same absolute T4 edge, through clock change and an early CC18 wake-up.
    deadline = 0x00010000
    assert run(deadline - 100, 100)[1][2] == (CC18, 0x0022)
    assert run(deadline - 70, 70, mode=T8_FAST)[1][2] == (CC18, 0x0108)
    assert run(deadline - 1, 1, mode=T8_FAST)[0] == EDGE
    assert run(deadline, 0, mode=T8_FAST)[0] == DUE

    return {
        "status": "PASS_OFFLINE_ISA_COMPARE_SERVICE",
        "candidate_sha256": manifest["sha256"],
        "model_code_bytes": len(code),
        "model_overlay_address": hex(ORIGIN),
        "compare_vectors": vectors,
        "lead_time_aborts": lead_aborts,
        "stock_timer_and_pin_registers_written": False,
        "vector_installed_in_candidate": False,
        "native_mode_switch_hooks_installed": False,
        "actual_irq_latency_tested": False,
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
