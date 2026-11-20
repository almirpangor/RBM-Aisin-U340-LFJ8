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
    FIXTURE as UPDATE_FIXTURE,
    INSTALL_ACCEPT, INSTALL_BEGIN, INSTALL_DENY, observe,
)


SITE = 0x003568
STOCK_WORD = 0xB810000B
DISABLE = 0x003594
DISABLE_BRANCH = 0xFF000000 | ((DISABLE - SITE) // 4)
SERVICE_ACTIVATE = 0x003364
SERVICE_RETURN = 0x00336C
SERVICE_STATE = 0x808578
VIRTUAL_RAM_BASE = 0x807000
PAGE_SIZE = 0x1000


def check(base, compiler):
    identity = identify_h03(base)
    rom = base.read_bytes()
    if sha256(rom).hexdigest() != identity["sha256"]:
        raise ValueError("H03 changed while preparing the Virtual Flash fixture")
    if int.from_bytes(rom[SITE:SITE + 4], "big") != STOCK_WORD:
        raise ValueError("Unexpected activation branch at the H03 lockout site")

    with TemporaryDirectory(prefix="rbm-h03-vflash-lockout-") as directory:
        work = Path(directory)

        def run(*args):
            return subprocess.run(
                [str(arg) for arg in args], cwd=work, check=True, capture_output=True, timeout=15,
            ).stdout

        (work / "stock.dat").write_bytes(rom)
        (work / "fixture.S").write_text(FIXTURE, encoding="ascii")
        (work / "fixture.ld").write_text(LAYOUT, encoding="ascii")
        run(compiler, "-m32r", "-Wa,-EB", "-nostdlib", "-Wl,-T,fixture.ld", "fixture.S", "-o", "fixture.elf")
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
                memory += (("unsigned int", SITE, DISABLE_BRANCH),)
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
        for path in paths:
            for bank in control_banks:
                probe(path, bank, VIRTUAL_RAM_BASE, False, False)
            for bank in range(len(rom) // PAGE_SIZE):
                for enabled in (False, True):
                    probe(path, bank, VIRTUAL_RAM_BASE, enabled, True)

        for destination in (VIRTUAL_RAM_BASE - 1, VIRTUAL_RAM_BASE + 1):
            probe("service", 0x20, destination, True, False)
            probe("service", 0x20, destination, True, True)

        patch = (("unsigned int", SITE, DISABLE_BRANCH),)
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
        (work / "h03.dat").write_bytes(rom)
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
    return {
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
        parser.exit(1, (error.stderr or str(error).encode()).decode(errors="replace") + "\n")
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
