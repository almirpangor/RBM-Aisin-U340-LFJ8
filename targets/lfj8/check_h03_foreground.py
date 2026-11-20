"""Compare OEM and wrapped H03 foreground execution on the M32R simulator."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import struct
import subprocess
from tempfile import TemporaryDirectory

from check_h03_link import identify_h03


HERE = Path(__file__).resolve().parent
CALL_SITE = 0x00816C
OEM_ENTRY = 0x040324
OEM_END = 0x04039C
TEST_SP = 0x9FFFFC
FIXTURE_SECTIONS = (
    (".fixture_start", 0x1000),
    (".h03_call", CALL_SITE),
    (".h03_mock_adc", 0x009FF4),
    (".h03_mock_a0cc", 0x00A0CC),
    (".h03_mock_bed8", 0x00BED8),
    (".h03_mock_d108", 0x00D108),
    (".h03_oem_pieces", OEM_ENTRY),
    (".h03_mock_4039c", OEM_END),
    (".h03_mock_403c0", 0x0403C0),
    (".fixture_code", 0x060000),
    (".fixture_data", 0x100000),
)


def check(base, compiler):
    identity = identify_h03(base)
    source = base.read_bytes()
    if sha256(source).hexdigest() != identity["sha256"]:
        raise ValueError("The H03 base changed while the fixture was being prepared")
    call = source[CALL_SITE:CALL_SITE + 4]
    target = CALL_SITE + 4 * int.from_bytes(call[1:], "big", signed=True)
    if call[0] != 0xFE or target != OEM_ENTRY:
        raise ValueError("The H03 foreground instruction is not the expected wide BL")
    with TemporaryDirectory(prefix="rbm-h03-foreground-") as directory:
        work = Path(directory)
        shutil.copyfile(HERE / "h03_foreground_test.S", work / "fixture.S")
        (work / "call-site.dat").write_bytes(call)
        (work / "stock-task.dat").write_bytes(source[OEM_ENTRY:OEM_END])
        sections = "\n".join(f"  {section} {address:#x} : {{ *({section}) }}"
                             for section, address in FIXTURE_SECTIONS)
        (work / "fixture.ld").write_text(
            f"ENTRY(_start)\nSECTIONS {{\n{sections}\n"
            "  /DISCARD/ : { *(.note*) *(.comment) }\n}\n",
            encoding="ascii",
        )

        def run(*args):
            return subprocess.run([str(arg) for arg in args], cwd=work, check=True,
                                  capture_output=True, timeout=15).stdout

        if run(compiler, "-dumpmachine").strip() != b"m32r-elf":
            raise ValueError("A bare-metal M32R compiler is required")
        compiler_version = run(compiler, "--version").decode().splitlines()[0]
        simulator = compiler.with_name(f"m32r-elf-run{compiler.suffix}")
        cases = []
        for sample, flag in ((0, 0), (347, 2), (1023, 0)):
            snapshots = []
            for wrapped in (False, True):
                variant = ["-DWRAPPED=1"] if wrapped else []
                run(compiler, "-m32r", "-Wa,-EB", "-nostdlib", "-Wl,-T,fixture.ld",
                    f"-DADC2_SAMPLE={sample}", f"-DINITIAL_FLAG={flag}", *variant,
                    "fixture.S", "-o", "simulator-test.elf")
                result = run(simulator, "--memory-size", "16M", "simulator-test.elf")
                if len(result) != 224:
                    raise ValueError(f"Expected a complete CPU snapshot, got {len(result)} bytes")
                snapshots.append(struct.unpack(">28I", bytes.fromhex(result.decode("ascii"))))
            stock, wrapped = snapshots
            if stock[:24] != wrapped[:24] or stock[27] != wrapped[27]:
                raise ValueError(f"Wrapped execution changed the OEM return state for ADC={sample}")
            if stock[13:16] != (0x808000, CALL_SITE + 4, TEST_SP):
                raise ValueError("OEM return R13, LR or SP does not match the H03 call model")
            if stock[17:19] != (0, 0x789ABC):
                raise ValueError(f"Unexpected ACC at the return: {stock[17]:#x}:{stock[18]:#x}")
            if stock[19:24] != (3, 0x020304, sample, 0x7D3B, 100):
                raise ValueError(f"OEM channel order or RAM values differ for ADC={sample}")
            if stock[24:27] != (0, 0, 0) or wrapped[24:27] != (1, sample, TEST_SP - 72):
                raise ValueError("The read-only observer or wrapper stack frame did not match")
            cases.append({
                "adc2_10bit": sample,
                "mock_adc2_16bit": f"0x{(sample << 6) | 0x3F:04X}",
                "adc_channels_in_order": [2, 3, 4],
                "observer_reads": wrapped[24],
                "observer_adc2": wrapped[25],
                "oem_status_byte_before": flag,
                "oem_status_byte_after": stock[27],
                "psw_at_return": f"0x{stock[16]:X}",
            })

    return {
        "base": identity,
        "compiler": compiler_version,
        "oem_instruction_bytes": f"[0x{OEM_ENTRY:06X}, 0x{OEM_END:06X})",
        "oem_instruction_sha256": sha256(source[OEM_ENTRY:OEM_END]).hexdigest(),
        "call_site": f"0x{CALL_SITE:06X}",
        "call_instruction": call.hex().upper(),
        "pc_at_continuation": f"0x{CALL_SITE + 4:06X}",
        "compared_state": ["R0-R15", "CR0", "ACC low word", "ADC result words", "OEM status byte"],
        "acc_upper_word_verified": False,
        "wrapper_frame_bytes_in_test": 72,
        "adc_word_address": "0x804BC6",
        "cases": cases,
        "hardware_executed": False,
        "flashable_image": None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--gcc", required=True, type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.out and (args.out.suffix.lower() != ".json" or args.out.resolve() == args.base.resolve()):
        parser.error("--out must be a separate JSON report")
    try:
        result = json.dumps(check(args.base, args.gcc.resolve()), indent=2) + "\n"
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(result, encoding="utf-8")
        print(result, end="")
    except subprocess.CalledProcessError as error:
        message = error.stderr or error.stdout or str(error).encode()
        parser.exit(1, message.decode(errors="replace") + "\n")
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
