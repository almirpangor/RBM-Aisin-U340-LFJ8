"""Encode eligible local ST10 absolute jumps as equivalent relative jumps."""


def compact_local_branches(part, code):
    """Relocate one contiguous assembler section within a single code segment."""
    locations = {}
    short_jumps = set()
    old_end = part.origin + len(code)
    segment = part.origin & ~0xFFFF
    if old_end > segment + 0x10000:
        raise ValueError("Compact ST10 section crosses a code segment")
    # An unlabelled end address can be the entry of adjacent stock code.
    end_label = old_end in part.labels.values()
    cursor = part.origin
    old_cursor = part.origin
    for cpu, length, _ in part.rows:
        if cpu != old_cursor or length not in (2, 4) or cpu + length > old_end:
            raise ValueError(f"Invalid instruction boundary at {cpu:#x}")
        start = cpu - part.origin
        raw = code[start:start + length]
        if raw[0] in (0xEA, 0xDA, 0xFA) and length != 4:
            raise ValueError(f"Invalid absolute instruction length at {cpu:#x}")
        locations[cpu] = cursor
        if raw[0] == 0xEA:
            target = segment | int.from_bytes(raw[2:4], "little")
            old_delta = target - (cpu + 2)
            local = part.origin <= target < old_end or (target == old_end and end_label)
            # Shorter instructions between PC and target only reduce the span.
            if local and -256 <= old_delta <= 254:
                short_jumps.add(cpu)
        cursor += 2 if cpu in short_jumps else length
        old_cursor += length
    if old_cursor != old_end:
        raise ValueError("Instruction listing does not cover the section")
    if end_label:
        locations[old_end] = cursor

    relocated = bytearray()
    listing = []
    for cpu, length, description in part.rows:
        start = cpu - part.origin
        raw = code[start:start + length]
        position = locations[cpu]
        opcode = raw[0]
        if opcode in (0xEA, 0xDA, 0xFA):
            target_segment = segment if opcode == 0xEA else raw[1] << 16
            target = target_segment | int.from_bytes(raw[2:4], "little")
            if part.origin <= target < old_end and target not in locations:
                raise ValueError(f"Branch target {target:#x} is not an instruction boundary at {cpu:#x}")
            new_target = locations.get(target, target)
            if cpu in short_jumps:
                delta = new_target - (position + 2)
                if delta % 2 or not -256 <= delta <= 254:
                    raise ValueError(f"Relative jump outside range at {cpu:#x}")
                raw = bytes((raw[1] | 0x0D, (delta // 2) & 0xFF))
                description = description.replace("JMPA", "JMPR", 1)
            elif new_target != target:
                selector = raw[1] if opcode == 0xEA else new_target >> 16
                raw = bytes((opcode, selector)) + (new_target & 0xFFFF).to_bytes(2, "little")
        elif opcode & 0x0F == 0x0D or opcode in (0x8A, 0x9A, 0xAA, 0xBA, 0xCA):
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
