"""Trace the approved H03 BasicCAN RX handler in the M32R CPU simulator."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
from typing import NamedTuple

from check_h03_flash_policy import (
    ERASE_CALL, ERASE_DENIED, ERASE_POLICY, FCNT1, FESBANK1, LAYOUT,
    VIRTUAL_CONFIG, VIRTUAL_CONFIG_DONE, VIRTUAL_SELECT,
)
from check_h03_flash_residency import PROGRAMMING_MODE
from check_h03_link import HERE, ROOT, TARGET, identify_h03
from check_h03_service_isolation import INSTALL_ACCEPT, INSTALL_BEGIN, INSTALL_DENY
from lfj8_h03_layout import alloc_sections, read_elf


SLIST = 0x80100C
EXTID = 0x801004
MSC = 0x801050
SLOT_DATA = 0x801100
COPY = 0x808526
CAN0_IRQ_ENTRY = 0x004724
CAN0_IRQ_TABLE_WORD = 0x0009D8
HOOK_SITE = 0x001534
HOOK_RESUME = HOOK_SITE + 4
HOOK_STOCK = bytes.fromhex("80c800ff")
DISPATCH_SITE = 0x004738
DISPATCH_STOCK = bytes.fromhex("fefff32e")
RESIDENT_START, APP_START, FLASH_LIMIT = 0x006000, 0x008000, 0x080000
RESIDENT_GEOMETRY = 0x000940
MVTACHI_R0 = 0x5070
STACK_PROBE_BYTES = 512
STACK_PATTERN = 0xA55AA55A
REGISTERS = [f"$r{i}" for i in range(13)] + ["$fp", "$lr", "$sp", "$psw", "$accl", "$acch"]
HOOK_LAYOUT = """
ENTRY(_start)
SECTIONS {
  .oem 0x000000 : { KEEP(*(.oem)) }
  .fixture 0x100000 : { KEEP(*(.fixture)) }
  .text 0x101000 : { KEEP(*(.text.rbm_h03_dtc_rx_hook)) *(.text*) }
  .rodata : { *(.rodata*) }
  .data : { *(.data*) }
  .bss : { *(.bss*) *(COMMON) }
  /DISCARD/ : { *(.note*) *(.comment) }
  h03_dtc_rx_resume = 0x001538;
  h03_dtc_rx_entry = 0x0013F0;
}
"""
RESIDENT_LAYOUT = """
ENTRY(_start)
SECTIONS {
  .oem_low 0x000000 : { KEEP(*(.oem_low)) }
  .resident_rx 0x006000 : {
    FILL(0xffffffff)
    KEEP(*(.text.rbm_h03_dtc_rx_hook))
    *(.text*)
    *(.rodata*)
    rx_resident_end = .;
    . = 0x2000;
  }
  .oem_app 0x008000 : { KEEP(*(.oem_app)) }
  .fixture 0x100000 : { KEEP(*(.fixture)) }
  .data 0x101000 : { *(.data*) }
  .bss : { *(.bss*) *(COMMON) }
  /DISCARD/ : { *(.note*) *(.comment) }
  ASSERT(SIZEOF(.data) == 0, "Resident RX fixture must not load writable data")
  h03_dtc_rx_resume = 0x001538;
  h03_dtc_rx_entry = 0x0013F0;
}
"""
FIXTURE = """
    .section .fixture,"ax",@progbits
    .global _start, fixture_ready, fixture_done
_start:
    ld24 sp,#0x9ffffc
#ifdef RBM_DTC_RX_HOOK_FIXTURE
    bl fixture_rx_init
    ld24 r0,#0x445566
    mvtaclo r0
#endif
    ldi r8,#8
    ldi r9,#9
    ldi r10,#10
    .p2align 2
fixture_ready:
#ifdef RBM_DTC_RX_RESIDENT_FIXTURE
    ld24 r0,#fixture_update_arguments
    ld r4,@r0
    beqz r4,.Lrx_fixture_probe
    ld r1,@(8,r0)
    ld r5,@(12,r0)
    ld r8,@(16,r0)
    ld r9,@(20,r0)
    ld r0,@(4,r0)
    jmp r4
    .p2align 2
.Lrx_fixture_probe:
#endif
#ifdef RBM_DTC_RX_TARGET_FIXTURE
    bl fixture_rx_foreground
    .global fixture_target_ready
fixture_target_ready:
#endif
#ifdef RBM_DTC_RX_HOOK_FIXTURE
    ld24 r0,#fixture_rx_high_probe
    ld r0,@r0
    beqz r0,.Lrx_fixture_entry
    ld24 r0,#0x712345
    slli r0,#8
    mulhi r0,r0
.Lrx_fixture_entry:
    ld24 r4,#0x004724
#else
    ld24 r4,#0x0013f0
#endif
    jl r4
    nop
#ifdef RBM_DTC_RX_HOOK_FIXTURE
    mvfachi r1
    mvfaclo r2
#endif
fixture_done:
#ifdef RBM_DTC_RX_TARGET_FIXTURE
    bl fixture_rx_foreground
    .global fixture_target_done
fixture_target_done:
    bl fixture_rx_foreground
    bra fixture_target_done
#else
    bra fixture_done
#endif
#ifdef RBM_DTC_RX_RESIDENT_FIXTURE
    .section .bss.fixture_update,"aw",@nobits
    .p2align 2
    .global fixture_update_arguments
fixture_update_arguments:
    .space 24
    .section .oem_low,"ax",@progbits
    .incbin "h03.dat",0,0x6000
    .section .oem_app,"ax",@progbits
    .incbin "h03.dat",0x8000
#else
    .section .oem,"ax",@progbits
    .incbin "h03.dat"
#endif
"""


class Overwrite(NamedTuple):
    slot: int
    frame: bytes
    control: int
    during_copy: bool
    before_attempt: bool = False


class Case(NamedTuple):
    name: str
    slots: dict[int, tuple[bytes, int]]
    expected: list[tuple]
    extended: int = 0
    overwrite: Overwrite | None = None
    deliveries: tuple[bytes, ...] = ()
    paired_slots: int = 0
    paired_deliveries: tuple[bytes, ...] | None = None


def slot_mask(slot):
    return 0x8000 >> slot


def raw_slot(can_id, dlc, payload, timestamp):
    header = bytes((can_id >> 6, can_id & 0x3F, 0xAD, 0xBE, 0xEF, dlc))
    data = bytes.fromhex(payload).ljust(8, b"\xCC")
    return header + data + timestamp.to_bytes(2, "big")


def write_slot(slot, raw, control):
    address = SLOT_DATA + 16 * slot
    return [f"set {{unsigned char}}{MSC + slot:#x} = {control:#x}"] + [
        f"set {{unsigned int}}{address + offset:#x} = 0x{raw[offset:offset + 4].hex()}"
        for offset in range(0, 16, 4)
    ]


def at(location, *commands):
    return [f"break {location}", "commands", "silent", *commands, "continue", "end"]


def trace(event, *values):
    fields = " %x" * len(values)
    return f'printf "RX {event}{fields}\\n", {", ".join(values)}'


def bytes_at(address, count):
    return [f"*(unsigned char*){address + offset:#x}" for offset in range(count)]


def run_probe(run, work, debugger, commands, elf="fixture.elf"):
    (work / "probe.gdb").write_text("\n".join(commands) + "\n", encoding="ascii")
    return run(debugger, "--batch", "-nx", "-x", "probe.gdb", elf).decode(errors="replace")


def simulate(run, work, debugger, case, *, compare_hook=False, patches=None,
             compare_dispatch=False, high_probe=False, setup=(), target=False, foreground=False,
             reset_owner=False, warm_rebind=False, target_start=(), target_steps=()):
    pending = sum(slot_mask(slot) for slot in case.slots)
    commands = [
        "set confirm off", "target sim --memory-size 16M", "load",
        "tbreak *fixture_ready", "run",
    ]
    if target:
        commands += [
            "set {unsigned char}0x806ae6 = 6",
            "set {unsigned short}0x801000 = 8",
            "set {unsigned short}0x801002 = 0x0800",
            "set {unsigned short}0x801008 = 0x1400",
            "set {unsigned short}0x801010 = 0x8003",
            "set {unsigned char}0x801028 = 0x1f",
            "set {unsigned char}0x801029 = 0x3f",
            "set {unsigned int}0x8003e0 = 5000",
            f"set {{unsigned char}}{MSC + 14:#x} = 0x40",
            f"set {{unsigned char}}{MSC + 15:#x} = 0x40",
            *target_start,
            "tbreak *fixture_target_ready", "continue",
            trace("startup", "fixture_foreground_result.available",
                  "fixture_target.queue.generation", "fixture_target.queue.count"),
        ]
    commands += [
        f"set {{unsigned short}}{SLIST:#x} = {pending:#x}",
        f"set {{unsigned short}}{EXTID:#x} = {case.extended:#x}",
        f"set {{unsigned int}}0x80851c = {MSC:#x}",
        f"set {{unsigned int}}0x808518 = {SLOT_DATA:#x}",
        *setup,
    ]
    for slot, (raw, control) in case.slots.items():
        commands.extend(write_slot(slot, raw, control))
    if compare_hook:
        commands += [
            "set {unsigned short}0x801002 = 0x0800",
            f"set $stack_floor = $sp - {STACK_PROBE_BYTES}",
            "set $probe = $stack_floor",
            "while $probe < $sp",
            f"set {{unsigned int}}$probe = {STACK_PATTERN:#x}",
            "set $probe = $probe + 4",
            "end",
        ]
        commands += at(f"*{HOOK_RESUME:#x}", trace("context", *REGISTERS))
    if compare_dispatch:
        commands += at("*0x0013f0", trace("dispatch_entry", *REGISTERS))
    linked = patches and (work / "fixture-patched.elf").is_file()
    if patches and not linked:
        commands += [f"set {{unsigned int}}{site:#x} = {word:#x}" for site, word in patches.items()]
    if high_probe:
        commands.append("set fixture_rx_high_probe = 1")
        if patches:
            commands += at("*rbm_h03_dtc_rx_restore_high",
                           trace("restore_high", "$r0", "*(unsigned short*)$pc"))
            if compare_dispatch:
                commands += at("*rbm_h03_dtc_rx_dispatch_restore_high",
                               trace("restore_high", "$r0", "*(unsigned short*)$pc"))
    commands += at("*0x152c", f"set $slist_before = *(unsigned short*){SLIST:#x}")
    # CAN0SLIST has write-zero-to-clear bits; plain simulator RAM does not.
    commands += at(
        "*0x1530",
        trace("ack", "$r8", "$slist_before", f"*(unsigned short*){SLIST:#x}"),
        f"set {{unsigned short}}{SLIST:#x} = $slist_before & *(unsigned short*){SLIST:#x}",
    )

    inject = []
    if case.overwrite:
        slot, raw, control, during_copy, before_attempt = case.overwrite
        inject = [
            "set $injected = 1",
            trace("overwrite", "$r8"),
            *write_slot(slot, raw, control),
            f"set {{unsigned short}}{SLIST:#x} = *(unsigned short*){SLIST:#x} | {slot_mask(slot):#x}",
        ]
        commands.append("set $injected = 0")
        if during_copy:
            commands += at(
                f"*0x3cf4 if $lr == 0x1564 && $r3 == 8 && $r8 == {slot} && !$injected",
                *inject,
            )
            inject = []
        elif before_attempt:
            commands += at(f"*{HOOK_SITE:#x} if $r8 == {slot} && !$injected", *inject)
            inject = []
        else:
            inject = [f"if $r8 == {slot} && !$injected", *inject, "end"]

    status = f"*(unsigned char*)({MSC:#x} + $r8)"
    commands += at(
        "*0x1544",
        trace("pre_clear", "$r8", "$r2", f"!!(*(unsigned short*){EXTID:#x} & (0x8000 >> $r8))"),
        *inject,
    )
    commands += at("*0x1548", trace("write_msc", "$r8", status))
    commands += at("*0x1564", trace("copy", "$r8", status, *bytes_at(COPY, 16)))
    commands += at("*0x1574", trace("stable", "$r9"))
    commands += at("*0x15e0", trace("lookup_match", "*(unsigned char*)0x808520"))
    commands += at("*0x3830", trace("oem_diagnostic", "$r0", "*(unsigned char*)0x808520"))
    commands += at("*0x34b4", trace("oem_monitor", "$r0", "*(unsigned char*)0x808e05",
                                   *bytes_at(0x808DFC, 8)))
    commands += [
        "tbreak *fixture_done", "continue",
        trace("return", "$pc == (unsigned int)&fixture_done", "$sp", "$r8", "$r9", "$r10",
              f"*(unsigned short*){SLIST:#x}"),
    ]
    if compare_hook:
        queue = "fixture_target.queue" if target else "fixture_rx_queue"
        received = f"{queue}.entries[$entry].delivery.received"
        if target:
            observation = [trace("target_queue", f"{queue}.count", f"{queue}.rejected")]
        else:
            observation = [trace("observer", "fixture_rx_calls", "fixture_rx_irq_enabled",
                                 f"{queue}.count", f"{queue}.rejected")]
            if compare_dispatch:
                observation.append(trace("dispatch", "fixture_rx_begins", "fixture_rx_paired_mask",
                                         "fixture_rx_skips"))
        commands += [
            trace("accumulator", "$r1", "$r2"),
            "set $probe = $stack_floor",
            f"while $probe < $sp && *(unsigned int*)$probe == {STACK_PATTERN:#x}",
            "set $probe = $probe + 4",
            "end",
            trace("stack", "$sp - $probe"),
            *observation,
            "set $entry = 0",
            f"while $entry < {queue}.count && $entry < 4",
            trace("delivery", f"{received}.generation", f"{received}.can_timestamp",
                  f"{received}.frame.id", f"{received}.frame.length",
                  *(f"{received}.frame.data[{i}]" for i in range(8))),
            "set $entry = $entry + 1",
            "end",
        ]
    if foreground:
        commands += [
            "tbreak *fixture_target_done", "continue",
            trace("foreground", "fixture_foreground_result.available",
                  "fixture_foreground_result.diagnostic_consumed", "fixture_target.queue.count",
                  "*(unsigned char*)0x80105d", *bytes_at(0x8011d0, 14)),
        ]
    if warm_rebind:
        commands += [
            "set fixture_rebind = 1",
            f"set {{unsigned short}}{SLIST:#x} = 0",
            f"set {{unsigned char}}{MSC + 13:#x} = 0",
            "tbreak *fixture_target_done", "continue",
            trace("warm_rebind", "fixture_native_bound", "h03_can_owner.setup_generation",
                  "h03_can_owner.grant", "fixture_target.queue.count",
                  "fixture_foreground_result.available", f"*(unsigned char*){MSC + 13:#x}"),
        ]
    if reset_owner:
        commands += [
            "set h03_can_owner.grant = 0", "set h03_can_owner.setup_generation = 8",
            f"set {{unsigned short}}{SLIST:#x} = 0",
            f"set {{unsigned char}}{MSC + 13:#x} = 0",
            f"set {{unsigned char}}{MSC + 14:#x} = 0x40",
            f"set {{unsigned char}}{MSC + 15:#x} = 0x40",
            "set {unsigned short}0x801008 = 0x1402",
            "set {unsigned int}0x8003e0 = 5004",
            "tbreak *fixture_target_done", "continue",
            trace("new_generation", "h03_can_owner.grant", "fixture_target.queue.generation",
                  "fixture_target.queue.count", "fixture_foreground_result.diagnostic_consumed",
                  "*(unsigned char*)0x80105d", "broker.diagnostic.link.session.mode_bits"),
        ]
    commands.extend(target_steps)
    events = []
    elf = "fixture-patched.elf" if linked else "fixture.elf"
    for line in run_probe(run, work, debugger, commands, elf).splitlines():
        if line.startswith("RX "):
            _, name, *fields = line.split()
            events.append((name, *(int(field, 16) for field in fields)))
    return events


def attempt(slot, raw, control=0x41, *, extended=0, replacement=None, during_copy=False):
    result = [("pre_clear", slot, control, extended)]
    if replacement and not during_copy:
        result.append(("overwrite", slot))
    result.append(("write_msc", slot, control & 0xFE))
    if during_copy:
        return result + [("overwrite", slot), ("copy", slot, 0x41, *raw[:8], *replacement[8:])]
    return result + [("copy", slot, control & 0xFE, *(replacement or raw)), ("stable", slot)]


def ack(slot, pending):
    return [("ack", slot, pending, 0xFFFF ^ slot_mask(slot))]


def cases(with_dispatch=False):
    session = raw_slot(0x732, 8, "0210860000000000", 0x1234)
    flow = raw_slot(0x732, 3, "300000", 0x1300)
    yield Case("no_slot_interrupt", {}, [])
    yield Case("rx14_session", {14: (session, 0x41)}, ack(14, 2) + attempt(14, session),
               deliveries=(session,))
    yield Case("rx15_flow_control", {15: (flow, 0x41)}, ack(15, 1) + attempt(15, flow),
               deliveries=(flow,))
    yield Case("both_slots_pending", {14: (session, 0x41), 15: (flow, 0x41)}, [
        *ack(15, 3), *attempt(15, flow), *ack(14, 2), *attempt(14, session),
    ], deliveries=(flow, session), paired_slots=3, paired_deliveries=(session, flow))
    for name, raw, control, extended in (
        ("foreign_id", raw_slot(0x733, 8, "021086", 0x1234), 0x41, 0),
        ("lost_before_read", session, 0x45, 0),
        ("remote_flag", session, 0x49, 0),
        ("extended_slot", session, 0x41, 1),
        ("interrupt_without_trfin", flow, 0x40, 0),
    ):
        yield Case(name, {15: (raw, control)}, [
            *ack(15, 1), *attempt(15, raw, control, extended=extended),
        ], extended)
    yield Case("overwrite_during_copy", {15: (session, 0x41)}, [
        *ack(15, 1), *attempt(15, session, replacement=flow, during_copy=True),
        *attempt(15, flow),
    ], overwrite=Overwrite(15, flow, 0x41, during_copy=True), deliveries=(session, flow))
    yield Case("overwrite_after_status_read", {15: (session, 0x41)}, [
        *ack(15, 1), *attempt(15, session, replacement=flow),
    ], overwrite=Overwrite(15, flow, 0x45, during_copy=False), deliveries=(session,))

    for can_id, index in ((0x7E1, 0), (0x7DF, 1), (0x602, 2)):
        raw = raw_slot(can_id, 8, "F011223344556677", 0x1380)
        endpoint = ("oem_diagnostic", COPY + 6, index) if index < 2 else (
            "oem_monitor", 0x808DFC, 1, *raw[6:14],
        )
        yield Case(f"oem_{can_id:03x}", {15: (raw, 0x41)}, [
            *ack(15, 1), *attempt(15, raw), ("lookup_match", index), endpoint,
        ])
    short = raw_slot(0x602, 3, "F01122", 0x1380)
    yield Case("oem_monitor_short_dlc", {15: (short, 0x41)}, [
        *ack(15, 1), *attempt(15, short), ("lookup_match", 2),
    ])

    if with_dispatch:
        read = raw_slot(0x732, 4, "0317ff00", 0x1310)
        yield Case("paired_retry_new_frame", {14: (session, 0x41), 15: (flow, 0x41)}, [
            *ack(15, 3), *attempt(15, flow, replacement=read, during_copy=True),
            *attempt(15, read), *ack(14, 3), *attempt(14, session),
        ], overwrite=Overwrite(15, read, 0x41, during_copy=True),
                   paired_slots=3, paired_deliveries=(session, flow, read))
        yield Case("paired_overwrite_before_ack", {14: (session, 0x41), 15: (flow, 0x41)}, [
            *ack(15, 3), ("overwrite", 15), *attempt(15, read, 0x45),
            *ack(14, 3), *attempt(14, session),
        ], overwrite=Overwrite(15, read, 0x45, during_copy=False, before_attempt=True),
                   paired_slots=3, paired_deliveries=(session, flow))
        yield Case("paired_only_one_eligible", {14: (session, 0x45), 15: (flow, 0x41)}, [
            *ack(15, 3), *attempt(15, flow), *ack(14, 2), *attempt(14, session, 0x45),
        ], paired_slots=1, paired_deliveries=(flow,))


RX_RESIDENT_ROOTS = (
    "rbm_h03_dtc_rx_hook",
    "rbm_h03_dtc_rx_dispatch_hook",
    "lfj8_h03_mmio",
    "lfj8_h03_tml0ct_m32r",
)


def link_resident_target(run, work, gcc, compile_flags, sources, libraries):
    objects = []
    for source in ("fixture.S", *sources):
        obj = Path(source).stem + ".o"
        run(gcc, *TARGET, *compile_flags, "-c", source, "-o", obj)
        objects.append(obj)

    # The indirect epoch adapter has local linkage. Keeping it as a
    # separate root avoids pulling the foreground via the const ops table.
    (work / "closure.ld").write_text(
        "SECTIONS { .text.native_rx_epoch : { KEEP(*(.text.native_rx_epoch)) } }\n", encoding="ascii")
    roots = tuple(f"-Wl,--undefined={root}" for root in RX_RESIDENT_ROOTS)
    objcopy = gcc.with_name(f"m32r-elf-objcopy{gcc.suffix}")
    closure_objects = []
    for obj in objects[1:]:
        stripped = f"rx-{obj}"
        run(objcopy, "--strip-debug", obj, stripped)
        closure_objects.append(stripped)
    run(gcc, *TARGET, "-r", "-nostdlib", "-Wl,--gc-sections,-T,closure.ld",
        *roots, *closure_objects, *libraries, "-o", "rx-closure.o")
    closure = read_elf(work / "rx-closure.o", 1)
    missing = {name for name, symbol in closure["symbols"].items() if symbol["section"] == 0}
    if missing != {"h03_dtc_rx_entry", "h03_dtc_rx_resume"}:
        raise ValueError(f"Unexpected resident RX references: {sorted(missing)}")
    sections = {s["name"]: s["size"] for s in alloc_sections(closure) if s["type"] != 8}
    if ".text.native_rx_epoch" not in sections:
        raise ValueError("Resident RX epoch adapter was not linked")
    (work / "rx-sections.ld").write_text(
        "".join(f"rx_input_{index}_start = .;\n*(\"{section}\")\nrx_input_{index}_end = .;\n"
                for index, section in enumerate(sections)), encoding="ascii")
    shutil.copyfile(HERE / "h03_dtc_rx_resident.ld", work / "fixture.ld")
    link_flags = (*TARGET, "-nostdlib", "-Wl,--gc-sections,-T,fixture.ld", *roots)
    run(gcc, *link_flags, *objects, *libraries, "-o", "fixture.elf")
    low = (
        f'.incbin "h03.dat",0,{HOOK_SITE:#x}\n'
        '    bra.l rbm_h03_dtc_rx_hook\n'
        f'    .incbin "h03.dat",{HOOK_RESUME:#x},{DISPATCH_SITE - HOOK_RESUME:#x}\n'
        '    bl.l rbm_h03_dtc_rx_dispatch_hook\n'
        f'    .incbin "h03.dat",{DISPATCH_SITE + 4:#x},{RESIDENT_START - DISPATCH_SITE - 4:#x}'
    )
    patched = FIXTURE.replace('.incbin "h03.dat",0,0x6000', low)
    (work / "fixture-patched.S").write_text(patched, encoding="ascii")
    run(gcc, *TARGET, *compile_flags, "-c", "fixture-patched.S", "-o", "fixture-patched.o")
    run(gcc, *link_flags, "fixture-patched.o", *objects[1:], *libraries, "-o", "fixture-patched.elf")
    return sections


def verify_resident_target(path, symbols, end, sections, rom):
    elf = read_elf(path, 2)
    linked = {s["name"]: s for s in elf["sections"]}
    resident = linked[".resident_rx"]
    if (resident["address"], resident["size"]) != (RESIDENT_START, APP_START - RESIDENT_START):
        raise ValueError("The linked resident RX sector differs from the H03 geometry")
    for name, start, limit in ((".oem_low", 0, RESIDENT_START), (".oem_app", APP_START, FLASH_LIMIT)):
        if (linked[name]["address"], linked[name]["data"]) != (start, rom[start:limit]):
            raise ValueError(f"Linked fixture changed OEM bytes in {name}")
    if resident["data"][end - RESIDENT_START:] != b"\xff" * (APP_START - end):
        raise ValueError("Bytes after resident RX code do not preserve H03 sector fill")
    if any(s["type"] in (4, 9) and s["size"] for s in elf["sections"]):
        raise ValueError("The linked resident RX fixture contains unresolved relocations")
    for index, (section, size) in enumerate(sections.items()):
        start = symbols.get(f"rx_input_{index}_start", 0)
        stop = symbols.get(f"rx_input_{index}_end", 0)
        # A final input range can be larger because of alignment or another
        # archive member using the same section name, but cannot shrink.
        if not RESIDENT_START <= start <= stop <= end or stop - start < size:
            raise ValueError(f"Resident RX input section missing from final link: {section}")

    local_names = (*RX_RESIDENT_ROOTS, "rbm_h03_dtc_rx_begin", "rbm_h03_dtc_rx_observe",
                   "lfj8_h03_can_owner_rx_epoch", "native_rx_epoch", "native_owner_ops",
                   "lfj8_h03_sensor_clock_ready_locked", "lfj8_h03_sensor_clock_registers_match")
    if any(not RESIDENT_START <= symbols.get(name, 0) < end for name in local_names):
        raise ValueError("A required RX symbol is not resident")

    def words(name, count):
        start = symbols[name] - RESIDENT_START
        raw = resident["data"][start:start + 4 * count]
        return tuple(int.from_bytes(raw[offset:offset + 4], "big") for offset in range(0, len(raw), 4))

    epoch, poll, context = words("native_owner_ops", 3)
    if (epoch, poll, context) != (symbols["native_rx_epoch"], symbols["native_poll_owner"],
                                  symbols["h03_can_owner"]):
        raise ValueError("The linked CAN-owner operations do not match the native binding")
    foreground = linked[".text"]
    upper_start = foreground["address"]
    upper_end = max(linked[name]["address"] + linked[name]["size"]
                    for name in (".text", ".rodata") if name in linked)
    if not 0x101000 <= upper_start <= poll < upper_start + foreground["size"]:
        raise ValueError("Foreground code was pulled into the resident RX sector")
    bss = linked[".bss"]
    if (bss["type"] != 8 or bss["address"] < upper_end or
            any(not bss["address"] <= symbols[name] < bss["address"] + bss["size"]
                for name in ("irq_target", "fixture_target", "h03_can_owner", "rbm_h03_tml0_1mhz_qualified"))):
        raise ValueError("The fixture RX binding uses storage outside simulator BSS")
    mmio = words("lfj8_h03_mmio", 7)
    if len(mmio) != 7 or mmio[0] != 0 or any(not RESIDENT_START <= addr < end for addr in mmio[1:]):
        raise ValueError("An indirect RX MMIO operation is not resident")
    (path.parent / "erased-foreground.dat").write_bytes(b"\xff" * (upper_end - upper_start))
    return {
        "retained_read_only_input_sections": sorted(sections),
        "resident_symbols": {name: f"0x{symbols[name]:06X}" for name in local_names},
        "mmio_entry_addresses": [f"0x{addr:06X}" for addr in mmio[1:]],
        "fixture_foreground_poll": f"0x{poll:06X}",
        "fixture_foreground_code": [f"0x{upper_start:06X}", f"0x{upper_end:06X}"],
        "fixture_irq_pointer": f"0x{symbols['irq_target']:06X}",
        "resident_sector_sha256": sha256(resident["data"]).hexdigest(),
    }


def verify_linked_rx_words(work, rom, patches):
    def loadable(name):
        return {s["name"]: (s["address"], s["data"])
                for s in alloc_sections(read_elf(work / name, 2))}

    stock = loadable("fixture.elf")
    expected = bytearray(rom[:RESIDENT_START])
    for site, word in patches.items():
        expected[site:site + 4] = word.to_bytes(4, "big")
    stock[".oem_low"] = (0, bytes(expected))
    if loadable("fixture-patched.elf") != stock:
        raise ValueError("Resident RX link changed bytes outside its two validated branches")


def build_hook_fixture(run, work, gcc, rom, with_dispatch=False, resident=False, target=False,
                       can_owner_dir=None):
    sites = [(HOOK_SITE, HOOK_STOCK, "rbm_h03_dtc_rx_hook", 0xFF000000)]
    if with_dispatch:
        sites.append((DISPATCH_SITE, DISPATCH_STOCK, "rbm_h03_dtc_rx_dispatch_hook", 0xFE000000))
    for site, instruction, _, _ in sites:
        if rom[site:site + 4] != instruction:
            raise ValueError(f"The H03 instruction at {site:#x} differs")
    sources = ("h03_dtc_rx_hook.S", "h03_dtc_rx_hook_fixture.c",
               "lfj8_h03_dtc_rx_queue.c", "lfj8_h03_dtc_can.c")
    diagnostics = ROOT / "diagnostics"
    header_dirs = [HERE, diagnostics]
    if target:
        sources += ("lfj8_h03_dtc_target.c", "lfj8_h03_dtc_foreground.c", "lfj8_h03_mmio.c",
                    "lfj8_donor_io.c", "lfj8_h03_can13.c", "lfj8_h03_torque_can.c",
                    "lfj8_h03_torque.c", "lfj8_chery_tx.c", "lfj8_bridge.c")
        header_dirs.append(ROOT / "controller/vendor/toyota/include")
    for name in sources:
        shutil.copyfile(HERE / name, work / name)
    if target:
        diagnostic_sources = ("chery_dtc.c", "chery_dtc_link.c", "chery_dtc_can.c")
        for name in diagnostic_sources:
            shutil.copyfile(diagnostics / name, work / name)
        sources += diagnostic_sources
    for directory in header_dirs:
        for path in directory.glob("*.h"):
            shutil.copyfile(path, work / path.name)
    (work / "fixture.ld").write_text(RESIDENT_LAYOUT if resident else HOOK_LAYOUT, encoding="ascii")
    defines = ["-DRBM_DTC_RX_HOOK_FIXTURE"]
    roots = []
    if with_dispatch:
        defines.append("-DRBM_DTC_RX_DISPATCH_FIXTURE")
        roots.append("-Wl,--undefined=rbm_h03_dtc_rx_dispatch_hook")
    if target:
        defines.append("-DRBM_DTC_RX_TARGET_FIXTURE")
    if can_owner_dir:
        for name in ("lfj8_h03_can_owner.c", "lfj8_h03_can_owner.h", "lfj8_donor_io.c", "lfj8_donor_io.h"):
            shutil.copyfile(can_owner_dir / name, work / name)
        for name in ("lfj8_h03_dtc_native.c", "lfj8_h03_atf_tml0.c"):
            shutil.copyfile(HERE / name, work / name)
        sources += ("lfj8_h03_can_owner.c", "lfj8_h03_dtc_native.c", "lfj8_h03_atf_tml0.c")
        defines.append("-DRBM_DTC_RX_CAN_OWNER_FIXTURE")
    if resident:
        if int.from_bytes(rom[CAN0_IRQ_TABLE_WORD:CAN0_IRQ_TABLE_WORD + 4], "big") != CAN0_IRQ_ENTRY:
            raise ValueError("Unexpected H03 CAN0 IRQ table entry")
        geometry = (RESIDENT_START.to_bytes(4, "big") + (APP_START - 2).to_bytes(4, "big")
                    + APP_START.to_bytes(4, "big"))
        if rom[RESIDENT_GEOMETRY:RESIDENT_GEOMETRY + len(geometry)] != geometry:
            raise ValueError("Unexpected H03 geometry for the resident RX sector")
        if rom[RESIDENT_START:APP_START] != b"\xff" * (APP_START - RESIDENT_START):
            raise ValueError("The H03 resident RX sector is not empty")
        defines.append("-DRBM_DTC_RX_RESIDENT_FIXTURE")
    compile_flags = ("-Os", "-g", "-std=c11", "-ffunction-sections", "-fdata-sections", *defines, "-I.")
    libraries = ("-Wl,--start-group", "-lc", "-lgcc", "-Wl,--end-group")
    resident_target = resident and target
    if resident_target:
        sections = link_resident_target(run, work, gcc, compile_flags, sources, libraries)
    else:
        run(gcc, *TARGET, *compile_flags, *roots, "-nostdlib", "-Wl,--gc-sections,-T,fixture.ld",
            "fixture.S", *sources, *libraries, "-o", "fixture.elf")
    nm = gcc.with_name(f"m32r-elf-nm{gcc.suffix}")
    symbols = {word[2]: int(word[0], 16) for word in
               (line.split() for line in run(nm, "--defined-only", "fixture.elf").decode().splitlines())
               if len(word) == 3}
    minimum = RESIDENT_START if resident else 0x101000
    limit = symbols["rx_resident_end"] if resident else 0x1000000
    if resident and not RESIDENT_START < limit <= APP_START:
        raise ValueError("Resident RX code and constants exceed the lower Flash sector")
    patches = {}
    for site, _, symbol, opcode in sites:
        target = symbols.get(symbol, 0)
        displacement = target - site
        if not minimum <= target < limit or displacement % 4 or not 0 <= displacement < (1 << 25):
            raise ValueError(f"The branch to {symbol} does not target the simulator fixture area")
        patches[site] = opcode | (displacement // 4)
    binding = None
    if resident_target:
        verify_linked_rx_words(work, rom, patches)
        binding = verify_resident_target(work / "fixture.elf", symbols, limit, sections, rom)
        binding["rx_branches_resolved_by_linker"] = True
    return patches, limit, binding


def expected_observation(case, with_dispatch=False):
    attempts = sum(event[0] == "pre_clear" for event in case.expected)
    deliveries = case.deliveries
    rejected = attempts - len(deliveries)
    if with_dispatch and case.paired_deliveries is not None:
        deliveries = case.paired_deliveries
        rejected = attempts + 2 - case.paired_slots.bit_count() - len(deliveries)
    queued = [("observer", attempts, 0, len(deliveries), rejected)]
    if with_dispatch:
        queued.append(("dispatch", int(bool(case.slots)), case.paired_slots, case.paired_slots.bit_count()))
    for raw in deliveries:
        dlc = raw[5] & 0xf
        data = raw[6:6 + dlc].ljust(8, b"\x00")
        queued.append(("delivery", 7, int.from_bytes(raw[14:], "big"), 0x732, dlc, *data))
    return queued


def render_events(events):
    return [" ".join((event, *(f"{value:x}" for value in values))) for event, *values in events]


def split_stack_observation(events):
    depths = [row[1] for row in events if row[0] == "stack"]
    if len(depths) != 1 or not 0 < depths[0] < STACK_PROBE_BYTES:
        raise ValueError(f"The observed stack depth is missing or exceeds the fixture: {depths}")
    return [row for row in events if row[0] != "stack"], depths[0]


def compare_high_word(run, work, debugger, case, patches, with_dispatch=False):
    stock = simulate(run, work, debugger, case, compare_hook=True,
                     compare_dispatch=with_dispatch, high_probe=True)
    wrapped = simulate(run, work, debugger, case, compare_hook=True, patches=patches,
                       compare_dispatch=with_dispatch, high_probe=True)
    original = next(row[1] for row in stock if row[0] == "accumulator")
    returned = next(row[1] for row in wrapped if row[0] == "accumulator")
    operand = [row for row in wrapped if row[0] == "restore_high"]
    restores = 2 if with_dispatch else 1
    if not original or operand != [("restore_high", original, MVTACHI_R0)] * restores or returned != original:
        raise ValueError(f"Unexpected high accumulator restore: {original:#x}, {operand}, {returned:#x}")
    observer_events = ("restore_high", "stack", "observer", "delivery", "dispatch")
    if ([row for row in stock if row[0] not in observer_events] !=
            [row for row in wrapped if row[0] not in observer_events]):
        raise ValueError("The high accumulator probe changed the OEM path or context")
    return {"original": f"0x{original:08X}", "restore_operand": f"0x{operand[0][1]:08X}",
            "returned": f"0x{returned:08X}"}


def compare_resident_bypass(run, work, debugger, patches, target=False):
    case = next(case for case in cases(True) if case.name == "paired_retry_new_frame")
    (work / "erased-app.dat").write_bytes(b"\xff" * (FLASH_LIMIT - APP_START))
    programming = f"set {{unsigned char}}{PROGRAMMING_MODE:#x} = 1"
    contexts = {
        "programming": (programming,),
        "virtual_flash_register_shadow": (
            f"set {{unsigned char}}{FCNT1:#x} = 1",
            f"set {{unsigned short}}{FESBANK1:#x} = 0x8020",
        ),
        "programming_with_erased_application": (
            programming, f"restore erased-app.dat binary {APP_START:#x}",
        ),
    }
    callback_trace = [
        command
        for label in ("rbm_h03_dtc_rx_begin", "rbm_h03_dtc_rx_observe")
        for command in at(f"*{label}", trace("callback", "$pc"))
    ] if target else []
    checks = {}
    for name, setup in contexts.items():
        stock = simulate(run, work, debugger, case, compare_hook=True, compare_dispatch=True,
                         setup=setup, target=target)
        wrapped = simulate(run, work, debugger, case, compare_hook=True, compare_dispatch=True,
                           patches=patches, setup=(*setup, *callback_trace), target=target)
        stock, stock_depth = split_stack_observation(stock)
        wrapped, wrapped_depth = split_stack_observation(wrapped)
        empty = [("target_queue", 0, 0)] if target else [("observer", 0, 0, 0, 0), ("dispatch", 0, 0, 0)]
        attempts = sum(event[0] == "pre_clear" for event in stock)
        if stock[-len(empty):] != empty or attempts != 3 or wrapped != stock:
            raise ValueError(f"Resident RX bypass changed the original path in {name}")
        checks[name] = {"stock_attempts": attempts, "observer_calls": 0, "dispatch_calls": 0,
                        "stock_stack_bytes_written": stock_depth,
                        "hook_stack_bytes_written": wrapped_depth}
    return checks


def compare_active_resident_rx(run, work, debugger, patches, foreground_start):
    case = next(case for case in cases(True) if case.name == "paired_retry_new_frame")
    ordinary = simulate(run, work, debugger, case, compare_hook=True, compare_dispatch=True,
                        patches=patches, target=True)
    # Admission and the pointer setup have already run at fixture_target_ready.
    # Keep that RAM state and erase both higher code ranges before entering CAN0.
    setup = (f"restore erased-app.dat binary {APP_START:#x}",
             f"restore erased-foreground.dat binary {foreground_start}")
    isolated = simulate(run, work, debugger, case, compare_hook=True, compare_dispatch=True,
                        patches=patches, target=True, setup=setup)
    if isolated != ordinary:
        raise ValueError("Admitted resident RX depends on application or fixture foreground code")
    return {"case": case.name, "application_erased_after_admission": True,
            "fixture_foreground_erased_after_admission": True,
            "deliveries": sum(row[0] == "delivery" for row in isolated)}


def probe_native_policy(run, work, debugger, entry, registers, stops, *, setup=(), fields=()):
    commands = ["set confirm off", "target sim --memory-size 16M", "load",
                "tbreak *fixture_ready", "run", *setup]
    arguments = (entry, *(registers.get(reg, 0) for reg in (0, 1, 5, 8, 9)))
    commands += [f"set {{unsigned int}}((char*)&fixture_update_arguments+{index * 4}) = {value:#x}"
                 for index, value in enumerate(arguments)]
    commands += [f"tbreak *{stop:#x}" for stop in stops]
    commands += ["continue", trace("policy", "$pc", *fields)]
    results = [tuple(int(value, 16) for value in line.split()[2:])
               for line in run_probe(run, work, debugger, commands).splitlines()
               if line.startswith("RX policy ")]
    if len(results) != 1 or results[0][0] not in stops:
        raise ValueError(f"Unexpected H03 policy stop at {entry:#x}: {results}")
    return results[0]


def compare_update_boundary(run, work, debugger):
    def admitted(entry, accept, deny, registers):
        (stop,) = probe_native_policy(run, work, debugger, entry, registers, (accept, deny))
        return stop == accept

    writes = {}
    for start in (HOOK_SITE, DISPATCH_SITE, RESIDENT_START, APP_START - 1, APP_START):
        accepted = admitted(INSTALL_BEGIN, INSTALL_ACCEPT, INSTALL_DENY, {0: 4, 1: 0, 5: start})
        if accepted != (start == APP_START):
            raise ValueError(f"Unexpected H03 write boundary decision for {start:#x}")
        writes[f"0x{start:06X}"] = accepted

    erases = {}
    for start, end in ((0, 0x002000), (0x004000, RESIDENT_START), (RESIDENT_START, APP_START),
                       (APP_START, FLASH_LIMIT)):
        accepted = admitted(ERASE_POLICY, ERASE_CALL, ERASE_DENIED, {8: start, 9: end})
        if accepted != (start == APP_START):
            raise ValueError(f"Unexpected H03 erase boundary decision for {start:#x}..{end:#x}")
        erases[f"0x{start:06X}..0x{end:06X}"] = accepted
    return {"write_start_4_bytes": writes, "erase_range_end_exclusive": erases,
            "drivers_executed": False}


def probe_lower_page_selections(run, work, debugger):
    selections = {}
    for address in (CAN0_IRQ_TABLE_WORD, HOOK_SITE, DISPATCH_SITE, RESIDENT_START):
        page = address & ~0xFFF
        bank = page >> 12
        setup = (f"set {{unsigned short}}{VIRTUAL_SELECT:#x} = {bank:#x}",
                 "set {unsigned int}0x809f9c = 0x809f9c")
        _, control, selection = probe_native_policy(
            run, work, debugger, VIRTUAL_CONFIG, {0: 0x807000}, (VIRTUAL_CONFIG_DONE,),
            setup=setup, fields=(f"*(unsigned char*){FCNT1:#x}", f"*(unsigned short*){FESBANK1:#x}"),
        )
        if (control, selection) != (1, 0x8000 | bank):
            raise ValueError(f"Unexpected Virtual Flash register shadow for RX page {page:#x}")
        selections[f"0x{page:06X}"] = f"0x{selection:04X}"
    return selections


def check_native_t6(run, work, debugger, patches, case):
    start_us = 0xFFFFFFFE
    start = (
        "set fixture_t6_action = 1", "set fixture_t6_initial = 0xffffffff",
        f"set {{unsigned int}}0x8003e0 = {start_us:#x}",
    )
    observation = trace(
        "t6", "fixture_t6_started", "fixture_t6_clock.active", "fixture_t6_clock.tick",
        "fixture_t6_clock.remainder", "h03_can_owner.grant",
        "broker.diagnostic.link.session_steps_left", "broker.diagnostic.link.session.mode_bits",
    )

    def turn(elapsed, *before):
        return (
            f"set {{unsigned int}}0x8003e0 = {(start_us + elapsed) & 0xffffffff:#x}",
            f"set {{unsigned short}}0x801008 = {0x1400 + elapsed // 2:#x}",
            *before, "tbreak *fixture_target_done", "continue", observation,
        )

    def run_clock(startup=start, steps=(), *, with_foreground=True):
        return simulate(
            run, work, debugger, case, compare_hook=True, patches=patches, compare_dispatch=True,
            target=True, foreground=with_foreground, target_start=startup, target_steps=steps,
        )

    steps = [observation, *turn(2, "set {unsigned char}0x80105d = 0x81"),
             *turn(3, "set fixture_t6_action = 1")]
    expected = [
        ("t6", 1, 1, 0xFFFFFFFF, 0, 1, 9, 0x90),
        ("t6", 1, 1, 0xFFFFFFFF, 4, 1, 9, 0x90),
        ("t6", 0, 1, 0, 1, 1, 9, 0x90),
    ]
    for event in range(9):
        tick = 64 + 128 * event
        elapsed = ((tick + 1) * 5 + 1) // 2
        steps.extend(turn(elapsed))
        expected.append(("t6", 0, 1, tick, elapsed * 2 % 5, 1, 8 - event,
                         0x90 if event < 8 else 0x9F))
    steps.extend(turn(elapsed + 1000))
    steps.extend(turn(elapsed + 2001))
    expected += [
        ("t6", 0, 1, tick + 400, elapsed * 2 % 5, 1, 0, 0x9F),
        ("t6", 0, 0, tick + 400, elapsed * 2 % 5, 0, 0, 0x9F),
    ]
    actual = [row for row in run_clock(steps=steps) if row[0] == "t6"]
    if actual != expected:
        raise ValueError(f"T6 clock did not deliver the expected phase/expiry: {actual}")

    refused = {
        "zero_denominator": ("set fixture_t6_config.period_us_denominator = 0",),
        "sub_microsecond_period": ("set fixture_t6_config.period_us_numerator = 1",),
        "zero_gap": ("set fixture_t6_config.max_sample_gap_us = 0",),
        "half_range_gap": ("set fixture_t6_config.max_sample_gap_us = 0x80000000",),
        "scaled_gap_overflow": (
            "set fixture_t6_config.period_us_denominator = 0x200000",
            "set fixture_t6_config.period_us_numerator = 0x200000",
            "set fixture_t6_config.max_sample_gap_us = 0x10000",
        ),
        "unqualified_timer": ("set {unsigned char}0x8003eb = 0",),
    }
    for name, commands in refused.items():
        refused_trace = run_clock(start + commands, (observation,), with_foreground=False)
        if [row for row in refused_trace if row[0] == "t6"] != [("t6", 0, 0, 0, 0, 0, 0, 0x9F)]:
            raise ValueError(f"Invalid T6 setup admitted CAN: {name}")

    loss = (
        *turn(2, "set {unsigned char}0x8003eb = 0"),
        *turn(3, "set {unsigned char}0x8003eb = 1",
              "set rbm_h03_tml0_1mhz_qualified = 1", "set h03_can_owner.setup_generation = 8",
              "set {unsigned char}0x80105d = 0"),
        *turn(4, "set fixture_t6_action = 1"),
    )
    actual_loss = [row for row in run_clock(steps=loss) if row[0] == "t6"]
    if actual_loss != [
        ("t6", 1, 0, 0xFFFFFFFF, 0, 0, 0, 0x9F),
        ("t6", 1, 0, 0xFFFFFFFF, 0, 0, 0, 0x9F),
        ("t6", 1, 1, 0xFFFFFFFF, 0, 1, 0, 0x9F),
    ]:
        raise ValueError(f"T6 clock resumed without qualification and a new start: {actual_loss}")
    return {"synthetic_period_us": [5, 2], "session_release_events": 9,
            "tml0_and_t6_wrap": True, "live_rephase_refused": True,
            "excessive_gap_revoked": True, "explicit_restart_after_clock_loss": True,
            "startup_refusals": list(refused)}


def check_target_foreground(run, work, debugger, patches, with_can_owner=False):
    case = next(case for case in cases() if case.name == "rx14_session")
    trace_events = simulate(run, work, debugger, case, compare_hook=True, patches=patches,
                            compare_dispatch=True, target=True, foreground=True)
    reply = [row for row in trace_events if row[0] == "foreground"]
    expected = (1, 1, 0, 0x80)
    if len(reply) != 1 or reply[0][1:5] != expected:
        raise ValueError(f"The diagnostic request did not reach CAN13 TX: {reply}")
    slot = reply[0][5:]
    can_id = ((slot[0] & 0x1F) << 6) | (slot[1] & 0x3F)
    if (can_id, slot[5], slot[6:14]) != (0x722, 8, (2, 0x50, 0x86, 0, 0, 0, 0, 0)):
        raise ValueError(f"Unexpected native diagnostic reply in slot 13: {slot}")

    (work / "erased-app.dat").write_bytes(b"\xff" * (FLASH_LIMIT - APP_START))
    bypass = {
        "unbound": ("set irq_target = 0",),
        "programming_with_erased_application": (
            f"set {{unsigned char}}{PROGRAMMING_MODE:#x} = 1",
            f"restore erased-app.dat binary {APP_START:#x}",
        ),
    }
    for name, setup in bypass.items():
        stock = simulate(run, work, debugger, case, compare_hook=True, compare_dispatch=True,
                         target=True, setup=setup)
        wrapped = simulate(run, work, debugger, case, compare_hook=True, patches=patches,
                           compare_dispatch=True, target=True, setup=setup)
        if split_stack_observation(wrapped)[0] != split_stack_observation(stock)[0]:
            raise ValueError(f"The target altered the OEM receive path in {name}")
    result = {"request_id": "0x732", "reply_id": f"0x{can_id:03X}", "reply": bytes(slot[6:14]).hex(),
              "consumed": True, "tx13_submission": True, "oem_bypass_comparisons": list(bypass)}
    if with_can_owner:
        bad_clock = simulate(
            run, work, debugger, case, compare_hook=True, patches=patches, compare_dispatch=True,
            target=True, foreground=True, setup=("set {unsigned char}0x8003eb = 0",),
        )
        queue_after_loss = [row for row in bad_clock if row[0] == "target_queue"]
        tx_after_loss = [row[1:5] for row in bad_clock if row[0] == "foreground"]
        excluded = {"stack", "target_queue", "delivery", "foreground"}
        if (queue_after_loss != [("target_queue", 0, 0)] or tx_after_loss != [(0, 0, 0, 0x40)] or
                [row for row in bad_clock if row[0] not in excluded] !=
                [row for row in trace_events if row[0] not in excluded]):
            raise ValueError(f"Loss of native clock changed OEM RX or admitted DTC: {queue_after_loss}, {tx_after_loss}")
        both = next(case for case in cases(True) if case.name == "both_slots_pending")
        events = simulate(run, work, debugger, both, compare_hook=True, patches=patches,
                          compare_dispatch=True, target=True, foreground=True, reset_owner=True)
        warm = simulate(run, work, debugger, both, compare_hook=True, patches=patches,
                        compare_dispatch=True, target=True, foreground=True,
                        reset_owner=True, warm_rebind=True)
        warm_step = [row for row in warm if row[0] == "warm_rebind"]
        warm_next = [row for row in warm if row[0] == "new_generation"]
        if (warm_step != [("warm_rebind", 1, 7, 0, 0, 0, 0)] or
                [row[1:5] for row in warm_next] != [(1, 8, 0, 0)]):
            raise ValueError(f"Rebinding admitted the old epoch or lost the new one: {warm_step}, {warm_next}")
        before = [row[1:5] for row in events if row[0] == "foreground"]
        after = [row for row in events if row[0] == "new_generation"]
        if before != [(1, 1, 1, 0x80)] or after != [("new_generation", 1, 8, 0, 0, 0x40, 0x9F)]:
            raise ValueError(f"The old queue or diagnostic session survived CAN reset: {before}, {after}")
        result["native_clock_mismatch_rejects_rx_and_tx"] = True
        result["native_warm_rebind_requires_new_generation"] = True
        result["native_owner_restart"] = {
            "new_generation": 8, "old_frames_retained": 0, "default_session_mode": "0x9F",
            "post_reset_tx13_submission": False,
        }
        result["native_t6_clock"] = check_native_t6(run, work, debugger, patches, case)
    return result


def check(base, gcc, with_rx_hook=False, *, with_rx_dispatch=False, resident=False, target=False,
          can_owner_dir=None):
    with_rx_dispatch = with_rx_dispatch or resident or target
    with_rx_hook = with_rx_hook or with_rx_dispatch
    if resident and target and can_owner_dir is None:
        can_owner_dir = HERE
    identity = identify_h03(base)
    rom = base.read_bytes()
    if sha256(rom).hexdigest() != identity["sha256"]:
        raise ValueError("H03 changed while the fixture was being prepared")
    with TemporaryDirectory(prefix="rbm-h03-dtc-basiccan-") as directory:
        work = Path(directory)

        def run(*args):
            return subprocess.run([str(arg) for arg in args], cwd=work, check=True,
                                  capture_output=True, timeout=30).stdout

        if run(gcc, "-dumpmachine").strip() != b"m32r-elf":
            raise ValueError("A bare-metal M32R compiler is required")
        debugger = gcc.with_name(f"m32r-elf-gdb{gcc.suffix}")
        version = run(gcc, "--version").decode().splitlines()[0]
        (work / "h03.dat").write_bytes(rom)
        (work / "fixture.S").write_text(FIXTURE, encoding="ascii")
        patches = {}
        if with_rx_hook:
            patches, code_end, binding = build_hook_fixture(run, work, gcc, rom, with_rx_dispatch,
                                                           resident, target, can_owner_dir)
        else:
            (work / "fixture.ld").write_text(LAYOUT, encoding="ascii")
            run(gcc, "-m32r", "-Wa,-EB", "-nostdlib", "-Wl,-T,fixture.ld", "fixture.S", "-o", "fixture.elf")
        results = {}
        hook_cases = {}
        for case in cases(with_rx_dispatch):
            stock = simulate(run, work, debugger, case, compare_hook=with_rx_hook,
                             compare_dispatch=with_rx_dispatch, target=target)
            if target and stock[0:1] != [("startup", 1, 7, 0)]:
                raise ValueError(f"{case.name}: CAN foreground did not admit the fresh empty queue")
            if with_rx_hook:
                stock, stock_depth = split_stack_observation(stock)
            observer_events = ("observer", "context", "accumulator", "dispatch", "dispatch_entry",
                               "target_queue", "startup")
            actual = [event for event in stock if event[0] not in observer_events]
            pending = slot_mask(case.overwrite.slot) if case.overwrite else 0
            expected = [*case.expected, ("return", 1, 0x9FFFFC, 8, 9, 10, pending)]
            if actual != expected:
                raise ValueError(f"{case.name}:\nexpected {expected}\nobserved {actual}")
            results[case.name] = render_events(actual)
            if with_rx_hook:
                empty = [("observer", 0, 0, 0, 0)]
                if with_rx_dispatch:
                    empty.append(("dispatch", 0, 0, 0))
                if target:
                    empty = [("target_queue", 0, 0)]
                if stock[-len(empty):] != empty:
                    raise ValueError(f"{case.name}: the unmodified H03 called the observer")
                wrapped = simulate(run, work, debugger, case, compare_hook=True, patches=patches,
                                   compare_dispatch=with_rx_dispatch, target=target)
                wrapped, wrapped_depth = split_stack_observation(wrapped)
                expected_tail = expected_observation(case, with_rx_dispatch)
                if target:
                    expected_tail = [("target_queue", *expected_tail[0][-2:]), *expected_tail[2:]]
                expected_hook = [*stock[:-len(empty)], *expected_tail]
                if wrapped != expected_hook:
                    raise ValueError(f"{case.name}, with hook:\nexpected {expected_hook}\nobserved {wrapped}")
                hook_cases[case.name] = {
                    "observer_and_deliveries": render_events(wrapped[-len(expected_tail):]),
                    "stock_stack_bytes_written": stock_depth,
                    "hook_stack_bytes_written": wrapped_depth,
                }
        if target:
            dialogue = check_target_foreground(run, work, debugger, patches, can_owner_dir is not None)
        elif with_rx_hook:
            single_rx = next(case for case in cases() if case.name == "rx14_session")
            high_word = compare_high_word(run, work, debugger, single_rx, patches, with_rx_dispatch)
        if resident:
            bypass = compare_resident_bypass(run, work, debugger, patches, target)
            update = compare_update_boundary(run, work, debugger)
            lower_pages = probe_lower_page_selections(run, work, debugger)
            if binding is not None:
                foreground_start = binding["fixture_foreground_code"][0]
                binding["active_capture_with_erased_upper_code"] = compare_active_resident_rx(
                    run, work, debugger, patches, foreground_start)
    result = {
        "base": identity,
        "compiler": version,
        "entry": "0x004724" if with_rx_hook else "0x0013F0",
        "executed_cases": len(results),
        "peripheral_model": "RAM shadows with explicit CAN0SLIST W0C and scripted frame replacement",
        "cases": results,
        "hardware_executed": False,
        "flashable_image": None,
    }
    if with_rx_hook:
        result["simulator_hook"] = {
            "site": f"0x{HOOK_SITE:06X}",
            "resume": f"0x{HOOK_RESUME:06X}",
            "matched_context": REGISTERS,
            "paired_cases": len(hook_cases),
            "all_observations": hook_cases,
        }
        if not target:
            result["simulator_hook"]["high_accumulator_probe"] = high_word
    if with_rx_dispatch:
        result["simulator_hook"]["dispatch_site"] = f"0x{DISPATCH_SITE:06X}"
        result["simulator_hook"]["dispatch_entry"] = "0x0013F0"
    if resident:
        result["resident_layout"] = {
            "start": f"0x{RESIDENT_START:06X}",
            "code_and_constants_end_exclusive": f"0x{code_end:06X}",
            "application_start": f"0x{APP_START:06X}",
            "code_and_constants_bytes": code_end - RESIDENT_START,
            "oem_can0_irq_table": f"0x{CAN0_IRQ_TABLE_WORD:06X}",
            "oem_can0_irq_entry": f"0x{CAN0_IRQ_ENTRY:06X}",
            "patched_words": {
                f"0x{site:06X}": {
                    "stock": rom[site:site + 4].hex(),
                    "branch": f"{word:08x}",
                    "target": f"0x{site + 4 * (word & 0xFFFFFF):06X}",
                }
                for site, word in patches.items()
            },
            "bypass_cases": bypass,
            "native_update_admission": update,
            "native_virtual_flash_selection_shadows": lower_pages,
            "actual_virtual_flash_mapping_modelled": False,
            "target_ram_ownership_verified": False,
        }
        if binding is not None:
            result["resident_layout"]["target_binding"] = binding
    if target:
        result["target_foreground"] = dialogue
        result["target_foreground"]["can_owner_implementation"] = "CAN-03" if can_owner_dir else "fixture"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--gcc", required=True, type=Path)
    parser.add_argument("--out", type=Path)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--with-rx-hook", action="store_true",
                       help="Also compare the isolated RX hook against the original instructions")
    modes.add_argument("--with-rx-dispatch", action="store_true",
                       help="Compare the ordered pair and per-attempt hooks together")
    modes.add_argument("--with-resident-rx", action="store_true",
                       help="Verify both hooks with code and constants below H03 application Flash")
    modes.add_argument("--with-target-rx", action="store_true",
                       help="Run the target binding and CAN13 foreground from the native RX path")
    modes.add_argument("--with-resident-target-rx", action="store_true",
                       help="Link the target RX IRQ below application Flash and run CAN-03 foreground")
    parser.add_argument("--can-owner-dir", type=Path,
                        help="Use CAN-03 owner and donor I/O sources from this targets/lfj8 directory")
    args = parser.parse_args()
    resident = args.with_resident_rx or args.with_resident_target_rx
    target = args.with_target_rx or args.with_resident_target_rx
    if args.can_owner_dir and not target:
        parser.error("--can-owner-dir requires a target RX mode")
    if args.out and (args.out.suffix.lower() != ".json" or args.out.resolve() == args.base.resolve()):
        parser.error("--out must be a separate JSON report")
    try:
        result = check(args.base, args.gcc.resolve(), args.with_rx_hook,
                       with_rx_dispatch=args.with_rx_dispatch, resident=resident,
                       target=target, can_owner_dir=args.can_owner_dir)
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(f"PASS: {result['executed_cases']} H03 BasicCAN RX cases (M32R CPU simulator)")
        if "simulator_hook" in result:
            print(f"PASS: {result['simulator_hook']['paired_cases']} stock/hook comparisons")
        if "high_accumulator_probe" in result.get("simulator_hook", {}):
            print("PASS: high accumulator operand, instruction and return probe")
        if resident:
            print(f"PASS: {len(result['resident_layout']['bypass_cases'])} resident RX bypass comparisons")
            print("PASS: H03 write and erase admission at the resident RX boundary")
            print("PASS: H03 Virtual Flash register probes for the lower RX pages")
        if target:
            print("PASS: native BasicCAN RX -> target foreground -> CAN13 0x722")
    except subprocess.CalledProcessError as error:
        detail = b"\n".join(filter(None, (error.stdout, error.stderr))) or str(error).encode()
        parser.exit(1, detail.decode(errors="replace") + "\n")
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
