"""Run the H03 BasicCAN RX queue and CAN13 foreground model on PC or M32R."""

import argparse
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

from check_h03_link import HERE, ROOT, TARGET, elf_info


LFJ8_SOURCES = (
    "lfj8_bridge.c", "lfj8_donor_io.c", "lfj8_chery_tx.c", "lfj8_h03_torque.c",
    "lfj8_h03_torque_can.c", "lfj8_h03_dtc_can.c", "lfj8_h03_can13.c",
    "lfj8_h03_dtc_rx_queue.c", "lfj8_h03_dtc_foreground.c", "test_lfj8_h03_dtc_foreground.c",
)
DIAGNOSTIC_SOURCES = ("chery_dtc.c", "chery_dtc_can.c", "chery_dtc_link.c")
FLAGS = ("-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
         "-ffunction-sections", "-fdata-sections", "-I.")


def check(compiler, controller):
    diagnostics = ROOT / "diagnostics"
    toyota_headers = ROOT / "controller/vendor/toyota/include"
    with TemporaryDirectory(prefix="rbm-h03-dtc-foreground-") as directory:
        stage = Path(directory)
        for source_dir, sources in ((HERE, LFJ8_SOURCES), (diagnostics, DIAGNOSTIC_SOURCES),
                                    (toyota_headers, ())):
            for path in (*(source_dir / name for name in sources), *source_dir.glob("*.h")):
                shutil.copyfile(path, stage / path.name)
        library = stage / controller.name
        shutil.copyfile(controller, library)

        def run(*args):
            return subprocess.run([str(arg) for arg in args], cwd=stage, check=True,
                                  capture_output=True, text=True, timeout=60).stdout.strip()

        sources = (*LFJ8_SOURCES, *DIAGNOSTIC_SOURCES)
        driver = (compiler, "cc") if compiler.stem.casefold() == "zig" else (compiler,)
        if run(*driver, "-dumpmachine") == "m32r-elf":
            elf_info(library, 1)
            start = run(compiler, *TARGET, "-print-file-name=crt0.o")
            (stage / "crt_hooks.c").write_text("void __init(void) {}\nvoid __fini(void) {}\n", encoding="ascii")
            run(compiler, *TARGET, *FLAGS, "-Wno-missing-braces", "-Wno-missing-field-initializers",
                "-nostartfiles", start, *sources, "crt_hooks.c", library.name,
                "-Wl,--gc-sections,-e,_start,--start-group", "-lc", "-lgloss", "-lgcc",
                "-Wl,--end-group", "-o", "fixture.elf")
            simulator = compiler.with_name(f"m32r-elf-run{compiler.suffix}")
            output = run(simulator, "fixture.elf")
        else:
            suffix = ".exe" if sys.platform == "win32" else ""
            executable = stage / f"fixture{suffix}"
            rpath = {"win32": (), "darwin": ("-Wl,-rpath,@loader_path",)}
            run(*driver, *FLAGS, *sources, library.name, *rpath.get(sys.platform, ("-Wl,-rpath,$ORIGIN",)),
                "-o", executable)
            output = run(executable)
        if (not output.startswith("PASS H03 DTC foreground:") or "\nPASS BasicCAN pair:" not in output
                or "\nPASS BasicCAN dispatch markers:" not in output):
            raise ValueError(f"The fixture did not report a passing result: {output}")
        return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cc", required=True, type=Path)
    parser.add_argument("--controller", required=True, type=Path,
                        help="Controller shared library on PC, or relocatable M32R controller object")
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
