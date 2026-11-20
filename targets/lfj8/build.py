"""Build and verify the Windows test and relocatable embedded objects."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parents[1]
CORE = ["lfj8_bridge.c", "ta2005_chery_inputs.c"]
S05_ADAPTER = ["../pcm-s05/native/s05_chery.c"]
DONOR_ADAPTER = ["lfj8_donor_io.c", "lfj8_chery_tx.c", "lfj8_selector_adc.c"]
WARNINGS = ["-Wall", "-Wextra", "-Werror", "-Wconversion", "-Wsign-conversion"]
FREESTANDING = [
    "-Os", "-std=c99", "-ffreestanding", "-fno-builtin", "-fno-common",
    "-fno-stack-protector", "-fno-unwind-tables", "-fno-asynchronous-unwind-tables",
]


def command(*args, tool_bin=None):
    env = None
    if tool_bin:
        env = os.environ.copy()
        env["PATH"] = str(tool_bin) + os.pathsep + env.get("PATH", "")
    return subprocess.run([str(arg) for arg in args], cwd=ROOT, check=True,
                          text=True, capture_output=True, env=env).stdout.strip()


def summary(file):
    data = file.read_bytes()
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def verified_9e1c_base(image):
    registry = json.loads((PROJECT / "data/sources.json").read_text(encoding="utf-8"))
    expected = next(item for item in registry["supporting_materials"] if item["id"] == "H03")
    identity = json.loads(command(
        sys.executable, "-B", PROJECT / "tools/inspect_lfj8_tcm.py", image,
        "--expect", "LFJ8-18-9E1C",
    ))
    if identity["sha256"] != expected["sha256"] or identity["bytes"] != expected["bytes"]:
        raise ValueError("Supply the exact LFJ8-T-D.bin selected as H03")
    return {
        "source_id": "H03",
        "name": image.name,
        "embedded_id": identity["embedded_id"],
        "software": identity["software"],
        "bytes": identity["bytes"],
        "sha256": identity["sha256"],
        "physical_9e1d_compatibility_verified": False,
    }


def publish(file, destination):
    descriptor, staging = tempfile.mkstemp(prefix=f".{file.name}.", dir=destination)
    os.close(descriptor)
    stage = Path(staging)
    try:
        shutil.copyfile(file, stage)
        stage.replace(destination / file.name)
    finally:
        stage.unlink(missing_ok=True)


def build_host(zig, work):
    output = work / "lfj8_host_check.exe"
    command(zig, "cc", "-std=c11", "-O2", *WARNINGS, "-o", output,
            "host_check.c", *CORE, *DONOR_ADAPTER)
    result = command(output)
    print(result)
    return output, {"compiler": f"Zig {command(zig, 'version')}", "host_test": result}


def build_embedded(compiler, work, architecture, sh_cpu, use_9e1c_base=False):
    triple = command(compiler, "-dumpmachine")
    if architecture == "m32r":
        if not triple.startswith("m32r"):
            raise ValueError(f"Expected M32R compiler. Detected {triple}")
        sources = CORE + DONOR_ADAPTER
        target_flags = ["-m32r", "-mmodel=medium", "-msdata=none"]
        assembler_flags = ["-Wa,-EB"]
        output_name = "lfj8_9e1c_m32r.o" if use_9e1c_base else "lfj8_m32r.o"
        expected_machine = 88
        expected_sh_flags = None
    else:
        if not triple.startswith("sh"):
            raise ValueError(f"Expected SuperH compiler. Detected {triple}")
        sources = CORE + S05_ADAPTER
        target_flags = ["-mb", f"-{sh_cpu}"]
        assembler_flags = []
        output_name = "s05_chery_sh.o"
        expected_machine = 42
        expected_sh_flags = {"m2": 2, "m2e": 11}[sh_cpu]

    objects = []
    for source in sources:
        obj = work / f"{architecture}-{Path(source).stem}.o"
        command(compiler, *target_flags, *assembler_flags, *FREESTANDING, *WARNINGS,
                "-I", ".", "-c", source, "-o", obj)
        objects.append(obj)

    output = work / output_name
    if architecture == "m32r":
        command(compiler, *target_flags, "-nostdlib", "-Wl,-EB,-r", "-o", output,
                *objects, "-lgcc")
    else:
        linker = command(compiler, "-print-prog-name=ld")
        command(linker, "-EB", "-m", "shelf", "-r", "-o", output, *objects,
                tool_bin=compiler.parent)
    data = output.read_bytes()
    if data[:7] != b"\x7fELF\x01\x02\x01" or len(data) < 52:
        raise ValueError(f"{output.name}: expected ELF32 big-endian")
    elf_type, machine, elf_version, entry = struct.unpack_from(">HHII", data, 16)
    if (elf_type, machine, elf_version, entry) != (1, expected_machine, 1, 0):
        raise ValueError(f"{output.name}: unexpected ELF type, machine or entry point")
    flags = struct.unpack_from(">I", data, 36)[0]
    if expected_sh_flags is not None and (flags & 0x1F) != expected_sh_flags:
        raise ValueError(f"{output.name}: unexpected SuperH machine flags 0x{flags:X}")
    nm = command(compiler, "-print-prog-name=nm")
    undefined = command(nm, "-u", output, tool_bin=compiler.parent)
    if undefined:
        raise ValueError(f"{output.name}: unresolved symbols\n{undefined}")
    info = {
        "compiler": command(compiler, "--version").splitlines()[0],
        "triple": triple,
        "target_flags": target_flags,
        "elf": {"class": 32, "endian": "big", "type": "REL", "machine": machine,
                "flags": f"0x{flags:X}", "entry": entry},
        "sources": sources,
        "undefined_symbols": [],
    }
    print(f"{output.name}: ELF32 BE REL machine {machine}, flags 0x{flags:X}, no undefined symbols")
    return output, info


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--zig", type=Path)
    parser.add_argument("--m32r-cc", type=Path)
    parser.add_argument("--base-9e1c", type=Path, help="Bind the M32R build report to the exact H03 input")
    parser.add_argument("--sh-cc", type=Path)
    parser.add_argument("--sh-cpu", choices=["m2", "m2e"], default="m2")
    args = parser.parse_args()
    if not any((args.zig, args.m32r_cc, args.sh_cc)):
        parser.error("Supply at least one compiler with --zig, --m32r-cc or --sh-cc")
    if args.base_9e1c and not args.m32r_cc:
        parser.error("--base-9e1c requires --m32r-cc")

    sources = [*CORE, *DONOR_ADAPTER, "host_check.c", "build.py",
               "lfj8_bridge.h", "lfj8_donor_io.h", "lfj8_chery_tx.h", "lfj8_selector_adc.h",
               "ta2005_chery_inputs.h"]
    manifest = {"sources": {name: summary(ROOT / name) for name in sources}, "artifacts": {}}
    if args.sh_cc:
        s05_files = [*S05_ADAPTER, "../pcm-s05/native/s05_chery.h"]
        for name in s05_files:
            manifest["sources"][name] = summary(ROOT / name)
    try:
        if args.base_9e1c:
            manifest["m32r_base"] = verified_9e1c_base(args.base_9e1c.resolve())
        destination = args.output.resolve()
        destination.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="rbm-lfj8-build-") as temporary:
            work = Path(temporary)
            results = []
            if args.zig:
                results.append(build_host(args.zig.resolve(), work))
            if args.m32r_cc:
                results.append(build_embedded(args.m32r_cc.resolve(), work, "m32r", args.sh_cpu,
                                              use_9e1c_base=args.base_9e1c is not None))
            if args.sh_cc:
                results.append(build_embedded(args.sh_cc.resolve(), work, "sh", args.sh_cpu))
            for artifact, metadata in results:
                manifest["artifacts"][artifact.name] = {**summary(artifact), **metadata}
                publish(artifact, destination)
            staged_manifest = work / "build-manifest.json"
            staged_manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            publish(staged_manifest, destination)
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.stderr or error.stdout or str(error)) from error
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
