"""Rebuild the two OFFLINE_ONLY images from the pinned project and donor sources."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parent
TCM = "LFJ8_H03_EARLY_IRQ_DMA4_SERVICE_GUARDS_OFFLINE_ONLY.bin"
ECU = "E4M3_CHERY_ORDINARY_MODEL_NO_CRUISE_RX_TIMESTAMP_RB_NATIVE_PERMIT_CHERY_PASSIVE_CAPTURE_COMPACT_OFFLINE_ONLY.bin"
EXPECTED = {TCM: "2e593a44841b73e454db9b33ea4194035d6b269d5210f6f36dc719d6c6b4ea02",
            ECU: "2fb7fbee3a7daf1f33f4e5612854bccc69fb6bda5a108b19fd75c2908981b75e"}

def run(script, *args, log):
    with log.open("w", encoding="utf-8") as stream:
        subprocess.run([sys.executable, "-X", "utf8", "-B", str(script), *map(str, args)],
                       stdout=stream, check=True)

def build(out, gcc, verify):
    if out.exists():
        raise FileExistsError(f"Output path already exists: {out}")
    out.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".u340e-", dir=out.parent) as temporary:
        work = Path(temporary)
        result = work / "result"
        result.mkdir()
        engine = ROOT / "sources/R4/development/E4M3/engine"
        s04 = ROOT / "inputs/GW4G15_REV8_E4M3.bin"
        h03 = work / "h03"
        bosch = work / "bosch"
        run(ROOT / "build/h03/rebuild.py", "--gcc", gcc, "--base", ROOT / "inputs/LFJ8-T-D.bin",
            "--out", h03, log=result / "H03-build.log")
        run(ROOT / "sources/bosch-passive/build.py", "--engine", engine, "--s04", s04,
            "--outdir", bosch, "--with-model-fields", "--with-ordinary-model-field",
            "--with-rb-native-permit", "--with-rx-timestamp", "--with-chery-passive-capture",
            "--compact", log=result / "Bosch-build.json")
        for name, path in [(TCM, h03 / TCM), (ECU, bosch / ECU)]:
            if hashlib.sha256(path.read_bytes()).hexdigest() != EXPECTED[name]:
                raise ValueError(f"Rebuilt image differs from the tested version: {name}")
            path.rename(result / name)
        if verify:
            report = result / "Bosch-ST10.json"
            run(ROOT / "sources/bosch-passive/verify_passive_capture.py", "--engine", engine,
                "--s04", s04, "--image", result / ECU, log=report)
            checks = json.loads(report.read_bytes())
            if checks["status"] != "PASS_OFFLINE_ONLY" or checks["sha256"] != EXPECTED[ECU]:
                raise ValueError("ST10 verification failed")
        (result / "SHA256SUMS.txt").write_text("".join(f"{h}  {n}\n" for n, h in EXPECTED.items()),
                                              encoding="ascii")
        result.rename(out)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--gcc", type=Path, default=ROOT / "tools/SysGCC-m32r-elf-4.8.0/bin/m32r-elf-gcc.exe")
    parser.add_argument("--verify", action="store_true", help="Also repeat the full Bosch ST10 passive-receive regression")
    arguments = parser.parse_args()
    build(arguments.out.resolve(), arguments.gcc.resolve(), arguments.verify)
    print("PASS_OFFLINE_ONLY", arguments.out.resolve())
