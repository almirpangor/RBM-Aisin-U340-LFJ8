"""Verify the Chery S02 CAN scheduler, clock settings, and request cadence."""

import argparse
import hashlib
import json
from pathlib import Path
import struct


S02_SHA256 = "99dc271a861ab6d9e6749e8beb4637ab5c6c7e111f3ff0d9df4e147b2a0a6e1c"


def unpack(image: bytes, offset: int, size: int) -> int:
    return int.from_bytes(image[offset:offset + size], "little")


def check_bytes(image: bytes, signatures: dict[int, str]) -> None:
    for offset, hex_bytes in signatures.items():
        expected = bytes.fromhex(hex_bytes)
        if image[offset:offset + len(expected)] != expected:
            raise ValueError(f"Instruction sequence differs at 0x{offset:06X}")


def verify(image: bytes) -> dict:
    if len(image) != 851_968 or hashlib.sha256(image).hexdigest() != S02_SHA256:
        raise ValueError("S02 size or SHA-256 is different")

    check_bytes(image, {
        0x018BDA: "e6f30000 62f344ff e6f10600 0031 f6f344ff",
        0x018BF0: "e6f2bfff 9120 74f244ff",
        0x094232: "e6f20d03 8820 e01c e6fd3840 e6fe0900 d4f00200 da01ee92",
        0x094038: "f2f41688 2d07 f0c4 da013c88",
        0x094B88: "e6f27222 f6f21688",
        0x094BD2: "e6f28222 f6f21688",
        0x094126: "c2f4c2f7 22f4fa1d f094 4840 bd11 f2f4f81d 1b49 f2f40efe 06f40d03",
        0x09415E: "e01c f2fdfc87 da010e97",
        0x0946C6: "da025404 da0a362a",
        0x09483A: "da0a362a",
        0x0A2B16: "d7402a00 f2f4a622 6842 4842 3d05 da0aa21c e08c da023005",
        0x0A2B96: "d7402a00 f2f4a622 66f42000 46f42000 3d05 da0acc1f e0cc da023005",
        0x0A2BC8: "f3f8778c 4980 fd04 2981 f7f8778c 0d25",
        0x0A2BDC: "da02fe05 f084 f095 4890 3d09 46f8ae01 3d06 da0af421",
        0x0A2BFE: "43f8ae05",
        0x0A2C1C: "e118 f7f8778c",
        0x0A2C38: "f3f8768c 4980 fd04 2981 f7f8768c 0d25",
        0x0A2C4C: "da02fe05 f084 f095 4890 3d09 46f80003 3d06 da0a7224",
        0x0A2C6E: "43f8af05",
        0x0A2C8C: "e158 f7f8768c",
        0x0A29D8: "e01c da09103a da0ad027",
        0x093A46: "e6fc036b f6fc06ef",
        0x093A84: "f68e0cef",
    })

    def task_descriptor(offset: int) -> dict:
        list_offset = 0xB8000 + unpack(image, offset, 2)
        task, continuation = struct.unpack_from("<II", image, list_offset)
        return {"record": f"0x{offset:06X}", "task": f"0x{task:06X}",
                "continuation": f"0x{continuation:06X}"}

    tasks = [task_descriptor(address) for address in (0xBA272, 0xBA282)]
    if [record["task"] for record in tasks] != ["0x09454A", "0x0947DA"]:
        raise ValueError("CAN task descriptor mismatch")

    prescaler = 1 << (3 + (image[0x018BE4] & 7))
    base_ticks = unpack(image, 0x094234, 2)
    extension_threshold = unpack(image, 0xB9DFA, 2)
    extension_factor = unpack(image, 0xB9DF8, 2)
    max_ticks = base_ticks + extension_factor * max(255 - extension_threshold, 0)
    btr = unpack(image, 0x093A48, 2)
    time_quanta = 1 + (((btr >> 8) & 15) + 1) + (((btr >> 12) & 7) + 1)
    baud_divisor = ((btr & 63) + 1) * time_quanta
    tx_mask = unpack(image, 0xAA2A6, 2)

    return {
        "input": "S02",
        "sha256": S02_SHA256,
        "callback": "0x094038",
        "can_service": "0x0A2A36",
        "tasks": tasks,
        "clock": {
            "timer": "GPT1 T4",
            "timer_cpu_divisor": prescaler,
            "initial_period_ticks": base_ticks,
            "max_calibrated_period_ticks": max_ticks,
            "period_ms_at_40mhz": [round(period * prescaler / 40_000, 6)
                                      for period in (base_ticks, max_ticks)],
            "can1_btr": f"0x{btr:04X}",
            "can_clock_divisor_per_bit": baud_divisor,
        },
        "rx_calibration_mask": f"0x{image[0xA818A]:02X}",
        "frames": {
            "0x0FA": {"tx_mask_set": bool(tx_mask & 0x20), "request_every_task_calls": 1},
            "0x278": {"tx_mask_set": bool(tx_mask & 0x02), "request_every_task_calls": 1},
            "0x1AE": {"poll_every_task_calls": 2, "timeout_missed_polls": image[0xB85AE] + 1},
            "0x300": {"poll_every_task_calls": 6, "timeout_missed_polls": image[0xB85AF] + 1},
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, help="Path to CHERY_REFERENCE_DO_NOT_FLASH.bin")
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.image.read_bytes()), indent=2))
    except (OSError, ValueError) as error:
        parser.exit(1, f"Verification failed: {error}\n")


if __name__ == "__main__":
    main()
