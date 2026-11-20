"""Encode eligible local ST10 absolute jumps as equivalent relative jumps."""


def compact_local_branches(part, code):
    """Relocate one contiguous assembler section driven by its instruction listing."""
    locations = {}
    short_jumps = set()
    old_end = part.origin + len(code)
    cursor = part.origin
    old_cursor = part.origin
    for cpu, length, _ in part.rows:
        if cpu != old_cursor or length not in (2, 4):
            raise ValueError(f"Invalid instruction boundary at {cpu:#x}")
        start = cpu - part.origin
        raw = code[start:start + length]
        locations[cpu] = cursor
        if raw[0] == 0xEA:
            target = (cpu & 0xFF0000) | int.from_bytes(raw[2:4], "little")
            old_delta = target - (cpu + 2)
            # Shorter instructions between PC and target only reduce the span.
            if part.origin <= target <= old_end and -256 <= old_delta <= 254:
                short_jumps.add(cpu)
        cursor += 2 if cpu in short_jumps else length
        old_cursor += length
    if old_cursor != old_end:
        raise ValueError("Instruction listing does not cover the section")
    locations[old_end] = cursor

    relocated = bytearray()
    listing = []
    for cpu, length, description in part.rows:
        start = cpu - part.origin
        raw = code[start:start + length]
        position = locations[cpu]
        if raw[0] == 0xEA:
            target = (cpu & 0xFF0000) | int.from_bytes(raw[2:4], "little")
            new_target = locations[target]
            if cpu in short_jumps:
                delta = new_target - (position + 2)
                if delta % 2 or not -256 <= delta <= 254:
                    raise ValueError(f"Relative jump outside range at {cpu:#x}")
                raw = bytes((raw[1] | 0x0D, (delta // 2) & 0xFF))
                description = description.replace("JMPA", "JMPR", 1)
            else:
                raw = raw[:2] + (new_target & 0xFFFF).to_bytes(2, "little")
        elif raw[0] in (0xDA, 0xFA):
            target = (raw[1] << 16) | int.from_bytes(raw[2:4], "little")
            new_target = locations.get(target, target)
            raw = bytes((raw[0], new_target >> 16)) + (new_target & 0xFFFF).to_bytes(2, "little")
        elif raw[0] & 0x0F == 0x0D or raw[0] in (0x8A, 0x9A, 0xAA, 0xBA, 0xCA):
            raise ValueError(f"Unexpected relative or near control flow at {cpu:#x}")
        if position != part.origin + len(relocated):
            raise ValueError(f"Relocated instruction boundary disagrees at {cpu:#x}")
        relocated.extend(raw)
        listing.append((position, len(raw), description))

    part.data = relocated
    part.rows = listing
    part.labels = {name: locations[cpu] for name, cpu in part.labels.items()}
    part.fix.clear()
    return part.finish()
