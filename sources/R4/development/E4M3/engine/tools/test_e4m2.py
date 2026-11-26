#!/usr/bin/env python3
"""Regression against actual native startup bytes; not a full ECU/relay emulator.

The small address-flow executor intentionally has no peripheral/IRQ scheduler.
Unknown instructions fail. CP aliases the register bank, and EXTP ranges count
instructions (IRANG + 1), including NOPs. Run both native startup configurations.
"""
import hashlib
import json
from pathlib import Path
from audit_machine import Machine, seed
from build_can_diag import offset, checks
from build_e4 import ROOT, NAME, build
import torque_patch as tq


class NativeAddressProbe:
    def __init__(self, image, cp=0xFC00):
        self.image=image;self.mem=bytearray(1<<20);self.cp=cp
        self.mem[:0x8000]=image[:0x8000];self.mem[0x18000:0xE0000]=image[0x8000:]
        self.write(0xFE10,cp);self.ext=None;self.left=0;self.trace=[]
        self.dpp=[0x2E,0x2F,0x3C,3]
    def read(self,a):return int.from_bytes(self.mem[a:a+2],'little')
    def write(self,a,v):self.mem[a:a+2]=(v&65535).to_bytes(2,'little')
    def r(self,n):return self.read(self.cp+2*n)
    def set(self,n,v):self.write(self.cp+2*n,v)
    def addr(self,a):return (self.ext if self.left else self.dpp[a>>14])*0x4000+(a&0x3FFF)
    def run(self,pc,stop):
        count=0
        while pc!=stop:
            count+=1;assert count<100,hex(pc)
            at=pc;p=offset(pc);op,s=self.image[p:p+2]
            w=int.from_bytes(self.image[p+2:p+4],'little');pc+=2
            if op==0xDC:
                assert s&0xC0==0x40
                self.ext=self.r(s&15);self.left=((s>>4)&3)+1
                self.trace.append((at,'EXTP',self.ext,self.left));continue
            if op==0x88:
                src,dst=s>>4,s&15;v=self.r(src);self.set(dst,self.r(dst)-2)
                a=self.addr(self.r(dst));self.write(a,v);self.trace.append((at,'stack_write',a,v))
            elif op==0xF0:self.set(s>>4,self.r(s&15))
            elif op==0xE6:
                assert s>=0xF0;self.set(s-0xF0,w);pc+=2
            elif op==0x08:self.set(s>>4,self.r(s>>4)+(s&15))
            elif op in (0x06,0x26):
                assert s>=0xF0;self.set(s-0xF0,self.r(s-0xF0)+(w if op==6 else -w));pc+=2
            elif op==0x98:
                dst,src=s>>4,s&15;a=self.addr(self.r(src));v=self.read(a)
                self.set(src,self.r(src)+2);self.set(dst,v);self.trace.append((at,'read',a,v))
            elif op==0xA8:
                a=self.addr(self.r(s&15));v=self.read(a);self.set(s>>4,v);self.trace.append((at,'read',a,v))
            elif op==0xD4:
                a=self.addr((self.r(s&15)+w)&65535);v=self.read(a)
                self.set(s>>4,v);pc+=2;self.trace.append((at,'read',a,v))
            elif op==0xF2:
                assert s>=0xF0;a=self.addr(w);v=self.read(a);self.set(s-0xF0,v);pc+=2
                self.trace.append((at,'read',a,v))
            elif op==0xB8:
                a=self.addr(self.r(s&15));v=self.r(s>>4);self.write(a,v)
                self.trace.append((at,'write',a,v))
            elif op==0xCC:assert s==0
            elif op==0xD1:assert s==0x20  # Atomicity is irrelevant without an IRQ scheduler.
            elif op==0x1A:
                assert s==0x88 and w==0xF8F0;pc+=2  # PSW only, no address-flow effect.
            else:raise AssertionError(('unsupported native opcode',hex(at),hex(op),hex(s)))
            if self.left:
                self.left-=1
                if not self.left:self.ext=None
            self.trace.append((at,'R0',self.r(0)))


def main():
    image=(ROOT/'firmware'/NAME).read_bytes()
    m1=(ROOT/'build_inputs/E4M1_RELAY_FAULT_REPRO_ONLY_DO_NOT_FLASH.bin').read_bytes()
    e2=(ROOT.parent/'rollback/GW4G15_REV8_CAN_DIAG_BENCH_E1.bin').read_bytes()
    assert hashlib.sha256(m1).hexdigest()=='4538fc6ac1b60603bcef6ab260083c0ae56a70d856b194ec6174e35601f91724'
    report=json.loads((ROOT/'firmware/PATCH_E4_REPORT.json').read_text())
    rebuilt,*_=build((ROOT/'build_inputs/GW4G15_REV8_BASELINE_NO_LIN.bin').read_bytes(),
                    (ROOT/'build_inputs/CHERY_REFERENCE_DO_NOT_FLASH.bin').read_bytes())
    assert image==rebuilt and all(x['valid'] for x in checks(image))
    # Deliberately tight: two-byte table field, one build-ID byte, two clock
    # load operands, plus checksum words. No native hook or relay output edits.
    allowed=set(range(0xB43C,0xB43E));timer_operands=[]
    for p in range(offset(0x64800),offset(0x64800)+3934,2):
        if m1[p:p+4] in (bytes.fromhex('f2fb0ee1'),bytes.fromhex('f2fd0ee1')):
            allowed.update(range(p+2,p+4));timer_operands.append(p+2)
    assert len(timer_operands)==2
    build_id=[]
    for p in range(offset(0x1E200),offset(0x1E200)+7652,2):
        if m1[p:p+4]==bytes.fromhex('e6f40109'):
            assert image[p:p+4]==bytes.fromhex('e6f4010a');allowed.add(p+3);build_id.append(p+3)
    assert len(build_id)==1
    for r in checks(image):allowed.update(range(r['file_offset']+8,r['file_offset']+16))
    diff={i for i,(a,b) in enumerate(zip(m1,image)) if a!=b};assert diff<=allowed

    runs=[]
    for name,b,wanted in [('working_E2',e2,0xE7FE),('failed_E4M1',m1,0xE7FE),('E4M2',image,0xE7BE)]:
        for caller,call_pc in [(0x1BC4A,0x1BC52),(0x1BAA4,0x1BAAC)]:
            for cp in (0xF800,0xFC00):
                q=NativeAddressProbe(b,cp)
                q.set(0,int.from_bytes(b[0x2B4:0x2B6],'little'))
                q.run(caller,call_pc)
                assert b[offset(call_pc):offset(call_pc)+4]==bytes.fromhex('da013480')
                config=q.r(13)*0x4000+(q.r(12)&0x3FFF)
                q.run(0x18034,0x18062)
                assert q.r(0)==wanted
                assert (0x18056,'read',0x1B43C,wanted) in q.trace
                assert (0x18060,'write',cp,wanted) in q.trace
                # Execute real validation prologue to locate native software
                # stack writes. This establishes ownership, not concurrency.
                q.run(0x18220,0x1822C)
                writes=[x[2] for x in q.trace if x[1]=='stack_write' and 0x18220<=x[0]<0x1822C]
                overlap=[a for a in writes if 0xE7C0<=a<0xE800]
                assert bool(overlap)==(name!='E4M2')
                # Construct a live-frame fixture at those native addresses.
                # Execute actual E4 first tick and check whether it clobbers it.
                # This is a focused regression, NOT an actual ECU boot trace.
                clobbered=[]
                if name!='working_E2':
                    m=Machine(b);seed(m,rpm4=0)
                    for a in writes:m.poke(a,0xA55A)
                    m.poke(tq.MAGIC,0)
                    m.run(report['labels']['torque_tick'])
                    clobbered=[a for a in writes if m.get(a)!=0xA55A]
                    assert bool(clobbered)==(name=='failed_E4M1')
                runs.append(dict(image=name,caller=hex(caller),configuration=hex(config),cp=hex(cp),
                    R0_after_native_init=hex(wanted),native_prologue_writes=[hex(a) for a in writes],
                    overlap_bytes=2*len(overlap),constructed_frame_clobbered=[hex(a) for a in clobbered]))

    # Independently anchor the RUNNING timer source to vector and native ISR.
    assert image[0x90:0x94]==bytes.fromhex('fa01608c')
    assert image[offset(0x18C6C):offset(0x18C6C)+4]==bytes.fromhex('248f76e1')
    assert image[offset(0x18C2C):offset(0x18C2C)+4]==bytes.fromhex('f2f476e1')
    timer_cases=[]
    for name,b in [('failed_E4M1',m1),('E4M2',image)]:
        m=Machine(b);m.poke(0xFF44,0x46);m.poke(0xE10E,5)
        for high,low in [(0,0xFFFF),(1,0),(1,1),(23,30000),(0xFFFF,0xFFFF)]:
            m.poke(0xE176,high);m.poke(0xFE44,low);m.poke(0xFF64,0)
            m.return_stack.append((0x647FE,2));m.run(report['labels']['clock'],stop=0x647FE)
            assert m.reg[12]==1 and m.reg[10]==low
            assert m.reg[11]==(5 if name=='failed_E4M1' else high)
            timer_cases.append(dict(image=name,native_high=high,returned_high=m.reg[11],low=low))

    result=dict(status='PASS',version='E4M2',sha256=hashlib.sha256(image).hexdigest(),
        changed_bytes_vs_E4M1=len(diff),changed_file_offsets=[hex(p) for p in sorted(diff)],
        reproducible_build=True,valid_checksum_records=51,native_startup_cases=runs,
        application_timer_cases=timer_cases,hardware_tested=False,relay_chatter_resolved=None,
        limits=['Address-flow probe executes only specified native startup/prologue instructions; no full ECU boot, interrupt scheduling or relay simulation',
                'Live-frame clobber test is a constructed overlap fixture, not a measured on-ECU execution trace',
                'Full native stack depth and physical relay result still require bench verification'])
    out=ROOT.parent/'evidence/E4M2';out.mkdir(exist_ok=True)
    (out/'NATIVE_STARTUP_REGRESSION.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('native_startup_cases','application_timer_cases')},indent=2))
    print('12 native configuration/CP cases; 10 application timer source cases: PASS')


if __name__=='__main__':main()
