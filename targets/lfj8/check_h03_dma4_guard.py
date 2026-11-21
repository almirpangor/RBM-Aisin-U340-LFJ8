"""Verify the DMA4 entry guard against the exact H03 ROM in an M32R ELF."""

import argparse
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from check_h03_link import HERE, TARGET, identify_h03
from check_h03_range_pnp import LAYOUT, START
from check_h03_service_isolation import storage_blocks
from lfj8_h03_service_placement import DMA4_GUARD, policy_ranges, verify_and_overlay


SETTER = DMA4_GUARD.address
SETTER_WORD = DMA4_GUARD.stock.to_bytes(4, "big")
DISPATCH = 0x032768
FIXTURE = r"""
#include "lfj8_h03_service_guard.h"

#define REG8(a) (*(volatile uint8_t *)(uintptr_t)(a))
#define REG16(a) (*(volatile uint16_t *)(uintptr_t)(a))
#define REG32(a) (*(volatile uint32_t *)(uintptr_t)(a))

const Lfj8H03ServicePolicy rbm_h03_service_policy = {
    .count = INVALID_POLICY ? 0u : 2u,
    .ranges = {{PROTECTED_FIRST, PROTECTED_END}, {SECOND_PROTECTED_FIRST, 0x808E90u}},
};

extern void h03_dma4_setter(uint32_t count, uint32_t destination, uint32_t mode);
typedef void (*Setter)(uint32_t, uint32_t, uint32_t);

enum {
    INTERRUPT_ENABLE = 0x40,
    PSW_CURSOR = 0x809F9C,
    DMAC4_CONTROL = 0x800450,
    DMAC4_COUNT = 0x800451,
    DMAC4_SOURCE = 0x800452,
    DMAC4_DESTINATION = 0x800454,
};

static void prime(void)
{
    REG32(PSW_CURSOR) = PSW_CURSOR;
    REG16(0x804910u) = 0x0135u;
    REG8(0x800400u) = 0x09u;
    REG8(0x800401u) = 0x80u;
    REG8(0x800102u) = 0x81u;
    REG8(0x800110u) = 0x82u;
    REG8(0x800116u) = 0x83u;
    REG8(0x800117u) = 0x84u;
    REG8(DMAC4_CONTROL) = 0x25u;
    REG8(DMAC4_COUNT) = 0x07u;
    REG16(DMAC4_SOURCE) = 0x1234u;
    REG16(DMAC4_DESTINATION) = 0x683Au;
}

static uint32_t current_psw(void)
{
    uint32_t psw;
    __asm__ volatile ("mvfc %0,psw" : "=r"(psw));
    return psw;
}

static int unchanged(void)
{
    return REG32(PSW_CURSOR) == PSW_CURSOR && REG16(0x804910u) == 0x0135u &&
           REG8(0x800400u) == 0x09u && REG8(0x800401u) == 0x80u &&
           REG8(0x800102u) == 0x81u && REG8(0x800110u) == 0x82u &&
           REG8(0x800116u) == 0x83u && REG8(0x800117u) == 0x84u &&
           REG8(DMAC4_CONTROL) == 0x25u && REG8(DMAC4_COUNT) == 0x07u &&
           REG16(DMAC4_SOURCE) == 0x1234u && REG16(DMAC4_DESTINATION) == 0x683Au;
}

static int stock_result(uint32_t count, uint32_t dest, uint32_t mode)
{
    return REG32(PSW_CURSOR) == PSW_CURSOR && REG16(0x804910u) == 0u &&
           REG8(0x800400u) == 0xE7u && REG8(0x800401u) == 0x98u &&
           REG8(0x800102u) == 8u && REG8(0x800110u) == 1u &&
           REG8(0x800116u) == 16u && REG8(0x800117u) == (mode ? 9u : 19u) &&
           REG8(DMAC4_CONTROL) == 0x6Du && REG8(DMAC4_COUNT) == (uint8_t)(count - 1u) &&
           REG16(DMAC4_SOURCE) == 0x0115u && REG16(DMAC4_DESTINATION) == (uint16_t)dest;
}

int main(void)
{
    const Setter indirect = (Setter)(uintptr_t)REG32(0x032768u);
    static const struct {
        uint32_t count, destination, mode;
        int deny, via_table, ie;
    } cases[] = {
        {2u,   0x80683Au,   0u, 0, 0, 0},
        {256u, 0x80683Bu,   1u, 0, 1, 1},
        {0u,   0x80683Bu,   0u, 0, 0, 1},
        {258u, 0xFF80683Au, 1u, 0, 1, 0},
        {1u,   PROTECTED_FIRST - 1u,             0u, 0, 0, 0},
        {1u,   PROTECTED_END,                    0u, 0, 0, 1},
        {2u,   PROTECTED_FIRST - 1u,             0u, 1, 1, 1},
        {1u,   PROTECTED_FIRST,                  0u, 1, 0, 0},
        {1u,   0xFF000000u | SECOND_PROTECTED_FIRST, 1u, 1, 1, 1},
        {0u,   PROTECTED_FIRST - 255u,           0u, 1, 0, 1},
        {2u,   0x80FFFFu,   1u, 1, 0, 0},
        {1u,   0x80FFFFu,   1u, 0, 1, 0},
    };
    for (unsigned i = 0; i < sizeof cases / sizeof cases[0]; ++i) {
        prime();
        const Setter setter = cases[i].via_table ? indirect : h03_dma4_setter;
        const uint32_t psw = cases[i].ie ? INTERRUPT_ENABLE : 0u;
        __asm__ volatile ("mvtc %0,psw" : : "r"(psw) : "memory", "cc");
        setter(cases[i].count, cases[i].destination, cases[i].mode);
        const uint32_t restored_ie = current_psw() & INTERRUPT_ENABLE;
        if (restored_ie != psw) {
            return 41 + (int)i;
        }
        if (PATCHED && (INVALID_POLICY || cases[i].deny)) {
            if (!unchanged()) {
                return 1 + (int)i;
            }
        } else if (!stock_result(cases[i].count, cases[i].destination, cases[i].mode)) {
            return 21 + (int)i;
        }
    }
    return 0;
}
"""

SCENARIOS = (
    "known receive buffer through direct entry",
    "known receive buffer through the stock indirect table",
    "zero low byte means 256 transfers",
    "truncated count and destination reach the same effective registers",
    "span ending at protected range start",
    "span beginning at protected range end",
    "partial overlap from below through the stock table",
    "destination inside the primary protected range",
    "low-half alias of the second protected range",
    "overlap via the effective 256-byte count",
    "destination counter crosses the effective bank end",
    "one byte reaches the effective bank end without wrapping",
)


def check(base, compiler, placed_elf=None, storage_report=None):
    identity = identify_h03(base)
    rom = base.read_bytes()
    if rom[SETTER:SETTER + 4] != SETTER_WORD or int.from_bytes(
            rom[DISPATCH:DISPATCH + 4], "big") != SETTER:
        raise ValueError("The OEM DMA4 entry or dispatch table changed")

    with TemporaryDirectory(prefix="rbm-h03-dma4-guard-") as directory:
        work = Path(directory)

        def run(*args, checked=True):
            return subprocess.run([str(arg) for arg in args], cwd=work, capture_output=True,
                                  check=checked, timeout=60)

        def simulate(description):
            result = run(tools["run"], "--memory-size=16M", "fixture.elf", checked=False)
            if result.returncode:
                category, index = divmod(result.returncode - 1, 20)
                if 0 <= category < 3 and index < len(SCENARIOS):
                    raise ValueError(f"{description}: {SCENARIOS[index]} (exit {result.returncode})")
                result.check_returncode()

        def build(model, image, start, patched, invalid, boundaries, modules):
            (work / "h03.rom").write_bytes(image)
            (work / "start.S").write_text(start, encoding="ascii")
            flags = [flag for flag in TARGET if not flag.startswith("-mmodel=")]
            defines = [f"-D{name}={value:#x}u" for name, value in zip(
                ("PROTECTED_FIRST", "PROTECTED_END", "SECOND_PROTECTED_FIRST"), boundaries)]
            run(compiler, *flags, f"-mmodel={model}", "-Os", "-std=c11", "-Wall", "-Wextra", "-Werror",
                "-ffreestanding", "-fno-builtin", "-ffunction-sections", "-fdata-sections", *defines,
                f"-DPATCHED={int(patched)}", f"-DINVALID_POLICY={int(invalid)}", "-I", HERE, "-nostdlib",
                "-Wl,-T,layout.ld,--gc-sections", "start.S", "fixture.c", *modules, "-o", "fixture.elf")
            run(tools["objcopy"], "-j", ".stock", "-O", "binary", "fixture.elf", "linked.rom")
            return (work / "linked.rom").read_bytes()

        (work / "fixture.c").write_text(FIXTURE, encoding="ascii")
        (work / "layout.ld").write_text(
            LAYOUT + f"\nh03_dma4_setter = {SETTER:#x};\nh03_dma4_after_entry = {SETTER + 4:#x};\n",
            encoding="ascii")
        patched_start = START.replace('.incbin "h03.rom"', f'''\
.incbin "h03.rom", 0, {SETTER:#x}
    bra.l rbm_h03_dma4_guard
    .incbin "h03.rom", {SETTER + 4:#x}''')
        tools = {name: compiler.with_name(f"m32r-elf-{name}{compiler.suffix}")
                 for name in ("objcopy", "nm", "run")}
        guard_sizes = {}
        for model, patched, invalid in (
            ("medium", False, False), ("medium", True, False),
            ("small", True, False), ("medium", True, True),
        ):
            linked = build(model, rom, patched_start if patched else START, patched, invalid,
                           (0x806B40, 0x806B60, 0x808E40),
                           (HERE / "h03_dma4_guard.S", HERE / "lfj8_h03_service_guard.c"))
            if patched:
                rows = run(tools["nm"], "-S", "--defined-only", "fixture.elf").stdout.splitlines()
                address, size, _, _ = next(row.split() for row in rows
                                           if row.endswith(b" rbm_h03_dma4_guard"))
                if linked[SETTER:SETTER + 4] != DMA4_GUARD.branch(int(address, 16)):
                    raise ValueError("The mapped setter does not branch to the linked guard")
                guard_sizes[model] = int(size, 16)
                linked = linked[:SETTER] + SETTER_WORD + linked[SETTER + 4:]
            if linked != rom:
                raise ValueError("The simulator link changed other OEM bytes")
            simulate(f"{model}, patched={patched}, invalid policy={invalid}")

        placement = None
        if placed_elf is not None:
            blocks = storage_blocks(storage_report.read_bytes(), identity)
            overlay, placement = verify_and_overlay(rom, placed_elf, policy_ranges(blocks),
                                                    dma4_guard=True)
            first, end = blocks["control"]
            if build("medium", overlay, START, True, False,
                     (first, end, blocks["communication"][0]), ()) != overlay:
                raise ValueError("The simulator did not preserve the verified placed service image")
            simulate("placed service guard and actual candidate policy")

    return {"status": "PASS", "base": identity, "redirect": f"{SETTER:#08x}",
            "scenarios": SCENARIOS, "guard_code_bytes": guard_sizes,
            "verified_placement": placement,
            "invalid_policy_rejected": True, "hardware_tested": False, "flashable_image": None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("base", "gcc", "out"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    parser.add_argument("--placed-elf", type=Path)
    parser.add_argument("--storage-report", type=Path)
    args = parser.parse_args()
    base, compiler, out = args.base.resolve(), args.gcc.resolve(), args.out.resolve()
    if bool(args.placed_elf) != bool(args.storage_report):
        parser.error("--placed-elf and --storage-report must be supplied together")
    inputs = [source.resolve() for source in (base, compiler, args.placed_elf, args.storage_report)
              if source is not None]
    if out.suffix.lower() != ".json" or any(
            out == source or (out.exists() and source.exists() and out.samefile(source)) for source in inputs):
        parser.error("--out must be a separate JSON report")
    try:
        report = check(base, compiler, args.placed_elf, args.storage_report)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print("H03 DMA4 guard: PASS (stock, small, medium, invalid policy)")
    except subprocess.CalledProcessError as error:
        parser.exit(1, (error.stderr or error.stdout or str(error).encode()).decode(errors="replace") + "\n")
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
