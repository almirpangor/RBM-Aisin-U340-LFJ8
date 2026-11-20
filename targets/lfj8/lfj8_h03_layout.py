"""Strict M32R section placement into explicitly selected H03 candidate windows.

These windows and RAM addresses are hypotheses. A valid ELF never grants
physical ownership, initialized runtime state, or permission to flash a BIN.
"""
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import re
import struct


@dataclass(frozen=True)
class Window:
    name: str
    start: int
    end: int


PROFILES = {
    "two-window": (Window("primary", 0x20000, 0x30000), Window("tail", 0x7C118, 0x7FFFC)),
    "prefix-candidate": (Window("prefix_primary", 0x1F7D0, 0x30000),
                         Window("tail", 0x7C118, 0x7FFFC)),
}
# Application padding only. Boot area below 0x8000 and identity/marker bytes
# are deliberately excluded. FF fill is checked against the exact base.
PROFILES["padding-candidate"] = (
    Window("pad_f5dc", 0xF5DC, 0x10000),
    Window("pad_10af4", 0x10AF4, 0x11000),
    Window("pad_12b2c", 0x12B2C, 0x13000),
    Window("pad_14e68", 0x14E68, 0x15000),
    Window("pad_16c0c", 0x16C0C, 0x17000),
    Window("pad_17d58", 0x17D58, 0x18000),
    Window("pad_18c20", 0x18C20, 0x19000),
    Window("pad_19e58", 0x19E58, 0x1A000),
    Window("pad_1aa1c", 0x1AA1C, 0x1B000),
    Window("pad_1bea0", 0x1BEA0, 0x1C000),
    Window("pad_1cec4", 0x1CEC4, 0x1D000),
    Window("pad_1eabc", 0x1EABC, 0x1F000),
    *PROFILES["prefix-candidate"],
    Window("pad_33084", 0x33084, 0x34000),
    Window("pad_3f608", 0x3F608, 0x3FFC8),
)


class PlacementError(ValueError):
    def __init__(self, message, report):
        super().__init__(message)
        self.report = report


def aligned(value, alignment):
    return (value + alignment - 1) & ~(alignment - 1)


def validate_windows(windows, rom=None):
    previous = 0
    names = set()
    for window in sorted(windows, key=lambda item: item.start):
        if (not re.fullmatch(r"[a-z][a-z0-9_]*", window.name) or window.name in names or
                not 0 <= window.start < window.end <= 0x1000000 or window.start < previous or
                window.start % 4 or window.end % 4):
            raise ValueError("Invalid, duplicate or overlapping placement window")
        if rom is not None and (window.end > len(rom) or
                                rom[window.start:window.end] != b"\xff" * (window.end-window.start)):
            raise ValueError("Candidate is not entirely erased in H03: " + window.name)
        names.add(window.name)
        previous = window.end


def read_elf(path, kind):
    data = Path(path).read_bytes()
    if len(data) < 52 or data[:7] != b"\x7fELF\x01\x02\x01":
        raise ValueError("Expected ELF32 big-endian")
    if struct.unpack_from(">HHI", data, 16) != (kind, 88, 1):
        raise ValueError("Expected the requested M32R ELF type")
    table = struct.unpack_from(">I", data, 32)[0]
    stride, count, strings = struct.unpack_from(">HHH", data, 46)
    if stride != 40 or not count or strings >= count or table+count*stride > len(data):
        raise ValueError("Invalid ELF section table")
    raw = [struct.unpack_from(">10I", data, table+i*stride) for i in range(count)]
    if raw[strings][1] != 3:
        raise ValueError("ELF section names do not reference a string table")
    def blob(entry):
        if entry[1] == 8:
            return b""
        offset, size = entry[4:6]
        if offset+size > len(data):
            raise ValueError("ELF section exceeds file")
        return data[offset:offset+size]
    names = blob(raw[strings])
    def string(table, index):
        if index >= len(table) or b"\0" not in table[index:]:
            raise ValueError("Invalid ELF string")
        return table[index:table.index(b"\0",index)].decode("ascii")
    sections = []
    for index, entry in enumerate(raw):
        name, typ, flags, address, offset, size, link, info, align, entsize = entry
        sections.append({"index":index,"name":string(names,name),"type":typ,"flags":flags,
                         "address":address,"size":size,"alignment":align or 1,"link":link,
                         "entry_size":entsize,"data":blob(entry)})
    symbols = {}
    for section in sections:
        if section["type"] != 2:
            continue
        if section["entry_size"] != 16 or section["size"] % 16 or section["link"] >= len(sections):
            raise ValueError("Invalid ELF symbol table")
        if sections[section["link"]]["type"] != 3:
            raise ValueError("ELF symbols do not reference a string table")
        strings = sections[section["link"]]["data"]
        for offset in range(0,section["size"],16):
            name,value,size,info,other,index=struct.unpack_from(">IIIBBH",section["data"],offset)
            if index >= len(sections) and index < 0xFF00:
                raise ValueError("ELF symbol has an invalid section index")
            if name and info >> 4 in (1,2):
                name=string(strings,name)
                record={"address":value,"size":size,"section":index,"type":info&15}
                if name in symbols and symbols[name] != record:
                    raise ValueError("Conflicting ELF global symbol: "+name)
                symbols[name]=record
    return {"sha256":sha256(data).hexdigest(),"sections":sections,"symbols":symbols}


def alloc_sections(elf):
    result=[]
    names=set()
    for section in elf["sections"]:
        if not section["flags"] & 2 or not section["size"]:
            continue
        if (section["type"] not in (1,8) or section["flags"] & 0x400 or
                section["type"] == 8 and not section["flags"] & 1):
            raise ValueError("Unsupported allocated ELF section: "+section["name"])
        if section["flags"] & 1 and section["type"] != 8:
            raise ValueError("Initialized writable state needs an implemented startup copy: "+section["name"])
        if (not re.fullmatch(r"[.A-Za-z0-9_]+",section["name"]) or section["name"] in names or
                section["alignment"] & (section["alignment"]-1)):
            raise ValueError("Ambiguous name or invalid section alignment")
        names.add(section["name"])
        result.append(section)
    return result


def pack(sections, windows):
    validate_windows(windows)
    cursors={w.name:w.start for w in windows}
    placements=[]
    # Best-fit decreasing. No section is dropped or split. Failure is explicit,
    # not a proof that a more expensive packing search cannot fit the payload.
    for section in sorted(sections,key=lambda s:(-s["size"],-s["alignment"],s["name"])):
        choices=[]
        for w in windows:
            start=aligned(cursors[w.name],section["alignment"])
            if start+section["size"] <= w.end:
                choices.append((w.end-start-section["size"],w.start,w.name,start))
        if not choices:
            raise PlacementError("Retained section does not fit: "+section["name"],{
                "unplaced_section":section["name"],"unplaced_bytes":section["size"],
                "payload_bytes":sum(s["size"] for s in sections),
                "capacity_bytes":sum(w.end-w.start for w in windows),
                "placed_sections":len(placements),"accepted_layout":False})
        _,_,name,start=min(choices)
        placements.append({"section":section["name"],"window":name,"address":start,
                           "bytes":section["size"],"alignment":section["alignment"],
                           "noload":section["type"]==8,"flags":section["flags"]})
        cursors[name]=start+section["size"]
    return sorted(placements,key=lambda item:item["address"])


def linker_script(placements):
    lines=["ENTRY(rbm_u340e_step)","SECTIONS {"]
    for index,p in enumerate(placements):
        noload=" (NOLOAD)" if p["noload"] else ""
        lines.append(f' .p{index:04d} {p["address"]:#x}{noload} : {{ retained.o("{p["section"]}") }}')
    lines.extend([" /DISCARD/ : { *(.note*) *(.comment) }","}"])
    for index,p in enumerate(placements):
        lines.append(f'ASSERT(SIZEOF(.p{index:04d}) == {p["bytes"]}, "Placed section size changed")')
    return "\n".join(lines)+"\n"


def verify_linked(elf, placements, roots):
    allocated=alloc_sections(elf)
    expected={f".p{i:04d}":p for i,p in enumerate(placements)}
    if {s["name"] for s in allocated} != set(expected):
        raise ValueError("Final ELF has missing or orphan allocated sections")
    for s in allocated:
        p=expected[s["name"]]
        if (s["address"],s["size"],s["type"]==8,s["flags"]) != (
                p["address"],p["bytes"],p["noload"],p["flags"]):
            raise ValueError("Final ELF allocation differs from plan")
    if any(s["type"] in (4,9) and s["size"] for s in elf["sections"]):
        raise ValueError("Final ELF contains unresolved relocation records")
    if any(s["section"]==0 for s in elf["symbols"].values()):
        raise ValueError("Final ELF has an undefined global symbol")
    for root in roots:
        symbol=elf["symbols"].get(root)
        if symbol is None or not 0 < symbol["section"] < len(elf["sections"]):
            raise ValueError("Missing required root: "+root)
        section=elf["sections"][symbol["section"]]
        if not section["flags"] & 4 or not section["address"] <= symbol["address"] < section["address"]+section["size"]:
            raise ValueError("Required root is not executable: "+root)


def symbol_bytes(elf,name):
    symbol=elf["symbols"].get(name)
    if symbol is None or not 0 < symbol["section"] < len(elf["sections"]):
        raise ValueError("Missing data symbol: "+name)
    section=elf["sections"][symbol["section"]]
    offset=symbol["address"]-section["address"]
    if offset<0 or offset+symbol["size"]>len(section["data"]):
        raise ValueError("Data symbol extends past its section")
    return section["data"][offset:offset+symbol["size"]]


def raw_reference_patterns(rom,windows):
    result={}
    for window in windows:
        hits={"aligned_u32":[],"ld24_pattern":[]}
        for offset in range(0,len(rom)-3,4):
            word=int.from_bytes(rom[offset:offset+4],"big")
            if window.start <= word < window.end:
                hits["aligned_u32"].append(hex(offset))
            if word >> 28 == 0xE and window.start <= word & 0xFFFFFF < window.end:
                hits["ld24_pattern"].append(hex(offset))
        result[window.name]=hits
    return {"classification":"Raw patterns may be calibration data, not executed instructions. Computed references are not excluded.",
            "windows":result}
