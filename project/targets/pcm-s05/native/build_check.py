"""Build and execute the S05 Chery SuperH self-test in an isolated CPU emulator."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile


HERE = Path(__file__).resolve().parent
BRIDGE = Path("../../lfj8")
FLAGS = [
    "-mb", "-m2e", "-Os", "-std=c11", "-Wall", "-Wextra", "-Werror",
    "-Wconversion", "-Wsign-conversion", "-ffreestanding", "-fno-builtin",
    "-fno-stack-protector", "-fno-unwind-tables", "-fno-asynchronous-unwind-tables",
    "-ffunction-sections", "-fdata-sections", "-fno-pie",
]


def build(gcc: Path, go: Path, output: Path) -> None:
    env = dict(os.environ)
    env["PATH"] = str(gcc.parent) + os.pathsep + env["PATH"]

    def run(*args, cwd=HERE):
        command = [str(arg) for arg in args]
        completed = subprocess.run(command, cwd=cwd, env=env, check=True,
                                   capture_output=True, text=True)
        return completed.stdout.strip()

    if not run(gcc, "-dumpmachine").startswith("sh"):
        raise ValueError("A bare-metal SuperH GCC is required")
    linker = run(gcc, "-print-prog-name=ld")
    nm = run(gcc, "-print-prog-name=nm")
    output.mkdir(parents=True, exist_ok=True)
    # The Windows GNU cross toolchain expects ANSI arguments. Keep source and
    # object paths relative when the checkout is in a Unicode directory.
    with tempfile.TemporaryDirectory(prefix="s05-check-", dir=HERE) as temporary:
        work = Path(temporary).relative_to(HERE)
        objects = []
        for source in (Path("check.c"), Path("s05_chery.c"), BRIDGE / "lfj8_bridge.c",
                       BRIDGE / "ta2005_chery_inputs.c"):
            obj = work / f"{source.stem}.o"
            run(gcc, *FLAGS, "-I", BRIDGE, "-c", source, "-o", obj)
            objects.append(obj)
        elf = work / "s05-chery-selftest.elf"
        run(linker, "-EB", "-m", "shelf", "--gc-sections", "--no-undefined",
            "-T", "check.ld", "-o", elf, *objects)
        data = (HERE / elf).read_bytes()
        if data[:7] != b"\x7fELF\x01\x02\x01" or len(data) < 52:
            raise ValueError("Expected ELF32 big-endian")
        elf_type, machine, version, entry = struct.unpack_from(">HHII", data, 16)
        flags = struct.unpack_from(">I", data, 36)[0]
        if (elf_type, machine, version, flags & 0x1F) != (2, 42, 1, 0xB):
            raise ValueError("Expected SH-2E executable ELF")
        if run(nm, "-u", elf):
            raise ValueError("Unexpected unresolved symbols in the test executable")
        result = run(go, "run", "-mod=readonly", ".", HERE / elf, cwd=HERE / "check_sh")
        print(result)
        report = {
            "artifact": elf.name,
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "compiler": run(gcc, "--version").splitlines()[0],
            "emulator": "github.com/user-none/erings/core/sh2 v1.2.0",
            "elf": {"type": "EXEC", "class": 32, "byte_order": "big", "machine": machine,
                    "flags": f"0x{flags:X}", "entry": f"0x{entry:X}", "undefined_symbols": []},
            "execution": result,
            "test_only": True,
        }
        shutil.copyfile(HERE / elf, output / elf.name)
        (output / "selftest.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gcc", required=True, type=Path)
    parser.add_argument("--go", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    try:
        build(args.gcc.resolve(), args.go.resolve(), args.out.resolve())
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"{getattr(error, 'stderr', None) or error}\n")


if __name__ == "__main__":
    main()
