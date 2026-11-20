"""Replay H03 writers with a RAM range guard; no patched BIN is exported."""
import argparse
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory

import check_h03_service_writes as writes
from check_h03_link import identify_h03, TARGET
from check_h03_service_isolation import storage_blocks
from lfj8_h03_layout import read_elf

HERE=Path(__file__).resolve().parent
PATCHES=((0x2924,0x2E7F4FF8,'rbm_h03_service_direct_hook',0xFF),
         (0x294C,0xFE0002F7,'rbm_h03_service_span_hook',0xFE),
         (0x2D1C,0x2E7F297F,'rbm_h03_service_copy_hook',0xFF))
SOURCES=('lfj8_h03_service_guard.c','lfj8_h03_service_guard.h',
         'h03_service_guard_hooks.S','h03_service_guard_fixture.c')


def scenarios(blocks):
    for case in writes.scenarios(blocks):
        if case.name=='stock_protected_prepared_copy':
            # The policy ALSO reserves the stock monitor range. This check
            # does not touch live monitor state even for a prepared request.
            yield replace(case,bytes_per_call=(0,))
        elif case.name=='checksum_delays_copy':
            # Rejected BEFORE checksum consumption, covered separately below.
            continue
        elif case.name=='no_pending_copy':
            yield case
        elif case.name=='control_two_adc0_passes':
            yield replace(case,bytes_per_call=(0,0))
        else:
            yield replace(case,bytes_per_call=tuple(0 for _ in case.bytes_per_call))
    start,end=blocks['control']
    for label,address in [('before',start-1),('after',end)]:
        yield writes.Case(label+'_direct',writes.DIRECT,address,1,(1,))
        yield writes.Case(label+'_deferred',writes.ADC0,address,1,(1,),close=True)
    yield writes.Case('crossing_direct',writes.DIRECT,start-1,2,(0,))
    yield writes.Case('allowed_257',writes.ADC0,end,257,(256,1),close=True)
    yield writes.Case('allowed_checksum',writes.ADC0,end,1,(0,),close=True,checksum=257)


def check(base,compiler,storage_report):
    identity=identify_h03(base)
    rom=base.read_bytes()
    blocks=storage_blocks(storage_report.read_bytes(),identity)
    if set(blocks)!={'control','communication','workspace'}:
        raise ValueError('Expected the three measured storage groups')
    for address,word,_,_ in PATCHES:
        if int.from_bytes(rom[address:address+4],'big')!=word:
            raise ValueError('H03 writer site changed')
    # Existing monitor protection is also applied to PREPARED copies, which
    # originally bypass it. No production range is guessed in this fixture.
    ranges=sorted([*blocks.values(),(0x808578,0x808DB4)])
    if any(end>start for (_,end),(start,_) in zip(ranges,ranges[1:])):
        raise ValueError('The proposed RAM overlaps live service state')
    with TemporaryDirectory(prefix='rbm-h03-service-guard-') as folder:
        work=Path(folder)
        def run(*args):
            return subprocess.run([str(x) for x in args],cwd=work,check=True,
                                  capture_output=True,timeout=40).stdout
        if run(compiler,'-dumpmachine').strip()!=b'm32r-elf':
            raise ValueError('Use a bare-metal M32R compiler')
        flags=[*TARGET,'-Os','-std=c11','-Wall','-Wextra','-Werror','-ffreestanding',
               '-fno-builtin','-ffunction-sections','-fdata-sections','-I',HERE]
        crt=run(compiler,*TARGET,'-print-file-name=crt0.o').decode().strip()
        run(compiler,*flags,'-nostartfiles',crt,HERE/SOURCES[0],HERE/SOURCES[3],
            '-Wl,--start-group','-lc','-lgloss','-lgcc','-Wl,--end-group','-o','policy.elf')
        policy_test=run(compiler.with_name('m32r-elf-run'+compiler.suffix),'policy.elf').decode().strip()
        if not policy_test.endswith('assertions PASS'):
            raise ValueError('Policy edge-case tests did not finish')
        policy='#include "lfj8_h03_service_guard.h"\nconst Lfj8H03ServicePolicy rbm_h03_service_policy = {'
        policy+=f'.count={len(ranges)}, .ranges={{'+','.join(f'{{{start:#x},{end:#x}}}' for start,end in ranges)+'}};\n'
        (work/'policy.c').write_text(policy,encoding='ascii')
        fixture=writes.FIXTURE.replace('ld24 lr,#fixture_done','ld24 lr,#fixture_capture_return')
        fixture=fixture.replace('    jmp r3','    ld24 r4,#fixture_call_psw\n    ld r4,@r4\n    mvtc r4,psw\n    jmp r3',1)
        fixture=fixture.replace('fixture_done:\n',
            'fixture_capture_return:\n    mvfc r7,psw\n    ld24 r6,#fixture_return_psw\n    st r7,@r6\nfixture_done:\n')
        fixture=fixture.replace('    .space 24','    .space 24\n    .global fixture_return_psw\nfixture_return_psw:\n    .space 4')
        fixture+=r'''
    .section .fixture_data,"aw",@progbits
    .global fixture_store_ie,fixture_store_count,fixture_call_psw
fixture_store_ie: .word 0
fixture_store_count: .word 0
fixture_call_psw: .word 0x41
    .section .fixture,"ax",@progbits
    .macro store_probe name,source,destination,resume
    .p2align 2
    .global \name
\name:
    push r5
    push r6
    push r7
    mvfc r7,psw
    push r7
    and3 r7,r7,#0x40
    ld24 r5,#fixture_store_ie
    ld r6,@r5
    or r6,r7
    st r6,@r5
    ld24 r5,#fixture_store_count
    ld r6,@r5
    addi r6,#1
    st r6,@r5
    pop r7
    mvtc r7,psw
    pop r7
    pop r6
    pop r5
    stb \source,@\destination
    bra.l \resume
    .endm
    store_probe fixture_direct_store,r1,r4,h03_direct_after_store
    store_probe fixture_copy_store,r3,r1,fixture_copy_increment
    .p2align 2
fixture_copy_increment:
    addi r2,#1
    bra.l h03_copy_after_store
'''
        fixture=fixture.replace('.section .oem,"ax",@progbits\n    .incbin "h03.dat"',
            '.section .oem_before,"ax",@progbits\n    .incbin "h03.dat",0,0x20000\n'
            '    .section .oem_after,"ax",@progbits\n    .incbin "h03.dat",0x30000,0x50000')
        (work/'fixture.S').write_text(fixture,encoding='ascii')
        (work/'fixture.ld').write_text('''ENTRY(_start)
SECTIONS {
 .oem_before 0 : { *(.oem_before) }
 .guard 0x20000 : { *(.text*) *(.rodata*) }
 .oem_after 0x30000 : { *(.oem_after) }
 .fixture 0x100000 : { *(.fixture) }
 .fixture_data : { *(.fixture_data) }
 /DISCARD/ : { *(.note*) *(.comment) }
}
ASSERT(SIZEOF(.guard) <= 0x10000, "Guard exceeds empty model window")
stock_selector = 0x003550;
stock_close = 0x002e80;
h03_service_direct_after_entry = 0x002928;
h03_service_stock_span_check = 0x003528;
h03_service_copy_after_entry = 0x002d20;
h03_direct_after_store = 0x00297c;
h03_copy_after_store = 0x002de4;
''',encoding='ascii')
        (work/'h03.dat').write_bytes(rom)
        def link():
            run(compiler,*flags,'-nostdlib','-Wl,-T,fixture.ld','fixture.S',
                HERE/'h03_service_guard_hooks.S',HERE/'lfj8_h03_service_guard.c','policy.c','-o','fixture.elf')
        link()
        elf=read_elf(work/'fixture.elf',2)
        patched=bytearray(rom)
        sites=[]
        for address,original,symbol,opcode in PATCHES:
            target=elf['symbols'][symbol]['address'];distance=(target-address)//4
            if target%4 or not -(1<<23)<=distance<(1<<23): raise ValueError('Invalid native branch')
            value=opcode<<24 | (distance&0xFFFFFF)
            patched[address:address+4]=value.to_bytes(4,'big')
            sites.append({'address':hex(address),'original':f'{original:08x}','model_patch':f'{value:08x}','target':hex(target)})
        instrumented=bytearray(patched)
        # Simulator-only probes preserve registers/PSW and execute the exact
        # displaced store bundle. First run the original stores without probes.
        for address,word,symbol in ((0x2978,0x2104F000,'fixture_direct_store'),
                                    (0x2DE0,0x23014201,'fixture_copy_store')):
            if int.from_bytes(rom[address:address+4],'big')!=word: raise ValueError('Store bundle changed')
            target=elf['symbols'][symbol]['address']
            instrumented[address:address+4]=(0xFF000000 | ((target-address)//4 & 0xFFFFFF)).to_bytes(4,'big')
        gdb=compiler.with_name('m32r-elf-gdb'+compiler.suffix)
        rows=[]
        for probes,variant in ((False,patched),(True,instrumented)):
            (work/'h03.dat').write_bytes(variant);link()
            for caller_psw in ((0,1,0x40,0x41) if probes else (0x41,)):
                for case in scenarios(blocks):
                    for lockout in (False,True):
                        seen=[]
                        def audited_run(*args):
                            if Path(args[0])==gdb:
                                script=work/'probe.gdb';s=script.read_text('ascii')
                                s=s.replace(writes.report_line('READY'),writes.report_line('READY')+
                                    f'\nset {{unsigned int}}&fixture_call_psw = {caller_psw:#x}')
                                for index in range(len(case.bytes_per_call)):
                                    marker=writes.report_line(f'STORE_{index}')
                                    s=s.replace(marker,marker+'\nprintf "GUARD_OBS %x %x %x\\n", '
                                        '*(unsigned int*)&fixture_return_psw, *(unsigned int*)&fixture_store_ie, *(unsigned int*)&fixture_store_count')
                                script.write_text(s,encoding='ascii')
                            output=run(*args)
                            if Path(args[0])==gdb:
                                samples=re.findall(rb'GUARD_OBS ([0-9a-f]+) ([0-9a-f]+) ([0-9a-f]+)',output)
                                if len(samples)!=len(case.bytes_per_call): raise ValueError('Missing native guard observations')
                                written=0
                                for index,(value,ie,count) in enumerate(samples):
                                    written+=case.bytes_per_call[index]
                                    if probes and (int(ie,16) or int(count,16)!=written):
                                        raise ValueError('Store count or interrupt mask differs from expected writes')
                                    pc=writes.observation(output,f'STORE_{index}')[0]
                                    if pc not in (elf['symbols']['fixture_done']['address'],writes.COPY_COMPLETE):
                                        raise ValueError('Writer did not reach its exact expected stop')
                                    if pc==elf['symbols']['fixture_done']['address']:
                                        if int(value,16)&0x40 != caller_psw&0x40:
                                            raise ValueError(f'{case.name}: caller IRQ enable not restored')
                                        if case.entry==writes.DIRECT and int(value,16)!=caller_psw:
                                            raise ValueError('Direct writer changed the caller PSW')
                                seen.append(written)
                            return output
                        row=writes.run_case(audited_run,work,gdb,case,lockout)
                        row.update(store_probes=probes,caller_psw=caller_psw,
                                   stores_observed_with_ie_masked=sum(seen) if probes else None)
                        rows.append(row)
        final=read_elf(work/'fixture.elf',2)
        guard=next(s for s in final['sections'] if s['name']=='.guard')
    return {'status':'PASS_SELECTED_WRITERS_MODEL_ONLY','base':identity,
            'policy_ranges':[[hex(a),hex(b)] for a,b in ranges],'native_sites':sites,
            'guard_with_fixture_policy_bytes':guard['size'],'new_mutable_state_bytes':0,
            'policy_test':policy_test,'native_cases':rows,
            'simulation_only_instrumentation':['Relocated 2978 and 2DE0 store bundles capture PSW/IE and count stores; registers and PSW restored'],
            'input_sha256_lf':{name:sha256((HERE/name).read_bytes().replace(b'\r\n',b'\n')).hexdigest() for name in SOURCES},
            'limits':['Three hooks below 0x8000; programmer support not established',
                      'Held copy preserves pending state and returns busy; lifecycle cancellation/recovery is still required',
                      'Final RAM/stack ranges and all write paths still require qualification',
                      'SBI/DMA, Virtual Flash residency and interrupt latency not proven',
                      'Model code at 0x20000 is isolated; final combined placement is not implemented'],
            'hardware_tested':False,'flashable_image':None}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('base','gcc','storage-report','out'): parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    if args.out.suffix.lower()!='.json' or any(args.out.resolve()==p.resolve() for p in (args.base,args.gcc,args.storage_report)):
        parser.error('Use a separate JSON report')
    if args.out.exists():
        if any(args.out.samefile(p) for p in (args.base,args.gcc,args.storage_report)):
            parser.error('The report must not alias an input')
        args.out.unlink()
    try:
        report=check(args.base,args.gcc.resolve(),args.storage_report)
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({k:report[k] for k in ('status','guard_with_fixture_policy_bytes','new_mutable_state_bytes','policy_test','flashable_image')}))
        print('native cases:',len(report['native_cases']))
    except (OSError,ValueError,subprocess.SubprocessError) as error:
        detail=getattr(error,'stderr',None) or str(error)
        parser.exit(1,(detail.decode(errors='replace') if isinstance(detail,bytes) else detail)+'\n')


if __name__=='__main__': main()
