#!/usr/bin/env python3
"""Build the E4 torque variant separately; E3 remains reproducible rollback."""
import hashlib,json,struct
from pathlib import Path
import build_can_diag as diag
import torque_patch as tq

ROOT=Path(__file__).resolve().parents[1]
NAME='GW4G15_REV8_CAN_TORQUE_E4_BENCH.bin'

def build(base,donor):
    # Retain exact donor / PID / baseline anchors and original patch provenance.
    _,_,e3=diag.build(base,donor)
    a,code=diag.assemble(torque=True)
    t,tc=tq.assemble_torque(diag.BasicAsm,diag.far,diag.word)
    b=bytearray(base);patches=[]
    def patch(p,old,new,why):
        assert len(old)==len(new) and b[p:p+len(old)]==old,(hex(p),why)
        b[p:p+len(old)]=new
        patches.append(dict(file_offset=p,old=old.hex(),new=new.hex(),why=why))
    for x in e3['patches']:
        if x['file_offset']==diag.offset(diag.ORIGIN):continue
        patch(x['file_offset'],bytes.fromhex(x['old']),bytes.fromhex(x['new']),x['why'])
    patch(diag.offset(diag.ORIGIN),b'\xff'*len(code),code,'E3 diagnostics + serialized E4 torque service')
    patch(diag.offset(tq.ORIGIN),b'\xff'*len(tc),tc,'E4 checked request, hardware-clock lease, relative native arbitration hooks')
    for addr,old,label in tq.HOOKS:
        old=bytes.fromhex(old);new=diag.far(0xDA,t.labels[label])+b'\xcc\x00'*((len(old)-4)//2)
        patch(diag.offset(addr),old,new,label+'; replay displaced native instructions')
    # Explicitly reserve the upper 64 bytes of the native descending R0 stack.
    # All four reset initializers, four programming-mode R0 initializers, and
    # all three stack-monitor upper-bound constants and the OS configuration
    # reload are covered. RAM self-test
    # and zero fill still cover the full E000..E7FE range before the application.
    for p in (0x2B2,0x386,0x3B0,0x3E8):
        patch(p,bytes.fromhex('e6f0fee7'),bytes.fromhex('e6f0bee7'),'R0 stack top E7FE -> E7BE; reserve E7C0..E7FF')
    for p in (0x23E2,0x2436,0x24A8,0x2518):
        patch(p,bytes.fromhex('e6fcfce7'),bytes.fromhex('e6fcbce7'),'Programming-mode R0 top follows reservation')
    for p in (0x85BD6,0x85BEE,0x85BF8):
        old=base[p:p+4];assert old[-2:]==bytes.fromhex('fee7')
        patch(p,old,old[:2]+bytes.fromhex('bee7'),'Native software-stack usage monitor follows reserved top')
    # BOTH startup configurations (CPU 1BABE and 947A8) point to 1B416.
    # CPU 18034 loads config->table + 0x26 and writes it to [CP], i.e. R0.
    # Reset immediates alone therefore do NOT reserve the application stack.
    patch(0xB43C,bytes.fromhex('fee7'),bytes.fromhex('bee7'),
          'OS startup table R0 reload E7FE -> E7BE; preserve E4 private RAM')
    for _ in range(5):
        invalid=[x for x in diag.checks(b) if not x['valid']]
        if not invalid:break
        for x in invalid:struct.pack_into('<II',b,x['file_offset']+8,x['actual'],x['actual']^0xFFFFFFFF)
    assert all(x['valid'] for x in diag.checks(b))
    allowed=set()
    for x in patches:allowed.update(range(x['file_offset'],x['file_offset']+len(bytes.fromhex(x['new']))))
    for p in diag.CHECKS:allowed.update(range(p+8,p+16))
    changed={i for i,(v,w) in enumerate(zip(base,b)) if v!=w};assert changed<=allowed
    report=dict(base_sha256=diag.BASE_SHA,result_sha256=hashlib.sha256(b).hexdigest(),bytes=len(b),
        revision='E4M3_COMPLETED_REQUEST_LATCH_FIX',status='EXPERIMENTAL_BENCH_ONLY_NOT_PHYSICALLY_TESTED',
        patches=patches,changed_bytes=len(changed),checksum_records=diag.checks(b),
        diagnostic_code_bytes=len(code),torque_code_bytes=len(tc),labels=t.labels,
        torque_reduction=True,physical_torque_verified=False,units='relative reduction of native unsigned request, Q8; not Nm',
        max_reduction_q8=64,request_id=0x5E8,status_id=0x5E9,
        ram_reserved=[tq.RAM,tq.RAM_END],ram_bytes=64,native_R0_stack_top=0xE7BE,
        clock='read application T4 FE44 / E176 (vector 0x90 -> 0x018C60); require FF44[8:0]=0x046; no timer writes',
        assumed_cpu_hz=40000000,lease_ticks=tq.LEASE,max_pulse_ticks=tq.PULSE_MAX,
        original_KLine_callback_preserved=True,engine_calibration_bytes_changed=False,
        valve_control_changed=False,schematics_changed=False,
        supersedes_sha256='4b427be3ce5d70f04708c00ceec74100683c1042dce20beec80989c686a5b1b5',
        fix='Clear completed request atomically after checking its epoch; preserve E4M2 stack, clock and CAN fixes',
        reference='Native startup 018034..018062, configurations 01BABE / 0947A8, table 01B43C; T4 vector 000090 -> 018C60',
        hardware_relay_chatter_resolved=None,
        limits=['No physical ECU/vehicle or HIL execution; native output response and calibration require measurement',
                'Only the emitted patch plus selected native arbitration windows execute in the instruction model',
                '64 bytes are subtracted from the software stack; full native interrupt/call-depth margin remains a bench check',
                'A blank flash gap and reference scan do not prove absence of all computed references'])
    return bytes(b),a,t,report

def main():
    b,a,t,r=build((ROOT/'build_inputs/GW4G15_REV8_BASELINE_NO_LIN.bin').read_bytes(),(ROOT/'build_inputs/CHERY_REFERENCE_DO_NOT_FLASH.bin').read_bytes())
    out=ROOT/'firmware';out.mkdir(exist_ok=True)
    (out/NAME).write_bytes(b);(out/'PATCH_E4_REPORT.json').write_text(json.dumps(r,indent=2)+'\n')
    for name,asm in [('can_diag_e4.asm',a),('torque_e4.asm',t)]:
        lines=[]
        for pc,n,s in asm.rows:
            lines.extend(k+':' for k,v in asm.labels.items() if v==pc)
            lines.append(f'{pc:06X} file:{diag.offset(pc):06X} {b[diag.offset(pc):diag.offset(pc)+n].hex().upper():12} {s}')
        (out/name).write_text('\n'.join(lines)+'\n')
    print(json.dumps({k:r[k] for k in ('result_sha256','diagnostic_code_bytes','torque_code_bytes','changed_bytes')}))

if __name__=='__main__':main()
