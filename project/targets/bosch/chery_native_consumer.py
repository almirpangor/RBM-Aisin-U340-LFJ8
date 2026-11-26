"""Emit a relocatable ST10 implementation of the S02 Chery request cycle.

This is machine code, rather than a Python runtime receiver.  R15 points to a
caller-owned, word-aligned context; R14 points to eight stable CAN data bytes.
Every context slot is a 16-bit word, including zero-extended native bytes.
The ordinary DPP mapping applies to both pointers.  All registers, PSW and
MDH/MDL are preserved.  Entry points return with RETS and require CALLS.

No donor RAM address is a target write address.  No RAM, CAN scheduler, clock,
or GW torque-unit binding is silently chosen by this component.  In particular
the published words retain S02 numerical units; they are not Nm or RB permille.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path


DONOR_SHA256 = "99dc271a861ab6d9e6749e8beb4637ab5c6c7e111f3ff0d9df4e147b2a0a6e1c"

# The field names retain their S02 provenance.  These are offsets in an ABI,
# never instructions to overwrite the similarly named GW logical addresses.
BYTE_FIELDS = (
    "b8166 b8168 b8169 b816a b816d b816e b8172 b8173 b8176 b8177 "
    "b8178 b8179 b817a b817b flags_8182 previous_8184 fault_8185 fault_8181 "
    "count_8cb8 recovery_8cba recovery_count_8cbb count_8ca2 recovery_8ca0 "
    "recovery_count_8ca1 good_8cb4 good_count_8cb5 bad_8cb6 bad_count_8cb7 "
    "latch_8ca4 flags_8183 published_8186 published_8187 latch_8ca6 "
    "latch_8ca8 pulse_8caa previous_8cab pulse_8cac previous_8cad "
    "pulse_8cae previous_8caf pulse_8cb0 previous_8cb1 latch_8cb2"
).split()
WORD_FIELDS = (
    "flags_fd82 flags_fd10 flags_fd12 flags_fd02 flags_fd74 w8c54 w8c5e w8c60 "
    "request_8c86 request_8c84 offset_98ca lower_9822 source_f7c4 "
    "published_8c96 published_8c90 source_98a4 source_8966 timer_8cbe "
    "timer_8cbc published_8c8a published_8c9e accumulator_low_8cc8 "
    "accumulator_high_8cca published_8c8e accumulator_low_8cc4 "
    "accumulator_high_8cc6 published_8c8c state_8cc2 state_8cc0 "
    "published_8c88 published_8c9c published_8c9a published_8c98 "
    "published_8c92 published_8c94"
).split()
FIELDS = tuple(BYTE_FIELDS + WORD_FIELDS)
LAYOUT = {name: index * 2 for index, name in enumerate(FIELDS)}
CONTEXT_BYTES = len(FIELDS) * 2
EXTERNAL_INPUTS = (
    "flags_fd02", "flags_fd74", "offset_98ca", "lower_9822",
    "source_98a4", "source_8966",
)
ENTRIES = ("decode", "defaults_invalid", "defaults_zero", "qualify", "tail", "cycle")


def word(value: int) -> bytes:
    return (value & 65535).to_bytes(2, "little")


@dataclass
class Component:
    origin: int
    code: bytes
    labels: dict[str, int]
    rows: list[tuple[int, bytes, str]]

    def manifest(self) -> dict:
        return {
            "kind": "ST10_CALLS_COMPONENT_REQUIRES_TARGET_ADAPTER",
            "sha256": hashlib.sha256(self.code).hexdigest(),
            "bytes": len(self.code), "origin": hex(self.origin),
            "entry_cpu": {name: hex(self.labels[name]) for name in ENTRIES},
            "abi": {"context_register": "R15", "raw_bytes_register": "R14",
                    "context_bytes": CONTEXT_BYTES, "slot_bytes": 2,
                    "layout": LAYOUT, "byte_slots_zero_extended": BYTE_FIELDS,
                    "external_inputs": list(EXTERNAL_INPUTS),
                    "preserves": "R0..R15, PSW, MDH, MDL, DPP0..3",
                    "return": "RETS; invoke with CALLS",
                    "max_system_stack_bytes_including_entry_return": 44},
            "semantics": {"donor_sha256": DONOR_SHA256,
                          "decode_cpu": "0x0A21F4",
                          "defaults_cpu": ["0x0A23A2", "0x0A240A"],
                          "request_cycle_cpu": "0x028CD0..0x02957A",
                          "operand": "trunc((raw-50)*32768/125), positive saturation32767",
                          "publication": "S02 encoded native words; upper tested before lower",
                          "calibration": "AA2AE, AA2D0, AA2EE and A81A2 from pinned S02"},
            "target_adapter_installed": False, "physical_units_bound": False,
            "hardware_tested": False,
            "required_target_adapter": [
                "Prove ownership of context RAM, stable eight-byte input and non-reentrancy",
                "Invoke after valid CAN header and chronology, before checksum filtering",
                "Supply six external inputs from coherent, proved native producers",
                "Bind S02 publications to GW consumers with a proved numerical conversion",
                "Define reset/default scheduling and invalidate authority on link expiry"],
        }


class Assembler:
    """Small ST10 encoder.  Every emitted opcode is exercised by the verifier."""

    def __init__(self, origin: int):
        if origin & 1 or not 0 <= origin <= 0xFFFFFF:
            raise ValueError("ST10 origin must be an aligned 24-bit address")
        self.origin = origin
        self.data = bytearray()
        self.labels = {}
        self.rows = []
        self.fixups = []
        self.serial = 0

    @property
    def pc(self):
        return self.origin + len(self.data)

    def label(self, name):
        if name in self.labels:
            raise ValueError(f"Duplicate label: {name}")
        self.labels[name] = self.pc

    def unique(self, stem):
        self.serial += 1
        return f"{stem}_{self.serial}"

    def emit(self, data, text):
        self.rows.append((self.pc, bytes(data), text))
        self.data.extend(data)

    def imm(self, reg, value):
        self.emit(bytes((0xE6, 0xF0 + reg)) + word(value), f"MOV R{reg},#{value & 65535:04X}")

    def rr(self, dest, source):
        self.emit(bytes((0xF0, 16 * dest + source)), f"MOV R{dest},R{source}")

    def alu(self, kind, dest, source):
        self.emit(bytes((16 * kind, 16 * dest + source)), f"ALU{kind} R{dest},R{source}")

    def ri(self, kind, reg, value):
        self.emit(bytes((16 * kind + 6, 0xF0 + reg)) + word(value),
                  f"ALU{kind} R{reg},#{value & 65535:04X}")

    def shift(self, reg, count, mode="right"):
        if not 0 <= count <= 15:
            raise ValueError("ST10 immediate shift range")
        self.emit(bytes(({"left": 0x5C, "right": 0x7C, "signed": 0xBC}[mode],
                         16 * count + reg)), f"SHIFT {mode} R{reg},#{count}")

    def load(self, reg, name):
        self.emit(bytes((0xD4, 16 * reg + 15)) + word(LAYOUT[name]), f"MOV R{reg},[R15+{name}]")

    def store(self, name, reg):
        self.emit(bytes((0xC4, 16 * reg + 15)) + word(LAYOUT[name]), f"MOV [R15+{name}],R{reg}")

    def raw_byte(self, reg, index):
        if reg > 7:
            raise ValueError("Byte temporary must be R0..R7")
        self.emit(bytes((0xF4, 32 * reg + 14)) + word(index), f"MOVB RL{reg},[R14+{index}]")
        self.emit(bytes((0xC0, 32 * reg + reg)), f"MOVBZ R{reg},RL{reg}")

    def set(self, name, value, reg=4):
        self.imm(reg, value)
        self.store(name, reg)

    def copy(self, dest, source, reg=4):
        self.load(reg, source)
        self.store(dest, reg)

    def branch(self, condition, label):
        self.fixups.append((len(self.data), label, False))
        self.emit(bytes((0xEA, 16 * condition, 0, 0)), f"JMPA cc{condition},{label}")

    def call(self, label):
        self.fixups.append((len(self.data), label, True))
        self.emit(bytes((0xDA, 0, 0, 0)), f"CALLS {label}")

    def ret(self):
        self.emit(b"\xDB\0", "RETS")

    def push(self, direct):
        self.emit(bytes((0xEC, direct)), f"PUSH direct{direct:02X}")

    def pop(self, direct):
        self.emit(bytes((0xFC, direct)), f"POP direct{direct:02X}")

    def enter(self, name):
        self.label(name)
        self.push(0x88)  # PSW before any MOV/arithmetic instruction.
        for reg in range(1, 14):
            self.push(0xF0 + reg)
        self.push(6)  # MDH FE0C
        self.push(7)  # MDL FE0E

    def leave(self):
        self.pop(7)
        self.pop(6)
        for reg in reversed(range(1, 14)):
            self.pop(0xF0 + reg)
        self.pop(0x88)
        self.ret()

    def mdu_read(self, reg, direct):
        self.emit(bytes((0xF2, 0xF0 + reg)) + word(direct), f"MOV R{reg},MD")

    def mdu_write(self, direct, reg):
        self.emit(bytes((0xF6, 0xF0 + reg)) + word(direct), f"MOV MD,R{reg}")

    def mul(self, first, second, signed=False):
        self.emit(bytes((0x0B if signed else 0x1B, 16 * first + second)), "MUL" if signed else "MULU")

    def divlu(self, reg):
        self.emit(bytes((0x7B, 17 * reg)), f"DIVLU R{reg}")

    def flag(self, name, mask, enabled_reg):
        """Set a mask from a boolean register without changing other flags."""
        done = self.unique("flag_done")
        self.load(12, name)
        self.ri(6, 12, ~mask)
        self.ri(4, enabled_reg, 0)
        self.branch(2, done)
        self.ri(7, 12, mask)
        self.label(done)
        self.store(name, 12)

    def boolean(self, reg, condition):
        # MOV preserves C/V, but changes N/Z, so branch BEFORE the MOV.
        yes, done = self.unique("yes"), self.unique("bool_done")
        self.branch(condition, yes)
        self.imm(reg, 0)
        self.branch(0, done)
        self.label(yes)
        self.imm(reg, 1)
        self.label(done)

    def finish(self):
        if self.pc > (self.origin & ~65535) + 65536:
            raise ValueError("Component must fit one 64KiB code segment")
        for offset, name, far in self.fixups:
            address = self.labels[name]
            if far:
                self.data[offset + 1] = address >> 16
            self.data[offset + 2:offset + 4] = word(address)
        return Component(self.origin, bytes(self.data), dict(self.labels), list(self.rows))


def emit_decode(a):
    a.enter("decode")
    # Preserve all native flags outside the exact assigned masks.
    a.raw_byte(4, 0)
    a.store("b8179", 4)
    a.rr(5, 4)
    a.ri(6, 5, 16)
    a.flag("flags_fd82", 8192, 5)
    a.ri(6, 4, 15)
    a.store("b816a", 4)
    a.raw_byte(4, 2)
    a.store("b8177", 4)
    for name, mask, source in (("flags_fd10", 8192, 1), ("flags_fd10", 64, 2),
                               ("flags_fd12", 1, 128)):
        a.rr(5, 4)
        a.ri(6, 5, source)
        a.flag(name, mask, 5)
    a.rr(5, 4)
    a.shift(5, 4)
    a.ri(6, 5, 7)
    a.store("b8166", 5)
    a.shift(4, 2)
    a.ri(6, 4, 3)
    first, second, done = (a.unique(n) for n in ("mode1", "mode2", "mode_done"))
    a.ri(4, 4, 1)
    a.branch(2, first)
    a.ri(4, 4, 2)
    a.branch(2, second)
    a.imm(5, 64)
    a.branch(0, done)
    a.label(first)
    a.imm(5, 128)
    a.branch(0, done)
    a.label(second)
    a.imm(5, 32)
    a.label(done)
    a.load(4, "flags_fd12")
    a.ri(6, 4, ~224)
    a.alu(7, 4, 5)
    a.store("flags_fd12", 4)
    for index, names in ((1, ("b817a", "b8173")), (4, ("b817b", "b8172")),
                         (3, ("b8178",)), (5, ("b8176",))):
        a.raw_byte(4, index)
        for name in names:
            a.store(name, 4)
    a.load(4, "b8178")
    a.rr(5, 4)
    a.shift(4, 4)
    a.store("b816e", 4)
    a.ri(6, 5, 15)
    a.store("b8169", 5)
    # Unknown gear nibbles deliberately retain prior gear and FD12.8.
    keep, gear, no_bit, end = (a.unique(n) for n in ("gear_keep", "gear", "gear_no_bit", "gear_done"))
    a.ri(4, 4, 1)
    a.branch(8, keep)
    a.ri(4, 4, 5)
    a.branch(15, gear)
    for code, result in ((9, 7), (15, 3), (10, 0)):
        nxt = a.unique("gear_next")
        a.ri(4, 4, code)
        a.branch(3, nxt)
        a.imm(4, result)
        a.branch(0, no_bit if code == 10 else gear)
        a.label(nxt)
    a.branch(0, keep)
    a.label(gear)
    a.store("b816d", 4)
    a.imm(5, 1)
    a.flag("flags_fd12", 256, 5)
    a.branch(0, end)
    a.label(no_bit)
    a.store("b816d", 4)
    a.imm(5, 0)
    a.flag("flags_fd12", 256, 5)
    a.branch(0, end)
    a.label(keep)
    a.label(end)
    a.load(4, "b8176")
    speed = a.unique("byte_speed")
    a.ri(4, 4, 255)
    a.branch(3, speed)
    a.imm(4, 0)
    a.label(speed)
    a.shift(4, 4, "left")
    a.store("w8c54", 4)
    a.raw_byte(4, 6)
    a.shift(4, 8, "left")
    a.raw_byte(5, 7)
    a.alu(7, 4, 5)
    a.store("w8c5e", 4)
    a.ri(4, 4, 65535)
    a.boolean(5, 2)
    a.flag("flags_fd10", 32, 5)
    valid, done = a.unique("speed_valid"), a.unique("speed_done")
    a.ri(4, 5, 0)
    a.branch(2, valid)
    a.imm(4, 0)
    a.branch(0, done)
    a.label(valid)
    a.imm(6, 0)
    a.mdu_write(0xFE0C, 6)
    a.mdu_write(0xFE0E, 4)
    a.imm(6, 25)
    a.divlu(6)
    a.mdu_read(4, 0xFE0E)
    a.shift(4, 5, "left")
    a.label(done)
    a.store("w8c60", 4)
    a.load(4, "b8169")
    a.shift(4, 4, "left")
    a.load(5, "b816a")
    a.alu(7, 4, 5)
    a.store("b8168", 4)
    a.leave()


def emit_defaults(a):
    for name, invalid in (("defaults_invalid", True), ("defaults_zero", False)):
        a.enter(name)
        a.load(4, "flags_fd82")
        a.ri(6, 4, ~8192)
        a.store("flags_fd82", 4)
        a.load(4, "flags_fd10")
        a.ri(6, 4, ~(8192 | 64 | 32))
        if invalid:
            a.ri(7, 4, 32)
        a.store("flags_fd10", 4)
        a.load(4, "flags_fd12")
        a.ri(6, 4, ~161)
        a.ri(7, 4, 320)
        a.store("flags_fd12", 4)
        for field, value in {
            "b8173": 255, "b8172": 255, "b8176": 255, "b816e": 15,
            "w8c5e": 65535 if invalid else 0, "b816a": 1, "b8169": 0,
            "b8168": 1, "b816d": 3, "b8166": 0, "w8c60": 0,
            "w8c54": 0, "b8179": 1, "b817a": 255, "b8177": 0,
            "b8178": 240, "b817b": 255,
        }.items():
            a.set(field, value)
        a.leave()


def qualify_counter(a, output, count, enabled, threshold):
    disabled, asserted, done = (a.unique(n) for n in ("q_disabled", "q_asserted", "q_done"))
    a.ri(4, enabled, 0)
    a.branch(2, disabled)
    if threshold:
        a.load(4, count)
        a.ri(4, 4, threshold)
        a.branch(9, asserted)
        a.ri(0, 4, 1)
        a.store(count, 4)
        a.branch(0, done)
    a.label(asserted)
    a.set(output, 1)
    a.branch(0, done)
    a.label(disabled)
    a.set(output, 0)
    a.set(count, 0)
    a.label(done)


def qualify_fault(a, bad_reg, count, recovery, recovery_count, fault, mask, threshold):
    good, counted, keep = (a.unique(n) for n in ("fault_good", "fault_counted", "fault_keep"))
    a.ri(4, bad_reg, 0)
    a.branch(2, good)
    a.load(4, count)
    a.ri(4, 4, 3)
    cap = a.unique("fault_cap")
    a.branch(9, cap)
    a.ri(0, 4, 1)
    a.branch(0, counted)
    a.label(cap)
    a.imm(4, 3)
    a.label(counted)
    a.store(count, 4)
    a.label(good)
    a.ri(4, bad_reg, 0)
    a.boolean(9, 2)
    qualify_counter(a, recovery, recovery_count, 9, threshold)
    a.load(4, recovery)
    a.ri(4, 4, 0)
    a.branch(2, keep)
    a.set(count, 0)
    a.label(keep)
    a.copy(fault, count)
    a.load(4, count)
    zero, done = a.unique("fault_zero"), a.unique("fault_done")
    a.ri(4, 4, 0)
    a.branch(2, zero)
    a.ri(4, 4, 3)
    a.branch(3, done)
    a.load(4, "flags_8182")
    a.ri(7, 4, mask)
    a.store("flags_8182", 4)
    a.branch(0, done)
    a.label(zero)
    a.load(4, "flags_8182")
    a.ri(6, 4, ~mask)
    a.store("flags_8182", 4)
    a.label(done)


def emit_qualify(a):
    a.enter("qualify")
    a.load(4, "b8172")
    a.load(5, "b8173")
    a.alu(0, 4, 5)
    a.ri(6, 4, 255)
    a.imm(5, 255)
    a.alu(2, 5, 4)
    a.load(4, "b8168")
    a.alu(4, 4, 5)
    a.boolean(8, 3)
    a.flag("flags_8182", 1, 8)
    qualify_fault(a, 8, "count_8cb8", "recovery_8cba", "recovery_count_8cbb", "fault_8185", 128, 3)
    a.load(4, "flags_fd10")
    a.ri(6, 4, 8192)
    inactive, seq_done = a.unique("seq_inactive"), a.unique("seq_done")
    a.ri(4, 4, 0)
    a.branch(2, inactive)
    a.load(4, "b8166")
    a.ri(0, 4, 8)
    a.load(5, "previous_8184")
    a.alu(2, 4, 5)
    a.ri(6, 4, 7)
    bad = a.unique("seq_bad")
    a.ri(4, 4, 0)
    a.branch(2, bad)
    a.ri(4, 4, 3)
    a.boolean(8, 9)
    a.branch(0, seq_done)
    a.label(bad)
    a.imm(8, 1)
    a.branch(0, seq_done)
    a.label(inactive)
    a.imm(8, 0)
    a.set("previous_8184", 0)
    a.label(seq_done)
    a.flag("flags_8182", 2, 8)
    qualify_fault(a, 8, "count_8ca2", "recovery_8ca0", "recovery_count_8ca1", "fault_8181", 64, 0)
    a.copy("previous_8184", "b8166")
    a.load(4, "flags_8182")
    a.ri(6, 4, 3)
    a.ri(4, 4, 0)
    a.boolean(8, 3)
    a.ri(4, 8, 0)
    a.boolean(9, 2)
    qualify_counter(a, "good_8cb4", "good_count_8cb5", 9, 3)
    qualify_counter(a, "bad_8cb6", "bad_count_8cb7", 8, 3)
    bad, done = a.unique("latch_bad"), a.unique("latch_done")
    a.load(4, "good_8cb4")
    a.ri(4, 4, 0)
    a.branch(2, bad)
    a.set("latch_8ca4", 0)
    a.branch(0, done)
    a.label(bad)
    a.load(4, "bad_8cb6")
    a.ri(4, 4, 0)
    a.branch(2, done)
    a.set("latch_8ca4", 255)
    a.label(done)
    a.load(5, "latch_8ca4")
    a.flag("flags_8182", 32, 5)
    keep = a.unique("requests_held")
    a.ri(4, 8, 0)
    a.branch(3, keep)
    for raw, request in (("b8173", "request_8c86"), ("b8172", "request_8c84")):
        a.load(4, raw)
        a.call("operand")
        a.store(request, 4)
    a.label(keep)
    a.load(4, "flags_8182")
    a.ri(6, 4, 224)
    a.load(5, "flags_fd74")
    a.ri(6, 5, 8192)
    a.alu(7, 4, 5)
    a.ri(4, 4, 0)
    a.boolean(8, 3)
    for raw, request, output, mask in (
        ("b8173", "request_8c86", "published_8c96", 8),
        ("b8172", "request_8c84", "published_8c90", 16),
    ):
        a.load(4, raw)
        a.ri(4, 4, 255)
        a.boolean(5, 2)
        a.alu(7, 5, 8)
        a.flag("flags_8182", mask, 5)
        a.load(4, request)
        a.load(6, "offset_98ca")
        a.load(7, "lower_9822")
        a.call("publication")
        a.store(output, 4)
    a.leave()


def emit_numeric_helpers(a):
    # R4 raw -> R4 signed16 native request; clobbers R5/R6 and MD.
    a.label("operand")
    negative, calc, negate, done = (a.unique(n) for n in ("operand_negative", "operand_calc", "operand_negate", "operand_done"))
    a.ri(4, 4, 50)
    a.branch(8, negative)
    a.ri(4, 4, 175)
    a.branch(8, calc)
    a.imm(4, 32767)
    a.ret()
    a.label(calc)
    a.ri(2, 4, 50)
    a.imm(5, 0)
    a.branch(0, negate)
    a.label(negative)
    a.imm(6, 50)
    a.alu(2, 6, 4)
    a.rr(4, 6)
    a.imm(5, 1)
    a.label(negate)
    a.imm(6, 32768)
    a.mul(4, 6)
    a.imm(6, 125)
    a.divlu(6)
    a.mdu_read(4, 0xFE0E)
    a.ri(4, 5, 0)
    a.branch(2, done)
    a.imm(6, 0)
    a.alu(2, 6, 4)
    a.rr(4, 6)
    a.label(done)
    a.ret()
    # R4 signed request, R5 fallback, R6 offset, R7 lower -> R4.
    a.label("publication")
    fallback, lower, upper, zero, add, done = (a.unique(n) for n in ("pub_fallback", "pub_lower", "pub_upper", "pub_zero", "pub_add", "pub_done"))
    a.ri(4, 5, 0)
    a.branch(3, fallback)
    a.rr(9, 4)
    a.shift(9, 15, "signed")
    a.alu(0, 4, 4)
    a.alu(1, 9, 9)
    a.branch(0, add)
    a.label(fallback)
    a.imm(4, 65025)
    a.imm(9, 0)
    a.label(add)
    a.alu(0, 4, 6)
    a.imm(5, 0)
    a.alu(1, 9, 5)
    a.ri(4, 9, 0)
    a.branch(12, zero)  # signed high <0
    a.branch(3, upper)  # positive high >0
    a.ri(4, 4, 65024)
    a.branch(14, upper)
    a.branch(0, lower)
    a.label(zero)
    a.imm(4, 0)
    a.label(lower)
    a.alu(4, 4, 7)
    a.branch(9, done)
    a.rr(4, 7)
    a.branch(0, done)
    a.label(upper)
    a.imm(4, 65024)
    a.label(done)
    a.ret()
    # R4 signed delta, R10 low/R11 high -> clamped signed32 accumulator.
    a.label("accumulate")
    a.imm(5, 1311)
    a.mul(4, 5, signed=True)
    a.mdu_read(6, 0xFE0E)
    a.mdu_read(7, 0xFE0C)
    a.alu(0, 10, 6)
    a.alu(1, 11, 7)
    overflow, zero, upper, done = (a.unique(n) for n in ("acc_overflow", "acc_zero", "acc_upper", "acc_done"))
    a.branch(4, overflow)
    a.ri(4, 11, 32768)
    a.branch(9, zero)
    a.ri(4, 11, 32766)
    a.branch(8, done)
    a.branch(14, upper)
    a.ri(4, 10, 0)
    a.branch(2, done)
    a.branch(0, upper)
    a.label(overflow)
    a.ri(4, 7, 32768)
    a.branch(9, zero)
    a.label(upper)
    a.imm(10, 0)
    a.imm(11, 32766)
    a.branch(0, done)
    a.label(zero)
    a.imm(10, 0)
    a.imm(11, 0)
    a.label(done)
    a.ret()
    # Exact two-stage interpolation of AA2D0, not a combined fraction.
    a.label("threshold")
    for boundary, axis, ordinate, delta, width in (
        (1280, 0, 1311, 0, 1280),
        (5120, 1280, 1311, 1966, 3840),
        (7680, 5120, 3277, 4587, 2560),
        (10240, 7680, 7864, 1966, 2560),
    ):
        nxt = a.unique("threshold_next")
        a.ri(4, 4, boundary)
        a.branch(9, nxt)
        if delta:
            a.ri(2, 4, axis)
            a.imm(5, 256)
            a.mul(4, 5)
            a.imm(5, width)
            a.divlu(5)
            a.mdu_read(4, 0xFE0E)
            a.imm(5, delta)
            a.mul(4, 5)
            a.mdu_read(4, 0xFE0E)
            a.mdu_read(5, 0xFE0C)
            a.shift(4, 8)
            a.shift(5, 8, "left")
            a.alu(7, 4, 5)
            a.ri(0, 4, ordinate)
        else:
            a.imm(4, ordinate)
        a.ret()
        a.label(nxt)
    a.imm(4, 9830)
    a.ret()


def floor_quarter_difference(a, first, second, negate=False):
    if negate:
        a.imm(4, 0)
    else:
        a.load(4, first)
    a.load(5, second)
    a.alu(2, 4, 5)
    a.imm(5, 0)  # MOV keeps subtraction carry.
    a.alu(3, 5, 5)
    a.shift(4, 2)
    a.shift(5, 14, "left")
    a.alu(7, 4, 5)


def emit_tail(a):
    a.enter("tail")
    a.load(4, "flags_fd10")
    a.ri(6, 4, 8192)
    a.ri(4, 4, 0)
    a.boolean(8, 3)  # active retained across helpers.
    # Timer for inactive duration, with both edge memories in OEM order.
    a.load(4, "previous_8cad")
    a.ri(4, 4, 0)
    a.boolean(5, 3)
    a.alu(4, 5, 8)
    a.boolean(5, 2)
    a.store("pulse_8cac", 5)
    a.imm(4, 1)
    a.alu(2, 4, 8)
    a.store("previous_8cad", 4)
    keep = a.unique("timer_inactive_keep")
    a.ri(4, 5, 0)
    a.branch(2, keep)
    a.set("timer_8cbe", 0)
    a.label(keep)
    active = a.unique("timer_inactive_done")
    a.ri(4, 8, 0)
    a.branch(3, active)
    increment_word(a, "timer_8cbe", 1, 65535)
    a.label(active)
    a.copy("published_8c8a", "timer_8cbe")
    a.load(4, "previous_8caf")
    a.ri(4, 4, 0)
    a.boolean(5, 3)
    a.imm(4, 1)
    a.alu(2, 4, 8)
    a.alu(6, 5, 4)
    a.store("pulse_8cae", 5)
    a.store("previous_8caf", 8)
    keep = a.unique("timer_active_keep")
    a.ri(4, 5, 0)
    a.branch(2, keep)
    a.set("timer_8cbc", 0)
    a.label(keep)
    inactive = a.unique("timer_active_done")
    a.ri(4, 8, 0)
    a.branch(2, inactive)
    increment_word(a, "timer_8cbc", 1, 65535)
    a.label(inactive)
    a.copy("published_8c9e", "timer_8cbc")
    active_timer, latch_done = a.unique("latch_timer_active"), a.unique("latch_timer_done")
    a.load(4, "published_8c8a")
    a.ri(4, 4, 100)
    a.branch(8, active_timer)
    a.set("latch_8ca6", 0)
    a.branch(0, latch_done)
    a.label(active_timer)
    a.load(4, "published_8c9e")
    a.ri(4, 4, 250)
    a.branch(8, latch_done)
    a.set("latch_8ca6", 255)
    a.label(latch_done)
    a.load(5, "latch_8ca6")
    a.flag("flags_8183", 4, 5)
    use_offset, delta_done = a.unique("integrator_offset"), a.unique("integrator_delta")
    a.ri(4, 8, 0)
    a.branch(2, use_offset)
    floor_quarter_difference(a, "published_8c96", "source_98a4")
    a.branch(0, delta_done)
    a.label(use_offset)
    floor_quarter_difference(a, None, "offset_98ca", negate=True)
    a.label(delta_done)
    accumulate_context(a, "8cc8", "8cca", "published_8c8e")
    nonzero, latch_done = a.unique("acc_nonzero"), a.unique("acc_latch_done")
    a.ri(4, 11, 0)
    a.branch(3, nonzero)
    a.set("latch_8cb2", 0)
    a.branch(0, latch_done)
    a.label(nonzero)
    a.ri(4, 11, 17695)
    a.branch(12, latch_done)
    a.set("latch_8cb2", 255)
    a.label(latch_done)
    a.load(5, "latch_8cb2")
    a.flag("flags_8183", 1, 5)
    a.load(4, "previous_8cb1")
    a.ri(4, 4, 0)
    a.boolean(5, 2)
    a.alu(6, 5, 8)
    a.store("pulse_8cb0", 5)
    a.store("previous_8cb1", 8)
    a.load(4, "previous_8cab")
    a.ri(4, 4, 0)
    a.boolean(5, 3)
    a.imm(4, 1)
    a.alu(2, 4, 8)
    a.alu(6, 5, 4)
    a.store("pulse_8caa", 5)
    a.store("previous_8cab", 8)
    keep = a.unique("acc_active_keep")
    a.ri(4, 5, 0)
    a.branch(2, keep)
    a.set("accumulator_high_8cc6", 0)
    a.set("accumulator_low_8cc4", 0)
    a.label(keep)
    inactive = a.unique("acc_active_done")
    a.ri(4, 8, 0)
    a.branch(2, inactive)
    floor_quarter_difference(a, "published_8c90", "source_98a4")
    accumulate_context(a, "8cc4", "8cc6", "published_8c8c")
    a.label(inactive)
    a.copy("published_8c8c", "accumulator_high_8cc6")
    no_edge, latch_done = a.unique("threshold_no_edge"), a.unique("threshold_latch_done")
    a.load(4, "pulse_8cb0")
    a.ri(4, 4, 0)
    a.branch(2, no_edge)
    a.set("latch_8ca8", 0)
    a.branch(0, latch_done)
    a.label(no_edge)
    a.load(4, "source_8966")
    a.call("threshold")
    a.load(5, "published_8c8c")
    a.alu(4, 4, 5)
    a.branch(13, latch_done)  # signed threshold >= signed publication
    a.set("latch_8ca8", 255)
    a.label(latch_done)
    a.load(5, "latch_8ca8")
    a.flag("flags_8183", 2, 5)
    a.set("published_8c88", 65529)
    a.load(10, "source_98a4")
    a.ri(0, 10, 65529)
    upper_ok = a.unique("tail_upper_ok")
    a.branch(9, upper_ok)
    a.imm(10, 65535)
    a.label(upper_ok)
    # Inhibit before FD74.12 is separately published as FD12.11.
    a.load(4, "flags_8183")
    a.ri(6, 4, 7)
    a.imm(5, 1)
    a.alu(2, 5, 8)
    a.alu(7, 4, 5)
    a.load(5, "flags_fd02")
    a.ri(6, 5, 8192)
    a.ri(4, 5, 0)
    a.boolean(5, 2)
    a.alu(7, 4, 5)
    a.load(5, "flags_8182")
    a.ri(6, 5, 24)
    a.alu(7, 4, 5)
    a.ri(4, 4, 0)
    a.boolean(9, 3)
    a.flag("flags_fd12", 2048, 9)
    a.load(4, "flags_fd74")
    a.ri(6, 4, 4096)
    a.alu(7, 9, 4)
    # Keep command in R11; helpers used below do not touch R9..R11.
    no_command, command_done = a.unique("tail_no_command"), a.unique("tail_command_done")
    a.ri(4, 9, 0)
    a.branch(3, no_command)
    a.rr(11, 10)
    minimum_context(a, 11, "published_8c90")
    minimum_context(a, 11, "published_8c96")
    a.branch(0, command_done)
    a.label(no_command)
    a.imm(11, 0)
    a.label(command_done)
    grow, state_done = a.unique("tail_state_grow"), a.unique("tail_state_done")
    a.ri(4, 8, 0)
    a.branch(2, grow)
    a.load(4, "flags_fd02")
    a.ri(6, 4, 8192)
    a.ri(4, 4, 0)
    a.branch(2, grow)
    a.load(4, "flags_8183")
    a.ri(6, 4, 4)
    a.ri(4, 4, 0)
    a.branch(3, grow)
    a.copy("state_8cc2", "published_8c96")
    a.copy("state_8cc0", "published_8c90")
    a.branch(0, state_done)
    a.label(grow)
    increment_word(a, "state_8cc2", 13107, 65024)
    increment_word(a, "state_8cc0", 13107, 65024)
    a.label(state_done)
    a.rr(4, 11)
    a.shift(4, 8)
    a.store("published_8186", 4)
    a.imm(5, 255)
    a.alu(2, 5, 4)
    a.store("published_8187", 5)
    a.store("published_8c9c", 11)
    a.ri(4, 9, 0)
    publish_zero, done = a.unique("tail_9a_zero"), a.unique("tail_9a_done")
    a.branch(3, publish_zero)
    a.rr(4, 10)
    minimum_context(a, 4, "published_8c90", temp=5)
    a.branch(0, done)
    a.label(publish_zero)
    a.imm(4, 0)
    a.label(done)
    a.store("published_8c9a", 4)
    a.copy("published_8c98", "state_8cc2")
    a.copy("published_8c94", "state_8cc0")
    standard, done = a.unique("tail_92_standard"), a.unique("tail_92_done")
    a.load(4, "flags_fd02")
    a.ri(6, 4, 8192)
    a.ri(4, 4, 0)
    a.branch(2, standard)
    a.ri(4, 8, 0)
    a.branch(3, standard)
    a.load(4, "published_8c90")
    a.branch(0, done)
    a.label(standard)
    a.imm(4, 65024)
    a.label(done)
    a.store("published_8c92", 4)
    a.leave()


def increment_word(a, field, increment, upper):
    cap, done = a.unique("inc_cap"), a.unique("inc_done")
    a.load(4, field)
    a.ri(0, 4, increment)
    a.branch(8, cap)
    a.ri(4, 4, upper)
    a.branch(15, done)
    a.label(cap)
    a.imm(4, upper)
    a.label(done)
    a.store(field, 4)


def minimum_context(a, dest, field, temp=4):
    if dest == temp:
        raise ValueError("Minimum temporary aliases destination")
    done = a.unique("minimum_done")
    a.load(temp, field)
    a.alu(4, dest, temp)
    a.branch(15, done)
    a.rr(dest, temp)
    a.label(done)


def accumulate_context(a, low, high, publication):
    a.load(10, "accumulator_low_" + low)
    a.load(11, "accumulator_high_" + high)
    a.call("accumulate")
    a.store("accumulator_low_" + low, 10)
    a.store("accumulator_high_" + high, 11)
    a.store(publication, 11)


def assemble(origin=0x068000):
    a = Assembler(origin)
    emit_decode(a)
    emit_defaults(a)
    emit_qualify(a)
    emit_tail(a)
    a.label("cycle")
    for name in ("decode", "qualify", "tail"):
        a.call(name)
    a.ret()
    emit_numeric_helpers(a)
    return a.finish()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", type=lambda value: int(value, 0), default=0x068000)
    parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args()
    part = assemble(args.origin)
    args.outdir.mkdir(parents=True, exist_ok=False)
    (args.outdir / "CHERY_NATIVE_CONSUMER_ST10_COMPONENT.bin").write_bytes(part.code)
    (args.outdir / "manifest.json").write_text(json.dumps(part.manifest(), indent=2) + "\n", encoding="utf-8")
    # Resolve the listing from final code; row bytes before branch fixups are
    # deliberately not used as executable-byte provenance.
    lines = [f"{pc:06X} {part.code[pc-part.origin:pc-part.origin+len(raw)].hex():8} {text}"
             for pc, raw, text in part.rows]
    (args.outdir / "component.asm").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(part.manifest(), indent=2))


if __name__ == "__main__":
    main()
