"""Audit the original H03 CAN0 paths used by the torque mailbox adapter."""

import argparse
from hashlib import sha256
import json
from pathlib import Path

from check_h03_link import identify_h03


def addresses(values):
    return [f"0x{value:06X}" for value in values]


def check_words(rom, words):
    evidence = {}
    for address, expected in words.items():
        expected = bytes.fromhex(expected)
        if rom[address:address + len(expected)] != expected:
            raise ValueError(f"Unexpected H03 bytes at {address:#08x}")
        evidence[f"0x{address:06X}"] = expected.hex().upper()
    return evidence


def scan_direct_references(rom):
    """Scan operand encodings for fixed-offset 32-bit loads and relative BLs."""
    slot_loads = {offset: [] for offset in (0x2658, 0x265C, 0x269C, 0x26DC, 0x271C, 0x275C)}
    calls = {entry: [] for entry in (0xC34C, 0xC538, 0x465F8)}
    for base in range(0, len(rom), 4):
        word = rom[base:base + 4]
        if word[0] & 0xF0 == 0xA0 and word[1] & 0xF0 == 0xC0:
            offset = int.from_bytes(word[2:], "big")
            if offset in slot_loads:
                slot_loads[offset].append(base)
        if word[0] == 0xFE:
            target = base + 4 * int.from_bytes(word[1:], "big", signed=True)
            if target in calls:
                calls[target].append(base)
        elif word[0] < 0x80:
            for half in (0, 2):
                if word[half] == 0x7E:
                    displacement = int.from_bytes(word[half + 1:half + 2], "big", signed=True)
                    target = base + 4 * displacement
                    if target in calls:
                        calls[target].append(base + half)
    if slot_loads != {
        0x2658: [0xBC48, 0xC550, 0xC600], 0x265C: [0xBC04, 0xC030, 0xC378, 0xC4D0],
        0x269C: [0xC440], 0x26DC: [0xC454], 0x271C: [0xC468], 0x275C: [0xC380],
    } or calls != {0xC34C: [0xC338, 0xC346], 0xC538: [0x46734], 0x465F8: [0x465D0]}:
        raise ValueError("The fixed-offset CAN0 loads or direct calls differ from the H03 audit")
    return slot_loads, calls


def check(base):
    identity = identify_h03(base)
    rom = base.read_bytes()
    if sha256(rom).hexdigest() != identity["sha256"]:
        raise ValueError("H03 changed while the audit was being prepared")

    rx_table = 0x032EC4
    rx_ids = [int.from_bytes(rom[address:address + 2], "big")
              for address in range(rx_table, rx_table + 11 * 16, 16)]
    if rx_ids != [0x200, 0x201, 0x211, 0x215, 0x240, 0x420, 0x430, 0x4B0, 0x4EC, 0x4F1, 0xFFFF]:
        raise ValueError("The H03 default RX table differs from the audit")
    loads, calls = scan_direct_references(rom)

    signal_loads = (0x380CC, 0x380EC, 0x38114, 0x38130, 0x38150, 0x38168)
    slot5 = check_words(rom, {
        0x01652A: "01", 0x008358: "e401652a20946301b0030015", 0x0083C4: "d3c0000383a32ec42364",
        0x032F04: "02400800000000000000000000000000",
        0x00BF48: "e7806b1206a720966240f000b0120027", 0x00BF78: "60402002",
        0x00BFAC: "e0804a2000a8f000feffff6a", 0x00BDE4: "e4804a2042f804a2",
        0x0373EC: "e401652a20946101b0110044", 0x037408: "fe000329",
        0x0372D8: "feff4537", 0x0087E4: "fe000d6f1980108bfe000d84",
        **{address: "90f00240" for address in signal_loads},
    })
    slot12 = check_words(rom, {
        0x032658: "0080105c", 0x00BC14: "60002024", 0x00BC2C: "02c05250b082000e",
        0x0465B4: "610000c1b080000f", 0x0465D0: "7e0af000", 0x046734: "feff1781",
        0x00C600: "a1c5265892f000802201f000",
    })
    slot13 = check_words(rom, {
        0x03265C: "0080105d", 0x00BC04: "a1c5265c62002201", 0x00B7D0: "fe0000c9",
        0x00B878: "fe00009f", 0x00C020: "e4804ae82094f000b080001d",
        0x00C030: "a0c5265c2190515f01917c04", 0x00C338: "7e05f000",
        0x00C344: "2e7f7e02", 0x00C34C: "2e7f2a7f", 0x00C418: "67002701",
        0x00C4D0: "a1c6265c92f0008022017f04", 0x00C630: "7e13f000",
        0x00C680: "82c1ffff63100253", 0x00C6A4: "84a4262804a027c4620f2207",
        0x00010C: "000009d8", 0x0009D8: "00004724", 0x001128: "e4008003",
        0x004728: "e180100c20b1f00082c08003", 0x00475C: "e180100c20b1505d00907d07",
        0x004768: "e200fffb2221f000", 0x00477C: "fe000e48", 0x00809C: "ff0010aa",
        0x00B8D4: "e100800744fb2124", 0x00B97C: "e100800744fb2124",
    })
    basic = check_words(rom, {
        0x00B910: "22006118e4801030210444012204f000",
        0x00B930: "2203621843042203e480103962002204",
        0x00BA00: "e180103020916218", 0x00BA50: "e180103820916218",
        0x004738: "fefff32e", 0x001500: "680ff000", 0x001514: "630e0253",
        0x00152C: "00b02021", 0x001544: "02c32201", 0x001560: "fe0009e1",
        0x0015B8: "83a33d30", 0x003D30: "1f211f1f1802",
    })

    return {
        "base": identity,
        "default_receive_slots_1_through_10": [f"0x{value:03X}" for value in rx_ids[:-1]],
        "slot5": {"id": "0x240", "decoder": "0x0380AC", "bitfield_decodes": 6,
                  "receive_buffer": "0x804A40", "evidence": slot5},
        "slot12": {"native_static_tx_entry": "0x00C538", "tx_caller_gate": "constant_zero",
                   "init_tx_gate": "constant_zero", "evidence": slot12},
        "slot13": {
            "native_tx_writer_entry": "0x00C34C",
            "foreground_call": "0x00C338",
            "irq_path": addresses((0x00477C, 0x00809C, 0x00C344, 0x00C34C)),
            "native_init_control_zero": "0x00BC08",
            "watchdog_control_read": "0x00C034",
            "recovery_all_slot_abort": "0x00C67C",
            "native_irq_list_write_value": "0xFFFB",
            "evidence": slot13,
        },
        "basic_can_14_15": {"standard_high_id_mask": "0x18", "accepted_ids": "0x600-0x7FF",
                            "includes_0x5E9": False, "evidence": basic},
        "fixed_offset_ld_candidates": {f"0x03{offset:04X}": addresses(sites) for offset, sites in loads.items()},
        "direct_bl_candidates": {f"0x{target:06X}": addresses(sites) for target, sites in calls.items()},
        "scope": "Original H03 static evidence, including indexed recovery writes. No CAN hardware timing measured.",
        "hardware_executed": False,
        "flashable_image": None,
    }


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--base", required=True, type=Path)
    cli.add_argument("--out", type=Path)
    args = cli.parse_args()
    if args.out and (args.out.suffix.lower() != ".json" or args.out.resolve() == args.base.resolve()):
        cli.error("--out must be a separate JSON report")
    try:
        report = json.dumps(check(args.base), indent=2) + "\n"
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(report, encoding="utf-8")
        print(report, end="")
    except (OSError, ValueError) as error:
        cli.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()
