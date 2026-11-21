"""Test the H03 RAM owner against linked service veneers and the real cold gate."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory

from check_h03_application_binding import FIXTURE_PROFILE
from check_h03_boot_writers import check as replay_boot_writers
from check_h03_can_monitor_revoke import aggregate_placement, aliases_for
from check_h03_link import HERE, ROOT, TARGET, identify_h03
from check_h03_toyota_source import RELEASE_ROOTS, simulate as simulate_toyota
from lfj8_h03_layout import alloc_sections, read_elf


SITES = {"DIRECT": 0x002924, "SPAN": 0x00294C, "COPY": 0x002D1C,
         "CLOSE": 0x002E9C, "VIRTUAL": 0x003568,
         "EARLY_IRQ": 0x003DBC, "DMA4": 0x00CF0C}
SBI_SITES = {"SBI_VECTOR": 0x000010, "SBI_MASK_READ": 0x003E5C,
             "SBI_PSW_SAVE": 0x003E60, "SBI_SAVE_CALL": 0x003F7C,
             "SBI_LAST_STORE": 0x003FC0, "SBI_STOP": 0x003FC4}
CONTINUATIONS = {
    "h03_service_direct_after_entry": 0x002928,
    "h03_service_stock_span_check": 0x003528,
    "h03_service_copy_after_entry": 0x002D20,
    "h03_service_close_after_store": 0x002EA0,
    "rbm_h03_service_policy": 0x030000,
    "h03_early_irq_after_entry": 0x003DC0,
    "h03_dma4_after_entry": 0x00CF10,
}


SBI_FRAGMENTS = {
    "vector": (0x000010, 0x000014), "psw": (0x003E50, 0x003E78),
    "sbi": (0x003F50, 0x003FCC),
}
SBI_ENTRY_SPI = 0x809EFC
SBI_ENTRY_CURSOR = 0x809F9C
SBI_AFTER_SAVE = 0x003F80
SBI_STOP = 0x003FC4


def probe_sbi(base, compiler):
    rom = base.read_bytes()
    with TemporaryDirectory(prefix="rbm-h03-sbi-stack-") as directory:
        folder = Path(directory)
        source = """
    .text
    .p2align 2
    .global _start
_start:
    ld24 sp,#0x809efc
    ld24 r0,#0x809f9c
    st r0,@r0
    ldi r1,#1
    mvtc r1,psw
    bra.l stock_vector
"""
        linker_sections = []
        fragments = {}
        for name, (first, end) in SBI_FRAGMENTS.items():
            data = rom[first:end]
            (folder / f"{name}.dat").write_bytes(data)
            fragments[name] = {"range": [f"{first:#08x}", f"{end:#08x}"],
                               "sha256": sha256(data).hexdigest()}
            source += f"""
    .section .stock_{name},"ax"
    .p2align 2
stock_{name}:
    .incbin "{name}.dat"
"""
            linker_sections.append(f"-Wl,--section-start=.stock_{name}={first:#x}")
        (folder / "sbi.S").write_text(source, encoding="ascii")
        def run(*items):
            return subprocess.run([str(item) for item in items], cwd=folder, check=True,
                                  capture_output=True, timeout=90).stdout

        run(compiler, *TARGET, "-nostdlib", "-Wl,-e,_start,-Ttext=0x10000", *linker_sections,
            "sbi.S", "-o", "sbi.elf")
        debugger = compiler.with_name(f"m32r-elf-gdb{compiler.suffix}")
        def observe(address):
            (folder / "observe.gdb").write_text(
                "set confirm off\ntarget sim --memory-size 16M\nload\n"
                f"tbreak *{address:#x}\nrun\n"
                'printf "SBI_STACK %x %x %x %x\\n", $pc, $sp, '
                '*(unsigned int*)0x809f9c, *(unsigned int*)0x809f98\n', encoding="ascii")
            output = run(debugger, "--batch", "-nx", "-x", "observe.gdb", "sbi.elf")
            match = re.search(rb"^SBI_STACK ([0-9a-f]+) ([0-9a-f]+) ([0-9a-f]+) ([0-9a-f]+)\r?$",
                              output, re.M)
            if not match:
                raise ValueError(f"The original SBI path did not reach {address:#x} in M32R")
            return tuple(int(value, 16) for value in match.groups())

        saved = observe(SBI_AFTER_SAVE)
        stopped = observe(SBI_STOP)
    pc, spi, cursor, saved_psw = saved
    if saved != (SBI_AFTER_SAVE, SBI_ENTRY_SPI - 40, SBI_ENTRY_CURSOR - 4, 1):
        raise ValueError(f"Unexpected stock SBI stack after save: {saved}")
    if stopped[0] != SBI_STOP or stopped[2:] != (cursor, saved_psw):
        raise ValueError(f"Unexpected stock SBI terminal stop observation: {stopped}")
    return {
        "original_fragments": fragments,
        "pc_after_save": f"{pc:#08x}",
        "terminal_loop_pc": f"{stopped[0]:#08x}",
        "terminal_sample_spi": f"{stopped[1]:#08x}",
        "spi_before_and_after": [f"{SBI_ENTRY_SPI:#08x}", f"{spi:#08x}"],
        "psw_cursor_before_and_after": [f"{SBI_ENTRY_CURSOR:#08x}", f"{cursor:#08x}"],
        "spi_consumed_bytes": SBI_ENTRY_SPI - spi,
        "psw_consumed_bytes": SBI_ENTRY_CURSOR - cursor,
        "entry_with_ie_masked": True,
        "external_sbi_trigger_simulated": False,
    }


def simulate(base, compiler, blocks):
    rom = base.read_bytes()

    def run(*args):
        process = subprocess.run([str(arg) for arg in args], check=True, capture_output=True, timeout=90)
        return process.stdout.decode(errors="replace").strip()

    crt = run(compiler, *TARGET, "-print-file-name=crt0.o")
    includes = (ROOT / "controller/include", ROOT / "controller/vendor/toyota/include",
                ROOT / "diagnostics")
    sources = ("test_lfj8_h03_ram_owner.c", "lfj8_h03_ram_owner.c", "lfj8_h03_target_memory.c",
               "lfj8_h03_application.c", "h03_application_hooks.S", "lfj8_h03_mmio.c",
               "lfj8_h03_service_guard.c", "h03_service_guard_hooks.S", "h03_dma4_guard.S")
    # Derive the state ranges from the checked M32R inventory. Stack bounds,
    # remaining reserves and the IRQ pointer here are only fixture geometry.
    ranges = {name: (block["address"], block["end_exclusive"])
              for name, block in blocks.items()}
    ranges.update(spi=(0x809700, 0x809efc), psw=(0x809f00, 0x809fa0))
    symbols = dict(CONTINUATIONS, rbm_h03_ram_spi_reserve=0x100,
                   rbm_h03_ram_psw_reserve=8, h03_dtc_irq_pointer=ranges["workspace"][1])
    for name, (first, end) in ranges.items():
        symbols[f"rbm_h03_ram_{name}_first"] = first
        symbols[f"rbm_h03_ram_{name}_end"] = end
    with TemporaryDirectory(prefix="rbm-h03-ram-owner-") as directory:
        folder = Path(directory)
        shim = folder / "crt.c"
        shim.write_text("void __init(void) {}\nvoid __fini(void) {}\n", encoding="ascii")
        resident = folder / "resident.ld"
        resident.write_text(
            "SECTIONS { .h03_early 0x6000 : { *(.text.rbm_h03_early_irq_gate) } } "
            "INSERT BEFORE .text;\n", encoding="ascii")
        elf = folder / "ram-owner.elf"
        run(compiler, *TARGET, "-Os", "-std=c11", "-Wall", "-Wextra", "-Werror",
            "-ffunction-sections", "-fdata-sections",
            "-DRBM_H03_COMMON_DMA4_GUARD=1",
            *(option for path in includes for option in ("-I", path)),
            *(f"-DROM_{name}=0x{rom[address:address + 4].hex()}u"
              for name, address in (SITES | SBI_SITES).items()),
            "-nostartfiles", crt, *(HERE / source for source in sources), shim,
            "-Wl,-e,_start,-Ttext=0x10000,--gc-sections",
            f"-Wl,-T,{resident}",
            *(f"-Wl,--defsym={name}={address:#x}" for name, address in symbols.items()),
            "-Wl,--start-group", "-lc", "-lgloss", "-lgcc", "-Wl,--end-group", "-o", elf)
        simulator = compiler.with_name(f"m32r-elf-run{compiler.suffix}")
        result = run(simulator, "--memory-size=16M", elf)
        if result != "H03 RAM owner: target binding, cold hook, service words, live stacks and DMA PASS":
            raise ValueError(f"Unexpected M32R result: {result}")
        return result


def probe_application_link(compiler):
    """Resolve the native consumer and provider without a target qualification."""
    with TemporaryDirectory(prefix="rbm-h03-memory-link-") as directory:
        stage = Path(directory)

        def run(*args):
            subprocess.run([str(item) for item in args], cwd=stage, check=True,
                           capture_output=True, timeout=90)

        (stage / "fixture_profile.h").write_text(FIXTURE_PROFILE, encoding="ascii")
        includes = (ROOT / "controller/include", ROOT / "controller/vendor/toyota/include",
                    ROOT / "diagnostics")
        flags = (compiler, *TARGET, "-Os", "-std=c11", "-Wall", "-Wextra", "-Werror",
                 "-ffreestanding", "-fno-builtin", "-ffunction-sections", "-fdata-sections",
                 "-Wno-missing-braces", "-Wno-missing-field-initializers",
                 *(option for path in includes for option in ("-I", path)))
        run(*flags, "-c", HERE / "lfj8_h03_target_memory.c", "-o", "provider.o")
        run(*flags, "-I", stage, '-DRBM_H03_APPLICATION_PROFILE="fixture_profile.h"',
            "-c", HERE / "lfj8_h03_application_binding.c", "-o", "binding.o")
        run(compiler, *TARGET, "-r", "-nostdlib", "binding.o", "provider.o", "-o", "bound.o")
        provider = read_elf(stage / "provider.o", 1)
        unbound = read_elf(stage / "binding.o", 1)["symbols"]
        bound = read_elf(stage / "bound.o", 1)["symbols"]
        name = "rbm_h03_target_ram_owned"
        if (unbound[name]["section"] != 0 or bound[name]["section"] == 0 or
                bound["rbm_h03_boot_writers_owned"]["section"] != 0):
            raise ValueError("Native RAM provider or mandatory boot qualification was not linked as expected")
        sections = alloc_sections(provider)
        if any(section["flags"] & 1 for section in sections):
            raise ValueError("Native RAM provider must have no writable static storage")
        return {"provider_resolved_in_native_binding": True,
                "boot_writers_qualification_remains_undefined": True,
                "readonly_payload_bytes": sum(section["size"] for section in sections),
                "writable_static_bytes": 0}


def check(args):
    sys.path.insert(0, str(ROOT))
    from tools import check_h03_image_layout as layout

    identity = identify_h03(args.base)
    compiler = args.gcc.resolve()
    _, aliases = aliases_for(args.base, compiler, args.storage_report)
    storage = json.loads(args.storage_report.read_text(encoding="utf-8"))
    result = simulate(args.base, compiler, storage["blocks"])
    application_link = probe_application_link(compiler)
    sbi = probe_sbi(args.base, compiler)
    boot_writers = replay_boot_writers(args.base, compiler)
    toyota = simulate_toyota(compiler, args.bridge.resolve(), args.controller.resolve())
    old_modules = layout.BINDING_MODULES
    old_roots = layout.EXTRA_ROOTS
    layout.BINDING_MODULES += ("lfj8_h03_ram_owner.c", "lfj8_h03_target_memory.c")
    layout.EXTRA_ROOTS += RELEASE_ROOTS
    try:
        placement = aggregate_placement(args, aliases)
    finally:
        layout.BINDING_MODULES = old_modules
        layout.EXTRA_ROOTS = old_roots
    return {
        "base": identity,
        "m32r": result,
        "stock_sbi": sbi,
        "native_boot_writers_replay": boot_writers,
        "native_application_link": application_link,
        "toyota_m32r": toyota,
        "live_dma_model_tested": True,
        "stock_hook_sites_checked": [f"0x{address:06X}" for address in SITES.values()],
        "linked_service_veneers_and_real_cold_gate": True,
        "linked_target_ram_owned": True,
        "external_writers_qualification_supplied_by_fixture": True,
        "aggregate_placement": placement,
        "hardware_tested": False,
        "flashable_image": None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("base", "gcc", "controller", "bridge", "storage-report", "out"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    inputs = (args.base, args.gcc, args.controller, args.bridge, args.storage_report)
    if args.out.suffix.lower() != ".json" or any(
            args.out.resolve() == path.resolve() or
            (args.out.exists() and path.exists() and args.out.samefile(path)) for path in inputs):
        parser.error("Use a separate JSON report")
    try:
        result = check(args)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or error.stdout or str(error).encode()).decode(errors="replace")
        parser.exit(1, f"{detail}\n")
    except (KeyError, OSError, ValueError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
