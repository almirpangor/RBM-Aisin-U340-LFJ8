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


def assemble(diag, torque):
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
