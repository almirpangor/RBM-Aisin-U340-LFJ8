"""Verify the Mazda PCM CAN tables against the supplied S05 image."""

import argparse
import hashlib
import json
import struct
from pathlib import Path


def read_frames(image, table, max_slots):
    offset = int(table["file_offset"], 16)
    end_marker = int(table["end_marker"], 16)
    frames = []
    for index in range(max_slots):
        can_id, = struct.unpack_from(">H", image, offset + table["can_id_offset_in_record"])
        if can_id == end_marker:
            return frames
        dlc = image[offset + table["dlc_offset_in_record"]]
        mailbox = table["first_mailbox"] + index * table["mailbox_step"]
        if can_id >= 0x800 or dlc > 8 or not 0 <= mailbox < max_slots:
            raise ValueError(f"Invalid frame descriptor at offset 0x{offset:06X}")
        frames.append({"can_id": f"0x{can_id:03X}", "dlc": dlc, "mailbox": mailbox})
        offset += table["stride_bytes"]
    raise ValueError(f"Missing end marker for table at {table['file_offset']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, help="Path to the original S05 BIN")
    args = parser.parse_args()
    manifest_path = Path(__file__).resolve().parents[1] / "data" / "mazda-pcm-can.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        image = args.image.read_bytes()
        source = manifest["source"]
        digest = hashlib.sha256(image).hexdigest()
        if len(image) != source["size_bytes"] or digest != source["sha256"]:
            raise ValueError(f"S05 identity mismatch. Size {len(image)} bytes, SHA-256 {digest}")

        mailbox = manifest["mailbox_control"]
        offset = int(mailbox["pointer_table_file_offset"], 16)
        base = int(mailbox["register_base"], 16)
        slots = mailbox["max_slots"]
        stride = mailbox["register_stride_bytes"]
        pointers = struct.unpack_from(f">{slots}I", image, offset)
        expected_pointers = tuple(range(base, base + slots * stride, stride))
        if pointers != expected_pointers:
            raise ValueError("The mailbox pointer table does not match the documented register layout")

        for direction, table in manifest["tables"].items():
            frames = read_frames(image, table, slots)
            if frames != table["frames"]:
                raise ValueError(f"The {direction.upper()} descriptors differ from the manifest")
            print(f"{direction.upper()}: {len(frames)} static descriptors match")
    except (OSError, ValueError, KeyError, IndexError, struct.error) as error:
        parser.exit(1, f"Verification failed: {error}\n")

    print(f"S05 SHA-256 {digest}, {slots} mailbox pointers match")


if __name__ == "__main__":
    main()
