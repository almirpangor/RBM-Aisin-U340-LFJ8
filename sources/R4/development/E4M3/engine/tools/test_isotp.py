#!/usr/bin/env python3
"""Exercise emitted bytes against independent ISO-TP/DTC expectations.

The model omits real interrupts, CPU timing, electrical faults and NVM effects.
"""
import argparse, hashlib, json, random, struct
from pathlib import Path
from audit_machine import Machine,seed
from can_isotp import TP_STATE, TP_TIMER, TP_INDEX, WAIT_FC, WAIT_TX, VERIFY_DONE

def start(image,delay=0):
    m=Machine(image);m.transfer_delay=delay;seed(m)
    for _ in range(120):m.run()
    assert m.get(0xEF4E)&255==0
    return m

def slots(m,records):
    m.poke(0xF0B56,0x2BDA);m.poke(0xF0B5C,0);m.poke(0xF2859,len(records),1)
    for i in range(10):
        event,status,subtype,flags=records[i] if i<len(records) else (0,0,0,0)
        a=0xF382E+72*i
        for addr,v,n in ((a,event,2),(a+5,status,1),(a+8,subtype<<8,2),(a+10,flags,2)):m.poke(addr,v,n)

def expect(image,records,sid):
    codes=[]
    for event,status,subtype,flags in records:
        if not event:continue
        if event>104:return bytes([0x7F,sid,0x22])
        if not flags&8 or not (status>10 if sid==3 else 10<=status<=12):continue
        kind=image[0xAB112+(subtype&15)]
        if kind>3:return bytes([0x7F,sid,0x22])
        code=struct.unpack_from('<H',image,0xAABDA+8*event+2*kind)[0]
        if code in (0,65535):return bytes([0x7F,sid,0x22])
        codes.append(code)
    return bytes([sid+0x40,len(codes)])+b''.join(x.to_bytes(2,'big') for x in codes)

def fc(m,bs=0,st=0,kind=0x30):
    assert m.inject(0x7E0,bytes([kind,bs,st,0,0,0,0,0]))

def exchange(m,sid,bs=0,st=0,ident=0x7E0,max_ticks=1100,auto_fc=True):
    before=len(m.frames);assert m.inject(ident,bytes([1,sid,0,0,0,0,0,0]))
    seen=before;payload=bytearray();size=None;seq=1;block=0;frames=[]
    for _ in range(max_ticks):
        m.run()
        for f in m.frames[seen:]:
            if f['id']!=0x7E8:continue
            d=bytes.fromhex(f['data']);frames.append(f)
            if d[0]<0x10:
                assert not payload
                return d[1:1+d[0]],frames
            if d[0]>>4==1:
                assert not payload
                size=(d[0]&15)*256+d[1];assert 8<=size<=22
                payload.extend(d[2:])
                if auto_fc:fc(m,bs,st)
            else:
                assert size is not None and d[0]==0x20|seq,(d.hex(),seq)
                seq=(seq+1)&15;payload.extend(d[1:]);block+=1
                if len(payload)>=size:return bytes(payload[:size]),frames
                if auto_fc and bs and block==bs:fc(m,bs,st);block=0
        seen=len(m.frames)
    return None,frames

def first_frame(m,sid=3):
    n=len(m.frames);m.inject(0x7E0,bytes([1,sid,0,0,0,0,0,0]))
    for _ in range(100):
        m.run()
        frames=[f for f in m.frames[n:] if f['id']==0x7E8]
        if frames:
            assert bytes.fromhex(frames[0]['data'])[0]==0x10
            return frames[0]
    raise AssertionError('No First Frame')

def main(image,out):
    b=Path(image).read_bytes();result={};max_stack=max_insns=0
    def stats(m):
        nonlocal max_stack,max_insns
        max_stack=max(max_stack,m.max_stack);max_insns=max(max_insns,m.max_insns)
        assert m.calls.count(0x1A060)==m.tick and all((0xEF00<=a<=0xEF54 and a!=0xEF40) or (m.torque_enabled and 0xE7C0<=a<0xE800) for a,v in m.writes)
    events=[e for e in range(1,105) if struct.unpack_from('<H',b,0xAABDA+8*e)[0] not in (0,65535)][:10]
    records=[(e,11,1,8) for e in events]
    cases=0
    for delay in (0,1,2):
        for sid in (3,7):
            for n in range(11):
                for ident in (0x7E0,0x7DF):
                    for bs in (0,1,2,3,255):
                        m=start(b,delay);slots(m,records[:n]);got,frames=exchange(m,sid,bs,ident=ident)
                        assert got==expect(b,records[:n],sid),(delay,sid,n,ident,bs,got,frames)
                        stats(m);cases+=1
    result['sizes_0_to_10_both_services_addresses_BS_async_cases']=cases
    cases=0
    for st in (0,1,2,5,20,127,0xF1,0xF9):
        for bs in (0,1,2):
            m=start(b);slots(m,records);got,frames=exchange(m,3,bs,st)
            assert got==expect(b,records,3)
            cfs=[f for f in frames if bytes.fromhex(f['data'])[0]>>4==2]
            min_us=st*1000 if st<128 else (st-0xF0)*100
            assert all((c['tick']-p['tick'])*2000>=min_us for p,c in zip(cfs,cfs[1:])),(st,bs,frames)
            stats(m);cases+=1
    result['STmin_and_block_boundary_cases']=cases
    random.seed(20261001);cases=0
    for _ in range(500):
        rec=[(random.randrange(106),random.choice([0,9,10,11,12,13,255]),random.randrange(16),random.randrange(16)) for _ in range(random.randrange(11))]
        for sid in (3,7):
            m=start(b);slots(m,rec);got,frames=exchange(m,sid)
            assert got==expect(b,rec,sid),(sid,rec,got,expect(b,rec,sid))
            stats(m);cases+=1
    result['random_native_selection_cases']=cases
    # Invalid metadata must not look like an empty list, and functional failures stay silent.
    for ident in (0x7E0,0x7DF):
        for bad in ('pointer','init','count','zero_code','bad_event'):
            m=start(b);slots(m,records)
            if bad=='pointer':m.poke(0xF0B56,0)
            elif bad=='init':m.poke(0xF0B5C,0x5A5A)
            elif bad=='count':m.poke(0xF2859,11,1)
            elif bad=='zero_code':slots(m,[(2,11,1,8)])
            else:slots(m,[(105,11,1,8)])
            got,_=exchange(m,3,ident=ident,max_ticks=80)
            assert got==(bytes.fromhex('7F0322') if ident==0x7E0 else None),(ident,bad,got)
    result['uninitialized_invalid_and_functional_errors']=10
    # No FC: expire cleanly and accept another request.
    m=start(b);slots(m,records);first_frame(m);n=len(m.frames)
    for _ in range(550):m.run()
    assert m.get(TP_STATE)>>8==0 and not any(f['id']==0x7E8 for f in m.frames[n:])
    assert exchange(m,3)[0]==expect(b,records,3);stats(m)
    # WAIT maximum, overflow, reserved separation time.
    for st,kind in ((0,0x32),(0x80,0x30),(0xF0,0x30),(0xFA,0x30)):
        m=start(b);slots(m,records);first_frame(m);fc(m,0,st,kind)
        for _ in range(30):m.run()
        assert m.get(TP_STATE)>>8==0
        assert exchange(m,7)[0]==expect(b,records,7);stats(m)
    m=start(b);slots(m,records);first_frame(m)
    for n in range(4):
        fc(m,kind=0x31)
        for _ in range(25):m.run()
        assert (m.get(TP_STATE)>>8!=0)==(n<3)
    assert exchange(m,3)[0]==expect(b,records,3);stats(m)
    result['timeout_overflow_reserved_STmin_WAIT_limit_and_reuse']='PASS'
    # Do not let a TX-pending frame get overwritten; bound first-CF waiting.
    m=start(b);slots(m,records);first_frame(m);m.pending=1<<6;fc(m)
    before=len(m.frames)
    for _ in range(530):m.run()
    assert m.get(TP_STATE)>>8==0
    assert not any(f['id']==0x7E8 for f in m.frames[before:])
    m.pending=0;assert exchange(m,3)[0]==expect(b,records,3);stats(m)
    result['stuck_TX_request_timeout']='PASS'
    # Change native data between build and verification: no cached DTC frame escapes.
    m=start(b);slots(m,records);before=len(m.frames);m.inject(0x7E0,bytes.fromhex('0103000000000000'))
    for _ in range(50):
        m.run()
        if m.get(TP_STATE)>>8==VERIFY_DONE:break
    else:raise AssertionError('No verification state')
    m.poke(0xF382E,events[1])
    for _ in range(60):m.run()
    replies=[f['data'] for f in m.frames[before:] if f['id']==0x7E8]
    assert replies==['037f032100000000'],replies;stats(m)
    result['changed_snapshot_rejected_before_first_frame']=True
    # Stuck IF1 cache verification triggers bounded CAN recovery, never a busy loop.
    m=start(b);slots(m,records);m.inject(0x7E0,bytes.fromhex('0103000000000000'))
    for _ in range(50):
        m.run()
        if m.get(TP_STATE)>>8==VERIFY_DONE:break
    else:raise AssertionError('No verification state')
    m.busy=True
    for _ in range(540):m.run()
    assert m.get(0xEF4E)&255==0xFE
    m.busy=False
    for _ in range(700):m.run()
    assert exchange(m,3)[0]==expect(b,records,3);stats(m)
    result['stuck_IF1_verify_timeout_and_recovery']=True
    # Competing requests during a long response must not corrupt cached data.
    m=start(b);slots(m,records);first_frame(m);before=len(m.frames)
    for _ in range(40):m.inject(0x7E0,bytes.fromhex('02010C0000000000'));m.run()
    assert not any(f['id']==0x7E8 for f in m.frames[before:])
    fc(m)
    for _ in range(80):m.run()
    cf=[f for f in m.frames[before:] if f['id']==0x7E8]
    assert [int(f['data'][:2],16) for f in cf]==[0x21,0x22,0x23]
    for ident,maxgap in ((0x5E0,14),(0x5E1,58),(0x5E2,58)):
        frames=[f for f in m.frames if f['id']==ident]
        assert max(c['tick']-p['tick'] for p,c in zip(frames,frames[1:]))<=maxgap
    stats(m);result['telemetry_and_serial_continue_during_ISOTP']=True
    result.update(status='PASS_LIMITED_MACHINE_REGISTER_MODEL',sha256=hashlib.sha256(b).hexdigest(),max_observed_stack_bytes=max_stack,max_observed_instructions=max_insns,physical_ECU_test=False)
    Path(out).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('image');p.add_argument('--out',required=True);a=p.parse_args();main(a.image,a.out)
