#!/usr/bin/env python3
"""Execute emitted ST10 instructions with a small C_CAN register model.

Audit model E4M1: CAN word-only accesses, reserved bits, MOV flags and
asynchronous IF1 RX/TX are modeled.
This is neither a full ECU emulator nor an electrical CAN/HIL test. The sole
original serial-service call is stubbed. All added instruction bytes execute.
"""
import argparse
import hashlib
import json
import random
import struct
from pathlib import Path
from build_can_diag import (assemble,offset,checks,ORIGIN,STATE,WAIT,MAGIC,TAG,
                         FAST_DIV,SLOW_DIV,FAST_SEQ,SLOW_SEQ,EXTRA_SEQ)

class Machine:
    def __init__(self,image):
        self.torque_enabled=image[0x495A8:0x495AA]==bytes.fromhex('da06');self.native_writes=set();self.image=image;self.mem=bytearray(1<<20);self.reg=[0]*16
        self.mem[:0x8000]=image[:0x8000];self.mem[0x18000:0xE0000]=image[0x8000:]
        self.psw=0x0800;self.stack=[];self.ext=None;self.writes=[];self.calls=[]
        self.objects=[dict(mask1=0,mask2=0,arb1=0,arb2=0,control=0,data=b'\0'*8) for _ in range(32)]
        self.frames=[];self.tick=0;self.busy=False;self.pending=0;self.stuck_timing=False
        self.max_stack=0;self.max_insns=0;self.poke(0xEF00,1);self.return_stack=[]
        self.stub_result=None
        self.transfer_delay=0;self.transfer=None;self.transfer_left=0
        self.ack=True;self.noack_attempts=0;self.read_hook=None;self.reads=[]
    def get(self,a,n=2):
        # UM0404 rev2, 21.1.1/21.1.2 (p410): CAN1/2 support word accesses
        # only. Reject unsupported accesses rather than invent silicon behavior
        # (a bus trap/reset is NOT simulated by this assertion).
        self.check_can_access(a,n)
        if self.read_hook:self.read_hook(self,a,n)
        # Read trace omitted during fuzzing to keep memory bounded.
        if a==0xEF10:return 0x8000 if self.busy or self.transfer is not None else 0
        if a==0xEF80:return self.pending
        if a==0xEF90:return sum(1<<i for i,o in enumerate(self.objects[:16]) if o['control']&0x8000)
        if a==0xEF06 and self.stuck_timing:return 0
        v=int.from_bytes(self.mem[a:a+n],'little')
        if a in (0xEF1C,0xEF4C):return v&0xFF8F
        return v|0x2000 if a in (0xEF16,0xEF46) else v
    def poke(self,a,v,n=2):self.mem[a:a+n]=(v&((1<<(n*8))-1)).to_bytes(n,'little')
    def check_can_access(self,a,n):
        if 0xEE00<=a<0xF000:
            assert n==2 and a%2==0,('Unsupported CAN access',hex(a),n,
                                     hex(getattr(self,'instruction_pc',0)))
    def put(self,a,v,n=2):
        self.check_can_access(a,n)
        assert n==2 and (0xEF00<=a<=0xEF54 or self.torque_enabled and (0xE7C0<=a<0xE800 or a in self.native_writes)),('Unexpected store',hex(a),n)
        assert a!=0xEF40,'IF2 command request must never be written'
        if a in (0xEF1C,0xEF4C):assert v&0x70==0,'Reserved MCTRL bits must stay zero'
        self.writes.append((a,v));self.poke(a,v,n)
        if a==0xEF10:
            assert not self.busy and self.transfer is None,'IF1 command while busy'
            assert 1<=v<=32,v
            self.transfer=(v,self.get(0xEF12));self.transfer_left=self.transfer_delay
            if not self.transfer_delay:self.complete_transfer()
    def complete_transfer(self):
        v,mask=self.transfer;self.transfer=None;obj=self.objects[v-1]
        if mask&0x80:
            if mask&0x40:obj['mask1']=self.get(0xEF14);obj['mask2']=self.get(0xEF16)&0xDFFF
            if mask&0x20:obj['arb1']=self.get(0xEF18);obj['arb2']=self.get(0xEF1A)
            if mask&0x10:obj['control']=self.get(0xEF1C)
            if mask&3:
                assert mask&3==3
                obj['data']=bytes(self.mem[0xEF1E:0xEF26])
            if mask&4:
                assert obj['arb2']&0xE000==0xA000,'Standard valid TX object'
                assert obj['control']&0xF==8
                assert obj['control']&0xC00==0,'No CAN message interrupts'
                assert self.get(0xEF00)==0x20,'CAN enabled, DAR and no IRQs'
                if self.ack:self.frames.append({'tick':self.tick,'id':(obj['arb2']>>2)&0x7FF,'data':obj['data'].hex()})
                else:self.noack_attempts+=1
                obj['control']&=~0x8100
        else:
            if mask&0x40:self.poke(0xEF14,obj['mask1']);self.poke(0xEF16,obj['mask2'])
            if mask&0x20:self.poke(0xEF18,obj['arb1']);self.poke(0xEF1A,obj['arb2'])
            if mask&0x10:self.poke(0xEF1C,obj['control'])
            if mask&3:
                assert mask&3==3;self.mem[0xEF1E:0xEF26]=obj['data']
            if mask&4:obj['control']&=~0x8000
            if mask&8:obj['control']&=~0x2000
    def inject(self,can_id,data,extended=False,remote=False,dlc=None):
        if self.get(0xEF00)&1:return False
        if dlc is None:dlc=len(data)
        assert 0<=dlc<=8
        arb=(0x4000 if extended else 0)|(0x2000 if remote else 0)|((can_id&0x7FF)<<2)
        for obj in self.objects:
            if not obj['arb2']&0x8000 or obj['arb2']&0x2000:continue
            mask=obj['mask2']
            if obj['control']&0x1000:
                if mask&0x8000 and bool(arb&0x4000)!=bool(obj['arb2']&0x4000):continue
                if mask&0x4000 and bool(arb&0x2000)!=bool(obj['arb2']&0x2000):continue
                if (arb^obj['arb2'])&(mask&0x1FFF):continue
            elif (arb^obj['arb2'])&0x5FFC:continue
            lost=bool(obj['control']&0x8000)
            obj['control']=(obj['control']&~15)|dlc|0x8000|(0x4000 if lost else 0)
            obj['data']=bytes(data[:dlc]).ljust(8,b'\xA5');obj['arb2']=0x8000|arb
            return True
        return False
    def move_flags(self,v,zero_extend=False):
        # PM0036 MOV/MOVBZ/PUSH/POP: retain C,V; update E,Z,N.
        self.psw=(self.psw&~0x19)|(8 if v==0 else 0)|(0 if zero_extend else ((1 if v&0x8000 else 0)|(16 if v==0x8000 else 0)))
    def sget(self,s):
        if s>=0xF0:return self.reg[s-0xF0]
        if s==0x88:return self.psw
        if s==0x8E:return 0
        raise AssertionError(('SFR read',s))
    def sset(self,s,v):
        if s>=0xF0:self.reg[s-0xF0]=v&65535
        elif s==0x88:self.psw=v&65535
        else:raise AssertionError(('SFR write',s))
    def flags(self,v,c=False):
        # Only N,C,Z are used by this instruction subset's branch predicates.
        self.psw=(self.psw&~0xF)|(8 if v&65535==0 else 0)|(1 if v&0x8000 else 0)|(int(c)<<1)
    def direct(self,a,ext):
        return ext*0x4000+(a&0x3FFF) if ext is not None else [0x2E,0x2F,0x3C,3][a>>14]*0x4000+(a&0x3FFF)
    def run(self,entry=ORIGIN,stop=None):
        if self.transfer is not None:
            self.transfer_left-=1
            if self.transfer_left<=0:self.complete_transfer()
        self.tick+=1;pc=entry;count=0;depth=len(self.stack);atomic_until=0
        while True:
            if pc==stop:self.max_insns=max(self.max_insns,count);return count
            count+=1;assert count<=6000,('Unbounded payload',hex(pc))
            hook=getattr(self,'instruction_hook',None)
            if hook is not None and count>atomic_until:hook(self,pc)
            self.instruction_pc=pc
            p=offset(pc);op,s=self.image[p:p+2];w=int.from_bytes(self.image[p+2:p+4],'little')
            pc+=2;ext=self.ext;self.ext=None
            if op==0xDA:
                target=s*65536+w;pc+=2;self.calls.append(target)
                if target!=0x1A060:
                    assert self.torque_enabled and 0x64800<=target<0x68000,hex(target)
                    self.return_stack.append((pc,4));pc=target
                    self.max_stack=max(self.max_stack,2*len(self.stack)+sum(n for _,n in self.return_stack))
                    continue
                self.reg=[(x*73+self.tick*17+i)&65535 for i,x in enumerate(self.reg)]
                self.psw=(self.psw*31+self.tick)&65535
                self.stub_result=(self.reg[:],self.psw)
            elif op==0xCA:
                assert s==0
                self.return_stack.append((pc+2,2));pc=(pc&0xff0000)|w
                self.max_stack=max(self.max_stack,2*len(self.stack)+sum(n for _,n in self.return_stack))
            elif op==0xCB:
                assert self.return_stack
                pc,n=self.return_stack.pop();assert n==2
            elif op==0xEC:
                v=self.sget(s);self.stack.append(v);self.max_stack=max(self.max_stack,2*len(self.stack)+sum(n for _,n in self.return_stack));self.move_flags(v)
            elif op==0xFC:
                v=self.stack.pop();self.move_flags(v);self.sset(s,v)
            elif op==0xDB:
                if self.return_stack:
                    pc,n=self.return_stack.pop();assert n==4;continue
                assert not self.return_stack
                assert len(self.stack)==depth
                if entry==ORIGIN:assert self.stub_result==(self.reg,self.psw),'Register/PSW preservation'
                self.max_insns=max(self.max_insns,count);return count
            elif op==0xD7:
                assert s==0x40;self.ext=w;pc+=2
            elif op==0xE6:self.move_flags(w);self.sset(s,w);pc+=2
            elif op==0xF2:
                v=self.get(self.direct(w,ext));self.move_flags(v);self.sset(s,v);pc+=2
            elif op==0xC2:
                v=self.get(self.direct(w,ext),1);self.reg[s-0xF0]=v;self.move_flags(v,True);pc+=2
            elif op in (0xD4,0xF4):
                d,r=s>>4,s&15;v=self.get(self.direct((self.reg[r]+w)&65535,ext),1 if op==0xF4 else 2);pc+=2
                if op==0xD4:self.reg[d]=v
                else:
                    wordreg=d//2;shift=8*(d%2);self.reg[wordreg]=(self.reg[wordreg]&~(255<<shift))|(v<<shift)
                self.move_flags(v)
            elif op==0xC0:
                d,r=s&15,s>>4;v=(self.reg[r//2]>>(8*(r%2)))&255
                self.reg[d]=v;self.move_flags(v,True)
            elif op==0xF6:
                v=self.sget(s);self.put(self.direct(w,ext),v);self.move_flags(v);pc+=2
            elif op==0xF0:
                v=self.reg[s&15];self.reg[s>>4]=v;self.move_flags(v)
            elif op in (0x5C,0x7C):
                r=s&15;n=s>>4;v=self.reg[r]
                c=bool(v&(1<<(16-n))) if op==0x5C else bool(v&(1<<(n-1)))
                self.reg[r]=(v<<n)&65535 if op==0x5C else v>>n
                self.flags(self.reg[r],c)
            elif op in (0x00,0x20,0x40,0x50,0x70):
                d,r=s>>4,s&15;v,k=self.reg[d],self.reg[r]
                if op==0x00:z=v+k;self.reg[d]=z&65535;self.flags(z,z>65535)
                elif op in (0x20,0x40):
                    z=(v-k)&65535;self.flags(z,v<k)
                    if op==0x20:self.reg[d]=z
                elif op==0x50:self.reg[d]=v^k;self.flags(v^k)
                else:self.reg[d]=v|k;self.flags(v|k)
            elif op in (0x06,0x26,0x46,0x56,0x66,0x76):
                r=s-0xF0;v=self.reg[r];pc+=2
                if op==0x06:z=v+w;self.reg[r]=z&65535;self.flags(z,z>65535)
                elif op in (0x26,0x46):
                    z=(v-w)&65535;self.flags(z,v<w)
                    if op==0x26:self.reg[r]=z
                elif op==0x56:self.reg[r]=v^w;self.flags(v^w)
                elif op==0x66:self.reg[r]=v&w;self.flags(v&w)
                else:self.reg[r]=v|w;self.flags(v|w)
            elif op==0x42:
                v=self.sget(s);k=self.get(self.direct(w,ext));self.flags((v-k)&65535,v<k);pc+=2
            elif op==0xD1:
                assert s in (0x20,0x30)
                atomic_until=count+(s>>4)+1
            elif op==0xCC:assert s==0
            elif op&15==13:
                cc=op>>4;z=bool(self.psw&8);c=bool(self.psw&2)
                if {0:True,2:z,3:not z,8:c,9:not c,14:not(c or z),15:c or z}[cc]:pc+=(s if s<128 else s-256)*2
            elif op==0xEA:
                pc+=2;cc=s>>4;z=bool(self.psw&8);c=bool(self.psw&2)
                yes={0:True,2:z,3:not z,8:c,9:not c,14:not(c or z),15:c or z}[cc]
                if yes:pc=(pc&0xFF0000)|w
            else:raise AssertionError(('Unknown opcode',hex(pc-2),hex(op),hex(s)))


def seed(m,rpm4=3200,tps12=1024,load_n=1000,load_d=2000,running=1,ect=160,iat=100,mapq=25600,spark=16):
    for a,v,n in [(0xF7C4,rpm4,2),(0xF0616,tps12,2),(0xF8D6,load_n,2),
                  (0xF4686,load_d,2),(0xF7C2,running,1),(0xF41D1,ect,1),
                  (0xF41C9,iat,1),(0xF1238,mapq,2),(0xF0527,spark,1)]:m.poke(a,v,n)
