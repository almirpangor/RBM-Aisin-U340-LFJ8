#!/usr/bin/env python3
"""Integrate the actual host ISO-TP parser/FC with actual emitted ECU bytes."""
import argparse,hashlib,json,struct,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'client'))
from audit_machine import Machine
from test_isotp import start,slots
from test_can_diag import query
from rb_can_diag import Client,IsoReceiver,decode_sf,parse_elm,DiagnosticError

def main(image,out):
    b=Path(image).read_bytes();m=start(b);events=[e for e in range(1,105) if struct.unpack_from('<H',b,0xAABDA+8*e)[0] not in (0,65535)][:10]
    slots(m,[(e,11,1,8) for e in events]);m.poke(0xF40BF,1,1)
    for i,v in enumerate([0x8A,7,0x65,4]):m.poke(0xF40BB+i,v,1)
    class Transport:
        def exchange(self,request):
            rx=IsoReceiver(request);seen=len(m.frames)
            assert m.inject(0x7E0,bytes([len(request)])+request+bytes(7-len(request)))
            for _ in range(750):
                m.run()
                for f in m.frames[seen:]:
                    if f['id']!=0x7E8:continue
                    r=rx.feed(bytes.fromhex(f['data']))
                    if rx.needs_fc:assert m.inject(0x7E0,bytes.fromhex('3000050000000000'))
                    if r is not None:return r
                seen=len(m.frames)
            raise DiagnosticError('Model timeout')
    c=Client(Transport(),interval=0)
    result={'info':c.info(),'state':c.state(),'live':c.live(),'monitors':c.monitors(),'RB_DTC':c.dtc(),
            'confirmed':c.standard_dtc(3),'pending':c.standard_dtc(7)}
    assert result['info']['build']==('BENCH_E4M3' if m.torque_enabled else 'BENCH_E3_SW') and result['monitors']['MIL_on']
    assert result['state']['catalog_pointer']=='2BDA' and result['state']['pending_operation_marker']=='0000'
    assert result['state']['native_slot_count']==10 and result['state']['PID01_valid_byte']==1
    assert result['confirmed']['codes']==result['pending']['codes']==[r['code'] for r in result['RB_DTC']['records']]
    assert len(result['confirmed']['codes'])==10
    # Real bytes from the model are also parsed as ELM ATH1 output.
    n=len(m.frames);want=c.standard_dtc(3)['raw_payload']
    raw=[f['data'] for f in m.frames[n:] if f['id']==0x7E8]
    text='SEARCHING...\r'+'\r'.join('7E8 '+bytes.fromhex(f).hex(' ') for f in raw)+'\r>'
    assert parse_elm(text,b'\x03').hex(' ').upper()==want
    for s in ('7E8 04 41 0C 0C 80 00 00 00\r>', 'SEARCHING...\n7E804410C0C80000000\n>'):
        assert parse_elm(s,bytes.fromhex('010C'))==bytes.fromhex('410C0C80')
    for s in ('NO DATA\n>','7E8 03 41 05 70 00 00 00 00\n>','7E8 '+raw[0]+'\n7E8 '+raw[2]+'\n>'):
        try:parse_elm(s,b'\x03' if raw[0] in s else bytes.fromhex('010C'))
        except DiagnosticError:pass
        else:raise AssertionError('Bad/truncated response accepted')
    # Partial/malformed response is never decoded into a valid empty DTC list.
    for payload in (b'\x43',b'\x43\x01',b'\x43\x01\0\0',b'\x43\x01\xff\xff',b'\x43\x00\x01\x23'):
        class Bad:
            def exchange(self,request):return payload
        try:Client(Bad(),0).standard_dtc(3)
        except DiagnosticError:pass
        else:raise AssertionError(payload)
    m.poke(0xF0B5C,0x5A5A)
    assert c.state()['pending_operation_marker']=='5A5A'
    for operation in (c.dtc,lambda:c.standard_dtc(3)):
        try:operation()
        except DiagnosticError:pass
        else:raise AssertionError('Unavailable DTC list presented as valid')
    result.update(status='PASS_HOST_ECU_MODEL_INTEGRATION_AND_ELM_PARSER',sha256=hashlib.sha256(b).hexdigest(),physical_adapter_test=False)
    Path(out).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print('Host/ECU model integration, ELM parser, error handling: PASS')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('image');p.add_argument('--out',required=True)
    a=p.parse_args();main(a.image,a.out)
