"""Prove the Unicode-safe CAN assembly emits the original bytes and relocations."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "targets/lfj8"))
import check_h03_can_monitor_startup as startup

def verify(base, gcc):
    identity = startup.identify_h03(base)
    rom = base.read_bytes()
    if hashlib.sha256(rom).hexdigest() != identity["sha256"]:
        raise ValueError("Input changed")
    with TemporaryDirectory(prefix="rbm-parked-equivalence-") as temporary:
        stage = Path(temporary) / "проверка пути"
        stage.mkdir()
        (stage / "h03-before.dat").write_bytes(rom[:startup.CANDIDATE_START])
        originals = (startup.PARKED_SETUP, startup.inline_parked_setup(rom))
        results = []
        for label, assembly in zip(("original", "inline"), originals):
            assembly.encode("ascii")
            (stage / (label + ".S")).write_text(assembly, encoding="ascii")
            def run(*args):
                return subprocess.run([str(x) for x in args], cwd=stage,
                    capture_output=True, check=True, timeout=60).stdout
            run(gcc, *startup.TARGET, "-c", label + ".S", "-o", label + ".o")
            run(gcc.with_name("m32r-elf-objcopy" + gcc.suffix), "-O", "binary",
                "-j", ".text.rbm_h03_stock_can0_setup_parked", label + ".o", label + ".dat")
            relocations = run(gcc.with_name("m32r-elf-objdump" + gcc.suffix), "-r", label + ".o")
            relocations = relocations[relocations.index(b"RELOCATION RECORDS"):]
            results.append(((stage / (label + ".dat")).read_bytes(), relocations))
        if results[0] != results[1]:
            raise ValueError("Inline assembly changed native bytes or relocations")
        return {"status": "PASS_ASSEMBLY_EQUIVALENCE", "base": identity,
                "bytes": len(results[0][0]), "text_sha256": hashlib.sha256(results[0][0]).hexdigest(),
                "relocations_sha256": hashlib.sha256(results[0][1]).hexdigest(),
                "path_contains_cyrillic": True, "hardware_verified": False}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for field in ("base", "gcc", "out"):
        parser.add_argument("--" + field, type=Path, required=True)
    args = parser.parse_args()
    if args.out.resolve() in (args.base.resolve(), args.gcc.resolve()):
        parser.error("Output must be separate")
    result = verify(args.base.resolve(), args.gcc.resolve())
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(result["status"])
