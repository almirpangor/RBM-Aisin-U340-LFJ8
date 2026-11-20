"""Build and exercise the portable controller on this computer."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

from hydraulic_port import write_port


CONTROLLER = Path(__file__).resolve().parent
TOYOTA = CONTROLLER / "vendor" / "toyota"
CONTROLLER_SOURCES = ("src/rbm_u340e.c", "src/rbm_u340e_runtime.c")
CONTROLLER_TESTS = ("tests/test_controller.c", "tests/test_runtime.c")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def verify_toyota() -> tuple[dict, list[Path]]:
    provenance = json.loads((TOYOTA / "manifest.json").read_text(encoding="utf-8"))
    files = []
    for entry in provenance["files"]:
        path = TOYOTA / entry["path"]
        if sha256(path) != entry["sha256"]:
            raise ValueError(f"Toyota source SHA-256 mismatch: {entry['path']}")
        files.append(path)
    return provenance, files


def build(compiler: str, destination: Path) -> None:
    resolved = shutil.which(compiler)
    if resolved is None:
        raise ValueError(f"Compiler not found: {compiler}")
    zig = Path(resolved).stem.casefold() == "zig"
    driver = [resolved, "cc"] if zig else [resolved]
    version_flag = "version" if zig else "--version"
    version = subprocess.check_output([resolved, version_flag], text=True).splitlines()[0]

    provenance, vendor_files = verify_toyota()
    sources = [*(CONTROLLER / path for path in CONTROLLER_SOURCES),
               *(p for p in vendor_files if p.suffix == ".c")]
    test_sources = [CONTROLLER / path for path in CONTROLLER_TESTS]
    flags = [
        "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
        "-I", str(CONTROLLER / "include"),
        "-I", str(TOYOTA / "include"),
    ]

    destination.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        library, executable, shared = "rbm_u340e.dll", "u340e_controller_test.exe", ["-shared"]
    elif sys.platform == "darwin":
        library, executable, shared = "librbm_u340e.dylib", "u340e_controller_test", ["-dynamiclib"]
    else:
        library, executable, shared = "librbm_u340e.so", "u340e_controller_test", ["-shared", "-fPIC"]

    with TemporaryDirectory(dir=destination) as stage_directory:
        stage = Path(stage_directory)
        port = write_port(TOYOTA / "src", stage)
        source_args = [str(path) for path in sources if path.name != "factory_hydraulics.c"] + [str(port)]
        subprocess.run([*driver, *flags, *shared, *source_args, "-o", str(stage / library)], check=True)
        subprocess.run(
            [*driver, *flags, "-DRBM_TEST_TRANSFERS", "-DRBM_TEST_RUNTIME", *source_args,
             *map(str, test_sources), "-o", str(stage / executable)],
            check=True,
        )
        tests = subprocess.check_output([str(stage / executable)], text=True).strip()
        print(tests)

        manifest = {
            "purpose": "host calculation and logical outputs",
            "platform": sys.platform,
            "compiler": version,
            "tests": tests,
            "toyota_commit": provenance["commit"],
            "source_sha256": {
                path.relative_to(CONTROLLER).as_posix(): sha256(path)
                for path in (
                    *sources,
                    *sorted((CONTROLLER / "include").glob("*.h")),
                    *(p for p in vendor_files if p.suffix == ".h"),
                    *test_sources,
                    Path(__file__).resolve(),
                    CONTROLLER / "hydraulic_port.py",
                )
            },
            "sha256": {name: sha256(stage / name) for name in (library, executable)},
        }
        (stage / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        for name in (library, executable, "manifest.json"):
            (stage / name).replace(destination / name)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cc", default="zig", help="Zig, GCC or Clang compiler executable")
    parser.add_argument("--out", type=Path, default=CONTROLLER.parent / "local" / "controller")
    args = parser.parse_args()
    build(args.cc, args.out.resolve())


if __name__ == "__main__":
    main()
