"""Diagnostic Chery engine-signal transmitter assembled for the pinned E4M3."""

from dataclasses import dataclass

ORIGIN, LIMIT = 0x66800, 0x67000
RPM_LAST, COOLANT_LAST, DEFER = 0xE7F6, 0xE7F8, 0xE7FA
PREFER_COOLANT = 0xE7FC


@dataclass(frozen=True)
class Signal:
    label: str
    identifier: int
    object_number: int
    init_stage: int
    last_tick: int
    period: int


RPM = Signal("rpm", 0x0FA, 14, 40, RPM_LAST, 625)
COOLANT = Signal("coolant", 0x278, 15, 41, COOLANT_LAST, 1250)


def encode_model_delta(a, source, name):
    # S02 0A18F8 and 0A1956, calibration bytes 25/40. Compute the high
    # word of abs(source-base)*125 without changing the MCU's MD registers.
    a.rr(4, source)
    a.sub(4, 12)
    a.branch(9, name + "_magnitude")
    a.imm(4, 0)
    a.sub(4, source)
    a.add(4, 12)
    a.label(name + "_magnitude")
    a.rr(5, 4)
    a.andi(4, 255)
    a.shift(5, 8)
    for reg in (4, 5):
        a.rr(6, reg)
        a.shift(reg, 7, left=True)
        a.sub(reg, 6)
        a.sub(reg, 6)
        a.sub(reg, 6)
    a.shift(4, 8)
    a.add(4, 5)
    a.shift(4, 8)
    a.cmpreg(source, 12)
    a.branch(8, name + "_negative")
    a.addi(4, 50)
    a.branch(0, name + "_done")
    a.label(name + "_negative")
    a.imm(6, 50)
    a.sub(6, 4)
    a.rr(4, 6)
    a.branch(9, name + "_done")  # MOV preserves the subtraction carry.
    a.imm(4, 0)
    a.label(name + "_done")


def pack_model_fields(a):
    # Physical addresses on the selected GW image. R9 is the TX clock.
    words = ((10, 0xF16FC), (11, 0xF165A), (12, 0xF1680))
    flags = ((13, 0xF325A), (14, 0xF32B0))
    for reg, address in flags + words:
        a.physical(reg, address)
    a.rr(4, 13)
    a.andi(4, 1)
    a.cmp(4, 0)
    a.branch(2, "model_encode")
    a.rr(4, 14)
    a.andi(4, 1)
    a.cmp(4, 0)
    a.branch(3, "model_invalid")
    a.label("model_encode")
    encode_model_delta(a, 10, "model_now")
    a.rr(15, 4)
    encode_model_delta(a, 11, "model_limit")
    a.shift(4, 8, left=True)
    a.rr(7, 4)
    # A changing input during the calculation invalidates the pair together.
    for reg, address in words + flags:
        a.physical(4, address)
        a.cmpreg(4, reg)
        a.branch(3, "model_invalid")
    a.ori(15, 0xFF00)  # The independently produced byte 3 is unavailable.
    a.st(0xEF20, 15)
    a.st(0xEF22, 7)
    a.branch(0, "model_packed")
    a.label("model_invalid")
    a.set(0xEF20, 0xFFFF)
    a.set(0xEF22, 0xFF00)
    a.label("model_packed")


def pack_ordinary_model_field(a):
    # Explicit application profile with no cruise contribution and no override.
    # 8FAC is homologous to S02 91C2. B286/B288 are the corresponding events.
    # 98E6 and FD7C.4 are the request and auxiliary state consumed together
    # at GW 05A078..05A0CE. 8FAE < FFFF guarantees that the corresponding
    # S02 91C4 input clears its mode latch in the 0C1ED4 task.
    inputs = ((10, 0xF0FAC), (11, 0xF3286), (12, 0xF3288),
              (13, 0xF18E6), (14, 0xFD7C), (15, 0xF0FAE))
    a.ld(4, 0xEF1E)
    a.cmp(4, 0xFFFF)
    a.branch(2, "ordinary_model_done")
    for reg, address in inputs:
        a.physical(reg, address)
    a.cmp(13, 0)
    a.branch(3, "ordinary_model_done")
    a.rr(4, 14)
    a.andi(4, 0x10)
    a.branch(3, "ordinary_model_done")
    a.cmp(15, 0xFFFF)
    a.branch(2, "ordinary_model_done")
    a.rr(4, 11)
    a.andi(4, 1)
    a.branch(2, "ordinary_model_encode")
    a.rr(4, 12)
    a.andi(4, 1)
    a.branch(3, "ordinary_model_done")
    a.label("ordinary_model_encode")

    # For x = 256*hi + lo, floor(x/257) is hi minus one if lo < hi.
    # The ordinary Chery branch caps the code at 253.
    a.rr(7, 10)
    a.shift(7, 8)
    a.rr(4, 10)
    a.andi(4, 255)
    a.cmpreg(4, 7)
    a.branch(9, "ordinary_model_cap")
    a.subi(7, 1)
    a.label("ordinary_model_cap")
    a.cmp(7, 253)
    a.branch(15, "ordinary_model_recheck")
    a.imm(7, 253)
    a.label("ordinary_model_recheck")
    for reg, address in inputs:
        a.physical(4, address)
        a.cmpreg(4, reg)
        a.branch(3, "ordinary_model_done")
    a.shift(7, 8, left=True)
    a.ld(4, 0xEF20)
    a.andi(4, 255)
    a.either(4, 7)
    a.st(0xEF20, 4)
    a.label("ordinary_model_done")


def assemble(diag, torque, *, model_fields=False, ordinary_model_field=False):
    a = diag.Asm(ORIGIN, LIMIT)

    a.label("configure")
    a.ld(4, diag.STATE)
    for signal in (RPM, COOLANT):
        a.cmp(4, signal.init_stage)
        a.branch(2, f"configure_{signal.label}")
    a.imm(4, 1)
    a.raw("db00", "RETS")
    for signal in (RPM, COOLANT):
        a.label(f"configure_{signal.label}")
        a.imm(6, signal.object_number)
        a.imm(7, 0xA000 | (signal.identifier << 2))
        a.imm(8, signal.init_stage + 1)
        a.branch(0, "configure_object")
    a.label("configure_object")
    for address in (0xEF14, 0xEF16, 0xEF18, 0xEF1E, 0xEF20, 0xEF22, 0xEF24):
        a.zero(address)
    a.st(0xEF1A, 7)
    a.set(0xEF1C, 0x88)
    a.set(0xEF12, 0xF3)
    a.st(0xEF10, 6)
    a.st(diag.STATE, 8)
    a.branch(0, "free")

    a.label("tick")
    a.ld(4, DEFER)
    a.cmp(4, 0)
    a.branch(2, "check_owner")
    a.zero(DEFER)
    a.branch(0, "free")
    a.label("check_owner")
    for address, mask in (
        (diag.DIAG_PHASE, 0xF),
        (torque.PHASE, 0xFFFF),
        (torque.BUSY_COUNT, 0xFFFF),
        (0xEF10, 0x8000),
    ):
        a.ld(4, address)
        a.andi(4, mask)
        a.cmp(4, 0)
        a.branch(3, "free")
    a.ld(4, 0xFF44)
    a.andi(4, 0x1FF)
    a.cmp(4, 0x46)
    a.branch(3, "free")
    a.ld(9, 0xFE44)
    a.ld(4, PREFER_COOLANT)
    a.cmp(4, 0)
    a.branch(3, "coolant_first")
    # Both frames share the same IF1. If both are due, alternate precedence.
    for choice, order in (("rpm_first", (RPM, COOLANT)), ("coolant_first", (COOLANT, RPM))):
        a.label(choice)
        for signal in order:
            defer = f"defer_{choice}_{signal.label}"
            a.ld(4, signal.last_tick)
            a.rr(5, 9)
            a.sub(5, 4)
            a.cmp(5, signal.period)
            a.branch(8, defer)
            a.ld(4, 0xEF80)
            a.andi(4, 1 << (signal.object_number - 1))
            a.cmp(4, 0)
            a.branch(2, f"pack_{signal.label}")
            a.label(defer)
        a.branch(0, "free")

    a.label("pack_rpm")
    a.ld(4, 0xFD18)
    a.andi(4, 0x0040)
    a.cmp(4, 0)
    a.branch(2, "rpm_invalid")
    a.ld(4, 0xFD1A)
    a.andi(4, 0x4000)
    a.cmp(4, 0)
    a.branch(3, "rpm_invalid")
    a.physical(4, 0xF7C4)
    a.cmp(4, 0)
    a.branch(2, "rpm_invalid")
    a.cmp(4, 40000)
    a.branch(14, "rpm_invalid")
    a.swap(4)
    a.branch(0, "rpm_write")
    a.label("rpm_invalid")
    a.imm(4, 0xFFFF)
    a.label("rpm_write")
    a.st(0xEF1E, 4)
    if model_fields:
        pack_model_fields(a)
        if ordinary_model_field:
            a.label("ordinary_model_field")
            pack_ordinary_model_field(a)
    else:
        a.set(0xEF20, 0xFFFF)
        a.set(0xEF22, 0xFF00)
    a.zero(0xEF24)
    a.st(RPM.last_tick, 9)
    a.set(PREFER_COOLANT, 1)
    a.imm(6, RPM.object_number)
    a.branch(0, "send")

    a.label("pack_coolant")
    a.physical(4, 0xF32F4)
    a.andi(4, 1)
    a.cmp(4, 0)
    a.branch(3, "coolant_invalid")
    a.physical(8, 0xF0382, True)
    a.physical(4, 0xF32F4)
    a.andi(4, 1)
    a.cmp(4, 0)
    a.branch(3, "coolant_invalid")
    a.physical(4, 0xF0382, True)
    a.cmpreg(4, 8)
    a.branch(3, "coolant_invalid")
    a.branch(0, "coolant_write")
    a.label("coolant_invalid")
    a.imm(4, 255)
    a.label("coolant_write")
    a.ori(4, 0xFF00)
    a.st(0xEF1E, 4)
    for address in (0xEF20, 0xEF22, 0xEF24):
        a.set(address, 0xFFFF)
    a.st(COOLANT.last_tick, 9)
    a.zero(PREFER_COOLANT)
    a.imm(6, COOLANT.object_number)

    a.label("send")
    a.set(0xEF1C, 0x8088)
    a.set(0xEF12, 0x97)
    a.st(0xEF10, 6)
    a.set(DEFER, 1)
    a.imm(4, 1)
    a.raw("db00", "RETS")
    a.label("free")
    a.imm(4, 0)
    a.raw("db00", "RETS")
    return a, a.finish()
