"""Trace the approved H03 BasicCAN RX handler in the M32R CPU simulator."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
from typing import NamedTuple

from check_h03_flash_policy import LAYOUT
from check_h03_link import HERE, ROOT, TARGET, identify_h03


SLIST = 0x80100C
EXTID = 0x801004
MSC = 0x801050
SLOT_DATA = 0x801100
COPY = 0x808526
HOOK_SITE = 0x001534
HOOK_RESUME = HOOK_SITE + 4
HOOK_STOCK = bytes.fromhex("80c800ff")
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
    bra fixture_done
    .section .oem,"ax",@progbits
    .incbin "h03.dat"
"""


class Overwrite(NamedTuple):
    slot: int
    frame: bytes
    control: int
    during_copy: bool


class Case(NamedTuple):
    name: str
    slots: dict[int, tuple[bytes, int]]
    expected: list[tuple]
    extended: int = 0
    overwrite: Overwrite | None = None
    deliveries: tuple[bytes, ...] = ()


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


def simulate(run, work, debugger, case, *, compare_hook=False, hook_branch=None, high_probe=False):
    pending = sum(slot_mask(slot) for slot in case.slots)
    commands = [
        "set confirm off", "target sim --memory-size 16M", "load",
        "tbreak *fixture_ready", "run",
        f"set {{unsigned short}}{SLIST:#x} = {pending:#x}",
        f"set {{unsigned short}}{EXTID:#x} = {case.extended:#x}",
        f"set {{unsigned int}}0x80851c = {MSC:#x}",
        f"set {{unsigned int}}0x808518 = {SLOT_DATA:#x}",
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
    if hook_branch is not None:
        commands.append(f"set {{unsigned int}}{HOOK_SITE:#x} = {hook_branch:#x}")
    if high_probe:
        commands.append("set fixture_rx_high_probe = 1")
        if hook_branch is not None:
            commands += at("*rbm_h03_dtc_rx_restore_high",
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
        slot, raw, control, during_copy = case.overwrite
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
        received = "fixture_rx_queue.entries[$entry].delivery.received"
        commands += [
            trace("accumulator", "$r1", "$r2"),
            "set $probe = $stack_floor",
            f"while $probe < $sp && *(unsigned int*)$probe == {STACK_PATTERN:#x}",
            "set $probe = $probe + 4",
            "end",
            trace("stack", "$sp - $probe"),
            trace("observer", "fixture_rx_calls", "fixture_rx_irq_enabled",
                  "fixture_rx_queue.count", "fixture_rx_queue.rejected"),
            "set $entry = 0",
            "while $entry < fixture_rx_queue.count && $entry < 4",
            trace("delivery", f"{received}.generation", f"{received}.can_timestamp",
                  f"{received}.frame.id", f"{received}.frame.length",
                  *(f"{received}.frame.data[{i}]" for i in range(8))),
            "set $entry = $entry + 1",
            "end",
        ]
    (work / "probe.gdb").write_text("\n".join(commands) + "\n", encoding="ascii")
    output = run(debugger, "--batch", "-nx", "-x", "probe.gdb", "fixture.elf")
    events = []
    for line in output.decode(errors="replace").splitlines():
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


def cases():
    session = raw_slot(0x732, 8, "0210860000000000", 0x1234)
    flow = raw_slot(0x732, 3, "300000", 0x1300)
    yield Case("no_slot_interrupt", {}, [])
    yield Case("rx14_session", {14: (session, 0x41)}, ack(14, 2) + attempt(14, session),
               deliveries=(session,))
    yield Case("rx15_flow_control", {15: (flow, 0x41)}, ack(15, 1) + attempt(15, flow),
               deliveries=(flow,))
    yield Case("both_slots_pending", {14: (session, 0x41), 15: (flow, 0x41)}, [
        *ack(15, 3), *attempt(15, flow), *ack(14, 2), *attempt(14, session),
    ], deliveries=(flow, session))
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


def build_hook_fixture(run, work, gcc, rom):
    if rom[HOOK_SITE:HOOK_RESUME] != HOOK_STOCK:
        raise ValueError("The H03 instruction before the MSC read differs")
    sources = ("h03_dtc_rx_hook.S", "h03_dtc_rx_hook_fixture.c",
               "lfj8_h03_dtc_rx_queue.c", "lfj8_h03_dtc_can.c")
    for name in sources:
        shutil.copyfile(HERE / name, work / name)
    for directory in (HERE, ROOT / "diagnostics"):
        for path in directory.glob("*.h"):
            shutil.copyfile(path, work / path.name)
    (work / "fixture.ld").write_text(HOOK_LAYOUT, encoding="ascii")
    run(gcc, *TARGET, "-Os", "-g", "-std=c11", "-ffunction-sections", "-fdata-sections",
        "-DRBM_DTC_RX_HOOK_FIXTURE", "-nostdlib", "-I.", "-Wl,--gc-sections,-T,fixture.ld",
        "fixture.S", *sources, "-Wl,--start-group", "-lc", "-lgcc", "-Wl,--end-group", "-o", "fixture.elf")
    nm = gcc.with_name(f"m32r-elf-nm{gcc.suffix}")
    for line in run(nm, "--defined-only", "fixture.elf").decode().splitlines():
        words = line.split()
        if words[-1:] == ["rbm_h03_dtc_rx_hook"]:
            target = int(words[0], 16)
            displacement = target - HOOK_SITE
            if target < 0x101000 or displacement % 4 or not 0 <= displacement < (1 << 25):
                raise ValueError("The RX hook branch does not target the simulator fixture area")
            return 0xFF000000 | (displacement // 4)
    raise ValueError("The RX hook symbol is missing from the simulator ELF")


def expected_observation(case):
    attempts = sum(event[0] == "pre_clear" for event in case.expected)
    queued = [("observer", attempts, 0, len(case.deliveries), attempts - len(case.deliveries))]
    for raw in case.deliveries:
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


def compare_high_word(run, work, debugger, case, branch):
    stock = simulate(run, work, debugger, case, compare_hook=True, high_probe=True)
    wrapped = simulate(run, work, debugger, case, compare_hook=True, hook_branch=branch, high_probe=True)
    original = next(row[1] for row in stock if row[0] == "accumulator")
    returned = next(row[1] for row in wrapped if row[0] == "accumulator")
    operand = [row for row in wrapped if row[0] == "restore_high"]
    if not original or operand != [("restore_high", original, MVTACHI_R0)] or returned != original:
        raise ValueError(f"Unexpected high accumulator restore: {original:#x}, {operand}, {returned:#x}")
    observer_events = ("restore_high", "stack", "observer", "delivery")
    if ([row for row in stock if row[0] not in observer_events] !=
            [row for row in wrapped if row[0] not in observer_events]):
        raise ValueError("The high accumulator probe changed the OEM path or context")
    return {"original": f"0x{original:08X}", "restore_operand": f"0x{operand[0][1]:08X}",
            "returned": f"0x{returned:08X}"}


def check(base, gcc, with_rx_hook=False):
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
        branch = None
        if with_rx_hook:
            branch = build_hook_fixture(run, work, gcc, rom)
        else:
            (work / "fixture.ld").write_text(LAYOUT, encoding="ascii")
            run(gcc, "-m32r", "-Wa,-EB", "-nostdlib", "-Wl,-T,fixture.ld", "fixture.S", "-o", "fixture.elf")
        results = {}
        hook_cases = {}
        for case in cases():
            stock = simulate(run, work, debugger, case, compare_hook=with_rx_hook)
            if with_rx_hook:
                stock, stock_depth = split_stack_observation(stock)
            actual = [event for event in stock if event[0] not in ("observer", "context", "accumulator")]
            pending = slot_mask(case.overwrite.slot) if case.overwrite else 0
            expected = [*case.expected, ("return", 1, 0x9FFFFC, 8, 9, 10, pending)]
            if actual != expected:
                raise ValueError(f"{case.name}:\nexpected {expected}\nobserved {actual}")
            results[case.name] = render_events(actual)
            if with_rx_hook:
                if stock[-1] != ("observer", 0, 0, 0, 0):
                    raise ValueError(f"{case.name}: the unmodified H03 called the observer")
                wrapped = simulate(run, work, debugger, case, compare_hook=True, hook_branch=branch)
                wrapped, wrapped_depth = split_stack_observation(wrapped)
                expected_hook = [*stock[:-1], *expected_observation(case)]
                if wrapped != expected_hook:
                    raise ValueError(f"{case.name}, with hook:\nexpected {expected_hook}\nobserved {wrapped}")
                hook_cases[case.name] = {
                    "observer_and_deliveries": render_events(wrapped[-(1 + len(case.deliveries)):]),
                    "stock_stack_bytes_written": stock_depth,
                    "hook_stack_bytes_written": wrapped_depth,
                }
        if with_rx_hook:
            single_rx = next(case for case in cases() if case.name == "rx14_session")
            high_word = compare_high_word(run, work, debugger, single_rx, branch)
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
            "high_accumulator_probe": high_word,
        }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--gcc", required=True, type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--with-rx-hook", action="store_true",
                        help="Also compare the isolated RX hook against the original instructions")
    args = parser.parse_args()
    if args.out and (args.out.suffix.lower() != ".json" or args.out.resolve() == args.base.resolve()):
        parser.error("--out must be a separate JSON report")
    try:
        result = check(args.base, args.gcc.resolve(), args.with_rx_hook)
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(f"PASS: {result['executed_cases']} H03 BasicCAN RX cases (M32R CPU simulator)")
        if args.with_rx_hook:
            print(f"PASS: {result['simulator_hook']['paired_cases']} stock/hook comparisons")
            print("PASS: high accumulator operand, instruction and return probe")
    except subprocess.CalledProcessError as error:
        detail = b"\n".join(filter(None, (error.stdout, error.stderr))) or str(error).encode()
        parser.exit(1, detail.decode(errors="replace") + "\n")
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
