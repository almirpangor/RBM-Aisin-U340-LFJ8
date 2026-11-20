"""Run the CAN owner register model on PC or M32R."""

import argparse
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

from check_h03_dtc_foreground import DIAGNOSTIC_SOURCES, FLAGS, LFJ8_SOURCES
from check_h03_link import HERE, ROOT, TARGET, elf_info


def check(compiler: Path, controller: Path) -> str:
    driver = (compiler, "cc") if compiler.stem.casefold() == "zig" else (compiler,)
    sources = [HERE / name for name in LFJ8_SOURCES if not name.startswith("test_")]
    sources.extend((HERE / "lfj8_h03_can_owner.c", HERE / "test_lfj8_h03_can_owner.c"))
    sources.extend(ROOT / "diagnostics" / name for name in DIAGNOSTIC_SOURCES)
    includes = ("-I", HERE, "-I", ROOT / "diagnostics", "-I", ROOT / "controller/vendor/toyota/include")

    with TemporaryDirectory(prefix="rbm-h03-can-owner-") as directory:
        stage = Path(directory)
        library = stage / controller.name
        shutil.copyfile(controller, library)

        def run(*args) -> str:
            return subprocess.run([str(arg) for arg in args], cwd=stage, check=True,
                                  capture_output=True, text=True, timeout=60).stdout.strip()

        if run(*driver, "-dumpmachine") == "m32r-elf":
            elf_info(library, 1)
            start = run(compiler, *TARGET, "-print-file-name=crt0.o")
            hooks = stage / "crt_hooks.c"
            hooks.write_text("void __init(void) {}\nvoid __fini(void) {}\n", encoding="ascii")
            run(compiler, *TARGET, *FLAGS, *includes, "-Wno-missing-braces", "-Wno-missing-field-initializers",
                "-nostartfiles", start, *sources, hooks, HERE / "h03_can0_setup_hook.S", library,
                "-Wl,--gc-sections,-e,_start,--start-group", "-lc", "-lgloss", "-lgcc",
                "-Wl,--end-group", "-o", "fixture.elf")
            simulator = compiler.with_name(f"m32r-elf-run{compiler.suffix}")
            output = run(simulator, "fixture.elf")
        else:
            executable = stage / ("fixture.exe" if sys.platform == "win32" else "fixture")
            rpath = {"win32": (), "darwin": ("-Wl,-rpath,@loader_path",)}
            run(*driver, *FLAGS, *includes, *sources, library, *rpath.get(sys.platform, ("-Wl,-rpath,$ORIGIN",)),
                "-o", executable)
            output = run(executable)
    if not output.startswith("H03 CAN owner:") or " PASS\n" not in output:
        raise ValueError(f"The CAN owner fixture did not report PASS: {output}")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cc", required=True, type=Path)
    parser.add_argument("--controller", required=True, type=Path)
    args = parser.parse_args()
    try:
        print(check(args.cc.resolve(), args.controller.resolve()))
    except subprocess.CalledProcessError as error:
        detail = "\n".join(filter(None, (error.stdout, error.stderr))) or str(error)
        parser.exit(1, detail + "\n")
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
