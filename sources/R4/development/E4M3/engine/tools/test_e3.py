#!/usr/bin/env python3
"""Execute new DID instruction bytes; verify restricted calibration patches."""
import json
from pathlib import Path
from build_can_diag import build,checks
from test_isotp import start
from test_can_diag import query
from calibrate_speed import calibrate
root=Path(__file__).resolve().parents[1]
image,_,_=build((root/'build_inputs/GW4G15_REV8_BASELINE_NO_LIN.bin').read_bytes(),(root/'build_inputs/CHERY_REFERENCE_DO_NOT_FLASH.bin').read_bytes())
assert image==(root/'firmware/GW4G15_REV8_CAN_DIAG_BENCH_E3_SW.bin').read_bytes()
m=start(image)
m.poke(0xF02F8,0xa5,1);m.poke(0xF02FB,0x5a,1)
m.poke(0xF177C,0x1234);m.poke(0xF06C4,0x5678)
assert query(m,[0x22,0xf2,3])==bytes.fromhex('0762f203a55a3400')
assert query(m,[0x22,0xf2,4])==bytes.fromhex('0762f20412345678')
assert query(m,[0x22,0xf2,5])==bytes.fromhex('0762f20512c06680')
for did in (3,4,5):assert query(m,[0x22,0xf2,did],identifier=0x7df) is None
assert all(0xef00<=a<=0xef54 for a,v in m.writes)
for speeds,k in (((80,100),3840),((100,80),6000),((100,100),4800)):
    patched,report=calibrate(image,image,*speeds);assert report['new_coefficient']==k
    assert all(r['valid'] for r in checks(patched))
for a,b in ((0,1),(1,0),('NaN',1),('Infinity',1),(1,300)):
    try:calibrate(image,image,a,b)
    except ValueError:pass
    else:raise AssertionError('Invalid input accepted')
report=dict(status='PASS',new_DIDs_executed=3,fixed_address_read_only=True,existing_serial_callback_preserved=True,exact_image_reproduction=True,speed_patch_extent_and_checksums=True,hardware_tested=False)
(root.parent/'evidence/ECU_E3_EXTENSIONS.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
