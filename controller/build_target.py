"""Build big-endian relocatable controller code and run the M32R CPU checks."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

from build import CONTROLLER, CONTROLLER_SOURCES, CONTROLLER_TESTS, TOYOTA, sha256, stage_toyota_sources, verify_toyota
from hydraulic_port import write_port
from size_port import apply_m32r_size_port


ARCHITECTURE = {
    "m32r": (88, ["-m32r", "-mmodel=medium", "-msdata=none", "-Wa,-EB"], "m32r-elf-"),
    "sh2": (42, ["-m2", "-mb", "-Wno-misleading-indentation"], "sh-elf-"),
}


def elf_flags(path: Path, machine: int, elf_type: int) -> int:
    header = path.read_bytes()[:52]
    expected_fields = elf_type.to_bytes(2, "big") + machine.to_bytes(2, "big")
    if header[:6] != b"\x7fELF\x01\x02" or header[16:20] != expected_fields:
        raise ValueError(f"Expected a 32-bit big-endian ELF of machine {machine}: {path}")
    return int.from_bytes(header[36:40], "big")


def build(architecture: str, compiler: Path, destination: Path, sh_runner: Path | None) -> None:
    provenance, files = verify_toyota()
    source_paths = sorted(path for path in CONTROLLER.rglob("*")
                          if path.is_file() and path.suffix in (".c", ".h", ".py"))
    source_hashes = {path.relative_to(CONTROLLER.parent).as_posix():
                     hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
                     for path in source_paths}
    machine, target_flags, triplet = ARCHITECTURE[architecture]
    suffix = compiler.suffix
    environment = dict(os.environ, PATH=str(compiler.parent) + os.pathsep + os.environ.get("PATH", ""))
    nm = subprocess.check_output([compiler, "-print-prog-name=nm"], env=environment, text=True).strip()
    flags = [
        "-std=c11", "-Os", "-Wall", "-Wextra", "-Werror",
        "-Wno-missing-braces", "-Wno-missing-field-initializers", "-ffreestanding", "-fno-builtin",
        "-fno-common", "-fno-stack-protector", "-fno-unwind-tables", "-fno-asynchronous-unwind-tables",
        "-ffunction-sections", "-fdata-sections",
        *target_flags, "-Iinclude", "-Ivendor/include",
    ]
    with TemporaryDirectory(prefix="rbm-u340-target-") as temp:
        stage = Path(temp)
        shutil.copytree(CONTROLLER / "include", stage / "include")
        shutil.copytree(TOYOTA / "include", stage / "vendor/include")
        stage_toyota_sources(stage / "vendor/src")
        size_port = apply_m32r_size_port(stage / "vendor/src") if architecture == "m32r" else None

        def copy_source(path: str) -> str:
            name = Path(path).name
            shutil.copy2(CONTROLLER / path, stage / name)
            return name

        port = write_port(stage / "vendor/src", stage)
        sources = [*map(copy_source, CONTROLLER_SOURCES), *(
            "vendor/src/" + path.name for path in files
            if path.suffix == ".c" and path.name != "factory_hydraulics.c"
        ), port.name]
        tests = list(map(copy_source, CONTROLLER_TESTS))
        test_flags = ["-DRBM_TEST_TRANSFERS", "-DRBM_TEST_RUNTIME"]
        objects = []
        compile_flags = [*flags, "-fstack-usage"] if architecture == "sh2" else flags
        for source in sources:
            object_file = Path(source).stem + ".o"
            subprocess.run(
                [compiler, *compile_flags, "-c", source, "-o", object_file],
                cwd=stage, env=environment, check=True,
            )
            objects.append(object_file)

        controller_object = stage / f"rbm_u340e_{architecture}_be.o"
        subprocess.run(
            [
                compiler, *target_flags, "-fno-use-linker-plugin", "-r", "-nostdlib",
                *objects, "-o", controller_object.name,
            ],
            cwd=stage, env=environment, check=True,
        )
        arch_flags = elf_flags(controller_object, machine, 1)
        if architecture == "sh2" and arch_flags & 0x1F != 2:
            raise ValueError(f"Expected SuperH SH-2, got ELF flags {arch_flags:#x}")
        undefined = subprocess.check_output([nm, "-u", controller_object.name], cwd=stage, env=environment, text=True)
        artifacts = [controller_object]
        test_result = "not_run"
        if architecture == "sh2":
            entries = []
            for report in stage.glob("*.su"):
                for line in report.read_text(encoding="utf-8").splitlines():
                    location, size, qualifier = line.split("\t")
                    entries.append((int(size), location, qualifier))
            if not entries:
                raise ValueError("The SH2 compiler produced no stack-usage report")
            stack_usage = stage / "stack-usage.tsv"
            stack_usage.write_text(
                "bytes\tfunction\tqualifier\n" + "".join(
                    f"{size}\t{location}\t{qualifier}\n"
                    for size, location, qualifier in sorted(entries, reverse=True)
                ),
                encoding="utf-8", newline="\n",
            )
            artifacts.append(stack_usage)

        if architecture == "m32r":
            simulator = compiler.with_name(triplet + "run" + suffix)
            startup = subprocess.check_output(
                [compiler, *target_flags, "-print-file-name=crt0.o"], cwd=stage, env=environment, text=True,
            ).strip()
            test_elf = stage / "u340e_m32r_sim.elf"
            # The bundled monitor CRT expects init/fini hooks normally provided
            # by its board package. These hooks belong to the simulator only.
            (stage / "sim_crt.c").write_text(
                "void __init(void) {}\nvoid __fini(void) {}\n", encoding="utf-8"
            )
            subprocess.run(
                [
                    compiler, *flags, *test_flags, "-nostartfiles", startup, *sources,
                    *tests, "sim_crt.c", "-Wl,-e,_start", "-Wl,--start-group",
                    "-lc", "-lgloss", "-lgcc", "-Wl,--end-group", "-o", test_elf.name,
                ],
                cwd=stage, env=environment, check=True,
            )
            elf_flags(test_elf, machine, 2)
            test_result = subprocess.check_output(
                [simulator, test_elf.name], cwd=stage, env=environment, text=True, timeout=60,
            ).strip()
            expected_checks = ("Controller tests passed:", "Toyota GP runtime:", "Toyota scheduler:")
            if not all(check in test_result for check in expected_checks):
                raise ValueError(f"M32R simulator did not finish the test: {test_result}")
            artifacts.append(test_elf)
        elif sh_runner is not None:
            for name in ("sh2_sim.c", "sh2_sim.ld"):
                shutil.copy2(CONTROLLER / "tests" / name, stage / name)
            # Keep each fixture within the simulator's ROM and stack model.
            sh_tests = (
                ("u340e_sh2_sim.elf", "test_controller.c", "-DRBM_TEST_TRANSFERS"),
                ("u340e_sh2_runtime_sim.elf", "test_runtime.c", "-DRBM_TEST_RUNTIME_STANDALONE"),
            )
            results = []
            for filename, test_source, test_flag in sh_tests:
                test_elf = stage / filename
                subprocess.run(
                    [
                        compiler, *flags, test_flag, "-DRBM_TEST_QUIET",
                        "-fno-use-linker-plugin", "-nostdlib", *sources, test_source, "sh2_sim.c",
                        "-Wl,-T,sh2_sim.ld,--gc-sections", "-lgcc", "-o", test_elf.name,
                    ],
                    cwd=stage, env=environment, check=True,
                )
                elf_flags(test_elf, machine, 2)
                result = subprocess.check_output(
                    [sh_runner, test_elf.name], cwd=stage, env=environment, text=True, timeout=60,
                ).strip()
                if not result.startswith("PASS SuperH test:"):
                    raise ValueError(f"SH2 simulator did not finish the test: {result}")
                results.append(f"{result} ({filename})")
                artifacts.append(test_elf)
            test_result = "\n".join(results)

        manifest = {
            "purpose": "relocatable control code and CPU simulation, without board I/O",
            "architecture": architecture,
            "source_hash_format": "lf",
            "source_sha256": source_hashes,
            "size_port": size_port,
            "compiler": subprocess.check_output([compiler, "--version"], env=environment, text=True).splitlines()[0],
            "flags": compile_flags,
            "elf_flags": f"{arch_flags:#x}",
            "undefined_symbols": [line.split()[-1] for line in undefined.splitlines() if line.strip()],
            "toyota_commit": provenance["commit"],
            "tests": test_result,
            "sha256": {path.name: sha256(path) for path in artifacts},
        }
        destination.mkdir(parents=True, exist_ok=True)
        for artifact in artifacts:
            shutil.copy2(artifact, destination / artifact.name)
        (destination / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        print(f"{controller_object.name}: big-endian ELF, flags {arch_flags:#x}")
        print(test_result)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("architecture", choices=ARCHITECTURE)
    parser.add_argument("--cc", required=True, help="Path to the cross compiler")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--sh-runner", type=Path, help="Build and run the SH-2 ELF in the project simulator")
    args = parser.parse_args()
    compiler = shutil.which(args.cc)
    if compiler is None:
        parser.error(f"Compiler not found: {args.cc}")
    destination = args.out or CONTROLLER.parent / "local/controller" / args.architecture
    sh_runner = args.sh_runner.resolve(strict=True) if args.sh_runner else None
    build(args.architecture, Path(compiler).resolve(), destination.resolve(), sh_runner)


if __name__ == "__main__":
    main()
