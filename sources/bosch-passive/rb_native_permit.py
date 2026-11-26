"""Attach E4M3 RPM qualification to the shared native RB request gate."""

from tx import LIMIT, require_native_rpm

# Tail of the same checked FF window as the Chery transmitter. The builder
# verifies S04 bytes, section bounds and disjointness with the actual TX code.
ORIGIN = 0x66F00
GATE_FIRST = bytes.fromhex("f2f454ef")  # MOV R4,[EF54], the RB signature word.
JMPA_UNCONDITIONAL = bytes.fromhex("ea00")


def assemble(diag, torque):
    gate = torque.labels["gate"]
    denied = torque.labels["gate_bad"]
    resume = gate + len(GATE_FIRST)
    offset = gate - torque.origin
    if torque.data[offset:offset + len(GATE_FIRST)] != GATE_FIRST:
        raise ValueError("Unexpected first instruction of the pinned RB gate")
    if len({address >> 16 for address in (ORIGIN, gate, denied, resume)}) != 1:
        raise ValueError("RB gate detour must keep the near CALLA/RET segment")

    guard = diag.Asm(ORIGIN, LIMIT)
    guard.label("entry")
    require_native_rpm(guard, "reject")
    # Clobber only the original gate's R4. Both branches tail-jump so the
    # original near return frame and the caller's clock registers survive.
    guard.emit(GATE_FIRST, "MOV R4,[EF54] (displaced RB gate instruction)")
    guard.emit(JMPA_UNCONDITIONAL + diag.word(resume), "JMPA original RB gate continuation")
    guard.label("reject")
    guard.emit(JMPA_UNCONDITIONAL + diag.word(denied), "JMPA original RB gate reject")
    return gate, JMPA_UNCONDITIONAL + diag.word(ORIGIN), guard, guard.finish()
