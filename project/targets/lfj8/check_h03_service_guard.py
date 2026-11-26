"""Replay H03 writers with a RAM range guard; no patched BIN is exported."""
import argparse
from dataclasses import dataclass, replace
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
import lfj8_h03_service_placement as service

HERE=Path(__file__).resolve().parent
CLOSE_STORE = service.WRITER_SITES[-1].address
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


@dataclass(frozen=True)
class CloseCase:
    name: str
    address: int
    total: int
    remaining: int
    checksum: int = 0
    active: bool = True
    held: bool = False
    canceled: bool = False
    completes: bool = False


def close_cases(blocks):
    start, end = blocks["control"]
    return (
        CloseCase("held_then_closed", start, 257, 257, held=True, canceled=True),
        CloseCase("partial_original_overlap", end - 1, 257, 1, held=True, canceled=True),
        CloseCase("bad_remaining", end, 1, 2, held=True, canceled=True),
        CloseCase("independent_checksum", start, 1, 1, checksum=257, held=True, canceled=True),
        CloseCase("accepted_allowed", end, 1, 1, completes=True),
        CloseCase("inactive_close", start, 1, 1, active=False, held=True),
        CloseCase("idle_previous_count", start, 257, 0),
    )


def close_state_line(name):
    address = writes.MONITOR
    return (f'printf "{name} %x %x %x %x %x %x %x %x %x %x %x\\n", $pc, $r0, *(unsigned int*)&fixture_close_psw, '
            f"*(unsigned char*){address + 8:#x}, *(unsigned char*){address + 9:#x}, "
            f"*(unsigned int*){address + 0x830:#x}, *(unsigned int*){address + 0x834:#x}, "
            f"*(unsigned int*){address + 0x82c:#x}, *(unsigned int*){address + 20:#x}, "
            f"*(unsigned short*){address + 4:#x}, *(unsigned int*){address:#x}")


def check_close(run, work, debugger, symbols, case, psw, lockout, *, lockout_installed=False):
    monitor, source = writes.MONITOR, writes.SOURCE
    width = max(case.total, case.remaining, 1)
    sentinel = bytes([writes.SENTINEL]) * (width + 2)
    payload = bytes(0x80 | (i & 0x3f) for i in range(max(width, case.checksum)))
    (work / "cancel-sentinel.dat").write_bytes(sentinel)
    (work / "cancel-payload.dat").write_bytes(payload)
    flags = 0x20 if case.active else 0x10
    reply = 0x12345678
    seed = (
        ("unsigned int", 0x809f9c, 0x809f9c),
        ("unsigned short", writes.VIRTUAL_SELECT, writes.BANK),
        ("unsigned char", writes.FCNT1, 1),
        ("unsigned short", writes.FESBANK1, 0x8000 | writes.BANK),
        ("unsigned char", monitor + 8, flags),
        ("unsigned char", monitor + 9, 0x80),
        ("unsigned int", monitor, reply),
        ("unsigned int", monitor + 12, source),
        ("unsigned int", monitor + 16, case.address),
        ("unsigned int", monitor + 20, source),
        ("unsigned int", writes.CHECKSUM_REMAINING, case.checksum),
        ("unsigned int", writes.COPY_REMAINING, case.remaining),
        ("unsigned int", writes.COPY_REMAINING + 4, case.total),
    )
    commands = ["set confirm off", "target sim --memory-size 16M", "load",
                "tbreak *fixture_ready", "run"]
    commands.extend(writes.assignment(kind, hex(addr), value) for kind, addr, value in seed)
    if lockout and not lockout_installed:
        commands.append(writes.assignment("unsigned int", hex(writes.SITE), writes.DISABLE_BRANCH))
    arguments = (writes.ADC0, 0, 0, 0, 0, 1)
    commands.extend(writes.assignment("unsigned int", f"((char*)&fixture_arguments+{4*i})", value)
                    for i, value in enumerate(arguments))
    commands.extend((f"set {{unsigned int}}&fixture_call_psw = {psw:#x}",
                     f"set {{unsigned int}}&fixture_cancel_mode = {2 if case.held else 1}",
                     f"restore cancel-sentinel.dat binary {case.address - 1:#x}",
                     f"restore cancel-payload.dat binary {source:#x}"))
    if case.held:
        commands.extend(("tbreak *fixture_held_done", f"tbreak *{writes.COPY_COMPLETE:#x}",
                         "continue", close_state_line("HELD"), "delete breakpoints"))
    commands.extend(("tbreak *fixture_close_done", "tbreak *0x2870", "continue", close_state_line("CLOSED"),
                     "delete breakpoints", "tbreak *fixture_close_done", "tbreak *0x2870", "continue",
                     close_state_line("REPEATED"), "delete breakpoints",
                     "tbreak *fixture_adc_done", f"tbreak *{writes.COPY_COMPLETE:#x}",
                     "tbreak *0x2d88", "continue", close_state_line("ADC"),
                     f"dump binary memory cancel-result.dat {case.address - 1:#x} {case.address + width + 1:#x}"))
    (work / "cancel.gdb").write_text("\n".join(commands) + "\n", encoding="ascii")
    try:
        output = run(debugger, "--batch", "-nx", "-x", "cancel.gdb", "fixture.elf")
    except subprocess.CalledProcessError as error:
        raise ValueError(f"{case.name} PSW={psw:#x} lockout={lockout}: "
                         + (error.stderr or str(error).encode()).decode(errors="replace")) from error

    def address_of(symbol):
        return symbols[symbol]["address"]

    before = (flags, 0x80, case.remaining, case.total, case.checksum, source, 0, reply)
    if case.held:
        held = writes.observation(output, "HELD")
        if held[:2] != (address_of("fixture_held_done"), 1) or held[3:] != before:
            raise ValueError(f"{case.name}: did not enter close with an unchanged held copy: {held}")
    remaining, total = (0, 0) if case.canceled else (case.remaining, case.total)
    closed = (0x10, 0x80, remaining, total, case.checksum, source, 0, reply)
    for tag in ("CLOSED", "REPEATED"):
        observed = writes.observation(output, tag)
        if (observed[0] != address_of("fixture_close_done") or observed[2] & 0x40 != psw & 0x40
                or observed[3:] != closed):
            raise ValueError(f"{case.name}: {tag.lower()} changed unrelated state: {observed}")
    adc = writes.observation(output, "ADC")
    wrote = int(case.completes)
    summed = min(case.checksum, writes.COPY_SLICE) if case.canceled else 0
    expected_pc = writes.COPY_COMPLETE if case.completes else address_of("fixture_adc_done")
    expected_after_adc = (0x10, 0x80, remaining - wrote, total, case.checksum - summed,
                          source + summed, sum(payload[:summed]) & 0xffff, reply)
    expected_ram = sentinel if not wrote else sentinel[:1] + payload[:1] + sentinel[2:]
    if (adc[0] != expected_pc or adc[3:] != expected_after_adc
            or (not wrote and adc[1] != int(bool(remaining or case.checksum - summed)))
            or (work / "cancel-result.dat").read_bytes() != expected_ram):
        raise ValueError(f"{case.name}: unexpected copy completion or ADC0 state: {adc}")
    return {"case": case.name, "caller_psw": psw, "lockout": lockout, "active_close": case.active,
            "retired": case.canceled, "pending_before": case.remaining, "pending_after_close": remaining,
            "checksum_after_close": case.checksum, "adc_stop": hex(adc[0]), "bytes_written": wrote}


def check(base,compiler,storage_report,placed_elf=None, *, common_layout=None):
    identity=identify_h03(base)
    rom=base.read_bytes()
    if sha256(rom).hexdigest() != identity['sha256']:
        raise ValueError('H03 changed while preparing the service guard fixture')
    blocks=storage_blocks(storage_report.read_bytes(),identity)
    if set(blocks)!={'control','communication','workspace'}:
        raise ValueError('Expected the three measured storage groups')
    service.verify_stock(rom, service.WRITER_SITES)
    pointer = None
    scenario_blocks = blocks
    if common_layout is not None:
        if placed_elf is None:
            raise ValueError("Common layout replay requires its placed early IRQ ELF")
        report = json.loads(common_layout.read_text(encoding="utf-8"))
        model = report.get("early_irq_model", {})
        if report.get("base") != identity or not model.get("service_writers"):
            raise ValueError("Common H03 layout has no linked resident service writers for this ROM")
        pointer = model["irq_pointer"]
        candidate, policy = service.early_service_overlay(rom, placed_elf, model, blocks)
        placement = {"elf_sha256": model["elf_sha256"], "guard_bytes": report["service_writer_resident_bytes"],
                     "policy_ranges": policy, "sites": model["service_writers"], "irq_pointer": pointer,
                     "scope": "common_early_irq"}
        start, end = blocks["control"]
        if end == pointer:
            # The contiguous pointer extends the protected control interval.
            scenario_blocks = dict(blocks, control=(start, pointer + 4))
    elif placed_elf is not None:
        candidate, placement = service.verify_and_overlay(rom, placed_elf, service.policy_ranges(blocks))
    # Existing monitor protection is also applied to PREPARED copies, which
    # originally bypass it. No production range is guessed in this fixture.
    ranges=sorted([*blocks.values(),(0x808578,0x808DB4)])
    if any(end>start for (_,end),(start,_) in zip(ranges,ranges[1:])):
        raise ValueError('The proposed RAM overlaps live service state')
    with TemporaryDirectory(prefix='rbm-h03-service-guard-') as folder:
        work=Path(folder)
        for name in SOURCES:
            (work / name).write_bytes((HERE / name).read_bytes())
        def run(*args):
            return subprocess.run([str(x) for x in args],cwd=work,check=True,
                                  capture_output=True,timeout=40).stdout
        if run(compiler,'-dumpmachine').strip()!=b'm32r-elf':
            raise ValueError('Use a bare-metal M32R compiler')
        flags=[*TARGET,'-Os','-std=c11','-Wall','-Wextra','-Werror','-ffreestanding',
               '-fno-builtin','-ffunction-sections','-fdata-sections','-I.']
        crt=run(compiler,*TARGET,'-print-file-name=crt0.o').decode().strip()
        run(compiler,*flags,'-nostartfiles',crt,SOURCES[0],SOURCES[3],
            '-Wl,--start-group','-lc','-lgloss','-lgcc','-Wl,--end-group','-o','policy.elf')
        policy_test=run(compiler.with_name('m32r-elf-run'+compiler.suffix),'policy.elf').decode().strip()
        if not policy_test.endswith('assertions PASS'):
            raise ValueError('Policy edge-case tests did not finish')
        (work/'policy.c').write_text(service.policy_source(ranges),encoding='ascii')
        fixture=writes.FIXTURE.replace('ld24 lr,#fixture_done','ld24 lr,#fixture_capture_return')
        fixture=fixture.replace('    jmp r3','    ld24 r4,#fixture_call_psw\n    ld r4,@r4\n    mvtc r4,psw\n    jmp r3',1)
        fixture=fixture.replace('fixture_done:\n',
            'fixture_capture_return:\n    mvfc r7,psw\n    ld24 r6,#fixture_return_psw\n    st r7,@r6\nfixture_done:\n')
        fixture=fixture.replace('    .space 24','    .space 24\n    .global fixture_return_psw\nfixture_return_psw:\n    .space 4')
        fixture=fixture.replace('fixture_dispatch:\n', 'fixture_dispatch:\n'
            '    ld24 r4,#fixture_cancel_mode\n    ld r4,@r4\n'
            '    bnez r4,fixture_cancel_sequence\n')
        fixture+=r'''
    .section .fixture_data,"aw",@progbits
    .global fixture_store_ie,fixture_store_count,fixture_call_psw,fixture_cancel_mode
    .global fixture_close_psw
fixture_store_ie: .word 0
fixture_store_count: .word 0
fixture_call_psw: .word 0x41
fixture_cancel_mode: .word 0
fixture_close_psw: .word 0
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
    .p2align 2
    .global fixture_close_done,fixture_held_done,fixture_adc_done
fixture_cancel_sequence:
    addi r4,#-2
    bnez r4,.Lcancel_close_twice
    bl fixture_run_adc
fixture_held_done:
.Lcancel_close_twice:
    bl fixture_run_close
    bl fixture_run_close
    bl fixture_run_adc
fixture_adc_done:
    bra fixture_adc_done
    .p2align 2
fixture_run_close:
    push lr
    ld24 r4,#fixture_call_psw
    ld r4,@r4
    mvtc r4,psw
    bl.l fixture_close
    mvfc r6,psw
    ld24 r7,#fixture_close_psw
    st r6,@r7
fixture_close_done:
    pop lr
    jmp lr
    .p2align 2
fixture_run_adc:
    push lr
    ld24 r4,#fixture_call_psw
    ld r4,@r4
    mvtc r4,psw
    bl.l stock_adc0
    pop lr
    jmp lr
'''
        rom_sections = ' .oem 0 : { *(.oem) }'
        if placed_elf is None:
            fixture=fixture.replace('.section .oem,"ax",@progbits\n    .incbin "h03.dat"',
                '.section .oem_before,"ax",@progbits\n    .incbin "h03.dat",0,0x20000\n'
                '    .section .oem_after,"ax",@progbits\n    .incbin "h03.dat",0x30000,0x50000')
            rom_sections = ''' .oem_before 0 : { *(.oem_before) }
 .guard 0x20000 : { *(.text*) *(.rodata*) }
 .oem_after 0x30000 : { *(.oem_after) }'''
        (work/'fixture.S').write_text(fixture,encoding='ascii')
        linker_script = '''ENTRY(_start)
SECTIONS {
 ROM_SECTIONS
 .fixture 0x100000 : { *(.fixture) }
 .fixture_data : { *(.fixture_data) }
 /DISCARD/ : { *(.note*) *(.comment) }
}
GUARD_LIMIT
stock_selector = 0x003550;
stock_close = 0x002e80;
stock_adc0 = 0x003608;
h03_service_direct_after_entry = 0x002928;
h03_service_stock_span_check = 0x003528;
h03_service_copy_after_entry = 0x002d20;
h03_service_close_after_store = 0x002eA0;
h03_direct_after_store = 0x00297c;
h03_copy_after_store = 0x002de4;
'''
        guard_limit = ('ASSERT(SIZEOF(.guard) <= 0x10000, "Guard exceeds empty model window")'
                       if placed_elf is None else '')
        (work/'fixture.ld').write_text(linker_script.replace('ROM_SECTIONS', rom_sections)
                                     .replace('GUARD_LIMIT', guard_limit), encoding='ascii')
        gdb=compiler.with_name('m32r-elf-gdb'+compiler.suffix)
        if placed_elf is not None:
            (work/'h03.dat').write_bytes(candidate)
            run(compiler,*flags,'-nostdlib','-Wl,-T,fixture.ld','fixture.S','-o','fixture.elf')
            symbols = read_elf(work/'fixture.elf',2)['symbols']
            # Measure writers with the session open. The separate close cases
            # exercise its cancellation of an otherwise unchanged pending copy.
            stack_start, stack_end = placement["policy_ranges"][-1]
            placed_cases = [replace(case, close=False) for case in scenarios(scenario_blocks)]
            placed_cases.extend((
                writes.Case('conditional_stack_edge_direct', writes.DIRECT, stack_start, 1, (0,)),
                writes.Case('conditional_stack_crossing_direct', writes.DIRECT, stack_start - 1, 2, (0,)),
                writes.Case('conditional_psw_edge_deferred', writes.ADC0, stack_end - 1, 1, (0,)),
            ))
            if pointer is not None:
                placed_cases.extend((
                    writes.Case("early_irq_pointer_direct", writes.DIRECT, pointer, 4, (0,)),
                    writes.Case("early_irq_pointer_deferred", writes.ADC0, pointer, 4, (0,)),
                ))
            rows = [writes.run_case(run,work,gdb,case,True,lockout_installed=True)
                    for case in placed_cases]
            close_rows = [check_close(run,work,gdb,symbols,case,psw,True,lockout_installed=True)
                          for case in close_cases(scenario_blocks) for psw in (0,1,0x40,0x41)]
            return {'status':'PASS_PLACED_SERVICE_GUARD_MODEL_ONLY','base':identity,
                    'placement':placement,'guard_with_fixture_policy_bytes':placement['guard_bytes'],
                    'new_mutable_state_bytes':0,'policy_test':policy_test,'native_cases':rows,
                    'close_cases':close_rows,'hardware_tested':False,'flashable_image':None}
        (work/'h03.dat').write_bytes(rom)
        def link():
            run(compiler,*flags,'-nostdlib','-Wl,-T,fixture.ld','fixture.S',
                'h03_service_guard_hooks.S','lfj8_h03_service_guard.c','policy.c','-o','fixture.elf')
        link()
        elf=read_elf(work/'fixture.elf',2)
        patched=bytearray(rom)
        sites=[]
        for site in service.WRITER_SITES:
            target=elf['symbols'][site.target]['address']
            branch=site.branch(target)
            patched[site.address:site.address+4]=branch
            sites.append({'address':hex(site.address),'original':f'{site.stock:08x}',
                          'model_patch':branch.hex(),'target':hex(target)})
        writer_patched=bytearray(patched)
        writer_patched[CLOSE_STORE:CLOSE_STORE+4]=rom[CLOSE_STORE:CLOSE_STORE+4]
        instrumented=bytearray(writer_patched)
        # Simulator-only probes preserve registers/PSW and execute the exact
        # displaced store bundle. First run the original stores without probes.
        for address,word,symbol in ((0x2978,0x2104F000,'fixture_direct_store'),
                                    (0x2DE0,0x23014201,'fixture_copy_store')):
            if int.from_bytes(rom[address:address+4],'big')!=word: raise ValueError('Store bundle changed')
            target=elf['symbols'][symbol]['address']
            instrumented[address:address+4]=(0xFF000000 | ((target-address)//4 & 0xFFFFFF)).to_bytes(4,'big')
        (work/'h03.dat').write_bytes(patched)
        link()
        cancel_rows = [check_close(run,work,gdb,elf['symbols'],case,psw,lockout)
                       for case in close_cases(blocks)
                       for psw in (0,1,0x40,0x41)
                       for lockout in (False,True)]
        rows=[]
        for probes,variant in ((False,writer_patched),(True,instrumented)):
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
            'policy_test':policy_test,'native_cases':rows,'close_cases':cancel_rows,
            'simulation_only_instrumentation':['Relocated 2978 and 2DE0 store bundles capture PSW/IE and count stores; registers and PSW restored'],
            'input_sha256_lf':{name:sha256((HERE/name).read_bytes().replace(b'\r\n',b'\n')).hexdigest() for name in SOURCES},
            'limits':['Four hooks below 0x8000; programmer support not established',
                      'A guarded copy stays busy until the accepted session-close path retires it',
                      'Final RAM/stack ranges and all write paths still require qualification',
                      'SBI/DMA, Virtual Flash residency and interrupt latency not proven',
                      'Model code at 0x20000 is isolated; final combined placement is not implemented'],
            'hardware_tested':False,'flashable_image':None}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('base','gcc','storage-report','out'): parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--placed-elf', type=Path, help='replay the exact linked service protection')
    parser.add_argument('--common-layout', type=Path, help='layout.json for a common early IRQ ELF')
    args=parser.parse_args()
    inputs = [p for p in (args.base,args.gcc,args.storage_report,args.placed_elf,args.common_layout) if p is not None]
    if args.out.suffix.lower()!='.json' or any(args.out.resolve()==p.resolve() for p in inputs):
        parser.error('Use a separate JSON report')
    if args.out.exists():
        if any(args.out.samefile(p) for p in inputs):
            parser.error('The report must not alias an input')
        args.out.unlink()
    try:
        report=check(args.base,args.gcc.resolve(),args.storage_report,args.placed_elf,
                     common_layout=args.common_layout)
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({k:report[k] for k in ('status','guard_with_fixture_policy_bytes','new_mutable_state_bytes','policy_test','flashable_image')}))
        print('native writer cases:',len(report['native_cases']))
        print('native close cases:',len(report['close_cases']))
    except (KeyError,OSError,ValueError,subprocess.SubprocessError) as error:
        detail=getattr(error,'stderr',None) or str(error)
        parser.exit(1,(detail.decode(errors='replace') if isinstance(detail,bytes) else detail)+'\n')


if __name__=='__main__': main()
