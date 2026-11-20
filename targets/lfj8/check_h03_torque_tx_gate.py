"""Exercise the original H03 TX13 writer and both callers with a simulated lease."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

from check_h03_link import identify_h03
from check_h03_torque_can_native import check as audit_native_can


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

    simulator = compiler.with_name(f"m32r-elf-run{compiler.suffix}")
    cases = []
    with TemporaryDirectory(prefix="rbm-h03-torque-tx-gate-") as temp:
        work = Path(temp)
        fixture = (HERE / "h03_torque_tx_gate_fixture.S").read_text(encoding="utf-8")
        placements = []
        source = [fixture]
        digests = {}
        for name, start, end in FRAGMENTS:
            file = f"{name}.bin"
            fragment = rom[start:end]
            (work / file).write_bytes(fragment)
            digests[name] = sha256(fragment).hexdigest()
            section = ".stock_" + name.replace("-", "_")
            source.extend((f'    .section {section},"ax",@progbits', f'    .incbin "{file}"'))
            placements.append((section, start))
        (work / "fixture.S").write_text("\n".join(source) + "\n", encoding="ascii")
        (work / "tx-entry.bin").write_bytes(rom[0xC34C:0xC350])
        placements.extend(((".tx_entry", 0xC34C), (".fixture", 0x060000),
                           (".fixture_state", 0x100000)))
        sections = "\n".join(f"  {section} {address:#x} : {{ *({section}) }}"
                             for section, address in sorted(placements, key=lambda item: item[1]))
        (work / "fixture.ld").write_text(
            f"ENTRY(_start)\nSECTIONS {{\n{sections}\n"
            "  /DISCARD/ : { *(.note*) *(.comment) }\n}\n"
            "h03_irq = 0x004724; h03_foreground_call = 0x00C338; h03_tx_writer_resume = 0x00C350;\n"
            "ASSERT(SIZEOF(.tx_entry) == 4, \"TX entry replacement must be one word\")\n",
            encoding="ascii",
        )

        def run(*args):
            return subprocess.run([str(arg) for arg in args], cwd=work, check=True,
                                  capture_output=True, timeout=15)

        if run(compiler, "-dumpmachine").stdout.strip() != b"m32r-elf":
            raise ValueError("A bare-metal M32R compiler is required")
        for path, irq in (("foreground", 0), ("CAN0_irq", 1)):
            for hooked, lease, control in ((0, 0, 0x00), (0, 0, 0x81), (1, 0, 0x00),
                                           (1, 1, 0x00), (1, 1, 0x81), (1, 1, 0x41)):
                parameters = {"IRQ_PATH": irq, "HOOKED": hooked, "LEASE_VALUE": lease,
                              "INITIAL_CONTROL": control}
                run(compiler, "-m32r", "-Wa,-EB", "-nostdlib", "-Wl,-T,fixture.ld",
                    *(f"-D{k}={v}" for k, v in parameters.items()), "fixture.S", "-o", "fixture.elf")
                run(simulator, "--memory-size", "16M", "fixture.elf")
                cases.append({
                    "caller": path,
                    "hooked": bool(hooked),
                    "lease": bool(lease),
                    "initial_slot_control": f"0x{control:02X}",
                    "final_slot_control": f"0x{control if lease else 0x80:02X}",
                    "slot_data_preserved": bool(lease),
                })
    return {
        "base": identity,
        "native_slot13_entry": audit["slot13"]["native_tx_writer_entry"],
        "native_fragment_sha256": digests,
        "can_sl_mask_shadow": "0x8003",
        "native_irq_entry": "invoked directly with SLIST bit 2 set",
        "can_hardware_irq_modelled": False,
        "traces": cases,
        "scope": "Original H03 code and call sites; simulated MMIO, owner flag and branch patch.",
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
