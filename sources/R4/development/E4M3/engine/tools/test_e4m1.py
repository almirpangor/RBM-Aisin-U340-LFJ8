#!/usr/bin/env python3
"""E4 CAN access-width regression; this does not emulate ECU boot or relays."""
import hashlib
import json
import random
from pathlib import Path
from audit_machine import Machine, seed
from build_e4 import ROOT, NAME, build
from build_can_diag import checks, offset, BasicAsm, far, word, STATE
import torque_patch as tq


def main():
    old=(ROOT/'build_inputs/E4_RELAY_FAULT_REPRO_ONLY_DO_NOT_FLASH.bin').read_bytes()
    e2=(ROOT.parent/'rollback/GW4G15_REV8_CAN_DIAG_BENCH_E1.bin').read_bytes()
    fixed=(ROOT/'firmware'/NAME).read_bytes()
    assert hashlib.sha256(old).hexdigest()=='82af8f276c66bb51bbefac2e2ddee61400682ad89a2a5fce35b6e29f93305a5e'
    assert hashlib.sha256(e2).hexdigest()=='62b6d7a5f168a1876abfbf1e2ffb65e94fb459259f4fdb33f205b252abac8051'
    m=Machine(old);seed(m,rpm4=0)
    try:
        for _ in range(500):m.run()
    except AssertionError as exc:
        assert exc.args[0]==('Unsupported CAN access','0xef1e',1,'0x64f94'),exc
        assert m.tick==44
        old_failure={'service_invocation':m.tick,'cpu_pc':'0x064F94','address':'0xEF1E',
                     'access_bytes':1,'commands_sent':0,'engine_rpm':0}
    else:raise AssertionError('Original E4 must reproduce unsupported access')

    # Change confined to replacement code, hook target relocations and native
    # checksum values; E4M2 also patches the missed OS R0 table reload.
    report=json.loads((ROOT/'firmware/PATCH_E4_REPORT.json').read_text())
    allowed=set()
    for start,size in [(0x1E200,report['diagnostic_code_bytes']),
                       (0x64800,report['torque_code_bytes'])]:
        allowed.update(range(offset(start),offset(start)+size))
    for addr,raw,_ in tq.HOOKS:allowed.update(range(offset(addr),offset(addr)+len(bytes.fromhex(raw))))
    for record in checks(fixed):allowed.update(range(record['file_offset']+8,record['file_offset']+16))
    allowed.update(range(0xB43C,0xB43E))
    diff={i for i,(x,y) in enumerate(zip(old,fixed)) if x!=y}
    assert diff<=allowed
    assert all(c['valid'] for c in checks(fixed))
    rebuilt,_,_,_=build((ROOT/'build_inputs/GW4G15_REV8_BASELINE_NO_LIN.bin').read_bytes(),
                        (ROOT/'build_inputs/CHERY_REFERENCE_DO_NOT_FLASH.bin').read_bytes())
    assert fixed==rebuilt

    # No request is injected: simulate periodic service at key-on, idle and
    # running RPM, with and without ACK and with asynchronous IF1 transfers.
    runs=[]
    for name,image in [('working_E2',e2),('E4M2',fixed)]:
        for rpm4 in (0,3200,8000):
            for ack in (False,True):
                for startup_delay,delay in ((0,0),(1,3),(3,3)):
                    m=Machine(image);seed(m,rpm4=rpm4);m.ack=ack;m.transfer_delay=startup_delay
                    for i in range(3000):
                        if i==200:m.transfer_delay=delay
                        m.run()
                    if startup_delay==3:
                        # 38 objects x 3 invocations exceeds the inherited
                        # 100-call initialization timeout in both E2 and E4.
                        assert m.get(STATE)==0xFF and not m.frames
                        assert m.get(0xEF00)&1
                        assert m.get(tq.MODE)==0
                    elif name=='E4M2':
                        assert m.get(tq.READY)==2 and m.get(tq.MODE)==0 and m.get(tq.SEEN)==0
                        status=[bytes.fromhex(f['data']) for f in m.frames if f['id']==0x5E9]
                        if ack:assert status
                        assert all(d[0]==0xA4 and d[1]==0 and d[3]==0 and tq.crc8(d[:7])==d[7] for d in status)
                    runs.append(dict(image=name,rpm=rpm4//4,ack=ack,
                        startup_IF1_delay=startup_delay,IF1_delay=delay,
                        CAN_init_timeout_expected=startup_delay==3,
                        service_invocations=3000,max_instructions=m.max_insns,
                        max_modeled_stack_bytes=m.max_stack))

    # No-command native hook results must match the actual displaced OEM
    # instructions, even before the CAN/torque state has been initialized.
    asm,_=tq.assemble_torque(BasicAsm,far,word);rng=random.Random(0xE4A1);abi=0
    for addr,raw,label in tq.HOOKS:
        for initialized in (False,True):
            for _ in range(50):
                regs=[rng.randrange(65536) for _ in range(16)];psw=rng.randrange(65536)
                native=Machine(e2);patched=Machine(fixed)
                for q in (native,patched):
                    q.reg=regs[:];q.psw=psw;q.poke(0xF177C,30000);q.poke(0xF175E,32000)
                if initialized:patched.poke(tq.MAGIC,tq.TAG)
                native.run(addr,stop=addr+len(bytes.fromhex(raw)))
                patched.run(asm.labels[label])
                assert (native.reg,native.psw)==(patched.reg,patched.psw),(label,initialized)
                assert not patched.stack and not patched.return_stack
                abi+=1
    result=dict(status='PASS',sha256=hashlib.sha256(fixed).hexdigest(),
                original_E4_reproduced=old_failure,periodic_service_cases=runs,
                idle_native_hook_equivalence_cases=abi,
                changed_bytes_vs_old_E4=len(diff),known_checksum_records_valid=51,
                reproducible_build=True,hardware_tested=False,relay_chatter_resolved=None,
                limitations=['Only emitted patch and selected OEM instructions execute; full startup, IRQs and relay outputs are not emulated',
                             'Access-width rejection checks the manual; it does not assert a specific hardware trap/reset response'])
    out=ROOT.parent/'evidence/E4M2';out.mkdir(exist_ok=True)
    (out/'KEYON_REGRESSION.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='periodic_service_cases'},indent=2))
    print('Periodic service: 36 cases x 3000 invocations; no torque request: PASS')


if __name__=='__main__':main()
