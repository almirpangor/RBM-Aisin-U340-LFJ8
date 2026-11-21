"""Exercise the original H03 TX13 writer and both callers with a simulated lease."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

from check_h03_link import identify_h03
from check_h03_storage import check as check_storage
from check_h03_torque_can_native import check as audit_native_can
from lfj8_h03_dtc_rx_placement import owner_address
from lfj8_h03_layout import (PROFILES, Window, alloc_sections, linker_script, pack,
                            read_elf, validate_windows, verify_linked)
import lfj8_h03_tx13_placement as tx13


HERE = Path(__file__).resolve().parent
FRAGMENTS = (
    ("irq-lock", 0x003E50, 0x003E78),
    ("can-irq", 0x004724, 0x004784),
    ("irq-branch", 0x00809C, 0x0080A0),
    ("callers", 0x00C338, 0x00C34C),
    ("tx-body", 0x00C350, 0x00C538),
    ("slot-addresses", 0x032628, 0x032768),
    ("tx-table", 0x032AB4, 0x032C1C),
)


def check(base, compiler):
    audit = audit_native_can(base)
    identity = identify_h03(base)
    rom = base.read_bytes()
    if sha256(rom).hexdigest() != identity["sha256"]:
        raise ValueError("H03 changed while the fixture was being prepared")

    tx13.validate_stock(rom)
    windows = PROFILES["padding-candidate"]
    validate_windows(windows, rom)
    validate_windows((*windows, tx13.REDIRECT_WINDOW))
    owner = owner_address(check_storage(base, compiler))
    simulator = compiler.with_name(f"m32r-elf-run{compiler.suffix}")
    cases = []
    linked_tx13 = None
    with TemporaryDirectory(prefix="rbm-h03-torque-tx-gate-") as temp:
        work = Path(temp)
        fixture = (HERE / "h03_torque_tx_gate_fixture.S").read_text(encoding="utf-8")
        stock = {}
        source = [fixture]
        digests = {}
        for name, start, end in FRAGMENTS:
            file = f"{name}.bin"
            fragment = rom[start:end]
            (work / file).write_bytes(fragment)
            digests[name] = sha256(fragment).hexdigest()
            section = ".stock_" + name.replace("-", "_")
            source.extend((f'    .section {section},"ax",@progbits', f'    .incbin "{file}"'))
            stock[section] = Window(section[1:], start, end)
        (work / "fixture.S").write_text("\n".join(source) + "\n", encoding="ascii")
        (work / "tx-entry.bin").write_bytes(rom[tx13.SITE:tx13.SITE + 4])
        stock[".tx_entry"] = tx13.REDIRECT_WINDOW
        stock[".fixture"] = Window("fixture", 0x060000, 0x060800)
        validate_windows((*stock.values(), *windows))

        def run(*args):
            return subprocess.run([str(arg) for arg in args], cwd=work, check=True,
                                  capture_output=True, timeout=15)

        if run(compiler, "-dumpmachine").stdout.strip() != b"m32r-elf":
            raise ValueError("A bare-metal M32R compiler is required")
        flags = (compiler, "-m32r", "-Wa,-EB", f"-I{HERE}", "-nostdlib")
        run(*flags, "-r", *(HERE / name for name in tx13.MODULES), "-o", "tx13.o")
        retained = read_elf(work / "tx13.o", 1)
        fixed, movable = tx13.fixed_redirect(alloc_sections(retained))
        tx_placements = fixed + pack(movable, windows)
        proposed = tx13.describe(rom, retained, tx_placements, owner, linked=False)
        bindings = (f"h03_irq = 0x004724; h03_foreground_call = 0x00C338;\n"
                    f"{tx13.RESUME} = {tx13.SITE + 4:#x}; {tx13.OWNER} = {owner:#x};\n")
        for path, irq in (("foreground", 0), ("CAN0_irq", 1)):
            for hooked, lease, fence, control in (
                (0, 0, 0, 0x00), (0, 0, 0, 0x81), (1, 0, 0, 0x00),
                (1, 1, 0, 0x00), (1, 1, 0, 0x81), (1, 1, 0, 0x41),
                (1, 0, 1, 0x82), (1, 0, 1, 0x02), (1, 0, 1, 0x81),
            ):
                parameters = {"IRQ_PATH": irq, "HOOKED": hooked, "LEASE_VALUE": lease, "FENCE_VALUE": fence,
                              "INITIAL_CONTROL": control}
                run(*flags, "-c", *(f"-D{k}={v}" for k, v in parameters.items()),
                    "fixture.S", "-o", "fixture.o")
                sections = alloc_sections(read_elf(work / "fixture.o", 1))
                placements = [item for s in sections for item in pack((s,), (stock[s["name"]],))]
                if hooked:
                    placements += tx_placements
                placements.sort(key=lambda item: item["address"])
                run(*flags, "-r", "fixture.o", *(("tx13.o",) if hooked else ()), "-o", "retained.o")
                (work / "fixture.ld").write_text(bindings + linker_script(placements), encoding="ascii")
                run(*flags, "-Wl,-T,fixture.ld,-e,_start", "retained.o", "-o", "fixture.elf")
                linked = read_elf(work / "fixture.elf", 2)
                verify_linked(linked, placements, ("_start", *tx13.ROOTS) if hooked else ("_start",))
                if hooked:
                    verified = tx13.describe(rom, linked, placements, owner, linked=True)
                    if verified["patch"] != proposed["patch"] or linked_tx13 not in (None, verified):
                        raise ValueError("The linked TX13 region drifted between the OEM call paths")
                    linked_tx13 = verified
                run(simulator, "--memory-size", "16M", "fixture.elf")
                blocked = bool(hooked and (lease or fence))
                cases.append({
                    "caller": path,
                    "hooked": bool(hooked),
                    "lease": bool(lease),
                    "fence": bool(fence),
                    "initial_slot_control": f"0x{control:02X}",
                    "final_slot_control": f"0x{control if blocked else 0x80:02X}",
                    "slot_data_preserved": blocked,
                })
    return {
        "base": identity,
        "native_slot13_entry": audit["slot13"]["native_tx_writer_entry"],
        "native_fragment_sha256": digests,
        "can_sl_mask_shadow": "0x8003",
        "native_irq_entry": "invoked directly with SLIST bit 2 set",
        "can_hardware_irq_modelled": False,
        "traces": cases,
        "linked_tx13": linked_tx13,
        "scope": "Original H03 call sites and production TX gate with simulated MMIO and owner placement.",
        "hardware_executed": False,
        "flashable_image": None,
    }


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--base", required=True, type=Path)
    cli.add_argument("--gcc", required=True, type=Path)
    cli.add_argument("--out", type=Path)
    args = cli.parse_args()
    if args.out and (args.out.suffix.lower() != ".json" or args.out.resolve() == args.base.resolve()):
        cli.error("--out must be a separate JSON report")
    try:
        result = json.dumps(check(args.base, args.gcc.resolve()), indent=2) + "\n"
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(result, encoding="utf-8")
        print(result, end="")
    except subprocess.CalledProcessError as error:
        output = error.stderr or error.stdout or str(error).encode()
        cli.exit(1, output.decode(errors="replace") + "\n")
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        cli.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
