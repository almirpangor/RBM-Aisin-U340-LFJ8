"""Verify a bench-only H03 Virtual Flash lockout in simulator memory."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from check_h03_flash_policy import (
    APPLICATION, BOOT, FCNT1, FESBANK1, FIXTURE, LAYOUT, RECOVERY,
    VIRTUAL_CONFIG, VIRTUAL_CONFIG_DONE, VIRTUAL_SELECT, replay,
)
from check_h03_link import identify_h03
from check_h03_service_isolation import (
    FIXTURE as UPDATE_FIXTURE, INSTALL_ACCEPT, INSTALL_BEGIN, INSTALL_DENY, observe, storage_blocks,
)
import lfj8_h03_service_placement as service


SITE = service.LOCKOUT.address
STOCK_WORD = service.LOCKOUT.stock
DISABLE = service.STOCK_TARGETS[service.LOCKOUT.target]
DISABLE_BRANCH = int.from_bytes(service.LOCKOUT.branch(DISABLE), "big")
SERVICE_ACTIVATE = 0x003364
SERVICE_RETURN = 0x00336C
SERVICE_STATE = 0x808578
VIRTUAL_RAM_BASE = 0x807000
PAGE_SIZE = 0x1000


def check(base, compiler, placed_elf=None, storage_report=None, *, common_layout=None):
    identity = identify_h03(base)
    rom = base.read_bytes()
    if sha256(rom).hexdigest() != identity["sha256"]:
        raise ValueError("H03 changed while preparing the Virtual Flash fixture")
    service.verify_stock(rom, (service.LOCKOUT,))
    if (placed_elf is None) != (storage_report is None) or (common_layout is not None and placed_elf is None):
        raise ValueError("Supply both placed ELF and its storage report")
    placement = None
    if placed_elf is not None:
        blocks = storage_blocks(storage_report.read_bytes(), identity)
        if common_layout is None:
            candidate, placement = service.verify_and_overlay(rom, placed_elf, service.policy_ranges(blocks))
        else:
            report = json.loads(common_layout.read_text(encoding="utf-8"))
            model = report.get("early_irq_model", {})
            if report.get("base") != identity or not model.get("service_writers"):
                raise ValueError("Common H03 layout has no linked resident service writers for this ROM")
            candidate, policy = service.early_service_overlay(rom, placed_elf, model, blocks)
            placement = {"elf_sha256": model["elf_sha256"], "policy_ranges": policy,
                         "sites": model["service_writers"], "scope": "common_early_irq"}

    with TemporaryDirectory(prefix="rbm-h03-vflash-lockout-") as directory:
        work = Path(directory)

        def run(*args):
            return subprocess.run(
                [str(arg) for arg in args], cwd=work, check=True, capture_output=True, timeout=15,
            ).stdout

        (work / "fixture.S").write_text(FIXTURE, encoding="ascii")
        (work / "fixture.ld").write_text(LAYOUT, encoding="ascii")

        def load_rom(contents):
            (work / "stock.dat").write_bytes(contents)
            run(compiler, "-m32r", "-Wa,-EB", "-nostdlib", "-Wl,-T,fixture.ld", "fixture.S", "-o", "fixture.elf")

        load_rom(rom)
        patch = (("unsigned int", SITE, DISABLE_BRANCH),) if placement is None else ()
        debugger = compiler.with_name(f"m32r-elf-gdb{compiler.suffix}")

        def probe(path, bank, destination, enabled, patched):
            if path == "service":
                entry, stop = SERVICE_ACTIVATE, SERVICE_RETURN
            else:
                entry, stop = VIRTUAL_CONFIG, VIRTUAL_CONFIG_DONE
            initial_control = 0x40 | int(enabled)
            initial_bank = 0x2000 | (bank ^ 0x7F) | (0x8000 if enabled else 0)
            memory = (
                ("unsigned int", 0x809F9C, 0x809F9C),
                ("unsigned int", SERVICE_STATE + 12, destination),
                ("unsigned short", VIRTUAL_SELECT, bank),
                ("unsigned char", FCNT1, initial_control),
                ("unsigned short", FESBANK1, initial_bank),
            )
            if patched:
                memory += patch
            pc, *_, control, selection = replay(
                run, work, debugger, hex(entry), (hex(stop),),
                arguments=(0, 0, SERVICE_STATE), memory=memory, initial_r0=destination,
            )
            expect_overlay = not patched and destination == VIRTUAL_RAM_BASE
            expected = (0x41, 0x8000 | bank) if expect_overlay else (0x40, initial_bank & 0x7FFF)
            if pc != stop or (control, selection) != expected:
                raise ValueError(
                    f"Unexpected {path} response for bank {bank:#x}, destination {destination:#x}, "
                    f"initially enabled={enabled}, patched={patched}: {(pc, control, selection)}"
                )

        paths = ("selector", "service")
        control_banks = (0x00, 0x20, 0x7C, 0x7F)
        adjacent_destinations = (VIRTUAL_RAM_BASE - 1, VIRTUAL_RAM_BASE + 1)
        for path in paths:
            for bank in control_banks:
                probe(path, bank, VIRTUAL_RAM_BASE, False, False)
        for destination in adjacent_destinations:
            probe("service", 0x20, destination, True, False)
        if placement is not None:
            load_rom(candidate)
        for path in paths:
            for bank in range(len(rom) // PAGE_SIZE):
                for enabled in (False, True):
                    probe(path, bank, VIRTUAL_RAM_BASE, enabled, True)

        for destination in adjacent_destinations:
            probe("service", 0x20, destination, True, True)

        boot_cases = (
            ("valid_markers", APPLICATION, ()),
            ("bad_start_marker", RECOVERY, (("unsigned short", 0x008000, 0),)),
            ("bad_end_marker", RECOVERY, (("unsigned short", 0x07FFFE, 0),)),
        )
        for name, expected, changes in boot_cases:
            pc, *_ = replay(
                run, work, debugger, hex(BOOT), (hex(APPLICATION), hex(RECOVERY)),
                memory=patch + changes,
            )
            if pc != expected:
                raise ValueError(f"Unexpected reset dispatch with Virtual Flash lockout: {name}")

        # Run the existing native updater address probe on the exact new site.
        (work / "h03.dat").write_bytes(rom if placement is None else candidate)
        (work / "fixture.S").write_text(UPDATE_FIXTURE, encoding="ascii")
        run(compiler, "-m32r", "-Wa,-EB", "-nostdlib", "-Wl,-T,fixture.ld", "fixture.S", "-o", "fixture.elf")
        update_addresses = ((SITE, False), (0x007FFF, False), (0x008000, True))
        for address, allowed in update_addresses:
            pc, _ = observe(
                run, work, debugger, INSTALL_BEGIN, (1, 0, address),
                (hex(INSTALL_ACCEPT), hex(INSTALL_DENY)), 1,
            )
            if pc != (INSTALL_ACCEPT if allowed else INSTALL_DENY):
                raise ValueError(f"Unexpected native update decision for {address:#x}")

    pages = len(rom) // PAGE_SIZE
    report = {
        "base": identity,
        "simulation_patch": {
            "site": f"0x{SITE:06X}",
            "stock_word": f"{STOCK_WORD:08X}",
            "branch_word": f"{DISABLE_BRANCH:08X}",
            "destination": f"0x{DISABLE:06X}",
            "resident_code_and_data_added": False,
        },
        "selector_paths": list(paths),
        "all_internal_pages": pages,
        "patched_overlay_cases": pages * len(paths) * 2,
        "stock_positive_controls": len(control_banks) * len(paths),
        "adjacent_destination_controls": 4,
        "initial_overlay_states": ["disabled", "enabled"],
        "unrelated_control_and_selection_bits_preserved_on_disable": True,
        "stock_reset_dispatch": {name: f"0x{pc:06X}" for name, pc, _ in boot_cases},
        "native_update_start_addresses": [
            {"address": f"0x{address:06X}", "accepted": allowed} for address, allowed in update_addresses
        ],
        "limits": [
            "Native selector and internal monitor activation branch; MMIO is backed by simulator RAM.",
            "This bench-only change disables Virtual Flash, not the monitor's direct or deferred RAM writes.",
            "No external programmer profiles, physical remapping or recovery writes were tested.",
        ],
        "hardware_executed": False,
        "flashable_image": None,
    }
    if placement is not None:
        report["placed_service_protection"] = placement
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--gcc", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--placed-elf", type=Path, help="verify the exact linked branches")
    parser.add_argument("--storage-report", type=Path, help="candidate RAM inventory for the placed ELF")
    parser.add_argument("--common-layout", type=Path, help="layout.json for a common early IRQ ELF")
    args = parser.parse_args()
    inputs = (p for p in (args.base, args.gcc, args.placed_elf, args.storage_report, args.common_layout) if p is not None)
    if args.out.suffix.lower() != ".json" or any(args.out.resolve() == p.resolve() for p in inputs):
        parser.error("--out must be a separate JSON report")
    try:
        result = check(args.base, args.gcc.resolve(), args.placed_elf, args.storage_report,
                       common_layout=args.common_layout)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    except subprocess.CalledProcessError as error:
        parser.exit(1, (error.stderr or str(error).encode()).decode(errors="replace") + "\n")
    except (KeyError, OSError, ValueError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
