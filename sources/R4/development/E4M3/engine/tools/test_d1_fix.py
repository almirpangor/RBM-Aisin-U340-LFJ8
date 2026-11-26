#!/usr/bin/env python3
"""Reproduce Bench D guard failure and verify D1 from emitted instructions."""
import argparse,hashlib,json,struct
from pathlib import Path
from test_isotp import start,slots,exchange,expect
from test_can_diag import query

def main(old,new,base,out):
    old=Path(old).read_bytes();new=Path(new).read_bytes();base=Path(base).read_bytes()
    # Native operation marker: queued work sets 5A5A; both workers clear to zero.
    anchors={0x2CC28:'e6fc5a5af6fc5c8b',0x2D244:'f2fc5c8b46fc5a5a',
             0x2D2F8:'f68e5c8b',0x2D30A:'f2fc5c8b46fc5a5a',0x2D3BE:'f68e5c8b'}
    for cpu,h in anchors.items():
        raw=bytes.fromhex(h);assert base[cpu-0x10000:cpu-0x10000+len(raw)]==raw
    events=[e for e in range(1,105) if struct.unpack_from('<H',new,0xAABDA+8*e)[0] not in (0,65535)][:10]
    records=[(e,11,1,8) for e in events]
    results=[]
    for sid in (3,7):
        for n in (0,1,2,3,10):
            m=start(old);slots(m,records[:n]);bad,_=exchange(m,sid)
            assert bad==bytes([0x7F,sid,0x22])
            m=start(new);slots(m,records[:n]);good,frames=exchange(m,sid,st=5)
            assert good==expect(new,records[:n],sid)
            results.append({'service':f'{sid:02X}','slot_count':n,'old_reply':bad.hex(' '),
                            'new_reply':good.hex(' '),'new_frames':[f['data'] for f in frames]})
    rejects=0
    for marker in (0x5A5A,0xFFFF,1):
        for request in ([3],[7],[0x22,0xF2,0x10]):
            m=start(new);slots(m,records);m.poke(0xF0B5C,marker)
            assert query(m,request)==bytes([3,0x7F,request[0],0x22,0,0,0,0])
            rejects+=1
    # Debug reads remain available on bad guards and preserve byte order.
    m=start(new);slots(m,records);m.poke(0xF0B56,0x1234);m.poke(0xF0B5C,0xA1B2)
    m.poke(0xF2859,0xC7,1);m.poke(0xF40BF,0x96,1);m.poke(0xF0B60,0x5678)
    assert query(m,[0x22,0xF2,1])==bytes.fromhex('0762F2011234A1B2')
    assert query(m,[0x22,0xF2,2])==bytes.fromhex('0762F202C7965678')
    assert query(m,[0x22,0xF2,1],identifier=0x7DF) is None
    assert query(m,[0x22,0xF2,2],identifier=0x7DF) is None
    result={'status':'PASS_EMITTED_BYTES_MODEL','D_sha256':hashlib.sha256(old).hexdigest(),
            'D1_sha256':hashlib.sha256(new).hexdigest(),'native_byte_anchors':{f'{a:06X}':v for a,v in anchors.items()},
            'old_failure_new_success_cases':results,'pending_or_invalid_marker_rejections':rejects,
            'raw_state_DIDs_available_despite_failed_guards_and_byte_order_checked':True,
            'functional_custom_DIDs_silent':True,'physical_D1_ECU_test':False,
            'limitation':'The user trace did not read F0B5C; actual hardware guard values remain to be measured.'}
    Path(out).write_text(json.dumps(result,indent=2)+'\n')
    print('Native anchors, old-D failure reproduction, D1 SF/ISO-TP responses, busy guards, raw state DIDs: PASS')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('old');p.add_argument('new');p.add_argument('base');p.add_argument('--out',required=True)
    a=p.parse_args();main(a.old,a.new,a.base,a.out)
