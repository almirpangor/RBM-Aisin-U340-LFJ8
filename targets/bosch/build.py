#!/usr/bin/env python3
"""Emit an offline-only ST10 E4M3 candidate from an exact stock project image."""
import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

S04_SHA = "e25a1c97492ae556b1a52043e6ae85b88d2da86c03a78ef01dc2151c8a0a4a2a"
CAN_ID, OBJECT = 0x1AE, 13
SPEED = 0x18FC  # EXTP 0x3C: physical 0xF18FC, native logical 0x98FC
AGE, PHASE, DEFER, BUSY = 0xE7EE, 0xE7F0, 0xE7F2, 0xE7F4
STALE_CALLS = 32  # Candidate lease in service invocations; measure time on Bosch.
RAW_LIMIT = 51200  # Original S02 Q7 calculation wraps a 16-bit word here.
SPEED_ORIGIN, SPEED_LIMIT = 0x66000, 0x66800
CALIBRATION = 0xB8441
OUTPUT = "E4M3_CHERY_SPEED_OFFLINE_ONLY.bin"
TX_OUTPUT = "E4M3_CHERY_RPM_ECT_SPEED_OFFLINE_ONLY.bin"
INIT_SPEED = 39


def digest(data):
    return hashlib.sha256(data).hexdigest()


def assemble_speed(diag, torque, transmitter=None):
    a = diag.Asm(SPEED_ORIGIN, SPEED_LIMIT)
    arbitration = 0x8000 | (CAN_ID << 2)

    a.label("reset")
    for address in (AGE, PHASE, DEFER, BUSY):
        a.zero(address)
    if transmitter:
        from tx import COOLANT_LAST, DEFER as TX_DEFER, PREFER_COOLANT, RPM_LAST
        for address in (RPM_LAST, COOLANT_LAST, TX_DEFER, PREFER_COOLANT):
            a.zero(address)
    a.extp(0x3C)
    a.zero(SPEED)
    a.raw("db00", "RETS")

    a.label("configure")
    a.ld(4, diag.STATE)
    a.cmp(4, INIT_SPEED)
    a.branch(3, "can_enable")
    a.emit(diag.far(0xDA, a.labels["reset"]), "CALLS speed reset")
    a.zero(0xEF14)
    a.set(0xEF16, 0xDFFC)
    a.zero(0xEF18)
    a.set(0xEF1A, arbitration)
    a.set(0xEF1C, 0x1088)
    for address in range(0xEF1E, 0xEF26, 2):
        a.zero(address)
    a.set(0xEF12, 0xF3)
    a.set(0xEF10, OBJECT)
    a.set(diag.STATE, INIT_SPEED + 1)
    a.imm(4, 0)
    a.raw("db00", "RETS")
    a.label("can_enable")
    if transmitter:
        a.emit(diag.far(0xDA, transmitter.labels["configure"]), "CALLS engine signals configure")
    else:
        a.imm(4, 1)
    a.raw("db00", "RETS")

    a.label("tick")
    a.ld(4, AGE)
    a.cmp(4, 0)
    a.branch(2, "age_done")
    a.subi(4, 1)
    a.st(AGE, 4)
    a.cmp(4, 0)
    a.branch(3, "age_done")
    a.extp(0x3C)
    a.zero(SPEED)
    a.label("age_done")
    a.ld(4, PHASE)
    a.cmp(4, 0)
    a.branch(3, "complete")
    a.ld(4, DEFER)
    a.cmp(4, 0)
    a.branch(2, "idle")
    a.subi(4, 1)
    a.st(DEFER, 4)
    a.branch(0, "free")
    a.label("idle")
    if transmitter:
        # E4 must see a ready IF1 between otherwise independent transactions;
        # its hardware-stall counter is reset by its own ready branch.
        a.ld(4, torque.BUSY_COUNT)
        a.cmp(4, 0)
        a.branch(3, "free")
    for address, mask in ((diag.DIAG_PHASE, 0xF), (torque.PHASE, 0xFFFF), (0xEF10, 0x8000)):
        a.ld(4, address)
        a.andi(4, mask)
        a.cmp(4, 0)
        a.branch(3, "free")
    a.ld(4, 0xEF90)
    a.andi(4, 1 << (OBJECT - 1))
    a.cmp(4, 0)
    a.branch(2, "free")
    a.set(PHASE, 1)
    a.set(0xEF12, 0x37)
    a.set(0xEF10, OBJECT)
    a.branch(0, "owned")

    a.label("complete")
    a.ld(4, 0xEF10)
    a.andi(4, 0x8000)
    a.cmp(4, 0)
    a.branch(2, "received")
    a.ld(4, BUSY)
    a.addi(4, 1)
    a.st(BUSY, 4)
    a.cmp(4, 50)
    a.branch(8, "owned")
    a.set(0xEF00, 0x61)  # Existing wrapper re-enters its bus recovery state.
    a.branch(0, "owned")
    a.label("received")
    a.zero(BUSY)
    a.zero(PHASE)
    a.set(DEFER, 2)  # Give existing torque and diagnostics their service opportunities.
    a.ld(4, 0xEF1A)
    a.cmp(4, arbitration)
    a.branch(3, "restore_object")
    a.ld(4, 0xEF1C)
    a.andi(4, 0xC00F)
    a.cmp(4, 0x8008)
    a.branch(3, "restore_object")

    # Match the known Chery check field. It covers data bytes 1 and 4.
    a.ld(4, 0xEF1E)
    a.rr(5, 4)
    a.andi(4, 0xF)
    a.shift(5, 8)
    a.ld(6, 0xEF20)
    a.shift(6, 4)
    a.andi(6, 0xF0)
    a.either(4, 6)
    a.ld(6, 0xEF22)
    a.andi(6, 0xFF)
    a.add(5, 6)
    a.andi(5, 0xFF)
    a.imm(6, 255)
    a.sub(6, 5)
    a.cmpreg(4, 6)
    a.branch(3, "owned")

    a.ld(4, 0xEF24)
    a.swap(4)
    a.cmp(4, RAW_LIMIT)
    a.branch(9, "invalid_speed")
    # Eleven fixed, bounded iterations compute floor(raw/25) without MUL/DIV
    # or changes to native accumulator registers.
    a.label("division")
    a.imm(5, 0)
    a.imm(6, 25 << 10)
    a.imm(7, 1 << 10)
    a.label("division_step")
    a.cmpreg(4, 6)
    a.branch(8, "division_next")
    a.sub(4, 6)
    a.either(5, 7)
    a.label("division_next")
    a.shift(6, 1)
    a.shift(7, 1)
    a.cmp(7, 0)
    a.branch(3, "division_step")
    a.shift(5, 5, True)
    a.extp(0x3C)
    a.st(SPEED, 5)
    a.set(AGE, STALE_CALLS)
    a.branch(0, "owned")

    a.label("invalid_speed")
    a.zero(AGE)
    a.extp(0x3C)
    a.zero(SPEED)
    a.branch(0, "owned")
    a.label("restore_object")
    a.zero(0xEF18)
    a.set(0xEF1A, arbitration)
    a.set(0xEF1C, 0x1088)
    a.set(0xEF12, 0xB0)
    a.set(0xEF10, OBJECT)
    a.label("owned")
    a.imm(4, 1)
    a.raw("db00", "RETS")
    a.label("free")
    if transmitter:
        a.emit(diag.far(0xDA, transmitter.labels["tick"]), "CALLS engine signals tick")
    else:
        a.imm(4, 0)
    a.raw("db00", "RETS")
    return a, a.finish()


def revised_wrapper(diag, labels):
    # Retain the upstream assembly and place only three calls into its
    # serialized IF1 scheduler. Exact old source and machine code are checked.
    path = Path(diag.__file__)
    source = path.read_text(encoding="utf-8")
    injections = {
        "    a.ld(4,DIAG_PHASE);a.andi(4,15);a.cmp(4,0);a.branch(3,'diag_complete')":
            ("tick", 3),
        "    a.label('fault')": ("reset", None),
        "    a.label('enable')": ("configure", 2),
    }
    for anchor, (label, condition) in injections.items():
        if source.count(anchor) != 1:
            raise ValueError(f"Unexpected upstream assembler anchor: {anchor}")
        call = f"    a.emit(far(0xDA,{labels[label]:#x}),'CALLS speed_{label}')"
        if condition is not None:
            # Each hook sets Z with its final MOV R4,#0 or #1. RETS keeps PSW.
            call += f"\n    a.branch({condition},'exit')"
        replacement = f"{anchor}\n{call}" if label != "tick" else f"{call}\n{anchor}"
        source = source.replace(anchor, replacement)
    namespace = {"__file__": str(path), "__name__": "bosch_candidate_diag"}
    exec(compile(source, str(path), "exec"), namespace)
    return namespace["assemble"](torque=True)


def build(engine, s04, *, with_engine_signals_tx=False, compact=False):
    if digest(s04) != S04_SHA:
        raise ValueError("S04 SHA-256 does not match the pinned E4M3 image")
    sys.path.insert(0, str(engine / "tools"))
    import build_can_diag as diag
    import build_e4
    import torque_patch as torque
    from compact_branches import compact_local_branches

    base = (engine / "build_inputs/GW4G15_REV8_BASELINE_NO_LIN.bin").read_bytes()
    donor = (engine / "build_inputs/CHERY_REFERENCE_DO_NOT_FLASH.bin").read_bytes()
    rebuilt_s04, old_wrapper, old_torque, _ = build_e4.build(base, donor)
    if rebuilt_s04 != s04:
        raise ValueError("Pinned upstream build failed to reproduce S04")
    if not (torque.START_CALL_AGE < AGE < PHASE < DEFER < BUSY < torque.RAM_END):
        raise ValueError("Upstream torque state conflicts with the reserved receiver state")
    tx_part, tx_code = None, b""
    if with_engine_signals_tx:
        from tx import assemble
        for start, end in ((0x02519E, 0x0251A2), (0x030DC8, 0x030FA4),
                           (0x052A50, 0x052A6E), (0x0539D2, 0x0539D6), (0x093E90, 0x093E94)):
            span = slice(diag.offset(start), diag.offset(end))
            if s04[span] != base[span]:
                raise ValueError(f"E4M3 native producer differs from REV8 at {start:#x}")
        tx_part, tx_code = assemble(diag, torque)
        if compact:
            tx_code = compact_local_branches(tx_part, tx_code)
    speed, speed_code = assemble_speed(diag, torque, tx_part)
    if compact:
        speed_code = compact_local_branches(speed, speed_code)
    wrapper, wrapper_code = revised_wrapper(diag, speed.labels)
    output = bytearray(s04)
    allowed = set()
    regions = {}
    sections = [
        ("wrapper", wrapper.origin, wrapper_code),
        ("speed_receiver", speed.origin, speed_code),
        ("speed_selector", CALIBRATION, b"\x20"),
    ]
    if tx_part:
        sections.append(("engine_signals_tx", tx_part.origin, tx_code))
    for name, cpu, code in sections:
        off = diag.offset(cpu)
        if name in ("speed_receiver", "engine_signals_tx") and any(
            byte != 255 for byte in s04[off:off + len(code)]
        ):
            raise ValueError(f"{name} flash region overlaps existing contents")
        if name == "wrapper":
            if any(byte != 255 for byte in s04[off + len(old_wrapper.data):off + len(code)]):
                raise ValueError("CAN wrapper expansion overlaps existing contents")
        if name == "speed_selector" and s04[off] != 0:
            raise ValueError("Unexpected native speed source selector")
        output[off:off + len(code)] = code
        allowed.update(range(off, off + len(code)))
        regions[name] = {"cpu": hex(cpu), "offset": hex(off), "length": len(code)}
    for _ in range(5):
        invalid = [record for record in diag.checks(output) if not record["valid"]]
        if not invalid:
            break
        for record in invalid:
            p = record["file_offset"] + 8
            struct.pack_into("<II", output, p, record["actual"], record["actual"] ^ 0xFFFFFFFF)
            allowed.update(range(p, p + 8))
    records = diag.checks(output)
    if not all(record["valid"] for record in records):
        raise ValueError("Bosch checksum records failed after rebuild")
    ta = diag.offset(old_torque.origin)
    if output[ta:ta + len(old_torque.data)] != s04[ta:ta + len(old_torque.data)]:
        raise ValueError("Existing E4 torque machine code changed")
    changed = {i for i, (old, new) in enumerate(zip(s04, output, strict=True)) if old != new}
    if not changed <= allowed:
        raise ValueError("Unexpected S04 differences")
    manifest = {
        "status": "OFFLINE_ONLY_NOT_HARDWARE_TESTED",
        "base_sha256": S04_SHA,
        "sha256": digest(output),
        "bytes": len(output),
        "changed_bytes": len(changed),
        "regions": regions,
        "checksum_records": len(records),
        "can_standard_id": hex(CAN_ID),
        "can_object": OBJECT,
        "stale_service_calls": STALE_CALLS,
        "panel_output_implemented": False,
        "speed_receiver_symbols": {name: hex(address) for name, address in speed.labels.items()},
    }
    if tx_part:
        from tx import COOLANT, RPM
        manifest["diagnostic_signals_tx"] = [
            {"can_id": hex(x.identifier), "object": x.object_number, "period_t4_ticks": x.period}
            for x in (RPM, COOLANT)
        ]
        manifest["engine_signals_tx_symbols"] = {name: hex(address) for name, address in tx_part.labels.items()}
        speed.rows += tx_part.rows
        speed.labels.update({"engine_signals_" + name: address for name, address in tx_part.labels.items()})
    if compact:
        manifest["short_relative_branches"] = sum(
            instruction.startswith("JMPR") for _, _, instruction in speed.rows
        )
    return bytes(output), manifest, wrapper, speed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", required=True, type=Path, help="Pinned R4 development/E4M3/engine")
    parser.add_argument("--s04", required=True, type=Path)
    parser.add_argument("--outdir", required=True, type=Path)
    parser.add_argument("--with-engine-signals-tx", action="store_true")
    parser.add_argument("--compact", action="store_true", help="Shorten local RX/TX branches")
    args = parser.parse_args()
    image, manifest, wrapper, speed = build(
        args.engine.resolve(), args.s04.read_bytes(), with_engine_signals_tx=args.with_engine_signals_tx,
        compact=args.compact,
    )
    try:
        args.outdir.mkdir(parents=True)
    except FileExistsError:
        parser.error("Use a new output directory")
    filename = TX_OUTPUT if args.with_engine_signals_tx else OUTPUT
    if args.compact:
        filename = filename.replace("_OFFLINE_ONLY", "_COMPACT_OFFLINE_ONLY")
    (args.outdir / filename).write_bytes(image)
    (args.outdir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    with (args.outdir / "candidate.asm").open("w", encoding="utf-8") as stream:
        for part in (wrapper, speed):
            for cpu, length, instruction in part.rows:
                for name, address in part.labels.items():
                    if address == cpu:
                        stream.write(f"{name}:\n")
                off = cpu - 0x10000
                stream.write(f"{cpu:06X} {off:06X} {image[off:off + length].hex():8} {instruction}\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
