"""Independently verify the pinned S01 scheduler cadence evidence and the H03 clock scale."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from struct import unpack_from
import sys

S01_SHA256 = "a3cd723e7e21bf547ca4c17ec49a1e098d203773547dba4d7af21991a2cbead1"
S01_BRANCHES = {
    0x000090: 0x085058, 0x01404A: 0x017ED2, 0x017ED6: 0x01A376,
    0x013FA4: 0x0140E2, 0x013FBE: 0x085418,
    0x0144A4: 0x085418, 0x0144D6: 0x085B3C,
    0x01454C: 0x01430A, 0x014326: 0x0510B4, 0x0510F8: 0x05425C,
    0x01456E: 0x01432E, 0x014378: 0x0511A6, 0x05123A: 0x05421C,
    0x051366: 0x0540E4,
}


def branch(rom, site):
    """V850 22-bit JR/JARL with signed displacement and no delay slot."""
    head, tail = unpack_from("<HH", rom, site)
    if head & 0x07C0 != 0x0780 or tail & 1:
        raise ValueError(f"Expected wide JR/JARL at {site:#x}")
    offset = ((head & 0x3F) << 16) | tail
    if offset & (1 << 21):
        offset -= 1 << 22
    return site + offset


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("s01", "listing", "v850-vm", "h03", "repo", "out"):
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    rom = args.s01.read_bytes()
    require(len(rom) == 753664 and sha256(rom).hexdigest() == S01_SHA256, "Wrong S01 donor")
    for site, target in S01_BRANCHES.items():
        require(branch(rom, site) == target, f"Unexpected S01 branch at {site:#x}")
    require(unpack_from("<I", rom, 0x9D4 + 4 * 9)[0] == 0x13F96, "Unexpected ECR 0x90 dispatch")
    require(rom[0x2774:0x2776] == b"\x07\x00", "Unexpected task mask")
    require(rom[0x1A376:0x1A386].hex() == "20868000408700fbc0bf12f1c08f00f1", "S01 IRQ setup changed")
    table = unpack_from("<8I", rom, 0xAAA4)
    require(all((target == 0x51246) == (slot % 2 == 0) for slot, target in enumerate(table)),
            "Unexpected S01 MAIN dispatch table")

    sys.path.insert(0, str(args.v850_vm))
    import v850_subset
    vm = v850_subset.V850(rom, args.listing.read_text(encoding="utf-8"))
    gp = v850_subset.GP
    vm.write(0xFFFFF100, 1, 0xFF)
    vm.write(0xFFFFF112, 1, 0xFF)
    vm.run(0x017ED2)
    require([vm.read(address, 1) for address in (0xFFFFFB00, 0xFFFFF112, 0xFFFFF100)] ==
            [0x80, 0x7F, 0xFD], "S01 IRQ initialization register effects differ")

    vm.write(gp - 3296, 2, 0)
    vm.write(gp - 9490, 2, 0)
    vm.write(gp - 6191, 1, 1)
    vm.write(gp - 1601, 1, 0)
    vm.write(gp - 3285, 1, 0)
    vm.write(gp - 3289, 1, 100)
    vm.write(0xFFFFF408, 1, 0xC0)
    activations = []
    fast_posts = []

    def activate(machine):
        activations.append(machine.r[6])
        machine.r[10] = 0

    def set_event(machine):
        fast_posts.append((machine.r[6], machine.r[7]))
        machine.r[10] = 0

    def hook_without_effect(_):
        pass

    rows = []
    for irq in range(16):
        activations.clear()
        fast_posts.clear()
        vm.run(0x013F96, hooks={0x085418: activate})
        require(activations == [2], "S01 IRQ failed to activate the producer")
        require(vm.read(gp - 3296, 2) == irq + 1, "S01 IRQ count did not advance")
        vm.run(0x014484, hooks={
            0x0142E6: hook_without_effect, 0x085418: activate, 0x085B3C: set_event,
            0x0141AC: hook_without_effect, 0x01416E: hook_without_effect, 0x085518: hook_without_effect,
        })
        require(vm.read(gp - 9490, 2) == irq + 1, "S01 task 2 count did not advance")
        require(activations == ([2, 22] if irq % 8 == 4 else [2]), "S01 secondary request differs")
        require(fast_posts == ([(1, 1)] if irq % 4 == 2 else []), "S01 FAST post differs")
        pin_high = bool(vm.read(0xFFFFF408, 1) & 0x20)
        require(pin_high == (irq % 8 < 4), "S01 heartbeat phase differs")
        rows.append({"irq_index_before_increment": irq, "pin_high": pin_high,
                     "fast_post": bool(fast_posts), "secondary_post": len(activations) == 2})

    sys.path.insert(0, str(args.repo / "targets/lfj8"))
    from check_h03_bench_sensor_profile import check_stock
    h03 = check_stock(args.h03)
    require((h03["top10_ticks"], h03["phase_ticks"], h03["tml_nominal_hz"]) ==
            (500, 5000, 1000000), "Unexpected H03 ROM-derived nominal clock profile")
    report = {
        "status": "PASS_LOGICAL_CADENCE_AND_H03_NOMINAL_SCALE",
        "s01_sha256": S01_SHA256,
        "s01_ecr": "0x0090",
        "s01_vector_branch": "0x000090 -> 0x085058",
        "s01_dispatch_entry": "0x0009F8 -> 0x013F96",
        "s01_setup": {
            "routine": "0x01A376",
            "register_writes": ["0xFFFFFB00 = 0x80", "clear 0xFFFFF112.7", "clear 0xFFFFF100.1"],
            "clock_reset_control_site": "0x012C6C..0x012CB6",
            "mcu_part_or_clock_rate_proven": False,
        },
        "s01_running_gpio": "0xFFFFF408.5",
        "irq_per_same_edge": 8,
        "irq_per_fast_secondary_main": [4, 8, 16],
        "s01_irq_s": None,
        "h03_oem_nominal": h03,
        "rows": rows,
        "qualification": {
            "full_rtos_or_peripheral_emulated": False,
            "source_paths": "Exact S01 IRQ and producer instructions with OS entry stubs",
            "absolute_toyota_timing_proven": False,
            "physical_clock_and_target_latency_measured": False,
        },
    }
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in (
        "status", "s01_sha256", "s01_setup", "irq_per_same_edge", "irq_per_fast_secondary_main",
        "qualification",
    )}, indent=2))


if __name__ == "__main__":
    main()

