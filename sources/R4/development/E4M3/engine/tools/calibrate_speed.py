#!/usr/bin/env python3
"""Exact E3 image speed-scale calibration from a paired measurement.

Output is a separate bench image. This does not enable the native VMAX limiter,
modify brake inputs or assert the physical sensor timebase/pulses per km.
"""
import argparse,hashlib,json,struct
from decimal import Decimal,ROUND_HALF_UP
from pathlib import Path
from build_can_diag import build,checks,CHECKS,offset

def calibrate(image,expected,indicated,reference):
    if image!=expected:raise ValueError('Only the reproduced, unmodified E3 input is accepted')
    indicated,reference=Decimal(str(indicated)),Decimal(str(reference))
    if not indicated.is_finite() or not reference.is_finite() or not Decimal('.1')<=indicated<=300 or not Decimal('.1')<=reference<=300:raise ValueError('Measured speeds must be finite, 0.1..300 km/h')
    old=struct.unpack_from('<H',image,offset(0xBA964))[0]
    new=int((Decimal(old)*indicated/reference).to_integral_value(rounding=ROUND_HALF_UP))
    if not 1<=new<=65535 or (281250000//new)*255*128>0xffffffff:raise ValueError('Coefficient outside the audited uint32 arithmetic domain')
    result=bytearray(image);struct.pack_into('<H',result,offset(0xBA964),new)
    for _ in range(5):
        bad=[r for r in checks(result) if not r['valid']]
        if not bad:break
        for r in bad:struct.pack_into('<II',result,r['file_offset']+8,r['actual'],r['actual']^0xffffffff)
    if not all(r['valid'] for r in checks(result)):raise ValueError('Checksum repair did not converge')
    allowed={offset(0xBA964),offset(0xBA964)+1}
    for p in CHECKS:allowed.update(range(p+8,p+16))
    if any(i not in allowed and a!=b for i,(a,b) in enumerate(zip(image,result))):raise ValueError('Unexpected patch extent')
    return bytes(result),dict(old_coefficient=old,new_coefficient=new,indicated_kmh=str(indicated),reference_kmh=str(reference),formula='K_new = round(K_old * indicated / reference)',input_sha256=hashlib.sha256(image).hexdigest(),output_sha256=hashlib.sha256(result).hexdigest(),checksum_records=len(CHECKS),hardware_tested=False,vmax_modified=False)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('image',type=Path);p.add_argument('--indicated',required=True);p.add_argument('--reference',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    root=Path(__file__).resolve().parents[1]
    expected,_,_=build((root/'build_inputs/GW4G15_REV8_BASELINE_NO_LIN.bin').read_bytes(),(root/'build_inputs/CHERY_REFERENCE_DO_NOT_FLASH.bin').read_bytes())
    image,report=calibrate(a.image.read_bytes(),expected,a.indicated,a.reference)
    sidecar=a.output.with_suffix(a.output.suffix+'.json')
    if a.output.exists() or sidecar.exists():raise SystemExit('Output or report already exists')
    with a.output.open('xb') as f:f.write(image)
    sidecar.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
