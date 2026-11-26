#!/usr/bin/env python3
"""Test actual emitted instructions; no ECU, scheduler, wire or NVM simulation."""
from pathlib import Path
import argparse, collections, hashlib, json, random, struct
from audit_machine import Machine, seed
from build_can_diag import STATE, DIAG_PHASE, DIAG_WAIT, FAST_DIV, SLOW_DIV, WAIT

def start(m):
    seed(m)
    for _ in range(110):
        m.run()
        if m.get(STATE)==0:return
    raise AssertionError('Init did not complete')

def query(m,payload,identifier=0x7E0,raw=False,steps=22):
    data=bytes(payload) if raw else bytes([len(payload),*payload]).ljust(8,b'\0')
    before=len(m.frames)
    assert m.inject(identifier,data)
    for _ in range(steps):m.run()
    out=[bytes.fromhex(f['data']) for f in m.frames[before:] if f['id']==0x7E8]
    assert len(out)<=1,out
    return out[0] if out else None

def main(image,out):
    b=Path(image).read_bytes();m=Machine(b);start(m);result={}
    expected_mask=bytes.fromhex('064100be3eb81100')
    assert query(m,[1,0])==expected_mask
    assert query(m,[1,0],0x7DF)==expected_mask
    assert query(m,[0x22,0xF2,0])==bytes.fromhex('0762F200010B0F0A' if m.torque_enabled else '0762F2000107070A')
    assert query(m,[1,1])==bytes.fromhex('037F012200000000')
    m.poke(0xF40BF,1,1)
    for i,v in enumerate([0x83,0x07,0x65,0x04]):m.poke(0xF40BB+i,v,1)
    assert query(m,[1,1])==bytes.fromhex('0641018307650400')
    changed=[0]
    def mutate_readiness(machine,address,n):
        if address==0xF40BC:
            changed[0]+=1
            if changed[0]==2:machine.poke(address,0x08,1)
    m.read_hook=mutate_readiness
    assert query(m,[1,1])==bytes.fromhex('037F012100000000')
    m.read_hook=None
    result['native_PID01_copy_validity_and_consistency']='PASS'
    spec={1: (999611, 4), 3: (999640, 2), 4: (999829, 1), 5: (999630, 1), 6: (999581, 1), 7: (999583, 1), 11: (999836, 1), 12: (999577, 2), 13: (983521, 1), 14: (999616, 1), 15: (999632, 1), 17: (999587, 1), 19: (999628, 1), 20: (999603, 2), 21: (999599, 2), 28: (999606, 1), 33: (999608, 2)}
    result['supported_PIDs']=[f'{p:02X}' for p in spec]
    assert query(m,[1,0x20])==bytes.fromhex('0641208000000000')
    assert query(m,[1,0x20],0x7df)==bytes.fromhex('0641208000000000')
    random.seed(20261001);cases=0
    # Expected native addresses transcribed independently from native tables;
    # execute real new instruction bytes with all byte values and validity.
    for pid,(address,size) in spec.items():
        for value in range(256):
            data=bytes((value+j*71)&255 for j in range(size))
            for j,x in enumerate(data):m.poke(address+j,x,1)
            m.poke(address+size,1,1)
            want=bytes([2+size,0x41,pid])+data+bytes(5-size)
            assert query(m,[1,pid])==want,(pid,value)
            if value in (0,127,255):assert query(m,[1,pid],0x7df)==want
            cases+=1
        m.poke(address+size,0,1)
        assert query(m,[1,pid])==bytes.fromhex('037f012200000000')
        assert query(m,[1,pid],0x7df) is None
        m.poke(address+size,1,1);hits=[0]
        def change_data(machine,a,n):
            if a==address:
                hits[0]+=1
                if hits[0]==2:machine.poke(a,0x67,1)
        m.read_hook=change_data
        assert query(m,[1,pid])==bytes.fromhex('037f012100000000'),pid
        m.read_hook=None;hits=[0]
        def invalidate(machine,a,n):
            if a==address+size:
                hits[0]+=1
                if hits[0]==2:machine.poke(a,0,1)
        m.read_hook=invalidate
        assert query(m,[1,pid])==bytes.fromhex('037f012200000000'),pid
        m.read_hook=None
    result['native_OBD_byte_cases']=cases
    result['all_PID_validity_mutation_checks']=True
    # Only truthful supported services: no fake unsupported-service success.
    for sid in range(256):
        if sid in (1,3,7,0x22):continue
        assert query(m,[sid])==bytes([3,0x7F,sid,0x11,0,0,0,0])
        assert query(m,[sid],0x7DF) is None
    for pid in range(256):
        if pid in (0,32) or pid in spec:continue
        assert query(m,[1,pid])==bytes.fromhex('037F013100000000')
        assert query(m,[1,pid],0x7DF) is None
    result['unsupported_service_cases']=504;result['unsupported_PID_cases']=2*(256-19)
    for data in (bytes.fromhex('0001000000000000'),bytes.fromhex('1008010000000000'),
                 bytes.fromhex('2101000000000000'),bytes.fromhex('3000000000000000'),
                 bytes.fromhex('0801000000000000')):
        assert query(m,data,raw=True) is None
    for dlc in range(8):
        n=len(m.frames);assert m.inject(0x7E0,bytes([2,1,12,0,0,0,0,0]),dlc=dlc)
        for _ in range(22):m.run()
        assert not any(f['id']==0x7E8 for f in m.frames[n:])
    assert query(m,[1])==bytes.fromhex('037F011300000000')
    assert query(m,[1,12,5])==bytes.fromhex('037F011300000000')
    assert query(m,[0x22,0xF2])==bytes.fromhex('037F221300000000')
    for ident,ext,rtr in ((0x7E1,False,False),(0x5E0,False,False),(0x7E0,True,False),(0x7E0,False,True),(0x7DF,True,True)):
        assert not m.inject(ident,bytes.fromhex('02010C0000000000'),ext,rtr)
    result['malformed_and_filter_cases']=21
    # Exact Rev8 DTC metadata, initialisation and double-read guards.
    assert query(m,[0x22,0xF2,0x10])==bytes.fromhex('037F222200000000')
    m.poke(0xF0B56,0x2BDA);m.poke(0xF0B5C,0);m.poke(0xF2859,10,1)
    reference=Path(image).read_bytes()
    table=list(reference[0xAB112:0xAB122])
    dtc_cases=0
    for i in range(4000):
        slot=random.randrange(10);event=random.randrange(108);status=random.randrange(256)
        subtype=random.randrange(16);flags=random.randrange(65536);s=0xF382E+slot*72
        for addr,value,width in ((s,event,2),(s+5,status,1),(s+8,subtype<<8,2),(s+10,flags,2)):m.poke(addr,value,width)
        r=query(m,[0x22,0xF2,0x10+slot])
        if event==0:want=bytes([7,0x62,0xF2,0x10+slot,0,0,0,0])
        elif event>104 or table[subtype]>3:want=bytes.fromhex('037F222200000000')
        else:
            code=struct.unpack_from('<H',reference,0xAABDA+8*event+2*table[subtype])[0]
            f=1|(8 if flags&8 else 0)|(2 if flags&8 and status>10 else 0)|(4 if flags&8 and 10<=status<=12 else 0)
            want=bytes([7,0x62,0xF2,0x10+slot,code>>8,code&255,status,f])
        assert r==want,(slot,event,status,subtype,r,want);dtc_cases+=1
    result['DTC_slot_cases']=dtc_cases
    for value in (11,255):
        m.poke(0xF2859,value,1);assert query(m,[0x22,0xF2,0x10])==bytes.fromhex('037F222200000000')
    m.poke(0xF2859,0,1)
    for slot in range(10):assert query(m,[0x22,0xF2,0x10+slot])==bytes([7,0x62,0xF2,0x10+slot,0,0,0,0])
    m.poke(0xF2859,1,1);m.poke(0xF382E,5);m.poke(0xF3833,11,1);m.poke(0xF3836,0x100);m.poke(0xF3838,8)
    seen=[0]
    def change_slot(machine,address,n):
        if address==0xF382E:
            seen[0]+=1
            if seen[0]==2:machine.poke(address,6)
    m.read_hook=change_slot
    assert query(m,[0x22,0xF2,0x10])==bytes.fromhex('037F222100000000')
    m.read_hook=None;result['DTC_changed_during_read_rejected']=True
    # Truly delayed interface completion; no reads/writes of live staging data
    # until Busy clears. Tests include overwrite with a newer request.
    for delay in (0,1,2):
        q=Machine(b);q.transfer_delay=delay;start(q)
        for _ in range(15):assert query(q,[1,0],steps=28)==expected_mask
        assert q.calls.count(0x1A060)==q.tick
    result['asynchronous_IF1_transfer_delays_calls']=[0,1,2]
    q=Machine(b);start(q);q.inject(0x7E0,bytes.fromhex('02010C0000000000'));q.inject(0x7E0,bytes.fromhex('0201000000000000'))
    for _ in range(30):q.run()
    assert [f['data'] for f in q.frames if f['id']==0x7E8]==[expected_mask.hex()]
    assert query(q,[1,0])==expected_mask # MsgLst persists but does not poison RX.
    result['overrun_latest_request_and_next_request']=True
    # Continuous request flood cannot stop periodic transmission or serial calls.
    q=Machine(b);start(q)
    for i in range(5000):
        q.inject(0x7E0,bytes.fromhex('0201000000000000'));q.run()
    for ident,maximum in ((0x5E0,12),(0x5E1,54),(0x5E2,54)):
        f=[x for x in q.frames if x['id']==ident];assert len(f)>80
        gap=max(c['tick']-a['tick'] for a,c in zip(f,f[1:]));assert gap<=maximum,(ident,gap)
    result['flood_5000_calls_counts']={hex(k):v for k,v in collections.Counter(f['id'] for f in q.frames).items()}
    assert q.calls.count(0x1A060)==q.tick
    # Pending/busy stalls, absent ACK, failure latch and recovery with pending RX.
    for pending in (8,15):
        q=Machine(b);start(q);q.pending=pending;q.inject(0x7E0,bytes.fromhex('0201000000000000'))
        for _ in range(200):q.run()
        assert not any(f['id']==0x7E8 for f in q.frames)
        q.pending=0
        for _ in range(30):q.run()
        assert any(f['id']==0x7E8 for f in q.frames)
    q=Machine(b);start(q);q.ack=False
    assert query(q,[1,0]) is None and q.noack_attempts>0
    q.ack=True;assert query(q,[1,0])==expected_mask
    for kind in ('busy','timing'):
        q=Machine(b);seed(q)
        if kind=='busy':q.busy=True
        else:q.stuck_timing=True
        for _ in range(220):q.run()
        assert q.get(STATE)&255==0xFF and not q.frames and q.calls.count(0x1A060)==q.tick
    for pending_rx in (False,True):
        q=Machine(b);start(q)
        if pending_rx:
            q.inject(0x7E0,bytes.fromhex('0201000000000000'))
            for _ in range(10):
                q.run()
                if q.get(DIAG_PHASE)&15:break
            assert q.get(DIAG_PHASE)&15
        q.poke(0xEF02,0x80);q.poke(0xEF00,0x21)
        for _ in range(850):q.run()
        assert q.get(STATE)==0xFD and not q.get(0xEF00)&1
        q.poke(0xEF02,0)
        for _ in range(80):q.run()
        assert q.get(STATE)==0 and query(q,[1,0])==expected_mask
    result['busy_pending_noACK_busoff_failure_tests']='PASS'
    assert all((0xEF00<=a<=0xEF54 and a!=0xEF40) or (m.torque_enabled and 0xE7C0<=a<0xE800) for a,v in m.writes)
    result['stores_confined_to_CAN_and_reserved_torque_RAM']=True
    result['max_observed_stack_bytes']=m.max_stack
    result['saved_register_stack_bytes']=26
    assert m.max_stack==(32 if m.torque_enabled else 28)
    result['max_observed_wrapper_instructions']=m.max_insns
    result['sha256']=hashlib.sha256(b).hexdigest()
    result['status']='PASS_LIMITED_MACHINE_REGISTER_MODEL'
    result['physical_ECU_test']=False
    result['limits']=['Original serial callback is stubbed', 'No full firmware/interrupt/clock/stack/wire emulation', 'DTC extraction reference independently translated from native functions, not native task execution', 'No CAN DTC clearing; ISO-TP covered separately']
    Path(out).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('image');p.add_argument('--out',required=True)
    a=p.parse_args();main(a.image,a.out)
