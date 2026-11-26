#!/usr/bin/env python3
"""Independent decoder, footprint, checksum and native-anchor audit for E4."""
import hashlib,json,struct,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(Path(__file__).parent/'vendor'))
from c166_disasm import C166Disassembler
B=(ROOT/'firmware/GW4G15_REV8_CAN_TORQUE_E4_BENCH.bin').read_bytes()
BASE=(ROOT/'build_inputs/GW4G15_REV8_BASELINE_NO_LIN.bin').read_bytes()
report=json.loads((ROOT/'firmware/PATCH_E4_REPORT.json').read_text())
def offset(a):return a if a<0x8000 else a-0x10000
assert len(B)==len(BASE)==0xD0000
regions=[(0x1E200,report['diagnostic_code_bytes']),(0x64800,report['torque_code_bytes'])]
allowed={0x8405C,0x8405D,0x8405E,0x8405F};checksum_records=[]
for origin,n in regions:
    assert BASE[offset(origin):offset(origin)+n]==b'\xff'*n
    allowed.update(range(offset(origin),offset(origin)+n))
for addr,n in [(0x595A8,4),(0x5B0BE,6),(0x5B5D6,4)]:allowed.update(range(offset(addr),offset(addr)+n))
for p in (0x2B2,0x386,0x3B0,0x3E8,0x23E2,0x2436,0x24A8,0x2518,0x85BD6,0x85BEE,0x85BF8):
    allowed.update(range(p,p+4));assert B[p:p+2]==BASE[p:p+2]
    assert int.from_bytes(B[p+2:p+4],'little')==int.from_bytes(BASE[p+2:p+4],'little')-64
for p in (0x2FC,0x302,0x30E,0x314,0x336,0xBC38,0xBC3E):
    allowed.update(range(p,p+2));assert int.from_bytes(B[p:p+2],'little')==int.from_bytes(BASE[p:p+2],'little')|1
assert BASE[0xB43C:0xB43E]==bytes.fromhex('fee7') and B[0xB43C:0xB43E]==bytes.fromhex('bee7')
allowed.update(range(0xB43C,0xB43E))
for p in list(range(0xA7800,0xA7B00,16))+[0xA83CC,0xA83DC,0xA83EC]:
    assert B[p:p+8]==BASE[p:p+8];lo,hi,check,inv=struct.unpack_from('<4I',B,p)
    total=0
    for at in range(offset(lo),offset(hi)+1,2):total=(total+B[at]+256*B[at+1])&0xFFFFFFFF
    assert check==total and inv==total^0xFFFFFFFF
    allowed.update(range(p+8,p+16));checksum_records.append(dict(start_cpu=lo,end_cpu=hi,valid=True))
changed={i for i,(a,b) in enumerate(zip(BASE,B)) if a!=b};assert changed<=allowed
assert B[0x8405C:0x84060]==bytes.fromhex('da0100e2') and B[0xE200:0xE204]==bytes.fromhex('da0160a0')
decoder=C166Disassembler();rows=[];starts=set();stores=set();lines=[];branches=0
for origin,n in regions:
    decoded=decoder.decode_range(B[offset(origin):offset(origin)+n],origin,n)
    assert decoded[-1][0]+len(bytes.fromhex(decoded[-1][1]))==origin+n
    rows.extend(decoded);starts.update(a for a,_,_ in decoded)
for i,(pc,h,text) in enumerate(rows):
    raw=bytes.fromhex(h);op=raw[0]
    assert '(unknown' not in text and '(decode error' not in text,(hex(pc),text)
    # The entire torque payload reads CAN as aligned words. Byte memory
    # opcodes are forbidden here, including indexed MOVB hidden by EXTP.
    if 0x64800<=pc<0x64800+regions[1][1]:
        assert op not in (0xC2,0xC5,0xF3,0xF4,0xE4,0xF7),('Torque byte memory access',hex(pc),text)
    if op==0xD7:
        assert raw[:2]==bytes.fromhex('d740');text=f'EXTP #{int.from_bytes(raw[2:],"little"):04X}h,#1'
    if op==0xD1:
        assert raw in (bytes.fromhex('d120'),bytes.fromhex('d130'))
        text=f'ATOMIC #{(raw[1]>>4)+1} (IRANG={raw[1]>>4})'
    if op in (0xEA,0xCA):
        target=(pc&0xFF0000)|int.from_bytes(raw[2:],'little');assert target in starts;branches+=1
    if op==0xDA:
        target=raw[1]*65536+int.from_bytes(raw[2:],'little');assert target==0x1A060 or target in starts
    if op==0xF6:
        addr=int.from_bytes(raw[2:],'little');prev=bytes.fromhex(rows[i-1][1])
        if prev[:2]==bytes.fromhex('d740'):addr=int.from_bytes(prev[2:],'little')*0x4000+(addr&0x3FFF)
        assert (0xEF00<=addr<=0xEF54 and addr!=0xEF40) or 0xE7C0<=addr<0xE800,(hex(pc),hex(addr))
        stores.add(addr)
    lines.append(f'{pc:06X} file:{offset(pc):06X} {h:10} {text}')
# Direct incoming branch checks for displaced instruction interiors. Near
# relative branches have bounded reach; decode from known native entry points.
for start,end,interiors in [(0x59574,0x596DE,{0x595AA}),
                           (0x5AFD2,0x5B286,{0x5B0C0,0x5B0C2}),
                           (0x5B59E,0x5B6B8,{0x5B5D8})]:
    native=decoder.decode_range(BASE[offset(start):offset(end)],start,end-start)
    for pc,h,_ in native:
        raw=bytes.fromhex(h);op=raw[0]
        if op in (0xEA,0xCA):target=(pc&0xFF0000)|int.from_bytes(raw[2:],'little')
        elif op&15==13:target=pc+2+2*(raw[1] if raw[1]<128 else raw[1]-256)
        else:continue
        assert target not in interiors,(hex(pc),hex(target))
# Exclude direct far calls/jumps into the newly occupied gap in the base image.
direct_refs=[]
for p in range(0,len(BASE)-3,2):
    if BASE[p] in (0xDA,0xFA):
        target=BASE[p+1]*65536+int.from_bytes(BASE[p+2:p+4],'little')
        if 0x64800<=target<0x64800+regions[1][1]:direct_refs.append((p,target))
assert not direct_refs,direct_refs
anchors={
 'air_request_output_965E':(0x596D4,'f6f95e96'),
 'fast_request_output_970C_a':(0x5B0D2,'f6f80c97'),
 'fast_request_output_970C_b':(0x5B0D8,'f6f70c97'),
 'ignition_request_comparison':(0x61DBE,'42f40c97'),
 'ignition_intermediate_8504':(0x61EE6,'d2fc0485'),
 'ignition_candidate_850C':(0x61F2E,'f7f80c85'),
 'cylinder_candidate_array':(0x62422,'e4852a85'),
 'cylinder_angle_load':(0x62312,'f4a42a85'),
 'native_angle_FBC6':(0x62332,'f7fec6fb'),
 'reported_angle_8527':(0x62380,'f7f82785'),
 'load_request_971E':(0x5B61C,'f6f41e97'),
 'load_request_971C':(0x5B68A,'f6f41c97'),
 'load_conversion_input':(0x4BC4A,'f2fc1c97'),
 'load_conversion_output':(0x4BC58,'f6f4ee92'),
 'load_table_output':(0x4BC6A,'f6f4f092'),
 'native_application_T4_vector':(0x90,'fa01608c'),
 'native_application_T4_overflow_counter':(0x18C6C,'248f76e1'),
 'native_application_T4_read':(0x18C2C,'f2f476e1'),
 'native_OS_R0_reload':(0x18050,'06fa1600dc5bd44a1000cc00f2f510feb845'),
}
for name,(pc,expected) in anchors.items():
    raw=bytes.fromhex(expected);assert BASE[offset(pc):offset(pc)+len(raw)]==B[offset(pc):offset(pc)+len(raw)]==raw,(name,hex(pc))
out=dict(status='PASS_STATIC_LIMITED',sha256=hashlib.sha256(B).hexdigest(),decoded_instructions=len(rows),
    branch_targets_checked=branches,changed_bytes=len(changed),known_checksums=len(checksum_records),
    new_code_store_addresses=[hex(a) for a in sorted(stores)],native_anchors={k:hex(v[0]) for k,v in anchors.items()},
    private_RAM_reserved_from_R0_stack=True,software_stack_reserved_bytes=64,
    native_engine_RAM_directly_written_by_patch=False,calibration_bytes_unchanged=True,
    no_direct_base_references_to_new_gap=True,torque_byte_memory_accesses=0,hardware_tested=False,
    limits=['Static data-flow anchors do not prove achieved torque or every conditional native actuator path',
            'Computed references and full native interrupt stack depth are not proven by this audit'])
(ROOT.parent/'evidence/INDEPENDENT_STATIC_AUDIT_E4.json').write_text(json.dumps(out,indent=2)+'\n')
(ROOT.parent/'evidence/independent_disassembly_E4.asm').write_text('\n'.join(lines)+'\n')
print(json.dumps({k:v for k,v in out.items() if k not in ('new_code_store_addresses','native_anchors')},indent=2))
