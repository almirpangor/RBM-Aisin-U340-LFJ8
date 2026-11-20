#!/usr/bin/env python3
"""Exercise the CC18 interrupt vector and both native T8 switch sites in an ST10 model."""

import argparse
from itertools import product
import json
from pathlib import Path
import struct

import audit_panel_compare as compare

from audit_panel_compare import CC18IC, CCM4, COMPARE_T8, MODE_MASK, T78CON
from build import S04_SHA, build, digest
from verify import build_native_model

VECTOR, ORIGIN, LIMIT = 0x0000C8, 0x066B00, 0x066C00
SWITCHES = ((0x045AC8, "d1101a900707ce1e"), (0x045E22, "d1101a900407cf1e"))
STATE, PSW, DPP3 = 0xE7FE, 0xFF10, 0xFE06
NATIVE_BIT_WORD = 0xFD3C
RELEASED, ARMED, WAKEUP, REBASE = range(4)


def push_context(a, *, save_psw):
    if save_psw:
        a.raw("ec88", "PUSH PSW")
    a.raw("ec03e6030300ecf4ecf5", "PUSH DPP3; MOV DPP3,#3; PUSH R4; PUSH R5")


def pop_context(a, *, save_psw):
    a.raw("fcf5fcf4fc03", "POP R5; POP R4; POP DPP3")
    if save_psw:
        a.raw("fc88", "POP PSW")


def assemble(diag, native_switches):
    a = diag.BasicAsm(ORIGIN, LIMIT)
    a.label("interrupt")
    push_context(a, save_psw=False)
    a.ld(4, STATE)
    a.cmp(4, ARMED)
    a.branch(3, "stale_irq")
    a.emit(diag.far(0xDA, 0), "CALLS disable_compare")
    irq_call = len(a.data) - 4
    a.cmp(4, 2)  # Only a real armed compare may publish a wakeup.
    a.branch(3, "foreign_irq")
    a.set(STATE, WAKEUP)
    a.branch(0, "interrupt_exit")
    a.label("foreign_irq")
    a.zero(STATE)
    a.branch(0, "interrupt_exit")
    a.label("stale_irq")
    a.emit(diag.far(0xDA, 0), "CALLS disable_compare")
    stale_call = len(a.data) - 4
    a.label("interrupt_exit")
    pop_context(a, save_psw=False)
    a.label("reti")
    a.raw("fb88", "RETI")

    switch_calls = []
    for index, (site, original) in enumerate(native_switches):
        a.label(f"switch_{index}")
        push_context(a, save_psw=True)
        a.ld(4, STATE)
        a.cmp(4, RELEASED)
        a.branch(2, f"native_{index}")
        a.emit(diag.far(0xDA, 0), "CALLS disable_compare")
        switch_calls.append(len(a.data) - 4)
        a.cmp(4, 0)
        a.branch(2, f"foreign_{index}")
        a.set(STATE, REBASE)
        a.branch(0, f"native_{index}")
        a.label(f"foreign_{index}")
        a.zero(STATE)
        a.label(f"native_{index}")
        pop_context(a, save_psw=True)
        a.label(f"pair_{index}")
        a.emit(original, "Replay original ATOMIC, BFLDH and BSET/BCLR")
        a.emit(diag.far(0xFA, site + len(original)), "JMPS native continuation")

    a.label("disable_compare")
    a.ld(5, CCM4)
    a.rr(4, 5)
    a.andi(4, MODE_MASK)
    a.branch(2, "owned")
    a.cmp(4, COMPARE_T8)
    a.branch(3, "foreign")
    a.label("owned")
    a.andi(5, 0xFFFF ^ MODE_MASK)
    a.st(CCM4, 5)
    a.zero(CC18IC)
    a.shift(4, 11)
    a.raw("0841", "ADD R4,#1 ; 1 idle, 2 owned compare")
    a.raw("db00", "RETS")
    a.label("foreign")
    a.imm(4, 0)
    a.raw("db00", "RETS")
    for position in (irq_call, stale_call, *switch_calls):
        a.data[position:position + 4] = diag.far(0xDA, a.labels["disable_compare"])
    return a.finish(), a.labels


def rom_bytes(vm, start, length):
    return bytes(vm.rom[address] for address in range(start, start + length))


def run_to(vm, start, stop):
    """Use the existing C167 runner and remove its synthetic debugger return."""
    initial_sp = vm.sp
    vm.run(start, stop=stop)
    assert vm.sp == initial_sp - 4
    vm.sp = initial_sp


def execute_native_pair(vm, pc):
    """Decode the bounded stock opcode subset missing in the upstream executor."""
    atomic, count, op, target, value, mask, bit_move, offset = rom_bytes(vm, pc, 8)
    assert (atomic, count, op, target, mask, offset) == (0xD1, 0x10, 0x1A, 0x90, 7, 0x1E)
    assert (value, bit_move) in ((7, 0xCE), (4, 0xCF))
    # PM0036 BFLDH: masked high byte; N/Z describe the word and C/V/E clear.
    word = (vm.get(target) & ~(mask << 8)) | (value << 8)
    vm.put(target, word)
    vm.mov(word)
    vm.e = vm.c = vm.v = False
    # The original BSET/BCLR is supported by the pinned executor.
    run_to(vm, pc + 6, pc + 8)


def accept_irq(vm, reti, interrupted_pc, interrupted_psw):
    """Supply a segmented interrupt frame and decode RETI as specified by PM0036."""
    initial_sp = vm.sp
    vm.sp -= 2
    vm.write(vm.sp, interrupted_psw)
    push = vm.push_return
    vm.push_return = lambda pc: push(interrupted_pc if pc == 0xFFFFFE else pc)
    try:
        vm.run(VECTOR, stop=reti)
    finally:
        vm.push_return = push
    assert vm.sp == initial_sp - 6
    assert rom_bytes(vm, reti, 2) == b"\xfb\x88"
    ip, csp, psw = (vm.read(vm.sp + offset) for offset in (0, 2, 4))
    vm.sp += 6
    vm.write(PSW, psw)
    assert (csp << 16) | ip == interrupted_pc
    assert vm.sp == initial_sp and vm.read(PSW) == interrupted_psw


def probe_stack_reservation(diag, image):
    from test_e4m2 import NativeAddressProbe

    alternative = bytearray(image)
    groups = (
        ((0x2B2, 0x386, 0x3B0, 0x3E8), "e6f0bee7", "e6f0b6e7"),
        ((0x23E2, 0x2436, 0x24A8, 0x2518), "e6fcbce7", "e6fcb4e7"),
        ((0x85BD6,), "46fcbee7", "46fcb6e7"),
        ((0x85BEE,), "e6fcbee7", "e6fcb6e7"),
        ((0x85BF8,), "e6febee7", "e6feb6e7"),
        ((0xB43C,), "bee7", "b6e7"),
    )
    for offsets, old, new in groups:
        old, new = bytes.fromhex(old), bytes.fromhex(new)
        for offset in offsets:
            assert alternative[offset:offset + len(old)] == old
            alternative[offset:offset + len(new)] = new
    for _ in range(5):
        invalid = [record for record in diag.checks(alternative) if not record["valid"]]
        if not invalid:
            break
        for record in invalid:
            struct.pack_into("<II", alternative, record["file_offset"] + 8,
                             record["actual"], record["actual"] ^ 0xFFFFFFFF)
    records = diag.checks(alternative)
    assert len(records) == 51 and all(record["valid"] for record in records)
    assert digest(alternative) == "f08a485e27eecdd898145e1a534d42bdd2946d4412da4afb203803adbd518106"
    assert sum(old != new for old, new in zip(image, alternative, strict=True)) == 18

    for caller, call_pc in ((0x01BC4A, 0x01BC52), (0x01BAA4, 0x01BAAC)):
        for cp in (0xF800, 0xFC00):
            for blob, top in ((image, 0xE7BE), (alternative, 0xE7B6)):
                probe = NativeAddressProbe(blob, cp)
                probe.set(0, int.from_bytes(blob[0x2B4:0x2B6], "little"))
                probe.run(caller, call_pc)
                offset = diag.offset(call_pc)
                assert blob[offset:offset + 4] == b"\xda\x01\x34\x80"
                probe.run(0x018034, 0x018062)
                assert probe.r(0) == top and (0x018056, "read", 0x01B43C, top) in probe.trace
                probe.run(0x018220, 0x01822C)
                pushes = [event[2] for event in probe.trace
                          if event[1] == "stack_write" and 0x018220 <= event[0] < 0x01822C]
                assert pushes == [top - offset for offset in range(2, 14, 2)], pushes
                assert any(0xE7B8 <= addr < 0xE7C0 for addr in pushes) == (blob is image)
    return {
        "candidate_stack_top": "0xe7be",
        "model_only_stack_top": "0xe7b6",
        "model_only_state_words": ["0xe7b8", "0xe7ba", "0xe7bc", "0xe7be"],
        "model_only_reservation_sha256": digest(alternative),
        "startup_vectors_per_image": 4,
        "checksums_valid": len(records),
        "full_stack_watermark_verified": False,
    }


def verify(engine, s04, image, c167):
    if digest(s04) != S04_SHA:
        raise ValueError("Expected the pinned S04 project image")
    expected, manifest, _, _ = build(engine, s04, with_engine_signals_tx=True)
    if image != expected:
        raise ValueError("Expected the reproducible E4M3 transmitter/receiver candidate")

    import build_can_diag as diag

    vm = build_native_model(image, c167)
    native_switches = [(address, bytes.fromhex(text)) for address, text in SWITCHES]
    assert rom_bytes(vm, VECTOR, 4) == b"\xfa\x00\xc8\x00"
    assert rom_bytes(vm, 0x064888, 4) == b"\xf6\x8e\xfe\xe7"  # Stock reset clears this word.
    assert rom_bytes(vm, ORIGIN, LIMIT - ORIGIN) == b"\xff" * (LIMIT - ORIGIN)
    for address, blob in native_switches:
        assert rom_bytes(vm, address, len(blob)) == blob

    code, symbols = assemble(diag, native_switches)
    vm.rom.update(enumerate(code, ORIGIN))
    vm.rom.update(enumerate(diag.far(0xFA, symbols["interrupt"]), VECTOR))
    for index, (address, _) in enumerate(native_switches):
        vm.rom.update(enumerate(diag.far(0xFA, symbols[f"switch_{index}"]), address))

    states = (RELEASED, ARMED, WAKEUP, REBASE)
    foreign_mode = 0x0500
    register_context = [0xE600, *(0xB120 + index for index in range(1, 16))]

    def seed(state, mode, native_bit):
        vm.reset()
        vm.r[:] = register_context
        for address, value in ((STATE, state), (T78CON, 0xA548), (CCM4, 0xA07D | mode),
                               (DPP3, 3), (CC18IC, 0xD5), (PSW, 0x291F),
                               (NATIVE_BIT_WORD, 0x003A | native_bit)):
            vm.write(address, value)

    switches_tested = 0
    for index, state, mode, bit in product(range(2), states, (0, COMPARE_T8, foreign_mode), (0, 0x1000)):
        seed(state, mode, bit)
        site, original = native_switches[index]
        pair = symbols[f"pair_{index}"]
        run_to(vm, site, pair)
        assert vm.r == register_context and vm.read(PSW) == 0x291F and vm.read(DPP3) == 3
        owned = state != RELEASED and mode != foreign_mode
        assert vm.read(STATE) == (REBASE if owned else RELEASED)
        assert vm.read(CCM4) == (0xA07D if owned else 0xA07D | mode)
        assert vm.read(CC18IC) == (0 if owned else 0xD5)
        execute_native_pair(vm, pair)
        run_to(vm, pair + len(original), site + len(original))
        assert vm.read(T78CON) == (0xA748 if index == 0 else 0xA448)
        assert vm.read(NATIVE_BIT_WORD) == (0x003A if index == 0 else 0x103A)
        assert vm.read(PSW) == (0x2901 if bit else 0x2908)
        switches_tested += 1

    for state, mode in product(states, (0, COMPARE_T8, foreign_mode)):
        seed(state, mode, 0)
        vm.write(CC18IC, 0x55)  # IR was cleared by hardware interrupt acceptance.
        accept_irq(vm, symbols["reti"], 0x09405C, 0x1805)
        assert vm.r == register_context and vm.read(DPP3) == 3 and vm.read(T78CON) == 0xA548
        expected_state = (WAKEUP if mode == COMPARE_T8 else RELEASED) if state == ARMED else state
        assert vm.read(STATE) == expected_state
        assert vm.read(CC18IC) == (0x55 if mode == foreign_mode else 0)
        assert vm.read(CCM4) == (0xA57D if mode == foreign_mode else 0xA07D)

    compare_code = compare.assemble(diag)
    assert rom_bytes(vm, compare.ORIGIN, len(compare_code)) == b"\xff" * len(compare_code)
    vm.rom.update(enumerate(compare_code, compare.ORIGIN))
    deadline = 0x10000

    def arm(now):
        # Model caller presents coherent T4 snapshots and exclusive CC18 ownership.
        vm.r[7:11] = [2, 1, 1, 0x15]
        vm.r[12:16] = [now & 0xFFFF, now >> 16, deadline & 0xFFFF, deadline >> 16]
        vm.run(compare.ORIGIN)
        assert vm.r[4] == compare.EDGE
        vm.write(STATE, ARMED)

    for index, initial_mode in enumerate((compare.T8_FAST, compare.T8_SLOW)):
        seed(RELEASED, 0, 0)
        vm.write(T78CON, initial_mode | 0x004A)
        vm.write(compare.T4CON, 0x0046)
        vm.write(compare.T8REL, 0)
        vm.write(compare.T8, 0xFFF0)
        arm(deadline - 200)

        site, original = native_switches[index]
        pair = symbols[f"pair_{index}"]
        run_to(vm, site, pair)
        execute_native_pair(vm, pair)
        run_to(vm, pair + len(original), site + len(original))
        assert vm.read(STATE) == REBASE and vm.read(CC18IC) == 0
        accept_irq(vm, symbols["reti"], 0x09405C, 0x1805)  # No wakeup from a stale match.
        assert vm.read(STATE) == REBASE

        vm.write(compare.T8, 0xFFF0)
        arm(deadline - 150)
        ticks = 75 if initial_mode == compare.T8_FAST else 600
        assert vm.read(compare.CC18) == (0xFFF0 + ticks) & 0xFFFF
        vm.write(compare.T8, vm.read(compare.CC18))
        accept_irq(vm, symbols["reti"], 0x09405C, 0x1805)
        assert vm.read(STATE) == WAKEUP and vm.read(CC18IC) == 0

    return {
        "status": "PASS_OFFLINE_IRQ_LIFECYCLE_FIXTURE",
        "candidate_sha256": manifest["sha256"],
        "model_only_code_bytes": len(code),
        "mode_switch_vectors": switches_tested,
        "interrupt_vectors": len(states) * 3,
        "linked_mode_switch_sequences": 2,
        "tested_state_word": hex(STATE),
        "stack_reservation": probe_stack_reservation(diag, image),
        "absolute_edge_deadline_storage_resolved": False,
        "candidate_modified": False,
        "nested_interrupts_or_hardware_tested": False,
    }


def main():
    if not __debug__:
        raise RuntimeError("Enable Python assertions for the IRQ fixture")
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
