#!/usr/bin/env python3
"""Execute E4 instruction bytes, native hook windows, and the production STM C core.
The plant, native engine tasks outside selected windows, and physical CAN are not emulated.
"""
import ctypes as C,hashlib,json,random,sys,os
from pathlib import Path
from audit_machine import Machine,seed
import build_can_diag as diag
from build_e4 import ROOT,NAME
import torque_patch as tq
IMAGE=(ROOT/'firmware'/NAME).read_bytes()
ASM,_=tq.assemble_torque(diag.BasicAsm,diag.far,diag.word)
LABELS=ASM.labels
RESULT={}

def clock(m,ticks):
    m.poke(0xFE44,ticks&65535);m.poke(0xE176,(ticks>>16)&65535);m.poke(0xFF64,0)

def helper(m,name):
    m.return_stack.append((0x647FE,2));m.run(LABELS[name],stop=0x647FE)
    assert not m.return_stack
    return m.reg[4],m.reg[5]

def fresh(delay=0):
    m=Machine(IMAGE);seed(m,rpm4=8000);m.poke(0xFF44,0x46)
    for i in range(180):clock(m,i*156);m.run()
    assert m.get(tq.READY)==2 and m.get(tq.MODE)==0
    m.test_time=180*156;m.transfer_delay=delay
    return m

def steps(m,n=1,delta=156):
    for _ in range(n):m.test_time+=delta;clock(m,m.test_time);m.run()

def send(m,d,**kwargs):
    assert m.inject(0x5E8,d,**kwargs);steps(m,8)

def arm(m,red=32,duration=20,token=1,seq=1):
    send(m,tq.command(1,seq,red,duration,token))
    assert m.get(tq.MODE)==1 and m.get(tq.REASON)==0,(m.get(tq.MODE),m.get(tq.REASON))

def valid_state(m,now,start,rx,red=64,duration=23430):
    m.poke(tq.MAGIC,tq.TAG);m.poke(tq.MODE,1);m.poke(tq.RED,red);m.poke(tq.DURATION,duration)
    m.poke(tq.ORIGINAL_DURATION,duration);m.poke(tq.CALL_AGE,0);m.poke(tq.START_CALL_AGE,0)
    m.poke(tq.START_LO,start&65535);m.poke(tq.START_HI,start>>16)
    m.poke(tq.RX_LO,rx&65535);m.poke(tq.RX_HI,rx>>16);clock(m,now)

def expected(now,start,rx,red,duration):
    age=min(65535,(now-start)&0xFFFFFFFF);lease=min(65535,(now-rx)&0xFFFFFFFF)
    over=max(0,age-duration,lease-tq.LEASE)
    return max(0,min(red,(age-over)>>5)-(over>>7))

def unit_tests():
    m=fresh();rng=random.Random(0xA4)
    # Decoder/executor executes exact multiply-free scaling bytes, not C/Python substitute.
    pairs=[(x,r) for x in [0,1,2,127,128,255,256,257,32767,32768,65024,65534,65535] for r in range(65)]
    pairs += [(rng.randrange(65536),rng.randrange(65)) for _ in range(2500)]
    for x,r in pairs:
        m.reg[13]=x;m.reg[14]=r;v,_=helper(m,'scale');assert v==x*(256-r)//256,(x,r,v)
    RESULT['machine_scaling_cases']=len(pairs)
    # CRC independently cross-checked with the published check value.
    assert tq.crc8(b'123456789')==0x4B
    for _ in range(200):
        d=rng.randbytes(7);m.mem[0xEF1E:0xEF25]=d;m.reg[9]=0xEF1E;v,_=helper(m,'crc7');assert v==tq.crc8(d)
    RESULT['machine_crc_cases']=200
    count=0
    for start in [1000,65500,0xFFFFF000]:
        for elapsed in [0,31,32,100,1024,2048,3905,3906,3907,6000,12000,23430,24000,40000,65535,65536,200000,0x1000000]:
            for since_rx in [0,min(elapsed,2500),elapsed]:
                now=(start+elapsed)&0xFFFFFFFF;rx=(now-since_rx)&0xFFFFFFFF
                valid_state(m,now,start,rx);v,state=helper(m,'factor')
                assert v==expected(now,start,rx,64,23430),(start,elapsed,since_rx,v,state)
                count+=1
    RESULT['factor_clock_wrap_cases']=count
    # Hardware overflow pending, already serviced, and race during snapshot.
    clock(m,65536+2);m.poke(0xE176,0);m.poke(0xFF64,128);helper(m,'clock');assert (m.reg[11],m.reg[10],m.reg[12])==(1,2,1)
    clock(m,65530);m.poke(0xFF64,128);helper(m,'clock');assert m.reg[11]==0
    reads=[0]
    def rollover(q,a,n):
        if a==0xE176:
            reads[0]+=1
            if reads[0]==2:q.poke(a,1)
    clock(m,65530);m.read_hook=rollover;helper(m,'clock');assert m.reg[12]==0;m.read_hook=None
    # Gate loss latches off; restoring RPM/CAN does not reactivate the old pulse.
    for address,value in [(0xF7C4,4799),(0xF7C4,26001),(0xEF02,128),(0xEF00,0x21),(0xFF44,0),(tq.CALL_AGE,100),(tq.START_CALL_AGE,250)]:
        m=fresh();valid_state(m,3000,0,2500);m.poke(address,value);v,state=helper(m,'factor');assert (v,state,m.get(tq.MODE))==(0,5,0)
        m.poke(address,8000 if address==0xF7C4 else 0x46 if address==0xFF44 else 0x20 if address==0xEF00 else 0)
        assert helper(m,'factor')[0]==0
    RESULT['gate_and_counter_fault_cases']=7
    # Each native hook preserves every non-output register and displaced flags.
    # Branch windows execute original instructions from the patched image.
    cases=0
    for name,target,path in [('hook_air',9,1),('hook_fast',7,2),('hook_load',9,4)]:
        for red in [0,1,32,64]:
            for value in [0,1,255,256,20000,65024,65535]:
                m=fresh();valid_state(m,3000,0,2900,red=red)
                m.reg=[rng.randrange(65536) for _ in range(16)];m.reg[target]=value;old=m.reg[:];m.psw=0xA416;psw=m.psw
                m.poke(0xF177C,30000);m.poke(0xF175E,32000)
                m.run(LABELS[name]);out=value*(256-red)//256
                assert m.reg[target]==out,(name,red,value,m.reg[target],out)
                expected_regs=old[:];expected_regs[target]=out
                if name=='hook_fast':expected_regs[8]=out
                if name=='hook_load':expected_regs[4]=30000
                assert m.reg==expected_regs,(name,m.reg,expected_regs)
                if name!='hook_load':
                    cap=30000 if name=='hook_air' else 32000
                    assert bool(m.psw&2)==(out<cap) and bool(m.psw&8)==(out==cap)
                else:assert m.psw&~0x19==psw&~0x19
                assert m.get(tq.SEEN)==(path if red else 0)
                if red:assert m.get(tq.BEFORE)==value and m.get(tq.AFTER)==out
                cases+=1
    RESULT['native_hook_abi_cases']=cases
    # Actual downstream OEM min instructions remain effective.
    for native_cap in [0,7000,30000,65024]:
        m=fresh();valid_state(m,3000,0,2900,red=64);m.reg[9]=20000;m.poke(0xF177C,native_cap)
        m.run(0x595A8,stop=0x595B2);assert m.reg[9]==min(15000,native_cap)
        m=fresh();valid_state(m,3000,0,2900,red=64);m.reg[7]=20000;m.poke(0xF175E,native_cap)
        m.run(0x5B0BE,stop=0x5B0CA);assert m.reg[7]==min(15000,native_cap) and m.reg[8]==15000
    RESULT['native_minimum_windows']=8
    from test_can_diag import query
    m=fresh();m.poke(tq.BEFORE,20000);m.poke(tq.AFTER,17500)
    assert query(m,[0x22,0xf2,6])==bytes.fromhex('0762f2064e20445c')
    RESULT['native_sample_DID']='PASS'

def protocol_tests():
    for delay in [0,1,3]:
        m=fresh(delay);arm(m);stamp=(m.get(tq.RX_HI),m.get(tq.RX_LO));token=m.get(tq.TOKEN)
        # Duplicate/reordered/too-large sequence deltas cannot renew lease.
        for seq in [1,0,7]:
            send(m,tq.command(2,seq,32,20,1));assert (m.get(tq.RX_HI),m.get(tq.RX_LO))==stamp
        # Explicitly expire the lease: a valid next sequence cannot revive it.
        steps(m,30)
        send(m,tq.command(2,2,32,20,1));assert (m.get(tq.RX_HI),m.get(tq.RX_LO))==stamp
        steps(m,100);assert helper(m,'factor')[0]==0
        assert all(f['id'] in (0x5E0,0x5E1,0x5E2,0x5E9) for f in m.frames)
        for f in m.frames:
            if f['id']==0x5E9:
                d=bytes.fromhex(f['data']);assert tq.crc8(d[:7])==d[7] and not d[1]&0x70
    RESULT['IF1_async_delays']=[0,1,3]
    for change in [0,1,2,3,4,5,6,7]:
        m=fresh();bad=bytearray(tq.command(1,1,32,20,1));bad[change]^=1;send(m,bad);assert m.get(tq.MODE)==0
    for red,du,tk,op in [(0,20,1,1),(65,20,1,1),(32,0,1,1),(32,31,1,1),(32,20,0,1),(32,20,1,3)]:
        m=fresh();send(m,tq.command(op,1,red,du,tk));assert m.get(tq.MODE)==0
    for dlc in range(8):
        m=fresh();send(m,tq.command(1,1,32,20,1),dlc=dlc);assert m.get(tq.MODE)==0
    for ext,remote in [(True,False),(False,True)]:
        m=fresh();assert not m.inject(0x5E8,tq.command(1,1,32,20,1),extended=ext,remote=remote)
    RESULT['invalid_frame_cases']=24
    # Lost message object (overwrite before read) is rejected.
    m=fresh();m.inject(0x5E8,tq.command(1,1,32,20,1));m.inject(0x5E8,tq.command(1,2,32,20,1));steps(m,8);assert m.get(tq.MODE)==0;arm(m)
    # Refresh sequence wraps 255 -> 0, pulse deadline does not move.
    m=fresh();arm(m,seq=255);start=(m.get(tq.START_LO),m.get(tq.START_HI));send(m,tq.command(2,0,32,20,1));assert m.get(tq.SEQ)==0
    assert (m.get(tq.START_LO),m.get(tq.START_HI))==start
    # Cancellation cannot increase output or extend pulse; repeated cancel is idempotent.
    m=fresh();arm(m);before=helper(m,'factor')[0];send(m,tq.command(0,2,0,0,1));assert m.get(tq.MODE)==2
    duration=m.get(tq.DURATION);send(m,tq.command(0,3,0,0,1));assert m.get(tq.DURATION)==duration
    last=64
    for _ in range(100):
        steps(m);v,_=helper(m,'factor');assert v<=last;last=v
    assert last==0
    # Bus-off recovery clears pending intervention and reconfigures objects.
    m=fresh();arm(m);m.poke(0xEF02,128);steps(m);assert helper(m,'factor')[0]==0
    m.poke(0xEF02,0);steps(m,800);assert m.get(tq.READY)==2 and m.get(tq.MODE)==0
    # A new pulse needs the next token and the completed cooldown.
    m=fresh();arm(m);start=m.get(tq.START_LO);send(m,tq.command(1,2,32,20,2));assert m.get(tq.START_LO)==start
    steps(m,400);send(m,tq.command(1,2,32,20,5));assert m.get(tq.TOKEN)==1
    send(m,tq.command(1,2,32,20,2));assert m.get(tq.TOKEN)==2 and m.get(tq.MODE)==1
    send(m,tq.command(1,3,32,20,1));assert m.get(tq.TOKEN)==2
    # Hardware timer frozen: independent service-call watchdog latches off.
    m=fresh();arm(m);steps(m,110,delta=0);assert helper(m,'factor')[0]==0 and m.get(tq.MODE)==0
    RESULT['cancellation_restart_wrap_busoff']='PASS'

def cross_test():
    sys.path.insert(0,str(ROOT.parent/'stm32/tests'))
    from test_app import Model,d
    d.torque_request.argtypes=[C.c_uint8,C.c_uint16];d.torque_request.restype=C.c_int
    d.torque_confirmed.restype=C.c_int
    class TQ(C.Structure):
        _fields_=[(n,C.c_uint32) for n in ['started','due','last_status','last_progress','cooldown','stop_at']]+[(n,C.c_uint16) for n in ['token','ecu_token']]+[(n,C.c_uint8) for n in ['state','seq','ack_seq','reduction','duration','source','ecu_state','applied','seen','reason','have_status','have_ack','sent_start','cancel_count','fault','tx_op','cooldown_active','result','ever_applied','user_cancel']]
    state=TQ.in_dll(d,'torque')
    def run_case(drop_request=False,drop_status=False,replay_status=False,cancel_at=None,external_at=None,fail_tx=False,via_can=False,stm_time=1000,brake=False,brake_change_at=None):
        d.test_nv_empty();stm=Model();ecu=fresh();elapsed=0;stm.now=stm_time;cursor=len(ecu.frames);requests=[];values=[];confirmed=False;cached=None
        # P + IGN are required; exercise brake released and changes during the pulse.
        def step():
            nonlocal cursor,elapsed,confirmed,cached
            stm.now+=1;elapsed+=1;d.test_now(stm.now)
            bits=0x81|(0x40 if brake else 0)
            raw=(255^bits) if d.test_cfg(4) else bits
            d.app_sample(raw,(C.c_uint16*3)(2000,2000,2000),0,0,0)
            if elapsed%2==0:
                ecu.test_time+=156;clock(ecu,ecu.test_time);ecu.run()
                for f in ecu.frames[cursor:]:
                    ident=f['id'];payload=bytes.fromhex(f['data'])
                    if ident==0x5E9:
                        if replay_status and elapsed>140 and cached:payload=cached
                        if elapsed==140 or not cached:cached=payload
                        if drop_status and elapsed>140:continue
                    stm.recv(ident,payload)
                cursor=len(ecu.frames)
                # Native hook execution is distinct from CAN request acceptance.
                for name,target in [('hook_air',9),('hook_fast',7),('hook_load',9)]:
                    ecu.reg[target]=20000;ecu.poke(0xF177C,65024);ecu.poke(0xF175E,65024);ecu.run(LABELS[name])
                values.append(ecu.reg[9])
            old=d.test_count();d.app_tick(stm.now)
            if d.test_count()!=old:
                ident=d.test_id();payload=bytes(d.test_frame()[:8])
                if ident==0x5E8:
                    requests.append((elapsed,payload))
                    if not(drop_request and elapsed>140):ecu.inject(ident,payload)
                d.app_tx_done(0 if fail_tx and elapsed>140 else 1,stm.now)
            confirmed |= bool(d.torque_confirmed())
        for _ in range(100):step()
        if via_can:
            stm.recv(0x7e1,bytes.fromhex('063101f310201400'));step()
            assert state.state in (1,2),state.state
        else:assert d.torque_request(32,200)==1,(state.have_status,state.ecu_state,state.applied,stm.now)
        assert not d.torque_confirmed()
        assert d.torque_request(32,200)==0,'Do not restart/extend an active request'
        for _ in range(650):
            if brake_change_at==elapsed:brake=not brake
            if cancel_at==elapsed:d.torque_cancel()
            if external_at==elapsed:stm.recv(0x7E0,bytes.fromhex('02010c0000000000'))
            step()
            if brake_change_at is not None and elapsed==brake_change_at+1:assert state.state in (1,2) and not state.fault
        assert requests and requests[0][1][1]==1
        assert all(tq.crc8(p[:7])==p[7] for _,p in requests)
        assert helper(ecu,'factor')[0]==0,(drop_request,drop_status,state.state)
        assert state.state in (0,4),state.state
        assert any(v<20000 for v in values),requests
        assert confirmed or drop_status or fail_tx
        assert not d.torque_confirmed()
        if not any((drop_request,drop_status,replay_status,fail_tx,external_at,cancel_at)):
            assert state.result==5 and state.ever_applied and not state.fault
            assert ecu.get(tq.MODE)==0 and ecu.get(tq.REASON)!=6
        if cancel_at:assert state.result==6
        return dict(frames=len(requests),confirmed=confirmed,final_state=state.state,latched_result=state.result)
    RESULT['compiled_STM_to_ST10_cases']={
        'normal':run_case(), 'CAN_TCM_routine':run_case(via_can=True),
        'STM_ms_rollover':run_case(stm_time=0xFFFFFF40),'STM_long_idle':run_case(stm_time=0x90000000), 'lost_requests':run_case(drop_request=True),
        'lost_status':run_case(drop_status=True),'replayed_status':run_case(replay_status=True),
        'explicit_cancel':run_case(cancel_at=170),'external_scanner':run_case(external_at=170),
        'tx_failure':run_case(fail_tx=True),
        'brake_pressed':run_case(brake=True),
        'brake_press_during_pulse':run_case(brake_change_at=170),
        'brake_release_during_pulse':run_case(brake=True,brake_change_at=170)}

def main():
    unit_tests();protocol_tests();cross_test()
    RESULT.update(sha256=hashlib.sha256(IMAGE).hexdigest(),stm32_sha256=hashlib.sha256((ROOT.parent/'stm32'/('RB_TCM_C6_CAN_E4_GPIO_BENCH.bin' if os.environ.get('RB_DIRECT_INPUT_BENCH','0')=='1' else 'RB_TCM_C6_CAN_E4_TORQUE.bin')).read_bytes()).hexdigest(),status='PASS',hardware_tested=False,scope='emitted ST10 bytes + selected OEM windows + compiled production STM C')
    (ROOT.parent/'evidence/TORQUE_E4_TESTS.json').write_text(json.dumps(RESULT,indent=2)+'\n')
    print(json.dumps(RESULT,indent=2))
if __name__=='__main__':main()
