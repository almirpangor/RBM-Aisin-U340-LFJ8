"""Exercise an application-only H03 isolation candidate without a device."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory

from check_h03_flash_policy import APPLICATION, BOOT, FCNT1, FESBANK1, RECOVERY
from check_h03_flash_residency import CHECKSUM_REMAINING, COPY_REMAINING, SESSION_FLAGS
from check_h03_link import HERE, TARGET, elf_info, identify_h03


CANDIDATE_START, CANDIDATE_END = 0x020000, 0x030000
CAN0, CAN1 = 0x801000, 0x801400
ICTX = 0x808DBF
ADC0_TICKS = 0x808DC0
SENTINEL = 0x806B40
FLAGS = 0x25
CLOSED = 0x15
SOURCE = 0x102000

LAYOUT = """
ENTRY(_start)
SECTIONS {
  .oem_before 0 : { KEEP(*(.oem_before)) }
  .text 0x20000 : { *(.text .text.*) *(.rodata .rodata.*) }
  .oem_after 0x30000 : { KEEP(*(.oem_after)) }
  .fixture 0x100000 : { *(.fixture) }
  .data : { *(.data .data.*) }
  .bss : { *(.bss .bss.*) *(COMMON) }
  /DISCARD/ : { *(.note*) *(.comment) }
  ASSERT(SIZEOF(.text) <= 0x10000, "Isolation code exceeds candidate space")
}
stock_adc0 = 0x003608;
"""
ASM = r"""
    .section .oem_before,"ax",@progbits
    .incbin "h03-before.dat"
    .section .oem_after,"ax",@progbits
    .incbin "h03-after.dat"

    .section .fixture,"ax",@progbits
    .p2align 2
    .global _start,fixture_ready,fixture_done,fixture_drain
_start:
    ld24 sp,#0x9ffffc
fixture_ready:
    ldi r0,#0x40
    mvtc r0,psw
    ld24 r3,#fixture_target
    ld r3,@r3
    ld24 lr,#fixture_done
    ldi r0,#0
    jmp r3
    .p2align 2
fixture_drain:
    push lr
    bl.l fixture_quiesce
    bl.l stock_adc0
    pop lr
    jmp lr
    .p2align 2
fixture_done:
    bra fixture_done
"""
C_FIXTURE = r"""
#include "lfj8_h03_mmio.h"
#include "lfj8_h03_monitor_quiesce.h"

uint32_t fixture_target, fixture_drop, fixture_writes, fixture_unlocked, fixture_restored;
int fixture_result, fixture_guard;

static uint32_t psw(void)
{
    uint32_t value;
    __asm__ volatile ("mvfc %0,psw" : "=r"(value));
    return value;
}

static int record(uint32_t address)
{
    ++fixture_writes;
    fixture_unlocked |= psw() & 0x40u;
    return address != fixture_drop;
}

static void write8(void *context, uint32_t address, uint8_t value)
{
    if (record(address)) {
        lfj8_h03_mmio.write8(context, address, value);
    }
}

static void write16(void *context, uint32_t address, uint16_t value)
{
    (void)context;
    if (record(address)) {
        *(volatile uint16_t *)(uintptr_t)address = value;
    }
}

static void write32(void *context, uint32_t address, uint32_t value)
{
    (void)context;
    if (record(address)) {
        *(volatile uint32_t *)(uintptr_t)address = value;
    }
}

void fixture_configure(void)
{
    Lfj8RegisterIo io = lfj8_h03_mmio;
    io.write8 = write8;
    const uint32_t saved = io.enter(io.context);
    fixture_result = lfj8_h03_monitor_configure_filters_locked(&io);
    io.leave(io.context, saved);
    fixture_restored = psw() & 0x40u;
}

void fixture_quiesce(void)
{
    Lfj8RegisterIo io = lfj8_h03_mmio;
    io.write8 = write8;
    const Lfj8H03MonitorIo monitor = {&io, write16, write32};
    fixture_result = lfj8_h03_monitor_quiesce(&monitor);
    const uint32_t saved = io.enter(io.context);
    fixture_guard = lfj8_h03_monitor_isolated_locked(&io);
    io.leave(io.context, saved);
    fixture_restored = psw() & 0x40u;
}
"""


def set_memory(kind, address, value):
    return f"set {{{kind}}}{address:#x} = {value:#x}"


def probe(run, work, gdb, entry, memory, *, stops=("fixture_done",), drop=0, watch=()):
    watched = (
        ("unsigned char", FCNT1), ("unsigned short", FESBANK1),
        ("unsigned char", SESSION_FLAGS), ("unsigned int", CHECKSUM_REMAINING),
        ("unsigned int", COPY_REMAINING), ("unsigned short", ADC0_TICKS),
        ("unsigned int", SENTINEL), ("unsigned char", ICTX), *watch,
    )
    values = ("$pc", "$r0", "fixture_restored", "fixture_result", "fixture_guard",
              "fixture_writes", "fixture_unlocked", *(f"*({kind}*){address:#x}" for kind, address in watched))
    commands = ["set confirm off", "target sim --memory-size 16M", "load",
                "tbreak *fixture_ready", "run", f"set fixture_target = {entry}",
                f"set fixture_drop = {drop:#x}"]
    commands.extend(set_memory(*step) for step in memory)
    commands.extend(f"tbreak *{stop}" for stop in stops)
    commands.extend(("continue", 'printf "RESULT ' + " ".join(["%x"] * len(values)) + '\\n", ' + ", ".join(values)))
    (work / "probe.gdb").write_text("\n".join(commands) + "\n", encoding="ascii")
    output = run(gdb, "--batch", "-nx", "-x", "probe.gdb", "fixture.elf")
    match = re.search(rb"^RESULT ((?:[0-9a-f]+ )+[0-9a-f]+)\r?$", output, re.M)
    if match is None or len(match[1].split()) != len(values):
        raise ValueError(f"Missing observation for {entry}: {output[-1800:].decode(errors='replace')}")
    return tuple(int(number, 16) for number in match[1].split())


def can_state(stopped):
    for base in (CAN0, CAN1):
        yield ("unsigned short", base + 2, 0x0100 if stopped else 0x0800)
        for field in (0x30, 0x38, 0x1E0, 0x1F0):
            yield ("unsigned char", base + field, 0x18 if stopped else 0x1C)
        for slot in (14, 15):
            yield ("unsigned char", base + 0x50 + slot, 0 if stopped else 0x40)


def local_state():
    return (
        ("unsigned int", 0x809F9C, 0x809F9C),
        ("unsigned char", FCNT1, 1), ("unsigned short", FESBANK1, 0x8020),
        ("unsigned char", SESSION_FLAGS, FLAGS), ("unsigned int", CHECKSUM_REMAINING, 513),
        ("unsigned int", COPY_REMAINING, 257), ("unsigned int", COPY_REMAINING + 4, 257),
        ("unsigned int", 0x808584, SOURCE), ("unsigned int", 0x808588, SENTINEL),
        ("unsigned int", 0x80858C, SOURCE), ("unsigned short", ADC0_TICKS, 0),
        ("unsigned int", SENTINEL, 0xCCDDCCDD), ("unsigned char", ICTX, 0xFF),
    )


def qualification_cases(replay):
    rows = []
    for name, extra, drop, result, writes in (
        ("configure_both_channels", (), 0, 1, 16),
        ("can0_not_in_reset", (("unsigned short", CAN0 + 2, 0x0800),), 0, 0, 0),
        ("can1_receive_slot_active", (("unsigned char", CAN1 + 0x5F, 0x40),), 0, 0, 0),
        ("can1_unacknowledged_slot", (("unsigned char", CAN1 + 0x5E, 1),), 0, 0, 0),
        ("configure_write_dropped", (), CAN1 + 0x38, 0, 16),
    ):
        observed = replay("&fixture_configure", (*can_state(True), *extra), drop=drop)
        if observed[2] & 0x40 == 0 or observed[3:7] != (result, 0, writes, 0):
            raise ValueError(f"{name}: {observed}")
        rows.append({"scenario": name, "qualified": bool(result), "writes_under_lock": writes})

    for name, extra, drop, ready, expected_writes, adc in (
        ("quiesce_and_run_adc0", (), 0, True, 5, 1),
        ("repeat_quiesce",
         (("unsigned char", FCNT1, 0), ("unsigned short", FESBANK1, 0x20),
          ("unsigned int", CHECKSUM_REMAINING, 0), ("unsigned int", COPY_REMAINING, 0),
          ("unsigned char", SESSION_FLAGS, CLOSED)), 0, True, 4, 1),
        ("can0_slot_a_wildcard", (("unsigned char", CAN0 + 0x30, 0),), 0, False, 0, 0),
        ("can1_slot_b_wildcard", (("unsigned char", CAN1 + 0x38, 0),), 0, False, 0, 0),
        ("can1_slot_a_other_class", (("unsigned char", CAN1 + 0x1E0, 0x18),), 0, False, 0, 0),
        ("can0_extended", (("unsigned short", CAN0 + 4, 1),), 0, False, 0, 0),
        ("can0_stale_receive", (("unsigned char", CAN0 + 0x5E, 0x41),), 0, False, 0, 0),
        ("can1_stale_receive", (("unsigned char", CAN1 + 0x5F, 0x41),), 0, False, 0, 0),
        ("foreign_bank_enabled", (("unsigned short", 0x8007F0, 0x8008),), 0, False, 0, 0),
        ("erase_program_mode", (("unsigned char", FCNT1, 0x10),), 0, False, 0, 0),
        ("oem_programming_gate", (("unsigned char", 0x80801C, 1),), 0, False, 0, 0),
        ("oem_service_mode", (("unsigned char", 0x804887, 4),), 0, False, 0, 0),
        ("disable_mode_write_dropped", (), FCNT1, False, 5, 0),
        ("disable_bank_write_dropped", (), FESBANK1, False, 5, 0),
        ("sum_write_dropped", (), CHECKSUM_REMAINING, False, 5, 0),
        ("copy_write_dropped", (), COPY_REMAINING, False, 5, 0),
        ("close_write_dropped", (), SESSION_FLAGS, False, 5, 0),
    ):
        entry = "&fixture_drain" if adc else "&fixture_quiesce"
        values = replay(entry, (*can_state(False), *local_state(), *extra), drop=drop)
        if values[2] & 0x40 == 0 or values[3:7] != (int(ready), int(ready), expected_writes, 0):
            raise ValueError(f"{name}: disposition or lock mismatch: {values}")
        if values[12:15] != (adc, 0xCCDDCCDD, 0xFF):
            raise ValueError(f"{name}: ADC dispatch or sentinels changed: {values}")
        if ready and values[7:12] != (0, 0x20, CLOSED, 0, 0):
            raise ValueError(f"{name}: monitor or Virtual Flash left armed: {values}")
        if expected_writes == 0:
            control = 0x10 if name == "erase_program_mode" else 1
            if values[7:12] != (control, 0x8020, FLAGS, 513, 257):
                raise ValueError(f"{name}: unsafe input mutated: {values}")
        rows.append({"scenario": name, "qualified": ready, "writes_under_lock": expected_writes,
                     "fcnt1": values[7], "bank": f"0x{values[8]:04X}", "flags": values[9],
                     "checksum_remaining": values[10], "copy_remaining": values[11], "stock_adc0_ticks": adc})
    return rows


def native_transport(replay):
    results = []
    for channel, base, entry, pointers, exit_dispatch in (
        (0, CAN0, 0x0013F0, 0x808518, 0x0016F8),
        (1, CAN1, 0x001C04, 0x808540, 0x001F14),
    ):
        for slot, can_id, stop in ((13, 0x602, exit_dispatch), (14, 0x602, 0x0034B4),
                                   (15, 0x602, 0x0034B4), (14, 0x7E1, 0x003830),
                                   (15, 0x7DF, 0x003830)):
            address = base + 0x100 + 16 * slot
            memory = (
                ("unsigned int", 0x809F9C, 0x809F9C), ("unsigned char", ICTX, 0xFF),
                ("unsigned int", pointers, base + 0x100), ("unsigned int", pointers + 4, base + 0x50),
                ("unsigned short", base + 0x0C, 0x8000 >> slot),
                ("unsigned char", base + 0x50 + slot, 0x41),
                ("unsigned char", address, can_id >> 6), ("unsigned char", address + 1, can_id & 0x3F),
                ("unsigned char", address + 5, 8),
            )
            observations = replay(hex(entry), memory, stops=(hex(stop), "fixture_done"))
            # With pending slot 13 the original monitor parser is not reached.
            expected_context = 0xFF if slot == 13 else channel
            if observations[0] != stop or observations[-1] != expected_context:
                raise ValueError(f"CAN{channel} slot {slot} ID {can_id:#x}: {observations}")
            results.append({"channel": channel, "slot": slot, "standard_id": f"0x{can_id:03X}",
                            "stop": f"0x{stop:06X}", "route_context": expected_context})
    return results


def stock_reinitialization(replay):
    results = []
    for base, entry, stop in ((CAN0, 0x0010F8, 0x00121C), (CAN1, 0x00190C, 0x001A30)):
        mask_registers = tuple(("unsigned short", base + offset) for offset in (0x30, 0x38))
        memory = (*can_state(True), *(("unsigned short", address, 0x1C00)
                                      for _, address in mask_registers))
        result = replay(hex(entry), memory, stops=(hex(stop),), watch=mask_registers)
        if result[0] != stop or result[-2:] != (0x1800, 0x1800):
            raise ValueError(f"Unexpected original H03 masks at {stop:#x}: {result}")
        results.append({"setup_entry": f"0x{entry:06X}", "stop": f"0x{stop:06X}",
                        "local_masks_restored": ["0x1800", "0x1800"], "would_accept_monitor": True})
    return results


def reset_cases(replay):
    shadow = (("unsigned char", FCNT1, 1), ("unsigned short", FESBANK1, 0x8008))
    reset = replay("0x003E40", (*shadow, *local_state()[3:6]),
                   stops=("0x000AE0",))
    if reset[0] != 0xAE0 or reset[7:12] != (1, 0x8008, 0, 0, 0):
        raise ValueError(f"Unexpected state after original software reset: {reset}")
    rows = []
    for name, override, expected in (
        ("stock_markers", (), APPLICATION),
        ("alias_header_cleared", (("unsigned short", 0x008000, 0),), RECOVERY),
        ("alias_header_valid_handoff_changed", (("unsigned int", 0x008084, 0xFF000003),), 0x008090),
    ):
        visible = (*shadow, *override)
        marker = replay("0x003E40", visible, stops=("0x0035CC",))
        passed = expected != RECOVERY
        if (marker[0], marker[1], *marker[7:9]) != (0x0035CC, int(passed), 1, 0x8008):
            raise ValueError(f"{name}: unexpected warm reset marker check: {marker}")
        observed = replay(hex(BOOT), visible, stops=("0x008100", "0x0047d8", "0x008090"))
        if (observed[0], *observed[7:9]) != (expected, 1, 0x8008):
            raise ValueError(f"{name}: {observed}")
        rows.append({"scenario": name, "warm_reset_checks_marker": passed, "stop": f"0x{expected:06X}"})
    return {"software_reset": {"stop": "0x000AE0", "fcnt1": 1, "bank": "0x8008",
                               "pending_counters_cleared": True},
            "modeled_alias_dispatch": rows}


def check(base, compiler):
    identity = identify_h03(base)
    rom = base.read_bytes()
    if sha256(rom).hexdigest() != identity["sha256"]:
        raise ValueError("H03 changed while reading its instructions")
    if rom[CANDIDATE_START:CANDIDATE_END] != b"\xff" * (CANDIDATE_END - CANDIDATE_START):
        raise ValueError("H03 candidate sector differs")
    if rom[0x3D30:0x3D36] != bytes.fromhex("1F211F1F1802"):
        raise ValueError("Unexpected H03 transport descriptors")
    with TemporaryDirectory(prefix="rbm-h03-app-isolation-") as directory:
        work = Path(directory)

        def run(*args):
            return subprocess.run([str(arg) for arg in args], cwd=work, check=True,
                                  capture_output=True, timeout=30).stdout

        if run(compiler, "-dumpmachine").strip() != b"m32r-elf":
            raise ValueError("A bare-metal M32R compiler is required")
        for name, data in (("h03-before.dat", rom[:CANDIDATE_START]), ("h03-after.dat", rom[CANDIDATE_END:])):
            (work / name).write_bytes(data)
        for name, text in (("fixture.S", ASM), ("fixture.c", C_FIXTURE), ("fixture.ld", LAYOUT)):
            (work / name).write_text(text, encoding="ascii")
        run(compiler, *TARGET, "-Os", "-g", "-std=c99", "-ffreestanding", "-fno-builtin",
            "-Wall", "-Wextra", "-Werror", "-Wconversion", "-Wsign-conversion",
            "-ffunction-sections", "-fdata-sections", "-nostdlib", "-I", HERE,
            "-Wl,-T,fixture.ld,--gc-sections,--undefined=fixture_configure",
            "-Wl,--undefined=lfj8_h03_monitor_filters_locked", "-Wl,--undefined=fixture_drop,--undefined=fixture_guard",
            "-Wl,--undefined=fixture_drain", "fixture.S", "fixture.c",
            HERE / "lfj8_h03_monitor_quiesce.c", HERE / "lfj8_h03_mmio.c", "-lc", "-lgcc", "-o", "fixture.elf")
        objcopy = compiler.with_name(f"m32r-elf-objcopy{compiler.suffix}")
        run(objcopy, "-O", "binary", "-j", ".oem_before", "fixture.elf", "original-linked.dat")
        if (work / "original-linked.dat").read_bytes() != rom[:CANDIDATE_START]:
            raise ValueError("The linked fixture changed the original Flash below candidate code")
        _, sections = elf_info(work / "fixture.elf", 2)
        candidate = [(address, size) for address, size, _ in sections
                     if CANDIDATE_START <= address < CANDIDATE_END]
        if len(candidate) != 1 or candidate[0][0] != CANDIDATE_START or candidate[0][1] > CANDIDATE_END - CANDIDATE_START:
            raise ValueError("The linked candidate code is outside the approved test sector")
        gdb = compiler.with_name(f"m32r-elf-gdb{compiler.suffix}")

        def replay(entry, memory, **options):
            return probe(run, work, gdb, entry, memory, **options)

        guard = qualification_cases(replay)
        transport = native_transport(replay)
        recovery = stock_reinitialization(replay)
        resets = reset_cases(replay)
    admitted = [can_id for can_id in range(0x800) if (can_id ^ 0x700) & 0x700 == 0]
    diagnostics = (0x732, 0x7DF, 0x7E1)
    if len(admitted) != 256 or 0x602 in admitted or not set(diagnostics).issubset(admitted):
        raise ValueError("The proposed standard filter does not separate the required IDs")
    return {
        "base": identity,
        "candidate_flash_range": ["0x020000", "0x030000"],
        "linked_candidate_with_test_helpers_bytes": candidate[0][1],
        "lower_flash_unchanged_through_0x01ffff": True,
        "configure_and_quiesce": guard,
        "receiver_dispatch_with_synthetic_slots": transport,
        "stock_can_reinitialization": recovery,
        "standard_filter_model": {"compare_mask": "0x700", "slot_id": "0x700",
                                  "admitted_standard_ids": len(admitted), "excluded_monitor": "0x602",
                                  "admitted_diagnostic": [hex(can_id) for can_id in diagnostics]},
        "warm_reset": resets,
        "physical_can_and_remap_verified": False,
        "ready_for_application_authority_without_platform_binding": False,
        "flashable_image": None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--gcc", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.suffix.lower() != ".json" or args.out.resolve() == args.base.resolve():
        parser.error("--out must be a separate JSON report")
    try:
        result = check(args.base, args.gcc.resolve())
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    except subprocess.CalledProcessError as error:
        parser.exit(1, (error.stderr or error.stdout or str(error).encode()).decode(errors="replace") + "\n")
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
