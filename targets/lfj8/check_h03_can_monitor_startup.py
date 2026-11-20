"""Run H03's application entry and both CAN0 receive permits in M32R."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory

from check_h03_application_isolation import CANDIDATE_END, CANDIDATE_START, LAYOUT, set_memory
from check_h03_link import HERE, ROOT, TARGET, elf_info, identify_h03


PATCHES = (
    (0x008084, 0xFF00001F, "rbm_h03_can_monitor_cold_hook", 0xFF),
    (0x00B7F8, 0x61082125, "rbm_h03_can_monitor_start_permit", 0xFF),
    (0x00B864, 0xFEFFD69A, "rbm_h03_can_monitor_prepare_hook", 0xFE),
    (0x00B880, 0x60082024, "rbm_h03_can_monitor_recovery_permit", 0xFF),
)
LINK_SYMBOLS = """
h03_application_start = 0x008100;
h03_boot_recovery = 0x0047D8;
h03_stock_leave = 0x003E68;
h03_can0_recovery_skip = 0x00B890;
h03_can0_start_continuation = 0x00B7FC;
h03_can0_recovery_continuation = 0x00B884;
stock_can0_clear_transport = 0x000FC4;
stock_slot_clear = 0x003CCC;
"""
# Preserve original internal branch distances. The outer and inner routines
# are pinned to the exact H03. Three wide calls are relocated by the linker.
PARKED_SETUP = r"""
    .section .text.rbm_h03_stock_can0_setup_parked,"ax",@progbits
    .p2align 2
    .global rbm_h03_stock_can0_setup_parked
rbm_h03_stock_can0_setup_parked:
    .incbin "h03-before.dat",0x12cc,0x12f4-0x12cc
    bl.l stock_can0_clear_transport
    .incbin "h03-before.dat",0x12f8,0x1370-0x12f8
    bl.l .Lparked_controller
    .incbin "h03-before.dat",0x1374,0x137c-0x1374
.Lparked_controller:
    .incbin "h03-before.dat",0x10f8,0x1248-0x10f8
    bl.l stock_slot_clear
    .incbin "h03-before.dat",0x124c,0x1284-0x124c
    bra.l .Lskip_receive_requests
    .space 0x1298-0x1288
.Lskip_receive_requests:
    .incbin "h03-before.dat",0x1298,0x12a8-0x1298
    bra.l .Lskip_reset_release
    .space 0x12c0-0x12ac
.Lskip_reset_release:
    .incbin "h03-before.dat",0x12c0,0x12cc-0x12c0
    .size rbm_h03_stock_can0_setup_parked,.-rbm_h03_stock_can0_setup_parked
"""
FIXTURE = r"""
    .section .oem_before,"ax",@progbits
    .incbin "h03-before.dat"
    .section .oem_after,"ax",@progbits
    .incbin "h03-after.dat"
    .section .fixture,"ax",@progbits
    .p2align 2
    .global _start,fixture_ready,fixture_done,fixture_recovery
_start:
    ld24 sp,#0x9ffffc
    ld24 fp,#0x808000
fixture_ready:
    ldi r0,#0x40
    mvtc r0,psw
    ld24 r3,#fixture_target
    ld r3,@r3
    ld24 lr,#fixture_done
    ldi r0,#0
    jmp r3
    .p2align 2
fixture_recovery:
    push lr
    bra.l stock_recovery_body
    .p2align 2
fixture_done:
    bra fixture_done
"""
BACKEND = r"""
#include "lfj8_h03_can_monitor_startup.h"
#include "lfj8_h03_mmio.h"

enum { CAN0 = 0x801000, CAN1 = 0x801400 };
uint32_t fixture_target, fixture_fault, release_count, unsafe_writes, revoke_count;

#define BYTE(addr) (*(volatile uint8_t *)(uintptr_t)(addr))
#define HALF(addr) (*(volatile uint16_t *)(uintptr_t)(addr))
#define WORD(addr) (*(volatile uint32_t *)(uintptr_t)(addr))

static void require_lock(void)
{
    uint32_t psw;
    __asm__ volatile ("mvfc %0,psw" : "=r"(psw));
    if (psw & 0x40u) {
        ++unsafe_writes;
    }
}

static uint8_t read8(void *context, uint32_t addr)
{
    (void)context;
    return BYTE(addr);
}

static uint16_t read16(void *context, uint32_t addr)
{
    (void)context;
    return HALF(addr);
}

static uint32_t read32(void *context, uint32_t addr)
{
    (void)context;
    return WORD(addr);
}

static uint32_t enter(void *context)
{
    return lfj8_h03_mmio.enter(context);
}

static void leave(void *context, uint32_t saved)
{
    lfj8_h03_mmio.leave(context, saved);
}

static int pair_ready(uint32_t base)
{
    return HALF(base + 0x30u) == 0x1c00u && HALF(base + 0x38u) == 0x1c00u &&
        HALF(base + 0x1e0u) == 0x1c00u && HALF(base + 0x1f0u) == 0x1c00u &&
        BYTE(base + 0x5eu) == 0x40u && BYTE(base + 0x5fu) == 0x40u &&
        !(HALF(base + 0x0cu) & 3u);
}

static void write8(void *context, uint32_t addr, uint8_t value)
{
    (void)context;
    require_lock();
    if (fixture_fault != addr) {
        BYTE(addr) = value;
    }
}

static void write16(void *context, uint32_t addr, uint16_t value)
{
    (void)context;
    require_lock();
    if (addr == CAN0 || addr == CAN1) {
        if (!(value & 0x11u)) {
            ++release_count;
            if (!pair_ready(CAN0) || !pair_ready(CAN1) || WORD(0x808da4) || WORD(0x808da8) ||
                (BYTE(0x808580) & 0x20u) || BYTE(0x8007e2) || (HALF(0x8007f2) & 0x8000u)) {
                ++unsafe_writes;
            }
        }
        if (fixture_fault != addr) {
            HALF(addr + 2u) = (value & 0x11u) ? 0x0100u : 0x0800u;
        }
    }
    if (addr == CAN0 + 0x0cu || addr == CAN1 + 0x0cu) {
        HALF(addr) &= value;
    } else {
        HALF(addr) = value;
    }
}

static void write32(void *context, uint32_t addr, uint32_t value)
{
    (void)context;
    require_lock();
    if (fixture_fault != addr) {
        WORD(addr) = value;
    }
}

static const Lfj8RegisterIo simulated_io = {
    .read8 = read8, .read16 = read16, .read32 = read32, .write8 = write8,
    .enter = enter, .leave = leave,
};

const Lfj8H03MonitorIo rbm_h03_can_monitor_io = {&simulated_io, write16, write32};

void rbm_h03_can_monitor_revoke_locked(void)
{
    require_lock();
    ++revoke_count;
}
"""


def native_words():
    return {**{site: word for site, word, _, _ in PATCHES},
            0x12F4: 0xFEFFFF34, 0x1370: 0xFEFFFF62, 0x1248: 0xFE000AA1,
            0x128C: 0x2201F000, 0x1294: 0xA201000F, 0x12B0: 0x05C62524}


def patch_words(run, compiler):
    nm = compiler.with_name(f"m32r-elf-nm{compiler.suffix}")
    symbols = {row[2].decode(): int(row[0], 16) for row in
               (line.split() for line in run(nm, "-g", "--defined-only", "fixture.elf").splitlines())
               if len(row) == 3}
    words = []
    for site, _, name, opcode in PATCHES:
        target = symbols[name]
        displacement = target - site
        if not CANDIDATE_START <= target < CANDIDATE_END or displacement % 4:
            raise ValueError(f"Invalid linked target for {name}")
        words.append(("unsigned int", site, (opcode << 24) | (displacement // 4)))
    return words


WATCH = (
    ("unsigned short", 0x801000), ("unsigned short", 0x801400),
    ("unsigned short", 0x801030), ("unsigned short", 0x801038),
    ("unsigned short", 0x801430), ("unsigned short", 0x801438),
    ("unsigned char", 0x80105E), ("unsigned char", 0x80105F),
    ("unsigned char", 0x80145E), ("unsigned char", 0x80145F),
    ("unsigned int", 0x808DA4), ("unsigned int", 0x808DA8),
    ("unsigned short", 0x8007F2), ("unsigned char", 0x806AE6),
)


def read_probe(run, work, debugger, entry, memory, stops, fault):
    fields = ("$pc", "release_count", "unsafe_writes", "revoke_count",
              *(f"*({kind}*){address:#x}" for kind, address in WATCH))
    commands = ["set confirm off", "target sim --memory-size 16M", "load",
                "tbreak *fixture_ready", "run", f"set fixture_target = {entry}", f"set fixture_fault = {fault:#x}"]
    commands.extend(set_memory(*word) for word in memory)
    for index, alternatives in enumerate(stops):
        if index:
            commands.append("delete breakpoints")
        commands.extend(f"tbreak *{address:#x}" for address in alternatives)
        commands.extend(("continue", f'printf "MARK_{index} ' + " ".join(["%x"] * len(fields))
                         + '\\n", ' + ", ".join(fields)))
    (work / "probe.gdb").write_text("\n".join(commands) + "\n", encoding="ascii")
    output = run(debugger, "--batch", "-nx", "-x", "probe.gdb", "fixture.elf")
    seen = re.findall(rb"^MARK_\d+ ((?:[0-9a-f]+ )+[0-9a-f]+)\r?$", output, re.M)
    if len(seen) != len(stops):
        raise ValueError(f"Incomplete probe at {entry}: {output[-2200:].decode(errors='replace')}")
    return [tuple(int(value, 16) for value in row.split()) for row in seen]


def seed():
    return (
        ("unsigned int", 0x809F9C, 0x809F9C),
        ("unsigned short", 0x801000, 0x0C08), ("unsigned short", 0x801002, 0x0800),
        ("unsigned short", 0x801400, 0x0C08), ("unsigned short", 0x801402, 0x0800),
        ("unsigned short", 0x801030, 0x1800), ("unsigned short", 0x801038, 0x1800),
        ("unsigned short", 0x801430, 0x1800), ("unsigned short", 0x801438, 0x1800),
        ("unsigned char", 0x80105E, 0x41), ("unsigned char", 0x80105F, 0x41),
        ("unsigned char", 0x80145E, 0x41), ("unsigned char", 0x80145F, 0x41),
        ("unsigned short", 0x80100C, 3), ("unsigned short", 0x80140C, 3),
        ("unsigned char", 0x808580, 0x25), ("unsigned int", 0x808DA4, 513),
        ("unsigned int", 0x808DA8, 257), ("unsigned short", 0x8007F2, 0x8020),
        ("unsigned char", 0x806AE6, 3),
    )


def observations(run, work, compiler):
    debugger = compiler.with_name(f"m32r-elf-gdb{compiler.suffix}")
    patches = patch_words(run, compiler)

    def execute(entry, stops, fault=0, extra=(), *, patched=True):
        return read_probe(run, work, debugger, entry, (*seed(), *(patches if patched else ()), *extra),
                          stops, fault)

    stock, = execute("&fixture_recovery", ((0x0012B4,),), patched=False,
                     extra=(("unsigned short", 0x801002, 0x0100),))
    if (stock[0], stock[4] & 1, stock[6:8], stock[10:12]) != (0x12B4, 0, (0x1800, 0x1800), (0x40, 0x40)):
        raise ValueError(f"Unexpected original early receive permit: {stock}")

    rows = []
    for name, entry, stops, fault, extra, success, revoke in (
        ("reset_to_app_safe", "0x003DC8", ((0x008100, 0x0047D8),), 0, (), 0x008100, 0),
        ("reset_bad_marker", "0x003DC8", ((0x008100, 0x0047D8),), 0,
         (("unsigned short", 0x008000, 0),), None, 0),
        ("reset_active_virtual_flash", "0x003DC8", ((0x008100, 0x0047D8),), 0,
         (("unsigned char", 0x8007E2, 1),), None, 0),
        ("reset_timeout", "0x003DC8", ((0x008100, 0x0047D8),), 0x801400, (), None, 0),
        ("reset_filter_write_lost", "0x003DC8", ((0x008100, 0x0047D8),), 0x801430, (), None, 0),
        ("reset_copy_cancel_lost", "0x003DC8", ((0x008100, 0x0047D8),), 0x808DA8, (), None, 0),
        ("stock_start_permit", "0x00B7CC", ((0x00B7FC,),), 0, (), 0x00B7FC, 1),
        ("stock_start_keeps_reset_on_fault", "0x00B7CC", ((0x00B7FC,),), 0x801430, (), None, 1),
        ("recovery_before_and_after_permit", "&fixture_recovery", ((0x00B868, 0x00B890), (0x00B884, 0x00B890)),
         0, (), 0x00B884, 2),
        ("recovery_prepare_timeout", "&fixture_recovery", ((0x00B868, 0x00B890),),
         0x801400, (), None, 1),
        ("recovery_rearm_rejects_wrong_mask", "&fixture_recovery", ((0x00B868, 0x00B890), (0x00B884, 0x00B890)),
         0x801030, (), None, 2),
        ("bus_off_recovery", "&fixture_recovery", ((0x00B868, 0x00B890), (0x00B884, 0x00B890)),
         0, (("unsigned short", 0x801002, 0x4000),), 0x00B884, 2),
    ):
        result = execute(entry, stops, fault, extra)
        last = result[-1]
        if len(result) == 2:
            middle = result[0]
            if (middle[0], middle[1:4], middle[4] & 1, middle[5] & 1, middle[10:16]) != (
                    0x00B868, (0, 0, 1), 1, 1, (0, 0, 0, 0, 0, 0)):
                raise ValueError(f"{name}: early release or pending worker after parked setup: {middle}")
        if last[1:4] != (2 if success else 0, 0, revoke):
            raise ValueError(f"{name}: wrong validation or lock count: {last}")
        controls = (0x0C08 if name == "reset_to_app_safe" else 8, 0x0C08)
        if success and (last[0], last[4:6], last[6:14], last[14:17]) != (
                success, controls, (0x1C00,) * 4 + (0x40,) * 4, (0, 0, 0x20)):
            raise ValueError(f"{name}: unsafe receive permit: {last}")
        if not success and last[0] != stops[-1][-1] and name != "stock_start_keeps_reset_on_fault":
            raise ValueError(f"{name}: wrong fallback PC: {last}")
        if not success and revoke and name != "recovery_prepare_timeout" and not (last[4] & 0x11):
            raise ValueError(f"{name}: failed release did not retain reset: {last}")
        rows.append({"case": name, "stop": f"0x{last[0]:06X}", "qualified_receive_releases": last[1],
                     "revoke_calls": last[3], "lower_setup_stayed_parked": len(result) == 2})
    return {"original_early_receive": f"0x{stock[0]:06X}", "cases": rows}


def check(base, compiler):
    identity = identify_h03(base)
    rom = base.read_bytes()
    if sha256(rom).hexdigest() != identity["sha256"]:
        raise ValueError("H03 changed while preparing the fixture")
    for address, expected in native_words().items():
        if int.from_bytes(rom[address:address + 4], "big") != expected:
            raise ValueError(f"The H03 word at {address:#x} differs from the pinned layout")
    if rom[CANDIDATE_START:CANDIDATE_END] != b"\xff" * (CANDIDATE_END - CANDIDATE_START):
        raise ValueError("H03 candidate sector differs")
    with TemporaryDirectory(prefix="rbm-h03-can-monitor-startup-") as directory:
        work = Path(directory)

        def run(*args):
            return subprocess.run([str(arg) for arg in args], cwd=work, check=True,
                                  capture_output=True, timeout=30).stdout

        if run(compiler, "-dumpmachine").strip() != b"m32r-elf":
            raise ValueError("Expected the bare-metal M32R compiler")
        for file, data in (("h03-before.dat", rom[:CANDIDATE_START]), ("h03-after.dat", rom[CANDIDATE_END:])):
            (work / file).write_bytes(data)
        for file, data in (("fixture.S", FIXTURE), ("parked.S", PARKED_SETUP), ("fixture.c", BACKEND),
                           ("fixture.ld", LAYOUT + LINK_SYMBOLS + "stock_recovery_body = 0x00B850;\n")):
            (work / file).write_text(data, encoding="ascii")
        run(compiler, *TARGET, "-Os", "-g", "-std=c99", "-ffreestanding", "-fno-builtin",
            "-Wall", "-Wextra", "-Werror", "-Wconversion", "-Wsign-conversion",
            "-ffunction-sections", "-fdata-sections", "-nostdlib",
            "-DRBM_H03_MONITOR_STARTUP_SIMULATOR", "-I", HERE,
            "-I", ROOT / "controller/include", "-I", ROOT / "controller/vendor/toyota/include",
            "-Wl,--gc-sections,-T,fixture.ld",
            "-Wl,--undefined=fixture_recovery,--undefined=fixture_fault",
            *(f"-Wl,--undefined={name}" for _, _, name, _ in PATCHES),
            "fixture.S", "parked.S", "fixture.c", HERE / "lfj8_h03_mmio.c",
            HERE / "lfj8_h03_monitor_quiesce.c", HERE / "lfj8_h03_can_monitor_startup.c",
            HERE / "h03_can_monitor_startup_hooks.S", "-lc", "-lgcc", "-o", "fixture.elf")
        objcopy = compiler.with_name(f"m32r-elf-objcopy{compiler.suffix}")
        run(objcopy, "-O", "binary", "-j", ".oem_before", "fixture.elf", "original-linked.dat")
        if (work / "original-linked.dat").read_bytes() != rom[:CANDIDATE_START]:
            raise ValueError("Original Flash in linked fixture differs")
        _, allocated = elf_info(work / "fixture.elf", 2)
        sizes = [size for address, size, _ in allocated if address == CANDIDATE_START]
        if len(sizes) != 1 or sizes[0] > CANDIDATE_END - CANDIDATE_START:
            raise ValueError("Unexpected candidate code region")
        result = observations(run, work, compiler)
    return {"base": identity,
            "patched_application_sites": [f"0x{site:06X}" for site, _, _, _ in PATCHES],
            "linked_with_test_mmio_and_inhibit_bytes": sizes[0],
            "native_setup_copy_bytes": (0x137C - 0x12CC) + (0x12CC - 0x10F8),
            "flash_below_0x008000_changed": False,
            "native_and_candidate": result,
            "physical_reset_and_filters_verified": False, "flashable_image": None}


def inline_parked_setup(rom):
    """Keep the pinned slices portable without absolute .incbin filenames."""
    pattern = r'\.incbin "h03-before.dat",(0x[0-9a-f]+),(0x[0-9a-f]+)-(0x[0-9a-f]+)'

    def emit(match):
        start, end, repeated_start = (int(value, 16) for value in match.groups())
        if start != repeated_start or not 0 <= start < end <= len(rom):
            raise ValueError("Invalid parked CAN slice")
        data = rom[start:end]
        return "\n".join("    .byte " + ",".join(f"0x{value:02x}" for value in data[i:i + 16])
                         for i in range(0, len(data), 16))

    assembly, count = re.subn(pattern, emit, PARKED_SETUP)
    if count != 7 or ".incbin" in assembly:
        raise ValueError("The pinned parked CAN slice list changed")
    return assembly


def aggregate_placement(args):
    """Retain the exact tree plus the real veneers and generated parked setup."""
    sys.path.insert(0, str(ROOT))
    from tools import check_h03_image_layout as layout

    rom = args.base.read_bytes()
    if sha256(rom).hexdigest() != identify_h03(args.base)["sha256"]:
        raise ValueError("H03 changed before aggregate measurement")
    local = ROOT / "local"
    local.mkdir(exist_ok=True)
    results = {}
    original_modules = layout.BINDING_MODULES
    with TemporaryDirectory(prefix="rbm-can-placement-", dir=local) as directory:
        work = Path(directory)
        native = work / "can-monitor-parked-setup.S"
        symbols = "\n".join(f".global {name}\n.set {name}, {value}"
                            for name, value in re.findall(r"(\w+)\s*=\s*(0x[0-9a-fA-F]+);", LINK_SYMBOLS))
        native.write_text(inline_parked_setup(rom) + symbols + "\n",
                          encoding="ascii")
        extra_modules = (
            "lfj8_h03_monitor_quiesce.c",
            "lfj8_h03_can_monitor_startup.c",
            "h03_can_monitor_startup_hooks.S",
            Path(os.path.relpath(native, HERE)).as_posix(),
        )
        try:
            for case, profile, extras in (
                ("main_baseline", "padding-candidate", ()),
                ("protected_two_windows", "two-window", extra_modules),
                ("protected_padding", "padding-candidate", extra_modules),
            ):
                layout.BINDING_MODULES = (*original_modules, *extras)
                out = work / case
                out.mkdir()
                options = argparse.Namespace(
                    base=args.base.resolve(), gcc=args.gcc.resolve(), controller=args.controller.resolve(),
                    bridge=args.bridge.resolve(), profile=profile, memory_model="medium", with_bindings=True,
                    storage_report=args.storage_report.resolve(), cpu_test=False, out=out,
                )
                try:
                    report = layout.build(options)
                except ValueError:
                    report_path = out / "layout.json"
                    if not report_path.is_file():
                        raise
                    report = json.loads(report_path.read_text(encoding="utf-8"))
                room = sum(window.end - window.start for window in layout.PROFILES[profile])
                results[case] = {
                    "status": report["status"], "profile": profile, "capacity_bytes": room,
                    "retained_roots": len(report["required_roots"]),
                    "retained_sections": report["retained_sections"],
                    "known_flash_bytes": report["flash_payload_bytes"],
                    "known_static_ram_bytes": report["new_static_ram_bytes"],
                    "nominal_flash_margin_before_alignment_and_missing_material": room - report["flash_payload_bytes"],
                    "missing_symbols": report.get("unresolved_symbols", []),
                    "known_sections_fit": report.get("known_sections_candidate_plan", {}).get("sections") is not None,
                }
        finally:
            layout.BINDING_MODULES = original_modules
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--gcc", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    for name in ("controller", "bridge", "storage-report"):
        parser.add_argument("--" + name, type=Path, help="also measure the aggregate placement")
    args = parser.parse_args()
    aggregate_inputs = (args.controller, args.bridge, args.storage_report)
    if any(aggregate_inputs) and not all(aggregate_inputs):
        parser.error("aggregate placement requires --controller, --bridge and --storage-report")
    inputs = (args.base, *(path for path in aggregate_inputs if path))
    if args.out.suffix.lower() != ".json" or any(args.out.resolve() == path.resolve() for path in inputs):
        parser.error("--out must be a separate JSON report")
    try:
        result = check(args.base, args.gcc.resolve())
        if all(aggregate_inputs):
            result["aggregate_placement"] = aggregate_placement(args)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    except subprocess.CalledProcessError as error:
        parser.exit(1, (error.stderr or error.stdout or str(error).encode()).decode(errors="replace") + "\n")
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
