#!/usr/bin/env python3
"""Execute candidate bytes; check completion, stale-reader race and native startup."""
from pathlib import Path
import hashlib,json
import test_torque as q
import torque_patch as tq
from build_e4 import ROOT,build
from build_can_diag import offset,checks
from test_e4m2 import NativeAddressProbe

def main():
    image=q.IMAGE
    baseline=(ROOT.parent/'rollback/GW4G15_REV8_E4M2.bin').read_bytes()
    assert hashlib.sha256(baseline).hexdigest()=='4b427be3ce5d70f04708c00ceec74100683c1042dce20beec80989c686a5b1b5'
    rebuilt,*_=build((ROOT/'build_inputs/GW4G15_REV8_BASELINE_NO_LIN.bin').read_bytes(),(ROOT/'build_inputs/CHERY_REFERENCE_DO_NOT_FLASH.bin').read_bytes())
    assert image==rebuilt and all(r['valid'] for r in checks(image))
    report=json.loads((ROOT/'firmware/PATCH_E4_REPORT.json').read_text())
    allowed=set(range(offset(tq.ORIGIN),offset(tq.ORIGIN)+report['torque_code_bytes']))
    for addr,old,_ in tq.HOOKS:allowed.update(range(offset(addr),offset(addr)+len(bytes.fromhex(old))))
    ids=[p+3 for p in range(offset(0x1E200),offset(0x1E200)+7652,2) if baseline[p:p+4]==bytes.fromhex('e6f4010a')]
    assert len(ids)==1 and image[ids[0]]==11;allowed.update(ids)
    for r in checks(image):allowed.update(range(r['file_offset']+8,r['file_offset']+16))
    diff={i for i,(a,b) in enumerate(zip(baseline,image)) if a!=b};assert len(image)==len(baseline) and diff<=allowed
    completion={}
    for case in ('scheduled_cancel','natural_expiry','lost_refresh'):
        m=q.fresh();values=[];first_zero=None
        for ms in range(0,1502,2):
            if ms==0 or (case!='lost_refresh' and ms<=180 and ms%20==0) or (case=='scheduled_cancel' and ms in (200,220,240)):
                op=1 if ms==0 else 0 if ms>=200 else 2
                seq=ms//20+1
                assert m.inject(0x5e8,tq.command(op,seq,32 if op else 0,20 if op else 0,1))
            q.steps(m);value,state=q.helper(m,'factor');values.append(value)
            assert m.get(tq.REASON)!=6,(case,ms)
            if max(values)>0 and not value and first_zero is None:first_zero=ms
            if first_zero is not None:assert value==0 and m.get(tq.MODE)==0,(case,ms)
        assert max(values)>0 and first_zero is not None and first_zero<350
        assert m.get(tq.CALL_AGE)<100
        q.arm(m,token=2);assert m.get(tq.MODE)==1
        completion[case]=dict(first_zero_model_ms=first_zero,new_token_accepted=True)
    # An old factor reader may complete after a new request publication. Its
    # epoch must fail the atomic compare, leaving that new request active.
    m=q.fresh();q.valid_state(m,40000,0,40000,red=32,duration=15620);old=m.get(tq.EPOCH)
    def publish_new(machine,pc):
        if pc==q.LABELS['factor_expired']:
            machine.poke(tq.EPOCH,old+1);machine.poke(tq.MODE,1);machine.instruction_hook=None
    m.instruction_hook=publish_new
    assert q.helper(m,'factor')==(0,0) and m.get(tq.MODE)==1 and m.get(tq.EPOCH)==old+1
    # Interrupt injection is deferred across all four guarded instructions.
    m=q.fresh();q.valid_state(m,40000,0,40000,red=32,duration=15620);points=[]
    m.instruction_hook=lambda machine,pc:points.append(pc)
    assert q.helper(m,'factor')==(0,4) and m.get(tq.MODE)==0
    start=q.LABELS['factor_expired'];assert not any(start<pc<start+16 for pc in points)
    native=[]
    for caller,call_pc in ((0x1BC4A,0x1BC52),(0x1BAA4,0x1BAAC)):
        for cp in (0xF800,0xFC00):
            p=NativeAddressProbe(image,cp);p.set(0,int.from_bytes(image[0x2b4:0x2b6],'little'));p.run(caller,call_pc);p.run(0x18034,0x18062)
            assert p.r(0)==0xe7be;p.run(0x18220,0x1822c)
            writes=[x[2] for x in p.trace if x[1]=='stack_write'];assert not any(0xe7c0<=a<0xe800 for a in writes)
            native.append(dict(caller=hex(caller),cp=hex(cp),reserved_RAM_untouched=True))
    result=dict(status='PASS',version='E4M3',sha256=hashlib.sha256(image).hexdigest(),changed_bytes_vs_E4M2=len(diff),
        unchanged_outside_torque_hooks_build_id_and_checksums=True,checksum_records=51,reproducible_build=True,
        completion=completion,stale_reader_does_not_clear_new_request=True,atomic_four_instruction_window_checked=True,
        native_startup=native,hardware_tested=False,limits=['Instruction model and selected native windows only; no full ECU, peripheral or relay simulation'])
    out=ROOT.parent/'evidence/E4M3';out.mkdir(exist_ok=True)
    (out/'COMPLETION_REGRESSION.json').write_bytes((json.dumps(result,indent=2)+'\n').encode())
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
