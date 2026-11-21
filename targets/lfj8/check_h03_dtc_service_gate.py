"""Exercise both linked lower BasicCAN redirects under H03 service and Flash gates."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

import check_h03_dtc_basiccan as basiccan


CALLBACKS = {
    "dispatch_callback": "rbm_h03_dtc_rx_begin",
    "observe_callback": "rbm_h03_dtc_rx_observe",
}
OBSERVER_EVENTS = {*CALLBACKS, "target_queue", "delivery"}
BANK_REGISTERS = {"felbank0": 0x8007E8, "felbank1": 0x8007EA,
                  "fesbank0": 0x8007F0, "fesbank1": basiccan.FESBANK1}


def check(base, gcc):
    identity = basiccan.identify_h03(base)
    rom = base.read_bytes()
    if sha256(rom).hexdigest() != identity["sha256"]:
        raise ValueError("H03 changed while the fixture was being prepared")
    case = next(case for case in basiccan.cases(True) if case.name == "paired_retry_new_frame")
    debugger = gcc.with_name(f"m32r-elf-gdb{gcc.suffix}")
    with TemporaryDirectory(prefix="rbm-h03-dtc-service-") as directory:
        work = Path(directory)

        def run(*args):
            return subprocess.run([str(arg) for arg in args], cwd=work, check=True,
                                  capture_output=True, timeout=30).stdout

        if run(gcc, "-dumpmachine").strip() != b"m32r-elf":
            raise ValueError("A bare-metal M32R compiler is required")
        (work / "h03.dat").write_bytes(rom)
        (work / "fixture.S").write_text(basiccan.FIXTURE, encoding="ascii")
        patches, code_end, _ = basiccan.build_hook_fixture(
            run, work, gcc, rom, with_dispatch=True, resident=True, target=True,
            can_owner_dir=basiccan.HERE)
        (work / "erased-app.dat").write_bytes(b"\xff" * (basiccan.FLASH_LIMIT - basiccan.APP_START))
        callback_probes = [command for event, symbol in CALLBACKS.items()
                           for command in basiccan.at(f"*{symbol}", basiccan.trace(event, "$pc"))]
        contexts = [
            ("ordinary_mode", 0, False, {}, False),
            ("mode_3", 3, False, {}, False),
            ("service_mode", 4, False, {}, True),
            ("service_mode_erased_application", 4, True, {}, True),
            ("disabled_bank_selectors", 0, False, dict.fromkeys(BANK_REGISTERS, 0x20), False),
        ]
        contexts.extend((f"{name}_enabled_only", 0, False, {name: 0x8020}, True)
                        for name in BANK_REGISTERS)
        trials = []
        for name, mode, erase_app, banks, bypass in contexts:
            setup = [f"set {{unsigned char}}0x804887 = {mode}",
                     f"set {{unsigned char}}{basiccan.PROGRAMMING_MODE:#x} = 0",
                     f"set {{unsigned char}}{basiccan.FCNT1:#x} = 0",
                     *(f"set {{unsigned short}}{address:#x} = {banks.get(bank, 0):#x}"
                       for bank, address in BANK_REGISTERS.items())]
            if erase_app:
                setup.append(f"restore erased-app.dat binary {basiccan.APP_START:#x}")
            opts = {"compare_hook": True, "compare_dispatch": True, "target": True}
            stock = basiccan.simulate(run, work, debugger, case, setup=setup, **opts)
            hooked = basiccan.simulate(run, work, debugger, case, patches=patches,
                                      setup=[*setup, *callback_probes], **opts)
            stock, stock_depth = basiccan.split_stack_observation(stock)
            hooked, hooked_depth = basiccan.split_stack_observation(hooked)
            callbacks = {event: sum(row[0] == event for row in hooked) for event in CALLBACKS}
            deliveries = sum(row[0] == "delivery" for row in hooked)
            attempts = sum(row[0] == "pre_clear" for row in stock)
            if stock[0] != ("startup", 1, 7, 0) or attempts != 3 or stock[-1] != ("target_queue", 0, 0):
                raise ValueError("The fixture did not admit CAN and exercise the OEM retry")
            if ([row for row in hooked if row[0] not in OBSERVER_EVENTS] !=
                    [row for row in stock if row[0] not in OBSERVER_EVENTS]):
                raise ValueError(f"{name} changed the OEM BasicCAN path")
            if bypass:
                if any(callbacks.values()) or deliveries or hooked[-1] != ("target_queue", 0, 0):
                    raise ValueError(f"{name} reached a project RX callback: {callbacks}")
            elif callbacks != {"dispatch_callback": 1, "observe_callback": attempts} or deliveries != 3:
                raise ValueError(f"{name} did not preserve normal project RX: {callbacks}")
            trials.append({"case": name, "service_mode": mode, "application_erased": erase_app,
                           "bank_registers": banks,
                           "oem_attempts": attempts, "callbacks": callbacks, "deliveries": deliveries,
                           "stock_stack_bytes": stock_depth, "hooked_stack_bytes": hooked_depth})

    return {"base": identity, "cases": trials, "resident_bytes": code_end - basiccan.RESIDENT_START,
            "hardware_executed": False, "flashable_image": None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--gcc", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = check(args.base.resolve(), args.gcc.resolve())
    except subprocess.CalledProcessError as error:
        parser.exit(1, (error.stderr or error.stdout or b"").decode(errors="replace") + "\n")
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"{error}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
