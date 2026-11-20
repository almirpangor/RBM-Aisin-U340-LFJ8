"""Build and exercise the portable controller on this computer."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

from hydraulic_port import replace_once, write_port


CONTROLLER = Path(__file__).resolve().parent
TOYOTA = CONTROLLER / "vendor" / "toyota"
CONTROLLER_SOURCES = ("src/rbm_u340e.c", "src/rbm_u340e_runtime.c", "src/rbm_u340e_scheduler.c")
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


def stage_toyota_sources(destination: Path) -> None:
    """Adapt a verified copy of the donor sources for host and target builds."""
    shutil.copytree(TOYOTA / "src", destination)
    header = destination / "donor_calibration.h"
    shared = destination / "donor_shared_calibration.c"
    declarations = header.read_text(encoding="utf-8")
    definitions = shared.read_text(encoding="utf-8")
    for name in ("learning_001C3C", "pressure_0015FC", "gear_000D08"):
        pattern = rf"^static (const uint8_t {name}\[\d+\])=(\{{[\d,]+\}});$"
        match = re.search(pattern, declarations, re.MULTILINE)
        if match is None:
            raise ValueError(f"Missing donor calibration definition: {name}")
        declarations = replace_once(declarations, match[0], f"extern {match[1]};")
        definitions += f"\n{match[1]}={match[2]};\n"
    header.write_text(declarations, encoding="utf-8")
    shared.write_text(definitions, encoding="utf-8")

    learning = destination / "factory_learning.c"
    source = learning.read_text(encoding="utf-8")
    # Subtract the donor base before adding an offset to the C array.
    source = replace_once(source, "learning_001C3C+a-0x1c3c", "learning_001C3C+(a-0x1c3c)")
    learning.write_text(source, encoding="utf-8")

    gears = destination / "factory_gears.c"
    source = gears.read_text(encoding="utf-8")
    source = replace_once(source, "static int gears_step(FactoryGearState *s)",
                          "static int gears_step(FactoryGearState *s, uint8_t requested_gear)")
    source = replace_once(source, "    if(!request_maps(s)) return 0;\n",
                          """    if(!request_maps(s)) return 0;
    /* Project input at the map output, ahead of every donor shift guard.
     * Neutral and the donor alternate strategy keep their original request. */
    if (requested_gear && !(B(7252) & 1u) && !(B(4845) & 8u) && !(B(4844) & 2u)) {
        B(4854) = (uint8_t)(requested_gear - 1u);
    }
""")
    source = replace_once(source, "if(!gears_step(&t)||!valid_gear(&t)) return 0;",
                          "if(!gears_step(&t, 0)||!valid_gear(&t)) return 0;")
    source = replace_once(source, """int factory_gears_outputs_step(FactoryGearState *p,FactoryGearWrites *writes) {
    if(!valid_gear(p)||!writes||p->driver5302[0]>4||p->driver5302[1]>4) return 0;
    FactoryGearState t=*p,*s=&t;
    if(!gears_step(s)||!valid_gear(s)) return 0;""", """int rbm_factory_gears_outputs_step(FactoryGearState *p, FactoryGearWrites *writes,
                                   uint8_t requested_gear) {
    if(requested_gear>4||!valid_gear(p)||!writes||p->driver5302[0]>4||p->driver5302[1]>4) return 0;
    FactoryGearState t=*p,*s=&t;
    if(!gears_step(s, requested_gear)||!valid_gear(s)) return 0;""")
    source = replace_once(source, "#define RETURN_WRAPPER(a,type)", """int factory_gears_outputs_step(FactoryGearState *p, FactoryGearWrites *writes) {
    return rbm_factory_gears_outputs_step(p, writes, 0);
}
#define RETURN_WRAPPER(a,type)""")
    gears.write_text(source, encoding="utf-8", newline="\n")


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
    policy_test = CONTROLLER / "tests/test_mode_policy.c"
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
        vendor_src = stage / "vendor"
        stage_toyota_sources(vendor_src)
        port = write_port(vendor_src, stage)
        source_args = [str(CONTROLLER / path) for path in CONTROLLER_SOURCES]
        source_args.extend(str(vendor_src / path.name) for path in vendor_files
                           if path.suffix == ".c" and path.name != "factory_hydraulics.c")
        source_args.append(str(port))
        subprocess.run([*driver, *flags, *shared, *source_args, "-o", str(stage / library)], check=True)
        subprocess.run(
            [*driver, *flags, "-DRBM_TEST_TRANSFERS", "-DRBM_TEST_RUNTIME", *source_args,
             *map(str, test_sources), "-o", str(stage / executable)],
            check=True,
        )
        policy_executable = stage / ("mode_policy_test" + Path(executable).suffix)
        subprocess.run([*driver, *flags, *source_args, str(policy_test), "-o", str(policy_executable)],
                       check=True)
        tests = "\n".join(subprocess.check_output([str(program)], text=True).strip()
                          for program in (stage / executable, policy_executable))
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
                    policy_test,
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
