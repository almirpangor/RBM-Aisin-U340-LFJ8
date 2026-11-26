#!/usr/bin/env python3
"""Verify package SHA256 values, rebuild the exact BIN, optionally compare MICRO readback."""
import argparse,hashlib,json
from pathlib import Path
from build_e4 import build,NAME

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--readback',type=Path);a=p.parse_args()
    root=Path(__file__).resolve().parents[1]
    expected=json.loads((root/'SHA256.json').read_text())
    for name,digest in expected.items():
        path=root/name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
            raise SystemExit('HASH MISMATCH: '+name)
    image=root/'firmware'/NAME
    rebuilt,_,_,_=build((root/'build_inputs/GW4G15_REV8_BASELINE_NO_LIN.bin').read_bytes(),
                      (root/'build_inputs/CHERY_REFERENCE_DO_NOT_FLASH.bin').read_bytes())
    assert rebuilt==image.read_bytes(),'REBUILD MISMATCH'
    print('Package hashes and reproducible BIN: PASS')
    if a.readback:
        readback=a.readback.read_bytes()
        if readback!=rebuilt:
            raise SystemExit('READBACK DIFFERS: compare file format, size and programmer log; do not treat as a verified write.')
        print('MICRO readback: exact match to E4M3')

if __name__=='__main__':main()
