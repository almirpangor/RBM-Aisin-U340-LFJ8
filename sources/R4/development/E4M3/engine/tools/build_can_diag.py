#!/usr/bin/env python3
"""Exact-image ST10 CAN1 bench E1: complete enabled native Mode 01 PID set.

The C_CAN register sequence is adapted from Chery's driver, not a binary copy
of its RAM-dependent protocol/task layer. RB telemetry IDs are deliberately
distinct from Chery's production drivetrain protocol. No engine control writes.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path

BASE_SHA = '2e1621c4329661f3b6991cf540aea188497fff2a88e32e4eaa6a172b6d7360a0'
DONOR_SHA = '99dc271a861ab6d9e6749e8beb4637ab5c6c7e111f3ff0d9df4e147b2a0a6e1c'
ORIGIN, LIMIT = 0x1E200, 0x1FFFE
CHECKS = list(range(0xA7800,0xA7B00,16))+[0xA83CC,0xA83DC,0xA83EC]
# IF2 is never commanded. Only its documented R/W staging registers store
# private state; neither engine RAM nor diagnostic buffers are allocated.
STATE, WAIT, FAST_SEQ, MAGIC = 0xEF4E,0xEF50,0xEF52,0xEF54
FAST_DIV, SLOW_DIV, SLOW_SEQ, EXTRA_SEQ = 0xEF44,0xEF46,0xEF48,0xEF4A
TAG = 0x5246
DIAG_PHASE, DIAG_WAIT = 0xEF4C, 0xEF42
NATIVE_PIDS = json.loads((Path(__file__).parent/'native_pids.json').read_text())
PID_LIST = tuple(int(x['pid'],16) for x in NATIVE_PIDS)
PID_MASK = sum(1 << (32-pid) for pid in PID_LIST if pid<=32) | 1
PID_MASK20 = sum(1 << (64-pid) for pid in PID_LIST if 32<pid<=64)

def offset(a):
    if 0 <= a < 0x8000: return a
    if 0x18000 <= a < 0xE0000: return a-0x10000
    raise ValueError(f'Unmapped CPU address {a:06X}')

def word(v): return struct.pack('<H',v & 65535)
def far(op,a): return bytes([op,a>>16])+word(a)

class BasicAsm:
    def __init__(self,origin=ORIGIN,limit=LIMIT): self.origin=origin;self.limit=limit;self.data=bytearray(); self.labels={}; self.rows=[]; self.fix=[]
    @property
    def pc(self): return self.origin+len(self.data)
    def label(self,n):
        assert n not in self.labels
        self.labels[n]=self.pc
    def emit(self,b,s): self.rows.append((self.pc,len(b),s)); self.data.extend(b)
    def raw(self,b,s): self.emit(bytes.fromhex(b),s)
    def imm(self,r,v): self.emit(bytes([0xE6,0xF0+r])+word(v),f'MOV R{r},#{v:04X}h')
    def ld(self,r,a): self.emit(bytes([0xF2,0xF0+r])+word(a),f'MOV R{r},{a:04X}h')
    def byte(self,r,a): self.emit(bytes([0xC2,0xF0+r])+word(a),f'MOVBZ R{r},{a:04X}h')
    def st(self,a,r): self.emit(bytes([0xF6,0xF0+r])+word(a),f'MOV {a:04X}h,R{r}')
    def set(self,a,v): self.imm(4,v);self.st(a,4)
    def zero(self,a): self.emit(bytes([0xF6,0x8E])+word(a),f'MOV {a:04X}h,ZEROS')
    def rr(self,d,s): self.emit(bytes([0xF0,d*16+s]),f'MOV R{d},R{s}')
    def ri(self,op,r,v,n): self.emit(bytes([op,0xF0+r])+word(v),f'{n} R{r},#{v:04X}h')
    def cmp(self,r,v): self.ri(0x46,r,v,'CMP')
    def addi(self,r,v): self.ri(0x06,r,v,'ADD')
    def subi(self,r,v): self.ri(0x26,r,v,'SUB')
    def andi(self,r,v): self.ri(0x66,r,v,'AND')
    def ori(self,r,v): self.ri(0x76,r,v,'OR')
    def op(self,op,d,s,n):self.emit(bytes([op,d*16+s]),f'{n} R{d},R{s}')
    def add(self,d,s):self.op(0x00,d,s,'ADD')
    def sub(self,d,s):self.op(0x20,d,s,'SUB')
    def cmpreg(self,d,s):self.op(0x40,d,s,'CMP')
    def either(self,d,s):self.op(0x70,d,s,'OR')
    def shift(self,r,n,left=False):self.emit(bytes([0x5C if left else 0x7C,n*16+r]),f'{"SHL" if left else "SHR"} R{r},#{n}')
    def branch(self,cc,n):
        self.fix.append((len(self.data)+2,n))
        self.emit(bytes([0xEA,cc*16,0,0]),f'JMPA CC_{cc:X},{n}')
    def extp(self,p):self.emit(bytes.fromhex('d740')+word(p),f'EXTP #{p:04X}h,#1')
    def indexed(self,r,base,disp,page,byte=False):
        self.extp(page)
        if byte:
            assert r <= 7
            self.emit(bytes([0xF4,32*r+base])+word(disp),f'MOVB RL{r},[R{base}+#{disp:04X}h]')
            self.emit(bytes([0xC0,32*r+r]),f'MOVBZ R{r},RL{r}')
        else:self.emit(bytes([0xD4,16*r+base])+word(disp),f'MOV R{r},[R{base}+#{disp:04X}h]')
    def swap(self,r,tmp=6):
        self.rr(tmp,r);self.shift(r,8);self.shift(tmp,8,True);self.either(r,tmp)
    def physical(self,r,a,byte=False):
        self.extp(a//0x4000)
        (self.byte if byte else self.ld)(r,a%0x4000)
    def percent(self):
        # Input R4 in 0..255. Exact floor(R4*100/255), no multiply/divide unit.
        self.rr(5,4);self.rr(6,4)
        self.shift(4,6,True);self.shift(5,5,True);self.shift(6,2,True)
        self.add(4,5);self.add(4,6)
        self.rr(5,4);self.shift(5,8);self.addi(4,1);self.add(4,5);self.shift(4,8)
    def temp(self,physical,label):
        self.physical(4,physical,True);self.rr(5,4);self.shift(4,1,True);self.add(4,5);self.shift(4,2)
        self.cmp(4,8);self.branch(9,label+'_nonnegative')
        self.imm(4,8);self.label(label+'_nonnegative');self.subi(4,8)
    def finish(self):
        for p,n in self.fix:self.data[p:p+2]=word(self.labels[n])
        assert self.pc <= self.limit
        return bytes(self.data)

class Asm(BasicAsm):
    # Private state is packed into high fields of IF2 staging registers.
    LOW_FIELDS={0xEF44:0xFF,0xEF46:0xFF,0xEF48:0xFF,0xEF4A:0xFF,
                0xEF4C:0x0F,0xEF4E:0xFF,0xEF50:0xFF,0xEF52:0xFF}
    def full_ld(self,r,addr): BasicAsm.ld(self,r,addr)
    def full_st(self,addr,r): BasicAsm.st(self,addr,r)
    def ld(self,r,addr):
        BasicAsm.ld(self,r,addr)
        if addr in self.LOW_FIELDS:self.andi(r,self.LOW_FIELDS[addr])
    def st(self,addr,r):
        if addr not in self.LOW_FIELDS:return BasicAsm.st(self,addr,r)
        assert r!=12
        mask=self.LOW_FIELDS[addr]
        self.full_ld(12,addr);self.andi(12,({0xEF46:0xDFFF,0xEF4C:0xFF8F}.get(addr,0xFFFF))^mask)
        self.andi(r,mask);self.either(12,r);self.full_st(addr,12)
    def zero(self,addr):
        if addr in self.LOW_FIELDS:self.set(addr,0)
        else:BasicAsm.zero(self,addr)
    def set_full(self,addr,value):self.imm(4,value);self.full_st(addr,4)
    def call(self,label):
        self.fix.append((len(self.data)+2,label))
        self.emit(bytes.fromhex('ca000000'),f'CALLA {label}')
    def ret(self):self.raw('cb00','RET')

def assemble(torque=False):
    a=Asm()
    if torque:
        from torque_patch import assemble_torque
        tq,_=assemble_torque(BasicAsm,far,word)
    a.label('tick_wrapper')
    a.emit(far(0xDA,0x01A060),'CALLS 01A060h ; original serial service, unchanged')
    a.raw('ec88','PUSH PSW')
    for r in range(4,16):a.emit(bytes([0xEC,0xF0+r]),f'PUSH R{r}')
    # Explicit DPP-independent accesses to all engine RAM; CAN direct accesses
    # use the original task's DPP3=3, as do the displaced OEM routines.
    a.ld(4,MAGIC);a.cmp(4,TAG);a.branch(3,'begin')
    a.ld(4,STATE);a.cmp(4,0xFF);a.branch(2,'exit')
    a.cmp(4,0xFE);a.branch(2,'recover_wait')
    a.cmp(4,0xFD);a.branch(2,'bus_sync_wait')
    a.cmp(4,0);a.branch(3,'initialize')
    a.ld(4,0xEF02);a.andi(4,0x80);a.cmp(4,0);a.branch(3,'fault')
    a.ld(4,0xEF00);a.andi(4,1);a.cmp(4,0);a.branch(3,'fault')
    a.call('tp_tick')
    # Saturate at zero: servicing a pending RX may defer a due telemetry frame.
    # Never underflow a divider and postpone that frame by 65536 calls.
    for addr,mask in ((FAST_DIV,0xFF),(SLOW_DIV,0xFF),(WAIT,0xFF),(DIAG_WAIT,0xFF)):
        a.ld(4,addr);a.andi(4,mask);a.cmp(4,0);a.branch(2,f'div_done_{addr}')
        a.subi(4,1);a.st(addr,4);a.label(f'div_done_{addr}')
    a.ld(4,DIAG_PHASE);a.andi(4,15);a.cmp(4,0);a.branch(3,'diag_complete')
    if torque:
        a.emit(far(0xDA,tq.labels['torque_tick']),'CALLS torque_tick')
        a.cmp(4,0);a.branch(3,'exit')
    # Slow/extra phases do not coincide with fast sends. All are attempted at
    # most once per period; no burst of stale queued samples after contention.
    a.ld(4,FAST_DIV);a.cmp(4,0);a.branch(2,'fast_due')
    a.ld(4,SLOW_DIV);a.andi(4,0x1FFF);a.cmp(4,0);a.branch(2,'slow_due')
    a.ld(4,WAIT);a.cmp(4,0);a.branch(2,'extra_due')
    a.branch(0,'diag_poll')

    a.label('begin')
    if torque:a.zero(0xE7C0) # Invalidate torque state before CAN object reinitialization.
    for addr in range(0xEF42,0xEF54,2):a.set_full(addr,0)
    a.set(0xEF00,0x61) # INIT, CCE, disable automatic retransmission; IRQs off.
    a.set(STATE,1);a.set(WAIT,0);a.set(FAST_SEQ,0);a.set(SLOW_SEQ,0);a.set(EXTRA_SEQ,0)
    a.set(MAGIC,TAG);a.branch(0,'exit')
    a.label('fault')
    a.set(0xEF00,0x61);a.set(STATE,0xFE);a.set_full(WAIT,500);a.branch(0,'exit')
    a.label('recover_wait')
    a.full_ld(4,WAIT);a.cmp(4,0);a.branch(2,'begin')
    a.subi(4,1);a.full_st(WAIT,4);a.branch(0,'exit')

    a.label('bus_sync_wait')
    # A bus-off status bit stays set until the hardware sees 129*11 recessive
    # bits after Init is released. Leave Init cleared while that recovery runs.
    # This state never spins and never queues TX while BOff is asserted.
    a.ld(4,0xEF00);a.andi(4,1);a.cmp(4,0);a.branch(3,'fault')
    a.ld(4,0xEF02);a.andi(4,0x80);a.cmp(4,0);a.branch(3,'exit')
    a.set(FAST_DIV,1);a.set(SLOW_DIV,2);a.set(WAIT,3);a.zero(DIAG_PHASE);a.zero(DIAG_WAIT);a.zero(STATE);a.branch(0,'exit')

    a.label('initialize')
    # Never spin on hardware. Initialization times out after 100 service calls.
    a.ld(4,WAIT);a.addi(4,1);a.st(WAIT,4);a.cmp(4,100);a.branch(14,'failed')
    a.ld(4,0xEF00);a.andi(4,0x41);a.cmp(4,0x41);a.branch(3,'exit')
    a.ld(4,0xEF10);a.andi(4,0x8000);a.cmp(4,0);a.branch(3,'exit')
    a.ld(7,STATE);a.cmp(7,1);a.branch(3,'timing_done')
    a.set(0xEF06,0x6B03);a.zero(0xEF0C)
    a.ld(4,0xEF06);a.cmp(4,0x6B03);a.branch(3,'failed')
    a.ld(4,0xEF0C);a.cmp(4,0);a.branch(3,'failed')
    a.label('timing_done')
    a.cmp(7,32);a.branch(14,'configure')
    a.zero(0xEF18);a.zero(0xEF1A);a.zero(0xEF1C)
    a.set(0xEF12,0xB0);a.st(0xEF10,7)
    a.addi(7,1);a.st(STATE,7);a.branch(0,'exit')
    a.label('configure')
    a.cmp(7,35);a.branch(14,'configure_diag')
    # Objects 1..3 have standard IDs 5E0..5E2. No receive objects / interrupts.
    a.rr(6,7);a.subi(6,32)
    a.rr(4,6);a.addi(4,0x5DF);a.shift(4,2,True);a.ori(4,0xA000);a.st(0xEF1A,4)
    a.zero(0xEF18);a.zero(0xEF14);a.zero(0xEF16)
    a.set(0xEF1C,0x88)
    for p in range(0xEF1E,0xEF26,2):a.zero(p)
    a.set(0xEF12,0xF3);a.st(0xEF10,6)
    a.addi(7,1);a.st(STATE,7);a.branch(0,'exit')
    a.label('configure_diag')
    a.cmp(7,38);a.branch(14,'enable')
    # 4 = response TX 7E8; 5 = physical RX 7E0; 6 = functional RX 7DF.
    a.rr(6,7);a.subi(6,32)
    a.zero(0xEF18);a.zero(0xEF14);a.set(0xEF16,0xDFFC)
    a.cmp(6,4);a.branch(3,'configure_rx')
    a.set(0xEF1A,0xA000|(0x7E8<<2));a.set(0xEF1C,0x88);a.branch(0,'configure_diag_write')
    a.label('configure_rx')
    a.set(0xEF1C,0x1088) # UMask + EoB + DLC8, no IRQ / remote response.
    a.imm(4,0x8000|(0x7E0<<2));a.cmp(6,5);a.branch(2,'configure_rx_id')
    a.imm(4,0x8000|(0x7DF<<2));a.label('configure_rx_id');a.st(0xEF1A,4)
    a.label('configure_diag_write')
    for p in range(0xEF1E,0xEF26,2):a.zero(p)
    a.set(0xEF12,0xF3);a.st(0xEF10,6)
    a.addi(7,1);a.st(STATE,7);a.branch(0,'exit')
    a.label('enable')
    a.set(0xEF00,0x20)
    a.ld(4,0xEF00);a.andi(4,0xFF);a.cmp(4,0x20);a.branch(3,'failed')
    a.set(STATE,0xFD);a.branch(0,'exit')
    a.label('failed')
    a.set(0xEF00,0x61);a.set(STATE,0xFF);a.branch(0,'exit')

    def ready(obj):
        a.ld(4,0xEF10);a.andi(4,0x8000);a.cmp(4,0);a.branch(3,'exit')
        a.ld(4,0xEF80);a.andi(4,1<<(obj-1));a.cmp(4,0);a.branch(3,'exit')
    def finish(obj,seqreg,valid=None):
        if valid is not None:a.imm(8,valid)
        a.ld(4,seqreg);a.andi(4,255);a.rr(5,4);a.shift(4,8,True);a.either(4,8);a.st(0xEF24,4)
        a.addi(5,1);a.andi(5,255);a.st(seqreg,5)
        a.set(0xEF1C,0x8088);a.set(0xEF12,0x97);a.set(0xEF10,obj);a.branch(0,'exit')

    a.label('fast_due');a.set(FAST_DIV,10);ready(1)
    a.imm(8,0)
    a.physical(4,0xF7C4);a.cmp(4,40000);a.branch(14,'rpm_bad')
    a.shift(4,2);a.ori(8,1);a.branch(0,'rpm_done')
    a.label('rpm_bad');a.imm(4,0)
    a.label('rpm_done');a.st(0xEF1E,4)
    a.physical(4,0xF0616);a.cmp(4,4095);a.branch(14,'tps_bad')
    a.shift(4,4);a.percent();a.ori(8,2);a.branch(0,'tps_done')
    a.label('tps_bad');a.imm(4,0)
    a.label('tps_done');a.rr(7,4)
    a.physical(4,0xF7C2,True);a.cmp(4,0);a.branch(2,'load_zero')
    a.physical(5,0xF4686);a.cmp(5,0);a.branch(2,'load_bad')
    a.physical(4,0xF8D6);a.cmpreg(4,5);a.branch(9,'load_saturated')
    a.imm(9,0)
    # Eight fixed iterations compute floor(numerator*256/denominator), n<d.
    for i in range(8):
        a.shift(9,1,True);a.shift(4,1,True);a.branch(8,f'load_sub_{i}')
        a.cmpreg(4,5);a.branch(8,f'load_next_{i}')
        a.label(f'load_sub_{i}');a.sub(4,5);a.ori(9,1)
        a.label(f'load_next_{i}')
    a.rr(4,9);a.branch(0,'load_scale')
    a.label('load_saturated');a.imm(4,255)
    a.label('load_scale');a.percent();a.ori(8,4);a.branch(0,'load_done')
    a.label('load_zero');a.ori(8,4)
    a.label('load_bad');a.imm(4,0)
    a.label('load_done');a.shift(4,8,True);a.either(4,7);a.st(0xEF20,4)
    a.zero(0xEF22) # Torque unavailable; corresponding validity bit is clear.
    finish(1,FAST_SEQ)

    a.label('slow_due');a.set(SLOW_DIV,50);ready(2)
    a.temp(0xF41D1,'ect');a.rr(7,4)
    a.temp(0xF41C9,'iat');a.shift(4,8,True);a.either(4,7);a.st(0xEF1E,4)
    a.zero(0xEF20);a.zero(0xEF22) # APP, flags, voltage not identified here.
    finish(2,SLOW_SEQ,3)

    a.label('extra_due');a.set(WAIT,50);ready(3)
    a.physical(4,0xF1238);a.shift(4,8);a.st(0xEF1E,4) # MAP, kPa.
    a.physical(4,0xF0527,True);a.st(0xEF20,4) # Signed raw spark advance; 0.75 deg/count.
    a.zero(0xEF22);finish(3,EXTRA_SEQ,3)

    # IF1 is shared serially. IF2 remains uncommanded private state storage.
    # A read starts in one call and is consumed only after Busy clears.
    a.label('diag_poll')
    ready(4)
    a.ld(4,DIAG_WAIT);a.andi(4,255);a.cmp(4,0);a.branch(3,'tp_poll')
    a.ld(4,0xEF90);a.andi(4,0x10);a.cmp(4,0);a.branch(2,'diag_functional')
    a.imm(7,5);a.branch(0,'diag_read')
    a.label('diag_functional')
    a.ld(4,0xEF90);a.andi(4,0x20);a.cmp(4,0);a.branch(2,'tp_poll');a.imm(7,6)
    a.label('diag_read')
    a.st(DIAG_PHASE,7);a.set(DIAG_WAIT,10)
    a.set(0xEF12,0x3F);a.st(0xEF10,7);a.branch(0,'exit')

    a.label('diag_complete')
    # A stuck cache read must not strand the asynchronous state machine.
    a.ld(4,DIAG_PHASE);a.cmp(4,7);a.branch(3,'diag_busy_check')
    a.full_ld(4,DIAG_PHASE);a.shift(4,7);a.cmp(4,0);a.branch(2,'fault')
    a.label('diag_busy_check')
    a.ld(4,0xEF10);a.andi(4,0x8000);a.cmp(4,0);a.branch(3,'exit')
    a.ld(4,DIAG_PHASE);a.cmp(4,7);a.branch(3,'diag_received')
    a.zero(DIAG_PHASE);a.branch(0,'tp_verify_done')
    a.label('diag_received');a.zero(DIAG_PHASE)
    a.ld(4,0xEF1C);a.andi(4,0x800F);a.cmp(4,0x8008);a.branch(3,'exit')
    a.ld(7,0xEF1A) # full arbitration must still match a standard data request.
    a.cmp(7,0x8000|(0x7E0<<2));a.branch(2,'diag_header')
    a.cmp(7,0x8000|(0x7DF<<2));a.branch(3,'exit')
    a.label('diag_header')
    a.ld(4,0xEF1E);a.rr(8,4);a.andi(4,255);a.shift(8,8)
    # Flow Control is handled only during the active physical ISO-TP transfer.
    a.rr(5,4);a.andi(5,0xF0);a.cmp(5,0x30);a.branch(2,'tp_fc')
    a.full_ld(5,0xEF44);a.shift(5,8);a.cmp(5,0);a.branch(3,'exit')
    # Incoming requests remain Single Frame; outgoing DTC lists support FF/CF.

    a.cmp(4,1);a.branch(8,'exit');a.cmp(4,7);a.branch(14,'exit')
    a.rr(10,4);a.ld(9,0xEF20)
    a.cmp(8,3);a.branch(2,'tp_start');a.cmp(8,7);a.branch(2,'tp_start')
    a.cmp(8,1);a.branch(2,'obd_request')
    a.cmp(7,0x8000|(0x7DF<<2));a.branch(2,'exit')
    a.cmp(8,0x22);a.branch(2,'rb_request')
    a.imm(5,0x11);a.branch(0,'negative')
    a.label('bad_length');a.imm(5,0x13);a.branch(0,'negative')
    a.label('not_supported');a.imm(5,0x31);a.branch(0,'negative')
    a.label('not_ready');a.imm(5,0x22);a.branch(0,'negative')
    a.label('retry_read');a.imm(8,0x22);a.imm(5,0x21);a.branch(0,'negative')
    a.label('negative')
    # Unsupported functional requests are silent. Never send fake empty DTCs.
    a.cmp(7,0x8000|(0x7DF<<2));a.branch(2,'exit')
    a.set(0xEF1E,0x7F03);a.shift(5,8,True);a.either(5,8);a.st(0xEF20,5)
    a.zero(0xEF22);a.zero(0xEF24);a.branch(0,'diag_send')

    a.label('obd_request')
    a.cmp(10,2);a.branch(3,'bad_length');a.andi(9,255)
    for pid in (0,0x20)+PID_LIST:
        a.cmp(9,pid);a.branch(2,f'pid_{pid}')
    a.branch(0,'not_supported')
    for pid,mask in ((0,PID_MASK),(0x20,PID_MASK20)):
        a.label(f'pid_{pid}');p=mask.to_bytes(4,'big')
        a.set(0xEF1E,0x4106);a.set(0xEF20,pid|(p[0]<<8))
        a.set(0xEF22,p[1]|(p[2]<<8));a.set(0xEF24,p[3]);a.branch(0,'diag_send')
    a.label('pid_1')
    # Native Mode01 CPU2F3C4..2F422: table BB338 = {00BB,003D};
    # PID BB33C = 01; bytes0..3 with byte4 validity. Copy the OEM data,
    # including actual MIL/readiness, rather than constructing readiness flags.
    a.physical(4,0xF40BF,True);a.cmp(4,0);a.branch(2,'not_ready')
    for i in range(4):a.physical(9+i,0xF40BB+i,True)
    for i in range(4):
        a.physical(4,0xF40BB+i,True);a.cmpreg(4,9+i);a.branch(3,'pid_1_changed')
    a.physical(4,0xF40BF,True);a.cmp(4,0);a.branch(2,'not_ready')
    a.rr(4,9);a.shift(4,8,True);a.ori(4,1);a.st(0xEF20,4)
    a.rr(4,11);a.shift(4,8,True);a.either(4,10);a.st(0xEF22,4)
    a.st(0xEF24,12);a.set(0xEF1E,0x4106);a.branch(0,'diag_send')
    a.label('pid_1_changed');a.imm(5,0x21);a.branch(0,'negative')

    # Exact native Mode01 buffers, including per-record validity. No guessed
    # conversions or unsupported catalyst/absolute-load/equivalence PIDs.
    for rec in NATIVE_PIDS:
        pid=int(rec['pid'],16)
        if pid==1:continue
        addr=int(rec['data_cpu_address'],16);size=rec['data_bytes']
        assert size in (1,2)
        a.label(f'pid_{pid}');a.imm(13,addr%0x4000);a.imm(14,size)
        a.branch(0,'native_page_'+str(addr//0x4000))
    for page in (0x3C,0x3D):
        a.label('native_page_'+str(page))
        # Byte accesses permit odd native RAM addresses. Check validity on both
        # sides and compare a second data read; does not claim atomic snapshot.
        a.rr(15,13);a.add(15,14)
        a.indexed(4,15,0,page,True);a.cmp(4,0);a.branch(2,'not_ready')
        a.indexed(4,13,0,page,True);a.rr(10,4);a.imm(11,0)
        a.cmp(14,1);a.branch(2,f'native_one_{page}')
        a.indexed(4,13,1,page,True);a.rr(11,4)
        a.label(f'native_one_{page}')
        a.indexed(4,13,0,page,True);a.cmpreg(4,10);a.branch(3,'pid_1_changed')
        a.cmp(14,1);a.branch(2,f'native_valid_{page}')
        a.indexed(4,13,1,page,True);a.cmpreg(4,11);a.branch(3,'pid_1_changed')
        a.label(f'native_valid_{page}')
        a.indexed(4,15,0,page,True);a.cmp(4,0);a.branch(2,'not_ready')
        a.branch(0,'native_send')
    a.label('native_send')
    a.shift(10,8,True);a.either(10,9);a.st(0xEF20,10)
    a.st(0xEF22,11);a.zero(0xEF24);a.addi(14,2);a.ori(14,0x4100)
    a.st(0xEF1E,14);a.branch(0,'diag_send')

    a.label('rb_request')
    a.cmp(10,3);a.branch(3,'bad_length')
    a.rr(4,9);a.andi(4,255);a.cmp(4,0xF2);a.branch(3,'not_supported')
    a.shift(9,8);a.cmp(9,0);a.branch(2,'rb_info')
    a.cmp(9,1);a.branch(2,'rb_dtc_guard_words')
    a.cmp(9,2);a.branch(2,'rb_dtc_state')
    for did in (3,4,5):a.cmp(9,did);a.branch(2,'rb_state_'+str(did))
    if torque:a.cmp(9,6);a.branch(2,'rb_torque_sample')
    a.cmp(9,0x10);a.branch(8,'not_supported');a.cmp(9,0x19);a.branch(14,'not_supported')
    # OEM DTC slots: F382E + 72*i, max ten. Read-only snapshot; no OEM calls.
    # Check catalog and absence of a pending native operation. F0B5C is NOT
    # an initialization signature: OEM2CC28..2CD3C sets5A5A for an operation,
    # and OEM2D2F8/2D3BE clears it to0. Bench D incorrectly required5A5A.
    a.physical(4,0xF0B56);a.cmp(4,0x2BDA);a.branch(3,'not_ready')
    a.physical(4,0xF0B5C);a.cmp(4,0);a.branch(3,'not_ready')
    a.physical(6,0xF2859,True);a.cmp(6,10);a.branch(14,'not_ready')
    a.set(0xEF1E,0x6207);a.rr(4,9);a.shift(4,8,True);a.ori(4,0xF2);a.st(0xEF20,4)
    a.subi(9,0x10);a.cmpreg(9,6);a.branch(9,'dtc_empty')
    a.rr(7,9);a.shift(7,3,True);a.add(7,9);a.shift(7,3,True)
    a.indexed(10,7,0x382E,0x3C);a.cmp(10,0);a.branch(2,'dtc_empty')
    a.cmp(10,104);a.branch(14,'dtc_unavailable')
    a.indexed(5,7,0x3833,0x3C,True)
    a.indexed(11,7,0x3836,0x3C);a.indexed(8,7,0x3838,0x3C)
    a.rr(4,11);a.shift(4,8);a.andi(4,15);a.indexed(4,4,0x3112,0x2E,True)
    # Only the four mapped single-bit subtypes are valid (table values 0..3).
    a.cmp(4,3);a.branch(14,'dtc_unavailable')
    a.rr(6,10);a.shift(6,2,True);a.add(6,4);a.shift(6,1,True)
    a.indexed(6,6,0x2BDA,0x2E);a.swap(6,4);a.st(0xEF22,6)
    a.imm(4,1);a.rr(6,8);a.andi(6,8);a.cmp(6,0);a.branch(2,'dtc_flags_done')
    a.ori(4,8);a.cmp(5,10);a.branch(15,'dtc_pending_test');a.ori(4,2)
    a.label('dtc_pending_test');a.cmp(5,10);a.branch(8,'dtc_flags_done')
    a.cmp(5,12);a.branch(14,'dtc_flags_done');a.ori(4,4)
    a.label('dtc_flags_done');a.shift(4,8,True);a.either(4,5);a.st(0xEF24,4)
    # Detect an interrupt/task changing the slot during extraction. The client
    # additionally requires two identical complete ten-slot sweeps.
    a.indexed(4,7,0x382E,0x3C);a.cmpreg(4,10);a.branch(3,'dtc_retry')
    a.indexed(4,7,0x3833,0x3C,True);a.cmpreg(4,5);a.branch(3,'dtc_retry')
    a.indexed(4,7,0x3836,0x3C);a.cmpreg(4,11);a.branch(3,'dtc_retry')
    a.indexed(4,7,0x3838,0x3C);a.cmpreg(4,8);a.branch(3,'dtc_retry')
    a.branch(0,'diag_send')
    a.label('dtc_empty');a.zero(0xEF22);a.zero(0xEF24);a.branch(0,'diag_send')
    a.label('dtc_retry');a.imm(7,0);a.branch(0,'retry_read')
    a.label('dtc_unavailable');a.imm(7,0);a.imm(8,0x22);a.branch(0,'not_ready')
    # Read-only engineering data, deliberately available even when DTC guard
    # rejects. They expose real state rather than encouraging guesswork.
    a.label('rb_dtc_guard_words')
    a.set(0xEF1E,0x6207);a.set(0xEF20,0x01F2)
    a.physical(4,0xF0B56);a.swap(4,5);a.st(0xEF22,4)
    a.physical(4,0xF0B5C);a.swap(4,5);a.st(0xEF24,4)
    a.branch(0,'diag_send')
    a.label('rb_dtc_state')
    a.set(0xEF1E,0x6207);a.set(0xEF20,0x02F2)
    a.physical(4,0xF2859,True);a.physical(5,0xF40BF,True)
    a.shift(5,8,True);a.either(4,5);a.st(0xEF22,4)
    a.physical(4,0xF0B60);a.swap(4,5);a.st(0xEF24,4)
    a.branch(0,'diag_send')
    # Engineering snapshots: fixed, audited addresses only; no memory-write API.
    for did,first,second,byte_pair in (
        (3,0xF02F8,0xF02FB,True),
        (4,0xF177C,0xF06C4,False),
        (5,0xBA964,0xBD04A,False)):
        a.label('rb_state_'+str(did))
        a.set(0xEF1E,0x6207);a.set(0xEF20,0xF2|(did<<8))
        if byte_pair:
            a.physical(4,first,True);a.physical(5,second,True)
            a.shift(5,8,True);a.either(4,5);a.st(0xEF22,4)
            a.physical(4,0xA861A,True);a.st(0xEF24,4)
        else:
            a.physical(4,first);a.swap(4,5);a.st(0xEF22,4)
            a.physical(4,second);a.swap(4,5);a.st(0xEF24,4)
        a.branch(0,'diag_send')
    if torque:
        a.label('rb_torque_sample')
        a.ld(4,0xE7C0);a.cmp(4,0xA4D2);a.branch(3,'not_ready')
        a.set(0xEF1E,0x6207);a.set(0xEF20,0x06F2)
        for addr,out in ((0xE7DA,0xEF22),(0xE7DC,0xEF24)):
            a.ld(4,addr);a.swap(4,5);a.st(out,4)
        a.branch(0,'diag_send')
    a.label('rb_info')
    # 62 F2 00: protocol revision1, build E4M3(11)/E3(7), capabilities, slots.
    a.set(0xEF1E,0x6207);a.set(0xEF20,0x00F2);a.set(0xEF22,0x0B01 if torque else 0x0701)
    a.set(0xEF24,0x0A0F if torque else 0x0A07);a.branch(0,'diag_send')
    a.label('diag_send')
    a.set(0xEF1C,0x8088);a.set(0xEF12,0x97);a.set(0xEF10,4);a.branch(0,'exit')
    from can_isotp import emit
    emit(a)
    a.label('exit')
    for r in reversed(range(4,16)):a.emit(bytes([0xFC,0xF0+r]),f'POP R{r}')
    a.raw('fc88','POP PSW');a.raw('db00','RETS')
    return a,a.finish()

def checks(b):
    out=[]
    for p in CHECKS:
        first,last,stored,inv=struct.unpack_from('<4I',b,p)
        lo,hi=offset(first),offset(last)+1
        assert lo%2==hi%2==0 and lo<hi<=len(b)
        actual=sum(x[0] for x in struct.iter_unpack('<H',b[lo:hi])) & 0xFFFFFFFF
        out.append({'file_offset':p,'start_cpu':first,'end_cpu':last,'stored':stored,
                    'actual':actual,'valid':actual==stored and inv==(stored^0xFFFFFFFF)})
    return out

def build(base,donor):
    assert len(base)==0xD0000 and hashlib.sha256(base).hexdigest()==BASE_SHA
    assert len(donor)==0xD0000 and hashlib.sha256(donor).hexdigest()==DONOR_SHA
    assert all(x['valid'] for x in checks(base))
    assert base[0xAB338:0xAB33D]==bytes.fromhex('BB003D0001') # native PID01 pointer/id
    for rec in NATIVE_PIDS:
        p=int(rec['descriptor_file_offset'],16)
        assert base[p]==int(rec['descriptor'],16)
        p=int(rec['pointer_file_offset'],16);off,page=struct.unpack_from('<HH',base,p)
        assert page*0x4000+off==int(rec['data_cpu_address'],16)
        assert base[int(rec['id_file_offset'],16)]==int(rec['pid'],16)
    anchors={0x93A46:'e6fc036bf6fc06ef',0x205B4:'e6fd9700f6fd12ef',0xA1BA0:'f2f4c4f77c84'}
    for p,h in anchors.items():assert donor[p:p+len(bytes.fromhex(h))]==bytes.fromhex(h)
    a,code=assemble();b=bytearray(base);patches=[]
    def patch(p,old,new,why):
        assert len(old)==len(new) and b[p:p+len(old)]==old,(hex(p),why)
        b[p:p+len(old)]=new
        patches.append({'file_offset':p,'old':old.hex(),'new':new.hex(),'why':why})
    patch(offset(ORIGIN),b'\xff'*len(code),code,'CAN telemetry and read-only diagnostic task; no engine RAM allocation')
    patch(0x8405C,bytes.fromhex('da0160a0'),far(0xDA,ORIGIN),'Wrap existing serial service; preserve its call and all other callbacks')
    for p,value in [(0x2FC,0x43C),(0x302,0x43C),(0x30E,0x414),(0x314,0x414),
                    (0x336,0x43C),(0xBC38,0x43C),(0xBC3E,0x43C)]:
        patch(p,word(value),word(value|1),'Enable CAN1 in known XPERCON/XPEREMU paths; CAN2 remains disabled')
    for _ in range(5):
        invalid=[x for x in checks(b) if not x['valid']]
        if not invalid:break
        for x in invalid:struct.pack_into('<II',b,x['file_offset']+8,x['actual'],x['actual']^0xFFFFFFFF)
    assert all(x['valid'] for x in checks(b))
    allowed=set()
    for x in patches:allowed.update(range(x['file_offset'],x['file_offset']+len(bytes.fromhex(x['new']))))
    for p in CHECKS:allowed.update(range(p+8,p+16))
    changed={i for i,(x,y) in enumerate(zip(base,b)) if x!=y}
    assert changed<=allowed
    return bytes(b),a,{'base_sha256':BASE_SHA,'donor_sha256':DONOR_SHA,
      'result_sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b),'code_bytes':len(code),
      'labels':a.labels,'patches':patches,'changed_bytes':len(changed),'checksum_records':checks(b),
      'status':'EXPERIMENTAL_BENCH_ONLY_NOT_PHYSICALLY_TESTED',
      'native_chery_protocol_preserved':False,'protocol':'RB telemetry 5E0..5E2 + OBD modes01/03/07 + ISO-TP responses + RB read-only DTC SID22; 7E0/7DF -> 7E8',
      'nominal_bitrate':500000,'assumed_CAN_clock_Hz':40000000,'btr':'0x6B03',
      'assumed_task_period_ms':2,'CAN_RX_control':False,'CAN_RX_diagnostics':True,'standard_OBD_PIDs':list(PID_LIST),'CAN_DTC_clear':False,'CAN_OBD_mode03_07':True,'RB_DTC_slot_DIDs':[0xF210+i for i in range(10)],'torque_reduction':False,
      'engine_calibration_bytes_changed':False,'original_KLine_callbacks_preserved':True,
      'source_routines_invoked_by_payload':[0x01A060],
      'additional_system_stack_bytes':36,'saved_register_stack_bytes':26,'wrapper_return_frame_bytes':4,'engine_RAM_allocated_bytes':0,
      'revision':'E3_SW', 'RB_state_DIDs':[0xF201,0xF202,0xF203,0xF204,0xF205], 'audit_fixes':['F0B5C must be0 for no pending operation;5A5A is not initialization', 'Read-only raw state DIDs for hardware diagnosis', 'Mask IF2M2 reserved bit13 on every slow-divider read', 'Wait with Init cleared until hardware clears BOff', 'Set NewDat with TxRqst when updating TX data', 'Saturate periodic dividers during asynchronous RX', 'Serialize IF1 receive/transmit without overwriting IF2 state'],
      'validation_limits':['No ECU execution, HIL, or full ST10 firmware emulation',
        'Flash FF gap and direct-reference scan cannot prove absence of computed references',
        'Task period and clock must be measured on ECU',
        'Payload validity indicates representable processed ECU values, not absence of sensor DTCs',
        'No proven actual torque, APP, or battery-voltage signal in this patch']}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('base',type=Path);p.add_argument('donor',type=Path);p.add_argument('--outdir',type=Path,required=True)
    q=p.parse_args();q.outdir.mkdir(parents=True,exist_ok=True)
    b,a,r=build(q.base.read_bytes(),q.donor.read_bytes())
    (q.outdir/'GW4G15_REV8_CAN_DIAG_BENCH_E3_SW.bin').write_bytes(b)
    (q.outdir/'PATCH_REPORT.json').write_text(json.dumps(r,indent=2)+'\n')
    lines=['; ST10 CAN telemetry and read-only diagnostic bench patch. CPU and packed-file addresses are distinct.']
    for pc,n,s in a.rows:
        lines += [k+':' for k,v in a.labels.items() if v==pc]
        lines.append(f'{pc:06X} file:{offset(pc):06X} {b[offset(pc):offset(pc)+n].hex().upper():10} {s}')
    (q.outdir/'can_diag.asm').write_text('\n'.join(lines)+'\n')
    print(json.dumps({k:r[k] for k in ('result_sha256','code_bytes','changed_bytes','status')}))

if __name__=='__main__':main()
