"""Run the H03 input proposal with the built controller on PC or M32R."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
from shutil import copyfile
from tempfile import TemporaryDirectory

from check_h03_selector_adc import run


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCES = ("lfj8_selector_adc.c", "lfj8_range_control.c",
           "lfj8_h03_input_binding.c", "lfj8_h03_button_capture.c", "test_lfj8_h03_input_binding.c")
FLAGS = ("-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-I.")
M32R = ("-m32r", "-Wa,-EB", "-mmodel=medium", "-msdata=none")


def check(compiler, controller, m32r):
    with TemporaryDirectory(prefix="rbm-h03-inputs-") as temporary:
        stage = Path(temporary)
        for folder in ("controller/include", "controller/vendor/toyota/include", "targets/lfj8"):
            for header in (ROOT / folder).glob("*.h"):
                copyfile(header, stage / header.name)
        for source in SOURCES:
            copyfile(HERE / source, stage / source)
        staged = stage / controller.name
        copyfile(controller, staged)
        digest = sha256(staged.read_bytes()).hexdigest()
        version = run(stage, compiler, "--version" if m32r else "version").splitlines()[0]
        if m32r:
            if run(stage, compiler, "-dumpmachine").strip() != "m32r-elf":
                raise ValueError("A bare-metal M32R compiler is required")
            startup = run(stage, compiler, *M32R, "-print-file-name=crt0.o").strip()
            (stage / "startup.c").write_text("void __init(void) {}\nvoid __fini(void) {}\n",
                                             encoding="ascii")
            run(stage, compiler, *M32R, *FLAGS, "-Wno-missing-braces",
                "-Wno-missing-field-initializers", "-nostartfiles", startup, "startup.c",
                *SOURCES, staged.name, "-Wl,-e,_start", "-Wl,--start-group", "-lc",
                "-lgloss", "-lgcc", "-Wl,--end-group", "-o", "input-binding.elf")
            simulator = compiler.with_name(f"m32r-elf-run{compiler.suffix}")
            output = run(stage, simulator, "input-binding.elf")
        else:
            # The test uses the shared library produced by controller/build.py.
            runtime = () if staged.suffix == ".dll" else ("-Wl,-rpath,$ORIGIN",)
            executable = stage / ("input-binding.exe" if staged.suffix == ".dll" else "input-binding")
            run(stage, compiler, "cc", *FLAGS, *SOURCES, staged.name, *runtime, "-o", executable)
            output = run(stage, executable)
    output = output.strip()
    if not output.startswith("H03 input proposal:") or not output.endswith(" PASS"):
        raise ValueError(f"The input proposal test did not report success: {output}")
    return {"status": "PASS", "target": "M32R simulator" if m32r else "PC", "compiler": version,
            "controller_sha256": digest, "test_output": output, "hardware_executed": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    compiler = parser.add_mutually_exclusive_group(required=True)
    compiler.add_argument("--zig", type=Path)
    compiler.add_argument("--gcc", type=Path, help="M32R bare-metal GCC")
    parser.add_argument("--controller", required=True, type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.out and (args.out.suffix.lower() != ".json" or args.out.resolve() == args.controller.resolve() or
                     (args.out.exists() and args.out.samefile(args.controller))):
        parser.error("--out must be a separate JSON report")
    try:
        report = check((args.gcc or args.zig).resolve(), args.controller.resolve(), args.gcc is not None)
        text = json.dumps(report, indent=2) + "\n"
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(text, encoding="utf-8")
        print(text, end="")
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
