"""Rebuild the scoped H03 IRQ/DMA4 simulator image with the M32R toolchain."""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
LFJ8 = ROOT / "project/targets/lfj8"
sys.path.insert(0, str(LFJ8))
import lfj8_h03_service_placement as service

ASSEMBLY = ("h03_dma4_guard.S", "h03_dtc_rx_hook.S", "h03_dtc_rx_redirects.S", "h03_service_guard_hooks.S")
C_SOURCES = ("lfj8_selector_adc.c", "lfj8_donor_io.c", "lfj8_h03_dtc_can.c", "lfj8_h03_dtc_rx_queue.c",
             "lfj8_h03_dtc_target.c", "lfj8_h03_service_guard.c")
FLAGS = ("-m32r", "-mmodel=small", "-msdata=none", "-Wa,-EB")
CFLAGS = ("-Os", "-std=c11", "-ffreestanding", "-fno-builtin", "-fno-common",
          "-ffunction-sections", "-fdata-sections")


def rebuild(gcc, base, output):
    manifest = json.loads((ROOT / "checks/image/H03-M32R.json").read_bytes())
    rom = base.read_bytes()
    if hashlib.sha256(rom).hexdigest() != manifest["source"]["sha256"]:
        raise ValueError("Incorrect H03 input")
    layout = json.loads((HERE / "layout.json").read_bytes())
    with TemporaryDirectory(prefix="rbm-h03-") as directory:
        temp = Path(directory)
        def run(*args):
            subprocess.run([str(gcc), *map(str, args)], cwd=temp, check=True)
        policy = temp / "h03_service_policy.c"
        policy.write_text(service.policy_source(layout["policy_ranges"]), encoding="ascii")
        redirects = temp / "h03_service_writer_redirects.S"
        service.write_redirects(redirects, service.SITES, service.WRITER_ROOTS)
        objects = []
        includes = [LFJ8, ROOT / "project/controller/include",
                    ROOT / "project/controller/vendor/toyota/include", ROOT / "project/diagnostics"]
        include_flags = [argument for path in includes for argument in ("-I", path)]
        for src in [*(LFJ8 / name for name in (*ASSEMBLY, *C_SOURCES)), policy, redirects]:
            defines = ("-DRBM_H03_COMMON_DMA4_GUARD=1", "-DRBM_H03_BENCH_EARLY_LATCHES=1") if src.name == "h03_dma4_guard.S" else ()
            obj = src.stem + ".o"
            run(*FLAGS, *CFLAGS, *defines, *include_flags, "-c", src, "-o", obj)
            objects.append(obj)
        roots = [f"-Wl,--undefined={name}" for name in layout["roots"]]
        # The project combines the bridge before retaining its early interrupt entry points.
        run(*FLAGS, "-fno-use-linker-plugin", "-r", "-nostdlib", *objects, "-o", "modules.o")
        run(*FLAGS, "-fno-use-linker-plugin", "-r", "-nostdlib", "-Wl,--gc-sections",
            *roots, "modules.o", "-Wl,--undefined=__muldi3", "-Wl,--undefined=memcmp",
            "-Wl,--undefined=memcpy", "-Wl,--undefined=memset", "-lgcc", "-lc", "-o", "early-irq.o")
        shutil.copyfile(HERE / "early-irq.ld", temp / "early-irq.ld")
        run(*FLAGS, "-nostdlib", "-Wl,-T,early-irq.ld", "early-irq.o", "-o", "early-irq.elf")
        linked = temp / "early-irq.elf"
        layout["elf_sha256"] = hashlib.sha256(linked.read_bytes()).hexdigest()
        rebuilt = service.early_overlay(rom, linked, layout)
        for region in manifest["writes"]:
            offset = region["address"]
            chunk = rebuilt[offset:offset + region["bytes"]]
            if hashlib.sha256(chunk).hexdigest() != region["after_sha256"]:
                raise ValueError(f"Unexpected code in {region['section']} at {offset:#x}")
        if hashlib.sha256(rebuilt).hexdigest() != manifest["image_sha256"]:
            raise ValueError("Final H03 binary differs from simulator-tested image")
        output.mkdir(parents=True, exist_ok=False)
        shutil.copyfile(linked, output / "early-irq.elf")
        (output / manifest["image_file"]).write_bytes(rebuilt)
        return manifest["image_file"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gcc", type=Path, required=True)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    print(rebuild(args.gcc.resolve(), args.base.resolve(), args.out.resolve()))
